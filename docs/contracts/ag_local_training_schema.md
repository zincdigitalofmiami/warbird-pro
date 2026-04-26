# AG Local Training Schema Contract — Superseded

**Date:** 2026-04-26
**Status:** Superseded reference only

The four-table local AG warehouse contract and `ag_training` view were part of
the retired warehouse/FRED/macro modeling plan.

They are not active training truth under Warbird Indicator-Only AG Plan v6.

Active modeling now uses Pine/TradingView outputs only. See:

- `docs/MASTER_PLAN.md`
- `docs/contracts/pine_indicator_ag_contract.md`
- `WARBIRD_MODEL_SPEC.md`

Do not build new writers, migrations, training scripts, SHAP workflows, or model
selection logic around `ag_fib_snapshots`, `ag_fib_interactions`,
`ag_fib_stop_variants`, `ag_fib_outcomes`, or `ag_training` unless Kirk
explicitly reopens the warehouse training architecture.
