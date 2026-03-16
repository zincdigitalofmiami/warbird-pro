#!/usr/bin/env python3
"""
Canonical Warbird GARCH engine.

Fits GJR-GARCH(1,1) with Student-t innovations against regime-anchored returns
and emits raw sigma plus volatility ratio features.
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd

REGIME_START = "2025-01-20T00:00:00Z"


def fit_garch_features(returns: np.ndarray, realized_window: np.ndarray | None = None) -> dict:
    clean = np.asarray(returns, dtype=float)
    clean = clean[np.isfinite(clean)]
    if clean.size < 120:
        sigma = float(np.std(clean)) if clean.size else 0.0
        realized = float(np.std(realized_window)) if realized_window is not None and len(realized_window) else sigma
        return {
            "method": "std_fallback",
            "sigma": sigma,
            "vol_ratio": sigma / realized if realized else 1.0,
        }

    try:
        from arch import arch_model

        model = arch_model(clean * 100.0, mean="Zero", vol="GARCH", p=1, o=1, q=1, dist="t")
        fit = model.fit(disp="off")
        forecast = fit.forecast(horizon=1, reindex=False)
        variance = float(forecast.variance.values[-1, 0]) / (100.0 * 100.0)
        sigma = math.sqrt(max(variance, 1e-12))
        realized = float(np.std(realized_window)) if realized_window is not None and len(realized_window) else sigma
        return {
            "method": "gjr_garch11_t",
            "sigma": sigma,
            "vol_ratio": sigma / realized if realized else 1.0,
            "params": {key: float(value) for key, value in fit.params.items()},
        }
    except Exception:
        sigma = float(np.std(clean))
        realized = float(np.std(realized_window)) if realized_window is not None and len(realized_window) else sigma
        return {
            "method": "std_proxy",
            "sigma": sigma,
            "vol_ratio": sigma / realized if realized else 1.0,
        }


def main() -> None:
    parser = argparse.ArgumentParser(description="Fit canonical Warbird GARCH features")
    parser.add_argument("--dataset", required=True, help="Path to canonical 1H dataset CSV")
    parser.add_argument("--output", default="models/warbird/garch_features.json")
    args = parser.parse_args()

    df = pd.read_csv(args.dataset)
    if "timestamp" in df.columns:
        df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
        df = df[df["timestamp"] >= pd.Timestamp(REGIME_START)]

    returns = df["returns_1h"].replace([np.inf, -np.inf], np.nan).dropna().to_numpy()
    realized_window = returns[-50:] if returns.size >= 50 else returns
    features = fit_garch_features(returns, realized_window)

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(features, indent=2))
    print(f"Wrote {output_path}")


if __name__ == "__main__":
    main()
