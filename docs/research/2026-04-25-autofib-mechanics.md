# Auto-Fibonacci Mechanics Research — 2026-04-25

**Context:** Kirk locked the canonical Warbird TF to 5m and asked for research on the best autofib mechanics, no-repaint patterns, and tuning approach before we touch the backtest strategy file again.

**Active plan:** `docs/plans/2026-04-24-v7-backtest-strategy-single-ladder-snapshot.md`
**File in scope:** `indicators/v7-warbird-institutional-backtest-strategy.pine`

---

## TL;DR — what changes

1. **Repainting is two different things; we conflate them.** "Mid-bar tentative drawing" and "past-bar value mutation" are distinct. ZigZag-based fib engines have the first kind (the unconfirmed tail) but not the second. The single-ladder snapshot in our plan eliminates the visible mid-trade ladder shift, which is the actual user-visible problem.
2. **`ta.pivothigh` / `ta.pivotlow` do NOT repaint historical values.** They have confirmation lag = `rightbars` bars. A pivot at bar `i` is reported at bar `i + rightbars`. The closed bars never mutate.
3. **The TradingView `ZigZag/7` library** the file already imports IS the mature, library-grade pivot engine. Its `Settings(devThreshold, depth, ...)` map cleanly to Optuna parameters.
4. **The file's parallel `fibHtfSnapshot` (using `ta.highest`/`ta.lowest`)** is a *range-based* leg detector, not a swing/pivot detector — it picks the highest bar in a window regardless of structure. Less lag but less structurally meaningful. Once we go 5m native (no HTF parent override), we stop calling this path entirely; we use `fibZzUpdate` which wraps the ZigZag/7 library.
5. **Backtest discipline already correct in the file:** `use_bar_magnifier=true`, `slippage=1`, `commission=$1.00/side`, `process_orders_on_close=false`. No changes needed.
6. **Optuna tuning surface is healthy.** All knobs (deviation, depth, threshold floor, min fib range, pivot right room, recent leg lookback, entry level, stop ATR mult, max risk ATR, imbalance rows, exit target) are `input.*` calls — Optuna can sweep them via the existing `tune_strategy_params.py` adapter. No tuning impedance.

---

## What We Use Today

The strategy file currently has TWO fib engines selected by the `useFibAnchorTimeframeOverride` ternary:

| Branch | When fired | Engine | Repaint behavior |
|---|---|---|---|
| `fibZzUpdate` | Chart TF == anchor TF (5m native) | `import TradingView/ZigZag/7 as zigzag` library — pivot-based | Mature, confirmed-pivot semantics. Tail line is tentative; confirmed pivots are stable. |
| `fibHtfSnapshot` | HTF parent override on (15m parent on 5m chart) | Custom `ta.highest`/`ta.lowest` over a window | Range-based — picks the bar in the window with the most extreme high/low. Different from a structural swing pivot. |

**Going 5m native means we stop using `fibHtfSnapshot` entirely.** The ZigZag/7 library becomes the sole fib engine — and it's the better one.

---

## Repaint vs No-Repaint — the actual mechanic

Per [earnforex.com on indicator repainting](https://www.earnforex.com/guides/what-is-repainting-indicator-in-forex/) and [TradingView's own docs surfaced via WebSearch](https://www.tradingview.com/scripts/zigzag/), there are two distinct behaviors people call "repainting":

### Type 1 — Current-bar tentative drawing (NORMAL)
"Nearly all technical indicators constantly update the current candle value with each new tick." This is expected. The fix is `barstate.isconfirmed` gating for any decision logic — let the bar close before acting.

### Type 2 — Past-bar value mutation (PROBLEM)
"The indicator's code is looking at the future candles to paint the display for the past bars." This is the real footgun. Past pivots SHIFT as new data arrives. Backtest results in this case do not match live results.

**`ta.pivothigh(left, right)` is a Type 1, not Type 2.** Per [codegenes.net's explanation of pivothigh/pivotlow](https://www.codegenes.net/blog/how-pivothigh-and-pivotlow-function-work-on-tradingview-pinescript/):
- The pivot at bar `i` is reported by Pine at bar `i + right` (after the rightbars window has elapsed).
- Once reported, the value never mutates. The pivot is locked at its actual timestamp.
- The "lag" is structural confirmation, not retroactive change.

**The TradingView `Zig Zag` indicator's tail-line drawing IS Type 1** — the dotted segment from the last confirmed pivot to the current bar is provisional and will redraw as the developing bar resolves. But the *confirmed* pivot points behind it are immutable.

Bottom line: our ZigZag/7-driven fib engine does not have the dangerous Type 2 repaint. The user-visible "two ladders" wreck Kirk showed is a different problem entirely — it's the *new sticky-overlay layer* drifting from the *underlying live ladder* as the engine re-anchors. The snapshot fix in the active plan addresses exactly that.

---

## TradingView ZigZag/7 Library — what's exposed

Per [the TradingView/ZigZag library page](https://www.tradingview.com/script/bzIRuGXC-ZigZag/) and our `import TradingView/ZigZag/7 as zigzag` usage:

| Setting | Maps to | Purpose |
|---|---|---|
| `devThreshold` | `fibDeviation` (input) | Minimum % deviation before direction reverses |
| `depth` | `fibDepth` (input) | Bars required for pivot detection (left/right window) |
| `lineColor` | (visual only) | Line color of confirmed pivot connections |
| `extendLast` | (visual only) | Whether to extend the tail line to current bar |
| `displayReversalPrice` | (visual only) | Print price labels on pivots |
| `allowZigZagOnOneBar` | (not currently used) | Allow a single bar to register both a high and low pivot |

**Optuna mapping:** `fibDeviation` and `fibDepth` are already exposed as `input.float`/`input.int` and tuned via `tune_strategy_params.py`. The Optuna surface already covers the library's main mechanics.

---

## `ta.pivothigh` / `ta.pivotlow` — the v6 primitive

Per [Pine Script v6 reference](https://www.tradingview.com/pine-script-reference/v6/) and [pinewizards.com on ta.pivothigh](https://pinewizards.com/technical-analysis-functions/ta-pivothigh-in-pine-script/):

**Signature:** `ta.pivothigh(leftbars, rightbars)` returns the price of the pivot, or `na`.

**Confirmation rule:** A bar `i` qualifies as a pivot high if `high[i]` exceeds all `high[i-1..i-leftbars]` AND all `high[i+1..i+rightbars]`. The function only reports the pivot at bar `i + rightbars` — when all rightbars have closed.

**Practical implication for our strategy:**
- If we used `ta.pivothigh(2, 2)` directly, there's a 2-bar (10-min on 5m) confirmation lag.
- The ZigZag/7 library wraps a more sophisticated detector that combines a pivot-window with a percentage-deviation threshold — it's stricter, with similar lag characteristics.
- Either approach has the inherent rightbars lag — there's no way to identify a pivot at `i` without seeing some bars after `i`. This is a hard constraint, not a bug.

**Non-repainting strategy entry pattern** (from [codegenes.net](https://www.codegenes.net/blog/how-pivothigh-and-pivotlow-function-work-on-tradingview-pinescript/)):
```pine
swing_high = ta.pivothigh(1, 1)
if not na(swing_high) and barstate.isconfirmed
    // act on confirmed pivot
```

The `barstate.isconfirmed` gate ensures the rightbars window has fully closed before any decision fires.

---

## Backtest Discipline — what the file already gets right

Per [Pine Script Strategies docs](https://www.tradingview.com/pine-script-docs/) and our existing `strategy()` declaration:

✅ `use_bar_magnifier=true` — intra-bar fill simulation; not a pure close-to-close approximation
✅ `slippage=1` — 1 tick floor; matches AGENTS.md "Slippage floor: 1 tick minimum"
✅ `commission_type=cash_per_contract`, `commission_value=1.00` — matches AGENTS.md "Commission floor for MES backtesting: $1.00/side minimum"
✅ `process_orders_on_close=false` — orders fire on next bar's open (default), not artificially on the same bar's close
✅ `fill_orders_on_standard_ohlc=true` — uses standard OHLC for fills, not heikin-ashi or other derived bars
✅ `pyramiding=0` — no stacking
✅ `default_qty_value=1` — single-contract baseline; Optuna can scale via separate input

**No backtest discipline changes needed in this fix.** The file's `strategy()` declaration is already conservative.

---

## Tuning Mechanics — Optuna-friendly

The Optuna adapter (`tune_strategy_params.py` + `strategy_tuning_space.json` + `tv_auto_tune.py`) drives this file via CDP. The currently exposed knobs:

| Input | Type | Optuna range (current) | Notes |
|---|---|---|---|
| `fibDeviation` (manual mode) | float | 0.5–20.0, step 0.5 | ZZ/7 `devThreshold` |
| `fibDepth` (manual mode) | int | 2–50 | ZZ/7 `depth` |
| `fibThresholdFloorPct` | float | 0.0–5.0, step 0.05 | ATR-scaled floor |
| `minFibRangeAtr` | float | 0.5–10.0, step 0.1 | Reject too-tight ladders |
| `optEntryLevelInput` | string | "0.500" / "0.618" / "0.786" | Which fib level fires entry |
| `optStopAtrMult` | float | (ranges in JSON) | Stop ATR multiplier |
| `optMaxRiskAtr` | float | (ranges in JSON) | Max risk in ATR |
| `optImbalanceRows` | int | (ranges in JSON) | Footprint imbalance gate |
| `backtestExitTargetInput` | string | "TP1"–"TP5" | Single-ticket exit target |
| `fibPivotRightRoomBars` | int | 1–20 | (only used by `fibHtfSnapshot` — dead code once we go 5m native) |
| `fibRecentLegLookbackBars` | int | 5–120 | (same — dead once 5m native) |

**Recommendation:** Once `useParentFibTimeframe` defaults to false, drop `fibPivotRightRoomBars` and `fibRecentLegLookbackBars` from the Optuna search space — they're tuning a code path the strategy no longer uses. This is a separate Optuna config change, not a Pine change.

**`autoTuneZZ` interaction:** The file has an `autoTuneZZ = input.bool(true)` that overrides the manual `fibDeviation`/`fibDepth` based on chart TF. For a 5m chart, the auto-tune branch picks `Deviation=3, Depth=15`. For Optuna runs, set `autoTuneZZ=false` so the manual values can sweep.

---

## Recommendations for the v7 Backtest Strategy (in priority order)

### 1. Land the snapshot fix from the active plan (already approved by Kirk)
The "two ladders" wreck is the visible Type-1-meets-overlay-drift problem. The snapshot freezes the ladder during a trade — one ladder, no overlap. This research confirms the architectural choice; no changes to the plan needed.

### 2. Flip input defaults to 5m native (Open Question A)
- `useParentFibTimeframe = input.bool(false, ...)` — disables HTF parent path
- `fibAnchorTimeframe = input.timeframe("5", ...)` — defaults to 5m if anyone re-enables the toggle

This is two one-line edits. Optuna impact: ZERO (Optuna sets values explicitly). User impact on chart-add: comes up in the right configuration without manual tweaking. **Recommend doing this in the same plan as the snapshot fix; the scope creep is minimal and the change is structurally aligned with Kirk's "we are fully on 5m" direction.**

### 3. Long-term: deprecate `fibHtfSnapshot`
Since the path won't be used, deleting it removes ~30 lines of `ta.highest`/`ta.lowest` machinery and simplifies the engine. **Out of scope for this plan** — propose as a follow-up after the snapshot fix is verified on chart.

### 4. No repainting fix needed
The file already uses the ZigZag/7 library, which has the safer pivot-confirmation semantics. The `barstate.isconfirmed` discipline is mostly already in place (entries fire on bar close via the state machine, not mid-bar). No change needed.

### 5. No backtest-discipline changes needed
`use_bar_magnifier`, slippage, commission floor, fill model all match AGENTS.md hard rules.

### 6. Optuna config tweak (separate task, separate file)
After the 5m flip lands, prune `fibPivotRightRoomBars` and `fibRecentLegLookbackBars` from `strategy_tuning_space.json` — they tune a dead code path. Single-line JSON edits in the Optuna config.

---

## Decision matrix for the active plan

| Question | Research answer |
|---|---|
| Should the snapshot architecture change based on research? | **No.** Snapshot freeze on TRADE_ACTIVE edge is correct. |
| Is there a no-repaint pattern we're missing? | **No.** ZigZag/7 + `barstate.isconfirmed` is the standard pattern. |
| Should we change the fib engine algorithm? | **No.** Library-grade ZZ is the right choice. The dead `fibHtfSnapshot` path can be removed in a follow-up plan. |
| Should the input defaults flip to 5m? | **Yes** — recommend including in this plan (Question A above). |
| Are backtest-friction settings adequate? | **Yes** — already at AGENTS.md floor. |
| Does the Optuna surface need expansion? | **Not for this fix.** Long-term: drop two dead inputs from the search space. |

---

## Sources

- [Auto-Fibonacci Tool in Pine Script — The Art of Trading](https://courses.theartoftrading.com/pages/auto-fibonacci-tool-in-pine-script)
- [Pine Script Fibonacci Retracements — Pineify Blog](https://pineify.app/resources/blog/pine-script-fibonacci-guide)
- [How pivothigh and pivotlow work — codegenes.net](https://www.codegenes.net/blog/how-pivothigh-and-pivotlow-function-work-on-tradingview-pinescript/)
- [What Is a Repainting Indicator in Forex — EarnForex](https://www.earnforex.com/guides/what-is-repainting-indicator-in-forex/)
- [TradingView ZigZag Library v7](https://www.tradingview.com/script/bzIRuGXC-ZigZag/)
- [Pine Script v6 Language Reference Manual](https://www.tradingview.com/pine-script-reference/v6/)
- [TradingView Pine Script Techniques FAQ](https://www.tradingview.com/pine-script-docs/faq/techniques/)
- [TradingView Pine Script Strategies docs](https://www.tradingview.com/pine-script-docs/concepts/strategies/)
- [Fibonacci Pro — toz-panzmoravy GitHub](https://github.com/toz-panzmoravy/Fibonacci_Pro)
- [Auto Fibonacci Levels — ChartWhizzperer](https://www.tradingview.com/script/xdyYLLCD-Auto-Fibonacci-Levels-ChartWhizzperer/)
- [Pivot detection patterns — Market Scripters](https://marketscripters.com/how-to-work-with-pivots-in-pine-script/)
- [ta.pivothigh in Pine Script — Pine Wizards](https://pinewizards.com/technical-analysis-functions/ta-pivothigh-in-pine-script/)
