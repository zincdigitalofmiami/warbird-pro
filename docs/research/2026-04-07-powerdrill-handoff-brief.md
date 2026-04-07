# Warbird PowerDrill Handoff Brief

**Date:** 2026-04-07  
**Purpose:** Single briefing document to hand to PowerDrill alongside the authoritative source files.  
**Status:** Handoff-ready summary. This document does not replace the active plan.

---

## 1. Attach These Files To PowerDrill

Repo link:

- `https://github.com/zincdigitalofmiami/warbird-pro`

Public raw URLs:

- README: `https://raw.githubusercontent.com/zincdigitalofmiami/warbird-pro/main/README.md`
- Model spec: `https://raw.githubusercontent.com/zincdigitalofmiami/warbird-pro/main/WARBIRD_MODEL_SPEC.md`
- Handoff brief: `https://raw.githubusercontent.com/zincdigitalofmiami/warbird-pro/main/docs/research/2026-04-07-powerdrill-handoff-brief.md`
- Active plan: `https://raw.githubusercontent.com/zincdigitalofmiami/warbird-pro/main/docs/plans/2026-03-20-ag-teaches-pine-architecture.md`
- PowerDrill findings: `https://raw.githubusercontent.com/zincdigitalofmiami/warbird-pro/main/docs/research/2026-04-06-powerdrill-findings.md`
- Raw backtest report: `https://raw.githubusercontent.com/zincdigitalofmiami/warbird-pro/main/docs/backtest-reports/2026-04-06-wb7-strat-backtest.md`
- Live indicator: `https://raw.githubusercontent.com/zincdigitalofmiami/warbird-pro/main/indicators/v7-warbird-institutional.pine`
- Canonical Warbird tables migration: `https://raw.githubusercontent.com/zincdigitalofmiami/warbird-pro/main/supabase/migrations/20260330000037_canonical_warbird_tables.sql`
- Canonical Warbird compat views migration: `https://raw.githubusercontent.com/zincdigitalofmiami/warbird-pro/main/supabase/migrations/20260330000038_canonical_warbird_compat_views.sql`
- MES runtime schema migration: `https://raw.githubusercontent.com/zincdigitalofmiami/warbird-pro/main/supabase/migrations/20260315000003_mes_data.sql`
- Cross-asset runtime schema migration: `https://raw.githubusercontent.com/zincdigitalofmiami/warbird-pro/main/supabase/migrations/20260315000004_cross_asset.sql`
- Econ runtime schema migration: `https://raw.githubusercontent.com/zincdigitalofmiami/warbird-pro/main/supabase/migrations/20260315000005_econ.sql`
- RLS migration: `https://raw.githubusercontent.com/zincdigitalofmiami/warbird-pro/main/supabase/migrations/20260315000008_rls.sql`
- Legacy trading schema migration: `https://raw.githubusercontent.com/zincdigitalofmiami/warbird-pro/main/supabase/migrations/20260315000007_trading.sql`
- `mes-1m` Edge Function: `https://raw.githubusercontent.com/zincdigitalofmiami/warbird-pro/main/supabase/functions/mes-1m/index.ts`
- `mes-hourly` Edge Function: `https://raw.githubusercontent.com/zincdigitalofmiami/warbird-pro/main/supabase/functions/mes-hourly/index.ts`
- `cross-asset` Edge Function: `https://raw.githubusercontent.com/zincdigitalofmiami/warbird-pro/main/supabase/functions/cross-asset/index.ts`
- `fred` Edge Function: `https://raw.githubusercontent.com/zincdigitalofmiami/warbird-pro/main/supabase/functions/fred/index.ts`
- `econ-calendar` Edge Function: `https://raw.githubusercontent.com/zincdigitalofmiami/warbird-pro/main/supabase/functions/econ-calendar/index.ts`
- `exec-orders` Edge Function: `https://raw.githubusercontent.com/zincdigitalofmiami/warbird-pro/main/supabase/functions/exec-orders/index.ts`

Local file to attach directly to PowerDrill:

- `/Volumes/Satechi Hub/warbird-pro/docs/research/2026-04-07-current-cloud-db-and-offline-data-state.md`

Primary files:

1. `/Volumes/Satechi Hub/warbird-pro/indicators/v7-warbird-institutional.pine`
2. `/Volumes/Satechi Hub/warbird-pro/docs/backtest-reports/2026-04-06-wb7-strat-backtest.md`
3. `/Volumes/Satechi Hub/warbird-pro/docs/research/2026-04-06-powerdrill-findings.md`
4. `/Volumes/Satechi Hub/warbird-pro/docs/plans/2026-03-20-ag-teaches-pine-architecture.md`

Cloud schema and runtime files:

5. `/Volumes/Satechi Hub/warbird-pro/supabase/migrations/20260330000037_canonical_warbird_tables.sql`
6. `/Volumes/Satechi Hub/warbird-pro/supabase/migrations/20260330000038_canonical_warbird_compat_views.sql`
7. `/Volumes/Satechi Hub/warbird-pro/supabase/migrations/20260315000003_mes_data.sql`
8. `/Volumes/Satechi Hub/warbird-pro/supabase/migrations/20260315000004_cross_asset.sql`
9. `/Volumes/Satechi Hub/warbird-pro/supabase/migrations/20260315000005_econ.sql`
10. `/Volumes/Satechi Hub/warbird-pro/supabase/migrations/20260315000008_rls.sql`

Historical legacy-reference schema:

11. `/Volumes/Satechi Hub/warbird-pro/supabase/migrations/20260315000007_trading.sql`

Optional supporting reference:

12. `/Volumes/Satechi Hub/warbird-pro/WARBIRD_MODEL_SPEC.md`

Current-state audit to attach directly:

13. `/Volumes/Satechi Hub/warbird-pro/docs/research/2026-04-07-current-cloud-db-and-offline-data-state.md`

Runtime wiring files:

14. `/Volumes/Satechi Hub/warbird-pro/supabase/functions/mes-1m/index.ts`
15. `/Volumes/Satechi Hub/warbird-pro/supabase/functions/mes-hourly/index.ts`
16. `/Volumes/Satechi Hub/warbird-pro/supabase/functions/cross-asset/index.ts`
17. `/Volumes/Satechi Hub/warbird-pro/supabase/functions/fred/index.ts`
18. `/Volumes/Satechi Hub/warbird-pro/supabase/functions/econ-calendar/index.ts`
19. `/Volumes/Satechi Hub/warbird-pro/supabase/functions/exec-orders/index.ts`

Use this brief as the cover memo. The source files above are the actual authority.

---

## 2. What Warbird Is

Warbird is a MES 15m fib-outcome system with:

- Pine as the canonical live signal surface
- a dashboard as the mirrored operator surface
- AutoGluon offline only
- Supabase cloud as the lean runtime canonical store
- an external-drive local PostgreSQL warehouse for structured research/training data
- an external-drive `/data/` root for raw snapshots, parquet archives, datasets, and AG artifacts

Important storage boundary:

- public GitHub is the code/docs surface
- cloud Supabase is not a mirror of the local training warehouse
- offline local training data lives on the external drive and is not assumed available from GitHub
- local Docker Supabase is not the active local data contract

The canonical trade object is the **MES 15m fib setup** keyed by the MES 15m bar-close timestamp in `America/Chicago`.

The canonical flow is:

`fib_engine_snapshot -> candidate -> outcome -> decision -> signal`

The live model does **not** forecast price. It supports:

- TP1 probability
- TP2 probability
- reversal risk
- bounded stop-family selection

---

## 3. Source-of-Truth Surfaces

### 3.1 Live indicator

`v7-warbird-institutional.pine` is the active Pine work surface.

It currently contains:

- adaptive fib engine with ATR-multiplier ZigZag controls
- CME Globex intermarket basket: `NQ`, `RTY`, `CL`, `HG`, `6E`, `6J`
- daily context inputs for `SKEW` and NYSE advance/decline
- grouped regime engine: leadership, risk appetite, macro-FX, and execution quality
- event-state and setup-archetype logic
- hidden `ml_*` exports for offline feature capture
- 3 live alerts only:
  - `WARBIRD ENTRY LONG`
  - `WARBIRD ENTRY SHORT`
  - `PIVOT BREAK (against) + Regime Opposed`

Important current indicator facts:

- plot budget is already near the TradingView ceiling
- the hidden export surface is intentional and is part of the AG pipeline contract
- the indicator is the live execution surface; the dashboard must not re-derive fib geometry locally

### 3.2 Raw baseline backtest

The raw TradingView strategy conversion report is the baseline evidence set.

Core result:

- `15m` loses materially
- `1H` is roughly flat
- `4H` is the only profitable surface

### 3.3 PowerDrill findings

The 2026-04-06 findings document is the synthesis of the full research pack and is the current diagnosis source for:

- why the `15m` surface is weak
- what the next repair order should be
- how `PASS / WAIT / TAKE_TRADE` should replace simple binary entry behavior
- how stop-family testing should be sequenced
- how the offline selector and Pine-safe packet should be designed

### 3.4 Active architecture plan

The 2026-03-20 active plan is the single architecture source of truth.

It now includes a consolidated execution sequence that ties together:

- PowerDrill repairs
- canonical writer cutover
- reader cutover
- local warehouse buildout
- AG training and packet publish-up
- walk-forward validation and legacy retirement

### 3.5 Cloud schema source files

PowerDrill should use the migration files directly for schema truth instead of relying on summarized table descriptions.

Canonical cloud Warbird schema:

- `20260330000037_canonical_warbird_tables.sql`
- `20260330000038_canonical_warbird_compat_views.sql`

These define the current canonical Warbird families:

- enums:
  - `warbird_decision_code`
  - `warbird_outcome_code`
  - `warbird_signal_status`
  - `warbird_signal_event_type`
  - `warbird_setup_archetype`
  - `warbird_stop_family`
  - `warbird_fib_level`
  - `warbird_regime_bucket`
  - `warbird_session_bucket`
  - `warbird_packet_status`
- tables:
  - `warbird_training_runs`
  - `warbird_training_run_metrics`
  - `warbird_packets`
  - `warbird_packet_activations`
  - `warbird_packet_metrics`
  - `warbird_packet_feature_importance`
  - `warbird_packet_setting_hypotheses`
  - `warbird_packet_recommendations`
  - `warbird_fib_engine_snapshots_15m`
  - `warbird_fib_candidates_15m`
  - `warbird_candidate_outcomes_15m`
  - `warbird_signals_15m`
  - `warbird_signal_events`
- forward-facing views:
  - `warbird_active_signals_v`
  - `warbird_admin_candidate_rows_v`
  - `warbird_candidate_stats_by_bucket_v`
  - `warbird_active_packet_metrics_v`
  - `warbird_active_training_run_metrics_v`
  - `warbird_active_packet_feature_importance_v`
  - `warbird_active_packet_recommendations_v`
  - `warbird_active_packet_setting_hypotheses_v`

Runtime market and context schema:

- `20260315000003_mes_data.sql`
  - `mes_1m`
  - `mes_15m`
  - `mes_1h`
  - `mes_4h`
  - `mes_1d`
- `20260315000004_cross_asset.sql`
  - `cross_asset_1h`
  - `cross_asset_1d`
  - `options_stats_1d`
  - `options_ohlcv_1d`
- `20260315000005_econ.sql`
  - `series_catalog`
  - `econ_rates_1d`
  - `econ_yields_1d`
  - `econ_fx_1d`
  - `econ_vol_1d`
  - `econ_inflation_1d`
  - `econ_labor_1d`
  - `econ_activity_1d`
  - `econ_money_1d`
  - `econ_commodities_1d`
  - `econ_indexes_1d`
- `20260315000008_rls.sql`
  - baseline RLS and authenticated-read policies across runtime tables

Legacy reference only:

- `20260315000007_trading.sql`
  - contains legacy pre-canonical surfaces such as `warbird_setups`, `trade_scores`, `measured_moves`, `forecasts`, `job_log`, and `models`
  - this file is useful to explain historical code debt, but it is not the target schema authority for new work

### 3.6 Current state audit

Use `2026-04-07-current-cloud-db-and-offline-data-state.md` as the live storage-boundary memo.

It records directly verified facts that matter for architecture:

- cloud Supabase is the live DB truth
- the external-drive PostgreSQL warehouse plus `/data/` raw archives define the local training side
- local Docker Supabase is not active and is not the current local contract
- canonical Warbird lifecycle tables exist in cloud but are still empty
- runtime market/context ingestion tables are populated in cloud
- most offline training data artifacts are intentionally not on GitHub
### 3.7 Active Edge Functions

Current active Supabase function surfaces in the repo:

- `mes-1m`
- `mes-hourly`
- `cross-asset`
- `fred`
- `econ-calendar`
- `exec-orders`
- `massive-inflation`
- `massive-inflation-expectations`

PowerDrill should treat the first six as the main runtime ingestion surfaces and the shared `_shared/*` helpers as the implementation layer behind them.

---

## 4. Verified Baseline Problem

From the raw backtest:

- `15m`: `-$4,227.51`, `PF 0.903`, `374` trades
- `1H`: `-$185.57`, `PF 0.995`, `255` trades
- `4H`: `+$3,607.85`, `PF 1.192`, `97` trades

Recurring structural problems:

- average losses are about 2x average wins across all timeframes
- shorts underperform persistently
- the `15m` surface admits too many mediocre trades
- losers sit too long
- the current fixed stop geometry is the main structural pain point

This is why the project is blocked on candidate-quality repair before any canonical writer or AG buildout.

---

## 5. Dominant PowerDrill Conclusions

These are the highest-confidence conclusions from the 2026-04-06 PowerDrill findings:

- keep Pine as the structure generator
- move to `PASS / WAIT / TAKE_TRADE`
- require bar-close confirmation over permissive first-touch logic
- treat long and short behavior asymmetrically
- simplify the live regime stack instead of adding more confluence clutter
- use offline AutoGluon to rank and calibrate surviving candidates, not to invent live signals from scratch
- keep the packet compact, normalized, versioned, and Pine-safe

The dominant recommendation is:

**clean the candidate stream first, then let offline ML rank the survivors.**

---

## 6. Current Execution Order

This is the order PowerDrill should assume unless it can justify a better one without violating the active contract.

### Phase 0 — Contract and storage freeze

- freeze the MES 15m contract
- freeze cloud runtime vs local training boundaries
- reject any architecture that collapses back into a narrow legacy table story

### Phase 1 — Entry-surface repair

- fix the stop-lock bug in the strategy/backtest surface
- add the trigger-gate repair
- add bounded ATR stop-family testing
- re-test the candidate definition before any writer design

### Phase 2 — Canonical cloud writer cutover

- port or replace legacy setup-scoring routes
- write only to canonical snapshot/candidate/outcome/signal tables
- keep idempotent contract-key writes

### Phase 3 — Reader and dashboard cutover

- move `/admin`, API readers, and dashboard consumers to canonical views
- keep dashboard render-only against stored engine state

### Phase 4 — Local warehouse and feature pipeline

- build the offline source-loading and feature pipeline
- keep the local training surface separate from cloud runtime
- do not use daily, hourly, or standing cron pulls for training-only data
- refresh training data by batch pull on retrain day or explicit research rebuild only
- defer lower-timeframe intermarket expansion until SHAP justifies it

### Phase 5 — AutoGluon training and packet publish-up

- train staged baselines
- produce packet metrics, feature importance, and recommendations
- publish compact Pine-safe packets only after the warehouse and candidate contract are stable

### Phase 6 — Walk-forward validation and legacy retirement

- validate the full end-to-end path
- promote only additive changes
- retire legacy Warbird operational tables only after the canonical path is proven

---

## 7. Current Repo-Truth Blockers PowerDrill Must Respect

These are not abstract risks. They are current repository facts:

- the PowerDrill pre-Step-5 repairs are still open on the strategy surface
- legacy writers and readers still point at dropped or retired Warbird tables
- the `scripts/ag/*` workbench is not built yet; only the local research schema file exists there
- current bridge scripts still reference retired sources such as `news_signals`, `trump_effect_1d`, and `warbird_setups`
- subordinate docs still contain conflicting local-warehouse descriptions, so the active plan must be treated as the winner

PowerDrill should not assume the current codebase already has a working canonical writer path or a finished AG pipeline.

---

## 8. Non-Negotiable Constraints

PowerDrill must stay inside these constraints:

- no mock or placeholder data
- no live server-side inference path
- Pine remains the live signal source
- cloud Supabase remains the lean runtime canonical store
- local training remains offline only
- training-only data is batch-refreshed on retrain day; do not create recurring daily/hourly pulls for it
- recurring cloud ingestion is allowed only when the data is needed for the frontend, live indicator/runtime contract, dashboard state, or operator-facing surfaces
- the dashboard must mirror stored engine state, not compute a second fib engine
- the canonical trade object stays MES 15m
- `news_signals` is retired from the active contract
- cross-asset `15m` and `1m` expansion is SHAP-gated, not assumed

---

## 9. Exact Questions / Requests For PowerDrill

Use the attached files to answer these questions:

1. Does the current Phase 1 repair order look correct, or should the stop-family and trigger-gate test matrix be sequenced differently?
2. Given the live indicator export surface, which hidden `ml_*` fields are most likely redundant versus essential for the first AG baseline?
3. Does the current `PASS / WAIT / TAKE_TRADE` policy direction need a different bucket or threshold design before canonical writer implementation starts?
4. Does the live regime stack stay small enough, or should some current live intermarket logic move to research-only packet context?
5. Which stop-family comparison should be treated as the most defensible first production baseline for MES 15m?
6. What is the smallest safe packet design that preserves calibration, sample-count clarity, and Pine implementation safety?
7. What missing documentation or ambiguity would still block a clean writer/admin/AG handoff?

---

## 10. Minimal Summary For PowerDrill

If PowerDrill only reads one paragraph before opening the files, use this:

Warbird is a MES 15m fib-outcome system whose live signal source is `v7-warbird-institutional.pine`. The raw backtest says the current `15m` surface loses money because it admits too many mediocre trades, has oversized loss geometry, and handles shorts poorly. The active plan therefore blocks downstream writer, dashboard, and AG work until the candidate stream is repaired first. Use the attached indicator, raw backtest, findings synthesis, and active plan to pressure-test the Phase 1 repair order, the canonical writer/read-model sequence, the local warehouse boundary, and the compact Pine-safe packet design.
