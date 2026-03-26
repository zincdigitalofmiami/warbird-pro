---
name: tradingview-indicator-optimize
description: TradingView-specific optimization workflow for Pine indicators and strategies on MES/ES futures. Use for performance, robustness, and signal-quality improvements with strict non-repair boundaries, safety stops, checkpoints, and before/after evidence.
---

# TradingView Indicator Optimize

Optimize mode improves performance and reliability. It does not silently perform repair work.

## Scope

- Primary contract: MES 15m bar-close in `America/Chicago`.
- Primary files:
- `indicators/v6-warbird-complete.pine`
- `indicators/v6-warbird-complete-strategy.pine`
- Primary objective: measurable improvement without semantic drift.

## Safety Stops (Hard Stop Conditions)

Stop immediately and ask for direction if any of these occur:

1. A true defect is discovered that belongs to repair mode.
2. Proposed optimization changes entry, exit, stop, or target semantics without explicit approval.
3. Optimization requires widening contract or schema surfaces.
4. No-repaint assurances would be weakened.
5. Budget pressure against TradingView limits has no mitigation path.
6. Harness internals would need rewrite.
7. Before/after measurement cannot be produced.
8. Any attempt uses mock data.

## Non-Repair Boundary

- If something is broken, do not fix it under optimize mode by default.
- Record the issue, classify severity, and stop for user approval.
- Continue optimization only when behavior is already correct or user explicitly authorizes repair inside this run.

## Checkpoints

1. Baseline Lock
- Capture current behavior, gate state, and metric baseline.
- Define optimization target and expected gain.

2. Dry Test First
- Run:
- `scripts/run_optimize_checkpoints.sh --dry-run`
- Confirm sequence before touching logic.

3. Optimization Plan
- Define exactly what is being optimized:
- runtime and resource budget
- signal stability
- noise suppression
- Keep trade semantics unchanged unless approved.

4. Implement Narrow Optimization
- Apply focused, reversible changes.
- Avoid collateral logic rewrites.

5. Before/After Proof
- Run:
- `scripts/run_optimize_checkpoints.sh`
- Compare baseline vs optimized measurements.
- Validate unchanged signal semantics unless approved.

6. Release Decision
- Output net gain, tradeoffs, and residual risk.
- Issue `GO` or `NO-GO`.

## Optimization Output Contract

Every optimization result must include:

1. Baseline metrics and post-change metrics.
2. Semantic drift check outcome.
3. Defects found and whether optimization halted.
4. Gate results and release call.

## References

- [project-context-warbird](references/project-context-warbird.md)
- [deep-quant-validation](references/deep-quant-validation.md)
- [tradingview-limits-2026-03-26](references/tradingview-limits-2026-03-26.md)
- [sp500-futures-insights](references/sp500-futures-insights.md)

