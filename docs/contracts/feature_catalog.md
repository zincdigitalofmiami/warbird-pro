# Feature Catalog Contract

**Date:** 2026-04-26
**Status:** Active

## Purpose

Defines which fields are admitted into active indicator-only modeling.

## Active Feature Rule

A feature is admitted only if it is present in, or deterministically derived
from, the Pine/TradingView export used for the run.

Allowed feature families:

- Pine input settings
- Pine state-machine fields
- Pine `ml_*` hidden exports
- Strategy Tester trade fields
- OHLCV fields included in the TradingView export
- deterministic transformations of the same export

Disallowed feature families:

- FRED, macro, and economic calendar joins
- news/options fields
- cross-asset features
- Databento or Supabase ingestion tables
- local `ag_training` columns
- Python reconstructed fib features not emitted by Pine

## Point-In-Time Rule

Every modeling column must declare:

- source export
- source column
- whether it is a raw Pine field or deterministic derived field
- timestamp / trade identity
- whether it is available before the label being modeled

If point-in-time validity cannot be proven from the export, the field is not
admitted.
