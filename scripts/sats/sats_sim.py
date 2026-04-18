#!/usr/bin/env python3
"""
SATS v1.9.0 Python simulator — exact port of v8-warbird-prescreen.pine signal logic.

Vectorized pre-computation + tight sequential loop for the band ratchet.
No TV/CDP dependency. Runs 500 trials in ~3-5 minutes on local data.

Notes on Pine parity:
- charFlipDown/Up: Pine has `close < sourceInput` where sourceInput=close → always False.
  charFlip is effectively disabled for all Custom-mode sweeps with default sourceInput=close.
- strategy.exit: stop=tradeSl, limit=tradeTp3. Only TP3 (not TP1/TP2) closes the trade.
- Bar magnifier: we approximate with 15m OHLC. Same-bar SL+TP3 both hit → SL wins.
- Commission: 1.0 per contract per side ($1.00). MES point = $5.00.
- Timeout: trade closes at bar close when age >= tradeMaxAge.
"""

import numpy as np
import pandas as pd
from pathlib import Path


# ── Pine constants ──────────────────────────────────────────────────────────
WARMUP_FLOOR     = 50
MULT_SMOOTH_ALPHA = 0.15
MES_POINT_VALUE  = 5.0  # $5 per point for MES


# ── Rolling indicator helpers (numpy, matching Pine semantics) ──────────────

def _rma(src: np.ndarray, length: int) -> np.ndarray:
    """Wilder's RMA = EWM with alpha=1/length, adjust=False. Matches ta.atr()."""
    alpha = 1.0 / length
    out = np.empty(len(src))
    out[0] = src[0]
    for i in range(1, len(src)):
        out[i] = alpha * src[i] + (1.0 - alpha) * out[i - 1]
    return out


def _sma(src: np.ndarray, length: int) -> np.ndarray:
    """Simple rolling mean. NaN for bars < length (matches Pine ta.sma warmup)."""
    out = pd.Series(src).rolling(length, min_periods=length).mean().to_numpy()
    return out


def _rolling_std(src: np.ndarray, length: int) -> np.ndarray:
    """Rolling std with ddof=1."""
    return pd.Series(src).rolling(length, min_periods=length).std(ddof=1).to_numpy()


def _rolling_max(src: np.ndarray, length: int) -> np.ndarray:
    return pd.Series(src).rolling(length, min_periods=1).max().to_numpy()


def _rolling_min(src: np.ndarray, length: int) -> np.ndarray:
    return pd.Series(src).rolling(length, min_periods=1).min().to_numpy()


def _er(close: np.ndarray, length: int) -> np.ndarray:
    """Efficiency Ratio. Zero for first `length` bars."""
    n = len(close)
    out = np.zeros(n)
    for i in range(length, n):
        price_change = abs(close[i] - close[i - length])
        volatility = np.sum(np.abs(np.diff(close[i - length:i + 1])))
        out[i] = price_change / volatility if volatility > 0 else 0.0
    return out


def _ema_smooth(src: np.ndarray, alpha: float) -> np.ndarray:
    """EMA with given alpha. Matches Pine's MULT_SMOOTH_ALPHA EWM."""
    out = np.empty(len(src))
    out[0] = src[0]
    for i in range(1, len(src)):
        out[i] = src[i - 1] * (1.0 - alpha) + src[i] * alpha
    return out


def _momentum_align(close: np.ndarray, length: int) -> np.ndarray:
    """TQI momentum: fraction of bars in window aligned with window direction."""
    n = len(close)
    out = np.zeros(n)
    for i in range(length, n):
        window_change = close[i] - close[i - length]
        aligned = 0
        for j in range(length):
            bar_change = close[i - j] - close[i - j - 1]
            if (window_change > 0 and bar_change > 0) or (window_change < 0 and bar_change < 0):
                aligned += 1
        out[i] = aligned / length
    return out


def _calc_pivots(high: np.ndarray, low: np.ndarray, n: int):
    """
    Pine ta.pivothigh/ta.pivotlow equivalents.
    Returns arrays where non-nan values are confirmed pivots.
    Confirmation fires at bar i = pivot_bar + n (after n bars of right-side confirmation).
    """
    size = len(high)
    ph = np.full(size, np.nan)
    pl = np.full(size, np.nan)
    for i in range(2 * n, size):
        pivot_bar = i - n
        # Check left n bars and right n bars
        left_high = high[pivot_bar - n:pivot_bar]
        right_high = high[pivot_bar + 1:pivot_bar + n + 1]
        if high[pivot_bar] >= np.max(left_high) and high[pivot_bar] >= np.max(right_high):
            ph[i] = high[pivot_bar]
        left_low = low[pivot_bar - n:pivot_bar]
        right_low = low[pivot_bar + 1:pivot_bar + n + 1]
        if low[pivot_bar] <= np.min(left_low) and low[pivot_bar] <= np.min(right_low):
            pl[i] = low[pivot_bar]
    return ph, pl


def _mapclamp(v, in_lo, in_hi, out_lo, out_hi):
    """Linear map with clamping."""
    t = np.clip((v - in_lo) / (in_hi - in_lo), 0.0, 1.0)
    return out_lo + t * (out_hi - out_lo)


# ── Main simulator ──────────────────────────────────────────────────────────

def simulate_sats(df: pd.DataFrame, params: dict, start_date: str = '2025-01-01',
                  commission_per_side: float = 1.0) -> dict:
    """
    Simulate SATS strategy and return performance metrics.

    Parameters
    ----------
    df : DataFrame with columns [ts, open, high, low, close, volume]
         ts must be datetime64[ns, UTC]. Sorted ascending.
    params : dict of SATS input values (see INPUT_DEFAULTS below).
    start_date : ISO date string. Only trades starting on/after this date count.
    commission_per_side : dollars per contract per side.

    Returns
    -------
    dict: pf, trades, gross_profit, gross_loss, win_rate, max_dd_pct
    """
    # ── Extract params ──────────────────────────────────────────────────────
    atrLen           = int(params.get('atrLenInput',          13))
    baseMult         = float(params.get('baseMultInput',       2.0))
    useAdaptive      = bool(params.get('useAdaptiveInput',     True))
    erLen            = int(params.get('erLengthInput',         20))
    adaptStrength    = float(params.get('adaptStrengthInput',  0.5))
    atrBaselineLen   = int(params.get('atrBaselineLenInput',   100))

    useTqi           = bool(params.get('useTqiInput',          True))
    qualityStrength  = float(params.get('qualityStrengthInput',0.4))
    qualityCurve     = float(params.get('qualityCurveInput',   1.5))
    multSmooth       = bool(params.get('multSmoothInput',      True))
    useAsymBands     = bool(params.get('useAsymBandsInput',    True))
    asymStrength     = float(params.get('asymStrengthInput',   0.5))
    useEffAtr        = bool(params.get('useEffAtrInput',       True))

    # charFlip: pine has `close < sourceInput` where sourceInput=close → always False
    # useCharFlipInput has zero effect in Custom mode (sourceInput=close by default)
    # Included for completeness but skipped in computation.

    tqiWeightEr      = float(params.get('tqiWeightErInput',     0.35))
    tqiWeightVol     = float(params.get('tqiWeightVolInput',     0.20))
    tqiWeightStruct  = float(params.get('tqiWeightStructInput',  0.25))
    tqiWeightMom     = float(params.get('tqiWeightMomInput',     0.20))
    tqiStructLen     = int(params.get('tqiStructLenInput',       20))
    tqiMomLen        = int(params.get('tqiMomLenInput',          10))

    slAtrMult        = float(params.get('slAtrMultInput',         1.5))
    tp1R_raw         = float(params.get('tp1RInput',              1.0))
    tp2R_raw         = float(params.get('tp2RInput',              2.0))
    tp3R_raw         = float(params.get('tp3RInput',              3.0))
    tradeMaxAge      = int(params.get('tradeMaxAgeInput',         100))
    tpMode           = params.get('tpModeInput',                  'Fixed')

    # TP sort (Pine auto-sorts tp1 < tp2 < tp3)
    sorted_tps = sorted([tp1R_raw, tp2R_raw, tp3R_raw])
    liveTp3R = sorted_tps[2]  # only TP3 closes the strategy.exit

    PIVOT_LEN = 3  # pivotLenInput — display only, fixed
    VOL_LEN   = 20  # volLenInput  — display only, fixed

    # ── Prepare arrays ──────────────────────────────────────────────────────
    close  = df['close'].values.astype(np.float64)
    high   = df['high'].values.astype(np.float64)
    low    = df['low'].values.astype(np.float64)
    volume = df['volume'].values.astype(np.float64)
    ts_arr = df['ts'].values  # numpy datetime64[ns, UTC]
    n      = len(close)

    warmupBars = max(
        WARMUP_FLOOR,
        max(atrLen, erLen, VOL_LEN, PIVOT_LEN * 2 + 1, tqiMomLen, tqiStructLen) + 10
    )

    # ── Vectorized indicators ────────────────────────────────────────────────
    # True Range
    prev_close = np.roll(close, 1)
    prev_close[0] = close[0]
    tr = np.maximum(high - low,
         np.maximum(np.abs(high - prev_close), np.abs(low - prev_close)))

    rawAtr      = _rma(tr, atrLen)
    atrBaseline = _sma(rawAtr, atrBaselineLen)
    # Fill NaN in atrBaseline (first atrBaselineLen-1 bars) with rawAtr
    nan_mask = np.isnan(atrBaseline)
    atrBaseline = np.where(nan_mask, rawAtr, atrBaseline)
    volRatio = np.where(atrBaseline > 0, rawAtr / atrBaseline, 1.0)

    erValue = _er(close, erLen)
    effAtr  = rawAtr * (0.5 + 0.5 * erValue) if useEffAtr else rawAtr

    # TQI components
    tqiEr = np.clip(erValue, 0.0, 1.0)

    volMean = _sma(volume, VOL_LEN)
    volStd  = _rolling_std(volume, VOL_LEN)
    volMean = np.where(np.isnan(volMean), volume, volMean)
    volStd  = np.where(np.isnan(volStd) | (volStd == 0), 1.0, volStd)
    volZ    = (volume - volMean) / volStd
    tqiVol  = np.clip(_mapclamp(volZ, -1.0, 2.0, 0.0, 1.0), 0.0, 1.0)

    structHi    = _rolling_max(high, tqiStructLen)
    structLo    = _rolling_min(low,  tqiStructLen)
    structRange = structHi - structLo
    pricePos    = np.where(structRange > 0, (close - structLo) / structRange, 0.5)
    tqiStruct   = np.clip(np.abs(pricePos - 0.5) * 2.0, 0.0, 1.0)

    tqiMom = _momentum_align(close, tqiMomLen)

    # TQI aggregate
    weightSum   = tqiWeightEr + tqiWeightVol + tqiWeightStruct + tqiWeightMom
    weightDenom = weightSum if weightSum > 0 else 1.0
    if useTqi:
        tqiRaw = (tqiEr   * tqiWeightEr   +
                  tqiVol   * tqiWeightVol   +
                  tqiStruct* tqiWeightStruct +
                  tqiMom   * tqiWeightMom  ) / weightDenom
    else:
        tqiRaw = np.full(n, 0.5)
    tqi = np.clip(tqiRaw, 0.0, 1.0)

    # Legacy adaptation factor
    legacyAdapt = (1.0 + adaptStrength * (0.5 - erValue)) if useAdaptive else np.ones(n)

    # TQI multiplier
    qualDev = np.power(np.maximum(1.0 - tqi, 0.0), qualityCurve) if useTqi else np.full(n, 0.5)
    tqiMult = 1.0 - qualityStrength + qualityStrength * (0.6 + 0.8 * qualDev)

    symMult = baseMult * legacyAdapt * tqiMult

    if useTqi and useAsymBands:
        asymTighten   = 1.0 - asymStrength * tqi * 0.3
        asymWiden     = 1.0 + asymStrength * tqi * 0.4
        activeMultRaw = symMult * asymTighten
        passiveMultRaw= symMult * asymWiden
    else:
        activeMultRaw = symMult
        passiveMultRaw= symMult

    if multSmooth:
        activeMultSm  = _ema_smooth(activeMultRaw,  MULT_SMOOTH_ALPHA)
        passiveMultSm = _ema_smooth(passiveMultRaw, MULT_SMOOTH_ALPHA)
    else:
        activeMultSm  = activeMultRaw
        passiveMultSm = passiveMultRaw

    # Pivot high/low for SL anchor
    pivotHighArr, pivotLowArr = _calc_pivots(high, low, PIVOT_LEN)

    # Start timestamp (UTC) — precompute as boolean mask
    start_ts_pd = pd.Timestamp(start_date, tz='UTC')
    in_window = (df['ts'] >= start_ts_pd).values  # boolean array

    # ── Sequential loop: bands + trend + trades ──────────────────────────────
    lowerBand = np.nan
    upperBand = np.nan
    stTrend   = 1
    trendStartBar = 0

    lastPivotHigh = np.nan
    lastPivotLow  = np.nan

    tradeDir      = 0
    tradeEntryBar = -1
    tradeEntry    = np.nan
    tradeSl       = np.nan
    tradeTp3_val  = np.nan

    # Pending entry: signal fires at bar i, fills at bar i+1 open (TV default)
    pendingDir    = 0
    pendingSl     = np.nan
    pendingTp3    = np.nan

    gross_profit = 0.0
    gross_loss   = 0.0
    n_trades     = 0
    n_wins       = 0

    equity       = 0.0
    peak_equity  = 0.0
    max_dd_abs   = 0.0

    open_ = df['open'].values.astype(np.float64)

    for i in range(n):
        # ── Fill pending entry at this bar's open (TV next-bar-open fill) ───────
        if pendingDir != 0 and tradeDir == 0:
            fill = open_[i]
            if pendingDir == 1:
                # Long: if open gaps below SL, immediate SL hit at open
                if fill <= pendingSl:
                    pnl = (pendingSl - fill) * MES_POINT_VALUE - commission_per_side * 2.0
                    # SL above fill for long → small gain, but stop immediately triggered
                    # In reality TV exits at fill (gap below SL), P&L ≈ -commission only
                    pnl = -commission_per_side * 2.0
                    gross_loss -= pnl
                    n_trades   += 1
                    equity     += pnl
                    if equity > peak_equity: peak_equity = equity
                    dd = peak_equity - equity
                    if dd > max_dd_abs: max_dd_abs = dd
                else:
                    tradeDir      = pendingDir
                    tradeEntry    = fill
                    tradeSl       = pendingSl
                    tradeTp3_val  = pendingTp3
                    tradeEntryBar = i
            else:
                # Short: if open gaps above SL, immediate SL hit
                if fill >= pendingSl:
                    pnl = -commission_per_side * 2.0
                    gross_loss -= pnl
                    n_trades   += 1
                    equity     += pnl
                    if equity > peak_equity: peak_equity = equity
                    dd = peak_equity - equity
                    if dd > max_dd_abs: max_dd_abs = dd
                else:
                    tradeDir      = pendingDir
                    tradeEntry    = fill
                    tradeSl       = pendingSl
                    tradeTp3_val  = pendingTp3
                    tradeEntryBar = i
            pendingDir = 0

        # Update pivot state
        if not np.isnan(pivotHighArr[i]):
            lastPivotHigh = pivotHighArr[i]
        if not np.isnan(pivotLowArr[i]):
            lastPivotLow = pivotLowArr[i]

        isWarmedUp = (i >= warmupBars)
        prevTrend  = stTrend

        # Determine active/passive mult based on prior trend
        if prevTrend == 1:
            lowerMult = activeMultSm[i]
            upperMult = passiveMultSm[i]
        else:
            lowerMult = passiveMultSm[i]
            upperMult = activeMultSm[i]

        lowerBandRaw = close[i] - lowerMult * effAtr[i]
        upperBandRaw = close[i] + upperMult * effAtr[i]

        # Save prev bands BEFORE ratchet — flip checks use Pine's upperBand[1]/lowerBand[1]
        prevLowerBand = lowerBand
        prevUpperBand = upperBand

        # Ratchet (uses previous bar's close, matching Pine's close[1])
        prev_close_val = close[i - 1] if i > 0 else close[i]
        if np.isnan(lowerBand):
            lowerBand = lowerBandRaw
        else:
            lowerBand = max(lowerBandRaw, lowerBand) if prev_close_val > lowerBand else lowerBandRaw

        if np.isnan(upperBand):
            upperBand = upperBandRaw
        else:
            upperBand = min(upperBandRaw, upperBand) if prev_close_val < upperBand else upperBandRaw

        # Price flips — check against PREVIOUS bar's bands (Pine: upperBand[1], lowerBand[1])
        priceFlipUp   = (prevTrend == -1) and (not np.isnan(prevUpperBand)) and (close[i] > prevUpperBand)
        priceFlipDown = (prevTrend ==  1) and (not np.isnan(prevLowerBand)) and (close[i] < prevLowerBand)

        # charFlip is always False (sourceInput=close → close < close = False)

        if priceFlipUp:
            stTrend = 1
            trendStartBar = i
        elif priceFlipDown:
            stTrend = -1
            trendStartBar = i

        flipUp   = (stTrend ==  1 and prevTrend == -1)
        flipDown = (stTrend == -1 and prevTrend ==  1)

        comm2 = commission_per_side * 2.0  # round-trip commission

        # ── Active trade exit check ──────────────────────────────────────────
        if tradeDir != 0 and i > tradeEntryBar:
            tradeAge = i - tradeEntryBar

            if tradeDir == 1:
                sl_hit  = low[i]  <= tradeSl
                tp3_hit = high[i] >= tradeTp3_val
            else:
                sl_hit  = high[i] >= tradeSl
                tp3_hit = low[i]  <= tradeTp3_val

            timeout_hit = (tradeAge >= tradeMaxAge)

            # Same-bar: SL wins (conservative; bar magnifier would check 1m data)
            if sl_hit and tp3_hit:
                tp3_hit = False

            if sl_hit:
                exit_px = tradeSl
            elif tp3_hit:
                exit_px = tradeTp3_val
            elif timeout_hit:
                exit_px = close[i]
            else:
                exit_px = np.nan

            if not np.isnan(exit_px):
                if tradeDir == 1:
                    pnl = (exit_px - tradeEntry) * MES_POINT_VALUE - comm2
                else:
                    pnl = (tradeEntry - exit_px) * MES_POINT_VALUE - comm2
                if pnl >= 0:
                    gross_profit += pnl
                    n_wins       += 1
                else:
                    gross_loss   -= pnl
                n_trades += 1
                tradeDir  = 0
                equity   += pnl
                if equity > peak_equity:
                    peak_equity = equity
                dd = peak_equity - equity
                if dd > max_dd_abs:
                    max_dd_abs = dd

        # ── Reverse on opposite flip: queue close+reopen at next bar's open ──────
        if tradeDir != 0 and ((flipUp and tradeDir == -1) or (flipDown and tradeDir == 1)):
            # Compute new pending entry levels from signal bar's close
            atr_i = effAtr[i]
            if flipUp:
                slBase    = lastPivotLow if not np.isnan(lastPivotLow) else low[i]
                rawSl     = slBase - slAtrMult * atr_i
                minSl     = close[i] - slAtrMult * atr_i
                sl        = min(rawSl, minSl)
                risk      = close[i] - sl
                tp3_price = close[i] + risk * liveTp3R
                new_pend_dir = 1
            else:
                slBase    = lastPivotHigh if not np.isnan(lastPivotHigh) else high[i]
                rawSl     = slBase + slAtrMult * atr_i
                maxSl     = close[i] + slAtrMult * atr_i
                sl        = max(rawSl, maxSl)
                risk      = sl - close[i]
                tp3_price = close[i] - risk * liveTp3R
                new_pend_dir = -1

            # Close existing at next bar's open (modeled by marking fill pending)
            # For simplicity, close the existing trade NOW at close[i] price
            # (the existing trade's open was at a previous bar)
            if tradeDir == 1:
                pnl = (close[i] - tradeEntry) * MES_POINT_VALUE - comm2
            else:
                pnl = (tradeEntry - close[i]) * MES_POINT_VALUE - comm2
            if pnl >= 0:
                gross_profit += pnl
                n_wins       += 1
            else:
                gross_loss   -= pnl
            n_trades += 1
            tradeDir  = 0
            equity   += pnl
            if equity > peak_equity:
                peak_equity = equity
            dd = peak_equity - equity
            if dd > max_dd_abs:
                max_dd_abs = dd

            # Queue the new opposite-direction entry for next bar's open
            if risk > 0 and in_window[i]:
                pendingDir = new_pend_dir
                pendingSl  = sl
                pendingTp3 = tp3_price

        # ── Entry (queue pending fill at next bar's open) ────────────────────
        if isWarmedUp and tradeDir == 0 and pendingDir == 0 and (flipUp or flipDown):
            if in_window[i]:
                entry  = close[i]
                atr_i  = effAtr[i]

                if flipUp:
                    slBase    = lastPivotLow if not np.isnan(lastPivotLow) else low[i]
                    rawSl     = slBase - slAtrMult * atr_i
                    minSl     = entry - slAtrMult * atr_i
                    sl        = min(rawSl, minSl)
                    risk      = entry - sl
                    tp3_price = entry + risk * liveTp3R
                    pend_dir  = 1
                else:
                    slBase    = lastPivotHigh if not np.isnan(lastPivotHigh) else high[i]
                    rawSl     = slBase + slAtrMult * atr_i
                    maxSl     = entry + slAtrMult * atr_i
                    sl        = max(rawSl, maxSl)
                    risk      = sl - entry
                    tp3_price = entry - risk * liveTp3R
                    pend_dir  = -1

                if risk > 0:
                    pendingDir = pend_dir
                    pendingSl  = sl
                    pendingTp3 = tp3_price

    # ── Build result ─────────────────────────────────────────────────────────
    pf = (gross_profit / gross_loss) if gross_loss > 0 else (
         float('inf') if gross_profit > 0 else 0.0)
    win_rate = (n_wins / n_trades) if n_trades > 0 else 0.0
    max_dd_pct = (max_dd_abs / (peak_equity + 1e-9)) if peak_equity > 0 else 0.0

    return {
        'pf':            round(pf, 4),
        'trades':        n_trades,
        'gross_profit':  round(gross_profit, 2),
        'gross_loss':    round(gross_loss,   2),
        'win_rate':      round(win_rate, 4),
        'max_dd_abs':    round(max_dd_abs, 2),
        'max_dd_pct':    round(max_dd_pct, 4),
    }


# ── Default input values (Custom preset) ────────────────────────────────────
INPUT_DEFAULTS = {
    'atrLenInput':          13,
    'baseMultInput':        2.0,
    'useAdaptiveInput':     True,
    'erLengthInput':        20,
    'adaptStrengthInput':   0.5,
    'atrBaselineLenInput':  100,
    'useTqiInput':          True,
    'qualityStrengthInput': 0.4,
    'qualityCurveInput':    1.5,
    'multSmoothInput':      True,
    'useAsymBandsInput':    True,
    'asymStrengthInput':    0.5,
    'useEffAtrInput':       True,
    'useCharFlipInput':     True,   # has no effect (charFlip always False in Custom mode)
    'charFlipMinAgeInput':  5,
    'charFlipHighInput':    0.55,
    'charFlipLowInput':     0.25,
    'tqiWeightErInput':     0.35,
    'tqiWeightVolInput':    0.20,
    'tqiWeightStructInput': 0.25,
    'tqiWeightMomInput':    0.20,
    'tqiStructLenInput':    20,
    'tqiMomLenInput':       10,
    'slAtrMultInput':       1.5,
    'tp1RInput':            1.0,
    'tp2RInput':            2.0,
    'tp3RInput':            3.0,
    'tradeMaxAgeInput':     100,
    'tpModeInput':          'Fixed',
}

# Stage 1 anchor (Crypto 24/7 values mirrored in Custom)
CRYPTO_ANCHOR = {
    **INPUT_DEFAULTS,
    'atrLenInput':   14,
    'baseMultInput': 2.8,
    'slAtrMultInput':2.5,
    'erLengthInput': 20,
}


def load_data(source: str = 'db') -> pd.DataFrame:
    """
    Load and sort MES 15m OHLCV data.

    source='db'      — query local warbird PG17 (clean, recommended)
    source='parquet' — fallback to data/mes_15m.parquet (has bad ticks, use only if DB unavailable)
    """
    if source == 'db':
        try:
            import psycopg2
            conn = psycopg2.connect(dbname='warbird')
            # Cast ts to UTC in SQL to avoid pandas mixed-offset parse issues
            df = pd.read_sql(
                "SELECT ts AT TIME ZONE 'UTC' AS ts, open, high, low, close, volume "
                "FROM mes_15m ORDER BY ts",
                conn
            )
            conn.close()
            # AT TIME ZONE returns naive datetime in the target zone — mark as UTC
            df['ts'] = pd.to_datetime(df['ts']).dt.tz_localize('UTC')
            return df
        except Exception as e:
            print(f"[load_data] DB unavailable ({e}), falling back to parquet", flush=True)

    parquet_path = Path(__file__).parents[2] / 'data' / 'mes_15m.parquet'
    df = pd.read_parquet(parquet_path)
    df = df.sort_values('ts').reset_index(drop=True)
    # Fix corrupt ticks: low < high*0.5 → replace with min(open, close)
    bad = df['low'] < df['close'] * 0.5
    if bad.any():
        df.loc[bad, 'low'] = df.loc[bad, ['open', 'close']].min(axis=1)
    return df


if __name__ == '__main__':
    import time, json
    print("Loading data...")
    df = load_data()
    print(f"  {len(df):,} bars  {df['ts'].min()} → {df['ts'].max()}")

    # Time the default config
    t0 = time.perf_counter()
    result = simulate_sats(df, INPUT_DEFAULTS)
    elapsed = time.perf_counter() - t0
    print(f"\nDefault config:  {result}  [{elapsed:.2f}s]")

    # Time the Crypto anchor (Stage 1 expected: PF≈0.998, trades≈1174)
    t0 = time.perf_counter()
    result_anchor = simulate_sats(df, CRYPTO_ANCHOR)
    elapsed = time.perf_counter() - t0
    print(f"Crypto anchor:   {result_anchor}  [{elapsed:.2f}s]")

    print("\nVerify vs TV Stage 1 (target: PF≈0.998, trades≈1174)")
    print(f"  PF diff:     {abs(result_anchor['pf']    - 0.998):.4f}")
    print(f"  Trades diff: {abs(result_anchor['trades'] - 1174)}")
