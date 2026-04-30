# Claude Rogue-Proof Phase Contract

**Date:** 2026-04-30
**Status:** Active guardrail overlay for Warbird Pro + Nexus tuning

This contract hardens Claude/Codex execution for the current tuning program. It
is fail-closed: if a requirement is unmet, the task is incomplete.

## Locked Mission

Execute only this scoped program unless Kirk explicitly reopens scope:

1. Keep `indicators/warbird-pro-indicator.pine` as the only active main chart
   indicator.
2. Keep Nexus:
   - `indicators/warbird-nexus-machine-learning-rsi.pine`
   - `indicators/warbird-nexus-machine-learning-rsi-optuna-fast-test.pine`
3. Treat these Pine variants as retired/historical unless explicitly reopened:
   - `indicators/v7-warbird-institutional.pine`
   - `indicators/v7-warbird-strategy.pine`
   - `indicators/v7-warbird-institutional-backtest-strategy.pine`
   - `indicators/fibs-only.pine`
4. Preserve Warbird Pro fib anchor ownership and ladder math during 5m tuning.
5. Use only Pine/TradingView evidence for active modeling.

## Active Trigger Families

- `LIVE_ANCHOR_FOOTPRINT` for Warbird Pro
- `NEXUS_FOOTPRINT_DELTA` for Nexus

`STRATEGY_ACCEPT_SCALP` and `BACKTEST_DIRECT_ANCHOR` are retired until Kirk
explicitly reopens a strategy/backtest harness.

## Locked Phase Definitions

- **Phase 1 (1,000):** trend / VWAP / MA / liquidity sweep
- **Phase 2 (1,000):** momentum
  - VF Window, VF Candle Weight, VF Volume Weight, NFE Length, RSI KNN Window
- **Phase 3 (1,000):** footprint/exhaustion
  - Ticks, VA, Imbalance%, Extension ATR Tol, Zero-Print, Swing Lookback, Cooldown, Imbalance Rows
- **Phase 4 (1,000):** entry/risk
  - Execution Anchor, ATR Stop Multiplier, Max Setup Stop ATR, shared execution-safety knobs

## Non-Negotiable Guardrails

1. Do not modify Warbird Pro fib anchor ownership or ladder math without
   explicit reopen plus before/after evidence.
2. Do not touch unrelated files or refactor opportunistically.
3. Do not claim a knob is tuned unless it exists in the active Warbird Pro schema
   and phase space.
4. Do not run tuning/training without explicit user direction.
5. Do not invent evidence, trial outcomes, or verification results.
6. Do not use destructive git commands.
7. Do not claim completion if any required verification gate is missing.

## Execution Sequence

1. **Preflight**
   - `git status --short`
   - scope with `rg --files` / `rg -n`
   - read authority docs for touched surfaces
   - list touched write-set before edits

2. **Implement**
   - minimal diff
   - preserve Warbird Pro as the single active main indicator
   - keep Nexus retained
   - keep phase files explicit and phase-scoped

3. **Verify**
   - run required guard scripts for touched file types

4. **Close**
   - report pass/fail/not-run by command
   - fail closed when any mandatory check is missing

## Verification Gates

If any `.pine` file is touched:

1. pine-facade compile check
2. `./scripts/guards/pine-lint.sh <each touched .pine>`
3. `./scripts/guards/check-fib-scanner-guardrails.sh`
4. `./scripts/guards/check-contamination.sh`
5. `npm run build`

`./scripts/guards/check-indicator-strategy-parity.sh` is inactive unless Kirk
explicitly reopens a strategy harness coupled to Warbird Pro.

If docs/script/json only:

- run narrow syntax/lint checks as applicable
- run `npm run build` when operational truth docs are changed

## Completion Schema

Use this exact structure for implementation closures:

```text
STATUS: COMPLETE | INCOMPLETE
TOUCHED FILES:
- path

VERIFICATION:
- PASS: command
- FAIL: command
- NOT RUN: command — reason

BLOCKERS:
- none
```
