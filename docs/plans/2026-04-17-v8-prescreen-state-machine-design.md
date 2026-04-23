# v8-warbird-prescreen — State-Machine Redesign

**Date:** 2026-04-17
**Status:** Design approved by Kirk. Awaiting implementation plan (writing-plans).
**Authors:** Kirk + Claude (brainstorming skill)
**Supersedes:** The "enter on every baseline flip" wrapper committed at [4a96e92](https://github.com/zincdigitalofmiami/warbird-pro/commit/4a96e92).

---

## 1. Problem statement

Current `indicators/v8-warbird-prescreen.pine` fires `strategy.entry` on every baseline SuperTrend flip (`confirmedBuy` / `confirmedSell`). On MES 15m 2020–2024: **1,706 trades, PF 0.647, WR 33.4%, net −$9,833**.

Three observed issues:

1. **Every flip is a trade.** The inherited baseline scoring system (ARP 0–102 + TQI 0–1) computes a quality score, and `minScoreInput = input.int(60, ..., "Min Signal Score (display only)")` exists in the source, but the gate is literally labeled "display only" and never consulted by `strategy.entry`. No filter. No HTF agreement. No ADX. No session filter.
2. **SuperTrend line drifts on scroll.** `strategy(max_bars_back = 5000)` caps ATR warmup. When the visible window exceeds ~52 calendar days (15m ≈ 5000 bars), Pine re-seeds ST from a different anchor, shifting the plotted line and historical flip points.
3. **Ladder (ENTRY/SL/TP1-3) moves with new flips.** Every new flip overwrites `tradeEntry/tradeSl/tradeTp1-3`, and the drawing block deletes and re-creates the lines at the new levels. Visual effect: TP3 "chases the high".

Plus a semantic flaw: the existing labels call raw flips `▲ BUY` / `▼ SELL` and fire `strategy.entry` at the flip bar close. That's wrong. **A flip is a regime change signal, not an entry signal.** The ladder (ENTRY / SL / TP1-3) represents the trade. Entry should fire when price retraces to ENTRY and closes there, not when the flip happens.

---

## 2. Design principles

- Keep the locked inherited baseline engine verbatim (SuperTrend + ARP + TQI computations). Only change **how signals are consumed**.
- Explicit state machine from regime-flip → setup → entry → exit. No implicit state.
- Every filter is a toggleable input so we can measure per-layer lift via named backtest runs.
- Ladder is anchored at flip and does not move until the setup exits or is invalidated.
- Entry fires **on bar close** when price retests the ENTRY level, with all gates still aligned.

---

## 3. State machine

| State | Trigger | Visual | Strategy action |
|---|---|---|---|
| **IDLE** | no active setup | nothing | none |
| **FORMING** | ST flip + L1–L4 gates all pass at flip bar | "LONG BIAS" / "SHORT BIAS" label at flip bar + ladder drawn (grey dashed) | none |
| **READY** | FORMING bar confirmed | ladder turns solid | none |
| **TRADE_ON** | bar closes at/through ENTRY level with gates still aligned | "▲ BUY" / "▼ SELL" label at entry bar | `strategy.entry` fires |
| **EXITED** | SL / TP3 / opposite flip / bar timeout | ladder locked, outcome colored | `strategy.exit` fires |
| **INVALIDATED** | opposite ST flip occurs while in FORMING/READY | ladder greyed out, cancelled | none |
| **EXPIRED** | `expiryBarsInput` elapses without TRADE_ON | ladder removed | none |

**Anchor for ENTRY price:** flip bar close (current `tradeEntry = close` behavior). The number that appears on the chart ("ENTRY 7143.50") is the number price must retest.

**Entry trigger:** `barstate.isconfirmed AND ((tradeDir == 1 AND close <= tradeEntry) OR (tradeDir == -1 AND close >= tradeEntry)) AND allGatesStillAligned()`. Execution fills at next bar open (Pine default).

**Invalidation:** opposite ST flip before TRADE_ON reached → setup dies, no trade.

**Expiration:** `expiryBarsInput = input.int(20, ...)` bars elapsed from FORMING without TRADE_ON → setup dies, no trade.

**Only one active setup at a time.** If a new ST flip arrives while a setup is in FORMING/READY, it is ignored until the current setup resolves (TRADE_ON → EXITED, or INVALIDATED, or EXPIRED).

---

## 4. Gate layers (applied at FORMING and re-checked at TRADE_ON)

All gates are `input.bool`, toggleable independently for backtest isolation.

### L1 — Quality (baseline-native, already computed)

- `useQualityGate = input.bool(true)`
- **ARP score:** require `signalScore >= minScoreInput` (activate existing input; remove "display only" from its title). Defaults: longs 60, shorts 70.
- **TQI:** require `tqi >= minTqiInput` (new input, default 0.50).

### L2 — HTF trend agreement

- `useHtfGate = input.bool(true)`
- `htfInput = input.timeframe("60", options = ["15", "60", "240"])` (default 1h)
- Pull HTF ST direction: `[htfTrend] = request.security(syminfo.tickerid, htfInput, [stTrend], lookahead = barmerge.lookahead_off)`
- Longs require `htfTrend == 1`; shorts require `htfTrend == -1`.

### L3 — ADX trend strength

- `useAdxGate = input.bool(true)`
- `adxLen = input.int(14)`, `adxMin = input.int(22)`
- `[_, _, adxVal] = ta.dmi(adxLen, adxLen)`; require `adxVal >= adxMin`.

### L4 — Session filter

- `useSessionGate = input.bool(true)`
- Skip bars whose open time falls within `9:30–9:44 ET` (13:30–13:44 UTC).
- Optional: `rthOnlyInput = input.bool(false)` for RTH-only mode.

### L5 — Asymmetric thresholds (longs vs shorts)

- `longMinScore = input.int(60, minval = 0, maxval = 102)`
- `shortMinScore = input.int(70, minval = 0, maxval = 102)`
- Justified by Powerdrill's 4H PF asymmetry (longs 2.243, shorts 0.731).
- No additional structural filter for shorts in this revision — the score threshold asymmetry is the lever.

---

## 5. Execution contract

### Entry

- At TRADE_ON: `strategy.entry(id, strategy.long | strategy.short)`. Default fill = next bar open.

### Exit — ladder with partials

Three exits, unified by `from_entry`:

```pine
strategy.exit("TP1", from_entry = entryId, qty_percent = 40, stop = tradeSl, limit = tradeTp1)
strategy.exit("TP2", from_entry = entryId, qty_percent = 30, stop = tradeSl, limit = tradeTp2)
strategy.exit("TP3", from_entry = entryId, qty_percent = 30, stop = tradeSl, limit = tradeTp3)
```

- SL is shared across all three legs (all three `strategy.exit` calls pass the same `stop = tradeSl`).
- Realized partials are tagged per leg.
- On opposite ST flip while in TRADE_ON: call `strategy.close(entryId, comment = "opp_flip")` (hard close at market).
- On `timeoutBarsInput` bars from entry without TP3: `strategy.close(entryId, comment = "timeout")`. Default 100 (legacy author recommendation).

### Stop policy

- Keep the baseline structural ATR SL verbatim. **No hard dollar cap.** (Per Kirk's rule: "I don't care how wide the SL is if it's a winning trade.")
- The realized loss cap question stays deferred — may revisit after R1–R5 results.

### TP mode

- Switch default from **Dynamic** to **Fixed** at 1R / 2R / 3R.
- Rationale: dynamic scaling (`liveTp1R = effTp1R × dynScale`) recomputes per bar, which causes the "TP3 chases the high" visual. With Fixed mode, once the ladder is drawn, TP levels stay put.
- Dynamic can be re-enabled via input for later A/B testing after Fixed baseline is established.

---

## 6. Bug fixes bundled into this redesign

1. **ST drift on scroll** — remove `max_bars_back = 5000` at [v8-warbird-prescreen.pine:15](indicators/v8-warbird-prescreen.pine:15); let Pine auto-size. Verify by scrolling 2020 → 2026 on 15m with no visual line jump.

2. **Ladder not anchored to price** — solved by the state machine above. Ladder is drawn once at FORMING and not overwritten until the setup resolves. `tradeActive` var guards lines 628 and 662 so new flips cannot corrupt an in-flight setup.

3. **Invisible table** — diagnostic pass required before fix. Grep for `table.new` / `table.delete` / `showDashboardInput` and `GRP_DASH` defaults; most likely cause is either `showDashboardInput` defaulting to `false` or the table being deleted each bar without re-render. Implementation plan will identify and fix the exact cause.

4. **Pine warnings (7)** — lift `calcVolumeZ`, `calcSignalScore`, `calcScoreBreakdown` out of ternary/nested scopes into named local vars at the top of their blocks (warnings at L402, L595, L596, L650, L684). The two `barstate.islast` warnings (L931, L1052) are informational — acknowledge by design or move the logic out of `barstate.islast` branches if not needed in realtime.

5. **Chart hygiene** — remove the two dead public legacy prescreen instances on the TradingView chart (`xgdLpj`, `JxTjPm`). Keep only our PS strategy (`jrwTt0`).

---

## 7. Backtest plan (named runs, measure per-layer lift)

One file, progressive input toggles. Each run = one Strategy Tester snapshot. Record PF / WR / net P&L / trade count / max DD / avg trade / avg bars-in-trade.

Baseline conditions:
- MES 15m, 2020-01-01 → 2024-12-31
- 1 contract fixed, $1/side commission, slippage = 1 tick
- `use_bar_magnifier = true`, `process_orders_on_close = false`

| Run | Gates on | State machine | Hypothesis |
|---|---|---|---|
| **R0** | none | off (entry on flip, current behavior) | reproduce baseline PF 0.647 |
| **R0b** | none | **on** (wait-for-retest only, no quality gates) | isolate pure semantic-fix lift |
| **R1** | L1 only | on | baseline quality gate's standalone lift |
| **R2** | L1 + L2 | on | HTF trend filter incremental lift |
| **R3** | L1 + L2 + L3 | on | ADX incremental lift |
| **R4** | L1 + L2 + L3 + L4 | on | session filter lift |
| **R5** | all layers (L1–L5) | on | final production configuration |

**Kill switches:**

- If R0b alone hits PF ≥ 1.2: the entire gate stack may be unnecessary. Ship the state-machine fix and revisit gates empirically.
- If R1 alone hits PF ≥ 1.5: the inherited baseline scoring system is doing the work; L2–L5 are optional polish.
- If R5 lands PF < 1.5: fall back to **Approach C (long-only)** variant and re-run R5 with shorts disabled.

---

## 8. Success criteria

**Ship criteria for R5:**

- PF ≥ 1.5
- WR ≥ 45%
- Net P&L > +$5,000 on 2020–24 MES 15m (1-contract, $1/side, 1-tick slippage)
- Trade count in 100–400 range (ensures the system isn't over-selective)
- Max DD < $3,000

**Stretch:** PF ≥ 2.0 (hits Powerdrill's 4H long-only result on 15m).

**Floor:** PF ≥ 1.2 with WR ≥ 42%. Below this, design returns to brainstorming.

---

## 9. Out of scope for this design

- **480 × 2,592 CDP grid sweep (S2b plan):** deferred pending R1–R5 results. If the baseline scoring gate alone delivers edge, the grid is solving a solved problem.
- **AG training (Phase 4–5):** continues independently. This design produces a stronger candidate stream for AG to learn from.
- **`v8-warbird-live.pine` (companion indicator):** stays baseline-verbatim. Not touched in this design. Only `v8-warbird-prescreen.pine` changes.
- **Hard dollar loss cap:** deferred. May revisit after R1–R5 if realized loss distributions warrant it.
- **Dynamic TP mode:** kept as an input but defaults to off (Fixed). Can be A/B tested post-R5.

---

## 10. File layout

Single file changed: `indicators/v8-warbird-prescreen.pine`.

Expected diff shape:

- Add ~8 new inputs (gate toggles, thresholds, asymmetric scores, expiry/timeout bars, HTF timeframe, ADX params, session window).
- Remove `max_bars_back = 5000`.
- Add state machine: `tradeState` enum (`IDLE` / `FORMING` / `READY` / `TRADE_ON` / `EXITED` / `INVALIDATED` / `EXPIRED`) tracked as a `var int`. Add state transitions in the flip-detection block and the retest-check block.
- Rewrite `if confirmedBuy:` and `if confirmedSell:` blocks around lines 620–695 to enter FORMING state, compute and freeze ladder levels, and skip any new flip logic if `tradeState != IDLE`.
- Add new block: on every confirmed bar, if `tradeState == READY`, check retest trigger + gate re-alignment; on pass, transition TRADE_ON and fire `strategy.entry`.
- Replace monolithic `strategy.exit("Long Exit", ..., limit = tradeTp3)` with three-leg `qty_percent` ladder.
- Activate `minScoreInput` as entry gate; rename from "(display only)".
- Fix the invisible table (specific fix TBD in implementation plan, see §6.3).
- Lift function calls out of ternary/nested scope to clear Pine warnings.

Estimated LOC delta: +200 / −30.

---

## 11. Verification gates (per repo rules)

Before commit:

1. `pine-facade.tradingview.com` compile (must return `success: true, errors: 0`)
2. `scripts/guards/pine-lint.sh`
3. `scripts/guards/check-contamination.sh`
4. `scripts/guards/check-indicator-strategy-parity.sh` (if live indicator is affected — it shouldn't be)
5. `npm run build`
6. Backtest runs R0 through R5 on TradingView Strategy Tester with Deep Backtesting + Bar Magnifier enabled
7. Chart hygiene: confirm only `jrwTt0` remains on the chart after cleanup

---

## 12. Open questions to resolve in the implementation plan

- Exact root cause of the invisible table (diagnostic needed).
- Whether to expose the `gate-re-align at TRADE_ON` behavior as a separate input (`strictGateRecheck = input.bool(true)`) or hardcode it.
- Whether INVALIDATED / EXPIRED setups should leave a ghost ladder on the chart (for visual diagnostic) or be fully deleted. Default: delete on EXPIRED, grey out on INVALIDATED.
- Whether R0b deserves its own PR / git tag for the "semantic-fix-only" baseline, so it can be rolled back independently if gate layers regress.

---

## 13. Decision log

| Decision | Rationale |
|---|---|
| Approach B (full research-informed) | Hits every documented win lever. Layered backtest isolates per-filter lift. |
| Flip anchor = flip bar close (Option A) | Matches the ENTRY label already drawn on the chart. Simplest mental model. |
| Entry on **bar close** of retest, not intrabar touch | Kirk's explicit rule. Matches `barstate.isconfirmed` discipline. |
| Gate re-check at TRADE_ON | Kirk's explicit rule ("assuming all other gates are aligned"). Prevents stale setups from firing in degraded conditions. |
| Fixed TP mode default (not Dynamic) | Eliminates "TP3 chases the high" repaint. Dynamic can be re-enabled via input after Fixed baseline. |
| One active setup at a time | Prevents overlapping / overwriting ladders. Core of the ladder-anchoring fix. |
| No hard dollar loss cap at design time | Kirk's rule. Revisit after R1–R5. |
| Asymmetric long/short thresholds | Powerdrill 4H PF 2.243 vs 0.731 asymmetry. |
| Dynamic TP deferred, Crypto 24/7 preset deferred, grid sweep deferred | Prioritize semantic fix + native gate activation. Each deferred item becomes a follow-on experiment if needed. |
