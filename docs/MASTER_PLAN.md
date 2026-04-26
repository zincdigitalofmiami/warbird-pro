# Warbird Indicator-Only AG Plan v6

**Date:** 2026-04-26
**Status:** Active architecture plan

## Summary

Warbird training is now a pure PineScript indicator modeling program.

The active goal is to perfect the TradingView indicator itself: its settings,
state machine, entries, exits, filters, and visual/operator build. AutoGluon,
Optuna, SHAP, and supporting scripts may be used offline, but only to model and
rank PineScript indicator behavior. They do not create a separate data-stack
decision engine.

## Current Contract

- The canonical modeling object is the Pine indicator/strategy behavior on
  TradingView.
- Training truth comes from Pine/TradingView outputs: indicator exports,
  Strategy Tester trade lists, and deterministic Pine-derived state columns.
- The optimization target is indicator quality: settings, thresholds, module
  toggles, stop/target policy, signal frequency, profit factor, drawdown,
  yearly stability, direction balance, and operator usability.
- External feature stacking is out of scope. No FRED, macro, news, options,
  cross-asset, Supabase, or Databento-derived feature joins are admitted into
  the active modeling dataset.
- Daily/hourly ingestion is not a training source. It may remain only for live
  chart serving or legacy runtime support where already deployed.
- Local `warbird` warehouse AG tables and `ag_training` are superseded as active
  training truth. They remain reference-only unless explicitly reopened.
- Cloud Supabase is runtime/support only. It is not a model-training mirror and
  does not receive raw trials, raw labels, raw SHAP, or full research datasets.

## Active Surfaces

- Primary Pine work surface:
  - `indicators/v7-warbird-institutional.pine`
- Backtest/modeling surfaces:
  - `indicators/v7-warbird-strategy.pine`
  - `indicators/v7-warbird-institutional-backtest-strategy.pine`
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
- using `ag_training` as the model source
- training on FRED, macro, news, options, or cross-asset features
- reconstructing Pine behavior from Python OHLCV as the canonical label path
- promoting a live model packet that scores separate server-side features
- using cloud Supabase as a training database

## Plan Phases

### Phase 0 — Authority Reset

Update the repo authority docs so every active Markdown surface says the same
thing: indicator-only Pine modeling is the active contract.

Required updates:

- `AGENTS.md`
- `docs/INDEX.md`
- `docs/MASTER_PLAN.md`
- `docs/contracts/`
- `docs/runbooks/`
- `docs/cloud_scope.md`
- `WARBIRD_MODEL_SPEC.md`
- `CLAUDE.md`
- `README.md`

### Phase 1 — Pine Baseline Lock

Before modeling any settings, lock the exact Pine build being optimized.

Required facts:

- source file path
- TradingView symbol and timeframe
- indicator version / commit
- exported columns or Strategy Tester fields
- Pine input defaults
- plot/request budget
- compile/lint status
- backtest property assumptions: commission, slippage, bar magnifier, fill model

No Pine code changes are allowed without explicit session approval.

### Phase 2 — Pine Output Capture

Capture training rows from TradingView/Pine only.

Allowed sources:

- TradingView indicator CSV export
- TradingView Strategy Tester trade export
- CDP-read Strategy Tester data from `tv_auto_tune.py`
- deterministic artifacts produced from those Pine outputs

Required manifest fields:

- indicator file
- repo commit
- symbol
- timeframe
- TradingView export range
- Pine input settings
- TradingView tester properties
- row count / trade count
- export hash

### Phase 3 — Settings And Build Modeling

Run Optuna/AG-style modeling only against Pine-derived trial data.

Permitted modeling questions:

- Which input settings improve profit factor, win rate, expectancy, drawdown,
  trade density, and yearly consistency?
- Which filter/module toggles improve or damage the signal?
- Which stop/target policy works best inside the current Pine state machine?
- Which Pine states or `ml_*` exports explain winners versus failures?
- Which settings are robust across IS/OOS windows?

Prohibited modeling questions:

- Which macro/FRED/cross-asset feature should gate trades?
- Which server-side model should score live alerts?
- Which warehouse feature should be joined into the indicator decision?

### Phase 4 — Explainability And Recommendation

Use SHAP or equivalent importance analysis to convert model results into
actionable Pine settings/build recommendations.

The output is not a live model packet. The output is a settings/build brief:

- champion settings
- rejected settings
- feature/module importance
- stability notes
- expected trade count
- known failure modes
- recommended Pine edits, if any

### Phase 5 — Pine Implementation

Only after Kirk approval, apply Pine changes or default-setting changes.

Required gates after any `.pine` edit:

1. pine-facade compile check
2. `./scripts/guards/pine-lint.sh <file>`
3. `./scripts/guards/check-contamination.sh`
4. `npm run build`
5. parity guard when v7 indicator/strategy coupling is touched

### Phase 6 — Promotion

Promotion is manual. A champion means:

- the TradingView indicator settings/build are approved
- the evidence and artifacts are saved
- docs and runbooks are updated
- no separate server-side scoring engine is implied

## Pine Budget Baseline

Verified 2026-04-26:

- `v7-warbird-institutional.pine`: 58/64 output calls, 4
  `request.security()` calls + 1 `request.footprint()` path
- `v7-warbird-strategy.pine`: 60/64 output calls, 4
  `request.security()` calls + 1 `request.footprint()` path
- `v7-warbird-institutional-backtest-strategy.pine`: 53/64 output calls, 4
  `request.security()` calls + 1 `request.footprint()` path

Any Pine addition must be priced before code is written.

## Verification Locks

- No mock data.
- No external feature stacking.
- No daily-ingestion training dependency.
- No Pine edits without explicit approval.
- No strategy result is trusted without TradingView export/CDP evidence.
- No champion is accepted without IS/OOS or walk-forward-style review.
- Commission floor is $1.00/side for MES.
- Slippage floor is 1 tick.
- Bar Magnifier must be enabled for reported Strategy Tester results where
  intrabar stop/target behavior matters.

## Current Blocker

The next blocking item is to align the active scripts and runbooks to this
indicator-only contract, then run a fresh Pine-derived baseline export before
launching any modeling.
