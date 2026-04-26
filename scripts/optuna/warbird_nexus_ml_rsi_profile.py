#!/usr/bin/env python3
"""Optuna profile for Warbird Nexus Machine Learning RSI.

Guide-driven tuning surface for the user's actual workflow on MES 5m:
- primary signals are oscillator/signal crosses on the correct side of the midline
- confirmations come from volume flow, KNN, and confluence
- fatigue is a first-class weakening/reversal warning

This is the canonical Nexus research lane used by the Warbird Optuna Hub:
http://127.0.0.1:8090/studies/warbird_nexus_ml_rsi

It runs only over manifest-backed TradingView/Pine exports that include the
Nexus footprint columns emitted by request.footprint(). The prior local OHLCV
parquet delta proxy is intentionally not accepted as active model truth.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


MINTICK = 0.25
WORKSPACE_DIR = REPO_ROOT / "scripts" / "optuna" / "workspaces" / "warbird_nexus_ml_rsi"
DEFAULT_MANIFEST_PATH = WORKSPACE_DIR / "pine_export_manifest.json"
NEXUS_TRIGGER_FAMILY = "NEXUS_FOOTPRINT_DELTA"
NEXUS_PINE_FILE = "indicators/warbird-nexus-machine-learning-rsi-optuna-fast-test.pine"
EXPORT_PATH_KEYS = ("export_path", "csv_path", "path", "tradingview_csv")
REQUIRED_EXPORT_COLS = {
    "ts",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "nexus_fp_available",
    "nexus_fp_bar_delta",
    "nexus_fp_total_volume",
}


BOOL_PARAMS: list[str] = [
    "useConfluenceGate",
    "useVolumeFlowGate",
    "useZoneExitSignals",
    "useKnnGate",
]

NUMERIC_RANGES: dict[str, tuple[float, float]] = {
    "lengthInput": (8.0, 50.0),
    "sigLenInput": (3.0, 16.0),
    "obInput": (60.0, 88.0),
    "osInput": (12.0, 38.0),
    "confHighInput": (60.0, 75.0),
    "confLowInput": (25.0, 40.0),
    "fatigueBarsInput": (1.0, 5.0),
    "knnKInput": (3.0, 15.0),
    "knnWindowInput": (50.0, 400.0),
    "knnBullThresholdInput": (54.0, 66.0),
    "knnBearThresholdInput": (34.0, 46.0),
    "knnAtrLabelThresholdInput": (0.05, 0.30),
    "knnRecencyBoostInput": (0.00, 0.25),
    "vfBodyWeightInput": (0.45, 0.85),
    "vfFastLenMultInput": (0.35, 0.90),
    "vfSlowLenMultInput": (1.00, 2.20),
    "vfFastBlendWeightInput": (0.35, 0.80),
    "vfPeakLenMultInput": (2.0, 6.0),
    "vfSignalThresholdInput": (50.0, 60.0),
    "vfGateThresholdInput": (50.0, 60.0),
    "confOscBullThresholdInput": (52.0, 62.0),
    "confOscBearThresholdInput": (38.0, 48.0),
    "confVfBullThresholdInput": (52.0, 62.0),
    "confVfBearThresholdInput": (38.0, 48.0),
    "confErThresholdInput": (0.20, 0.45),
    "confSmoothLenInput": (1.0, 8.0),
    # Evaluation horizon (formerly hardcoded)
    "leg_threshold_pts": (6.0, 20.0),
    "response_bars":     (5.0, 25.0),
    "early_bars":        (2.0, 10.0),
    "adverse_bars":      (3.0, 15.0),
    # Delta parameters
    "delta_lookback":    (3.0, 20.0),
    "delta_slope_len":   (2.0, 10.0),
    "gasout_stall_bars": (2.0, 8.0),
    "delta_flip_thresh": (0.05, 0.40),
    "gasout_thresh":     (0.01, 0.20),
}

INT_PARAMS: set[str] = {
    "lengthInput",
    "sigLenInput",
    "fatigueBarsInput",
    "knnKInput",
    "knnWindowInput",
    "confSmoothLenInput",
    "response_bars",
    "early_bars",
    "adverse_bars",
    "delta_lookback",
    "delta_slope_len",
    "gasout_stall_bars",
}

CATEGORICAL_PARAMS: dict[str, list[Any]] = {
    "sourceInput": ["open", "high", "low", "close", "hl2", "hlc3", "ohlc4", "hlcc4"],
    "smoothTypeInput": ["EMA", "SMA", "DEMA", "TEMA", "WMA", "VWMA"],
    "presetInput": ["Scalping", "Default", "Swing", "Position"],
    "sigTypeInput": ["EMA", "SMA", "DEMA", "WMA"],
}

CONDITIONAL_PARAMS: dict[str, dict[str, list[str]]] = {
    "presetInput": {
        "Default": ["lengthInput", "obInput", "osInput"],
    },
}

INPUT_DEFAULTS: dict[str, Any] = {
    "lengthInput": 18,
    "sourceInput": "close",
    "smoothTypeInput": "DEMA",
    "presetInput": "Default",
    "sigLenInput": 6,
    "sigTypeInput": "EMA",
    "obInput": 75.0,
    "osInput": 25.0,
    "confHighInput": 65.0,
    "confLowInput": 35.0,
    "useConfluenceGate": True,
    "useVolumeFlowGate": True,
    "useZoneExitSignals": False,
    "useKnnGate": True,
    "fatigueBarsInput": 2,
    "knnKInput": 7,
    "knnWindowInput": 180,
    "knnBullThresholdInput": 58.0,
    "knnBearThresholdInput": 42.0,
    "knnAtrLabelThresholdInput": 0.15,
    "knnRecencyBoostInput": 0.10,
    "vfBodyWeightInput": 0.70,
    "vfFastLenMultInput": 0.60,
    "vfSlowLenMultInput": 1.40,
    "vfFastBlendWeightInput": 0.60,
    "vfPeakLenMultInput": 4.0,
    "vfSignalThresholdInput": 50.0,
    "vfGateThresholdInput": 50.0,
    "confOscBullThresholdInput": 55.0,
    "confOscBearThresholdInput": 45.0,
    "confVfBullThresholdInput": 55.0,
    "confVfBearThresholdInput": 45.0,
    "confErThresholdInput": 0.30,
    "confSmoothLenInput": 3,
    "leg_threshold_pts": 10.0,
    "response_bars":     12,
    "early_bars":        4,
    "adverse_bars":      6,
    "delta_lookback":    10,
    "delta_slope_len":   5,
    "gasout_stall_bars": 3,
    "delta_flip_thresh": 0.10,
    "gasout_thresh":     0.05,
}

OBJECTIVE_METRIC = "nexus_footprint_delta_signal_quality"


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


def _manifest_path() -> Path:
    raw = os.environ.get("WARBIRD_NEXUS_EXPORT_MANIFEST")
    return Path(raw).expanduser() if raw else DEFAULT_MANIFEST_PATH


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _canonical_col(name: Any) -> str:
    col = str(name).strip().lower()
    for old, new in (
        (" ", "_"),
        ("-", "_"),
        (":", "_"),
        ("/", "_"),
        ("(", ""),
        (")", ""),
        ("%", "pct"),
        (".", "_"),
    ):
        col = col.replace(old, new)
    return "_".join(part for part in col.split("_") if part)


def _resolve_export_path(manifest: dict[str, Any], manifest_path: Path) -> Path:
    raw_path = None
    for key in EXPORT_PATH_KEYS:
        value = manifest.get(key)
        if value:
            raw_path = str(value)
            break
    if not raw_path:
        raise ValueError(
            f"Nexus export manifest {manifest_path} must include one of "
            f"{', '.join(EXPORT_PATH_KEYS)}."
        )
    export_path = Path(raw_path).expanduser()
    if not export_path.is_absolute():
        export_path = manifest_path.parent / export_path
    return export_path


def _normalize_export_frame(raw: pd.DataFrame) -> pd.DataFrame:
    frame = raw.copy()
    frame.columns = [_canonical_col(c) for c in frame.columns]
    frame = frame.loc[:, ~frame.columns.duplicated()].copy()

    rename_map = {
        "time": "ts",
        "datetime": "ts",
        "date": "ts",
        "timestamp": "ts",
        "open": "open",
        "high": "high",
        "low": "low",
        "close": "close",
        "volume": "volume",
    }
    for src, dst in rename_map.items():
        if src in frame.columns and dst not in frame.columns:
            frame = frame.rename(columns={src: dst})
    for required_col in REQUIRED_EXPORT_COLS:
        if required_col in frame.columns:
            continue
        if not required_col.startswith("nexus_"):
            continue
        matches = [
            col
            for col in frame.columns
            if col.endswith(f"_{required_col}") or col.endswith(required_col)
        ]
        if len(matches) == 1:
            frame = frame.rename(columns={matches[0]: required_col})

    missing = REQUIRED_EXPORT_COLS.difference(frame.columns)
    if missing:
        raise ValueError(
            "Nexus TradingView export is missing required Pine footprint "
            f"columns: {sorted(missing)}. Do not backfill these from OHLCV or "
            "local parquet; export the Nexus indicator with request.footprint() "
            "fields enabled."
        )

    keep_cols = [
        c
        for c in frame.columns
        if c in REQUIRED_EXPORT_COLS or c in {"symbol", "nexus_mode_minutes"}
    ]
    frame = frame.loc[:, keep_cols].copy()
    ts_raw = frame["ts"]
    if pd.api.types.is_numeric_dtype(ts_raw):
        ts_numeric = pd.to_numeric(ts_raw, errors="coerce")
        unit = "ms" if ts_numeric.dropna().median() > 1_000_000_000_000 else "s"
        frame["ts"] = pd.to_datetime(ts_numeric, unit=unit, utc=True, errors="coerce")
    else:
        ts_text = ts_raw.astype(str).str.strip()
        ts_numeric = pd.to_numeric(ts_text.str.replace(",", "", regex=False), errors="coerce")
        numeric_ratio = float(ts_numeric.notna().mean()) if len(ts_numeric) else 0.0
        if numeric_ratio >= 0.90:
            unit = "ms" if ts_numeric.dropna().median() > 1_000_000_000_000 else "s"
            frame["ts"] = pd.to_datetime(ts_numeric, unit=unit, utc=True, errors="coerce")
        else:
            frame["ts"] = pd.to_datetime(ts_raw, utc=True, errors="coerce")
    numeric_cols = [c for c in frame.columns if c not in {"ts", "symbol"}]
    for col in numeric_cols:
        frame[col] = pd.to_numeric(
            frame[col].astype(str).str.replace(",", "", regex=False),
            errors="coerce",
        )
    frame = frame.dropna(subset=["ts", "open", "high", "low", "close"]).sort_values("ts")
    frame = frame.drop_duplicates(subset=["ts"]).reset_index(drop=True)
    return frame


def _series(values: np.ndarray) -> pd.Series:
    return pd.Series(np.asarray(values, dtype=np.float64))


def _safe_div(num: Any, den: Any, fallback: float = 0.0) -> Any:
    num_arr, den_arr = np.broadcast_arrays(
        np.asarray(num, dtype=np.float64),
        np.asarray(den, dtype=np.float64),
    )
    out = np.full(num_arr.shape, float(fallback), dtype=np.float64)
    mask = np.isfinite(num_arr) & np.isfinite(den_arr) & (den_arr != 0.0)
    out[mask] = num_arr[mask] / den_arr[mask]
    return out.item() if out.ndim == 0 else out


def _ema(src: np.ndarray, length: int) -> np.ndarray:
    return _series(src).ewm(span=max(int(length), 1), adjust=False).mean().to_numpy(dtype=np.float64)


def _sma(src: np.ndarray, length: int) -> np.ndarray:
    return _series(src).rolling(max(int(length), 1), min_periods=1).mean().to_numpy(dtype=np.float64)


def _wma(src: np.ndarray, length: int) -> np.ndarray:
    length = max(int(length), 1)
    weights = np.arange(1, length + 1, dtype=np.float64)

    def _apply(window: np.ndarray) -> float:
        local_weights = weights[-len(window):]
        return float(np.dot(window, local_weights) / local_weights.sum())

    return _series(src).rolling(length, min_periods=1).apply(_apply, raw=True).to_numpy(dtype=np.float64)


def _vwma(src: np.ndarray, volume: np.ndarray, length: int) -> np.ndarray:
    length = max(int(length), 1)
    num = _series(src * volume).rolling(length, min_periods=1).sum().to_numpy(dtype=np.float64)
    den = _series(volume).rolling(length, min_periods=1).sum().to_numpy(dtype=np.float64)
    return _safe_div(num, den, 0.0)


def _u_smooth(src: np.ndarray, length: int, method: str, volume: np.ndarray) -> np.ndarray:
    length = max(int(length), 1)
    e1 = _ema(src, length)
    e2 = _ema(e1, length)
    e3 = _ema(e2, length)
    if method == "EMA":
        return e1
    if method == "SMA":
        return _sma(src, length)
    if method == "DEMA":
        return 2.0 * e1 - e2
    if method == "TEMA":
        return 3.0 * e1 - 3.0 * e2 + e3
    if method == "WMA":
        return _wma(src, length)
    if method == "VWMA":
        return _vwma(src, volume, length)
    return e1


def _rolling_high(src: np.ndarray, length: int) -> np.ndarray:
    return _series(src).rolling(max(int(length), 1), min_periods=1).max().to_numpy(dtype=np.float64)


def _rolling_low(src: np.ndarray, length: int) -> np.ndarray:
    return _series(src).rolling(max(int(length), 1), min_periods=1).min().to_numpy(dtype=np.float64)


def _atr(high: np.ndarray, low: np.ndarray, close: np.ndarray, length: int) -> np.ndarray:
    prev_close = np.roll(close, 1)
    prev_close[0] = close[0]
    tr = np.maximum(high - low, np.maximum(np.abs(high - prev_close), np.abs(low - prev_close)))
    return _series(tr).ewm(alpha=1.0 / max(int(length), 1), adjust=False).mean().to_numpy(dtype=np.float64)


def _calc_er(src: np.ndarray, length: int) -> np.ndarray:
    length = max(int(length), 1)
    shifted = np.roll(src, length)
    shifted[:length] = src[0]
    direction = np.abs(src - shifted)
    volatility = _series(np.abs(np.diff(src, prepend=src[0]))).rolling(length, min_periods=1).sum().to_numpy(dtype=np.float64)
    return _safe_div(direction, volatility, 0.0)


def _cumulative_delta(bar_delta: np.ndarray, lookback: float) -> np.ndarray:
    lb = max(int(lookback), 1)
    return _series(bar_delta).rolling(lb, min_periods=1).sum().to_numpy(dtype=np.float64)


def _delta_slope(cumulative_delta: np.ndarray, slope_len: float) -> np.ndarray:
    sl = max(int(slope_len), 1)
    shifted = np.roll(cumulative_delta, sl)
    shifted[:sl] = cumulative_delta[0]
    return cumulative_delta - shifted


def _resolve_source(frame: pd.DataFrame, source_input: str) -> np.ndarray:
    close = frame["close"].to_numpy(dtype=np.float64)
    high = frame["high"].to_numpy(dtype=np.float64)
    low = frame["low"].to_numpy(dtype=np.float64)
    open_ = frame["open"].to_numpy(dtype=np.float64)
    if source_input == "open":
        return open_
    if source_input == "high":
        return high
    if source_input == "low":
        return low
    if source_input == "hl2":
        return (high + low) / 2.0
    if source_input == "hlc3":
        return (high + low + close) / 3.0
    if source_input == "ohlc4":
        return (open_ + high + low + close) / 4.0
    if source_input == "hlcc4":
        return (high + low + close + close) / 4.0
    return close


def _effective_length(params: dict[str, Any]) -> int:
    preset = str(params.get("presetInput", "Default"))
    if preset == "Scalping":
        return 8
    if preset == "Swing":
        return 21
    if preset == "Position":
        return 34
    return max(_safe_int(params.get("lengthInput"), 18), 2)


def _effective_zones(params: dict[str, Any]) -> tuple[float, float]:
    preset = str(params.get("presetInput", "Default"))
    if preset == "Scalping":
        return 75.0, 25.0
    if preset == "Swing":
        return 80.0, 20.0
    if preset == "Position":
        return 85.0, 15.0
    return _safe_float(params.get("obInput"), 75.0), _safe_float(params.get("osInput"), 25.0)


def _compute_core(frame: pd.DataFrame, params: dict[str, Any]) -> dict[str, np.ndarray]:
    eff_len = _effective_length(params)
    sig_len = max(_safe_int(params.get("sigLenInput"), 6), 1)
    source = _resolve_source(frame, str(params.get("sourceInput", "close")))
    smooth_type = str(params.get("smoothTypeInput", "DEMA"))
    sig_type = str(params.get("sigTypeInput", "EMA"))
    vf_delta_weight = float(np.clip(_safe_float(params.get("vfBodyWeightInput"), 0.70), 0.0, 1.0))
    vf_fast_len_mult = max(_safe_float(params.get("vfFastLenMultInput"), 0.60), 0.10)
    vf_slow_len_mult = max(_safe_float(params.get("vfSlowLenMultInput"), 1.40), 0.10)
    vf_fast_blend_weight = float(np.clip(_safe_float(params.get("vfFastBlendWeightInput"), 0.60), 0.0, 1.0))
    vf_peak_len_mult = max(_safe_float(params.get("vfPeakLenMultInput"), 4.0), 1.0)

    open_ = frame["open"].to_numpy(dtype=np.float64)
    high = frame["high"].to_numpy(dtype=np.float64)
    low = frame["low"].to_numpy(dtype=np.float64)
    close = frame["close"].to_numpy(dtype=np.float64)
    volume = np.nan_to_num(frame["volume"].to_numpy(dtype=np.float64), nan=0.0)
    fp_available = frame["nexus_fp_available"].to_numpy(dtype=np.float64) > 0.0
    fp_bar_delta = np.nan_to_num(frame["nexus_fp_bar_delta"].to_numpy(dtype=np.float64), nan=0.0)
    fp_total_volume = np.nan_to_num(frame["nexus_fp_total_volume"].to_numpy(dtype=np.float64), nan=0.0)
    volume_available = fp_available & np.isfinite(fp_bar_delta) & (fp_total_volume > 0.0)
    bar_volume = np.where(volume_available, fp_total_volume, 0.0)

    shifted = np.roll(source, eff_len)
    shifted[:eff_len] = np.nan
    roc = _safe_div(source - shifted, shifted, 0.0) * 100.0
    roc_smoothed = np.nan_to_num(_u_smooth(roc, eff_len, smooth_type, volume), nan=0.0)
    roc_high = np.nan_to_num(_rolling_high(roc_smoothed, eff_len * 3), nan=roc_smoothed)
    roc_low = np.nan_to_num(_rolling_low(roc_smoothed, eff_len * 3), nan=roc_smoothed)
    nroc = np.nan_to_num(_safe_div(roc_smoothed - roc_low, roc_high - roc_low, 0.5) * 100.0, nan=50.0)

    er = np.nan_to_num(_calc_er(source, eff_len), nan=0.0)
    atr_eff = np.nan_to_num(_atr(high, low, close, eff_len), nan=MINTICK)
    atr14 = np.nan_to_num(_atr(high, low, close, 14), nan=MINTICK)
    impulse_raw = np.diff(source, prepend=source[0])
    impulse_abs = np.where(atr_eff > 0.0, atr_eff, np.abs(impulse_raw) + 0.0001)
    normalized_impulse = _safe_div(impulse_raw, impulse_abs, 0.0) * er
    ewi_smoothed = np.nan_to_num(_u_smooth(normalized_impulse, eff_len, smooth_type, volume), nan=0.0)
    ewi_high = np.nan_to_num(_rolling_high(ewi_smoothed, eff_len * 4), nan=ewi_smoothed)
    ewi_low = np.nan_to_num(_rolling_low(ewi_smoothed, eff_len * 4), nan=ewi_smoothed)
    ewi = np.nan_to_num(_safe_div(ewi_smoothed - ewi_low, ewi_high - ewi_low, 0.5) * 100.0, nan=50.0)

    stoch_high = np.nan_to_num(_rolling_high(source, eff_len), nan=source)
    stoch_low = np.nan_to_num(_rolling_low(source, eff_len), nan=source)
    stoch_raw = _safe_div(source - stoch_low, stoch_high - stoch_low, 0.5) * 100.0
    smp_len = max(eff_len // 2, 2)
    smp = np.nan_to_num(_u_smooth(stoch_raw, smp_len, "EMA", volume), nan=50.0)

    er_smoothed = np.nan_to_num(_u_smooth(er, eff_len, "EMA", volume), nan=0.3)
    trend_weight = np.minimum(er_smoothed * 1.5, 0.75)
    range_weight = 1.0 - trend_weight
    osc_smooth_len = max(eff_len // 3, 2)
    osc_raw = trend_weight * (nroc * 0.55 + ewi * 0.45) + range_weight * smp
    osc = np.clip(np.nan_to_num(_u_smooth(osc_raw, osc_smooth_len, smooth_type, volume), nan=50.0), 0.0, 100.0)
    sig = np.nan_to_num(_u_smooth(osc, sig_len, sig_type, volume), nan=50.0)

    delta_lb = max(_safe_int(params.get("delta_lookback"), 10), 1)
    rolling_delta_mean = _cumulative_delta(fp_bar_delta, delta_lb) / float(delta_lb)
    signed_vol = np.where(
        volume_available,
        fp_bar_delta * vf_delta_weight + rolling_delta_mean * (1.0 - vf_delta_weight),
        0.0,
    )
    avg_vol = _sma(bar_volume, eff_len * 2)
    vnvf_raw = np.where(
        volume_available,
        _safe_div(signed_vol, np.maximum(atr_eff, MINTICK) * np.maximum(avg_vol, 1.0), 0.0),
        0.0,
    )
    vnvf_fast = _ema(vnvf_raw, max(int(round(eff_len * vf_fast_len_mult)), 2))
    vnvf_slow = _ema(vnvf_raw, max(int(round(eff_len * vf_slow_len_mult)), 3))
    vnvf_blend = vnvf_fast * vf_fast_blend_weight + vnvf_slow * (1.0 - vf_fast_blend_weight)
    vnvf_peak = np.maximum(_rolling_high(np.abs(vnvf_blend), max(int(round(eff_len * vf_peak_len_mult)), 1)), 0.0001)
    vf_raw = np.clip(_safe_div(vnvf_blend, vnvf_peak, 0.0) * 50.0 + 50.0, 0.0, 100.0)
    vf = np.where(volume_available, vf_raw, 50.0)

    return {
        "open": open_,
        "high": high,
        "low": low,
        "close": close,
        "volume": volume,
        "fp_bar_delta": fp_bar_delta,
        "fp_total_volume": fp_total_volume,
        "volume_available": volume_available,
        "atr_eff": np.maximum(atr_eff, MINTICK),
        "atr14": np.maximum(atr14, MINTICK),
        "er_smoothed": er_smoothed,
        "osc": osc,
        "sig": sig,
        "vf": vf,
        "eff_len": np.full(len(frame), eff_len, dtype=np.int64),
    }


def _compute_knn(
    osc: np.ndarray,
    sig: np.ndarray,
    vf: np.ndarray,
    er_smoothed: np.ndarray,
    close: np.ndarray,
    atr14: np.ndarray,
    warmup_mask: np.ndarray,
    k_neighbors: int,
    training_window: int,
    bull_threshold: float,
    bear_threshold: float,
    atr_label_threshold: float,
    recency_boost: float,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    feat1 = osc / 100.0
    feat2 = vf / 100.0
    feat3 = np.clip((osc - sig + 50.0) / 100.0, 0.0, 1.0)
    feat4 = np.clip(er_smoothed, 0.0, 1.0)

    knn_val = np.full(len(close), 50.0, dtype=np.float64)
    kf1: list[float] = []
    kf2: list[float] = []
    kf3: list[float] = []
    kf4: list[float] = []
    ky: list[int] = []
    k_label = 0

    for i in range(len(close)):
        if i == 0:
            outcome = 0
        else:
            if close[i] > close[i - 1] + atr14[i] * atr_label_threshold:
                outcome = 1
            elif close[i] < close[i - 1] - atr14[i] * atr_label_threshold:
                outcome = 0
            else:
                outcome = k_label
        k_label = outcome

        if i > 2 and warmup_mask[i]:
            kf1.append(float(feat1[i - 1]))
            kf2.append(float(feat2[i - 1]))
            kf3.append(float(feat3[i - 1]))
            kf4.append(float(feat4[i - 1]))
            ky.append(int(outcome))
            if len(kf1) > training_window:
                kf1.pop(0)
                kf2.pop(0)
                kf3.pop(0)
                kf4.pop(0)
                ky.pop(0)

        k_size = len(kf1)
        if k_size < k_neighbors:
            continue

        distances = np.empty(k_size, dtype=np.float64)
        for j in range(k_size):
            d = (
                abs(feat1[i] - kf1[j])
                + abs(feat2[i] - kf2[j])
                + abs(feat3[i] - kf3[j])
                + abs(feat4[i] - kf4[j])
            )
            recency_bonus = 1.0 + (j / float(k_size)) * recency_boost
            distances[j] = d / recency_bonus

        order = np.argsort(distances)[:k_neighbors]
        weights = 1.0 / (distances[order] + 0.001)
        labels = np.asarray([ky[idx] for idx in order], dtype=np.float64)
        bull_votes = float(np.sum(weights * labels))
        total_weight = float(np.sum(weights))
        knn_val[i] = _safe_float(_safe_div(bull_votes, total_weight, 0.5), 0.5) * 100.0

    knn_bull = knn_val >= bull_threshold
    knn_bear = knn_val <= bear_threshold
    return knn_val, knn_bull, knn_bear


def _compute_features(frame: pd.DataFrame, params: dict[str, Any]) -> pd.DataFrame:
    core = _compute_core(frame, params)
    osc = core["osc"]
    sig = core["sig"]
    vf = core["vf"]
    volume_available = core["volume_available"]
    er_smoothed = core["er_smoothed"]
    atr = core["atr_eff"]
    atr14 = core["atr14"]

    eff_len = _effective_length(params)
    ob_level, os_level = _effective_zones(params)
    fatigue_bars = max(_safe_int(params.get("fatigueBarsInput"), 2), 1)
    warmup_bars = max(eff_len * 3, 60)
    warmup_mask = np.arange(len(frame), dtype=np.int64) >= warmup_bars

    knn_k = max(_safe_int(params.get("knnKInput"), 7), 3)
    knn_window = max(_safe_int(params.get("knnWindowInput"), 180), 50)
    knn_bull_threshold = _safe_float(params.get("knnBullThresholdInput"), 58.0)
    knn_bear_threshold = _safe_float(params.get("knnBearThresholdInput"), 42.0)
    knn_atr_label_threshold = max(_safe_float(params.get("knnAtrLabelThresholdInput"), 0.15), 0.0)
    knn_recency_boost = max(_safe_float(params.get("knnRecencyBoostInput"), 0.10), 0.0)
    knn_val, knn_bull, knn_bear = _compute_knn(
        osc=osc,
        sig=sig,
        vf=vf,
        er_smoothed=er_smoothed,
        close=core["close"],
        atr14=atr14,
        warmup_mask=warmup_mask,
        k_neighbors=knn_k,
        training_window=knn_window,
        bull_threshold=knn_bull_threshold,
        bear_threshold=knn_bear_threshold,
        atr_label_threshold=knn_atr_label_threshold,
        recency_boost=knn_recency_boost,
    )

    conf_osc_bull_threshold = _safe_float(params.get("confOscBullThresholdInput"), 55.0)
    conf_osc_bear_threshold = _safe_float(params.get("confOscBearThresholdInput"), 45.0)
    conf_vf_bull_threshold = _safe_float(params.get("confVfBullThresholdInput"), 55.0)
    conf_vf_bear_threshold = _safe_float(params.get("confVfBearThresholdInput"), 45.0)
    conf_er_threshold = _safe_float(params.get("confErThresholdInput"), 0.30)
    conf_smooth_len = max(_safe_int(params.get("confSmoothLenInput"), 3), 1)
    vf_signal_threshold = _safe_float(params.get("vfSignalThresholdInput"), 50.0)
    vf_signal_bear_threshold = 100.0 - vf_signal_threshold

    er_trending = er_smoothed > conf_er_threshold
    conf_bull = np.zeros(len(frame), dtype=np.int64)
    conf_bear = np.zeros(len(frame), dtype=np.int64)
    conf_bull += (osc > conf_osc_bull_threshold).astype(np.int64)
    conf_bear += (osc < conf_osc_bear_threshold).astype(np.int64)
    conf_bull += (osc > sig).astype(np.int64)
    conf_bear += (osc < sig).astype(np.int64)
    conf_bull += ((vf > conf_vf_bull_threshold) & volume_available).astype(np.int64)
    conf_bear += ((vf < conf_vf_bear_threshold) & volume_available).astype(np.int64)
    conf_bull += (er_trending & (osc > 50.0)).astype(np.int64)
    conf_bear += (er_trending & (osc < 50.0)).astype(np.int64)
    conf_bull += knn_bull.astype(np.int64)
    conf_bear += knn_bear.astype(np.int64)
    conf_net = conf_bull - conf_bear
    conf_sources = np.where(volume_available, 5.0, 4.0)
    conf_raw = (conf_net + conf_sources) / (conf_sources * 2.0) * 100.0
    conf = np.clip(_ema(conf_raw, conf_smooth_len), 0.0, 100.0)

    prev_osc = np.roll(osc, 1)
    prev_sig = np.roll(sig, 1)
    prev_vf = np.roll(vf, 1)
    prev_osc[0] = osc[0]
    prev_sig[0] = sig[0]
    prev_vf[0] = vf[0]
    cross_up = (osc > sig) & (prev_osc <= prev_sig) & warmup_mask
    cross_down = (osc < sig) & (prev_osc >= prev_sig) & warmup_mask
    exit_os = (osc > os_level) & (prev_osc <= os_level) & warmup_mask
    exit_ob = (osc < ob_level) & (prev_osc >= ob_level) & warmup_mask
    vf_in = (vf > vf_signal_threshold) & (prev_vf <= vf_signal_threshold) & warmup_mask & volume_available
    vf_out = (vf < vf_signal_bear_threshold) & (prev_vf >= vf_signal_bear_threshold) & warmup_mask & volume_available

    fatigue_ob_weak = (osc >= ob_level) & (osc < prev_osc)
    fatigue_os_str = (osc <= os_level) & (osc > prev_osc)
    fat_ob_count = np.zeros(len(frame), dtype=np.int64)
    fat_os_count = np.zeros(len(frame), dtype=np.int64)
    for i in range(len(frame)):
        if fatigue_ob_weak[i]:
            fat_ob_count[i] = (fat_ob_count[i - 1] if i > 0 else 0) + 1
        if fatigue_os_str[i]:
            fat_os_count[i] = (fat_os_count[i - 1] if i > 0 else 0) + 1
    fat_ob_signal = (fat_ob_count == fatigue_bars) & warmup_mask
    fat_os_signal = (fat_os_count == fatigue_bars) & warmup_mask

    # ── Real footprint cumulative delta from exported Pine fields ───────────
    _delta_lb = max(int(params.get("delta_lookback", 10)), 1)
    _slope_len = max(int(params.get("delta_slope_len", 5)), 1)
    _flip_th = float(params.get("delta_flip_thresh", 0.10))
    _gasout_th = float(params.get("gasout_thresh", 0.05))

    bar_dlt = np.nan_to_num(core["fp_bar_delta"], nan=0.0)
    fp_total_volume = np.nan_to_num(core["fp_total_volume"], nan=0.0)
    fp_valid = volume_available & (fp_total_volume > 0.0)
    cum_dlt = _cumulative_delta(bar_dlt, _delta_lb)
    avg_vol_d = _series(fp_total_volume).rolling(_delta_lb, min_periods=1).mean().to_numpy(dtype=np.float64)
    norm_cum = np.clip(_safe_div(cum_dlt, np.maximum(avg_vol_d * _delta_lb, 1.0), 0.0), -1.0, 1.0)
    dlt_slope = _delta_slope(norm_cum, _slope_len)
    bar_ratio = np.clip(_safe_div(bar_dlt, np.maximum(fp_total_volume, 1.0), 0.0), -1.0, 1.0)
    price_pos  = _safe_div(
        core["close"] - core["low"],
        np.maximum(core["high"] - core["low"], 1e-9),
        0.5,
    )
    delta_dir = np.where(
        fp_valid & (norm_cum > _flip_th),
        1,
        np.where(fp_valid & (norm_cum < -_flip_th), -1, 0),
    ).astype(np.int8)
    gasout_bull = fp_valid & (norm_cum > 0.0) & (dlt_slope < -_gasout_th)
    gasout_bear = fp_valid & (norm_cum < 0.0) & (dlt_slope > _gasout_th)

    return pd.DataFrame(
        {
            "ts": pd.to_datetime(frame["ts"], utc=True),
            "open": core["open"],
            "high": core["high"],
            "low": core["low"],
            "close": core["close"],
            "volume": core["volume"],
            "volume_available": volume_available,
            "atr": atr,
            "osc": osc,
            "sig": sig,
            "vf": vf,
            "er": er_smoothed,
            "conf": conf,
            "knn_val": knn_val,
            "knn_bull": knn_bull,
            "knn_bear": knn_bear,
            "is_warmed_up": warmup_mask,
            "cross_up": cross_up,
            "cross_down": cross_down,
            "exit_os": exit_os,
            "exit_ob": exit_ob,
            "vf_in": vf_in,
            "vf_out": vf_out,
            "fat_ob_signal": fat_ob_signal,
            "fat_os_signal": fat_os_signal,
            "norm_cum_delta": norm_cum,
            "delta_slope":    dlt_slope,
            "bar_delta_ratio": bar_ratio,
            "price_position": price_pos,
            "delta_dir":      delta_dir,
            "gasout_bull":    gasout_bull,
            "gasout_bear":    gasout_bear,
        }
    )


def _bounded(value: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, float(value)))


def _presence_score(count: int, target: float) -> float:
    return _bounded(count / max(target, 1.0))


def _rate_band_score(rate: float, low: float, high: float, hard_high: float) -> float:
    if rate <= 0.0:
        return 0.0
    if rate < low:
        return _bounded(rate / low)
    if rate <= high:
        return 1.0
    return _bounded(1.0 - (rate - high) / max(hard_high - high, 1e-9))


def _score_directional_events(
    signal_direction: np.ndarray,
    high: np.ndarray,
    low: np.ndarray,
    close: np.ndarray,
    atr: np.ndarray,
    horizon_bars: int = 5,
    fast_bars: int = 3,
    favorable_atr: float = 0.75,
    adverse_atr: float = 0.75,
) -> dict[str, float]:
    horizon_bars = max(int(horizon_bars), 1)
    fast_bars = max(1, min(int(fast_bars), horizon_bars))
    count = 0
    good = 0
    favorable_hits = 0
    fast_hits = 0
    adverse_first = 0
    forward_atr_returns: list[float] = []
    favorable_offsets: list[int] = []

    for i in range(len(signal_direction) - 1):
        direction = int(signal_direction[i])
        if direction == 0:
            continue

        count += 1
        anchor = float(close[i])
        risk = max(float(atr[i]), MINTICK)
        favorable = anchor + direction * favorable_atr * risk
        adverse = anchor - direction * adverse_atr * risk
        end = min(i + horizon_bars, len(signal_direction) - 1)
        success: bool | None = None

        for j in range(i + 1, end + 1):
            if direction == 1:
                if low[j] <= adverse:
                    adverse_first += 1
                    success = False
                    break
                if high[j] >= favorable:
                    offset = j - i
                    favorable_hits += 1
                    favorable_offsets.append(offset)
                    if offset <= fast_bars:
                        fast_hits += 1
                    success = True
                    break
            else:
                if high[j] >= adverse:
                    adverse_first += 1
                    success = False
                    break
                if low[j] <= favorable:
                    offset = j - i
                    favorable_hits += 1
                    favorable_offsets.append(offset)
                    if offset <= fast_bars:
                        fast_hits += 1
                    success = True
                    break

        forward_atr_return = direction * (float(close[end]) - anchor) / risk
        forward_atr_returns.append(forward_atr_return)
        if success is None:
            success = forward_atr_return > 0.0
        if success:
            good += 1

    precision = good / count if count else 0.0
    fast_hit_rate = fast_hits / count if count else 0.0
    mean_forward_atr = float(np.mean(forward_atr_returns)) if forward_atr_returns else 0.0
    avg_favorable_bars = float(np.mean(favorable_offsets)) if favorable_offsets else 0.0
    edge_score = _bounded(0.5 + 0.5 * np.tanh(mean_forward_atr / 0.75))
    quality = _bounded(0.55 * precision + 0.25 * fast_hit_rate + 0.20 * edge_score)
    return {
        "count": float(count),
        "precision": float(precision),
        "mean_forward_atr": mean_forward_atr,
        "favorable_hit_rate": favorable_hits / count if count else 0.0,
        "fast_hit_rate": fast_hit_rate,
        "avg_favorable_bars": avg_favorable_bars,
        "adverse_first_rate": adverse_first / count if count else 0.0,
        "horizon_bars": float(horizon_bars),
        "fast_bars": float(fast_bars),
        "quality": quality,
    }


def _state_entries(state_direction: np.ndarray) -> np.ndarray:
    previous = np.roll(state_direction, 1)
    previous[0] = 0
    entries = np.zeros(len(state_direction), dtype=np.int8)
    mask = (state_direction != 0) & (state_direction != previous)
    entries[mask] = state_direction[mask]
    return entries


def _label_setups(
    close: np.ndarray,
    signal_mask: np.ndarray,
    direction: int,
    leg_threshold_pts: float,
    response_bars: int,
    adverse_bars: int,
) -> tuple[np.ndarray, np.ndarray]:
    """
    Returns (success_mask, failure_mask).
    SUCCESS: price moves leg_threshold_pts in direction within response_bars.
    FAILURE: adverse move happened first OR threshold not reached.

    Inner j-loop replaced with vectorized NumPy window slice + np.argmax.
    Outer loop over signal_indices is retained (typically ~1k-3k items/run).
    """
    n = len(close)
    r_bars = max(int(response_bars), 1)
    adv_bars = max(int(adverse_bars), 1)
    signal_indices = np.where(signal_mask)[0]
    success = np.zeros(n, dtype=bool)
    failure = np.zeros(n, dtype=bool)
    if len(signal_indices) == 0:
        return success, failure

    # Pad close so window slices never exceed array bounds.
    pad = r_bars + 1
    close_padded = np.concatenate([close, np.full(pad, close[-1])])

    for i in signal_indices:
        if i + 1 >= n:
            failure[i] = True
            continue
        entry = close_padded[i]
        # Vectorized moves for the full response window.
        window_len = min(r_bars, n - i - 1)
        moves = (close_padded[i + 1 : i + 1 + window_len] - entry) * direction

        # Adverse check: first bar where move <= -0.5 * leg_threshold_pts
        # within the adverse window.
        adv_len = min(adv_bars, window_len)
        adv_hits = moves[:adv_len] <= -leg_threshold_pts * 0.5
        if adv_hits.any():
            adv_bar = int(np.argmax(adv_hits))  # index of first adverse hit
            # Success only if threshold was crossed before the adverse bar.
            if adv_bar > 0 and moves[:adv_bar].max() >= leg_threshold_pts:
                success[i] = True
            else:
                failure[i] = True
        elif moves.max() >= leg_threshold_pts:
            success[i] = True
        else:
            failure[i] = True
    return success, failure


def _empty_quality_result() -> dict[str, Any]:
    return {
        "trades": 0,
        "total_signals": 0,
        "composite_score": 0.0,
        "reversal_precision": 0.0,
        "early_entry_quality": 0.0,
        "gasout_accuracy": 0.5,
        "false_avoidance": 0.0,
        "signal_rate_score": 0.0,
        "signals_per_day": 0.0,
        "leg_threshold_pts": 10.0,
        "win_rate": 0.0,
        "pf": 0.0,
        "gross_profit": 0.0,
        "gross_loss": 1.0,
        "max_dd_abs": 1.0,
    }


def objective_score(result: dict[str, Any]) -> float:
    total_signals = _safe_int(result.get("total_signals"), 0)
    if total_signals < 5:
        return 0.0
    return _bounded(_safe_float(result.get("composite_score"), 0.0))


def load_data() -> pd.DataFrame:
    manifest_path = _manifest_path()
    if not manifest_path.exists():
        raise FileNotFoundError(
            f"Nexus Pine export manifest not found: {manifest_path}. "
            f"Export {NEXUS_PINE_FILE} from TradingView with the hidden "
            "nexus_fp_* plots, save the CSV, and write a manifest for trigger "
            f"family {NEXUS_TRIGGER_FAMILY}. Set WARBIRD_NEXUS_EXPORT_MANIFEST "
            "to override the manifest path."
        )

    manifest = json.loads(manifest_path.read_text())
    trigger_family = str(manifest.get("trigger_family", "")).strip()
    if trigger_family != NEXUS_TRIGGER_FAMILY:
        raise ValueError(
            f"Nexus manifest {manifest_path} trigger_family must be "
            f"{NEXUS_TRIGGER_FAMILY!r}; got {trigger_family!r}."
        )

    indicator_file = str(manifest.get("indicator_file", "")).strip()
    if indicator_file and indicator_file != NEXUS_PINE_FILE:
        raise ValueError(
            f"Nexus manifest indicator_file must reference {NEXUS_PINE_FILE}; "
            f"got {indicator_file!r}."
        )

    export_path = _resolve_export_path(manifest, manifest_path)
    if not export_path.exists():
        raise FileNotFoundError(f"Nexus TradingView export CSV not found: {export_path}")

    expected_hash = manifest.get("export_hash") or manifest.get("sha256") or manifest.get("csv_sha256")
    actual_hash = _sha256_file(export_path)
    if expected_hash and str(expected_hash).lower() != actual_hash.lower():
        raise ValueError(
            f"Nexus export hash mismatch for {export_path}: manifest={expected_hash} "
            f"actual={actual_hash}"
        )

    raw = pd.read_csv(export_path)
    df = _normalize_export_frame(raw)
    manifest_row_count = manifest.get("row_count")
    if manifest_row_count is not None and _safe_int(manifest_row_count, -1) != len(df):
        raise ValueError(
            f"Nexus manifest row_count={manifest_row_count} does not match "
            f"normalized export rows={len(df)}."
        )

    df = df.loc[df["nexus_fp_available"].fillna(0.0) > 0.0].reset_index(drop=True)
    df = df.loc[df["nexus_fp_total_volume"].fillna(0.0) > 0.0].reset_index(drop=True)
    if df.empty:
        raise ValueError(
            "Nexus export contains no rows with available real footprint volume. "
            "Do not run Optuna from OHLCV-only rows."
        )

    if "symbol" not in df.columns:
        df["symbol"] = str(manifest.get("symbol", "MES1!"))

    df.attrs["warbird_manifest"] = {
        "manifest_path": str(manifest_path),
        "export_path": str(export_path),
        "export_hash": actual_hash,
        "trigger_family": NEXUS_TRIGGER_FAMILY,
        "indicator_file": NEXUS_PINE_FILE,
        "symbol": manifest.get("symbol"),
        "timeframe": manifest.get("timeframe"),
        "row_count": len(df),
    }
    return df


def run_backtest(df: pd.DataFrame, params: dict[str, Any], start_date: str) -> dict[str, Any]:
    start_ts = pd.Timestamp(start_date)
    start_ts = start_ts.tz_localize("UTC") if start_ts.tzinfo is None else start_ts.tz_convert("UTC")

    frame = df.loc[pd.to_datetime(df["ts"], utc=True) >= start_ts].copy()
    if frame.empty:
        return _empty_quality_result()

    feat = _compute_features(frame, params).reset_index(drop=True)

    # ── Signal construction (same gates as before) ─────────────────────────
    use_conf = bool(params.get("useConfluenceGate", True))
    use_vf   = bool(params.get("useVolumeFlowGate", True))
    use_zone_exit = bool(params.get("useZoneExitSignals", False))
    use_knn  = bool(params.get("useKnnGate", True))

    conf_high = _safe_float(params.get("confHighInput"), 65.0)
    conf_low  = _safe_float(params.get("confLowInput"), 35.0)
    vf_gate_threshold = _safe_float(params.get("vfGateThresholdInput"), 50.0)
    vf_gate_bear_threshold = 100.0 - vf_gate_threshold

    osc = feat["osc"].to_numpy(dtype=np.float64)
    prev_osc = np.roll(osc, 1)
    prev_osc[0] = osc[0]
    cross_up = feat["cross_up"].to_numpy(dtype=bool)
    cross_down = feat["cross_down"].to_numpy(dtype=bool)

    primary_long  = cross_up  & ((osc < 50.0) | (prev_osc < 50.0))
    primary_short = cross_down & ((osc > 50.0) | (prev_osc > 50.0))
    long_signal  = primary_long.copy()
    short_signal = primary_short.copy()
    if use_zone_exit:
        long_signal  |= feat["exit_os"].to_numpy(dtype=bool)
        short_signal |= feat["exit_ob"].to_numpy(dtype=bool)

    conf_arr = feat["conf"].to_numpy(dtype=np.float64)
    vf_arr   = feat["vf"].to_numpy(dtype=np.float64)
    if use_conf:
        long_signal  &= conf_arr >= conf_high
        short_signal &= conf_arr <= conf_low
    if use_vf:
        long_signal  &= vf_arr >= vf_gate_threshold
        short_signal &= vf_arr <= vf_gate_bear_threshold
    if use_knn:
        long_signal  &= feat["knn_bull"].to_numpy(dtype=bool)
        short_signal &= feat["knn_bear"].to_numpy(dtype=bool)

    warmup_mask = feat["is_warmed_up"].to_numpy(dtype=bool)

    # ── Delta gates (new) ─────────────────────────────────────────────────
    delta_dir = feat["delta_dir"].to_numpy(dtype=np.int8)
    long_signal  &= warmup_mask & (delta_dir == 1)
    short_signal &= warmup_mask & (delta_dir == -1)

    close = feat["close"].to_numpy(dtype=np.float64)

    # ── Label setups ──────────────────────────────────────────────────────
    leg_pts    = float(params.get("leg_threshold_pts", 10.0))
    r_bars     = max(int(params.get("response_bars", 12)), 1)
    early      = max(int(params.get("early_bars", 4)), 1)
    adv_bars   = max(int(params.get("adverse_bars", 6)), 1)

    bull_succ, bull_fail = _label_setups(close, long_signal,  +1, leg_pts, r_bars, adv_bars)
    bear_succ, bear_fail = _label_setups(close, short_signal, -1, leg_pts, r_bars, adv_bars)

    total_signals = int(long_signal.sum() + short_signal.sum())
    if total_signals < 5:
        return _empty_quality_result()

    # ── Reversal precision (0.40 weight) ──────────────────────────────────
    total_succ = int(bull_succ.sum() + bear_succ.sum())
    reversal_precision = total_succ / total_signals

    # ── Early entry quality (0.25 weight) ─────────────────────────────────
    early_hits  = 0
    early_total = int(bull_succ.sum() + bear_succ.sum())
    if early_total > 0:
        # Pad close once; reuse for both directions.
        _pad = early + 1
        close_padded_eq = np.concatenate([close, np.full(_pad, close[-1])])
        for direction, succ_mask in [(+1, bull_succ), (-1, bear_succ)]:
            for i in np.where(succ_mask)[0]:
                window_len = min(early, len(close) - i - 1)
                if window_len < 1:
                    continue
                moves = (close_padded_eq[i + 1 : i + 1 + window_len] - close_padded_eq[i]) * direction
                if moves.max() >= leg_pts * 0.5:
                    early_hits += 1
        early_entry_quality = early_hits / early_total
    else:
        early_entry_quality = 0.0

    # ── Gassing out accuracy (0.15 weight) ────────────────────────────────
    gasout_bull = feat["gasout_bull"].to_numpy(dtype=bool)
    gasout_bear = feat["gasout_bear"].to_numpy(dtype=bool)
    gasout_stall = max(int(params.get("gasout_stall_bars", 3)), 1)
    gasout_mask  = (gasout_bull | gasout_bear) & warmup_mask
    n_gasout = int(gasout_mask.sum())
    if n_gasout > 0:
        gasout_correct = 0
        for i in np.where(gasout_mask)[0]:
            direction = +1 if gasout_bull[i] else -1
            entry = close[i]
            stalled = True
            for j in range(1, min(gasout_stall + 1, len(close) - i)):
                move = (close[i + j] - entry) * direction
                if move >= leg_pts:
                    stalled = False
                    break
            if stalled:
                gasout_correct += 1
        gasout_accuracy = gasout_correct / n_gasout
    else:
        gasout_accuracy = 0.5

    # ── False continuation avoidance (0.10 weight) ────────────────────────
    false_avoidance = 1.0 - (int(bull_fail.sum()) + int(bear_fail.sum())) / total_signals

    # ── Signal rate in target band 4–10/day on 5m (0.10 weight) ──────────
    ts_chicago      = feat["ts"].dt.tz_convert("America/Chicago")
    day_count       = max(int(ts_chicago.dt.date.nunique()), 1)
    signals_per_day = total_signals / day_count
    target_lo, target_hi = 4.0, 10.0
    if target_lo <= signals_per_day <= target_hi:
        signal_rate_score = 1.0
    elif signals_per_day < target_lo:
        signal_rate_score = max(0.0, signals_per_day / target_lo)
    else:
        signal_rate_score = max(0.0, 1.0 - (signals_per_day - target_hi) / target_hi)

    # ── Composite ─────────────────────────────────────────────────────────
    composite = _bounded(
        0.40 * reversal_precision
        + 0.25 * early_entry_quality
        + 0.15 * gasout_accuracy
        + 0.10 * false_avoidance
        + 0.10 * signal_rate_score
    )

    return {
        "trades":              total_signals,
        "total_signals":       total_signals,
        "composite_score":     composite,
        "reversal_precision":  reversal_precision,
        "early_entry_quality": early_entry_quality,
        "gasout_accuracy":     gasout_accuracy,
        "false_avoidance":     false_avoidance,
        "signal_rate_score":   signal_rate_score,
        "signals_per_day":     signals_per_day,
        "leg_threshold_pts":   leg_pts,
        # Runner-required aliases
        "win_rate":            reversal_precision,
        "pf":                  _bounded(reversal_precision / max(1.0 - reversal_precision, 0.001), 0.0, 99.0),
        "gross_profit":        composite,
        "gross_loss":          max(1.0 - composite, 0.0),
        "max_dd_abs":          max(1.0 - false_avoidance, 0.0),
    }
