# Pine Indicator AG Contract

**Date:** 2026-04-26
**Status:** Active modeling contract

## Purpose

This contract defines the active Warbird training/modeling surface: pure
PineScript indicator behavior on TradingView.

## Source Of Truth

Training rows may come only from:

- TradingView indicator CSV exports
- TradingView Strategy Tester trade exports
- CDP-read Strategy Tester data
- deterministic columns derived from those Pine/TradingView exports

No external feature stack is admitted.

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
- export method (`CSV`, `STRATEGY_TESTER_CSV`, `CDP_REPORT_DATA`)
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
