#!/usr/bin/env python3
"""Optuna profile for Warbird Nexus Machine Learning RSI.

Guide-driven tuning surface for the user's actual workflow on MES 5m:
- primary signals are oscillator/signal crosses on the correct side of the midline
- confirmations come from volume flow, KNN, and confluence
- fatigue is a first-class weakening/reversal warning

This is still a research harness over MES 5m OHLCV, not a claim of exact
TradingView parity for every visual or alert-only subsystem.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


MINTICK = 0.25
DATA_PATH = REPO_ROOT / "data" / "mes_5m.parquet"
SOURCE_1M_PATH = REPO_ROOT / "data" / "mes_1m.parquet"
SIGNAL_HORIZON_BARS = 12


BOOL_PARAMS: list[str] = [
    "useConfluenceGate",
    "useVolumeFlowGate",
    "useZoneExitSignals",
    "useKnnGate",
]

NUMERIC_RANGES: dict[str, tuple[float, float]] = {
    "lengthInput": (8.0, 34.0),
    "sigLenInput": (3.0, 10.0),
    "obInput": (70.0, 85.0),
    "osInput": (15.0, 30.0),
    "confHighInput": (60.0, 75.0),
    "confLowInput": (25.0, 40.0),
    "fatigueBarsInput": (1.0, 4.0),
    "knnKInput": (3.0, 10.0),
    "knnWindowInput": (80.0, 300.0),
}

INT_PARAMS: set[str] = {
    "lengthInput",
    "sigLenInput",
    "fatigueBarsInput",
    "knnKInput",
    "knnWindowInput",
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
}

OBJECTIVE_METRIC = "nexus_5m_signal_quality"


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

    open_ = frame["open"].to_numpy(dtype=np.float64)
    high = frame["high"].to_numpy(dtype=np.float64)
    low = frame["low"].to_numpy(dtype=np.float64)
    close = frame["close"].to_numpy(dtype=np.float64)
    volume = np.nan_to_num(frame["volume"].to_numpy(dtype=np.float64), nan=0.0)
    volume_available = np.cumsum(np.maximum(volume, 0.0)) > 0.0
    bar_volume = np.where(volume_available, volume, 0.0)

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

    candle_range = high - low
    body_size = np.abs(close - open_)
    body_ratio = _safe_div(body_size, candle_range, 0.0)
    upper_wick = high - np.maximum(close, open_)
    lower_wick = np.minimum(close, open_) - low
    wick_bias = _safe_div(lower_wick - upper_wick, candle_range, 0.0)
    body_dir = np.where(close > open_, 1.0, np.where(close < open_, -1.0, 0.0))
    candle_score = body_dir * body_ratio * 0.7 + wick_bias * 0.3
    signed_vol = np.where(volume_available, candle_score * bar_volume, 0.0)
    avg_vol = _sma(bar_volume, eff_len * 2)
    vnvf_raw = np.where(
        volume_available,
        _safe_div(signed_vol, np.maximum(atr_eff, MINTICK) * np.maximum(avg_vol, 1.0), 0.0),
        0.0,
    )
    vnvf_fast = _ema(vnvf_raw, max(int(round(eff_len * 0.6)), 2))
    vnvf_slow = _ema(vnvf_raw, max(int(round(eff_len * 1.4)), 3))
    vnvf_blend = vnvf_fast * 0.6 + vnvf_slow * 0.4
    vnvf_peak = np.maximum(_rolling_high(np.abs(vnvf_blend), eff_len * 4), 0.0001)
    vf_raw = np.clip(_safe_div(vnvf_blend, vnvf_peak, 0.0) * 50.0 + 50.0, 0.0, 100.0)
    vf = np.where(volume_available, vf_raw, 50.0)

    return {
        "open": open_,
        "high": high,
        "low": low,
        "close": close,
        "volume": volume,
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
            if close[i] > close[i - 1] + atr14[i] * 0.15:
                outcome = 1
            elif close[i] < close[i - 1] - atr14[i] * 0.15:
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
            recency_bonus = 1.0 + (j / float(k_size)) * 0.1
            distances[j] = d / recency_bonus

        order = np.argsort(distances)[:k_neighbors]
        weights = 1.0 / (distances[order] + 0.001)
        labels = np.asarray([ky[idx] for idx in order], dtype=np.float64)
        bull_votes = float(np.sum(weights * labels))
        total_weight = float(np.sum(weights))
        knn_val[i] = _safe_float(_safe_div(bull_votes, total_weight, 0.5), 0.5) * 100.0

    knn_bull = knn_val >= 58.0
    knn_bear = knn_val <= 42.0
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
    )

    er_trending = er_smoothed > 0.3
    conf_bull = np.zeros(len(frame), dtype=np.int64)
    conf_bear = np.zeros(len(frame), dtype=np.int64)
    conf_bull += (osc > 55.0).astype(np.int64)
    conf_bear += (osc < 45.0).astype(np.int64)
    conf_bull += (osc > sig).astype(np.int64)
    conf_bear += (osc < sig).astype(np.int64)
    conf_bull += ((vf > 55.0) & volume_available).astype(np.int64)
    conf_bear += ((vf < 45.0) & volume_available).astype(np.int64)
    conf_bull += (er_trending & (osc > 50.0)).astype(np.int64)
    conf_bear += (er_trending & (osc < 50.0)).astype(np.int64)
    conf_bull += knn_bull.astype(np.int64)
    conf_bear += knn_bear.astype(np.int64)
    conf_net = conf_bull - conf_bear
    conf_sources = np.where(volume_available, 5.0, 4.0)
    conf_raw = (conf_net + conf_sources) / (conf_sources * 2.0) * 100.0
    conf = np.clip(_ema(conf_raw, 3), 0.0, 100.0)

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
    vf_in = (vf > 50.0) & (prev_vf <= 50.0) & warmup_mask & volume_available
    vf_out = (vf < 50.0) & (prev_vf >= 50.0) & warmup_mask & volume_available

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
    horizon_bars: int = SIGNAL_HORIZON_BARS,
    favorable_atr: float = 0.75,
    adverse_atr: float = 0.75,
) -> dict[str, float]:
    count = 0
    good = 0
    favorable_hits = 0
    adverse_first = 0
    forward_atr_returns: list[float] = []

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
                    favorable_hits += 1
                    success = True
                    break
            else:
                if high[j] >= adverse:
                    adverse_first += 1
                    success = False
                    break
                if low[j] <= favorable:
                    favorable_hits += 1
                    success = True
                    break

        forward_atr_return = direction * (float(close[end]) - anchor) / risk
        forward_atr_returns.append(forward_atr_return)
        if success is None:
            success = forward_atr_return > 0.0
        if success:
            good += 1

    precision = good / count if count else 0.0
    mean_forward_atr = float(np.mean(forward_atr_returns)) if forward_atr_returns else 0.0
    edge_score = _bounded(0.5 + 0.5 * np.tanh(mean_forward_atr / 0.75))
    quality = _bounded(0.70 * precision + 0.30 * edge_score)
    return {
        "count": float(count),
        "precision": float(precision),
        "mean_forward_atr": mean_forward_atr,
        "favorable_hit_rate": favorable_hits / count if count else 0.0,
        "adverse_first_rate": adverse_first / count if count else 0.0,
        "quality": quality,
    }


def _state_entries(state_direction: np.ndarray) -> np.ndarray:
    previous = np.roll(state_direction, 1)
    previous[0] = 0
    entries = np.zeros(len(state_direction), dtype=np.int8)
    mask = (state_direction != 0) & (state_direction != previous)
    entries[mask] = state_direction[mask]
    return entries


def _empty_quality_result() -> dict[str, Any]:
    return {
        "trades": 0,
        "win_rate": 0.0,
        "pf": 0.0,
        "gross_profit": 0.0,
        "gross_loss": 1.0,
        "max_dd_abs": 1.0,
        "net_profit": 0.0,
        "signal_quality_score": 0.0,
        "primary_signal_quality": 0.0,
        "confluence_calibration": 0.0,
        "volume_flow_quality": 0.0,
        "fatigue_warning_quality": 0.0,
        "knn_bias_quality": 0.0,
        "noise_control": 0.0,
        "quality_events": 0,
        "entry_signal_count": 0,
        "entry_signal_precision": 0.0,
        "primary_signal_count": 0,
        "primary_signal_precision": 0.0,
        "fatigue_signal_count": 0,
        "fatigue_signal_precision": 0.0,
        "confluence_event_count": 0,
        "confluence_precision": 0.0,
        "volume_flow_event_count": 0,
        "volume_flow_precision": 0.0,
        "knn_state_count": 0,
        "knn_state_precision": 0.0,
        "primary_signals_per_day": 0.0,
        "fatigue_signals_per_day": 0.0,
        "knn_flips_per_day": 0.0,
        "confluence_flips_per_day": 0.0,
        "volume_flow_flips_per_day": 0.0,
    }


def objective_score(result: dict[str, Any]) -> float:
    quality_events = _safe_int(result.get("quality_events"), _safe_int(result.get("trades"), 0))
    if quality_events < 20:
        return 0.0
    return _bounded(_safe_float(result.get("signal_quality_score"), 0.0))


def _rollup_1m_to_5m(df: pd.DataFrame) -> pd.DataFrame:
    frame = df.copy()
    frame["ts"] = pd.to_datetime(frame["ts"], utc=True)
    frame = frame.sort_values("ts").drop_duplicates(subset=["ts"]).set_index("ts")
    agg: dict[str, Any] = {
        "open": "first",
        "high": "max",
        "low": "min",
        "close": "last",
        "volume": "sum",
    }
    if "symbol" in frame.columns:
        agg["symbol"] = "first"
    rolled = frame.resample("5min", origin="epoch", label="left", closed="left").agg(agg)
    rolled = rolled.dropna(subset=["open", "high", "low", "close"]).reset_index()
    if "symbol" not in rolled.columns:
        rolled["symbol"] = "MES"
    return rolled.loc[:, ["ts", "open", "high", "low", "close", "volume", "symbol"]]


def load_data() -> pd.DataFrame:
    if DATA_PATH.exists():
        df = pd.read_parquet(DATA_PATH)
    elif SOURCE_1M_PATH.exists():
        df = _rollup_1m_to_5m(pd.read_parquet(SOURCE_1M_PATH))
    else:
        raise FileNotFoundError(f"Missing MES 5m parquet: {DATA_PATH}")

    required = {"ts", "open", "high", "low", "close", "volume"}
    missing = required.difference(df.columns)
    if missing:
        raise ValueError(f"mes_5m parquet missing required columns: {sorted(missing)}")

    df = df.loc[:, [c for c in df.columns if c in {"ts", "open", "high", "low", "close", "volume", "symbol"}]].copy()
    df["ts"] = pd.to_datetime(df["ts"], utc=True)
    df = df.sort_values("ts").drop_duplicates(subset=["ts"]).reset_index(drop=True)
    return df


def run_backtest(df: pd.DataFrame, params: dict[str, Any], start_date: str) -> dict[str, Any]:
    start_ts = pd.Timestamp(start_date)
    start_ts = start_ts.tz_localize("UTC") if start_ts.tzinfo is None else start_ts.tz_convert("UTC")

    frame = df.loc[pd.to_datetime(df["ts"], utc=True) >= start_ts].copy()
    if frame.empty:
        return _empty_quality_result()

    feat = _compute_features(frame, params).reset_index(drop=True)

    use_conf = bool(params.get("useConfluenceGate", True))
    use_vf = bool(params.get("useVolumeFlowGate", True))
    use_zone_exit = bool(params.get("useZoneExitSignals", False))
    use_knn = bool(params.get("useKnnGate", True))

    conf_high = _safe_float(params.get("confHighInput"), 65.0)
    conf_low = _safe_float(params.get("confLowInput"), 35.0)
    ob_level, os_level = _effective_zones(params)

    osc = feat["osc"].to_numpy(dtype=np.float64)
    prev_osc = np.roll(osc, 1)
    prev_osc[0] = osc[0]
    cross_up = feat["cross_up"].to_numpy(dtype=bool)
    cross_down = feat["cross_down"].to_numpy(dtype=bool)

    primary_long = cross_up & ((osc < 50.0) | (prev_osc < 50.0))
    primary_short = cross_down & ((osc > 50.0) | (prev_osc > 50.0))
    long_signal = primary_long.copy()
    short_signal = primary_short.copy()
    if use_zone_exit:
        long_signal |= feat["exit_os"].to_numpy(dtype=bool)
        short_signal |= feat["exit_ob"].to_numpy(dtype=bool)

    conf_arr = feat["conf"].to_numpy(dtype=np.float64)
    vf_arr = feat["vf"].to_numpy(dtype=np.float64)
    if use_conf:
        long_signal &= conf_arr >= conf_high
        short_signal &= conf_arr <= conf_low
    if use_vf:
        long_signal &= vf_arr >= 50.0
        short_signal &= vf_arr <= 50.0
    if use_knn:
        long_signal &= feat["knn_bull"].to_numpy(dtype=bool)
        short_signal &= feat["knn_bear"].to_numpy(dtype=bool)

    warmup_mask = feat["is_warmed_up"].to_numpy(dtype=bool)
    long_signal &= warmup_mask
    short_signal &= warmup_mask

    chosen_signal = np.zeros(len(feat), dtype=np.int8)
    chosen_signal[long_signal & ~short_signal] = 1
    chosen_signal[short_signal & ~long_signal] = -1

    high = feat["high"].to_numpy(dtype=np.float64)
    low = feat["low"].to_numpy(dtype=np.float64)
    close = feat["close"].to_numpy(dtype=np.float64)
    atr = feat["atr"].to_numpy(dtype=np.float64)
    primary_stats = _score_directional_events(
        signal_direction=chosen_signal,
        high=high,
        low=low,
        close=close,
        atr=atr,
        horizon_bars=SIGNAL_HORIZON_BARS,
        favorable_atr=0.75,
        adverse_atr=0.75,
    )

    fat_ob_signal = feat["fat_ob_signal"].to_numpy(dtype=bool)
    fat_os_signal = feat["fat_os_signal"].to_numpy(dtype=bool)
    fatigue_direction = np.zeros(len(feat), dtype=np.int8)
    fatigue_direction[fat_os_signal & warmup_mask] = 1
    fatigue_direction[fat_ob_signal & warmup_mask] = -1
    fatigue_stats = _score_directional_events(
        signal_direction=fatigue_direction,
        high=high,
        low=low,
        close=close,
        atr=atr,
        horizon_bars=max(SIGNAL_HORIZON_BARS // 2, 3),
        favorable_atr=0.50,
        adverse_atr=0.75,
    )

    conf_direction = np.zeros(len(feat), dtype=np.int8)
    conf_direction[(conf_arr >= conf_high) & warmup_mask] = 1
    conf_direction[(conf_arr <= conf_low) & warmup_mask] = -1
    conf_events = _state_entries(conf_direction)
    conf_stats = _score_directional_events(
        signal_direction=conf_events,
        high=high,
        low=low,
        close=close,
        atr=atr,
        horizon_bars=SIGNAL_HORIZON_BARS,
        favorable_atr=0.75,
        adverse_atr=0.75,
    )

    knn_direction = np.zeros(len(feat), dtype=np.int8)
    knn_direction[feat["knn_bull"].to_numpy(dtype=bool) & warmup_mask] = 1
    knn_direction[feat["knn_bear"].to_numpy(dtype=bool) & warmup_mask] = -1
    knn_events = _state_entries(knn_direction)
    knn_stats = _score_directional_events(
        signal_direction=knn_events,
        high=high,
        low=low,
        close=close,
        atr=atr,
        horizon_bars=max(SIGNAL_HORIZON_BARS // 2, 3),
        favorable_atr=0.35,
        adverse_atr=0.35,
    )

    volume_direction = np.zeros(len(feat), dtype=np.int8)
    volume_direction[feat["vf_in"].to_numpy(dtype=bool)] = 1
    volume_direction[feat["vf_out"].to_numpy(dtype=bool)] = -1
    volume_stats = _score_directional_events(
        signal_direction=volume_direction,
        high=high,
        low=low,
        close=close,
        atr=atr,
        horizon_bars=max(SIGNAL_HORIZON_BARS // 2, 3),
        favorable_atr=0.50,
        adverse_atr=0.50,
    )

    ts_chicago = feat["ts"].dt.tz_convert("America/Chicago")
    day_count = max(int(ts_chicago.dt.date.nunique()), 1)
    primary_signal_count = int(primary_stats["count"])
    fatigue_signal_count = int(fatigue_stats["count"])
    confluence_event_count = int(conf_stats["count"])
    volume_flow_event_count = int(volume_stats["count"])
    knn_state_count = int(knn_stats["count"])
    confluence_flips = int(np.count_nonzero(conf_events))
    volume_flow_flips = int(np.count_nonzero(volume_direction))
    knn_flips = int(np.count_nonzero(knn_events))

    primary_signals_per_day = primary_signal_count / day_count
    fatigue_signals_per_day = fatigue_signal_count / day_count
    confluence_flips_per_day = confluence_flips / day_count
    volume_flow_flips_per_day = volume_flow_flips / day_count
    knn_flips_per_day = knn_flips / day_count

    primary_signal_quality = primary_stats["quality"] * _presence_score(primary_signal_count, 60.0)
    confluence_calibration = conf_stats["quality"] * _presence_score(confluence_event_count, 80.0)
    volume_flow_stability = _bounded(1.0 - volume_flow_flips_per_day / 18.0)
    volume_flow_quality = (
        0.80 * volume_stats["quality"] * _presence_score(volume_flow_event_count, 60.0)
        + 0.20 * volume_flow_stability
    )
    fatigue_warning_quality = fatigue_stats["quality"] * _presence_score(fatigue_signal_count, 40.0)
    knn_stability = _bounded(1.0 - knn_flips_per_day / 18.0)
    knn_bias_quality = (
        0.75 * knn_stats["quality"] * _presence_score(knn_state_count, 80.0)
        + 0.25 * knn_stability
    )

    primary_rate_score = _rate_band_score(primary_signals_per_day, low=0.35, high=8.0, hard_high=20.0)
    fatigue_rate_score = _rate_band_score(fatigue_signals_per_day, low=0.15, high=8.0, hard_high=20.0)
    confluence_stability = _bounded(1.0 - confluence_flips_per_day / 12.0)
    noise_control = (
        0.30 * primary_rate_score
        + 0.20 * fatigue_rate_score
        + 0.20 * knn_stability
        + 0.15 * confluence_stability
        + 0.15 * volume_flow_stability
    )

    signal_quality_score = _bounded(
        0.30 * primary_signal_quality
        + 0.20 * confluence_calibration
        + 0.15 * volume_flow_quality
        + 0.15 * fatigue_warning_quality
        + 0.10 * knn_bias_quality
        + 0.10 * noise_control
    )
    quality_events = primary_signal_count + fatigue_signal_count + confluence_event_count + volume_flow_event_count + knn_state_count
    quality_ratio = signal_quality_score / max(1.0 - signal_quality_score, 0.001)

    return {
        "trades": quality_events,
        "win_rate": primary_stats["precision"],
        "pf": min(quality_ratio, 99.0),
        "gross_profit": signal_quality_score,
        "gross_loss": max(1.0 - signal_quality_score, 0.0),
        "max_dd_abs": max(1.0 - noise_control, 0.0),
        "net_profit": signal_quality_score,
        "signal_quality_score": signal_quality_score,
        "primary_signal_quality": primary_signal_quality,
        "confluence_calibration": confluence_calibration,
        "volume_flow_quality": volume_flow_quality,
        "fatigue_warning_quality": fatigue_warning_quality,
        "knn_bias_quality": knn_bias_quality,
        "noise_control": noise_control,
        "quality_events": quality_events,
        "entry_signal_count": primary_signal_count,
        "entry_signal_precision": primary_stats["precision"],
        "primary_signal_count": primary_signal_count,
        "primary_signal_precision": primary_stats["precision"],
        "primary_mean_forward_atr": primary_stats["mean_forward_atr"],
        "primary_favorable_hit_rate": primary_stats["favorable_hit_rate"],
        "primary_adverse_first_rate": primary_stats["adverse_first_rate"],
        "fatigue_signal_count": fatigue_signal_count,
        "fatigue_signal_precision": fatigue_stats["precision"],
        "fatigue_mean_forward_atr": fatigue_stats["mean_forward_atr"],
        "confluence_event_count": confluence_event_count,
        "confluence_precision": conf_stats["precision"],
        "confluence_mean_forward_atr": conf_stats["mean_forward_atr"],
        "volume_flow_event_count": volume_flow_event_count,
        "volume_flow_precision": volume_stats["precision"],
        "volume_flow_mean_forward_atr": volume_stats["mean_forward_atr"],
        "knn_state_count": knn_state_count,
        "knn_state_precision": knn_stats["precision"],
        "knn_mean_forward_atr": knn_stats["mean_forward_atr"],
        "primary_signals_per_day": primary_signals_per_day,
        "fatigue_signals_per_day": fatigue_signals_per_day,
        "knn_flips_per_day": knn_flips_per_day,
        "confluence_flips_per_day": confluence_flips_per_day,
        "volume_flow_flips_per_day": volume_flow_flips_per_day,
    }
