#!/usr/bin/env python3
"""DEPRECATED 2026-05-09 — Hybrid+ Card 3 (warbird_pro_v9_ag_meta_cpcv).

The Hybrid+ 4-card chain (exit_cpcv + entry_filter_cpcv + this card +
joint_challenger) was scrapped. Path went 4 cards -> 2 cards -> single Core
AutoGluon card. See docs/MASTER_PLAN.md "V9 Core AutoGluon" section and the
`warbird_pro_core` entry in scripts/optuna/indicator_registry.json.

This file is retained for git history only. It is NOT runnable: importing it
raises SystemExit. It also references V8-era features (ml_pat_morning_star,
ml_in_zone, ml_bar_delta, ml_net_delta_20, ml_exhaust_*) that current V9 Pine
no longer emits.
"""
from __future__ import annotations

import sys

raise SystemExit(
    "warbird_pro_v9_ag_meta_cpcv_profile is DEPRECATED (Hybrid+ Card 3). "
    "Use scripts/optuna/cards/core_training/2026_05_09_warbird_pro_autogluon_core.py instead."
)

# --- legacy code below (unreachable) -----------------------------------------
import json
import os
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

# Apple Silicon OpenMP guards must precede any AG/lightgbm import path.
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")
os.environ.setdefault("MKL_NUM_THREADS", "1")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("LIGHTGBM_NUM_THREADS", "1")

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.optuna import warbird_pro_v9_profile as _strategy_base
from scripts.optuna.cpcv_helpers import (
    REQUIRED_AG_USER_ATTRS,  # noqa: F401  (imported so test can introspect)
    ag_embargoed_train_and_score,
)
from scripts.optuna.paths import workspace_dir

PROFILE_KEY = "warbird_pro_v9_ag_meta_cpcv"
TRIGGER_FAMILY = _strategy_base.TRIGGER_FAMILY
PINE_FILE = _strategy_base.PINE_FILE
DATA_FLOOR = _strategy_base.DATA_FLOOR
MIN_TRADES = 200  # AG needs more rows than the strategy lanes
OBJECTIVE_METRIC = "ag_gating_lift"

LABEL_COL = "winner"
ML_FEATURES: list[str] = [
    "ml_atr14", "ml_dir", "ml_fib_range",
    "ml_pivot_dist_atr", "ml_p618_dist_atr",
    "ml_bars_since_break", "ml_break_in_dir",
    "ml_rsi_value", "ml_rsi_stance_code", "ml_ma_bias",
    "ml_pat_hammer", "ml_pat_inv_hammer", "ml_pat_dragonfly",
    "ml_pat_bull_engulf", "ml_pat_piercing", "ml_pat_morning_star",
    "ml_pat_three_white",
    "ml_pat_shooting_star", "ml_pat_hanging_man", "ml_pat_gravestone",
    "ml_pat_bear_engulf", "ml_pat_dark_cloud", "ml_pat_evening_star",
    "ml_pat_three_black",
    "ml_bsl_dist_atr", "ml_ssl_dist_atr",
    "ml_swept_bsl", "ml_swept_ssl", "ml_reclaimed_bsl", "ml_reclaimed_ssl",
    "ml_bar_delta", "ml_net_delta_20",
    "ml_xa_nq_code",
    "ml_exhaust_long", "ml_exhaust_short", "ml_htf_conf_total",
]

CANDIDATES_ENV = "WARBIRD_V9_AG_CANDIDATES"
DEFAULT_CANDIDATES_PATH = (
    workspace_dir(PROFILE_KEY) / "strategy_candidates.json"
)

# Top-K candidate manifest is written by orchestrate_v9_run.py from Cards 1+2
# top-N exports. If the manifest is missing this profile falls back to the
# base exit-policy INPUT_DEFAULTS as a single candidate so the card still runs
# in a smoke test.
_FALLBACK_CANDIDATES = [
    {"id": 0, "label": "fallback_defaults", "params": dict(_strategy_base.INPUT_DEFAULTS)},
]


def _load_candidates() -> list[dict[str, Any]]:
    path = Path(os.environ.get(CANDIDATES_ENV, str(DEFAULT_CANDIDATES_PATH)))
    if not path.exists():
        return list(_FALLBACK_CANDIDATES)
    try:
        data = json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Card-3 candidate manifest invalid JSON ({path}): {exc}")
    if not isinstance(data, list) or not data:
        raise SystemExit(f"Card-3 candidate manifest must be a non-empty list ({path})")
    for entry in data:
        if not isinstance(entry, dict) or "params" not in entry:
            raise SystemExit(f"Card-3 candidate entry missing 'params' field: {entry}")
    return data


_CANDIDATES_CACHE: list[dict[str, Any]] | None = None


def _candidates() -> list[dict[str, Any]]:
    global _CANDIDATES_CACHE
    if _CANDIDATES_CACHE is None:
        _CANDIDATES_CACHE = _load_candidates()
    return _CANDIDATES_CACHE


def _candidate_ids() -> list[int]:
    return [int(c.get("id", i)) for i, c in enumerate(_candidates())]


# ── Optuna profile contract ─────────────────────────────────────────────────

CATEGORICAL_PARAMS: dict[str, list[Any]] = {
    "ag_family": ["BEST"],  # best_quality preset: full model zoo + stacking
    "strategy_candidate_id": _candidate_ids(),
}

NUMERIC_RANGES: dict[str, tuple[float, float]] = {
    "prob_threshold": (0.50, 0.75),
    "ag_time_limit": (3600.0, 14400.0),  # 1–4 hours per fit
}

INT_PARAMS: set[str] = {"ag_time_limit"}
BOOL_PARAMS: list[str] = []
INPUT_DEFAULTS: dict[str, Any] = {
    "ag_family": "BEST",
    "strategy_candidate_id": _candidate_ids()[0] if _candidate_ids() else 0,
    "prob_threshold": 0.55,
    "ag_time_limit": 7200,  # 2-hour default
}


def assert_v9_contract() -> None:
    _strategy_base.assert_v9_contract()
    if not _candidate_ids():
        raise AssertionError("Card 3 has zero strategy candidates loaded.")


def load_data() -> pd.DataFrame:
    """Card 3 reuses the strategy lane's load_data which already enforces
    Databento manifest, MES-only, and the 2020-01-01 data floor."""
    return _strategy_base.load_data()


def objective_score(result: dict[str, Any]) -> float:
    return float(result.get(OBJECTIVE_METRIC, 0.0) or 0.0)


# ── Trade builder ───────────────────────────────────────────────────────────

def _build_labeled_trades(
    df: pd.DataFrame,
    max_hold_bars: int,
) -> pd.DataFrame:
    df = df.sort_values("ts").reset_index(drop=True)
    long_mask = df["ml_entry_long_trigger"].astype(float) > 0
    short_mask = df["ml_entry_short_trigger"].astype(float) > 0
    entry_idx = np.where(long_mask | short_mask)[0]
    if entry_idx.size == 0:
        return pd.DataFrame()

    outcomes = df["ml_last_exit_outcome"].astype(float).to_numpy()
    feature_cols = [c for c in ML_FEATURES if c in df.columns]
    rows: list[dict[str, Any]] = []
    for i in entry_idx:
        end = min(i + max_hold_bars + 1, len(df))
        future = outcomes[i + 1 : end]
        nz = np.where(future != 0)[0]
        if nz.size == 0:
            continue
        offset = int(nz[0])
        rec = {col: df[col].iloc[i] for col in feature_cols}
        rec["ts"] = df["ts"].iloc[i]
        rec[LABEL_COL] = 1 if int(future[offset]) == 1 else 0
        rows.append(rec)
    return pd.DataFrame(rows)


# ── run_backtest (Optuna trial body) ─────────────────────────────────────────

def run_backtest(df: pd.DataFrame, params: dict[str, Any], start_date: str) -> dict[str, Any]:
    assert_v9_contract()

    candidate_id = int(params.get("strategy_candidate_id", _candidate_ids()[0]))
    candidates_by_id = {int(c.get("id", i)): c for i, c in enumerate(_candidates())}
    candidate = candidates_by_id.get(candidate_id)
    if candidate is None:
        return _ag_card_empty_result(
            candidate_id=candidate_id,
            label_horizon=int(_strategy_base.INPUT_DEFAULTS["maxHoldBars"]),
            fit_status="unknown_candidate",
            leakage={"unknown_candidate": candidate_id},
            params=params,
        )

    cand_params = dict(_strategy_base.INPUT_DEFAULTS)
    cand_params.update(candidate.get("params") or {})
    max_hold = int(cand_params.get("maxHoldBars", _strategy_base.INPUT_DEFAULTS["maxHoldBars"]))

    start_ts = pd.Timestamp(start_date)
    start_ts = start_ts.tz_localize("UTC") if start_ts.tzinfo is None else start_ts.tz_convert("UTC")
    is_df = df.loc[pd.to_datetime(df["ts"], utc=True) >= start_ts].copy()

    trades = _build_labeled_trades(is_df, max_hold_bars=max_hold)
    if len(trades) < MIN_TRADES:
        wr = float(trades[LABEL_COL].mean()) if len(trades) else 0.0
        return _ag_card_empty_result(
            candidate_id=candidate_id,
            label_horizon=int(max_hold),
            fit_status="too_few_trades",
            leakage={},
            params=params,
            trades=int(len(trades)),
            win_rate=wr,
        )

    family = str(params.get("ag_family", "GBM"))
    ag_hyperparams = _resolve_family_hyperparameters(family)
    time_limit = int(params.get("ag_time_limit", INPUT_DEFAULTS["ag_time_limit"]))
    prob_threshold = float(params.get("prob_threshold", INPUT_DEFAULTS["prob_threshold"]))

    output_dir = workspace_dir(PROFILE_KEY) / f"trial_models" / f"cand{candidate_id}_{family}_{time_limit}s"
    feature_cols = [c for c in ML_FEATURES if c in trades.columns]

    ag_result = ag_embargoed_train_and_score(
        trades_df=trades,
        label_col=LABEL_COL,
        feature_cols=feature_cols,
        ag_hyperparams=ag_hyperparams,
        label_horizon_bars=max_hold,
        output_dir=output_dir,
        time_limit=time_limit,
        prob_threshold=prob_threshold,
    )

    lift = float(ag_result.get("lift", 0.0)) if ag_result.get("fit_status") == "ok" else 0.0
    leakage_flags = ag_result.get("leakage_flags", {}) or {}

    summary = {
        "trades": int(ag_result.get("n_test", 0)),
        "win_rate": float(ag_result.get("gated_winrate", 0.0) or 0.0),
        "pf": 0.0,  # AG card scores via lift, not PF — keep neutral for legacy ranker
        "gross_profit": 0.0,
        "gross_loss": 0.0,
        "max_dd_abs": 0.0,
        OBJECTIVE_METRIC: lift,
        "fit_status": str(ag_result.get("fit_status", "unknown")),
        "model_path": str(ag_result.get("model_path", str(output_dir))),
        "prob_threshold": prob_threshold,
        "leakage_flags": json.dumps(leakage_flags),
        "candidate_id": candidate_id,
        "candidate_label": str(candidate.get("label", "")),
        "ag_family": family,
        "ag_time_limit": time_limit,
        "ag_test_auc": float(ag_result.get("test_auc", 0.0) or 0.0),
        "ag_test_brier": float(ag_result.get("test_brier", 0.0) or 0.0),
        "ag_n_train": int(ag_result.get("n_train", 0) or 0),
        "ag_n_val": int(ag_result.get("n_val", 0) or 0),
        "ag_n_test": int(ag_result.get("n_test", 0) or 0),
        "ag_n_gated": int(ag_result.get("n_gated", 0) or 0),
        "ag_base_winrate": float(ag_result.get("base_winrate", 0.0) or 0.0),
        "ag_gated_winrate": float(ag_result.get("gated_winrate", 0.0) or 0.0),
        "ag_lift": lift,
        "label_horizon_bars": int(max_hold),
    }
    return summary


def _ag_card_empty_result(
    *,
    candidate_id: int,
    label_horizon: int,
    fit_status: str,
    leakage: dict[str, Any],
    params: dict[str, Any],
    trades: int = 0,
    win_rate: float = 0.0,
) -> dict[str, Any]:
    """Shape-stable empty/short-circuit result for Card 3.

    Always emits the bare-key contract required by cpcv_helpers
    (model_path, prob_threshold, fit_status, leakage_flags) so trial
    user_attrs render uniformly on the dashboard regardless of fit_status.
    """
    return {
        "trades": int(trades),
        "win_rate": float(win_rate),
        "pf": 0.0,
        "gross_profit": 0.0,
        "gross_loss": 0.0,
        "max_dd_abs": 0.0,
        OBJECTIVE_METRIC: 0.0,
        "fit_status": str(fit_status),
        "model_path": "",
        "prob_threshold": float(params.get("prob_threshold", INPUT_DEFAULTS["prob_threshold"])),
        "leakage_flags": json.dumps(leakage or {}),
        "candidate_id": int(candidate_id),
        "label_horizon_bars": int(label_horizon),
    }


def _resolve_family_hyperparameters(family: str) -> dict[str, Any] | None:
    """Return AG hyperparameters dict, or None for best_quality full-zoo mode.

    None signals ag_embargoed_train_and_score to use presets="best_quality"
    (LightGBM + CatBoost + XGBoost + Neural Net + RF + ExtraTrees ensemble).
    """
    family = family.upper()
    if family == "BEST":
        return None  # ag_embargoed_train_and_score uses best_quality preset
    if family == "GBM":
        return {"GBM": [{"num_threads": 1}]}
    if family == "CAT":
        return {"CAT": [{"thread_count": 1}]}
    if family == "XGB":
        return {"XGB": [{"n_jobs": 1}]}
    raise ValueError(f"Unsupported AG family for Card 3: {family}")
