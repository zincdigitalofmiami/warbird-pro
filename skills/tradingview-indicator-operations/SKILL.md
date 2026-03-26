---
name: tradingview-indicator-operations
description: TradingView indicator operations workflow covering Indicator Review, Indicator Build, Indicator Repair, and Indicator Optimize with checkpointed safety gates, deep quant validation, logic checks, and project data-contract alignment. Use when working on Pine indicator or strategy files and release-readiness decisions that must stay aligned with the active project plan.
---

# TradingView Indicator Operations

Run a checkpointed workflow for Pine indicator engineering and review. Discover active project rules dynamically so this skill remains valid when plan files change.

## Operation Modes

Choose exactly one primary mode for each task:

1. Indicator Review
- Audit logic, no-repaint behavior, alerts, exports, and contract alignment.
- Produce severity-ranked findings with evidence.

2. Indicator Build
- Implement new indicator logic or features within contract boundaries.
- Run gates and produce release recommendation.

3. Indicator Repair
- Debug and remediate compile/runtime defects or behavior regressions.
- Confirm fixes with targeted regression checks and full gates.

4. Indicator Optimize
- Improve reliability, performance budget, and signal quality without breaking contract semantics.
- Quantify impact with before/after evidence.

If mode is ambiguous, default to `Indicator Review` and ask only after context discovery if ambiguity blocks safe execution.

## Active Context Discovery

1. Read `AGENTS.md` and identify the active plan file path and active update area.
2. Read the active plan file identified in step 1.
3. Read `CLAUDE.md` and `WARBIRD_MODEL_SPEC.md`.
4. Read target Pine files. Default to:
- `indicators/v6-warbird-complete.pine`
- `indicators/v6-warbird-complete-strategy.pine`
5. Inspect latest work:
- `git log --oneline --decorate -n 12`
- `git status --short`
6. Run baseline checkpoints with `scripts/run_indicator_checkpoints.sh` (use `--skip-build` when context discovery only).

Stop and ask if `AGENTS.md` does not clearly define an active plan path.

## Workflow Checkpoints

### Checkpoint 1: Scope and Contract Lock

- Confirm the canonical trade contract, timeframe, and timezone from active docs.
- Record recent changes relevant to the target indicator or strategy.
- Record blocker list before proposing changes.

Output: Context snapshot and scope boundaries.

### Checkpoint 2: TradingView Limits and Runtime Budget

- Load [tradingview-limits-2026-03-26](references/tradingview-limits-2026-03-26.md).
- Count `request.*()` calls, plot counts, table locations, and drawing declarations.
- Flag budget pressure at `>= 75%` for any hard cap.

Output: Limit budget table and risk notes.

### Checkpoint 3: Deep Quant Validation Design

- Load [deep-quant-validation](references/deep-quant-validation.md).
- Define regime, session, and event stress cases.
- Define evidence capture for every test case.

Output: Explicit quant validation matrix with pass or fail gates.

### Checkpoint 4: Logic Review and Findings

- Review no-repaint safety, bar-close determinism, and alert correctness.
- Review hidden export contract and indicator or strategy parity.
- Classify findings by severity (`P0` to `P3`) and confidence.

Output: Findings list with direct evidence.

### Checkpoint 5: Suggestions and Implementation Plan

- Map each suggestion to impacted code paths, `ml_*` fields, and data surfaces.
- Include priority, expected impact, effort (`S` or `M` or `L`), and risk (`low` or `medium` or `high`).
- Keep suggestions minimal and testable.

Output: Prioritized recommendation list.

### Checkpoint 6: Gate Execution and Release Call

- Run `scripts/run_indicator_checkpoints.sh`.
- Report exact pass/fail states.
- Issue `GO` or `NO-GO` with next blocking item.

Output: Release recommendation and next blocker.

## Data-Matching Rules for Suggestions

- Anchor all suggestions to the canonical MES 15m bar-close contract.
- Match proposed indicator outputs to existing `ml_*` exports before adding new fields.
- Match live-path suggestions to active tables in [project-context-warbird](references/project-context-warbird.md).
- If a proposal needs new data, define exact table and column additions plus migration impact.

## Adaptation Rules (Plan Changes)

- Treat `AGENTS.md` as the source of truth for which plan is active.
- Re-read `AGENTS.md` and the active plan at the start of each task and after major direction changes.
- Preserve checkpoint structure even when plan content changes.
- Pull current details from active docs each run instead of assuming old values.

## Guardrails

- Never claim Deep Backtesting evidence without explicit proof.
- Never assume optional Pine toolchains are available; verify environment capabilities first.
- Never use mock data.
- Prefer exact-copy harness internals for required open-source modules; apply interface-only edits.

## Resources

- Run repo gates with `scripts/run_indicator_checkpoints.sh`.
- Generate a structured report with `scripts/new_indicator_review_report.py`.
- Load [project-context-warbird](references/project-context-warbird.md) for contract and data surfaces.
- Load [deep-quant-validation](references/deep-quant-validation.md) for test matrix and pass criteria.
- Load [tradingview-limits-2026-03-26](references/tradingview-limits-2026-03-26.md) for Pine limits.
