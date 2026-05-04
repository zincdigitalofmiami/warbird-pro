# Candidate Identity Contract

**Date:** 2026-04-26
**Status:** Active

## Purpose

Defines identity for active-contract modeling rows and trials.

## Same-Run Rule

Two source files belong to the same modeling run only when all of the following
match:

- source kind / capture method
- indicator file when the source is a Pine/TradingView export
- repo commit or indicator version
- symbol
- timeframe
- export date range
- Pine input settings
- TradingView Strategy Tester properties where applicable

## Row Identity

For indicator-state rows, identity is:

- export manifest hash
- bar timestamp
- direction/state fields when present

For Databento market-data rows, identity is:

- source manifest hash
- symbol / normalized root
- bar timestamp
- timeframe / schema

For Strategy Tester trades, identity is:

- export manifest hash
- trade number or TradingView trade id if present
- entry timestamp
- exit timestamp
- direction

## Replay Rule

Re-exporting the same settings and date range should produce the same manifest
hash or be recorded as a new export with a reason. Do not silently merge
conflicting exports.
