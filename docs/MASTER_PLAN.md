# Warbird Full Reset Plan v5: External-Drive Local Warehouse, AG Training View, Full SHAP

## Summary

- This plan is decision complete. No further repo-level architecture locks remain before execution.
- Canonical split is fixed:
  - local `warbird` on PG17 `127.0.0.1:5432` = full data zoo, canonical warehouse, training, artifacts, raw SHAP, diagnostics
  - cloud Supabase `qhwgrzqjcdtdqppvhhme` + Vercel `warbird-pro` = serving-only for frontend, TradingView/indicator support, packets, dashboard/admin read models, and curated SHAP/report surfaces
- Canonical local AG contract is **four canonical local AG tables and one canonical training view.**
  - tables: `ag_fib_snapshots`, `ag_fib_interactions`, `ag_fib_stop_variants`, `ag_fib_outcomes`
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
  only exists to derive `5m` execution context. `15m` remains the owning fib map
  and may emit the parent-bar execution state directly.
- First macro scope is locked to the curated FRED regime set + `econ_calendar`.
- Cloud promotion is locked to `manual promote`.

## Execution Supplement Reference

- `docs/WARBIRD_V8_PLAN.md` is the active team execution supplement for the
  SuperTrend + TQI slice workflow.
- Use it for slice sequencing, handoff contracts, and Approval & Drift Gates
  (Kirk approve -> Codex execute -> Claude review -> Kirk close).
- This supplement does **not** replace this master plan as the architecture
  authority; it governs execution discipline for the v8 lane.
- v8 gate protocol: see `docs/WARBIRD_V8_PLAN.md` § Approval & Drift Gate

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

## 2026-04-22 Execution Checkpoint — Optuna Operator Surface

- Verified local Optuna entrypoint is canonical on `http://localhost:8090`.
  The legacy `http://localhost:8080` compatibility redirect and its launchd
  agent were retired on 2026-04-23; 8090 is now the sole operator surface.
- The hub now treats the real on-disk workspace set under
  `scripts/optuna/workspaces/` as authoritative for visible lanes. It no longer
  auto-creates empty workspace folders from registry intent.
- Child `optuna-dashboard` processes are lazy-launched through
  `/open-study/<key>` instead of pre-spawned on every hub load, which removes
  the prior idle scientific-Python bloat pattern from the default operator path.
- Auto-refresh now reloads the current URL instead of the original response URL,
  so filter and sort state persist across refresh windows.
- `warbird_pro_sniper` is retired from the active local Optuna surface.
  Verified live workspaces on disk are `v7_warbird_institutional` and
  `warbird_nexus_ml_rsi`.
- Browser verification completed against the live hub:
  - filter state persists across refresh
  - sort state persists across refresh
  - both surviving study UIs launch on demand
- This checkpoint is operator-surface hardening only. It does not change the
  canonical MES/AG contract or the active Phase 4 / Phase 5 blockers.

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
- Execution becomes a subordinate micro execution layer attached to that parent setup.
  The parent defines the map and target ladder. The micro layer defines when the
  operator should engage.
- `5m` and parent-bar `15m` are the admitted execution timeframes. `5m` is
  derived from canonical local `mes_1m` and exists only as execution context
  around the active parent map; `15m` remains the only fib owner and is not a
  second trade object.
- Order-flow is first-class execution evidence. Fibs are the map; order-flow at
  the level is the trigger.
- Pine runtime vocabulary for the micro execution layer is locked to:
  - `FORMING`
  - `READY`
  - `TRADE_ON`
  - `INVALIDATED`
  - `EXPIRED`
- First admitted micro execution patterns:
  - `PULLBACK_HOLD`
  - `FAILED_RECLAIM`
  - `CLIMAX_REVERSAL`
  - `FAILED_EXPANSION`
- Child states must remain point-in-time safe and keyed back to the same parent
  15m setup. They do not create a second canonical trade object.
- Child execution direction is now an explicit field on the parent row. It may
  match the parent map or oppose it when the lower timeframe emits a legal
  failure trigger against the active 15m context.
- Historical backfill may use real `mes_1m` OHLCV-derived microstructure plus
  TradingView footprint capture where available. Do not claim full-history
  footprint truth until a real lower-timeframe capture path exists.
- Current tuner profile `mes15m_agfit_v3` is a parent-settings sweep only. It
  is not authorized to choose `5m` trigger policy versus parent-bar `15m`
  execution. A separate micro-execution tuning profile is required.
- 2026-04-14 parent-owner fib freeze landed:
  - canonical `15m` fib owner is now locked to `Deviation=4`, `Depth=20`,
    `Threshold Floor=0.50`, `Min Fib Range=0.5`
  - `5m` no longer owns fib anchors; it remains execution-only context around
    the active parent map
  - live Pine defaults and local AG reconstruction now share the same frozen
    15m owner settings

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
  micro execution-state reconstruction. This does not change the completed
  Phase 2 bootstrap facts above and does not create a new primary trade object.

## Phase 3: Canonical AG Schema — COMPLETE 2026-04-11

- Implement **four canonical local AG tables and one canonical training view.**
- Implement the four canonical local AG tables exactly as provided:
  - `ag_fib_snapshots`
  - `ag_fib_interactions` — stop-agnostic parent interaction surface
  - `ag_fib_stop_variants` — stop-specific candidate surface; one row per (interaction, stop family)
  - `ag_fib_outcomes`
- Implement `ag_training` exactly as defined in `docs/contracts/ag_local_training_schema.md`.
- `ag_training` must use `WHERE outcome_label != 'CENSORED'`.
- No versioned canonical name is allowed.
- The canonical warehouse truth remains these four tables plus the supporting market/macro source tables, with `ag_training` as the canonical view over them.

**Verified 2026-04-11 (original three-table schema):** Migration `007_ag_schema.sql` applied. Tables `ag_fib_snapshots`, `ag_fib_interactions`, `ag_fib_outcomes` and view `ag_training` live in `warbird`. Censored filter (`WHERE outcome_label != 'CENSORED'`) present.
**Contract expansion (migration 016):** `ag_fib_stop_variants` added; `ag_fib_interactions` made stop-agnostic; `ag_fib_outcomes` re-keyed to `stop_variant_id`; `ag_training` rebuilt with four-way join. Stop-family evaluation now produces six training rows per parent interaction.

## Phase 4: Python Pipeline in `scripts/ag/`

> **2026-04-16:** Phase 4 execution front replaced by v8 SuperTrend+TQI architecture.
> Active execution document: `docs/WARBIRD_V8_PLAN.md`. MASTER_PLAN.md remains governance spine.

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
- First feature scope is locked to `MES 1m/15m/1h/4h + SP500 spot + macro`.
- Current operational truth for that scope:
  - `MES 1m/15m/1h/4h` = admitted locally
  - `SP500` = daily FRED regime series in the first trainer cut
  - true intraday S&P 500 cash spot remains a separate admission task if reopened
- S/R feature scope is locked to per-type wide numeric families as specified in
  Phase 0.5 and `docs/contracts/ag_local_training_schema.md`. Expected budget: 25-35 columns.
- Behavioral features (`ml_session_tier` through `ml_favorable_excursion_pts`) are
  first-run scope. Spec in Phase 0.5 and `docs/contracts/ag_local_training_schema.md`.
- Exhaustion / continuation / diamond features (`ml_exh_*`, `ml_cont_*`) are
  tuning-only in the first run. Keep them out of the canonical AG training
  matrix and any production predictor SHAP. Use a separate sidecar tuning/SHAP
  study if their setting sensitivity needs explanation later.
- Indicator snapshot features (from automated webhook pipeline) are first-run scope.
  Sourced from `indicator_snapshots_15m` local table via nightly sync from cloud capture.
- Micro-execution features are reopened for first-run scope under the
  2026-04-14 delta: local `mes_1m` supplies the canonical backfill tape,
  `5m` is derived on read, and order-flow / footprint evidence attaches to
  the parent 15m setup as micro execution-state context.
- Live trade review loss drivers are required as feature-engineering context for Phase 4.
- Macro scope is locked to:
  - curated FRED regime set
  - `econ_calendar`
  - no news or narrative sources
  - curated FRED list:
    `SP500`, `DFF`, `SOFR`, `T10Y2Y`, `DGS2`, `DGS5`, `DGS10`, `DGS30`, `DGS3MO`,
    `DFEDTARL`, `DFEDTARU`, `CPIAUCSL`, `CPILFESL`, `PCEPILFE`, `T5YIE`, `T10YIE`,
    `DFII5`, `DFII10`, `DTWEXBGS`, `DEXUSEU`, `DEXJPUS`, `VIXCLS`, `VXNCLS`,
    `RVXCLS`, `OVXCLS`, `GVZCLS`, `NFCI`
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
  - joins the canonical `ag_training` rows with the curated `FRED/econ_calendar` regime context
  - strips realized-outcome leakage before training
  - writes local run artifacts under `artifacts/ag_runs/`
  - blocks training when validation/test slices collapse below 2 target classes
  - trainer defaults now force `presets=best_quality`, `time_limit=3600`,
    `num_bag_folds=0`, `num_stack_levels=0`, `dynamic_stacking=off`
  - AutoGluon internal ensembling is blocked by default for the MES
    walk-forward harness: no IID bagging, no stacking, no weighted ensemble
    unless a purged temporal child splitter is explicitly implemented and approved
- verified current local training-state facts:
  - `ag_training` label distribution:
    - `STOPPED`: 15,893
    - `TP5_HIT`: 1,114
    - `TP1_ONLY`: 74
    - `TP2_HIT`: 19
  - no trained predictor artifact currently exists under `artifacts/`
  - `autogluon` is not installed in the active local Python environment, so
    `TabularPredictor.fit()` cannot complete in this workspace yet

**Checkpoint 2026-04-14:** subordinate micro-execution scaffold landed.
Outputs:
- migration `011_mes_1m_micro_execution.sql` applied to local `warbird`
  - created local `mes_1m`
  - added micro execution fields (`ml_exec_*`) to `ag_fib_interactions`
  - recreated `ag_training` so the new fields surface in training reads
- loader `local_warehouse/bootstrap/load_mes_1m_from_parquet.py` added
- project-home source `data/mes_1m.parquet` loaded into local `warbird.mes_1m`
  - row count: `2,207,167`
  - range: `2020-01-01 17:00:00-06` -> `2026-04-03 08:14:00-05`
- `scripts/ag/build_ag_pipeline.py` updated to read local `mes_1m` and populate
  first micro execution fields on `ag_fib_interactions`
- rebuild completed successfully:
  - `bars_loaded`: `147,860`
  - `micro_bars_loaded`: `2,207,167`
  - `agfit_20260414T112223Z` split manifest written under `artifacts/ag_runs/`
- project-home data hygiene completed on `2026-04-14`:
  - `data/mes_1m.parquet` deduplicated from `3,237,058` rows to `2,207,167`
    unique `(ts, symbol)` rows
  - `data/mes_1h.parquet` deduplicated from `105,130` rows to `36,937`
    unique `(ts, symbol)` rows
  - legacy options backup CSVs removed from `data/local-db-backups/`
- current micro execution implementation is an OHLCV-derived microstructure
  scaffold only. Footprint-specific micro fields remain unavailable until
  lower-timeframe capture is wired.

Remaining Phase 4 blocker after this checkpoint:
- micro execution semantics still need Pine/runtime admission. The local
  training pipeline now emits `ml_exec_*`, but the chart surface does not yet
  expose `FORMING -> READY -> TRADE_ON -> INVALIDATED -> EXPIRED`.
- micro pattern math still needs a second pass against real live tape examples.
  The current implementation is a deterministic 1m OHLCV scaffold, not the
  final order-flow contract.
- the warehouse micro-state contract now treats stale `FORMING` / `READY` rows as
  `EXPIRED` once they drift `>= 1.5 ATR` from the pocket without printing more
  than `0.15 ATR` of fresh impulse.
- local validation on 2026-04-14: `EXPIRED` populated `968` micro rows, with
  `901 STOPPED`, `1 TP5_HIT`, and the remainder unresolved or minor-path cases.
  That is strong enough to keep the stale-state rule in the warehouse contract.
- local bootstrap on 2026-04-14 extended canonical `mes_1m` to
  `2026-04-14 08:40 America/Chicago` using direct Databento historical
  `GLBX.MDP3 / MES.c.0 / ohlcv-1m`, then rolled local `mes_15m` forward to
  `2026-04-14 08:15 America/Chicago` from canonical local `mes_1m`.
- first April 14 warehouse audit now has real parent+micro coverage through the
  morning tape. Current result: micro-execution rows at `05:00`, `05:30`, `05:45`,
  `06:00`, and `06:15` are all parent-aligned longs; `06:00` and `06:15` are
  `TRADE_ON`. No counter-direction short row is emitted during the failure
  sequence the operator marked as obvious.
- repair landed on 2026-04-14: micro execution direction is now explicit on
  the parent row, and the warehouse can emit counter-direction failure triggers
  without creating a second trade object.
- verified on 2026-04-14 morning tape before the `5m/15m` scope cut: the
  `05:45 America/Chicago` parent row emitted `ml_exec_direction_code = -1`,
  `ml_exec_tf_code = 3`, `ml_exec_state_code = TRADE_ON`, `ml_exec_pattern_code = FAILED_RECLAIM`,
  and `ml_exec_orderflow_bias = -1` while the parent 15m `direction` remains
  `1` (long). That is the first warehouse-proof of the missed failure short.
- AG-ready contract decision: stop adding micro-route taxonomy by hand. The
  admitted micro surface is the primitive feature family already on the parent
  row (`ml_exec_tf_code`, `ml_exec_direction_code`, `ml_exec_state_code`,
  `ml_exec_pattern_code`, pressure, imbalance, and target-leg context). AG and
  SHAP decide what survives; warehouse work should not pre-commit an extra
  routing policy first.
- the tuner must split into two scopes:
  - parent 15m fib/settings profile
  - micro 5m/15m execution profile
- evaluation-policy repair for the current `outcome_label` regime. Verified on 2026-04-13: `TP1_ONLY` disappears after 2022-06-28 and 2024+ is nearly all `STOPPED`, so several time-safe multiclass folds are structurally invalid.
- ZigZag contract drift remains unresolved across docs, Pine runtime, and Python reconstruction. Do not claim reproducible AG/Pine parity until one depth contract is selected and enforced everywhere.
- 2026-04-14 Phase 5 spine landed:
  - migration `014_ag_training_run_lineage.sql` creates local lineage/reporting tables in `warbird`:
    `ag_training_runs`, `ag_training_run_metrics`, `ag_artifacts`,
    `ag_shap_feature_summary`, `ag_shap_cohort_summary`,
    `ag_shap_interaction_summary`, `ag_shap_temporal_stability`,
    `ag_shap_feature_decisions`, `ag_shap_run_drift`
  - `scripts/ag/train_ag_baseline.py` now writes run metadata, fold metrics,
    and artifact registry rows for dry runs and real fits
  - verified with dry run `agtrain_20260414T183606833153Z`: `ag_training_runs`
    row present (`SUCCEEDED`, `dry_run=true`), baseline fold metrics written,
    and dataset/feature/fold/training artifacts registered in `ag_artifacts`
  - raw SHAP summary tables remain intentionally empty until the first fitted run emits SHAP artifacts
- current first-run feature parity gap:
  - the trainer admits `SP500` from the curated daily FRED regime set
  - true intraday S&P 500 cash spot is not yet admitted into local `warbird`
- 2026-04-14 evaluation-policy repair landed in `scripts/ag/build_ag_pipeline.py`:
  rows are now censored only when the full forward observation window is not
  observable at the end of the available history. Rows that complete the full
  window but stop short of `TP5` keep their realized `highest_tp_hit` class
  (`TP1_ONLY` through `TP4_HIT`) instead of being mislabeled `CENSORED`.
- 2026-04-14 follow-on repair landed:
  - migration `015_ml_exec_tf_code_scope_cut.sql` aligns the live warehouse
    constraint with the active `ml_exec_tf_code` contract (`0`, `5`, `15`)
  - `scripts/ag/train_ag_baseline.py` now performs a simple class-aware forward
    search for validation/test windows so the one-year dry run does not die on
    the first single-class slice when a legal later slice exists
  - verified dry run `agtrain_20260414T184346894785Z` on `2020-01-03` through
    `2020-12-31`: `train_rows=3243`, `val_rows=682`, `test_rows=354`,
    `val_class_count=3`, `test_class_count=3`
- 2026-04-14 owner-freeze rebuild landed:
  - `scripts/ag/build_ag_pipeline.py` now reconstructs the parent 15m map with
    `Deviation=4`, `Depth=20`, `Threshold Floor=0.50`, `Min Fib Range=0.5`
  - rebuild run `agfit_20260414T204213Z` wrote
    `snapshots=2240`, `interactions=54662`, `outcomes=54662`
  - local `ag_fib_snapshots` now verify as one frozen contract:
    `zz_deviation=4`, `zz_depth=20` across all `2240` rows
- next blocking item: verify the frozen 15m owner behavior on-chart, especially flip/redraw behavior, then complete the first corrected one-year AutoGluon fit and populate the Phase 5 SHAP surfaces from that run.

## Phase 5: Full-Surface SHAP Program

- Full SHAP is mandatory and local-only at raw level.
- Phase 5 lineage spine landed 2026-04-14:
  - `ag_training_runs`
  - `ag_training_run_metrics`
  - `ag_artifacts`
  - `ag_shap_feature_summary`
  - `ag_shap_cohort_summary`
  - `ag_shap_interaction_summary`
  - `ag_shap_temporal_stability`
  - `ag_shap_feature_decisions`
  - `ag_shap_run_drift`
- Remaining Phase 5 work:
  - emit raw SHAP values and interaction artifacts under `artifacts/shap/{run_id}/`
  - populate summary, cohort, interaction, stability, decision, and drift tables from fitted runs
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
