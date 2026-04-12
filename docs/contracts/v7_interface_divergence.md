# v7 Pine Interface: Surface Divergences

**Date:** 2026-04-12
**Updated:** 2026-04-13
**Status:** Active — documents intentional mechanical divergences between the two v7 files.

## Institutional (`v7-warbird-institutional.pine`) — Live Chart Surface

- **Entry trigger:** `acceptEvent` path (zone break → retest → close back through zone)
- **Purpose:** human-readable signal overlay, alert broadcast, live entry cue
- **Output budget:** 51/64 (46 plot + 2 plotshape + 3 alertcondition, 13 headroom)
- **Alerts:** 3 `alertcondition()` calls (ENTRY LONG, ENTRY SHORT, PIVOT BREAK)

## Strategy (`v7-warbird-strategy.pine`) — AG Training Data Generator

- **Entry trigger:** `acceptEvent` path — identical to institutional (see closure note below)
- **Purpose:** emit every structurally valid 15m candidate; AG labels the outcome
- **Output budget:** 48/64 (46 plot + 2 plotshape, 16 headroom); uses `alert()` not `alertcondition()`
- **Exit:** SL or TP5 (2.618) only — no scaled exits; AG reads `highestTargetHit` for outcome label
- **Commission floor:** $1.00/side; `use_bar_magnifier=true`; `slippage=1` — pinned in `strategy()` declaration

## Shared Contract (must stay in sync)

- All `ml_*` hidden export field names must match between both files
- `stopFamilyCode`, `eventPivotInteractionCode`, `setupArchetypeCode` patterns identical
- All coupled input defaults must match (strategy is source of truth)
- Verified by `scripts/guards/check-indicator-strategy-parity.sh`

## Intentionally NOT Enforced by Guard

- Exit mechanics (alert-based lifecycle vs. SL/TP5 only)
- `alertcondition` presence (institutional has 3, strategy has 0)
- Strategy-only `strategy()` declaration with Bar Magnifier / commission / slippage pins

## Closure Note: candidateSetup Divergence (resolved 2026-04-13)

A prior entry in this doc claimed the strategy used a `candidateSetup` path (`priceAtFibLevel` — any close within 15% ATR of 6 fib levels) while the indicator used `acceptEvent`. This was stale: the live strategy already followed the same `acceptEvent` → `TRADE_SETUP` → `TRADE_ACTIVE` path as the indicator. The `candidateSetup` variable is still computed for diagnostic/export purposes but does not drive entries. The divergence row was removed and the parity guard was updated to enforce this shared path.

## Rationale

The institutional file is optimized for human operator use: it shows high-confidence accept signals on the chart. The strategy file is optimized for AG training coverage: it emits every structurally valid candidate so AutoGluon can learn which setups produce which outcomes. Both use the same entry trigger semantics (`acceptEvent`). AG decides quality from features, not Pine gates.
