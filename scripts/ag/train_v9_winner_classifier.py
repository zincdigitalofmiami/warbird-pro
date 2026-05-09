#!/usr/bin/env python3
"""DEPRECATED 2026-05-09 — V9 winner classifier (Hybrid+ chain).

This standalone AG winner classifier was a precursor to the Hybrid+ Card 3
AG meta-labeler. Both are retired in favor of the single Core AutoGluon card
(scripts/optuna/cards/core_training/2026_05_09_warbird_pro_autogluon_core.py),
which uses the canonical Core training script scripts/ag/train_v9_locked.py.

Retained for git history only. Not runnable.
"""
from __future__ import annotations

import sys

raise SystemExit(
    "train_v9_winner_classifier is DEPRECATED (Hybrid+ chain). "
    "Use scripts/ag/train_v9_locked.py with the Core card config instead."
)

# --- legacy code below (unreachable) -----------------------------------------
import argparse
import json
import os
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

# V9 canonical feature surface — kept in sync with scripts/ag/train_v9_locked.py
# Phantom features (ml_in_zone, ml_reject_at_zone, ml_bar_delta, ml_net_delta_20,
# ml_exhaust_*, ml_entry_route_code, 14-pattern set) were dropped during the V9
# rebuild; this list now mirrors the active V9 Pine output.
ML_FEATURE_COLS = [
    # structural / regime
    "ml_atr14", "ml_dir", "ml_fib_range",
    "ml_pivot_dist_atr", "ml_p618_dist_atr",
    "ml_bars_since_break", "ml_break_in_dir",
    # momentum
    "ml_rsi_value", "ml_rsi_stance_code", "ml_ma_bias",
    "ml_ma_slow_dist_atr", "ml_ma_fast_dist_atr",
    # ADX
    "ml_adx_value", "ml_adx_plus_di", "ml_adx_minus_di",
    # candlestick patterns (curated 4)
    "ml_pat_rising_window",
    "ml_pat_bear_engulf", "ml_pat_marubozu_black", "ml_pat_tweezer_top",
    # liquidity primitives (BSL/SSL sweep+reclaim)
    "ml_bsl_dist_atr", "ml_ssl_dist_atr",
    "ml_swept_bsl", "ml_swept_ssl",
    "ml_reclaimed_bsl", "ml_reclaimed_ssl",
    # liquidity expansions
    "ml_liq_eqh_dist_atr", "ml_liq_eql_dist_atr",
    "ml_liq_vwap_dist_atr", "ml_liq_vol_zscore",
    # cross-asset 5m
    "ml_xa_nq_code", "ml_xa_zn_code", "ml_xa_dx_code",
    # cross-asset advanced (VIX, MES↔NQ correlation, DXY divergence)
    "ml_xa_vix_zscore", "ml_xa_corr_nq", "ml_xa_dxy_diverge",
    # HTF confluence
    "ml_htf_conf_total",
    # daily/weekly S/R distances
    "ml_lvl_pdh_dist_atr", "ml_lvl_pdl_dist_atr",
    "ml_lvl_pwh_dist_atr", "ml_lvl_pwl_dist_atr",
    # footprint (intrabar bid/ask delta, POC, VA position)
    "ml_fp_delta_pct", "ml_fp_poc_dist_atr", "ml_fp_va_position",
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
