# v8-prescreen Backtest Results (2026-04-17 rebuild)

Tracks per-layer PF lift during the state-machine rebuild. See `2026-04-17-v8-prescreen-state-machine-design.md` §7 for the run taxonomy and `2026-04-17-v8-prescreen-state-machine-plan.md` for the task sequence producing these rows.

All runs on CME_MINI:MES1! 15m, **Strategy Tester Deep Backtesting range Jan 1 2020 -> Apr 17 2026 (~6.3 years)**, 1 contract fixed, $1/side commission, slippage 1 tick, Bar Magnifier enabled.

**How the range is set:** Strategy Tester panel's Deep Backtesting date picker in the report area. NOT via chart scroll or `chart_set_visible_range` — those only move the viewport. Kirk set the dates manually during R0.

## Diagnostics

- **Baseline asymmetry (R0, full 6.3y):** Long −$2,741.50 (PF 0.981, WR 35.51%) / Short −$22,586.25 (PF 0.850, WR 31.17%). Shorts are structurally broken on this instrument — **89% of the total loss is from the short side.** Independently confirms Powerdrill's 4H PF 2.243 vs 0.731 asymmetry against real historical data. L5 asymmetric thresholds and an Approach C (long-only) fallback are both justified.
- **Trade geometry is OK, entry quality is the problem:** avg winner $102.22 vs avg loser $55.93 (win/loss ratio 1.828). Avg winner lives 32 bars, avg loser 12 bars — winners ride, losers cut. The problem is NOT stops or TPs; it's that 66.66% of trades lose. Filters that raise WR = primary lever.
- **Strategy underperformed buy-and-hold by $833,077.75** over the 6.3-year window. Raw ST on MES 15m is actively destructive.
- **DOM selector:** use `.bottom-widgetbar-content.backtesting` (or `.backtestingReport-qyUx4U7K`) for strategy tester scrapes. The plan template's `[data-name="backtesting-content-wrapper"]` does not match.
- **MCP `data_get_strategy_results` is broken** (returns `metric_count: 0, source: "internal_api"`). All R0 -> R5 captures must use the DOM scrape path.

## Runs

| Run | Gates | Trades | PF | WR | Net P&L | Max DD | Commit |
|-----|-------|--------|----|----|---------|--------|--------|
| R0  | none (raw SATS flip = every trade), 6.3y | 7924 | 0.914 | 33.34% | -$25,327.75 | $29,468.50 | 4a96e92 |

## Per-direction baseline (R0 breakdown, for L5 calibration)

| Side | Trades | PF | WR | Net P&L | Avg P&L | Gross Profit | Gross Loss |
|------|--------|----|----|---------|---------|--------------|------------|
| Long  | 3,962 | 0.981 | 35.51% | -$2,741.50  | -$0.69  | $141,707.25 | $144,448.75 |
| Short | 3,962 | 0.850 | 31.17% | -$22,586.25 | -$5.70  | $128,363.75 | $150,950.00 |
