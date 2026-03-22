# P0 + Phase 1 Execution Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Clean the repo of contamination risks, de-duplicate legacy pipelines, commit all design artifacts, and freeze the v1 live series inventory.

**Architecture:** P0 is housekeeping — deprecate legacy scripts, add contamination safeguards, archive stale root docs. Phase 1 is verification — confirm every locked v1 live series resolves in TradingView and document gaps.

**Tech Stack:** Git, Bash, TradingView (manual verification), Supabase (existing)

**Parent docs:**
- Design: `docs/plans/2026-03-22-ag-pine-implementation-design.md`
- Active plan: `docs/plans/2026-03-20-ag-teaches-pine-architecture.md`

---

## P0: Prerequisites

### Task 1: Commit Design Doc

**Files:**
- Stage: `docs/plans/2026-03-22-ag-pine-implementation-design.md`
- Stage: `docs/plans/2026-03-22-p0-phase1-execution.md`

**Step 1: Stage and commit**

```bash
cd "/Volumes/Satechi Hub/warbird-pro"
git add docs/plans/2026-03-22-ag-pine-implementation-design.md docs/plans/2026-03-22-p0-phase1-execution.md
git commit -m "docs: add AG-Pine implementation design and P0+Phase1 execution plan"
```

Expected: Clean commit on main.

---

### Task 2: Archive WARBIRD_CANONICAL.md

**Files:**
- Move: `WARBIRD_CANONICAL.md` → `docs/plans/archive/WARBIRD_CANONICAL.md`

**Step 1: Move file**

```bash
cd "/Volumes/Satechi Hub/warbird-pro"
git mv WARBIRD_CANONICAL.md docs/plans/archive/WARBIRD_CANONICAL.md
```

**Step 2: Verify no broken references**

```bash
cd "/Volumes/Satechi Hub/warbird-pro"
grep -r "WARBIRD_CANONICAL" --include="*.ts" --include="*.tsx" --include="*.md" -l | grep -v archive | grep -v node_modules
```

Expected: Only `CLAUDE.md` and possibly `AGENTS.md` reference it. Update any references to point to the archive path.

**Step 3: Update references if found**

If `CLAUDE.md` or `AGENTS.md` reference `WARBIRD_CANONICAL.md`, update the path to `docs/plans/archive/WARBIRD_CANONICAL.md`.

**Step 4: Commit**

```bash
git add -A
git commit -m "docs: move WARBIRD_CANONICAL.md to archive"
```

---

### Task 3: Deprecate Legacy Scripts

**Files:**
- Modify: `scripts/build-dataset.py` (add deprecation header)
- Modify: `scripts/train-warbird.py` (add deprecation header)
- Modify: `scripts/predict-warbird.py` (add deprecation header)

**Step 1: Add deprecation notice to `scripts/build-dataset.py`**

Read the file first. Then prepend (after any shebang/encoding line):

```python
import sys
print("=" * 60)
print("DEPRECATED: This script is superseded by scripts/warbird/build-warbird-dataset.ts")
print("and will be replaced by scripts/ag/build-fib-dataset.py in Phase 4.")
print("Do NOT use for new work.")
print("=" * 60)
sys.exit(1)
```

**Step 2: Add deprecation notice to `scripts/train-warbird.py`**

Same pattern:

```python
import sys
print("=" * 60)
print("DEPRECATED: This script is superseded by scripts/warbird/train-warbird.py")
print("and will be replaced by scripts/ag/train-fib-model.py in Phase 4.")
print("Do NOT use for new work.")
print("=" * 60)
sys.exit(1)
```

**Step 3: Add deprecation notice to `scripts/predict-warbird.py`**

Same pattern:

```python
import sys
print("=" * 60)
print("DEPRECATED: Inference will move to scripts/ag/ in Phase 4.")
print("Do NOT use for new work.")
print("=" * 60)
sys.exit(1)
```

**Step 4: Verify no active cron or route imports these scripts**

```bash
cd "/Volumes/Satechi Hub/warbird-pro"
grep -r "build-dataset\|train-warbird\|predict-warbird" app/ lib/ --include="*.ts" --include="*.tsx" -l
```

Expected: No matches in app/ or lib/ (these are Python scripts called manually, not imported by TS).

**Step 5: Check admin UI references**

```bash
grep -n "predict-warbird\|train-warbird\|build-dataset" app/\(workspace\)/admin/page.tsx
```

If found, note the line numbers for Task 4.

**Step 6: Commit**

```bash
git add scripts/build-dataset.py scripts/train-warbird.py scripts/predict-warbird.py
git commit -m "chore: deprecate legacy root-level ML scripts with hard exit"
```

---

### Task 4: Update Admin UI Script References

**Files:**
- Modify: `app/(workspace)/admin/page.tsx` (if references found in Task 3 Step 5)

**Step 1: Read the admin page and find script references**

Look for any text referencing `predict-warbird.py`, `train-warbird.py`, or `build-dataset.py`.

**Step 2: Update text to reference canonical paths**

Replace with references to `scripts/ag/*` (Phase 4 canonical paths) with a note that these don't exist yet:

```
"scripts/ag/build-fib-dataset.py (Phase 4 — not yet built)"
"scripts/ag/train-fib-model.py (Phase 4 — not yet built)"
```

**Step 3: Commit**

```bash
git add "app/(workspace)/admin/page.tsx"
git commit -m "fix: update admin UI script references to canonical Phase 4 paths"
```

Skip this task entirely if no references were found in Task 3 Step 5.

---

### Task 5: Add Anti-Contamination Safeguards

**Files:**
- Create: `scripts/ag/.gitkeep` (placeholder for Phase 4 canonical scripts)
- Create: `scripts/guards/check-contamination.sh`

**Step 1: Create Phase 4 script directory**

```bash
cd "/Volumes/Satechi Hub/warbird-pro"
mkdir -p scripts/ag
touch scripts/ag/.gitkeep
```

**Step 2: Create contamination check script**

Create `scripts/guards/check-contamination.sh`:

```bash
#!/bin/bash
# Anti-contamination check: ensure no Rabid Raccoon data/code paths leak into training
# Run before any AG training or dataset build

set -e

echo "=== Warbird Anti-Contamination Check ==="

# Check for rabid-raccoon imports in Python scripts
HITS=$(grep -r "rabid.raccoon\|rabid_raccoon\|/rabid-raccoon/" scripts/ lib/ app/ --include="*.py" --include="*.ts" --include="*.tsx" -l 2>/dev/null | grep -v node_modules | grep -v archive || true)

if [ -n "$HITS" ]; then
    echo "FAIL: Rabid Raccoon references found in active code:"
    echo "$HITS"
    exit 1
fi

# Check for cross-project data paths
DATA_HITS=$(grep -r "/rabid-raccoon/\|rabid.raccoon" scripts/ --include="*.py" --include="*.ts" -l 2>/dev/null || true)

if [ -n "$DATA_HITS" ]; then
    echo "FAIL: Cross-project data paths found:"
    echo "$DATA_HITS"
    exit 1
fi

echo "PASS: No cross-project contamination detected."
echo "=== Check Complete ==="
```

**Step 3: Make executable**

```bash
chmod +x scripts/guards/check-contamination.sh
```

**Step 4: Run it to verify it passes**

```bash
./scripts/guards/check-contamination.sh
```

Expected: `PASS: No cross-project contamination detected.`

Note: `lib/setup-engine.ts` has a COMMENT about Rabid Raccoon (line 7) but no import. The grep pattern should match it. If it does, update the grep to exclude comment-only matches OR document it as known legacy lineage that is safe (comment only, no runtime dependency).

**Step 5: Commit**

```bash
git add scripts/ag/.gitkeep scripts/guards/check-contamination.sh
git commit -m "chore: add anti-contamination guard and Phase 4 script directory"
```

---

### Task 6: Document Known Legacy Lineage

**Files:**
- Create: `docs/decisions/legacy-lineage-audit.md`

**Step 1: Create lineage audit doc**

```markdown
# Legacy Lineage Audit

**Date:** 2026-03-22
**Status:** Documented — No Action Required Yet

## Rabid Raccoon Lineage (Safe — Comments Only)

These files contain COMMENTS referencing Rabid Raccoon but have NO runtime imports or data dependencies:

| File | Line | Content | Risk |
|------|------|---------|------|
| `lib/setup-engine.ts` | 7 | "Ported from rabid-raccoon" comment | None — comment only |
| `lib/fibonacci.ts` | 23 | Reference comment | None — comment only |
| `supabase/migrations/20260315000002_symbols.sql` | 2 | Provenance comment | None — migration already applied |
| `supabase/seed.sql` | 2 | Provenance comment | None — seed data |

## Duplicate Pipeline Paths (Deprecated)

| Legacy Path | Canonical Path | Status |
|-------------|---------------|--------|
| `scripts/build-dataset.py` | `scripts/ag/build-fib-dataset.py` (Phase 4) | Deprecated with hard exit |
| `scripts/train-warbird.py` | `scripts/ag/train-fib-model.py` (Phase 4) | Deprecated with hard exit |
| `scripts/predict-warbird.py` | `scripts/ag/` (Phase 4) | Deprecated with hard exit |

## scripts/warbird/* Status

These are the "current-ish" path from the prior architecture. They will be superseded by `scripts/ag/*` in Phase 4 but are NOT deprecated yet because they contain reference logic:

- `scripts/warbird/build-warbird-dataset.ts` — reference for dataset builder design
- `scripts/warbird/train-warbird.py` — reference for training config
- `scripts/warbird/predict-warbird.py` — reference for inference pattern
- `scripts/warbird/fib-engine.ts` — reference for fib calculation logic
- `scripts/warbird/trigger-15m.ts` — reference for 15m bar trigger logic

These stay as-is until Phase 4 builds their replacements.
```

**Step 2: Commit**

```bash
git add docs/decisions/legacy-lineage-audit.md
git commit -m "docs: add legacy lineage audit with contamination status"
```

---

### Task 7: Run Build Verification

**Step 1: Run npm build**

```bash
cd "/Volumes/Satechi Hub/warbird-pro"
npm run build
```

Expected: Build passes. If it fails, fix only build-breaking issues introduced by P0 changes.

**Step 2: Verify clean git state**

```bash
git status -sb
```

Expected: `## main...origin/main` with no uncommitted changes.

**Step 3: Push**

```bash
git push origin main
```

---

## Phase 1: Series Inventory Freeze

### Task 8: Verify request.security() Series in TradingView

**Files:**
- Create: `docs/decisions/series-inventory-freeze.md`

This task requires MANUAL verification in TradingView. The agent cannot do this automatically.

**Step 1: Document the locked v1 series list**

From the active plan, these are the locked v1 `request.security()` targets:

| Symbol | TradingView Ticker | Purpose |
|--------|-------------------|---------|
| MES | `CME_MINI:MES1!` | Primary instrument (chart) |
| NQ | `CME_MINI:NQ1!` | Intermarket — tech correlation |
| BANK | `NASDAQ:BANK` | Intermarket — financials |
| VIX | `CBOE:VIX` | Volatility regime |
| DXY | `TVC:DXY` | Dollar strength |
| US10Y | `TVC:US10Y` | Yield/rates |
| HYG | `AMEX:HYG` | Credit risk (high yield) |
| LQD | `AMEX:LQD` | Credit risk (investment grade) |

**Step 2: Manual TradingView check**

For each ticker above:
1. Open TradingView
2. Search for the exact ticker
3. Confirm it resolves to the correct instrument
4. Confirm 15m data is available
5. Note any issues (e.g., delayed data, missing history)

**Step 3: Document results in `docs/decisions/series-inventory-freeze.md`**

```markdown
# Series Inventory Freeze — v1

**Date:** 2026-03-22
**Status:** [FROZEN / PENDING VERIFICATION]

## request.security() Series (8 calls)

| Symbol | TV Ticker | Verified | 15m Data | Notes |
|--------|-----------|----------|----------|-------|
| NQ | `CME_MINI:NQ1!` | [ ] | [ ] | |
| BANK | `NASDAQ:BANK` | [ ] | [ ] | |
| VIX | `CBOE:VIX` | [ ] | [ ] | |
| DXY | `TVC:DXY` | [ ] | [ ] | |
| US10Y | `TVC:US10Y` | [ ] | [ ] | |
| HYG | `AMEX:HYG` | [ ] | [ ] | |
| LQD | `AMEX:LQD` | [ ] | [ ] | |

## request.economic() Series (4 calls — pending Pine verification)

| Series | TV Code | Purpose | Verified |
|--------|---------|---------|----------|
| Fed Funds | `request.economic("US", "IRSTCB01")` | Interest rates | [ ] |
| CPI YoY | `request.economic("US", "CPALTT01")` | Inflation | [ ] |
| Unemployment | `request.economic("US", "LRHUTTTTUSM156S")` | Labor | [ ] |
| PMI Mfg | `request.economic("US", "BSCICP02")` | Activity | [ ] |

## Budget

- Planned: 11 unique request.*() calls (7 security + 4 economic)
- TV limit: 40 (64 on Ultimate)
- Reserve: 29 calls for future expansion

## Excluded from v1 (unless reopened by decision)

- RTY1!, YM1!, crude, gold, VVIX, JNK, GDP growth
```

**Step 4: Verify request.economic() codes**

This requires a Pine Script test. Create a minimal test indicator:

```pinescript
//@version=6
indicator("Series Verification Test", overlay=false)

fed = request.economic("US", "IRSTCB01")
cpi = request.economic("US", "CPALTT01")
unemp = request.economic("US", "LRHUTTTTUSM156S")
pmi = request.economic("US", "BSCICP02")

plot(fed, "Fed Funds")
plot(cpi, "CPI YoY")
plot(unemp, "Unemployment")
plot(pmi, "PMI Mfg")
```

Load this on any chart in TradingView. Verify all 4 plots render with real data.

**Step 5: Update freeze doc with results and commit**

After manual verification, fill in the checkboxes and notes.

```bash
git add docs/decisions/series-inventory-freeze.md
git commit -m "docs: add series inventory freeze with verification status"
```

---

### Task 9: Final P0 + Phase 1 Verification

**Step 1: Run contamination check**

```bash
./scripts/guards/check-contamination.sh
```

Expected: PASS

**Step 2: Run build**

```bash
npm run build
```

Expected: PASS

**Step 3: Verify all P0 + Phase 1 commits are clean**

```bash
git log --oneline -10
```

Expected: 5-7 new commits from this plan.

**Step 4: Push everything**

```bash
git push origin main
```

**Step 5: Verify clean state**

```bash
git status -sb
```

Expected: `## main...origin/main` — clean.

---

## Gate: P0 + Phase 1 Complete

**Checklist before proceeding to Phase 2:**

- [ ] Design doc committed and pushed
- [ ] WARBIRD_CANONICAL.md archived
- [ ] Legacy scripts deprecated with hard exit
- [ ] Anti-contamination guard script passes
- [ ] Admin UI references updated (if applicable)
- [ ] Legacy lineage audit documented
- [ ] Series inventory verified in TradingView (manual)
- [ ] request.economic() codes verified in Pine (manual)
- [ ] npm run build passes
- [ ] All changes pushed to main

**Next:** Phase 2 (Refactor Current Script) requires a separate execution plan focused on Pine Script work. Use `writing-plans` to create `2026-03-22-phase2-pine-refactor.md`.
