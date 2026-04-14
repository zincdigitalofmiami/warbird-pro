# Warbird Full Reset Plan v5: External-Drive Local Warehouse, AG Training View, Full SHAP

## Summary

- This plan is decision complete. No further repo-level architecture locks remain before execution.
- Canonical split is fixed:
  - local `warbird` on PG17 `127.0.0.1:5432` = full data zoo, canonical warehouse, training, artifacts, raw SHAP, diagnostics
  - cloud Supabase `qhwgrzqjcdtdqppvhhme` + Vercel `warbird-pro` = serving-only for frontend, TradingView/indicator support, packets, dashboard/admin read models, and curated SHAP/report surfaces
- Canonical local AG contract is **three canonical local AG tables and one canonical training view.**
  - tables: `ag_fib_snapshots`, `ag_fib_interactions`, `ag_fib_outcomes`
  - view: `ag_training`
- Exact column/type and view SQL authority: `docs/contracts/ag_local_training_schema.md`
- Canonical names never use version suffixes.
- Removed from the canonical local build:
  - `cross_asset_1d`
  - all news surfaces
  - all options surfaces
  - all legacy setup/trade/news tables
- `mes_1m` is readmitted only as subordinate local micro-execution context for
  canonical MES 15m parent setups. It is not a new primary trade object and
  does not authorize canonical stored `3m` / `5m` tables.
- First macro scope is locked to `FRED + econ_calendar`.
- Cloud promotion is locked to `manual promote`.

## Repository and Storage Layout

- Everything is rooted on `/Volumes/Satechi Hub/warbird-pro/`.
- Repo layout is locked to:
  - `local_warehouse/migrations/` = local-only DDL and migration ledger management
  - `scripts/ag/` = Python warehouse build, feature engineering, training, SHAP, publish-up
  - `data/` = raw Databento archives, parquet inputs, HG source files
  - `artifacts/` = append-only model outputs, reports, SHAP artifacts
  - `artifacts/shap/{run_id}/shap_values_{fold}_{split}.parquet`
  - `artifacts/shap/{run_id}/shap_interactions_{fold}_{split}.parquet`
  - `supabase/migrations/` = cloud-serving DDL only
- PG17 data directory being on the external drive is an infrastructure fact, not a repo contract. The repo only assumes a reachable local PG17 instance at `127.0.0.1:5432`.

## 2026-04-10 Execution Checkpoint

- Verified directly from the worktree and local PG17:
  - `rabid_raccoon` exists; `warbird` does not yet exist.
  - `local_warehouse/` is absent, so `local_warehouse/migrations/` and `local_schema_migrations` are still pending.
  - `data/` exists with bootstrap candidate files/parquet extracts; `artifacts/` is still absent.
- `scripts/ag/` now includes Phase 4 bootstrap implementation (`build_ag_pipeline.py`) plus tuner utilities.
- Exact drift blocking execution:
  - `scripts/ag/local_warehouse_schema.sql` is legacy local-research SQL. It assumes canonical cloud tables already exist locally and references legacy `warbird_*` tables plus retired news surfaces, so it does not satisfy the Phase 1 local warehouse or Phase 3 canonical AG contract.
  - `docs/contracts/ag_local_training_schema.md` exists in the working tree but is currently untracked, so the Phase 0 authority rewrite is not yet fully protected in git.
- Current blocking item:
  - Create local `warbird`, create `local_warehouse/migrations/`, create `local_schema_migrations`, then implement the canonical AG tables/view from `docs/contracts/ag_local_training_schema.md`.

## 2026-04-11 Session Additions

- Pine Script v6 capability analysis complete. Exhaustion diamond v2 architecture designed.
  `request.footprint()` confirmed for v6 plans that support footprint; confluence model locked
  to geometry + statistics + order flow with explicit confidence tiers.
- Loss drivers from live trade review are locked as indicator design inputs:
  revenge re-entry clustering, premature winner exits, session-quality degradation,
  and size escalation during drawdown.
- S/R feature architecture locked: per-type wide numeric families only. Full spec in
  `docs/contracts/ag_local_training_schema.md`.
- Automated indicator capture pipeline designed: Pine alert -> webhook -> Supabase Edge
  Function -> cloud relay table -> nightly local sync. Recurring manual TV CSV exports
  are removed after one-time historical seed ingest.
- Phase 0 complete — `ag_local_training_schema.md` landed at commit 92ea751.

## Phase 0: Authority Rewrite Order

- Rewrite order is fixed:
  1. `AGENTS.md`
  2. `WARBIRD_MODEL_SPEC.md`
  3. `docs/MASTER_PLAN.md`
- After each rewrite, stop and audit that document before moving to the next.
- `AGENTS.md` must lock:
  - local `warbird` is canonical
  - cloud is serving-only
  - `rabid_raccoon` is bootstrap-only legacy input
  - canonical names have no version suffixes
  - local warehouse DDL does not live in `supabase/migrations/`
- `WARBIRD_MODEL_SPEC.md` must lock:
  - the exact three AG tables from the prompt
  - `ag_training` as the canonical flat training view
  - the exact SQL contract reference in `docs/contracts/ag_local_training_schema.md`
  - `live generator` = Pine runtime engine
  - `training generator` = Python reconstruction pipeline
  - full-surface SHAP as mandatory
- `docs/MASTER_PLAN.md` must replace the old architecture with:
  - local warehouse creation
  - one-time bootstrap
  - Python candidate/outcome generation
  - AutoGluon training
  - full SHAP
  - manual publish-up to cloud
  - runtime/dashboard/admin serving

## Phase 0.5: Indicator Pre-Implementation Locks and AG-Facing Scope

This phase begins after Phase 0 is fully landed (`docs/contracts/ag_local_training_schema.md`
tracked in git). It runs in parallel with Phase 1 warehouse work and does not block Phase 1
warehouse execution. It blocks only the Pine indicator implementation work stream.

### Pine Budget Baseline

Verified 2026-04-13 (pine-lint.sh, both files):

`v7-warbird-institutional.pine` (live indicator):
  Output: 51/64 (46 plot + 2 plotshape + 3 alertcondition, 13 headroom)
  Request: 4 `request.security()` + 1 `request.footprint()` = 5 paths

`v7-warbird-strategy.pine` (AG training data generator):
  Output: 52/64 (50 plot + 2 plotshape, 12 headroom)
  Request: 4 `request.security()` + 1 `request.footprint()` = 5 paths

2026-04-13 session changes:
- Dead HyperWave oscillator + EXHAUSTION DIAMOND energy blocks removed from both files
  (were live v6 code driving sidebar; orphaned in v7 when sidebar was removed).
- `Exhaustion ATR Multiplier` removed from strategy_tuning_space.json (fed only dead code).
- ZigZag contract is not actually locked yet. Verified 2026-04-13: docs still state
  Deviation=3.0 / Depth=12, but runtime and generator paths are split:
  institutional auto-tune uses 15m Depth=15, strategy manual default stays Depth=12
  while strategy auto-tune also resolves 15m to Depth=15, and
  `scripts/ag/build_ag_pipeline.py` hardcodes Deviation=3.0 / Depth=15.
- Raw footprint numeric exports added to strategy: `ml_exh_fp_delta`, `ml_exh_trigger_row_delta`,
  `ml_exh_extreme_vol_ratio`, `ml_exh_stacked_imbalance_count`.
- CDP tuner automation built: `scripts/ag/tv_auto_tune.py` replaces manual knob→CSV loop.

All additions must be priced against these baselines before any code is written.
Any implementation exceeding 64 plots or 40 request calls is invalid without
an explicit approved recount.

### Platform Constraints (Hard Rules)

`request.footprint()` is budget-constrained and must be designed as a single cached
source per bar for all footprint-derived features.

Confidence tier handling as of 2026-04-13:
- Reversal exhaustion (`ml_exh_confidence_tier`): Tier 1 only when footprint confirms; otherwise 0.
- Continuation evidence (`ml_cont_confidence_tier`): Tier 1 (full) and Tier 2 (reduced when footprint is unavailable).
Do not reintroduce geometry-only reversal Tier 2 without explicit approval.

`polyline.new()` replaces multi-line Fibonacci grid construction where equivalent.
Pine v6 strict booleans are required for exhaustion and hold-state logic.

### Verification Steps (Required Before Indicator Implementation)

1. Confirm `request.footprint()` returns non-`na` data for MES1! on production
   TradingView setup. Validate `footprint.delta()`, `footprint.poc()`, and row access.
2. Run full Pine budget audit for planned additions (exhaustion v2, behavioral modules,
   S/R exports, diagnostics table, polyline objects, webhook alert payload). Document
   before/after budget in this plan section.
3. Get explicit approval before touching `indicators/v7-warbird-institutional.pine`.

### Indicator Implementation Scope — Primary Modules

The indicator update must prioritize these loss-driver corrections:

- Consecutive loss context and cooldown state to prevent revenge re-entry clustering.
- Exhaustion hold logic to reduce premature exits before structural extension completes.
- Session-quality labeling and maintenance-window suppression.
- Direction alignment and momentum validation states as visual friction.
- Position-size warning in drawdown context.
- Structural and emergency stop visualization with ATR scaling.

### Exhaustion Diamond v2 — Architecture (Pine v6)

Confluence logic (short side, mirrored for long):

exhaustion_short =
(price >= fib_1272 OR price >= fib_1618)
AND (zscore >= 2.5)
AND (delta_diverging)
AND NOT (stacked_imbalance)

Patterns:

- Pattern A (required): delta divergence at extension target.
- Pattern B (Tier 1 elevation): absorption node near extreme with rejection.
- Pattern C (Tier 1 elevation): zero-print / finished auction with regime-conditioned threshold.

Tier rendering:

- Tier 1: full confluence and footprint confirmation.
- Tier 2: geometry + statistics only when footprint unavailable.

### Automated Indicator Capture Pipeline (Required Before Phase 4)

Pipeline:
Pine `alert()` at `barstate.isconfirmed`
-> Supabase Edge Function (`indicator-capture`)
-> `indicator_snapshots_15m` cloud relay
-> nightly sync to local `warbird`
-> AG weekly training from local warehouse

After one-time historical seed ingest, recurring manual TV CSV export is removed.

### 2026-04-14 Execution Delta — Parent Setup, Child Trigger

Live tape review on 2026-04-14 invalidated the assumption that a 15m-only
accept/exhaustion trigger contract is sufficient for the best Warbird entries.
The fib ladder repeatedly identified the correct map, but the current trigger
surface missed obvious high-R executions that resolved between a pocket failure
and the parent `1.0` / `TARGET 1` path. The contract delta is:

- The canonical trade object remains the MES 15m fib setup keyed by the MES 15m
  bar close in `America/Chicago`.
- Execution becomes a subordinate child layer attached to that parent setup.
  The parent defines the map and target ladder. The child defines when the
  operator should engage.
- Child trigger timeframes are `1m`, `3m`, or `5m`. `3m` and `5m` are derived
  from canonical local `mes_1m`; they are not new stored canonical tables.
- Order-flow is first-class execution evidence. Fibs are the map; order-flow at
  the level is the trigger.
- Pine runtime vocabulary for the child layer is locked to:
  - `WATCH`
  - `ARMED`
  - `GREEN_LIGHT`
  - `INVALIDATED`
- First admitted child execution patterns:
  - `PULLBACK_HOLD`
  - `FAILED_RECLAIM`
  - `CLIMAX_REVERSAL`
  - `FAILED_EXPANSION`
- Child states must remain point-in-time safe and keyed back to the same parent
  15m setup. They do not create a second canonical trade object.
- Historical backfill may use real `mes_1m` OHLCV-derived microstructure plus
  TradingView footprint capture where available. Do not claim full-history
  footprint truth until a real lower-timeframe capture path exists.
- Current tuner profile `mes15m_agfit_v3` is a parent-settings sweep only. It
  is not authorized to choose `1m/3m/5m` trigger policy. A separate
  micro-execution tuning profile is required.

### Backtesting Protocol Locks

- Deep Backtesting for multi-regime coverage.
- Bar Magnifier for intrabar order-of-fill realism.
- Walk-forward IS/OOS only with one-session embargo minimum.
- Commission/slippage floors required in all reported strategy results.
- Parameter sweeps must report trade frequency and precision jointly.

## Phase 1: Local Warehouse Creation — COMPLETE 2026-04-11

**Verified:** `warbird` database live on PG17 (`127.0.0.1:5432`). Owner: `zincdigital`. UTF8.
**Migrations applied:** 001–006 via `local_warehouse/migrations/`. Ledger: `local_schema_migrations`.
**Tables created (18):** `mes_15m`, `mes_1h`, `mes_4h`, `mes_1d`, `cross_asset_1h`,
`economic_series`, 10 FRED families (`econ_rates_1d` through `econ_indexes_1d`), `econ_calendar`.

Original requirements:

- ~~Create a clean local database named `warbird`.~~ Done.
- ~~Use a dedicated local migration system in `local_warehouse/migrations/`.~~ Done.
- ~~Add a local migration ledger table named `local_schema_migrations`.~~ Done.
- Keep cloud migrations in `supabase/migrations/` only. (Invariant maintained.)
- Default schema choice is locked to `public` with canonical snake_case table names and no secondary schema split. (Applied.)

## Phase 2: One-Time Bootstrap from `rabid_raccoon` — COMPLETE 2026-04-11

**Verified row counts (warbird post-bootstrap):**

- `mes_15m`: 144,540 rows (2020-01-01 → 2026-03-09)
- `mes_1h`: 36,321 rows (2020-01-01 → 2026-03-09)
- `mes_4h`: 9,513 rows (2020-01-01 → 2026-03-09, derived from mes_1h)
- `mes_1d`: 1,919 rows (2020-01-01 → 2026-03-08)
- `cross_asset_1h`: 221,954 rows, all 6 symbols (6E/6J/CL/HG/NQ/RTY, 2020-01-01 → 2026-04-03)
  - HG sourced from `data/cross_asset_1h.parquet` (not in rabid_raccoon). **HG blocker resolved.**
- `economic_series`: 141 series
- All 10 FRED families: see CLAUDE.md for per-table counts
- `econ_calendar`: 3,227 events (2020-01-02 → 2026-12-16)

**Bootstrap script:** `local_warehouse/bootstrap/bootstrap_from_rabid_raccoon.sh`
**HG source:** `data/cross_asset_1h.parquet` (Databento intermarket export, continuous front-month)

`rabid_raccoon` is now legacy reference only. Do not treat it as canonical.

Original requirements:

- Bootstrap source is `rabid_raccoon` on the same PG instance, one time only.
- After bootstrap, `rabid_raccoon` becomes legacy reference only and must not be treated as canonical again.
- Import only approved `2020+` core surfaces into `warbird`:
  - `mes_15m`
  - `mes_1h`
  - `mes_4h` derived from `mes_1h`
  - `mes_1d`
  - `cross_asset_1h` for exactly `NQ`, `RTY`, `CL`, `6E`, `6J`, `HG`
  - daily FRED families admitted by the current contract
  - `econ_calendar`
  - minimal reference tables required to support the above
- Do not import into canonical warehouse:
  - `mkt_futures_mes_1m`
  - any news table
  - any options table
  - `warbird_setups`
  - `scored_trades`
  - `news_signals`
  - `econ_news_1d`
  - `policy_news_1d`
  - any other legacy operational surface
- Bootstrap mapping must be explicit:
  - legacy camelCase columns map into canonical snake_case columns through documented bootstrap SQL
  - `econ_calendar` merges date/time into a canonical timestamp with explicit timezone handling
  - `HG` is mandatory; if missing in `rabid_raccoon`, source it from the raw drive files before bootstrap signoff
- Retention floor is locked to `2020-01-01T00:00:00Z` for canonical training surfaces.

2026-04-14 follow-on delta:
- `mes_1m` is reopened as a new Phase 4 subordinate microstructure surface for
  child execution-state reconstruction. This does not change the completed
  Phase 2 bootstrap facts above and does not create a new primary trade object.

## Phase 3: Canonical AG Schema — COMPLETE 2026-04-11

- Implement **three canonical local AG tables and one canonical training view.**
- Implement the three canonical local AG tables exactly as provided:
  - `ag_fib_snapshots`
  - `ag_fib_interactions`
  - `ag_fib_outcomes`
- Implement `ag_training` exactly as defined in `docs/contracts/ag_local_training_schema.md`.
- `ag_training` must use `WHERE outcome_label != 'CENSORED'`.
- No versioned canonical name is allowed.
- The canonical warehouse truth remains these three tables plus the supporting market/macro source tables, with `ag_training` as the canonical view over them. Stop-family comparisons and SHAP lineage expand around this base contract; they do not replace it.

**Verified 2026-04-11:** Migration `007_ag_schema.sql` applied. Tables `ag_fib_snapshots`, `ag_fib_interactions`, `ag_fib_outcomes` and view `ag_training` live in `warbird`. Censored filter (`WHERE outcome_label != 'CENSORED'`) present.

## Phase 4: Python Pipeline in `scripts/ag/`

- Python owns the full offline pipeline:
  - extract from local `warbird`
  - reconstruct fib snapshots
  - generate interactions
  - label forward outcomes
  - populate `ag_fib_snapshots`, `ag_fib_interactions`, `ag_fib_outcomes`
  - consume `ag_training` as the canonical training read view
  - create walk-forward splits
  - train AutoGluon
  - compute SHAP and SHAP interactions
  - register artifacts
  - publish approved outputs to cloud
- First model target is locked to multiclass `outcome_label`.
- First feature scope is locked to `MES + cross-asset + macro`.
- S/R feature scope is locked to per-type wide numeric families as specified in
  Phase 0.5 and `docs/contracts/ag_local_training_schema.md`. Expected budget: 25-35 columns.
- Behavioral features (`ml_session_tier` through `ml_favorable_excursion_pts`) are
  first-run scope. Spec in Phase 0.5 and `docs/contracts/ag_local_training_schema.md`.
- Exhaustion features (`ml_exh_*` columns) are first-run scope. Feature enrichment only.
  Not candidate gates. Spec in Phase 0.5 and `docs/contracts/ag_local_training_schema.md`.
- Indicator snapshot features (from automated webhook pipeline) are first-run scope.
  Sourced from `indicator_snapshots_15m` local table via nightly sync from cloud capture.
- Micro-execution features are reopened for first-run scope under the
  2026-04-14 delta: local `mes_1m` supplies the canonical backfill tape,
  `3m/5m` are derived on read, and order-flow / footprint evidence attaches to
  the parent 15m setup as child execution-state context.
- Live trade review loss drivers are required as feature-engineering context for Phase 4.
- Macro scope is locked to:
  - daily FRED families
  - `econ_calendar`
  - no news or narrative sources
- Training discipline is locked:
  - walk-forward splits only
  - one-session embargo minimum
  - no shuffle
  - no fit on full dataset
  - no tuning on test
  - naive baseline required
  - full run metadata required

**Checkpoint 2026-04-13:** `scripts/ag/build_ag_pipeline.py` implemented and executed against local `warbird`.  
Outputs:
- populated canonical AG tables from `mes_15m` reconstruction:
  - `ag_fib_snapshots`: 3,101 rows
  - `ag_fib_interactions`: 37,450 rows
  - `ag_fib_outcomes`: 37,450 rows
  - `ag_training` (non-censored): 17,100 rows
- generated walk-forward split structure at `artifacts/ag_runs/agfit_20260413T192255Z/` (`train.csv`, `val.csv`, `test.csv`, `manifest.json`)
- added repo-native baseline trainer scaffold at `scripts/ag/train_ag_baseline.py`:
  - consumes `ag_training`
  - joins real `cross_asset_1h` + `FRED/econ_calendar`
  - strips realized-outcome leakage before training
  - writes local run artifacts under `artifacts/ag_runs/`
  - blocks training when validation/test slices collapse below 2 target classes
  - trainer defaults now force `presets=best_quality`, `num_bag_folds=5`,
    `num_stack_levels=2`, `dynamic_stacking=auto`
- verified current local training-state facts:
  - `ag_training` label distribution:
    - `STOPPED`: 15,893
    - `TP5_HIT`: 1,114
    - `TP1_ONLY`: 74
    - `TP2_HIT`: 19
  - no trained predictor artifact currently exists under `artifacts/`
  - `autogluon` is not installed in the active local Python environment, so
    `TabularPredictor.fit()` cannot complete in this workspace yet

Remaining Phase 4 blocker after this checkpoint:
- execution-contract repair. Current 15m-only trigger semantics do not express
  `WATCH -> ARMED -> GREEN_LIGHT -> INVALIDATED` child execution states or the
  simple pocket-failure trades that resolve cleanly into `1.0` / `TARGET 1`.
- local `mes_1m` admission is now required as subordinate microstructure input
  for the child execution layer. `3m/5m` remain derived on read.
- the tuner must split into two scopes:
  - parent 15m fib/settings profile
  - child 1m/3m/5m execution profile
- evaluation-policy repair for the current `outcome_label` regime. Verified on 2026-04-13: `TP1_ONLY` disappears after 2022-06-28 and 2024+ is nearly all `STOPPED`, so several time-safe multiclass folds are structurally invalid.
- ZigZag contract drift remains unresolved across docs, Pine runtime, and Python reconstruction. Do not claim reproducible AG/Pine parity until one depth contract is selected and enforced everywhere.
- local lineage/reporting tables are still absent in `warbird`: `ag_training_runs`, `ag_shap_feature_summary`, `ag_shap_interactions`.
- then finish feature parity for first-run scope (`MES + cross-asset + macro` plus indicator-snapshot-derived feature families) and complete AutoGluon training/SHAP lineage steps.

## Phase 5: Full-Surface SHAP Program

- Full SHAP is mandatory and local-only at raw level.
- Add local lineage tables:
  - `ag_training_runs`
  - `ag_training_run_metrics`
  - `ag_artifacts`
  - `ag_shap_feature_summary`
  - `ag_shap_cohort_summary`
  - `ag_shap_interaction_summary`
  - `ag_shap_temporal_stability`
  - `ag_shap_feature_decisions`
  - `ag_shap_run_drift`
- Store append-only raw artifacts in `artifacts/shap/{run_id}/`.
- Raw SHAP storage must include:
  - per-row SHAP values
  - per-row SHAP interaction values
  - `interaction_id`
  - `run_id`
  - `target_name`
  - `split_code`
  - `fold_code`
- SHAP coverage is locked to the full surface:
  - all 16 fib levels
  - all indicators/features
  - both directions
  - all outcome classes
  - all stop families
  - all sessions
  - all volatility regimes
  - all walk-forward folds
- Mandatory cohort dimensions for `ag_shap_cohort_summary`:
  - fib level
  - direction
  - outcome class
  - stop family
  - session
  - volatility regime
  - fold
- Mandatory SHAP interaction analysis:
  - global pairwise interaction importance
  - fold-specific interaction importance
  - cohort-specific interaction importance
  - prior-run vs current-run interaction drift
- Mandatory temporal stability analysis:
  - fold-over-fold rank correlation
  - normalized importance drift
  - stability bucket per feature
- Mandatory baseline drift analysis:
  - compare each retrain's SHAP against the prior approved run
  - record rank deltas, importance deltas, cohort deltas, and interaction deltas
- Mandatory Diagnostician path:
  - query key is `run_id + interaction_id`
  - resolve raw SHAP artifact via `ag_artifacts`
  - return the per-trade waterfall and top interaction-pair contributions
- Feature decision protocol is locked:
  - first run includes every point-in-time-safe available feature
  - no auto-drop after first run
  - `REVIEW_DROP` only after 3 consecutive runs of negligible global importance, no cohort prominence, and no strong interaction role
  - actual removal requires explicit approval after SHAP evidence is recorded

## Phase 6: Cloud Serving and Manual Promotion

- Keep current linked projects:
  - Vercel project `warbird-pro`
  - Supabase project `qhwgrzqjcdtdqppvhhme`
- Promotion is manual:
  - local training and SHAP complete first
  - publish-up happens only after explicit approval/promotion
- Cloud receives only these published serving surfaces:
  - `warbird_signals_15m`
  - `warbird_signal_events`
  - `warbird_packets`
  - `warbird_packet_activations`
  - `warbird_packet_metrics`
  - `warbird_packet_feature_importance`
  - `warbird_packet_recommendations`
  - `warbird_packet_setting_hypotheses`
  - `warbird_active_packet_metrics_v`
  - `warbird_active_training_run_metrics_v`
  - `warbird_active_packet_feature_importance_v`
  - `warbird_active_packet_recommendations_v`
  - `warbird_active_packet_setting_hypotheses_v`
  - `warbird_active_signals_v`
  - `warbird_admin_candidate_rows_v`
  - `warbird_candidate_stats_by_bucket_v`
  - `job_log`
  - `mes_1m`, `mes_15m`, `mes_1h`, `mes_4h`, `mes_1d`
  - `cross_asset_1h`, `cross_asset_15m`
  - `econ_calendar`
  - `econ_rates_1d`, `econ_yields_1d`, `econ_fx_1d`, `econ_vol_1d`, `econ_inflation_1d`, `econ_labor_1d`, `econ_activity_1d`, `econ_money_1d`, `econ_commodities_1d`, `econ_indexes_1d`
- Cloud never receives:
  - `ag_fib_snapshots`
  - `ag_fib_interactions`
  - `ag_fib_outcomes`
  - `ag_training`
  - raw features
  - raw labels
  - raw SHAP matrices
  - raw SHAP interaction matrices
- Cloud migration drift must be verified before cloud schema work resumes.
- Current known drift remains an execution check, not an architecture blocker.

## Validation and Acceptance

- Doc acceptance:
  - all three authority docs reflect the new architecture
  - no stale version-suffix canonical naming remains
  - no stale cloud-as-warehouse language remains
- Warehouse acceptance:
  - `warbird` exists
  - approved `2020+` bootstrap completes
  - `HG` exists
  - `econ_calendar` canonical timestamp is correct
  - `mes_4h` derives deterministically from `mes_1h`
- Contract acceptance:
  - the three AG tables match `docs/contracts/ag_local_training_schema.md`
  - `ag_training` matches the canonical SQL view definition
  - the view filter is exactly `WHERE outcome_label != 'CENSORED'`
- Training acceptance:
  - temporal split rules hold
  - naive baseline is logged
  - multiclass metrics are logged
  - no leakage is found
- SHAP acceptance:
  - raw per-row SHAP exists
  - raw SHAP interactions exist
  - feature, cohort, interaction, temporal stability, and run drift summaries all populate
  - per-trade waterfall lookup works
- Cloud acceptance:
  - only approved serving surfaces are published
  - frontend and TV use cloud-serving read models only
  - no local warehouse truth is exposed directly to cloud consumers

## Operational Sources

- Vercel environment workflow: [vercel env pull](https://vercel.com/docs/cli/env)
- Supabase migration workflow: [database migrations](https://supabase.com/docs/guides/deployment/database-migrations)
- Supabase local/CLI reference: [CLI local development](https://supabase.com/docs/guides/cli/local-development)
