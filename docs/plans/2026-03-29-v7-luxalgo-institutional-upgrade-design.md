# Warbird v7 — LuxAlgo-Informed Institutional Upgrade Design

**Date:** 2026-03-29
**Status:** IMPLEMENTED — features built + intermarket basket fully replaced (flow-based leading indicators), regime gate simplified, TV-validated 58/64 budget
**Base:** Copy of `indicators/v6-warbird-complete.pine` → `indicators/v7-warbird-institutional.pine`
**Governing plan:** `docs/plans/2026-03-20-ag-teaches-pine-architecture.md`

---

## Motivation

The LuxAlgo team reviewed WB v6 and identified concrete weaknesses that make the indicator untrustworthy for AG training:

1. No volume confirmation on entry — fires on drift, not institutional defense
2. No Opening Range awareness — blind to session structure failures
3. No liquidity grab / sweep detection — enters before stop hunts, not after
4. No market structure break (CHoCH/BOS) — no post-trade reversal detection
5. No FVG detection — misses displacement confirmation
6. BANK as required anchor in tech-led rallies — kills valid MES longs when semis lead
7. VIX instead of VVIX — coincident signal, not leading
8. No post-trade reset — sits in TRADE_NONE waiting for new pivot, misses reversal windows
9. Fixed -0.236 SL with no volatility adjustment — stop-hunted in high-VIX environments
10. No exhaustion scoring — can't detect overbought/oversold at fib extensions

WB v7 addresses all 10 by implementing **standard ICT/Smart Money Concepts methodology** — the same institutional trading patterns LuxAlgo packages in their proprietary scripts, built from published open-source reference implementations. No hand-rolled interpretations.

**Critical finding:** LuxAlgo's scripts (PAC, Smart Trail, Oscillator Matrix) are **proprietary/closed-source**. We cannot port their exact code wholesale. However, Kirk provided the actual Oscillator Matrix 6.0 and Signals & Overlays 6.3 source files — the **HyperWave formula** and **Money Flow formula** are directly extracted from that source and used in the exhaustion scoring. For ICT/SMC structure features (CHoCH/BOS, FVG, liquidity sweeps), the niquedegraaff SMC gist (CC BY-NC-SA 4.0) provides verified reference patterns that align with the same methodology LuxAlgo packages.

**Verified source formulas (from Oscillator Matrix 6.0):**
- HyperWave: `ta.ema(ta.linreg((close - math.avg(hi, lo, av)) / (hi - lo) * 100, 7, 0), 3)`
- Money Flow: `ta.sma(ta.mfi(hl2, 35) - 50, 6)`
- Reversal detection: `volume > ta.sma(volume, 7) * 1.4` + oscillator/MFI confluence

---

## Architecture Decisions

### 1. New File, Not a Modification

`v7-warbird-institutional.pine` is a separate indicator file. WB v6 remains untouched as the stable baseline.

### 2. TA Core Pack Offloaded to Server-Side

The 15 TA Core Pack `plot()` exports are removed. The computation code stays (Pine needs the variables for AG packet-driven gates). AG computes identical TA metrics server-side from Databento OHLCV.

**Parity requirement:** A one-time parity test must verify Pine and server-side TA computations match within 0.01% relative error before AG training begins. This is an AG workbench step, not a blocker for v7 Pine work.

### 3. ICT/SMC Methodology From Published References, Not Hand-Rolled

LuxAlgo's scripts are proprietary. Every new feature must trace to a **published open-source reference implementation** of the same ICT/SMC concept. Rule #8 applies: copy the reference logic, adapt the interface only.

| Feature | ICT/SMC Concept | Reference Source | Detection Pattern |
|---|---|---|---|
| Liquidity sweeps | Swing sweep + close back inside | Standard fractal sweep (pivothigh/pivotlow) | `low < prevSwingLow AND close > prevSwingLow` |
| CHoCH / BOS | Market structure break | ta.pivothigh / ta.pivotlow comparison | Break of tracked swing level against/with trend |
| FVG detection | Fair Value Gap (3-bar imbalance) | Universal definition | `low > high[2]` (bullish), `high < low[2]` (bearish) |
| Exhaustion scoring | Overbought/oversold at extremes | RSI(14) + signal line crossover at 80/20 | Crossover at extreme + fib extension proximity |
| Adaptive trailing stop | Chandelier Stop / ATR trail | Standard ATR trailing stop | `math.min(fibSL, entry - ATR * multiplier)` |
| Volume confirmation | Relative Volume (RVOL) | Standard RVOL definition | `volume > ta.sma(volume, 20)` |

### 4. Entire Intermarket Basket Replaced (IMPLEMENTED)

The original basket (NQ, BANK, VIX, DXY, US10Y, SMH) was mostly coincident price correlations. Replaced with 7 flow-based LEADING indicators: TICK, VOLD, VVIX, VIX/VIX3M term structure, HYG, RTY, SKEW. Plus NYSE A/D (`USI:ADD`) for daily breadth. See "Intermarket Basket Change" section below for full details.

### 5. Regime Gate Simplified (IMPLEMENTED)

Removed the Decision Model dropdown and weighted scoring system. Single model: all 7 symbols must agree for regime confirmation. Hysteresis prevents whipsaw: 3 bars to flip, 4 bars cooldown, 16 bars (4h) neutralize stale regime. AG will discover optimal correlations and thresholds via SHAP.

---

## Plot Budget

| Category | v6 (baseline) | v7 (current) |
|---|---|---|
| Fib engine / structure exports | 20 | 20 |
| Intermarket / regime exports | 10 | 8 (7 symbol states + VTS ratio) |
| Volume delta / CLV exports | 4 | 4 |
| TA Core Pack exports | 15 | **0** (server-side) |
| Model contract exports (ml_*) | 11 | 11 |
| **New institutional features** | **0** | **12** |
| **Total plots** | **60** | **55** |
| Alertconditions | 3 | 3 |
| **Budget used** | **63/64** | **58/64** |
| **Headroom** | **1 slot** | **6 slots** |

## Security Call Budget

| Category | v6 | v7 |
|---|---|---|
| Intermarket 60min (TICK, VOLD, VVIX, VIX, VIX3M, HYG, RTY) | 5 | **6** (flow-based basket) |
| Intermarket daily (SKEW, ADD) | 2 | **2** (daily regime + breadth) |
| VIX daily (close + percentrank) | 2 | **0** (dropped — VIX now in 60min basket via term structure) |
| HTF fib (1H, 4H, 1D) | 3 | 3 |
| **Total** | **10/40** | **~12/40** |

---

## New Feature Surface (14 exports)

All new features are Pine-only exports — things that depend on Pine's internal state (fib engine, session context, multi-bar structural patterns) and cannot be computed from raw OHLCV alone.

| # | Feature | Plot Name | Source | Description |
|---|---------|-----------|--------|-------------|
| 1 | RVOL at entry | `ml_rvol_at_entry` | Smart Trail Overflow | volume / SMA(volume, 20) at acceptEvent bars |
| 2 | Opening Range state | `ml_or_state` | Session structure | 1.0 = above OR high, -1.0 = below OR low, 0.0 = inside |
| 3 | OR distance | `ml_or_dist_pct` | Session structure | % distance from close to nearest OR boundary |
| 4 | Liquidity sweep bull | `ml_liq_sweep_bull` | LuxAlgo PAC | 1.0 when price sweeps N-bar low and closes back above |
| 5 | Liquidity sweep bear | `ml_liq_sweep_bear` | LuxAlgo PAC | 1.0 when price sweeps N-bar high and closes back below |
| 6 | CHoCH code | `ml_choch_code` | LuxAlgo PAC | 1 = bullish CHoCH, -1 = bearish CHoCH, 0 = none |
| 7 | FVG bull distance | `ml_fvg_bull_dist` | LuxAlgo PAC | Distance to nearest unmitigated bullish FVG (pts) |
| 8 | FVG bear distance | `ml_fvg_bear_dist` | LuxAlgo PAC | Distance to nearest unmitigated bearish FVG (pts) |
| 9 | Intermarket alignment count | `ml_align_on` / `ml_align_off` | Regime gate | Count of 7 symbols in risk-on / risk-off (0-7) |
| 10 | VTS ratio | `ml_vts_ratio` | VIX term structure | VIX/VIX3M: < 0.92 calm, > 1.0 stress |
| 11 | Post-trade cooldown | `ml_cooldown_bars` | LuxAlgo reset logic | Bars remaining in post-SL/TP cooldown (0 = ready) |
| 12 | Bars since exit | `ml_bars_since_exit` | Trade reset context | Bars since last SL or TP event |
| 13 | Vol-adjusted SL dist | `ml_vol_adj_sl_dist` | Smart Trail Switch | Distance from entry to volatility-adjusted SL (pts) |
| 14 | Exhaustion score | `ml_exhaustion_score` | LuxAlgo Oscillator Matrix (exact HyperWave + Money Flow formulas) | 0-100 score: HyperWave(40) + MoneFlow(30) + FibProximity(30) |

---

## Entry Trigger Upgrade

Current v6 trigger (no volume filter):
```
entryLongTrigger = acceptEvent AND dir==1 AND targetEligible20pt AND NOT conflictBreak AND NOT breakAgainstConfirmed
```

v7 trigger (with LuxAlgo-informed gates):
```
bool volConfirm = volume > ta.sma(volume, 20)
entryLongTrigger = acceptEvent AND dir==1 AND targetEligible20pt AND NOT conflictBreak AND NOT breakAgainstConfirmed AND volConfirm
```

AG will later replace these hand-coded gates with packet-driven thresholds. The volume gate is the minimum institutional filter until AG takes over.

---

## Intermarket Basket Change (IMPLEMENTED)

The entire intermarket basket was replaced with flow-based LEADING indicators. The old basket (NQ, BANK, DXY, US10Y, SMH) was mostly coincident price correlations with MES — essentially redundant. The new basket measures institutional order flow, volatility expectations, credit stress, and breadth — signals that LEAD MES moves.

| Symbol | TradingView ID | v7 Role | Detection Method |
|---|---|---|---|
| TICK | `USI:TICK` | NYSE uptick/downtick — institutional program trading | Zero threshold (> 0 bull, < 0 bear) |
| VOLD | `USI:VOLD` | NYSE up vol − down vol — money flow | Zero threshold (> 0 bull, < 0 bear) |
| VVIX | `CBOE:VVIX` | Vol of vol — leads VIX by 1-3 bars | Level threshold (< 17 risk-on, > 25 risk-off) |
| VIX | `CBOE:VIX` | 30-day implied vol — used for term structure | Part of VTS ratio |
| VIX3M | `CBOE:VIX3M` | 3-month implied vol — VTS denominator | Part of VTS ratio |
| HYG | `AMEX:HYG` | High-yield credit — credit desks sell before equity desks | EMA trend (price > EMA = bull) |
| RTY | `CME_MINI:RTY1!` | Russell 2000 small-cap — breaks down/recovers first | EMA trend (price > EMA = bull) |
| SKEW | `CBOE:SKEW` | Tail-risk hedging — institutions hedge before selling (daily) | Level threshold (< 140 risk-on, > 155 risk-off) |
| NYSE A/D | `USI:ADD` | Advance-Decline breadth (daily) | Exported as feature, divergence = exhaustion |

**VIX Term Structure (VTS):** `VIX / VIX3M` ratio. < 0.92 = contango (calm, risk-on). > 1.0 = backwardation (stress, risk-off). Backwardation is ALWAYS a warning regardless of regime.

**Regime model:** All 7 must agree for regime confirmation. No weighted scoring, no decision model options. AG decides correlations and optimal thresholds from data. Hysteresis: 3 bars to flip, 4 bars cooldown, 16 bars (4h) neutralize stale regime.

**Replaced (do NOT use):** NQ (0.95+ correlation, redundant), BANK (coincident/lagging), DXY (daily/weekly, not 15m leading), US10Y/ZN (regime-dependent, unreliable gate), SMH (partially redundant with NQ).

---

## Post-Trade Reset Logic

Current v6: After SL or TP2, engine sits in `TRADE_NONE` until new ZigZag pivot.

v7: After SL or TP2:
1. Enter cooldown (default 5 bars)
2. After cooldown expires, allow reversal-zone touches and liquidity grabs to trigger re-evaluation
3. CHoCH detection can flip regime to neutral/opposite immediately after TP2
4. `ml_cooldown_bars` and `ml_bars_since_exit` exported for AG to learn optimal reset timing

---

## Volatility-Adjusted Stop Loss

Current v6: Fixed `fibPrice(-0.236)`.

v7 hybrid (from Smart Trail Switch logic):
```
float volAdjSL = math.min(fibPrice(-0.236), entryLevel - ta.atr(14) * 1.5 * fibDir)
```

Takes the tighter of:
- Fib invalidation (-0.236 extension)
- ATR-based volatility stop (1.5x ATR from entry)

Ensures stop is outside the "noise range" in high-VIX environments while still respecting fib structure. AG packet can later override the 1.5 multiplier.

---

## Research Requirements

Before writing any feature code, the implementation must:

1. Fetch and read **published open-source reference implementations** for each ICT/SMC concept
2. Extract the exact detection logic, lookback periods, and conditions from the reference
3. Document which reference source maps to which lines of v7 code
4. Run `pine-lint.sh`, `check-contamination.sh`, and `npm run build` after every feature addition
5. Do NOT attempt to reverse-engineer LuxAlgo proprietary code — use the standard ICT methodology

---

## What v7 Does NOT Change

- Fib engine (ZigZag, anchor logic, confluence) — unchanged, hardening is a separate task
- HTF confluence check — unchanged
- Fib level definitions and colors — unchanged (visual spec is a contract)
- 3 alertconditions — unchanged
- `barstate.isconfirmed` gating — non-negotiable
- Model spec contract — v7 is additive features, not a contract change
- TA Core Pack computation code — stays internal, only `plot()` exports removed

---

## Success Criteria

1. `pine-lint.sh` passes with 0 errors
2. `check-contamination.sh` passes
3. `npm run build` passes
4. TradingView paste-and-load validates — all new exports visible in Style tab
5. Plot budget <= 64
6. Security call budget <= 40
7. Every new feature traces to a published open-source reference implementation
8. No hand-rolled detection logic — standard ICT/SMC methodology only
