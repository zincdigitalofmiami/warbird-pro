# Warbird Plan Logic Audit (Deep)
**Date:** 2026-03-18  
**Scope:** Canonical plan logic + current implementation compatibility  
**Method:** Two-pass reasoning (fit check, then adversarial risk check)

---

## 1) Audit Inputs

- Canonical simplification handoff: `docs/plans/2026-03-17-warbird-simplification-handoff.md`
- Canonical spec: `WARBIRD_CANONICAL.md`
- Runtime wiring: `app/api/cron/*`, `app/api/warbird/*`, `components/charts/*`
- Schema/migrations: `supabase/migrations/*`
- Model/data scripts: `scripts/warbird/*`

---

## 2) Pass 1 — Direct Compatibility Check

### Critical incompatibilities (must fix first)

1. **`mes_1s` continuity layer is required in plan, but absent in schema and ingestion**
   - Plan requirement: `1s -> 1m -> 15m` continuity
   - Evidence:
     - `docs/plans/2026-03-17-warbird-simplification-handoff.md:95-105`
     - `docs/plans/2026-03-17-warbird-simplification-handoff.md:199-201`
     - `supabase/migrations/20260315000003_mes_data.sql:1-65` (no `mes_1s`)
     - `app/api/cron/mes-catchup/route.ts:11-20` (only `1m/15m/1h/4h/1d`)
     - `lib/ingestion/databento.ts:1-4, 47-51` (default schema `ohlcv-1m`)
   - Risk: feed-integrity objective is declared but not implementable as written.

2. **15m-primary logic is declared, but setup engine remains 1H-primary fallback**
   - Plan requirement: 15m is primary geometry/model timeframe
   - Evidence:
     - `docs/plans/2026-03-17-warbird-simplification-handoff.md:97-104`
     - `docs/plans/2026-03-17-warbird-simplification-handoff.md:112-131`
     - `app/api/cron/detect-setups/route.ts:129-156` (1H forecast + 1H geometry, 15m optional fallback)
     - `scripts/warbird/fib-engine.ts:2-5` ("Canonical 1H Fib Geometry")
     - `scripts/warbird/trigger-15m.ts:11-20, 71-72` (1H geometry as trigger anchor)
   - Risk: execution behavior can diverge from the stated 15m-primary system.

3. **Model-score columns required by plan are not first-class in forecast schema/API**
   - Plan requirement: add score columns and use them as primary live outputs
   - Evidence:
     - `docs/plans/2026-03-17-warbird-simplification-handoff.md:118-125`
     - `docs/plans/2026-03-17-warbird-simplification-handoff.md:247-249`
     - `supabase/migrations/20260316000010_warbird_v1_cutover.sql:97-116` (no explicit prob/score columns)
     - `scripts/warbird/predict-warbird.py:183-217` (probabilities only in `feature_snapshot`, not dedicated columns)
     - `lib/warbird/projection.ts:46-55` (API projects target/MAE/MFE/confidence, not path probabilities/setup_score)
   - Risk: downstream consumers and admin cannot reliably depend on typed probability fields.

4. **Production inference path is not wired; cron only performs health check**
   - Plan direction: system should run from production wiring, not ad-hoc local dependency
   - Evidence:
     - `app/api/cron/forecast/route.ts:7-9, 28-36` (staleness check only)
     - `scripts/warbird/predict-warbird.py:252-260` (forecast writes happen from local script execution)
     - `rg` result: only writer is `scripts/warbird/predict-warbird.py`
   - Risk: signal freshness depends on manual/local execution, not deterministic hosted pipeline.

5. **Runner logic still exists in live scoring path, conflicting with simplified direction**
   - Plan/canonical direction: sidecar out, simplification, no runner in v1
   - Evidence:
     - `docs/plans/2026-03-17-warbird-simplification-handoff.md:128-131, 282-284`
     - `WARBIRD_CANONICAL.md:136, 144`
     - `app/api/cron/score-trades/route.ts:131-157, 174-238` (RUNNER_* and PULLBACK_REVERSAL branches active)
     - `supabase/migrations/20260316000010_warbird_v1_cutover.sql:48-68` (runner-centric statuses/events present)
   - Risk: live outcomes and status semantics drift from intended simplified model.

6. **Training dataset builder is 1H-centric and synthetic-forward-labeled, not 15m-primary lifecycle-grounded**
   - Plan requirement: 15m-primary geometry scoring with robust labels
   - Evidence:
     - `docs/plans/2026-03-17-warbird-simplification-handoff.md:97-104, 167-173`
     - `scripts/warbird/build-warbird-dataset.ts:343-347, 365-393` (base series = `mes_1h`)
     - `scripts/warbird/build-warbird-dataset.ts:579-596` (geometry/targets from 1H bars)
     - `scripts/warbird/build-warbird-dataset.ts:587-596` (forward-scan target construction)
   - Risk: model learns a different regime than declared runtime methodology.

### High incompatibilities

7. **`warbird_forecasts_1h` training config diverges from canonical training contract**
   - Evidence:
     - Canonical target metric snippet: `WARBIRD_CANONICAL.md:200-205` (binary metric shown as `roc_auc`)
     - Current trainer: `scripts/warbird/train-warbird.py:27-40` (`log_loss`)
     - Current fit options: `scripts/warbird/train-warbird.py:149-153` (`dynamic_stacking=False`, `use_bag_holdout=True`)
   - Risk: model-selection behavior differs from documented intended baseline.

8. **Trigger-state-machine requirements from live capture are not represented in schema/events**
   - Requirement:
     - `docs/plans/2026-03-17-warbird-simplification-handoff.md:343-357`
   - Current enum:
     - `supabase/migrations/20260316000010_warbird_v1_cutover.sql:59-68`
   - Risk: cannot store/validate required `SweepDetected / Acceptance / Imbalance / Displacement` flow.

9. **Cron windows may under-cover MES session logic**
   - Evidence:
     - `vercel.json:18` (`detect-setups` limited to `12-21 UTC` weekdays)
     - MES market-hours logic exists but schedule still restricts route entry points.
   - Risk: unobserved setups outside scheduled window despite market-open periods.

### Medium incompatibilities

10. **Measured-moves cron writes invalid `job_log` schema/status semantics**
    - Evidence:
      - `app/api/cron/measured-moves/route.ts:75-79` uses `status: "OK"` and `rows_written`
      - `supabase/migrations/20260315000007_trading.sql` defines `job_log.status` as enum and column `rows_affected`
    - Risk: observability/log integrity gap for this job.

11. **Admin currently consumes outcomes correctly, but training labels are still disconnected from outcome ledger**
    - Admin now uses `warbird_setups + warbird_setup_events`.
    - Dataset builder still uses synthetic forward scan (`build-warbird-dataset.ts:587-596`).
    - Risk: reported/admin truth and training truth can diverge.

---

## 3) Pass 2 — Adversarial Logic Review (Plan Weaknesses)

These are plan-level weaknesses independent of current code quality.

1. **`mes_1s` requirement lacks explicit ingestion/retention contract**
   - Missing specifics: source schema, retention policy, compression/downsampling, weekend/holiday handling.
   - Consequence: teams can "implement mes_1s" in incompatible ways.

2. **Frozen-geometry versioning is conceptually defined but not data-contract complete**
   - Plan states freeze/supersede behavior but does not define canonical keys:
     - geometry version id
     - superseded-by pointer
     - frozen window boundaries
     - execution linkage
   - Consequence: high risk of mutable history by accident.

3. **Label precedence for same-bar TP/SL conflicts is not specified**
   - For path labels (`hit_sl_first`, `hit_pt1_first`, `hit_pt2_after_pt1`), ambiguous bars can hit both boundaries.
   - Consequence: label noise and inconsistent model behavior across rebuilds.

4. **1000t trigger authority is declared but infrastructure path is undefined**
   - Plan names `1000t` as trigger authority but no ingestion/storage/clock synchronization contract is defined.
   - Consequence: requirement is non-executable without additional architecture.

5. **Non-goal “runner rework” conflicts with “no runner logic” simplification**
   - If runner is out, runner code/status paths must be removed or hard-disabled with clear deprecation policy.
   - Consequence: ambiguous operational behavior.

---

## 4) Canonical Reconciliation (What should be treated as true now)

Use this resolution order:
1. `WARBIRD_CANONICAL.md`
2. `docs/plans/2026-03-17-warbird-simplification-handoff.md`
3. legacy large plan (`gentle-giggling-mccarthy.md`) only where not conflicting

Operationally:
- 15m-primary is canonical for setup/model/chart.
- Sidecar is out for production runtime.
- `mes_1s` continuity is required but currently not implemented.
- Admin shell is preserved; data feeding it must come from canonical lifecycle tables.

---

## 5) Minimal Remediation Sequence (Execution-safe)

### Phase A — Contract Lock (no behavior break)
1. Add migration for `mes_1s` table + index + RLS + (optional) realtime publication.
2. Add explicit score columns to `warbird_forecasts_1h`:
   - `prob_hit_sl_first`
   - `prob_hit_pt1_first`
   - `prob_hit_pt2_after_pt1`
   - `expected_max_extension`
   - `setup_score`
3. Add trigger geometry version fields to `warbird_triggers_15m`:
   - `geometry_version`
   - `geometry_status`
   - `geometry_frozen_until_ts`

### Phase B — Runtime Alignment
4. Make detect-setups strictly 15m-primary for geometry (no 1H fallback as decision authority).
5. Keep 1H/4H as optional context inputs only.
6. Keep runner fields passive (no new runner transitions in scoring path).

### Phase C — Training/Data Truth
7. Move dataset base from 1H-bar-centric geometry rows to 15m geometry rows.
8. Define deterministic tie-break policy for same-bar TP/SL touches and codify it.
9. Add dataset label mode option:
   - synthetic forward-scan (backfill/research)
   - lifecycle-truth labels from `warbird_setups` + `warbird_setup_events` (production truth set)

### Phase D — Production Integrity
10. Replace `forecast-check` only cron with actual hosted inference writer path.
11. Fix measured-moves job logging fields/status to match `job_log` schema.
12. Reassess cron schedule coverage after geometry authority switch.

---

## 6) Current Status Summary

- Admin outcomes are now backend-driven from setup/event truth and auditable with last-event evidence.
- Core canonical gaps are upstream: continuity layer, model column contract, 15m authority enforcement, and training-label alignment.
- Next best move is Phase A (schema contract lock) before further trigger/model rewiring.
