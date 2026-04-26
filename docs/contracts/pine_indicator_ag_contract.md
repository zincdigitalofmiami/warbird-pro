# Pine Indicator AG Contract

**Date:** 2026-04-26
**Status:** Active modeling contract

## Purpose

This contract defines the active Warbird training/modeling surface: pure
PineScript indicator behavior on TradingView.

## Iteration Policy

The active contract is allowed to evolve as tuning and training continue.
Trigger families, settings, thresholds, search spaces, and labels are current
evidence snapshots. They must be versioned through Markdown updates whenever a
new TradingView export, Strategy Tester result, Optuna trial set, AG model, or
SHAP review changes the accepted understanding.

Do not reuse an old export or trial without checking that its trigger family and
settings still match the current contract.

## Source Of Truth

Training rows may come only from:

- TradingView indicator CSV exports for non-Nexus lanes
- TradingView Strategy Tester trade exports
- CDP-read Strategy Tester data
- TradingView/Pine `request.footprint()` `nexus_fp_*` snapshots for
  `NEXUS_FOOTPRINT_DELTA`
- deterministic columns derived from those Pine/TradingView exports

No external feature stack is admitted.

## Entry Trigger Authority

Every modeling run must declare which Pine trigger family produced its rows.
Do not mix trigger families inside one run.

- `LIVE_ANCHOR_FOOTPRINT`: live institutional trigger from
  `v7-warbird-institutional.pine`. Entries are
  `entryLongTrigger` / `entryShortTrigger`, built from the selected fib
  execution-anchor reclaim, setup context, footprint confirmation, one-shot
  gating, ladder validity, and the bullish-trend short gate.
- `STRATEGY_ACCEPT_SCALP`: Strategy Tester trigger from
  `v7-warbird-strategy.pine`. Entries are `acceptEvent` plus confirmation, or
  the optional footprint scalp path, with risk, ladder, HTF, and suppression
  gates.
- `BACKTEST_DIRECT_ANCHOR`: Optuna/backtest wrapper trigger from
  `v7-warbird-institutional-backtest-strategy.pine` when
  `Backtest Fib Anchor Hits Directly` is enabled. Entries fire from the selected
  fib execution-anchor hit/reclaim path and intentionally bypass the full live
  footprint/context path.
- `NEXUS_FOOTPRINT_DELTA`: Nexus lower-pane footprint-delta trigger from
  `warbird-nexus-machine-learning-rsi-optuna-fast-test.pine`. Rows must come
  from TradingView/Pine `request.footprint()` evidence containing `nexus_fp_*`
  fields. CSV exports, local OHLCV parquet, Databento bars, and synthetic
  body/wick delta are not valid tuning evidence for this trigger family.

`acceptEvent` alone is not the live institutional entry trigger. It is a
diagnostic/setup-archetype event unless a specific strategy surface uses it as
part of its own execution path.

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
- export method (`CSV`, `STRATEGY_TESTER_CSV`, `CDP_REPORT_DATA`,
  `TV_FOOTPRINT_PARQUET`)
- trigger family
- Pine input settings
- Strategy Tester properties where applicable
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

Invalid recommendations:

- server-side feature gates
- cloud scoring packets
- macro/FRED gates
- daily-ingestion dependencies
- invisible data joins not present in Pine output

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
