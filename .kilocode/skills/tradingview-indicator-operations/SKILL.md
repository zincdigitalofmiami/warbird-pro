---
name: tradingview-indicator-operations
description: >
  Operations workflow for Warbird Pine indicator and strategy work. Use when Kilo must
  review, repair, build, or optimize Pine files while staying aligned with the current
  contract, entry-state semantics, and repo verification gates.
---

# TradingView Indicator Operations

Choose exactly one primary mode for each task:

1. Review
2. Repair
3. Build
4. Optimize

If the correct mode is unclear, start as a review until the defect or change class is obvious.

## Context Discovery

1. Read `AGENTS.md`
2. Read `docs/INDEX.md`, `CLAUDE.md`, `docs/MASTER_PLAN.md`
3. Read `docs/contracts/README.md`, `docs/contracts/signal_event_payload.md`, and `WARBIRD_MODEL_SPEC.md`
4. Read the active Pine files:
   - `indicators/v7-warbird-institutional.pine`
   - `indicators/v7-warbird-strategy.pine`
5. Run `git status --short`
6. Scope recent work with `rg -n`

## Operation Checkpoints

### 1. Scope and contract lock

- Confirm MES 15m bar-close contract
- Confirm indicator = live candidate-generator
- Confirm strategy = backtest mirror
- Confirm entry-state truth is in scope when evaluating trade logic

### 2. Budget and platform limits

- Count `request.*()` usage
- Count plot and alert budget pressure
- Check for unnecessary drawing pressure

### 3. Logic review

- Confirm no-repaint and confirmed-bar discipline
- Confirm entry event, entry timing, and entry spot semantics
- Confirm Tier 1 versus Tier 2 boundaries
- Confirm indicator and strategy parity where shared logic exists

### 4. Execute the change

- Keep the write-set minimal
- Do not add new live gates unless the contract explicitly changed
- Do not reintroduce regime or research-only fields into live trigger logic

### 5. Verification

- `./scripts/guards/compile-pine.sh <each touched .pine file>`
- `./scripts/guards/pine-lint.sh <each touched .pine file>`
- `./scripts/guards/check-contamination.sh`
- `./scripts/guards/check-indicator-strategy-parity.sh` when both active v7 files or shared logic changed
- `npm run build`

## Release Call

- `GO` only if all required gates passed
- `NO-GO` if any required gate failed or was not run
- End with the next blocker, not a vague “needs more testing”

## Guardrails

- Do not reduce validation to TP1 or TP2 labels alone
- Do not claim Deep Backtesting or live-chart proof unless you actually have it
- Do not assume old v6 behavior still governs v7
