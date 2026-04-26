# Warbird Cloud Scope

**Date:** 2026-04-26
**Status:** Active Cloud Scope
**Governing plan:** Warbird Indicator-Only AG Plan v6

Cloud Supabase is runtime/support only. It is not an active model-training
database and must not become a mirror of local Pine/TradingView modeling
artifacts.

## Allowed Cloud Roles

Cloud may support:

- frontend/dashboard runtime
- auth and admin runtime
- live chart data already used by the app
- Pine alert/webhook support if explicitly approved
- operational health logging

## Explicitly Out Of Scope For Cloud

Cloud must not receive:

- raw TradingView exports
- raw Strategy Tester trade lists
- raw Optuna trial tables
- raw AutoGluon/SHAP artifacts
- full research datasets
- training labels
- local `ag_training` or legacy AG lineage tables
- FRED/macro/cross-asset feature warehouses for active modeling

## Training Boundary

Active training/modeling happens locally from Pine/TradingView outputs. Daily or
hourly ingestion is not a training source. If runtime ingestion remains for the
dashboard, it is not evidence for model training unless explicitly exported from
Pine/TradingView under the active contract.

## Review Rule

Before any cloud object is added, answer:

1. Does it serve live runtime/support rather than training?
2. Can the indicator-only modeling program run without it?
3. Does it avoid storing raw trials, labels, or research artifacts?

If any answer is no, the object does not belong in cloud.
