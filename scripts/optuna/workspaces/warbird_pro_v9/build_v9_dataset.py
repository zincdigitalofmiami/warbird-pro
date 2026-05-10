#!/usr/bin/env python3
"""Build Warbird Pro V9 research replay rows from ES (or MES) 1m bars.

Reads data/<symbol>_1m.parquet, resamples to 5m, computes Pine indicator entry
triggers and fib context features in Python, writes a research CSV + manifest.
This is not accepted by the active warbird_pro_v9 TradingView-export profile
unless Kirk explicitly reopens a Databento replay lane and parity gate.

Reproduces deterministic logic of indicators/warbird-pro-v9.pine
sufficient for V9 ATR/risk exit modeling:
  - ZigZag deviation pivots (TradingView/ZigZag/7 semantics)
  - Fib anchor + ladder + midpoint regime with hysteresis
  - HTF 1h confluence
  - SMA(100) slow + EMA(close, 50) fast MA gate
  - RSI(14) extreme gate (75/25)
  - Candlestick pattern confirmation (3 bull, 4 bear)
  - Liquidity sweep confirmation
  - One-shot entry edge detection with cooldown

Output columns (CSV):
  ts (unix seconds, UTC), open, high, low, close, volume,
  ml_entry_long_trigger, ml_entry_short_trigger, fib_neg_0236_context,
  ma_sma, ema_close  -- audit-only, helpful for cross-check vs TV CSV

Run:
  python scripts/optuna/workspaces/warbird_pro_v9/build_v9_dataset.py \\
      --symbol ES --source data/es_1m.parquet
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[4]
PINE_FILE = "indicators/warbird-pro-v9.pine"
TRIGGER_FAMILY = "LIVE_ANCHOR_FOOTPRINT"
WORKSPACE = REPO_ROOT / "scripts" / "optuna" / "workspaces" / "warbird_pro_v9"
EXPORTS_DIR = WORKSPACE / "exports"

# Pine input defaults — must match LIVE indicator settings on TradingView exactly
FIB_DEVIATION = 3.0
FIB_DEPTH = 10
FIB_THRESHOLD_FLOOR_PCT = 0.15
MIN_FIB_RANGE_ATR = 0.5
FIB_HYSTERESIS_PCT = 2.0
FIB_CONFLUENCE_TOL_PCT = 0.05
HTF_CONF_TOL_PCT = 0.15

LENGTH_MA = 100
LENGTH_EMA = 50
RSI_LENGTH = 14
RSI_OVERBOUGHT = 75.0
RSI_OVERSOLD = 25.0
SIGNAL_COOLDOWN_BARS = 3
LIQ_SWEEP_LOOKBACK = 10
USE_MA_GATE = True
USE_PATTERN_CONFIRM = True
USE_ML_FILTER = False
USE_LIQUIDITY_SWEEP = False
GATE_SHORTS_IN_BULL_TREND = False
SHORT_GATE_RSI_FLOOR = 55.0
ONE_SHOT_EVENT = True
EXEC_ANCHOR_RATIO = 0.618
TRADE_STOP_ATR_MULT = 1.50

FIB_236 = 0.236
FIB_382 = 0.382
FIB_PIVOT = 0.5
FIB_618 = 0.618
FIB_786 = 0.786
FIB_T1 = 1.236


def repo_commit() -> str:
    try:
        out = subprocess.check_output(
            ["git", "-C", str(REPO_ROOT), "rev-parse", "HEAD"], text=True
        )
        return out.strip()
    except Exception:
        return "unknown"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


_OUTRIGHT_BY_ROOT = {
    "MES": __import__("re").compile(r"^MES[FGHJKMNQUVXZ]\d{1,2}$"),
    "ES": __import__("re").compile(r"^ES[FGHJKMNQUVXZ]\d{1,2}$"),
}


def _normalize_symbol_root(symbol: str) -> str:
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
    return "MES" if root.startswith("MES") else "ES" if root.startswith("ES") else root


def load_databento_csv(csv_path: Path, symbol_root: str) -> pd.DataFrame:
    """Load Databento OHLCV-1m CSV for one outright symbol family.

    Filters to outright ES or MES futures contracts only (no calendar spreads,
    no butterflies, no flies — those trade at tiny absolute prices and
    contaminate aggregation). Then collapses to continuous front-month by
    selecting the highest-volume outright contract per timestamp.
    Returns DataFrame with: ts (UTC), open, high, low, close, volume, symbol.
    """
    outright_re = _OUTRIGHT_BY_ROOT.get(symbol_root)
    if outright_re is None:
        raise ValueError(f"Unsupported symbol root for Databento loader: {symbol_root!r}")
    raw = pd.read_csv(csv_path)
    required = {"ts_event", "open", "high", "low", "close", "volume", "symbol"}
    missing = required.difference(raw.columns)
    if missing:
        raise ValueError(f"CSV missing required columns: {sorted(missing)}")
    raw["ts"] = pd.to_datetime(raw["ts_event"], utc=True)
    for col in ("open", "high", "low", "close"):
        raw[col] = pd.to_numeric(raw[col], errors="coerce")
    raw["volume"] = pd.to_numeric(raw["volume"], errors="coerce").fillna(0).astype("int64")
    raw = raw.dropna(subset=["open", "high", "low", "close"]).reset_index(drop=True)
    pre_n = len(raw)
    raw = raw.loc[raw["symbol"].astype(str).str.match(outright_re)].reset_index(drop=True)
    dropped = pre_n - len(raw)
    if dropped:
        print(f"  filtered {dropped:,} non-outright rows ({dropped/pre_n*100:.1f}%) — spreads/flies excluded")
    if raw.empty:
        raise ValueError(f"No outright {symbol_root} rows found in {csv_path}")
    front_idx = raw.groupby("ts")["volume"].idxmax()
    front = raw.loc[front_idx, ["ts", "open", "high", "low", "close", "volume", "symbol"]].copy()
    front = front.sort_values("ts").reset_index(drop=True)
    return front


def resample_to_timeframe(df_1m: pd.DataFrame, timeframe_minutes: int) -> pd.DataFrame:
    s = df_1m.set_index("ts").sort_index()
    agg = s.resample(f"{timeframe_minutes}min", label="left", closed="left").agg(
        open=("open", "first"),
        high=("high", "max"),
        low=("low", "min"),
        close=("close", "last"),
        volume=("volume", "sum"),
    )
    agg = agg.dropna(subset=["close"]).reset_index()
    return agg


def atr_rma(high: np.ndarray, low: np.ndarray, close: np.ndarray, period: int) -> np.ndarray:
    n = len(close)
    out = np.full(n, np.nan)
    if n < period:
        return out
    prev_close = np.empty(n)
    prev_close[0] = close[0]
    prev_close[1:] = close[:-1]
    tr = np.maximum(high - low, np.maximum(np.abs(high - prev_close), np.abs(low - prev_close)))
    out[period - 1] = float(np.nanmean(tr[:period]))
    alpha = 1.0 / period
    for i in range(period, n):
        out[i] = tr[i] * alpha + out[i - 1] * (1.0 - alpha)
    return out


def sma(x: np.ndarray, period: int) -> np.ndarray:
    return pd.Series(x).rolling(period, min_periods=period).mean().to_numpy()


def ema_of(x: np.ndarray, period: int) -> np.ndarray:
    return pd.Series(x).ewm(span=period, adjust=False, min_periods=period).mean().to_numpy()


def rsi_rma(close: np.ndarray, period: int) -> np.ndarray:
    n = len(close)
    out = np.full(n, np.nan)
    if n < period + 1:
        return out
    diff = np.diff(close, prepend=close[0])
    gain = np.where(diff > 0, diff, 0.0)
    loss = np.where(diff < 0, -diff, 0.0)
    avg_gain = np.full(n, np.nan)
    avg_loss = np.full(n, np.nan)
    avg_gain[period] = gain[1 : period + 1].mean()
    avg_loss[period] = loss[1 : period + 1].mean()
    alpha = 1.0 / period
    for i in range(period + 1, n):
        avg_gain[i] = gain[i] * alpha + avg_gain[i - 1] * (1.0 - alpha)
        avg_loss[i] = loss[i] * alpha + avg_loss[i - 1] * (1.0 - alpha)
    rs = np.where(avg_loss == 0, np.inf, avg_gain / np.maximum(avg_loss, 1e-12))
    out = 100.0 - 100.0 / (1.0 + rs)
    return out


def zigzag_pivots(
    high: np.ndarray,
    low: np.ndarray,
    close: np.ndarray,
    atr10: np.ndarray,
    deviation: float,
    threshold_floor_pct: float,
    depth: int,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """ZigZag deviation algorithm matching TradingView/ZigZag/7 semantics.

    Returns per-bar arrays (forward-filled from the most recent confirmed pivot pair):
      anchor_high_price, anchor_low_price, anchor_high_bar, anchor_low_bar.

    A pivot is confirmed when price moves >= threshold (% of close) in the
    opposite direction from a tracked swing extreme. Depth enforces a minimum
    bar separation between consecutive confirmed pivots.
    """
    n = len(close)
    anchor_high = np.full(n, np.nan)
    anchor_low = np.full(n, np.nan)
    anchor_high_bar = np.full(n, -1, dtype=np.int64)
    anchor_low_bar = np.full(n, -1, dtype=np.int64)

    pivots: list[tuple[int, float, int]] = []  # (idx, price, +1=high/-1=low)
    swing_high = float(high[0])
    swing_high_idx = 0
    swing_low = float(low[0])
    swing_low_idx = 0
    last_dir = 0

    for i in range(n):
        if not np.isnan(atr10[i]) and close[i] > 0:
            thr_pct = max((atr10[i] / close[i]) * 100.0 * deviation, threshold_floor_pct)
        else:
            thr_pct = threshold_floor_pct
        thr_abs = thr_pct * 0.01 * close[i]

        if high[i] > swing_high:
            swing_high = float(high[i])
            swing_high_idx = i
        if low[i] < swing_low:
            swing_low = float(low[i])
            swing_low_idx = i

        if last_dir != 1 and (swing_high - low[i]) >= thr_abs:
            if not pivots or (swing_high_idx - pivots[-1][0]) >= depth:
                pivots.append((swing_high_idx, swing_high, 1))
                last_dir = 1
                swing_low = float(low[i])
                swing_low_idx = i
        elif last_dir != -1 and (high[i] - swing_low) >= thr_abs:
            if not pivots or (swing_low_idx - pivots[-1][0]) >= depth:
                pivots.append((swing_low_idx, swing_low, -1))
                last_dir = -1
                swing_high = float(high[i])
                swing_high_idx = i

        if len(pivots) >= 2:
            p_a = pivots[-2]
            p_b = pivots[-1]
            if p_a[2] > 0:
                hp, lp = p_a, p_b
            else:
                hp, lp = p_b, p_a
            anchor_high[i] = hp[1]
            anchor_low[i] = lp[1]
            anchor_high_bar[i] = hp[0]
            anchor_low_bar[i] = lp[0]

    return anchor_high, anchor_low, anchor_high_bar, anchor_low_bar


def htf_1h_levels(frame: pd.DataFrame) -> pd.DataFrame:
    """Resample the active bar frame to 1h and broadcast levels back to that index."""
    s = frame.set_index("ts").sort_index()
    h_1h = s["high"].resample("1h", label="left", closed="left").max()
    l_1h = s["low"].resample("1h", label="left", closed="left").min()
    htf_high = h_1h.rolling(55, min_periods=55).max()
    htf_low = l_1h.rolling(55, min_periods=55).min()
    htf_range = (htf_high - htf_low).fillna(0.0)
    htf = pd.DataFrame(
        {
            "htf1h_high": htf_high,
            "htf1h_low": htf_low,
            "htf1h_range": htf_range,
        }
    )
    htf["htf1h_p382"] = htf["htf1h_low"] + htf["htf1h_range"] * FIB_382
    htf["htf1h_p500"] = htf["htf1h_low"] + htf["htf1h_range"] * FIB_PIVOT
    htf["htf1h_p618"] = htf["htf1h_low"] + htf["htf1h_range"] * FIB_618
    aligned = htf.reindex(s.index, method="ffill").reset_index(drop=True)
    return aligned


def compute_features(frame: pd.DataFrame) -> pd.DataFrame:
    df = frame.copy().reset_index(drop=True)
    n = len(df)
    open_ = df["open"].to_numpy(dtype=float)
    high = df["high"].to_numpy(dtype=float)
    low = df["low"].to_numpy(dtype=float)
    close = df["close"].to_numpy(dtype=float)

    atr14 = atr_rma(high, low, close, 14)
    atr10 = atr_rma(high, low, close, 10)
    rsi14 = rsi_rma(close, RSI_LENGTH)
    ma_sma_v = sma(close, LENGTH_MA)
    ema_close_v = ema_of(close, LENGTH_EMA)
    ma_bull = ema_close_v > ma_sma_v
    ma_bear = ema_close_v < ma_sma_v

    bar_range = high - low
    body_size = np.abs(close - open_)
    bullish_candle = close > open_
    bearish_candle = close < open_
    upper_wick = high - np.maximum(open_, close)
    lower_wick = np.minimum(open_, close) - low
    upper_wick_ratio = np.where(bar_range > 0, upper_wick / np.maximum(bar_range, 1e-12), 0.0)
    lower_wick_ratio = np.where(bar_range > 0, lower_wick / np.maximum(bar_range, 1e-12), 0.0)
    body_ratio = np.where(bar_range > 0, body_size / np.maximum(bar_range, 1e-12), 0.0)

    long_lower_shadow = (lower_wick_ratio >= 0.55) & (upper_wick_ratio <= 0.25)
    dragonfly_doji = (lower_wick_ratio >= 0.60) & (body_ratio <= 0.15)
    rising_window = np.empty(n, dtype=bool)
    rising_window[0] = False
    rising_window[1:] = low[1:] > high[:-1]

    long_upper_shadow = (upper_wick_ratio >= 0.55) & (lower_wick_ratio <= 0.25)
    shooting_star = (upper_wick_ratio >= 0.50) & (body_ratio <= 0.35) & bearish_candle
    bearish_engulfing = np.zeros(n, dtype=bool)
    bearish_engulfing[1:] = (
        bearish_candle[1:]
        & (close[:-1] > open_[:-1])
        & (close[1:] < open_[:-1])
        & (open_[1:] > close[:-1])
    )
    falling_window = np.empty(n, dtype=bool)
    falling_window[0] = False
    falling_window[1:] = high[1:] < low[:-1]

    proven_bull = long_lower_shadow | dragonfly_doji | rising_window
    proven_bear = long_upper_shadow | shooting_star | bearish_engulfing | falling_window

    swing_high_lb = (
        pd.Series(high).rolling(LIQ_SWEEP_LOOKBACK, min_periods=1).max().shift(1).to_numpy()
    )
    swing_low_lb = (
        pd.Series(low).rolling(LIQ_SWEEP_LOOKBACK, min_periods=1).min().shift(1).to_numpy()
    )
    liq_sweep_bull = (low < swing_low_lb) & (close > swing_low_lb)
    liq_sweep_bear = (high > swing_high_lb) & (close < swing_high_lb)

    anchor_high, anchor_low, _, _ = zigzag_pivots(
        high, low, close, atr10,
        deviation=FIB_DEVIATION,
        threshold_floor_pct=FIB_THRESHOLD_FLOOR_PCT,
        depth=FIB_DEPTH,
    )

    fib_range = anchor_high - anchor_low
    min_fib_range = MIN_FIB_RANGE_ATR * atr14
    is_valid = (~np.isnan(anchor_high)) & (~np.isnan(anchor_low)) & (fib_range >= min_fib_range)

    midpoint = anchor_low + fib_range * 0.5
    hyst_band = fib_range * (FIB_HYSTERESIS_PCT * 0.01)
    fib_bull = np.ones(n, dtype=bool)
    state = True
    for i in range(n):
        if is_valid[i]:
            if close[i] >= midpoint[i] + hyst_band[i]:
                state = True
            elif close[i] <= midpoint[i] - hyst_band[i]:
                state = False
        else:
            state = True
        fib_bull[i] = state

    fib_base = np.where(fib_bull, anchor_low, anchor_high)
    fib_dir = np.where(fib_bull, 1.0, -1.0)
    direction_code = np.where(fib_bull, 1, -1)

    def fib_price(ratio: float) -> np.ndarray:
        return np.where(fib_range > 0, fib_base + fib_dir * fib_range * ratio, np.nan)

    p_neg_236 = fib_price(-FIB_236)
    p_zero = fib_price(0.0)
    p_236 = fib_price(FIB_236)
    p_382 = fib_price(FIB_382)
    p_pivot = fib_price(FIB_PIVOT)
    p_618 = fib_price(FIB_618)
    p_786 = fib_price(FIB_786)
    p_one = fib_price(1.0)
    p_t1 = fib_price(FIB_T1)

    entry_zone_upper = np.maximum(p_pivot, p_786)
    entry_zone_lower = np.minimum(p_pivot, p_786)
    zone_upper = np.maximum(p_618, p_786)
    zone_lower = np.minimum(p_618, p_786)

    htf = htf_1h_levels(df)
    fib_range_safe = np.where(fib_range > 0, fib_range, np.nan)
    tol = fib_range_safe * HTF_CONF_TOL_PCT * 0.01

    def htf_hits(level_arr: np.ndarray) -> np.ndarray:
        hits = np.zeros(n, dtype=int)
        for col in ("htf1h_p382", "htf1h_p500", "htf1h_p618"):
            ref = htf[col].to_numpy(dtype=float)
            mask = (~np.isnan(ref)) & (~np.isnan(level_arr)) & (~np.isnan(tol))
            diff = np.abs(level_arr - ref)
            hits = hits + np.where(mask & (diff <= tol), 1, 0)
        return hits

    htf_conf_total = htf_hits(p_pivot) + htf_hits(p_382) + htf_hits(p_618)

    rsi_stance_bull = rsi14 <= RSI_OVERSOLD
    rsi_stance_bear = rsi14 >= RSI_OVERBOUGHT
    rsi_stance_code = np.where(
        rsi_stance_bull, 1.0, np.where(rsi_stance_bear, -1.0, 0.0)
    )

    short_gate = GATE_SHORTS_IN_BULL_TREND & ma_bull & (rsi14 >= SHORT_GATE_RSI_FLOOR)

    entry_level = fib_price(EXEC_ANCHOR_RATIO)
    entry_zone_touched = (
        (~np.isnan(entry_zone_upper))
        & (~np.isnan(entry_zone_lower))
        & (high >= entry_zone_lower)
        & (low <= entry_zone_upper)
    )
    entry_anchor_long = (~np.isnan(entry_level)) & (low <= entry_level) & (close >= entry_level)
    entry_anchor_short = (~np.isnan(entry_level)) & (high >= entry_level) & (close <= entry_level)

    long_struct = direction_code == 1
    short_struct = direction_code == -1
    long_pattern = proven_bull if USE_PATTERN_CONFIRM else np.ones(n, dtype=bool)
    short_pattern = proven_bear if USE_PATTERN_CONFIRM else np.ones(n, dtype=bool)
    long_sweep = liq_sweep_bull if USE_LIQUIDITY_SWEEP else np.ones(n, dtype=bool)
    short_sweep = liq_sweep_bear if USE_LIQUIDITY_SWEEP else np.ones(n, dtype=bool)
    if USE_MA_GATE:
        ma_long_ok = ma_bull
        ma_short_ok = ma_bear
    else:
        ma_long_ok = np.ones(n, dtype=bool)
        ma_short_ok = np.ones(n, dtype=bool)
    if USE_ML_FILTER:
        ml_long_ok = rsi_stance_bull
        ml_short_ok = rsi_stance_bear
    else:
        ml_long_ok = np.ones(n, dtype=bool)
        ml_short_ok = np.ones(n, dtype=bool)

    long_core = (
        is_valid
        & entry_zone_touched
        & entry_anchor_long
        & long_struct
        & long_pattern
        & long_sweep
        & ma_long_ok
        & ml_long_ok
    )
    short_core = (
        is_valid
        & entry_zone_touched
        & entry_anchor_short
        & short_struct
        & short_pattern
        & short_sweep
        & ma_short_ok
        & ml_short_ok
        & ~short_gate
    )

    long_signal_raw = np.zeros(n, dtype=bool)
    short_signal_raw = np.zeros(n, dtype=bool)
    last_signal_bar = -10**9
    for i in range(n):
        cooldown_ok = (i - last_signal_bar) >= SIGNAL_COOLDOWN_BARS
        long_signal_raw[i] = bool(long_core[i] and cooldown_ok)
        short_signal_raw[i] = bool(short_core[i] and cooldown_ok)
        if long_signal_raw[i] or short_signal_raw[i]:
            last_signal_bar = i

    if ONE_SHOT_EVENT:
        prev_long = np.roll(long_signal_raw, 1)
        prev_long[0] = False
        prev_short = np.roll(short_signal_raw, 1)
        prev_short[0] = False
        entry_long_trigger = long_signal_raw & ~prev_long
        entry_short_trigger = short_signal_raw & ~prev_short
    else:
        entry_long_trigger = long_signal_raw
        entry_short_trigger = short_signal_raw

    out = pd.DataFrame(
        {
            "ts": df["ts"],
            "open": close * 0 + open_,
            "high": high,
            "low": low,
            "close": close,
            "volume": df["volume"].astype("int64").to_numpy(),
            "ml_entry_long_trigger": entry_long_trigger.astype("float64"),
            "ml_entry_short_trigger": entry_short_trigger.astype("float64"),
            "fib_neg_0236_context": p_neg_236,
            "ma_sma": ma_sma_v,
            "ema_close": ema_close_v,
            "fib_range": fib_range,
            "ml_direction_code": direction_code.astype("float64"),
            "ml_rsi_value": rsi14,
            "ml_rsi_stance_code": rsi_stance_code,
            "htf_conf_total": htf_conf_total.astype("float64"),
        }
    )
    return out


def write_outputs(
    df_features: pd.DataFrame,
    symbol: str,
    timeframe: str,
    out_dir: Path,
    source_parquet: Path,
) -> tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    sym_norm = symbol.lower().replace("!", "").replace("1", "")
    csv_path = out_dir / f"{sym_norm}_{timeframe}m.csv"
    manifest_path = csv_path.with_suffix(".manifest.json")

    out = df_features.copy()
    out["ts"] = (
        pd.to_datetime(out["ts"], utc=True).astype("int64") // 10**9
    ).astype("int64")
    out.to_csv(csv_path, index=False)

    csv_hash = sha256_file(csv_path)
    ts_min = pd.to_datetime(df_features["ts"], utc=True).min().isoformat()
    ts_max = pd.to_datetime(df_features["ts"], utc=True).max().isoformat()
    rows = int(len(df_features))
    long_signals = int(df_features["ml_entry_long_trigger"].sum())
    short_signals = int(df_features["ml_entry_short_trigger"].sum())

    manifest = {
        "repo_commit": repo_commit(),
        "symbol": symbol,
        "timeframe": str(timeframe),
        "trigger_family": TRIGGER_FAMILY,
        "capture_method": "DATABENTO_TRAINING_CSV",
        "source_kind": "MES_1M_PARQUET_PYTHON_PIPELINE",
        "source_parquet": str(source_parquet),
        "ts_first": ts_min,
        "ts_last": ts_max,
        "row_count": rows,
        "long_signal_count": long_signals,
        "short_signal_count": short_signals,
        "sha256": csv_hash,
        "build_utc": datetime.now(timezone.utc).isoformat(),
        "pine_input_settings": {
            "fibDeviationManual": FIB_DEVIATION,
            "fibDepthManual": FIB_DEPTH,
            "fibThresholdFloorPct": FIB_THRESHOLD_FLOOR_PCT,
            "minFibRangeAtr": MIN_FIB_RANGE_ATR,
            "fibHysteresisPct": FIB_HYSTERESIS_PCT,
            "fibConfluenceTolPct": FIB_CONFLUENCE_TOL_PCT,
            "lengthMA": LENGTH_MA,
            "lengthEMA": LENGTH_EMA,
            "rsiLength": RSI_LENGTH,
            "rsiOverbought": RSI_OVERBOUGHT,
            "rsiOversold": RSI_OVERSOLD,
            "signalCooldownBars": SIGNAL_COOLDOWN_BARS,
            "liqSweepLookbackBarsInput": LIQ_SWEEP_LOOKBACK,
            "useMaGate": USE_MA_GATE,
            "usePatternConfirm": USE_PATTERN_CONFIRM,
            "useMlFilter": USE_ML_FILTER,
            "useLiquiditySweepConfirm": USE_LIQUIDITY_SWEEP,
            "gateShortsInBullTrend": GATE_SHORTS_IN_BULL_TREND,
            "shortGateRsiFloor": SHORT_GATE_RSI_FLOOR,
            "oneShotEvent": ONE_SHOT_EVENT,
            "optEntryLevelInput": str(EXEC_ANCHOR_RATIO),
            "tradeStopAtrMult": TRADE_STOP_ATR_MULT,
        },
        "notes": "Python reproduction of warbird-pro-v9.pine entry trigger logic "
                 "over single-symbol resampled bars. Research/parity-only unless "
                 "the active contract explicitly reopens a Databento replay lane.",
    }
    manifest_path.write_text(json.dumps(manifest, indent=2))
    return csv_path, manifest_path


def main() -> int:
    ap = argparse.ArgumentParser(description="Build Warbird Pro V9 dataset from 1m source bars")
    ap.add_argument("--symbol", required=True, help="Symbol root (MES, ES, MES1!, ES1!).")
    ap.add_argument("--source", required=True, type=Path,
                    help="Path to source 1m bars: Databento OHLCV-1m CSV/CSV.zst, "
                         "or legacy parquet (auto-detected by extension).")
    ap.add_argument("--out-dir", type=Path, default=EXPORTS_DIR, help="Output directory for CSV+manifest.")
    ap.add_argument("--start", default=None, help="ISO start date (UTC), e.g. 2020-01-01.")
    ap.add_argument("--end", default=None, help="ISO end date (UTC).")
    ap.add_argument("--timeframe", default="5", choices=["5", "15"], help="Output timeframe in minutes.")
    args = ap.parse_args()
    symbol_root = _normalize_symbol_root(args.symbol)

    if not args.source.exists():
        raise SystemExit(f"Source not found: {args.source}")

    suffix = "".join(args.source.suffixes).lower()
    if suffix.endswith(".csv") or suffix.endswith(".csv.zst"):
        df = load_databento_csv(args.source, symbol_root)
    elif suffix.endswith(".parquet"):
        df = pd.read_parquet(args.source)
        if "ts" not in df.columns:
            raise SystemExit(f"Parquet missing 'ts' column. Got: {list(df.columns)}")
        df["ts"] = pd.to_datetime(df["ts"], utc=True)
    else:
        raise SystemExit(f"Unsupported source extension: {suffix}")

    if args.start:
        df = df.loc[df["ts"] >= pd.Timestamp(args.start, tz="UTC")]
    if args.end:
        df = df.loc[df["ts"] <= pd.Timestamp(args.end, tz="UTC")]
    if df.empty:
        raise SystemExit("No rows in selected window.")

    print(f"  loaded {len(df):,} 1m bars from {df['ts'].min()} to {df['ts'].max()}")
    timeframe_minutes = int(args.timeframe)
    df_tf = resample_to_timeframe(df, timeframe_minutes)
    print(f"  resampled to {len(df_tf):,} {timeframe_minutes}m bars")
    features = compute_features(df_tf)
    print(f"  computed features for {len(features):,} bars")
    long_n = int(features["ml_entry_long_trigger"].sum())
    short_n = int(features["ml_entry_short_trigger"].sum())
    print(f"  long signals: {long_n}, short signals: {short_n}")

    csv_path, manifest_path = write_outputs(
        features, args.symbol, args.timeframe, args.out_dir, args.source
    )
    print(f"  wrote {csv_path}")
    print(f"  wrote {manifest_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
