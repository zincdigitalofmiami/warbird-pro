#!/usr/bin/env python3
"""Optuna profile for Warbird Precision Sniper Pine script.

This module is designed to plug into `scripts/sats/sats_optuna.py` via:

  --profile-module scripts.sats.precision_sniper_profile

It ports the trading-affecting portions of the Pine logic into a deterministic
Python backtest loop and exposes the profile contract expected by the Optuna
harness:
  - BOOL_PARAMS
  - NUMERIC_RANGES
  - INT_PARAMS
  - CATEGORICAL_PARAMS
  - INPUT_DEFAULTS
  - load_data()
  - run_backtest(...)

It also includes an optional AutoGluon surrogate fit utility that trains a
tabular regression model over completed Optuna trials for parameter-importance
inspection.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import optuna


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


# Search space contract for scripts/sats/sats_optuna.py
BOOL_PARAMS: list[str] = [
    "useTrailInput",
    "useStructureSLInput",
]

NUMERIC_RANGES: dict[str, tuple[float, float]] = {
    "emaFastLenInput": (3, 30),
    "emaSlowLenInput": (10, 80),
    "emaTrendLenInput": (20, 160),
    "minScoreInput": (1, 10),
    "rsiLenInput": (5, 30),
    "atrLenInput": (5, 50),
    "slMultInput": (0.5, 5.0),
    "tp1MultInput": (0.5, 5.0),
    "tp2MultInput": (1.0, 8.0),
    "tp3MultInput": (1.5, 12.0),
    "swingLookbackInput": (3, 30),
}

INT_PARAMS: set[str] = {
    "emaFastLenInput",
    "emaSlowLenInput",
    "emaTrendLenInput",
    "minScoreInput",
    "rsiLenInput",
    "atrLenInput",
    "swingLookbackInput",
}

CATEGORICAL_PARAMS: dict[str, list[Any]] = {
    "gradeFilterInput": ["All", "A+ and A", "A+ Only"],
    "sourceInput": ["close", "open", "high", "low", "hl2", "hlc3", "ohlc4"],
    "htfInput": ["", "60", "240", "D"],
}

INPUT_DEFAULTS: dict[str, Any] = {
    # Optimized via Optuna — 3003 trials, best WR 90.32% (trial #2957, 2026-04-20)
    "presetInput": "Custom",
    "emaFastLenInput": 11,
    "emaSlowLenInput": 58,
    "emaTrendLenInput": 78,
    "minScoreInput": 1,
    "rsiLenInput": 6,
    "gradeFilterInput": "A+ Only",
    "hideCGradeInput": False,
    "atrLenInput": 17,
    "slMultInput": 2.3756474215627477,
    "tp1MultInput": 0.6079184201375041,
    "tp2MultInput": 4.188843483504861,
    "tp3MultInput": 8.932568989158101,
    "useTrailInput": False,
    "useStructureSLInput": True,
    "swingLookbackInput": 9,
    "sourceInput": "ohlc4",
    "htfInput": "",
    "themeInput": "Auto",
    "showSignalsInput": True,
    "signalSizeInput": "Small",
    "showTPSLInput": True,
    "showRibbonInput": False,
    "showTrailInput": False,
    "showBgInput": True,
    "showWatermarkInput": True,
    "showGradeInput": True,
    "labelOffsetInput": 37,
    "showDashInput": True,
    "showBtDashInput": False,
    "dashPosStr": "Bottom Right",
    "webhookInput": False,
    "bullColorInput": "#00E676",
    "bearColorInput": "#FF5252",
    "neutralColorInput": "#FFEB3B",
}

MIN_TRADES_DEFAULT = 20


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


def _rma(src: np.ndarray, length: int) -> np.ndarray:
    alpha = 1.0 / max(length, 1)
    out = np.empty(len(src), dtype=np.float64)
    out[0] = src[0]
    for i in range(1, len(src)):
        out[i] = alpha * src[i] + (1.0 - alpha) * out[i - 1]
    return out


def _ema(src: np.ndarray, length: int) -> np.ndarray:
    return pd.Series(src).ewm(span=max(length, 1), adjust=False).mean().to_numpy(dtype=np.float64)


def _atr(high: np.ndarray, low: np.ndarray, close: np.ndarray, length: int) -> np.ndarray:
    prev_close = np.roll(close, 1)
    prev_close[0] = close[0]
    tr = np.maximum(high - low, np.maximum(np.abs(high - prev_close), np.abs(low - prev_close)))
    return _rma(tr, length)


def _rsi(close: np.ndarray, length: int) -> np.ndarray:
    diff = np.diff(close, prepend=close[0])
    up = np.where(diff > 0.0, diff, 0.0)
    down = np.where(diff < 0.0, -diff, 0.0)
    avg_up = _rma(up, length)
    avg_down = _rma(down, length)
    rs = np.divide(avg_up, avg_down, out=np.zeros_like(avg_up), where=avg_down != 0.0)
    return 100.0 - (100.0 / (1.0 + rs))


def _dmi(high: np.ndarray, low: np.ndarray, close: np.ndarray, length: int = 14) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    up_move = high - np.roll(high, 1)
    down_move = np.roll(low, 1) - low
    up_move[0] = 0.0
    down_move[0] = 0.0

    plus_dm = np.where((up_move > down_move) & (up_move > 0.0), up_move, 0.0)
    minus_dm = np.where((down_move > up_move) & (down_move > 0.0), down_move, 0.0)

    atr = _atr(high, low, close, length)
    plus_di = np.divide(100.0 * _rma(plus_dm, length), atr, out=np.zeros_like(atr), where=atr != 0.0)
    minus_di = np.divide(100.0 * _rma(minus_dm, length), atr, out=np.zeros_like(atr), where=atr != 0.0)

    dx_den = plus_di + minus_di
    dx = np.divide(100.0 * np.abs(plus_di - minus_di), dx_den, out=np.zeros_like(dx_den), where=dx_den != 0.0)
    adx = _rma(dx, length)
    return plus_di, minus_di, adx


def _session_vwap(df: pd.DataFrame) -> np.ndarray:
    ts = pd.to_datetime(df["ts"], utc=True)
    session = ts.dt.tz_convert("America/Chicago").dt.date
    tp = (df["high"].to_numpy(dtype=np.float64) + df["low"].to_numpy(dtype=np.float64) + df["close"].to_numpy(dtype=np.float64)) / 3.0
    vol = df["volume"].to_numpy(dtype=np.float64)
    tpv = pd.Series(tp * vol)
    cum_tpv = tpv.groupby(session).cumsum().to_numpy(dtype=np.float64)
    cum_vol = pd.Series(vol).groupby(session).cumsum().to_numpy(dtype=np.float64)
    fallback = df["close"].to_numpy(dtype=np.float64).copy()
    return np.divide(cum_tpv, cum_vol, out=fallback, where=cum_vol > 0.0)


def _tf_minutes(ts: pd.Series) -> float:
    s = pd.to_datetime(ts, utc=True)
    if len(s) < 2:
        return 15.0
    deltas = s.diff().dt.total_seconds().dropna()
    if deltas.empty:
        return 15.0
    return float(np.median(deltas.to_numpy(dtype=np.float64)) / 60.0)


def _resolve_source(frame: pd.DataFrame, source_input: str) -> np.ndarray:
    o = frame["open"].to_numpy(dtype=np.float64)
    h = frame["high"].to_numpy(dtype=np.float64)
    l = frame["low"].to_numpy(dtype=np.float64)
    c = frame["close"].to_numpy(dtype=np.float64)

    if source_input == "open":
        return o
    if source_input == "high":
        return h
    if source_input == "low":
        return l
    if source_input == "hl2":
        return (h + l) / 2.0
    if source_input == "hlc3":
        return (h + l + c) / 3.0
    if source_input == "ohlc4":
        return (o + h + l + c) / 4.0
    return c


def _normalize_htf(htf: str) -> str:
    if htf in {"", None}:
        return ""
    s = str(htf).strip().upper()
    if s in {"60", "1H", "H", "1HR"}:
        return "60"
    if s in {"240", "4H", "4HR"}:
        return "240"
    if s in {"D", "1D", "DAY"}:
        return "D"
    return ""


def _htf_bias_from_source(
    ts: pd.Series,
    source: np.ndarray,
    ema_fast: np.ndarray,
    ema_slow: np.ndarray,
    htf_input: str,
    fast_len: int,
    slow_len: int,
) -> np.ndarray:
    htf = _normalize_htf(htf_input)
    if htf == "":
        fast = np.roll(ema_fast, 1)
        slow = np.roll(ema_slow, 1)
        fast[0] = ema_fast[0]
        slow[0] = ema_slow[0]
        return np.where(fast > slow, 1, np.where(fast < slow, -1, 0))

    rule = {"60": "1h", "240": "4h", "D": "1D"}[htf]
    base_index = pd.DatetimeIndex(pd.to_datetime(ts, utc=True))
    src_series = pd.Series(source, index=base_index)
    htf_series = src_series.resample(rule, label="right", closed="right").last().dropna()

    htf_fast = htf_series.ewm(span=max(fast_len, 1), adjust=False).mean().shift(1)
    htf_slow = htf_series.ewm(span=max(slow_len, 1), adjust=False).mean().shift(1)

    aligned_fast = htf_fast.reindex(base_index, method="ffill")
    aligned_slow = htf_slow.reindex(base_index, method="ffill")

    safe_fast = np.where(np.isnan(aligned_fast.to_numpy(dtype=np.float64)), ema_fast, aligned_fast.to_numpy(dtype=np.float64))
    safe_slow = np.where(np.isnan(aligned_slow.to_numpy(dtype=np.float64)), ema_slow, aligned_slow.to_numpy(dtype=np.float64))
    return np.where(safe_fast > safe_slow, 1, np.where(safe_fast < safe_slow, -1, 0))


def _resolve_preset(preset_input: str, tf_minutes: float) -> str:
    resolved = preset_input
    if preset_input == "Auto":
        if tf_minutes <= 5.0:
            resolved = "Scalping"
        elif tf_minutes <= 60.0:
            resolved = "Default"
        elif tf_minutes <= 240.0:
            resolved = "Aggressive"
        else:
            resolved = "Swing"
    return resolved


def _effective_params(p: dict[str, Any], tf_minutes: float) -> dict[str, Any]:
    resolved = _resolve_preset(str(p.get("presetInput", "Auto")), tf_minutes)

    preset_map = {
        "Scalping": {"ema_fast": 5, "ema_slow": 13, "ema_trend": 34, "rsi_len": 8, "atr_len": 10, "score": 4, "sl": 0.8},
        "Aggressive": {"ema_fast": 8, "ema_slow": 18, "ema_trend": 50, "rsi_len": 11, "atr_len": 12, "score": 3, "sl": 1.2},
        "Default": {"ema_fast": 9, "ema_slow": 21, "ema_trend": 55, "rsi_len": 13, "atr_len": 14, "score": 5, "sl": 1.5},
        "Conservative": {"ema_fast": 12, "ema_slow": 26, "ema_trend": 89, "rsi_len": 14, "atr_len": 14, "score": 7, "sl": 2.0},
        "Swing": {"ema_fast": 13, "ema_slow": 34, "ema_trend": 89, "rsi_len": 21, "atr_len": 20, "score": 6, "sl": 2.5},
        "Crypto 24/7": {"ema_fast": 9, "ema_slow": 21, "ema_trend": 55, "rsi_len": 14, "atr_len": 20, "score": 5, "sl": 2.0},
    }

    if resolved in preset_map:
        core = dict(preset_map[resolved])
    else:
        core = {
            "ema_fast": _safe_int(p.get("emaFastLenInput", 9), 9),
            "ema_slow": _safe_int(p.get("emaSlowLenInput", 21), 21),
            "ema_trend": _safe_int(p.get("emaTrendLenInput", 55), 55),
            "rsi_len": _safe_int(p.get("rsiLenInput", 13), 13),
            "atr_len": _safe_int(p.get("atrLenInput", 14), 14),
            "score": _safe_int(p.get("minScoreInput", 5), 5),
            "sl": _safe_float(p.get("slMultInput", 1.5), 1.5),
        }

    core["ema_fast"] = int(np.clip(core["ema_fast"], 3, 50))
    core["ema_slow"] = int(np.clip(max(core["ema_slow"], core["ema_fast"] + 1), 10, 100))
    core["ema_trend"] = int(np.clip(max(core["ema_trend"], core["ema_slow"] + 1), 20, 200))
    core["rsi_len"] = int(np.clip(core["rsi_len"], 5, 30))
    core["atr_len"] = int(np.clip(core["atr_len"], 5, 50))
    core["score"] = int(np.clip(core["score"], 1, 10))
    core["sl"] = float(np.clip(core["sl"], 0.5, 5.0))

    tp1 = float(np.clip(_safe_float(p.get("tp1MultInput", 1.0), 1.0), 0.5, 5.0))
    tp2 = float(np.clip(_safe_float(p.get("tp2MultInput", 2.0), 2.0), 1.0, 8.0))
    tp3 = float(np.clip(_safe_float(p.get("tp3MultInput", 3.0), 3.0), 1.5, 12.0))
    tp_sorted = sorted([tp1, tp2, tp3])

    core["tp1"] = tp_sorted[0]
    core["tp2"] = tp_sorted[1]
    core["tp3"] = tp_sorted[2]
    core["use_trail"] = bool(p.get("useTrailInput", True))
    core["use_structure"] = bool(p.get("useStructureSLInput", True))
    core["swing_lookback"] = int(np.clip(_safe_int(p.get("swingLookbackInput", 10), 10), 3, 30))
    core["grade_filter"] = str(p.get("gradeFilterInput", "All"))
    core["hide_c_grade"] = False  # fixed off — redundant when gradeFilterInput="A+ Only"
    core["resolved_preset"] = resolved
    return core


def _passes_grade_filter(score: float, grade_filter: str, hide_c_grade: bool) -> bool:
    if grade_filter == "A+ Only":
        grade_ok = score >= 8.0
    elif grade_filter == "A+ and A":
        grade_ok = score >= 6.5
    else:
        grade_ok = True
    c_ok = (score >= 5.0) if hide_c_grade else True
    return grade_ok and c_ok


def load_data() -> pd.DataFrame:
    try:
        from scripts.sats.sats_sim import load_data as sats_load_data
    except Exception:
        from sats_sim import load_data as sats_load_data

    df = sats_load_data(source="db")
    out = df[["ts", "open", "high", "low", "close", "volume"]].copy()
    out = out.sort_values("ts").reset_index(drop=True)
    out["ts"] = pd.to_datetime(out["ts"], utc=True)
    return out


def run_backtest(
    df: pd.DataFrame,
    params: dict[str, Any],
    start_date: str = "2025-01-01",
    return_trades: bool = False,
) -> dict[str, Any] | tuple[dict[str, Any], pd.DataFrame]:
    p = {**INPUT_DEFAULTS, **(params or {})}
    frame = df.copy()
    frame = frame.sort_values("ts").reset_index(drop=True)
    frame["ts"] = pd.to_datetime(frame["ts"], utc=True)

    tf_min = _tf_minutes(frame["ts"])
    eff = _effective_params(p, tf_min)

    close = frame["close"].to_numpy(dtype=np.float64)
    high = frame["high"].to_numpy(dtype=np.float64)
    low = frame["low"].to_numpy(dtype=np.float64)
    volume = frame["volume"].to_numpy(dtype=np.float64)
    ts = frame["ts"]
    source = _resolve_source(frame, str(p.get("sourceInput", "close")))
    n = len(frame)
    if n < 10:
        return {
            "trades": 0,
            "win_rate": 0.0,
            "pf": 0.0,
            "gross_profit": 0.0,
            "gross_loss": 0.0,
            "max_dd_abs": 0.0,
            "max_dd_pct": 0.0,
            "total_r": 0.0,
        }

    ema_fast = _ema(source, eff["ema_fast"])
    ema_slow = _ema(source, eff["ema_slow"])
    ema_trend = _ema(source, eff["ema_trend"])
    atr = _atr(high, low, close, eff["atr_len"])
    rsi = _rsi(source, eff["rsi_len"])

    macd_fast = _ema(source, 12)
    macd_slow = _ema(source, 26)
    macd_line = macd_fast - macd_slow
    macd_signal = _ema(macd_line, 9)
    macd_hist = macd_line - macd_signal

    vol_sma = pd.Series(volume).rolling(20, min_periods=20).mean().to_numpy(dtype=np.float64)
    vol_sma = np.where(np.isnan(vol_sma), volume, vol_sma)
    has_volume = volume > 0.0
    vol_above_avg = np.where(has_volume, volume > vol_sma * 1.2, True)

    di_plus, di_minus, adx = _dmi(high, low, close, 14)
    strong_trend = adx > 20.0

    vwap = _session_vwap(frame)
    atr_sma_global = pd.Series(atr).rolling(42, min_periods=42).mean().to_numpy(dtype=np.float64)
    atr_sma_global = np.where(np.isnan(atr_sma_global), atr, atr_sma_global)
    _ = np.divide(atr, atr_sma_global, out=np.ones_like(atr), where=atr_sma_global != 0.0)

    htf_bias = _htf_bias_from_source(
        ts=ts,
        source=source,
        ema_fast=ema_fast,
        ema_slow=ema_slow,
        htf_input=str(p.get("htfInput", "")),
        fast_len=eff["ema_fast"],
        slow_len=eff["ema_slow"],
    )

    swing_window = eff["swing_lookback"] + 1
    recent_swing_low = pd.Series(low).rolling(swing_window, min_periods=1).min().to_numpy(dtype=np.float64)
    recent_swing_high = pd.Series(high).rolling(swing_window, min_periods=1).max().to_numpy(dtype=np.float64)

    warmup_bars = max(eff["ema_trend"], 50)
    start_ts = pd.Timestamp(start_date, tz="UTC")
    in_window = ts >= start_ts

    last_direction = 0
    sl_hit_prev = False

    entry_price = np.nan
    sl_price = np.nan
    tp1_price = np.nan
    tp2_price = np.nan
    tp3_price = np.nan
    trail_price = np.nan
    tp1_hit = False
    tp2_hit = False
    tp3_hit = False
    sl_hit = False
    trade_dir = 0
    trade_risk = np.nan
    entry_bar = -1

    bt_total_trades = 0
    bt_wins = 0
    bt_losses = 0
    bt_total_r = 0.0
    bt_gross_win = 0.0
    bt_gross_loss = 0.0

    prev_trade_open = False
    prev_dir = 0
    prev_tp1 = False
    prev_tp2 = False
    prev_tp3 = False
    prev_sl = False

    equity_r = 0.0
    peak_equity_r = 0.0
    max_dd_r = 0.0
    active_trade_features: dict[str, Any] | None = None
    trade_rows: list[dict[str, Any]] = []

    for i in range(n):
        bull_score = 0.0
        bull_score += 1.0 if ema_fast[i] > ema_slow[i] else 0.0
        bull_score += 1.0 if close[i] > ema_trend[i] else 0.0
        bull_score += 1.0 if (rsi[i] > 50.0 and rsi[i] < 75.0) else 0.0
        bull_score += 1.0 if macd_hist[i] > 0.0 else 0.0
        bull_score += 1.0 if macd_line[i] > macd_signal[i] else 0.0
        bull_score += 1.0 if close[i] > vwap[i] else 0.0
        bull_score += 1.0 if bool(vol_above_avg[i]) else 0.0
        bull_score += 1.0 if (strong_trend[i] and di_plus[i] > di_minus[i]) else 0.0
        bull_score += 1.5 if htf_bias[i] == 1 else 0.0
        bull_score += 0.5 if close[i] > ema_fast[i] else 0.0

        bear_score = 0.0
        bear_score += 1.0 if ema_fast[i] < ema_slow[i] else 0.0
        bear_score += 1.0 if close[i] < ema_trend[i] else 0.0
        bear_score += 1.0 if (rsi[i] < 50.0 and rsi[i] > 25.0) else 0.0
        bear_score += 1.0 if macd_hist[i] < 0.0 else 0.0
        bear_score += 1.0 if macd_line[i] < macd_signal[i] else 0.0
        bear_score += 1.0 if close[i] < vwap[i] else 0.0
        bear_score += 1.0 if bool(vol_above_avg[i]) else 0.0
        bear_score += 1.0 if (strong_trend[i] and di_minus[i] > di_plus[i]) else 0.0
        bear_score += 1.5 if htf_bias[i] == -1 else 0.0
        bear_score += 0.5 if close[i] < ema_fast[i] else 0.0

        prev_fast = ema_fast[i - 1] if i > 0 else ema_fast[i]
        prev_slow = ema_slow[i - 1] if i > 0 else ema_slow[i]
        ema_bull_cross = (ema_fast[i] > ema_slow[i]) and (prev_fast <= prev_slow)
        ema_bear_cross = (ema_fast[i] < ema_slow[i]) and (prev_fast >= prev_slow)

        bull_momentum = close[i] > ema_fast[i] and close[i] > ema_slow[i]
        bear_momentum = close[i] < ema_fast[i] and close[i] < ema_slow[i]
        rsi_not_ob = rsi[i] < 75.0
        rsi_not_os = rsi[i] > 25.0

        raw_buy = (
            ema_bull_cross
            and bull_momentum
            and rsi_not_ob
            and bull_score >= eff["score"]
            and _passes_grade_filter(bull_score, eff["grade_filter"], eff["hide_c_grade"])
        )
        raw_sell = (
            ema_bear_cross
            and bear_momentum
            and rsi_not_os
            and bear_score >= eff["score"]
            and _passes_grade_filter(bear_score, eff["grade_filter"], eff["hide_c_grade"])
        )

        buy_condition = raw_buy and last_direction != 1
        sell_condition = raw_sell and last_direction != -1

        confirmed_buy = bool(buy_condition and i >= warmup_bars and in_window.iloc[i])
        confirmed_sell = bool(sell_condition and i >= warmup_bars and in_window.iloc[i])
        if confirmed_buy and confirmed_sell:
            confirmed_sell = False

        if confirmed_buy:
            last_direction = 1
        elif confirmed_sell:
            last_direction = -1

        prev_active_trade_features = active_trade_features
        prev_entry_for_case = entry_price
        prev_risk_for_case = trade_risk

        def calc_sl(is_long: bool, entry: float, atr_sl: float) -> float:
            atr_stop = (entry - atr_sl) if is_long else (entry + atr_sl)
            if eff["use_structure"]:
                struct_stop = (
                    (recent_swing_low[i] - atr[i] * 0.2)
                    if is_long
                    else (recent_swing_high[i] + atr[i] * 0.2)
                )
                final_stop = max(atr_stop, struct_stop) if is_long else min(atr_stop, struct_stop)
                min_dist = atr[i] * 0.5
                if abs(entry - final_stop) < min_dist:
                    final_stop = (entry - min_dist) if is_long else (entry + min_dist)
                return final_stop
            return atr_stop

        if confirmed_buy:
            entry_price = close[i]
            trade_dir = 1
            risk = atr[i] * eff["sl"]
            sl_price = calc_sl(True, close[i], risk)
            trade_risk = abs(close[i] - sl_price)
            tp1_price = close[i] + trade_risk * eff["tp1"]
            tp2_price = close[i] + trade_risk * eff["tp2"]
            tp3_price = close[i] + trade_risk * eff["tp3"]
            trail_price = sl_price
            tp1_hit = False
            tp2_hit = False
            tp3_hit = False
            sl_hit = False
            entry_bar = i
            active_trade_features = {
                "entry_ts": ts.iloc[i],
                "direction": 1,
                "entry_price": float(entry_price),
                "bull_score": float(bull_score),
                "bear_score": float(bear_score),
                "rsi": float(rsi[i]),
                "adx": float(adx[i]),
                "atr": float(atr[i]),
                "ema_gap": float(ema_fast[i] - ema_slow[i]),
                "trend_gap": float(close[i] - ema_trend[i]),
                "vwap_gap": float(close[i] - vwap[i]),
                "vol_above_avg": int(bool(vol_above_avg[i])),
                "htf_bias": int(htf_bias[i]),
                "resolved_preset": eff["resolved_preset"],
            }

        if confirmed_sell:
            entry_price = close[i]
            trade_dir = -1
            risk = atr[i] * eff["sl"]
            sl_price = calc_sl(False, close[i], risk)
            trade_risk = abs(close[i] - sl_price)
            tp1_price = close[i] - trade_risk * eff["tp1"]
            tp2_price = close[i] - trade_risk * eff["tp2"]
            tp3_price = close[i] - trade_risk * eff["tp3"]
            trail_price = sl_price
            tp1_hit = False
            tp2_hit = False
            tp3_hit = False
            sl_hit = False
            entry_bar = i
            active_trade_features = {
                "entry_ts": ts.iloc[i],
                "direction": -1,
                "entry_price": float(entry_price),
                "bull_score": float(bull_score),
                "bear_score": float(bear_score),
                "rsi": float(rsi[i]),
                "adx": float(adx[i]),
                "atr": float(atr[i]),
                "ema_gap": float(ema_fast[i] - ema_slow[i]),
                "trend_gap": float(close[i] - ema_trend[i]),
                "vwap_gap": float(close[i] - vwap[i]),
                "vol_above_avg": int(bool(vol_above_avg[i])),
                "htf_bias": int(htf_bias[i]),
                "resolved_preset": eff["resolved_preset"],
            }

        can_check_tpsl = i > entry_bar and trade_dir != 0 and (not sl_hit)
        if can_check_tpsl and trade_dir == 1:
            pre_trail = trail_price
            if high[i] >= tp1_price and not tp1_hit:
                tp1_hit = True
                if eff["use_trail"]:
                    trail_price = entry_price
            if high[i] >= tp2_price and not tp2_hit:
                tp2_hit = True
                if eff["use_trail"]:
                    trail_price = tp1_price
            if high[i] >= tp3_price and not tp3_hit:
                tp3_hit = True
                if eff["use_trail"]:
                    trail_price = tp2_price
            stop_check = pre_trail if not np.isnan(pre_trail) else sl_price
            if low[i] <= stop_check:
                sl_hit = True

        if can_check_tpsl and trade_dir == -1:
            pre_trail = trail_price
            if low[i] <= tp1_price and not tp1_hit:
                tp1_hit = True
                if eff["use_trail"]:
                    trail_price = entry_price
            if low[i] <= tp2_price and not tp2_hit:
                tp2_hit = True
                if eff["use_trail"]:
                    trail_price = tp1_price
            if low[i] <= tp3_price and not tp3_hit:
                tp3_hit = True
                if eff["use_trail"]:
                    trail_price = tp2_price
            stop_check = pre_trail if not np.isnan(pre_trail) else sl_price
            if high[i] >= stop_check:
                sl_hit = True

        trade_active = trade_dir != 0 and (not sl_hit)

        if sl_hit and (not sl_hit_prev):
            last_direction = 0
        sl_hit_prev = sl_hit

        trade_just_closed = False
        closed_r = 0.0

        if sl_hit and (not prev_sl) and prev_trade_open:
            trade_just_closed = True
            if eff["use_trail"]:
                if prev_tp3 or tp3_hit:
                    closed_r = eff["tp2"]
                elif prev_tp2 or tp2_hit:
                    closed_r = eff["tp1"]
                elif prev_tp1 or tp1_hit:
                    closed_r = 0.0
                else:
                    closed_r = -1.0
            else:
                if prev_tp3 or tp3_hit:
                    closed_r = eff["tp3"]
                elif prev_tp2 or tp2_hit:
                    closed_r = eff["tp2"]
                elif prev_tp1 or tp1_hit:
                    closed_r = eff["tp1"]
                else:
                    closed_r = -1.0

        elif ((confirmed_buy and prev_dir == -1 and prev_trade_open) or (confirmed_sell and prev_dir == 1 and prev_trade_open)):
            trade_just_closed = True
            if prev_tp3:
                closed_r = eff["tp3"]
            elif prev_tp2:
                closed_r = eff["tp2"]
            elif prev_tp1:
                closed_r = eff["tp1"]
            else:
                prev_entry = prev_entry_for_case if not np.isnan(prev_entry_for_case) else close[i]
                prev_risk = prev_risk_for_case if (not np.isnan(prev_risk_for_case) and prev_risk_for_case > 0.0) else atr[i]
                pnl = (close[i] - prev_entry) if prev_dir == 1 else (prev_entry - close[i])
                closed_r = pnl / prev_risk if prev_risk != 0.0 else 0.0

        if trade_just_closed:
            bt_total_trades += 1
            bt_total_r += closed_r
            if closed_r > 0.0:
                bt_wins += 1
                bt_gross_win += closed_r
            elif closed_r < 0.0:
                bt_losses += 1
                bt_gross_loss += abs(closed_r)

            equity_r += closed_r
            if equity_r > peak_equity_r:
                peak_equity_r = equity_r
            dd_r = peak_equity_r - equity_r
            if dd_r > max_dd_r:
                max_dd_r = dd_r

            if return_trades:
                src = prev_active_trade_features or active_trade_features or {
                    "entry_ts": ts.iloc[i],
                    "direction": int(prev_dir),
                    "entry_price": float(prev_entry_for_case if not np.isnan(prev_entry_for_case) else close[i]),
                    "bull_score": float(bull_score),
                    "bear_score": float(bear_score),
                    "rsi": float(rsi[i]),
                    "adx": float(adx[i]),
                    "atr": float(atr[i]),
                    "ema_gap": float(ema_fast[i] - ema_slow[i]),
                    "trend_gap": float(close[i] - ema_trend[i]),
                    "vwap_gap": float(close[i] - vwap[i]),
                    "vol_above_avg": int(bool(vol_above_avg[i])),
                    "htf_bias": int(htf_bias[i]),
                    "resolved_preset": eff["resolved_preset"],
                }
                row = dict(src)
                row["exit_ts"] = ts.iloc[i]
                row["closed_r"] = float(closed_r)
                row["target_win"] = int(closed_r > 0.0)
                if closed_r > 0.0:
                    row["target_outcome"] = "WIN"
                elif closed_r < 0.0:
                    row["target_outcome"] = "LOSS"
                else:
                    row["target_outcome"] = "BREAKEVEN"
                trade_rows.append(row)

            if sl_hit and not (confirmed_buy or confirmed_sell):
                active_trade_features = None

        prev_trade_open = trade_active
        prev_dir = trade_dir
        prev_tp1 = tp1_hit
        prev_tp2 = tp2_hit
        prev_tp3 = tp3_hit
        prev_sl = sl_hit

    bt_win_rate = (bt_wins / bt_total_trades) if bt_total_trades > 0 else 0.0
    bt_pf = (bt_gross_win / bt_gross_loss) if bt_gross_loss > 0.0 else (999.0 if bt_gross_win > 0.0 else 0.0)
    max_dd_pct = (max_dd_r / peak_equity_r) if peak_equity_r > 0.0 else 0.0

    metrics = {
        "trades": int(bt_total_trades),
        "win_rate": float(bt_win_rate),
        "pf": float(bt_pf),
        "gross_profit": float(bt_gross_win),
        "gross_loss": float(bt_gross_loss),
        "max_dd_abs": float(max_dd_r),
        "max_dd_pct": float(max_dd_pct),
        "total_r": float(bt_total_r),
        "resolved_preset": eff["resolved_preset"],
    }
    if not return_trades:
        return metrics
    trades_df = pd.DataFrame(trade_rows)
    if not trades_df.empty:
        trades_df["entry_ts"] = pd.to_datetime(trades_df["entry_ts"], utc=True)
        trades_df["exit_ts"] = pd.to_datetime(trades_df["exit_ts"], utc=True)
        trades_df = trades_df.sort_values("entry_ts").reset_index(drop=True)
    return metrics, trades_df


def load_trials_frame(
    study_db_path: str | Path,
    study_name: str,
    min_trades: int = MIN_TRADES_DEFAULT,
) -> pd.DataFrame:
    storage = f"sqlite:///{Path(study_db_path)}"
    study = optuna.load_study(study_name=study_name, storage=storage)

    rows: list[dict[str, Any]] = []
    for trial in study.trials:
        if trial.state != optuna.trial.TrialState.COMPLETE:
            continue
        trades = _safe_int(trial.user_attrs.get("trades"), 0)
        if trades < min_trades:
            continue

        row: dict[str, Any] = dict(trial.params)
        row["objective_score"] = _safe_float(trial.value, 0.0)
        row["win_rate"] = _safe_float(trial.user_attrs.get("win_rate"), 0.0)
        row["pf"] = _safe_float(trial.user_attrs.get("pf"), 0.0)
        row["trades"] = trades
        row["max_dd"] = _safe_float(trial.user_attrs.get("max_dd"), 0.0)
        rows.append(row)

    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows)


def fit_autogluon_on_trials(
    study_db_path: str | Path,
    study_name: str,
    out_dir: str | Path,
    min_trades: int = MIN_TRADES_DEFAULT,
    time_limit: int = 180,
) -> dict[str, Any]:
    from autogluon.tabular import TabularPredictor

    trials_df = load_trials_frame(study_db_path, study_name, min_trades=min_trades)
    if trials_df.empty:
        raise ValueError("No qualifying completed trials found for AutoGluon surrogate fit.")

    param_cols = [c for c in trials_df.columns if c not in {"objective_score", "win_rate", "pf", "trades", "max_dd"}]
    train_df = trials_df[param_cols + ["objective_score"]].copy()

    out_path = Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)
    predictor_path = out_path / "autogluon_surrogate"

    predictor = TabularPredictor(
        label="objective_score",
        problem_type="regression",
        eval_metric="root_mean_squared_error",
        path=str(predictor_path),
    )
    predictor.fit(
        train_data=train_df,
        presets="medium_quality",
        time_limit=time_limit,
        num_bag_folds=0,
        num_stack_levels=0,
        dynamic_stacking=False,
    )

    leaderboard = predictor.leaderboard(train_df, silent=True)
    fi = predictor.feature_importance(train_df, silent=True)

    summary = {
        "study_db_path": str(study_db_path),
        "study_name": study_name,
        "rows": int(len(train_df)),
        "feature_columns": param_cols,
        "best_model": str(leaderboard.iloc[0]["model"]) if len(leaderboard) > 0 else None,
        "leaderboard_top10": leaderboard.head(10).to_dict(orient="records"),
        "feature_importance_top20": fi.head(20).reset_index().rename(columns={"index": "feature"}).to_dict(orient="records"),
    }

    summary_path = out_path / "autogluon_surrogate_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2))
    return summary


def _cli() -> None:
    parser = argparse.ArgumentParser(description="Precision Sniper profile utilities")
    sub = parser.add_subparsers(dest="cmd", required=True)

    bt = sub.add_parser("backtest", help="Run one backtest with INPUT_DEFAULTS")
    bt.add_argument("--start", default="2025-01-01")

    ag = sub.add_parser("fit-autogluon", help="Fit AutoGluon surrogate over Optuna trials")
    ag.add_argument("--study-db", required=True)
    ag.add_argument("--study-name", required=True)
    ag.add_argument("--out-dir", required=True)
    ag.add_argument("--min-trades", type=int, default=MIN_TRADES_DEFAULT)
    ag.add_argument("--time-limit", type=int, default=180)

    args = parser.parse_args()

    if args.cmd == "backtest":
        df = load_data()
        metrics = run_backtest(df, INPUT_DEFAULTS, start_date=args.start)
        print(json.dumps(metrics, indent=2))
        return

    if args.cmd == "fit-autogluon":
        summary = fit_autogluon_on_trials(
            study_db_path=args.study_db,
            study_name=args.study_name,
            out_dir=args.out_dir,
            min_trades=args.min_trades,
            time_limit=args.time_limit,
        )
        print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    _cli()
