#!/usr/bin/env python3
"""Build the Warbird Pro V9 Core training dataset.

This is the AG/Core ETL surface, not a Pine edit. It builds manifest-backed
ES rows at 5m or 15m with the locked V9 feature schema, Yahoo DXY parity,
VIX movement pressure fallback, and optional Databento trade-side order-flow
reconstruction for CVD/divergence/absorption.

Core mode:
  - bars: ES OHLCV, normalized to selected timeframe (5m or 15m)
  - cross-asset: NQ/ZN from local Databento 1h bars when available
  - DXY: Yahoo Finance DX-Y.NYB, aligned to the selected bar clock
  - VIX: movement pressure from VIXCLS daily close fallback when available
  - order flow: Databento trades zip, outright contract rows for the selected symbol root only
  - labels are built by scripts/ag/train_v9_locked.py, not here

The builder emits the exact feature names expected by train_v9_locked.ML_FEATURES
and fails hard on stale `ml_xa_dx_code`, OHLCV pseudo-delta columns, or missing
required columns in Core validation mode.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
import subprocess
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[4]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.ag.train_v9_locked import LABEL_COL, ML_FEATURES

WORKSPACE = REPO_ROOT / "scripts" / "optuna" / "workspaces" / "warbird_pro_core"
EXPORTS_DIR = WORKSPACE / "exports"
DEFAULT_TRADES_ZIP = REPO_ROOT / "data" / "MES ES Trades GLBX-20260508-SAGMRP8P3H.zip"
DEFAULT_CROSS_ASSET_1H = Path(
    "/Volumes/Satechi Hub/Historical Data/Databento/raw/databento_futures_ohlcv_1h.parquet"
)
DEFAULT_VIX_CSV = Path("/Volumes/Satechi Hub/ZINC-FUSION-V15/data/downloads/VIXCLS.csv")
DEFAULT_SOURCE_BY_ROOT = {
    "ES": REPO_ROOT / "data" / "es_1m_20260503.parquet",
    "MES": REPO_ROOT / "data" / "mes_1m.parquet",
}

TRIGGER_FAMILY = "LIVE_ANCHOR_FOOTPRINT"
PINE_FILE = "indicators/warbird-pro-v9.pine"

FIB_236 = 0.236
FIB_382 = 0.382
FIB_PIVOT = 0.5
FIB_618 = 0.618
FIB_786 = 0.786
FIB_T1 = 1.236

FIB_DEVIATION = 3.0
FIB_DEPTH = 10
FIB_THRESHOLD_FLOOR_PCT = 0.15
MIN_FIB_RANGE_ATR = 0.5
FIB_HYSTERESIS_PCT = 2.0
HTF_CONF_TOL_PCT = 1.5

USE_MA_GATE = True
MA_SLOW_LEN = 100
MA_FAST_LEN = 50
XA_MIN_AGREEMENT = 3
VIX_PRESSURE_BAND = 0.35
RSI_LEN = 14
RSI_OVERBOUGHT = 75.0
RSI_OVERSOLD = 25.0
LIQ_LOOKBACK_BARS = 20
LIQ_RECENCY_BARS = 8
EQH_TOL_PCT = 5
EQH_MIN_TAPS = 2
EQH_LOOKBACK = 100
VOL_Z_LEN = 20
CORR_LEN = 20
VIX_MOVE_BARS = 3
VIX_ATR_LEN = 14
ORDERFLOW_ROLLING_LEN = 20
ORDERFLOW_ABSORPTION_DELTA_PCT = 35.0
ORDERFLOW_FLUSH_DELTA_PCT = 35.0
ORDERFLOW_EVENT_VOLUME_SPIKE = 1.5
ORDERFLOW_COMPRESSED_RANGE_ATR = 0.75

OUTRIGHT_ROOT_PATTERNS = {
    "ES": re.compile(r"^ES[FGHJKMNQUVXZ]\d{1,2}$"),
}
TRADES_MEMBER_RE = re.compile(r"(\d{8})-(\d{8})\.trades\.csv\.zst$")


def repo_commit() -> str:
    try:
        return subprocess.check_output(
            ["git", "-C", str(REPO_ROOT), "rev-parse", "HEAD"], text=True
        ).strip()
    except Exception:
        return "unknown"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def utc_ts(value: str | None) -> pd.Timestamp | None:
    if value is None:
        return None
    return pd.Timestamp(value, tz="UTC")


def normalize_symbol_root(symbol: str) -> str:
    token = str(symbol).upper().strip()
    if ":" in token:
        token = token.split(":", 1)[1]
    token = token.replace("!", "")
    root = ""
    for char in token:
        if char.isalpha():
            root += char
        else:
            break
    if root.startswith("MES"):
        return "MES"
    if root.startswith("ES"):
        return "ES"
    return root


def default_source_for_symbol(symbol: str) -> Path:
    return DEFAULT_SOURCE_BY_ROOT.get(normalize_symbol_root(symbol), DEFAULT_SOURCE_BY_ROOT["ES"])


def rma(values: np.ndarray, period: int) -> np.ndarray:
    out = np.full(len(values), np.nan, dtype=float)
    if len(values) < period:
        return out
    out[period - 1] = np.nanmean(values[:period])
    alpha = 1.0 / period
    for i in range(period, len(values)):
        out[i] = values[i] * alpha + out[i - 1] * (1.0 - alpha)
    return out


def atr_rma(high: np.ndarray, low: np.ndarray, close: np.ndarray, period: int) -> np.ndarray:
    prev_close = np.r_[close[0], close[:-1]]
    tr = np.maximum(high - low, np.maximum(np.abs(high - prev_close), np.abs(low - prev_close)))
    return rma(tr, period)


def sma(values: np.ndarray, period: int) -> np.ndarray:
    return pd.Series(values).rolling(period, min_periods=period).mean().to_numpy(dtype=float)


def ema(values: np.ndarray, period: int) -> np.ndarray:
    return pd.Series(values).ewm(span=period, adjust=False, min_periods=period).mean().to_numpy(dtype=float)


def rsi_rma(close: np.ndarray, period: int) -> np.ndarray:
    diff = np.diff(close, prepend=close[0])
    gain = np.where(diff > 0, diff, 0.0)
    loss = np.where(diff < 0, -diff, 0.0)
    avg_gain = rma(gain, period)
    avg_loss = rma(loss, period)
    rs = np.divide(avg_gain, np.maximum(avg_loss, 1e-12))
    return 100.0 - 100.0 / (1.0 + rs)


def dmi_adx(high: np.ndarray, low: np.ndarray, close: np.ndarray, period: int = 14) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    up = high - np.r_[high[0], high[:-1]]
    down = np.r_[low[0], low[:-1]] - low
    plus_dm = np.where((up > down) & (up > 0), up, 0.0)
    minus_dm = np.where((down > up) & (down > 0), down, 0.0)
    atr = atr_rma(high, low, close, period)
    plus_di = 100.0 * rma(plus_dm, period) / np.maximum(atr, 1e-12)
    minus_di = 100.0 * rma(minus_dm, period) / np.maximum(atr, 1e-12)
    dx = 100.0 * np.abs(plus_di - minus_di) / np.maximum(plus_di + minus_di, 1e-12)
    adx = rma(dx, period)
    return plus_di, minus_di, adx


def zscore(series: pd.Series, length: int) -> pd.Series:
    mean = series.rolling(length, min_periods=length).mean()
    sd = series.rolling(length, min_periods=length).std(ddof=0)
    return ((series - mean) / sd.replace(0, np.nan)).fillna(0.0)


def close_movement_pressure(series: pd.Series, move_bars: int, atr_length: int) -> pd.Series:
    move = series - series.shift(move_bars)
    one_bar_move = series.diff().abs()
    atr_proxy = one_bar_move.ewm(alpha=1.0 / atr_length, adjust=False, min_periods=atr_length).mean()
    return (move / atr_proxy.replace(0, np.nan)).replace([np.inf, -np.inf], np.nan).fillna(0.0)


def xa_code(close: pd.Series) -> pd.Series:
    slow = close.rolling(21, min_periods=21).mean()
    fast = close.ewm(span=9, adjust=False, min_periods=9).mean()
    code = pd.Series(0, index=close.index, dtype="float64")
    code[(fast > slow) & (close > fast)] = 2
    code[(fast > slow) & ~(close > fast)] = 1
    code[(fast < slow) & (close < fast)] = -2
    code[(fast < slow) & ~(close < fast)] = -1
    return code.fillna(0.0)


def load_bars(source: Path) -> pd.DataFrame:
    suffix = "".join(source.suffixes).lower()
    if suffix.endswith(".parquet"):
        df = pd.read_parquet(source)
        ts_col = "ts" if "ts" in df.columns else "ts_event"
        required = {ts_col, "open", "high", "low", "close", "volume"}
        missing = required.difference(df.columns)
        if missing:
            raise SystemExit(f"{source} missing columns: {sorted(missing)}")
        df = df.rename(columns={ts_col: "ts"}).copy()
    elif suffix.endswith(".csv") or suffix.endswith(".csv.zst"):
        df = pd.read_csv(source)
        ts_col = "ts" if "ts" in df.columns else "ts_event"
        required = {ts_col, "open", "high", "low", "close", "volume"}
        missing = required.difference(df.columns)
        if missing:
            raise SystemExit(f"{source} missing columns: {sorted(missing)}")
        df = df.rename(columns={ts_col: "ts"}).copy()
    else:
        raise SystemExit(f"Unsupported source type: {source}")

    df["ts"] = pd.to_datetime(df["ts"], utc=True)
    for col in ("open", "high", "low", "close", "volume"):
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.dropna(subset=["ts", "open", "high", "low", "close"]).sort_values("ts")
    return df[["ts", "open", "high", "low", "close", "volume"]].reset_index(drop=True)


def normalize_to_timeframe(df: pd.DataFrame, timeframe_min: int) -> pd.DataFrame:
    ts = pd.to_datetime(df["ts"], utc=True)
    diffs = ts.sort_values().diff().dropna()
    target_seconds = timeframe_min * 60
    median_seconds = diffs.dt.total_seconds().median() if not diffs.empty else target_seconds
    if median_seconds <= 90:
        s = df.set_index("ts").sort_index()
        out = s.resample(f"{timeframe_min}min", label="left", closed="left").agg(
            open=("open", "first"),
            high=("high", "max"),
            low=("low", "min"),
            close=("close", "last"),
            volume=("volume", "sum"),
        )
        return out.dropna(subset=["close"]).reset_index()
    return df.copy().sort_values("ts").reset_index(drop=True)


def zigzag_anchors(high: np.ndarray, low: np.ndarray, close: np.ndarray, atr10: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    n = len(close)
    anchor_high = np.full(n, np.nan)
    anchor_low = np.full(n, np.nan)
    anchor_high_bar = np.full(n, -1, dtype=np.int64)
    anchor_low_bar = np.full(n, -1, dtype=np.int64)
    pivots: list[tuple[int, float, int]] = []
    swing_high = float(high[0])
    swing_high_idx = 0
    swing_low = float(low[0])
    swing_low_idx = 0
    last_dir = 0
    for i in range(n):
        if close[i] > 0 and np.isfinite(atr10[i]):
            threshold_pct = max((atr10[i] / close[i]) * 100.0 * FIB_DEVIATION, FIB_THRESHOLD_FLOOR_PCT)
        else:
            threshold_pct = FIB_THRESHOLD_FLOOR_PCT
        threshold_abs = threshold_pct * 0.01 * close[i]
        if high[i] > swing_high:
            swing_high = float(high[i])
            swing_high_idx = i
        if low[i] < swing_low:
            swing_low = float(low[i])
            swing_low_idx = i
        if last_dir != 1 and (swing_high - low[i]) >= threshold_abs:
            if not pivots or (i - pivots[-1][0]) >= FIB_DEPTH:
                pivots.append((swing_high_idx, swing_high, 1))
                last_dir = 1
                swing_low = float(low[i])
                swing_low_idx = i
        elif last_dir != -1 and (high[i] - swing_low) >= threshold_abs:
            if not pivots or (i - pivots[-1][0]) >= FIB_DEPTH:
                pivots.append((swing_low_idx, swing_low, -1))
                last_dir = -1
                swing_high = float(high[i])
                swing_high_idx = i
        if len(pivots) >= 2:
            a, b = pivots[-2], pivots[-1]
            hp, lp = (a, b) if a[2] > 0 else (b, a)
            anchor_high[i] = hp[1]
            anchor_low[i] = lp[1]
            anchor_high_bar[i] = hp[0]
            anchor_low_bar[i] = lp[0]
    return anchor_high, anchor_low, anchor_high_bar, anchor_low_bar


def htf_confluence(df: pd.DataFrame, p_pivot: np.ndarray, p_382: np.ndarray, p_618: np.ndarray, fib_range: np.ndarray) -> np.ndarray:
    s = df.set_index("ts").sort_index()
    high_1h = s["high"].resample("1h", label="left", closed="left").max()
    low_1h = s["low"].resample("1h", label="left", closed="left").min()
    htf_high = high_1h.rolling(55, min_periods=55).max()
    htf_low = low_1h.rolling(55, min_periods=55).min()
    htf_range = htf_high - htf_low
    htf = pd.DataFrame(index=htf_high.index)
    htf["p382"] = htf_low + htf_range * FIB_382
    htf["p500"] = htf_low + htf_range * FIB_PIVOT
    htf["p618"] = htf_low + htf_range * FIB_618
    aligned = htf.reindex(s.index, method="ffill")
    tol = fib_range * HTF_CONF_TOL_PCT * 0.01
    total = np.zeros(len(df), dtype=float)
    for level in (p_pivot, p_382, p_618):
        for col in ("p382", "p500", "p618"):
            ref = aligned[col].to_numpy(dtype=float)
            total += np.where(np.isfinite(level) & np.isfinite(ref) & (np.abs(level - ref) <= tol), 1.0, 0.0)
    return total


def prior_day_week_levels(df: pd.DataFrame) -> pd.DataFrame:
    s = df.set_index("ts").sort_index()
    daily = s.resample("1D").agg(pdh=("high", "max"), pdl=("low", "min")).shift(1)
    weekly = s.resample("1W-MON", label="left", closed="left").agg(pwh=("high", "max"), pwl=("low", "min")).shift(1)
    levels = daily.reindex(s.index, method="ffill").join(weekly.reindex(s.index, method="ffill"))
    return levels.reset_index(drop=True)


def compute_base_features(df_5m: pd.DataFrame) -> pd.DataFrame:
    df = df_5m.copy().reset_index(drop=True)
    n = len(df)
    open_ = df["open"].to_numpy(dtype=float)
    high = df["high"].to_numpy(dtype=float)
    low = df["low"].to_numpy(dtype=float)
    close = df["close"].to_numpy(dtype=float)
    volume = df["volume"].fillna(0).to_numpy(dtype=float)

    atr14 = atr_rma(high, low, close, 14)
    atr10 = atr_rma(high, low, close, 10)
    rsi14 = rsi_rma(close, RSI_LEN)
    slow_ma = sma(close, MA_SLOW_LEN)
    fast_ma = ema(close, MA_FAST_LEN)
    ma_bull = fast_ma > slow_ma
    ma_bear = fast_ma < slow_ma
    plus_di, minus_di, adx = dmi_adx(high, low, close, 14)

    bar_range = high - low
    body_size = np.abs(close - open_)
    bullish = close > open_
    bearish = close < open_
    upper_wick = high - np.maximum(open_, close)
    lower_wick = np.minimum(open_, close) - low
    upper_wick_ratio = np.where(bar_range > 0, upper_wick / np.maximum(bar_range, 1e-12), 0.0)
    lower_wick_ratio = np.where(bar_range > 0, lower_wick / np.maximum(bar_range, 1e-12), 0.0)
    body_ratio = np.where(bar_range > 0, body_size / np.maximum(bar_range, 1e-12), 0.0)

    pat_rising_window = np.r_[False, bullish[1:] & (low[1:] > high[:-1])]
    pat_bear_engulf = np.r_[False, bearish[1:] & bullish[:-1] & (close[1:] < open_[:-1]) & (open_[1:] > close[:-1])]
    pat_marubozu_black = bearish & (body_ratio >= 0.85) & (upper_wick_ratio <= 0.10) & (lower_wick_ratio <= 0.10)
    pat_tweezer_top = np.r_[False, bearish[1:] & (np.abs(high[1:] - high[:-1]) <= atr14[1:] * 0.05) & bullish[:-1]]

    anchors_high, anchors_low, _ahb, _alb = zigzag_anchors(high, low, close, atr10)
    fib_range = anchors_high - anchors_low
    is_valid = np.isfinite(anchors_high) & np.isfinite(anchors_low) & (fib_range >= MIN_FIB_RANGE_ATR * atr14)
    midpoint = anchors_low + fib_range * 0.5
    hyst = fib_range * FIB_HYSTERESIS_PCT * 0.01
    fib_bull = np.ones(n, dtype=bool)
    state = True
    for i in range(n):
        if is_valid[i]:
            if close[i] >= midpoint[i] + hyst[i]:
                state = True
            elif close[i] <= midpoint[i] - hyst[i]:
                state = False
        else:
            state = True
        fib_bull[i] = state
    direction = np.where(fib_bull, 1, -1)
    fib_base = np.where(fib_bull, anchors_low, anchors_high)
    fib_dir = np.where(fib_bull, 1.0, -1.0)

    def fib_price(ratio: float) -> np.ndarray:
        return np.where(fib_range > 0, fib_base + fib_dir * fib_range * ratio, np.nan)

    p_382 = fib_price(FIB_382)
    p_pivot = fib_price(FIB_PIVOT)
    p_618 = fib_price(FIB_618)
    p_786 = fib_price(FIB_786)
    p_t1 = fib_price(FIB_T1)

    zone_upper = np.maximum(p_618, p_786)
    zone_lower = np.minimum(p_618, p_786)
    break_in_dir = np.zeros(n, dtype=bool)
    break_in_dir[1:] = np.where(
        direction[1:] == 1,
        (close[1:] > zone_upper[1:]) & (close[:-1] <= zone_upper[1:]),
        (close[1:] < zone_lower[1:]) & (close[:-1] >= zone_lower[1:]),
    )
    bars_since_break = np.full(n, -1.0)
    last_break = -1
    for i, flag in enumerate(break_in_dir):
        if flag:
            last_break = i
        bars_since_break[i] = -1.0 if last_break < 0 else float(i - last_break)

    bsl = pd.Series(high).rolling(LIQ_LOOKBACK_BARS, min_periods=LIQ_LOOKBACK_BARS).max().shift(1).to_numpy()
    ssl = pd.Series(low).rolling(LIQ_LOOKBACK_BARS, min_periods=LIQ_LOOKBACK_BARS).min().shift(1).to_numpy()
    swept_bsl = (high > bsl) & (close < bsl)
    swept_ssl = (low < ssl) & (close > ssl)
    reclaimed_bsl = np.r_[False, swept_bsl[:-1] & (close[1:] < bsl[1:])]
    reclaimed_ssl = np.r_[False, swept_ssl[:-1] & (close[1:] > ssl[1:])]
    liq_bull = swept_ssl | reclaimed_ssl
    liq_bear = swept_bsl | reclaimed_bsl
    bars_since_liq_bull = bars_since_event(liq_bull)
    bars_since_liq_bear = bars_since_event(liq_bear)
    recent_liq_bull = (bars_since_liq_bull >= 0) & (bars_since_liq_bull < LIQ_RECENCY_BARS)
    recent_liq_bear = (bars_since_liq_bear >= 0) & (bars_since_liq_bear < LIQ_RECENCY_BARS)

    eqh_tol = atr14 * (EQH_TOL_PCT / 100.0)
    hi_taps = np.zeros(n, dtype=int)
    lo_taps = np.zeros(n, dtype=int)
    for i in range(n):
        lo_idx = max(0, i - EQH_LOOKBACK)
        if i > lo_idx and np.isfinite(eqh_tol[i]):
            hi_taps[i] = int(np.sum(np.abs(high[lo_idx:i] - high[i]) <= eqh_tol[i]))
            lo_taps[i] = int(np.sum(np.abs(low[lo_idx:i] - low[i]) <= eqh_tol[i]))
    last_eqh = pd.Series(np.where(hi_taps >= EQH_MIN_TAPS, high, np.nan)).ffill().to_numpy()
    last_eql = pd.Series(np.where(lo_taps >= EQH_MIN_TAPS, low, np.nan)).ffill().to_numpy()

    vwap_session = session_vwap(df, volume)
    vol_z = zscore(pd.Series(volume), VOL_Z_LEN).to_numpy(dtype=float)
    htf_conf_total = htf_confluence(df, p_pivot, p_382, p_618, fib_range)
    levels = prior_day_week_levels(df)

    touched500_long = np.r_[False, (direction[1:] == 1) & np.isfinite(p_pivot[1:]) & (close[:-1] > p_pivot[1:]) & (low[1:] <= p_pivot[1:]) & (close[1:] >= p_pivot[1:])]
    touched618_long = np.r_[False, (direction[1:] == 1) & np.isfinite(p_618[1:]) & (close[:-1] > p_618[1:]) & (low[1:] <= p_618[1:]) & (close[1:] >= p_618[1:])]
    touched786_long = np.r_[False, (direction[1:] == 1) & np.isfinite(p_786[1:]) & (close[:-1] > p_786[1:]) & (low[1:] <= p_786[1:]) & (close[1:] >= p_786[1:])]
    touched500_short = np.r_[False, (direction[1:] == -1) & np.isfinite(p_pivot[1:]) & (close[:-1] < p_pivot[1:]) & (high[1:] >= p_pivot[1:]) & (close[1:] <= p_pivot[1:])]
    touched618_short = np.r_[False, (direction[1:] == -1) & np.isfinite(p_618[1:]) & (close[:-1] < p_618[1:]) & (high[1:] >= p_618[1:]) & (close[1:] <= p_618[1:])]
    touched786_short = np.r_[False, (direction[1:] == -1) & np.isfinite(p_786[1:]) & (close[:-1] < p_786[1:]) & (high[1:] >= p_786[1:]) & (close[1:] <= p_786[1:])]
    trigger_long = touched500_long | touched618_long | touched786_long
    trigger_short = touched500_short | touched618_short | touched786_short
    entry_level = np.where(
        touched786_long | touched786_short,
        p_786,
        np.where(touched618_long | touched618_short, p_618, np.where(touched500_long | touched500_short, p_pivot, np.nan)),
    )
    fib_touch_level_code = np.where(touched500_long | touched500_short, 500.0, np.where(touched618_long | touched618_short, 618.0, np.where(touched786_long | touched786_short, 786.0, 0.0)))

    out = pd.DataFrame(
        {
            "ts": df["ts"],
            "open": open_,
            "high": high,
            "low": low,
            "close": close,
            "volume": volume,
            "ml_atr14": atr14,
            "ml_dir": direction.astype(float),
            "ml_fib_range": fib_range,
            "ml_pivot_dist_atr": safe_div(close - p_pivot, atr14),
            "ml_p618_dist_atr": safe_div(close - p_618, atr14),
            "ml_bars_since_break": bars_since_break,
            "ml_break_in_dir": break_in_dir.astype(float),
            "ml_rsi_value": rsi14,
            "ml_rsi_stance_code": np.where(rsi14 <= RSI_OVERSOLD, 1.0, np.where(rsi14 >= RSI_OVERBOUGHT, -1.0, 0.0)),
            "ml_ma_bias": np.where(ma_bull, 1.0, np.where(ma_bear, -1.0, 0.0)),
            "ml_ma_slow_dist_atr": safe_div(close - slow_ma, atr14),
            "ml_ma_fast_dist_atr": safe_div(close - fast_ma, atr14),
            "ml_adx_value": adx,
            "ml_adx_plus_di": plus_di,
            "ml_adx_minus_di": minus_di,
            "ml_pat_rising_window": pat_rising_window.astype(float),
            "ml_pat_bear_engulf": pat_bear_engulf.astype(float),
            "ml_pat_marubozu_black": pat_marubozu_black.astype(float),
            "ml_pat_tweezer_top": pat_tweezer_top.astype(float),
            "ml_bsl_dist_atr": safe_div(bsl - close, atr14),
            "ml_ssl_dist_atr": safe_div(close - ssl, atr14),
            "ml_swept_bsl": swept_bsl.astype(float),
            "ml_swept_ssl": swept_ssl.astype(float),
            "ml_reclaimed_bsl": reclaimed_bsl.astype(float),
            "ml_reclaimed_ssl": reclaimed_ssl.astype(float),
            "ml_liq_eqh_dist_atr": safe_div(last_eqh - close, atr14),
            "ml_liq_eql_dist_atr": safe_div(close - last_eql, atr14),
            "ml_liq_vwap_dist_atr": safe_div(close - vwap_session, atr14),
            "ml_liq_vol_zscore": vol_z,
            "ml_htf_conf_total": htf_conf_total,
            "ml_lvl_pdh_dist_atr": safe_div(levels["pdh"].to_numpy(dtype=float) - close, atr14),
            "ml_lvl_pdl_dist_atr": safe_div(close - levels["pdl"].to_numpy(dtype=float), atr14),
            "ml_lvl_pwh_dist_atr": safe_div(levels["pwh"].to_numpy(dtype=float) - close, atr14),
            "ml_lvl_pwl_dist_atr": safe_div(close - levels["pwl"].to_numpy(dtype=float), atr14),
            "ml_trade_entry": entry_level,
            "ml_trade_tp": p_t1,
            "ml_fib_touch_level_code": fib_touch_level_code,
            "__trigger_long": trigger_long.astype(bool),
            "__trigger_short": trigger_short.astype(bool),
            "__recent_liq_bull": recent_liq_bull.astype(bool),
            "__recent_liq_bear": recent_liq_bear.astype(bool),
            "__is_valid": is_valid.astype(bool),
        }
    )
    return out


def safe_div(num: np.ndarray, denom: np.ndarray) -> np.ndarray:
    return np.divide(num, denom, out=np.zeros_like(num, dtype=float), where=np.isfinite(denom) & (np.abs(denom) > 1e-12))


def bars_since_event(mask: np.ndarray) -> np.ndarray:
    out = np.full(len(mask), -1, dtype=int)
    last = -1
    for i, flag in enumerate(mask):
        if bool(flag):
            last = i
        out[i] = -1 if last < 0 else i - last
    return out


def session_vwap(df: pd.DataFrame, volume: np.ndarray) -> np.ndarray:
    typical = (df["high"].to_numpy(dtype=float) + df["low"].to_numpy(dtype=float) + df["close"].to_numpy(dtype=float)) / 3.0
    dates = pd.to_datetime(df["ts"], utc=True).dt.date
    pv = pd.Series(typical * volume).groupby(dates).cumsum().to_numpy(dtype=float)
    vv = pd.Series(volume).groupby(dates).cumsum().to_numpy(dtype=float)
    return safe_div(pv, vv)


def align_series_to_index(series: pd.Series, target_index: pd.DatetimeIndex) -> pd.Series:
    s = series.copy()
    s.index = pd.to_datetime(s.index, utc=True)
    s = s[~s.index.duplicated(keep="last")].sort_index()
    return s.reindex(target_index, method="ffill").ffill().bfill()


def load_yahoo_dxy(target_index: pd.DatetimeIndex, start: pd.Timestamp, end: pd.Timestamp, interval: str) -> pd.Series:
    import yfinance as yf

    yf_start = (start - pd.Timedelta(days=7)).date().isoformat()
    yf_end = (end + pd.Timedelta(days=2)).date().isoformat()
    data = yf.download(
        "DX-Y.NYB",
        start=yf_start,
        end=yf_end,
        interval=interval,
        progress=False,
        auto_adjust=False,
        threads=False,
    )
    if data.empty:
        raise RuntimeError("Yahoo DX-Y.NYB returned no rows")
    if isinstance(data.columns, pd.MultiIndex):
        data.columns = [col[0] for col in data.columns]
    close_col = "Close" if "Close" in data.columns else "Adj Close"
    dxy = data[close_col].dropna()
    return align_series_to_index(dxy, target_index)


def merge_cross_assets(df: pd.DataFrame, cross_asset_path: Path | None, dxy_interval: str, use_yahoo_dxy: bool, vix_csv: Path | None, warnings: list[str]) -> pd.DataFrame:
    out = df.copy()
    idx = pd.DatetimeIndex(pd.to_datetime(out["ts"], utc=True))
    start = idx.min()
    end = idx.max()

    for symbol, col in (("NQ", "ml_xa_nq_code"), ("ZN", "ml_xa_zn_code")):
        out[col] = 0.0
    if cross_asset_path and cross_asset_path.exists():
        xa = pd.read_parquet(cross_asset_path)
        ts_col = "ts" if "ts" in xa.columns else "ts_event"
        xa[ts_col] = pd.to_datetime(xa[ts_col], utc=True)
        xa["close"] = pd.to_numeric(xa["close"], errors="coerce")
        xa = xa.dropna(subset=[ts_col, "close", "symbol"])
        for symbol, col in (("NQ", "ml_xa_nq_code"), ("ZN", "ml_xa_zn_code")):
            sym = xa.loc[xa["symbol"].astype(str).eq(symbol), [ts_col, "close"]].sort_values(ts_col)
            if sym.empty:
                warnings.append(f"cross-asset source missing {symbol}; {col}=0")
                continue
            close = sym.drop_duplicates(ts_col).set_index(ts_col)["close"]
            code = xa_code(close)
            out[col] = align_series_to_index(code, idx).to_numpy(dtype=float)
    else:
        warnings.append("cross-asset 1h source unavailable; NQ/ZN codes set to 0")

    if use_yahoo_dxy:
        dxy = load_yahoo_dxy(idx, start, end, dxy_interval)
        out["ml_xa_dxy_code"] = xa_code(dxy).to_numpy(dtype=float)
        dxy_arr = dxy.to_numpy(dtype=float)
        dxy_up = dxy_arr > np.r_[np.nan, dxy_arr[:-1]]
        close_arr = out["close"].to_numpy(dtype=float)
        mes_up = close_arr > np.r_[np.nan, close_arr[:-1]]
        out["ml_xa_dxy_diverge"] = ((mes_up & dxy_up) | (~mes_up & ~dxy_up)).astype(float)
        out["_dxy_close"] = dxy.to_numpy(dtype=float)
    else:
        out["ml_xa_dxy_code"] = 0.0
        out["ml_xa_dxy_diverge"] = 0.0
        warnings.append("Yahoo DXY disabled; DXY features set to 0")

    if vix_csv and vix_csv.exists():
        vix = pd.read_csv(vix_csv)
        date_col = "observation_date"
        value_col = "VIXCLS"
        vix[date_col] = pd.to_datetime(vix[date_col], utc=True)
        vix[value_col] = pd.to_numeric(vix[value_col], errors="coerce")
        vix_series = vix.dropna(subset=[value_col]).set_index(date_col)[value_col].sort_index()
        vix_aligned = align_series_to_index(vix_series, idx)
        out["ml_xa_vix_pressure"] = close_movement_pressure(vix_aligned, VIX_MOVE_BARS, VIX_ATR_LEN).to_numpy(dtype=float)
    else:
        out["ml_xa_vix_pressure"] = 0.0
        warnings.append("VIX CSV unavailable; VIX movement pressure set to 0")

    nq_proxy = out["ml_xa_nq_code"].replace(0, np.nan).ffill().fillna(0.0)
    out["ml_xa_corr_nq"] = (
        out["close"]
        .rolling(CORR_LEN, min_periods=CORR_LEN)
        .corr(nq_proxy)
        .replace([np.inf, -np.inf], np.nan)
        .fillna(0.0)
    )
    return out


def trade_members_for_window(zip_path: Path, start: pd.Timestamp, end: pd.Timestamp) -> list[str]:
    selected: list[str] = []
    with zipfile.ZipFile(zip_path) as zf:
        for name in zf.namelist():
            m = TRADES_MEMBER_RE.search(name)
            if not m:
                continue
            file_start = pd.Timestamp(m.group(1), tz="UTC")
            file_end = pd.Timestamp(m.group(2), tz="UTC") + pd.Timedelta(days=1)
            if file_end >= start and file_start <= end:
                selected.append(name)
    return selected


def _outright_pattern_for_root(symbol_root: str) -> re.Pattern[str]:
    root = str(symbol_root).upper().strip()
    if root not in OUTRIGHT_ROOT_PATTERNS:
        raise ValueError(f"Unsupported symbol root for order-flow filter: {symbol_root!r}")
    return OUTRIGHT_ROOT_PATTERNS[root]


def read_trade_chunks(
    zip_path: Path,
    members: list[str],
    start: pd.Timestamp,
    end: pd.Timestamp,
    symbol_root: str,
):
    import zstandard as zstd

    symbol_re = _outright_pattern_for_root(symbol_root)
    usecols = ["ts_event", "side", "price", "size", "symbol"]
    with zipfile.ZipFile(zip_path) as zf:
        for member in members:
            with zf.open(member) as raw:
                reader = zstd.ZstdDecompressor().stream_reader(raw)
                text = io.TextIOWrapper(reader, encoding="utf-8")
                for chunk in pd.read_csv(text, usecols=usecols, chunksize=500_000):
                    chunk["ts_event"] = pd.to_datetime(chunk["ts_event"], utc=True, format="ISO8601")
                    chunk = chunk.loc[(chunk["ts_event"] >= start) & (chunk["ts_event"] <= end)]
                    if chunk.empty:
                        continue
                    chunk = chunk.loc[chunk["symbol"].astype(str).str.match(symbol_re)]
                    if chunk.empty:
                        continue
                    chunk["price"] = pd.to_numeric(chunk["price"], errors="coerce")
                    chunk["size"] = pd.to_numeric(chunk["size"], errors="coerce").fillna(0.0)
                    chunk = chunk.dropna(subset=["price"])
                    if not chunk.empty:
                        yield chunk


def build_orderflow_features(
    df: pd.DataFrame,
    trades_zip: Path | None,
    gate_mode: str,
    warnings: list[str],
    symbol_root: str,
    bar_freq: str,
) -> pd.DataFrame:
    out = df.copy()
    idx = pd.DatetimeIndex(pd.to_datetime(out["ts"], utc=True))
    zeros = np.zeros(len(out), dtype=float)
    if not trades_zip or not trades_zip.exists():
        warnings.append("Databento trades zip unavailable; order-flow features set to 0")
        return assign_empty_orderflow(out, zeros)

    freq_delta = pd.to_timedelta(bar_freq)
    start = idx.min()
    end = idx.max() + freq_delta
    members = trade_members_for_window(trades_zip, start, end)
    if not members:
        warnings.append("No trades zip members overlap selected window; order-flow features set to 0")
        return assign_empty_orderflow(out, zeros)

    bar_aggs: list[pd.DataFrame] = []
    price_aggs: list[pd.DataFrame] = []
    for chunk in read_trade_chunks(trades_zip, members, start, end, symbol_root):
        chunk["bar_ts"] = chunk["ts_event"].dt.floor(bar_freq)
        side = chunk["side"].astype(str)
        size = chunk["size"].astype(float)
        chunk["buy_vol"] = np.where(side.eq("B"), size, 0.0)
        chunk["sell_vol"] = np.where(side.eq("A"), size, 0.0)
        chunk["signed_delta"] = chunk["buy_vol"] - chunk["sell_vol"]
        bar_aggs.append(
            chunk.groupby("bar_ts", as_index=True).agg(
                buy_vol=("buy_vol", "sum"),
                sell_vol=("sell_vol", "sum"),
                delta=("signed_delta", "sum"),
                total_trade_volume=("size", "sum"),
                trade_count=("size", "size"),
            )
        )
        price_aggs.append(chunk.groupby(["bar_ts", "price"], as_index=False)["size"].sum())

    if not bar_aggs:
        warnings.append(f"No {symbol_root} outright trade rows after filtering; order-flow features set to 0")
        return assign_empty_orderflow(out, zeros)

    bars = pd.concat(bar_aggs).groupby(level=0).sum().sort_index()
    bars = bars.reindex(idx, fill_value=0.0)
    profile = build_volume_profile(price_aggs, idx)
    bars = bars.join(profile, how="left")

    total = bars["buy_vol"] + bars["sell_vol"]
    delta = bars["delta"].astype(float)
    delta_pct = (delta / total.replace(0, np.nan) * 100.0).fillna(0.0)
    trade_vol = bars["total_trade_volume"].astype(float)
    volume_spike = (trade_vol / trade_vol.rolling(ORDERFLOW_ROLLING_LEN, min_periods=1).mean().replace(0, np.nan)).fillna(0.0)
    atr = out["ml_atr14"].replace(0, np.nan)
    atr_arr = atr.to_numpy(dtype=float)
    poc = bars["poc_price"]
    vah = bars["vah_price"]
    val = bars["val_price"]
    cvd = delta.groupby(idx.date).cumsum()

    close_arr = out["close"].to_numpy(dtype=float)
    high_arr = out["high"].to_numpy(dtype=float)
    low_arr = out["low"].to_numpy(dtype=float)
    vah_arr = vah.to_numpy(dtype=float)
    val_arr = val.to_numpy(dtype=float)
    cvd_arr = cvd.to_numpy(dtype=float)
    cvd_shift_arr = cvd.shift(10).to_numpy(dtype=float)
    delta_pct_arr = delta_pct.to_numpy(dtype=float)
    volume_spike_arr = volume_spike.to_numpy(dtype=float)

    out["ml_fp_delta_pct"] = delta_pct_arr
    poc_arr = poc.to_numpy(dtype=float)
    out["ml_fp_poc_dist_atr"] = ((close_arr - poc_arr) / atr_arr)
    out["ml_fp_poc_dist_atr"] = out["ml_fp_poc_dist_atr"].replace([np.inf, -np.inf], np.nan).fillna(0.0)
    out["ml_fp_va_position"] = np.where(close_arr > vah_arr, 1.0, np.where(close_arr < val_arr, -1.0, 0.0))
    out["ml_cvd_div_bull"] = (
        (low_arr < np.r_[np.full(10, np.nan), low_arr[:-10]])
        & (cvd_arr > cvd_shift_arr)
    ).astype(float)
    out["ml_cvd_div_bear"] = (
        (high_arr > np.r_[np.full(10, np.nan), high_arr[:-10]])
        & (cvd_arr < cvd_shift_arr)
    ).astype(float)

    out["ml_delta_imbalance_pct"] = out["ml_fp_delta_pct"]
    out["ml_delta_acceleration"] = delta.diff().fillna(0.0).to_numpy(dtype=float)
    out["ml_aggressor_pulse"] = (delta / delta.rolling(ORDERFLOW_ROLLING_LEN, min_periods=5).std(ddof=0).replace(0, np.nan)).replace([np.inf, -np.inf], np.nan).fillna(0.0).to_numpy(dtype=float)
    out["ml_volume_spike_ratio"] = volume_spike.to_numpy(dtype=float)
    poc_shift = np.r_[np.nan, np.diff(poc_arr)] / atr_arr
    out["ml_poc_shift"] = np.nan_to_num(poc_shift, nan=0.0, posinf=0.0, neginf=0.0)
    compressed_range = ((high_arr - low_arr) / atr_arr)
    compressed_range = np.nan_to_num(compressed_range, nan=0.0, posinf=0.0, neginf=0.0)
    out["ml_absorption_candidate"] = (
        (np.abs(delta_pct_arr) >= ORDERFLOW_ABSORPTION_DELTA_PCT)
        & (volume_spike_arr >= ORDERFLOW_EVENT_VOLUME_SPIKE)
        & (compressed_range <= ORDERFLOW_COMPRESSED_RANGE_ATR)
    ).astype(float)
    out["ml_flush_candidate"] = (
        (np.abs(delta_pct_arr) >= ORDERFLOW_FLUSH_DELTA_PCT)
        & (volume_spike_arr >= ORDERFLOW_EVENT_VOLUME_SPIKE)
        & (compressed_range > ORDERFLOW_COMPRESSED_RANGE_ATR)
    ).astype(float)

    if gate_mode in {"smoke", "strict"} and float(out["ml_fp_delta_pct"].abs().sum()) == 0.0:
        raise RuntimeError("Order-flow reconstruction produced all-zero fp delta")
    return out


def assign_empty_orderflow(df: pd.DataFrame, zeros: np.ndarray) -> pd.DataFrame:
    out = df.copy()
    for col in (
        "ml_fp_delta_pct",
        "ml_fp_poc_dist_atr",
        "ml_fp_va_position",
        "ml_cvd_div_bull",
        "ml_cvd_div_bear",
        "ml_delta_imbalance_pct",
        "ml_delta_acceleration",
        "ml_aggressor_pulse",
        "ml_absorption_candidate",
        "ml_flush_candidate",
        "ml_volume_spike_ratio",
        "ml_poc_shift",
    ):
        out[col] = zeros
    return out


def build_volume_profile(price_aggs: list[pd.DataFrame], target_index: pd.DatetimeIndex) -> pd.DataFrame:
    prices = pd.concat(price_aggs, ignore_index=True)
    prices = prices.groupby(["bar_ts", "price"], as_index=False)["size"].sum()
    rows: list[dict[str, Any]] = []
    for bar_ts, group in prices.groupby("bar_ts", sort=True):
        total = float(group["size"].sum())
        if total <= 0:
            continue
        sorted_by_vol = group.sort_values("size", ascending=False)
        poc_price = float(sorted_by_vol.iloc[0]["price"])
        chosen = sorted_by_vol.loc[sorted_by_vol["size"].cumsum() <= total * 0.70]
        if chosen.empty:
            chosen = sorted_by_vol.head(1)
        rows.append(
            {
                "bar_ts": bar_ts,
                "poc_price": poc_price,
                "vah_price": float(chosen["price"].max()),
                "val_price": float(chosen["price"].min()),
            }
        )
    profile = pd.DataFrame(rows)
    if profile.empty:
        return pd.DataFrame(index=target_index, columns=["poc_price", "vah_price", "val_price"], dtype=float)
    profile["bar_ts"] = pd.to_datetime(profile["bar_ts"], utc=True)
    return profile.set_index("bar_ts").reindex(target_index)


def finalize_entries(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    ma_long_ok = (out["ml_ma_bias"] > 0) if USE_MA_GATE else True
    ma_short_ok = (out["ml_ma_bias"] < 0) if USE_MA_GATE else True
    xa_long_agreement = (
        (out["ml_xa_nq_code"] > 0).astype(int)
        + (out["ml_xa_zn_code"] > 0).astype(int)
        + (out["ml_xa_dxy_code"] < 0).astype(int)
        + (out["ml_xa_vix_pressure"] < -VIX_PRESSURE_BAND).astype(int)
    )
    xa_short_agreement = (
        (out["ml_xa_nq_code"] < 0).astype(int)
        + (out["ml_xa_zn_code"] < 0).astype(int)
        + (out["ml_xa_dxy_code"] > 0).astype(int)
        + (out["ml_xa_vix_pressure"] > VIX_PRESSURE_BAND).astype(int)
    )
    long_ok = out["__is_valid"] & out["__trigger_long"] & ma_long_ok & (xa_long_agreement >= XA_MIN_AGREEMENT) & out["__recent_liq_bull"]
    short_ok = out["__is_valid"] & out["__trigger_short"] & ma_short_ok & (xa_short_agreement >= XA_MIN_AGREEMENT) & out["__recent_liq_bear"]
    out["ml_entry_long_trigger"] = long_ok.astype(float)
    out["ml_entry_short_trigger"] = short_ok.astype(float)
    return out.drop(columns=[c for c in out.columns if c.startswith("__")])


def validate_core_frame(df: pd.DataFrame, gate_mode: str) -> None:
    stale = [col for col in ("ml_xa_dx_code", "ml_bar_delta", "ml_net_delta_20") if col in df.columns]
    if stale:
        raise RuntimeError(f"stale/banned columns present: {stale}")
    missing = [col for col in ML_FEATURES if col not in df.columns]
    if missing:
        raise RuntimeError(f"missing locked ML_FEATURES: {missing}")
    if "ml_xa_dxy_code" not in df.columns or "ml_xa_dxy_diverge" not in df.columns:
        raise RuntimeError("DXY feature columns missing")
    if gate_mode == "strict":
        all_null = [col for col in ML_FEATURES if df[col].isna().all()]
        if all_null:
            raise RuntimeError(f"all-null feature columns: {all_null}")
    if gate_mode == "strict":
        entries = int(df["ml_entry_long_trigger"].sum() + df["ml_entry_short_trigger"].sum())
        if entries < 25:
            raise RuntimeError(f"strict gate failed: only {entries} entry candidates")
        if float(df["ml_fp_delta_pct"].abs().sum()) == 0.0:
            raise RuntimeError("strict gate failed: all-zero footprint delta")


def write_outputs(
    df: pd.DataFrame,
    out_dir: Path,
    symbol: str,
    timeframe: str,
    source: Path,
    trades_zip: Path | None,
    manifest_extra: dict[str, Any],
) -> tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    symbol_root = normalize_symbol_root(symbol)
    timeframe_text = str(timeframe).strip().removesuffix("m")
    csv_path = out_dir / f"{symbol_root.lower()}_{timeframe_text}m_core.csv"
    manifest_path = csv_path.with_suffix(".manifest.json")
    export = df.copy()
    export["ts"] = pd.to_datetime(export["ts"], utc=True).dt.strftime("%Y-%m-%dT%H:%M:%S%z")
    export.to_csv(csv_path, index=False)
    manifest = {
        "repo_commit": repo_commit(),
        "symbol": symbol_root,
        "symbol_root": symbol_root,
        "timeframe": timeframe_text,
        "trigger_family": TRIGGER_FAMILY,
        "source_kind": f"DATABENTO_{symbol_root}_CORE_ETL",
        "source_bars": str(source),
        "source_trades_zip": str(trades_zip) if trades_zip else None,
        "pine_file": PINE_FILE,
        "label_column": LABEL_COL,
        "feature_count_locked": len(ML_FEATURES),
        "feature_columns_locked": ML_FEATURES,
        "row_count": int(len(df)),
        "entry_long_count": int(df["ml_entry_long_trigger"].sum()),
        "entry_short_count": int(df["ml_entry_short_trigger"].sum()),
        "ts_first": pd.to_datetime(df["ts"], utc=True).min().isoformat(),
        "ts_last": pd.to_datetime(df["ts"], utc=True).max().isoformat(),
        "sha256": sha256_file(csv_path),
        "build_utc": datetime.now(timezone.utc).isoformat(),
        **manifest_extra,
    }
    manifest_path.write_text(json.dumps(manifest, indent=2, default=str))
    return csv_path, manifest_path


def main() -> int:
    ap = argparse.ArgumentParser(description="Build Warbird Pro V9 Core 5m/15m dataset")
    ap.add_argument("--symbol", choices=["ES"], default="ES")
    ap.add_argument("--timeframe", choices=["5", "15"], default="5")
    ap.add_argument("--source", type=Path, default=None)
    ap.add_argument("--trades-zip", type=Path, default=DEFAULT_TRADES_ZIP)
    ap.add_argument("--cross-asset-1h", type=Path, default=DEFAULT_CROSS_ASSET_1H)
    ap.add_argument("--vix-csv", type=Path, default=DEFAULT_VIX_CSV)
    ap.add_argument("--out-dir", type=Path, default=EXPORTS_DIR)
    ap.add_argument("--start", default=None)
    ap.add_argument("--end", default=None)
    ap.add_argument("--dxy-interval", default="1h", choices=["5m", "1h", "1d"])
    ap.add_argument("--base-regime-only", action="store_true",
                    help="Allow order-flow features to be zero-filled for a base/regime build.")
    ap.add_argument("--skip-yahoo-dxy", action="store_true")
    ap.add_argument("--gate-mode", choices=["schema", "smoke", "strict"], default="smoke")
    args = ap.parse_args()
    symbol_root = normalize_symbol_root(args.symbol)
    source_path = args.source or default_source_for_symbol(symbol_root)

    if not source_path.exists():
        raise SystemExit(f"Source bars not found: {source_path}")

    start = utc_ts(args.start)
    end = utc_ts(args.end)
    raw = load_bars(source_path)
    if start is not None:
        raw = raw.loc[raw["ts"] >= start]
    if end is not None:
        raw = raw.loc[raw["ts"] <= end]
    if raw.empty:
        raise SystemExit("No bar rows in selected window")

    timeframe_min = int(args.timeframe)
    bar_freq = f"{timeframe_min}min"

    bars_tf = normalize_to_timeframe(raw, timeframe_min)
    print(f"bars: {len(raw):,} source rows -> {len(bars_tf):,} {timeframe_min}m rows")
    print(f"range: {bars_tf['ts'].min()} -> {bars_tf['ts'].max()}")

    warnings: list[str] = []
    features = compute_base_features(bars_tf)
    features = merge_cross_assets(
        features,
        args.cross_asset_1h,
        args.dxy_interval,
        not args.skip_yahoo_dxy,
        args.vix_csv,
        warnings,
    )
    trades_zip = None if args.base_regime_only else args.trades_zip
    features = build_orderflow_features(
        features,
        trades_zip,
        args.gate_mode,
        warnings,
        symbol_root=symbol_root,
        bar_freq=bar_freq,
    )
    features = finalize_entries(features)

    validate_core_frame(features, args.gate_mode)
    csv_path, manifest_path = write_outputs(
        features,
        args.out_dir,
        symbol_root,
        args.timeframe,
        source_path,
        trades_zip,
        {
            "gate_mode": args.gate_mode,
            "base_regime_only": bool(args.base_regime_only),
            "dxy_source": None if args.skip_yahoo_dxy else "Yahoo Finance DX-Y.NYB",
            "dxy_interval": None if args.skip_yahoo_dxy else args.dxy_interval,
            "cross_asset_source": str(args.cross_asset_1h) if args.cross_asset_1h else None,
            "warnings": warnings,
            "orderflow_candidate_thresholds": {
                "rolling_len": ORDERFLOW_ROLLING_LEN,
                "absorption_delta_pct": ORDERFLOW_ABSORPTION_DELTA_PCT,
                "flush_delta_pct": ORDERFLOW_FLUSH_DELTA_PCT,
                "event_volume_spike": ORDERFLOW_EVENT_VOLUME_SPIKE,
                "compressed_range_atr": ORDERFLOW_COMPRESSED_RANGE_ATR,
            },
            "extra_candidate_features": [
                "ml_delta_imbalance_pct",
                "ml_delta_acceleration",
                "ml_aggressor_pulse",
                "ml_absorption_candidate",
                "ml_flush_candidate",
                "ml_volume_spike_ratio",
                "ml_poc_shift",
                "ml_fib_touch_level_code",
            ],
        },
    )
    print(f"entries: long={int(features['ml_entry_long_trigger'].sum())} short={int(features['ml_entry_short_trigger'].sum())}")
    if warnings:
        print("warnings:")
        for warning in warnings:
            print(f"  - {warning}")
    print(f"wrote {csv_path}")
    print(f"wrote {manifest_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
