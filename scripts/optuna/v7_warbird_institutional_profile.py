#!/usr/bin/env python3
"""
Warbird v7 Institutional — standalone Optuna profile.

Optimizes v7 Warbird Institutional Pine indicator parameters against a
TradingView CSV export.  Fully standalone — no shared strategy code.

Architecture
------------
1. load_data()
   - Reads data/optuna/v7_warbird_institutional/export.csv (TV CSV export)
   - Merges with data/mes_15m.parquet for OHLCV ground truth
   - Precomputes ATR(14), EMA(100), DMI(14) for filter/simulation use

2. run_backtest(df, params, start_date)
   - Recomputes momentum oscillators (VF, NFE, RSI-KNN) with trial params
   - Extracts trades from Pine state machine (trade_state + ml_last_exit_outcome)
   - Re-simulates each trade outcome with the trial stop family against raw OHLCV
   - Applies confirmation filters (momentum, HTF confluence, short gate)
   - Returns composite score: 0.40 × PF + 0.35 × WR + 0.25 × yearly consistency

Fib geometry recovery
---------------------
pNeg236 (ml_fib_neg_0236) is the only exported absolute price.
fibBase is recovered as:
    fibBase = pNeg236 + fibDir * 0.236 * fibRange
All other levels follow: fibBase + fibDir * fibRange * ratio

TV-only params (require Pine re-run, not swept here)
-----------------------------------------------------
retestBars, fibConfluenceTolPct, footprintTicksPerRow, footprintVaPercent,
footprintImbalancePercent, zeroPrintVolRatio, stackedImbalanceRows,
exhaustionZLen, exhaustionZThreshold, exhaustionLevelAtrTol.
See docs/runbooks/wbv7_institutional_optuna.md for CDP sweep instructions.

Runner interface
----------------
BOOL_PARAMS, NUMERIC_RANGES, INT_PARAMS, CATEGORICAL_PARAMS, INPUT_DEFAULTS,
load_data() -> pd.DataFrame,
run_backtest(df, params, start_date) -> dict
"""

from __future__ import annotations

import warnings
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

# ── Paths ─────────────────────────────────────────────────────────────────────

REPO_ROOT  = Path(__file__).parents[2]
OPTUNA_DIR = REPO_ROOT / "data" / "optuna" / "v7_warbird_institutional"
CSV_PATH   = OPTUNA_DIR / "export.csv"
OHLCV_PATH = REPO_ROOT / "data" / "mes_15m.parquet"

# ── Constants ─────────────────────────────────────────────────────────────────

MES_POINT_VALUE  = 5.0    # USD per point, 1 MES contract
COMMISSION_SIDE  = 1.0    # USD per side (floor per CLAUDE.md)
MINTICK          = 0.25   # MES minimum tick
DATA_FLOOR       = "2020-01-01"
MIN_TRADES       = 80     # reject configs below this trade count
MAX_EXPIRED_FRAC = 0.70   # reject if > 70% of outcomes are EXPIRED

# Pine ml_last_exit_outcome codes
OUTCOME_NONE    = 0
OUTCOME_TP1     = 1
OUTCOME_TP2     = 2
OUTCOME_STOPPED = 3
OUTCOME_EXPIRED = 4
OUTCOME_TP3     = 5
OUTCOME_TP4     = 6
OUTCOME_TP5     = 7
WINNER_OUTCOMES = frozenset({OUTCOME_TP1, OUTCOME_TP2, OUTCOME_TP3, OUTCOME_TP4, OUTCOME_TP5})

# Pine trade_state codes
TRADE_NONE   = 0
TRADE_SETUP  = 1
TRADE_ACTIVE = 2

# Fib extension ratios (canonical, matches v7 Pine constants)
FIB_T1, FIB_T2, FIB_T3, FIB_T4, FIB_T5 = 1.236, 1.618, 2.000, 2.236, 2.618

# ── Profile interface (required by runner.py) ─────────────────────────────────

BOOL_PARAMS: list[str] = ["gateShortsInBullTrend"]

NUMERIC_RANGES: dict[str, tuple[float, float]] = {
    # Stop geometry — primary lever (re-simulates full outcomes)
    "continuationHoldStopAtrMult": (1.0,  4.0),
    "continuationHoldBars":        (1.0,  8.0),   # int via INT_PARAMS
    # Momentum windows — recomputed from OHLCV each trial
    "vfLenInput":                  (10.0, 50.0),   # int
    "vfFlowWeight":                (10.0, 50.0),
    "vfVolWeight":                 (2.0,  20.0),
    "nfeLenInput":                 (7.0,  30.0),   # int
    "rsiKnnWindow":                (10.0, 40.0),   # int
    # Confirmation filters
    "shortTrendGateAdx":           (10.0, 40.0),
    "momentumMinFilter":           (40.0, 70.0),   # ml_confluence threshold at entry
}

INT_PARAMS: set[str] = {
    "continuationHoldBars",
    "vfLenInput",
    "nfeLenInput",
    "rsiKnnWindow",
}

CATEGORICAL_PARAMS: dict[str, list[Any]] = {
    "stopFamilyId": [
        "FIB_NEG_0236",
        "FIB_NEG_0382",
        "ATR_1_0",
        "ATR_1_5",
        "ATR_STRUCTURE_1_25",
        "FIB_0236_ATR_COMPRESS_0_50",
    ],
}

INPUT_DEFAULTS: dict[str, Any] = {
    "gateShortsInBullTrend":         True,
    "continuationHoldStopAtrMult":   1.0,
    "continuationHoldBars":          3,
    "vfLenInput":                    20,
    "vfFlowWeight":                  25.0,
    "vfVolWeight":                   10.0,
    "nfeLenInput":                   14,
    "rsiKnnWindow":                  20,
    "shortTrendGateAdx":             10.0,
    "momentumMinFilter":             40.0,  # 40 = effectively no filter
    "stopFamilyId":                  "ATR_1_0",
}

# ── Fib geometry helpers ───────────────────────────────────────────────────────

def _fib_base(p_neg_0236: float, fib_dir: float, fib_range: float) -> float:
    """
    Recover fibBase from the exported pNeg236 absolute price.

    Pine: pNeg236 = fibBase + fibDir * fibRange * (-0.236)
    =>    fibBase = pNeg236 + fibDir * 0.236 * fibRange
    """
    return p_neg_0236 + fib_dir * 0.236 * fib_range


def _fib_price(fb: float, fib_dir: float, fib_range: float, ratio: float) -> float:
    return fb + fib_dir * fib_range * ratio


def _entry_level(fb: float, fib_dir: float, fib_range: float, direction: int) -> float:
    """p618 for bull (dir +1), p382 for bear (dir -1). Matches Pine."""
    return _fib_price(fb, fib_dir, fib_range, 0.618 if direction == 1 else 0.382)


# ── ATR computation ────────────────────────────────────────────────────────────

def _atr(high: np.ndarray, low: np.ndarray, close: np.ndarray, period: int = 14) -> np.ndarray:
    """Wilder ATR. Matches ta.atr() in Pine."""
    n = len(close)
    prev_c = np.roll(close, 1)
    prev_c[0] = close[0]
    tr = np.maximum(high - low, np.maximum(np.abs(high - prev_c), np.abs(low - prev_c)))
    result = np.full(n, np.nan)
    if n < period:
        return result
    result[period - 1] = float(np.mean(tr[:period]))
    alpha = 1.0 / period
    for i in range(period, n):
        result[i] = tr[i] * alpha + result[i - 1] * (1.0 - alpha)
    return result


# ── DMI computation ────────────────────────────────────────────────────────────

def _dmi(
    high: np.ndarray, low: np.ndarray, close: np.ndarray, period: int = 14
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Wilder DMI → (+DI, -DI, ADX). Matches ta.dmi() in Pine."""
    n = len(close)
    dm_plus  = np.zeros(n)
    dm_minus = np.zeros(n)
    for i in range(1, n):
        h_diff = high[i] - high[i - 1]
        l_diff = low[i - 1] - low[i]
        dm_plus[i]  = h_diff if h_diff > l_diff and h_diff > 0 else 0.0
        dm_minus[i] = l_diff if l_diff > h_diff and l_diff > 0 else 0.0

    prev_c = np.roll(close, 1); prev_c[0] = close[0]
    tr = np.maximum(high - low, np.maximum(np.abs(high - prev_c), np.abs(low - prev_c)))

    alpha = 1.0 / period
    atr_w = np.full(n, np.nan)
    dmp_w = np.full(n, np.nan)
    dmm_w = np.full(n, np.nan)
    atr_w[0] = tr[0]; dmp_w[0] = dm_plus[0]; dmm_w[0] = dm_minus[0]
    for i in range(1, n):
        atr_w[i] = tr[i]       * alpha + atr_w[i - 1] * (1 - alpha)
        dmp_w[i] = dm_plus[i]  * alpha + dmp_w[i - 1] * (1 - alpha)
        dmm_w[i] = dm_minus[i] * alpha + dmm_w[i - 1] * (1 - alpha)

    di_plus  = np.where(atr_w > 0, 100.0 * dmp_w / atr_w, 0.0)
    di_minus = np.where(atr_w > 0, 100.0 * dmm_w / atr_w, 0.0)
    dx  = np.where((di_plus + di_minus) > 0,
                   100.0 * np.abs(di_plus - di_minus) / (di_plus + di_minus), 0.0)
    adx = np.full(n, np.nan)
    if n >= period:
        adx[period - 1] = float(np.mean(dx[:period]))
        for i in range(period, n):
            adx[i] = dx[i] * alpha + adx[i - 1] * (1 - alpha)
    return di_plus, di_minus, adx


# ── EMA computation ────────────────────────────────────────────────────────────

def _ema(values: np.ndarray, period: int) -> np.ndarray:
    """EMA seeded from first SMA. Matches ta.ema() in Pine."""
    result = np.full(len(values), np.nan)
    alpha = 2.0 / (period + 1)
    start = period - 1
    if start >= len(values):
        return result
    result[start] = float(np.nanmean(values[:start + 1]))
    for i in range(start + 1, len(values)):
        result[i] = values[i] * alpha + result[i - 1] * (1.0 - alpha)
    return result


# ── RSI and KNN-smoothed RSI ───────────────────────────────────────────────────

def _rsi(close: np.ndarray, period: int) -> np.ndarray:
    """Wilder RSI. Matches ta.rsi() in Pine."""
    n = len(close)
    result = np.full(n, np.nan)
    if n < period + 1:
        return result
    delta  = np.diff(close)
    gains  = np.maximum(delta, 0.0)
    losses = np.abs(np.minimum(delta, 0.0))
    alpha  = 1.0 / period
    avg_g  = np.full(n, np.nan)
    avg_l  = np.full(n, np.nan)
    avg_g[period] = float(np.mean(gains[:period]))
    avg_l[period] = float(np.mean(losses[:period]))
    for i in range(period + 1, n):
        avg_g[i] = gains[i - 1] * alpha + avg_g[i - 1] * (1.0 - alpha)
        avg_l[i] = losses[i - 1] * alpha + avg_l[i - 1] * (1.0 - alpha)
    rs = np.where(avg_l > 0, avg_g / avg_l, 100.0)
    result[period:] = 100.0 - 100.0 / (1.0 + rs[period:])
    return result


def _rsi_knn(rsi_arr: np.ndarray, window: int) -> np.ndarray:
    """
    KNN-weighted RSI smoother — matches f_rsi_knn() in Pine.
    O(n × window): fine for n≈150k, window≤40.
    """
    result = rsi_arr.copy().astype(float)
    for i in range(len(rsi_arr)):
        src = rsi_arr[i]
        if np.isnan(src):
            continue
        sum_w = sum_v = 0.0
        for lag in range(1, min(window, i) + 1):
            prev = rsi_arr[i - lag]
            if np.isnan(prev):
                continue
            w = 1.0 / (abs(src - prev) + 0.001)
            sum_w += w
            sum_v += prev * w
        if sum_w > 0:
            result[i] = sum_v / sum_w
    return result


# ── Stop family price computation ──────────────────────────────────────────────

def _compute_sl(
    family: str,
    direction: int,
    entry_px: float,
    fib_base: float,
    fib_dir: float,
    fib_range: float,
    atr: float,
) -> float:
    """
    Python port of Pine's stopFamilyLevel().
    Exact logic per each stop family; rounded to MINTICK.
    """
    safe_atr   = max(atr, MINTICK)
    p_neg_0236 = _fib_price(fib_base, fib_dir, fib_range, -0.236)

    if family == "FIB_NEG_0236":
        raw = p_neg_0236 - MINTICK if direction == 1 else p_neg_0236 + MINTICK

    elif family == "FIB_NEG_0382":
        raw = (fib_base - 0.382 * fib_range - MINTICK
               if direction == 1
               else fib_base + 0.382 * fib_range + MINTICK)

    elif family == "ATR_1_0":
        raw = entry_px - safe_atr if direction == 1 else entry_px + safe_atr

    elif family == "ATR_1_5":
        raw = entry_px - 1.5 * safe_atr if direction == 1 else entry_px + 1.5 * safe_atr

    elif family == "ATR_STRUCTURE_1_25":
        raw = (max(fib_base - MINTICK, entry_px - 1.25 * safe_atr)
               if direction == 1
               else min(fib_base + MINTICK, entry_px + 1.25 * safe_atr))

    else:  # FIB_0236_ATR_COMPRESS_0_50
        raw = (max(fib_base - 0.5 * safe_atr, p_neg_0236) - MINTICK
               if direction == 1
               else min(fib_base + 0.5 * safe_atr, p_neg_0236) + MINTICK)

    # Sanity: SL must be on the correct side of entry
    if direction == 1 and raw >= entry_px:
        raw = entry_px - safe_atr
    if direction == -1 and raw <= entry_px:
        raw = entry_px + safe_atr

    return round(raw / MINTICK) * MINTICK


# ── Momentum oscillator recomputation ─────────────────────────────────────────

def _add_momentum(df: pd.DataFrame, params: dict) -> pd.DataFrame:
    """
    Recompute VF, NFE, RSI-KNN, and momentum confluence with trial params.
    Overwrites: ml_vf_bull, ml_vf_bear, ml_nfe, ml_rsi_knn, ml_confluence.
    Matches Pine's exact formulas for each oscillator.
    """
    vf_len  = int(params.get("vfLenInput",   20))
    vf_flow = float(params.get("vfFlowWeight", 25.0))
    vf_vol  = float(params.get("vfVolWeight",  10.0))
    nfe_len = int(params.get("nfeLenInput",   14))
    knn_win = int(params.get("rsiKnnWindow",  20))

    close  = df["close"].values.astype(float)
    open_  = df["open"].values.astype(float)
    high   = df["high"].values.astype(float)
    low    = df["low"].values.astype(float)
    volume = df["volume"].values.astype(float)

    bar_range  = high - low
    body_norm  = np.where(bar_range > MINTICK, (close - open_) / bar_range, 0.0)

    vol_s    = pd.Series(volume)
    vol_mean = vol_s.rolling(vf_len, min_periods=vf_len).mean().values
    vol_std  = vol_s.rolling(vf_len, min_periods=vf_len).std(ddof=0).values
    vol_std  = np.where(vol_std > 0, vol_std, 1.0)
    vol_z    = np.nan_to_num((volume - vol_mean) / vol_std, nan=0.0)

    vf_bull = np.clip(50.0 + body_norm * vf_flow + vol_z * vf_vol, 0.0, 100.0)
    vf_bear = np.clip(50.0 - body_norm * vf_flow - vol_z * vf_vol, 0.0, 100.0)

    rsi14   = _rsi(close, 14)
    nfe_raw = _rsi(close, nfe_len)
    ml_nfe  = _ema(nfe_raw, 3)
    ml_knn  = _rsi_knn(rsi14, knn_win)

    vf_net  = (vf_bull - vf_bear + 100.0) * 0.5
    ml_conf = np.clip(
        (np.nan_to_num(ml_nfe, nan=50.0) + vf_net + np.nan_to_num(ml_knn, nan=50.0)) / 3.0,
        0.0, 100.0,
    )

    df = df.copy()
    df["ml_vf_bull"]    = vf_bull
    df["ml_vf_bear"]    = vf_bear
    df["ml_nfe"]        = ml_nfe
    df["ml_rsi_knn"]    = ml_knn
    df["ml_confluence"] = ml_conf
    return df


# ── Trade extraction from Pine state machine ───────────────────────────────────

def _extract_trades(df: pd.DataFrame) -> list[dict]:
    """
    Walk the Pine state machine export (trade_state + ml_last_exit_outcome)
    to identify each trade's entry and exit bar.

    Entry detected as: trade_state transitions SETUP(1) → ACTIVE(2).
    Exit detected as:  ml_last_exit_outcome != 0 (fires at resolution bar).

    Returns list of trade dicts keyed off the entry bar's values.
    """
    states   = df["trade_state"].fillna(0).astype(int).values
    outcomes = df["ml_last_exit_outcome"].fillna(0).astype(int).values
    n        = len(df)

    trades: list[dict] = []
    entry_idx: int | None = None

    for i in range(1, n):
        prev_state = states[i - 1]
        cur_state  = states[i]
        outcome    = outcomes[i]

        # Entry: SETUP → ACTIVE transition
        if prev_state == TRADE_SETUP and cur_state == TRADE_ACTIVE and entry_idx is None:
            entry_idx = i

        # Exit: ml_last_exit_outcome fires (trade_state already reset to NONE)
        if outcome != OUTCOME_NONE and entry_idx is not None:
            row_e = df.iloc[entry_idx]
            row_x = df.iloc[i]

            p_neg  = float(row_e.get("ml_fib_neg_0236", np.nan))
            f_rng  = float(row_e.get("fib_range", np.nan))
            dirn   = int(row_e.get("ml_direction_code", 1))
            atr_e  = float(row_e.get("_atr14", np.nan))

            if any(np.isnan(v) for v in (p_neg, f_rng, atr_e)) or f_rng <= 0:
                entry_idx = None
                continue

            fib_dir = float(dirn)
            fb      = _fib_base(p_neg, fib_dir, f_rng)
            e_px    = _entry_level(fb, fib_dir, f_rng, dirn)

            trades.append({
                "entry_idx":            entry_idx,
                "exit_idx":             i,
                "entry_ts":             row_e["ts"],
                "exit_ts":              row_x["ts"],
                "direction":            dirn,
                "fib_dir":              fib_dir,
                "fib_base":             fb,
                "fib_range":            f_rng,
                "entry_px":             e_px,
                "atr_at_entry":         atr_e,
                "outcome_pine":         outcome,
                # Confirmation signals at entry bar (momentum already recomputed)
                "exh_conf_tier":        int(row_e.get("ml_exh_confidence_tier", 0)),
                "exh_geom":             int(row_e.get("ml_exh_geom_confluence", 0)),
                "liq_sweep":            float(row_e.get("ml_liq_sweep", 0.0)),
                "htf_conf_total":       int(row_e.get("htf_conf_total", 0)),
                "ml_confluence_entry":  float(row_e.get("ml_confluence", 50.0)),
                "ml_nfe_entry":         float(row_e.get("ml_nfe", 50.0)),
            })
            entry_idx = None

        # Guard: state reset without outcome (shouldn't occur, defensive)
        if cur_state == TRADE_NONE and outcome == OUTCOME_NONE and entry_idx is not None:
            entry_idx = None

    return trades


# ── Per-trade outcome re-simulation ───────────────────────────────────────────

def _simulate_outcome(trade: dict, ohlcv: pd.DataFrame, params: dict) -> dict:
    """
    Re-simulate a single trade outcome with the trial stop family.

    Replays OHLCV bars forward from entry+1.  The continuation hold window
    (first continuationHoldBars bars) uses the widened stop; subsequent bars
    revert to the base stop family price.

    P&L uses TP1 as the win target for gross profit calculation, matching
    the objective function spec.
    """
    family    = params.get("stopFamilyId", "ATR_1_0")
    hold_bars = int(params.get("continuationHoldBars", 3))
    hold_mult = float(params.get("continuationHoldStopAtrMult", 1.0))

    fb        = trade["fib_base"]
    fib_dir   = trade["fib_dir"]
    f_rng     = trade["fib_range"]
    dirn      = trade["direction"]
    e_px      = trade["entry_px"]
    atr_e     = trade["atr_at_entry"]
    entry_idx = trade["entry_idx"]

    sl_px  = _compute_sl(family, dirn, e_px, fb, fib_dir, f_rng, atr_e)
    tp_pxs = [_fib_price(fb, fib_dir, f_rng, r) for r in (FIB_T1, FIB_T2, FIB_T3, FIB_T4, FIB_T5)]

    # Continuation hold widened stop (approximation: applies to first hold_bars)
    safe_atr    = max(atr_e, MINTICK)
    hold_sl_raw = e_px - dirn * safe_atr * hold_mult
    hold_sl     = round(hold_sl_raw / MINTICK) * MINTICK

    highest_tp  = 0
    outcome_sim = OUTCOME_EXPIRED
    MAX_BARS    = 500

    for offset in range(1, MAX_BARS):
        idx = entry_idx + offset
        if idx >= len(ohlcv):
            break

        row = ohlcv.iloc[idx]
        hi  = float(row["high"])
        lo  = float(row["low"])

        # Active stop: widened during hold window, base stop thereafter
        if offset <= hold_bars:
            active_sl = (min(sl_px, hold_sl) if dirn == 1 else max(sl_px, hold_sl))
        else:
            active_sl = sl_px

        sl_hit = (dirn == 1 and lo <= active_sl) or (dirn == -1 and hi >= active_sl)

        # Advance highest TP reached
        for tp_idx, tp_px in enumerate(tp_pxs):
            tp_hit = (dirn == 1 and hi >= tp_px) or (dirn == -1 and lo <= tp_px)
            if tp_hit and (tp_idx + 1) > highest_tp:
                highest_tp = tp_idx + 1

        if sl_hit:
            outcome_sim = OUTCOME_STOPPED
            break

        if highest_tp == 5:
            outcome_sim = OUTCOME_TP5
            break

    # Resolve: if we stopped but had already hit a TP, preserve the TP
    _tp_map = {1: OUTCOME_TP1, 2: OUTCOME_TP2, 3: OUTCOME_TP3, 4: OUTCOME_TP4, 5: OUTCOME_TP5}
    if highest_tp > 0 and outcome_sim not in (OUTCOME_STOPPED,):
        outcome_sim = _tp_map[highest_tp]
    elif outcome_sim == OUTCOME_STOPPED and highest_tp > 0:
        # Stopped after reaching TP(s) — record the highest TP as the outcome
        outcome_sim = _tp_map[highest_tp]

    # P&L: winners measured at TP1 distance, losers at actual SL distance
    if outcome_sim in WINNER_OUTCOMES:
        pnl = abs(tp_pxs[0] - e_px) * MES_POINT_VALUE - COMMISSION_SIDE * 2.0
    elif outcome_sim == OUTCOME_STOPPED:
        pnl = -abs(e_px - sl_px) * MES_POINT_VALUE - COMMISSION_SIDE * 2.0
    else:
        pnl = 0.0

    return {**trade, "sl_px": sl_px, "tp1_px": tp_pxs[0], "outcome_sim": outcome_sim, "pnl_usd": pnl}


# ── Confirmation filters ───────────────────────────────────────────────────────

def _apply_filters(trades: list[dict], params: dict, df: pd.DataFrame) -> list[dict]:
    """
    Filter trade list by parameter-dependent confirmation thresholds.
    All filters are applied post-simulation so trade count is the controlling variable.
    """
    gate_shorts   = bool(params.get("gateShortsInBullTrend", True))
    adx_floor     = float(params.get("shortTrendGateAdx", 10.0))
    momentum_min  = float(params.get("momentumMinFilter", 40.0))

    result = []
    for t in trades:
        dirn      = t["direction"]
        entry_idx = t["entry_idx"]
        row       = df.iloc[entry_idx]

        # Momentum confluence filter — uses recomputed values
        if t["ml_confluence_entry"] < momentum_min:
            continue

        # Short gate: block shorts when strong bull regime indicators align
        if gate_shorts and dirn == -1:
            adx_val   = float(row.get("_adx14", 0.0))
            di_plus   = float(row.get("_di_plus", 0.0))
            di_minus  = float(row.get("_di_minus", 0.0))
            ema100    = float(row.get("_ema100", 0.0))
            close_val = float(row.get("close", 0.0))
            if adx_val >= adx_floor and di_plus > di_minus and close_val > ema100:
                continue

        result.append(t)

    return result


# ── Composite scoring ──────────────────────────────────────────────────────────

def _empty_result() -> dict:
    return {
        "win_rate": -999.0, "pf": 0.0, "trades": 0,
        "gross_profit": 0.0, "gross_loss": 0.0,
        "max_dd_abs": 0.0, "max_dd_pct": 0.0,
        "raw_win_rate": 0.0, "pf_score": 0.0, "wr_score": 0.0,
        "consistency_score": 0.0, "years_above_breakeven": 0,
        "yearly_pf": {},
    }


def _score_trades(trades: list[dict], start_date: str) -> dict:
    """
    Composite score = 0.40 × PF_score + 0.35 × WR_score + 0.25 × consistency_score.

    Returned as result["win_rate"] so runner.py's win_rate_primary_score() maximizes it.
    Actual win rate is stored in result["raw_win_rate"].
    """
    start_ts = pd.Timestamp(start_date, tz="UTC")
    trades   = [t for t in trades if t["entry_ts"] >= start_ts]

    n_total   = len(trades)
    n_expired = sum(1 for t in trades if t["outcome_sim"] == OUTCOME_EXPIRED)

    if n_total == 0 or n_total < MIN_TRADES:
        return _empty_result()
    if n_expired / n_total > MAX_EXPIRED_FRAC:
        return _empty_result()

    tradeable   = [t for t in trades if t["outcome_sim"] != OUTCOME_EXPIRED]
    n_tradeable = len(tradeable)
    n_winners   = sum(1 for t in tradeable if t["outcome_sim"] in WINNER_OUTCOMES)

    if n_tradeable < MIN_TRADES:
        return _empty_result()

    gross_profit = sum(t["pnl_usd"] for t in tradeable if t["pnl_usd"] > 0)
    gross_loss   = abs(sum(t["pnl_usd"] for t in tradeable if t["pnl_usd"] < 0))
    pf = gross_profit / max(gross_loss, 1e-6)
    wr = n_winners / max(n_tradeable, 1)

    # Drawdown from equity curve
    pnl_arr = np.array([t["pnl_usd"] for t in tradeable])
    equity  = np.cumsum(pnl_arr)
    peak    = np.maximum.accumulate(np.concatenate([[0.0], equity]))
    dd      = peak[1:] - equity
    max_dd      = float(dd.max()) if len(dd) > 0 else 0.0
    max_dd_pct  = max_dd / peak.max() if peak.max() > 0 else 0.0

    # Yearly consistency (2020–2025)
    start_year  = pd.Timestamp(start_date).year
    end_year    = 2025
    yearly_pf: dict[int, float] = {}
    years_below = 0

    for year in range(start_year, end_year + 1):
        yr = [t for t in tradeable if t["entry_ts"].year == year]
        if len(yr) < 5:
            # Fewer than 5 tradeable trades → reject this config outright
            return _empty_result()
        if len(yr) < 10:
            yearly_pf[year] = 0.8
            years_below += 1
            continue
        yr_gp = sum(t["pnl_usd"] for t in yr if t["pnl_usd"] > 0)
        yr_gl = abs(sum(t["pnl_usd"] for t in yr if t["pnl_usd"] < 0))
        yr_pf = yr_gp / max(yr_gl, 1e-6)
        yearly_pf[year] = yr_pf
        if yr_pf < 1.0:
            years_below += 1

    n_years     = end_year - start_year + 1
    years_above = n_years - years_below
    consistency = years_above / max(n_years, 1)

    pf_score  = min(pf / 2.5, 1.0)
    wr_score  = min(wr / 0.65, 1.0)
    composite = 0.40 * pf_score + 0.35 * wr_score + 0.25 * consistency

    return {
        "win_rate":              composite,      # maximized by Optuna
        "pf":                    round(pf, 4),
        "trades":                n_tradeable,
        "gross_profit":          round(gross_profit, 2),
        "gross_loss":            round(gross_loss, 2),
        "max_dd_abs":            round(max_dd, 2),
        "max_dd_pct":            round(float(max_dd_pct), 4),
        "raw_win_rate":          round(wr, 4),
        "pf_score":              round(pf_score, 4),
        "wr_score":              round(wr_score, 4),
        "consistency_score":     round(consistency, 4),
        "years_above_breakeven": int(years_above),
        "yearly_pf":             {str(y): round(v, 4) for y, v in yearly_pf.items()},
    }


# ── Data loading ───────────────────────────────────────────────────────────────

def _parse_tv_csv(path: Path) -> pd.DataFrame:
    """
    Parse a TradingView Pine Script CSV export.

    TV exports the first column as 'time' (Unix epoch, seconds) followed by
    OHLCV then each hidden plot named by its plot() display name.
    Returns DataFrame with 'ts' as UTC datetime.
    """
    raw = pd.read_csv(path)

    time_col = next(
        (c for c in raw.columns if c.strip().lower() in ("time", "timestamp", "ts")),
        None,
    )
    if time_col is None:
        raise ValueError(
            f"No time column in TV CSV.  Expected 'time', 'timestamp', or 'ts'.  "
            f"Found: {list(raw.columns)[:10]}"
        )

    raw = raw.rename(columns={time_col: "ts"})
    if pd.api.types.is_numeric_dtype(raw["ts"]):
        raw["ts"] = pd.to_datetime(raw["ts"], unit="s", utc=True)
    else:
        raw["ts"] = pd.to_datetime(raw["ts"], utc=True)

    raw.columns = [c.strip().lower().replace(" ", "_") for c in raw.columns]
    return raw.sort_values("ts").reset_index(drop=True)


def load_data() -> pd.DataFrame:
    """
    Load the TV CSV export and merge with mes_15m.parquet OHLCV.

    Precomputes: ATR(14), EMA(100), DMI(14) — required for stop re-simulation
    and short-gate filter.

    Raises FileNotFoundError with export instructions if the CSV is absent.

    TV CSV export instructions
    --------------------------
    1. Open TradingView Desktop
    2. Load indicators/v7-warbird-institutional.pine on MES1! 15m chart
    3. Pine Editor → Export CSV (or Script → Export Data to CSV)
    4. Save to: data/optuna/v7_warbird_institutional/export.csv
    """
    if not CSV_PATH.exists():
        raise FileNotFoundError(
            f"\n\nTV CSV export not found:\n  {CSV_PATH}\n\n"
            "To generate:\n"
            "  1. Open TradingView Desktop\n"
            "  2. Load indicators/v7-warbird-institutional.pine on MES1! 15m\n"
            "  3. Pine Editor → Export → Export CSV\n"
            f"  4. Save to {CSV_PATH}\n"
            "See docs/runbooks/wbv7_institutional_optuna.md for full instructions.\n"
        )

    if not OHLCV_PATH.exists():
        raise FileNotFoundError(f"OHLCV parquet not found: {OHLCV_PATH}")

    csv_df = _parse_tv_csv(CSV_PATH)

    ohlcv = pd.read_parquet(OHLCV_PATH)[["ts", "open", "high", "low", "close", "volume"]].copy()

    # Drop OHLCV columns from CSV (parquet is ground truth)
    drop_ohlcv = [c for c in ("open", "high", "low", "close", "volume") if c in csv_df.columns]
    merged = ohlcv.merge(
        csv_df.drop(columns=drop_ohlcv, errors="ignore"),
        on="ts",
        how="left",
    )

    merged = (
        merged[merged["ts"] >= pd.Timestamp(DATA_FLOOR, tz="UTC")]
        .copy()
        .reset_index(drop=True)
    )

    hi = merged["high"].values.astype(float)
    lo = merged["low"].values.astype(float)
    cl = merged["close"].values.astype(float)

    merged["_atr14"] = _atr(hi, lo, cl, period=14)
    merged["_ema100"] = _ema(cl, period=100)

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        di_p, di_m, adx = _dmi(hi, lo, cl, period=14)
    merged["_di_plus"]  = di_p
    merged["_di_minus"] = di_m
    merged["_adx14"]    = adx

    # Fill missing Pine export columns with safe defaults
    _pine_defaults: dict[str, float] = {
        "trade_state":               0.0,
        "ml_last_exit_outcome":      0.0,
        "ml_direction_code":         1.0,
        "fib_range":                 0.0,
        "ml_fib_neg_0236":           np.nan,
        "ml_exh_confidence_tier":    0.0,
        "ml_exh_geom_confluence":    0.0,
        "ml_liq_sweep":              0.0,
        "htf_conf_total":            0.0,
        "ml_vf_bull":                50.0,
        "ml_vf_bear":                50.0,
        "ml_nfe":                    50.0,
        "ml_rsi_knn":                50.0,
        "ml_confluence":             50.0,
    }
    for col, default in _pine_defaults.items():
        if col not in merged.columns:
            merged[col] = default

    return merged


# ── Main backtest entry point ──────────────────────────────────────────────────

def run_backtest(df: pd.DataFrame, params: dict[str, Any], start_date: str) -> dict[str, Any]:
    """
    Optuna objective for v7 Warbird Institutional.

    Steps
    -----
    1. Rejection check: ATR family + oversized hold stop (undefined behavior)
    2. Recompute momentum oscillators with trial params
    3. Extract trades from Pine state machine
    4. Re-simulate each trade outcome with trial stop family against raw OHLCV
    5. Apply confirmation filters (momentum threshold, short gate)
    6. Score with composite objective

    Return dict
    -----------
    win_rate     = composite_score (0.40 × PF + 0.35 × WR + 0.25 × consistency)
                   This is what runner.py maximizes via win_rate_primary_score().
    pf           = actual profit factor
    trades       = tradeable trade count (EXPIRED excluded)
    gross_profit, gross_loss, max_dd_abs, max_dd_pct
    raw_win_rate = actual TP1+ hit rate
    pf_score, wr_score, consistency_score
    years_above_breakeven, yearly_pf

    Rejection rules (returns win_rate=-999.0)
    -----------------------------------------
    - < 80 tradeable trades
    - > 70% EXPIRED outcomes
    - Any year with 1–4 tradeable trades (data gap or broken config)
    - ATR stop family + continuationHoldStopAtrMult > 2.5 (stop geometry undefined)
    """
    # Rejection: ATR family + oversized hold stop
    atr_families = frozenset({"ATR_1_0", "ATR_1_5", "ATR_STRUCTURE_1_25"})
    if (params.get("stopFamilyId") in atr_families and
            float(params.get("continuationHoldStopAtrMult", 1.0)) > 2.5):
        return _empty_result()

    work   = _add_momentum(df, params)
    trades = _extract_trades(work)
    if not trades:
        return _empty_result()

    sim    = [_simulate_outcome(t, work, params) for t in trades]
    sim    = _apply_filters(sim, params, work)

    return _score_trades(sim, start_date)
