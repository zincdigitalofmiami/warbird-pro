#!/usr/bin/env python3
"""Optuna profile for Warbird Nexus Machine Learning RSI.

Guide-driven tuning surface for the user's actual workflow on MES 15m:
- primary entries are oscillator/signal crosses in extreme zones
- confirmations come from volume flow, KNN, HTF, and confluence
- fatigue is a first-class exit/weakening signal

This is still a research harness over MES 15m OHLCV, not a claim of exact
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


MES_POINT_VALUE = 5.0
COMMISSION_SIDE = 1.0
MINTICK = 0.25
DATA_PATH = REPO_ROOT / "data" / "mes_15m.parquet"
SESSION_TZ = "America/Chicago"
SESSION_ANCHOR_HOUR = 17
SIGNAL_HORIZON_BARS = 12


BOOL_PARAMS: list[str] = [
    "useConfluenceGate",
    "useHtfBiasGate",
    "useVolumeFlowGate",
    "useZoneExitSignals",
    "useKnnGate",
]

NUMERIC_RANGES: dict[str, tuple[float, float]] = {
    "lengthInput": (8.0, 50.0),
    "sigLenInput": (3.0, 15.0),
    "obInput": (65.0, 90.0),
    "osInput": (10.0, 35.0),
    "confHighInput": (55.0, 75.0),
    "confLowInput": (25.0, 45.0),
    "stopAtrMult": (0.75, 4.0),
    "targetAtrMult": (0.75, 8.0),
    "maxHoldBars": (4.0, 48.0),
    "fatigueBarsInput": (1.0, 5.0),
    "knnKInput": (3.0, 15.0),
    "knnWindowInput": (50.0, 400.0),
}

INT_PARAMS: set[str] = {
    "lengthInput",
    "sigLenInput",
    "maxHoldBars",
    "fatigueBarsInput",
    "knnKInput",
    "knnWindowInput",
}

CATEGORICAL_PARAMS: dict[str, list[Any]] = {
    "sourceInput": ["close", "hlc3", "ohlc4"],
    "smoothTypeInput": ["EMA", "SMA", "DEMA", "TEMA", "WMA", "VWMA"],
    "sigTypeInput": ["EMA", "SMA", "DEMA", "WMA"],
    "htfInput": ["", "60", "240", "D"],
}

INPUT_DEFAULTS: dict[str, Any] = {
    "lengthInput": 14,
    "sourceInput": "close",
    "smoothTypeInput": "DEMA",
    "sigLenInput": 7,
    "sigTypeInput": "EMA",
    "obInput": 80.0,
    "osInput": 20.0,
    "confHighInput": 70.0,
    "confLowInput": 30.0,
    "stopAtrMult": 1.5,
    "targetAtrMult": 3.0,
    "maxHoldBars": 20,
    "useConfluenceGate": True,
    "useHtfBiasGate": True,
    "useVolumeFlowGate": True,
    "useZoneExitSignals": False,
    "useKnnGate": True,
    "useFatigueExit": True,
    "htfInput": "60",
    "fatigueBarsInput": 3,
    "knnKInput": 5,
    "knnWindowInput": 120,
}

OBJECTIVE_METRIC = "confirmation_fatigue"


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
    if source_input == "hlc3":
        return (high + low + close) / 3.0
    if source_input == "ohlc4":
        return (open_ + high + low + close) / 4.0
    return close


def _htf_freq(htf_input: str) -> str | None:
    if htf_input == "60":
        return "60min"
    if htf_input == "240":
        return "240min"
    if htf_input == "D":
        return "1D"
    return None


def _session_bucket_start(ts: pd.Series, freq: str) -> pd.Series:
    local = pd.to_datetime(ts, utc=True).dt.tz_convert(SESSION_TZ)
    anchored = local - pd.Timedelta(hours=SESSION_ANCHOR_HOUR)
    return anchored.dt.floor(freq) + pd.Timedelta(hours=SESSION_ANCHOR_HOUR)


def _resample_ohlcv(frame: pd.DataFrame, freq: str) -> pd.DataFrame:
    work = frame.loc[:, ["ts", "open", "high", "low", "close", "volume"]].copy()
    bucket_start = _session_bucket_start(work["ts"], freq)
    delta = pd.to_timedelta(freq)
    work["bucket_start"] = bucket_start
    grouped = work.groupby("bucket_start", sort=True)
    out = grouped.agg(
        open=("open", "first"),
        high=("high", "max"),
        low=("low", "min"),
        close=("close", "last"),
        volume=("volume", "sum"),
    ).reset_index()
    out["ts"] = (out["bucket_start"] + delta).dt.tz_convert("UTC")
    return out.loc[:, ["ts", "open", "high", "low", "close", "volume"]]


def _compute_core(frame: pd.DataFrame, params: dict[str, Any]) -> dict[str, np.ndarray]:
    eff_len = max(_safe_int(params.get("lengthInput"), 14), 2)
    sig_len = max(_safe_int(params.get("sigLenInput"), 7), 1)
    source = _resolve_source(frame, str(params.get("sourceInput", "close")))
    smooth_type = str(params.get("smoothTypeInput", "DEMA"))
    sig_type = str(params.get("sigTypeInput", "EMA"))

    open_ = frame["open"].to_numpy(dtype=np.float64)
    high = frame["high"].to_numpy(dtype=np.float64)
    low = frame["low"].to_numpy(dtype=np.float64)
    close = frame["close"].to_numpy(dtype=np.float64)
    volume = frame["volume"].to_numpy(dtype=np.float64)

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
    signed_vol = candle_score * volume
    avg_vol = _sma(volume, eff_len * 2)
    vnvf_raw = _safe_div(signed_vol, np.maximum(atr_eff, MINTICK) * np.maximum(avg_vol, 1.0), 0.0)
    vnvf_fast = _ema(vnvf_raw, max(int(round(eff_len * 0.6)), 2))
    vnvf_slow = _ema(vnvf_raw, max(int(round(eff_len * 1.4)), 3))
    vnvf_blend = vnvf_fast * 0.6 + vnvf_slow * 0.4
    vnvf_peak = np.maximum(_rolling_high(np.abs(vnvf_blend), eff_len * 4), 0.0001)
    vf = np.clip(_safe_div(vnvf_blend, vnvf_peak, 0.0) * 50.0 + 50.0, 0.0, 100.0)

    return {
        "open": open_,
        "high": high,
        "low": low,
        "close": close,
        "volume": volume,
        "atr_eff": np.maximum(atr_eff, MINTICK),
        "atr14": np.maximum(atr14, MINTICK),
        "er_smoothed": er_smoothed,
        "osc": osc,
        "sig": sig,
        "vf": vf,
        "eff_len": np.full(len(frame), eff_len, dtype=np.int64),
    }


def _build_htf_bias(frame: pd.DataFrame, params: dict[str, Any]) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    htf_input = str(params.get("htfInput", ""))
    freq = _htf_freq(htf_input)
    n = len(frame)
    neutral = np.full(n, 50.0, dtype=np.float64)
    neutral_bool = np.zeros(n, dtype=bool)
    if not freq:
        return neutral, neutral, neutral_bool, neutral_bool

    htf_frame = _resample_ohlcv(frame, freq)
    if htf_frame.empty:
        return neutral, neutral, neutral_bool, neutral_bool

    htf_core = _compute_core(htf_frame, params)
    htf_view = pd.DataFrame(
        {
            "ts": pd.to_datetime(htf_frame["ts"], utc=True),
            "osc": htf_core["osc"],
            "sig": htf_core["sig"],
        }
    ).sort_values("ts")

    base_ts = pd.DataFrame({"ts": pd.to_datetime(frame["ts"], utc=True)}).sort_values("ts")
    merged = pd.merge_asof(
        base_ts,
        htf_view,
        on="ts",
        direction="backward",
        allow_exact_matches=False,
    )
    htf_osc = merged["osc"].fillna(50.0).to_numpy(dtype=np.float64)
    htf_sig = merged["sig"].fillna(50.0).to_numpy(dtype=np.float64)
    htf_bull = (htf_osc > 50.0) & (htf_osc > htf_sig)
    htf_bear = (htf_osc < 50.0) & (htf_osc < htf_sig)
    return htf_osc, htf_sig, htf_bull, htf_bear


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
    er_smoothed = core["er_smoothed"]
    atr = core["atr_eff"]
    atr14 = core["atr14"]

    eff_len = max(_safe_int(params.get("lengthInput"), 14), 2)
    ob_level = _safe_float(params.get("obInput"), 80.0)
    os_level = _safe_float(params.get("osInput"), 20.0)
    fatigue_bars = max(_safe_int(params.get("fatigueBarsInput"), 3), 1)
    warmup_bars = max(eff_len * 3, 60)
    warmup_mask = np.arange(len(frame), dtype=np.int64) >= warmup_bars

    htf_osc, htf_sig, htf_bull, htf_bear = _build_htf_bias(frame, params)
    knn_k = max(_safe_int(params.get("knnKInput"), 5), 3)
    knn_window = max(_safe_int(params.get("knnWindowInput"), 120), 50)
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
    conf_bull += (vf > 55.0).astype(np.int64)
    conf_bear += (vf < 45.0).astype(np.int64)
    conf_bull += (er_trending & (osc > 50.0)).astype(np.int64)
    conf_bear += (er_trending & (osc < 50.0)).astype(np.int64)
    conf_bull += knn_bull.astype(np.int64)
    conf_bear += knn_bear.astype(np.int64)
    conf_bull += htf_bull.astype(np.int64)
    conf_bear += htf_bear.astype(np.int64)
    conf_net = conf_bull - conf_bear
    conf_raw = (conf_net + 6.0) / 12.0 * 100.0
    conf = np.clip(_ema(conf_raw, 3), 0.0, 100.0)

    prev_osc = np.roll(osc, 1)
    prev_sig = np.roll(sig, 1)
    prev_osc[0] = osc[0]
    prev_sig[0] = sig[0]
    cross_up = (osc > sig) & (prev_osc <= prev_sig) & warmup_mask
    cross_down = (osc < sig) & (prev_osc >= prev_sig) & warmup_mask
    exit_os = (osc > os_level) & (prev_osc <= os_level) & warmup_mask
    exit_ob = (osc < ob_level) & (prev_osc >= ob_level) & warmup_mask

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
            "atr": atr,
            "osc": osc,
            "sig": sig,
            "vf": vf,
            "er": er_smoothed,
            "conf": conf,
            "knn_val": knn_val,
            "knn_bull": knn_bull,
            "knn_bear": knn_bear,
            "htf_osc": htf_osc,
            "htf_sig": htf_sig,
            "htf_bull": htf_bull,
            "htf_bear": htf_bear,
            "is_warmed_up": warmup_mask,
            "cross_up": cross_up,
            "cross_down": cross_down,
            "exit_os": exit_os,
            "exit_ob": exit_ob,
            "fat_ob_signal": fat_ob_signal,
            "fat_os_signal": fat_os_signal,
        }
    )


def _score_entry_precision(
    chosen_signal: np.ndarray,
    open_: np.ndarray,
    high: np.ndarray,
    low: np.ndarray,
    atr: np.ndarray,
    horizon_bars: int = SIGNAL_HORIZON_BARS,
) -> tuple[int, float]:
    signal_count = 0
    good_signals = 0
    for i in range(len(chosen_signal) - 1):
        direction = int(chosen_signal[i])
        if direction == 0:
            continue
        signal_count += 1
        entry_price = open_[i + 1] + (MINTICK if direction == 1 else -MINTICK)
        risk = max(float(atr[i]), MINTICK)
        favorable = entry_price + direction * risk
        adverse = entry_price - direction * 0.75 * risk
        end = min(i + 1 + horizon_bars, len(chosen_signal) - 1)
        success = False
        for j in range(i + 1, end + 1):
            if direction == 1:
                if low[j] <= adverse:
                    break
                if high[j] >= favorable:
                    success = True
                    break
            else:
                if high[j] >= adverse:
                    break
                if low[j] <= favorable:
                    success = True
                    break
        if success:
            good_signals += 1
    precision = good_signals / signal_count if signal_count else 0.0
    return signal_count, precision


def objective_score(result: dict[str, Any]) -> float:
    trades = _safe_int(result.get("trades"), 0)
    signal_count = _safe_int(result.get("entry_signal_count"), 0)
    if signal_count < 20 or trades < 20:
        return 0.0

    entry_precision = _safe_float(result.get("entry_signal_precision"), 0.0)
    wr = _safe_float(result.get("win_rate"), 0.0)
    pf_norm = min(_safe_float(result.get("pf"), 0.0), 3.0) / 3.0
    fatigue_exits = _safe_int(result.get("fatigue_exits"), 0)
    fatigue_exit_precision = _safe_float(result.get("fatigue_exit_precision"), 0.0)
    fatigue_exit_presence = min(fatigue_exits / max(trades * 0.20, 1.0), 1.0)

    net_profit = _safe_float(result.get("net_profit"), 0.0)
    max_dd_abs = max(_safe_float(result.get("max_dd_abs"), 0.0), 1.0)
    dd_efficiency = max(0.0, min(net_profit / max_dd_abs, 2.0) / 2.0)

    entry_presence = min(signal_count / 60.0, 1.0)
    coverage = min(trades / 80.0, 1.0)
    entry_quality = (
        0.55 * entry_precision * entry_presence
        + 0.25 * wr
        + 0.20 * pf_norm
    )
    exit_quality = (
        0.70 * fatigue_exit_precision * fatigue_exit_presence
        + 0.30 * dd_efficiency
    )
    return 0.50 * entry_quality + 0.40 * exit_quality + 0.10 * coverage


def load_data() -> pd.DataFrame:
    if not DATA_PATH.exists():
        raise FileNotFoundError(f"Missing OHLCV parquet: {DATA_PATH}")

    df = pd.read_parquet(DATA_PATH)
    required = {"ts", "open", "high", "low", "close", "volume"}
    missing = required.difference(df.columns)
    if missing:
        raise ValueError(f"mes_15m parquet missing required columns: {sorted(missing)}")

    df = df.loc[:, [c for c in df.columns if c in {"ts", "open", "high", "low", "close", "volume", "symbol"}]].copy()
    df["ts"] = pd.to_datetime(df["ts"], utc=True)
    df = df.sort_values("ts").drop_duplicates(subset=["ts"]).reset_index(drop=True)
    return df


def run_backtest(df: pd.DataFrame, params: dict[str, Any], start_date: str) -> dict[str, Any]:
    start_ts = pd.Timestamp(start_date)
    start_ts = start_ts.tz_localize("UTC") if start_ts.tzinfo is None else start_ts.tz_convert("UTC")

    frame = df.loc[pd.to_datetime(df["ts"], utc=True) >= start_ts].copy()
    if frame.empty:
        return {
            "trades": 0,
            "win_rate": 0.0,
            "pf": 0.0,
            "gross_profit": 0.0,
            "gross_loss": 0.0,
            "max_dd_abs": 0.0,
            "entry_signal_count": 0,
            "entry_signal_precision": 0.0,
            "fatigue_exits": 0,
            "fatigue_exit_precision": 0.0,
            "net_profit": 0.0,
        }

    feat = _compute_features(frame, params).reset_index(drop=True)

    use_conf = bool(params.get("useConfluenceGate", True))
    use_htf = bool(params.get("useHtfBiasGate", False))
    use_vf = bool(params.get("useVolumeFlowGate", True))
    use_zone_exit = bool(params.get("useZoneExitSignals", False))
    use_knn = bool(params.get("useKnnGate", True))
    use_fatigue_exit = bool(params.get("useFatigueExit", True))

    conf_high = _safe_float(params.get("confHighInput"), 70.0)
    conf_low = _safe_float(params.get("confLowInput"), 30.0)
    ob_level = _safe_float(params.get("obInput"), 80.0)
    os_level = _safe_float(params.get("osInput"), 20.0)

    osc = feat["osc"].to_numpy(dtype=np.float64)
    prev_osc = np.roll(osc, 1)
    prev_osc[0] = osc[0]
    cross_up = feat["cross_up"].to_numpy(dtype=bool)
    cross_down = feat["cross_down"].to_numpy(dtype=bool)

    primary_long = cross_up & ((osc <= os_level) | (prev_osc <= os_level))
    primary_short = cross_down & ((osc >= ob_level) | (prev_osc >= ob_level))
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
    if use_htf:
        long_signal &= feat["htf_bull"].to_numpy(dtype=bool)
        short_signal &= feat["htf_bear"].to_numpy(dtype=bool)
    if use_knn:
        long_signal &= feat["knn_bull"].to_numpy(dtype=bool)
        short_signal &= feat["knn_bear"].to_numpy(dtype=bool)

    warmup_mask = feat["is_warmed_up"].to_numpy(dtype=bool)
    long_signal &= warmup_mask
    short_signal &= warmup_mask

    chosen_signal = np.zeros(len(feat), dtype=np.int8)
    chosen_signal[long_signal & ~short_signal] = 1
    chosen_signal[short_signal & ~long_signal] = -1

    open_ = feat["open"].to_numpy(dtype=np.float64)
    high = feat["high"].to_numpy(dtype=np.float64)
    low = feat["low"].to_numpy(dtype=np.float64)
    close = feat["close"].to_numpy(dtype=np.float64)
    atr = feat["atr"].to_numpy(dtype=np.float64)
    entry_signal_count, entry_signal_precision = _score_entry_precision(
        chosen_signal=chosen_signal,
        open_=open_,
        high=high,
        low=low,
        atr=atr,
    )

    stop_mult = max(_safe_float(params.get("stopAtrMult"), 1.5), 0.25)
    target_mult = max(_safe_float(params.get("targetAtrMult"), 3.0), 0.25)
    max_hold_bars = max(_safe_int(params.get("maxHoldBars"), 20), 1)
    fat_ob_signal = feat["fat_ob_signal"].to_numpy(dtype=bool)
    fat_os_signal = feat["fat_os_signal"].to_numpy(dtype=bool)

    equity = 0.0
    peak_equity = 0.0
    max_dd_abs = 0.0
    gross_profit = 0.0
    gross_loss = 0.0
    wins = 0
    trades = 0

    position = 0
    entry_price = 0.0
    entry_bar = -1
    stop_price = 0.0
    target_price = 0.0
    fatigue_exits = 0
    fatigue_good_exits = 0

    def _close_trade(exit_price: float, reason: str, bar_index: int) -> None:
        nonlocal equity, peak_equity, max_dd_abs, gross_profit, gross_loss
        nonlocal wins, trades, position, entry_price, entry_bar, stop_price, target_price
        nonlocal fatigue_exits, fatigue_good_exits

        trade_dir = position
        pnl_points = (exit_price - entry_price) * trade_dir
        pnl_cash = pnl_points * MES_POINT_VALUE - 2.0 * COMMISSION_SIDE
        trades += 1
        if pnl_cash > 0.0:
            wins += 1
            gross_profit += pnl_cash
        else:
            gross_loss += abs(pnl_cash)
        equity += pnl_cash
        peak_equity = max(peak_equity, equity)
        max_dd_abs = max(max_dd_abs, peak_equity - equity)

        if reason == "fatigue":
            fatigue_exits += 1
            lookahead_end = min(bar_index + 4, len(feat))
            lookahead_high = high[bar_index + 1:lookahead_end]
            lookahead_low = low[bar_index + 1:lookahead_end]
            if trade_dir == 1 and lookahead_low.size > 0:
                if np.min(lookahead_low) <= exit_price - 0.5 * atr[bar_index]:
                    fatigue_good_exits += 1
            if trade_dir == -1 and lookahead_high.size > 0:
                if np.max(lookahead_high) >= exit_price + 0.5 * atr[bar_index]:
                    fatigue_good_exits += 1

        position = 0
        entry_price = 0.0
        entry_bar = -1
        stop_price = 0.0
        target_price = 0.0

    for i in range(1, len(feat)):
        if position == 0 and chosen_signal[i - 1] != 0:
            direction = int(chosen_signal[i - 1])
            entry_price = open_[i] + (MINTICK if direction == 1 else -MINTICK)
            risk = max(atr[i - 1], MINTICK)
            stop_price = entry_price - direction * stop_mult * risk
            target_price = entry_price + direction * target_mult * risk
            position = direction
            entry_bar = i

        if position == 0:
            continue

        hit_stop = low[i] <= stop_price if position == 1 else high[i] >= stop_price
        hit_target = high[i] >= target_price if position == 1 else low[i] <= target_price

        if hit_stop and hit_target:
            _close_trade(stop_price, "stop", i)
            continue
        if hit_stop:
            _close_trade(stop_price, "stop", i)
            continue
        if hit_target:
            _close_trade(target_price, "target", i)
            continue

        bars_held = i - entry_bar + 1
        if position == 1:
            weakening_exit = use_fatigue_exit and fat_ob_signal[i]
            reversal_exit = cross_down[i]
            if weakening_exit or reversal_exit or bars_held >= max_hold_bars:
                _close_trade(close[i] - MINTICK, "fatigue" if weakening_exit else "signal", i)
        else:
            weakening_exit = use_fatigue_exit and fat_os_signal[i]
            reversal_exit = cross_up[i]
            if weakening_exit or reversal_exit or bars_held >= max_hold_bars:
                _close_trade(close[i] + MINTICK, "fatigue" if weakening_exit else "signal", i)

    if position != 0:
        final_exit = close[-1] - MINTICK if position == 1 else close[-1] + MINTICK
        _close_trade(final_exit, "final", len(feat) - 1)

    win_rate = wins / trades if trades else 0.0
    if gross_loss > 0.0:
        pf = gross_profit / gross_loss
    elif gross_profit > 0.0:
        pf = 99.0
    else:
        pf = 0.0

    return {
        "trades": trades,
        "win_rate": win_rate,
        "pf": pf,
        "gross_profit": gross_profit,
        "gross_loss": gross_loss,
        "max_dd_abs": max_dd_abs,
        "net_profit": gross_profit - gross_loss,
        "entry_signal_count": entry_signal_count,
        "entry_signal_precision": entry_signal_precision,
        "fatigue_exits": fatigue_exits,
        "fatigue_exit_precision": fatigue_good_exits / fatigue_exits if fatigue_exits else 0.0,
    }
