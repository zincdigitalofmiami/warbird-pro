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

### Phase 0.2 — Invisible-table diagnosis (2026-04-17)

**Finding: not invisible. False alarm.** The dashboard table IS rendering correctly on-chart. Phase 1.2 fix is not needed.

- **Dashboard toggle = `showDashInput`** at `indicators/v8-warbird-prescreen.pine:154` (`input.bool(true, "Show Dashboard", group = GRP_DASH)`). Default `true`.
- **TV input-id mapping** (counting `input.*()` calls from top of file, skipping `__chart_bgcolor`/`__profile`): `in_65=showDashInput`, `in_66=showTqiBreakdownInput`, `in_67=showBreakdownInput`, `in_68=showPerfInput`, `in_69=dashPosStr`.
- **Live values on `jrwTt0`** via `mcp__tradingview__data_get_indicator`: `in_65=true`, `in_66=true`, `in_67=true`, `in_68=true`, `in_69="Bottom Right"`. All dashboard toggles are ON.
- **Render gate at line 931** (`if showDashInput and barstate.islast`) is satisfied.
- **`mcp__tradingview__data_get_pine_tables` (no filter)** returns 2 tables from the legacy v8 prescreen study — a 34-row dashboard (Preset | Crypto 24/7, TQI | .28, Signal | —, Regime | Mixed / High Vol, Performance | 85/100, Win Rate | 80.0%, Avg R | +1.40R, Streak W/L | W:5/11 L:0/3, ... through ST Break | 16.0) plus the 1-row watermark table. The dashboard `table.new()` at line 932 and all `table.cell()` calls at lines 934-1046 are firing.
- **Visual confirmation**: screenshot `/Users/zincdigital/tradingview-mcp/screenshots/v8-prescreen-dashboard-check.png` shows the table rendered in the bottom-right corner of the chart with all sections (main stats, TQI Components, Performance, last-signal breakdown) visible.
- **Why earlier filter returned 0**: the initial filtered `data_get_pine_tables` call used an outdated study-name token. The live study display name did not match that token, while `study_filter` omitted or aligned to the displayed title worked correctly.
- **Action for Phase 1.2**: none required. The "invisible table" premise was incorrect. If Kirk still perceives a rendering issue, it is a position/theme/overlap problem with other on-chart studies (e.g. `Nexus Fusion Engine ML` dashboard may overlap), not a code-path failure. Phase 1.2 can either be skipped or repurposed to relocate the dashboard (`dashPosStr`) if a conflict is observed live.

## Runs

| Run | Gates | Trades | PF | WR | Net P&L | Max DD | Commit |
|-----|-------|--------|----|----|---------|--------|--------|
| R0  | none (raw baseline flip = every trade), 6.3y | 7924 | 0.914 | 33.34% | -$25,327.75 | $29,468.50 | 4a96e92 |

## Per-direction baseline (R0 breakdown, for L5 calibration)

| Side | Trades | PF | WR | Net P&L | Avg P&L | Gross Profit | Gross Loss |
|------|--------|----|----|---------|---------|--------------|------------|
| Long  | 3,962 | 0.981 | 35.51% | -$2,741.50  | -$0.69  | $141,707.25 | $144,448.75 |
| Short | 3,962 | 0.850 | 31.17% | -$22,586.25 | -$5.70  | $128,363.75 | $150,950.00 |
