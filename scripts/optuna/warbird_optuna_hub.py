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
    parts.append(f"--study-name {spec.default_study_name}")
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
        if _safe_int(best.get("quality_events"), 0) > 0:
            best_text = (
                f'{_h(best["indicator_name"])} ({_h(best["indicator_key"])}) '
                f'Score {_safe_float(best["objective_score"]):.3f} | Events {_safe_int(best["quality_events"])}'
            )
        else:
            best_text = (
                f'{_h(best["indicator_name"])} ({_h(best["indicator_key"])}) '
                f'WR {_safe_float(best["win_rate"]):.2%} | PF {_safe_float(best["pf"]):.3f} | '
                f'Trades {_safe_int(best["trades"])}'
            )

    stack = snapshot["stack_health"]
    ag_badge_class = "ok" if stack["availability"]["autogluon_1_5"] else "warn"
    ag_badge_text = "AutoGluon 1.5 READY" if stack["availability"]["autogluon_1_5"] else "AutoGluon 1.5 MISSING"

    cards_html: list[str] = []
    for idx, card in enumerate(snapshot["cards"]):
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

        link_html = "<span class='btn disabled'>No DB</span>"
        if card["dashboard_url"]:
            link_html = (
                f"<a class='btn' href='{_h(card['dashboard_url'])}' target='_blank' rel='noreferrer'>"
                "Open Study UI</a>"
            )
        elif card["db_exists"] and snapshot["child_dashboards_enabled"]:
            link_html = (
                f"<a class='btn' href='/open-study/{_h(card['key'])}' target='_blank' rel='noreferrer'>"
                "Launch Study UI</a>"
            )
        elif card["db_exists"]:
            link_html = "<span class='btn disabled'>Dashboard Offline</span>"

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
            f"data-name='{_h(card['name'])}' "
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
            f"<header><h3>{_h(card['name'])}</h3><span class='badge'>{_h(card['key'])}</span></header>"
            "<div class='meta-line'>"
            f"<span class='chip surface'>{_h(card['surface_type'])}</span>"
            f"<span class='chip category'>{_h(card['category'])}</span>"
            f"<span class='chip {profile_class}'>{_h(card['profile_label'])}</span>"
            "</div>"
            f"<div class='path'><span>Active Study:</span> {_h(card['default_study_name'])}</div>"
            f"<div class='path'><span>Pine:</span> {_h(card['pine_file'])}</div>"
            f"<div class='path'><span>Workspace:</span> {_h(card['indicator_dir'])}</div>"
            f"<div class='path'><span>Experiments:</span> {_h(card['experiments_dir'])}</div>"
            f"<div class='path'><span>DB:</span> {_h(card['db_path'])}</div>"
            f"<div class='path'><span>Top-N:</span> {_h(card['topn_path'])}</div>"
            f"{notes_html}"
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
            "<details class='cmd'>"
            "<summary>Run Command</summary>"
            f"<pre>{_h(card['run_command'])}</pre>"
            "</details>"
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
      --bg: #040b17;
      --panel: #0f1a2f;
      --panel-2: #152640;
      --text: #d8e7ff;
      --muted: #8ea7ca;
      --accent: #22d3ee;
      --ok: #22c55e;
      --warn: #f59e0b;
      --bad: #ef4444;
      --border: #22395d;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Ubuntu, Cantarell, Noto Sans, Arial;
      background: radial-gradient(circle at top right, #112342 0%, var(--bg) 60%);
      color: var(--text);
    }}
    .wrap {{
      max-width: 1500px;
      margin: 0 auto;
      padding: 18px 16px 28px;
    }}
    .top {{
      display: grid;
      grid-template-columns: 1.6fr repeat(6, minmax(130px, 1fr));
      gap: 10px;
      margin-bottom: 14px;
    }}
    .summary {{
      background: linear-gradient(160deg, #0d1d35 0%, #18345c 100%);
      border: 1px solid var(--border);
      border-radius: 12px;
      padding: 12px;
      min-height: 108px;
    }}
    .summary h1 {{
      margin: 0 0 5px;
      font-size: 20px;
      letter-spacing: 0.2px;
    }}
    .meta {{
      color: var(--muted);
      font-size: 12px;
      line-height: 1.35;
    }}
    .best {{
      margin-top: 8px;
      color: #67e8f9;
      font-size: 13px;
    }}
    .stack {{
      margin-top: 6px;
      font-size: 12px;
      color: #bfdbfe;
    }}
    .stack-badge {{
      display: inline-block;
      font-size: 11px;
      padding: 2px 7px;
      border-radius: 999px;
      margin-right: 8px;
      border: 1px solid transparent;
    }}
    .stack-badge.ok {{ color: #bbf7d0; border-color: #14532d; background: #052e16; }}
    .stack-badge.warn {{ color: #fde68a; border-color: #78350f; background: #451a03; }}
    .kpi {{
      background: var(--panel);
      border: 1px solid var(--border);
      border-radius: 12px;
      padding: 10px;
      display: grid;
      align-content: center;
      gap: 3px;
    }}
    .kpi .label {{ color: var(--muted); font-size: 11px; }}
    .kpi .value {{ font-size: 22px; font-weight: 700; }}
    .toolbar {{
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      margin-bottom: 12px;
      align-items: center;
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
      border: 1px solid #244670;
      background: #0b203f;
      color: #dbeafe;
      border-radius: 999px;
      padding: 5px 10px;
      cursor: pointer;
    }}
    .filter-btn.active {{
      border-color: #0891b2;
      background: #083344;
      color: #cffafe;
    }}
    .sort-select {{
      font-size: 11px;
      border: 1px solid #244670;
      background: #0b203f;
      color: #dbeafe;
      border-radius: 8px;
      padding: 5px 10px;
      min-width: 140px;
    }}
    .grid {{
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(380px, 1fr));
      gap: 10px;
    }}
    .card {{
      background: linear-gradient(180deg, var(--panel) 0%, var(--panel-2) 100%);
      border: 1px solid var(--border);
      border-radius: 12px;
      padding: 11px;
      display: grid;
      gap: 7px;
      box-shadow: 0 6px 14px rgba(0, 0, 0, 0.24);
    }}
    .card header {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 10px;
    }}
    .card h3 {{
      margin: 0;
      font-size: 16px;
      font-weight: 700;
      line-height: 1.2;
    }}
    .badge {{
      font-size: 11px;
      color: #cffafe;
      border: 1px solid #164e63;
      background: #083344;
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
      letter-spacing: 0.4px;
    }}
    .chip.surface {{ color: #bfdbfe; background: #172554; border-color: #1d4ed8; }}
    .chip.category {{ color: #e0f2fe; background: #164e63; border-color: #0e7490; }}
    .chip.ok {{ color: #bbf7d0; background: #052e16; border-color: #14532d; text-transform: none; }}
    .chip.warn {{ color: #fde68a; background: #451a03; border-color: #78350f; text-transform: none; }}
    .path {{
      color: #bfd7f7;
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
    .status.ready {{ color: #86efac; border-color: #14532d; background: #052e16; }}
    .status.warn {{ color: #fde68a; border-color: #78350f; background: #451a03; }}
    .status.empty {{ color: #fde68a; border-color: #78350f; background: #451a03; }}
    .status.error {{ color: #fecaca; border-color: #7f1d1d; background: #450a0a; }}
    .counts {{
      display: flex;
      flex-wrap: wrap;
      gap: 5px;
    }}
    .counts span {{
      font-size: 11px;
      color: #dbeafe;
      background: rgba(15, 23, 42, 0.65);
      border: 1px solid #1e3a5f;
      border-radius: 999px;
      padding: 2px 7px;
    }}
    .metrics {{
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 5px;
    }}
    .metrics div {{
      background: rgba(2, 8, 25, 0.5);
      border: 1px solid #20314d;
      border-radius: 8px;
      padding: 6px 7px;
      display: grid;
      gap: 2px;
    }}
    .metrics span {{ color: var(--muted); font-size: 11px; }}
    .metrics strong {{ font-size: 13px; color: #f0f9ff; }}
    .muted {{ color: var(--muted); font-size: 12px; }}
    .topn {{
      font-size: 11px;
      color: #86efac;
      background: rgba(5, 46, 22, 0.5);
      border: 1px solid #14532d;
      border-radius: 8px;
      padding: 4px 6px;
    }}
    details.cmd {{
      background: rgba(8, 15, 32, 0.8);
      border: 1px solid #1f3759;
      border-radius: 8px;
      padding: 6px;
    }}
    details.cmd summary {{
      cursor: pointer;
      color: #bfdbfe;
      font-size: 12px;
    }}
    details.cmd pre {{
      margin: 8px 0 0;
      color: #e0f2fe;
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
      padding: 6px 10px;
      border-radius: 8px;
      font-size: 12px;
      text-decoration: none;
      border: 1px solid #0e7490;
      background: #083344;
      color: #cffafe;
    }}
    .btn.disabled {{
      border-color: #334155;
      background: #0f172a;
      color: #64748b;
    }}
    .warning {{
      font-size: 11px;
      color: #fecaca;
      background: #450a0a;
      border: 1px solid #7f1d1d;
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
  </style>
</head>
<body>
  <main class="wrap">
    <section class="top">
      <div class="summary">
        <h1>Warbird Optuna Hub</h1>
        <div class="meta">Unified dashboard for all indicators + strategies with AutoGluon 1.5 readiness checks.</div>
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
        const bestKey = stringAttr(bestCard, 'data-key');
        const events = numberAttr(bestCard, 'data-best-events', 0);
        if (events > 0) {{
          const score = numberAttr(bestCard, 'data-best-score', 0);
          bestText.textContent = `${{bestName}} (${{bestKey}}) Score ${{score.toFixed(3)}} | Events ${{events}}`;
          return;
        }}
        const winRate = numberAttr(bestCard, 'data-best-win-rate', 0) * 100;
        const pf = numberAttr(bestCard, 'data-best-pf', 0);
        const trades = numberAttr(bestCard, 'data-best-trades', 0);
        bestText.textContent = `${{bestName}} (${{bestKey}}) WR ${{winRate.toFixed(2)}}% | PF ${{pf.toFixed(3)}} | Trades ${{trades}}`;
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
