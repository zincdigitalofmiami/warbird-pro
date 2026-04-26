---
name: training-tv-backtesting
description: TradingView Strategy Tester workflow for validating Pine Script strategies and indicator outputs under the indicator-only AG contract.
---

> **2026-04-26 indicator-only reset:** This skill remains active only for Pine/TradingView output modeling. Do not join FRED, macro, local `ag_training`, Databento-ingestion, or other external features.
> **Ongoing tuning note:** Current trigger families, settings, thresholds, and
> search spaces are evidence snapshots. Re-read the active docs before each run
> and update Markdown when new TradingView/Optuna/AG/SHAP evidence changes the
> accepted contract.

# Training — TradingView Backtesting

Use TradingView Desktop and Strategy Tester as the primary evidence loop for
indicator-only modeling.

## When To Use

- Validating `v7-warbird-strategy.pine` or the backtest wrapper after Pine changes
- Comparing a new stop/entry/settings policy against the baseline
- Capturing real Strategy Tester evidence for Optuna/AG settings modeling
- Reviewing specific trades from exported Pine/TradingView outputs

## Required Evidence

- indicator/strategy file
- repo commit
- symbol and timeframe
- date range
- full Pine input settings
- commission, slippage, Bar Magnifier, and fill settings
- Strategy Tester summary
- trade list or CDP `reportData().trades()` payload

## Required Settings

- Order size: 1 MES contract unless the test explicitly documents otherwise
- Commission: at least $1.00/side
- Slippage: at least 1 tick
- Bar Magnifier: ON when intrabar stop/target behavior matters
- Deep Backtesting: ON when available and needed for the stated date range

Use the values pinned in the active strategy declaration when they differ from
manual UI defaults.

## Boundaries

- TradingView output is the evidence source.
- Do not cross-reference local `ag_training`.
- Do not use Databento roll conventions as training truth.
- Do not claim a champion setting without held-out or walk-forward-style review.

## Gates Before Pine Commit

1. pine-facade compile
2. `./scripts/guards/pine-lint.sh <file>`
3. `./scripts/guards/check-contamination.sh`
4. `npm run build`
5. `./scripts/guards/check-indicator-strategy-parity.sh` when v7 parity is touched
