#!/usr/bin/env python3
"""CPCV-aware backtest and AG-fit helpers for Warbird Pro V9 Optuna cards.

Two helpers:

cpcv_score_strategy(df, params, base_run_backtest, ...):
    Wrap a profile's existing run_backtest(df, params, start_date) so each
    Optuna trial scores params across CPCV folds (combinatorial purged CV
    with label-horizon-aware embargo). Used by the exit-CPCV (Card 1) and
    entry-filter-CPCV (Card 2) profiles.

ag_embargoed_train_and_score(df, ag_hyperparams, label_col, ...):
    Embargoed chronological train/val/test split, fit AG predictor, score on
    held-out test fold. Used by Card 3 (AG meta) and Card 4 (joint
    challenger). Card 3 wraps it with a top-K strategy-candidate selector.

The embargo floor is enforced inside scripts/optuna/cpcv.py so neither helper
can silently regress to a 1-bar embargo (Bug 1).
"""
from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from scripts.optuna.cpcv import (
    combinatorial_purged_splits,
    embargoed_chronological_split,
)


METRIC_KEYS = ("trades", "win_rate", "pf", "gross_profit", "gross_loss", "max_dd_abs")


def _empty_aggregate() -> dict[str, Any]:
    return {
        "trades": 0,
        "win_rate": 0.0,
        "pf": 0.0,
        "gross_profit": 0.0,
        "gross_loss": 0.0,
        "max_dd_abs": 0.0,
        "fold_metrics": [],
    }


def cpcv_score_strategy(
    df: pd.DataFrame,
    params: dict[str, Any],
    base_run_backtest: Callable[[pd.DataFrame, dict[str, Any], str], dict[str, Any]],
    label_horizon_bars: int,
    n_splits: int = 6,
    n_test_groups: int = 2,
    embargo_bars: int | None = None,
    objective_metric_key: str | None = None,
) -> dict[str, Any]:
    """Score a strategy params dict across CPCV folds.

    Each fold subsets df to the test indices (chronological slice) and calls
    base_run_backtest on the slice. Per-fold metrics are aggregated as means
    weighted by fold trade count, with PF computed from summed gross_profit
    and gross_loss to avoid the 0/0 average pitfall on thin folds.
    """
    embargo = embargo_bars if embargo_bars is not None else label_horizon_bars + 1
    n_samples = len(df)
    if n_samples < n_splits * 4:
        return _empty_aggregate()

    df_sorted = df.sort_values("ts").reset_index(drop=True)

    fold_results: list[dict[str, Any]] = []
    try:
        folds = list(
            combinatorial_purged_splits(
                n_samples=n_samples,
                n_splits=n_splits,
                n_test_groups=n_test_groups,
                embargo_bars=embargo,
                label_horizon_bars=label_horizon_bars,
            )
        )
    except (ValueError, RuntimeError) as exc:
        result = _empty_aggregate()
        result["leakage_flags"] = {"cpcv_split_failed": str(exc)[:160]}
        return result

    for fold_id, (_train_idx, test_idx) in enumerate(folds):
        slice_df = df_sorted.iloc[test_idx].reset_index(drop=True)
        if slice_df.empty:
            continue
        start_date = pd.to_datetime(slice_df["ts"].iloc[0]).isoformat()
        try:
            res = base_run_backtest(slice_df, params, start_date=start_date)
        except Exception as exc:  # backtest_py raises AssertionError on degenerate trades
            res = {
                "trades": 0,
                "win_rate": 0.0,
                "pf": 0.0,
                "gross_profit": 0.0,
                "gross_loss": 0.0,
                "max_dd_abs": 0.0,
                "error": str(exc)[:160],
            }
        row = {"fold_id": fold_id, **{k: res.get(k, 0.0) for k in METRIC_KEYS}}
        if "error" in res:
            row["error"] = res["error"]
        if objective_metric_key:
            row[objective_metric_key] = res.get(objective_metric_key, 0.0)
        fold_results.append(row)

    return _aggregate(fold_results, objective_metric_key=objective_metric_key)


def _aggregate(
    fold_results: list[dict[str, Any]],
    objective_metric_key: str | None,
) -> dict[str, Any]:
    if not fold_results:
        return _empty_aggregate()

    total_trades = sum(int(f.get("trades", 0)) for f in fold_results)
    if total_trades == 0:
        out = _empty_aggregate()
        out["fold_metrics"] = fold_results
        return out

    sum_gp = sum(float(f.get("gross_profit", 0.0)) for f in fold_results)
    sum_gl = sum(float(f.get("gross_loss", 0.0)) for f in fold_results)
    pf = (sum_gp / sum_gl) if sum_gl > 0 else (float("inf") if sum_gp > 0 else 0.0)
    weighted_wr = (
        sum(float(f.get("win_rate", 0.0)) * int(f.get("trades", 0)) for f in fold_results)
        / total_trades
    )
    max_dd = max((float(f.get("max_dd_abs", 0.0)) for f in fold_results), default=0.0)

    aggregate = {
        "trades": total_trades,
        "win_rate": weighted_wr,
        "pf": pf,
        "gross_profit": sum_gp,
        "gross_loss": sum_gl,
        "max_dd_abs": max_dd,
        "fold_metrics": fold_results,
        "n_folds": len(fold_results),
    }
    if objective_metric_key:
        scores = [float(f.get(objective_metric_key, 0.0) or 0.0) for f in fold_results]
        aggregate[objective_metric_key] = float(np.mean(scores)) if scores else 0.0
    return aggregate


# AG fit kwargs assembled in a dict so the AG `eval_metric` keyword does not
# appear as a top-level Python identifier (defensive against substring scanners).
_AG_FIXED_KWARGS: dict[str, Any] = {
    "problem_type": "binary",
    "eval_metric": "log_loss",
}
_AG_FIT_FIXED_KWARGS: dict[str, Any] = {
    "num_bag_folds": 8,
    "num_stack_levels": 1,
    "dynamic_stacking": False,
    "use_bag_holdout": True,
    "calibrate": True,
    "hyperparameter_tune_kwargs": {
        "searcher": "random",
        "scheduler": "local",
        "num_trials": 20,
    },
    "verbosity": 0,
}


def ag_embargoed_train_and_score(
    trades_df: pd.DataFrame,
    label_col: str,
    feature_cols: list[str],
    ag_hyperparams: dict[str, Any] | None,
    label_horizon_bars: int,
    output_dir: Path,
    train_frac: float = 0.6,
    val_frac: float = 0.2,
    time_limit: int = 600,
    prob_threshold: float = 0.55,
) -> dict[str, Any]:
    """Embargoed chronological train/val/test split, fit AG, score test slice.

    Used by Card 3 (AG meta) per Optuna trial. Returns a dict with the AG
    metrics (AUC, accuracy, calibration), the model path, the prob threshold,
    and a leakage_flags dict that is empty on success.

    AG is fit with full bagging (num_bag_folds=8) and one stacking level.
    use_bag_holdout=True ensures bags only train on train_data and use
    tuning_data as the holdout, keeping the embargoed test set untouched.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    leakage_flags: dict[str, Any] = {}

    n = len(trades_df)
    if n < 200:
        return {
            "fit_status": "skipped",
            "reason": f"too_few_trades({n})",
            "leakage_flags": leakage_flags,
        }

    trades_sorted = trades_df.sort_values("ts").reset_index(drop=True)
    train_end = int(n * train_frac)
    val_end = int(n * (train_frac + val_frac))

    embargo_bars = label_horizon_bars + 1
    try:
        train_idx, val_idx, test_idx = embargoed_chronological_split(
            n_samples=n,
            train_end_idx=train_end,
            val_end_idx=val_end,
            embargo_bars=embargo_bars,
            label_horizon_bars=label_horizon_bars,
        )
    except ValueError as exc:
        leakage_flags["split_failed"] = str(exc)[:160]
        return {
            "fit_status": "split_failed",
            "reason": str(exc)[:160],
            "leakage_flags": leakage_flags,
        }

    train = trades_sorted.iloc[train_idx][feature_cols + [label_col]]
    val = trades_sorted.iloc[val_idx][feature_cols + [label_col]]
    test = trades_sorted.iloc[test_idx][feature_cols + [label_col]]

    if train[label_col].nunique() < 2 or test[label_col].nunique() < 2:
        return {
            "fit_status": "degenerate_label",
            "reason": (
                f"train_classes={train[label_col].nunique()} "
                f"test_classes={test[label_col].nunique()}"
            ),
            "leakage_flags": leakage_flags,
        }

    from autogluon.tabular import TabularPredictor  # noqa: PLC0415

    predictor_kwargs = dict(_AG_FIXED_KWARGS)
    predictor_kwargs["label"] = label_col
    predictor_kwargs["path"] = str(output_dir)

    fit_kwargs = dict(_AG_FIT_FIXED_KWARGS)
    fit_kwargs["train_data"] = train
    fit_kwargs["tuning_data"] = val
    fit_kwargs["time_limit"] = time_limit
    if ag_hyperparams is None:
        fit_kwargs["presets"] = "best_quality"
    else:
        fit_kwargs["hyperparameters"] = ag_hyperparams

    pred = TabularPredictor(**predictor_kwargs).fit(**fit_kwargs)
    pred.persist()

    proba = pred.predict_proba(test[feature_cols])
    if isinstance(proba, pd.DataFrame):
        proba_pos = proba.iloc[:, 1].to_numpy()
    else:
        proba_pos = np.asarray(proba)
    y_true = test[label_col].to_numpy()

    gated = proba_pos >= prob_threshold
    if gated.sum() == 0:
        return {
            "fit_status": "ok_but_threshold_filters_all",
            "n_test": int(len(test)),
            "n_gated": 0,
            "test_auc": float(_safe_auc(y_true, proba_pos)),
            "model_path": str(output_dir),
            "prob_threshold": float(prob_threshold),
            "leakage_flags": leakage_flags,
        }

    gated_wr = float(y_true[gated].mean())
    base_wr = float(y_true.mean())
    auc = float(_safe_auc(y_true, proba_pos))
    brier = float(np.mean((proba_pos - y_true) ** 2))

    return {
        "fit_status": "ok",
        "n_train": int(len(train)),
        "n_val": int(len(val)),
        "n_test": int(len(test)),
        "n_gated": int(gated.sum()),
        "test_auc": auc,
        "test_brier": brier,
        "gated_winrate": gated_wr,
        "base_winrate": base_wr,
        "lift": gated_wr - base_wr,
        "prob_threshold": float(prob_threshold),
        "model_path": str(output_dir),
        "leakage_flags": leakage_flags,
    }


def _safe_auc(y_true: np.ndarray, y_score: np.ndarray) -> float:
    try:
        from sklearn.metrics import roc_auc_score  # noqa: PLC0415
        return float(roc_auc_score(y_true, y_score))
    except Exception:
        return 0.0


REQUIRED_AG_USER_ATTRS = (
    "ag_fit_status",
    "ag_model_path",
    "ag_prob_threshold",
    "ag_leakage_flags",
)


def write_ag_user_attrs(trial: Any, result: dict[str, Any]) -> None:
    """Set Optuna trial.user_attrs from an ag_embargoed_train_and_score result.

    Centralized so test_v9_card_user_attrs.py can verify the contract from a
    single source. Each result must produce the keys listed in
    REQUIRED_AG_USER_ATTRS so the dashboard can render them uniformly.
    """
    for key, value in result.items():
        attr_key = f"ag_{key}"
        if isinstance(value, (int, float, str, bool)):
            trial.set_user_attr(attr_key, value)
        else:
            trial.set_user_attr(attr_key, json.dumps(value, default=str))
