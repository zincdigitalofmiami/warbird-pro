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
  - `mes_1m`
  - `cross_asset_1d`
  - all news surfaces
  - all options surfaces
  - all legacy setup/trade/news tables
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
  - `scripts/ag/` exists but only contains `.gitkeep` and `local_warehouse_schema.sql`; there is no Phase 4 pipeline implementation yet.
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
- Phase 0 completion remains blocked until `docs/contracts/ag_local_training_schema.md`
  is staged in git.

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

### Pine Budget Baseline (v7-warbird-institutional.pine)

  Plot budget:    35 / 64
  Request budget:  4 / 40

All additions must be priced against these baselines before any code is written.
Any implementation exceeding 64 plots or 40 request calls is invalid without
an explicit approved recount.

### Platform Constraints (Hard Rules)

`request.footprint()` is budget-constrained and must be designed as a single cached
source per bar for all footprint-derived features.

Two confidence tiers are required for all exhaustion-dependent outputs:
  Tier 1 (full):    geometry + Z-score + footprint confirmed
  Tier 2 (reduced): geometry + Z-score only, footprint returned `na` or unavailable
  Both tiers are first-class signal states with distinct visual rendering.

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

### Backtesting Protocol Locks

- Deep Backtesting for multi-regime coverage.
- Bar Magnifier for intrabar order-of-fill realism.
- Walk-forward IS/OOS only with one-session embargo minimum.
- Commission/slippage floors required in all reported strategy results.
- Parameter sweeps must report trade frequency and precision jointly.

## Phase 1: Local Warehouse Creation
- Create a clean local database named `warbird`.
- Use a dedicated local migration system in `local_warehouse/migrations/`.
- Add a local migration ledger table named `local_schema_migrations`.
- Keep cloud migrations in `supabase/migrations/` only.
- Default schema choice is locked to `public` with canonical snake_case table names and no secondary schema split.

## Phase 2: One-Time Bootstrap from `rabid_raccoon`
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

## Phase 3: Canonical AG Schema
- Implement **three canonical local AG tables and one canonical training view.**
- Implement the three canonical local AG tables exactly as provided:
  - `ag_fib_snapshots`
  - `ag_fib_interactions`
  - `ag_fib_outcomes`
- Implement `ag_training` exactly as defined in `docs/contracts/ag_local_training_schema.md`.
- `ag_training` must use `WHERE outcome_label != 'CENSORED'`.
- No versioned canonical name is allowed.
- The canonical warehouse truth remains these three tables plus the supporting market/macro source tables, with `ag_training` as the canonical view over them. Stop-family comparisons and SHAP lineage expand around this base contract; they do not replace it.

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
