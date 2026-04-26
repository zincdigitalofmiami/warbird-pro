# Warbird Runbooks

**Date:** 2026-04-26
**Status:** Active Runbook Index

The active runbooks support indicator-only Pine modeling.

Canonical Optuna hub: `http://127.0.0.1:8090/`.
Canonical Nexus lane: `http://127.0.0.1:8090/studies/warbird_nexus_ml_rsi`.
Do not create alternate hub processes, workspaces, or replacement Nexus study
names for active tuning.

## Iteration Rule

Runbooks are operational snapshots for the current tuning cycle. Trigger
families, settings spaces, export requirements, and pass/fail gates may change
as Pine tuning and training continue. When a runbook no longer matches accepted
TradingView/Optuna/AG evidence, update it before launching the next batch.

## Active

- `docs/runbooks/strategy_tuning.md`
  - TradingView/Pine settings sweep workflow
- `docs/runbooks/wbv7_institutional_optuna.md`
  - v7 institutional indicator Optuna workflow
- `CLAUDE.md`
  - current operational truth
- `docs/agent-safety-gates.md`
  - fail-closed verification gates

## Legacy

- `docs/runbooks/optuna_legacy_strategy_tuning.md`
  - archived single-lane Optuna note

Warehouse AG runbooks and skills are legacy unless Kirk explicitly reopens the
old local `ag_training` architecture.
