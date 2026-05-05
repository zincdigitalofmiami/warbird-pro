#!/usr/bin/env python3
"""Warbird Pro V9 — LOCKED AG full-zoo training run.

Per-skill discipline (training-ag-best-practices, training-full-zoo):
  - 7-family canonical zoo with single-thread pins
  - num_bag_folds=0 (mandatory time-series)
  - num_stack_levels=0 (mandatory when bag_folds=0)
  - dynamic_stacking=False (explicit)
  - presets="good_quality" (NOT best_quality — best_quality enables dynamic_stacking)
  - time_limit=7200s (2 hours so NN_TORCH/FASTAI fully converge)
  - chronological train/val/test split with embargo = max_hold_bars + 1 bars
    (label-horizon-aware; enforced by scripts/optuna/cpcv.py)
  - eval_metric=roc_auc, problem_type=binary
  - Apple Silicon OpenMP guards set BEFORE any AG/lightgbm import
  - Drop AG-flagged useless features (ml_in_zone constant=1, ml_xa_zn/dx_code
    constant=0 because data not local, ml_entry_route_code constant)

Note: full Combinatorial Purged CV across IS is the responsibility of the
Hybrid+ Card 3 Optuna profile (warbird_pro_v9_ag_meta_cpcv_profile). This
standalone trainer fits a single predictor on an embargoed chronological
split for fast iteration; CPCV per trial would multiply this script's
runtime by ~15x without changing the deliverable (one predictor).
"""
from __future__ import annotations

import os

# Apple Silicon OpenMP guards — MUST be set BEFORE any AG/lightgbm import
os.environ["OMP_NUM_THREADS"] = "1"
os.environ["LIGHTGBM_NUM_THREADS"] = "1"
os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"
os.environ["MKL_NUM_THREADS"] = "1"
os.environ["OPENBLAS_NUM_THREADS"] = "1"

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.optuna.cpcv import embargoed_chronological_split

CSV_PATH = REPO_ROOT / "scripts/optuna/workspaces/warbird_pro/exports/databento_mes_5m_2020-2026_strict.csv"
OUTPUT_ROOT = REPO_ROOT / "models/warbird_pro_v9"

# Features used by AG. Excluded from this list:
#   ml_in_zone           — constant=1 at entry-trigger time (precondition not feature)
#   ml_xa_zn_code        — constant=0 (ZN data not in local cross_asset_1h)
#   ml_xa_dx_code        — constant=0 (DX data not in local cross_asset_1h)
#   ml_entry_route_code  — constant in single-config replay (no variation)
#   ml_reject_at_zone    — AG flagged useless on prior run; rare and mostly noise
#   direction (derived from ml_dir, would be redundant)
ML_FEATURES = [
    # structural / regime
    "ml_atr14", "ml_dir", "ml_fib_range",
    "ml_pivot_dist_atr", "ml_p618_dist_atr",
    "ml_bars_since_break", "ml_break_in_dir",
    # momentum
    "ml_rsi_value", "ml_rsi_stance_code", "ml_ma_bias",
    # candlestick patterns (top handful)
    "ml_pat_hammer", "ml_pat_inv_hammer", "ml_pat_dragonfly",
    "ml_pat_bull_engulf", "ml_pat_piercing", "ml_pat_morning_star",
    "ml_pat_three_white",
    "ml_pat_shooting_star", "ml_pat_hanging_man", "ml_pat_gravestone",
    "ml_pat_bear_engulf", "ml_pat_dark_cloud", "ml_pat_evening_star",
    "ml_pat_three_black",
    # liquidity
    "ml_bsl_dist_atr", "ml_ssl_dist_atr",
    "ml_swept_bsl", "ml_swept_ssl", "ml_reclaimed_bsl", "ml_reclaimed_ssl",
    # volume delta
    "ml_bar_delta", "ml_net_delta_20",
    # cross-asset (NQ only — ZN/DX not local)
    "ml_xa_nq_code",
    # exhaustion / HTF
    "ml_exhaust_long", "ml_exhaust_short", "ml_htf_conf_total",
]
LABEL_COL = "winner"

# Chronological split BOUNDARIES. Embargo gaps between train/val and val/test
# are applied at runtime in main() via embargoed_chronological_split() so the
# embargo size tracks --max-hold-bars. The 1-bar embargo present in earlier
# revisions (Bug 1) leaked labels across the 6-hour resolution window — fixed
# now by enforcing embargo >= max_hold_bars + 1 in scripts/optuna/cpcv.py.
TRAIN_END = pd.Timestamp("2024-06-30T23:55:00", tz="UTC")
VAL_END = pd.Timestamp("2024-12-31T23:55:00", tz="UTC")
TEST_START = pd.Timestamp("2025-01-01T00:00:00", tz="UTC")  # OOS lock — no HPO trial may see this


def build_trade_dataset(df: pd.DataFrame, max_hold_bars: int = 72) -> pd.DataFrame:
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
        future = outcomes[i + 1:end]
        nz = np.where(future != 0)[0]
        if len(nz) == 0:
            continue
        offset = int(nz[0])
        outcome_code = int(future[offset])
        winner = 1 if outcome_code == 1 else 0
        rec = {col: df[col].iloc[i] for col in ML_FEATURES if col in df.columns}
        rec["ts"] = df["ts"].iloc[i]
        rec[LABEL_COL] = winner
        rec["_outcome_code"] = outcome_code
        rec["_bars_to_resolution"] = offset + 1
        rows.append(rec)

    out = pd.DataFrame(rows).sort_values("ts").reset_index(drop=True)
    print(f"  resolved trades: {len(out):,}", flush=True)
    print(f"  winner rate: {out[LABEL_COL].mean():.4f}  ({int(out[LABEL_COL].sum()):,} winners / {len(out):,} total)", flush=True)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", type=Path, default=CSV_PATH)
    ap.add_argument("--output-root", type=Path, default=OUTPUT_ROOT)
    ap.add_argument("--time-limit", type=int, default=7200)
    ap.add_argument("--max-hold-bars", type=int, default=72)
    args = ap.parse_args()

    print(f"loading {args.csv}", flush=True)
    df = pd.read_csv(args.csv, parse_dates=["ts"])
    print(f"  rows={len(df):,}  range={df['ts'].iloc[0]} -> {df['ts'].iloc[-1]}", flush=True)

    trades = build_trade_dataset(df, max_hold_bars=args.max_hold_bars)

    # Label-horizon-aware embargo. The label looks forward up to
    # max_hold_bars; the embargo around each split boundary must be at least
    # max_hold_bars + 1 to keep the resolution window from leaking across
    # train/val/test. Enforced by cpcv._enforce_embargo_floor().
    embargo_bars = args.max_hold_bars + 1

    train_end_idx = int(np.searchsorted(trades["ts"].to_numpy(), np.datetime64(TRAIN_END.to_numpy()), side="right"))
    val_end_idx = int(np.searchsorted(trades["ts"].to_numpy(), np.datetime64(VAL_END.to_numpy()), side="right"))

    train_pos, val_pos, test_pos = embargoed_chronological_split(
        n_samples=len(trades),
        train_end_idx=train_end_idx,
        val_end_idx=val_end_idx,
        embargo_bars=embargo_bars,
        label_horizon_bars=args.max_hold_bars,
    )
    train_df = trades.iloc[train_pos].copy()
    val_df = trades.iloc[val_pos].copy()
    test_df = trades.iloc[test_pos].copy()

    print(f"\nsplit (embargo={embargo_bars} bars between segments):")
    print(f"  IS  (train):  {len(train_df):,}  WR={train_df[LABEL_COL].mean():.4f}  ({train_df['ts'].min()} → {train_df['ts'].max()})", flush=True)
    print(f"  VAL (tuning): {len(val_df):,}  WR={val_df[LABEL_COL].mean():.4f}  ({val_df['ts'].min()} → {val_df['ts'].max()})", flush=True)
    print(f"  OOS (test):   {len(test_df):,}  WR={test_df[LABEL_COL].mean():.4f}  ({test_df['ts'].min()} → {test_df['ts'].max()})", flush=True)
    if test_df["ts"].min() < TEST_START:
        raise RuntimeError(
            f"OOS lock violated: test segment starts {test_df['ts'].min()} < {TEST_START}"
        )

    if len(train_df) < 200 or len(val_df) < 50 or len(test_df) < 50:
        raise RuntimeError(f"Splits too thin: train={len(train_df)} val={len(val_df)} test={len(test_df)}")

    feature_cols = [c for c in ML_FEATURES if c in trades.columns]
    train = train_df[feature_cols + [LABEL_COL]].copy()
    val = val_df[feature_cols + [LABEL_COL]].copy()
    test = test_df[feature_cols + [LABEL_COL]].copy()

    from autogluon.tabular import TabularPredictor

    ts_tag = pd.Timestamp.now().strftime("%Y%m%d_%H%M%S")
    out_dir = args.output_root / f"locked_{ts_tag}"
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"\nLOCKED AG full-zoo run", flush=True)
    print(f"  output dir:    {out_dir}", flush=True)
    print(f"  features:      {len(feature_cols)} ({', '.join(feature_cols[:6])}, ...)", flush=True)
    print(f"  time-limit:    {args.time_limit}s", flush=True)
    print(f"  preset:        good_quality (NOT best_quality — explicit)", flush=True)
    print(f"  num_bag_folds: 0 (time-series MANDATORY)", flush=True)
    print(f"  stack_levels:  0 (when bag_folds=0)", flush=True)
    print(f"  dyn_stacking:  False (explicit, reproducible)", flush=True)
    print(f"  zoo:           7-family canonical (single-thread pins)", flush=True)
    print(f"  eval_metric:   roc_auc", flush=True)
    print(f"  OMP_NUM_THREADS={os.environ.get('OMP_NUM_THREADS')} KMP_DUPLICATE_LIB_OK={os.environ.get('KMP_DUPLICATE_LIB_OK')}", flush=True)

    pred = TabularPredictor(
        label=LABEL_COL,
        path=str(out_dir),
        eval_metric="roc_auc",
        problem_type="binary",
    ).fit(
        train_data=train,
        tuning_data=val,
        use_bag_holdout=True,
        time_limit=args.time_limit,
        presets="good_quality",
        num_bag_folds=0,
        num_stack_levels=0,
        dynamic_stacking=False,
        ag_args_ensemble={"fold_fitting_strategy": "sequential_local"},
        hyperparameters={
            "GBM": [{"num_threads": 1}, {"num_threads": 1, "extra_trees": True}],
            "CAT": {"thread_count": 1},
            "XGB": {"n_jobs": 1},
            "RF":  [{"criterion": "gini"}, {"criterion": "entropy"}],
            "XT":  [{"criterion": "gini"}, {"criterion": "entropy"}],
            "NN_TORCH": {},
            "FASTAI":   {},
        },
        verbosity=2,
        num_gpus=0,
    )

    print("\n=== leaderboard (OOS test set) ===", flush=True)
    lb = pred.leaderboard(test, silent=True)
    print(lb.to_string(), flush=True)
    lb.to_csv(out_dir / "leaderboard.csv", index=False)

    print("\n=== feature importance (test set, 5 shuffle sets) ===", flush=True)
    fi = pred.feature_importance(test, num_shuffle_sets=5)
    print(fi.to_string(), flush=True)
    fi.to_csv(out_dir / "feature_importance.csv")

    summary = {
        "trained_at": ts_tag,
        "csv_sha256_assumed_via_manifest": "see exports/*.manifest.json",
        "csv_path": str(args.csv),
        "is_rows": int(len(train)),
        "val_rows": int(len(val)),
        "oos_rows": int(len(test)),
        "is_winrate": float(train[LABEL_COL].mean()),
        "val_winrate": float(val[LABEL_COL].mean()),
        "oos_winrate": float(test[LABEL_COL].mean()),
        "feature_count": len(feature_cols),
        "time_limit_sec": args.time_limit,
        "leaderboard_top_model": str(lb.iloc[0]["model"]),
        "leaderboard_top_score_test": float(lb.iloc[0]["score_test"]),
        "leaderboard_top_score_val": float(lb.iloc[0]["score_val"]),
        "feature_importance_top10": fi.head(10).to_dict(orient="index"),
    }
    summary_path = out_dir / "v9_winner_clf_summary.json"
    summary_path.write_text(json.dumps(summary, default=str, indent=2))
    print(f"\nwrote {summary_path}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
