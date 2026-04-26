# v7 Interface Reconciliation Implementation Plan

> **Historical 2026-04-26:** This plan is closed lineage. The active architecture
> is indicator-only Pine/TradingView modeling under `docs/MASTER_PLAN.md`.

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Reconcile the v7 Pine indicator/strategy surfaces and authority docs so the repository state matches the post-audit truth — no stale claims, no orphan exports, no dead stubs in strategy, guard points at v7 files.

**Architecture:** Four sequential tasks. Tasks 1–3 are Pine + docs work. Task 4 is guard modernization. Each task ends with a verification gate before the next begins. Tasks 1 and 2 require explicit session approval to touch Pine files per `AGENTS.md:162`.

**Tech Stack:** Pine Script v6, bash guard scripts, Markdown authority docs.

---

## Scope Boundary

This plan covers items from the 2026-04-12 audit that are bounded, low-risk, and unblock authority-doc truth. Deferred to later plans:
- Alert payload JSON wiring (Step 3 of audit)
- `indicator-capture` Edge Function + relay path (Step 4)
- `request.footprint()` exhaustion path (Step 5)

---

## Task 1: Strategy File — Mirror Institutional Group A+B+C Cleanup

> **Requires explicit session approval** to touch `v7-warbird-strategy.pine` before starting.

**Files:**
- Modify: `indicators/v7-warbird-strategy.pine`

The institutional file received Group A+B+C in the previous session. Strategy still carries the full intermarket stub block, dead regime vars, dead export, and stale alert text. This task mirrors exactly what was done to the institutional file.

### Step 1: Approve Pine edit

State: "Request approval to edit `v7-warbird-strategy.pine` for Group A+B+C mirror cleanup." Wait for explicit approval before proceeding.

### Step 2: Remove intermarket stubs block + stateFlip log (Group A)

In `indicators/v7-warbird-strategy.pine`, remove lines 543–572:

```
// Intermarket removed — AG handles off-chart. Neutral stubs for downstream refs.
bool useIntermarket = false
float leaderScore = 0.0
float riskScore = 0.0
float macroFxScore = 0.0
float regimeScore = 50.0
var int regime = 0
bool riskOn = false
bool riskOff = false
int eventNqState = 0
int eventRtyState = 0
int eventClState = 0
int eventHgState = 0
int eventEurState = 0
int eventJpyState = 0
int eventSkewState = 0
int alignOn = 0
int alignOff = 0
int agreementVelocity = 0
bool shockContinuation = false
bool shockFailure = false
float eventShockScore = 0.0
float eventReversalScore = 0.0
float confidenceScore = 50.0
float impulseQuality = 0.0

if enableDebugLogs and barstate.isconfirmed
    bool stateFlip = riskOn != riskOn[1] or riskOff != riskOff[1] or regime != regime[1]
    if stateFlip
        log.info(str.format("WBDBG_STATE bar={0} useIM={1} regime={2} riskOn={3} riskOff={4} score={5}", bar_index, useIntermarket, regime, riskOn, riskOff, regimeScore))
```

Replace with nothing (delete entire block).

### Step 3: Remove regimeAligned/regimeOpposed (Group A)

Remove lines 600–601:
```
bool regimeAligned = dir == 1 ? riskOn : riskOff
bool regimeOpposed = dir == 1 ? riskOff : riskOn
```

### Step 4: Remove conflictBreak / conflictEvent (Group B)

Remove line 605: `bool conflictBreak = false`
Remove line 609: `bool conflictEvent = false`

### Step 5: Remove eventModeCode + its plot (Group B)

Remove line 652: `int eventModeCode = conflictBreak ? 6 : shockFailure ? 2 : shockContinuation ? 1 : rejectConfirmed ? 3 : 0`

Remove line 925: `plot(float(eventModeCode), "ml_event_mode_code", display=display.none, editable=false)`

### Step 6: Fix WBDBG_EVENT log format string (Group A)

Current (line 754–755):
```pine
if enableDebugLogs and barstate.isconfirmed and (acceptEvent or rejectEvent or breakAgainstEvent or conflictEvent or entryLongTrigger or entryShortTrigger)
    log.info(str.format("WBDBG_EVENT bar={0} dir={1} accept={2} reject={3} breakAgainst={4}", bar_index, dir, acceptEvent, rejectEvent, breakAgainstEvent) + str.format(" conflict={0} longTrig={1} shortTrig={2} aligned={3} opposed={4}", conflictEvent, entryLongTrigger, entryShortTrigger, regimeAligned, regimeOpposed))
```

Replace with:
```pine
if enableDebugLogs and barstate.isconfirmed and (acceptEvent or rejectEvent or breakAgainstEvent or entryLongTrigger or entryShortTrigger)
    log.info(str.format("WBDBG_EVENT bar={0} dir={1} accept={2} reject={3} breakAgainst={4} longTrig={5} shortTrig={6}", bar_index, dir, acceptEvent, rejectEvent, breakAgainstEvent, entryLongTrigger, entryShortTrigger))
```

### Step 7: Fix stale alert text (Group C)

Current (line 996):
```pine
    alert("PIVOT BREAK against + Regime Opposed. Close=" + str.tostring(close), alert.freq_once_per_bar_close)
```

Replace with:
```pine
    alert("PIVOT BREAK against AutoFib direction. Close=" + str.tostring(close), alert.freq_once_per_bar_close)
```

### Step 8: Update strategy header budget comment

After removing `ml_event_mode_code`, verify plot count:
```bash
grep -c "^plot(" indicators/v7-warbird-strategy.pine
grep -c "^plotshape(" indicators/v7-warbird-strategy.pine
```

Expected: 33 plot + 1 plotshape = 34/64 (no alertcondition in strategy — uses `alert()`).
Update header comment and footer comment to match confirmed count.

### Step 9: Fix commission floor (audit Step 6)

Strategy `strategy()` declaration at line 28 currently has `commission_value=0.62`. The locked rule is `$1.00/side minimum`.

Change:
```pine
commission_value=0.62
```
To:
```pine
commission_value=1.00
```

### Step 10: Run verification pipeline

Run all four checks in order:

```bash
# 1. Compiler
cd "/Volumes/Satechi Hub/warbird-pro"
pine_code=$(cat "indicators/v7-warbird-strategy.pine")
curl -s -X POST "https://pine-facade.tradingview.com/pine-facade/translate_light?user_name=admin&v=3" \
  -H 'Referer: https://www.tradingview.com/' \
  -F "source=$pine_code" | python3 -c "
import json,sys; d=json.load(sys.stdin)
errs=d.get('result',{}).get('errors',[])
print('success:',d.get('success'),'errors:',len(errs))
[print('ERR:',e) for e in errs]
"

# 2. Lint
./scripts/guards/pine-lint.sh

# 3. Contamination
./scripts/guards/check-contamination.sh

# 4. Build
npm run build
```

Expected: all PASS, 0 errors.

### Step 11: Commit

```bash
git add indicators/v7-warbird-strategy.pine
git commit -m "Pine strategy: mirror Group A+B+C cleanup + commission floor fix

- Remove dead intermarket stubs (useIntermarket, riskOn/Off, eventNq/Rty/Cl/Hg/Eur/Jpy/SkewState,
  alignOn/Off, agreementVelocity, shockContinuation/Failure, confidenceScore, impulseQuality)
- Remove dead regime vars (regimeAligned, regimeOpposed, conflictBreak, conflictEvent)
- Remove dead export: ml_event_mode_code
- Fix WBDBG_EVENT log: remove aligned/opposed fields
- Fix alert text: remove 'Regime Opposed' reference
- Commission floor raised from 0.62 to 1.00 per locked rule ($1.00/side minimum)"
```

---

## Task 2: Modernize Parity Guard for v7

> No Pine approval needed — bash script only.

**Files:**
- Modify: `scripts/guards/check-indicator-strategy-parity.sh`

The current guard targets v6 files and checks v6-era contract patterns (`eventModeCode`, `targetEligible20pt`, `longSignal`, `shortSignal`, `canTradeBar`, `regimeBucketCode`, `sessionBucketCode`). None of these exist in v7. It will always fail (missing files) or check the wrong things.

The v7 guard should:
1. Point to v7 files
2. Check budget caps (< 64 outputs each)
3. Check that shared `ml_*` fields are not orphaned (no field in strategy-only or indicator-only)
4. Check v7 strategy execution primitives exist
5. NOT check trigger parity (institutional uses `acceptEvent`, strategy uses `candidateSetup` — intentional divergence documented in Task 4)

### Step 1: Rewrite the guard

Replace entire file content with:

```bash
#!/bin/bash
# Parity guard for v7 warbird indicator and strategy Pine surfaces.
# Checks: file existence, budget cap, shared ml_* field consistency, strategy primitives.
# NOTE: trigger semantics intentionally diverge (institutional=acceptEvent, strategy=candidateSetup).
# Guard does NOT enforce trigger parity — only shared export field parity.

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
INDICATOR_FILE="$ROOT_DIR/indicators/v7-warbird-institutional.pine"
STRATEGY_FILE="$ROOT_DIR/indicators/v7-warbird-strategy.pine"

echo "=== Warbird v7 Indicator/Strategy Parity Check ==="

if [[ ! -f "$INDICATOR_FILE" ]]; then
    echo "FAIL: Missing indicator file: $INDICATOR_FILE"
    exit 1
fi

if [[ ! -f "$STRATEGY_FILE" ]]; then
    echo "FAIL: Missing strategy file: $STRATEGY_FILE"
    exit 1
fi

TMP_DIR="$ROOT_DIR/.tmp/parity"
mkdir -p "$TMP_DIR"

# Count all output-consuming calls (plot, plotshape, plotchar, plotarrow, alertcondition)
count_outputs() {
    local f="$1"
    local plots plotshapes alerts
    plots=$(grep -c '^plot(' "$f" 2>/dev/null || echo 0)
    plotshapes=$(grep -c '^plotshape(' "$f" 2>/dev/null || echo 0)
    alerts=$(grep -c '^alertcondition(' "$f" 2>/dev/null || echo 0)
    echo $(( plots + plotshapes + alerts ))
}

INDICATOR_OUTPUTS=$(count_outputs "$INDICATOR_FILE")
STRATEGY_OUTPUTS=$(count_outputs "$STRATEGY_FILE")
echo "INFO: Output budget -> indicator=${INDICATOR_OUTPUTS}/64, strategy=${STRATEGY_OUTPUTS}/64"

if [[ "$INDICATOR_OUTPUTS" -gt 64 ]]; then
    echo "FAIL: Indicator exceeds 64-output cap (${INDICATOR_OUTPUTS})"
    exit 1
fi

if [[ "$STRATEGY_OUTPUTS" -gt 64 ]]; then
    echo "FAIL: Strategy exceeds 64-output cap (${STRATEGY_OUTPUTS})"
    exit 1
fi

# Extract shared ml_* export field names from hidden plots
extract_ml_fields() {
    local f="$1" out="$2"
    grep -oE '"ml_[^"]+"' "$f" | tr -d '"' | sort -u > "$out"
}

extract_ml_fields "$INDICATOR_FILE" "$TMP_DIR/ml_indicator.txt"
extract_ml_fields "$STRATEGY_FILE" "$TMP_DIR/ml_strategy.txt"

# Shared fields must match (orphan ml_ exports on either side are a contract break)
if ! diff -u "$TMP_DIR/ml_indicator.txt" "$TMP_DIR/ml_strategy.txt" > "$TMP_DIR/ml_diff.txt"; then
    echo "FAIL: ml_* export field mismatch between indicator and strategy"
    sed -n '1,120p' "$TMP_DIR/ml_diff.txt"
    exit 1
fi

ML_COUNT=$(wc -l < "$TMP_DIR/ml_indicator.txt" | tr -d '[:space:]')
echo "INFO: Shared ml_* fields: ${ML_COUNT} (no drift)"

# Verify v7 strategy execution primitives exist
for required in \
    'strategy\.entry\("Long", strategy\.long\)' \
    'strategy\.entry\("Short", strategy\.short\)' \
    'strategy\.exit\("Long Exit"' \
    'strategy\.exit\("Short Exit"' \
    '^bool candidateSetup =' \
    '^bool priceAtFibLevel ='
do
    if ! grep -qE "$required" "$STRATEGY_FILE"; then
        echo "FAIL: Strategy v7 primitive missing: $required"
        exit 1
    fi
done
echo "INFO: v7 strategy execution primitives present"

# Verify shared structural patterns exist in both files
for required in \
    '^int stopFamilyCode =' \
    '^int eventPivotInteractionCode =' \
    '^int setupArchetypeCode ='
do
    if ! grep -qE "$required" "$INDICATOR_FILE"; then
        echo "FAIL: Indicator missing shared structural pattern: $required"
        exit 1
    fi
    if ! grep -qE "$required" "$STRATEGY_FILE"; then
        echo "FAIL: Strategy missing shared structural pattern: $required"
        exit 1
    fi
done
echo "INFO: Shared structural patterns present in both files"

echo "PASS: v7 indicator/strategy parity checks passed."
echo "=== Check Complete ==="
```

### Step 2: Run the guard to verify it passes

```bash
chmod +x scripts/guards/check-indicator-strategy-parity.sh
./scripts/guards/check-indicator-strategy-parity.sh
```

Expected output:
```
=== Warbird v7 Indicator/Strategy Parity Check ===
INFO: Output budget -> indicator=37/64, strategy=34/64
INFO: Shared ml_* fields: N (no drift)
INFO: v7 strategy execution primitives present
INFO: Shared shared structural patterns present in both files
PASS: v7 indicator/strategy parity checks passed.
=== Check Complete ===
```

If `ml_* field mismatch` is reported here, it means Task 1 (strategy cleanup) was not yet committed. Ensure Task 1 is complete before running this guard.

### Step 3: Commit

```bash
git add scripts/guards/check-indicator-strategy-parity.sh
git commit -m "Guard: modernize check-indicator-strategy-parity.sh for v7

Repoints from v6-warbird-complete files to v7 files.
Removes v6-era contract checks (eventModeCode, targetEligible20pt, longSignal,
shortSignal, canTradeBar, regimeBucketCode, sessionBucketCode).
Adds v7 checks: budget caps, shared ml_* field parity (no orphans),
v7 strategy primitives (candidateSetup, priceAtFibLevel, Long/Short Exit).
Documents intentional trigger-path divergence in guard header comment."
```

---

## Task 3: Authority Doc Reconciliation

> No Pine approval needed — Markdown only.

**Files:**
- Modify: `CLAUDE.md`
- Modify: `AGENTS.md`
- Modify: `WARBIRD_MODEL_SPEC.md`
- Modify: `docs/MASTER_PLAN.md`

### Step 1: Fix CLAUDE.md

Make these targeted edits (exact line numbers will shift after Task 1–2 commits; use grep to locate):

| Find | Replace |
|------|---------|
| `Phase 0 … not yet landed because … still untracked in git. Active execution remains blocked before Phase 1 kickoff until authority docs are landed.` (line ~22) | `Phases 0–3 are complete and landed. Phase 4 (Python Pipeline) is the current execution front.` |
| `Phase 1: Local Warehouse Creation — …` (no marker, line ~26) | append `— COMPLETE 2026-04-11` |
| `Phase 2: One-Time Bootstrap from \`rabid_raccoon\` — …` (line ~27) | append `— COMPLETE 2026-04-11` |
| `Phase 3: Canonical AG Schema — …` (line ~28) | append `— COMPLETE 2026-04-11` |
| `Three canonical local AG tables and one canonical training view … not yet created (Phase 3)` (line ~62) | `~~Three canonical local AG tables…~~ **DONE 2026-04-11** — migration 007. 3 tables + view live.` |
| `Current v7 budget: 35/64 (29 headroom)` (line ~112) | `Current v7 budget: 37/64 (27 headroom)` |
| `Output budget: 38/64` (line ~41, inside "What Works") | `Output budget: 37/64 (33 plot + 1 plotshape + 3 alertcondition, 27 headroom)` |

### Step 2: Fix AGENTS.md

Locate the Pine budget baselines block (around line 165–167):
```
    Plot budget:    35 / 64
    Request budget:  4 / 40
```
Change to:
```
    Plot budget:    37 / 64   (33 plot + 1 plotshape + 3 alertcondition; strategy: 34/64)
    Request budget:  4 / 40
```

### Step 3: Fix WARBIRD_MODEL_SPEC.md

Locate line ~532:
```
**Current v7 budget: 32 plot + 3 alertcondition = 35/64 (29 headroom).** Any change that exceeds `64` is invalid.
```
Replace with:
```
**Current v7 budget: 33 plot + 1 plotshape + 3 alertcondition = 37/64 (27 headroom).** Any change that exceeds `64` is invalid.
```

### Step 4: Fix docs/MASTER_PLAN.md

Locate and fix these stale passages:

**Lines ~40–44 (2026-04-10 session block):**
Find: passage claiming `ag_local_training_schema.md` is untracked and warbird/migrations/schema missing.
Replace or annotate with: `Resolved at commit 92ea751 (Phase 0) and 2026-04-11 session (Phases 1–3).`

**Line ~59:**
Find: `Phase 0 completion remains blocked until docs/contracts/ag_local_training_schema.md is staged in git.`
Replace with: `Phase 0 complete — ag_local_training_schema.md landed at commit 92ea751.`

**Line ~100:**
Find: `Output budget:   38 / 64   (34 plot + 1 plotshape + 3 alertcondition, 26 headroom)`
Replace with: `Output budget:   37 / 64   (33 plot + 1 plotshape + 3 alertcondition, 27 headroom)`

**Line ~104:**
Find: `Header comment in the Pine file is stale (says 63/64, 11/40). Do not use header as authority.`
Replace with: `Header comment corrected at commit 7f49194 and now matches this audit.`

**Phase 3 heading (~line 241):**
Find: `## Phase 3: Canonical AG Schema`
Replace with: `## Phase 3: Canonical AG Schema — COMPLETE 2026-04-11`

Add verified block after Phase 3 requirements list:
```markdown
**Verified 2026-04-11:** Migration `007_ag_schema.sql` applied. Tables `ag_fib_snapshots`, `ag_fib_interactions`, `ag_fib_outcomes` and view `ag_training` live in `warbird`. Censored filter (`WHERE outcome_label != 'CENSORED'`) present.
```

### Step 5: Verify no stale phrases remain

```bash
cd "/Volumes/Satechi Hub/warbird-pro"

# These should return 0 matches after edits:
grep -n "not yet landed" CLAUDE.md && echo "FAIL: stale phrase found" || echo "PASS"
grep -n "blocked before Phase 1" CLAUDE.md && echo "FAIL: stale phrase found" || echo "PASS"
grep -n "remains blocked" docs/MASTER_PLAN.md && echo "FAIL: stale phrase found" || echo "PASS"
grep -rn "35/64\|35 / 64" CLAUDE.md AGENTS.md WARBIRD_MODEL_SPEC.md docs/MASTER_PLAN.md && echo "FAIL: stale budget" || echo "PASS"
grep -n "38/64" CLAUDE.md docs/MASTER_PLAN.md && echo "FAIL: stale budget" || echo "PASS"
grep -n "not yet created (Phase 3)" CLAUDE.md && echo "FAIL: stale phase status" || echo "PASS"
```

All should print PASS.

### Step 6: Commit

```bash
git add CLAUDE.md AGENTS.md WARBIRD_MODEL_SPEC.md docs/MASTER_PLAN.md
git commit -m "Docs: reconcile authority files to post-audit truth

Phases 0–3 marked complete. Pine budget corrected to 37/64 across all
authority files (CLAUDE.md, AGENTS.md, WARBIRD_MODEL_SPEC.md, MASTER_PLAN.md).
Stale 'Phase 0 blocked' and 'AG tables not created' claims removed.
Phase 3 heading and MASTER_PLAN audit block updated to reflect verified state."
```

---

## Task 4: Document Interface Divergence Contract

> No Pine approval needed — Markdown only.

**Files:**
- Modify: `docs/contracts/README.md` (or create `docs/contracts/v7-interface-contract.md`)

The audit flags that institutional and strategy use different trigger paths — this is intentional but undocumented. A one-page note prevents future confusion.

### Step 1: Check if docs/contracts/README.md is the right place

```bash
head -20 "/Volumes/Satechi Hub/warbird-pro/docs/contracts/README.md"
```

If it's an index/overview file, add a section there. If it's dense with schema detail, create `docs/contracts/v7-interface-contract.md`.

### Step 2: Add the divergence note

Add or create with this content:

```markdown
## v7 Pine Interface: Intentional Trigger Divergence

**Institutional (`v7-warbird-institutional.pine`)** — live chart surface
- Trigger: `acceptEvent` path (zone break → retest → close back through zone)
- Purpose: human-readable signal overlay, alert broadcast, live entry cue
- Output: 37/64 (33 plot + 1 plotshape + 3 alertcondition)

**Strategy (`v7-warbird-strategy.pine`)** — AG training data generator
- Trigger: `candidateSetup` path (`priceAtFibLevel` — any close within 15% ATR of 6 fib levels)
- Purpose: emit every structurally valid 15m candidate; AG labels the outcome
- Output: 34/64 (33 plot + 1 plotshape); uses `alert()` not `alertcondition()`
- Exit: SL or TP5 only — no scaled exits; AG reads `highestTargetHit` for outcome label

**Shared contract (must stay in sync):**
- All `ml_*` hidden export field names must match between both files
- `stopFamilyCode`, `eventPivotInteractionCode`, `setupArchetypeCode` patterns identical
- Verified by `scripts/guards/check-indicator-strategy-parity.sh`

**Intentionally NOT enforced by guard:**
- Entry trigger semantics (acceptEvent vs. candidateSetup)
- Exit mechanics (alert-based vs. SL/TP5 only)
- alertcondition presence (institutional has 3, strategy has 0)
```

### Step 3: Commit

```bash
git add docs/contracts/
git commit -m "Docs: add v7 interface divergence contract note

Documents intentional trigger-path split between institutional (acceptEvent)
and strategy (candidateSetup). Clarifies what the parity guard enforces vs.
what is explicitly excluded."
```

---

## Verification Checklist (end state)

After all four tasks are committed:

```bash
cd "/Volumes/Satechi Hub/warbird-pro"

# 1. Pine compiles clean
pine_code=$(cat "indicators/v7-warbird-institutional.pine")
curl -s -X POST "https://pine-facade.tradingview.com/pine-facade/translate_light?user_name=admin&v=3" \
  -H 'Referer: https://www.tradingview.com/' -F "source=$pine_code" | \
  python3 -c "import json,sys; d=json.load(sys.stdin); print('INST:', d.get('success'), len(d.get('result',{}).get('errors',[])),'errors')"

pine_code=$(cat "indicators/v7-warbird-strategy.pine")
curl -s -X POST "https://pine-facade.tradingview.com/pine-facade/translate_light?user_name=admin&v=3" \
  -H 'Referer: https://www.tradingview.com/' -F "source=$pine_code" | \
  python3 -c "import json,sys; d=json.load(sys.stdin); print('STRAT:', d.get('success'), len(d.get('result',{}).get('errors',[])),'errors')"

# 2. Lint both
./scripts/guards/pine-lint.sh

# 3. Parity guard (v7)
./scripts/guards/check-indicator-strategy-parity.sh

# 4. Build
npm run build 2>&1 | grep -E "Compiled|error" | head -5

# 5. Git log
git log --oneline -5
```

Expected: no errors, parity guard PASS, 4 new commits visible.

---

## Deferred (Out of Scope This Plan)

| Audit Step | Work | Gate |
|-----------|------|------|
| Step 3 | Alert payload JSON wiring (`alert()` contract) | Requires `signal_event_payload.md` spec review |
| Step 4 | `indicator-capture` Edge Function + relay + nightly sync | Phase 4 / new plan |
| Step 5 | `request.footprint()` exhaustion path | Requires Phase 0.5 budget gate + approval |
