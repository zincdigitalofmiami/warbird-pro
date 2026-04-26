# Label Resolution Contract

**Date:** 2026-04-26
**Status:** Active

## Purpose

Defines labels for indicator-only modeling.

## Label Source

Labels must resolve from Pine/TradingView output only.

Allowed label sources:

- Strategy Tester closed-trade profit/loss
- Strategy Tester entry/exit fields
- Pine exported state fields such as `ml_last_exit_outcome`
- deterministic labels computed from the same export

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

- No label may use external data.
- No label may use fields unavailable in the Pine/TradingView export.
- Same-bar TP/SL conflicts follow TradingView Strategy Tester behavior when
  Strategy Tester is the source.
- If a label cannot be reconstructed from the export, mark it missing.
