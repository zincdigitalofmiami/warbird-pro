#!/usr/bin/env python3
"""
Canonical Warbird v1 training pipeline.

Trains the Warbird v1 model bundle against the canonical dataset. AutoGluon
trains one predictor per target: 3 binary (TP1/TP2/stopped) + 2 regression
(MFE/MAE). RF included in ensemble.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

TARGET_CONFIG = {
    "reached_tp1":           {"problem_type": "binary",     "eval_metric": "roc_auc"},
    "reached_tp2":           {"problem_type": "binary",     "eval_metric": "roc_auc"},
    "setup_stopped":         {"problem_type": "binary",     "eval_metric": "roc_auc"},
    "max_favorable_excursion": {"problem_type": "regression", "eval_metric": "root_mean_squared_error"},
    "max_adverse_excursion":   {"problem_type": "regression", "eval_metric": "root_mean_squared_error"},
}

DROP_COLS = {
    "timestamp",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "target_price_1h",
    "target_price_4h",
    "target_mae_1h",
    "target_mae_4h",
    "target_mfe_1h",
    "target_mfe_4h",
}


def main() -> None:
    parser = argparse.ArgumentParser(description="Train the canonical Warbird v1 forecaster")
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--output", default="models/warbird_v1")
    args = parser.parse_args()

    from autogluon.tabular import TabularPredictor

    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    df = pd.read_csv(args.dataset)
    df = df.sort_values("timestamp").reset_index(drop=True)
    split_index = int(len(df) * 0.8)
    train = df.iloc[:split_index].copy()
    valid = df.iloc[split_index:].copy()

    bundle_manifest: dict[str, dict] = {}

    for target, config in TARGET_CONFIG.items():
        feature_cols = [
            col
            for col in df.columns
            if col not in DROP_COLS and not col.startswith("target_") and col != target
        ]
        predictor_path = output_dir / target
        predictor = TabularPredictor(
            label=target,
            problem_type=config["problem_type"],
            eval_metric=config["eval_metric"],
            path=str(predictor_path),
        )
        predictor.fit(
            train_data=train[feature_cols + [target]],
            tuning_data=valid[feature_cols + [target]],
            presets="best_quality",
            num_bag_folds=5,
            num_stack_levels=1,
            dynamic_stacking="auto",
            excluded_model_types=["KNN", "FASTAI"],
            ag_args_ensemble={"fold_fitting_strategy": "sequential_local"},
        )

        leaderboard = predictor.leaderboard(
            valid[feature_cols + [target]],
            silent=True,
        ).head(5)
        bundle_manifest[target] = {
            "path": str(predictor_path),
            "features": feature_cols,
            "leaderboard": leaderboard.to_dict(orient="records"),
        }

    (output_dir / "manifest.json").write_text(json.dumps(bundle_manifest, indent=2))
    print(f"Wrote canonical Warbird model bundle to {output_dir}")


if __name__ == "__main__":
    main()
