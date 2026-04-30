# Warbird Runbooks

**Date:** 2026-04-30
**Status:** Active Runbook Index

The active runbooks support indicator-only Pine modeling.

## Iteration Rule

Runbooks are operational snapshots for the current tuning cycle. Trigger
families, settings spaces, export requirements, and pass/fail gates may change
as Pine tuning and training continue. When a runbook no longer matches accepted
TradingView/Optuna evidence, update it before launching the next batch.

Current lock state (2026-04-30): use `indicators/warbird-pro-indicator.pine`
as the only active main chart indicator, keep Nexus retained, and run 5m tuning
without altering Warbird Pro fib anchor ownership or ladder math unless
explicitly approved.

## Active

- `docs/runbooks/startup_repo_review.md`
  - required fresh-chat/start-of-day read-only repo initialization and report checklist
- `docs/runbooks/strategy_tuning.md`
  - TradingView/Pine settings sweep workflow; must be interpreted through the
    2026-04-30 Warbird Pro + Nexus active surface
- `docs/runbooks/claude_rogue_proof_phase_contract.md`
  - fail-closed phased tuning guardrails for Claude execution, updated for the
    Warbird Pro + Nexus active surface
- `CLAUDE.md`
  - current operational truth
- `docs/agent-safety-gates.md`
  - fail-closed verification gates

## Legacy

- `docs/runbooks/wbv7_institutional_optuna.md`
  - superseded v7 institutional indicator Optuna workflow
- `docs/runbooks/optuna_legacy_strategy_tuning.md`
  - archived single-lane Optuna note

Warehouse runbooks and skills are legacy unless Kirk explicitly reopens the
old local `ag_training` architecture.
