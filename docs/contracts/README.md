# Warbird Contracts

**Date:** 2026-04-26
**Status:** Active Interface Authority

This directory is the only interface authority for Warbird payloads,
indicator-only modeling identity, labels, feature tiers, Pine settings artifacts,
and schema migration policy.

Ignore interface definitions in old plans, scratch notes, and historical decision docs unless they are copied into this directory.

## Contract Set

- `signal_event_payload.md`
- `candidate_identity.md`
- `stop_families.md`
- `label_resolution.md`
- `feature_catalog.md`
- `packet_schema.md`
- `schema_migration_policy.md`
- `pine_indicator_ag_contract.md`
- `nexus_visual_plot_freeze.md`
- `ag_local_training_schema.md`
- `v7_interface_divergence.md`

`pine_indicator_ag_contract.md` is the active modeling contract.
`nexus_visual_plot_freeze.md` is a hard visual/visible-output freeze for Nexus
ML RSI and overrides stale plan text that proposes Nexus styling, watermark,
table, `barcolor`, `plot`, `fill`, or marker changes.
`ag_local_training_schema.md` is superseded reference for the retired warehouse
AG plan and must not drive active modeling unless explicitly reopened.

## Iteration Rule

Contract details are expected to evolve during active Pine tuning and training.
When a run changes trigger semantics, settings, labels, features, or promotion
criteria, update the affected contract Markdown before another agent relies on
the result. Historical contract text must be clearly marked superseded instead
of left ambiguous.

Nexus visual and plot behavior is not part of the iterative tuning surface.
Treat any Nexus visual/plot recommendation as blocked unless Kirk explicitly
requests that exact visual/plot edit in the current session.

## Working Rule

- `docs/MASTER_PLAN.md` defines sequencing and architecture.
- `docs/contracts/` defines the interface details that active code and runbooks
  must implement.
- `docs/cloud_scope.md` defines what may exist in cloud Supabase.
