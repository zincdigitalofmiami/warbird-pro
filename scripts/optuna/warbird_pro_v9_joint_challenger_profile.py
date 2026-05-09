#!/usr/bin/env python3
"""DEPRECATED 2026-05-09 — Hybrid+ Card 4 (warbird_pro_v9_joint_challenger).

The Hybrid+ 4-card chain (exit_cpcv + entry_filter_cpcv + ag_meta_cpcv +
this card) was scrapped. Path went 4 cards -> 2 cards -> single Core
AutoGluon card. See docs/MASTER_PLAN.md "V9 Core AutoGluon" section and the
`warbird_pro_core` entry in scripts/optuna/indicator_registry.json.

This file is retained for git history only. It is NOT runnable: importing it
raises SystemExit.
"""
from __future__ import annotations

import sys

raise SystemExit(
    "warbird_pro_v9_joint_challenger_profile is DEPRECATED (Hybrid+ Card 4). "
    "Use scripts/optuna/cards/core_training/2026_05_09_warbird_pro_autogluon_core.py instead."
)

# --- legacy code below (unreachable) -----------------------------------------
import json
import os
from pathlib import Path
from typing import Any

import pandas as pd

os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")
os.environ.setdefault("MKL_NUM_THREADS", "1")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("LIGHTGBM_NUM_THREADS", "1")

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.optuna import warbird_pro_v9_profile as _strategy_base
from scripts.optuna.cpcv_helpers import ag_embargoed_train_and_score
from scripts.optuna.paths import workspace_dir
from scripts.optuna.warbird_pro_v9_ag_meta_cpcv_profile import (
    LABEL_COL,
    ML_FEATURES,
    _build_labeled_trades,
    _resolve_family_hyperparameters,
)

PROFILE_KEY = "warbird_pro_v9_joint_challenger"
TRIGGER_FAMILY = _strategy_base.TRIGGER_FAMILY
PINE_FILE = _strategy_base.PINE_FILE
DATA_FLOOR = _strategy_base.DATA_FLOOR
MIN_TRADES = 200
OBJECTIVE_METRIC = "joint_challenger_lift"

# Card 4 search space = strategy exit params (from base) + AG hyperparams.
BOOL_PARAMS: list[str] = list(_strategy_base.BOOL_PARAMS)

NUMERIC_RANGES: dict[str, tuple[float, float]] = {
    **_strategy_base.NUMERIC_RANGES,
    "prob_threshold": (0.50, 0.75),
    "ag_time_limit": (180.0, 1200.0),
}

INT_PARAMS: set[str] = set(_strategy_base.INT_PARAMS) | {"ag_time_limit"}

CATEGORICAL_PARAMS: dict[str, list[Any]] = {
    **_strategy_base.CATEGORICAL_PARAMS,
    "ag_family": ["GBM", "CAT", "XGB"],
}

INPUT_DEFAULTS: dict[str, Any] = {
    **_strategy_base.INPUT_DEFAULTS,
    "ag_family": "GBM",
    "prob_threshold": 0.55,
    "ag_time_limit": 600,
}

FROZEN_PINE_PARAMS = frozenset(_strategy_base.FROZEN_PINE_PARAMS)


def assert_v9_contract() -> None:
    _strategy_base.assert_v9_contract()


def load_data() -> pd.DataFrame:
    return _strategy_base.load_data()


def objective_score(result: dict[str, Any]) -> float:
    return float(result.get(OBJECTIVE_METRIC, 0.0) or 0.0)


def run_backtest(df: pd.DataFrame, params: dict[str, Any], start_date: str) -> dict[str, Any]:
    assert_v9_contract()

    start_ts = pd.Timestamp(start_date)
    start_ts = start_ts.tz_localize("UTC") if start_ts.tzinfo is None else start_ts.tz_convert("UTC")
    is_df = df.loc[pd.to_datetime(df["ts"], utc=True) >= start_ts].copy()

    max_hold = int(params.get("maxHoldBars", _strategy_base.INPUT_DEFAULTS["maxHoldBars"]))
    trades = _build_labeled_trades(is_df, max_hold_bars=max_hold)

    if len(trades) < MIN_TRADES:
        return {
            "trades": int(len(trades)),
            "win_rate": float(trades[LABEL_COL].mean()) if len(trades) else 0.0,
            "pf": 0.0,
            "gross_profit": 0.0,
            "gross_loss": 0.0,
            "max_dd_abs": 0.0,
            OBJECTIVE_METRIC: 0.0,
            "fit_status": "too_few_trades",
            "model_path": "",
            "prob_threshold": float(params.get("prob_threshold", INPUT_DEFAULTS["prob_threshold"])),
            "leakage_flags": json.dumps({}),
            "label_horizon_bars": max_hold,
            "challenger_only": True,
        }

    family = str(params.get("ag_family", "GBM"))
    ag_hyperparams = _resolve_family_hyperparameters(family)
    time_limit = int(params.get("ag_time_limit", INPUT_DEFAULTS["ag_time_limit"]))
    prob_threshold = float(params.get("prob_threshold", INPUT_DEFAULTS["prob_threshold"]))

    output_dir = (
        workspace_dir(PROFILE_KEY) / "trial_models" / f"{family}_{time_limit}s_p{int(prob_threshold * 100)}"
    )
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

    return {
        "trades": int(ag_result.get("n_test", 0)),
        "win_rate": float(ag_result.get("gated_winrate", 0.0) or 0.0),
        "pf": 0.0,
        "gross_profit": 0.0,
        "gross_loss": 0.0,
        "max_dd_abs": 0.0,
        OBJECTIVE_METRIC: lift,
        "fit_status": str(ag_result.get("fit_status", "unknown")),
        "model_path": str(ag_result.get("model_path", str(output_dir))),
        "prob_threshold": prob_threshold,
        "leakage_flags": json.dumps(leakage_flags),
        "ag_family": family,
        "ag_time_limit": time_limit,
        "ag_test_auc": float(ag_result.get("test_auc", 0.0) or 0.0),
        "ag_test_brier": float(ag_result.get("test_brier", 0.0) or 0.0),
        "ag_lift": lift,
        "label_horizon_bars": max_hold,
        "challenger_only": True,
    }
