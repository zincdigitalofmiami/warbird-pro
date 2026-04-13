---
name: tradingview-indicator-review
description: Deep TradingView-specific review workflow for Pine indicators and strategies on MES/ES futures. Use for release-readiness audits, no-repaint checks, alert correctness, ML export contract checks, and severity-ranked review findings with hard safety stops and checkpoint gates.
---

# TradingView Indicator Review

Review mode is audit-only by default. Treat this as a quant-grade, evidence-first code review for Pine.

## Scope

- Primary contract: MES 15m bar-close in `America/Chicago`.
- Primary files:
- `indicators/v7-warbird-institutional.pine`
- `indicators/v7-warbird-strategy.pine`
- Primary objective: identify defects, regression risk, and release blockers.

## Safety Stops (Hard Stop Conditions)

Stop immediately and ask for direction if any of these occur:

1. `AGENTS.md` does not clearly resolve a single active plan path.
2. The active plan conflicts with MES 15m contract assumptions.
3. Required harness source internals cannot be verified as open-source and exact-copy compatible.
4. TradingView hard limits are at risk and no acceptable reduction path exists.
5. No-repaint behavior cannot be proven with bar-close deterministic evidence.
6. A claim requires Deep Backtesting evidence that is not available.
7. Requested action requires code edits (repair/build) without explicit approval to leave review-only mode.
8. Any proposal depends on mock or synthetic data.

## Checkpoints

1. Context Lock
- Read `AGENTS.md`, active plan, `CLAUDE.md`, `WARBIRD_MODEL_SPEC.md`, and target Pine files.
- Confirm MES 15m and timezone assumptions.

2. Dry Test First
- Run:
- `scripts/run_review_checkpoints.sh --dry-run`
- Validate planned gates before any heavy execution.

3. Baseline Gates
- Run:
- `scripts/run_review_checkpoints.sh`
- Use `--skip-build` only when user asks for fast triage.

4. TradingView Budget and Runtime Review
- Use [tradingview-limits-2026-03-26](references/tradingview-limits-2026-03-26.md).
- Count `request.*`, plot pressure, drawing counts, table usage, and likely runtime hotspots.
- Raise warning at 75 percent, block at unsafe levels.

5. MES/ES Quant + Finance + ML Review
- Use [deep-quant-validation](references/deep-quant-validation.md).
- Use [sp500-futures-insights](references/sp500-futures-insights.md).
- Validate:
- RTH/ETH session behavior
- event-mode transitions (CPI/FOMC/NFP contexts)
- cross-asset coherence (`NQ`, `DXY`, `US10Y`, `VIX`)
- indicator/strategy parity and `ml_*` export integrity

6. Findings and Release Call
- Output severity-ranked findings (`P0` to `P3`) with file evidence.
- Output `GO` or `NO-GO` and next blocking item.

## Review Output Contract

Every review result must include:

1. Findings first, sorted by severity, with impacted file paths and logic sections.
2. Confidence statement per finding (`high`, `medium`, `low`).
3. Explicit regression risk notes.
4. Open questions and assumptions.
5. Short change recommendation list (only after findings).

## References

- [project-context-warbird](references/project-context-warbird.md)
- [deep-quant-validation](references/deep-quant-validation.md)
- [tradingview-limits-2026-03-26](references/tradingview-limits-2026-03-26.md)
- [sp500-futures-insights](references/sp500-futures-insights.md)

