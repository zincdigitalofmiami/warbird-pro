# Pine Export Payload Contract

**Date:** 2026-04-26
**Status:** Active

## Purpose

Defines the minimum metadata required for Pine/TradingView exports used in
indicator-only modeling.

## Required Identity Fields

- `indicator_file`
- `indicator_version` or repo commit
- `symbol`
- `timeframe`
- `export_start`
- `export_end`
- `export_method`
- `export_hash`

## Required Settings Fields

- full Pine input settings used for the export
- Strategy Tester commission/slippage/fill settings where applicable
- Bar Magnifier state where applicable

## Required Row/Trade Fields

The exact row fields may vary by export, but each run must document:

- time column
- OHLCV columns present
- Pine state columns present
- trade entry/exit columns present
- label/outcome columns present
- fields missing because TradingView did not export them

## Payload Rules

- UTC or explicitly documented exchange/chart timezone only.
- No unknown derived columns without formula documentation.
- No external joins.
- No post-outcome leakage columns in predictor sets.
- Missing fields must be documented instead of silently backfilled from another
  data source.
