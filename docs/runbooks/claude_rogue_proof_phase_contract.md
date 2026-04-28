# Claude Rogue-Proof Phase Contract

**Date:** 2026-04-28  
**Status:** Active guardrail overlay for phased 5m tuning

This contract hardens Claude execution for the current phased tuning program.
It is fail-closed: if a requirement is unmet, the task is incomplete.

## Locked Mission

Execute only this scoped program unless Kirk explicitly reopens scope:

1. **Phase 0 (Pine schema parity):**
   - Align shared inputs across:
     - `indicators/v7-warbird-strategy.pine`
     - `indicators/v7-warbird-institutional.pine`
   - Required shared inputs:
     - MA family + MA lengths
     - Liquidity Sweep Lookback
     - Exhaustion Swing Lookback
     - Exhaustion Cooldown Bars
   - This still requires explicit current-session Pine approval.

2. **Phase-space scaffolding:**
   - `scripts/ag/strategy_tuning_space.phase1.json`
   - `scripts/ag/strategy_tuning_space.phase2.json`
   - `scripts/ag/strategy_tuning_space.phase3.json`
   - `scripts/ag/strategy_tuning_space.phase4.json`
   - Keep `scripts/ag/strategy_tuning_space.json` as legacy single-pass baseline.

3. **Cohort banding automation:**
   - `scripts/ag/band_phase_winners.py`
   - Must derive next-phase bounds from top cohort in
     `warbird_strategy_tuning_trials`:
     - numerics: median +/- clipped IQR/MAD band
     - categoricals/bools: top 1-2 modes, minority retained only with meaningful support

4. **Phased progression enforcement in docs/runbooks:**
   - 20 batches x 50 trials per phase
   - top 10-20 cohort carried forward
   - OOS/walk-forward gate required after each 1,000 before next phase

## Locked Phase Definitions

- **Phase 1 (1,000):** trend / VWAP / MA / liquidity sweep
- **Phase 2 (1,000):** momentum
  - VF Window, VF Candle Weight, VF Volume Weight, NFE Length, RSI KNN Window
- **Phase 3 (1,000):** footprint/exhaustion
  - Ticks, VA, Imbalance%, Extension ATR Tol, Zero-Print, Swing Lookback, Cooldown, Imbalance Rows
- **Phase 4 (1,000):** entry/risk
  - Execution Anchor, ATR Stop Multiplier, Max Setup Stop ATR, shared execution-safety knobs

## Non-Negotiable Guardrails

1. Do not modify backtest fib-core internals in
   `indicators/v7-warbird-institutional-backtest-strategy.pine` without explicit reopen + before/after evidence.
2. Do not touch unrelated files or refactor opportunistically.
3. Do not claim a knob is tuned unless it exists in the active shared schema and phase space.
4. Do not run tuning/training without explicit user direction.
5. Do not invent evidence, trial outcomes, or verification results.
6. Do not use destructive git commands.
7. Do not claim completion if any required verification gate is missing.

## Execution Sequence (Mandatory)

1. **Preflight**
   - `git status --short`
   - scope with `rg --files` / `rg -n`
   - read authority docs for touched surfaces
   - list touched write-set before edits

2. **Implement**
   - minimal diff
   - preserve naming parity between strategy and institutional surfaces
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
6. `./scripts/guards/check-indicator-strategy-parity.sh` when v7 indicator/strategy coupling is touched

If docs/script/json only:

- run narrow syntax/lint checks as applicable
- run `npm run build` when operational truth docs are changed

## Completion Schema (Mandatory)

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
- none | blocker
```

Rules:

1. `COMPLETE` is allowed only when all required gates passed.
2. Any `FAIL` or required `NOT RUN` forces `INCOMPLETE`.
3. Do not hide blockers; list concrete blocker + evidence.
