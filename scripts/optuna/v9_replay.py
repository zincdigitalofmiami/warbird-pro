#!/usr/bin/env python3
"""Warbird Pro V9 Pine -> Python feature replay.

Mirrors `indicators/warbird-pro-v9.pine` bar-by-bar to derive the 50 ml_*
feature columns from raw MES 5m OHLCV. Parity intent (not bit-exact) — the
ZigZag pivot detection is a deviation-based approximation of the TradingView
ZigZag/7 library since that library is closed-source.

Inputs:
  data/mes_5m.parquet  (cols: ts, open, high, low, close, volume, symbol)

Output (per call):
  pandas.DataFrame with columns: ts, open, high, low, close, volume, symbol,
  plus all ml_* feature columns required by warbird_pro_profile.py and
  warbird_pro_v9_profile.py.

Pine line references in comments tie each computation to the source.
"""
from __future__ import annotations

import math
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

# ===== Pine V9 input defaults (frozen per V9 contract) =====
LENGTH_MA = 13
LENGTH_EMA = 6
RSI_LENGTH = 14
ATR_LEN = 14
ATR_LEN_ZZ = 10  # ATR for ZigZag dynamic threshold

FIB_DEVIATION = 4.0
FIB_DEPTH = 20
FIB_THRESHOLD_FLOOR_PCT = 0.50
MIN_FIB_RANGE_ATR = 0.5
FIB_HYSTERESIS_PCT = 2.0

LIQ_LOOKBACK = 20
SIGNAL_COOLDOWN = 3
RETEST_CONTEXT = 3

OPT_ENTRY_RATIO = 0.618  # default entry anchor
TRADE_STOP_ATR_MULT = 1.50
TRADE_MAX_HOLD_BARS = 72

# Replay emits WIDE candidates so the Optuna filter lane has real material to
# optimize. Each gate is re-imposable via the filter HPO's boolean params
# (requireBullPatternLong, requireSweepConfirmLong, etc.). Live Pine stays tight.
USE_PATTERN_CONFIRM = False
USE_MA_GATE = False
USE_LIQ_SWEEP = False
USE_ML_FILTER = False
USE_EXHAUSTION = True
GATE_SHORTS_BULL = False
ONE_SHOT = True

EXHAUSTION_LEVEL_ATR_TOL = 0.10
RSI_OVERBOUGHT = 75.0
RSI_OVERSOLD = 25.0
SHORT_GATE_RSI_FLOOR = 55.0

HTF_CONF_TOL_PCT = 1.5  # widened per V9 audit; user-tunable in Pine

# Fib ratios
FIB_236 = 0.236
FIB_382 = 0.382
FIB_PIVOT = 0.5
FIB_618 = 0.618
FIB_786 = 0.786
FIB_T1 = 1.236
FIB_T2 = 1.618


# ===== TA primitives =====

def rma(values: np.ndarray, length: int) -> np.ndarray:
    """Wilder's RMA (Pine ta.rma / used by ta.atr / ta.rsi)."""
    n = len(values)
    out = np.full(n, np.nan)
    if n == 0:
        return out
    alpha = 1.0 / length
    # Seed: simple mean of first `length` values
    if n >= length:
        seed = float(np.nanmean(values[:length]))
        out[length - 1] = seed
        for i in range(length, n):
            v = values[i]
            prev = out[i - 1]
            out[i] = alpha * v + (1.0 - alpha) * prev if not math.isnan(v) else prev
    return out


def true_range(high: np.ndarray, low: np.ndarray, close: np.ndarray) -> np.ndarray:
    n = len(close)
    tr = np.zeros(n)
    tr[0] = high[0] - low[0]
    for i in range(1, n):
        tr[i] = max(
            high[i] - low[i],
            abs(high[i] - close[i - 1]),
            abs(low[i] - close[i - 1]),
        )
    return tr


def atr(high: np.ndarray, low: np.ndarray, close: np.ndarray, length: int) -> np.ndarray:
    return rma(true_range(high, low, close), length)


def rsi(close: np.ndarray, length: int) -> np.ndarray:
    n = len(close)
    out = np.full(n, np.nan)
    if n < length + 1:
        return out
    diff = np.diff(close, prepend=close[0])
    gains = np.where(diff > 0, diff, 0.0)
    losses = np.where(diff < 0, -diff, 0.0)
    avg_gain = rma(gains, length)
    avg_loss = rma(losses, length)
    for i in range(length, n):
        ag = avg_gain[i]
        al = avg_loss[i]
        if math.isnan(ag) or math.isnan(al) or al == 0:
            out[i] = 100.0 if al == 0 and ag > 0 else 50.0
            continue
        rs = ag / al
        out[i] = 100.0 - 100.0 / (1.0 + rs)
    return out


def sma(values: np.ndarray, length: int) -> np.ndarray:
    s = pd.Series(values)
    return s.rolling(length, min_periods=length).mean().to_numpy()


def ema(values: np.ndarray, length: int) -> np.ndarray:
    s = pd.Series(values)
    return s.ewm(span=length, adjust=False, min_periods=length).mean().to_numpy()


def rolling_max(values: np.ndarray, length: int) -> np.ndarray:
    return pd.Series(values).rolling(length, min_periods=length).max().to_numpy()


def rolling_min(values: np.ndarray, length: int) -> np.ndarray:
    return pd.Series(values).rolling(length, min_periods=length).min().to_numpy()


# ===== Candlestick patterns (Pine V9 lines 175-200) =====

def candlestick_patterns(o: np.ndarray, h: np.ndarray, l: np.ndarray, c: np.ndarray) -> dict[str, np.ndarray]:
    n = len(c)
    body = np.abs(c - o)
    rng = h - l
    body_ratio = np.where(rng > 0, body / rng, 0.0)
    upper_wick = h - np.maximum(o, c)
    lower_wick = np.minimum(o, c) - l
    upper_ratio = np.where(rng > 0, upper_wick / rng, 0.0)
    lower_ratio = np.where(rng > 0, lower_wick / rng, 0.0)
    bullish = c > o
    bearish = c < o

    def shift(arr: np.ndarray, k: int) -> np.ndarray:
        out = np.full_like(arr, fill_value=np.nan, dtype=float)
        if k > 0:
            out[k:] = arr[:-k]
        elif k < 0:
            out[:k] = arr[-k:]
        else:
            out[:] = arr
        return out

    o1, c1 = shift(o, 1), shift(c, 1)
    o2, c2 = shift(o, 2), shift(c, 2)
    bullish1, bearish1 = shift(bullish.astype(float), 1) > 0, shift(bearish.astype(float), 1) > 0
    bullish2, bearish2 = shift(bullish.astype(float), 2) > 0, shift(bearish.astype(float), 2) > 0
    body_ratio1 = shift(body_ratio, 1)
    c_lag1, c_lag2 = shift(c, 1), shift(c, 2)
    o_lag1, o_lag2 = shift(o, 1), shift(o, 2)

    pat = {}
    pat["ml_pat_hammer"] = (bullish & (body_ratio <= 0.35) & (lower_ratio >= 0.55) & (upper_ratio <= 0.20)).astype(float)
    pat["ml_pat_inv_hammer"] = (bullish & (body_ratio <= 0.35) & (upper_ratio >= 0.55) & (lower_ratio <= 0.20)).astype(float)
    pat["ml_pat_dragonfly"] = ((body_ratio <= 0.10) & (lower_ratio >= 0.65) & (upper_ratio <= 0.15)).astype(float)
    pat["ml_pat_bull_engulf"] = (bullish & bearish1 & (c > o1) & (o < c1)).astype(float)
    pat["ml_pat_piercing"] = (bullish & bearish1 & (o < c1) & (c >= (o1 + c1) / 2.0) & (c < o1)).astype(float)
    pat["ml_pat_morning_star"] = (bearish2 & (body_ratio1 <= 0.35) & bullish & (c >= (o2 + c2) / 2.0)).astype(float)
    pat["ml_pat_three_white"] = (
        bullish & bullish1 & bullish2
        & (c > c_lag1) & (c_lag1 > c_lag2)
        & (o > o_lag1) & (o_lag1 > o_lag2)
    ).astype(float)
    pat["ml_pat_shooting_star"] = (bearish & (body_ratio <= 0.35) & (upper_ratio >= 0.55) & (lower_ratio <= 0.20)).astype(float)
    pat["ml_pat_hanging_man"] = (bearish & (body_ratio <= 0.35) & (lower_ratio >= 0.55) & (upper_ratio <= 0.20)).astype(float)
    pat["ml_pat_gravestone"] = ((body_ratio <= 0.10) & (upper_ratio >= 0.65) & (lower_ratio <= 0.15)).astype(float)
    pat["ml_pat_bear_engulf"] = (bearish & bullish1 & (c < o1) & (o > c1)).astype(float)
    pat["ml_pat_dark_cloud"] = (bearish & bullish1 & (o > c1) & (c <= (o1 + c1) / 2.0) & (c > o1)).astype(float)
    pat["ml_pat_evening_star"] = (bullish2 & (body_ratio1 <= 0.35) & bearish & (c <= (o2 + c2) / 2.0)).astype(float)
    pat["ml_pat_three_black"] = (
        bearish & bearish1 & bearish2
        & (c < c_lag1) & (c_lag1 < c_lag2)
        & (o < o_lag1) & (o_lag1 < o_lag2)
    ).astype(float)
    return pat


# ===== ZigZag (deviation-based approximation of TV ZigZag/7) =====

@dataclass
class ZZPivot:
    bar: int
    price: float
    is_high: bool


def zigzag_pivots(
    high: np.ndarray,
    low: np.ndarray,
    close: np.ndarray,
    atr10: np.ndarray,
    deviation: float,
    depth: int,
    threshold_floor_pct: float,
) -> list[ZZPivot]:
    """Deviation-based ZigZag closely matching Pine TradingView/ZigZag/7 with
    dynamic threshold = max(ATR(10)/close*100*deviation, thresholdFloorPct)%."""
    n = len(close)
    pivots: list[ZZPivot] = []
    if n < depth:
        return pivots

    # Initial direction: compare extremes in first `depth` bars
    init_high = float(np.max(high[:depth]))
    init_low = float(np.min(low[:depth]))
    init_high_idx = int(np.argmax(high[:depth]))
    init_low_idx = int(np.argmin(low[:depth]))

    if init_high_idx > init_low_idx:
        # Last extreme is high → seed with low first then high
        pivots.append(ZZPivot(init_low_idx, init_low, False))
        pivots.append(ZZPivot(init_high_idx, init_high, True))
        looking_for_high = False
    else:
        pivots.append(ZZPivot(init_high_idx, init_high, True))
        pivots.append(ZZPivot(init_low_idx, init_low, False))
        looking_for_high = True

    last_pivot = pivots[-1]
    extreme_bar = last_pivot.bar
    extreme_price = last_pivot.price

    for i in range(max(init_high_idx, init_low_idx) + 1, n):
        c = close[i]
        a = atr10[i] if not math.isnan(atr10[i]) else 0.0
        thresh_pct = max(a / c * 100.0 * deviation, threshold_floor_pct) if c > 0 else threshold_floor_pct

        if looking_for_high:
            if high[i] > extreme_price:
                extreme_price = float(high[i])
                extreme_bar = i
            else:
                pct_move = (extreme_price - low[i]) / extreme_price * 100.0
                if pct_move >= thresh_pct and (i - extreme_bar) >= 1:
                    pivots.append(ZZPivot(extreme_bar, extreme_price, True))
                    looking_for_high = False
                    extreme_price = float(low[i])
                    extreme_bar = i
        else:
            if low[i] < extreme_price:
                extreme_price = float(low[i])
                extreme_bar = i
            else:
                pct_move = (high[i] - extreme_price) / extreme_price * 100.0 if extreme_price > 0 else 0.0
                if pct_move >= thresh_pct and (i - extreme_bar) >= 1:
                    pivots.append(ZZPivot(extreme_bar, extreme_price, False))
                    looking_for_high = True
                    extreme_price = float(high[i])
                    extreme_bar = i
    return pivots


# ===== Fib state machine =====

@dataclass
class FibState:
    anchor_high: float = math.nan
    anchor_low: float = math.nan
    anchor_high_bar: int = -1
    anchor_low_bar: int = -1
    last_break_bar: int = -1
    fib_bull: bool = True


def fib_price(base: float, direction: float, fib_range: float, ratio: float) -> float:
    if fib_range <= 0:
        return math.nan
    return base + direction * fib_range * ratio


# ===== Main replay =====

def _nq_trend_code_per_5m(ts: pd.Series) -> np.ndarray:
    """Per-5m-bar NQ 1h trend code from data/cross_asset_1h.parquet.

    Code: 2=STRONG_BULL, 1=BULL, 0=NEUTRAL/no-data, -1=BEAR, -2=STRONG_BEAR
    Mirrors Pine V9's f_xa_code(close, sma21, ema9) on NQ 1h bars.
    """
    n = len(ts)
    out = np.zeros(n, dtype=float)
    parq = Path("data/cross_asset_1h.parquet")
    if not parq.exists():
        return out
    df = pd.read_parquet(parq)
    nq = df[df["symbol"] == "NQ"].copy()
    if nq.empty:
        return out
    nq = nq.sort_values("ts").reset_index(drop=True)
    nq["ts"] = pd.to_datetime(nq["ts"], utc=True)
    nq["sma21"] = nq["close"].rolling(21, min_periods=21).mean()
    nq["ema9"] = nq["close"].ewm(span=9, adjust=False, min_periods=9).mean()
    nq["bucket"] = nq["ts"].dt.floor("1h")
    s = pd.DataFrame({"ts": pd.to_datetime(ts.values, utc=True)})
    s["bucket"] = s["ts"].dt.floor("1h")
    merged = s.merge(nq[["bucket", "close", "sma21", "ema9"]], on="bucket", how="left")
    c = merged["close"].to_numpy()
    slow = merged["sma21"].to_numpy()
    fast = merged["ema9"].to_numpy()
    valid = ~(np.isnan(c) | np.isnan(slow) | np.isnan(fast))
    out[valid & (fast > slow) & (c > fast)] = 2.0
    out[valid & (fast > slow) & (c <= fast)] = 1.0
    out[valid & (fast < slow) & (c < fast)] = -2.0
    out[valid & (fast < slow) & (c >= fast)] = -1.0
    return out


def _htf_levels_per_5m(ts: pd.Series, h: np.ndarray, l: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Compute 1h rolling-55 high/low and derive p382/p500/p618 per 5m bar.

    Mirrors Pine V9's request.security("60", [ta.highest(high,55), ta.lowest(low,55)],
    lookahead_off). For each 5m bar we use the 1h bar that closed on or before
    its timestamp; the rolling-55 window is shifted by 1 bar to enforce close-only.
    """
    n = len(h)
    s = pd.DataFrame({"ts": ts.values, "high": h, "low": l})
    s["bucket"] = s["ts"].dt.floor("1h")
    agg = s.groupby("bucket", sort=True).agg(h_max=("high", "max"), l_min=("low", "min")).reset_index()
    agg["h55"] = agg["h_max"].shift(1).rolling(55, min_periods=1).max()
    agg["l55"] = agg["l_min"].shift(1).rolling(55, min_periods=1).min()
    agg["rng"] = agg["h55"] - agg["l55"]
    agg["p382"] = agg["l55"] + agg["rng"] * 0.382
    agg["p500"] = agg["l55"] + agg["rng"] * 0.5
    agg["p618"] = agg["l55"] + agg["rng"] * 0.618
    merged = s.merge(agg[["bucket", "p382", "p500", "p618"]], on="bucket", how="left")
    return (
        merged["p382"].to_numpy(dtype=float),
        merged["p500"].to_numpy(dtype=float),
        merged["p618"].to_numpy(dtype=float),
    )


def replay(df: pd.DataFrame) -> pd.DataFrame:
    """Bar-by-bar replay of Pine V9 over OHLCV. Returns df + ml_* columns."""
    o = df["open"].to_numpy(dtype=float)
    h = df["high"].to_numpy(dtype=float)
    l = df["low"].to_numpy(dtype=float)
    c = df["close"].to_numpy(dtype=float)
    v = df["volume"].to_numpy(dtype=float)
    n = len(c)
    htf_p382, htf_p500, htf_p618 = _htf_levels_per_5m(df["ts"], h, l)
    nq_codes = _nq_trend_code_per_5m(df["ts"])

    # Base TA
    atr14 = atr(h, l, c, ATR_LEN)
    atr10 = atr(h, l, c, ATR_LEN_ZZ)
    rsi_v = rsi(c, RSI_LENGTH)
    x_ma = sma(c, LENGTH_MA)
    x_ema = ema(c, LENGTH_EMA)
    ma_bull = (x_ema > x_ma).astype(float)
    ma_bear = (x_ema < x_ma).astype(float)

    # Candlestick patterns (Pine V9 line refs in helper)
    pats = candlestick_patterns(o, h, l, c)
    bull_cols = [
        "ml_pat_hammer", "ml_pat_inv_hammer", "ml_pat_dragonfly",
        "ml_pat_bull_engulf", "ml_pat_piercing", "ml_pat_morning_star",
        "ml_pat_three_white",
    ]
    bear_cols = [
        "ml_pat_shooting_star", "ml_pat_hanging_man", "ml_pat_gravestone",
        "ml_pat_bear_engulf", "ml_pat_dark_cloud", "ml_pat_evening_star",
        "ml_pat_three_black",
    ]
    proven_bull = np.zeros(n)
    proven_bear = np.zeros(n)
    for col in bull_cols:
        proven_bull = np.maximum(proven_bull, pats[col])
    for col in bear_cols:
        proven_bear = np.maximum(proven_bear, pats[col])

    # Volume delta (Pine line ~256)
    rng = h - l
    close_pos = np.where(rng > 0, (c - l) / rng, 0.5)
    bar_delta = v * (2.0 * close_pos - 1.0)
    net_delta_20 = pd.Series(bar_delta).rolling(20, min_periods=1).sum().to_numpy()

    # Liquidity (Pine line ~270)
    bsl = np.roll(rolling_max(h, LIQ_LOOKBACK), 1)
    ssl = np.roll(rolling_min(l, LIQ_LOOKBACK), 1)
    bsl[0] = np.nan
    ssl[0] = np.nan
    swept_bsl = ((h > bsl) & (c < bsl)).astype(float)
    swept_ssl = ((l < ssl) & (c > ssl)).astype(float)
    swept_bsl_prev = np.roll(swept_bsl, 1); swept_bsl_prev[0] = 0.0
    swept_ssl_prev = np.roll(swept_ssl, 1); swept_ssl_prev[0] = 0.0
    reclaimed_bsl = ((swept_bsl_prev > 0) & (c < bsl)).astype(float)
    reclaimed_ssl = ((swept_ssl_prev > 0) & (c > ssl)).astype(float)

    bsl_dist_atr = np.where(atr14 > 0, (bsl - c) / atr14, 0.0)
    ssl_dist_atr = np.where(atr14 > 0, (c - ssl) / atr14, 0.0)

    # ZigZag → fib state machine
    pivots = zigzag_pivots(h, l, c, atr10, FIB_DEVIATION, FIB_DEPTH, FIB_THRESHOLD_FLOOR_PCT)
    pivot_bar_index: dict[int, ZZPivot] = {p.bar: p for p in pivots}

    fib = FibState()
    out_cols: dict[str, np.ndarray] = {
        "ml_atr14": atr14,
        "ml_dir": np.zeros(n),
        "ml_fib_range": np.zeros(n),
        "ml_pivot_dist_atr": np.zeros(n),
        "ml_p618_dist_atr": np.zeros(n),
        "ml_in_zone": np.zeros(n),
        "ml_bars_since_break": np.full(n, -1.0),
        "ml_break_in_dir": np.zeros(n),
        "ml_reject_at_zone": np.zeros(n),
        "ml_rsi_value": rsi_v,
        "ml_rsi_stance_code": np.where(rsi_v <= RSI_OVERSOLD, 1.0, np.where(rsi_v >= RSI_OVERBOUGHT, -1.0, 0.0)),
        "ml_ma_bias": np.where(ma_bull > 0, 1.0, np.where(ma_bear > 0, -1.0, 0.0)),
        "ml_bsl_dist_atr": bsl_dist_atr,
        "ml_ssl_dist_atr": ssl_dist_atr,
        "ml_swept_bsl": swept_bsl,
        "ml_swept_ssl": swept_ssl,
        "ml_reclaimed_bsl": reclaimed_bsl,
        "ml_reclaimed_ssl": reclaimed_ssl,
        "ml_bar_delta": bar_delta,
        "ml_net_delta_20": net_delta_20,
        "ml_xa_nq_code": nq_codes,
        # ZN and DX are not available in local cross_asset_1h.parquet — emitted
        # as constant 0 for schema parity. Trainer/HPO must NOT use these.
        "ml_xa_zn_code": np.zeros(n),
        "ml_xa_dx_code": np.zeros(n),
        "ml_exhaust_long": np.zeros(n),
        "ml_exhaust_short": np.zeros(n),
        "ml_entry_route_code": np.zeros(n),
        "ml_htf_conf_total": np.zeros(n),
        "ml_entry_long_trigger": np.zeros(n),
        "ml_entry_short_trigger": np.zeros(n),
        "ml_trade_entry": np.full(n, np.nan),
        "ml_trade_stop": np.full(n, np.nan),
        "ml_trade_tp": np.full(n, np.nan),
        "ml_last_exit_outcome": np.zeros(n),
        "ml_fib_neg_0236": np.full(n, np.nan),
    }
    for col in bull_cols + bear_cols:
        out_cols[col] = pats[col]

    # Trade state
    trade_active = False
    trade_side = 0
    trade_entry_price = math.nan
    trade_stop_price = math.nan
    trade_target_price = math.nan
    trade_entry_bar = -1
    last_signal_bar = -1
    last_long_signal_raw_prev = False
    last_short_signal_raw_prev = False

    for i in range(n):
        # Update fib anchor when we hit a confirmed pivot
        if i in pivot_bar_index:
            pv = pivot_bar_index[i]
            # Find the immediately preceding pivot of opposite kind
            preceding = None
            for p in reversed(pivots):
                if p.bar < i and p.is_high != pv.is_high:
                    preceding = p
                    break
            if preceding is not None:
                if pv.is_high:
                    fib.anchor_high = pv.price
                    fib.anchor_low = preceding.price
                    fib.anchor_high_bar = pv.bar
                    fib.anchor_low_bar = preceding.bar
                else:
                    fib.anchor_low = pv.price
                    fib.anchor_high = preceding.price
                    fib.anchor_low_bar = pv.bar
                    fib.anchor_high_bar = preceding.bar
                fib.last_break_bar = -1

        if math.isnan(fib.anchor_high) or math.isnan(fib.anchor_low):
            continue

        fib_range = fib.anchor_high - fib.anchor_low
        min_fib_range = MIN_FIB_RANGE_ATR * (atr14[i] if not math.isnan(atr14[i]) else 0.0)
        is_valid = fib_range >= min_fib_range and fib_range > 0
        if not is_valid:
            continue

        # Hysteresis-based fib_bull state
        midpoint = fib.anchor_low + fib_range * 0.5
        hyst = fib_range * (FIB_HYSTERESIS_PCT * 0.01)
        if c[i] >= midpoint + hyst:
            fib.fib_bull = True
        elif c[i] <= midpoint - hyst:
            fib.fib_bull = False

        base = fib.anchor_low if fib.fib_bull else fib.anchor_high
        direction = 1.0 if fib.fib_bull else -1.0

        p_pivot = fib_price(base, direction, fib_range, FIB_PIVOT)
        p_618 = fib_price(base, direction, fib_range, FIB_618)
        p_786 = fib_price(base, direction, fib_range, FIB_786)
        p_t1 = fib_price(base, direction, fib_range, FIB_T1)
        p_t2 = fib_price(base, direction, fib_range, FIB_T2)
        p_neg236 = fib_price(base, direction, fib_range, -FIB_236)
        out_cols["ml_fib_neg_0236"][i] = p_neg236

        zone_upper = max(p_618, p_786)
        zone_lower = min(p_618, p_786)
        entry_zone_upper = max(p_pivot, p_786)
        entry_zone_lower = min(p_pivot, p_786)

        dir_code = 1 if fib.fib_bull else -1
        out_cols["ml_dir"][i] = float(dir_code)
        out_cols["ml_fib_range"][i] = fib_range
        out_cols["ml_pivot_dist_atr"][i] = (c[i] - p_pivot) / atr14[i] if atr14[i] > 0 else 0.0
        out_cols["ml_p618_dist_atr"][i] = (c[i] - p_618) / atr14[i] if atr14[i] > 0 else 0.0

        # HTF confluence: count how many of {pivot, .382, .618} on the 5m fib match
        # the corresponding 1h fib level within tol = fib_range * HTF_CONF_TOL_PCT %.
        if fib_range > 0:
            tol = fib_range * HTF_CONF_TOL_PCT * 0.01
            hp382, hp500, hp618 = htf_p382[i], htf_p500[i], htf_p618[i]
            p_382_5m = fib_price(base, direction, fib_range, FIB_382)
            hits = 0
            if not math.isnan(hp382) and abs(p_382_5m - hp382) <= tol:
                hits += 1
            if not math.isnan(hp500) and abs(p_pivot - hp500) <= tol:
                hits += 1
            if not math.isnan(hp618) and abs(p_618 - hp618) <= tol:
                hits += 1
            out_cols["ml_htf_conf_total"][i] = float(hits)

        # Structural
        break_in_dir = False
        if i > 0:
            if dir_code == 1:
                break_in_dir = c[i] > zone_upper and c[i - 1] <= zone_upper
            else:
                break_in_dir = c[i] < zone_lower and c[i - 1] >= zone_lower
        if break_in_dir:
            fib.last_break_bar = i
        out_cols["ml_break_in_dir"][i] = 1.0 if break_in_dir else 0.0

        bars_since_break = i - fib.last_break_bar if fib.last_break_bar >= 0 else -1
        out_cols["ml_bars_since_break"][i] = float(bars_since_break)

        if dir_code == 1:
            reject_at_zone = h[i] >= zone_lower and c[i] < zone_lower
        else:
            reject_at_zone = l[i] <= zone_upper and c[i] > zone_upper
        out_cols["ml_reject_at_zone"][i] = 1.0 if reject_at_zone else 0.0

        entry_zone_touched = h[i] >= entry_zone_lower and l[i] <= entry_zone_upper
        out_cols["ml_in_zone"][i] = 1.0 if entry_zone_touched else 0.0

        entry_level = fib_price(base, direction, fib_range, OPT_ENTRY_RATIO)
        entry_anchor_long = (l[i] <= entry_level) and (c[i] >= entry_level)
        entry_anchor_short = (h[i] >= entry_level) and (c[i] <= entry_level)

        rsi_stance_bull = rsi_v[i] <= RSI_OVERSOLD if not math.isnan(rsi_v[i]) else False
        rsi_stance_bear = rsi_v[i] >= RSI_OVERBOUGHT if not math.isnan(rsi_v[i]) else False
        ma_b = ma_bull[i] > 0
        ma_brr = ma_bear[i] > 0

        long_pat_ok = (not USE_PATTERN_CONFIRM) or (proven_bull[i] > 0)
        short_pat_ok = (not USE_PATTERN_CONFIRM) or (proven_bear[i] > 0)
        long_sweep_ok = (not USE_LIQ_SWEEP) or (swept_ssl[i] > 0 or reclaimed_ssl[i] > 0)
        short_sweep_ok = (not USE_LIQ_SWEEP) or (swept_bsl[i] > 0 or reclaimed_bsl[i] > 0)
        long_ma_ok = (not USE_MA_GATE) or (ma_b and c[i] >= x_ema[i])
        short_ma_ok = (not USE_MA_GATE) or (ma_brr and c[i] <= x_ema[i])
        long_ml_ok = (not USE_ML_FILTER) or rsi_stance_bull
        short_ml_ok = (not USE_ML_FILTER) or rsi_stance_bear
        short_block = (
            GATE_SHORTS_BULL and ma_b
            and (rsi_v[i] >= SHORT_GATE_RSI_FLOOR if not math.isnan(rsi_v[i]) else False)
        )

        long_struct_ok = dir_code == 1
        short_struct_ok = dir_code == -1

        long_core = (
            entry_zone_touched and entry_anchor_long and long_struct_ok
            and long_pat_ok and long_sweep_ok and long_ma_ok and long_ml_ok
        )
        short_core = (
            entry_zone_touched and entry_anchor_short and short_struct_ok
            and short_pat_ok and short_sweep_ok and short_ma_ok and short_ml_ok
            and not short_block
        )

        cooldown_ok = last_signal_bar < 0 or (i - last_signal_bar) >= SIGNAL_COOLDOWN
        long_signal_raw = long_core and cooldown_ok
        short_signal_raw = short_core and cooldown_ok

        if ONE_SHOT:
            entry_long_trigger = long_signal_raw and not last_long_signal_raw_prev
            entry_short_trigger = short_signal_raw and not last_short_signal_raw_prev
        else:
            entry_long_trigger = long_signal_raw
            entry_short_trigger = short_signal_raw

        last_long_signal_raw_prev = long_signal_raw
        last_short_signal_raw_prev = short_signal_raw

        if entry_long_trigger or entry_short_trigger:
            last_signal_bar = i

        out_cols["ml_entry_long_trigger"][i] = 1.0 if entry_long_trigger else 0.0
        out_cols["ml_entry_short_trigger"][i] = 1.0 if entry_short_trigger else 0.0

        if entry_long_trigger or entry_short_trigger:
            out_cols["ml_entry_route_code"][i] = (
                (1 if USE_PATTERN_CONFIRM else 0)
                + (2 if USE_MA_GATE else 0)
                + (4 if USE_LIQ_SWEEP else 0)
                + (8 if USE_ML_FILTER else 0)
                + (16 if USE_EXHAUSTION else 0)
            )

        # Exhaustion (Pine line ~437)
        ext_touch_long = (
            (h[i] >= p_t1 - atr14[i] * EXHAUSTION_LEVEL_ATR_TOL)
            or (h[i] >= p_t2 - atr14[i] * EXHAUSTION_LEVEL_ATR_TOL)
        )
        ext_touch_short = (
            (l[i] <= p_t1 + atr14[i] * EXHAUSTION_LEVEL_ATR_TOL)
            or (l[i] <= p_t2 + atr14[i] * EXHAUSTION_LEVEL_ATR_TOL)
        )
        if USE_EXHAUSTION:
            if dir_code == 1 and ext_touch_long and proven_bear[i] > 0 and rsi_stance_bear:
                out_cols["ml_exhaust_long"][i] = 1.0
            if dir_code == -1 and ext_touch_short and proven_bull[i] > 0 and rsi_stance_bull:
                out_cols["ml_exhaust_short"][i] = 1.0

        # Trade engine
        if not trade_active:
            if entry_long_trigger:
                trade_active = True
                trade_side = 1
                trade_entry_price = entry_level
                trade_stop_price = entry_level - atr14[i] * TRADE_STOP_ATR_MULT
                trade_target_price = p_t1
                trade_entry_bar = i
            elif entry_short_trigger:
                trade_active = True
                trade_side = -1
                trade_entry_price = entry_level
                trade_stop_price = entry_level + atr14[i] * TRADE_STOP_ATR_MULT
                trade_target_price = p_t1
                trade_entry_bar = i
        else:
            if i > trade_entry_bar:
                stop_hit = False
                target_hit = False
                if trade_side == 1:
                    stop_hit = l[i] <= trade_stop_price
                    target_hit = h[i] >= trade_target_price
                else:
                    stop_hit = h[i] >= trade_stop_price
                    target_hit = l[i] <= trade_target_price
                time_out = (i - trade_entry_bar) >= TRADE_MAX_HOLD_BARS
                if stop_hit:
                    out_cols["ml_last_exit_outcome"][i] = -1
                    trade_active = False
                elif target_hit:
                    out_cols["ml_last_exit_outcome"][i] = 1
                    trade_active = False
                elif time_out:
                    out_cols["ml_last_exit_outcome"][i] = 2
                    trade_active = False

        if trade_active:
            out_cols["ml_trade_entry"][i] = trade_entry_price
            out_cols["ml_trade_stop"][i] = trade_stop_price
            out_cols["ml_trade_tp"][i] = trade_target_price

    out = df.copy().reset_index(drop=True)
    for col, arr in out_cols.items():
        out[col] = arr
    return out


def main(argv: list[str]) -> int:
    parquet_path = Path(argv[1]) if len(argv) > 1 else Path("data/mes_5m.parquet")
    out_path = Path(argv[2]) if len(argv) > 2 else Path("scripts/optuna/workspaces/warbird_pro/exports/databento_mes_5m_2020-2026.csv")

    print(f"loading {parquet_path}", flush=True)
    df = pd.read_parquet(parquet_path)
    print(f"  rows={len(df):,}  range={df['ts'].iloc[0]} -> {df['ts'].iloc[-1]}", flush=True)

    if "symbol" in df.columns:
        df = df[df["symbol"].astype(str).str.startswith("MES")].copy()
        df["symbol"] = "MES1!"

    # Filter Databento sentinel rows. MES has never traded below ~$1500 in our
    # window (2020 COVID low ~$2000); $500 is a safe absolute floor that drops
    # all sentinel rows (-1, 0, 0.05, 0.35, 49.45, 124.1, etc.) without losing
    # real bars. Then drop any remaining row with >50% deviation from prior
    # close as a belt-and-braces guard.
    n_before = len(df)
    floor_mask = (df["open"] < 500) | (df["high"] < 500) | (df["low"] < 500) | (df["close"] < 500)
    df = df.loc[~floor_mask].reset_index(drop=True)
    prev_close = df["close"].shift(1)
    dev_mask = (df["low"] < 0.5 * prev_close) | (df["close"] < 0.5 * prev_close)
    df = df.loc[~dev_mask].reset_index(drop=True)
    print(f"  dropped {n_before - len(df):,} sentinel/decimal-shift rows (kept {len(df):,})", flush=True)

    print("running V9 replay (this may take a couple minutes)...", flush=True)
    out = replay(df.reset_index(drop=True))
    out["ts"] = pd.to_datetime(out["ts"], utc=True)
    print(f"  output rows={len(out):,}  cols={len(out.columns)}", flush=True)

    long_trigs = int(out["ml_entry_long_trigger"].sum())
    short_trigs = int(out["ml_entry_short_trigger"].sum())
    exits = out["ml_last_exit_outcome"]
    print(f"  long triggers={long_trigs}  short triggers={short_trigs}", flush=True)
    print(f"  exits: target={int((exits==1).sum())}  stop={int((exits==-1).sum())}  time={int((exits==2).sum())}", flush=True)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(out_path, index=False)
    print(f"wrote {out_path}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
