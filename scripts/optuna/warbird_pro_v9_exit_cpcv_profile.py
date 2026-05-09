#!/usr/bin/env python3
"""DEPRECATED 2026-05-09 — Hybrid+ Card 1 (warbird_pro_v9_exit_cpcv).

The Hybrid+ 4-card chain (this card + entry_filter_cpcv + ag_meta_cpcv +
joint_challenger) was scrapped. Path went 4 cards -> 2 cards -> single Core
AutoGluon card. See docs/MASTER_PLAN.md "V9 Core AutoGluon" section and the
`warbird_pro_core` entry in scripts/optuna/indicator_registry.json.

This file is retained for git history / promotion-logic reference only. It is
NOT runnable: importing it raises SystemExit.
"""
from __future__ import annotations

import sys

raise SystemExit(
    "warbird_pro_v9_exit_cpcv_profile is DEPRECATED (Hybrid+ Card 1). "
    "Use scripts/optuna/cards/core_training/2026_05_09_warbird_pro_autogluon_core.py instead."
)

# --- legacy code below (unreachable) -----------------------------------------
from typing import Any

import pandas as pd

from scripts.optuna import warbird_pro_v9_profile as _base
from scripts.optuna.cpcv_helpers import cpcv_score_strategy

PROFILE_KEY = "warbird_pro_v9_exit_cpcv"
TRIGGER_FAMILY = _base.TRIGGER_FAMILY
PINE_FILE = _base.PINE_FILE
DATA_FLOOR = _base.DATA_FLOOR
MIN_TRADES = _base.MIN_TRADES
OBJECTIVE_METRIC = _base.OBJECTIVE_METRIC

BOOL_PARAMS = list(_base.BOOL_PARAMS)
NUMERIC_RANGES = dict(_base.NUMERIC_RANGES)
INT_PARAMS = set(_base.INT_PARAMS)
CATEGORICAL_PARAMS = dict(_base.CATEGORICAL_PARAMS)
INPUT_DEFAULTS = dict(_base.INPUT_DEFAULTS)
FROZEN_PINE_PARAMS = frozenset(_base.FROZEN_PINE_PARAMS)

CPCV_N_SPLITS = 6
CPCV_N_TEST = 2


def assert_v9_contract() -> None:
    _base.assert_v9_contract()


def load_data() -> pd.DataFrame:
    return _base.load_data()


def objective_score(result: dict[str, Any]) -> float:
    return float(result.get(OBJECTIVE_METRIC, 0.0) or 0.0)


def run_backtest(df: pd.DataFrame, params: dict[str, Any], start_date: str) -> dict[str, Any]:
    """Score exit params under CPCV. start_date is honored once at IS-window
    bounds (runner.py clamps to --end before calling)."""
    assert_v9_contract()

    start_ts = pd.Timestamp(start_date)
    start_ts = start_ts.tz_localize("UTC") if start_ts.tzinfo is None else start_ts.tz_convert("UTC")
    is_df = df.loc[pd.to_datetime(df["ts"], utc=True) >= start_ts].copy()

    label_horizon = int(params.get("maxHoldBars", INPUT_DEFAULTS["maxHoldBars"]))

    aggregated = cpcv_score_strategy(
        df=is_df,
        params=params,
        base_run_backtest=_base.run_backtest,
        label_horizon_bars=label_horizon,
        n_splits=CPCV_N_SPLITS,
        n_test_groups=CPCV_N_TEST,
        objective_metric_key=OBJECTIVE_METRIC,
    )
    aggregated["card"] = PROFILE_KEY
    return aggregated
