#!/usr/bin/env python3
"""
Warbird Inference — Load trained models, predict on latest data, write to Supabase.

Loads the most recent dataset row, runs all trained fold models,
ensembles predictions, computes Monte Carlo bands, and upserts
to the `forecasts` table.

Usage:
    python scripts/predict-warbird.py --dataset datasets/mes_unified_1h.csv --models models/warbird
    python scripts/predict-warbird.py --dataset datasets/mes_unified_1h.csv --models models/warbird --write
"""

import argparse
import json
import math
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")

HORIZONS = {"1h": 1, "4h": 4, "1d": 24, "1w": 120}
TARGET_TYPES = ("price", "mae", "mfe")

DROP_COLS = {"ts", "timestamp", "open", "high", "low", "close", "volume"}


def load_fold_models(model_dir: Path) -> list[tuple]:
    """Load all fold predictors for a model."""
    from autogluon.tabular import TabularPredictor

    folds = []
    for fold_dir in sorted(model_dir.glob("fold_*")):
        meta_path = fold_dir / "fold_meta.json"
        if not meta_path.exists():
            continue
        with open(meta_path) as f:
            meta = json.load(f)
        try:
            predictor = TabularPredictor.load(str(fold_dir))
            folds.append((predictor, meta.get("features", []), meta))
        except Exception as e:
            print(f"  Warning: failed to load {fold_dir}: {e}")
    return folds


def predict_ensemble(folds: list[tuple], row_df: pd.DataFrame) -> float | None:
    """Average predictions across all folds."""
    predictions = []
    for predictor, features, meta in folds:
        available = [f for f in features if f in row_df.columns]
        if not available:
            continue
        try:
            pred_df = row_df[available].copy()
            num_cols = pred_df.select_dtypes(include=[np.number]).columns
            pred_df[num_cols] = pred_df[num_cols].replace([np.inf, -np.inf], np.nan)
            pred = predictor.predict(pred_df)
            val = float(pred.iloc[0])
            if np.isfinite(val):
                predictions.append(val)
        except Exception as e:
            print(f"    Fold prediction failed: {e}")

    if not predictions:
        return None
    return float(np.mean(predictions))


def monte_carlo_band(
    current_price: float,
    predicted_price: float,
    sigma_horizon: float,
    horizon_bars: int,
    n_paths: int = 10_000,
) -> dict:
    """Monte Carlo band around predicted price."""
    if sigma_horizon <= 0 or not np.isfinite(predicted_price):
        return {"q10": predicted_price, "q50": predicted_price, "q90": predicted_price}

    rng = np.random.default_rng(42)
    drift = (predicted_price - current_price) / current_price
    mu_step = drift / max(1, horizon_bars)
    sigma_step = max(sigma_horizon / math.sqrt(max(1, horizon_bars)), 1e-8)

    steps = rng.normal(loc=mu_step, scale=sigma_step, size=(n_paths, horizon_bars))
    steps = np.clip(steps, -0.99, None)
    total_ret = np.prod(1.0 + steps, axis=1) - 1.0
    end_prices = current_price * (1.0 + total_ret)

    q10, q25, q50, q75, q90 = np.quantile(end_prices, [0.1, 0.25, 0.5, 0.75, 0.9])
    return {
        "q10": float(q10),
        "q25": float(q25),
        "q50": float(q50),
        "q75": float(q75),
        "q90": float(q90),
        "prob_up": float(np.mean(end_prices > current_price)),
    }


def main():
    parser = argparse.ArgumentParser(description="Warbird inference")
    parser.add_argument("--dataset", type=str, required=True)
    parser.add_argument("--models", type=str, default="models/warbird")
    parser.add_argument("--write", action="store_true", help="Write predictions to Supabase")
    args = parser.parse_args()

    model_dir = Path(args.models)

    # Load dataset
    print("Loading dataset...", end=" ", flush=True)
    df = pd.read_csv(args.dataset)
    df = df.sort_values("timestamp").reset_index(drop=True)
    print(f"{len(df):,} rows")

    # Latest row for prediction
    latest = df.tail(1).copy()
    current_price = float(latest["close"].iloc[0])
    ts = latest["timestamp"].iloc[0]
    print(f"Latest: {ts} | Price: {current_price:.2f}")

    # Feature columns
    target_cols = {c for c in df.columns if c.startswith("target_")}
    feature_cols = [c for c in df.columns if c not in DROP_COLS and c not in target_cols]

    results = {}

    for h_name, h_bars in HORIZONS.items():
        h_results = {}

        # Load GARCH params
        garch_path = model_dir / f"garch_{h_name}.json"
        sigma_horizon = 0.0
        if garch_path.exists():
            with open(garch_path) as f:
                garch = json.load(f)
            sigma_horizon = garch.get("sigma_horizon", 0.0)

        for target_type in TARGET_TYPES:
            sub_dir = model_dir / f"{h_name}_{target_type}"
            if not sub_dir.exists():
                continue

            folds = load_fold_models(sub_dir)
            if not folds:
                continue

            pred = predict_ensemble(folds, latest)
            if pred is None:
                continue

            h_results[target_type] = pred
            print(f"  {h_name}/{target_type}: {pred:.2f}")

        # Monte Carlo bands for price prediction
        if "price" in h_results and sigma_horizon > 0:
            mc = monte_carlo_band(current_price, h_results["price"], sigma_horizon, h_bars)
            h_results["mc"] = mc
            print(f"  {h_name}/MC: Q10={mc['q10']:.2f} Q50={mc['q50']:.2f} "
                  f"Q90={mc['q90']:.2f} P(up)={mc['prob_up']:.1%}")

        if h_results:
            results[h_name] = h_results

    # Write to Supabase
    if args.write and results and SUPABASE_URL and SUPABASE_KEY:
        from supabase import create_client
        supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

        now = datetime.now(timezone.utc).isoformat()
        rows = []
        for h_name, h_data in results.items():
            row = {
                "ts": now,
                "horizon": h_name,
                "symbol_code": "MES.c.0",
                "predicted_price": h_data.get("price"),
                "predicted_mae": h_data.get("mae"),
                "predicted_mfe": h_data.get("mfe"),
                "current_price": current_price,
            }
            mc = h_data.get("mc", {})
            if mc:
                row["mc_q10"] = mc.get("q10")
                row["mc_q50"] = mc.get("q50")
                row["mc_q90"] = mc.get("q90")
                row["mc_prob_up"] = mc.get("prob_up")
            rows.append(row)

        supabase.table("forecasts").insert(rows).execute()
        print(f"\nWrote {len(rows)} forecasts to Supabase")
    elif args.write:
        print("\nWARNING: --write specified but missing SUPABASE_URL/KEY")

    # Save locally
    output_path = model_dir / "latest_predictions.json"
    with open(output_path, "w") as f:
        json.dump({"timestamp": ts, "price": current_price, "predictions": results}, f, indent=2)
    print(f"\nSaved to {output_path}")


if __name__ == "__main__":
    main()
