# Pine Indicator Optuna Contract

**Date:** 2026-04-30
**Status:** Active modeling contract

## Purpose

This contract defines the active Warbird training/modeling surface: pure
PineScript indicator behavior on TradingView.

## Iteration Policy

The active contract is allowed to evolve as tuning and training continue.
Trigger families, settings, thresholds, search spaces, and labels are current
evidence snapshots. They must be versioned through Markdown updates whenever a
new TradingView export or Optuna trial set changes the accepted understanding.

Do not reuse an old export or trial without checking that its trigger family and
settings still match the current contract.

V9 lane contract (2026-05-02): `warbird_pro_v9` is a separate Optuna lane over
the active Warbird Pro rebuild indicator. It does not create a new Pine source,
does not authorize Pine edits, and does not mutate the canonical fib anchor,
fib visual, or EMA/MA setup. It admits manifest-backed ES/MES TradingView
indicator CSV exports only and ignores NQ/MNQ exports.

## Source Of Truth

Training rows may come only from:

- TradingView indicator CSV exports for non-Nexus lanes
- TradingView/Pine `request.footprint()` `nexus_fp_*` snapshots for
  `NEXUS_FOOTPRINT_DELTA`
- deterministic columns derived from those Pine/TradingView exports

No external feature stack is admitted.

`warbird_pro_v9` may load ES and MES exports as separate rows from the same
active Warbird Pro Pine surface. NQ/MNQ rows are ignored. No cross-symbol join,
NQ leadership feature, Databento join, cloud table, or external feature stack is
admitted into this lane.

## Entry Trigger Authority

Every modeling run must declare which Pine trigger family produced its rows.
Do not mix trigger families inside one run.

- `LIVE_ANCHOR_FOOTPRINT`: live Warbird Pro trigger from
  `indicators/warbird-pro-rebuild-fib-ml.pine`. Entries are
  `entryLongTrigger` / `entryShortTrigger`, built from the selected fib
  execution-anchor reclaim, structure context, winning candlestick confirmation,
  EMA/MA crossover alignment, optional ML RSI filtering, optional
  liquidity-sweep confirmation, one-shot gating, ladder validity, and the
  bullish-trend short gate. (The trigger-family name is legacy and retained for
  continuity.)
- `NEXUS_FOOTPRINT_DELTA`: Nexus lower-pane footprint-delta trigger from
  `indicators/warbird-nexus-machine-learning-rsi-optuna-fast-test.pine`. Rows
  must come from TradingView/Pine `request.footprint()` evidence containing
  `nexus_fp_*` fields. CSV exports, local OHLCV parquet, Databento bars, and
  synthetic body/wick delta are not valid tuning evidence for this trigger
  family.

`acceptEvent` alone is not the live Warbird Pro entry trigger. It is a
diagnostic/setup-archetype event unless a future explicitly reopened strategy
surface defines it as part of its own execution path.

Retired trigger families are historical only unless Kirk explicitly reopens
them with a new active strategy/backtest harness:

- `STRATEGY_ACCEPT_SCALP`
- `BACKTEST_DIRECT_ANCHOR`

## Locked Fib Baseline (2026-04-30)

Warbird Pro fib core in `indicators/warbird-pro-rebuild-fib-ml.pine` is the
protected baseline. It must remain stable while 5m tuning iterates.

Protected scope:

- `fibZzUpdate()` and ZigZag settings semantics
- anchor ownership/state transition logic for fib legs
- fib ladder construction via `fibPrice` and canonical fib ratios
- active fib draw span and chart-level construction

Allowed tuning scope while lock is active:

- non-fib thresholds and safety gates
- lookback/cooldown controls outside fib anchor math
- pattern/EMA-MA/ML gating strictness and execution toggles

Any proposed fib-core change requires explicit approval plus before/after
TradingView evidence with manifest coverage.

## Warbird Pro V9 Exit Modeling

The `warbird_pro_v9` lane models ATR/risk exits from existing Warbird Pro rebuild
entry triggers. It must not treat `-.236` or any negative fib extension as a stop
family/candidate. If `-.236` is exported, it is context only and may be carried
as `fib_neg_0236_context`.

Frozen during V9:

- fib anchor ownership and ZigZag settings
- fib ladder/visual construction
- EMA/MA setup inputs and visual display
- Pine source code until promotion approval

## Explicit Exclusions

The active modeling dataset must not join:

- FRED or macro data
- economic calendar data
- news/options data
- cross-asset futures data
- Supabase cloud tables
- Databento daily/hourly ingestion tables
- local `ag_training` rows
- Python reconstructed fib interactions

## Required Export Manifest

Every modeling run must record:

- indicator file path
- repo commit
- TradingView symbol
- timeframe
- export date range
- export method (`CSV` for Warbird Pro indicator exports, `TV_FOOTPRINT_PARQUET`
  for Nexus request.footprint snapshots)
- trigger family
- Pine input settings
- row count and trade count
- export hash
- notes on missing or platform-limited fields

## Modeling Target

The target is a Pine settings/build recommendation.

Valid recommendations:

- input default changes
- search-space narrowing
- module keep/remove decisions
- threshold changes
- stop/target policy changes
- Pine code-change proposals for explicit approval
- V9 ATR/risk exit policy recommendations from ES/MES export evidence

Invalid recommendations:

- server-side feature gates
- cloud scoring packets
- macro/FRED gates
- daily-ingestion dependencies
- invisible data joins not present in Pine output
- V9 promotion based on NQ/MNQ, negative-fib stop candidates, or Pine edits made
  before explicit promotion approval

## Validation

A champion setting/build requires:

- real TradingView evidence
- no mock rows
- exact manifest
- IS/OOS or walk-forward-style review
- commission and slippage assumptions recorded
- failure modes documented

## Promotion

Promotion is manual. A promoted result updates Pine settings/build docs and, only
after approval, Pine defaults or code. It does not imply server-side live model
deployment.
