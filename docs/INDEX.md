# Warbird Documentation Index

**Date:** 2026-04-07
**Status:** Active Documentation Authority

This file is the single entrypoint for Warbird architecture, contract, and operations documentation.

Ignore all other plans, decisions, scratch notes, and historical architecture docs unless they are linked from this index.

## Read Order

1. `docs/MASTER_PLAN.md`
2. `docs/contracts/README.md`
3. `docs/runbooks/README.md`
4. `docs/contracts/schema_migration_policy.md`
5. `docs/cloud_scope.md`
6. `WARBIRD_MODEL_SPEC.md`
7. `CLAUDE.md`
8. `docs/agent-safety-gates.md`
9. `docs/research/2026-04-06-powerdrill-findings.md`

## Authority Split

- `docs/MASTER_PLAN.md`
  - the only planning authority
- `docs/contracts/`
  - the only interface and payload authority
- `docs/cloud_scope.md`
  - the only cloud-whitelist authority
- `docs/runbooks/README.md`
  - the operational runbook index
- `CLAUDE.md`
  - current operational truth and runtime status
- `WARBIRD_MODEL_SPEC.md`
  - subordinate model contract and packet semantics

## Historical Material

- Everything outside this index is reference-only unless a document linked here explicitly reopens it.
- Legacy plan and decision docs remain useful for lineage, but they must not drive new implementation.
