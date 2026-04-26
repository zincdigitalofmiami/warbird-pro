# v7 Pine Interface: Surface Divergences

**Date:** 2026-04-12
**Updated:** 2026-04-26
**Status:** Active - documents intentional mechanical divergences between the v7 files.

This is the current trigger-family snapshot during active tuning. It may change
after new TradingView evidence, Optuna runs, AG analysis, or SHAP review. Any
accepted change must update this file with the same commit that updates Pine,
settings, or runbooks.

## Institutional (`v7-warbird-institutional.pine`) — Live Chart Surface

- **Entry trigger:** `entryLongTrigger` / `entryShortTrigger` from the fib
  execution-anchor reclaim plus footprint gate path, not `acceptEvent`.
  The live chain is:
  - `entryLevel = fibPrice(optEntryRatio)`
  - setup context: fib direction, EMA/VWAP trend bias, entry-zone touch, ATR
    risk acceptance
  - anchor reclaim: long `low <= entryLevel and close >= entryLevel`; short
    `high >= entryLevel and close <= entryLevel`
  - footprint gate: long bullish delta plus stacked buy imbalance; short bearish
    delta plus stacked sell imbalance
  - one-shot event, ladder invalidation, and bullish-trend short gate
- **Purpose:** human-readable signal overlay, alert broadcast, live entry cue
- **Output budget:** 58/64 (55 plot + 3 alertcondition, 6 headroom)
- **Alerts:** 3 `alertcondition()` calls (ENTRY LONG, ENTRY SHORT, PIVOT BREAK)
- **Non-entry diagnostics:** `acceptEvent` still exists for pivot-interaction
  diagnostics, debug logging, and setup archetype fields; it does not fire the
  live entry alerts in the institutional file.

## Strategy (`v7-warbird-strategy.pine`) — Strategy Tester / Pine Modeling Surface

- **Entry trigger:** gated SETUP -> `acceptEvent` + confirmation path, with optional footprint scalp path and risk/ladder/HTF suppressors
- **Purpose:** Strategy Tester execution surface and Pine `ml_*` export-compatibility mirror. Active modeling uses TradingView/Pine outputs only.
- **Output budget:** 60/64 (60 plot, 4 headroom); uses `alert()` not `alertcondition()`
- **Exit:** SL or active target; TP1 by default with fast-runner target promotion where configured
- **Commission floor:** $1.00/side; `use_bar_magnifier=true`; `slippage=1` -
  pinned in `strategy()` declaration

## Shared Contract (must stay in sync)

- All `ml_*` hidden export field names must match between both files
- `stopFamilyCode`, `eventPivotInteractionCode`, `setupArchetypeCode` patterns identical
- All coupled input defaults must match (strategy is source of truth)
- Verified by `scripts/guards/check-indicator-strategy-parity.sh`

## Intentionally NOT Enforced by Guard

- Exit mechanics (alert-based lifecycle vs. SL/TP5 only)
- `alertcondition` presence (institutional has 3, strategy has 0)
- Strategy-only `strategy()` declaration with Bar Magnifier / commission / slippage pins
- Trigger-family equivalence across all wrappers. The backtest wrapper can run a
  direct fib-anchor Optuna path, while the live institutional indicator uses the
  anchor-reclaim plus footprint gate path.

## Closure Note: Trigger Divergence (reconciled 2026-04-26)

A prior entry in this doc claimed the strategy used a `candidateSetup` path
(`priceAtFibLevel` - any close within 15% ATR of 6 fib levels) while the
indicator used `acceptEvent`. That was stale in two directions:

- `candidateSetup` remains diagnostic/export-only in the strategy.
- The institutional live alerts do not use `acceptEvent`; they use the
  `entryLongTrigger` / `entryShortTrigger` anchor-reclaim plus footprint gate
  chain.

Under the current plan, this matters only for Pine/TradingView modeling
fidelity; there is no active Python warehouse training generator to reconcile
against.

## Rationale

The institutional file is optimized for human operator use: it shows
high-confidence fib-anchor reclaim signals confirmed by footprint evidence on
the chart. The strategy files are optimized for TradingView execution testing
and Pine export/modeling workflows. Offline modeling may rank settings and
build choices from those Pine outputs; it must not join external features or
replace Pine with a separate server-side decision engine.
