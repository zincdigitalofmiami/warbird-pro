# 2026-03-28 Schema + Admin Contract Handoff

## Decision

Lock the Warbird architecture around the MES 15m fib candidate outcome contract, preserve canonical cloud tables for point-in-time setup/path/signal truth only, keep raw research surfaces local, and expose Admin through structured packet and candidate views instead of Markdown report blobs.

This handoff captures the current checkpoint truth so a new chat can resume from repository state instead of reconstructed context.

## Repository Reality

### Locked architecture decisions

1. The outcome contract drives the platform. The current model family does not.
2. Warbird is split into three roles:
   - `Generator`: Pine + admitted exact-copy harnesses define the candidate object.
   - `Selector`: offline model stack scores frozen candidates.
   - `Diagnostician`: research stack explains wins, losses, feature value, and entry-definition changes.
3. Canonical trade object is one frozen MES 15m fib candidate at bar close in `America/Chicago`.
4. Canonical cloud tables store setup truth, realized path truth, and published decision/signal lineage.
5. Local research tables store raw SHAP, stop-out attribution, ablations, and entry-definition experiments.
6. `EXPIRED` and `NO_REACTION` are not canonical economic truth labels.
7. Unresolved rows at the edge of observation remain `OPEN` until resolution.
8. Admin must render structured data, not Markdown blobs.

### Major drift findings from the repo audit

1. Remote Supabase migration ledger only records through `20260326000017`; later schema work exists only locally or was applied directly.
2. Canonical 2026-03-30 schema was missing or incomplete in cloud when audited.
3. Live setup generation was effectively dead because continuity logic rejected the normal CME daily maintenance gap.
4. Runtime remained hardwired to legacy `warbird_*` and `measured_moves` tables.
5. `detect-setups` and `score-trades` were still App Router routes, not Supabase Edge Functions.
6. Active Pine indicator was not TradingView-loadable due to undeclared `isValid` and `atr`.
7. Pine lint/parity guardrails were materially misleading or stale.
8. Training/data contract drift existed between legacy dataset builders, the live indicator, and the locked candidate contract.

### Research conclusions locked into the design

1. The target should be extension attainment vs stop failure on a frozen candidate, not generic price forecasting.
2. `TP2` does not need a separate "first" path target because `TP2` implies `TP1`.
3. The meaningful binary path questions are:
   - `tp1_before_sl`
   - `tp2_before_sl`
   - `sl_before_tp1`
4. If there is no trade expiry, unresolved rows should remain `OPEN` rather than being mislabeled as failures.
5. AutoGluon is the first selector layer, not the architecture owner.
6. SHAP is diagnostic/promotional, not schema-defining.
7. Quantile/pinball models are for excursions and uncertainty bands, not the core extension-hit truth.
8. Monte Carlo belongs in downstream policy simulation, not label definition.

## Options Evaluated

### 1. Keep legacy surfaces alive and patch around them
- Fastest path to visible rows.
- Rejected because it deepens object drift and keeps Admin/API bound to the wrong contract.

### 2. Push raw research outputs directly into the live dashboard schema
- Would make SHAP and experiment outputs immediately visible.
- Rejected because it lets experiment churn dictate canonical schema and operator contracts.

### 3. Separate canonical truth from research surfaces, then publish distilled Admin data
- Canonical cloud schema stores setup/path/signal truth plus stable packet/reporting surfaces.
- Local warehouse holds raw explainability and experiment outputs.
- Accepted. This is the current locked direction.

## Reasoning

The repo had two separate problems:

1. architectural drift
2. operational drift

Architectural drift came from allowing old trigger/setup/forecast surfaces, raw research concepts, and changing model ideas to bleed into the production contract.

Operational drift came from canonical migrations not being live, App Router bridge code still acting as core writers, and Admin/dashboard surfaces still reading legacy tables.

The safest correction was:

1. lock the hierarchy and truth semantics first
2. rewrite the draft schema package against that lock
3. preserve raw research data locally
4. publish only stable Admin-ready packet/candidate surfaces to cloud

This gives three concrete advantages:

1. dataset truth stays stable while model families evolve
2. Admin can show rich model/training output without coupling the UI to raw experiment artifacts
3. next implementation work becomes a bounded writer/API cutover instead of another architecture debate

## Implemented Artifacts In Repo

### Canonical docs updated and pushed
- `CLAUDE.md`
- `WARBIRD_MODEL_SPEC.md`
- `docs/plans/2026-03-20-ag-teaches-pine-architecture.md`

### Draft schema package reconciled and pushed
- `supabase/migrations/20260330000037_canonical_warbird_tables.sql`
- `supabase/migrations/20260330000038_canonical_warbird_compat_views.sql`
- `scripts/ag/local_warehouse_schema.sql`

### Cloud publish-up entities now defined in the draft contract
- `warbird_training_runs`
- `warbird_training_run_metrics`
- `warbird_packets`
- `warbird_packet_activations`
- `warbird_packet_metrics`
- `warbird_packet_feature_importance`
- `warbird_packet_setting_hypotheses`
- `warbird_packet_recommendations`

### Canonical point-in-time entities now defined in the draft contract
- `warbird_fib_engine_snapshots_15m`
- `warbird_fib_candidates_15m`
- `warbird_candidate_outcomes_15m`
- `warbird_signals_15m`
- `warbird_signal_events`

### Local-only research entities now defined in the draft contract
- `warbird_shap_results`
- `warbird_shap_indicator_settings`
- `warbird_snapshot_pine_features`
- `warbird_candidate_macro_context`
- `warbird_candidate_microstructure`
- `warbird_candidate_path_diagnostics`
- `warbird_candidate_stopout_attribution`
- `warbird_feature_ablation_runs`
- `warbird_entry_definition_experiments`

### Admin-facing views now defined in the draft contract
- `warbird_active_signals_v`
- `warbird_admin_candidate_rows_v`
- `warbird_active_training_run_metrics_v`
- `warbird_active_packet_metrics_v`
- `warbird_active_packet_feature_importance_v`
- `warbird_active_packet_setting_hypotheses_v`
- `warbird_active_packet_recommendations_v`

## Admin Contract Lock

Admin is explicitly expected to show both of these:

1. screenshot-style candidate/signal rows
   - time
   - direction
   - anchor
   - target
   - retrace
   - fib ratio
   - target-hit state
   - outcome state
   - status
   - packet/model probabilities
2. full model/training output
   - all run metrics
   - packet KPIs
   - feature drivers
   - setting hypotheses
   - AI-generated recommendations

Admin must not depend on Markdown report blobs.

## Verification Checklist

Completed during this checkpoint:

1. Reconciled docs and draft schema to the 2026-03-28 hierarchy lock.
2. Replaced Markdown report direction with structured Admin packet surfaces.
3. Added screenshot-style Admin row view and full training-metrics view.
4. Validated `037`, `038`, and local warehouse DDL in a disposable Postgres 17 instance.
5. Pushed the checkpoint directly to `main`.

Validation result:

- `037 OK`
- `038 OK`
- `local OK`

Saved commit prior to this handoff artifact:

- `79ba4cd` `Lock canonical schema and admin packet contract`

## Work Intentionally Not Done In This Checkpoint

1. No remote Supabase apply was performed.
2. No `/api/admin/status` cutover was implemented.
3. No Admin UI TSX cutover was implemented.
4. No writer cutover from App Router to Edge Functions was implemented.
5. No Pine compile/plot-budget repair was implemented.
6. No legacy table retirement was performed.

## Current Blockers

### Immediate blocker
Implement the canonical writer checkpoint:

1. port or replace `detect-setups`
2. port or replace `score-trades`
3. write canonical rows into the new snapshot/candidate/outcome/signal surfaces
4. fix CME continuity-gap handling before enabling the writer path live

### Next blocker after that
Cut readers over:

1. `/api/admin/status`
2. Admin page
3. `/api/warbird/*`
4. dashboard/chart read surfaces

### Then
1. Pine recovery (`isValid`, `atr`, plot budget)
2. local selector workbench and packet publish-up implementation
3. legacy table retirement

## Current Exclusions From Git Commit Scope

These local changes existed and were intentionally not included in the architecture/schema commit:

- `components/charts/LiveMesChart.tsx`
- `supabase/.temp/cli-latest`
- `.github/`
- `.tmp/`

A new chat should not assume those files are part of the locked checkpoint.

## Implementation Implications For The Next Chat

The next chat should start from this sequence:

1. Read:
   - `AGENTS.md`
   - `CLAUDE.md`
   - `WARBIRD_MODEL_SPEC.md`
   - `docs/plans/2026-03-20-ag-teaches-pine-architecture.md`
   - this handoff doc
2. Treat the schema/admin contract as locked.
3. Do not reopen Markdown report storage.
4. Do not reopen raw SHAP into cloud/dashboard.
5. Do not create another unresolved branch unless explicitly required.
6. Work directly on the next blocker: canonical writer cutover, then Admin/API reader cutover.

## Sources

### Repo sources
- `AGENTS.md`
- `CLAUDE.md`
- `WARBIRD_MODEL_SPEC.md`
- `docs/plans/2026-03-20-ag-teaches-pine-architecture.md`
- `app/api/admin/status/route.ts`
- `app/(workspace)/admin/page.tsx`
- `supabase/migrations/20260330000037_canonical_warbird_tables.sql`
- `supabase/migrations/20260330000038_canonical_warbird_compat_views.sql`
- `scripts/ag/local_warehouse_schema.sql`

### External research sources used in the checkpoint
- AutoGluon install docs: https://auto.gluon.ai/stable/install.html
- AutoGluon TabularPredictor docs: https://auto.gluon.ai/dev/api/autogluon.tabular.TabularPredictor.html
- AutoGluon custom metric docs: https://auto.gluon.ai/stable/tutorials/tabular/advanced/tabular-custom-metric.html
- AutoGluon release notes: https://auto.gluon.ai/stable/whats_new/index.html
- mlfinpy labeling docs: https://mlfinpy.readthedocs.io/en/stable/Labelling.html
- scikit-survival competing risks guide: https://scikit-survival.readthedocs.io/en/latest/user_guide/competing-risks.html
- scikit-survival cumulative incidence docs: https://scikit-survival.readthedocs.io/en/latest/api/generated/sksurv.nonparametric.cumulative_incidence_competing_risks.html
- SHAP TreeExplainer docs: https://shap.readthedocs.io/en/latest/generated/shap.TreeExplainer.html
