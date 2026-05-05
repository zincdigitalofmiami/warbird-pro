#!/usr/bin/env python3
"""Build a parity-check artifact for Pine V9 ↔ Python replay verification.

Samples 50 random `ml_entry_long_trigger=1` bars + 50 random
`ml_entry_short_trigger=1` bars from the latest strict V9 replay CSV. For each
sampled bar, dumps a row containing:

  ts, open, high, low, close, volume,
  ml_dir, ml_fib_range, ml_atr14, ml_rsi_value, ml_ma_bias,
  ml_pivot_dist_atr, ml_p618_dist_atr,
  ml_in_zone, ml_break_in_dir, ml_bars_since_break,
  ml_swept_bsl, ml_swept_ssl, ml_reclaimed_bsl, ml_reclaimed_ssl,
  ml_bar_delta, ml_net_delta_20,
  ml_xa_nq_code, ml_htf_conf_total,
  ml_pat_<all 14 patterns>,
  ml_entry_long_trigger, ml_entry_short_trigger,
  ml_trade_entry, ml_trade_stop, ml_trade_tp,

Output:
  scripts/optuna/workspaces/warbird_pro/parity_check_50long_50short.csv

Operator opens this CSV, picks 5-10 rows at random, opens TradingView's
Warbird Pro V9 indicator on the same MES 5m bar timestamp, and verifies
that Pine V9 ALSO fires an entry trigger on those bars with similar fib
state and gating booleans. Mismatches indicate replay parity bugs.
"""
from __future__ import annotations
import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_CSV = REPO_ROOT / "scripts/optuna/workspaces/warbird_pro/exports/databento_mes_5m_2020-2026_strict.csv"
OUT_CSV = REPO_ROOT / "scripts/optuna/workspaces/warbird_pro/parity_check_50long_50short.csv"

CORE_COLS = [
    "ts", "open", "high", "low", "close", "volume",
    "ml_dir", "ml_fib_range", "ml_atr14", "ml_rsi_value", "ml_ma_bias",
    "ml_pivot_dist_atr", "ml_p618_dist_atr",
    "ml_in_zone", "ml_break_in_dir", "ml_bars_since_break",
    "ml_swept_bsl", "ml_swept_ssl", "ml_reclaimed_bsl", "ml_reclaimed_ssl",
    "ml_bar_delta", "ml_net_delta_20",
    "ml_xa_nq_code", "ml_htf_conf_total",
    "ml_pat_hammer", "ml_pat_inv_hammer", "ml_pat_dragonfly",
    "ml_pat_bull_engulf", "ml_pat_piercing", "ml_pat_morning_star",
    "ml_pat_three_white",
    "ml_pat_shooting_star", "ml_pat_hanging_man", "ml_pat_gravestone",
    "ml_pat_bear_engulf", "ml_pat_dark_cloud", "ml_pat_evening_star",
    "ml_pat_three_black",
    "ml_entry_long_trigger", "ml_entry_short_trigger",
    "ml_trade_entry", "ml_trade_stop", "ml_trade_tp",
]


def main() -> int:
    print(f"loading {SRC_CSV}")
    df = pd.read_csv(SRC_CSV, parse_dates=["ts"])
    print(f"  rows={len(df):,}")

    longs = df[df["ml_entry_long_trigger"] > 0]
    shorts = df[df["ml_entry_short_trigger"] > 0]
    print(f"  total entry candidates: {len(longs):,} longs, {len(shorts):,} shorts")

    rng = np.random.default_rng(seed=20260504)
    n_long = min(50, len(longs))
    n_short = min(50, len(shorts))
    sample_l = longs.iloc[rng.choice(len(longs), size=n_long, replace=False)].copy()
    sample_s = shorts.iloc[rng.choice(len(shorts), size=n_short, replace=False)].copy()
    sample = pd.concat([sample_l, sample_s], ignore_index=True).sort_values("ts").reset_index(drop=True)

    available = [c for c in CORE_COLS if c in sample.columns]
    sample[available].to_csv(OUT_CSV, index=False)
    print(f"wrote {OUT_CSV} with {len(sample)} rows ({n_long} longs + {n_short} shorts)")
    print()
    print("Operator verification protocol:")
    print("  1. Open TradingView, attach Warbird Pro V9 to MES1! 5m chart.")
    print("  2. Pick 5-10 random rows from the CSV (mix of longs and shorts).")
    print("  3. For each picked row, jump the chart to that ts (use Go To Date).")
    print("  4. Confirm Pine V9 ALSO fires an entry trigger on that bar.")
    print("  5. Confirm fib anchor high/low ≈ replay's, dir matches, RSI matches.")
    print("  6. If <80% of sampled bars match, the replay has parity bugs and")
    print("     all downstream Optuna+AG results need to be redone.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
