# Warbird Master Execution Plan

**Date:** 2026-04-07
**Status:** Active Plan - Single Source of Truth
**Scope:** MES 15m fib contract, Pine signal surface, local canonical warehouse, curated cloud runtime subset, AutoGluon packet publish-up

This file is the only planning authority for Warbird.

If any other plan, decision note, scratch doc, or archived checkpoint disagrees with this file, this file wins immediately.

## 0. Binding Rules

### 0.1 Canonical database boundary

- The external-drive local PostgreSQL warehouse is the single canonical database truth.
- The local warehouse owns the full retained data zoo:
  - raw market bars
  - macro and context inputs
  - canonical Warbird lifecycle tables
  - training datasets
  - feature tables
  - label tables
  - training runs
  - metrics
  - SHAP artifacts
  - packet registry
  - activation and rollback history
- This local warehouse is not a mirror of cloud Supabase.
- Still banned:
  - local Supabase
  - Docker-local runtime
  - a third database

### 0.2 Cloud runtime boundary

- Cloud Supabase is runtime-only.
- Cloud contains only what must stay online for:
  - frontend and dashboard UX
  - indicator and alert runtime contract handling
  - operator monitoring
  - packet distribution
  - curated SHAP and report serving
- Cloud must not become a second warehouse.
- Any cloud object not whitelisted in `docs/cloud_scope.md` is retirement debt.

### 0.3 Runtime dependency rule

- Pine remains the canonical live signal surface.
- Cloud ingress must remain durable even if the local warehouse is temporarily unavailable.
- If local canonical write-through is delayed, cloud may queue, retry, and expose degraded runtime status, but it must not silently promote cloud intake rows into warehouse truth.
- The canonical write happens in local PostgreSQL only.

### 0.4 Training refresh rule

- Offline training and research rebuilds are on-demand only.
- No scheduled training-data refreshes.
- Approved triggers:
  - explicit research rebuild
  - explicit retrain run
  - explicit backfill command

### 0.5 Retention and contract rule

- The canonical trade object is the MES 15m fib setup.
- The canonical key is the MES 15m bar close in `America/Chicago`, derived deterministically from the ingress timestamp.
- Core retained history starts at `2020-01-01T00:00:00Z`.
- Pine emits the live candidate surface.
- AutoGluon is offline only and may publish only Pine-safe packet outputs.

## 1. Documentation Authority Reset

### 1.1 Canonical documentation surfaces

- `docs/INDEX.md` is the only entrypoint.
- `docs/MASTER_PLAN.md` is the only planning authority.
- `docs/contracts/` is the only interface authority.
- `docs/cloud_scope.md` is the only cloud-whitelist authority.

### 1.2 Legacy document handling

Every other plan or decision document must be treated as one of the following:

- archived historical reference
- refactored into this master plan
- converted into a contract document under `docs/contracts/`

No new architecture plan, checkpoint plan, or sidecar decision note may be treated as authoritative unless it is linked from `docs/INDEX.md`.

## 2. Architecture Summary

### 2.1 Two-database architecture

- Local PostgreSQL warehouse
  - canonical normalized warehouse
  - owns the full lifecycle, training, features, labels, metrics, SHAP, packets, and historical zoo
- Cloud Supabase
  - minimal runtime ingress
  - curated frontend read models
  - packet distribution metadata
  - curated SHAP and report surfaces
  - operational health logging

### 2.2 Controlled one-way publish model

The allowed direction of truth is:

1. Pine or TradingView emits an alert to cloud ingress.
2. Cloud ingress validates and stores the minimum runtime intake record.
3. Cloud ingress forwards to the local canonical writer or queues a reliable retry.
4. Local canonical writer validates and writes authoritative normalized rows into local PostgreSQL.
5. Local publish jobs push a curated runtime subset back to cloud Supabase.

Cloud is not a canonical lifecycle store.

### 2.3 Required components

- Cloud ingress endpoint
  - Supabase Edge Function or approved Next.js API route
  - validates payload
  - records minimal intake and monitoring rows
  - forwards or queues for local canonical write
- Local canonical writer
  - validates contracts
  - writes canonical normalized tables
  - enforces idempotency
  - records reconciliation state
- Cloud publish job
  - publishes only curated read models, packet metadata, and curated SHAP or report outputs

## 3. Cloud Whitelist

Cloud is allowed to contain only these categories:

1. ingress tables
2. ingress idempotency and retry ledgers
3. runtime frontend read models
4. active packet distribution metadata
5. curated SHAP and report serving tables
6. operator-facing runtime aggregates
7. operational logs and health views

Anything else belongs in local PostgreSQL or on the external-drive file surface.

The enforceable whitelist lives in `docs/cloud_scope.md`.

## 4. Phased Execution Plan

### Phase 0: Planning Reset And Contract Freeze

Purpose:

- stop the plan zoo
- freeze the two-database boundary
- freeze the cloud whitelist
- freeze the interface contract set

Required work:

- maintain `docs/MASTER_PLAN.md` as the only plan
- maintain `docs/INDEX.md` as the only documentation entrypoint
- maintain `docs/contracts/` as the only interface authority
- maintain `docs/cloud_scope.md` as the only cloud-whitelist authority
- mark superseded plan docs as reference-only

Exit criteria:

- every engineer and agent has one plan, one contract set, and one cloud whitelist

### Phase 1: Local PostgreSQL Canonical Schema

Purpose:

- stand up the warehouse-first canonical schema in local PostgreSQL

Required work:

- implement normalized local canonical tables for:
  - market data
  - Warbird lifecycle truth
  - training registry
  - packet registry
  - activation and rollback log
  - SHAP artifact registry
- keep raw and archive files under `/Volumes/Satechi Hub/warbird-pro/data/` as companion surfaces, not as a second truth
- ensure local canonical tables can drive ingest, training, evaluation, publish-up, and audit with no cloud warehouse dependency

Exit criteria:

- local PostgreSQL can run ingest to canonical to train to evaluate end-to-end without depending on cloud warehouse tables

### Phase 2: Runtime Ingress To Local Canonical

Purpose:

- make the runtime alert path durable while keeping local canonical truth authoritative

Required work:

- implement cloud ingress validation
- write minimal cloud intake rows for runtime monitoring only
- forward alerts to the local canonical writer with retry and DLQ behavior
- enforce candidate idempotency in local canonical writes
- record ingress failures and reconciliation status explicitly

Exit criteria:

- a Pine alert produces exactly one canonical local candidate row, or a visible retry or failure state, with no duplicate truth rows

### Phase 3: Curated Cloud Read Models

Purpose:

- expose only the runtime subset needed by frontend, indicator-support operations, and admin monitoring

Required work:

- build curated cloud read models fed only from local publish-up
- cut dashboard and admin readers to those models only
- remove local recomputation of fib geometry
- expose runtime stream health, packet activation status, and curated operator metrics

Exit criteria:

- cloud contains only the runtime subset needed for UI and operator surfaces, and the UI does not depend on cloud warehouse tables

### Phase 4: Local AutoGluon Pipeline

Purpose:

- keep model training, evaluation, diagnostics, and artifact generation entirely local

Required work:

- extract features and labels from local canonical tables only
- train and evaluate locally
- generate SHAP outputs locally
- register training and artifact lineage in local PostgreSQL
- keep Tier 1 packet features distinct from Tier 2 research-only features

Exit criteria:

- full retraining completes without needing cloud warehouse tables

### Phase 5: Publish-Up

Purpose:

- publish only the serving subset back to cloud

Required work:

- publish:
  - active packet pointer
  - minimal packet metadata
  - packet download location or blob reference if needed
  - curated SHAP and report summaries
  - slim runtime aggregates needed by frontend
- verify published schemas against `docs/cloud_scope.md`

Exit criteria:

- cloud serving is replaceable, minimal, and derived from local truth only

### Phase 6: Cloud Cleanup And Enforcement

Purpose:

- remove all warehouse drift from cloud and block regressions

Required work:

- inventory live cloud objects against `docs/cloud_scope.md`
- mark out-of-scope objects deprecated
- stop writers to deprecated objects
- remove reader dependencies
- drop deprecated views before dropping deprecated tables
- add CI or review checks that block new cloud tables unless they are added to the whitelist first

Exit criteria:

- cloud schema matches the whitelist and no warehouse-zoo objects remain online

## 5. Immediate Execution Checklist

1. Keep this master plan, the contracts, and the cloud-scope doc aligned.
2. Verify live cloud objects against `docs/cloud_scope.md` before dropping anything.
3. Rewrite reader, writer, and model docs so local PostgreSQL is always described as canonical.
4. Block any new cloud table or view unless it serves the whitelist.
5. Treat any warehouse-like cloud object as removal debt unless explicitly reapproved here.

## 6. Cloud Cleanup Checklist

Use this checklist before any drop migration:

1. Verify the object exists in live cloud and classify it against `docs/cloud_scope.md`.
2. If the object is out of scope, mark it `deprecated` in `docs/cloud_scope.md`.
3. Stop all writers to that object.
4. Remove all readers and compat views that depend on it.
5. Drop dependent views first.
6. Drop the table or function only after runtime monitoring confirms no remaining reads or writes.
7. Record the migration and the removal reason in repo docs.

## 7. Non-Negotiable Outcome

Warbird is complete only when:

- local PostgreSQL is the single canonical warehouse
- cloud Supabase is reduced to the strict curated runtime subset
- Pine emits the live contract
- local canonical writes are idempotent and auditable
- AutoGluon trains locally from local truth
- published packets and curated SHAP surfaces are served safely from cloud
- cloud can no longer drift back into a second warehouse
