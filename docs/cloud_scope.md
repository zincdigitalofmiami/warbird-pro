# Warbird Cloud Scope

**Date:** 2026-04-10
**Status:** Active Cloud Whitelist
**Governing plan:** Warbird Full Reset Plan v5

This document is the only authority for what may exist in cloud Supabase (`qhwgrzqjcdtdqppvhhme`).

If a cloud table, view, function, or blob-serving surface is not listed here, it is out of scope until explicitly approved here first.

Cloud promotion is manual. Local training and SHAP must complete first; publish-up happens only after explicit approval.

## 1. Allowed Cloud Surfaces (Named)

Only the surfaces listed below are allowed in cloud Supabase.

### 1.1 Runtime Signal and Operator Read Surfaces

- `warbird_signals_15m`
- `warbird_signal_events`
- `warbird_active_signals_v`
- `warbird_admin_candidate_rows_v`
- `warbird_candidate_stats_by_bucket_v`

### 1.2 Packet Distribution Surfaces

- `warbird_packets`
- `warbird_packet_activations`
- `warbird_packet_metrics`
- `warbird_packet_feature_importance`
- `warbird_packet_recommendations`
- `warbird_packet_setting_hypotheses`

### 1.3 Published Model Diagnostics and Admin Read Models

- `warbird_active_packet_metrics_v`
- `warbird_active_training_run_metrics_v`
- `warbird_active_packet_feature_importance_v`
- `warbird_active_packet_recommendations_v`
- `warbird_active_packet_setting_hypotheses_v`

These are published/read-model surfaces. They are not permission to copy local AG lineage tables directly.

### 1.4 Market Data Serving Surfaces

- `mes_1m`, `mes_15m`, `mes_1h`, `mes_4h`, `mes_1d`
- `cross_asset_1h`, `cross_asset_15m`
- `econ_calendar`
- `econ_rates_1d`, `econ_yields_1d`, `econ_fx_1d`, `econ_vol_1d`, `econ_inflation_1d`, `econ_labor_1d`, `econ_activity_1d`, `econ_money_1d`, `econ_commodities_1d`, `econ_indexes_1d`

### 1.5 Operational Logging Surfaces

- `job_log`

### 1.6 Real-Time Capture Relay Surfaces

These surfaces exist in cloud solely as automated capture relay points.
They are NOT serving surfaces, NOT mirrors of local warehouse truth, and
NOT permanent cloud storage. They exist only to bridge the gap between
the always-on TradingView server-side alert system and the local warehouse
nightly sync. Rolling retention only — local warbird holds full history.

- `indicator_snapshots_15m`
  Populated by: Supabase Edge Function `indicator-capture` receiving Pine alert webhooks
  Written: once per 15m bar close at `barstate.isconfirmed`
  Retention: rolling ~90 days (sufficient for nightly sync lag tolerance)
  Consumed by: nightly Python sync job pulling to local warbird
  Scope exception rationale: TV alerts are server-side and require a reachable
  endpoint. Cloud Edge Function is the only reliable always-on receiver.
  Local warbird is the canonical truth. Cloud holds the relay window only.

Review rule override for section 1.6 surfaces:
  These surfaces answer Yes to question 1 (they serve the automated training
  data pipeline which is required for live indicator support) and Yes to
  question 2 (local canonical truth remains complete — local holds full history).
  They are approved as capture relay surfaces, not as warehouse extensions.

## 2. Explicitly Out Of Scope For Cloud

These belong in the local canonical `warbird` warehouse unless explicitly reapproved:

- `ag_fib_snapshots`
- `ag_fib_interactions`
- `ag_fib_outcomes`
- `ag_training`
- raw features
- raw labels
- raw SHAP matrices
- raw SHAP interaction matrices
- training datasets
- fold tables
- experiment tables
- full packet registry history
- full activation or rollback lineage used only for research or audit
- abandoned experiment or agent-created warehouse tables
- large historical bar warehouses beyond the cloud serving window
- research-only macro or context warehouses
- SHAP lineage tables (`ag_training_runs`, `ag_training_run_metrics`, `ag_artifacts`, `ag_shap_feature_summary`, `ag_shap_cohort_summary`, `ag_shap_interaction_summary`, `ag_shap_temporal_stability`, `ag_shap_feature_decisions`, `ag_shap_run_drift`)

## 3. Candidate Retirement Backlog

These object families are removal candidates if they still exist in live cloud and are not explicitly reapproved:

- legacy Warbird operational tables:
  - `warbird_triggers_15m`
  - `warbird_conviction`
  - `warbird_risk`
  - `warbird_setups`
  - `warbird_setup_events`
  - `measured_moves`
  - `warbird_forecasts_1h`
- training-only or warehouse-like tables carrying wide features, labels, experiments, or raw SHAP outputs
- abandoned one-off agent or experiment objects not required by the active UI or runtime contract

Live existence must be verified directly before any drop is claimed.

## 4. Safe Deletion Protocol

### Phase A: Deprecate

- classify the object
- document the reason it is out of scope
- stop all new writers

### Phase B: Detach Readers

- remove frontend, API, admin, and compat-view dependencies
- verify no active runtime path still reads the object

### Phase C: Drop

- drop dependent views first
- drop tables second
- drop functions last if they are no longer referenced

### Phase D: Block Regression

- reject new cloud objects unless they are added to this whitelist first
- reject new cloud warehouse patterns in reviews and migrations

## 5. Review Rule

Before any cloud schema change is approved, answer these questions:

1. Does this object serve live frontend, indicator-support runtime, packet distribution, curated SHAP serving, or operational health?
2. If cloud lost this object, would local canonical truth still remain complete?
3. Could this object be replaced by a published read model instead of storing warehouse truth in cloud?

If the answer to question 1 is no, the object does not belong in cloud.
