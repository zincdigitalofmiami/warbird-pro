#!/usr/bin/env python3
"""Warbird Pro V9 — LOCKED AG full-zoo training run.

Per-skill discipline (training-ag-best-practices, training-full-zoo,
training-ag-feature-finder):
  - 7-family canonical zoo with single-thread pins
  - presets="best_quality" — full zoo (no bagging/stacking)
  - calibrate=True — built-in isotonic calibration so predict_proba
    outputs true probabilities for the downstream EV decision rule
  - eval_metric=log_loss — proper probability scoring (roc_auc only
    ranks; log_loss penalizes miscalibrated confidence)
  - hyperparameter_tune_kwargs — per-family HPO within time budge
  - num_bag_folds=0, num_stack_levels=0 — time-series safe
    (no internal IID bagging/stacking)
  - dynamic_stacking=False (explicit, reproducible)
  - time_limit=7200s (2 hours so NN_TORCH/FASTAI fully converge)
  - chronological train/val/test split with embargo = max_hold_bars + 1 bars
    (label-horizon-aware; enforced by scripts/optuna/cpcv.py)
  - predictor.persist_models() after fit for fast repeated predic
  - leaderboard(extra_info=True) for hyperparameter visibility
  - Apple Silicon OpenMP guards set BEFORE any AG/lightgbm impor
  - Drop AG-flagged useless features (ml_in_zone constant=1, stale dx_code,
    ml_entry_route_code constant)

Note: this standalone trainer fits a single predictor on an embargoed
chronological split for fast iteration. The Core AutoGluon card
(scripts/optuna/cards/core_training/2026_05_09_warbird_pro_autogluon_core.py)
is the production training surface and goes through scripts/ag/train_hard_gate.py.
The earlier Hybrid+ Card 3 (warbird_pro_v9_ag_meta_cpcv) that wrapped this
trainer in CPCV was deprecated 2026-05-09.
"""
from __future__ import annotations

import os

# Apple Silicon OpenMP guards — MUST be set BEFORE any AG/lightgbm impor
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

# Features matching the locked Warbird Pro V9 Core surface.
# Missing columns are fatal. The Core trainer must not silently fall back to an
# older replay/export schema because that masks stale feature contracts.
ML_FEATURES = [
    # structural / regime
    "ml_atr14", "ml_dir", "ml_fib_range",
    "ml_pivot_dist_atr", "ml_p618_dist_atr",
    "ml_bars_since_break", "ml_break_in_dir",
    # momentum
    "ml_rsi_value", "ml_rsi_stance_code", "ml_ma_bias",
    "ml_ma_slow_dist_atr", "ml_ma_fast_dist_atr",
    # ADX
    "ml_adx_value", "ml_adx_plus_di", "ml_adx_minus_di",
    # candlestick patterns (curated 4 from real backtest performance)
    "ml_pat_rising_window",
    "ml_pat_bear_engulf", "ml_pat_marubozu_black", "ml_pat_tweezer_top",
    # liquidity primitives (BSL/SSL sweep+reclaim)
    "ml_bsl_dist_atr", "ml_ssl_dist_atr",
    "ml_swept_bsl", "ml_swept_ssl",
    "ml_reclaimed_bsl", "ml_reclaimed_ssl",
    # liquidity expansions (equal H/L pools, VWAP, volume z-score)
    "ml_liq_eqh_dist_atr", "ml_liq_eql_dist_atr",
    "ml_liq_vwap_dist_atr", "ml_liq_vol_zscore",
    # ETL CVD divergence features (Python-only, no Pine budget impact)
    "ml_cvd_div_bull", "ml_cvd_div_bear",
    # cross-asset 5m
    "ml_xa_nq_code", "ml_xa_zn_code", "ml_xa_dxy_code",
    # cross-asset advanced (VIX movement pressure, MES↔NQ correlation, DXY divergence)
    "ml_xa_vix_pressure", "ml_xa_corr_nq", "ml_xa_dxy_diverge",
    # HTF confluence
    "ml_htf_conf_total",
    # daily/weekly S/R distances
    "ml_lvl_pdh_dist_atr", "ml_lvl_pdl_dist_atr",
    "ml_lvl_pwh_dist_atr", "ml_lvl_pwl_dist_atr",
    # footprint / order flow (real intrabar bid/ask delta, POC, VA position)
    "ml_fp_delta_pct", "ml_fp_poc_dist_atr", "ml_fp_va_position",
    "ml_delta_imbalance_pct", "ml_delta_acceleration",
    "ml_aggressor_pulse", "ml_absorption_candidate",
    "ml_flush_candidate", "ml_volume_spike_ratio", "ml_poc_shift",
]
LABEL_COL = "winner_10pt_24bar"

REQUIRED_INPUT_COLUMNS = [
    "ts",
    "high",
    "low",
    "close",
    "ml_entry_long_trigger",
    "ml_entry_short_trigger",
    *ML_FEATURES,
]


def validate_input_schema(df: pd.DataFrame) -> None:
    missing = [col for col in REQUIRED_INPUT_COLUMNS if col not in df.columns]
    if missing:
        raise RuntimeError(
            "Core training CSV is missing required columns: "
            + ", ".join(missing)
        )
    stale = [col for col in ("ml_xa_dx_code", "ml_bar_delta", "ml_net_delta_20") if col in df.columns]
    if stale:
        raise RuntimeError(
            "Core training CSV still contains stale/banned columns: "
            + ", ".join(stale)
        )


def validate_trade_features(trades: pd.DataFrame) -> None:
    missing = [col for col in ML_FEATURES if col not in trades.columns]
    if missing:
        raise RuntimeError(f"Trade feature set missing required columns: {missing}")
    bad_inf = [
        col for col in ML_FEATURES
        if np.isinf(pd.to_numeric(trades[col], errors="coerce")).any()
    ]
    if bad_inf:
        raise RuntimeError(f"Trade feature set contains +/-inf values: {bad_inf}")
    all_null = [col for col in ML_FEATURES if trades[col].isna().all()]
    if all_null:
        raise RuntimeError(f"Trade feature columns are entirely null: {all_null}")



def build_trade_dataset(df: pd.DataFrame, max_hold_bars: int = 24) -> pd.DataFrame:
    """Build fixed 10/-5/24 triple-barrier labels at entry bars.

    A win is +10 MES points before -5 MES points within 24 5m bars. Rows where
    neither barrier is hit are dropped. If target and stop are both touched in
    the same future bar, the label is pessimistically a loss because 5m OHLC
    cannot prove target-before-stop ordering.
    """
    df = df.sort_values("ts").reset_index(drop=True)
    long_mask = df["ml_entry_long_trigger"].astype(float) > 0
    short_mask = df["ml_entry_short_trigger"].astype(float) > 0
    entry_mask = long_mask | short_mask
    entry_idx = np.where(entry_mask)[0]
    print(f"  entry candidates: {len(entry_idx):,}", flush=True)

    highs = df["high"].to_numpy()
    lows = df["low"].to_numpy()
    entries = (
        df["ml_trade_entry"].to_numpy()
        if "ml_trade_entry" in df.columns
        else np.full(len(df), np.nan)
    )
    closes = df["close"].to_numpy()

    rows = []
    dropped_neither = 0

    for i in entry_idx:
        entry_price = entries[i] if pd.notna(entries[i]) and entries[i] > 0 else closes[i]
        is_long = bool(long_mask.iloc[i])

        target_hit_idx = -1
        stop_hit_idx = -1

        tp_dist = 10.0
        sl_dist = 5.0
        tp_price = entry_price + tp_dist if is_long else entry_price - tp_dist
        sl_price = entry_price - sl_dist if is_long else entry_price + sl_dist
        resolution_bar = -1
        outcome = 0

        end_idx = min(i + max_hold_bars + 1, len(df))
        for j in range(i + 1, end_idx):
            h = highs[j]
            l = lows[j]

            if is_long and l <= sl_price:
                stop_hit_idx = j
            elif not is_long and h >= sl_price:
                stop_hit_idx = j

            if is_long and h >= tp_price:
                target_hit_idx = j
            elif not is_long and l <= tp_price:
                target_hit_idx = j

            if target_hit_idx != -1 and stop_hit_idx != -1:
                outcome = 0
                resolution_bar = j
                break
            elif target_hit_idx != -1:
                outcome = 1
                resolution_bar = j
                break
            elif stop_hit_idx != -1:
                outcome = 0
                resolution_bar = j
                break
        else:
            # Neither hit within max_hold_bars
            dropped_neither += 1
            continue

        rec = {col: df[col].iloc[i] for col in ML_FEATURES}
        rec["ts"] = df["ts"].iloc[i]
        rec["direction"] = 1 if is_long else -1
        rec["entry_price"] = float(entry_price)
        rec["target_price"] = float(tp_price)
        rec["stop_price"] = float(sl_price)
        rec[LABEL_COL] = outcome
        rec["_outcome_code"] = 1 if outcome == 1 else -1
        rec["_bars_to_resolution"] = resolution_bar - i
        rows.append(rec)

    if not rows:
        out_cols = [
            *ML_FEATURES,
            "ts",
            "direction",
            "entry_price",
            "target_price",
            "stop_price",
            LABEL_COL,
            "_outcome_code",
            "_bars_to_resolution",
        ]
        print(f"  resolved trades: 0")
        print(f"  dropped neither-hit: {dropped_neither:,}")
        return pd.DataFrame(columns=out_cols)

    out = pd.DataFrame(rows).sort_values("ts").reset_index(drop=True)
    print(f"  resolved trades: {len(out):,}")
    print(f"  dropped neither-hit: {dropped_neither:,}")
    if len(out) > 0:
        print(f"  {LABEL_COL} rate: {out[LABEL_COL].mean():.4f}  ({int(out[LABEL_COL].sum()):,} positives / {len(out):,} total)")
    validate_trade_features(out)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", type=Path, default=CSV_PATH)
    ap.add_argument("--output-root", type=Path, default=OUTPUT_ROOT)
    ap.add_argument("--time-limit", type=int, default=7200)
    ap.add_argument("--max-hold-bars", type=int, default=24)
    ap.add_argument("--train-frac", type=float, default=0.70)
    ap.add_argument("--val-frac", type=float, default=0.15)
    ap.add_argument("--validate-only", action="store_true",
                    help="Build labels/splits and run hard schema gates without fitting AutoGluon.")
    ap.add_argument("--smoke-ok", action="store_true",
                    help="With --validate-only, accept a small smoke CSV below full-training trade/split floors.")
    args = ap.parse_args()
    if args.smoke_ok and not args.validate_only:
        raise SystemExit("--smoke-ok is only valid with --validate-only")
    if not (0.0 < args.train_frac < 1.0):
        raise SystemExit("--train-frac must be in (0, 1)")
    if not (0.0 < args.val_frac < 1.0):
        raise SystemExit("--val-frac must be in (0, 1)")
    if args.train_frac + args.val_frac >= 1.0:
        raise SystemExit("--train-frac + --val-frac must leave a non-empty test segment")

    print(f"loading {args.csv}", flush=True)
    df = pd.read_csv(args.csv, parse_dates=["ts"])
    print(f"  rows={len(df):,}  range={df['ts'].iloc[0]} -> {df['ts'].iloc[-1]}", flush=True)
    validate_input_schema(df)

    trades = build_trade_dataset(df, max_hold_bars=args.max_hold_bars)
    feature_cols = list(ML_FEATURES)
    if args.validate_only and args.smoke_ok:
        if len(trades) == 0:
            raise RuntimeError("Smoke validation requires at least one resolved trade")
        if trades[LABEL_COL].nunique() != 2:
            raise RuntimeError(f"Smoke validation requires both {LABEL_COL} classes")
        print("\nsmoke validate-only PASS")
        print(f"  resolved trades: {len(trades):,}")
        print(f"  positives: {int(trades[LABEL_COL].sum()):,}")
        print(f"  negatives: {int((1 - trades[LABEL_COL]).sum()):,}")
        print(f"  features: {len(feature_cols)}")
        print(f"  label: {LABEL_COL}")
        print(f"  max_hold_bars: {args.max_hold_bars}")
        return 0

    if len(trades) < 200:
        raise RuntimeError(f"Too few resolved trades: {len(trades):,}")
    if trades[LABEL_COL].nunique() != 2:
        raise RuntimeError(f"{LABEL_COL} must contain both classes")

    # Label-horizon-aware embargo. The label looks forward up to
    # max_hold_bars; the embargo around each split boundary must be at leas
    # max_hold_bars + 1 to keep the resolution window from leaking across
    # train/val/test. Enforced by cpcv._enforce_embargo_floor().
    embargo_bars = args.max_hold_bars + 1

    train_end_idx = int(len(trades) * args.train_frac)
    val_end_idx = int(len(trades) * (args.train_frac + args.val_frac))

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
    if len(train_df) < 200 or len(val_df) < 50 or len(test_df) < 50:
        raise RuntimeError(f"Splits too thin: train={len(train_df)} val={len(val_df)} test={len(test_df)}")
    for name, slice_df in (("train", train_df), ("val", val_df), ("test", test_df)):
        if slice_df[LABEL_COL].nunique() != 2:
            raise RuntimeError(f"{name} split missing one label class")

    train = train_df[feature_cols + [LABEL_COL]].copy()
    val = val_df[feature_cols + [LABEL_COL]].copy()
    test = test_df[feature_cols + [LABEL_COL]].copy()

    if args.validate_only:
        print("\nvalidate-only PASS")
        print(f"  features: {len(feature_cols)}")
        print(f"  label: {LABEL_COL}")
        print(f"  max_hold_bars: {args.max_hold_bars}")
        return 0

    from autogluon.tabular import TabularPredictor

    ts_tag = pd.Timestamp.now().strftime("%Y%m%d_%H%M%S")
    out_dir = args.output_root / f"locked_{ts_tag}"
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"\nLOCKED AG full-zoo run", flush=True)
    print(f"  output dir:    {out_dir}", flush=True)
    print(f"  features:      {len(feature_cols)} ({', '.join(feature_cols[:6])}, ...)", flush=True)
    print(f"  time-limit:    {args.time_limit}s", flush=True)
    print(f"  preset:        best_quality (full zoo, no bagging/stacking)", flush=True)
    print(f"  calibrate:     True (isotonic calibration for EV rule)", flush=True)
    print(f"  num_bag_folds: 0 (time-series safe)", flush=True)
    print(f"  stack_levels:  0", flush=True)
    print(f"  dyn_stacking:  False (explicit, reproducible)", flush=True)
    print(f"  HPO:           random searcher, 20 trials per family", flush=True)
    print(f"  zoo:           7-family canonical (single-thread pins)", flush=True)
    print(f"  eval_metric:   log_loss (probability scoring for EV rule)", flush=True)
    print(f"  OMP_NUM_THREADS={os.environ.get('OMP_NUM_THREADS')} KMP_DUPLICATE_LIB_OK={os.environ.get('KMP_DUPLICATE_LIB_OK')}", flush=True)

    pred = TabularPredictor(
        label=LABEL_COL,
        path=str(out_dir),
        eval_metric="log_loss",
        problem_type="binary",
    ).fit(
        train_data=train,
        tuning_data=val,
        use_bag_holdout=False,
        time_limit=args.time_limit,
        presets="best_quality",
        calibrate=True,
        num_bag_folds=0,
        num_stack_levels=0,
        dynamic_stacking=False,
        ag_args_ensemble={"fold_fitting_strategy": "sequential_local"},
        hyperparameter_tune_kwargs={
            "searcher": "random",
            "scheduler": "local",
            "num_trials": 20,
        },
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
    pred.persist()

    print("\n=== leaderboard (OOS test set) ===", flush=True)
    lb = pred.leaderboard(test, extra_info=True, silent=True)
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
