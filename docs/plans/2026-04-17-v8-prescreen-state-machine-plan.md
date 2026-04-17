# v8-prescreen State-Machine Rebuild — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Turn `indicators/v8-warbird-prescreen.pine` from a losing every-flip-is-a-trade strategy (PF 0.647, 1,706 trades) into a gated, state-machine-based wrapper that fires `strategy.entry` only when price retests the ladder ENTRY level with all quality/HTF/ADX/session/asymmetric gates aligned.

**Architecture:** Keep SATS v1.9.0 engine verbatim. Add a `tradeState` enum (IDLE → FORMING → READY → TRADE_ON → EXITED/INVALIDATED/EXPIRED). Ladder is drawn at FORMING and frozen until resolution. Entry fires at TRADE_ON when a bar closes at/through ENTRY with gates still aligned. Five independently-toggleable gate layers (L1–L5) let us measure per-layer PF lift via named backtest runs R0 → R5.

**Tech Stack:** Pine Script v6 (TradingView strategy), TradingView MCP for compile + backtest automation, `scripts/guards/pine-lint.sh`, `scripts/guards/check-contamination.sh`, `scripts/guards/check-indicator-strategy-parity.sh`, `npm run build`.

**Design doc:** `docs/plans/2026-04-17-v8-prescreen-state-machine-design.md` (commit 39e4d77).

---

## Task conventions for this plan

Pine has no unit test framework, so "tests" are:
- **Compile:** `pine_check` via MCP returns `success: true, errors: 0`.
- **Guard suite:** `pine-lint.sh`, `check-contamination.sh`, `check-indicator-strategy-parity.sh` all pass.
- **Build:** `npm run build` passes.
- **Backtest gate:** After each layer, run the strategy on TV (MES 15m, 2020-01-01 → 2024-12-31) and record PF / WR / net P&L / trade count / max DD into `docs/plans/2026-04-17-backtest-results.md`.

Each task ends in a commit. Push only on Kirk's explicit OK (per `feedback_no_push_without_permission.md`).

---

## Phase 0 — Preflight

### Task 0.1: Snapshot current on-chart state (baseline R0)

**Files:**
- Create: `docs/plans/2026-04-17-backtest-results.md` (table header only)
- Use: `mcp__tradingview__data_get_strategy_results`, `mcp__tradingview__capture_screenshot`, browser `ui_evaluate` fallback

**Step 1:** Ensure TV chart is on `CME_MINI:MES1!` 15m, Strategy Tester panel open, chart range covers 2020-01-01 → 2024-12-31 with Deep Backtesting on. Capture full screenshot to `screenshots/r0-baseline.png`.

**Step 2:** Read strategy metrics via `ui_evaluate` DOM scrape (MCP internal_api path is broken — use DOM):

```js
(function(){
  const panel = document.querySelector('[data-name="backtesting-content-wrapper"]');
  return panel ? panel.innerText.slice(0, 3000) : 'panel not found';
})()
```

**Step 3:** Append row to `docs/plans/2026-04-17-backtest-results.md`:

```markdown
| Run | Gates | Trades | PF | WR | Net P&L | Max DD | Commit |
|-----|-------|--------|----|----|---------|--------|--------|
| R0  | none (current) | 1706 | 0.647 | 33.4% | -$9,833 | $11,657 | 4a96e92 |
```

**Step 4:** Commit:
```
git add docs/plans/2026-04-17-backtest-results.md screenshots/r0-baseline.png
git commit -m "Baseline R0: snapshot current v8-prescreen state (PF 0.647)"
```

---

### Task 0.2: Diagnose invisible table root cause

**Files:**
- Read-only: `indicators/v8-warbird-prescreen.pine`

**Step 1:** Grep for table-related code:
```
Grep pattern: "table\.new|table\.cell|table\.delete|showDashboard|showInfoTable|showScoreTable|GRP_DASH"
```

**Step 2:** Inspect inputs in `GRP_DASH` group — identify which dashboard toggle is expected to show the table and its default. Record finding in `docs/plans/2026-04-17-backtest-results.md` under "Diagnostics" subsection.

**Step 3:** Check on-chart indicator inputs via MCP (`data_get_indicator` with `entity_id jrwTt0`) — find which `in_NN` corresponds to the dashboard toggle and its current value.

**Step 4:** If toggle is OFF, flip it ON via `indicator_set_inputs` and verify table appears. If toggle is ON but table invisible, the cause is in the Pine code — record exact line(s) responsible and defer fix to Task 1.2.

**Step 5:** Commit the diagnostic note only (no code change yet):
```
git add docs/plans/2026-04-17-backtest-results.md
git commit -m "Diagnose invisible table (root cause finding)"
```

---

## Phase 1 — Bug fixes (no behavior change)

### Task 1.1: Remove `max_bars_back = 5000` (ST drift fix)

**Files:**
- Modify: `indicators/v8-warbird-prescreen.pine:15`

**Step 1:** Edit line 15, remove the line:
```pine
     max_bars_back          = 5000,
```

**Step 2:** Compile via `mcp__tradingview__pine_check` — expect `success: true, errors: 0`. Warnings about `barstate.islast` may still appear; those are addressed in Task 1.5.

**Step 3:** Inject source via `pine_set_source` then `pine_smart_compile`. Scroll chart from 2020 to 2026 on 15m. Capture screenshots at 4 zoom levels: 1 month, 6 months, 2 years, full history. Save to `screenshots/task1.1-st-zoom-*.png`.

**Step 4:** Verify no ST line jump between zoom levels. If ST still drifts, root cause is deeper than `max_bars_back` — open a diagnostic subtask.

**Step 5:** Commit:
```
git add indicators/v8-warbird-prescreen.pine screenshots/task1.1-st-zoom-*.png
git commit -m "Remove max_bars_back=5000 cap (fix ST drift on scroll)"
```

---

### Task 1.2: Fix invisible table

**Files:**
- Modify: `indicators/v8-warbird-prescreen.pine` (exact lines from Task 0.2 diagnostic)

**Step 1:** Apply the fix identified in Task 0.2. Likely shapes:
- Flip `showDashboardInput` default to `true`, **or**
- Hoist `table.new` out of a conditional that never fires, **or**
- Guard `table.delete` with `barstate.isfirst` so it doesn't run every bar.

**Step 2:** Compile via MCP → expect clean.

**Step 3:** Inject via `pine_set_source` + `pine_smart_compile`. Verify table renders on chart. Capture screenshot to `screenshots/task1.2-table-visible.png`.

**Step 4:** Commit:
```
git add indicators/v8-warbird-prescreen.pine screenshots/task1.2-table-visible.png
git commit -m "Fix invisible dashboard table"
```

---

### Task 1.3: Remove 2 dead public SATS instances from TV chart

**Files:** none (chart hygiene only)

**Step 1:** Use `mcp__tradingview__chart_manage_indicator` with `action: remove` and `entity_id: xgdLpj`, then again with `entity_id: JxTjPm`.

**Step 2:** Call `chart_get_state`; verify only `jrwTt0` (SATS-PS) remains among SATS-family studies. Other studies (Warbird v7, Auto Fib, Nexus, etc.) stay.

**Step 3:** Capture `screenshots/task1.3-clean-studies.png`.

**Step 4:** No code commit — note the cleanup in `docs/plans/2026-04-17-backtest-results.md` under "Diagnostics":
```
git add docs/plans/2026-04-17-backtest-results.md screenshots/task1.3-clean-studies.png
git commit -m "Remove dead public SATS copies from TV chart"
```

---

### Task 1.4: Clear 5 ternary-scope Pine warnings

**Files:**
- Modify: `indicators/v8-warbird-prescreen.pine` at lines 402, 595, 596, 650, 684

**Step 1:** At each line, lift the function call out of the ternary / nested scope into a local var called on every bar. Example for L402:

Before (pattern — actual line may differ; read the file):
```pine
float volZ = hasVolume ? calcVolumeZ(volLen) : 0.0
```

After:
```pine
float vzCalc = calcVolumeZ(volLen)
float volZ   = hasVolume ? vzCalc : 0.0
```

Apply the same pattern to `calcSignalScore` (L595, L596) and `calcScoreBreakdown` (L650, L684).

**Step 2:** Compile via MCP → expect `errors: 0, warnings: 2` (only the remaining 2 `barstate.islast` warnings).

**Step 3:** Commit:
```
git add indicators/v8-warbird-prescreen.pine
git commit -m "Lift fn calls out of ternary/nested scope (clear 5 Pine warnings)"
```

---

### Task 1.5: Acknowledge or clear 2 `barstate.islast` warnings

**Files:**
- Modify: `indicators/v8-warbird-prescreen.pine:931`, `:1052`

**Step 1:** Read both blocks. Classify each:
- If the logic is display-only (updating a label with latest values) and OK to run only on confirmed bars: **acknowledge** with an inline comment like `// intentional: display-only, confirmed-bar cadence is fine` and leave the warning.
- If the logic must fire on realtime open bars: **move** the code out of `barstate.islast` and replace with a more appropriate guard (usually `barstate.isconfirmed or barstate.islast`), or enable `calc_on_every_tick = true` at the `strategy()` header (expensive, only if necessary).

**Step 2:** Compile → expect `errors: 0, warnings: 0` (clean) if we added `calc_on_every_tick`; else `warnings: 2` with acknowledgment comments.

**Step 3:** Commit:
```
git add indicators/v8-warbird-prescreen.pine
git commit -m "Resolve remaining Pine barstate.islast warnings"
```

---

## Phase 2 — State machine scaffolding

### Task 2.1: Add `tradeState` enum, var, and helper functions

**Files:**
- Modify: `indicators/v8-warbird-prescreen.pine` — insert block after existing var declarations (near line 470, just before the flip-detection block)

**Step 1:** Add enum + state var + helper:

```pine
// ══════════════════════════════════════════════════════════
// STATE MACHINE
// ══════════════════════════════════════════════════════════
// Pine v6 has no real enum; use named int constants.
int STATE_IDLE         = 0
int STATE_FORMING      = 1
int STATE_READY        = 2
int STATE_TRADE_ON     = 3
int STATE_EXITED       = 4
int STATE_INVALIDATED  = 5
int STATE_EXPIRED      = 6

var int   tradeState    = STATE_IDLE
var int   formingBar    = na   // bar_index when setup entered FORMING
var int   entryBarIdx   = na   // bar_index when TRADE_ON fired
var float setupScore    = na   // snapshot of signalScore at FORMING
var float setupTqi      = na   // snapshot of TQI at FORMING

// New inputs
expiryBarsInput  = input.int(20,  "Setup Expiry (bars without entry)", minval = 5,  maxval = 200, group = GRP_RISK)
timeoutBarsInput = input.int(100, "Trade Timeout (bars post-entry)",   minval = 10, maxval = 500, group = GRP_RISK)
```

**Step 2:** Compile. Expect clean. No behavior change yet — these vars are declared but not yet used in any transition.

**Step 3:** Commit:
```
git add indicators/v8-warbird-prescreen.pine
git commit -m "Scaffold state-machine constants, vars, and expiry/timeout inputs"
```

---

### Task 2.2: Add gate-evaluation helper

**Files:**
- Modify: `indicators/v8-warbird-prescreen.pine` — same region as Task 2.1

**Step 1:** Add a single `gatesPass(isBuy)` helper that returns a bool. This is the pure gate evaluator; individual gate inputs will be added progressively in Phases 7–11. For Phase 2, it returns `true` (no gates active yet):

```pine
gatesPass(bool isBuy) =>
    // Phase 7 (L1): quality
    // Phase 8 (L2): HTF trend
    // Phase 9 (L3): ADX
    // Phase 10 (L4): session
    // Phase 11 (L5): asymmetric
    // For now all layers off — returns true so R0b backtest measures
    // pure state-machine impact.
    true
```

**Step 2:** Compile → clean.

**Step 3:** Commit:
```
git add indicators/v8-warbird-prescreen.pine
git commit -m "Add gatesPass() helper (stub for L1-L5 layers)"
```

---

## Phase 3 — Flip handler → FORMING transition

### Task 3.1: Rewrite `if confirmedBuy` block

**Files:**
- Modify: `indicators/v8-warbird-prescreen.pine` — current block around L620-660 (read first, line numbers may shift after Phase 1/2 edits)

**Step 1:** Replace the current `if confirmedBuy:` block with:

```pine
if confirmedBuy and tradeState == STATE_IDLE and gatesPass(true)
    float tEntry = close
    float slBase = not na(lastPivotLow) ? lastPivotLow : low
    float rawSl  = slBase - effectiveSlMult * atrValue
    float minSl  = tEntry - effectiveSlMult * atrValue
    float tSl    = math.min(rawSl, minSl)
    float risk   = tEntry - tSl

    tradeDir      := 1
    tradeEntryBar := bar_index          // flip bar (anchor)
    tradeEntry    := tEntry
    tradeSl       := tSl
    tradeTp1      := tEntry + risk * liveTp1R
    tradeTp2      := tEntry + risk * liveTp2R
    tradeTp3      := tEntry + risk * liveTp3R
    tradeTp1R     := liveTp1R
    tradeTp2R     := liveTp2R
    tradeTp3R     := liveTp3R
    hitTp1        := false
    hitTp2        := false
    hitTp3        := false

    tradeState    := STATE_FORMING
    formingBar    := bar_index
    setupScore    := buyScore           // existing computed var
    setupTqi      := tqi

    // DO NOT call strategy.entry here — moved to Phase 4 Task 4.2
```

**Step 2:** Compile → clean.

**Step 3:** Commit:
```
git add indicators/v8-warbird-prescreen.pine
git commit -m "Rewrite long flip handler to enter FORMING state (no entry yet)"
```

---

### Task 3.2: Rewrite `if confirmedSell` block

**Files:**
- Modify: `indicators/v8-warbird-prescreen.pine`

**Step 1:** Mirror Task 3.1 for shorts — same structure, inverted stop/risk math, `tradeDir := -1`, `setupScore := sellScore`.

**Step 2:** Compile → clean.

**Step 3:** Commit:
```
git add indicators/v8-warbird-prescreen.pine
git commit -m "Rewrite short flip handler to enter FORMING state (no entry yet)"
```

---

### Task 3.3: Add INVALIDATED transition (opposite flip before TRADE_ON)

**Files:**
- Modify: `indicators/v8-warbird-prescreen.pine` — insert before the new FORMING transitions so INVALIDATED is checked first

**Step 1:** Add:

```pine
// INVALIDATED: opposite ST flip while setup is FORMING or READY
if (tradeState == STATE_FORMING or tradeState == STATE_READY) and ((tradeDir == 1 and confirmedSell) or (tradeDir == -1 and confirmedBuy))
    tradeState := STATE_INVALIDATED
    // Clear trade vars so next flip can create a fresh setup
    tradeDir   := 0
    // (Ladder lines get greyed-out/deleted in the drawing block, not here.)
```

**Step 2:** Immediately after the INVALIDATED check, add a transition from `INVALIDATED → IDLE` so the next flip can create a new setup:

```pine
if tradeState == STATE_INVALIDATED and barstate.isconfirmed
    tradeState := STATE_IDLE
```

**Step 3:** Compile → clean.

**Step 4:** Commit:
```
git add indicators/v8-warbird-prescreen.pine
git commit -m "Add INVALIDATED state on opposite flip before TRADE_ON"
```

---

### Task 3.4: Add EXPIRED transition (bars elapsed without entry)

**Files:**
- Modify: `indicators/v8-warbird-prescreen.pine`

**Step 1:** Add:

```pine
// EXPIRED: setup has been FORMING/READY for > expiryBarsInput bars without a retest
if (tradeState == STATE_FORMING or tradeState == STATE_READY) and not na(formingBar) and (bar_index - formingBar) >= expiryBarsInput
    tradeState := STATE_EXPIRED

if tradeState == STATE_EXPIRED and barstate.isconfirmed
    tradeState := STATE_IDLE
    tradeDir   := 0
```

**Step 2:** Compile → clean.

**Step 3:** Commit:
```
git add indicators/v8-warbird-prescreen.pine
git commit -m "Add EXPIRED state after N bars without retest"
```

---

### Task 3.5: Add FORMING → READY confirmation transition

**Files:**
- Modify: `indicators/v8-warbird-prescreen.pine`

**Step 1:** Add right after the FORMING transitions:

```pine
// READY: bar that entered FORMING has confirmed
if tradeState == STATE_FORMING and barstate.isconfirmed and bar_index > formingBar
    tradeState := STATE_READY
```

**Step 2:** Compile → clean.

**Step 3:** Commit:
```
git add indicators/v8-warbird-prescreen.pine
git commit -m "Add FORMING to READY transition on next confirmed bar"
```

---

## Phase 4 — Retest trigger → TRADE_ON

### Task 4.1: Add retest check + TRADE_ON transition + `strategy.entry` move

**Files:**
- Modify: `indicators/v8-warbird-prescreen.pine`

**Step 1:** Insert after the FORMING/READY/INVALIDATED/EXPIRED logic:

```pine
// TRADE_ON: bar closes at or through ENTRY with gates still aligned
bool retestLong  = tradeDir ==  1 and barstate.isconfirmed and close <= tradeEntry
bool retestShort = tradeDir == -1 and barstate.isconfirmed and close >= tradeEntry
bool gatesStill  = gatesPass(tradeDir == 1)

if tradeState == STATE_READY and (retestLong or retestShort) and gatesStill
    tradeState  := STATE_TRADE_ON
    entryBarIdx := bar_index
    if tradeDir == 1
        strategy.entry("Long", strategy.long)
    else
        strategy.entry("Short", strategy.short)
```

**Step 2:** Compile → clean.

**Step 3:** Commit:
```
git add indicators/v8-warbird-prescreen.pine
git commit -m "Add TRADE_ON transition on retest with gate re-check; move strategy.entry"
```

---

### Task 4.2: Ensure original flip handler no longer calls `strategy.entry`

**Files:**
- Modify: `indicators/v8-warbird-prescreen.pine`

**Step 1:** Grep for `strategy.entry` — should now appear **only** inside the TRADE_ON block. If it also exists in Task 3.1/3.2 blocks (leftover), remove.

**Step 2:** Compile → clean.

**Step 3:** Commit if any change needed; otherwise skip with a `git commit --allow-empty` to mark the audit.
```
git commit --allow-empty -m "Verify strategy.entry only fires from TRADE_ON transition"
```

---

## Phase 5 — Execution contract (TP ladder + exits)

### Task 5.1: Replace monolithic `strategy.exit` with 3-leg `qty_percent` ladder

**Files:**
- Modify: `indicators/v8-warbird-prescreen.pine` — insert after the `strategy.entry` calls in Task 4.1

**Step 1:** In the TRADE_ON block, after `strategy.entry`, add:

```pine
// Split exit: 40% at TP1, 30% at TP2, 30% at TP3. SL shared.
string entryId = tradeDir == 1 ? "Long" : "Short"
strategy.exit("TP1", from_entry = entryId, qty_percent = 40, stop = tradeSl, limit = tradeTp1)
strategy.exit("TP2", from_entry = entryId, qty_percent = 30, stop = tradeSl, limit = tradeTp2)
strategy.exit("TP3", from_entry = entryId, qty_percent = 30, stop = tradeSl, limit = tradeTp3)
```

**Step 2:** Remove any existing `strategy.exit` calls from the old flip-handler blocks (the single `stop=tradeSl, limit=tradeTp3` exit).

**Step 3:** Compile → clean.

**Step 4:** Commit:
```
git add indicators/v8-warbird-prescreen.pine
git commit -m "Replace single exit with 3-leg qty_percent ladder (40/30/30 at TP1/TP2/TP3)"
```

---

### Task 5.2: Switch TP mode default `Dynamic` → `Fixed`

**Files:**
- Modify: `indicators/v8-warbird-prescreen.pine` — `tpModeInput` definition (grep for `tpModeInput = input.string`)

**Step 1:** Change the default from `"Dynamic"` to `"Fixed"`. Keep both options available.

**Step 2:** Compile → clean.

**Step 3:** On TV chart, open indicator inputs and confirm the new default appears, or use `indicator_set_inputs` to set the live chart instance to Fixed.

**Step 4:** Commit:
```
git add indicators/v8-warbird-prescreen.pine
git commit -m "Default TP mode to Fixed (stops dynamic TP3 repaint)"
```

---

### Task 5.3: Add TRADE_ON → EXITED on opposite flip / timeout

**Files:**
- Modify: `indicators/v8-warbird-prescreen.pine`

**Step 1:** Add after the TRADE_ON block:

```pine
// Opposite-flip exit during active trade
if tradeState == STATE_TRADE_ON and ((tradeDir == 1 and confirmedSell) or (tradeDir == -1 and confirmedBuy))
    strategy.close(tradeDir == 1 ? "Long" : "Short", comment = "opp_flip")
    tradeState := STATE_EXITED

// Timeout exit
if tradeState == STATE_TRADE_ON and not na(entryBarIdx) and (bar_index - entryBarIdx) >= timeoutBarsInput
    strategy.close(tradeDir == 1 ? "Long" : "Short", comment = "timeout")
    tradeState := STATE_EXITED

// EXITED → IDLE on next confirmed bar
if tradeState == STATE_EXITED and barstate.isconfirmed
    tradeState := STATE_IDLE
    tradeDir   := 0
```

**Step 2:** Note: the SL and TP3 exits from the ladder (Task 5.1) will naturally close the position; this block adds the opp-flip and timeout forced closes. When the ladder's SL/TP3 fills, we need to also reset `tradeState`. Add detection based on `strategy.position_size`:

```pine
// Ladder-based SL/TP3 exit detection
if tradeState == STATE_TRADE_ON and strategy.position_size == 0
    tradeState := STATE_EXITED
```

**Step 3:** Compile → clean.

**Step 4:** Commit:
```
git add indicators/v8-warbird-prescreen.pine
git commit -m "Add TRADE_ON exits (opposite flip, timeout, position-flat detection)"
```

---

### Task 5.4: Update ladder drawing to respect state machine

**Files:**
- Modify: `indicators/v8-warbird-prescreen.pine` — current block around L719-770 (the `showRiskInput` drawing block)

**Step 1:** Change the drawing trigger from `(confirmedBuy or confirmedSell) and not na(tradeSl)` to `tradeState == STATE_FORMING and not na(tradeSl)`. This ensures the ladder is drawn **once, at FORMING**, not every flip.

**Step 2:** Inside the INVALIDATED block (Task 3.3), delete the ladder lines and labels so they don't linger:
```pine
if tradeState == STATE_INVALIDATED
    line.delete(lineEntry)
    line.delete(lineSL)
    line.delete(lineTp1)
    line.delete(lineTp2)
    line.delete(lineTp3)
    label.delete(lbEntry)
    label.delete(lbSL)
    label.delete(lbTp1)
    label.delete(lbTp2)
    label.delete(lbTp3)
```

**Step 3:** Same for EXPIRED block.

**Step 4:** In the label text, change `"▲ BUY"` / `"▼ SELL"` at FORMING time to `"LONG BIAS"` / `"SHORT BIAS"`. The real `"▲ BUY"` / `"▼ SELL"` labels now fire only at TRADE_ON. Insert new label.new calls at the TRADE_ON block.

**Step 5:** Compile → clean.

**Step 6:** Commit:
```
git add indicators/v8-warbird-prescreen.pine
git commit -m "Anchor ladder drawing to FORMING state; cleanup on INVALIDATED/EXPIRED"
```

---

## Phase 6 — R0b: measure pure semantic-fix lift

### Task 6.1: Confirm all gates OFF, run R0b backtest

**Files:**
- Modify: live TV chart inputs only (no code change)
- Record: `docs/plans/2026-04-17-backtest-results.md`

**Step 1:** Via `indicator_set_inputs`, set all gate toggles (`useHtfGate`, `useAdxGate`, `useSessionGate`) to `false`. `gatesPass()` already returns `true` until Phases 7–11. Quality gate is not yet active.

**Step 2:** Let backtest recompute. Capture `screenshots/r0b-semantic-only.png` (full + strategy tester).

**Step 3:** DOM-scrape metrics (same approach as Task 0.1). Append to results table:
```
| R0b | semantic only | <N> | <PF> | <WR> | <P&L> | <DD> | <commit> |
```

**Step 4:** Kill-switch check: if R0b PF ≥ 1.2, flag to Kirk that the gate stack may be unnecessary.

**Step 5:** Commit:
```
git add docs/plans/2026-04-17-backtest-results.md screenshots/r0b-semantic-only.png
git commit -m "R0b backtest: semantic fix only (no gates)"
```

---

## Phase 7 — L1: Quality gate

### Task 7.1: Rename `minScoreInput` + activate it in `gatesPass()`

**Files:**
- Modify: `indicators/v8-warbird-prescreen.pine:108` (or wherever `minScoreInput` is defined)

**Step 1:** Rename title from `"Min Signal Score (display only)"` to `"Min ARP Score (ENTRY GATE)"`. Keep the var name the same.

**Step 2:** Add `useQualityGate = input.bool(true, "Enable Quality Gate (L1)", group = GRP_FILTER)` near the other gate inputs.

**Step 3:** Add TQI input: `minTqiInput = input.float(0.50, "Min TQI", minval = 0.0, maxval = 1.0, step = 0.05, group = GRP_FILTER)`.

**Step 4:** Update `gatesPass(isBuy)`:

```pine
gatesPass(bool isBuy) =>
    float s = isBuy ? buyScore : sellScore
    bool l1 = not useQualityGate or (s >= minScoreInput and tqi >= minTqiInput)
    l1
```

**Step 5:** Compile → clean.

**Step 6:** Commit:
```
git add indicators/v8-warbird-prescreen.pine
git commit -m "Activate L1 quality gate (ARP score + TQI)"
```

---

### Task 7.2: Run R1 backtest

**Step 1:** On TV chart, enable `useQualityGate`. Keep L2–L5 off.

**Step 2:** Capture `screenshots/r1-l1-quality.png`. DOM-scrape metrics.

**Step 3:** Append row to results table.

**Step 4:** Kill-switch check: if R1 PF ≥ 1.5, flag Kirk — L2–L5 may be optional polish.

**Step 5:** Commit:
```
git add docs/plans/2026-04-17-backtest-results.md screenshots/r1-l1-quality.png
git commit -m "R1 backtest: L1 quality gate active"
```

---

## Phase 8 — L2: HTF trend gate

### Task 8.1: Add HTF gate

**Files:**
- Modify: `indicators/v8-warbird-prescreen.pine`

**Step 1:** Add inputs:

```pine
useHtfGate = input.bool(true, "Enable HTF Trend Gate (L2)", group = GRP_FILTER)
htfInput   = input.timeframe("60", "HTF Timeframe", options = ["15", "60", "240"], group = GRP_FILTER)
```

**Step 2:** Add security call (near top of file after the ST computation but hoisted to global scope — `request.security` has strict placement rules):

```pine
[htfTrend] = request.security(syminfo.tickerid, htfInput, [stTrend], lookahead = barmerge.lookahead_off)
```

**Step 3:** Update `gatesPass`:

```pine
gatesPass(bool isBuy) =>
    float s  = isBuy ? buyScore : sellScore
    bool l1  = not useQualityGate or (s >= minScoreInput and tqi >= minTqiInput)
    bool l2  = not useHtfGate or (isBuy ? htfTrend == 1 : htfTrend == -1)
    l1 and l2
```

**Step 4:** Compile → clean.

**Step 5:** Commit:
```
git add indicators/v8-warbird-prescreen.pine
git commit -m "Add L2 HTF trend gate (MES 1h default)"
```

---

### Task 8.2: Run R2 backtest

Same pattern as Task 7.2. Enable L1 + L2, record metrics, commit.

---

## Phase 9 — L3: ADX gate

### Task 9.1: Add ADX gate

**Files:**
- Modify: `indicators/v8-warbird-prescreen.pine`

**Step 1:** Add inputs:

```pine
useAdxGate = input.bool(true, "Enable ADX Gate (L3)",  group = GRP_FILTER)
adxLenInput = input.int(14, "ADX Length",              group = GRP_FILTER)
adxMinInput = input.int(22, "ADX Min (trend threshold)", group = GRP_FILTER)
```

**Step 2:** Compute ADX (place next to other ta.* computations):

```pine
[_plusDI, _minusDI, adxVal] = ta.dmi(adxLenInput, adxLenInput)
```

**Step 3:** Extend `gatesPass`:

```pine
bool l3 = not useAdxGate or (adxVal >= adxMinInput)
l1 and l2 and l3
```

**Step 4:** Compile → clean.

**Step 5:** Commit:
```
git add indicators/v8-warbird-prescreen.pine
git commit -m "Add L3 ADX trend-strength gate"
```

---

### Task 9.2: Run R3 backtest

Same pattern. Enable L1 + L2 + L3, record, commit.

---

## Phase 10 — L4: Session gate

### Task 10.1: Add session filter

**Files:**
- Modify: `indicators/v8-warbird-prescreen.pine`

**Step 1:** Add inputs:

```pine
useSessionGate = input.bool(true, "Enable Session Gate (L4)",    group = GRP_FILTER)
skipOpenInput  = input.bool(true, "Skip 9:30-9:44 ET (open 15m)", group = GRP_FILTER)
rthOnlyInput   = input.bool(false, "RTH Only (9:30-16:00 ET)",    group = GRP_FILTER)
```

**Step 2:** Add helper:

```pine
inOpeningBars() =>
    // TradingView's time-of-day is based on chart exchange tz.
    // NY open = 9:30 ET. On MES (CME_MINI) chart tz, check hh:mm.
    int h = hour(time, "America/New_York")
    int m = minute(time, "America/New_York")
    h == 9 and m >= 30 and m < 45

inRth() =>
    int h = hour(time, "America/New_York")
    h >= 9 and h < 16 and not (h == 9 and minute(time, "America/New_York") < 30)
```

**Step 3:** Extend `gatesPass`:

```pine
bool l4 = not useSessionGate or (not (skipOpenInput and inOpeningBars()) and (not rthOnlyInput or inRth()))
l1 and l2 and l3 and l4
```

**Step 4:** Compile → clean.

**Step 5:** Commit:
```
git add indicators/v8-warbird-prescreen.pine
git commit -m "Add L4 session gate (skip 9:30-9:44 ET + optional RTH-only)"
```

---

### Task 10.2: Run R4 backtest

Same pattern. Enable L1 + L2 + L3 + L4, record, commit.

---

## Phase 11 — L5: Asymmetric thresholds

### Task 11.1: Split `minScoreInput` into long + short

**Files:**
- Modify: `indicators/v8-warbird-prescreen.pine`

**Step 1:** Replace `minScoreInput` with two inputs:

```pine
longMinScoreInput  = input.int(60, "Long Min ARP Score",  minval = 0, maxval = 102, group = GRP_FILTER)
shortMinScoreInput = input.int(70, "Short Min ARP Score", minval = 0, maxval = 102, group = GRP_FILTER)
```

**Step 2:** Update L1 in `gatesPass`:

```pine
float l1Min = isBuy ? longMinScoreInput : shortMinScoreInput
bool l1 = not useQualityGate or (s >= l1Min and tqi >= minTqiInput)
```

**Step 3:** Compile → clean.

**Step 4:** Commit:
```
git add indicators/v8-warbird-prescreen.pine
git commit -m "Add L5 asymmetric long/short quality thresholds"
```

---

### Task 11.2: Run R5 backtest (final config)

**Step 1:** Enable all L1–L5 gates on chart.

**Step 2:** Capture + scrape metrics. Append R5 row.

**Step 3:** Check ship criteria from design doc §8:
- PF ≥ 1.5
- WR ≥ 45%
- Net P&L > +$5,000
- Trade count 100–400
- Max DD < $3,000

**Step 4:** If **all** criteria met → proceed to Phase 12.
   If **some** met, **some** missed → report to Kirk with diagnosis.
   If **floor missed** (PF < 1.2 or WR < 42%) → halt, report, propose Approach C (long-only fallback).

**Step 5:** Commit:
```
git add docs/plans/2026-04-17-backtest-results.md screenshots/r5-all-layers.png
git commit -m "R5 backtest: all layers active (final config)"
```

---

## Phase 12 — Verification + ship

### Task 12.1: Full verification pipeline

**Files:** run all guards

**Step 1:**
```bash
# 1. TV compile
pine_code=$(cat "/Volumes/Satechi Hub/warbird-pro/indicators/v8-warbird-prescreen.pine")
curl -s -X POST "https://pine-facade.tradingview.com/pine-facade/translate_light?user_name=admin&v=3" \
  -H 'Referer: https://www.tradingview.com/' \
  -F "source=$pine_code" | python3 -c "import json,sys; d=json.load(sys.stdin); print('ok:' if d.get('success') and len(d['result']['errors'])==0 else 'FAIL:', d['result'])"

# 2. Pine lint
cd "/Volumes/Satechi Hub/warbird-pro" && ./scripts/guards/pine-lint.sh

# 3. Contamination
./scripts/guards/check-contamination.sh

# 4. Parity (should be unaffected — we only changed prescreen)
./scripts/guards/check-indicator-strategy-parity.sh

# 5. Build
npm run build
```

**Step 2:** All must pass. If any fails, halt and diagnose.

**Step 3:** Commit (if guards produced any lockfile / generated-file updates):
```
git add -A
git commit -m "Phase 12.1: verification pipeline passes clean"
```

---

### Task 12.2: Write results summary

**Files:**
- Append to: `docs/plans/2026-04-17-backtest-results.md`

**Step 1:** Add a narrative summary:
- Per-layer lift observations
- Which layers contributed, which were marginal
- R5 vs ship criteria: pass/fail breakdown
- Follow-up experiments (Dynamic TP revisit, long-only comparison, grid sweep relevance)

**Step 2:** Commit:
```
git add docs/plans/2026-04-17-backtest-results.md
git commit -m "Phase 12.2: results summary and follow-up recommendations"
```

---

### Task 12.3: Update memory

**Files:**
- Create: `/Users/zincdigital/.claude/projects/-Volumes-Satechi-Hub-warbird-pro/memory/project_v8_prescreen_state_machine.md`
- Modify: `/Users/zincdigital/.claude/projects/-Volumes-Satechi-Hub-warbird-pro/memory/MEMORY.md` (add index entry)

**Step 1:** Save memory with type=project covering:
- The R0→R5 lift profile
- Which gates are load-bearing vs optional
- The fact that `minScoreInput` was latent "display only" → now active gate
- Ship/fallback decisions

**Step 2:** Update MEMORY.md with a one-line index entry under "v8 Architecture".

**Step 3:** Memory files do not get committed (out of repo).

---

### Task 12.4: Kirk decision gate — ship or fallback

**No file changes.** Present R5 results vs ship criteria in terminal. Await one of:

- **SHIP:** push `main` (Kirk runs `git push`)
- **FALLBACK C (long-only):** open a new plan to strip short logic, re-run R5 long-only, compare
- **TUNE:** adjust thresholds (e.g., `adxMinInput` 22 → 25), re-run R5, repeat

---

## Per-phase time estimates

| Phase | Est. time | Dependency |
|---|---|---|
| 0 (Preflight) | 30 min | TV chart must be open |
| 1 (Bug fixes) | 60 min | Phase 0 diagnostics |
| 2 (Scaffold) | 20 min | Phase 1 |
| 3 (Flip → FORMING) | 45 min | Phase 2 |
| 4 (Retest → TRADE_ON) | 30 min | Phase 3 |
| 5 (Exits + ladder) | 45 min | Phase 4 |
| 6 (R0b backtest) | 15 min | Phase 5 |
| 7 (L1 + R1) | 30 min | Phase 6 |
| 8 (L2 + R2) | 30 min | Phase 7 |
| 9 (L3 + R3) | 30 min | Phase 8 |
| 10 (L4 + R4) | 30 min | Phase 9 |
| 11 (L5 + R5) | 30 min | Phase 10 |
| 12 (Ship) | 45 min | Phase 11 |

**Total:** ~7 hours of hands-on work, spread across as many sessions as Kirk wants. Natural stopping points between every phase.

---

## Rollback points

Each phase is a clean commit. To roll back:

- **To baseline (R0):** `git reset --hard 4a96e92` (current PS commit)
- **To semantic-fix only (R0b):** reset to the R0b commit
- **To last shipped layer:** reset to the most recent passing R-run commit

Never `git push --force`; if rollback is needed on main after push, create a revert commit.

---

## Skills / sub-skills invoked during execution

- `superpowers:executing-plans` (top-level)
- `superpowers:systematic-debugging` (on any failing compile / guard)
- `superpowers:verification-before-completion` (before each phase's commit)
- `trading-indicators:pine:debug` (on any Pine compile error)
- `trading-indicators:pine:validate` (Pine-specific lint)
- `trading-indicators:pine:verify` (full Warbird Pine verification pipeline)
