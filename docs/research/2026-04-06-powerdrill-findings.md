# Warbird PowerDrill Draft Findings Compilation

**Date:** 2026-04-06  
**Purpose:** Consolidate the full `docs/backtest-reports/` research pack into one decision-grade document.  
**Sources Reviewed:** 57 artifacts total - 1 raw backtest markdown, 16 PDFs, and 40 PNGs.  
**Status:** Draft source synthesis. This document compiles source-origin proposals, metrics, and recurring patterns from the PowerDrill materials.

---

## 1. Executive Synthesis

The raw strategy report presents the current WB7 `15m` surface as materially weaker than the `1H` and `4H` surfaces.

- `15m` loses: `-$4,227.51`, `PF 0.903`, `374` trades.
- `1H` is roughly flat: `-$185.57`, `PF 0.995`, `255` trades.
- `4H` is the only profitable test: `+$3,607.85` closed net, `PF 1.192`, `97` trades.
- Longs materially outperform shorts, especially on `4H`.
- Multiple artifacts describe the same core issue: **average losses are about 2x average wins**, and bad trades are not cut fast enough.

The PowerDrill pack largely argues for **filtering and restructuring the existing entry stream** while keeping the fib engine as the underlying structure source. Six recurring themes showed up most often:

1. Pine as the structure generator
2. `PASS / WAIT / TAKE_TRADE` replacing binary entry behavior
3. bar-close confirmation over first-touch fib entry
4. asymmetric long/short treatment, with materially stricter short logic
5. simplified live regime gating instead of more indicator clutter
6. offline AutoGluon ranking/filtering candidates and managing TP1/TP2/runner policy through a compact Pine-safe packet

Across the entire pack, the strongest repeated conclusions are:

- the current `15m` strategy loses mostly because it admits too many mediocre trades
- the short side is structurally worse than the long side
- first-touch fib entries are too permissive
- fixed `-0.236` stop geometry is likely too blunt
- a small HTF regime stack beats a big confluence zoo
- ML is generally framed as refining existing entries rather than inventing them from scratch

---

## 2. Source Coverage And Method

This synthesis reviewed every artifact in:

- `docs/backtest-reports/2026-04-06-wb7-strat-backtest.md`
- `docs/backtest-reports/PowerDrill Research/`

Method:

- the raw markdown backtest was used as the baseline truth surface for reported performance
- all PDFs and PNGs were reviewed through parallel subagents and collapsed into one evidence set
- repeated themes were treated as stronger evidence than one-off screenshots
- screenshots that were operational noise were still reviewed, but not allowed to override stronger sources

Evidence quality tiers used in this document:

- **High confidence:** repeated across multiple artifacts and aligned with the raw backtest diagnosis
- **Medium confidence:** visible in multiple screenshot exports but not anchored to one explicit final test
- **Low confidence:** visible only once, partially OCR-limited, or clearly still exploratory

---

## 3. Verified Baseline From The Raw Backtest

Source: `docs/backtest-reports/2026-04-06-wb7-strat-backtest.md`

### 3.1 Timeframe results

| Timeframe | Net P&L | Profit Factor | Win Rate | Trades | Max DD | Readout |
|---|---:|---:|---:|---:|---:|---|
| `15m` | `-$4,227.51` | `0.903` | `65.51%` | `374` | `9.54%` | weakest result |
| `1H` | `-$185.57` | `0.995` | `67.45%` | `255` | `12.60%` | flat / noisy |
| `4H` | `+$3,607.85` | `1.192` | `71.13%` | `97` | `8.76%` | only profitable test |

### 3.2 Structural diagnosis from the raw report

- `4H` longs are the standout: `PF 2.243`, `78.85%` win rate.
- Shorts bleed everywhere: `PF 0.731` on `4H`, `0.913` on `1H`, `0.934` on `15m`.
- Average win/loss ratio is only about `0.48` across all timeframes.
- `15m` losers last too long: average losing trade is `98` bars.
- The report itself identifies the stop structure as the number one problem.

This matters because every later PowerDrill recommendation is trying to fix exactly these pathologies:

- too many low-quality `15m` trades
- weak short-side behavior
- oversized or late invalidation
- insufficient separation between mediocre and high-quality fib interactions

---

## 4. Cross-Source Consensus

### 4.1 What the full pack agrees on

| Topic | Consensus finding | Confidence |
|---|---|---|
| Entry architecture | `PASS / WAIT / TAKE_TRADE` tiers recur throughout the pack | High |
| Entry timing | Bar-close confirmation is emphasized over first-touch-only entry | High |
| Side handling | Longs and shorts are frequently presented with asymmetric rules | High |
| Volume | Volume confirmation appears repeatedly in entry proposals | High |
| Regime | A **small HTF regime stack** appears more often than a large live confluence basket | High |
| Execution | **RTH bar-close execution** appears more often than delayed or premarket entry ideas | High |
| Stops | Fixed `-0.236` invalidation is frequently questioned, with ATR-aware alternatives recurring | High |
| Fib calibration | Entry-zone selection is often tied to volatility / trend quality | Medium |
| ML role | ML is generally framed as filtering existing candidates and managing policy, rather than replacing Pine signal generation | High |
| Packet design | A compact, normalized, versioned Pine-safe packet recurs throughout the ML-related artifacts | High |

### 4.2 Lower-emphasis directions in the pack

- large live-filter expansion appears less emphasized than simplification
- fully symmetric long/short handling appears less emphasized than asymmetric handling
- using the `4H` result as a direct proxy for `15m` quality appears inconsistent with the pack
- wick-touch-only execution appears lower emphasis than bar-close confirmation
- a hidden live server-side decision engine appears outside the dominant direction

---

## 5. The Proposed System Shape

The synthesized design is a layered system, not a single score or one-off rule.

### 5.1 Layer 1 - Pine structure generator

Pine is generally framed as owning:

- swing-anchor detection
- fib grid and entry zone geometry
- exhaustion / sweep / structure visuals
- on-chart long and short candidate generation
- bar-close semantics only

### 5.2 Layer 2 - Policy state machine

The recurring proposal is:

- `PASS` = expectancy is poor enough to block the setup entirely
- `WAIT` = structure is interesting, but one more layer of confirmation is required
- `TAKE_TRADE` = aligned structure, regime, and confirmation justify execution
- `HOLD_RUNNER` = separate post-TP1 management state in the ML/packet layer

The clearest visible research example gives approximate ordering like this:

| State | Approx. win profile | Intended meaning |
|---|---:|---|
| `PASS` | `~21.7%` | negative expectancy cluster |
| `WAIT` | `~55.5%` | partial alignment, conditional only |
| `TAKE_TRADE` | `~79.2%` | high-conviction cluster |

Those numbers appear in the research outputs as draft state bands, not as final locked thresholds.

### 5.3 Layer 3 - Trade management

The pack repeatedly separates:

- entry qualification
- stop logic
- TP1 capture
- TP2 / runner retention

This is important because the source pack explicitly treats the current one-size-fits-all stop structure as a root problem.

### 5.4 Layer 4 - Offline selector / packet system

The ML design repeated across multiple artifacts is:

- **TP1 head** on the full candidate set
- **TP2 head** on the TP1-hit subset only
- **runner-strength head** for post-TP1 continuation quality

The strongest repeated supporting metrics were:

- about `728` reviewed entry trades across three datasets
- about `488` TP1-positive trades
- about `112` TP2-positive trades inside the TP1 subset
- strong importance for excursion-style features over nominal size/price fields

The repeated implementation rule is to emit a **compact, normalized, versioned packet** that Pine can consume safely.

---

## 6. High-Confidence Findings By Topic

### 6.1 Entry logic and confirmation

The pack converges on a stricter entry philosophy:

- no first-touch entries without confirmation
- prefer **bar-close acceptance/rejection logic**
- score fib touches instead of hard-blocking everything up front
- use explicit skip states instead of only directional bias

Repeated entry-quality features:

- close quality inside the fib zone
- candle-body strength
- sweep / rejection behavior
- volume expansion
- higher-timeframe directional alignment
- local impulse quality

The clearest repeated volume rule was:

- **volume > `120%` of the 20-bar average** as a baseline confirmation threshold

Some later short-side proposals were even stricter:

- require volume spike `>150%` of moving average in certain short regimes
- require a meaningful portion of the candle body to finish outside the zone before accepting the break/reject behavior

### 6.2 Long-short asymmetry

This is the strongest directional conclusion in the full pack.

- Longs are structurally more stable.
- Shorts require stricter confirmation and probably different regime gating.
- Some sources suggest short-side behavior is better framed as selective mean-reversion or high-conviction failure conditions, not symmetric continuation logic.

Practical implication:

- do **not** use the same fib retracement, confirmation, and regime rules for both sides

### 6.3 Fib calibration and anchor behavior

Two similar but not identical calibration ideas repeat:

#### Fixed-style baseline seen in named PDF exports

- ZigZag depth around `9-10`
- deviation around `4-5%`
- backstep `3`
- pivot confirmation around `3` bars

#### ATR-adaptive variant seen in later screenshot research

- ATR-adaptive deviation roughly `2.5x-3.5x`
- working preference near `2.8x-3.2x`
- depth roughly `8-12` bars
- reject sweep-like false pivots that break the swing and then close back inside structure

The shared directional conclusion is stronger than the exact numbers:

- anchors are repeatedly described as better when they are **less noisy** than ultra-responsive settings
- confirmation matters
- anchor sensitivity is often framed as adapting to regime rather than staying rigid

### 6.4 Volatility-aware fib zones

The recurring fib-zone proposal is:

- strong / high-volatility continuation: favor `38.2%`
- normal conditions: favor `50%-61.8%`
- low-volatility / range: require more confirmation and be selective

This connects directly to the repeated critique that one fixed retracement rule is not handling all MES regimes well.

### 6.5 Regime and intermarket filters

The pack repeatedly argues for **simplification** in the live stack.

The clearest regime table found in the screenshot set was:

| Filter stack | Trade count | Win rate | Readout |
|---|---:|---:|---|
| none | `100%` | `52%` | too noisy |
| `1H trend` | `74%` | `58%` | meaningful improvement |
| `1H trend + VIX < 20` | `55%` | `61%` | strongest simple primary gate |
| `1H trend + VIX < 20 + NQ corr > 0.85` | `40%` | `64%` | best quality, but may over-filter |

The best synthesis of all regime artifacts is:

- use a **small live filter stack**
- keep the broader `NQ / RTY / CL / HG / 6E / 6J` basket for research, packet generation, and higher-level regime context
- do **not** let the live entry stack become a large confluence machine

Most repeated live candidates:

- `1H` trend alignment
- `VIX < 20` as a clean primary risk filter
- `NQ` confirmation or correlation as an optional higher-quality gate in choppy conditions
- `RVOL`, `ATR`, and session state as compact execution-quality filters

### 6.6 Session and execution timing

The pack strongly prefers **realistic bar-close execution**.

Most readable execution table:

| Execution method | Avg slippage | Fill certainty | Interpretation |
|---|---:|---:|---|
| market at bar close (`t+0`) | `0.40 pt` | `92%` | most-favored baseline in the pack |
| wait `2s` | `0.32 pt` | `87%` | slightly better price, more dropouts |
| wait `5s` | `0.25 pt` | `78%` | worse certainty |
| passive limit (`+0.5 pt`) | `0.10 pt` | `68%` | too much non-fill risk |

The recurring session guidance was:

- prefer RTH execution
- avoid premarket triggers
- lunch is the choppiest / weakest-quality period
- open and close can be tradable, but spreads widen

### 6.7 Stop logic and invalidation

The source pack repeatedly calls the current stop geometry into question.

Repeated diagnosis:

- current fixed `-0.236` style invalidation leads to oversized losses relative to average wins

Repeated alternatives:

- ATR-based stop family
- fib plus ATR buffer
- structure breach stop
- early adverse-excursion invalidation

The most readable stop comparison from the screenshot set suggested:

| Stop style | Approx. loss/win profile | Typical win rate | Interpretation |
|---|---:|---:|---|
| current fixed fib invalidation | worst | highest pain | main pain point |
| `1.0x ATR` | `1.30` | `52%` | better but still exploratory |
| `1.5x ATR` | `1.10` | `48%` | favored by one note for parity |
| `2.0x ATR` | `0.95` | `40%` | probably too loose / low win rate |

This reads as a draft test direction rather than a single settled stop choice.

### 6.8 MAE / adverse excursion gating

Multiple artifacts propose early damage control.

Most explicit state-bucket proposal found:

| MAE bucket | State | Suggested sizing |
|---|---|---:|
| `<8%` | `TAKE_TRADE` | `2.0%` |
| `8-15%` | `WAIT` | `1.0%` |
| `15-20%` | `PASS` | `0.5%` |
| `>20%` | `REJECT` | `0%` |

Separate late-session PDF exports also describe this same idea more generally:

- small early adverse excursion = valid candidate
- middling excursion = conditional / wait state
- large immediate excursion = invalidate quickly

The repeated principle is stronger than the exact percentages:

- a recurring proposal is to treat large early damage as invalidating or sharply downgrading the setup

---

## 7. ML And Packet Findings

### 7.1 The research pack's ML position

The ML layer is consistently framed as:

- offline only
- candidate ranking / gating only
- probability and runner-management support only
- Pine-safe deployment through a compact packet

### 7.2 Feature selection themes

The strongest repeated feature-selection claims were:

- excursion-style features matter more than nominal size and price fields
- `size_value` and `price_usd` look heavily redundant
- MAE, MFE, and MFE/MAE style ratios are consistently informative
- TP2 is presented as a different problem from TP1 and often uses a separate training surface

### 7.3 Packet design rules that repeat

- keep the packet compact
- normalize and cap fields
- use explicit confidence bins
- encode policy actions and thresholds, not raw model complexity
- version the schema so Pine consumption stays deterministic

### 7.4 Strongest practical ML conclusion

The pack is not asking for a smarter hidden entry engine. It is asking for:

- a cleaner Pine candidate stream
- a smaller number of better filters
- an offline selector that ranks those candidates by TP1 / TP2 / runner quality

---

## 8. Conflicts, Ambiguities, And Weak Evidence

These are the main places where the pack is **not** yet internally final.

### 8.1 Broad basket vs minimal live stack

Two ideas coexist:

- a broad `NQ / RTY / CL / HG / 6E / 6J` context basket for research and regime framing
- a much smaller live entry stack centered on `1H trend`, `VIX`, `NQ`, `RVOL`, and `ATR`

The pack leaves open the role of the full six-asset basket in directly gating live `15m` entries.

### 8.2 Fixed ZigZag vs ATR-adaptive ZigZag

The pack contains both calibration families:

- a fixed calibration around `depth 9-10`, `deviation 4-5%`, `backstep 3`
- an adaptive calibration around `depth 8-12`, `2.8x-3.2x ATR`

This is a design choice that still needs real testing.

### 8.3 Stop baseline

The pack repeatedly questions the current stop baseline, but it does not settle on one uncontested replacement.

Competing directions still present:

- compressed fib plus ATR buffer
- `1.0x ATR`
- `1.5x ATR`
- structure breach

### 8.4 Frequency target mismatch

Some screenshots wanted roughly `2-12` trades per day, while the raw strategy report shows only `374` total `15m` trades over the full test period.

That means parts of the research pack are targeting a future architecture, not merely describing the current one.

### 8.5 Operational-noise screenshots

These were reviewed and contributed mainly process context:

- `Screenshot 2026-04-06 at 1.10.26 PM.png`
- `Screenshot 2026-04-06 at 2.23.12 PM.png`
- `Screenshot 2026-04-06 at 3.01.23 PM.png`

They provide process context, not trading-system evidence.

---

## 9. Recommended Next-Test Order

This is the cleanest decision sequence implied by the full pack.

### Phase 1 - Fix the `15m` entry surface before any advanced ML work

- add explicit `PASS / WAIT / TAKE_TRADE`
- ban first-touch execution without bar-close confirmation
- split long and short rules
- add basic volume and close-quality confirmation

### Phase 2 - Simplify the live regime gate

- test `1H trend` only
- test `1H trend + VIX < 20`
- test optional `NQ` confirmation only as an additional quality gate
- keep the broader six-asset basket in research/packet context until proven necessary live

### Phase 3 - Re-test stop families against the raw report's core failure mode

- current fixed fib invalidation
- fib plus ATR buffer
- pure ATR stop
- structure breach
- early adverse-excursion invalidation

### Phase 4 - Re-test fib-zone and anchor calibration

- fixed `9-10 / 4-5% / backstep 3` baseline
- ATR-adaptive `8-12 / 2.8x-3.2x ATR`
- volatility-aware `38.2 / 50-61.8 / selective low-vol` entry zoning

### Phase 5 - Only then lock the selector packet

- TP1 head
- TP2 conditional head
- runner-quality head
- compact policy packet for Pine

---

## 10. What This Master Document Says To Do Right Now

If one sentence had to represent the entire pack, it would be this:

**Stop trying to make raw fib touches smarter by stacking more live filters; instead, make the `15m` candidate stream cleaner, asymmetric, state-based, and risk-aware, then let offline ML rank the surviving candidates.**

That is the dominant conclusion across the raw backtest, the named PDFs, the PowerDrill export PDFs, and the screenshot set.

---

## 11. Implementation Specifications

These specifications were derived from the PowerDrill research and recorded in draft plan `polished-sniffing-hare.md`. They define the exact changes required to `indicators/v7-warbird-strategy.pine` before re-running the 15m backtest.

---

### 11.1 Stop-Lock Bug Fix

**File:** `indicators/v7-warbird-strategy.pine` — lines 1178–1194

**The bug:** `strategy.exit()` passes `slLevel`, `tp1Level`, and `tp2Level` — non-`var` floats that recalculate every bar as the ZigZag shifts anchors. Stops and targets silently drift mid-trade.

**The correct values:** `slPrice`, `tp1Price`, `tp2Price` are locked as `var` floats at entry (lines 888–890) and reset to `na` at exit (lines 922–924). The internal trade state machine already uses them correctly. Only `strategy.exit()` is wrong.

**Fix — three locations in lines 1186–1193:**
- `levelsValid` check (line 1181): change to use `slPrice`/`tp1Price`/`tp2Price`
- Long exits (lines 1186–1187): `stop=slPrice`, `limit=tp1Price` / `limit=tp2Price`
- Short exits (lines 1192–1193): `stop=slPrice`, `limit=tp1Price` / `limit=tp2Price`

**Execution order safety:** The trade state machine (line 877) runs before `strategy.exit()` (line 1184) in the same `barstate.isconfirmed` block. Pine executes top-to-bottom. When `entryLongTrigger` fires, the state machine has already locked `slPrice`/`tp1Price`/`tp2Price` on the same bar. Safe.

**Plot budget impact:** Zero.

---

### 11.2 Four-Factor Trigger Gate

**File:** `indicators/v7-warbird-strategy.pine` — lines 831–833

**PowerDrill specification:** The trigger bar must satisfy ALL four:
1. Fib zone — price at a tracked retracement level (already enforced by `acceptEvent`)
2. Body ≥ 65% — candle body is at least 65% of total bar range (no doji/spinning tops)
3. Volume > 1.5× 20-bar average — volume threshold tightened from current default of 1.2
4. RSI 50-bounce — RSI(14) treats 50 as support (longs) or resistance (shorts), touches the 45–55 band and reverses direction within the last 5 bars

**Body filter** — add at global scope after line 831:
```
bodyPct = abs(close - open) / (high - low) if (high - low) > 0 else 0.0
bodyOK = bodyPct >= 0.65
```

**Volume threshold** — change `rvolMin` input default (line 97) from `1.2` to `1.5`. Reuses existing `rvolOK` variable. Saved TV layouts will retain the old value; reset manually.

**RSI 50-bounce** — add at global scope (after line 831, before entry triggers). Uses `rsi14` already computed at line 169. Key: `ta.barssince()` is a series and **must be at global scope**, never inside an `if` block.
- Lookback: 5 bars (`rsiBounceBack = 5`)
- Band: 45.0–55.0
- `rsiBounceOK = (dir == 1 and rsiBounceUp) or (dir == -1 and rsiBounceDown)`

**Updated entry triggers** (lines 832–833): append `and bodyOK and rsiBounceOK` to both `entryLongTrigger` and `entryShortTrigger`.

**Optional ML export plots** (display.none): `ml_body_pct` and `ml_rsi_bounce`. Budget: 60 → 62 plots (2 headroom remaining of 64). Budget comment at lines 40 and 1174 must be updated.

**Expected impact:** Trade count drops from 374 toward the ~109 the regime filter alone achieved. Win rate improves by rejecting weak candles. Some short bleed addressed by RSI/body gate.

---

### 11.3 Stop Family Input Toggle

**File:** `indicators/v7-warbird-strategy.pine` — lines 868–871

**New inputs** (add to Structure Logic group near line 97):
- `stopFamily` — string: "Fib Extension" (default) or "ATR"
- `atrStopMult` — float: 0.50 default, range 0.1–3.0, step 0.1 (only active when Stop Family = ATR)

**Computation reorder** (lines 868–871): `entryLevel` must move before `slLevel` because the ATR formula references it. New order:
1. `entryLevel = fibBull ? p618 : p382`
2. `slLevelFib = fibPrice(-0.236)`
3. `slLevelAtr = entryLevel ± (atrStopMult × atr14)` (direction-relative)
4. `slLevel = stopFamily == "ATR" ? slLevelAtr : slLevelFib`

`atr14` is already computed at line 170. `slDistPts` and `slDistAtr` at lines 873–875 continue unchanged.

**Strategy.exit() interaction:** After the Task 1 fix, `strategy.exit()` uses locked `slPrice`. The lock at line 888 (`slPrice := slLevel`) captures whichever stop family was active at entry. Both families freeze correctly.

**ATR calibration notes from research:**
- PowerDrill referenced 0.50× ATR as the starting point
- 15m ATR(14) for MES ≈ 3–8 pts → 0.50× = 1.5–4pt stop (may be tight; tune with `atrStopMult`)
- 4H ATR(14) for MES ≈ 15–30 pts → 0.50× = 7.5–15pt stop (reasonable)
- The multiplier input allows per-timeframe calibration without code changes

**A/B testing workflow:** Switch Stop Family in TradingView strategy settings, re-run the strategy tester, compare PF/WR/drawdown directly.

**Plot budget impact:** Zero.

---

### 11.4 Execution Order

Tasks have one dependency chain. Execute in this order:

1. **Task 1** — Fix slLevel → slPrice (required before Task 3, both touch lines 1181–1193)
2. **Task 3** — Add stop family toggle (modifies lines 868–871)
3. **Task 2** — Add 4-factor trigger gate (independent of Tasks 1 and 3, modifies lines 831–833)

One commit per task.

---

### 11.5 Verification Checklist

After all three tasks:

1. `scripts/guards/pine-lint.sh indicators/v7-warbird-strategy.pine` — must PASS
2. `scripts/guards/check-contamination.sh` — must PASS
3. `npm run build` — must PASS
4. `grep "strategy.exit" indicators/v7-warbird-strategy.pine` — confirm zero `slLevel`/`tp1Level`/`tp2Level` in any `strategy.exit()` call
5. `grep "ta.barssince" indicators/v7-warbird-strategy.pine` — confirm at global scope, not inside an `if` block
6. `grep -c "^plot(" indicators/v7-warbird-strategy.pine` — verify plot count is within 64 (plots + alertconditions)
7. Budget comment at lines 40 and 1174 updated to match actual count
8. Backtest MES 4H with Stop Family = "Fib Extension" — compare to pre-fix baseline (expect improvement from stop-lock fix alone)
9. Backtest MES 4H with Stop Family = "ATR", multiplier 0.50 — compare to fib baseline
10. Backtest MES 15m with both stop families — compare trade count, WR, PF to baseline: 374 trades / 65.51% WR / PF 0.903
11. Kirk manually loads into TradingView and verifies compilation + visual output

---

### 11.6 Items Documented But Outside This Scope

Findings from the PowerDrill session that require separate work:

- **Runner hold score** — P(TP2|TP1 hit), regime alignment at TP1, ATR-normalized remaining distance. Requires TP1 partial exit logic rework.
- **Intermarket basket reduction to NQ+VIX+CL** — strategy already uses full 6-symbol weighted regime. Reduction may be a separate A/B experiment, not a removal.
- **All-fib-touches candidate dataset** — build with all filters OFF for AG training baseline. Requires dataset tooling, not Pine changes.
- **MFE/MAE distribution per stop family** — requires resolved outcome rows, not Pine changes. Run after backtest data is captured.
- **Short-side asymmetry** — shorts bleed across all timeframes. Future: direction-specific body/volume thresholds or a short-suppression input flag.
- **Losers sit too long** — 15m avg losing trade = 98 bars (24.5 hours). Possible fix: time-based exit or tighter trailing after a defined bar count.
- **AE% execution policy tiers** — PASS/WAIT/TAKE_TRADE as a formal policy layer with MAE thresholds. Currently implicit.
- **Exhaustion diamond as confidence modifier** — currently visual only in the strategy; not wired to sizing or policy tiers.
- **Commission drag** — $464 on 15m vs $121 on 4H. Trigger gate should reduce this by lowering trade count.

---

## Appendix A - Full Source Manifest

### A.1 Raw backtest markdown

- `docs/backtest-reports/2026-04-06-wb7-strat-backtest.md`

### A.2 Named PDFs and PNGs

- `docs/backtest-reports/PowerDrill Research/CalibrateFibs.pdf`
- `docs/backtest-reports/PowerDrill Research/entries.pdf`
- `docs/backtest-reports/PowerDrill Research/PASS:WAIT:TAKE logic.pdf`
- `docs/backtest-reports/PowerDrill Research/Refine regime filters and confluence requirements.pdf`
- `docs/backtest-reports/PowerDrill Research/fibscreencapture-powerdrill-ai-session-uc-1f13206993956522a8b848649b61e16c-2026-04-06-17_39_28.pdf`
- `docs/backtest-reports/PowerDrill Research/Intermarketscreencapture-powerdrill-ai-session-uc-1f13206993956522a8b848649b61e16c-2026-04-06-17_38_42.pdf`
- `docs/backtest-reports/PowerDrill Research/preview.png`
- `docs/backtest-reports/PowerDrill Research/Equity chart_2026-04-06_14-52-16_e2ced.png`

### A.3 Early PowerDrill export sequence

- `docs/backtest-reports/PowerDrill Research/screencapture-powerdrill-ai-session-uc-1f132006b21c64c28405e4e51ba9050e-2026-04-06-16_47_43.png`
- `docs/backtest-reports/PowerDrill Research/screencapture-powerdrill-ai-session-uc-1f132006b21c64c28405e4e51ba9050e-2026-04-06-16_48_15.png`
- `docs/backtest-reports/PowerDrill Research/screencapture-powerdrill-ai-session-uc-1f132006b21c64c28405e4e51ba9050e-2026-04-06-16_48_34.png`
- `docs/backtest-reports/PowerDrill Research/screencapture-powerdrill-ai-session-uc-1f132006b21c64c28405e4e51ba9050e-2026-04-06-16_48_50.png`
- `docs/backtest-reports/PowerDrill Research/screencapture-powerdrill-ai-session-uc-1f132006b21c64c28405e4e51ba9050e-2026-04-06-16_49_11.png`
- `docs/backtest-reports/PowerDrill Research/screencapture-powerdrill-ai-session-uc-1f132006b21c64c28405e4e51ba9050e-2026-04-06-16_54_56.png`
- `docs/backtest-reports/PowerDrill Research/screencapture-powerdrill-ai-session-uc-1f132006b21c64c28405e4e51ba9050e-2026-04-06-17_00_44.png`
- `docs/backtest-reports/PowerDrill Research/screencapture-powerdrill-ai-session-uc-1f132006b21c64c28405e4e51ba9050e-2026-04-06-17_05_33.png`
- `docs/backtest-reports/PowerDrill Research/screencapture-powerdrill-ai-session-uc-1f132006b21c64c28405e4e51ba9050e-2026-04-06-17_08_10.png`
- `docs/backtest-reports/PowerDrill Research/screencapture-powerdrill-ai-session-uc-1f132006b21c64c28405e4e51ba9050e-2026-04-06-17_15_47.pdf`
- `docs/backtest-reports/PowerDrill Research/screencapture-powerdrill-ai-session-uc-1f132006b21c64c28405e4e51ba9050e-2026-04-06-17_16_12.pdf`
- `docs/backtest-reports/PowerDrill Research/screencapture-powerdrill-ai-session-uc-1f132006b21c64c28405e4e51ba9050e-2026-04-06-17_16_28.pdf`
- `docs/backtest-reports/PowerDrill Research/screencapture-powerdrill-ai-session-uc-1f132006b21c64c28405e4e51ba9050e-2026-04-06-17_16_46.pdf`
- `docs/backtest-reports/PowerDrill Research/screencapture-powerdrill-ai-session-uc-1f132006b21c64c28405e4e51ba9050e-2026-04-06-17_17_04.pdf`

### A.4 Later PowerDrill export sequence

- `docs/backtest-reports/PowerDrill Research/screencapture-powerdrill-ai-session-uc-1f13206993956522a8b848649b61e16c-2026-04-06-17_40_39.pdf`
- `docs/backtest-reports/PowerDrill Research/screencapture-powerdrill-ai-session-uc-1f1320a6eb9a6d029d633e67d411d723-2026-04-06-18_01_12.pdf`
- `docs/backtest-reports/PowerDrill Research/screencapture-powerdrill-ai-session-uc-1f1320a6eb9a6d029d633e67d411d723-2026-04-06-18_08_10.pdf`
- `docs/backtest-reports/PowerDrill Research/screencapture-powerdrill-ai-session-uc-1f1320a6eb9a6d029d633e67d411d723-2026-04-06-18_10_01.pdf`
- `docs/backtest-reports/PowerDrill Research/screencapture-powerdrill-ai-session-uc-1f1320a6eb9a6d029d633e67d411d723-2026-04-06-18_10_18.pdf`

### A.5 Screenshot PNG set

- `docs/backtest-reports/PowerDrill Research/Screenshot 2026-04-06 at 1.10.26 PM.png`
- `docs/backtest-reports/PowerDrill Research/Screenshot 2026-04-06 at 2.23.12 PM.png`
- `docs/backtest-reports/PowerDrill Research/Screenshot 2026-04-06 at 2.29.02 PM.png`
- `docs/backtest-reports/PowerDrill Research/Screenshot 2026-04-06 at 3.01.23 PM.png`
- `docs/backtest-reports/PowerDrill Research/Screenshot 2026-04-06 at 4.36.43 PM.png`
- `docs/backtest-reports/PowerDrill Research/Screenshot 2026-04-06 at 4.45.50 PM.png`
- `docs/backtest-reports/PowerDrill Research/Screenshot 2026-04-06 at 5.20.57 PM.png`
- `docs/backtest-reports/PowerDrill Research/Screenshot 2026-04-06 at 5.21.51 PM.png`
- `docs/backtest-reports/PowerDrill Research/Screenshot 2026-04-06 at 5.22.08 PM.png`
- `docs/backtest-reports/PowerDrill Research/Screenshot 2026-04-06 at 5.22.14 PM.png`
- `docs/backtest-reports/PowerDrill Research/Screenshot 2026-04-06 at 5.26.33 PM.png`
- `docs/backtest-reports/PowerDrill Research/Screenshot 2026-04-06 at 5.26.59 PM.png`
- `docs/backtest-reports/PowerDrill Research/Screenshot 2026-04-06 at 5.27.05 PM.png`
- `docs/backtest-reports/PowerDrill Research/Screenshot 2026-04-06 at 5.47.00 PM.png`
- `docs/backtest-reports/PowerDrill Research/Screenshot 2026-04-06 at 5.47.08 PM.png`
- `docs/backtest-reports/PowerDrill Research/Screenshot 2026-04-06 at 5.47.11 PM.png`
- `docs/backtest-reports/PowerDrill Research/Screenshot 2026-04-06 at 5.47.15 PM.png`
- `docs/backtest-reports/PowerDrill Research/Screenshot 2026-04-06 at 6.07.06 PM.png`
- `docs/backtest-reports/PowerDrill Research/Screenshot 2026-04-06 at 6.07.20 PM.png`
- `docs/backtest-reports/PowerDrill Research/Screenshot 2026-04-06 at 6.07.30 PM.png`
- `docs/backtest-reports/PowerDrill Research/Screenshot 2026-04-06 at 6.07.44 PM.png`
- `docs/backtest-reports/PowerDrill Research/Screenshot 2026-04-06 at 6.07.49 PM.png`
- `docs/backtest-reports/PowerDrill Research/Screenshot 2026-04-06 at 6.08.32 PM.png`
- `docs/backtest-reports/PowerDrill Research/Screenshot 2026-04-06 at 6.08.40 PM.png`
- `docs/backtest-reports/PowerDrill Research/Screenshot 2026-04-06 at 6.09.14 PM.png`
- `docs/backtest-reports/PowerDrill Research/Screenshot 2026-04-06 at 6.09.22 PM.png`
- `docs/backtest-reports/PowerDrill Research/Screenshot 2026-04-06 at 6.09.38 PM.png`
- `docs/backtest-reports/PowerDrill Research/Screenshot 2026-04-06 at 6.09.49 PM.png`
- `docs/backtest-reports/PowerDrill Research/Screenshot 2026-04-06 at 6.12.16 PM.png`
