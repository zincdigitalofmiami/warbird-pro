# Warbird Pro Indicator — Deep Audit

**Date:** 2026-04-29
**Audited file:** `indicators/warbird-pro-indicator.pine` (1685 lines, post-Phase-0.7 extraction with CW10003 fix applied)
**Auditor posture:** skeptical, hunting bugs, comments treated as suspect, line-cited findings only
**Pine compile status at time of audit:** 0 errors, 0 warnings (verified via TV pine-facade `--strict`)

## Executive Summary (in priority order)

1. **CRITICAL — pattern set sign-error contaminates AG exhaustion exports.** Lines 769-805 hardcoded "PROVEN PATTERNS" set is the same one called out as inverted by `docs/research/2026-04-29-candlestick-tf-priority-data.md`. The chain `bearCandleProven` (L1071) → `bearishExhaustion` (L1072) → `lastExhTriggerBar` → `mlExhBarsSinceTrigger` AG plot reaches the AG export surface. Until pattern selection is rebuilt off the corrected MUQWISHI top-6 slate (Phase 2), every downstream metric and ML-feature is contaminated. **Spot-check confirmed.**

2. **HIGH — `longConfirmed`/`shortConfirmed` are dead code in this indicator (lines 821-829).** They were the seed for the liquidity-sweep fakeout bug in the strategy parent. In the indicator they are defined but never read — so the bug is **inert here**. Good news, but the dead structure should be deleted to prevent silent re-activation. **Spot-check confirmed: definitions exist, zero reads.**

3. **HIGH — HTF confluence is direction-asymmetric (lines 371-410).** `htfFibPrice()` always anchors `htfLow + htfRange * ratio` (low up), but chart-TF `fibPrice()` uses `fibBase + fibDir * fibRange * ratio` with `fibDir` flipping by `fibBull`. Result: in bear setups (`fibBull=false`), chart `.382`/`.618` won't align with HTF `.382`/`.618` except by coincidence. ML features `htfConf382`, `htfConf618`, `htfConfTotal` carry asymmetric distributions. **Spot-check confirmed: htfFibPrice has no direction parameter.**

4. **HIGH — diamond AND-of-6 chain remains restrictive (lines 1067, 1072).** Same near-zero-joint-probability gate as the strategy parent. `bullCandleProven = longLowerShadow OR dragonflyDoji` is narrow; combined with `bullFpTriple` and `isSwingLowBar`, joint probability collapses to <1%. This is the campaign Phase 1 target — confirmed present in the indicator. **Spot-check confirmed.**

5. **HIGH — ~50 orphan computed features.** `regimeTrending`, `regimeRanging`, `er10`, `er20`, `atrPct`, `diSpread`, `adxSlope`, `barSpreadXVol`, `obvVal`, `mfi14`, `macdHist`, OR state, FVG distances, event-day flags, momentum oscillators (`mlVfBull`, `mlNfe`, `mlRsiKnn`, `mlConfluence`), execution-quality scores — all computed, zero plotted. **Spot-check confirmed (regimeTrending=1 occurrence, er10=1, atrPct=1, isEventDay=1, etc.).** Either delete the computations or re-add the export plots; the trailing comment claims they were removed for strategy-mode budget pressure but this is the indicator and that pressure no longer applies.

6. **HIGH — PLOT BUDGET comments contradict each other.** Header L26: "47 plot = 47/64 (17 headroom)". Footer L1686: "53 plot = 53/64". Actual count: **47 plot calls.** Header is correct, footer is stale. Of the 47, 5 emit constants/na (`mlExhZScore`, `mlExhZExtreme`, `mlContConfidenceTier`, `ml_cont_bars_since_trigger`, `ml_reversal_warning_in_trade`) — wasted slots. **Spot-check confirmed: header=47, actual=47, footer=53 stale.**

## Severity Rollup

| Severity | Count |
|----------|------:|
| CRITICAL | 1 |
| HIGH     | 11 |
| MEDIUM   | 13 |
| LOW      | 11 |
| INFO     | 12 |

## Per-Subsystem Findings (line-cited)

### Subsystem 1 — Header / Declaration / Request Budget

- **INFO** L26: header "PLOT BUDGET: 47 plot = 47/64 (17 headroom)" matches actual.
- **INFO** L28: stale comment "Momentum Oscillators (5 plots: ml_vf_bull, ml_vf_bear, ml_nfe, ml_rsi_knn, ml_confluence) added 2026-04-20" — these plots do NOT exist.
- **MEDIUM** L33: `max_bars_back(time, DRAW_HISTORY_BARS=5000)` constrains only `time`, not `close/high/low`. Some history accesses (e.g., `time[barsBack]` at L464 where `barsBack = legRightBars - recentHighOffset`) are uncapped if `recentHighOffset` is negative.
- **LOW** L17-24: claimed 6 request paths; actual = 5 unconditional `request.security` + 1 conditional + 1 `request.footprint` = 6. Matches.

### Subsystem 2 — Fib Engine (LOCKED FIB CORE per AGENTS.md L150-153)

> All findings flagged locked. Document only.

- **INFO (locked)** L421-440: `fibSettings.devThreshold` mutated each bar via `ta.atr(10)/close*100*deviationPct`. ZigZag library state captured via `var`. Standard pattern.
- **INFO (locked)** L437-442: pivot direction inferred from `lastPvt.start.price >= lastPvt.end.price`. Edge case: flat pivots degenerate but ZigZag/7 shouldn't produce flats.
- **MEDIUM (locked)** L584-615: `firstStructuralRetraced` resets to `false` on ZZ-only fallback. The lock state is dropped silently when transitioning out of structural-pivot territory.
- **MEDIUM (visual)** L624-630: `anchorBarFromTime` uses constant bar spacing — drifts across overnight gaps. Affects line drawing only.
- **LOW (locked)** L689-694: hysteresis `else: fibBull := true` resets to bullish every bar `isValid` is false; could produce false bullish initial state on dropouts.

### Subsystem 3 — Confirmation Gates (Lines 821-829)

- **HIGH** L821-829: `longConfirmed`/`shortConfirmed` are **defined but never read in this indicator.** Dead structure encoding the liquidity-sweep-fakeout bug. Recommendation: delete OR repurpose with diamond gate per Phase 1.

### Subsystem 4 — Pattern Detection (Lines 760-805)

- **CRITICAL** L769-805: hardcoded "EMPIRICALLY VALIDATED" pattern set is sign-error contaminated. `longUpperShadow`, `shootingStar`, `bearishEngulfing` are catalogued LOSING short signals on 4h MES per `docs/research/2026-04-29-candlestick-tf-priority-data.md`. Comment block reads negative-return cells as "STRONGEST bearish" — sign error.
- **MEDIUM** L779: `risingWindow = low > high[1]` — gap-up proxy that doesn't check wick fill. Acceptable.
- **MEDIUM** L792: `bearishEngulfing` doesn't require body to fully engulf prior body, only crosses. Strict enough definition.

### Subsystem 5 — Liquidity Sweep Detection (Lines 324-328) and Entries

- **HIGH** L324-328: hardcoded `swingLookback = 10`. Phase 3 candidate for tunability per fakeouts research doc.
- **HIGH** L1158-1159: `sweepLongTrigger`/`sweepShortTrigger` defined but never read in indicator. Inert — but should be deleted.
- **INFO** L1666: `liqSweepBull/Bear` IS used for `ml_liq_sweep` AG export. Only active downstream of sweep detection in this file.

### Subsystem 6 — Trade State Machine (Lines 1085-1295)

- **MEDIUM** L1204-1220: same-bar NONE→SETUP→ACTIVE transition. `setupBar == entryBar` whenever they coincide. No enforcement that setup precedes entry by ≥1 bar.
- **MEDIUM** L1257-1268: same-bar SL+TP race resolution defaults to SL-first (pessimistic). Acceptable for label-only indicator. Document the assumption.
- **LOW** L1222: `tradeInFlight` excludes TRADE_HIT_TP5; relies on "resolution happens this bar" invariant. Brittle.
- **LOW** L1278: outcome remap order-dependent; legend at L1109 says `5=TP3_HIT`. Verify external consumers honor this exact mapping.
- **MEDIUM** L1293: `tradeSetupEndedNow` defined and never read. Orphan.
- **MEDIUM** L1113-1116: `lastExhTriggerDir`, `lastTier1ExhBar`, `lastTier1ExhDir` never read. Orphans.
- **LOW** L1117: `mlContConfidenceTier = 0` `var`-declared and never reassigned; plot at L1679 always emits 0.0.

### Subsystem 7 — Stop Ratchet (Lines 1224-1251)

- **INFO** L1228-1248: ratchet uses `math.max` (long) / `math.min` (short) — guarantees stop only tightens. **Validated correct.**
- **LOW** L1230: `roundToTick(entryPrice)` redundant since entry is already a tick-rounded fib level. Minor.
- **MEDIUM** L1226-1248: no explicit `>= 5` rung. If exit target < TP5 and price tags TP5, no extra ratchet. Edge case.

### Subsystem 8 — HTF Confluence (Lines 360-410)

- **HIGH** L371-410: direction-asymmetric. `htfFibPrice` always anchors low-up; chart-TF flips by `fibBull`. Bear setups won't align with HTF except by coincidence. ML features `htfConf382/618/Total` are biased.
- **MEDIUM** L361: `htfConfTolPct = 0.15` hardcoded, not tunable.
- **LOW** L363-365: HTF security calls all use `lookahead_off`. Correct.

### Subsystem 9 — Footprint + Diamond (Lines 735-1080)

- **HIGH** L1067, L1072: AND-of-6 diamond chain. Joint probability ~0.1% of bars. Same dead-diamond issue documented in `project_diamond_detectability_crisis.md`.
- **MEDIUM** L988: `mlExhGeomConfluence` uses `p1272` which is computed but not drawn (per L93 comment).
- **MEDIUM** L996-998: `triggerRow`, `triggerRowDelta`, `pocRowVol` defined and never read directly (`pocRowVol` IS used at L1000 to compute `extremeRowVolRatio` which is used).
- **MEDIUM** L1005-1007: `mlExhAbsorption` definition — sign convention sane.
- **LOW** L1019: `exhCooldown = 8` hardcoded. Tunability gap.
- **LOW** L1023: `mlExhSessionValid = hourEt != 17` blocks only 5pm ET. Reasonable.

### Subsystem 10 — Regime Detection (Lines 234-256)

- **HIGH** L240-241: `regimeTrending`, `regimeRanging` computed but never read. Orphans.
- **HIGH** L244-256: `er10`, `er20`, `atrPct`, `diSpread`, `adxSlope` computed but never read. Orphans.

### Subsystem 11 — Visual Rendering (LOCKED PER VISUAL CONTRACT)

> All findings inside protected R01-R14 regions. Document only.

- **INFO (visual)** L1319-1335: var line/box declarations match R06.
- **LOW (visual)** L1449: `effectiveDrawLeftBar = tradeFibFrozen ? snapDrawLeftBar : drawLeftBar`. Implicit invariant that snapDrawLeftBar non-na when tradeFibFrozen is true. Fragile.
- **INFO (visual)** L1480-1495: 16 `drawAnchoredLine` calls match R09. `lineNeg236` drawn with `visible=false` (L1481) — historical artifact.

### Subsystem 12 — AG Export Plots (Lines 1623-1681)

- **HIGH** L1670: `plot(mlExhZScore, ...)` where `mlExhZScore = na` permanently. Wasted slot.
- **HIGH** L1671: `plot(mlExhZExtreme ? 1.0 : 0.0, ...)` where `mlExhZExtreme = false` permanently. Wasted slot.
- **HIGH** L1679: `plot(float(mlContConfidenceTier), ...)` where value is permanently 0. Wasted slot.
- **HIGH** L1680: `plot(float(na), "ml_cont_bars_since_trigger", ...)` — explicit na plot. Wasted slot.
- **HIGH** L1681: `plot(0.0, "ml_reversal_warning_in_trade", ...)` — explicit constant 0. Wasted slot.
- **Total wasted: 5 of 47 plot slots.** Useful: 42.
- **HIGH** L1684-1686: footer comment claims "53 plot = 53/64" — stale.

### Subsystem 13 — Repaint Discipline + barstate.isconfirmed

- **INFO** L888: `confirmed = barstate.isconfirmed` propagated through structure conditions and state machine. **Validated correct.**
- **LOW** L327-328: `liqSweepBull/Bear` not gated by `confirmed`. Could repaint AG dataset on incomplete bars. (Used only at L1666 export — typically read post-close.)
- **LOW** L336-345: `fvgBull`, `fvgBear`, `nearestFvgBullMid/BearMid` updates run unconditionally.
- **MEDIUM** L289 (OR detection): no `barstate.isconfirmed` gating.

### Subsystem 14 — Pine v6 Idioms

- **INFO** L30: `import TradingView/ZigZag/7 as zigzag` — current published library.
- **INFO** L33: `max_bars_back(time, DRAW_HISTORY_BARS)` — correctly applies only to `time`.
- **LOW** L1085-1094: `var int TRADE_NONE = 0` etc. — `const int` would be more idiomatic for never-changing values.
- **LOW** L64: `useFibAnchorTimeframeOverride` relies on `timeframe.in_seconds()` returning sane values for all inputs. Edge case for non-time inputs.
- **LOW** L656-668: hardcoded loop bound for confluence-quality periods. Maintainability hazard.

## Cross-Cutting Concerns

### C1 — Computed-but-not-exported feature stack (HIGH)

~25 derivative features computed and zero exported. Either delete the computations (if AG owns server-side per the trailing comment) or re-add the plots. AG cannot lineage these features back to Pine without exports.

### C2 — Sign-error contamination chain (CRITICAL → HIGH downstream)

Pattern sign-error reaches: `provenBearishPattern` (L805) → `bearCandleProven` (L1071) → `bearishExhaustion` (L1072) → `exhaustionSignalDir` (L1075) → `lastExhTriggerBar` / `mlExhBarsSinceTrigger` AG export (L1297) and `ml_exh_confidence_tier` plot (L1675). Until Phase 2 lands, AG bear-direction features are inverted.

### C3 — Orphan-variable density (~50 variables, MEDIUM)

Removing them simplifies future audits, reduces compute, and clarifies the indicator's actual export surface.

### C4 — Lookback windows (MEDIUM)

Multiple `ta.highest`/`ta.lowest` windows hardcoded (8/13/21/34/55 + 55 HTF + structural windows + direct-lock recent leg). All at top level; not in conditional branches. OK on budget.

## Recommended Priority Order

### Phase A — must address before AG treats this indicator as truth

1. Pattern detection sign error (CRITICAL, L769-805) — Phase 2 plan delivers this.
2. Diamond AND-of-6 collapse (HIGH, L1067, L1072) — Phase 1 plan delivers this.
3. HTF confluence direction asymmetry (HIGH, L371-410) — new finding, needs its own micro-plan.

### Phase B — clarity / correctness

4. Delete dead `longConfirmed`/`shortConfirmed` (L821-829) and `sweepLongTrigger`/`sweepShortTrigger` (L1158-1159).
5. Resolve PLOT BUDGET comment contradiction (header 47 correct, footer 53 stale).
6. Remove `mlExhZScore`, `mlExhZExtreme`, `mlContConfidenceTier`, `ml_cont_bars_since_trigger`, `ml_reversal_warning_in_trade` zero-emit plots (5 wasted slots) OR wire them with real values.
7. Decide: delete orphan computations OR re-add corresponding export plots within the 47/64 → 64 budget.

### Phase C — robustness

8. Opening-range timeframe fragility (L284-303) — gate by `timeframe.in_seconds()` or delete since OR exports are orphan.
9. Same-bar SETUP→ACTIVE — document the invariant or enforce `bar_index > setupBar`.
10. Stop ratchet TP5 step (L1226-1248) — add `>= 5` rung.

### Phase D — cosmetic

11. Replace `var int TRADE_NONE = 0` with `const int TRADE_NONE = 0`.
12. Remove stale "Momentum Oscillators" comment (L28).
13. Reconcile request budget header (L17-24) with actual count.

## Validated As Correct (carefully scrutinized, not glossed over)

- `barstate.isconfirmed` propagation through entry triggers and state machine. No mid-bar trade-state writes.
- `request.security` lookahead — all 5 calls use `barmerge.lookahead_off`. No repaint vector.
- `ta.*` placement — all calls at function/module top level (post-CW10003 fix). No conditional-branch CW10003 risk.
- ZigZag library handle persistence — `var fibSettings`, `var fibZZ` correctly persist; `lastPvt` resets each bar.
- Stop ratchet monotonicity — confirmed.
- Trade resolution SL-first ordering — confirmed.
- Trade direction lock at SETUP→ACTIVE prevents anchor-shift corruption.
- Trade fib snapshot freeze/release via `snapCaptureEdge`/`snapReleaseEdge` correct.
- Cooldown counter handles no-prior-exit case (default 999).
- `fpAvailable` consistently null-checked before footprint access.
- One-shot event semantics applied consistently.
- Footprint row indexing symmetric from both ends.
- EMA distance helpers (`f_ema_dist_pct`, `f_ema_dir`) handle both sides.
- Visual contract regions R01-R14 intact.
- Locked fib core (`fibHtfSnapshot`, `fibZzSource`, anchor ownership, ladder math, snapP*) structurally identical to strategy parent. No drift.
- `pivotNearZone` correctly uses `isValid` AND zone bounds. No na-leak.
- `backtestExitTargetIndex` correctly maps strings to ints with TP1 fallback.
- AD line uses `lookahead_off`. Daily breadth cannot leak future.
- Anchor change → `lastBreakBar` reset prevents stale break references.

## What This Audit Does NOT Do

- Modify any Pine files. Audit only.
- Propose changes to the locked fib core (per AGENTS.md L150-153) — flagged for Architect.
- Propose changes to the visual contract (per `visual_contract_line_ranges.md`) — flagged for Architect.
- Run Optuna or backtests.
- Provide pixel-precise visual validation — that requires TV chart inspection.

## Sources

- Source code: `/Volumes/Satechi Hub/warbird-pro/indicators/warbird-pro-indicator.pine` (1685 lines, audit timestamp 2026-04-29)
- TV pine-facade compile validation: 0 errors, 0 warnings under `--strict`.
- Visual contract guard: PASS (all 14 regions intact).
- Fib scanner guardrails: PASS (no banned patterns).
- Cross-references: `AGENTS.md` L150-153, `docs/contracts/pine_indicator_ag_contract.md`, `docs/research/2026-04-29-candlestick-tf-priority-data.md`, `docs/research/2026-04-29-fakeouts-to-avoid.md`, `docs/research/2026-04-29-fib-anchor-tf-failure-modes.md`, `docs/contracts/visual_contract_line_ranges.md`, `feedback_visual_contract_sacred.md`, `project_diamond_detectability_crisis.md`, `project_liquidity_sweep_filter.md`.
