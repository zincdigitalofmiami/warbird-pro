# Warbird Documentation Index

**Date:** 2026-04-30
**Status:** Active Documentation Authority
**Active Plan:** Warbird Indicator-Only Optuna Plan v6

This file is the single entrypoint for Warbird architecture, contract, and operations documentation.

Ignore all other plans, decisions, scratch notes, and historical architecture docs unless they are linked from this index.

## Iteration Rule

The indicator-only plan is active, but tuning and training are ongoing. Treat
current trigger families, settings, thresholds, and search spaces as the latest
documented evidence snapshot. They may change after new TradingView exports and
Optuna trials. Any accepted change must update this indexed authority set in
the same commit.

Current checkpoint lock (2026-04-30): `indicators/warbird-pro-indicator.pine`
is the only active main chart indicator, Nexus is retained, and all other Pine
variants are historical unless explicitly reopened. 5m tuning must preserve the
protected Warbird Pro fib anchor ownership and ladder math unless explicitly
reopened with evidence.

## Read Order

1. `docs/MASTER_PLAN.md` — Warbird Indicator-Only Optuna Plan v6
2. `docs/contracts/README.md`
3. `docs/contracts/pine_indicator_ag_contract.md`
4. `docs/runbooks/README.md`
5. `docs/runbooks/startup_repo_review.md` - required fresh-chat/start-of-day read-only initialization
6. `docs/contracts/schema_migration_policy.md`
7. `docs/cloud_scope.md`
8. `WARBIRD_MODEL_SPEC.md`
9. `CLAUDE.md`
10. `docs/agent-safety-gates.md`
11. `Powerdrill/reports/2026-04-06-powerdrill-findings.md`

## Authority Split

- `docs/MASTER_PLAN.md`
  - the only planning authority — Warbird Indicator-Only Optuna Plan v6
- `docs/contracts/`
  - the only interface and payload authority
- `docs/contracts/pine_indicator_ag_contract.md`
  - exact active indicator-only Optuna modeling contract (legacy filename)
- `docs/cloud_scope.md`
  - the only cloud-whitelist authority
- `docs/runbooks/README.md`
  - the operational runbook index
- `docs/runbooks/startup_repo_review.md`
  - required fresh-chat/start-of-day read-only initialization report checklist
- `CLAUDE.md`
  - current operational truth and runtime status
- `WARBIRD_MODEL_SPEC.md`
  - subordinate indicator-only model contract and settings artifact semantics

## Canonical Split

- **Pine/TradingView outputs** = active training/modeling truth
- **Active Pine files** = `warbird-pro-indicator.pine` plus the two retained
  Nexus Pine files
- **Local Optuna workspaces** under `scripts/optuna/workspaces/` = active optimization state
- **Local `warbird` PG17 warehouse** = legacy/reference unless explicitly reopened
- **Cloud Supabase** = runtime/support only, not training truth
- Active artifacts: `artifacts/tuning/` and `scripts/optuna/workspaces/<indicator_key>/`

## Startup Review Records

- `docs/runbooks/2026-04-29-startup-repo-review-initialization.md`
  - initial startup repo review findings and permanence record

## Historical Material

- Everything outside this index is reference-only unless a document linked here explicitly reopens it.
- Legacy plan and decision docs remain useful for lineage, but they must not drive new implementation.
