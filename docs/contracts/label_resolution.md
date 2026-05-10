# Label Resolution Contract

**Date:** 2026-04-26
**Status:** Active

## Purpose

Defines labels for indicator-only modeling.

## Label Source

Labels must resolve from the manifest-backed source rows admitted by the active
contract.

Allowed label sources:

- Strategy Tester closed-trade profit/loss
- Strategy Tester entry/exit fields
- Pine exported state fields such as `ml_last_exit_outcome`
- Databento-backed ES 5m/15m market-data training rows when the manifest declares
  Databento as the source/capture kind
- deterministic labels computed from the same approved source data

## Common Labels

- `net_profit`
- `is_win`
- `hit_tp1`
- `stopped`
- `exit_outcome`
- `bars_in_trade`
- `mae`
- `mfe`
- `year`
- `walk_forward_split`

Exact labels are run-specific and must be declared in the export manifest.

## Rules

- No label may use undeclared external data.
- No label may use fields unavailable in the manifest-backed source rows.
- Same-bar TP/SL conflicts follow TradingView Strategy Tester behavior when
  Strategy Tester is the source.
- If a label cannot be reconstructed from the source data, mark it missing.
