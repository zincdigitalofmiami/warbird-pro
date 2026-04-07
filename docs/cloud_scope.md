# Warbird Cloud Scope

**Date:** 2026-04-07
**Status:** Active Cloud Whitelist

This document is the only authority for what may exist in cloud Supabase.

If a cloud table, view, function, or blob-serving surface is not listed here, it is out of scope until explicitly approved here first.

## 1. Allowed Cloud Categories

### 1.1 Ingress

Allowed purpose:

- receive TradingView or Pine alerts
- validate payloads
- record minimal runtime intake and error state

Allowed object families:

- ingress intake tables
- ingress idempotency ledgers
- retry and DLQ tables
- ingress health views

### 1.2 Frontend Runtime Read Models

Allowed purpose:

- power dashboard and operator UX
- expose live and recent runtime state
- support admin status views

Allowed object families:

- current candidate stream views
- recent signal stream views
- runtime status and health views
- slim operator aggregates
- compat views required by the active UI

### 1.3 Packet Distribution

Allowed purpose:

- serve the current active packet and minimal lineage needed by runtime operators

Allowed object families:

- active packet pointer
- minimal published packet metadata
- packet blob reference or download location
- packet activation surface needed by runtime operators

### 1.4 Curated SHAP And Report Serving

Allowed purpose:

- serve report summaries and operator-friendly model diagnostics

Allowed object families:

- SHAP summary tables
- feature-importance summaries
- report metadata
- artifact URL or path references

Raw SHAP matrices, wide experiment outputs, and research-only diagnostics are local-only.

### 1.5 Operational Logging

Allowed purpose:

- support runtime monitoring, retries, failures, and publish-job health

Allowed object families:

- `job_log`
- ingress and publish job status tables
- runtime health aggregates

## 2. Explicitly Out Of Scope For Cloud

These belong in the local canonical warehouse unless explicitly reapproved:

- large historical bar warehouses
- research-only macro or context warehouses
- canonical lifecycle history beyond the slim runtime subset
- feature tables
- label tables
- training datasets
- fold tables
- experiment tables
- raw SHAP artifacts
- full packet registry history
- full activation or rollback lineage used only for research or audit
- abandoned experiment or agent-created warehouse tables

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
