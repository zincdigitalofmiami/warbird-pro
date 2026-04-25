# Plan — v7 Backtest Strategy: Single-Ladder Snapshot Fix

**Date:** 2026-04-24
**Working file:** `indicators/v7-warbird-institutional-backtest-strategy.pine`
**Approved by:** Kirk (2026-04-24 — "do this, make the plan")
**Visual contract:** Screenshot 3 (clean single-ladder reference). NO deviation by 1 pixel.

---

## Summary

The prior /work session's "sticky trade projection overlay" added a second set of fib lines (`lineTradeEntry`, `lineActiveSl`, `lineTradeT1-T5`) on top of the live fib ladder. When the ZigZag engine re-anchors mid-trade, the overlay stays at the captured prices while the live ladder drifts, producing two stacked ladders with different anchor points — Kirk's Screenshot 1 wreck.

This plan removes that overlay architecture entirely and replaces it with a **15-value snapshot** of the existing fib ladder that freezes on `TRADE_SETUP → TRADE_ACTIVE` transition and releases on trade resolution. One set of line objects. One set of prices at any given bar. No stacking possible.

**Net effect:** diff shrinks by ~20 lines. Visual contract preserved pixel-perfect (all `label.set_*` calls untouched).

---

## Discovery Findings

- File size: 1,580 lines. 2 pre-existing warnings: W4 (4 EMA/VWAP plots without `display=`), W9 (53/64 outputs above 75% cap — informational only). 0 errors.
- Uncommitted diff: +200 / -142 across fib engine rewrite, strategy topology, pivot safety gates, and the overlay. This plan touches ONLY the overlay.
- File variants on disk:
  - `v7-warbird-institutional.pine` (78KB) — **LOCKED live indicator, NEVER touch (CLAUDE.md + feedback_never_touch_indicator.md)**
  - `v7-warbird-institutional-backtest-strategy.pine` (95KB) — **work surface, modified in working tree**
  - `v7-warbird-strategy.pine` (90KB) — AG training strategy, out of scope
- DANGER SCAN resolved as false positive — this work touches the backtest-strategy variant, not the locked live indicator.
- Label system at [1409-1443](../../indicators/v7-warbird-institutional-backtest-strategy.pine:1409) already matches Screenshot 3 visually. These calls are the pixel contract and will NOT be modified.

---

## Pushback & Resolution

| Question | Kirk's position | Impact on plan |
|---|---|---|
| Full revert of the 200-insertion diff? | NO — "not a full refactor" | Keep fib engine rewrite, strategy topology, pivot gates |
| Freeze at setup-start or at entry? | Entry (`TRADE_ACTIVE` edge) is the trade-is-alive contract | Setup phase stays live; ladder freezes only after entry fires |
| Can labels move even 1 pixel? | **NO** | Zero edits to any `label.set_*` or label init call |
| CDP for TV verify? | Unknown — will probe via `tv_health_check` | Task 4 has two branches: CDP-up path (ask to push) vs CDP-down path (manual paste) |

---

## Known Pitfalls (from feedback memory)

1. `feedback_no_speculative_causes.md` — every claim must ride on a tool-call result.
2. `feedback_pine_strategy_tv_compile_required.md` — this is a FUNCTIONAL change; TV `pine_smart_compile` is required, not just pine-facade.
3. `feedback_tv_must_always_have_cdp.md` — **NEVER call `tv_launch`**. `tv_health_check` is read-only and safe.
4. `feedback_check_tv_source_not_repo.md` — ground truth for "what's on the chart" is `pine_get_source`, not the repo.
5. `feedback_fix_all_errors_in_touched_file.md` — W4 warnings are in-scope because edits overlap the plot block only if we touch it; this plan does NOT touch plot lines, so W4 stays untouched. W9 is informational, not addressable without output removal.
6. `feedback_never_touch_indicator.md` — `v7-warbird-institutional.pine` is read-only. This plan touches ONLY the backtest-strategy variant.
7. `feedback_tv_bulk_set_inputs_breaks_gear.md` — not relevant here (no input bulk changes).
8. Pixel-perfect constraint — Kirk's exact words: "NOT ONE SINGLE PIXEL CAN BE OFF." This supersedes any stylistic preference I might have.

---

## Scope

### IN

- **Delete** 7 overlay line objects: `lineTradeEntry`, `lineActiveSl`, `lineTradeT1`, `lineTradeT2`, `lineTradeT3`, `lineTradeT4`, `lineTradeT5` (var declarations at ~[1241-1247](../../indicators/v7-warbird-institutional-backtest-strategy.pine:1241))
- **Delete** function `drawTradeProjectionLine(...)` at ~[1328-1337](../../indicators/v7-warbird-institutional-backtest-strategy.pine:1328)
- **Delete** 7 `drawTradeProjectionLine(...)` call sites at ~[1374-1380](../../indicators/v7-warbird-institutional-backtest-strategy.pine:1374)
- **Delete** `tradeProjectionLeftBar`, `tradeProjectionEntryPrice`, `tradeProjectionSlPrice`, `tradeProjectionTp1Price..Tp5Price` (7 persistent floats) and the capture/release state-machine block at ~[1279-1311](../../indicators/v7-warbird-institutional-backtest-strategy.pine:1279)
- **Delete** intermediates: `tradeProjectionReady`, `tradeProjectionStarted`, `tradeActivatedNow`, `tradeProjectionDrawLeftBar`, `tradeEntryLineColor`, `tradeEntryLineWidth`, `tradeSlVisualLevel`
- **Delete** dead `if showTradeLevels and na(_lblEntry) ... label.new(...)` block at [1400-1407](../../indicators/v7-warbird-institutional-backtest-strategy.pine:1400) — unreachable because labels are pre-initialized at [1251-1257](../../indicators/v7-warbird-institutional-backtest-strategy.pine:1251)
- **Add** 15+1 `var float snap*` + `var int snapDrawLeftBar` for the ladder snapshot: `snapPZero, snapP236, snapP382, snapPPivot, snapP618, snapP786, snapPOne, snapP1382, snapP150, snapP1786, snapPT1, snapPT2, snapPT3, snapPT4, snapPT5, snapDrawLeftBar`
- **Add** capture block: fire ONCE on `tradeState` edge `TRADE_SETUP → TRADE_ACTIVE` — i.e., `tradeState == TRADE_ACTIVE and tradeState[1] != TRADE_ACTIVE`. Capture all 15 live `p*` + current `drawLeftBar`.
- **Add** release block: fire on trade resolution edges — `tradeState` enters `TRADE_STOPPED`, `TRADE_EXPIRED`, or `TRADE_HIT_TP5`. Clear all snap values to `na`.
- **Modify** the 15 existing `drawAnchoredLine(...)` call sites at ~[1356-1371](../../indicators/v7-warbird-institutional-backtest-strategy.pine:1356) to pass `tradeFibFrozen ? snapP* : p*` as price and `tradeFibFrozen ? snapDrawLeftBar : drawLeftBar` as leftBar. Define `bool tradeFibFrozen = not na(snapPZero)` as the switch.
- **Modify** `tradeActiveVisible` remains the gate for right-side labels (unchanged behavior — labels already pixel-correct in Screenshot 3).

### OUT

- Fib engine (`fibHtfSnapshot` rewrite, `fibPivotRightRoomBars`, `fibRecentLegLookbackBars`) — stays.
- Strategy topology (`default_qty_value=1`, `margin_long=25`, `margin_short=25`, single-ticket `backtestExitTargetInput` exit ladder) — stays.
- Pivot-safety gates (`longPivotSafety`, `shortPivotSafety`) — stays.
- `alertcondition` removal — stays (by Kirk's prior scope).
- Fib-level label barstate (`barstate.islastconfirmedhistory`) — separate plan if it becomes an issue.
- W9 output-count warning — informational; not addressable without output cuts.
- `v7-warbird-institutional.pine` — **LOCKED**, not touched.
- `v7-warbird-strategy.pine` — out of scope (training file).
- No changes to `input.*` calls → **zero Optuna impact**.

---

## Rollback Plan

- Intra-task: `git diff indicators/v7-warbird-institutional-backtest-strategy.pine` to see current uncommitted delta; revert any single wrong edit with a targeted reverse-patch.
- Full rollback from this plan: `git checkout -- indicators/v7-warbird-institutional-backtest-strategy.pine` returns to the current Screenshot-1 state (pre-fix, post-prior-session).
- Nuclear rollback from the prior session's work: `git checkout HEAD -- indicators/v7-warbird-institutional-backtest-strategy.pine` drops everything and returns to commit 299f064's clean baseline. Only with Kirk's explicit call.

---

## Tasks

### Task 1 — Delete sticky overlay machinery

**Goal:** Remove every Scope-IN deletion item above in one atomic edit sequence. No new logic added in this task — pure removal.
**Files:** `indicators/v7-warbird-institutional-backtest-strategy.pine`
**Specialist tool:** `./scripts/guards/pine-lint.sh` — MUST return PASS with 2 warnings (W4, W9), 0 errors, same as baseline. Line count MUST decrease by ~40.
**Checkpoint memory entry:** `session_20260424_ladder_snapshot_task1.md` with before/after line counts, any new warnings, and confirmation that no label or draw-anchored code was touched.
**Risk:** LOW. Pure deletion.
**Rollback:** `git checkout --`.

### Task 2 — Add snapshot capture + release + threading

**Goal:** Add Scope-IN additions and modifications.
**Order within task:**
1. Add 16 `var` declarations near the existing `var line` block.
2. Add capture block on `TRADE_SETUP → TRADE_ACTIVE` edge (conceptually near where `entryPrice` gets locked in the state machine).
3. Add release block on trade-resolution edges.
4. Add `bool tradeFibFrozen = not na(snapPZero)`.
5. Modify the 15 `drawAnchoredLine(...)` call sites to use ternaries — minimum-risk change shape.
**Files:** `indicators/v7-warbird-institutional-backtest-strategy.pine`
**Specialist tool:** `./scripts/guards/pine-lint.sh` + pine-facade curl compile. Both MUST return PASS/success:True with 0 errors.
**Checkpoint memory entry:** `session_20260424_ladder_snapshot_task2.md` with the exact capture-edge logic, release-edge logic, and the ternary pattern in draw calls.
**Risk:** MEDIUM. New state-machine logic; failure modes include: missed capture (state-machine edge mis-read), premature release (stale `tradeState`), ternary truth-table error leaking live values during frozen state.
**Rollback:** revert just this task's additions; Task-1 deletions can stand standalone (would leave file with NO overlay — degrades to live-only, same as pre-prior-session).

### Task 3 — Full Pine verification pipeline

**Specialist tools (in required order):**
1. `curl https://pine-facade.tradingview.com/pine-facade/translate_light` with source body — **authoritative compiler**. MUST return `success: True, errors: 0`.
2. `./scripts/guards/pine-lint.sh indicators/v7-warbird-institutional-backtest-strategy.pine` — MUST return PASS, 0 errors.
3. `./scripts/guards/check-contamination.sh` — MUST PASS.
4. `./scripts/guards/check-indicator-strategy-parity.sh` — MUST PASS (this strategy variant must stay in parity contract with the live indicator).
5. `npm run build` — MUST return exit 0.
**Checkpoint memory entry:** `session_20260424_ladder_snapshot_task3.md` with each tool's exit code and tail output.
**Risk:** LOW — mechanical gate chain.

### Task 4 — TV chart pixel-perfect verification

**Subtask 4a — probe CDP:**
- Call `mcp__tradingview__tv_health_check` (read-only, safe per `feedback_tv_must_always_have_cdp.md`).
- Report result to Kirk.

**Subtask 4b — if CDP up:**
- ASK Kirk explicitly: "CDP up. Permission to `pine_set_source` into the backtest-strategy slot?" (never push without his session-level go-ahead).
- If approved: `pine_set_source` → `pine_smart_compile` (catches CE10244 that pine-facade misses).
- `capture_screenshot` of the 15M MES chart with a visible active trade.
- Visual diff vs Kirk's Screenshot 3 reference. Compare: label bg color + alpha, text color, font size, line width per fib family, line extend mode, zone shading, label x-offset.
- Send capture to Kirk for sign-off.

**Subtask 4c — if CDP down:**
- Report to Kirk: "CDP unavailable. `tv_health_check` failed."
- Present the updated source via repo diff for him to manually paste into Pine Editor.
- Request a fresh chart screenshot from Kirk.
- Visual diff.

**Kirk must explicitly confirm "pixel-perfect" before this task closes.** No self-certification.
**Specialist tool:** visual side-by-side with Screenshot 3.
**Checkpoint memory entry:** `session_20260424_ladder_snapshot_task4.md` with CDP state, whether push was authorized, screenshot hash, Kirk's explicit sign-off line.
**Risk:** HIGH — subjective pixel standard, non-deterministic.

---

## Progress Table

| # | Task | Status | Specialist Tool | Result |
|---|------|--------|-----------------|--------|
| 2 | Write plan doc | in_progress | Read plan doc back | |
| 3.1 | Delete overlay | pending | pine-lint.sh | |
| 3.2 | Add snapshot + thread | pending | pine-lint.sh + pine-facade | |
| 3.3 | Full verification | pending | 5-step chain | |
| 3.4 | TV pixel verification | pending | visual diff vs Screenshot 3 | |

---

## Workflow Improvements

_(populated during execution)_

- 2026-04-24: Phase 0 preflight should not be a completed TodoWrite task without a plan doc already in place to checkpoint against. Fold preflight into the first in_progress task until Phase 2 plan exists. Proposed (not self-applied) to Kirk as a /work skill refinement.
