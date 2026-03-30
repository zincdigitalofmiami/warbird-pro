# Warbird v7 Institutional Upgrade — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Create `indicators/v7-warbird-institutional.pine` with 14 new institutional-grade features (ICT/SMC methodology), VVIX/SMH intermarket upgrades, and TA Core Pack plot offload — giving AG a high-quality training feature surface.

**Architecture:** Copy v6 as base. Remove 15 TA Core Pack plot exports (keep computation code). Add 14 new institutional features as `ml_*` hidden plot exports. Swap VIX→VVIX, add SMH, add volume/structure/session features. All new detection logic from published ICT/SMC reference implementations.

**Tech Stack:** Pine Script v6, TradingView ZigZag/7 library, standard `ta.*` built-ins.

**Design doc:** `docs/plans/2026-03-29-v7-luxalgo-institutional-upgrade-design.md`

**Verification after every task:** `./scripts/guards/pine-lint.sh` + `./scripts/guards/check-contamination.sh` + `npm run build`

**Reference implementations (verified sources):**
- Liquidity sweeps: Standard fractal sweep — `low < ta.lowest(low, N)[1] AND close > ta.lowest(low, N)[1]`
- CHoCH/BOS: `ta.pivothigh()` / `ta.pivotlow()` swing tracking with break detection (ref: niquedegraaff SMC gist — dual-level internal 5-bar + configurable swing, BOS vs CHoCH discrimination via trend state)
- FVG: Universal 3-bar gap — `low > high[2]` (bullish), `high < low[2]` (bearish) (ref: SMC gist — includes auto-threshold and mitigation tracking)
- Exhaustion: HyperWave oscillator from LuxAlgo Oscillator Matrix source (Kirk-provided) — `ta.ema(ta.linreg((close - math.avg(hi, lo, av)) / (hi - lo) * 100, 7, 0), 3)` + Money Flow `ta.sma(ta.mfi(hl2, 35) - 50, 6)`
- Vol-adjusted SL: Chandelier stop pattern — `math.min(fibSL, entry - ATR * multiplier)`
- RVOL: `volume > ta.sma(volume, 20)`
- Order Blocks / EQH/EQL: Available in SMC gist for future consideration (not in current v7 scope, would need plot budget)

---

### Task 1: Create v7 File (Copy v6 Base)

**Files:**
- Create: `indicators/v7-warbird-institutional.pine` (copy of `indicators/v6-warbird-complete.pine`)

**Step 1: Copy v6 to v7**

```bash
cp "/Volumes/Satechi Hub/warbird-pro/indicators/v6-warbird-complete.pine" "/Volumes/Satechi Hub/warbird-pro/indicators/v7-warbird-institutional.pine"
```

**Step 2: Update header and indicator name**

Change line 3 and line 23:
```pine
// Warbird v7 Institutional — LuxAlgo-Informed ICT/SMC Upgrade
// Base: v6-warbird-complete.pine (2026-03-26)
// Upgrade: ICT/SMC institutional features, VVIX/SMH intermarket, TA Core Pack offloaded
// Date: 2026-03-29
```
```pine
indicator("Warbird v7 Institutional", shorttitle="WB v7", overlay=true, max_lines_count=200, max_labels_count=200, max_boxes_count=100)
```

**Step 3: Run verification**

```bash
./scripts/guards/pine-lint.sh
./scripts/guards/check-contamination.sh
npm run build
```
Expected: All pass (identical to v6 except name).

**Step 4: Commit**

```bash
git add indicators/v7-warbird-institutional.pine
git commit -m "feat: create v7 indicator file from v6 base"
```

---

### Task 2: Remove TA Core Pack Plot Exports (Free 15 Slots)

**Files:**
- Modify: `indicators/v7-warbird-institutional.pine` (lines 847-862)

**Step 1: Delete the 15 TA Core Pack plot lines**

Remove these exact lines (keep ALL computation code above them — `ema100`, `macdHist`, `rsi14`, `atr14`, `volSma20`, `volRatio`, `volAccel`, `barSpreadXVol`, `obvVal`, `mfi14` variables STAY):

```pine
// DELETE these 15 lines:
plot(ema21,         "ml_ema_21",            display=display.none)
plot(ema50,         "ml_ema_50",            display=display.none)
plot(ema100,        "ml_ema_100",           display=display.none)
plot(ema200,        "ml_ema_200",           display=display.none)
plot(macdHist,      "ml_macd_hist",         display=display.none)
plot(rsi14,         "ml_rsi_14",            display=display.none)
plot(atr14,         "ml_atr_14",            display=display.none)
plot(adxVal,        "ml_adx_14",            display=display.none)
plot(volume,        "ml_volume_raw",        display=display.none)
plot(volSma20,      "ml_vol_sma_20",        display=display.none)
plot(volRatio,      "ml_vol_ratio",         display=display.none)
plot(volAccel,      "ml_vol_acceleration",  display=display.none)
plot(barSpreadXVol, "ml_bar_spread_x_vol",  display=display.none)
plot(obvVal,        "ml_obv",               display=display.none)
plot(mfi14,         "ml_mfi_14",            display=display.none)
```

Also remove the section comment `// ── TA Core Pack Exports ──` and replace with:
```pine
// ── TA Core Pack: computation stays (used by AG packet gates), plot exports
// ── offloaded to server-side (AG computes from Databento OHLCV) ──
```

**Step 2: Run verification**

```bash
./scripts/guards/pine-lint.sh
```
Expected: Plot count drops from 60 to 45. 48/64 budget (45 plot + 3 alert).

**Step 3: Commit**

```bash
git add indicators/v7-warbird-institutional.pine
git commit -m "feat(v7): offload TA Core Pack plots to server-side — frees 15 slots"
```

---

### Task 3: Swap VIX → VVIX and Drop Daily VIX Calls

**Files:**
- Modify: `indicators/v7-warbird-institutional.pine`

**Step 1: Change VIX symbol default to VVIX**

Find and replace in the intermarket inputs section:
```pine
// BEFORE:
string symVIX  = input.symbol("CBOE:VIX", "VIX (volatility)", group=groupIM)
float vixMaxRiskOn  = input.float(20.40, "VIX Max (risk-on filter)", step=0.1, group=groupIM)

// AFTER:
string symVVIX = input.symbol("CBOE:VVIX", "VVIX (vol of vol — leading)", group=groupIM)
float vvixMaxRiskOn = input.float(90.0, "VVIX Max (risk-on filter)", step=1.0, group=groupIM, tooltip="VVIX typically 60-150+. Below 90 = complacent/risk-on. Above 120 = fear/risk-off.")
```

**Step 2: Remove the 2 daily VIX request.security() calls**

Delete these lines (around line 144-145):
```pine
// DELETE:
float vixDaily = request.security("CBOE:VIX", "D", close, gaps=barmerge.gaps_off, lookahead=barmerge.lookahead_off)
float vixPctRank = request.security("CBOE:VIX", "D", ta.percentrank(close, 252), gaps=barmerge.gaps_off, lookahead=barmerge.lookahead_off)
```

**Step 3: Update intermarket series to use VVIX**

```pine
// BEFORE:
float vx = imClose(symVIX)
// ...
bool vxRiskOn = vxDown and vx < vixMaxRiskOn

// AFTER:
float vvx = imClose(symVVIX)
float vvxMA = ta.ema(vvx, maLen)
[vvxUp, vvxDown] = trendFlags(vvx, vvxMA, slopeBars, neutralBandPct)
// VVIX is inverse: declining VVIX = complacency = risk-on
bool vvxRiskOn = vvxDown and vvx < vvixMaxRiskOn
bool vvxRiskOff = vvxUp
```

Update all downstream references: `vx` → `vvx`, `vxRiskOn` → `vvxRiskOn`, `vxRiskOff` → `vvxRiskOff`, `wVIX` → `wVVIX` (input label update too).

**Step 4: Remove vix_close plot export**

Delete: `plot(vixDaily, "vix_close", display=display.none)`

**Step 5: Update ml_event_vix_state export**

Rename to reflect VVIX:
```pine
plot(float(eventVixState), "ml_event_vvix_state", display=display.none)
```

**Step 6: Update request.security() budget comment**

```pine
// REQUEST.SECURITY() BUDGET:
// Intermarket (60min): NQ, BANK, VVIX, DXY, 10Y        = 5 calls
// SMH (60min):         close                             = 1 call  (Task 4)
// HTF fib (1H):        [high, low] tuple                 = 1 call
// HTF fib (4H):        [high, low] tuple                 = 1 call
// HTF fib (1D):        [high, low] tuple                 = 1 call
// TOTAL:                                                 = 9 of 40 (22%)
```

**Step 7: Run verification**

```bash
./scripts/guards/pine-lint.sh
```
Expected: Security call count drops from 10 to 8 (SMH not added yet). Plot count drops by 1 (vix_close removed).

**Step 8: Commit**

```bash
git add indicators/v7-warbird-institutional.pine
git commit -m "feat(v7): swap VIX→VVIX, drop daily VIX calls — leading signal, -2 security calls"
```

---

### Task 4: Add SMH Intermarket Symbol

**Files:**
- Modify: `indicators/v7-warbird-institutional.pine`

**Step 1: Add SMH input**

In the intermarket inputs section, after the `sym10Y` line:
```pine
string symSMH  = input.symbol("AMEX:SMH", "SMH (semiconductors — tech leader)", group=groupIM)
```

**Step 2: Add SMH weight input**

In the intermarket model section:
```pine
int wSMH  = input.int(2, "Weight: SMH", minval=0, maxval=10, group=groupIMModel)
```

**Step 3: Add SMH security call and trend flags**

After the `y10` series block:
```pine
float smh = imClose(symSMH)
float smhMA = ta.ema(smh, maLen)
[smhUp, smhDown] = trendFlags(smh, smhMA, slopeBars, neutralBandPct)
bool smhBull = smhUp
bool smhBear = smhDown
```

**Step 4: Wire SMH into scoring**

Update `totalWeight`:
```pine
int totalWeight = wNQ + wBANK + wVVIX + wDXY + activeW10Y + wSMH
```

Update `scoreOn` and `scoreOff`:
```pine
int scoreOn = (
    (nqBull ? wNQ : 0) +
    (bkBull ? wBANK : 0) +
    (vvxRiskOn ? wVVIX : 0) +
    (dxRiskOn ? wDXY : 0) +
    ((use10YConfirm and y10RiskOn) ? w10Y : 0) +
    (smhBull ? wSMH : 0)
)
int scoreOff = (
    (nqBear ? wNQ : 0) +
    (bkBear ? wBANK : 0) +
    (vvxRiskOff ? wVVIX : 0) +
    (dxRiskOff ? wDXY : 0) +
    ((use10YConfirm and y10RiskOff) ? w10Y : 0) +
    (smhBear ? wSMH : 0)
)
```

Note: `anchorsOn` / `anchorsOff` keep requiring NQ+BANK. SMH supplements via scoring, doesn't replace BANK as anchor.

**Step 5: Add SMH state export**

```pine
int smhState = smhBull ? 1 : smhBear ? -1 : 0
plot(float(smhState), "ml_smh_state", display=display.none)
```

**Step 6: Run verification**

```bash
./scripts/guards/pine-lint.sh
```
Expected: Security calls = 9/40. Plots = 45 + 1 (SMH) = 46.

**Step 7: Commit**

```bash
git add indicators/v7-warbird-institutional.pine
git commit -m "feat(v7): add SMH intermarket — tech-led rally leader"
```

---

### Task 5: Add Intermarket Bitmask Encoding

**Files:**
- Modify: `indicators/v7-warbird-institutional.pine`

**Step 1: Add bitmask computation after regime detection**

```pine
//=====================
// INTERMARKET BITMASK (single-slot regime state matrix for AG)
//=====================
int regimeBitmask = 0
regimeBitmask += (nqBull ? 1 : 0)
regimeBitmask += (bkBull ? 2 : 0)
regimeBitmask += (vvxRiskOn ? 4 : 0)
regimeBitmask += (dxRiskOn ? 8 : 0)
regimeBitmask += (y10RiskOn ? 16 : 0)
regimeBitmask += (smhBull ? 32 : 0)
```

**Step 2: Add export**

```pine
plot(float(regimeBitmask), "ml_im_bitmask", display=display.none)
```

**Step 3: Run verification + commit**

```bash
./scripts/guards/pine-lint.sh && git add indicators/v7-warbird-institutional.pine && git commit -m "feat(v7): add intermarket bitmask — 6-symbol regime matrix in 1 plot slot"
```

---

### Task 6: Add RVOL Gate on Entry Trigger

**Files:**
- Modify: `indicators/v7-warbird-institutional.pine`

**Step 1: Add RVOL computation (uses existing volSma20)**

After the volume delta section:
```pine
//=====================
// RVOL CONFIRMATION (ICT: institutional volume > average = defense of level)
// Reference: standard Relative Volume definition
//=====================
float rvol = volSma20 > 0 ? volume / volSma20 : 0.0
bool volConfirm = rvol > 1.0
```

**Step 2: Wire into entry triggers**

```pine
// BEFORE:
bool entryLongTrigger = acceptEvent and dir == 1 and targetEligible20pt and not conflictBreak and not breakAgainstConfirmed
bool entryShortTrigger = acceptEvent and dir == -1 and targetEligible20pt and not conflictBreak and not breakAgainstConfirmed

// AFTER:
bool entryLongTrigger = acceptEvent and dir == 1 and targetEligible20pt and not conflictBreak and not breakAgainstConfirmed and volConfirm
bool entryShortTrigger = acceptEvent and dir == -1 and targetEligible20pt and not conflictBreak and not breakAgainstConfirmed and volConfirm
```

**Step 3: Add export**

```pine
plot(rvol, "ml_rvol_at_entry", display=display.none)
```

**Step 4: Run verification + commit**

```bash
./scripts/guards/pine-lint.sh && git add indicators/v7-warbird-institutional.pine && git commit -m "feat(v7): add RVOL gate on entry — filters drift from institutional defense"
```

---

### Task 7: Add Opening Range Detection

**Files:**
- Modify: `indicators/v7-warbird-institutional.pine`

**Step 1: Add Opening Range inputs**

```pine
string groupSession = "Session Structure"
int orStartHour = input.int(8, "OR Start Hour (exchange TZ)", minval=0, maxval=23, group=groupSession, tooltip="MES RTH opens 8:30 CT. First 15m bar = 8:30-8:45.")
int orStartMin  = input.int(30, "OR Start Minute", minval=0, maxval=59, group=groupSession)
```

**Step 2: Add Opening Range logic**

```pine
//=====================
// OPENING RANGE (first 15m bar of RTH session)
// Standard session-structure concept: fibs inside a bearish OR have higher STOPPED rate
//=====================
var float orHigh = na
var float orLow = na
bool isORBar = (hour == orStartHour and minute == orStartMin)
if isORBar
    orHigh := high
    orLow := low

float orState = na(orHigh) ? 0.0 : close > orHigh ? 1.0 : close < orLow ? -1.0 : 0.0
float orDistPct = na(orHigh) or na(orLow) or (orHigh == orLow) ? 0.0 :
    close > orHigh ? (close - orHigh) / (orHigh - orLow) * 100.0 :
    close < orLow ? (orLow - close) / (orHigh - orLow) * 100.0 : 0.0
```

**Step 3: Add exports (2 slots)**

```pine
plot(orState, "ml_or_state", display=display.none)
plot(orDistPct, "ml_or_dist_pct", display=display.none)
```

**Step 4: Run verification + commit**

```bash
./scripts/guards/pine-lint.sh && git add indicators/v7-warbird-institutional.pine && git commit -m "feat(v7): add Opening Range state — session structure filter"
```

---

### Task 8: Add Liquidity Sweep Detection

**Files:**
- Modify: `indicators/v7-warbird-institutional.pine`

**Step 1: Add sweep inputs**

```pine
string groupICT = "ICT / Smart Money Concepts"
int sweepLookback = input.int(24, "Liquidity Sweep Lookback (bars)", minval=5, maxval=100, group=groupICT, tooltip="Bars to look back for swing high/low. 24 = ~6 hours on 15m.")
```

**Step 2: Add liquidity sweep logic**

Standard ICT sweep detection: price exceeds a swing extreme and closes back inside.

```pine
//=====================
// LIQUIDITY SWEEPS (ICT: price sweeps swing high/low, closes back inside)
// Reference: Standard fractal sweep detection
// Bullish sweep = sweep of lows (stop hunt below) then close back above = bullish
// Bearish sweep = sweep of highs (stop hunt above) then close back below = bearish
//=====================
float swingLow = ta.lowest(low, sweepLookback)
float swingHigh = ta.highest(high, sweepLookback)
float prevSwingLow = ta.lowest(low, sweepLookback)[1]
float prevSwingHigh = ta.highest(high, sweepLookback)[1]

// Bullish sweep: wick below prior swing low, close back above it
bool liqSweepBull = barstate.isconfirmed and (low < prevSwingLow) and (close > prevSwingLow)
// Bearish sweep: wick above prior swing high, close back below it
bool liqSweepBear = barstate.isconfirmed and (high > prevSwingHigh) and (close < prevSwingHigh)
```

**Step 3: Add exports (2 slots)**

```pine
plot(liqSweepBull ? 1.0 : 0.0, "ml_liq_sweep_bull", display=display.none)
plot(liqSweepBear ? 1.0 : 0.0, "ml_liq_sweep_bear", display=display.none)
```

**Step 4: Run verification + commit**

```bash
./scripts/guards/pine-lint.sh && git add indicators/v7-warbird-institutional.pine && git commit -m "feat(v7): add liquidity sweep detection — ICT stop hunt filter"
```

---

### Task 9: Add CHoCH / Market Structure Break Detection

**Files:**
- Modify: `indicators/v7-warbird-institutional.pine`

**Step 1: Add CHoCH inputs**

```pine
int chochPivotLen = input.int(3, "CHoCH Pivot Length (bars each side)", minval=1, maxval=10, group=groupICT, tooltip="Fractal confirmation bars. 3 = standard for 15m.")
```

**Step 2: Add CHoCH detection logic**

Standard ICT CHoCH: track swing highs/lows, detect break against current trend.

```pine
//=====================
// CHoCH / BOS (ICT: Change of Character / Break of Structure)
// Reference: ta.pivothigh / ta.pivotlow swing tracking
// CHoCH = break of swing point AGAINST current trend (reversal signal)
// BOS = break of swing point WITH current trend (continuation)
//=====================
float swHigh = ta.pivothigh(high, chochPivotLen, chochPivotLen)
float swLow = ta.pivotlow(low, chochPivotLen, chochPivotLen)

var float lastSwHigh = na
var float lastSwLow = na
var float prevSwHigh2 = na
var float prevSwLow2 = na
var bool swingUptrend = true

if not na(swHigh)
    prevSwHigh2 := lastSwHigh
    lastSwHigh := swHigh
if not na(swLow)
    prevSwLow2 := lastSwLow
    lastSwLow := swLow

// Track trend via swing sequence
if not na(lastSwHigh) and not na(prevSwHigh2) and not na(lastSwLow) and not na(prevSwLow2)
    if lastSwHigh > prevSwHigh2 and lastSwLow > prevSwLow2
        swingUptrend := true
    else if lastSwHigh < prevSwHigh2 and lastSwLow < prevSwLow2
        swingUptrend := false

// CHoCH detection (confirmed bars only)
bool bearishChoch = barstate.isconfirmed and swingUptrend and not na(lastSwLow) and close < lastSwLow
bool bullishChoch = barstate.isconfirmed and not swingUptrend and not na(lastSwHigh) and close > lastSwHigh

int chochCode = bullishChoch ? 1 : bearishChoch ? -1 : 0
```

**Step 3: Add export (1 slot)**

```pine
plot(float(chochCode), "ml_choch_code", display=display.none)
```

**Step 4: Run verification + commit**

```bash
./scripts/guards/pine-lint.sh && git add indicators/v7-warbird-institutional.pine && git commit -m "feat(v7): add CHoCH market structure break — ICT reversal detection"
```

---

### Task 10: Add Fair Value Gap (FVG) Detection

**Files:**
- Modify: `indicators/v7-warbird-institutional.pine`

**Step 1: Add FVG tracking logic**

Standard ICT FVG: 3-bar imbalance where current bar low > 2-bars-ago high (bullish) or current bar high < 2-bars-ago low (bearish). Track nearest unmitigated gap.

```pine
//=====================
// FAIR VALUE GAPS (ICT: 3-bar imbalance zones)
// Reference: Universal FVG definition
// Bullish FVG: low > high[2] (gap up, buyers dominant)
// Bearish FVG: high < low[2] (gap down, sellers dominant)
// Track nearest unmitigated FVG distance for AG
//=====================
int fvgMaxTrack = 10  // max unmitigated FVGs to track

var array<float> bullFvgTops = array.new_float(0)
var array<float> bullFvgBots = array.new_float(0)
var array<float> bearFvgTops = array.new_float(0)
var array<float> bearFvgBots = array.new_float(0)

// Detect new FVGs
bool newBullFvg = barstate.isconfirmed and (low > high[2])
bool newBearFvg = barstate.isconfirmed and (high < low[2])

if newBullFvg
    array.push(bullFvgTops, low)
    array.push(bullFvgBots, high[2])
    if array.size(bullFvgTops) > fvgMaxTrack
        array.shift(bullFvgTops)
        array.shift(bullFvgBots)

if newBearFvg
    array.push(bearFvgTops, low[2])
    array.push(bearFvgBots, high)
    if array.size(bearFvgTops) > fvgMaxTrack
        array.shift(bearFvgTops)
        array.shift(bearFvgBots)

// Mitigate FVGs (close fills the gap)
if array.size(bullFvgTops) > 0
    for i = array.size(bullFvgTops) - 1 to 0
        if close < array.get(bullFvgBots, i)
            array.remove(bullFvgTops, i)
            array.remove(bullFvgBots, i)

if array.size(bearFvgTops) > 0
    for i = array.size(bearFvgTops) - 1 to 0
        if close > array.get(bearFvgTops, i)
            array.remove(bearFvgTops, i)
            array.remove(bearFvgBots, i)

// Nearest unmitigated FVG distance (points)
float nearestBullFvgDist = na
if array.size(bullFvgTops) > 0
    for i = array.size(bullFvgTops) - 1 to 0
        float mid = (array.get(bullFvgTops, i) + array.get(bullFvgBots, i)) / 2.0
        float d = close - mid
        if na(nearestBullFvgDist) or math.abs(d) < math.abs(nearestBullFvgDist)
            nearestBullFvgDist := d

float nearestBearFvgDist = na
if array.size(bearFvgTops) > 0
    for i = array.size(bearFvgTops) - 1 to 0
        float mid = (array.get(bearFvgTops, i) + array.get(bearFvgBots, i)) / 2.0
        float d = close - mid
        if na(nearestBearFvgDist) or math.abs(d) < math.abs(nearestBearFvgDist)
            nearestBearFvgDist := d
```

**Step 2: Add exports (2 slots)**

```pine
plot(nz(nearestBullFvgDist), "ml_fvg_bull_dist", display=display.none)
plot(nz(nearestBearFvgDist), "ml_fvg_bear_dist", display=display.none)
```

**Step 3: Run verification + commit**

```bash
./scripts/guards/pine-lint.sh && git add indicators/v7-warbird-institutional.pine && git commit -m "feat(v7): add FVG detection — ICT displacement confirmation"
```

---

### Task 11: Add Post-Trade Cooldown and Reset Logic

**Files:**
- Modify: `indicators/v7-warbird-institutional.pine`

**Step 1: Add cooldown state variables**

After the trade state machine variables:
```pine
var int cooldownCounter = 0
var int barsSinceExit = 0
var bool lastExitWasSL = false
```

**Step 2: Update trade state machine exit paths**

In the `barstate.isconfirmed` block, where `tradeState >= TRADE_HIT_TP1`:
```pine
    if tradeState == TRADE_STOPPED or tradeState == TRADE_HIT_TP2 or tradeState == TRADE_EXPIRED
        lastExitWasSL := (tradeState == TRADE_STOPPED)
        cooldownCounter := 5
        barsSinceExit := 0

    if tradeState >= TRADE_HIT_TP1
        tradeState := TRADE_NONE
        entryPrice := na
        slPrice := na
        tp1Price := na
        tp2Price := na
        setupBar := na
        entryBar := na

    // Cooldown tick
    if cooldownCounter > 0
        cooldownCounter -= 1
    barsSinceExit += 1
```

**Step 3: Add exports (2 slots)**

```pine
plot(float(cooldownCounter), "ml_cooldown_bars", display=display.none)
plot(float(math.min(barsSinceExit, 200)), "ml_bars_since_exit", display=display.none)
```

**Step 4: Run verification + commit**

```bash
./scripts/guards/pine-lint.sh && git add indicators/v7-warbird-institutional.pine && git commit -m "feat(v7): add post-trade cooldown — enables reversal re-entry windows"
```

---

### Task 12: Add Volatility-Adjusted Stop Loss

**Files:**
- Modify: `indicators/v7-warbird-institutional.pine`

**Step 1: Add vol-adjusted SL inputs**

```pine
string groupSL = "Stop Loss"
float slAtrMult = input.float(1.5, "Vol-Adjusted SL ATR Multiplier", minval=0.5, maxval=5.0, step=0.1, group=groupSL, tooltip="Chandelier stop: entry - ATR * multiplier. Takes tighter of fib SL and ATR SL.")
```

**Step 2: Compute vol-adjusted SL**

After the `slLevel` / `entryLevel` / `tp1Level` / `tp2Level` block:
```pine
// Volatility-adjusted SL (Chandelier stop pattern)
// Takes the WIDER of fib invalidation and ATR-based noise floor
// In bull: SL is below entry. Wider = lower price = math.min
// In bear: SL is above entry. Wider = higher price = math.max
float atrStop = fibBull ? (entryLevel - atr14 * slAtrMult) : (entryLevel + atr14 * slAtrMult)
float volAdjSL = fibBull ? math.min(slLevel, atrStop) : math.max(slLevel, atrStop)
float volAdjSlDist = not na(entryLevel) and not na(volAdjSL) ? math.abs(entryLevel - volAdjSL) : na
```

**Step 3: Wire vol-adjusted SL into trade state machine**

Replace `slPrice := slLevel` with:
```pine
slPrice := volAdjSL
```

**Step 4: Add export (1 slot)**

```pine
plot(nz(volAdjSlDist), "ml_vol_adj_sl_dist", display=display.none)
```

**Step 5: Run verification + commit**

```bash
./scripts/guards/pine-lint.sh && git add indicators/v7-warbird-institutional.pine && git commit -m "feat(v7): add volatility-adjusted SL — Chandelier stop hybrid"
```

---

### Task 13: Add Exhaustion Score (HyperWave + Money Flow)

**Files:**
- Modify: `indicators/v7-warbird-institutional.pine`

**Step 1: Add exhaustion scoring logic**

Uses the **real HyperWave oscillator** from the LuxAlgo Oscillator Matrix source (Kirk-provided), combined with centered Money Flow for confluence. This is the actual formula, not a proxy.

HyperWave: Normalized linear regression of price position within the high-low-average envelope, smoothed by EMA(3). Ranges roughly -100 to +100.

Money Flow: Centered MFI (MFI - 50) smoothed by SMA(6). Ranges roughly -50 to +50. Positive = buying pressure, negative = selling pressure.

Reversal detection: Volume spike + oscillator/MFI confluence at fib extension zones.

```pine
//=====================
// EXHAUSTION SCORE (HyperWave + Money Flow confluence)
// Source: LuxAlgo Oscillator Matrix — exact formula (Kirk-provided source)
// HyperWave: normalized linreg of price position, EMA smoothed
// Money Flow: centered MFI(35) with SMA(6) smoothing
// Reversal: volume spike + dual-oscillator confluence at fib extensions
//=====================

// --- HyperWave Oscillator (Oscillator Matrix params: len=7, sL=3) ---
int hwLen = 7
int hwSmooth = 3
float hwHi = ta.highest(hwLen)
float hwLo = ta.lowest(hwLen)
float hwAv = ta.sma(hl2, hwLen)
float hwOsc = ta.ema(ta.linreg((close - math.avg(hwHi, hwLo, hwAv)) / (hwHi - hwLo) * 100, hwLen, 0), hwSmooth)
float hwSignal = ta.sma(hwOsc, 2)

// --- Money Flow (Oscillator Matrix params: mfL=35, mfS=6) ---
float mfOsc = ta.sma(ta.mfi(hl2, 35) - 50, 6)

// --- Exhaustion detection ---
bool hwOverbought = hwOsc > 80
bool hwOversold = hwOsc < -80
bool mfOverbought = mfOsc > 20
bool mfOversold = mfOsc < -20

// Confluence: both oscillators agree on exhaustion
bool exhaustionBearish = hwOverbought and mfOverbought
bool exhaustionBullish = hwOversold and mfOversold

// Reversal signal: volume spike during exhaustion (Oscillator Matrix: rsF=4)
int rvLen = 7
float rvThreshold = 1.0 + 4.0 / 10.0  // 1.4x average volume
bool volSpike = volume > ta.sma(volume, rvLen) * rvThreshold
bool reversalBear = exhaustionBearish and volSpike and ta.crossunder(hwOsc, hwSignal)
bool reversalBull = exhaustionBullish and volSpike and ta.crossover(hwOsc, hwSignal)

// Proximity to fib extensions amplifies score
bool nearT1 = not na(pT1) and math.abs(close - pT1) <= atr14
bool nearT2 = not na(pT2) and math.abs(close - pT2) <= atr14
float fibProximityBoost = nearT2 ? 30.0 : nearT1 ? 15.0 : 0.0

// Exhaustion score: 0 = neutral, 100 = maximum exhaustion
// HyperWave contributes 0-40, Money Flow contributes 0-30, fib proximity 0-30
float hwContrib = hwOverbought or hwOversold ? math.min(40.0, math.abs(hwOsc) / 100.0 * 40.0) : 0.0
float mfContrib = mfOverbought or mfOversold ? math.min(30.0, math.abs(mfOsc) / 50.0 * 30.0) : 0.0
float exhaustionScore = math.max(0.0, math.min(100.0, hwContrib + mfContrib + fibProximityBoost))
```

**Step 2: Add export (1 slot)**

```pine
plot(exhaustionScore, "ml_exhaustion_score", display=display.none)
```

**Step 3: Run verification + commit**

```bash
./scripts/guards/pine-lint.sh && git add indicators/v7-warbird-institutional.pine && git commit -m "feat(v7): add exhaustion score — HyperWave + Money Flow confluence at fib extensions"
```

---

### Task 14: Final Budget Audit and Verification

**Files:**
- Verify: `indicators/v7-warbird-institutional.pine`

**Step 1: Run full verification pipeline**

```bash
./scripts/guards/pine-lint.sh
./scripts/guards/check-contamination.sh
npm run build
```

Expected:
- pine-lint: 0 errors, plot budget ~61/64 (58 plots + 3 alerts)
- check-contamination: pass
- npm run build: pass

**Step 2: Audit plot count manually**

Count all `plot(` and `alertcondition(` calls. Expected totals:
- v6 base: 60 plots
- Removed: -15 (TA Core Pack) -1 (vix_close) = 44 plots remaining
- New features: +14 (RVOL, OR state, OR dist, sweep bull, sweep bear, CHoCH, FVG bull, FVG bear, bitmask, SMH, cooldown, bars since exit, vol-adj SL, exhaustion)
- Plots: 44 + 14 = 58
- Alertconditions: 3 (unchanged)
- **Total: 61/64 (3 slots headroom)**

**Step 3: Verify no regressions**

Confirm these are unchanged:
- Fib engine (ZigZag, anchor, confluence)
- HTF confluence check
- Fib level definitions and colors
- 3 alertconditions (entry long, entry short, pivot break)
- `barstate.isconfirmed` on all structure conditions

**Step 4: Commit final state**

```bash
git add indicators/v7-warbird-institutional.pine
git commit -m "feat(v7): final audit — 61/64 budget, all verification gates pass"
```

---

### Task 15: Update Design Doc and Memory

**Files:**
- Modify: `docs/plans/2026-03-29-v7-luxalgo-institutional-upgrade-design.md`
- Modify: `docs/plans/2026-03-20-ag-teaches-pine-architecture.md` (update log entry)

**Step 1: Add completion note to design doc**

**Step 2: Add update log entry to active plan**

```markdown
- 2026-03-29: Created `indicators/v7-warbird-institutional.pine` — LuxAlgo-informed institutional upgrade. 14 new ICT/SMC features (RVOL, Opening Range, liquidity sweeps, CHoCH, FVG, bitmask, SMH, cooldown, vol-adjusted SL, exhaustion). VIX→VVIX swap. SMH intermarket addition. TA Core Pack plots offloaded to server-side (computation stays, exports removed). Plot budget: 61/64 (3 headroom). Security calls: 9/40. All detection logic from published ICT/SMC reference implementations, no hand-rolled patterns.
```

**Step 3: Save memory**

**Step 4: Commit**

```bash
git add docs/plans/ indicators/v7-warbird-institutional.pine
git commit -m "docs: complete v7 institutional upgrade — design doc + plan update"
```

---

## Post-Implementation: TradingView Validation

After all tasks are committed, Kirk must manually:

1. Paste `v7-warbird-institutional.pine` into TradingView Pine Editor
2. Confirm it compiles without errors
3. Confirm all 14 new `ml_*` exports appear in the Style tab
4. Confirm existing fib lines, zone box, and trade state lines render correctly
5. Confirm VVIX and SMH intermarket inputs are available in settings

This is NOT automatable — TradingView validation requires manual paste-and-load.
