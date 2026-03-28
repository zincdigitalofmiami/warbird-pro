#!/usr/bin/env python3
"""
Canonical Warbird inference pipeline.

Loads the trained Warbird model bundle, scores the latest dataset row, and
writes compatibility-safe output rows to warbird_forecasts_1h and warbird_risk.

Legacy `hit_*_first` target names still exist inside this old local
training/predictor workflow, but they are scheduled for deletion during the
training workbench rebuild and must not appear in new API, packet, or dashboard
contracts.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

import pandas as pd
from supabase import create_client

SUPABASE_URL = os.environ.get("NEXT_PUBLIC_SUPABASE_URL") or os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")

PRIMARY_BINARY_TARGETS = ("hit_sl_first", "hit_pt1_first", "hit_pt2_after_pt1")
PRIMARY_REGRESSION_TARGETS = ("max_favorable_excursion", "max_adverse_excursion")

LEGACY_BINARY_TARGETS = ("reached_tp1", "reached_tp2", "setup_stopped")
LEGACY_REGRESSION_TARGETS = ("max_favorable_excursion", "max_adverse_excursion")


def load_predictor(manifest_entry: dict):
    from autogluon.tabular import TabularPredictor

    return TabularPredictor.load(manifest_entry["path"]), manifest_entry["features"]


def read_float(row: pd.Series, column: str, default: float) -> float:
    value = row.get(column, default)
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return float(default)
    return parsed if parsed == parsed else float(default)


def require_float(row: pd.Series, column: str) -> float:
    value = row.get(column)
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        raise SystemExit(f"Missing required numeric column for inference: {column}")
    if parsed != parsed:
        raise SystemExit(f"NaN value is not allowed for inference column: {column}")
    return parsed


def infer_extension_bucket(predicted_mfe: float, tp1_distance: float, tp2_distance: float) -> float:
    ext_200_distance = tp2_distance * (2.0 / 1.618) if tp2_distance > 0 else tp1_distance * (2.0 / 1.236)
    if predicted_mfe >= ext_200_distance:
        return 2.0
    if predicted_mfe >= tp2_distance:
        return 1.618
    return 1.236


def predict_binary_probability(predictor, features: pd.DataFrame) -> float:
    proba = predictor.predict_proba(features)
    if isinstance(proba, pd.DataFrame):
        if 1 in proba.columns:
            return float(proba[1].iloc[0])
        if "1" in proba.columns:
            return float(proba["1"].iloc[0])
        if True in proba.columns:
            return float(proba[True].iloc[0])
        if "True" in proba.columns:
            return float(proba["True"].iloc[0])
        # Fallback for uncommon class labels.
        return float(proba.iloc[0, -1])

    # Fallback: predictor returned hard labels.
    pred = predictor.predict(features)
    return float(pred.iloc[0])


def main() -> None:
    parser = argparse.ArgumentParser(description="Run canonical Warbird inference")
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--models", default="models/warbird_v1")
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()

    df = pd.read_csv(args.dataset)
    sort_col = "timestamp" if "timestamp" in df.columns else "ts"
    if sort_col not in df.columns:
        raise SystemExit("Dataset must include either 'timestamp' or 'ts'")

    df = df.sort_values(sort_col).reset_index(drop=True)
    latest = df.tail(1).copy()
    if latest.empty:
        raise SystemExit("Dataset is empty")
    latest_row = latest.iloc[0]

    manifest_path = Path(args.models) / "manifest.json"
    if not manifest_path.exists():
        raise SystemExit(f"Manifest not found: {manifest_path}")
    manifest = json.loads(manifest_path.read_text())
    manifest_targets = set(manifest.keys())

    primary_supported = all(target in manifest_targets for target in (*PRIMARY_BINARY_TARGETS, *PRIMARY_REGRESSION_TARGETS))
    legacy_supported = all(target in manifest_targets for target in (*LEGACY_BINARY_TARGETS, *LEGACY_REGRESSION_TARGETS))

    if not primary_supported and not legacy_supported:
        raise SystemExit("Manifest does not contain a supported target bundle")

    mode = "primary" if primary_supported else "legacy"
    binary_targets = PRIMARY_BINARY_TARGETS if mode == "primary" else LEGACY_BINARY_TARGETS
    regression_targets = PRIMARY_REGRESSION_TARGETS if mode == "primary" else LEGACY_REGRESSION_TARGETS

    binary_probs: dict[str, float] = {}
    regression_preds: dict[str, float] = {}

    for target in binary_targets:
        predictor, features = load_predictor(manifest[target])
        binary_probs[target] = max(0.0, min(1.0, predict_binary_probability(predictor, latest[features])))

    for target in regression_targets:
        predictor, features = load_predictor(manifest[target])
        pred = predictor.predict(latest[features])
        regression_preds[target] = max(0.0, float(pred.iloc[0]))

    if mode == "primary":
        sl_before_tp1_probability = binary_probs["hit_sl_first"]
        tp1_before_sl_probability = binary_probs["hit_pt1_first"]
        tp2_given_tp1_probability = binary_probs["hit_pt2_after_pt1"]
    else:
        prob_reached_tp1 = binary_probs["reached_tp1"]
        prob_reached_tp2 = binary_probs["reached_tp2"]
        sl_before_tp1_probability = binary_probs["setup_stopped"]
        tp1_before_sl_probability = prob_reached_tp1 * (1.0 - sl_before_tp1_probability)
        tp2_given_tp1_probability = prob_reached_tp2 / max(prob_reached_tp1, 1e-6)
        tp2_given_tp1_probability = max(0.0, min(1.0, tp2_given_tp1_probability))

    tp2_before_sl_probability = tp1_before_sl_probability * tp2_given_tp1_probability

    direction_raw = str(latest_row.get("direction", "LONG")).upper()
    direction = "SHORT" if direction_raw == "SHORT" else "LONG"
    direction_sign = -1.0 if direction == "SHORT" else 1.0
    bias_1h = "BEAR" if direction == "SHORT" else "BULL"

    current_price = require_float(latest_row, "close")
    entry_price = require_float(latest_row, "entry_price")
    stop_loss = require_float(latest_row, "stop_loss")
    tp1_price = require_float(latest_row, "tp1_price")
    tp2_price = require_float(latest_row, "tp2_price")

    tp1_distance = abs(tp1_price - entry_price)
    tp2_distance = abs(tp2_price - entry_price)
    pred_mfe = max(0.0, regression_preds["max_favorable_excursion"])
    pred_mae = max(0.25, regression_preds["max_adverse_excursion"])

    expected_extension = infer_extension_bucket(pred_mfe, tp1_distance, tp2_distance)
    setup_score = max(
        0.0,
        min(
            100.0,
            100.0
            * (
                0.40 * tp1_before_sl_probability
                + 0.35 * tp2_before_sl_probability
                + 0.25 * (1.0 - sl_before_tp1_probability)
            ),
        ),
    )

    target_mfe_4h = max(pred_mfe, tp2_distance)
    target_mae_1h = pred_mae
    target_mae_4h = pred_mae * 1.25
    target_price_1h = entry_price + direction_sign * max(pred_mfe, tp1_distance)
    target_price_4h = entry_price + direction_sign * target_mfe_4h
    confidence = setup_score / 100.0
    symbol_code = str(latest_row.get("symbol_code", "MES"))
    ts_value = str(latest_row[sort_col])

    feature_snapshot = {
        "model_mode": mode,
        "geometry_status": str(latest_row.get("geometry_status", "current")),
        "direction": direction,
        "entry_price": entry_price,
        "stop_loss": stop_loss,
        "tp1_price": tp1_price,
        "tp2_price": tp2_price,
        "tp1_before_sl_probability": tp1_before_sl_probability,
        "tp2_before_sl_probability": tp2_before_sl_probability,
        "sl_before_tp1_probability": sl_before_tp1_probability,
        "expected_max_extension": expected_extension,
        "setup_score": setup_score,
        "predicted_mfe": pred_mfe,
        "predicted_mae": pred_mae,
        "setup_frequency_7d": read_float(latest_row, "setup_frequency_7d", 0.0),
    }

    forecast_row = {
        "ts": ts_value,
        "symbol_code": symbol_code,
        "bias_1h": bias_1h,
        "target_price_1h": target_price_1h,
        "target_price_4h": target_price_4h,
        "target_mae_1h": target_mae_1h,
        "target_mae_4h": target_mae_4h,
        "target_mfe_1h": pred_mfe,
        "target_mfe_4h": target_mfe_4h,
        "sl_before_tp1_probability": sl_before_tp1_probability,
        "tp1_before_sl_probability": tp1_before_sl_probability,
        "tp2_before_sl_probability": tp2_before_sl_probability,
        "expected_max_extension": expected_extension,
        "setup_score": setup_score,
        "confidence": confidence,
        "mfe_mae_ratio_1h": pred_mfe / max(target_mae_1h, 0.25),
        "current_price": current_price,
        "model_version": "warbird-v1.1-trigger-prob",
        "feature_snapshot": feature_snapshot,
    }

    # Legacy table scrub only. Deprecated hit-first columns are intentionally nulled.
    forecast_write_row = {
        "ts": ts_value,
        "symbol_code": symbol_code,
        "bias_1h": bias_1h,
        "target_price_1h": target_price_1h,
        "target_price_4h": target_price_4h,
        "target_mae_1h": target_mae_1h,
        "target_mae_4h": target_mae_4h,
        "target_mfe_1h": pred_mfe,
        "target_mfe_4h": target_mfe_4h,
        "prob_hit_sl_first": None,
        "prob_hit_pt1_first": None,
        "prob_hit_pt2_after_pt1": None,
        "expected_max_extension": expected_extension,
        "setup_score": setup_score,
        "confidence": confidence,
        "mfe_mae_ratio_1h": pred_mfe / max(target_mae_1h, 0.25),
        "current_price": current_price,
        "model_version": "warbird-v1.1-trigger-prob",
        "feature_snapshot": feature_snapshot,
    }

    rolling_std_20 = read_float(latest_row, "rolling_std_20", 0.0)
    rolling_std_50 = read_float(latest_row, "rolling_std_50", 1.0)
    garch_vol_ratio = rolling_std_20 / max(rolling_std_50, 1e-6)
    if garch_vol_ratio >= 1.7:
        vol_state_name = "EXTREME"
    elif garch_vol_ratio >= 1.35:
        vol_state_name = "CRISIS"
    elif garch_vol_ratio >= 1.1:
        vol_state_name = "ELEVATED"
    elif garch_vol_ratio <= 0.75:
        vol_state_name = "COMPRESSED"
    else:
        vol_state_name = "NORMAL"

    risk_row = {
        "ts": ts_value,
        "symbol_code": symbol_code,
        "garch_sigma": rolling_std_20,
        "garch_vol_ratio": garch_vol_ratio,
        "zone_1_upper": target_price_1h + target_mae_1h,
        "zone_1_lower": target_price_1h - target_mae_1h,
        "zone_2_upper": target_price_4h + target_mae_4h,
        "zone_2_lower": target_price_4h - target_mae_4h,
        "gpr_level": read_float(latest_row, "gpr_level", 0.0),
        "trump_effect_active": bool(read_float(latest_row, "trump_events_7d", 0.0)),
        "vix_level": read_float(latest_row, "fred_vixcls", 0.0),
        "vix_percentile_20d": read_float(latest_row, "fred_vixcls_pctile_20", 0.0),
        "vix_percentile_regime": read_float(latest_row, "fred_vixcls_pctile_20", 0.0),
        "vol_state_name": vol_state_name,
        "regime_label": str(latest_row.get("regime_label", "trump_2")),
        "days_into_regime": int(read_float(latest_row, "days_into_regime", 0.0)),
    }

    if args.write:
        if not SUPABASE_URL or not SUPABASE_KEY:
            raise SystemExit("Missing Supabase credentials")
        supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

        forecast_result = (
            supabase.table("warbird_forecasts_1h")
            .upsert(forecast_write_row, on_conflict="symbol_code,ts")
            .execute()
        )
        forecast_data = forecast_result.data if isinstance(forecast_result.data, list) else []
        forecast_id = forecast_data[0]["id"] if forecast_data else None

        if forecast_id is not None:
            risk_row["forecast_id"] = forecast_id
            supabase.table("warbird_risk").upsert(risk_row, on_conflict="forecast_id").execute()

    print(
        json.dumps(
            {
                "mode": mode,
                "forecast": forecast_row,
                "risk": risk_row,
            },
            indent=2,
            default=float,
        ),
    )


if __name__ == "__main__":
    main()
