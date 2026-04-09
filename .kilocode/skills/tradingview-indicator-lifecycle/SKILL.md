---
name: tradingview-indicator-lifecycle
description: >
  Router for the full Warbird Pine lifecycle. Use when a request spans contract review,
  repair, build, optimization, transport checks, and release closeout and Kilo must
  choose the right next Pine operation.
---

# TradingView Indicator Lifecycle

Use this skill when the request spans more than one Pine phase or when you need to decide what kind of Pine work comes first.

## Lifecycle Order

1. Lock authority and contract truth
2. Validate candidate and entry-state semantics
3. Choose the primary operation mode
4. Execute the Pine change
5. Run repo gates
6. Update active docs only if truth changed

## Authority Lock

Read:

1. `AGENTS.md`
2. `docs/INDEX.md`
3. `docs/MASTER_PLAN.md`
4. `docs/contracts/README.md`
5. `docs/contracts/signal_event_payload.md`
6. `CLAUDE.md`
7. `WARBIRD_MODEL_SPEC.md`

Lock these truths before touching Pine:

- canonical object = MES 15m fib setup
- canonical key = MES 15m bar close in `America/Chicago`
- indicator = live structural candidate-generator
- strategy = backtest mirror
- Tier 1 = Pine candidate transport
- Tier 2 = server-side AG scoring
- entry-state and entry spot semantics are first-class contract truth

## Choose the Mode

- Review: findings, risks, release readiness
- Repair: compile defect, runtime bug, behavior regression, naming issue
- Build: approved feature or contract extension
- Optimize: budget, stability, or signal-quality improvement without changing contract semantics

If multiple modes are needed, use this order:

1. Review
2. Repair
3. Build
4. Optimize

## Before Code

Confirm:

1. no-repaint and confirmed-bar logic
2. entry event and entry activation timing
3. captured entry price or spot semantics
4. indicator and strategy parity
5. Tier 1 and Tier 2 boundary compliance
6. Pine budget safety

If any of these are unresolved, the task is not ready for implementation.

## Closeout

- Run the required Pine guard scripts
- Run `npm run build`
- Report exact pass or fail status
- Update active docs only if contract or operational truth changed

## Guardrails

- TP1 and TP2 labels are not a substitute for entry-state validation
- Do not widen the task into an architecture rewrite unless explicitly asked
- Do not carry stale v6 assumptions into v7 work
