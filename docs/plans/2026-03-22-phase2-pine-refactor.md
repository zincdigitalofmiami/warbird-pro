# Phase 2: Pine Script Refactor — Unified Fib Engine

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Merge v1 AutoFib Structure + Intermarket indicator with v0 Rabid Raccoon's full level set and anchor reliability into a single production Pine Script v6 indicator, using `lib/fibonacci.ts` (dashboard) as the canonical spec.

**Architecture:** The dashboard TypeScript fib engine is production-proven and matches the screenshot. Pine must replicate its exact calculation, structural break locking, all 10 levels, and color scheme. The intermarket engine from v1 stays. ZigZag library from v0 is dropped (manual Reverse toggle = model-breaking).

**Tech Stack:** Pine Script v6, TradingView

**Parent docs:**
- Design: `docs/plans/2026-03-22-ag-pine-implementation-design.md`
- Active plan: `docs/plans/2026-03-20-ag-teaches-pine-architecture.md`
- P0+Phase1: `docs/plans/2026-03-22-p0-phase1-execution.md` (completed)

**Reference files (canonical spec — DO NOT modify these):**
- `lib/fibonacci.ts` — Multi-period confluence engine (8/13/21/34/55)
- `lib/charts/FibLinesPrimitive.ts` — Rendering spec (10 levels, colors, zone fill)
- `lib/colors.ts` — Color definitions
- `components/charts/LiveMesChart.tsx:855-902` — Structural break locking logic

**Input files (reference only — NOT the spec):**
- `indicators/v1-autofib-structure-intermarket.pine` — intermarket engine source
- `indicators/v0-rabid-raccoon-zigzag.pine` — level rendering reference

---

## What Changes vs v1

| Area | v1 (current) | v2 (this refactor) | Spec source |
|------|-------------|-------------------|-------------|
| Levels drawn | 3 (pivot, zone lo, zone hi) + optional targets/magnets | All 10 always (0, .236, .382, .5, .618, .786, 1, 1.236, 1.618, 2.0) | `FibLinesPrimitive.ts:49-60` |
| Colors | User-configurable (messy) | Locked to spec: white/grey/orange/green | `lib/colors.ts:43-54` |
| Confluence scoring | `fibScore()` counts matches but no range weighting | `confluence_count × range` (wider anchors preferred) | `lib/fibonacci.ts:146-173` |
| Direction | `close >= midpoint` → bullish | Same | `lib/fibonacci.ts:176-177` |
| Structural break | Re-anchor on close outside `[anchorHigh, anchorLow]` | Same — but must be `barstate.isconfirmed` only | `LiveMesChart.tsx:871` |
| Zone fill | Between `.618` and `.786` (decision zone) | Between `.382` and `.618` (around pivot) | `FibLinesPrimitive.ts:267-271` |
| Intermarket | Full engine (keep as-is) | Keep as-is | v1 indicator |
| News proxy | Full engine (keep as-is) | Keep as-is | v1 indicator |
| ZigZag library | Not used | Not used (dropped from v0) | N/A |

## What Does NOT Change

- Intermarket engine (all `request.security()` calls, regime logic, score model)
- News proxy engine
- Alert conditions
- Structure conditions (accept/reject/break logic)
- Signal markers

---

## Task 1: Create v2 Indicator File

**Files:**
- Create: `indicators/v2-warbird-unified.pine`

**Step 1: Copy v1 as starting point**

```bash
cd "/Volumes/Satechi Hub/warbird-pro"
cp indicators/v1-autofib-structure-intermarket.pine indicators/v2-warbird-unified.pine
```

**Step 2: Update header**

Change the indicator declaration to:

```pinescript
//@version=6
indicator("Warbird v2 — AutoFib + Intermarket", shorttitle="🦝 WB v2", overlay=true, max_lines_count=200, max_labels_count=200, max_boxes_count=50)
```

Add version comment block at top:

```pinescript
// Warbird v2 — Unified Fib Engine
// Canonical spec: lib/fibonacci.ts (dashboard TypeScript engine)
// Merge: v1 intermarket + v0 full levels + dashboard structural break locking
// Date: 2026-03-22
```

**Step 3: Commit**

```bash
git add indicators/v2-warbird-unified.pine
git commit -m "feat: create v2 warbird indicator scaffold from v1"
```

---

## Task 2: Replace Fib Level Definitions

**Files:**
- Modify: `indicators/v2-warbird-unified.pine`

**Step 1: Remove the old `groupStruct` input section**

Remove these inputs (they are now hardcoded to match spec):
- `pivotRatio`, `zoneLoRatio`, `zoneHiRatio`
- `target1Ratio`, `target2Ratio`
- `dnMagnet1Ratio`, `dnMagnet2Ratio`

**Step 2: Add the canonical 10-level definition**

Replace with constants matching `lib/fibonacci.ts:20-22` and `FibLinesPrimitive.ts:49-60`:

```pinescript
//=====================
// CANONICAL FIB LEVELS (from lib/fibonacci.ts + FibLinesPrimitive.ts)
// DO NOT change these — they match the dashboard exactly
//=====================

// Retracement ratios
FIB_ZERO  = 0.0
FIB_236   = 0.236
FIB_382   = 0.382
FIB_PIVOT = 0.5
FIB_618   = 0.618
FIB_786   = 0.786
FIB_ONE   = 1.0

// Extension ratios
FIB_T1    = 1.236
FIB_T2    = 1.618
FIB_T3    = 2.0

// Colors (from lib/colors.ts:43-54)
COLOR_ANCHOR      = #FFFFFF    // white — 0 and 1 levels
COLOR_RETRACEMENT = #808080    // 50% white — .236, .382, .618, .786
COLOR_PIVOT       = #FF9800    // orange — .5 level
COLOR_TARGET      = #4CAF50    // green — TARGET 1, 2, 3

// Widths (from FibLinesPrimitive.ts:49-60)
WIDTH_ANCHOR      = 1
WIDTH_RETRACEMENT = 1
WIDTH_PIVOT       = 2
WIDTH_TARGET      = 2
```

**Step 3: Verify no remaining references to old ratio inputs**

Search the file for `pivotRatio`, `zoneLoRatio`, `zoneHiRatio`, `target1Ratio`, `target2Ratio`, `dnMagnet1Ratio`, `dnMagnet2Ratio`. Replace all usage with the new constants.

**Step 4: Commit**

```bash
git add indicators/v2-warbird-unified.pine
git commit -m "feat(pine): replace configurable fib ratios with canonical 10-level spec"
```

---

## Task 3: Replace Confluence Scoring with Range-Weighted Version

**Files:**
- Modify: `indicators/v2-warbird-unified.pine`

**Step 1: Replace `fibScore()` function**

The current `fibScore()` counts confluence matches but does NOT weight by range. The dashboard spec at `lib/fibonacci.ts:146-173` uses `confluence_count × range`.

Replace the entire `fibScore()` function and the best-anchor selection logic with:

```pinescript
//=====================
// CONFLUENCE SCORING (from lib/fibonacci.ts:146-173)
// Score = confluence_count × range
// This prevents short-period narrow anchors from winning
//=====================

// Confluence ratios used for voting (lib/fibonacci.ts:30)
CONF_RATIOS_0 = 0.382
CONF_RATIOS_1 = 0.5
CONF_RATIOS_2 = 0.618

fibConfluenceScore(float h, float l) =>
    float rng = h - l
    if rng <= 0
        0.0
    else
        float tol = rng * fibConfluenceTolPct * 0.01
        int confCount = 0
        // For each of 3 confluence ratios on this anchor...
        for selfR = 0 to 2
            float selfRatio = selfR == 0 ? CONF_RATIOS_0 : selfR == 1 ? CONF_RATIOS_1 : CONF_RATIOS_2
            float selfLevel = l + rng * selfRatio
            // ...compare against 3 confluence ratios on each OTHER anchor
            for cmpR = 0 to 2
                float cmpRatio = cmpR == 0 ? CONF_RATIOS_0 : cmpR == 1 ? CONF_RATIOS_1 : CONF_RATIOS_2
                // Check all 5 period anchors
                float cmpLvl1 = fibLow1 + (fibHigh1 - fibLow1) * cmpRatio
                float cmpLvl2 = fibLow2 + (fibHigh2 - fibLow2) * cmpRatio
                float cmpLvl3 = fibLow3 + (fibHigh3 - fibLow3) * cmpRatio
                float cmpLvl4 = fibLow4 + (fibHigh4 - fibLow4) * cmpRatio
                float cmpLvl5 = fibLow5 + (fibHigh5 - fibLow5) * cmpRatio
                if math.abs(selfLevel - cmpLvl1) <= tol
                    confCount += 1
                if math.abs(selfLevel - cmpLvl2) <= tol
                    confCount += 1
                if math.abs(selfLevel - cmpLvl3) <= tol
                    confCount += 1
                if math.abs(selfLevel - cmpLvl4) <= tol
                    confCount += 1
                if math.abs(selfLevel - cmpLvl5) <= tol
                    confCount += 1
        // KEY DIFFERENCE: weight by range (lib/fibonacci.ts:168)
        float(confCount) * rng
```

**Step 2: Update score variables to float**

Change `score1` through `score5` and `bestScore` from `int` to `float` since the scoring now returns `float`:

```pinescript
score1 = fibConfluenceScore(fibHigh1, fibLow1)
score2 = fibConfluenceScore(fibHigh2, fibLow2)
score3 = fibConfluenceScore(fibHigh3, fibLow3)
score4 = fibConfluenceScore(fibHigh4, fibLow4)
score5 = fibConfluenceScore(fibHigh5, fibLow5)
bestScore = math.max(score1, score2, score3, score4, score5)
```

**Step 3: Verify anchor selection logic still works**

The `fibAnchorHighCandidate` / `fibAnchorLowCandidate` ternary chain should still work with float comparison. No changes needed there.

**Step 4: Commit**

```bash
git add indicators/v2-warbird-unified.pine
git commit -m "feat(pine): add range-weighted confluence scoring matching dashboard spec"
```

---

## Task 4: Add All 10 Level Lines + Zone Fill

**Files:**
- Modify: `indicators/v2-warbird-unified.pine`

**Step 1: Compute all 10 prices**

After the `fibPrice()` function, add:

```pinescript
// Compute all 10 canonical level prices
pZero   = fibPrice(FIB_ZERO)
p236    = fibPrice(FIB_236)
p382    = fibPrice(FIB_382)
pPivot  = fibPrice(FIB_PIVOT)
p618    = fibPrice(FIB_618)
p786    = fibPrice(FIB_786)
pOne    = fibPrice(FIB_ONE)
pT1     = fibPrice(FIB_T1)
pT2     = fibPrice(FIB_T2)
pT3     = fibPrice(FIB_T3)

// Zone fill bounds (around pivot, between .382 and .618)
// From FibLinesPrimitive.ts:267-271
zoneFillUpper = math.max(p382, p618)
zoneFillLower = math.min(p382, p618)
```

**Step 2: Replace line drawing section**

Remove the old 7-line drawing block and replace with 10 lines:

```pinescript
//=====================
// DRAW ALL 10 FIB LEVELS
//=====================

var line lineZero = line.new(bar_index, close, bar_index, close, color=color(na), width=1)
var line line236  = line.new(bar_index, close, bar_index, close, color=color(na), width=1)
var line line382  = line.new(bar_index, close, bar_index, close, color=color(na), width=1)
var line linePivot = line.new(bar_index, close, bar_index, close, color=color(na), width=1)
var line line618  = line.new(bar_index, close, bar_index, close, color=color(na), width=1)
var line line786  = line.new(bar_index, close, bar_index, close, color=color(na), width=1)
var line lineOne  = line.new(bar_index, close, bar_index, close, color=color(na), width=1)
var line lineT1   = line.new(bar_index, close, bar_index, close, color=color(na), width=1)
var line lineT2   = line.new(bar_index, close, bar_index, close, color=color(na), width=1)
var line lineT3   = line.new(bar_index, close, bar_index, close, color=color(na), width=1)

var box zoneBox = box.new(bar_index, close, bar_index, close, bgcolor=color(na), border_color=color(na))

drawAnchoredLine(lineZero,  true, pZero,  COLOR_ANCHOR,      WIDTH_ANCHOR,      drawLeftBar)
drawAnchoredLine(line236,   true, p236,   COLOR_RETRACEMENT, WIDTH_RETRACEMENT, drawLeftBar)
drawAnchoredLine(line382,   true, p382,   COLOR_RETRACEMENT, WIDTH_RETRACEMENT, drawLeftBar)
drawAnchoredLine(linePivot, true, pPivot, COLOR_PIVOT,       WIDTH_PIVOT,       drawLeftBar)
drawAnchoredLine(line618,   true, p618,   COLOR_RETRACEMENT, WIDTH_RETRACEMENT, drawLeftBar)
drawAnchoredLine(line786,   true, p786,   COLOR_RETRACEMENT, WIDTH_RETRACEMENT, drawLeftBar)
drawAnchoredLine(lineOne,   true, pOne,   COLOR_ANCHOR,      WIDTH_ANCHOR,      drawLeftBar)
drawAnchoredLine(lineT1,    true, pT1,    COLOR_TARGET,      WIDTH_TARGET,      drawLeftBar)
drawAnchoredLine(lineT2,    true, pT2,    COLOR_TARGET,      WIDTH_TARGET,      drawLeftBar)
drawAnchoredLine(lineT3,    true, pT3,    COLOR_TARGET,      WIDTH_TARGET,      drawLeftBar)

// Zone fill between .382 and .618 (FibLinesPrimitive.ts:267-271, PIVOT_FILL_OPACITY = 0.08)
if not na(zoneFillUpper) and not na(zoneFillLower)
    box.set_left(zoneBox, drawLeftBar)
    box.set_right(zoneBox, bar_index)
    box.set_top(zoneBox, zoneFillUpper)
    box.set_bottom(zoneBox, zoneFillLower)
    box.set_bgcolor(zoneBox, color.new(COLOR_PIVOT, 92))  // ~0.08 opacity = 92 transparency
    box.set_border_color(zoneBox, color.new(COLOR_PIVOT, 100))
else
    box.set_bgcolor(zoneBox, color(na))
    box.set_border_color(zoneBox, color(na))
```

**Step 3: Remove old visual toggle inputs that no longer apply**

Remove: `showPivotZone`, `showTargets`, `showDownMagnets`, `showZoneFill` — all 10 levels are always shown.

Keep: `targetLookbackBars`, `extendLevelsRight`, `useConfluenceAnchorSpan`, `showBg`, `showMarkers`.

Remove the entire `groupStyle` color/width inputs — colors are now locked to spec.

**Step 4: Update structure conditions to use new variable names**

Find all references to old price variables (`pZoneLo`, `pZoneHi`, `pDn1`, `pDn2`, `zoneUpper`, `zoneLower`) and update:
- `zoneUpper` → `math.max(p618, p786)` (decision zone for structure logic stays .618-.786)
- `zoneLower` → `math.min(p618, p786)` (decision zone for structure logic stays .618-.786)

Note: The zone FILL is .382-.618 (around pivot). The structure LOGIC zone is .618-.786 (decision zone). These are different.

**Step 5: Commit**

```bash
git add indicators/v2-warbird-unified.pine
git commit -m "feat(pine): draw all 10 canonical fib levels with spec colors and zone fill"
```

---

## Task 5: Verify No-Repaint Behavior

**Files:**
- Modify: `indicators/v2-warbird-unified.pine` (if fixes needed)

**Step 1: Audit all anchor updates for `barstate.isconfirmed` gating**

The structural break logic must ONLY re-anchor on confirmed bars. Check:

```pinescript
// This line must include barstate.isconfirmed:
bool structBreak = not na(fibAnchorHigh) and not na(fibAnchorLow) and
    barstate.isconfirmed and
    (close > fibAnchorHigh or close < fibAnchorLow)
```

And:

```pinescript
// This must also gate on confirmed:
if needsAnchor and (barstate.isconfirmed or na(fibAnchorHigh))
```

**Step 2: Audit `request.security()` calls for lookahead**

Every `request.security()` must use `lookahead=barmerge.lookahead_off`. Verify all 10 calls (5 intermarket + 5 news proxy) have this.

**Step 3: Audit structure conditions**

All structure break/accept/reject conditions use `close` and `close[1]`. Verify none reference `high[0]` on an unconfirmed bar in a way that could repaint.

**Step 4: Document findings**

Add a comment block at the top of the indicator:

```pinescript
// NO-REPAINT AUDIT:
// - Structural break: barstate.isconfirmed gated
// - request.security(): lookahead_off on all calls
// - Structure conditions: close-based, bar-close semantics
// - Last verified: 2026-03-22
```

**Step 5: Commit**

```bash
git add indicators/v2-warbird-unified.pine
git commit -m "audit(pine): verify no-repaint behavior on v2 indicator"
```

---

## Task 6: Clean Up Removed Inputs and Dead Code

**Files:**
- Modify: `indicators/v2-warbird-unified.pine`

**Step 1: Remove all `plot(na, ...)` phantom plots**

The old v1 had `plot(na, "Pivot")` etc. for alert placeholder compatibility. Remove these — we use `alertcondition()` which doesn't need phantom plots.

**Step 2: Remove the `groupStruct` input group entirely**

Already done in Task 2, but verify no orphaned references remain.

**Step 3: Remove the `groupStyle` input group entirely**

Colors and widths are now constants. Remove all user-configurable color/width inputs.

**Step 4: Verify the indicator compiles**

Paste the full script into TradingView Pine Editor and check for compilation errors. Fix any issues.

**Step 5: Commit**

```bash
git add indicators/v2-warbird-unified.pine
git commit -m "chore(pine): remove dead code and orphaned inputs from v2 indicator"
```

---

## Task 7: Update Alert Conditions for New Level Names

**Files:**
- Modify: `indicators/v2-warbird-unified.pine`

**Step 1: Update target alert conditions**

The v1 used `tagT1` for 1.236 and `tagT2` for 1.618. Add `tagT3` for 2.0:

```pinescript
tagT1 = not na(pT1) and (dir == 1 ? high >= pT1 : low <= pT1)
tagT2 = not na(pT2) and (dir == 1 ? high >= pT2 : low <= pT2)
tagT3 = not na(pT3) and (dir == 1 ? high >= pT3 : low <= pT3)

tagT1Event = oneShotEvent ? (tagT1 and not tagT1[1]) : tagT1
tagT2Event = oneShotEvent ? (tagT2 and not tagT2[1]) : tagT2
tagT3Event = oneShotEvent ? (tagT3 and not tagT3[1]) : tagT3

alertcondition(tagT1Event, "TARGET HIT: 1.236", "Warbird TARGET 1 (1.236) tagged. Price={{close}}")
alertcondition(tagT2Event, "TARGET HIT: 1.618", "Warbird TARGET 2 (1.618) tagged. Price={{close}}")
alertcondition(tagT3Event, "TARGET HIT: 2.0",   "Warbird TARGET 3 (2.0) tagged. Price={{close}}")
```

**Step 2: Commit**

```bash
git add indicators/v2-warbird-unified.pine
git commit -m "feat(pine): add TARGET 3 (2.0) alert and update alert messages"
```

---

## Task 8: Build Verification + Push

**Step 1: Run npm build**

```bash
cd "/Volumes/Satechi Hub/warbird-pro"
npm run build
```

Expected: PASS (Pine files don't affect TS build, but verify nothing else broke)

**Step 2: Run contamination check**

```bash
./scripts/guards/check-contamination.sh
```

Expected: PASS

**Step 3: Verify git status clean**

```bash
git status -sb
```

**Step 4: Push**

```bash
git push origin main
```

---

## Task 9: Manual TradingView Verification (Human Required)

This task requires the trader to manually verify the indicator in TradingView.

**Step 1: Load v2 indicator on MES 15m chart**

Copy the contents of `indicators/v2-warbird-unified.pine` into TradingView Pine Editor and add to chart.

**Step 2: Verify checklist**

- [ ] All 10 levels render (ZERO through TARGET 3)
- [ ] Colors match spec: white anchors, grey retracements, orange pivot, green targets
- [ ] Zone fill appears between .382 and .618 (subtle orange)
- [ ] Structural break re-anchors only on bar close (not intrabar)
- [ ] Fib direction flips correctly without manual "Reverse" toggle
- [ ] Intermarket regime background tint works (if `showBg` enabled)
- [ ] All alert conditions fire correctly
- [ ] No visible repaint on scroll-back
- [ ] Lines match dashboard fib rendering (compare side-by-side)

**Step 3: Document results**

Update this file with verification results and any bugs found.

---

## Gate: Phase 2 Complete

**Checklist before proceeding to Phase 3:**

- [ ] v2 indicator committed with all 10 levels
- [ ] Colors locked to dashboard spec
- [ ] Range-weighted confluence scoring implemented
- [ ] No-repaint audit passed
- [ ] All alerts working (including TARGET 3)
- [ ] Manual TradingView verification passed
- [ ] npm run build passes
- [ ] Contamination check passes
- [ ] All changes pushed to main

**Next:** Phase 3 (Strategy Build) requires a separate execution plan for Pine strategy + deep backtesting. Use `writing-plans` to create `2026-03-XX-phase3-strategy-build.md`.
