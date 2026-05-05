#!/usr/bin/env python3
"""Warbird Pro V9 winner classifier — AutoGluon full-zoo training.

Trains a binary classifier (winner vs non-winner) on the V9 ml_* feature surface
emitted by `indicators/warbird-pro-v9.pine` and replayed via
`scripts/optuna/v9_replay.py`. Output is a TabularPredictor + per-feature
importance ranking suitable for SHAP analysis.

Input:
  scripts/optuna/workspaces/warbird_pro/exports/databento_mes_5m_*.csv
  (the strict-gated V9 replay output)

Label construction:
  Trades = bars where ml_entry_long_trigger=1 OR ml_entry_short_trigger=1
  Looking forward, find ml_last_exit_outcome in {1, -1, 2}
  winner = (outcome == 1)  # target hit
  losers/timeouts = (outcome in {-1, 2})

Time-series correctness:
  --num-bag-folds 0  (mandatory per training-full-zoo skill)
  Train/test split is chronological, not random.
  Embargo between IS and OOS = max_hold_bars + 1 bars (label-horizon-aware,
  enforced by scripts/optuna/cpcv.py). The previous 0-bar gap leaked the
  in-flight 6-hour resolution window across the OOS boundary (Bug 1).
  IS = 2020-01-01 .. 2024-12-31, OOS = 2025-01-01 onward (Trump regime).

Usage:
  python scripts/ag/train_v9_winner_classifier.py [--time-limit 14400]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

# Apple Silicon OpenMP guards — must be set BEFORE LightGBM/AG import.
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.optuna.cpcv import _enforce_embargo_floor  # noqa: PLC2701  (intentional internal use)

CSV_PATH = REPO_ROOT / "scripts/optuna/workspaces/warbird_pro/exports/databento_mes_5m_2020-2026_strict.csv"
OUTPUT_ROOT = REPO_ROOT / "models/warbird_pro_v9"

ML_FEATURE_COLS = [
    "ml_atr14", "ml_dir", "ml_fib_range",
    "ml_pivot_dist_atr", "ml_p618_dist_atr",
    "ml_in_zone", "ml_bars_since_break", "ml_break_in_dir", "ml_reject_at_zone",
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
    "ml_xa_nq_code", "ml_xa_zn_code", "ml_xa_dx_code",
    "ml_exhaust_long", "ml_exhaust_short",
    "ml_entry_route_code", "ml_htf_conf_total",
]

LABEL_COL = "winner"


def load_v9_export(csv_path: Path) -> pd.DataFrame:
    print(f"loading {csv_path}", flush=True)
    df = pd.read_csv(csv_path, parse_dates=["ts"])
    print(f"  rows={len(df):,}", flush=True)
    return df


def build_trade_dataset(df: pd.DataFrame, max_hold_bars: int = 72) -> pd.DataFrame:
    """For each entry-trigger bar, look forward up to max_hold_bars to find the
    next non-zero ml_last_exit_outcome. Label winner=1 if outcome==1 (target),
    else 0 (stop or time exit). Return a DataFrame keyed by entry-bar index
    with all ml_* features at entry time + the resolved label."""
    df = df.sort_values("ts").reset_index(drop=True)
    long_mask = df["ml_entry_long_trigger"].astype(float) > 0
    short_mask = df["ml_entry_short_trigger"].astype(float) > 0
    entry_mask = long_mask | short_mask
    entry_idx = np.where(entry_mask)[0]
    print(f"  entry candidates: {len(entry_idx):,}", flush=True)

    outcomes = df["ml_last_exit_outcome"].astype(float).to_numpy()

    rows: list[dict[str, Any]] = []
    for i in entry_idx:
        end = min(i + max_hold_bars + 1, len(df))
        future = outcomes[i + 1 : end]
        nz = np.where(future != 0)[0]
        if len(nz) == 0:
            continue
        offset = int(nz[0])
        outcome_code = int(future[offset])
        winner = 1 if outcome_code == 1 else 0
        rec = {col: df[col].iloc[i] for col in ML_FEATURE_COLS}
        rec["ts"] = df["ts"].iloc[i]
        rec["direction"] = 1 if long_mask.iloc[i] else -1
        rec["outcome_code"] = outcome_code
        rec["bars_to_resolution"] = offset + 1
        rec[LABEL_COL] = winner
        rows.append(rec)

    out = pd.DataFrame(rows).sort_values("ts").reset_index(drop=True)
    print(f"  resolved trades: {len(out):,}  winners={int(out[LABEL_COL].sum())}  losers={int(((1 - out[LABEL_COL])).sum())}", flush=True)
    print(f"  WR: {out[LABEL_COL].mean():.3f}", flush=True)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", type=Path, default=CSV_PATH)
    ap.add_argument("--output-root", type=Path, default=OUTPUT_ROOT)
    ap.add_argument("--time-limit", type=int, default=3600, help="AG train time-limit seconds")
    ap.add_argument("--oos-start", type=str, default="2025-01-01")
    ap.add_argument("--max-hold-bars", type=int, default=72)
    args = ap.parse_args()

    df = load_v9_export(args.csv)
    trades = build_trade_dataset(df, max_hold_bars=args.max_hold_bars)
    if len(trades) < 200:
        raise RuntimeError(f"Too few resolved trades: {len(trades)}")

    oos_ts = pd.Timestamp(args.oos_start, tz="UTC")
    embargo_bars = args.max_hold_bars + 1
    _enforce_embargo_floor(embargo_bars, args.max_hold_bars)
    # Embargo gap on the IS side: drop trades whose label horizon could leak
    # into the OOS window. At 5m bars, embargo_bars * 5min covers the
    # max-hold resolution window, so no IS row can resolve into 2025+.
    embargo_td = pd.Timedelta(minutes=5 * embargo_bars)
    is_cutoff = oos_ts - embargo_td
    is_df = trades[trades["ts"] < is_cutoff].copy()
    oos_df = trades[trades["ts"] >= oos_ts].copy()
    if oos_df["ts"].min() < oos_ts:
        raise RuntimeError(f"OOS lock violated: {oos_df['ts'].min()} < {oos_ts}")
    print(
        f"  IS={len(is_df):,} OOS={len(oos_df):,} "
        f"(split at {args.oos_start}, embargo={embargo_bars} bars / {embargo_td})",
        flush=True,
    )

    feature_cols = ML_FEATURE_COLS + ["direction"]
    train_df = is_df[feature_cols + [LABEL_COL]].copy()
    test_df = oos_df[feature_cols + [LABEL_COL]].copy()

    from autogluon.tabular import TabularPredictor

    ts_tag = pd.Timestamp.now().strftime("%Y%m%d_%H%M%S")
    out_dir = args.output_root / f"winner_clf_{ts_tag}"
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"\ntraining AG full-zoo on {len(train_df):,} IS rows ({(train_df[LABEL_COL]==1).mean():.3f} positive class)", flush=True)
    print(f"  output dir: {out_dir}", flush=True)
    print(f"  time-limit: {args.time_limit}s", flush=True)

    pred = TabularPredictor(
        label=LABEL_COL,
        path=str(out_dir),
        eval_metric="roc_auc",
        problem_type="binary",
    ).fit(
        train_data=train_df,
        time_limit=args.time_limit,
        num_bag_folds=0,
        num_stack_levels=0,
        hyperparameters={
            # Full 7-family canonical zoo with explicit single-thread pins to
            # cooperate with KMP_DUPLICATE_LIB_OK=TRUE / OMP_NUM_THREADS=1 on
            # Apple Silicon. NN_TORCH + FASTAI restored after RAM headroom check.
            "GBM":      [{"num_threads": 1}, {"num_threads": 1, "extra_trees": True}],
            "CAT":      [{"thread_count": 1}],
            "XGB":      [{"n_jobs": 1, "tree_method": "hist"}],
            "RF":       [{"criterion": "gini", "n_jobs": 1}, {"criterion": "entropy", "n_jobs": 1}],
            "XT":       [{"criterion": "gini", "n_jobs": 1}, {"criterion": "entropy", "n_jobs": 1}],
            "NN_TORCH": [{}],
            "FASTAI":   [{}],
        },
        verbosity=2,
    )

    print("\n=== leaderboard ===", flush=True)
    lb = pred.leaderboard(test_df, silent=True)
    print(lb.to_string(), flush=True)

    print("\n=== feature importance (test set) ===", flush=True)
    fi = pred.feature_importance(test_df, num_shuffle_sets=3)
    print(fi.to_string(), flush=True)

    summary = {
        "trained_at": ts_tag,
        "csv_path": str(args.csv),
        "is_rows": int(len(train_df)),
        "oos_rows": int(len(test_df)),
        "is_winrate": float(train_df[LABEL_COL].mean()),
        "oos_winrate": float(test_df[LABEL_COL].mean()),
        "time_limit_sec": args.time_limit,
        "leaderboard_top_model": str(lb.iloc[0]["model"]),
        "leaderboard_top_score": float(lb.iloc[0]["score_test"]),
        "feature_importance_top10": fi.head(10).to_dict(orient="index"),
    }
    summary_path = out_dir / "v9_winner_clf_summary.json"
    summary_path.write_text(json.dumps(summary, default=str, indent=2))
    print(f"\nwrote {summary_path}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
