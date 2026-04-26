# Pine Execution Semantics Contract

**Date:** 2026-04-26
**Status:** Active

## Purpose

The active execution semantics are the Pine/TradingView semantics of the
indicator or strategy being modeled.

## Rules

- Do not reconstruct a separate Python execution engine as canonical truth.
- When Strategy Tester is the source, TradingView's trade list and settings are
  the execution evidence.
- When indicator CSV is the source, only exported Pine state can be modeled.
- Any Python post-processing must document exactly which Pine fields it reads and
  which deterministic formulas it applies.

## Required Manifest Fields

- `process_orders_on_close`
- `use_bar_magnifier`
- `fill_orders_on_standard_ohlc`
- commission
- slippage
- date range
- symbol/timeframe
- Pine input settings

## Conflict Rule

If Python post-processing disagrees with TradingView output, TradingView output
wins unless the Pine script itself is being repaired and the user approved that
repair.
