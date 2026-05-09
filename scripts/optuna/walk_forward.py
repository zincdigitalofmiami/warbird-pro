#!/usr/bin/env python3
"""Expanding-window walk-forward validation for Warbird Pro V9.

Simulates real deployment: train on [0, T], predict on [T, T+step], advance.
Each window trains a fresh AG predictor and scores the unseen forward slice.
The embargo between train and test windows prevents label leakage.

Results per window: win_rate, profit_factor, expectancy, trade_count,
calibration (predicted vs realized), AUC, log_loss, Brier score.

Usage:
  python scripts/optuna/walk_forward.py \
      --csv exports/mes_5m.csv \
      --step-months 3 \
      --time-limit 3600 \
      [--min-train-months 24] \
      [--output-dir artifacts/walk_forward/<tag>]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")
os.environ.setdefault("MKL_NUM_THREADS", "1")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("LIGHTGBM_NUM_THREADS", "1")

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.optuna.cpcv import _enforce_embargo_floor

DEFAULT_OUTPUT_ROOT = REPO_ROOT / "artifacts" / "walk_forward"
LABEL_COL = "winner"


def _build_trade_dataset(
    df: pd.DataFrame,
    feature_cols: list[str],
    max_hold_bars: int,
) -> pd.DataFrame:
    df = df.sort_values("ts").reset_index(drop=True)
    long_mask = df["ml_entry_long_trigger"].astype(float) > 0
    short_mask = df["ml_entry_short_trigger"].astype(float) > 0
    entry_idx = np.where(long_mask | short_mask)[0]
    outcomes = df["ml_last_exit_outcome"].astype(float).to_numpy()
    rows: list[dict[str, Any]] = []
    for i in entry_idx:
        end = min(i + max_hold_bars + 1, len(df))
        future = outcomes[i + 1:end]
        nz = np.where(future != 0)[0]
        if nz.size == 0:
            continue
        offset = int(nz[0])
        rec = {col: df[col].iloc[i] for col in feature_cols if col in df.columns}
        rec["ts"] = df["ts"].iloc[i]
        rec[LABEL_COL] = 1 if int(future[offset]) == 1 else 0
        rows.append(rec)
    return pd.DataFrame(rows).sort_values("ts").reset_index(drop=True)


def _generate_windows(
    ts_series: pd.Series,
    min_train_months: int,
    step_months: int,
) -> list[tuple[pd.Timestamp, pd.Timestamp, pd.Timestamp]]:
    ts_min = ts_series.min()
    ts_max = ts_series.max()
    train_start = ts_min
    windows: list[tuple[pd.Timestamp, pd.Timestamp, pd.Timestamp]] = []
    split_ts = train_start + pd.DateOffset(months=min_train_months)
    while split_ts < ts_max:
        test_end = min(split_ts + pd.DateOffset(months=step_months), ts_max)
        if test_end <= split_ts:
            break
        windows.append((train_start, split_ts, test_end))
        split_ts = split_ts + pd.DateOffset(months=step_months)
    return windows


def _fit_and_score_window(
    trades: pd.DataFrame,
    feature_cols: list[str],
    train_end: pd.Timestamp,
    test_end: pd.Timestamp,
    embargo_bars: int,
    time_limit: int,
    output_dir: Path,
    window_id: int,
) -> dict[str, Any]:
    ts = pd.to_datetime(trades["ts"], utc=True)
    train_mask = ts < train_end
    test_mask = (ts >= train_end + pd.Timedelta(minutes=5 * embargo_bars)) & (ts < test_end)

    train_df = trades.loc[train_mask, feature_cols + [LABEL_COL]].copy()
    test_df = trades.loc[test_mask, feature_cols + [LABEL_COL]].copy()

    if len(train_df) < 200 or len(test_df) < 30:
        return {
            "window_id": window_id,
            "train_end": str(train_end.date()),
            "test_end": str(test_end.date()),
            "status": "skipped_thin",
            "n_train": len(train_df),
            "n_test": len(test_df),
        }

    if train_df[LABEL_COL].nunique() < 2 or test_df[LABEL_COL].nunique() < 2:
        return {
            "window_id": window_id,
            "train_end": str(train_end.date()),
            "test_end": str(test_end.date()),
            "status": "skipped_degenerate",
            "n_train": len(train_df),
            "n_test": len(test_df),
        }

    val_split = int(len(train_df) * 0.85)
    train_slice = train_df.iloc[:val_split]
    val_slice = train_df.iloc[val_split:]

    from autogluon.tabular import TabularPredictor

    wf_dir = output_dir / f"window_{window_id:03d}"
    pred = TabularPredictor(
        label=LABEL_COL,
        path=str(wf_dir),
        eval_metric="log_loss",
        problem_type="binary",
    ).fit(
        train_data=train_slice,
        tuning_data=val_slice,
        presets="best_quality",
        calibrate=True,
        time_limit=time_limit,
        num_bag_folds=8,
        num_stack_levels=1,
        dynamic_stacking=False,
        use_bag_holdout=True,
        hyperparameter_tune_kwargs={
            "searcher": "random",
            "scheduler": "local",
            "num_trials": 20,
        },
        verbosity=0,
        num_gpus=0,
    )
    pred.persist_models()

    y_true = test_df[LABEL_COL].to_numpy()
    proba = pred.predict_proba(test_df[feature_cols])
    if isinstance(proba, pd.DataFrame):
        proba_pos = proba.iloc[:, 1].to_numpy()
    else:
        proba_pos = np.asarray(proba)

    from sklearn.metrics import log_loss as sk_log_loss, roc_auc_score

    win_rate = float(y_true.mean())
    pred_wr = float(proba_pos.mean())
    n_test = len(test_df)
    try:
        auc = float(roc_auc_score(y_true, proba_pos))
    except Exception:
        auc = 0.0
    try:
        ll = float(sk_log_loss(y_true, proba_pos))
    except Exception:
        ll = float("inf")
    brier = float(np.mean((proba_pos - y_true) ** 2))

    threshold = 0.55
    gated = proba_pos >= threshold
    gated_wr = float(y_true[gated].mean()) if gated.sum() > 0 else 0.0
    n_gated = int(gated.sum())
    lift = gated_wr - win_rate

    lb = pred.leaderboard(test_df, extra_info=True, silent=True)
    lb.to_csv(wf_dir / "leaderboard.csv", index=False)

    return {
        "window_id": window_id,
        "train_end": str(train_end.date()),
        "test_end": str(test_end.date()),
        "status": "ok",
        "n_train": len(train_df),
        "n_test": n_test,
        "win_rate": win_rate,
        "predicted_wr": pred_wr,
        "auc": auc,
        "log_loss": ll,
        "brier": brier,
        "gated_wr": gated_wr,
        "n_gated": n_gated,
        "lift": lift,
        "threshold": threshold,
        "best_model": str(lb.iloc[0]["model"]) if len(lb) > 0 else None,
    }


def main() -> int:
    from scripts.ag.train_v9_locked import ML_FEATURES

    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", type=Path, required=True)
    ap.add_argument("--step-months", type=int, default=3)
    ap.add_argument("--min-train-months", type=int, default=24)
    ap.add_argument("--time-limit", type=int, default=3600)
    ap.add_argument("--max-hold-bars", type=int, default=72)
    ap.add_argument("--output-dir", type=Path, default=None)
    args = ap.parse_args()

    tag = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    output_dir = args.output_dir or (DEFAULT_OUTPUT_ROOT / f"wf_{tag}")
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"loading {args.csv}", flush=True)
    df = pd.read_csv(args.csv, parse_dates=["ts"])
    print(f"  rows={len(df):,}  range={df['ts'].iloc[0]} → {df['ts'].iloc[-1]}", flush=True)

    feature_cols = [c for c in ML_FEATURES if c in df.columns]
    trades = _build_trade_dataset(df, feature_cols, max_hold_bars=args.max_hold_bars)
    print(f"  trades={len(trades):,}  WR={trades[LABEL_COL].mean():.4f}", flush=True)

    trades["ts"] = pd.to_datetime(trades["ts"], utc=True)
    windows = _generate_windows(trades["ts"], args.min_train_months, args.step_months)
    print(f"  walk-forward windows: {len(windows)}", flush=True)

    embargo_bars = args.max_hold_bars + 1
    results: list[dict[str, Any]] = []
    for i, (train_start, split_ts, test_end) in enumerate(windows):
        print(f"\n=== window {i} : train → {split_ts.date()} | test → {test_end.date()} ===", flush=True)
        res = _fit_and_score_window(
            trades, feature_cols,
            train_end=split_ts, test_end=test_end,
            embargo_bars=embargo_bars,
            time_limit=args.time_limit,
            output_dir=output_dir,
            window_id=i,
        )
        results.append(res)
        print(f"  status={res['status']}  n_test={res.get('n_test',0)}"
              f"  WR={res.get('win_rate','?')}  lift={res.get('lift','?')}"
              f"  AUC={res.get('auc','?')}", flush=True)

    ok_results = [r for r in results if r["status"] == "ok"]
    summary = {
        "generated_at": tag,
        "csv": str(args.csv),
        "step_months": args.step_months,
        "min_train_months": args.min_train_months,
        "time_limit": args.time_limit,
        "max_hold_bars": args.max_hold_bars,
        "total_windows": len(windows),
        "ok_windows": len(ok_results),
        "per_window": results,
    }
    if ok_results:
        summary["mean_auc"] = float(np.mean([r["auc"] for r in ok_results]))
        summary["mean_lift"] = float(np.mean([r["lift"] for r in ok_results]))
        summary["mean_log_loss"] = float(np.mean([r["log_loss"] for r in ok_results]))
        summary["mean_brier"] = float(np.mean([r["brier"] for r in ok_results]))
        summary["mean_gated_wr"] = float(np.mean([r["gated_wr"] for r in ok_results]))
        summary["mean_win_rate"] = float(np.mean([r["win_rate"] for r in ok_results]))
        summary["std_lift"] = float(np.std([r["lift"] for r in ok_results], ddof=1)) if len(ok_results) > 1 else 0.0

    (output_dir / "walk_forward_summary.json").write_text(
        json.dumps(summary, indent=2, default=str)
    )
    print(f"\nwrote {output_dir / 'walk_forward_summary.json'}", flush=True)
    if ok_results:
        print(f"  mean AUC={summary['mean_auc']:.4f}  mean lift={summary['mean_lift']:.4f}"
              f"  mean log_loss={summary['mean_log_loss']:.4f}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
