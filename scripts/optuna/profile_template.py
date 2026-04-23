#!/usr/bin/env python3
"""
Optuna profile adapter template for Pine indicators / strategies.

Use with:
  python scripts/optuna/runner.py \
    --indicator-key <key> \
    --profile-module scripts.optuna.my_profile \
    --study-name <key>_wr_pf
"""

from __future__ import annotations

from typing import Any
import pandas as pd

# Required parameter-space attributes
BOOL_PARAMS: list[str] = []
NUMERIC_RANGES: dict[str, tuple[float, float]] = {}
INT_PARAMS: set[str] = set()
CATEGORICAL_PARAMS: dict[str, list[Any]] = {}
INPUT_DEFAULTS: dict[str, Any] = {}


def load_data() -> pd.DataFrame:
    """Return your strategy input DataFrame."""
    raise NotImplementedError("Implement load_data() for your strategy profile.")


def run_backtest(df: pd.DataFrame, params: dict[str, Any], start_date: str) -> dict[str, Any]:
    """Return metrics dict with at least:
    trades, win_rate, pf, gross_profit, gross_loss, max_dd_abs
    """
    raise NotImplementedError("Implement run_backtest() for your strategy profile.")
