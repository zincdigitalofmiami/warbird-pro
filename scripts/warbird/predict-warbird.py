#!/usr/bin/env python3
"""
Canonical Warbird v1 inference pipeline.

Loads the trained Warbird bundle, scores the latest 1H feature row, derives the
core tells, and writes canonical rows to warbird_forecasts_1h and warbird_risk.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

import numpy as np
import pandas as pd
from supabase import create_client

SUPABASE_URL = os.environ.get("NEXT_PUBLIC_SUPABASE_URL") or os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")

TARGETS = [
    "target_price_1h",
    "target_price_4h",
    "target_mae_1h",
    "target_mae_4h",
    "target_mfe_1h",
    "target_mfe_4h",
]


def load_predictor(manifest_entry: dict):
    from autogluon.tabular import TabularPredictor

    return TabularPredictor.load(manifest_entry["path"]), manifest_entry["features"]


def bias_from_price(current_price: float, target_price: float) -> str:
    delta = target_price - current_price
    if abs(delta) < 2.0:
        return "NEUTRAL"
    return "BULL" if delta > 0 else "BEAR"


def main() -> None:
    parser = argparse.ArgumentParser(description="Run canonical Warbird inference")
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--models", default="models/warbird_v1")
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()

    df = pd.read_csv(args.dataset)
    df = df.sort_values("timestamp").reset_index(drop=True)
    latest = df.tail(1).copy()
    if latest.empty:
        raise SystemExit("Dataset is empty")

    manifest = json.loads((Path(args.models) / "manifest.json").read_text())
    predictions: dict[str, float] = {}
    for target in TARGETS:
        predictor, features = load_predictor(manifest[target])
        pred = predictor.predict(latest[features])
        predictions[target] = float(pred.iloc[0])

    current_price = float(latest["close"].iloc[0])
    confidence = max(
        0.0,
        min(
            1.0,
            predictions["target_mfe_1h"] / max(predictions["target_mae_1h"], 0.25) / 3.0,
        ),
    )
    runner_headroom = predictions["target_mfe_4h"] - abs(predictions["target_price_4h"] - current_price)
    bias_1h = bias_from_price(current_price, predictions["target_price_1h"])

    feature_snapshot = {
        "correlation_score": latest.get("ca_nq.c.0_ret_1h", pd.Series([np.nan])).iloc[0],
        "win_rate_last20": latest.get("win_rate_last20", pd.Series([np.nan])).iloc[0],
        "current_streak": latest.get("current_streak", pd.Series([np.nan])).iloc[0],
        "avg_r_recent": latest.get("avg_r_recent", pd.Series([np.nan])).iloc[0],
        "setup_frequency_7d": latest.get("setup_frequency_7d", pd.Series([np.nan])).iloc[0],
    }

    forecast_row = {
        "ts": latest["timestamp"].iloc[0],
        "symbol_code": "MES",
        "bias_1h": bias_1h,
        "target_price_1h": predictions["target_price_1h"],
        "target_price_4h": predictions["target_price_4h"],
        "target_mae_1h": predictions["target_mae_1h"],
        "target_mae_4h": predictions["target_mae_4h"],
        "target_mfe_1h": predictions["target_mfe_1h"],
        "target_mfe_4h": predictions["target_mfe_4h"],
        "confidence": confidence,
        "mfe_mae_ratio_1h": predictions["target_mfe_1h"] / max(predictions["target_mae_1h"], 0.25),
        "runner_headroom_4h": runner_headroom,
        "current_price": current_price,
        "model_version": "warbird-v1.0",
        "feature_snapshot": feature_snapshot,
    }

    risk_row = {
        "ts": latest["timestamp"].iloc[0],
        "symbol_code": "MES",
        "garch_sigma": latest.get("rolling_std_20", pd.Series([np.nan])).iloc[0],
        "garch_vol_ratio": (
            latest.get("rolling_std_20", pd.Series([np.nan])).iloc[0]
            / max(latest.get("rolling_std_50", pd.Series([1.0])).iloc[0], 1e-6)
        ),
        "zone_1_upper": predictions["target_price_1h"] + predictions["target_mae_1h"],
        "zone_1_lower": predictions["target_price_1h"] - predictions["target_mae_1h"],
        "zone_2_upper": predictions["target_price_4h"] + predictions["target_mae_4h"],
        "zone_2_lower": predictions["target_price_4h"] - predictions["target_mae_4h"],
        "gpr_level": latest.get("gpr_level", pd.Series([np.nan])).iloc[0],
        "trump_effect_active": bool(latest.get("trump_events_7d", pd.Series([0])).iloc[0]),
        "vix_level": latest.get("fred_vol_vixcls", pd.Series([np.nan])).iloc[0],
        "vix_percentile_20d": latest.get("fred_vol_vixcls_pctile_20", pd.Series([np.nan])).iloc[0],
        "vix_percentile_regime": latest.get("fred_vol_vixcls_pctile_20", pd.Series([np.nan])).iloc[0],
        "vol_state_name": "NORMAL",
        "regime_label": "trump_2",
        "days_into_regime": latest.get("days_into_regime", pd.Series([np.nan])).iloc[0],
    }

    if args.write:
        if not SUPABASE_URL or not SUPABASE_KEY:
            raise SystemExit("Missing Supabase credentials")
        supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
        forecast_result = (
            supabase.table("warbird_forecasts_1h")
            .upsert(forecast_row, on_conflict="symbol_code,ts")
            .execute()
        )
        forecast_data = forecast_result.data if isinstance(forecast_result.data, list) else []
        forecast_id = forecast_data[0]["id"] if forecast_data else None
        if forecast_id is not None:
            risk_row["forecast_id"] = forecast_id
            supabase.table("warbird_risk").upsert(risk_row, on_conflict="forecast_id").execute()

    print(json.dumps({"forecast": forecast_row, "risk": risk_row}, indent=2, default=float))


if __name__ == "__main__":
    main()
