# Phase 7: Warbird Trading Schema Audit — Complete Findings

**Date:** 2026-03-27
**Author:** Agent (per Kirk's Phase 7 instructions in `2026-03-27-data-gaps-and-schema-rebuild.md`)
**Status:** RESEARCH COMPLETE — awaiting Kirk's review
**Scope:** Research-only audit. No code changes made.

---

## Executive Summary

The schema is **not lost**. The pipeline code is **complete and correct**. The tables are empty because **the scheduling pipeline is broken** — detect-setups lost its cron schedule during the Vercel → Supabase Edge cutover and was never re-wired.

---

## 1. Schema Evolution (What Happened)

### Migration 007 (2026-03-15): Original Touch/Hook/Go
- `warbird_setups` with `setup_phase` enum (TOUCHED, HOOKED, GO_FIRED, EXPIRED, STOPPED, TP1_HIT, TP2_HIT)
- `trade_scores` with predicted-price / MAE / MFE columns
- `measured_moves`, `forecasts`, `vol_states`, `models`

### Migration 010 (2026-03-16): Warbird v1 canonical cutover
- Dropped original Touch/Hook/Go `warbird_setups` and `forecasts`
- Rebuilt 8-table layered model with FK chain:
  `warbird_forecasts_1h` → `warbird_triggers_15m` → `warbird_conviction` → `warbird_setups` → `warbird_setup_events` + `warbird_risk`
- All execution tables required `forecast_id` NOT NULL FK to `warbird_forecasts_1h`

### Migration 018 (2026-03-26): 15m canonical cutover — THE KEY MIGRATION
- Backed up all warbird tables to `*_legacy_20260326` copies
- Dropped and recreated ALL execution tables **WITHOUT** the `forecast_id` dependency
- Key schema changes:
  - Removed `warbird_forecasts_1h` entirely (table still exists as backup only)
  - Replaced `ts` with `bar_close_ts` as the primary temporal key
  - Added `timeframe` column (default `M15`)
  - Changed unique constraints to `(symbol_code, timeframe, bar_close_ts)`
  - Dropped runner-related columns from setups
  - Added `tp1_probability`, `tp2_probability`, `reversal_risk`, `confidence_score` to warbird_risk
- Migrated legacy rows into the new schema structure

### Migration 012 (2026-03-18): measured_moves setup link
- Added nullable `setup_id` FK from `measured_moves` → `warbird_setups`

---

## 2. Route Code Audit

### `detect-setups/route.ts` — COMPLETE 5-LAYER PIPELINE

This is the canonical pipeline. It does everything the plan describes:

| Layer | Function | Reads | Writes |
|---|---|---|---|
| 1. Daily bias | `buildDailyBiasLayer()` | `mes_1d` (240 bars) | `warbird_daily_bias` |
| 2. 4H structure | `buildStructure4H()` | `mes_4h` (120 bars) | `warbird_structure_4h` |
| 3. 15m fib geometry | `buildFibGeometry()` | `mes_15m` (120 bars) | computed in-memory |
| 4. Conviction | `evaluateConviction()` | layers 1-3 output | `warbird_conviction` |
| 5. Trigger | `evaluateTrigger()` | `mes_1m` (60 bars) + geometry | `warbird_triggers_15m` |
| Risk | computed inline | `geopolitical_risk_1d`, `econ_vol_1d`, `trump_effect_1d` | `warbird_risk` |
| Setup | conditional | all above | `warbird_setups` (only if trigger=GO AND conviction≠NO_TRADE) |
| Events | conditional | setup output | `warbird_setup_events` (TRIGGERED event) |
| Measured moves | conditional | geometry output | `measured_moves` (if geometry has AB=CD pattern) |

**Gate conditions for setup creation:**
1. Market must be open (or `?force=1`)
2. ≥20 daily bars, ≥20 4H bars, ≥55 15m bars
3. 15m and 1m bar continuity (no weekend gaps)
4. Fib geometry must fire (returns null if no confluence anchor found)
5. Trigger decision = `GO`
6. Conviction level ≠ `NO_TRADE`

**Status:** Code is complete and matches the current schema (migration 018). NOT running because no cron schedule exists.

### `measured-moves/route.ts` — RETIRED

Explicitly retired with comment: "detect-setups is the canonical measured_moves writer." Always returns SKIPPED.

### `score-trades/route.ts` — MONITORING PIPELINE (ORPHANED)

Monitors active setups and resolves outcomes:
- Reads `warbird_setups` WHERE status IN ('ACTIVE', 'TP1_HIT')
- Reads latest price from `mes_1m`
- For each setup, checks stop/TP1/TP2/expiry conditions
- Updates `warbird_setups.status`, writes `warbird_setup_events`, syncs `measured_moves.status`

**Critical correction to plan docs:** This route does NOT write to `trade_scores`. It updates `warbird_setups` and `warbird_setup_events` directly. The active plan (line 2891) incorrectly says it writes to `trade_scores`.

**Status:** Code is complete. Explicitly STOPPED (removed from cron schedules per 2026-03-26 update). Has nothing to monitor because detect-setups never creates setups.

---

## 3. Library Code Audit

| File | Purpose | Used By | Status |
|---|---|---|---|
| `scripts/warbird/fib-engine.ts` | Canonical 15m fib geometry engine | `detect-setups`, `build-warbird-dataset` | ACTIVE, WORKS |
| `scripts/warbird/daily-layer.ts` | Daily bias from 200d MA | `detect-setups`, `build-warbird-dataset` | ACTIVE, EXISTS |
| `scripts/warbird/structure-4h.ts` | 4H market structure analysis | `detect-setups` | ACTIVE, EXISTS |
| `scripts/warbird/trigger-15m.ts` | 1m microstructure trigger evaluation | `detect-setups` | ACTIVE, EXISTS |
| `scripts/warbird/conviction-matrix.ts` | Multi-timeframe bias alignment scoring | `detect-setups` | ACTIVE, EXISTS |
| `lib/setup-engine.ts` | Original Touch/Hook/Go state machine | **NOTHING** — orphaned | DEAD CODE from migration 007 era |
| `lib/measured-move.ts` | AB=CD measured move detection | `fib-engine.ts` | ACTIVE, WORKS |
| `lib/setup-candidates.ts` | Maps warbird_setups rows to chart display | Chart API consumers | ACTIVE, WORKS |
| `lib/warbird/projection.ts` | Composes WarbirdSignal from all tables | Dashboard API | ACTIVE, WORKS |
| `lib/warbird/types.ts` | TypeScript types for all warbird tables | Throughout | ACTIVE, CORRECT for migration 018 schema |
| `scripts/warbird/build-warbird-dataset.ts` | Offline CSV dataset builder for AG training | Manual script only | ACTIVE, WORKS |

---

## 4. Table Status

| Table | Schema Source | Current Rows | Writer | Status |
|---|---|---|---|---|
| `warbird_daily_bias` | Migration 018 | 4 | `detect-setups` | CORRECT, starved (no cron) |
| `warbird_structure_4h` | Migration 018 | 12 | `detect-setups` | CORRECT, starved (no cron) |
| `warbird_triggers_15m` | Migration 018 | 0 | `detect-setups` | CORRECT, starved (no cron) |
| `warbird_conviction` | Migration 018 | 0 | `detect-setups` | CORRECT, starved (no cron) |
| `warbird_setups` | Migration 018 | 0 | `detect-setups` | CORRECT, starved (no cron + gate conditions) |
| `warbird_setup_events` | Migration 018 | 0 | `detect-setups` + `score-trades` | CORRECT, starved |
| `warbird_risk` | Migration 018 | 0 | `detect-setups` | CORRECT, starved (no cron) |
| `measured_moves` | Migration 007 + 012 | 76 | `detect-setups` | CORRECT, 76 legacy rows from pre-018 |
| `trade_scores` | Migration 007 | 0 | **NOTHING** — no active writer | ZOMBIE — superseded by warbird_setups outcome tracking |
| `models` | Migration 007 | 0 | **NOTHING** — no active writer | ZOMBIE — superseded by future packet lifecycle tables |
| `warbird_forecasts_1h` | Migration 010 (DROPPED by 018) | N/A | **DROPPED** | LEGACY — correctly removed |

---

## 5. What's "Lost" — The Real Problem

The schema was never lost. What happened:

1. **Vercel→Supabase cron cutover** (2026-03-26) removed all Vercel cron schedules
2. `detect-setups` was scheduled at `*/5 12-21 * * 1-5` as a Vercel cron
3. No Supabase Edge Function or pg_cron schedule was created to replace it
4. With detect-setups not running, no triggers/conviction/setups/events are created
5. With no setups, score-trades has nothing to monitor (and was also stopped)
6. The `build-warbird-dataset.ts` script generates training data but doesn't write to warbird tables (it computes everything fresh from mes_15m and outputs CSV)

**The 4-row warbird_daily_bias and 12-row warbird_structure_4h** are leftovers from the last few times detect-setups ran before the cron was removed.

---

## 6. Gap Analysis: Current State vs Required Pipeline

### Pipeline Step 1: Detect setups → warbird tables
| Requirement | Current State |
|---|---|
| Route code | EXISTS — `detect-setups/route.ts` is complete |
| Supabase Edge Function | MISSING |
| pg_cron schedule | MISSING |
| Historical backfill | MISSING — no way to populate from historical 15m data |

### Pipeline Step 2: Score outcomes → update setups
| Requirement | Current State |
|---|---|
| Route code | EXISTS — `score-trades/route.ts` is complete |
| Supabase Edge Function | MISSING |
| pg_cron schedule | REMOVED (was stopped 2026-03-26) |

### Pipeline Step 3: Training dataset → CSV for AG
| Requirement | Current State |
|---|---|
| Script | EXISTS — `build-warbird-dataset.ts` works |
| Depends on | `mes_15m`, `mes_1d`, `cross_asset_1h`, `econ_calendar`, `news_signals`, `geopolitical_risk_1d`, `trump_effect_1d`, `warbird_setups`, 10 FRED tables |

### Dead code to clean up
| Item | Action |
|---|---|
| `lib/setup-engine.ts` | DEAD CODE — Touch/Hook/Go state machine from migration 007. Not imported by anything current. Can be deleted. |
| `trade_scores` table | ZOMBIE — no writer. Plan says DROP. |
| `models` table | ZOMBIE — no writer. Plan says superseded by packet lifecycle. |

---

## 7. Recommendations

### A. Re-enable the pipeline (immediate)

1. **Port `detect-setups` to Supabase Edge Function** following the migration 023 pattern (vault lookup → `net.http_post()` → Edge Function URL). Schedule at `*/5 14-22 * * 1-5` (every 5 min, market hours UTC) — staggered from other crons.

2. **Port `score-trades` to Supabase Edge Function**. Schedule at `*/5 14-22 * * 1-5` offset by 2 minutes from detect-setups (e.g., `2,7,12,...`).

3. After both are running and creating setups, the `build-warbird-dataset.ts` script will automatically pick up the warbird_setups data for AG training.

### B. Historical backfill (parallel work)

The build-warbird-dataset script computes fib geometry + targets per bar and outputs CSV — it does NOT write to warbird tables. Two options:

**Option 1: Offline backfill script** — Write a variant of `build-warbird-dataset.ts` that, instead of CSV output, writes to `warbird_setups`, `warbird_setup_events`, `warbird_triggers_15m`, `warbird_conviction`, and `warbird_risk` for each bar where geometry fires. This populates the tables with historical setups for AG training.

**Option 2: Let the pipeline catch up** — Just enable the cron. The pipeline creates setups going forward. For AG training, the CSV script already works without warbird table data (it computes everything from scratch). The warbird tables are more for live monitoring than training.

**Recommendation:** Option 2 for immediate unblock. The `build-warbird-dataset.ts` script IS the AG training surface and doesn't need populated warbird tables. The warbird tables are the live monitoring/dashboard surface.

### C. Schema cleanup (after pipeline is live)

1. DROP `trade_scores` — zombie, no writer
2. DROP `models` — zombie, superseded by future packet lifecycle
3. DELETE `lib/setup-engine.ts` — dead code, not imported
4. DELETE `app/api/cron/measured-moves/route.ts` — retired stub, detect-setups handles measured_moves

### D. Plan doc corrections

The active plan has stale information:
- Line 2891: Says score-trades writes to `trade_scores` — **incorrect**, it writes to `warbird_setups` + `warbird_setup_events`
- Line 3209: Says detect-setups reads/writes `warbird_forecasts_1h` — **incorrect since migration 018**, route has no forecast_id dependency

---

## 8. Pipeline Dependency Diagram

```
mes_1m (every minute via pg_cron)
  ↓ rollup
mes_15m
  ↓
detect-setups (every 5 min, market hours) [MISSING CRON]
  ├─ reads: mes_1d, mes_4h, mes_15m, mes_1m
  ├─ reads: geopolitical_risk_1d, econ_vol_1d, trump_effect_1d
  ├─ writes: warbird_daily_bias, warbird_structure_4h
  ├─ writes: warbird_triggers_15m, warbird_conviction, warbird_risk
  ├─ writes: warbird_setups (conditional: GO + not NO_TRADE)
  ├─ writes: warbird_setup_events (TRIGGERED)
  └─ writes: measured_moves (conditional: AB=CD pattern)
       ↓
score-trades (every 5 min, market hours) [STOPPED]
  ├─ reads: warbird_setups WHERE status IN (ACTIVE, TP1_HIT)
  ├─ reads: mes_1m (latest price)
  ├─ writes: warbird_setups (status update)
  ├─ writes: warbird_setup_events (TP1_HIT, TP2_HIT, STOPPED, EXPIRED)
  └─ writes: measured_moves (status sync)
       ↓
build-warbird-dataset.ts (manual, local)
  ├─ reads: mes_15m, mes_1d, cross_asset_1h, ALL econ tables
  ├─ reads: news_signals, geopolitical_risk_1d, trump_effect_1d
  ├─ reads: warbird_setups (for counter_trend frequency features)
  └─ outputs: CSV for AG training
```

---

## 9. Risk Assessment

| Risk | Severity | Mitigation |
|---|---|---|
| detect-setups gate conditions too strict → zero setups even when running | Medium | Test with `?force=1` during market hours, check job_log for skip reasons |
| fib geometry doesn't fire often enough on 15m bars | Medium | Normal — geometry requires specific confluence conditions. Monitor via job_log |
| score-trades runs before detect-setups on same interval | Low | Offset by 2 minutes |
| Edge Function porting introduces bugs | Medium | Port exact route code, test with direct invoke before enabling cron |
| Historical backfill of warbird tables is impractical | Low | Not needed for AG training (build-warbird-dataset.ts works independently) |

---

## Files Audited

- `app/api/cron/detect-setups/route.ts` (527 lines)
- `app/api/cron/measured-moves/route.ts` (65 lines)
- `app/api/cron/score-trades/route.ts` (247 lines)
- `lib/setup-engine.ts` (409 lines)
- `lib/measured-move.ts` (92 lines)
- `lib/setup-candidates.ts` (161 lines)
- `lib/warbird/projection.ts` (234 lines)
- `lib/warbird/types.ts` (225 lines)
- `scripts/warbird/fib-engine.ts` (223 lines)
- `scripts/warbird/build-warbird-dataset.ts` (791 lines)
- `supabase/migrations/20260315000007_trading.sql` (169 lines)
- `supabase/migrations/20260316000010_warbird_v1_cutover.sql` (274 lines)
- `supabase/migrations/20260318000012_measured_moves_setup_link.sql` (14 lines)
- `supabase/migrations/20260326000018_15m_canonical_cutover.sql` (544 lines)
- `supabase/migrations/20260328000028_schema_cleanup_and_normalization.sql` (306 lines)
- `docs/plans/2026-03-20-ag-teaches-pine-architecture.md` (sections 14, 17)
- Git history: 4 commits touch warbird migration files, 6 commits touch cron routes
