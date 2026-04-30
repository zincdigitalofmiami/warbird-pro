# Warbird Pro 5m Tuning Runbook

**Date:** 2026-04-30
**Status:** Active — Warbird Pro main-indicator tuning lane

## Purpose

Tune `indicators/warbird-pro-indicator.pine` on MES using only
TradingView/Pine evidence and produce defensible Pine settings or build
recommendations. Nexus remains a separate retained lane and is tuned only from
TradingView/Pine `request.footprint()` evidence.

No FRED, macro, cross-asset, Databento-ingestion, Supabase, local legacy
warehouse rows (`ag_training`), or synthetic OHLCV reconstruction is admitted
into the active modeling dataset.

## Active Pine Surfaces

- Main chart indicator: `indicators/warbird-pro-indicator.pine`
- Nexus support lane: `indicators/warbird-nexus-machine-learning-rsi.pine`
- Nexus footprint tuning lane:
  `indicators/warbird-nexus-machine-learning-rsi-optuna-fast-test.pine`

Retired strategy/backtest/fib-only Pine variants are not active tuning sources:

- `indicators/v7-warbird-institutional.pine`
- `indicators/v7-warbird-strategy.pine`
- `indicators/v7-warbird-institutional-backtest-strategy.pine`
- `indicators/fibs-only.pine`

## Trigger Families

Every run must declare exactly one active trigger family:

- `LIVE_ANCHOR_FOOTPRINT` for `warbird-pro-indicator.pine`
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
- trend/MA/VWAP/liquidity-sweep toggles
- momentum oscillator windows and weights
- footprint/exhaustion thresholds
- execution anchor, ATR stop multiplier, and max-risk constraints

## Phase Framework

The 5m campaign remains phase-scoped. Use explicit space files and do not run a
generic single-pass sweep as the authoritative campaign.

| Phase | Profile | Space file | Scope |
|---|---|---|---|
| 1 | `mes5m_phase1_trend_vwap_ma_liqsweep` | `scripts/ag/strategy_tuning_space.phase1.json` | trend / VWAP / MA / liquidity sweep |
| 2 | `mes5m_phase2_momentum` | `scripts/ag/strategy_tuning_space.phase2.json` | VF Window / VF Candle Weight / VF Volume Weight / NFE Length / RSI KNN Window |
| 3 | `mes5m_phase3_footprint_exhaustion` | `scripts/ag/strategy_tuning_space.phase3.json` | Ticks / VA / Imbalance% / Extension ATR Tol / Zero-Print / Swing Lookback / Cooldown / Imbalance Rows |
| 4 | `mes5m_phase4_entry_risk` | `scripts/ag/strategy_tuning_space.phase4.json` | Execution Anchor / ATR Stop Multiplier / Max Setup Stop ATR / Acceptance Retest Window |

The promotion floor for a phase remains **1,000 authoritative trials** unless
Kirk explicitly overrides it. Any helper script used for trials must first be
verified against the active Warbird Pro file and trigger family; do not use a
script path that still requires a retired Pine strategy file.

## Evidence Requirements

Every recommendation must include:

- Pine file path and repo commit
- TradingView symbol and timeframe
- date range
- export method and manifest
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
