#!/usr/bin/env python3
"""
Warbird Optuna Hub
==================

Card-based local dashboard for multi-indicator and multi-strategy Optuna studies.

What it does:
1) Reads indicator/strategy registry from `scripts/optuna/indicator_registry.json`
2) Ensures the Optuna workspace root exists
3) Reads study metrics from each `study.db`
4) Surfaces profile wiring and top-N export readiness per lane
5) Shows AutoGluon/Optuna stack health (including AutoGluon 1.5)
6) Optionally launches one `optuna-dashboard` child process on demand per detected DB
7) Serves a slick operator UI at http://<host>:<port>

No training is executed by this script.
"""

from __future__ import annotations

import argparse
import atexit
import html
import importlib.util
import json
import re
import shlex
import shutil
import signal
import sqlite3
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib import metadata
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


REPO_ROOT = Path(__file__).resolve().parents[2]
REGISTRY_PATH = Path(__file__).resolve().with_name("indicator_registry.json")
LOG_ROOT = Path("/tmp/warbird-optuna-hub")
PUBLIC_ASSETS = {
    "/assets/chart_watermark.svg": REPO_ROOT / "public" / "chart_watermark.svg",
    "/assets/warbird-logo.svg": REPO_ROOT / "public" / "warbird-logo.svg",
    "/assets/warbird-icon.svg": REPO_ROOT / "public" / "warbird-icon.svg",
}

DEFAULT_HOST = "localhost"
DEFAULT_PORT = 8090
DEFAULT_CHILD_PORT_START = 8100
REFRESH_SECONDS = 15

# Ensure dotted profile modules like "scripts.optuna.<name>" can resolve when
# this script is launched via absolute file path.
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.optuna.paths import WORKSPACES_ROOT, experiments_dir, workspace_dir


@dataclass(frozen=True)
class IndicatorSpec:
    key: str
    name: str
    category: str
    surface_type: str
    pine_file: str
    notes: str = ""
    storage_mode: str = "standard"
    profile_module: str = ""
    profile_builtin: str = ""
    default_study_name: str = ""
    topn_filename: str = "top5.json"


@dataclass
class ChildRuntime:
    key: str
    port: int
    process: subprocess.Popen[Any] | None
    db_path: Path
    log_path: Path
    err: str | None = None


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _parse_json_scalar(value_json: str | None, fallback: float = 0.0) -> float:
    if value_json is None:
        return fallback
    try:
        parsed = json.loads(value_json)
        if isinstance(parsed, (int, float)):
            return float(parsed)
        if isinstance(parsed, str):
            return float(parsed)
    except Exception:
        pass
    return fallback


def _parse_json_text(value_json: str | None, fallback: str = "") -> str:
    if value_json is None:
        return fallback
    try:
        parsed = json.loads(value_json)
        return str(parsed)
    except Exception:
        return fallback


def _h(value: Any) -> str:
    return html.escape("" if value is None else str(value))


def _display_indicator_name(value: Any) -> str:
    label = str(value).replace("_", " ")
    label = re.sub(r"\([^)]*\bv\d+\b[^)]*\)", "", label, flags=re.IGNORECASE)
    label = re.sub(r"(?<![A-Za-z0-9])v\d+(?![A-Za-z0-9])", "", label, flags=re.IGNORECASE)
    label = re.sub(r"\s+", " ", label).strip()
    if label.islower():
        acronyms = {"ml": "ML", "rsi": "RSI", "nfe": "NFE", "qfp": "QFP", "mes": "MES"}
        label = " ".join(acronyms.get(token.lower(), token.capitalize()) for token in label.split())
    return label or str(value)


def _display_short_label(value: Any) -> str:
    label = str(value).replace("_", " ").replace("-", " ")
    label = re.sub(r"\s+", " ", label).strip()
    if not label:
        return ""
    acronyms = {
        "dema": "DEMA",
        "dsr": "DSR",
        "ema": "EMA",
        "hl2": "HL2",
        "hlc3": "HLC3",
        "ml": "ML",
        "nfe": "NFE",
        "ohlc4": "OHLC4",
        "qfp": "QFP",
        "rsi": "RSI",
        "mes": "MES",
        "sma": "SMA",
        "tema": "TEMA",
        "vwma": "VWMA",
        "wma": "WMA",
    }
    return " ".join(acronyms.get(token.lower(), token.capitalize()) for token in label.split())


def _display_param_label(value: Any) -> str:
    raw = str(value)
    labels = {
        "confHighInput": "High Confluence",
        "confLowInput": "Low Confluence",
        "fatigueBarsInput": "Fatigue Confirmation Bars",
        "knnKInput": "KNN Neighbors",
        "knnWindowInput": "KNN Training Window",
        "presetInput": "Preset",
        "sigLenInput": "Signal Period",
        "sigTypeInput": "Signal Smoothing",
        "smoothTypeInput": "Engine Smoothing",
        "sourceInput": "Source",
        "useConfluenceGate": "Use Confluence Gate",
        "useKnnGate": "Use KNN Gate",
        "useVolumeFlowGate": "Use Volume Flow Gate",
        "useZoneExitSignals": "Use Zone Exit Signals",
    }
    if raw in labels:
        return labels[raw]
    cleaned = re.sub(r"Input$", "", raw)
    cleaned = re.sub(r"(?<!^)([A-Z])", r" \1", cleaned)
    cleaned = cleaned.replace("Knn", "KNN").replace("Rsi", "RSI").replace("Ml", "ML")
    return re.sub(r"\s+", " ", cleaned).strip()


def _display_metric_label(value: Any) -> str:
    raw = str(value)
    labels = {
        "objective_score": "Objective Score",
        "quality_events": "Quality Events",
        "primary_signal_quality": "Primary Signal Quality",
        "primary_signal_precision": "Primary Signal Precision",
        "primary_signal_count": "Primary Signal Count",
        "primary_signals_per_day": "Primary Signals Per Day",
        "fatigue_warning_quality": "Fatigue Warning Quality",
        "fatigue_signal_precision": "Fatigue Signal Precision",
        "confluence_calibration": "Confluence Calibration",
        "knn_bias_quality": "KNN Bias Quality",
        "noise_control": "Noise Control",
        "win_rate": "Win Rate",
        "pf": "Profit Factor",
        "max_dd": "Max Drawdown",
        "objective_metric": "Objective Metric",
        "ranking_policy": "Ranking Policy",
        "window_start": "Window Start",
    }
    if raw in labels:
        return labels[raw]
    cleaned = raw.replace("_", " ")
    return _display_short_label(cleaned)


def _display_scalar(value: Any) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        if value.is_integer():
            return str(int(value))
        return f"{value:.4f}".rstrip("0").rstrip(".")
    return str(value)


def _parse_json_value(value_json: str | None) -> Any:
    if value_json is None:
        return None
    try:
        return json.loads(value_json)
    except Exception:
        return value_json


def _display_param_value(param_value: Any, distribution_json: str | None) -> str:
    try:
        parsed = json.loads(distribution_json or "{}")
    except Exception:
        parsed = {}
    if parsed.get("name") == "CategoricalDistribution":
        choices = parsed.get("attributes", {}).get("choices", [])
        idx = _safe_int(param_value, -1)
        if 0 <= idx < len(choices):
            choice = choices[idx]
            return _display_short_label(choice) if isinstance(choice, str) else _display_scalar(choice)
    return _display_scalar(_safe_float(param_value, 0.0))


def _display_metric_value(key: str, value: Any) -> str:
    if key in {"objective_metric", "ranking_policy"}:
        return _display_short_label(value)
    return _display_scalar(value)


def _display_host(host: str) -> str:
    if host in {"127.0.0.1", "::1", "localhost"}:
        return "localhost"
    return host


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text())


def load_registry(path: Path) -> list[IndicatorSpec]:
    if not path.exists():
        raise SystemExit(f"Registry not found: {path}")
    raw = _load_json(path)
    if not isinstance(raw, list):
        raise SystemExit(f"Invalid registry format in {path}: expected JSON list")

    specs: list[IndicatorSpec] = []
    seen: set[str] = set()
    for row in raw:
        if not isinstance(row, dict):
            raise SystemExit("Invalid registry row: expected object")
        key = str(row.get("key", "")).strip()
        if not key:
            raise SystemExit("Invalid registry row: missing key")
        if key in seen:
            raise SystemExit(f"Duplicate indicator key in registry: {key}")
        seen.add(key)

        default_study_name = str(row.get("default_study_name", "")).strip()
        if not default_study_name:
            default_study_name = "sats_2025_wr_pf" if key == "sats_ps" else f"{key}_wr_pf"

        specs.append(
            IndicatorSpec(
                key=key,
                name=str(row.get("name", key)).strip(),
                category=str(row.get("category", "uncategorized")).strip(),
                surface_type=str(row.get("surface_type", "indicator")).strip(),
                pine_file=str(row.get("pine_file", "")).strip(),
                notes=str(row.get("notes", "")).strip(),
                storage_mode=str(row.get("storage_mode", "standard")).strip(),
                profile_module=str(row.get("profile_module", "")).strip(),
                profile_builtin=str(row.get("profile_builtin", "")).strip(),
                default_study_name=default_study_name,
                topn_filename=str(row.get("topn_filename", "top5.json")).strip() or "top5.json",
            )
        )
    return specs


def resolve_indicator_dir(spec: IndicatorSpec) -> Path:
    return workspace_dir(spec.key)


def ensure_layout(specs: list[IndicatorSpec]) -> None:
    _ = specs
    WORKSPACES_ROOT.mkdir(parents=True, exist_ok=True)


def detect_stack_health() -> dict[str, Any]:
    versions: dict[str, str] = {}
    availability: dict[str, bool] = {}

    def _version(pkg_name: str) -> str | None:
        try:
            return metadata.version(pkg_name)
        except Exception:
            return None

    versions["python"] = sys.version.split()[0]
    optuna_v = _version("optuna")
    optuna_dash_v = _version("optuna-dashboard")
    if optuna_dash_v is None:
        dash_bin = REPO_ROOT / ".venv" / "bin" / "optuna-dashboard"
        if not dash_bin.exists():
            resolved_dash_bin = shutil.which("optuna-dashboard")
            dash_bin = Path(resolved_dash_bin) if resolved_dash_bin else Path()
        if dash_bin.exists():
            try:
                result = subprocess.run(
                    [str(dash_bin), "--version"],
                    check=True,
                    capture_output=True,
                    text=True,
                    timeout=2,
                    cwd=str(REPO_ROOT),
                )
                optuna_dash_v = (result.stdout or result.stderr).strip() or "available"
            except Exception:
                optuna_dash_v = "available"
    ag_v = _version("autogluon.tabular")

    versions["optuna"] = optuna_v or "not-installed"
    versions["optuna_dashboard"] = optuna_dash_v or "not-installed"
    versions["autogluon_tabular"] = ag_v or "not-installed"

    availability["optuna"] = optuna_v is not None
    availability["optuna_dashboard"] = optuna_dash_v is not None
    availability["autogluon_tabular"] = ag_v is not None
    availability["autogluon_1_5"] = bool(ag_v and ag_v.startswith("1.5."))

    status = "ready"
    note = "AutoGluon 1.5 stack is ready."
    if not availability["autogluon_tabular"]:
        status = "warn"
        note = "AutoGluon not installed in current Python environment."
    elif not availability["autogluon_1_5"]:
        status = "warn"
        note = f"AutoGluon installed ({versions['autogluon_tabular']}) but not 1.5.x."

    return {
        "versions": versions,
        "availability": availability,
        "status": status,
        "note": note,
    }


def assess_profile_wiring(spec: IndicatorSpec) -> dict[str, str]:
    if spec.profile_builtin:
        return {
            "status": "ready",
            "label": f"Built-in profile: {spec.profile_builtin}",
        }
    if spec.profile_module:
        try:
            found = importlib.util.find_spec(spec.profile_module)
        except ModuleNotFoundError:
            found = None
        if found is None:
            return {
                "status": "missing",
                "label": f"Missing module: {spec.profile_module}",
            }
        return {
            "status": "ready",
            "label": f"Profile module: {spec.profile_module}",
        }
    return {
        "status": "missing",
        "label": "No profile wired",
    }


def load_topn_stats(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"exists": False, "count": 0, "best_wr": None, "best_pf": None, "best_score": None, "best_events": None, "error": None}
    try:
        payload = _load_json(path)
        if not isinstance(payload, list):
            return {
                "exists": True,
                "count": 0,
                "best_wr": None,
                "best_pf": None,
                "best_score": None,
                "best_events": None,
                "error": "top-N file is not a JSON list",
            }
        if len(payload) == 0:
            return {"exists": True, "count": 0, "best_wr": None, "best_pf": None, "best_score": None, "best_events": None, "error": None}
        top = payload[0] if isinstance(payload[0], dict) else {}
        top_metrics = top.get("metrics", {}) if isinstance(top.get("metrics"), dict) else {}
        return {
            "exists": True,
            "count": len(payload),
            "best_wr": _safe_float(top.get("win_rate"), 0.0) if top else None,
            "best_pf": _safe_float(top.get("pf"), 0.0) if top else None,
            "best_score": _safe_float(top_metrics.get("signal_quality_score"), _safe_float(top.get("objective_score"), 0.0)) if top else None,
            "best_events": _safe_int(top.get("events"), _safe_int(top_metrics.get("quality_events"), 0)) if top else None,
            "error": None,
        }
    except Exception as exc:
        return {
            "exists": True,
            "count": 0,
            "best_wr": None,
            "best_pf": None,
            "best_score": None,
            "best_events": None,
            "error": str(exc),
        }


def build_run_command(spec: IndicatorSpec) -> str:
    parts = [
        "python scripts/optuna/runner.py",
        f"--indicator-key {spec.key}",
    ]
    if spec.profile_builtin:
        parts.append(f"--profile {spec.profile_builtin}")
    elif spec.profile_module:
        parts.append(f"--profile-module {spec.profile_module}")
    else:
        parts.append(f"--profile-module scripts.optuna.{spec.key}_profile")
    parts.append(f"--study-name {shlex.quote(spec.default_study_name)}")
    parts.append("--n-trials 300")
    parts.append("--resume")
    return " \\\n  ".join(parts)


def load_study_stats(db_path: Path, target_study_name: str) -> dict[str, Any]:
    if not db_path.exists() or db_path.stat().st_size == 0:
        return {
            "exists": False,
            "study_count": 0,
            "target_study_exists": False,
            "trial_count": 0,
            "complete_count": 0,
            "running_count": 0,
            "pruned_count": 0,
            "fail_count": 0,
            "best": None,
            "last_complete": None,
            "error": None,
        }

    con: sqlite3.Connection | None = None
    try:
        con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        cur = con.cursor()

        study_count = _safe_int(cur.execute("SELECT COUNT(*) FROM studies").fetchone()[0])
        target_study_exists = _safe_int(
            cur.execute("SELECT COUNT(*) FROM studies WHERE study_name = ?", (target_study_name,)).fetchone()[0]
        ) > 0
        trial_count = _safe_int(
            cur.execute(
                """
                SELECT COUNT(*)
                FROM trials t
                JOIN studies s ON s.study_id = t.study_id
                WHERE s.study_name = ?
                """,
                (target_study_name,),
            ).fetchone()[0]
        )
        complete_count = _safe_int(
            cur.execute(
                """
                SELECT COUNT(*)
                FROM trials t
                JOIN studies s ON s.study_id = t.study_id
                WHERE s.study_name = ? AND t.state = 'COMPLETE'
                """,
                (target_study_name,),
            ).fetchone()[0]
        )
        running_count = _safe_int(
            cur.execute(
                """
                SELECT COUNT(*)
                FROM trials t
                JOIN studies s ON s.study_id = t.study_id
                WHERE s.study_name = ? AND t.state = 'RUNNING'
                """,
                (target_study_name,),
            ).fetchone()[0]
        )
        pruned_count = _safe_int(
            cur.execute(
                """
                SELECT COUNT(*)
                FROM trials t
                JOIN studies s ON s.study_id = t.study_id
                WHERE s.study_name = ? AND t.state = 'PRUNED'
                """,
                (target_study_name,),
            ).fetchone()[0]
        )
        fail_count = _safe_int(
            cur.execute(
                """
                SELECT COUNT(*)
                FROM trials t
                JOIN studies s ON s.study_id = t.study_id
                WHERE s.study_name = ? AND t.state = 'FAIL'
                """,
                (target_study_name,),
            ).fetchone()[0]
        )

        trial_rows = cur.execute(
            """
            SELECT
                t.trial_id,
                t.number,
                t.datetime_complete,
                s.study_name,
                tv.value
            FROM trials t
            JOIN studies s ON s.study_id = t.study_id
            LEFT JOIN trial_values tv ON tv.trial_id = t.trial_id AND tv.objective = 0
            WHERE t.state = 'COMPLETE' AND s.study_name = ?
            """,
            (target_study_name,),
        ).fetchall()

        attrs: dict[int, dict[str, str]] = {}
        for trial_id, key, value_json in cur.execute(
            """
            SELECT tua.trial_id, tua.key, tua.value_json
            FROM trial_user_attributes tua
            JOIN trials t ON t.trial_id = tua.trial_id
            JOIN studies s ON s.study_id = t.study_id
            WHERE s.study_name = ? AND tua.key IN (
                'win_rate', 'pf', 'trades', 'max_dd',
                'objective_score', 'objective_metric',
                'signal_quality_score', 'quality_events',
                'primary_signal_quality', 'confluence_calibration',
                'volume_flow_quality', 'fatigue_warning_quality',
                'knn_bias_quality', 'noise_control'
            )
            """,
            (target_study_name,),
        ).fetchall():
            attrs.setdefault(_safe_int(trial_id), {})[str(key)] = value_json

        def trial_rank(row: tuple[Any, ...]) -> tuple[float, float, float, float, int]:
            trial_id = _safe_int(row[0])
            objective_val = _safe_float(row[4], 0.0)
            ta = attrs.get(trial_id, {})
            objective_score = _parse_json_scalar(ta.get("objective_score"), objective_val)
            win_rate = _parse_json_scalar(ta.get("win_rate"), objective_val)
            pf = _parse_json_scalar(ta.get("pf"), 0.0)
            max_dd = _parse_json_scalar(ta.get("max_dd"), float("inf"))
            trades = int(round(_parse_json_scalar(ta.get("trades"), 0.0)))
            return (objective_score, win_rate, pf, -max_dd, trades)

        best = None
        if trial_rows:
            best_row = max(trial_rows, key=trial_rank)
            best_trial_id = _safe_int(best_row[0])
            best_attrs = attrs.get(best_trial_id, {})
            best = {
                "trial_number": _safe_int(best_row[1]),
                "study_name": str(best_row[3]),
                "objective": _safe_float(best_row[4], 0.0),
                "objective_score": _parse_json_scalar(best_attrs.get("objective_score"), _safe_float(best_row[4], 0.0)),
                "objective_metric": _parse_json_text(best_attrs.get("objective_metric"), ""),
                "win_rate": _parse_json_scalar(best_attrs.get("win_rate"), _safe_float(best_row[4], 0.0)),
                "pf": _parse_json_scalar(best_attrs.get("pf"), 0.0),
                "trades": int(round(_parse_json_scalar(best_attrs.get("trades"), 0.0))),
                "max_dd": _parse_json_scalar(best_attrs.get("max_dd"), 0.0),
                "signal_quality_score": _parse_json_scalar(best_attrs.get("signal_quality_score"), 0.0),
                "quality_events": int(round(_parse_json_scalar(best_attrs.get("quality_events"), 0.0))),
                "primary_signal_quality": _parse_json_scalar(best_attrs.get("primary_signal_quality"), 0.0),
                "confluence_calibration": _parse_json_scalar(best_attrs.get("confluence_calibration"), 0.0),
                "volume_flow_quality": _parse_json_scalar(best_attrs.get("volume_flow_quality"), 0.0),
                "fatigue_warning_quality": _parse_json_scalar(best_attrs.get("fatigue_warning_quality"), 0.0),
                "knn_bias_quality": _parse_json_scalar(best_attrs.get("knn_bias_quality"), 0.0),
                "noise_control": _parse_json_scalar(best_attrs.get("noise_control"), 0.0),
            }

        last_complete = None
        for row in trial_rows:
            dt = row[2]
            if dt is not None:
                dt_str = str(dt)
                if last_complete is None or dt_str > last_complete:
                    last_complete = dt_str

        return {
            "exists": True,
            "study_count": study_count,
            "target_study_exists": target_study_exists,
            "trial_count": trial_count,
            "complete_count": complete_count,
            "running_count": running_count,
            "pruned_count": pruned_count,
            "fail_count": fail_count,
            "best": best,
            "last_complete": last_complete,
            "error": None,
        }
    except Exception as exc:
        return {
            "exists": True,
            "study_count": 0,
            "target_study_exists": False,
            "trial_count": 0,
            "complete_count": 0,
            "running_count": 0,
            "pruned_count": 0,
            "fail_count": 0,
            "best": None,
            "last_complete": None,
            "error": str(exc),
        }
    finally:
        if con is not None:
            con.close()


def _clean_study_title(study_name: str) -> str:
    title = study_name.replace("_", " ")
    title = re.sub(r"\bv\d+\b", "", title, flags=re.IGNORECASE)
    title = re.sub(r"\bwr\b", "Win Rate", title, flags=re.IGNORECASE)
    title = re.sub(r"\bpf\b", "Profit Factor", title, flags=re.IGNORECASE)
    title = re.sub(r"\s+", " ", title).strip()
    if not title.islower():
        return title
    acronyms = {
        "ml": "ML",
        "rsi": "RSI",
        "nfe": "NFE",
        "qfp": "QFP",
        "mes": "MES",
    }
    return " ".join(acronyms.get(token.lower(), token.capitalize()) for token in title.split())


def _study_purpose(study_title: str) -> str:
    lower = study_title.lower()
    if "baseline" in lower:
        return "Baseline comparison run for the current indicator defaults."
    if "volume" in lower:
        return "Volume Flow calibration and validation on real MES volume."
    if "signal" in lower:
        return "Signal-quality optimization for entries, reversals, and confirmation gates."
    if "win rate" in lower or "profit factor" in lower:
        return "Win-rate and profit-factor optimization for the active indicator contract."
    return "Optimization study for this indicator lane."


def load_workspace_studies(db_path: Path) -> list[dict[str, Any]]:
    if not db_path.exists() or db_path.stat().st_size == 0:
        return []

    con: sqlite3.Connection | None = None
    try:
        con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        cur = con.cursor()
        rows = cur.execute(
            """
            SELECT
                s.study_id,
                s.study_name,
                COALESCE(sd.direction, ''),
                COUNT(t.trial_id),
                SUM(CASE WHEN t.state = 'COMPLETE' THEN 1 ELSE 0 END),
                SUM(CASE WHEN t.state = 'RUNNING' THEN 1 ELSE 0 END),
                SUM(CASE WHEN t.state = 'FAIL' THEN 1 ELSE 0 END),
                MAX(t.datetime_complete)
            FROM studies s
            LEFT JOIN study_directions sd ON sd.study_id = s.study_id AND sd.objective = 0
            LEFT JOIN trials t ON t.study_id = s.study_id
            GROUP BY s.study_id, s.study_name, sd.direction
            ORDER BY s.study_id DESC
            """
        ).fetchall()

        studies: list[dict[str, Any]] = []
        for study_id, study_name, direction, trials, complete, running, fail, last_complete in rows:
            best_score = cur.execute(
                """
                SELECT MAX(tv.value)
                FROM trials t
                JOIN trial_values tv ON tv.trial_id = t.trial_id AND tv.objective = 0
                WHERE t.study_id = ? AND t.state = 'COMPLETE'
                """,
                (_safe_int(study_id),),
            ).fetchone()[0]
            title = _clean_study_title(str(study_name))
            studies.append(
                {
                    "study_id": _safe_int(study_id),
                    "study_name": str(study_name),
                    "title": title,
                    "purpose": _study_purpose(title),
                    "direction": str(direction or "MAXIMIZE"),
                    "trial_count": _safe_int(trials),
                    "complete_count": _safe_int(complete),
                    "running_count": _safe_int(running),
                    "fail_count": _safe_int(fail),
                    "last_complete": str(last_complete) if last_complete is not None else None,
                    "best_score": _safe_float(best_score, 0.0) if best_score is not None else None,
                }
            )
        return studies
    except Exception:
        return []
    finally:
        if con is not None:
            con.close()


def load_workspace_study_detail(db_path: Path, study_id: int) -> dict[str, Any] | None:
    if not db_path.exists() or db_path.stat().st_size == 0:
        return None

    summaries = {study["study_id"]: study for study in load_workspace_studies(db_path)}
    summary = summaries.get(study_id)
    if summary is None:
        return None

    con: sqlite3.Connection | None = None
    try:
        con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        cur = con.cursor()
        order_dir = "ASC" if str(summary["direction"]).upper() == "MINIMIZE" else "DESC"
        trial_rows = cur.execute(
            f"""
            SELECT
                t.trial_id,
                t.number,
                t.state,
                t.datetime_start,
                t.datetime_complete,
                tv.value
            FROM trials t
            LEFT JOIN trial_values tv ON tv.trial_id = t.trial_id AND tv.objective = 0
            WHERE t.study_id = ? AND t.state = 'COMPLETE'
            ORDER BY tv.value {order_dir}, t.number ASC
            LIMIT 12
            """,
            (study_id,),
        ).fetchall()

        top_trials = [
            {
                "trial_id": _safe_int(trial_id),
                "number": _safe_int(number),
                "state": str(state),
                "started": str(started) if started is not None else None,
                "completed": str(completed) if completed is not None else None,
                "score": _safe_float(score, 0.0) if score is not None else None,
            }
            for trial_id, number, state, started, completed, score in trial_rows
        ]

        best_trial = top_trials[0] if top_trials else None
        best_trial_id = _safe_int(best_trial["trial_id"]) if best_trial else None

        params: list[dict[str, str]] = []
        metrics: list[dict[str, str]] = []
        if best_trial_id is not None:
            for param_name, param_value, distribution_json in cur.execute(
                """
                SELECT param_name, param_value, distribution_json
                FROM trial_params
                WHERE trial_id = ?
                ORDER BY param_name
                """,
                (best_trial_id,),
            ).fetchall():
                params.append(
                    {
                        "name": str(param_name),
                        "label": _display_param_label(param_name),
                        "value": _display_param_value(param_value, distribution_json),
                    }
                )

            metric_priority = [
                "objective_score",
                "quality_events",
                "primary_signal_quality",
                "primary_signal_precision",
                "primary_signal_count",
                "primary_signals_per_day",
                "fatigue_warning_quality",
                "fatigue_signal_precision",
                "confluence_calibration",
                "knn_bias_quality",
                "noise_control",
                "win_rate",
                "pf",
                "max_dd",
                "objective_metric",
                "ranking_policy",
                "window_start",
            ]
            raw_attrs = {
                str(key): _parse_json_value(value_json)
                for key, value_json in cur.execute(
                    """
                    SELECT "key", value_json
                    FROM trial_user_attributes
                    WHERE trial_id = ?
                    """,
                    (best_trial_id,),
                ).fetchall()
            }
            for key in metric_priority:
                if key in raw_attrs:
                    metrics.append(
                        {
                            "name": key,
                            "label": _display_metric_label(key),
                            "value": _display_metric_value(key, raw_attrs[key]),
                        }
                    )

        return {
            **summary,
            "best_trial": best_trial,
            "top_trials": top_trials,
            "params": params,
            "metrics": metrics,
        }
    except Exception:
        return None
    finally:
        if con is not None:
            con.close()


class ChildManager:
    def __init__(self, optuna_dashboard_bin: str, host: str, port_start: int):
        self.optuna_dashboard_bin = optuna_dashboard_bin
        self.host = host
        self.port_start = port_start
        self.children: dict[str, ChildRuntime] = {}

    def _desired_port(self, ordered_keys: list[str], key: str) -> int:
        try:
            idx = ordered_keys.index(key)
        except ValueError:
            idx = len(ordered_keys)
        return self.port_start + idx

    def _start_child(self, key: str, db_path: Path, port: int) -> ChildRuntime:
        LOG_ROOT.mkdir(parents=True, exist_ok=True)
        log_path = LOG_ROOT / f"{key}.log"
        log_file = log_path.open("a", encoding="utf-8")
        cmd = [
            self.optuna_dashboard_bin,
            f"sqlite:///{db_path}",
            "--host",
            self.host,
            "--port",
            str(port),
        ]
        try:
            process = subprocess.Popen(
                cmd,
                stdout=log_file,
                stderr=subprocess.STDOUT,
                cwd=str(REPO_ROOT),
            )
            time.sleep(0.25)
            err = None
            if process.poll() is not None:
                err = f"child exited with code {process.returncode}"
            return ChildRuntime(
                key=key,
                port=port,
                process=process,
                db_path=db_path,
                log_path=log_path,
                err=err,
            )
        except Exception as exc:
            return ChildRuntime(
                key=key,
                port=port,
                process=None,
                db_path=db_path,
                log_path=log_path,
                err=f"failed to launch child: {exc}",
            )

    def _stop_child(self, key: str) -> None:
        runtime = self.children.pop(key, None)
        if runtime is None:
            return
        proc = runtime.process
        if proc is None:
            return
        if proc.poll() is None:
            try:
                proc.terminate()
                proc.wait(timeout=3)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass

    def ensure_child(self, ordered_keys: list[str], key: str, db_path: Path) -> ChildRuntime:
        runtime = self.children.get(key)
        if runtime is not None and runtime.process is not None and runtime.process.poll() is None:
            runtime.err = None
            return runtime
        if runtime is not None:
            self._stop_child(key)
        port = self._desired_port(ordered_keys, key)
        runtime = self._start_child(key=key, db_path=db_path, port=port)
        self.children[key] = runtime
        return runtime

    def shutdown(self) -> None:
        for key in list(self.children.keys()):
            self._stop_child(key)

    def card_link(self, key: str) -> str | None:
        runtime = self.children.get(key)
        if runtime is None or runtime.process is None:
            return None
        if runtime.process.poll() is not None:
            return None
        return f"http://{_display_host(self.host)}:{runtime.port}"

    def card_error(self, key: str) -> str | None:
        runtime = self.children.get(key)
        if runtime is None:
            return None
        if runtime.err:
            return runtime.err
        if runtime.process is None:
            return "child process unavailable"
        if runtime.process.poll() is not None:
            return f"child exited with code {runtime.process.returncode}"
        return None


class HubState:
    def __init__(
        self,
        specs: list[IndicatorSpec],
        host: str,
        port: int,
        spawn_children: bool,
        child_manager: ChildManager | None,
    ):
        self.specs = specs
        self.host = host
        self.port = port
        self.spawn_children = spawn_children
        self.child_manager = child_manager
        self.stack_health = detect_stack_health()
        self.profile_health = {spec.key: assess_profile_wiring(spec) for spec in specs}

    def snapshot(self) -> dict[str, Any]:
        cards: list[dict[str, Any]] = []
        for spec in self.specs:
            indicator_dir = resolve_indicator_dir(spec)
            if not indicator_dir.exists():
                continue
            exp_dir = experiments_dir(spec.key)
            db_path = indicator_dir / "study.db"
            topn_path = indicator_dir / spec.topn_filename

            stats = load_study_stats(db_path, spec.default_study_name)
            topn = load_topn_stats(topn_path)
            profile = self.profile_health.get(spec.key, {"status": "missing", "label": "No profile wired"})
            run_cmd = build_run_command(spec)

            card = {
                "key": spec.key,
                "name": spec.name,
                "category": spec.category,
                "surface_type": spec.surface_type,
                "pine_file": spec.pine_file,
                "notes": spec.notes,
                "indicator_dir": str(indicator_dir),
                "experiments_dir": str(exp_dir),
                "db_path": str(db_path),
                "db_exists": stats["exists"],
                "study_count": stats["study_count"],
                "target_study_exists": stats["target_study_exists"],
                "trial_count": stats["trial_count"],
                "complete_count": stats["complete_count"],
                "running_count": stats["running_count"],
                "pruned_count": stats["pruned_count"],
                "fail_count": stats["fail_count"],
                "best": stats["best"],
                "last_complete": stats["last_complete"],
                "db_error": stats["error"],
                "topn_path": str(topn_path),
                "topn_exists": topn["exists"],
                "topn_count": topn["count"],
                "topn_best_wr": topn["best_wr"],
                "topn_best_pf": topn["best_pf"],
                "topn_best_score": topn["best_score"],
                "topn_best_events": topn["best_events"],
                "topn_error": topn["error"],
                "profile_status": profile["status"],
                "profile_label": profile["label"],
                "default_study_name": spec.default_study_name,
                "run_command": run_cmd,
                "dashboard_url": None,
                "dashboard_error": None,
                "dashboard_running": False,
            }
            cards.append(card)

        cards.sort(key=lambda c: (c["category"], c["surface_type"], c["name"]))

        if self.spawn_children and self.child_manager is not None:
            for card in cards:
                card["dashboard_url"] = self.child_manager.card_link(card["key"])
                card["dashboard_error"] = self.child_manager.card_error(card["key"])
                card["dashboard_running"] = card["dashboard_url"] is not None

        total_indicators = len(cards)
        total_strategies = sum(1 for c in cards if c["surface_type"] == "strategy")
        active_studies = sum(1 for c in cards if c["db_exists"])
        total_completed = sum(c["complete_count"] for c in cards)
        running_now = sum(c["running_count"] for c in cards)
        profile_ready = sum(1 for c in cards if c["profile_status"] == "ready")
        topn_ready = sum(1 for c in cards if c["topn_exists"] and c["topn_count"] > 0)

        best_overall = None
        for c in cards:
            b = c["best"]
            if b is None:
                continue
            quality_events = _safe_int(b.get("quality_events"), 0)
            rank = (
                _safe_float(b.get("objective_score"), _safe_float(b.get("objective"), 0.0)),
                _safe_float(b.get("win_rate"), 0.0),
                _safe_float(b.get("pf"), 0.0),
                -_safe_float(b.get("max_dd"), float("inf")),
                quality_events if quality_events > 0 else _safe_int(b.get("trades"), 0),
            )
            if best_overall is None or rank > best_overall["rank"]:
                best_overall = {
                    "rank": rank,
                    "indicator_key": c["key"],
                    "indicator_name": c["name"],
                    "objective_score": _safe_float(b.get("objective_score"), _safe_float(b.get("objective"), 0.0)),
                    "objective_metric": str(b.get("objective_metric") or ""),
                    "quality_events": quality_events,
                    "win_rate": _safe_float(b.get("win_rate"), 0.0),
                    "pf": _safe_float(b.get("pf"), 0.0),
                    "trades": _safe_int(b.get("trades"), 0),
                }

        return {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "host": self.host,
            "port": self.port,
            "refresh_seconds": REFRESH_SECONDS,
            "total_indicators": total_indicators,
            "total_strategies": total_strategies,
            "active_studies": active_studies,
            "profile_ready": profile_ready,
            "topn_ready": topn_ready,
            "total_completed": total_completed,
            "running_now": running_now,
            "best_overall": best_overall,
            "stack_health": self.stack_health,
            "child_dashboards_enabled": self.spawn_children,
            "cards": cards,
        }


def render_html(snapshot: dict[str, Any]) -> str:
    best = snapshot.get("best_overall")
    best_text = "No completed trials yet"
    if best:
        best_name = _display_indicator_name(best["indicator_name"])
        if _safe_int(best.get("quality_events"), 0) > 0:
            best_text = (
                f'{_h(best_name)} '
                f'Score {_safe_float(best["objective_score"]):.3f} | Events {_safe_int(best["quality_events"])}'
            )
        else:
            best_text = (
                f'{_h(best_name)} '
                f'WR {_safe_float(best["win_rate"]):.2%} | PF {_safe_float(best["pf"]):.3f} | '
                f'Trades {_safe_int(best["trades"])}'
            )

    stack = snapshot["stack_health"]
    ag_badge_class = "ok" if stack["availability"]["autogluon_1_5"] else "warn"
    ag_badge_text = "AutoGluon 1.5 READY" if stack["availability"]["autogluon_1_5"] else "AutoGluon 1.5 MISSING"

    cards_html: list[str] = []
    for idx, card in enumerate(snapshot["cards"]):
        display_name = _display_indicator_name(card["name"])
        surface_label = _display_short_label(card["surface_type"])
        category_label = _display_short_label(card["category"])
        best_block = "<div class='muted'>No completed trials</div>"
        if card["best"] is not None:
            b = card["best"]
            if _safe_int(b.get("quality_events"), 0) > 0:
                best_block = (
                    "<div class='metrics'>"
                    f"<div><span>Best Score</span><strong>{_safe_float(b['objective_score']):.3f}</strong></div>"
                    f"<div><span>Events</span><strong>{_safe_int(b['quality_events'])}</strong></div>"
                    f"<div><span>Primary</span><strong>{_safe_float(b['primary_signal_quality']):.3f}</strong></div>"
                    f"<div><span>Volume</span><strong>{_safe_float(b['volume_flow_quality']):.3f}</strong></div>"
                    "</div>"
                )
            else:
                best_block = (
                    "<div class='metrics'>"
                    f"<div><span>Best WR</span><strong>{_safe_float(b['win_rate']):.2%}</strong></div>"
                    f"<div><span>Best PF</span><strong>{_safe_float(b['pf']):.3f}</strong></div>"
                    f"<div><span>Trades</span><strong>{_safe_int(b['trades'])}</strong></div>"
                    f"<div><span>Max DD</span><strong>{_safe_float(b['max_dd']):.1f}</strong></div>"
                    "</div>"
                )

        topn_block = (
            "<div class='topn muted'>top-N export missing</div>"
            if not card["topn_exists"]
            else (
                f"<div class='topn'>top-N ready: {card['topn_count']} rows"
                + (
                    f" | Score {_safe_float(card['topn_best_score']):.3f} | Events {_safe_int(card['topn_best_events'])}"
                    if card.get("topn_best_events")
                    else (
                    f" | WR {_safe_float(card['topn_best_wr']):.2%} | PF {_safe_float(card['topn_best_pf']):.3f}"
                    if card["topn_best_wr"] is not None
                    else ""
                    )
                )
                + "</div>"
            )
        )
        if card["topn_error"]:
            topn_block = f"<div class='warning'>{_h(card['topn_error'])}</div>"

        profile_class = "ok" if card["profile_status"] == "ready" else "warn"
        profile_chip_label = "Profile Ready" if card["profile_status"] == "ready" else "Profile Missing"

        link_html = "<span class='btn disabled'>No DB</span>"
        if card["dashboard_url"]:
            link_html = (
                f"<a class='btn' href='/studies/{_h(card['key'])}' target='_blank' rel='noreferrer'>"
                "Open Studies</a>"
            )
        elif card["db_exists"] and snapshot["child_dashboards_enabled"]:
            link_html = (
                f"<a class='btn' href='/studies/{_h(card['key'])}' target='_blank' rel='noreferrer'>"
                "Open Studies</a>"
            )
        elif card["db_exists"]:
            link_html = (
                f"<a class='btn' href='/studies/{_h(card['key'])}' target='_blank' rel='noreferrer'>"
                "Open Studies</a>"
            )

        db_status = "ready" if card["db_exists"] and card["target_study_exists"] else "empty"
        db_status_label = "Active study detected" if card["target_study_exists"] else "No study.db yet"
        if card["db_exists"] and not card["target_study_exists"]:
            db_status = "warn"
            db_status_label = "Study DB ready; active study not created yet"
        if card["db_error"]:
            db_status = "error"
            db_status_label = f"DB error: {card['db_error']}"

        dash_error_html = ""
        if card["dashboard_error"]:
            dash_error_html = f"<div class='warning'>{_h(card['dashboard_error'])}</div>"

        notes_html = f"<div class='path'><span>Notes:</span> {_h(card['notes'])}</div>" if card["notes"] else ""
        operational_details = (
            "<details class='technical'>"
            "<summary>Operational Details</summary>"
            f"<div class='path'><span>Workspace Key:</span> {_h(card['key'])}</div>"
            f"<div class='path'><span>Active Study:</span> {_h(card['default_study_name'])}</div>"
            f"<div class='path'><span>Profile:</span> {_h(card['profile_label'])}</div>"
            f"<div class='path'><span>Pine:</span> {_h(card['pine_file'])}</div>"
            f"<div class='path'><span>Workspace:</span> {_h(card['indicator_dir'])}</div>"
            f"<div class='path'><span>Experiments:</span> {_h(card['experiments_dir'])}</div>"
            f"<div class='path'><span>DB:</span> {_h(card['db_path'])}</div>"
            f"<div class='path'><span>Top-N:</span> {_h(card['topn_path'])}</div>"
            f"{notes_html}"
            "<details class='cmd'>"
            "<summary>Run Command</summary>"
            f"<pre>{_h(card['run_command'])}</pre>"
            "</details>"
            "</details>"
        )
        best_wr = _safe_float(card["best"]["win_rate"], -1.0) if card["best"] is not None else -1.0
        best_pf = _safe_float(card["best"]["pf"], -1.0) if card["best"] is not None else -1.0
        best_trades = _safe_int(card["best"]["trades"], 0) if card["best"] is not None else 0
        best_max_dd = _safe_float(card["best"]["max_dd"], 1e18) if card["best"] is not None else 1e18
        best_score = _safe_float(card["best"]["objective_score"], -1.0) if card["best"] is not None else -1.0
        best_events = _safe_int(card["best"]["quality_events"], 0) if card["best"] is not None else 0
        topn_ready = 1 if card["topn_exists"] and card["topn_count"] > 0 else 0
        profile_ready = 1 if card["profile_status"] == "ready" else 0
        db_ready = 1 if card["db_exists"] else 0

        cards_html.append(
            f"<article class='card' "
            f"data-default-order='{idx}' "
            f"data-key='{_h(card['key'])}' "
            f"data-name='{_h(display_name)}' "
            f"data-surface='{_h(card['surface_type'])}' "
            f"data-category='{_h(card['category'])}' "
            f"data-trials='{_safe_int(card['trial_count'])}' "
            f"data-complete='{_safe_int(card['complete_count'])}' "
            f"data-running='{_safe_int(card['running_count'])}' "
            f"data-fail='{_safe_int(card['fail_count'])}' "
            f"data-db-ready='{db_ready}' "
            f"data-profile-ready='{profile_ready}' "
            f"data-topn-ready='{topn_ready}' "
            f"data-best-win-rate='{best_wr}' "
            f"data-best-pf='{best_pf}' "
            f"data-best-trades='{best_trades}' "
            f"data-best-max-dd='{best_max_dd}' "
            f"data-best-score='{best_score}' "
            f"data-best-events='{best_events}' "
            f"data-last-complete='{_h(card['last_complete'] or '')}' "
            f"data-has-best='{1 if card['best'] is not None else 0}'>"
            f"<header><h3>{_h(display_name)}</h3></header>"
            f"<p class='card-purpose'>{_h(card['default_study_name'])}</p>"
            "<div class='meta-line'>"
            f"<span class='chip surface'>{_h(surface_label)}</span>"
            f"<span class='chip category'>{_h(category_label)}</span>"
            f"<span class='chip {profile_class}'>{_h(profile_chip_label)}</span>"
            "</div>"
            f"<div class='status {db_status}'>{_h(db_status_label)}</div>"
            "<div class='counts'>"
            f"<span>Studies {_safe_int(card['study_count'])}</span>"
            f"<span>Trials {_safe_int(card['trial_count'])}</span>"
            f"<span>Complete {_safe_int(card['complete_count'])}</span>"
            f"<span>Running {_safe_int(card['running_count'])}</span>"
            f"<span>Pruned {_safe_int(card['pruned_count'])}</span>"
            f"<span>Fail {_safe_int(card['fail_count'])}</span>"
            "</div>"
            f"{best_block}"
            f"{topn_block}"
            f"<div class='path'><span>Last Complete:</span> {_h(card['last_complete'] or 'n/a')}</div>"
            f"{operational_details}"
            f"<div class='actions'>{link_html}</div>"
            f"{dash_error_html}"
            "</article>"
        )

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Warbird Optuna Hub</title>
  <style>
    :root {{
      color-scheme: dark;
      --bg: #000000;
      --panel: rgba(0, 0, 0, 0.50);
      --panel-2: rgba(18, 20, 22, 0.52);
      --panel-strong: rgba(8, 12, 18, 0.82);
      --text: rgba(255, 255, 255, 0.92);
      --muted: rgba(255, 255, 255, 0.56);
      --soft: rgba(255, 255, 255, 0.34);
      --accent: #26c6da;
      --ok: #22c55e;
      --warn: #f59e0b;
      --bad: #ef4444;
      --border: rgba(255, 255, 255, 0.08);
      --accent-border: rgba(38, 198, 218, 0.22);
    }}
    * {{ box-sizing: border-box; }}
    html {{
      background: #000;
    }}
    body {{
      margin: 0;
      font-family: ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Ubuntu, Cantarell, Noto Sans, Arial;
      min-height: 100vh;
      background:
        radial-gradient(circle at 72% 16%, rgba(38, 198, 218, 0.11), transparent 32%),
        linear-gradient(135deg, #000000 0%, #0a0a0a 50%, #111111 100%);
      color: var(--text);
    }}
    body::before {{
      content: "";
      position: fixed;
      inset: 0;
      pointer-events: none;
      background: url("/assets/chart_watermark.svg") center 92px / min(980px, 92vw) no-repeat;
      opacity: 0.68;
      filter: saturate(1.45) brightness(1.55) contrast(1.08);
      mix-blend-mode: screen;
      z-index: 0;
    }}
    body::after {{
      content: "";
      position: fixed;
      inset: 0;
      pointer-events: none;
      background:
        linear-gradient(180deg, rgba(0, 0, 0, 0.10), rgba(0, 0, 0, 0.38)),
        radial-gradient(circle at 50% 0%, rgba(255, 255, 255, 0.05), transparent 36%);
      z-index: 0;
    }}
    .brandbar {{
      position: relative;
      z-index: 1;
      height: 80px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 0 max(20px, calc((100vw - 1500px) / 2 + 16px));
      border-bottom: 1px solid rgba(255, 255, 255, 0.06);
      background: rgba(0, 0, 0, 0.28);
      backdrop-filter: blur(12px);
    }}
    .brand {{
      display: inline-flex;
      align-items: center;
      gap: 14px;
      color: var(--text);
      text-decoration: none;
      min-width: 0;
    }}
    .brand img {{
      width: 190px;
      height: auto;
      display: block;
    }}
    .brand span {{
      color: var(--muted);
      font-size: 13px;
      border-left: 1px solid rgba(255, 255, 255, 0.1);
      padding-left: 14px;
      white-space: nowrap;
    }}
    .brand-meta {{
      color: var(--soft);
      font-size: 12px;
      letter-spacing: 0;
      text-transform: uppercase;
    }}
    .wrap {{
      position: relative;
      z-index: 1;
      max-width: 1500px;
      margin: 0 auto;
      padding: 28px 16px 36px;
    }}
    .top {{
      display: grid;
      grid-template-columns: 1.6fr repeat(6, minmax(130px, 1fr));
      gap: 12px;
      margin-bottom: 14px;
    }}
    .summary {{
      background: linear-gradient(180deg, rgba(18, 20, 22, 0.52), rgba(0, 0, 0, 0.48));
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 20px;
      min-height: 148px;
      box-shadow: 0 20px 60px rgba(0, 0, 0, 0.28);
      backdrop-filter: blur(5px) saturate(1.04);
      -webkit-backdrop-filter: blur(5px) saturate(1.04);
    }}
    .summary h1 {{
      margin: 0 0 8px;
      color: #fff;
      font-size: clamp(28px, 3vw, 44px);
      letter-spacing: 0;
      line-height: 1.08;
    }}
    .meta {{
      color: var(--muted);
      font-size: 13px;
      line-height: 1.35;
    }}
    .best {{
      margin-top: 12px;
      color: rgba(38, 198, 218, 0.95);
      font-size: 13px;
    }}
    .stack {{
      margin-top: 8px;
      font-size: 12px;
      color: rgba(255, 255, 255, 0.62);
    }}
    .stack-badge {{
      display: inline-block;
      font-size: 11px;
      padding: 2px 7px;
      border-radius: 999px;
      margin-right: 8px;
      border: 1px solid transparent;
    }}
    .stack-badge.ok {{ color: #bbf7d0; border-color: rgba(34, 197, 94, 0.35); background: rgba(34, 197, 94, 0.08); }}
    .stack-badge.warn {{ color: #fde68a; border-color: rgba(245, 158, 11, 0.35); background: rgba(245, 158, 11, 0.08); }}
    .kpi {{
      background: var(--panel);
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 14px;
      display: grid;
      align-content: center;
      gap: 4px;
      min-height: 110px;
      backdrop-filter: blur(5px) saturate(1.04);
      -webkit-backdrop-filter: blur(5px) saturate(1.04);
    }}
    .kpi .label {{ color: var(--muted); font-size: 11px; text-transform: uppercase; letter-spacing: 0; }}
    .kpi .value {{ font-size: 26px; font-weight: 700; color: #fff; }}
    .toolbar {{
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      margin-bottom: 16px;
      align-items: center;
      border: 1px solid var(--border);
      background: rgba(0, 0, 0, 0.46);
      border-radius: 8px;
      padding: 12px;
      backdrop-filter: blur(5px) saturate(1.04);
      -webkit-backdrop-filter: blur(5px) saturate(1.04);
    }}
    .toolbar-group {{
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      align-items: center;
    }}
    .toolbar-spacer {{
      flex: 1 1 auto;
    }}
    .toolbar-label {{
      color: var(--muted);
      font-size: 11px;
    }}
    .filter-btn {{
      font-size: 11px;
      border: 1px solid rgba(255, 255, 255, 0.1);
      background: rgba(255, 255, 255, 0.03);
      color: rgba(255, 255, 255, 0.76);
      border-radius: 999px;
      padding: 6px 11px;
      cursor: pointer;
    }}
    .filter-btn.active {{
      border-color: var(--accent-border);
      background: rgba(38, 198, 218, 0.08);
      color: rgba(224, 242, 254, 0.96);
    }}
    .sort-select {{
      font-size: 11px;
      border: 1px solid rgba(255, 255, 255, 0.1);
      background: rgba(255, 255, 255, 0.03);
      color: rgba(255, 255, 255, 0.82);
      border-radius: 8px;
      padding: 6px 10px;
      min-width: 140px;
    }}
    .grid {{
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(380px, 1fr));
      gap: 12px;
    }}
    .card {{
      background: linear-gradient(180deg, rgba(18, 20, 22, 0.52), rgba(0, 0, 0, 0.48));
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 16px;
      display: grid;
      gap: 10px;
      box-shadow: 0 18px 52px rgba(0, 0, 0, 0.24);
      backdrop-filter: blur(5px) saturate(1.04);
      -webkit-backdrop-filter: blur(5px) saturate(1.04);
      transition: border-color 160ms ease, transform 160ms ease, background 160ms ease;
    }}
    .card:hover {{
      border-color: var(--accent-border);
      background: linear-gradient(180deg, rgba(24, 28, 30, 0.56), rgba(0, 0, 0, 0.48));
      transform: translateY(-1px);
    }}
    .card header {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 10px;
    }}
    .card h3 {{
      margin: 0;
      color: #fff;
      font-size: 17px;
      font-weight: 700;
      line-height: 1.2;
    }}
    .card-purpose {{
      margin: -3px 0 0;
      color: var(--muted);
      font-size: 13px;
      line-height: 1.4;
    }}
    .badge {{
      font-size: 11px;
      color: rgba(207, 250, 254, 0.92);
      border: 1px solid var(--accent-border);
      background: rgba(38, 198, 218, 0.06);
      border-radius: 999px;
      padding: 3px 8px;
      white-space: nowrap;
    }}
    .meta-line {{
      display: flex;
      flex-wrap: wrap;
      gap: 6px;
    }}
    .chip {{
      font-size: 10px;
      border-radius: 999px;
      border: 1px solid transparent;
      padding: 2px 7px;
      text-transform: uppercase;
      letter-spacing: 0;
    }}
    .chip.surface {{ color: rgba(191, 219, 254, 0.92); background: rgba(59, 130, 246, 0.08); border-color: rgba(59, 130, 246, 0.22); }}
    .chip.category {{ color: rgba(224, 242, 254, 0.92); background: rgba(38, 198, 218, 0.08); border-color: var(--accent-border); }}
    .chip.ok {{ color: #bbf7d0; background: rgba(34, 197, 94, 0.08); border-color: rgba(34, 197, 94, 0.28); text-transform: none; }}
    .chip.warn {{ color: #fde68a; background: rgba(245, 158, 11, 0.08); border-color: rgba(245, 158, 11, 0.28); text-transform: none; }}
    .path {{
      color: rgba(255, 255, 255, 0.68);
      font-size: 12px;
      overflow-wrap: anywhere;
    }}
    .path span {{ color: var(--muted); }}
    .status {{
      display: inline-flex;
      width: fit-content;
      font-size: 12px;
      border-radius: 8px;
      padding: 3px 8px;
      border: 1px solid transparent;
    }}
    .status.ready {{ color: #86efac; border-color: rgba(34, 197, 94, 0.28); background: rgba(34, 197, 94, 0.08); }}
    .status.warn {{ color: #fde68a; border-color: rgba(245, 158, 11, 0.28); background: rgba(245, 158, 11, 0.08); }}
    .status.empty {{ color: #fde68a; border-color: rgba(245, 158, 11, 0.28); background: rgba(245, 158, 11, 0.08); }}
    .status.error {{ color: #fecaca; border-color: rgba(239, 68, 68, 0.32); background: rgba(239, 68, 68, 0.08); }}
    .counts {{
      display: flex;
      flex-wrap: wrap;
      gap: 5px;
    }}
    .counts span {{
      font-size: 11px;
      color: rgba(255, 255, 255, 0.76);
      background: rgba(255, 255, 255, 0.035);
      border: 1px solid rgba(255, 255, 255, 0.08);
      border-radius: 999px;
      padding: 2px 7px;
    }}
    .metrics {{
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 5px;
    }}
    .metrics div {{
      background: rgba(0, 0, 0, 0.34);
      border: 1px solid rgba(255, 255, 255, 0.06);
      border-radius: 8px;
      padding: 6px 7px;
      display: grid;
      gap: 2px;
    }}
    .metrics span {{ color: var(--muted); font-size: 11px; }}
    .metrics strong {{ font-size: 13px; color: #fff; }}
    .muted {{ color: var(--muted); font-size: 12px; }}
    .topn {{
      font-size: 11px;
      color: #86efac;
      background: rgba(34, 197, 94, 0.08);
      border: 1px solid rgba(34, 197, 94, 0.28);
      border-radius: 8px;
      padding: 4px 6px;
    }}
    details.technical {{
      border: 1px solid rgba(255, 255, 255, 0.06);
      border-radius: 8px;
      padding: 7px;
      background: rgba(0, 0, 0, 0.34);
    }}
    details.technical summary {{
      cursor: pointer;
      color: rgba(255, 255, 255, 0.62);
      font-size: 12px;
    }}
    details.technical[open] {{
      display: grid;
      gap: 6px;
    }}
    details.cmd {{
      background: rgba(0, 0, 0, 0.22);
      border: 1px solid rgba(255, 255, 255, 0.06);
      border-radius: 8px;
      padding: 6px;
    }}
    details.cmd summary {{
      cursor: pointer;
      color: rgba(191, 219, 254, 0.86);
      font-size: 12px;
    }}
    details.cmd pre {{
      margin: 8px 0 0;
      color: rgba(224, 242, 254, 0.9);
      font-size: 11px;
      white-space: pre-wrap;
      word-break: break-word;
      font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, Liberation Mono, Courier New, monospace;
    }}
    .actions {{
      display: flex;
      gap: 8px;
      margin-top: 2px;
    }}
    .btn {{
      display: inline-flex;
      align-items: center;
      justify-content: center;
      min-height: 36px;
      padding: 0 12px;
      border-radius: 8px;
      font-size: 12px;
      text-decoration: none;
      border: 1px solid var(--accent-border);
      background: rgba(38, 198, 218, 0.08);
      color: rgba(207, 250, 254, 0.96);
    }}
    .btn.disabled {{
      border-color: rgba(255, 255, 255, 0.08);
      background: rgba(255, 255, 255, 0.03);
      color: rgba(255, 255, 255, 0.34);
    }}
    .warning {{
      font-size: 11px;
      color: #fecaca;
      background: rgba(239, 68, 68, 0.08);
      border: 1px solid rgba(239, 68, 68, 0.32);
      border-radius: 8px;
      padding: 5px 7px;
      overflow-wrap: anywhere;
    }}
    @media (max-width: 1220px) {{
      .top {{
        grid-template-columns: 1fr 1fr 1fr;
      }}
      .summary {{
        grid-column: 1 / -1;
      }}
    }}
    @media (max-width: 720px) {{
      .brandbar {{
        height: auto;
        min-height: 72px;
        align-items: flex-start;
        flex-direction: column;
        gap: 8px;
        padding: 16px 20px;
      }}
      .brand {{
        flex-wrap: wrap;
      }}
      .brand img {{
        width: 150px;
      }}
      .brand span {{
        border-left: 0;
        padding-left: 0;
      }}
      .brand-meta {{
        display: none;
      }}
      .top {{
        grid-template-columns: 1fr;
      }}
      .grid {{
        grid-template-columns: 1fr;
      }}
    }}
  </style>
</head>
<body>
  <header class="brandbar">
    <a class="brand" href="/">
      <img src="/assets/warbird-logo.svg" alt="Warbird Pro" />
      <span>Optuna Study Operations</span>
    </a>
    <div class="brand-meta">Local Operator Surface</div>
  </header>
  <main class="wrap">
    <section class="top">
      <div class="summary">
        <h1>Warbird Optuna Study Hub</h1>
        <div class="meta">One professional card per indicator lane. Each lane can hold multiple purpose-named studies.</div>
        <div class="meta">Generated: {_h(snapshot['generated_at'])}</div>
        <div class="meta" id="scope-label">Viewing: All Lanes</div>
        <div class="best" id="best-text">{best_text}</div>
        <div class="stack">
          <span class="stack-badge {ag_badge_class}">{ag_badge_text}</span>
          Python {_h(stack['versions']['python'])} |
          Optuna {_h(stack['versions']['optuna'])} |
          Optuna Dashboard {_h(stack['versions']['optuna_dashboard'])} |
          AutoGluon {_h(stack['versions']['autogluon_tabular'])}
        </div>
        <div class="meta">{_h(stack['note'])}</div>
      </div>
      <div class="kpi"><div class="label">Lanes</div><div class="value" id="kpi-lanes">{_safe_int(snapshot['total_indicators'])}</div></div>
      <div class="kpi"><div class="label">Strategies</div><div class="value" id="kpi-strategies">{_safe_int(snapshot['total_strategies'])}</div></div>
      <div class="kpi"><div class="label">Profiles Wired</div><div class="value" id="kpi-profiles">{_safe_int(snapshot['profile_ready'])}</div></div>
      <div class="kpi"><div class="label">DB Ready</div><div class="value" id="kpi-db-ready">{_safe_int(snapshot['active_studies'])}</div></div>
      <div class="kpi"><div class="label">Top-N Ready</div><div class="value" id="kpi-topn-ready">{_safe_int(snapshot['topn_ready'])}</div></div>
      <div class="kpi"><div class="label">Completed</div><div class="value" id="kpi-completed">{_safe_int(snapshot['total_completed'])}</div></div>
    </section>

    <section class="toolbar">
      <div class="toolbar-group">
        <button class="filter-btn active" data-filter="all">All</button>
        <button class="filter-btn" data-filter="indicator">Indicators</button>
        <button class="filter-btn" data-filter="strategy">Strategies</button>
        <button class="filter-btn" data-filter="lower-pane">Lower Pane</button>
        <button class="filter-btn" data-filter="chart-core">Chart Core</button>
        <button class="filter-btn" data-filter="legacy">Legacy</button>
      </div>
      <div class="toolbar-spacer"></div>
      <div class="toolbar-group">
        <label class="toolbar-label" for="sort-field">Sort</label>
        <select id="sort-field" class="sort-select">
          <option value="default">Default</option>
          <option value="name">Name</option>
          <option value="complete">Completed</option>
          <option value="trials">Trials</option>
          <option value="win_rate">Best WR</option>
          <option value="pf">Best PF</option>
          <option value="last_complete">Last Complete</option>
        </select>
        <button class="filter-btn" id="sort-dir" data-dir="desc">Desc</button>
      </div>
    </section>

    <section class="grid" id="card-grid">
      {''.join(cards_html)}
    </section>
  </main>
  <script>
    (function() {{
      const buttons = Array.from(document.querySelectorAll('.filter-btn'));
      const cards = Array.from(document.querySelectorAll('.card'));
      const filterButtons = buttons.filter((btn) => !!btn.dataset.filter);
      const grid = document.getElementById('card-grid');
      const sortField = document.getElementById('sort-field');
      const sortDirBtn = document.getElementById('sort-dir');
      const scopeLabel = document.getElementById('scope-label');
      const bestText = document.getElementById('best-text');
      const kpiLanes = document.getElementById('kpi-lanes');
      const kpiStrategies = document.getElementById('kpi-strategies');
      const kpiProfiles = document.getElementById('kpi-profiles');
      const kpiDbReady = document.getElementById('kpi-db-ready');
      const kpiTopnReady = document.getElementById('kpi-topn-ready');
      const kpiCompleted = document.getElementById('kpi-completed');
      const params = new URLSearchParams(window.location.search);
      const allowedFilters = new Set(['all', ...filterButtons.map((btn) => btn.dataset.filter)]);
      const allowedSorts = new Set(['default', 'name', 'complete', 'trials', 'win_rate', 'pf', 'last_complete']);
      const labels = {{
        all: 'All Lanes',
        indicator: 'Indicators',
        strategy: 'Strategies',
        'lower-pane': 'Lower Pane',
        'chart-core': 'Chart Core',
        legacy: 'Legacy',
      }};
      const state = {{
        filter: allowedFilters.has(params.get('filter')) ? params.get('filter') : 'all',
        sort: allowedSorts.has(params.get('sort')) ? params.get('sort') : 'default',
        dir: params.get('dir') === 'asc' ? 'asc' : 'desc',
      }};
      const refreshMs = {REFRESH_SECONDS} * 1000;

      function numberAttr(card, name, fallback) {{
        const raw = card.getAttribute(name);
        const value = Number(raw);
        return Number.isFinite(value) ? value : fallback;
      }}

      function stringAttr(card, name) {{
        return card.getAttribute(name) || '';
      }}

      function isVisible(card, filter) {{
        const surface = stringAttr(card, 'data-surface');
        const category = stringAttr(card, 'data-category');
        return filter === 'all' || filter === surface || filter === category;
      }}

      function updateUrl() {{
        const next = new URLSearchParams(window.location.search);
        if (state.filter === 'all') {{
          next.delete('filter');
        }} else {{
          next.set('filter', state.filter);
        }}
        if (state.sort === 'default') {{
          next.delete('sort');
        }} else {{
          next.set('sort', state.sort);
        }}
        if (state.dir === 'desc' && state.sort === 'default') {{
          next.delete('dir');
        }} else {{
          next.set('dir', state.dir);
        }}
        const query = next.toString();
        const nextUrl = window.location.pathname + (query ? '?' + query : '');
        window.history.replaceState({{}}, '', nextUrl);
      }}

      function compareCards(left, right) {{
        if (state.sort === 'default') {{
          return numberAttr(left, 'data-default-order', 0) - numberAttr(right, 'data-default-order', 0);
        }}

        let leftValue;
        let rightValue;
        switch (state.sort) {{
          case 'name':
            leftValue = stringAttr(left, 'data-name').toLowerCase();
            rightValue = stringAttr(right, 'data-name').toLowerCase();
            break;
          case 'complete':
            leftValue = numberAttr(left, 'data-complete', 0);
            rightValue = numberAttr(right, 'data-complete', 0);
            break;
          case 'trials':
            leftValue = numberAttr(left, 'data-trials', 0);
            rightValue = numberAttr(right, 'data-trials', 0);
            break;
          case 'win_rate':
            leftValue = numberAttr(left, 'data-best-win-rate', -1);
            rightValue = numberAttr(right, 'data-best-win-rate', -1);
            break;
          case 'pf':
            leftValue = numberAttr(left, 'data-best-pf', -1);
            rightValue = numberAttr(right, 'data-best-pf', -1);
            break;
          case 'last_complete':
            leftValue = stringAttr(left, 'data-last-complete');
            rightValue = stringAttr(right, 'data-last-complete');
            break;
          default:
            leftValue = numberAttr(left, 'data-default-order', 0);
            rightValue = numberAttr(right, 'data-default-order', 0);
            break;
        }}

        let cmp = 0;
        if (typeof leftValue === 'string') {{
          cmp = leftValue.localeCompare(rightValue);
        }} else {{
          cmp = leftValue === rightValue ? 0 : (leftValue < rightValue ? -1 : 1);
        }}
        if (cmp === 0) {{
          const fallbackLeft = numberAttr(left, 'data-default-order', 0);
          const fallbackRight = numberAttr(right, 'data-default-order', 0);
          cmp = fallbackLeft - fallbackRight;
        }}
        return state.dir === 'asc' ? cmp : -cmp;
      }}

      function updateSummary(visibleCards) {{
        const scopeText = labels[state.filter] || state.filter;
        scopeLabel.textContent = `Viewing: ${{scopeText}}`;

        kpiLanes.textContent = String(visibleCards.length);
        kpiStrategies.textContent = String(visibleCards.filter((card) => stringAttr(card, 'data-surface') === 'strategy').length);
        kpiProfiles.textContent = String(visibleCards.reduce((sum, card) => sum + numberAttr(card, 'data-profile-ready', 0), 0));
        kpiDbReady.textContent = String(visibleCards.reduce((sum, card) => sum + numberAttr(card, 'data-db-ready', 0), 0));
        kpiTopnReady.textContent = String(visibleCards.reduce((sum, card) => sum + numberAttr(card, 'data-topn-ready', 0), 0));
        kpiCompleted.textContent = String(visibleCards.reduce((sum, card) => sum + numberAttr(card, 'data-complete', 0), 0));

        let bestCard = null;
        let bestRank = null;
        visibleCards.forEach((card) => {{
          if (numberAttr(card, 'data-has-best', 0) !== 1) {{
            return;
          }}
          const events = numberAttr(card, 'data-best-events', 0);
          const rank = [
            numberAttr(card, 'data-best-score', -1),
            numberAttr(card, 'data-best-win-rate', -1),
            numberAttr(card, 'data-best-pf', -1),
            -numberAttr(card, 'data-best-max-dd', Number.POSITIVE_INFINITY),
            events > 0 ? events : numberAttr(card, 'data-best-trades', 0),
          ];
          if (bestRank === null) {{
            bestRank = rank;
            bestCard = card;
            return;
          }}
          for (let i = 0; i < rank.length; i += 1) {{
            if (rank[i] === bestRank[i]) {{
              continue;
            }}
            if (rank[i] > bestRank[i]) {{
              bestRank = rank;
              bestCard = card;
            }}
            return;
          }}
        }});

        if (!bestCard) {{
          bestText.textContent = visibleCards.length === 0 ? 'No lanes in current view' : 'No completed trials in current view';
          return;
        }}

        const bestName = stringAttr(bestCard, 'data-name');
        const events = numberAttr(bestCard, 'data-best-events', 0);
        if (events > 0) {{
          const score = numberAttr(bestCard, 'data-best-score', 0);
          bestText.textContent = `${{bestName}} Score ${{score.toFixed(3)}} | Events ${{events}}`;
          return;
        }}
        const winRate = numberAttr(bestCard, 'data-best-win-rate', 0) * 100;
        const pf = numberAttr(bestCard, 'data-best-pf', 0);
        const trades = numberAttr(bestCard, 'data-best-trades', 0);
        bestText.textContent = `${{bestName}} WR ${{winRate.toFixed(2)}}% | PF ${{pf.toFixed(3)}} | Trades ${{trades}}`;
      }}

      function applyState() {{
        sortField.value = state.sort;
        sortDirBtn.disabled = state.sort === 'default';
        sortDirBtn.dataset.dir = state.sort === 'default' ? 'default' : state.dir;
        sortDirBtn.textContent = state.sort === 'default' ? 'Default' : (state.dir === 'asc' ? 'Asc' : 'Desc');

        const ordered = [...cards].sort(compareCards);
        ordered.forEach((card) => grid.appendChild(card));

        const visibleCards = [];
        cards.forEach((card) => {{
          const visible = isVisible(card, state.filter);
          card.style.display = visible ? '' : 'none';
          if (visible) {{
            visibleCards.push(card);
          }}
        }});

        filterButtons.forEach((btn) => {{
          btn.classList.toggle('active', btn.dataset.filter === state.filter);
        }});
        updateSummary(visibleCards);
      }}

      filterButtons.forEach((btn) => {{
        btn.addEventListener('click', () => {{
          state.filter = btn.dataset.filter;
          updateUrl();
          applyState();
        }});
      }});

      sortField.addEventListener('change', () => {{
        state.sort = sortField.value;
        updateUrl();
        applyState();
      }});

      sortDirBtn.addEventListener('click', () => {{
        if (state.sort === 'default') {{
          return;
        }}
        state.dir = state.dir === 'asc' ? 'desc' : 'asc';
        updateUrl();
        applyState();
      }});

      applyState();

      window.setTimeout(() => {{
        window.location.reload();
      }}, refreshMs);
    }})();
  </script>
</body>
</html>"""


def render_study_landing(card: dict[str, Any], child_dashboards_enabled: bool) -> str:
    display_name = _display_indicator_name(card["name"])
    studies = load_workspace_studies(Path(card["db_path"]))
    studies_html: list[str] = []
    for study in studies:
        best = study["best_score"]
        best_text = "n/a" if best is None else f"{_safe_float(best):.4f}"
        study_url = f"/studies/{_h(card['key'])}/{_safe_int(study['study_id'])}"
        studies_html.append(
            "<article class='study-card'>"
            f"<h2><a class='study-link' href='{study_url}'>{_h(study['title'])}</a></h2>"
            f"<p>{_h(study['purpose'])}</p>"
            "<div class='facts'>"
            f"<span>Direction {_h(study['direction'])}</span>"
            f"<span>Trials {_safe_int(study['trial_count'])}</span>"
            f"<span>Complete {_safe_int(study['complete_count'])}</span>"
            f"<span>Running {_safe_int(study['running_count'])}</span>"
            f"<span>Fail {_safe_int(study['fail_count'])}</span>"
            f"<span>Best {best_text}</span>"
            "</div>"
            f"<div class='meta'>Study name: {_h(study['study_name'])}</div>"
            f"<div class='meta'>Last complete: {_h(study['last_complete'] or 'n/a')}</div>"
            f"<div class='study-actions'><a class='btn primary' href='{study_url}'>Open Study</a></div>"
            "</article>"
        )

    if not studies_html:
        studies_html.append("<div class='empty'>No studies have been created for this indicator yet.</div>")

    raw_link = (
        f"<a class='btn primary' href='/open-study/{_h(card['key'])}' target='_blank' rel='noreferrer'>"
        "Open Optuna Dashboard</a>"
        if child_dashboards_enabled and card["db_exists"]
        else "<span class='btn disabled'>Optuna Dashboard unavailable</span>"
    )

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{_h(display_name)} Studies</title>
  <style>
    :root {{
      color-scheme: dark;
      --bg: #000000;
      --panel: rgba(0, 0, 0, 0.50);
      --panel-2: rgba(18, 20, 22, 0.52);
      --text: rgba(255, 255, 255, 0.92);
      --muted: rgba(255, 255, 255, 0.56);
      --soft: rgba(255, 255, 255, 0.34);
      --line: rgba(255, 255, 255, 0.08);
      --accent: #26c6da;
      --accent-line: rgba(38, 198, 218, 0.22);
    }}
    * {{ box-sizing: border-box; }}
    html {{
      background: #000;
    }}
    body {{
      margin: 0;
      min-height: 100vh;
      background:
        radial-gradient(circle at 72% 16%, rgba(38, 198, 218, 0.11), transparent 32%),
        linear-gradient(135deg, #000000 0%, #0a0a0a 50%, #111111 100%);
      color: var(--text);
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }}
    body::before {{
      content: "";
      position: fixed;
      inset: 0;
      pointer-events: none;
      background: url("/assets/chart_watermark.svg") center 92px / min(980px, 92vw) no-repeat;
      opacity: 0.68;
      filter: saturate(1.45) brightness(1.55) contrast(1.08);
      mix-blend-mode: screen;
      z-index: 0;
    }}
    body::after {{
      content: "";
      position: fixed;
      inset: 0;
      pointer-events: none;
      background:
        linear-gradient(180deg, rgba(0, 0, 0, 0.10), rgba(0, 0, 0, 0.38)),
        radial-gradient(circle at 50% 0%, rgba(255, 255, 255, 0.05), transparent 36%);
      z-index: 0;
    }}
    .brandbar {{
      position: relative;
      z-index: 1;
      height: 80px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 0 max(20px, calc((100vw - 1120px) / 2 + 24px));
      border-bottom: 1px solid rgba(255, 255, 255, 0.06);
      background: rgba(0, 0, 0, 0.28);
      backdrop-filter: blur(12px);
    }}
    .brand {{
      display: inline-flex;
      align-items: center;
      gap: 14px;
      color: var(--text);
      text-decoration: none;
      min-width: 0;
    }}
    .brand img {{
      width: 190px;
      height: auto;
      display: block;
    }}
    .brand span {{
      color: var(--muted);
      font-size: 13px;
      border-left: 1px solid rgba(255, 255, 255, 0.1);
      padding-left: 14px;
      white-space: nowrap;
    }}
    .brand-meta {{
      color: var(--soft);
      font-size: 12px;
      letter-spacing: 0;
      text-transform: uppercase;
    }}
    main {{
      position: relative;
      z-index: 1;
      width: min(1120px, calc(100vw - 48px));
      margin: 0 auto;
      padding: 34px 0 48px;
    }}
    .top {{
      display: flex;
      justify-content: space-between;
      gap: 20px;
      align-items: flex-start;
      padding: 24px;
      border: 1px solid var(--line);
      background: linear-gradient(180deg, rgba(18, 20, 22, 0.52), rgba(0, 0, 0, 0.48));
      border-radius: 8px;
      box-shadow: 0 20px 60px rgba(0, 0, 0, 0.28);
      backdrop-filter: blur(5px) saturate(1.04);
      -webkit-backdrop-filter: blur(5px) saturate(1.04);
    }}
    h1 {{
      margin: 0 0 8px;
      color: #fff;
      font-size: clamp(30px, 4vw, 46px);
      line-height: 1.15;
      letter-spacing: 0;
    }}
    .subtitle {{
      max-width: 760px;
      color: var(--muted);
      line-height: 1.45;
      font-size: 14px;
    }}
    .actions {{
      display: flex;
      gap: 10px;
      flex-wrap: wrap;
      justify-content: flex-end;
    }}
    .btn {{
      display: inline-flex;
      align-items: center;
      justify-content: center;
      min-height: 36px;
      padding: 0 13px;
      border-radius: 8px;
      border: 1px solid var(--line);
      color: var(--text);
      text-decoration: none;
      font-size: 13px;
      white-space: nowrap;
      background: rgba(255, 255, 255, 0.03);
    }}
    .btn.primary {{
      border-color: var(--accent-line);
      background: rgba(38, 198, 218, 0.08);
      color: rgba(224, 242, 254, 0.96);
    }}
    .btn.disabled {{
      color: rgba(255, 255, 255, 0.34);
      background: rgba(255, 255, 255, 0.03);
    }}
    .grid {{
      margin-top: 22px;
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
      gap: 16px;
    }}
    .study-card, .empty {{
      border: 1px solid var(--line);
      background: linear-gradient(180deg, rgba(18, 20, 22, 0.52), rgba(0, 0, 0, 0.48));
      border-radius: 8px;
      padding: 18px;
      backdrop-filter: blur(5px) saturate(1.04);
      -webkit-backdrop-filter: blur(5px) saturate(1.04);
      box-shadow: 0 18px 52px rgba(0, 0, 0, 0.24);
      transition: border-color 160ms ease, transform 160ms ease, background 160ms ease;
    }}
    .study-card:hover {{
      border-color: var(--accent-line);
      background: linear-gradient(180deg, rgba(24, 28, 30, 0.56), rgba(0, 0, 0, 0.48));
      transform: translateY(-1px);
    }}
    .study-card h2 {{
      margin: 0 0 8px;
      color: #fff;
      font-size: 21px;
      line-height: 1.2;
      letter-spacing: 0;
    }}
    .study-link {{
      color: inherit;
      text-decoration: none;
    }}
    .study-link:hover {{
      color: rgba(224, 242, 254, 0.96);
    }}
    .study-card p {{
      margin: 0 0 14px;
      color: var(--muted);
      font-size: 13px;
      line-height: 1.45;
    }}
    .facts {{
      display: flex;
      flex-wrap: wrap;
      gap: 7px;
      margin-bottom: 12px;
    }}
    .facts span {{
      border: 1px solid var(--line);
      background: rgba(255, 255, 255, 0.035);
      border-radius: 999px;
      padding: 5px 9px;
      color: rgba(255, 255, 255, 0.76);
      font-size: 12px;
    }}
    .meta {{
      color: var(--muted);
      font-size: 12px;
      overflow-wrap: anywhere;
    }}
    .study-actions {{
      margin-top: 14px;
      display: flex;
      justify-content: flex-start;
    }}
    @media (max-width: 720px) {{
      .brandbar {{
        height: auto;
        min-height: 72px;
        align-items: flex-start;
        flex-direction: column;
        gap: 8px;
        padding: 16px 20px;
      }}
      .brand {{
        flex-wrap: wrap;
      }}
      .brand img {{
        width: 150px;
      }}
      .brand span {{
        border-left: 0;
        padding-left: 0;
      }}
      .brand-meta {{
        display: none;
      }}
      main {{
        width: min(100vw - 32px, 1120px);
      }}
      .top {{
        flex-direction: column;
      }}
      .actions {{
        justify-content: flex-start;
      }}
    }}
  </style>
</head>
<body>
  <header class="brandbar">
    <a class="brand" href="/">
      <img src="/assets/warbird-logo.svg" alt="Warbird Pro" />
      <span>Optuna Study Operations</span>
    </a>
    <div class="brand-meta">Local Operator Surface</div>
  </header>
  <main>
    <section class="top">
      <div>
        <h1>{_h(display_name)} Studies</h1>
        <div class="subtitle">
          One indicator lane, multiple clearly named Optuna studies. Use this page as the clean landing view;
          open the raw Optuna dashboard only when you need trial-level controls.
        </div>
      </div>
      <div class="actions">
        <a class="btn" href="/">Back to Hub</a>
        {raw_link}
      </div>
    </section>
    <section class="grid">
      {''.join(studies_html)}
    </section>
  </main>
</body>
</html>"""


def render_study_detail(card: dict[str, Any], study_id: int, child_dashboards_enabled: bool) -> str | None:
    display_name = _display_indicator_name(card["name"])
    study = load_workspace_study_detail(Path(card["db_path"]), study_id)
    if study is None:
        return None

    best_trial = study["best_trial"]
    best_score = best_trial["score"] if best_trial else None
    best_trial_text = f"Trial {best_trial['number']}" if best_trial else "No completed trial"
    best_score_text = _display_scalar(best_score)

    facts_html = (
        f"<span>Direction {_h(study['direction'])}</span>"
        f"<span>Trials {_safe_int(study['trial_count'])}</span>"
        f"<span>Complete {_safe_int(study['complete_count'])}</span>"
        f"<span>Running {_safe_int(study['running_count'])}</span>"
        f"<span>Fail {_safe_int(study['fail_count'])}</span>"
        f"<span>Best {best_score_text}</span>"
    )

    params_html = "".join(
        "<div class='param-row'>"
        f"<span>{_h(param['label'])}</span>"
        f"<strong>{_h(param['value'])}</strong>"
        "</div>"
        for param in study["params"]
    ) or "<div class='empty-inline'>No best-trial parameters found.</div>"

    metrics_html = "".join(
        "<div class='metric-row'>"
        f"<span>{_h(metric['label'])}</span>"
        f"<strong>{_h(metric['value'])}</strong>"
        "</div>"
        for metric in study["metrics"]
    ) or "<div class='empty-inline'>No best-trial metrics found.</div>"

    trials_html = "".join(
        "<tr>"
        f"<td>{_h(trial['number'])}</td>"
        f"<td>{_h(_display_scalar(trial['score']))}</td>"
        f"<td>{_h(trial['state'])}</td>"
        f"<td>{_h(trial['completed'] or 'n/a')}</td>"
        "</tr>"
        for trial in study["top_trials"]
    ) or "<tr><td colspan='4'>No completed trials found.</td></tr>"

    raw_link = (
        f"<a class='btn secondary' href='/open-study/{_h(card['key'])}' target='_blank' rel='noreferrer'>"
        "Open Raw Optuna</a>"
        if child_dashboards_enabled and card["db_exists"]
        else ""
    )

    detail_css = """
    :root {
      color-scheme: dark;
      --text: rgba(255, 255, 255, 0.92);
      --muted: rgba(255, 255, 255, 0.56);
      --soft: rgba(255, 255, 255, 0.34);
      --line: rgba(255, 255, 255, 0.08);
      --accent: #26c6da;
      --accent-line: rgba(38, 198, 218, 0.22);
    }
    * { box-sizing: border-box; }
    html { background: #000; }
    body {
      margin: 0;
      min-height: 100vh;
      background:
        radial-gradient(circle at 72% 16%, rgba(38, 198, 218, 0.11), transparent 32%),
        linear-gradient(135deg, #000000 0%, #0a0a0a 50%, #111111 100%);
      color: var(--text);
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }
    body::before {
      content: "";
      position: fixed;
      inset: 0;
      pointer-events: none;
      background: url("/assets/chart_watermark.svg") center 92px / min(980px, 92vw) no-repeat;
      opacity: 0.68;
      filter: saturate(1.45) brightness(1.55) contrast(1.08);
      mix-blend-mode: screen;
      z-index: 0;
    }
    body::after {
      content: "";
      position: fixed;
      inset: 0;
      pointer-events: none;
      background:
        linear-gradient(180deg, rgba(0, 0, 0, 0.10), rgba(0, 0, 0, 0.38)),
        radial-gradient(circle at 50% 0%, rgba(255, 255, 255, 0.05), transparent 36%);
      z-index: 0;
    }
    .brandbar {
      position: relative;
      z-index: 1;
      height: 80px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 0 max(20px, calc((100vw - 1120px) / 2 + 24px));
      border-bottom: 1px solid rgba(255, 255, 255, 0.06);
      background: rgba(0, 0, 0, 0.28);
      backdrop-filter: blur(12px);
    }
    .brand {
      display: inline-flex;
      align-items: center;
      gap: 14px;
      color: var(--text);
      text-decoration: none;
      min-width: 0;
    }
    .brand img { width: 190px; height: auto; display: block; }
    .brand span {
      color: var(--muted);
      font-size: 13px;
      border-left: 1px solid rgba(255, 255, 255, 0.1);
      padding-left: 14px;
      white-space: nowrap;
    }
    .brand-meta {
      color: var(--soft);
      font-size: 12px;
      text-transform: uppercase;
    }
    main {
      position: relative;
      z-index: 1;
      width: min(1120px, calc(100vw - 48px));
      margin: 0 auto;
      padding: 34px 0 48px;
    }
    .hero, .panel {
      border: 1px solid var(--line);
      background: linear-gradient(180deg, rgba(18, 20, 22, 0.52), rgba(0, 0, 0, 0.48));
      border-radius: 8px;
      box-shadow: 0 20px 60px rgba(0, 0, 0, 0.28);
      backdrop-filter: blur(5px) saturate(1.04);
      -webkit-backdrop-filter: blur(5px) saturate(1.04);
    }
    .hero {
      display: flex;
      justify-content: space-between;
      gap: 20px;
      align-items: flex-start;
      padding: 24px;
    }
    h1 {
      margin: 0 0 8px;
      color: #fff;
      font-size: clamp(30px, 4vw, 46px);
      line-height: 1.12;
      letter-spacing: 0;
    }
    .subtitle {
      max-width: 780px;
      color: var(--muted);
      line-height: 1.45;
      font-size: 14px;
    }
    .actions {
      display: flex;
      gap: 10px;
      flex-wrap: wrap;
      justify-content: flex-end;
    }
    .btn {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      min-height: 36px;
      padding: 0 13px;
      border-radius: 8px;
      border: 1px solid var(--line);
      color: var(--text);
      text-decoration: none;
      font-size: 13px;
      white-space: nowrap;
      background: rgba(255, 255, 255, 0.03);
    }
    .btn.primary, .btn.secondary {
      border-color: var(--accent-line);
      background: rgba(38, 198, 218, 0.08);
      color: rgba(224, 242, 254, 0.96);
    }
    .facts {
      display: flex;
      flex-wrap: wrap;
      gap: 7px;
      margin-top: 16px;
    }
    .facts span {
      border: 1px solid var(--line);
      background: rgba(255, 255, 255, 0.035);
      border-radius: 999px;
      padding: 5px 9px;
      color: rgba(255, 255, 255, 0.76);
      font-size: 12px;
    }
    .grid {
      margin-top: 18px;
      display: grid;
      grid-template-columns: minmax(0, 1fr) minmax(280px, 0.7fr);
      gap: 16px;
      align-items: start;
    }
    .panel {
      padding: 18px;
    }
    .panel h2 {
      margin: 0 0 14px;
      color: #fff;
      font-size: 18px;
      line-height: 1.25;
    }
    .param-grid {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 8px;
    }
    .param-row, .metric-row {
      display: grid;
      gap: 3px;
      border: 1px solid rgba(255, 255, 255, 0.06);
      background: rgba(0, 0, 0, 0.34);
      border-radius: 8px;
      padding: 9px;
    }
    .param-row span, .metric-row span {
      color: var(--muted);
      font-size: 12px;
    }
    .param-row strong, .metric-row strong {
      color: #fff;
      font-size: 14px;
      font-weight: 650;
      overflow-wrap: anywhere;
    }
    .metric-list {
      display: grid;
      gap: 8px;
    }
    .trial-callout {
      margin-bottom: 16px;
      border: 1px solid var(--accent-line);
      background: rgba(38, 198, 218, 0.08);
      border-radius: 8px;
      padding: 14px;
    }
    .trial-callout span {
      display: block;
      color: var(--muted);
      font-size: 12px;
      margin-bottom: 4px;
    }
    .trial-callout strong {
      color: #fff;
      font-size: 24px;
    }
    table {
      width: 100%;
      border-collapse: collapse;
      font-size: 12px;
    }
    th, td {
      border-bottom: 1px solid rgba(255, 255, 255, 0.06);
      padding: 9px 6px;
      text-align: left;
      color: rgba(255, 255, 255, 0.72);
    }
    th {
      color: var(--muted);
      font-weight: 600;
    }
    .empty-inline {
      color: var(--muted);
      font-size: 13px;
    }
    @media (max-width: 860px) {
      .brandbar {
        height: auto;
        min-height: 72px;
        align-items: flex-start;
        flex-direction: column;
        gap: 8px;
        padding: 16px 20px;
      }
      .brand { flex-wrap: wrap; }
      .brand img { width: 150px; }
      .brand span { border-left: 0; padding-left: 0; }
      .brand-meta { display: none; }
      main { width: min(100vw - 32px, 1120px); }
      .hero { flex-direction: column; }
      .actions { justify-content: flex-start; }
      .grid { grid-template-columns: 1fr; }
      .param-grid { grid-template-columns: 1fr; }
    }
    """

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{_h(study['title'])}</title>
  <style>{detail_css}</style>
</head>
<body>
  <header class="brandbar">
    <a class="brand" href="/">
      <img src="/assets/warbird-logo.svg" alt="Warbird Pro" />
      <span>Optuna Study Operations</span>
    </a>
    <div class="brand-meta">Local Operator Surface</div>
  </header>
  <main>
    <section class="hero">
      <div>
        <h1>{_h(study['title'])}</h1>
        <div class="subtitle">{_h(display_name)} · {_h(study['purpose'])}</div>
        <div class="facts">{facts_html}</div>
      </div>
      <div class="actions">
        <a class="btn" href="/studies/{_h(card['key'])}">Back to Studies</a>
        {raw_link}
      </div>
    </section>

    <section class="grid">
      <div class="panel">
        <h2>Best Parameters</h2>
        <div class="param-grid">{params_html}</div>
      </div>
      <aside class="panel">
        <div class="trial-callout">
          <span>{_h(best_trial_text)}</span>
          <strong>{_h(best_score_text)}</strong>
        </div>
        <h2>Best Trial Metrics</h2>
        <div class="metric-list">{metrics_html}</div>
      </aside>
      <div class="panel" style="grid-column: 1 / -1;">
        <h2>Top Completed Trials</h2>
        <table>
          <thead>
            <tr><th>Trial</th><th>Score</th><th>State</th><th>Completed</th></tr>
          </thead>
          <tbody>{trials_html}</tbody>
        </table>
      </div>
    </section>
  </main>
</body>
</html>"""


def _detect_optuna_dashboard_bin(user_path: str | None) -> str:
    if user_path:
        p = Path(user_path)
        if p.exists():
            return str(p)
        raise SystemExit(f"--optuna-dashboard-bin not found: {p}")

    repo_bin = REPO_ROOT / ".venv" / "bin" / "optuna-dashboard"
    if repo_bin.exists():
        return str(repo_bin)

    resolved = shutil.which("optuna-dashboard")
    if resolved:
        return resolved

    raise SystemExit(
        "optuna-dashboard binary not found. Install dependencies and/or pass "
        "--optuna-dashboard-bin /absolute/path/to/optuna-dashboard"
    )


def _build_handler(state: HubState):
    class HubHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            parsed = urlparse(self.path)
            snap = state.snapshot()

            if parsed.path in PUBLIC_ASSETS:
                asset_path = PUBLIC_ASSETS[parsed.path]
                if not asset_path.exists():
                    self.send_error(404, f"Asset not found: {parsed.path}")
                    return
                payload = asset_path.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "image/svg+xml; charset=utf-8")
                self.send_header("Cache-Control", "public, max-age=3600")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)
                return

            if parsed.path == "/favicon.ico":
                self.send_response(204)
                self.end_headers()
                return

            if parsed.path in {"/", "/index.html"}:
                payload = render_html(snap).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)
                return

            if parsed.path == "/api/snapshot":
                payload = json.dumps(snap, indent=2).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)
                return

            if parsed.path.startswith("/studies/"):
                parts = [part for part in parsed.path.removeprefix("/studies/").split("/") if part]
                if not parts:
                    self.send_error(404, "Missing workspace key")
                    return
                if len(parts) > 2:
                    self.send_error(404, "Unknown study route")
                    return
                key = parts[0]
                card = next((c for c in snap["cards"] if c["key"] == key), None)
                if card is None:
                    self.send_error(404, f"Unknown workspace key: {key}")
                    return
                if len(parts) == 2:
                    if not parts[1].isdigit():
                        self.send_error(404, f"Unknown study id: {parts[1]}")
                        return
                    payload_html = render_study_detail(card, _safe_int(parts[1]), snap["child_dashboards_enabled"])
                    if payload_html is None:
                        self.send_error(404, f"Study not found: {parts[1]}")
                        return
                    payload = payload_html.encode("utf-8")
                    self.send_response(200)
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                    self.send_header("Content-Length", str(len(payload)))
                    self.end_headers()
                    self.wfile.write(payload)
                    return
                payload = render_study_landing(card, snap["child_dashboards_enabled"]).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)
                return

            if parsed.path.startswith("/open-study/"):
                key = parsed.path.removeprefix("/open-study/").strip("/")
                if not key:
                    self.send_error(404, "Missing workspace key")
                    return
                if not state.spawn_children or state.child_manager is None:
                    self.send_error(409, "Child dashboards are disabled for this hub instance")
                    return

                ordered_keys = [c["key"] for c in sorted(snap["cards"], key=lambda x: x["key"]) if c["db_exists"]]
                card = next((c for c in snap["cards"] if c["key"] == key), None)
                if card is None:
                    self.send_error(404, f"Unknown workspace key: {key}")
                    return
                if not card["db_exists"]:
                    self.send_error(409, f"No study database found for workspace: {key}")
                    return

                runtime = state.child_manager.ensure_child(
                    ordered_keys=ordered_keys,
                    key=key,
                    db_path=Path(card["db_path"]),
                )
                link = state.child_manager.card_link(key)
                if runtime.err or link is None:
                    self.send_error(503, state.child_manager.card_error(key) or f"Failed to launch dashboard for {key}")
                    return

                self.send_response(302)
                self.send_header("Location", link)
                self.end_headers()
                return

            self.send_error(404, "Not found")

        def log_message(self, format: str, *args: Any) -> None:
            return

    return HubHandler


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Warbird multi-indicator Optuna dashboard hub")
    parser.add_argument("--host", default=DEFAULT_HOST, help=f"Hub host (default: {DEFAULT_HOST})")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help=f"Hub port (default: {DEFAULT_PORT})")
    parser.add_argument(
        "--child-port-start",
        type=int,
        default=DEFAULT_CHILD_PORT_START,
        help=f"Child optuna-dashboard start port (default: {DEFAULT_CHILD_PORT_START})",
    )
    parser.add_argument(
        "--no-child-dashboards",
        action="store_true",
        help="Do not launch child optuna-dashboard processes per study DB",
    )
    parser.add_argument(
        "--optuna-dashboard-bin",
        default=None,
        help="Optional absolute path to optuna-dashboard executable",
    )
    parser.add_argument(
        "--init-folders-only",
        action="store_true",
        help="Ensure the workspace root exists and exit",
    )
    parser.add_argument(
        "--print-layout",
        action="store_true",
        help="Print indicator -> folder mapping and exit",
    )
    return parser.parse_args()


def print_layout(specs: list[IndicatorSpec]) -> None:
    print("Warbird Optuna indicator/strategy layout")
    print("=" * 44)
    for spec in sorted(specs, key=lambda x: (x.category, x.surface_type, x.name)):
        indicator_dir = resolve_indicator_dir(spec)
        exp_dir = experiments_dir(spec.key)
        db_path = indicator_dir / "study.db"
        print(
            f"{spec.key:28} {spec.surface_type:10} workspace={indicator_dir} experiments={exp_dir} "
            f"(db: {db_path.name}, study_name: {spec.default_study_name})"
        )


def main() -> None:
    args = parse_args()

    specs = load_registry(REGISTRY_PATH)
    ensure_layout(specs)

    if args.print_layout:
        print_layout(specs)
        return

    if args.init_folders_only:
        print("Indicator folders initialized.")
        return

    spawn_children = not args.no_child_dashboards
    child_manager: ChildManager | None = None
    if spawn_children:
        optuna_bin = _detect_optuna_dashboard_bin(args.optuna_dashboard_bin)
        child_manager = ChildManager(
            optuna_dashboard_bin=optuna_bin,
            host=args.host,
            port_start=args.child_port_start,
        )
        atexit.register(child_manager.shutdown)

    state = HubState(
        specs=specs,
        host=args.host,
        port=args.port,
        spawn_children=spawn_children,
        child_manager=child_manager,
    )

    handler_cls = _build_handler(state)
    httpd = ThreadingHTTPServer((args.host, args.port), handler_cls)

    def _shutdown(*_: Any) -> None:
        try:
            httpd.shutdown()
        except Exception:
            pass

    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)

    print("Warbird Optuna Hub running")
    print(f"  Hub URL:          http://{_display_host(args.host)}:{args.port}")
    print(f"  Snapshot API:     http://{_display_host(args.host)}:{args.port}/api/snapshot")
    print(f"  Registry:         {REGISTRY_PATH}")
    print(f"  Child UIs:        {'enabled' if spawn_children else 'disabled'}")
    print(f"  Workspace root:   {WORKSPACES_ROOT}")
    sys.stdout.flush()

    try:
        httpd.serve_forever(poll_interval=0.5)
    finally:
        if child_manager is not None:
            child_manager.shutdown()
        httpd.server_close()


if __name__ == "__main__":
    main()
