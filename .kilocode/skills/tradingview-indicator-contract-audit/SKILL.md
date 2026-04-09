---
name: tradingview-indicator-contract-audit
description: >
  Audit Warbird Pine indicator and strategy contracts for entry-state truth, candidate
  semantics, no-repaint behavior, timing alignment, transport boundaries, and alert
  correctness.
---

# TradingView Indicator Contract Audit

Use this skill when Pine output, strategy parity, or downstream scoring depends on exact contract correctness.

## Required Reads

1. `AGENTS.md`
2. `docs/INDEX.md`
3. `docs/MASTER_PLAN.md`
4. `docs/contracts/README.md`
5. `docs/contracts/signal_event_payload.md`
6. `CLAUDE.md`
7. `WARBIRD_MODEL_SPEC.md`
8. Target Pine files:
   - `indicators/v7-warbird-institutional.pine`
   - `indicators/v7-warbird-strategy.pine`

## Audit Workflow

### 1. Contract inventory

- List Pine alerts, hidden exports, state fields, and strategy dependencies
- Map them to active contract docs
- Separate Tier 1 Pine fields from Tier 2 server-side fields

### 2. Timing and no-repaint

- Confirm MES 15m bar-close alignment in `America/Chicago`
- Confirm confirmed-bar-only semantics
- Confirm `request.security()` calls remain `lookahead_off`
- Flag repaint, delayed-emission, or timestamp-shift risk

### 3. Candidate and entry-state semantics

- Confirm the candidate is a point-in-time fib setup snapshot
- Audit:
  - entry event definition
  - entry activation timing
  - captured entry price or spot truth
  - trade-state transition timing
- Treat TP1, TP2, stop, and reversal as downstream path labels, not substitutes for entry truth

### 4. Indicator and strategy parity

- Confirm the strategy mirrors the structural trigger path
- Audit drift across direction, setup archetype, target viability, trade state, and entry timing
- Treat entry-state drift as a contract defect even if labels still populate

### 5. Tier boundaries and alerts

- Pine may emit structural candidate transport only
- Pine must not emit AG-only decisions or calibrated probabilities
- Confirm alert names, trigger conditions, and dedupe behavior
- Confirm hidden exports remain point-in-time faithful

## Expected Output

- Severity-ranked findings with file and line references
- Clear statement on entry-state correctness
- Clear statement on indicator/strategy parity
- Clear statement on Tier 1 versus Tier 2 boundary compliance

## Guardrails

- Do not collapse the audit into TP1 or TP2 correctness only
- Do not change semantics unless the user explicitly asked for repair or implementation
- Prefer deterministic confirmed-bar logic over convenient but ambiguous shortcuts
