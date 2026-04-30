# Warbird Model Spec — Indicator-Only v6

**Date:** 2026-04-30
**Status:** Active, subordinate to `docs/MASTER_PLAN.md`

## Contract

Warbird modeling is now pure PineScript indicator modeling.

The model program exists to improve the TradingView indicator settings and
build. It does not create a separate live prediction engine and it does not
train from external data stacks.

## Iteration Policy

Tuning and training are ongoing. Current trigger families, settings, thresholds,
search spaces, labels, and recommended build choices are mutable evidence
snapshots. They may be revised after new Pine/TradingView exports, Strategy
Tester evidence, and Optuna trials.

Any accepted model-contract change must update this spec, the Master Plan, the
active contract docs, and the relevant runbooks before the result is considered
ready for reuse by another agent.

## Training Truth

Allowed training inputs are only:

- TradingView indicator CSV exports for non-Nexus lanes
- TradingView/Pine `request.footprint()` `nexus_fp_*` snapshots for Nexus ML RSI
- deterministic features derived from those Pine/TradingView outputs

Disallowed active training inputs:

- FRED or macro joins
- news/options data
- cross-asset joins
- Databento or Supabase daily/hourly ingestion as a training feature source
- local `ag_training` warehouse rows
- Python OHLCV reconstruction as the canonical label source

Historical warehouse tables may remain on disk for lineage. They are not active
model truth unless Kirk explicitly reopens that architecture.

## Model Objective

The model evaluates Pine settings and build choices.

Primary outputs:

- champion Pine input settings
- rejected Pine input settings
- module keep/remove recommendations
- stop/target policy recommendations
- signal-frequency and trade-quality diagnostics
- failure-mode notes

Primary metrics:

- profit factor
- net profit
- expectancy per trade
- win rate
- max drawdown
- return over drawdown
- trade count and trade density
- long/short balance
- yearly and walk-forward stability
- footprint-rich versus footprint-poor cohort stability where available

## Active Pine Surfaces

- `indicators/warbird-pro-indicator.pine`
  - only active main chart indicator
  - live entry trigger: `entryLongTrigger` / `entryShortTrigger` from the
    selected fib execution-anchor reclaim plus setup context, footprint
    confirmation, ladder validity, optional MA/VWAP gates, and the bullish-trend
    short gate
- `indicators/warbird-nexus-machine-learning-rsi.pine`
  - retained Nexus lower-pane support surface
- `indicators/warbird-nexus-machine-learning-rsi-optuna-fast-test.pine`
  - retained Nexus lower-pane footprint-delta research/tuning surface
  - active trigger family: `NEXUS_FOOTPRINT_DELTA`
  - footprint delta must come from TradingView/Pine `request.footprint()`
    `nexus_fp_*` fields; CSV exports, local OHLCV parquet, and synthetic
    body/wick delta are invalid tuning evidence for this surface

Retired/removed Pine variants are historical lineage only:

- `indicators/v7-warbird-institutional.pine`
- `indicators/v7-warbird-strategy.pine`
- `indicators/v7-warbird-institutional-backtest-strategy.pine`
- `indicators/fibs-only.pine`
- `v8-warbird-live.pine`
- `v8-warbird-prescreen.pine`

## Locked Baseline Checkpoint (2026-04-27)

Operator checkpoint summary from TradingView strategy snapshots:

- 15m: +6.74% PnL, PF 1.143, 434 trades, 3.47% max drawdown
- 5m: -2.55% PnL, PF 0.91, 295 trades, 3.44% max drawdown
- 1h: -9.26% PnL, PF 0.929, 801 trades, 14.33% max drawdown

Policy from this checkpoint:

- 15m behavior remains a historical reference baseline for fib and structure
  semantics.
- 5m remains the active tuning lane.
- The protected fib core now lives in
  `indicators/warbird-pro-indicator.pine`. No strategy/backtest Pine harness is
  active unless Kirk explicitly reopens one.

Protected fib-core scope in `indicators/warbird-pro-indicator.pine`:

- ZigZag/fib anchor ownership transitions (`fibAnchorHigh/Low`, anchor bars,
  `fibZzUpdate()`, `fibBull`)
- fib ladder math (`fibPrice`, canonical retracement/extension level construction)
- active fib draw span and level construction

Allowed tuning scope while locked:

- non-fib risk gates, trigger thresholds, reclaim/sweep lookbacks, cooldowns
- footprint gating strictness and execution safety parameters
- module on/off decisions that do not alter fib math or anchor state ownership

## Feature Scope

Feature scope is indicator-only.

Admitted feature families:

- Pine input settings
- Pine state-machine fields
- Pine `ml_*` hidden exports
- Nexus `nexus_fp_*` footprint fields from TradingView/Pine
  `request.footprint()`
- OHLCV columns included in the TradingView export
- deterministic columns computed only from the same Pine export

Not admitted:

- server-side macro/fundamental context
- FRED/economic calendar fields
- Databento cross-asset context
- Supabase/cloud serving tables
- local warehouse reconstructed fib rows

## Label Scope

Labels resolve from Pine/TradingView outputs only.

Allowed labels:

- trade profit/loss
- Pine state outcomes such as `ml_last_exit_outcome`
- TP/SL-style state outcomes emitted by the active Pine indicator
- derived binary or multiclass labels computed from exported Pine trade/state
  fields

Any label must be tied to the export manifest and cannot use future columns not
available in the Pine/TradingView output.

## Explainability

Feature-importance analysis from Optuna runs is used to explain settings and
build choices, not to publish a live server model.

Required explanation outputs:

- setting importance
- module/toggle importance
- cohort stability
- long/short asymmetry
- yearly or walk-forward drift
- failure modes that require Pine review

## Packet Rule

There is no active server-side scoring packet requirement.

The promotion artifact is a Pine settings/build brief containing:

- indicator file and commit
- symbol/timeframe
- TradingView export manifest
- trigger family used for evidence
- champion settings
- validation metrics
- rejected settings
- recommended Pine code/default changes

## Runtime Boundary

Supabase and Databento ingestion may remain for live chart/runtime support, but
they are not active training sources. Cloud must not receive raw trial data,
raw labels, or full research datasets.

## Verification

Before any Pine build or settings promotion:

- verify the Pine source compiles through pine-facade
- run `pine-lint.sh`
- run contamination guard
- run `npm run build`
- save the TradingView export or CDP evidence
- document the exact settings and date range

## Legacy

The following are legacy for active modeling:

- `ag_fib_snapshots`
- `ag_fib_interactions`
- `ag_fib_stop_variants`
- `ag_fib_outcomes`
- `ag_training`
- local warehouse lineage tables
- FRED/macro feature scope
- Python reconstruction as canonical training generator
- server-side model packet promotion
