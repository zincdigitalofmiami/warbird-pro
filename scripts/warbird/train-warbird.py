#!/usr/bin/env python3
"""
Canonical Warbird training pipeline.

Trains one AutoGluon predictor per target against the Warbird dataset and
writes a bundle manifest consumed by scripts/warbird/predict-warbird.py.

Primary target set (current):
  - hit_sl_first
  - hit_pt1_first
  - hit_pt2_after_pt1
  - max_favorable_excursion
  - max_adverse_excursion

Legacy target set remains supported for backward compatibility.
"""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

import pandas as pd

PRIMARY_TARGET_CONFIG = {
    "hit_sl_first": {"problem_type": "binary", "eval_metric": "roc_auc"},
    "hit_pt1_first": {"problem_type": "binary", "eval_metric": "roc_auc"},
    "hit_pt2_after_pt1": {"problem_type": "binary", "eval_metric": "roc_auc"},
    "max_favorable_excursion": {"problem_type": "regression", "eval_metric": "root_mean_squared_error"},
    "max_adverse_excursion": {"problem_type": "regression", "eval_metric": "root_mean_squared_error"},
}

LEGACY_TARGET_CONFIG = {
    "reached_tp1": {"problem_type": "binary", "eval_metric": "roc_auc"},
    "reached_tp2": {"problem_type": "binary", "eval_metric": "roc_auc"},
    "setup_stopped": {"problem_type": "binary", "eval_metric": "roc_auc"},
    "max_favorable_excursion": {"problem_type": "regression", "eval_metric": "root_mean_squared_error"},
    "max_adverse_excursion": {"problem_type": "regression", "eval_metric": "root_mean_squared_error"},
}

DROP_COLS = {
    "timestamp",
    "ts",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "geometry_status",
    "sample_weight",
}

ALL_OUTCOME_COLS = {
    "reached_tp1",
    "reached_tp2",
    "setup_stopped",
    "hit_sl_first",
    "hit_pt1_first",
    "hit_pt2_after_pt1",
    "max_extension_reached",
    "max_favorable_excursion",
    "max_adverse_excursion",
}


def resolve_target_config(df: pd.DataFrame) -> dict[str, dict]:
    columns = set(df.columns)
    if all(col in columns for col in PRIMARY_TARGET_CONFIG):
        return PRIMARY_TARGET_CONFIG
    if all(col in columns for col in LEGACY_TARGET_CONFIG):
        return LEGACY_TARGET_CONFIG
    raise SystemExit(
        "Dataset missing required target columns for both primary and legacy target sets",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Train the canonical Warbird v1 forecaster")
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--output", default="models/warbird_v1")
    args = parser.parse_args()

    from autogluon.tabular import TabularPredictor

    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    df = pd.read_csv(args.dataset)
    target_config = resolve_target_config(df)
    sort_col = "timestamp" if "timestamp" in df.columns else "ts"
    if sort_col not in df.columns:
        raise SystemExit("Dataset must include either 'timestamp' or 'ts'")

    df = df.sort_values(sort_col).reset_index(drop=True)
    if len(df) < 200:
        raise SystemExit(f"Dataset is too small for training: {len(df)} rows")

    use_sample_weight = "sample_weight" in df.columns and df["sample_weight"].notna().any()
    outcome_cols = ALL_OUTCOME_COLS.intersection(df.columns)

    feature_cols = sorted(
        col
        for col in df.columns
        if col not in DROP_COLS
        and col not in outcome_cols
        and not col.startswith("target_")
    )

    if not feature_cols:
        raise SystemExit("No feature columns left after dropping labels/leakage columns")

    print(f"Training rows: {len(df)}")
    print(f"Feature columns: {len(feature_cols)}")
    print(f"Target set: {', '.join(target_config.keys())}")
    print(f"Sample weights enabled: {use_sample_weight}")

    split_index = int(len(df) * 0.8)
    train = df.iloc[:split_index].copy()
    valid = df.iloc[split_index:].copy()

    bundle_manifest: dict[str, dict] = {}

    for target, config in target_config.items():
        predictor_path = output_dir / target
        if predictor_path.exists():
            shutil.rmtree(predictor_path)

        predictor_kwargs = {
            "label": target,
            "problem_type": config["problem_type"],
            "eval_metric": config["eval_metric"],
            "path": str(predictor_path),
        }
        if use_sample_weight:
            predictor_kwargs["sample_weight"] = "sample_weight"
            predictor_kwargs["weight_evaluation"] = True

        predictor = TabularPredictor(**predictor_kwargs)
        fit_cols = feature_cols + [target]
        if use_sample_weight:
            fit_cols = fit_cols + ["sample_weight"]

        fit_kwargs = {
            "train_data": train[fit_cols],
            "tuning_data": valid[fit_cols],
            "presets": "best_quality",
            "num_bag_folds": 5,
            "num_stack_levels": 1,
            "dynamic_stacking": "auto",
            "excluded_model_types": ["KNN", "FASTAI"],
            "ag_args_ensemble": {"fold_fitting_strategy": "sequential_local"},
        }
        predictor.fit(**fit_kwargs)

        leaderboard = predictor.leaderboard(
            valid[feature_cols + [target]],
            silent=True,
        ).head(5)
        bundle_manifest[target] = {
            "path": str(predictor_path),
            "features": feature_cols,
            "problem_type": config["problem_type"],
            "eval_metric": config["eval_metric"],
            "leaderboard": leaderboard.to_dict(orient="records"),
        }

    (output_dir / "manifest.json").write_text(json.dumps(bundle_manifest, indent=2))
    print(f"Wrote canonical Warbird model bundle to {output_dir}")


if __name__ == "__main__":
    main()
