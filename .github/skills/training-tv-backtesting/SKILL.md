---
name: training-tv-backtesting
description: TradingView strategy tester workflow for validating Pine Script strategies and indicator outputs against the trained model's expectations. Uses Deep Backtesting + Bar Magnifier + walk-forward with embargo + realistic friction floors. Required before promoting any strategy change.
---

# Training — TradingView Backtesting

Warbird uses TradingView Desktop for visual + strategy-tester validation of Pine Script outputs. This is NOT the primary training loop — that's AutoGluon on the local warehouse — but it's a necessary gate before promoting indicator or strategy changes.

## When to use

- Validating `v7-warbird-strategy.pine` after any indicator change
- Comparing a new stop/entry policy against the baseline
- Spot-checking specific setups flagged by Monte Carlo (e.g., "show me all FIB_NEG_0382 longs in ETH_POST_RTH that MC said are -$350/trade")
- Before deploying a new Pine version to the live indicator

## TradingView MCP available

There are 78 tools under the `tradingview` MCP namespace. The most relevant for backtesting:

| Tool | Purpose |
|------|---------|
| `tv_launch` | Start TV Desktop with CDP remote debugging |
| `tv_health_check` | Verify CDP connection |
| `chart_set_symbol`, `chart_set_timeframe` | Switch instrument / resolution |
| `pine_open`, `pine_set_source`, `pine_smart_compile` | Load / edit / compile strategy |
| `data_get_strategy_results` | Pull strategy tester summary (net P&L, PF, WR, max DD, etc.) |
| `data_get_trades` | Per-trade list from strategy tester |
| `data_get_equity` | Equity curve points |
| `capture_screenshot` | Regions: full, chart, strategy_tester |
| `batch_run` | Run an action across multiple symbols / timeframes (sweep) |
| `replay_*` | Bar replay mode for forensic review of specific dates |

## Canonical backtest workflow

```
1. tv_launch (if not already running)
2. chart_set_symbol MES1!  (or NYMEX:MES1! for specific contract)
3. chart_set_timeframe 15
4. Load strategy:
   pine_open "v7-warbird-strategy"
   pine_smart_compile
5. Configure strategy properties (via UI or ui_* tools):
   - Order size: 1 contract
   - Commission: 1 tick per trade (NinjaTrader Basic)
   - Slippage: 0 (per user directive)
   - Use Bar Magnifier: ON
   - Deep Backtesting: ON
   - Backtest range: match trainer's test window (e.g. 2025-04-29 to 2026-04-13)
6. Wait for strategy tester to finish (usually 1-5 min for 1 year 15m)
7. data_get_strategy_results → summary
8. data_get_trades → per-trade list
9. data_get_equity → equity curve
10. capture_screenshot region=strategy_tester → archive
```

## Required settings (non-negotiable)

- **Order size:** 1 contract fixed
- **Commission:** 1 tick per trade flat (no round-trip doubling — user directive)
- **Slippage:** 0 by default (can override if user explicitly requests)
- **Use Bar Magnifier:** ON always (for 15m strategies, tests 1m granularity intra-bar)
- **Pyramiding:** 0 unless explicitly overridden
- **Process orders on close:** ON (matches training label-generation convention)
- **Recalculate after order filled:** OFF
- **Deep Backtesting:** ON

Per CLAUDE.md: `use_bar_magnifier=true` and `slippage=1` (tick) are **pinned in the `strategy()` declaration** of `indicators/v7-warbird-strategy.pine`. Never change those pins.

## Commission floor check

CLAUDE.md says "$1.00/side minimum for MES backtesting." The user's explicit directive for this project is **1 tick flat per trade** (NinjaTrader Basic free = $1.25 total, not per-side). Stick to the user directive. If documentation drifts, user's word wins.

## Walk-forward embargo in TV

TV's strategy tester doesn't natively support walk-forward. Two options:

1. **Manual embargo:** set backtest start/end to match a specific training fold's test window. Record results. Advance to next fold's test window. Aggregate manually.
2. **`batch_run` across timeframes or symbols:** for sensitivity analysis across MES / ES / NQ or across resolutions.

There is no full walk-forward harness in TV — for that, use the AutoGluon pipeline + `training-monte-carlo`. TV backtesting validates the Pine output matches the AG labels on specific periods.

## Verifying Pine output vs AG labels

If the trainer's `ag_training` has N interactions in a date window, TV's strategy should fire ~N trades on the same window (allowing for entry-trigger discrepancies). Discrepancies > 10% indicate the Pine indicator and the Python pipeline disagree on setup detection — investigate before trusting either.

Useful psql check:
```sql
SELECT count(*) FROM ag_fib_interactions
 WHERE ts >= '2025-04-29' AND ts < '2026-04-14'
   AND direction IN (-1, 1);
```
vs TV's `Total Trades` in the strategy tester summary for the same range.

## Forensic replay of specific trades

```
1. replay_start date="2026-01-15"
2. replay_step  (advance 1 bar at a time through the setup)
3. data_get_pine_lines / data_get_pine_labels → read indicator state at that bar
4. Note price, fib level, micro-exec state
5. Cross-reference with ag_training row at the same ts:
   SELECT * FROM ag_training WHERE ts = '2026-01-15 14:45:00+00' AND stop_family_id = 'ATR_1_0';
```

## Pine verification gates (before committing strategy)

From CLAUDE.md:
```bash
# 1. TV pine-facade compile (authoritative)
curl -s -X POST "https://pine-facade.tradingview.com/..." ...

# 2. Static analysis
./scripts/guards/pine-lint.sh

# 3. Contamination check
./scripts/guards/check-contamination.sh

# 4. Strategy parity with indicator
./scripts/guards/check-indicator-strategy-parity.sh

# 5. TypeScript build
npm run build
```

All five must pass before any `git commit` of a `.pine` file.

## Known traps

1. **TV Deep Backtesting on 15m requires Premium or higher plan.** Free / Essential plans cap 15m to 6-12 months. Kirk uses TradingView Ultimate ($239/mo) — full history available.
2. **Strategy tester's "Intrabar order fills" assumption.** With bar magnifier ON, TV simulates 1m fills inside the 15m bar. Without, it assumes fills at bar-close only — unrealistic for SL/TP that should fire intrabar. Bar magnifier is mandatory.
3. **MES1! roll convention.** TradingView rolls MES1! 8 calendar days before 3rd Friday. AG training uses Databento `.c.0` continuous front-month. These can diverge by a few days per quarter. If backtesting a specific day near contract roll, verify the contract matches.
4. **Strategy tester resets indicator state on each backtest.** Any stateful indicator logic (e.g., session counters, consecutive-loss blocks) should be tested over a long range to ensure state is stable.

## Related skills

- `training-indicator-optimization` — sweeping indicator PARAMETERS (not strategy-tester runs)
- `trading-indicators:pine:verify` — Pine verification pipeline
- `training-monte-carlo` — analytical equivalent of backtesting on AG predictions
- `supabase-ml-ops` — broader Pine / Fibonacci / indicator reference
