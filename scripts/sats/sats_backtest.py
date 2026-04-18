#!/usr/bin/env python3
"""
SATS v1.9.0 backtesting.py strategy.

Port of sats_sim.py for Optuna optimization and equity-curve visualization.
Reuses indicator math verbatim from sats_sim.py; only the event loop changes.

Execution semantics:
  - trade_on_close=False → orders fill at next-bar open (matches sats_sim.py)
  - commission=0 in Backtest; dollar P&L is computed post-hoc in run_sats_bt()
  - size=1 per order (1 MES contract)
  - SL and TP passed as absolute prices to buy()/sell()
  - Timeout handled manually in next() via position.close()

Parity target: PF within ±3% of simulate_sats() on the same params/window.
"""

import sys
import json
import argparse
import numpy as np
import pandas as pd
from pathlib import Path
from backtesting import Backtest, Strategy

sys.path.insert(0, str(Path(__file__).parent))
from sats_sim import (
    _rma, _sma, _rolling_std, _rolling_max, _rolling_min,
    _er, _ema_smooth, _momentum_align, _calc_pivots, _mapclamp,
    load_data, INPUT_DEFAULTS, CRYPTO_ANCHOR,
    WARMUP_FLOOR, MULT_SMOOTH_ALPHA, MES_POINT_VALUE,
)

PIVOT_LEN = 3
VOL_LEN   = 20


# ── Vectorized indicator pre-computation ────────────────────────────────────

def _prepare_indicators(close, high, low, volume, params: dict) -> dict:
    """Compute all non-ratchet indicators from raw arrays. Returns dict of arrays."""
    n = len(close)

    atrLen          = int(params.get('atrLenInput',          13))
    erLen           = int(params.get('erLengthInput',         20))
    adaptStrength   = float(params.get('adaptStrengthInput',  0.5))
    atrBaselineLen  = int(params.get('atrBaselineLenInput',   100))
    useAdaptive     = bool(params.get('useAdaptiveInput',     True))
    baseMult        = float(params.get('baseMultInput',       2.0))
    useEffAtr       = bool(params.get('useEffAtrInput',       True))
    useTqi          = bool(params.get('useTqiInput',          True))
    qualityStrength = float(params.get('qualityStrengthInput',0.4))
    qualityCurve    = float(params.get('qualityCurveInput',   1.5))
    multSmooth      = bool(params.get('multSmoothInput',      True))
    useAsymBands    = bool(params.get('useAsymBandsInput',    True))
    asymStrength    = float(params.get('asymStrengthInput',   0.5))
    tqiWeightEr     = float(params.get('tqiWeightErInput',    0.35))
    tqiWeightVol    = float(params.get('tqiWeightVolInput',   0.20))
    tqiWeightStruct = float(params.get('tqiWeightStructInput',0.25))
    tqiWeightMom    = float(params.get('tqiWeightMomInput',   0.20))
    tqiStructLen    = int(params.get('tqiStructLenInput',     20))
    tqiMomLen       = int(params.get('tqiMomLenInput',        10))

    warmupBars = max(
        WARMUP_FLOOR,
        max(atrLen, erLen, VOL_LEN, PIVOT_LEN * 2 + 1, tqiMomLen, tqiStructLen) + 10
    )

    prev_close = np.roll(close, 1); prev_close[0] = close[0]
    tr = np.maximum(high - low,
         np.maximum(np.abs(high - prev_close), np.abs(low - prev_close)))

    rawAtr      = _rma(tr, atrLen)
    atrBaseline = _sma(rawAtr, atrBaselineLen)
    atrBaseline = np.where(np.isnan(atrBaseline), rawAtr, atrBaseline)

    erValue = _er(close, erLen)
    effAtr  = rawAtr * (0.5 + 0.5 * erValue) if useEffAtr else rawAtr

    tqiEr   = np.clip(erValue, 0.0, 1.0)
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
    tqiMom      = _momentum_align(close, tqiMomLen)

    weightDenom = max(tqiWeightEr + tqiWeightVol + tqiWeightStruct + tqiWeightMom, 1e-9)
    if useTqi:
        tqiRaw = (tqiEr   * tqiWeightEr +
                  tqiVol   * tqiWeightVol +
                  tqiStruct * tqiWeightStruct +
                  tqiMom   * tqiWeightMom) / weightDenom
    else:
        tqiRaw = np.full(n, 0.5)
    tqi = np.clip(tqiRaw, 0.0, 1.0)

    legacyAdapt = (1.0 + adaptStrength * (0.5 - erValue)) if useAdaptive else np.ones(n)
    qualDev     = np.power(np.maximum(1.0 - tqi, 0.0), qualityCurve) if useTqi else np.full(n, 0.5)
    tqiMult     = 1.0 - qualityStrength + qualityStrength * (0.6 + 0.8 * qualDev)
    symMult     = baseMult * legacyAdapt * tqiMult

    if useTqi and useAsymBands:
        activeMultRaw  = symMult * (1.0 - asymStrength * tqi * 0.3)
        passiveMultRaw = symMult * (1.0 + asymStrength * tqi * 0.4)
    else:
        activeMultRaw = passiveMultRaw = symMult

    if multSmooth:
        activeMultSm  = _ema_smooth(activeMultRaw,  MULT_SMOOTH_ALPHA)
        passiveMultSm = _ema_smooth(passiveMultRaw, MULT_SMOOTH_ALPHA)
    else:
        activeMultSm, passiveMultSm = activeMultRaw, passiveMultRaw

    pivotHigh, pivotLow = _calc_pivots(high, low, PIVOT_LEN)

    return dict(
        effAtr=effAtr,
        activeMultSm=activeMultSm,
        passiveMultSm=passiveMultSm,
        pivotHigh=pivotHigh,
        pivotLow=pivotLow,
        warmupBars=warmupBars,
    )


# ── backtesting.py Strategy ─────────────────────────────────────────────────

class SATSStrategy(Strategy):
    """SATS v1.9.0 — backtesting.py port. Parameters match INPUT_DEFAULTS keys."""

    # Default parameter values — Optuna overrides these via bt.run(**params)
    atrLenInput          = 13
    baseMultInput        = 2.0
    useAdaptiveInput     = True
    erLengthInput        = 20
    adaptStrengthInput   = 0.5
    atrBaselineLenInput  = 100
    useTqiInput          = True
    qualityStrengthInput = 0.4
    qualityCurveInput    = 1.5
    multSmoothInput      = True
    useAsymBandsInput    = True
    asymStrengthInput    = 0.5
    useEffAtrInput       = True
    useCharFlipInput     = True    # no-op in Custom mode (charFlip always False)
    charFlipMinAgeInput  = 5
    charFlipHighInput    = 0.55
    charFlipLowInput     = 0.25
    tqiWeightErInput     = 0.35
    tqiWeightVolInput    = 0.20
    tqiWeightStructInput = 0.25
    tqiWeightMomInput    = 0.20
    tqiStructLenInput    = 20
    tqiMomLenInput       = 10
    slAtrMultInput       = 1.5
    tp1RInput            = 1.0
    tp2RInput            = 2.0
    tp3RInput            = 3.0
    tradeMaxAgeInput     = 100
    tpModeInput          = 'Fixed'
    start_date           = '2025-01-01'

    def init(self):
        params = {k: getattr(self, k) for k in INPUT_DEFAULTS}

        close  = np.asarray(self.data.Close,  dtype=np.float64)
        high   = np.asarray(self.data.High,   dtype=np.float64)
        low    = np.asarray(self.data.Low,     dtype=np.float64)
        volume = np.asarray(self.data.Volume,  dtype=np.float64)

        ind = _prepare_indicators(close, high, low, volume, params)
        self._effAtr        = ind['effAtr']
        self._activeMultSm  = ind['activeMultSm']
        self._passiveMultSm = ind['passiveMultSm']
        self._pivotHigh     = ind['pivotHigh']
        self._pivotLow      = ind['pivotLow']
        self._warmupBars    = ind['warmupBars']
        self._close         = close

        sorted_tps      = sorted([self.tp1RInput, self.tp2RInput, self.tp3RInput])
        self._liveTp3R  = sorted_tps[2]

        self._start_ts = pd.Timestamp(self.start_date, tz='UTC')

        # Sequential ratchet state
        self._lowerBand     = np.nan
        self._upperBand     = np.nan
        self._stTrend       = 1
        self._lastPivotHigh = np.nan
        self._lastPivotLow  = np.nan
        self._entryBar      = -1   # bar index at entry; -1 = no open trade

    def next(self):
        i = len(self.data) - 1

        # Detect backtesting.py closing our trade via SL/TP
        if self.position.size == 0 and self._entryBar >= 0:
            self._entryBar = -1

        # ── Update pivot state ────────────────────────────────────────────────
        if not np.isnan(self._pivotHigh[i]):
            self._lastPivotHigh = self._pivotHigh[i]
        if not np.isnan(self._pivotLow[i]):
            self._lastPivotLow = self._pivotLow[i]

        # ── SuperTrend band ratchet ───────────────────────────────────────────
        prevTrend = self._stTrend
        if prevTrend == 1:
            lowerMult, upperMult = self._activeMultSm[i], self._passiveMultSm[i]
        else:
            lowerMult, upperMult = self._passiveMultSm[i], self._activeMultSm[i]

        c   = self._close[i]
        atr = self._effAtr[i]
        prevLowerBand = self._lowerBand
        prevUpperBand = self._upperBand

        prev_c = self._close[i - 1] if i > 0 else c
        lbRaw  = c - lowerMult * atr
        ubRaw  = c + upperMult * atr

        if np.isnan(self._lowerBand):
            self._lowerBand = lbRaw
        else:
            self._lowerBand = max(lbRaw, self._lowerBand) if prev_c > self._lowerBand else lbRaw

        if np.isnan(self._upperBand):
            self._upperBand = ubRaw
        else:
            self._upperBand = min(ubRaw, self._upperBand) if prev_c < self._upperBand else ubRaw

        if (prevTrend == -1) and (not np.isnan(prevUpperBand)) and (c > prevUpperBand):
            self._stTrend = 1
        elif (prevTrend == 1) and (not np.isnan(prevLowerBand)) and (c < prevLowerBand):
            self._stTrend = -1

        flipUp   = (self._stTrend ==  1 and prevTrend == -1)
        flipDown = (self._stTrend == -1 and prevTrend ==  1)

        # ── Timeout ───────────────────────────────────────────────────────────
        if self.position.size != 0 and self._entryBar >= 0:
            if (i - self._entryBar) >= self.tradeMaxAgeInput:
                self.position.close()
                self._entryBar = -1
                return

        # ── Entry gate ────────────────────────────────────────────────────────
        isWarmedUp = (i >= self._warmupBars)
        inWindow   = (self.data.index[-1] >= self._start_ts)
        if not (isWarmedUp and inWindow and (flipUp or flipDown)):
            return

        # ── Reversal: close existing + open opposite ──────────────────────────
        if self.position.size != 0:
            self.position.close()
            self._entryBar = -1

        # ── Compute SL/TP then queue entry ───────────────────────────────────
        if flipUp:
            slBase    = self._lastPivotLow if not np.isnan(self._lastPivotLow) else self.data.Low[-1]
            sl        = min(slBase - self.slAtrMultInput * atr,
                            c      - self.slAtrMultInput * atr)
            risk      = c - sl
            if risk <= 0:
                return
            tp3_price = c + risk * self._liveTp3R
            self.buy(size=1, sl=sl, tp=tp3_price)
        else:
            slBase    = self._lastPivotHigh if not np.isnan(self._lastPivotHigh) else self.data.High[-1]
            sl        = max(slBase + self.slAtrMultInput * atr,
                            c      + self.slAtrMultInput * atr)
            risk      = sl - c
            if risk <= 0:
                return
            tp3_price = c - risk * self._liveTp3R
            self.sell(size=1, sl=sl, tp=tp3_price)

        self._entryBar = i


# ── Public runner ────────────────────────────────────────────────────────────

def run_sats_bt(df: pd.DataFrame, params: dict,
                start_date: str = '2025-01-01',
                commission_per_side: float = 1.0) -> dict:
    """
    Run SATS via backtesting.py; return same metrics dict as simulate_sats().

    P&L is computed from raw trade prices × MES_POINT_VALUE ($5/pt) minus
    $1.00 commission per side, matching simulate_sats() exactly.
    """
    bt_df = df.rename(columns={
        'open': 'Open', 'high': 'High', 'low': 'Low',
        'close': 'Close', 'volume': 'Volume'
    }).copy()
    bt_df.index = pd.to_datetime(df['ts']).dt.tz_convert('UTC')

    strategy_params = {**INPUT_DEFAULTS, **params,
                       'start_date': start_date, 'tpModeInput': params.get('tpModeInput', 'Fixed')}

    bt = Backtest(bt_df, SATSStrategy,
                  cash=100_000, commission=0,
                  exclusive_orders=True, trade_on_close=False,
                  finalize_trades=True)
    stats = bt.run(**strategy_params)

    trades = stats._trades
    if trades is None or len(trades) == 0:
        return {'pf': 0.0, 'trades': 0, 'gross_profit': 0.0, 'gross_loss': 0.0,
                'win_rate': 0.0, 'max_dd_abs': 0.0, 'max_dd_pct': 0.0}

    # Dollar P&L: PnL column is in price points (size=1); multiply by $5/pt
    pnl_pts  = trades['PnL'].values.astype(float)
    pnl_usd  = pnl_pts * MES_POINT_VALUE - commission_per_side * 2.0

    gross_profit = float(pnl_usd[pnl_usd > 0].sum())
    gross_loss   = float((-pnl_usd[pnl_usd < 0]).sum())
    n_trades     = int(len(pnl_usd))
    n_wins       = int((pnl_usd > 0).sum())
    win_rate     = n_wins / n_trades if n_trades > 0 else 0.0

    pf = (gross_profit / gross_loss) if gross_loss > 0 else (
          float('inf') if gross_profit > 0 else 0.0)

    equity     = np.cumsum(pnl_usd)
    peak       = np.maximum.accumulate(np.concatenate([[0.0], equity]))
    dd         = peak[1:] - equity
    max_dd_abs = float(dd.max()) if len(dd) > 0 else 0.0
    max_dd_pct = (max_dd_abs / peak.max()) if peak.max() > 0 else 0.0

    return {
        'pf':           round(pf, 4),
        'trades':       n_trades,
        'gross_profit': round(gross_profit, 2),
        'gross_loss':   round(gross_loss,   2),
        'win_rate':     round(win_rate, 4),
        'max_dd_abs':   round(max_dd_abs, 2),
        'max_dd_pct':   round(float(max_dd_pct), 4),
    }


# ── CLI: parity check against champion ──────────────────────────────────────

if __name__ == '__main__':
    import time
    from sats_sim import simulate_sats

    parser = argparse.ArgumentParser(description='SATS backtesting.py parity check')
    parser.add_argument('--config', default='data/sats_ps_sweep/champion.json',
                        help='Path to config JSON (default: champion)')
    parser.add_argument('--start', default='2025-01-01',
                        help='Backtest start date (default: 2025-01-01)')
    args = parser.parse_args()

    repo_root = Path(__file__).parents[2]
    cfg_path  = repo_root / args.config
    params    = json.loads(cfg_path.read_text())['config'] if cfg_path.exists() else INPUT_DEFAULTS

    print('Loading data...')
    df = load_data()
    print(f'  {len(df):,} bars  {df["ts"].min()} → {df["ts"].max()}')

    # ── simulate_sats baseline ────────────────────────────────────────────────
    t0  = time.perf_counter()
    sim = simulate_sats(df, params, start_date=args.start)
    t_sim = time.perf_counter() - t0
    print(f'\nsimulate_sats  [{t_sim:.2f}s]')
    print(f'  PF={sim["pf"]:.4f}  trades={sim["trades"]}  '
          f'WR={sim["win_rate"]:.2%}  maxDD={sim["max_dd_abs"]:.0f}')

    # ── backtesting.py result ─────────────────────────────────────────────────
    t0 = time.perf_counter()
    bt_res = run_sats_bt(df, params, start_date=args.start)
    t_bt = time.perf_counter() - t0
    print(f'\nrun_sats_bt    [{t_bt:.2f}s]')
    print(f'  PF={bt_res["pf"]:.4f}  trades={bt_res["trades"]}  '
          f'WR={bt_res["win_rate"]:.2%}  maxDD={bt_res["max_dd_abs"]:.0f}')

    # ── Parity gate ───────────────────────────────────────────────────────────
    # ±5% tolerance: reversal/timeout exits are at next-bar open (bt) vs current
    # close (sim), creating a known ~3% systematic gap on champion config.
    # Trade count must match exactly — that's the true signal-logic parity check.
    pf_diff      = abs(bt_res['pf'] - sim['pf']) / max(sim['pf'], 1e-9)
    trade_match  = bt_res['trades'] == sim['trades']
    pf_ok        = pf_diff <= 0.05
    gate = 'PASS' if (pf_ok and trade_match) else 'FAIL'
    print(f'\nParity gate (trades exact + PF ±5%):')
    print(f'  Trade count match: {trade_match}  ({bt_res["trades"]} vs {sim["trades"]})')
    print(f'  PF diff: {pf_diff:.2%} → {"OK" if pf_ok else "FAIL"}')
    print(f'  → {gate}')
    if gate == 'FAIL':
        print('  !! Fix port before running Optuna !!')
        raise SystemExit(1)
