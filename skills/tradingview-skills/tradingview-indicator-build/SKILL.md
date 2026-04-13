---
name: tradingview-indicator-build
description: TradingView-specific build workflow for Pine indicators and strategies on MES/ES futures. Use for new feature implementation with checkpointed safety stops, quant and finance validation, ML export contract discipline, and release gate execution.
---

# TradingView Indicator Build

Build mode is for intentional implementation with contract discipline and quant proof.

## Scope

- Primary contract: MES 15m bar-close in `America/Chicago`.
- Primary files:
- `indicators/v7-warbird-institutional.pine`
- `indicators/v7-warbird-strategy.pine`
- Primary objective: add approved capability without breaking semantics.

## Safety Stops (Hard Stop Conditions)

Stop immediately and ask for direction if any of these occur:

1. Active plan path is unresolved or contradictory.
2. Feature request conflicts with MES 15m canonical contract.
3. Feature requires schema or `ml_*` contract expansion without explicit approval.
4. Proposed implementation introduces lookahead or repaint risk.
5. TradingView limit pressure has no viable mitigation.
6. Required harness internals would need rewrites instead of interface-only edits.
7. Build request lacks acceptance criteria that can be validated.
8. Any step depends on non-real data.

## Checkpoints

1. Context and Contract Lock
- Read `AGENTS.md`, active plan, `CLAUDE.md`, `WARBIRD_MODEL_SPEC.md`.
- Confirm acceptance criteria and non-goals.

2. Dry Test First
- Run:
- `scripts/run_build_checkpoints.sh --dry-run`
- Validate gate sequence before edits.

3. Build Design Packet
- Define exact logic changes.
- Define affected `ml_*` fields, alerts, and dashboard surfaces.
- Define quant evidence needed for approval.

4. Implement Minimal Safe Delta
- Apply the smallest coherent patch set.
- Keep no-repaint and bar-close determinism intact.

5. Quant + Finance Validation
- Run:
- `scripts/run_build_checkpoints.sh`
- Validate with [deep-quant-validation](references/deep-quant-validation.md) and [sp500-futures-insights](references/sp500-futures-insights.md).
- Confirm event-mode and cross-asset behavior is coherent for MES/ES.

6. Release Recommendation
- Provide before/after behavior summary.
- Provide `GO` or `NO-GO`, blocker list, and rollback notes.

## Build Output Contract

Every build result must include:

1. Exact files changed and why.
2. Contract impact statement for `ml_*`, alerts, and parity surface.
3. Gate results with pass/fail detail.
4. Residual risk list and next verification step.

## References

- [project-context-warbird](references/project-context-warbird.md)
- [deep-quant-validation](references/deep-quant-validation.md)
- [tradingview-limits-2026-03-26](references/tradingview-limits-2026-03-26.md)
- [sp500-futures-insights](references/sp500-futures-insights.md)

