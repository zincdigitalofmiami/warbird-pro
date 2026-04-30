# Liquidity Sweeps Without Exhaustion — MES1! Annotated Evidence

**Date:** 2026-04-29
**Status:** Research — operator-annotated success criteria for the entry/exit/exhaustion campaign
**Source:** Architect's annotated TradingView screenshots, MES1!, 2026-04-28 → 2026-04-29 session
**Companion campaign:** `docs/plans/2026-04-29-entry-exit-exhaustion-optuna-campaign.md`
**Memory rule:** `feedback_visual_contract_sacred.md` (visual layer untouchable across all campaign work)
**Phases impacted:** Phase 1 (diamond detectability), Phase 2 (entry gate), Phase 3 (diamond tuning), Phase 4 (stop/target)

## Reframing — these are liquidity sweeps, not random fakeouts

Per Architect 2026-04-29 — the bars annotated below are **liquidity sweeps**, not random failed breakouts. ICT/SMC market-structure terminology:

- **Bullish liquidity sweep** = price wicks below a recent swing low to grab sell-side stops, then closes back above. Signals stop-hunt completion. May or may not precede a real bullish reversal.
- **Bearish liquidity sweep** = price wicks above a recent swing high to grab buy-side stops, then closes back below. Same logic, opposite direction.

A sweep is **not** automatically a tradeable entry. It's a *manipulation event* — institutional order flow grabbing stop liquidity. Whether the sweep precedes a real reversal vs. continuation in the original direction depends on what comes AFTER the sweep:

- Sweep + **real exhaustion** (footprint absorption, delta divergence, zero-print, etc.) → high-conviction reversal, valid entry.
- Sweep + **no exhaustion confirmation** → the wick was just liquidity collection; price likely continues in the original trend direction → NO entry.

**Per Architect: "Can be smoothed via accurate exhaustion."** Phase 1 (Diamond Detectability Fix) is the smoothing mechanism. When the diamond fires accurately, sweeps with no exhaustion get filtered out. Sweeps with exhaustion get green-lit.

## Existing code: where the bug lives

The paste already detects liquidity sweeps but uses them as direct entry confirmations without diamond gating:

```pine
// Paste lines 324-328 — primitives
int swingLookback = 10                                  // HARDCODED — Phase 3 candidate for tunability
float swingHigh = ta.highest(high, swingLookback)[1]
float swingLow = ta.lowest(low, swingLookback)[1]
bool liqSweepBull = low < swingLow and close > swingLow   // swept below, closed back inside
bool liqSweepBear = high > swingHigh and close < swingHigh // swept above, closed back inside

// Paste lines 821-823 — direct entry confirmation, NO diamond co-confirmation required
bool longConfirmed = (fpDeltaConfirmLong or not fpAvailable) and (
    provenBullishPattern or
    wickRejectBull or
    liqSweepBull)         // ← single sweep triggers entry; this is the fakeout path

bool shortConfirmed = (fpDeltaConfirmShort or not fpAvailable) and (
    provenBearishPattern or
    wickRejectBear or
    liqSweepBear)         // ← same on short side
```

Vestigial (dead) code at lines 1157-1158:
```pine
bool sweepLongTrigger = entryZoneTouched and liqSweepBull   // defined, never read
bool sweepShortTrigger = entryZoneTouched and liqSweepBear  // defined, never read
```
These can be removed in any future Pine prep cycle that touches this region. Not blocking.

## Annotated examples (from Architect's 2026-04-29 screenshots)

### Example 1 — bullish liquidity sweeps above .786 / 1.000 without follow-through

Visible context: MES1! recent bars showing a 3-bar cluster wicking up into the .786 (~7176-7182 area) on a fib ladder anchored 0=7131.25 → 1.000=7188.25. After the wicks, price did not push to T1 (7201.75) — instead reversed back into the .618-.786 zone.

**Architect annotation:** "fakeouts I want to avoid"

**Sweep classification:** these wicks penetrate the recent swing high (per `swingLookback=10` on chart TF) → `liqSweepBear` would fire, OR if the wick is testing the upside resistance from below, `liqSweepBull` of the previous swing low. Either way the current entry chain (`longConfirmed` / `shortConfirmed`) fires without exhaustion confirmation.

**Failure mode:** sweep without diamond co-occurrence. Phase 1 fix prevents the entry.

### Example 2 — bullish reclaim with sweeps stalling at .786

Visible context: MES1! WB_LONG → Long TP, then a cluster of bars at the upper edge of the trade range showing wicks above the prior swing high before the move continued. The annotation arrow points to the stalling cluster (approximately 7180-7184) where price tested above .786 (7182.50) but failed to make T1 cleanly.

**Architect annotation:** "fakeouts I want to avoid"

**Sweep classification:** bearish sweep wicks above the recent swing high → `liqSweepBear` fires → `shortConfirmed=true` if delta is bearish or footprint unavailable → premature short entry against the actual continuation trend.

**Failure mode:** sweep firing in CONTINUATION context (price actually wants higher) without exhaustion confirmation. Phase 1 fix gates the short entry until accurate exhaustion confirms the sweep is real.

### Example 3 — bearish liquidity sweep below .236 / 0 without follow-through

Visible context: MES1! WB_SHORT → Short TP, with subsequent bars wicking down to the 0 level (7131.25) but failing to extend lower. The trade itself was good (TP +1) but follow-up bars showed false-reversal wicks at the extreme.

**Architect annotation:** "fakeouts I want to avoid"

**Sweep classification:** bullish sweep below the recent swing low → `liqSweepBull` fires → re-entry temptation on a long that has no exhaustion backing.

**Failure mode:** sweep at extreme without diamond confirmation = liquidity grab, not reversal. No entry.

## Implications for the campaign

### Phase 1 (Diamond Detectability) — primary smoothing layer

The current AND-of-6 diamond gate fires zero diamonds. Phase 1 restructures this to a weighted score-based gate so diamonds fire reliably. **Critical addition:** the new gate must accept `liqSweepBull` / `liqSweepBear` as ONE input to the score, not as a separate pass-through entry trigger. The entry chain (`longConfirmed` / `shortConfirmed`) needs modification: when the only confirmation is `liqSweepBull/Bear` (no pattern, no wick rejection), require diamond co-occurrence.

Acceptance criterion for Phase 1: review the bars annotated above against the post-Phase-1 logic. Each annotated bar must classify as either:
- No entry fired (sweep + no diamond → suppressed), OR
- Entry fired but immediately invalidated by diamond + structure-break combo.

### Phase 2 (Entry Gate Patterns + MA)

The pattern set tuned in Phase 2 must complement, not duplicate, sweep detection. Patterns like Long Lower Shadow / Long Upper Shadow are wick-heavy by definition and may fire on the same bars as sweeps. The Optuna search must penalize trade configurations that take the sweep + pattern combo without diamond confirmation.

### Phase 3 (Diamond Tuning) — `swingLookback` becomes tunable

Currently `swingLookback = 10` is hardcoded. In Phase 3 it becomes an `input.int` (proposed range 5-25 per the existing campaign plan Section 4 Phase 3). Different timeframes need different sweep windows: 5 (=25 min on 5m) for fast scalp detection, 25 (=10 hours on 15m or 100 hours on 4h) for true HTF sweeps.

### Phase 4 (Stop / Target Structure)

If a sweep + diamond-confirmed entry hits a real reversal, the stop should NOT be inside the sweep wick. Phase 4 should evaluate: ATR stop sized to be outside the typical sweep wick range. The walk-forward isolates this.

## Success criterion for the campaign

When Phase 7 (Full Integrated Validation) runs, all bars annotated above must classify as **no entry fired**, OR **entry fired but immediately invalidated by Phase 1-tuned exhaustion signal**. Either outcome is acceptable. An entry that fires AND holds AND loses on these bars indicates the sweep filter didn't converge cleanly.

## Note on screenshots

I cannot save chat-attached PNGs to disk. Architect: drop the three annotated screenshots into `.references/` manually whenever convenient, suggested filenames:

- `.references/liquidity_sweep_2026-04-29_chart1_above_786.png`
- `.references/liquidity_sweep_2026-04-29_chart2_bullish_reclaim_stalls.png`
- `.references/liquidity_sweep_2026-04-29_chart3_below_236.png`

Until those files exist in `.references/`, this doc serves as the verbal record of the operator's intent.
