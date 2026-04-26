---
name: tradingview-indicator-repair
description: TradingView-specific repair workflow for Pine indicators and strategies on MES/ES futures. Use for debugging compile/runtime defects, contract drift, and behavior regressions with strict safety stops, root-cause checkpoints, and regression proofs.
---

# TradingView Indicator Repair

Repair mode is bug-fix mode. Target root cause, minimal patch, and regression proof.

## Scope

- Primary contract: MES 15m bar-close in `America/Chicago`.
- Primary files:
- `indicators/v7-warbird-institutional.pine`
- `indicators/v7-warbird-strategy.pine`
- Primary objective: correct verified defects without widening blast radius.

## Safety Stops (Hard Stop Conditions)

Stop immediately and ask for direction if any of these occur:

1. Defect cannot be reproduced or evidence is ambiguous.
2. Root cause is unknown but fix would still be speculative.
3. Proposed fix requires broad refactor outside defect scope.
4. Repair introduces contract changes not requested by user.
5. No-repaint or bar-close determinism would be weakened.
6. Required harness internals would be rewritten.
7. TradingView limits or runtime would be exceeded after fix.
8. Any attempted validation relies on non-real data.
9. Nexus ML RSI repair would alter styling or visible outputs without Kirk
   explicitly requesting that exact visual/plot edit in the current session.
   Frozen Nexus surfaces include colors, watermark, dashboard/KNN tables,
   `barcolor`, visible plots, fills, markers, labels, and visible output
   inventory.

## Checkpoints

1. Reproduction Lock
- Capture exact failure mode and conditions.
- Confirm expected vs actual behavior with evidence.

2. Dry Test First
- Run:
- `scripts/run_repair_checkpoints.sh --dry-run`
- Confirm gate flow before patching.

3. Root-Cause Isolation
- Localize failing logic path.
- Document precise defect mechanism.

4. Minimal Repair Implementation
- Patch only root-cause and required collateral lines.
- Avoid opportunistic optimization while repairing.

5. Regression + Quant Validation
- Run:
- `scripts/run_repair_checkpoints.sh`
- Re-test defect scenario plus [deep-quant-validation](references/deep-quant-validation.md) matrix items touched by fix.

6. Repair Sign-Off
- Confirm defect is resolved.
- Provide residual risk and follow-up test recommendations.

## Repair Output Contract

Every repair result must include:

1. Defect statement and reproducible trigger.
2. Root-cause explanation.
3. Exact fix summary with impacted files.
4. Regression evidence and gate results.
5. `GO` or `NO-GO` with next blocker.

## References

- [project-context-warbird](references/project-context-warbird.md)
- [deep-quant-validation](references/deep-quant-validation.md)
- [tradingview-limits-2026-03-26](references/tradingview-limits-2026-03-26.md)
- [sp500-futures-insights](references/sp500-futures-insights.md)
