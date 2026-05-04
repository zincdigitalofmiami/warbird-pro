# Warbird Pro 5m Tuning Runbook

**Date:** 2026-05-02
**Status:** Active — Warbird Pro main-indicator tuning lane

## Purpose

Tune `indicators/warbird-pro-v9.pine` on MES using manifest-backed active-lane
training data and produce defensible Pine settings or build recommendations.
TradingView/Pine exports and approved Databento ES/MES market-data training
rows are valid when the manifest declares the true source/capture kind. Nexus
remains a separate retained lane and is tuned only from TradingView/Pine
`request.footprint()` evidence for `NEXUS_FOOTPRINT_DELTA`.

No FRED, macro, cross-asset, Supabase, local legacy warehouse rows
(`ag_training`), synthetic OHLCV reconstruction, or mislabeled
Databento/TradingView artifact is admitted into the active modeling dataset.

## Active Pine Surfaces

- Main chart indicator: `indicators/warbird-pro-v9.pine`
- Nexus footprint tuning lane:
  `indicators/warbird-nexus-machine-learning-rsi-optuna-fast-test.pine`

Retired strategy/backtest/fib-only Pine variants are not active tuning sources:

- `indicators/warbird-pro-indicator.pine`
- `indicators/Warbird_Pro_v7.pine`
- `indicators/v7-warbird-institutional.pine`
- `indicators/v7-warbird-strategy.pine`
- `indicators/v7-warbird-institutional-backtest-strategy.pine`
- `indicators/fibs-only.pine`

## Trigger Families

Every run must declare exactly one active trigger family:

- `LIVE_ANCHOR_FOOTPRINT` for `warbird-pro-v9.pine`
- `NEXUS_FOOTPRINT_DELTA` for the Nexus footprint lane

`STRATEGY_ACCEPT_SCALP` and `BACKTEST_DIRECT_ANCHOR` are historical only unless
Kirk explicitly reopens a strategy/backtest harness.

## Locked Scope

Warbird Pro fib anchor ownership and ladder math are protected while 5m tuning
iterates. Do not modify:

- `fibZzUpdate()` semantics
- `fibAnchorHigh`, `fibAnchorLow`, `anchorHighBar`, `anchorLowBar`
- `fibBull`, `fibBase`, `fibDir`
- `fibPrice()` and canonical fib ratio construction
- fib draw-span semantics

Allowed tuning scope after explicit approval:

- non-fib risk gates
- pattern/structure/liquidity-sweep toggles
- EMA/MA crossover gate parameters
- ML RSI / KNN / filter parameters
- exhaustion thresholds
- execution anchor, ATR stop multiplier, and max-risk constraints

## Phase Framework

The campaign is phase-scoped and timeframe-scoped.

- Run each phase on **5m** and **15m** as separate surfaces.
- Promotion floor remains **1,000 authoritative trials per surface per phase**
  unless Kirk explicitly overrides it.
- Any helper script used for trials must be verified against the active
  Warbird Pro V9 file and trigger family; do not use scripts that require
  retired Pine files.

| Phase | Scope |
|---|---|
| A | Structure + execution anchor (`requireAcceptRetest`, `retestBars`, `optEntryLevelInput`, `signalCooldownBars`, fib hysteresis/range controls) |
| B | EMA/MA crossover gate (`useMaGate`, `lengthMA`, `lengthEMA`, short-gate controls) |
| C | Pattern and exhaustion strictness (`usePatternConfirm`, `useLiquiditySweepConfirm`, sweep lookback, `useExhaustion`, exhaustion tolerance) |
| D | ML filter surface (`useMlFilter`, RSI/KNN/filter parameters, thresholds, smoothing) |

## Evidence Requirements

Every recommendation must include:

- Pine file path and repo commit
- TradingView symbol and timeframe
- date range
- export method / source kind and manifest
- trigger family
- exact Pine input settings
- row count and trade count or event count
- export hash
- failure-mode notes

Nexus evidence must include the TradingView/Pine `request.footprint()`
`nexus_fp_*` snapshot manifest. CSV exports, local OHLCV parquet, Databento
bars, and synthetic body/wick delta are invalid for Nexus.

## Verification

Before committing any `.pine` edit:

1. `./scripts/guards/compile-pine.sh <file>`
2. `./scripts/guards/pine-lint.sh <file>`
3. `./scripts/guards/check-fib-scanner-guardrails.sh`
4. `./scripts/guards/check-contamination.sh`
5. `npm run build`

`./scripts/guards/check-indicator-strategy-parity.sh` is inactive while no
strategy harness exists.
