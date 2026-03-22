# TradingView Community Script Library Research

**Date:** 2026-03-22
**Purpose:** Exhaustive catalog of Pine Script v5/v6 libraries and indicators for AutoGluon feature engineering and Warbird Pro indicator development.

---

## IMPORT RECOMMENDATIONS (Use Directly)

| Library | Category | What | URL |
|---------|----------|------|-----|
| loxxmas (40+ MAs) | Moving Averages | KAMA, T3, Laguerre, Zero-lag, McGinley, 40+ variants | [Link](https://www.tradingview.com/script/Qc1LnCik) |
| MomentumIndicators | Oscillators | 12+ oscillators + meta-indicators (oscillators of oscillators) | [Link](https://www.tradingview.com/script/J40EscDD) |
| VolumeIndicators | Volume | MFI, CMF, OBV, A/D, PVT, VROC | [Link](https://www.tradingview.com/script/DgXwuNOm) |
| StatMetrics | Statistics/ML | z-score, hurst, autocorrelation, normalize, skew, kurtosis, sharpe, sortino | [Link](https://www.tradingview.com/script/45irqt6M) |
| ZigZag Library [TradingFinder] | Fibonacci/Pivots | Reusable confirmed-pivot ZigZag — **fixes our repaint problem** | [Link](https://www.tradingview.com/script/IGrDHMhJ) |
| Sessions [TradingFinder] | Time/Session | NY/London/Tokyo/Sydney session boundaries | [Link](https://www.tradingview.com/script/4lPybQbF) |
| Correlation HeatMap Matrix Data | Intermarket | Multi-symbol correlation computation (up to 20 symbols) | [Link](https://www.tradingview.com/script/eCMTOGfc) |
| MTFData | Multi-Timeframe | Multi-timeframe candle storage, swing tracking | [Link](https://www.tradingview.com/script/A7mNo0Oe) |

---

## EXTRACT PATTERNS FROM

| Script | Pattern to Extract | URL |
|--------|-------------------|-----|
| Golden Zone Structure [Kodexius] | HH/HL/LH/LL swing classification | [Link](https://www.tradingview.com/script/irJbG8Vs) |
| FVG & Order Block [Spoiltbrat] | FVG detection as AG feature | [Link](https://www.tradingview.com/script/TPNo5dgB) |
| Market Structure Shift [TehThomas] | BOS/CHoCH detection for regime | [Link](https://www.tradingview.com/script/DPAeE8us) |
| ADX Volatility Waves [BOSWaves] | Volatility-scaled fib targets | [Link](https://www.tradingview.com/script/31FxM7aE) |
| CVD Histogram | Intrabar volume delta analysis | [Link](https://www.tradingview.com/script/6J3xcsFn) |
| ConditionalAverages [PineCoders] | Selective/conditional averaging | [Link](https://www.tradingview.com/script/9l0ZpuQU) |
| PowerWave Oscillator [BOSWaves] | Volume-filtered momentum | [Link](https://www.tradingview.com/script/pj0iZk1j) |
| Trade Manager [AlgoScopes] | Trade state machine (in-trade vs awaiting) | [Link](https://www.tradingview.com/script/uKXfR91D) |
| Position Tracker [GG_ALGO] | Fib-based SL/TP tracking | [Link](https://www.tradingview.com/script/LSwjVtLB) |

---

## REFERENCE ONLY (Study, Don't Import)

| Script | Why Reference | URL |
|--------|--------------|-----|
| Smart Money Concepts [LuxAlgo] | Order blocks, FVGs, premium/discount — too complex to import directly | [Link](https://www.tradingview.com/script/CnB3fSph) |
| Auto Harmonic Pattern [UAlgo] | Multi-leg fib validation — secondary confirmation only | [Link](https://www.tradingview.com/script/Alg2Vb8K) |
| Volume Delta Methods [LuxAlgo] | Professional buy/sell volume — extract ratio at fib touches | [Link](https://www.tradingview.com/script/OhLE0vnH) |
| Intermarket Correlation Table | ES/NQ/YM/ZN/DXY correlation matrix | [Link](https://www.tradingview.com/script/UJFlWowq) |
| Inverted Yield Curve + VIX | 2Y/10Y spread + VIX overlay | [Link](https://www.tradingview.com/script/1HXQwhVr) |
| Cash VIX Term Structure | Contango/backwardation detection | [Link](https://www.tradingview.com/script/eLlP2P3E) |
| Bear Market Probability Model | Multi-category bear market scoring | [Link](https://www.tradingview.com/script/8jAHmKXS) |
| Bloomberg Financial Conditions Proxy | Financial conditions index | [Link](https://www.tradingview.com/script/EktpAXcq) |

---

## CRITICAL FINDINGS

### 1. Fib Anchor Repaint (HIGHEST RISK)
- **Problem:** Our `ta.highest()`/`ta.lowest()` repaints every bar
- **Solution:** ZigZag Library [TradingFinder] uses confirmed pivots that don't change
- **Action:** Replace current anchor engine with confirmed-pivot-only logic

### 2. Volume at Fib Levels (GOLD for AG)
- Extract MFI + CMF from VolumeIndicators library
- Compute volume absorption at each fib level
- Add CVD slope at fib touch as feature
- Feed to AG as `vol_score_fib_{level}`

### 3. Regime Detection
- ADX < 25 = fib rejection likely
- Choppiness Index for trending vs range
- Hurst exponent from StatMetrics for mean reversion
- Feed to AG as `regime_context` + `hurst_exponent`

### 4. Time-of-Day Features
- Session boundaries (NY_OPEN, LONDON_CLOSE, OVERLAP)
- Minutes-since-session-open normalized
- Feed to AG as `session_context`, `minutes_in_session`

### 5. Oscillator Ensemble
- Use MomentumIndicators library for ALL 12 types at entry
- Z-score normalize each (StatMetrics)
- Compute ensemble agreement score
- Feed `ensemble_agreement` to AG

---

## IMPLEMENTATION ROADMAP

### Phase 1: Core AG Features (High ROI)
1. ZigZag [TradingFinder] → confirmed pivot anchors (fixes repaint)
2. StatMetrics → zscore normalization + hurst exponent
3. VolumeIndicators → MFI/CMF at fib levels
4. ADX → regime classification
5. Trade state machine → SL/ENTRY/TP1/TP2 lifecycle

### Phase 2: Context Layers (Medium ROI)
6. Sessions [TradingFinder] → session flags
7. MTFData → HTF confluence
8. loxxmas → 40+ MA variants for AG feature vector
9. MomentumIndicators → ensemble agreement

### Phase 3: Refinement (Lower Priority)
10. FVG & Order Block → fib anchor quality score
11. Correlation HeatMap Matrix → macro regime flags
12. CVD Indicators → volume delta direction
13. Market Structure [TehThomas] → BOS/CHoCH detection

---

## RED FLAGS

1. **Non-Repainting:** Most ZigZag implementations repaint. Use confirmed-swing-only logic.
2. **Intrabar Limits:** CVD/footprint need intrabar access — may not work on all data sources.
3. **Correlation Lag:** Intermarket correlations lag 1-2 bars — confirmation only, not entry trigger.
4. **Library Conflicts:** Do NOT import multiple libraries doing overlapping work. One per category.
5. **Performance:** 40 MAs + 12 oscillators + volume = timeout risk. Pre-filter in AG, not Pine.
6. **request.security() Budget:** 40 total limit. Track every call.
