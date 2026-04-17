# v8-prescreen Backtest Results (2026-04-17 rebuild)

Tracks per-layer PF lift during the state-machine rebuild. See `2026-04-17-v8-prescreen-state-machine-design.md` §7 for the run taxonomy and `2026-04-17-v8-prescreen-state-machine-plan.md` for the task sequence producing these rows.

All runs on CME_MINI:MES1! 15m, 2020-01-01 -> 2024-12-31, 1 contract fixed, $1/side commission, slippage 1 tick, Deep Backtesting + Bar Magnifier enabled.

## Diagnostics

- **R0 capture (2026-04-17):** TradingView chart range at capture time was **Jun 1, 2025 -> Apr 17, 2026** (~10 months), NOT the spec window 2020-01-01 -> 2024-12-31. Per task contract the chart range was NOT modified; Kirk consult required before re-running R0 against the full 5-year window. Numbers below are the live DOM ground-truth for the actually-rendered ~10-month window. The earlier session's draft figures (1706 trades, PF 0.647, -$9,833 P&L, $11,657 DD) appear to have come from a different (longer) range and do not reconcile with the current strategy tester output.
- Deep Backtesting toggle state cannot be confirmed programmatically via TV MCP; verify visually from `screenshots/r0-baseline.png`.

## Runs

| Run | Gates | Trades | PF | WR | Net P&L | Max DD | Commit |
|-----|-------|--------|----|----|---------|--------|--------|
| R0  | none (current, range Jun 1 2025 - Apr 17 2026) | 1103 | 0.985 | 34.63% | -$685.75 | $5,157.50 | 4a96e92 |
