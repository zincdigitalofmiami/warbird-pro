#!/usr/bin/env python3
"""Direct Optuna + AutoGluon optimizer for Precision Sniper on MES 15m.

Every Pine input is represented in the Optuna parameter contract through
`precision_sniper_profile` (including UI-only inputs). Trial objective:
1) Generate trades from the 15m MES backtest
2) Train AutoGluon on trade-level outcomes for the sampled settings
3) Maximize a win-rate-first blended score
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np
import optuna
import pandas as pd
from optuna.exceptions import TrialPruned
from optuna.samplers import TPESampler

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.precision_sniper.precision_sniper_profile import (
    BOOL_PARAMS,
    CATEGORICAL_PARAMS,
    INPUT_DEFAULTS,
    INT_PARAMS,
    NUMERIC_RANGES,
    load_data,
    run_backtest,
)


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _binary_f1(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    tp = float(np.sum((y_true == 1) & (y_pred == 1)))
    fp = float(np.sum((y_true == 0) & (y_pred == 1)))
    fn = float(np.sum((y_true == 1) & (y_pred == 0)))

    precision = tp / (tp + fp) if (tp + fp) > 0.0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0.0 else 0.0
    if (precision + recall) == 0.0:
        return 0.0
    return 2.0 * precision * recall / (precision + recall)


def suggest_all_params(trial: optuna.Trial) -> dict[str, Any]:
    params: dict[str, Any] = {}
    for name in BOOL_PARAMS:
        params[name] = trial.suggest_categorical(name, [False, True])
    for name, choices in CATEGORICAL_PARAMS.items():
        params[name] = trial.suggest_categorical(name, choices)
    for name, (lo, hi) in NUMERIC_RANGES.items():
        if name in INT_PARAMS:
            params[name] = trial.suggest_int(name, int(lo), int(hi))
        else:
            params[name] = trial.suggest_float(name, lo, hi)
    for k, v in INPUT_DEFAULTS.items():
        if k not in params:
            params[k] = v
    return params


def build_feature_frame(trades: pd.DataFrame, params: dict[str, Any]) -> pd.DataFrame:
    df = trades.copy()
    chicago_ts = pd.to_datetime(df["entry_ts"], utc=True).dt.tz_convert("America/Chicago")
    df["entry_hour"] = chicago_ts.dt.hour.astype(int)
    df["entry_dow"] = chicago_ts.dt.dayofweek.astype(int)

    for k, v in params.items():
        df[f"param__{k}"] = v

    feature_cols = [
        "direction",
        "entry_price",
        "bull_score",
        "bear_score",
        "rsi",
        "adx",
        "atr",
        "ema_gap",
        "trend_gap",
        "vwap_gap",
        "vol_above_avg",
        "htf_bias",
        "resolved_preset",
        "entry_hour",
        "entry_dow",
    ] + [f"param__{k}" for k in sorted(params.keys())]

    out = df[feature_cols + ["target_win"]].copy()
    out["target_win"] = out["target_win"].astype(int)
    return out


def make_objective(
    bars_df: pd.DataFrame,
    start_date: str,
    trials_model_dir: Path,
    ag_time_limit: int,
    ag_presets: str,
    ag_hyperparameters: dict[str, Any],
    min_trades: int,
    min_train_rows: int,
    min_val_rows: int,
    train_fraction: float,
    keep_trial_models: bool,
    w_f1: float,
    w_wr: float,
    w_pf: float,
    pf_cap: float,
):
    from autogluon.tabular import TabularPredictor

    def objective(trial: optuna.Trial) -> float:
        params = suggest_all_params(trial)
        metrics, trades = run_backtest(bars_df, params, start_date=start_date, return_trades=True)

        trial.set_user_attr("trades", metrics["trades"])
        trial.set_user_attr("win_rate", metrics["win_rate"])
        trial.set_user_attr("pf", metrics["pf"])
        trial.set_user_attr("max_dd", metrics["max_dd_abs"])
        trial.set_user_attr("resolved_preset", metrics["resolved_preset"])

        if metrics["trades"] < min_trades or trades.empty:
            raise TrialPruned(f"min_trades:{metrics['trades']}<{min_trades}")

        dataset = build_feature_frame(trades, params)
        if len(dataset) < (min_train_rows + min_val_rows):
            raise TrialPruned(f"insufficient_rows:{len(dataset)}")

        split_idx = int(len(dataset) * train_fraction)
        split_idx = max(split_idx, min_train_rows)
        split_idx = min(split_idx, len(dataset) - min_val_rows)
        if split_idx <= 0 or split_idx >= len(dataset):
            raise TrialPruned("split_invalid")

        train_df = dataset.iloc[:split_idx].reset_index(drop=True)
        val_df = dataset.iloc[split_idx:].reset_index(drop=True)

        if train_df["target_win"].nunique() < 2:
            raise TrialPruned("train_single_class")
        if val_df["target_win"].nunique() < 2:
            raise TrialPruned("val_single_class")

        trial_model_path = trials_model_dir / f"trial_{trial.number:05d}"
        if trial_model_path.exists():
            shutil.rmtree(trial_model_path, ignore_errors=True)

        predictor = TabularPredictor(
            label="target_win",
            problem_type="binary",
            eval_metric="f1",
            path=str(trial_model_path),
        )
        fit_kwargs: dict[str, Any] = {
            "train_data": train_df,
            "time_limit": ag_time_limit,
            "num_bag_folds": 0,
            "num_stack_levels": 0,
            "dynamic_stacking": False,
            "hyperparameters": ag_hyperparameters,
            "ag_args_fit": {"num_gpus": 0, "num_cpus": 1},
            "verbosity": 0,
        }
        if ag_presets:
            fit_kwargs["presets"] = ag_presets
        predictor.fit(**fit_kwargs)

        y_pred = predictor.predict(val_df.drop(columns=["target_win"]))
        y_true = val_df["target_win"].to_numpy(dtype=np.int64)
        y_hat = pd.Series(y_pred).astype(int).to_numpy(dtype=np.int64)
        f1 = _binary_f1(y_true, y_hat)

        wr = _safe_float(metrics["win_rate"], 0.0)
        pf = _safe_float(metrics["pf"], 0.0)
        pf_score = min(pf / pf_cap, 1.0)

        objective_score = (w_f1 * f1) + (w_wr * wr) + (w_pf * pf_score)

        trial.set_user_attr("ag_f1", f1)
        trial.set_user_attr("pf_score", pf_score)
        trial.set_user_attr("objective_score", objective_score)

        if not keep_trial_models:
            shutil.rmtree(trial_model_path, ignore_errors=True)

        return objective_score

    return objective


def export_top_trials(study: optuna.Study, out_path: Path, n: int) -> None:
    completed = [t for t in study.trials if t.state == optuna.trial.TrialState.COMPLETE]
    ranked = sorted(completed, key=lambda t: _safe_float(t.value, 0.0), reverse=True)[:n]

    rows: list[dict[str, Any]] = []
    for rank, t in enumerate(ranked, 1):
        rows.append(
            {
                "rank": rank,
                "trial_number": t.number,
                "objective_score": _safe_float(t.value, 0.0),
                "ag_f1": _safe_float(t.user_attrs.get("ag_f1"), 0.0),
                "win_rate": _safe_float(t.user_attrs.get("win_rate"), 0.0),
                "pf": _safe_float(t.user_attrs.get("pf"), 0.0),
                "trades": _safe_int(t.user_attrs.get("trades"), 0),
                "max_dd": _safe_float(t.user_attrs.get("max_dd"), 0.0),
                "resolved_preset": t.user_attrs.get("resolved_preset"),
                "params": t.params,
            }
        )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(rows, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(description="Precision Sniper Optuna + AutoGluon optimizer")
    parser.add_argument("--n-trials", type=int, default=10)
    parser.add_argument("--n-jobs", type=int, default=1)
    parser.add_argument("--start", default="2025-01-01")
    parser.add_argument("--study-name", default="precision_sniper_ag_wr")
    parser.add_argument("--study-dir", default="data/optuna/precision_sniper_autogluon")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--top-n", type=int, default=10)

    parser.add_argument("--ag-time-limit", type=int, default=25)
    parser.add_argument("--ag-presets", default="")
    parser.add_argument("--keep-trial-models", action="store_true")
    parser.add_argument("--show-progress", action="store_true")

    parser.add_argument("--min-trades", type=int, default=60)
    parser.add_argument("--min-train-rows", type=int, default=40)
    parser.add_argument("--min-val-rows", type=int, default=20)
    parser.add_argument("--train-fraction", type=float, default=0.7)

    parser.add_argument("--w-f1", type=float, default=0.25)
    parser.add_argument("--w-wr", type=float, default=0.65)
    parser.add_argument("--w-pf", type=float, default=0.10)
    parser.add_argument("--pf-cap", type=float, default=2.0)
    args = parser.parse_args()

    study_dir = Path(args.study_dir)
    study_dir.mkdir(parents=True, exist_ok=True)
    trials_model_dir = study_dir / "trial_models"
    trials_model_dir.mkdir(parents=True, exist_ok=True)

    db_path = study_dir / "study.db"
    storage = f"sqlite:///{db_path.resolve()}"

    if not args.resume:
        try:
            optuna.delete_study(study_name=args.study_name, storage=storage)
        except Exception:
            pass

    study = optuna.create_study(
        study_name=args.study_name,
        storage=storage,
        direction="maximize",
        sampler=TPESampler(seed=42, n_startup_trials=15, multivariate=True),
        load_if_exists=args.resume,
    )
    study.set_user_attr("contract", "MES_15m")
    study.set_user_attr("surface", "precision_sniper")
    study.set_user_attr("objective", "win_rate_first_with_autogluon")
    study.set_user_attr("start_date", args.start)
    study.set_user_attr("ag_presets", args.ag_presets)
    study.set_user_attr("ag_time_limit", args.ag_time_limit)

    print("=== Precision Sniper | Optuna + AutoGluon ===")
    print(f"study:     {args.study_name}")
    print(f"storage:   {db_path}")
    print(f"trials:    {args.n_trials} (n_jobs={args.n_jobs})")
    print(f"start:     {args.start}")
    print(f"AG preset: {args.ag_presets} (time_limit={args.ag_time_limit}s/trial)")
    print("target:    maximize win-rate-first blended score")

    bars_df = load_data()
    print(f"bars:      {len(bars_df):,} rows  {bars_df['ts'].min()} -> {bars_df['ts'].max()}")

    objective = make_objective(
        bars_df=bars_df,
        start_date=args.start,
        trials_model_dir=trials_model_dir,
        ag_time_limit=args.ag_time_limit,
        ag_presets=args.ag_presets,
        ag_hyperparameters={"LR": {}},
        min_trades=args.min_trades,
        min_train_rows=args.min_train_rows,
        min_val_rows=args.min_val_rows,
        train_fraction=args.train_fraction,
        keep_trial_models=args.keep_trial_models,
        w_f1=args.w_f1,
        w_wr=args.w_wr,
        w_pf=args.w_pf,
        pf_cap=args.pf_cap,
    )

    t0 = time.perf_counter()
    study.optimize(
        objective,
        n_trials=args.n_trials,
        n_jobs=args.n_jobs,
        show_progress_bar=args.show_progress,
    )
    elapsed = time.perf_counter() - t0

    completed = [t for t in study.trials if t.state == optuna.trial.TrialState.COMPLETE]
    print(f"\ncompleted: {len(completed)} trials in {elapsed:.1f}s")
    if completed:
        best = max(completed, key=lambda t: _safe_float(t.value, 0.0))
        print(
            f"best: trial #{best.number} | score={_safe_float(best.value):.6f} | "
            f"WR={_safe_float(best.user_attrs.get('win_rate')):.2%} | "
            f"PF={_safe_float(best.user_attrs.get('pf')):.4f} | "
            f"AG_F1={_safe_float(best.user_attrs.get('ag_f1')):.4f} | "
            f"trades={_safe_int(best.user_attrs.get('trades'))}"
        )

    top_path = study_dir / f"top{args.top_n}.json"
    export_top_trials(study, top_path, args.top_n)
    print(f"top configs: {top_path}")


if __name__ == "__main__":
    main()
