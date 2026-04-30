# Warbird Indicator-Only Optuna Plan v6

**Date:** 2026-04-30
**Status:** Active architecture plan

## Summary

Warbird training is a pure PineScript indicator modeling program.

The active goal is to perfect the TradingView indicator itself: settings, state
machine, entries, exits, filters, hidden exports, and visual/operator build.
Optuna and supporting scripts may be used offline, but only to model and rank
PineScript indicator behavior. They do not create a separate data-stack
decision engine.

Single-surface update (2026-04-30): the only active main chart indicator is
`indicators/warbird-pro-indicator.pine`. Nexus remains as the only retained
support/research Pine lane:

- `indicators/warbird-nexus-machine-learning-rsi.pine`
- `indicators/warbird-nexus-machine-learning-rsi-optuna-fast-test.pine`

All other Pine indicator, strategy, backtest, and fib-only variants are retired
from the active `indicators/` surface.

## Current Contract

- The canonical modeling object is the `Warbird Pro` Pine indicator behavior on
  TradingView.
- Training truth comes from Pine/TradingView outputs emitted by
  `indicators/warbird-pro-indicator.pine` and, for Nexus work only, the retained
  Nexus Pine files.
- Allowed evidence includes TradingView indicator exports, hidden `ml_*` /
  `nexus_fp_*` plots, embedded `request.footprint()` evidence, and deterministic
  Pine-derived state columns.
- The optimization target is indicator quality: settings, thresholds, module
  toggles, stop/target policy, signal frequency, profit factor, drawdown,
  stability, direction balance, and operator usability.
- External feature stacking is out of scope. No FRED, macro, news, options,
  cross-asset, Supabase, or Databento-derived feature joins are admitted into
  the active modeling dataset.
- Cloud Supabase is runtime/support only. It is not a model-training mirror and
  does not receive raw trials, raw labels, or full research datasets.

## Active Surfaces

- Main chart indicator:
  - `indicators/warbird-pro-indicator.pine`
- Retained Nexus support/research lane:
  - `indicators/warbird-nexus-machine-learning-rsi.pine`
  - `indicators/warbird-nexus-machine-learning-rsi-optuna-fast-test.pine`
- Optimization and modeling tools:
  - `scripts/optuna/`
  - `scripts/ag/tv_auto_tune.py`
  - `scripts/ag/tune_strategy_params.py`
- Artifacts:
  - `artifacts/tuning/`
  - `scripts/optuna/workspaces/<indicator_key>/`

## Non-Goals

The following are explicitly retired from the active plan:

- building a daily-ingestion training warehouse
- using local legacy warehouse training tables (`ag_training`) as the model source
- training on FRED, macro, news, options, or cross-asset features
- reconstructing Pine behavior from Python OHLCV as the canonical label path
- promoting a live model packet that scores separate server-side features
- using cloud Supabase as a training database
- reviving deleted Pine strategy, backtest, or fib-only variants without an
  explicit architecture reopen

## Trigger Families

Every modeling run must declare exactly one trigger family:

- `LIVE_ANCHOR_FOOTPRINT`: entries from `warbird-pro-indicator.pine`
  `entryLongTrigger` / `entryShortTrigger`.
- `NEXUS_FOOTPRINT_DELTA`: Nexus lower-pane footprint-delta evidence from the
  retained Nexus Pine files. Rows must come from TradingView/Pine
  `request.footprint()` `nexus_fp_*` evidence.

Deleted strategy/backtest trigger families are inactive unless Kirk explicitly
reopens them in a new plan update.

## Plan Phases

### Phase 0 - Authority Reset

Keep the active authority docs aligned with the single main indicator plus
retained Nexus lane.

Required surfaces:

- `AGENTS.md`
- `docs/INDEX.md`
- `docs/MASTER_PLAN.md`
- `docs/contracts/`
- `docs/runbooks/`
- `docs/cloud_scope.md`
- `WARBIRD_MODEL_SPEC.md`
- `CLAUDE.md`
- `README.md`

### Phase 1 - Pine Baseline Lock

Before modeling any settings, lock the exact Pine build being optimized.

Required facts:

- source file path
- TradingView symbol and timeframe
- indicator version / commit
- exported columns
- Pine input defaults
- trigger family
- plot/request budget
- compile/lint status

No Pine code changes are allowed without explicit session approval.

### Phase 2 - Pine Output Capture

Capture training rows from TradingView/Pine only.

Allowed sources:

- TradingView indicator CSV export from `warbird-pro-indicator.pine`
- hidden `ml_*` export fields emitted by that indicator
- retained Nexus `nexus_fp_*` footprint exports for `NEXUS_FOOTPRINT_DELTA`
- deterministic artifacts produced from those Pine outputs

Required manifest fields:

- indicator file
- repo commit
- symbol
- timeframe
- TradingView export range
- Pine input settings
- trigger family and source Pine file
- row count
- export hash
- notes on missing or platform-limited fields

### Phase 3 - Settings And Build Modeling

Run Optuna modeling only against Pine-derived trial data.

Permitted modeling questions:

- Which input settings improve profit factor, win rate, expectancy, drawdown,
  trade density, and yearly consistency?
- Which filter/module toggles improve or damage the signal?
- Which stop/target policy works best inside the current Pine state machine?
- Which Pine states or `ml_*` / `nexus_fp_*` exports explain winners versus
  failures?
- Which settings are robust across IS/OOS windows?

Prohibited modeling questions:

- Which macro/FRED/cross-asset feature should gate trades?
- Which server-side model should score live alerts?
- Which warehouse feature should be joined into the indicator decision?

### Phase 4 - Explainability And Recommendation

Use feature-importance analysis from Optuna results to convert model outputs
into actionable Pine settings/build recommendations.

The output is a settings/build brief:

- champion settings
- rejected settings
- feature/module importance
- stability notes
- expected row/trade-state count
- known failure modes
- recommended Pine edits, if any

### Phase 5 - Pine Implementation

Only after Kirk approval, apply Pine changes or default-setting changes.

Required gates after any `.pine` edit:

1. pine-facade compile check
2. `./scripts/guards/pine-lint.sh <file>`
3. `./scripts/guards/check-fib-scanner-guardrails.sh`
4. `./scripts/guards/check-contamination.sh`
5. `npm run build`

Indicator/strategy parity is inactive because no active strategy Pine file
exists in `indicators/`.

### Phase 6 - Promotion

Promotion is manual. A champion means:

- the TradingView indicator settings/build are approved
- the evidence and artifacts are saved
- docs and runbooks are updated
- no separate server-side scoring engine is implied

## Pine Budget Baseline

Verified 2026-04-30:

- `warbird-pro-indicator.pine`: 53 plot calls + 3 alertcondition calls =
  56/64 output calls; 4 `request.security()` calls + 1 `request.footprint()`
  path.

Any Pine addition must be priced before code is written. Nexus request/output
budgets must be repriced before any Nexus edit.

## Verification Locks

- No mock data.
- No external feature stacking.
- No daily-ingestion training dependency.
- No Pine edits without explicit approval.
- Canonical fib and trade-state semantics are locked in
  `indicators/warbird-pro-indicator.pine`: anchor ownership, fib ladder
  construction (`fibPrice` + canonical levels), entry/stop/target state, and
  `ml_last_exit_outcome` semantics are protected scope.
- Banned regression pattern (repo-wide): do not use the pivot-window
  `fibHtfSnapshot` variant with `ta.barssince(...)` and
  `pivotHighInWindow` / `pivotLowInWindow`; it has repeatedly produced wide-fib
  failures.
- No settings result is trusted without TradingView indicator export evidence.
- No champion is accepted without IS/OOS or walk-forward-style review.

## Current Blocker

Re-baseline `indicators/warbird-pro-indicator.pine` as the single active main
indicator, then run controlled 5m non-fib tuning from manifest-backed
TradingView indicator exports. Keep Nexus available only for its retained
footprint/research lane.
