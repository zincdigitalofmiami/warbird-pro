# Warbird Documentation Index

**Date:** 2026-04-10
**Status:** Active Documentation Authority
**Active Plan:** Warbird Full Reset Plan v5

This file is the single entrypoint for Warbird architecture, contract, and operations documentation.

Ignore all other plans, decisions, scratch notes, and historical architecture docs unless they are linked from this index.

## Read Order

1. `docs/MASTER_PLAN.md` — Warbird Full Reset Plan v5
2. `docs/contracts/README.md`
3. `docs/contracts/ag_local_training_schema.md`
4. `docs/runbooks/README.md`
5. `docs/contracts/schema_migration_policy.md`
6. `docs/cloud_scope.md`
7. `WARBIRD_MODEL_SPEC.md`
8. `CLAUDE.md`
9. `docs/agent-safety-gates.md`
10. `Powerdrill/reports/2026-04-06-powerdrill-findings.md`

## Authority Split

- `docs/MASTER_PLAN.md`
  - the only planning authority — Warbird Full Reset Plan v5
  - v8 execution front is `docs/WARBIRD_V8_PLAN.md` (execution supplement; governance remains in MASTER_PLAN)
- `docs/contracts/`
  - the only interface and payload authority
- `docs/contracts/ag_local_training_schema.md`
  - exact local AG column-level schema authority (four tables + `ag_training` view: `ag_fib_snapshots`, `ag_fib_interactions`, `ag_fib_stop_variants`, `ag_fib_outcomes`)
- `docs/cloud_scope.md`
  - the only cloud-whitelist authority
- `docs/runbooks/README.md`
  - the operational runbook index
- `CLAUDE.md`
  - current operational truth and runtime status
- `WARBIRD_MODEL_SPEC.md`
  - subordinate model contract, canonical AG schema, SHAP program, and packet semantics

## Canonical Split

- **Local `warbird`** on PG17 (`127.0.0.1:5432`) = canonical warehouse, training, artifacts, raw SHAP, diagnostics
- **Cloud Supabase** (`qhwgrzqjcdtdqppvhhme`) + Vercel `warbird-pro` = serving-only for frontend, TradingView/indicator support, packets, dashboard/admin read models, curated SHAP/report surfaces
- Local warehouse DDL: `local_warehouse/migrations/`
- Cloud DDL: `supabase/migrations/`
- AG pipeline: `scripts/ag/`
- Raw artifacts: `artifacts/`

## Historical Material

- Everything outside this index is reference-only unless a document linked here explicitly reopens it.
- Legacy plan and decision docs remain useful for lineage, but they must not drive new implementation.
