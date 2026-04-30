# Fib Anchor Timeframe-Dependent Failure Modes — Research

**Date:** 2026-04-29
**Status:** Research — evidence collection, no implementation proposed
**Scope:** `indicators/v7-warbird-institutional.pine` + `indicators/v7-warbird-institutional-backtest-strategy.pine` fib anchor behavior across MES1! timeframes
**Constraint:** Fib core locked (AGENTS.md 150-153, CLAUDE.md 93-95). This doc proposes NO Pine changes. It documents new empirical evidence and identifies a gap not covered by prior approved design.

## Cross-References (read these first)

- `docs/plans/2026-04-10-fib-engine-fix-design.md` — approved 4-fix design (threshold floor, depth floor, range gate, direction-from-anchor)
- `docs/research/2026-04-25-autofib-mechanics.md` — ZigZag/7 + `ta.pivothigh` semantics validated, snapshot architecture confirmed
- `docs/plans/2026-04-24-v7-backtest-strategy-single-ladder-snapshot.md` — single-ladder snapshot fix (COMPLETE 2026-04-25)
- `docs/contracts/v7_interface_divergence.md` — institutional vs backtest-strategy trigger family split

---

## TL;DR

Three live-chart observations on MES1! 2026-04-29 (operator: Architect, both v7 institutional indicator and `codex/wb-opt-bt-first-structural-fibs` strategy loaded simultaneously):

1. **30m chart**: institutional indicator's pure-ZigZag anchor captures the most recent leg cleanly. Wins.
2. **1h chart**: both engines produce identical anchors (steady state — structural-pivot lock falls through to ZigZag when no terminal disagreement exists).
3. **4h chart**: both engines fail in **opposite** directions. Pure ZigZag pulls too wide (anchored to multi-month bracket, T4 ~7237). Structural-pivot lock holds too sticky (5+ week old leg, missed the most recent ~550-point move up).

**Common root cause:** neither engine has a "leg freshness" or "relevance" model. ZigZag honors any new pivot extreme regardless of whether the leg is still the dominant move. Structural-pivot lock validates only by retracement geometry (single `FIB_786` constant) and pivot deviation, never by leg age or relevance to current price action.

This is **a gap not covered by the 2026-04-10 fix design**. That design addressed direction inversion, threshold/depth floors, and the range gate. None of its four fixes constrain *which leg* gets anchored once those gates pass.

---

## Empirical Evidence

### Observation 1 — 30m MES1!, 2026-04-29

Institutional indicator anchor: 0=7188.00 → 1.000=7146.25 (range 41.75 pts). Captures the most recent down-leg from the late-April bounce high to the 12:00 PM 04-29 low. T1=7136.50, T2=7120.50, 1.786=7113.50 — all relevant projections for the live move.

`WB_SHORT` fired at ~7180 in the .236-.382 zone. Whether the trade was good is anecdote; the *anchor* is correct.

**Verdict:** Pure-ZigZag wins on 30m where pivot density is high enough that ZZ pivots = relevant legs.

### Observation 2 — 1h MES1!, 2026-04-29

Both engines produce identical anchor: 0=7223.00, .500=7184.75, 1.000=7146.25, 1.382=7117.00.

Trace: paste's `firstStructuralHigh` (line 612) defaults to `acceptedHigh = zzHighPrice` when no structural terminal qualifies (lines 605, 580). On a chart where ZZ and structural pivots agree, the paste's anchor pipeline is functionally a pass-through.

**Verdict:** No divergence in steady state. Structural lock is dormant.

### Observation 3 — 4h MES1!, 2026-04-29

Two anchor systems visible on chart, diverging hard:

- **Paste (structural lock):** 0=6352, 1.000=6654.75, range 302.75 pts. This leg is from late-March low to early-April high. Price has since climbed to ~7200 — five+ weeks past the 1.000 level. The first-structural-fib `FIB_786` retracement gate (paste lines 542-552) was never triggered, so the leg is still locked.
- **Indicator (pure ZZ):** anchored to a much earlier base, with extension targets reaching T4 7237.50 and a TS line at 7144.50. The ZZ engine accepted a wider, structurally older leg as the "current" anchor.

**Both wrong.** The visually correct anchor on this 4h chart is approximately the early-April low (~6352) to the most recent swing high (~7200) — neither engine produces it.

**Verdict:** Anchor selection breaks down on higher timeframes where multiple candidate legs exist and neither engine has a tiebreaker by relevance.

---

## Failure Mode Taxonomy

| Mode | Mechanism | TFs observed | Example |
|---|---|---|---|
| **Stale-leg lock** | Structural-pivot lock holds an old leg until 78.6% retracement; price runs without retracing → leg never released | 4h, likely higher | Paste on 4h: held late-March leg through 5+ weeks of advance |
| **Stale-pivot anchor** | ZigZag accepts any pivot meeting deviation/depth, regardless of recency or relevance | 4h, possibly D | Indicator on 4h: T4 ~7237 from multi-month-old base |
| **Steady-state agreement** | Both engines produce the same anchor when ZZ and structural pivots co-locate | 1h | Identical anchors on 1h |
| **Pivot-density correctness** | On low timeframes, ZZ pivot frequency matches the cadence of relevant legs | 5m, 30m, likely 15m | 30m correct, 5m presumed correct (not yet validated) |

---

## What Prior Approved Design Covers — and Does Not

`docs/plans/2026-04-10-fib-engine-fix-design.md` Fix 1-4:

| Fix | Addresses | Addresses TF failure modes? |
|---|---|---|
| 1. Threshold floor (2.0%) | Micro-swing detection | No — once a leg passes the threshold, no relevance check follows |
| 2. Depth floor (15) | Shallow pivots qualifying | No — same as above |
| 3. Min range gate (`minFibRangeAtr`) | Sub-10-point trades from tight ladders | Partial — rejects micro-ranges, doesn't reject stale wide ranges |
| 4. Direction from anchor structure + `breakAgainst` invalidation | Inverted fib grid, ladder validity gating | Partial — invalidates on counter-break, but stale-leg-without-counter-break is not detected |

**Gap:** none of the four fixes ask "is this leg still the dominant move on this timeframe?" The fixes harden *what qualifies as a pivot* and *what counts as invalidation* — neither concept covers leg freshness when the market simply walks away from a leg without retracing or counter-breaking.

`docs/research/2026-04-25-autofib-mechanics.md` Section 6 of recommendations explicitly defers this question: "No repainting fix needed... ZigZag/7 + `barstate.isconfirmed` is the standard pattern." That research validated mechanics; it did not propose a freshness model because the evidence for needing one wasn't yet collected.

---

## The Gap: Leg Freshness / Relevance Model

A complete anchor engine needs to answer three questions:

1. **What qualifies as a pivot?** ✅ Answered — ZigZag/7 deviation+depth, plus `ta.pivothigh/pivotlow` for structural pivots.
2. **What invalidates a leg?** ⚠️ Partially answered — counter-break (`breakAgainst`), 78.6% retracement (structural lock). Both require an event; neither handles silent staleness.
3. **What makes a leg the *current* leg?** ❌ Not answered.

Candidate freshness signals to evaluate (not implementation — just hypotheses to test against labeled data):

- **Time decay**: a leg older than N bars on the current TF is automatically deprecated unless reaffirmed by retest
- **Relative magnitude**: if a newer leg's range is ≥ X% of the locked leg's range, the newer leg supersedes
- **ATR distance**: if current price is more than M × ATR beyond the locked 1.000 without retracement, the leg is exhausted
- **HTF alignment**: anchor on the parent TF's most recent confirmed leg, not the chart TF's

These are mutually exclusive, partially overlapping, or complementary — labeling will tell us which combination matches operator judgment.

---

## Proposed Labeling Protocol (no Pine — pure data collection)

To validate any future freshness model before it's implemented:

1. Architect picks 15-25 bar timestamps across MES1! 5m, 15m, 30m, 1h, 4h spanning 2024-2026 (regime-balanced).
2. For each timestamp, Architect labels the **operator-correct anchor high/low** by visual judgment.
3. For each timestamp, log:
   - Pure-ZigZag output (institutional indicator)
   - Structural-pivot-lock output (paste branch)
   - 2026-04-10-fix-design predicted output (paper exercise — applying fixes to ZZ output)
4. Score each engine: ✅ matches operator label, ⚠️ off by one pivot, ❌ wrong leg entirely.
5. Group misses by failure mode (stale-leg-lock, stale-pivot, etc.) to confirm whether the taxonomy in this doc is complete.

A blank labeling sheet template lives at `docs/research/2026-04-29-fib-anchor-labeling-sheet.md` (see companion file).

**Gate before any Pine work:** at least one full labeling pass across all 5 timeframes, ≥3 examples per TF, results reviewed against the 2026-04-10 design. If labeled misses are dominantly *not* covered by the 4 existing fixes, then a follow-up plan adding a freshness model is justified. If labeled misses ARE covered by the 4 fixes (just not yet applied), no new plan is needed — apply the existing approved fixes.

---

## Open Questions for Architect

1. Does this evidence justify opening the fib core for an addendum to the 2026-04-10 plan (a 5th fix: freshness model)?
2. Or is the right move to first apply the 4 existing approved fixes to the paste branch (and main), retest across timeframes, and re-evaluate whether a 5th fix is still needed?
3. Are there additional regimes (NFP days, FOMC, gap-down opens, holiday sessions) that should be over-represented in the labeling protocol?

---

## Adjacent Finding: Confirmation Gate Is Also TF-Naive AND Sign-Mis-grounded

The confirmation gate (paste lines ~768-810) hardcodes a six-pattern set claimed as "EMPIRICALLY VALIDATED ON MES 15m." Independent verification using the MUQWISHI "Candlestick Patterns on Backtest" indicator (saved at `.references/candlestick-patterns-on-backtest-MUQWISHI.pine`, MPL 2.0) shows two compounding problems:

1. **Sign-interpretation error.** The paste reads negative-return Bear cells as "strong bearish signals." The MUQWISHI source backtest function proves the convention is the inverse: positive % = labeled-direction trade was profitable; negative % = trade lost money. The paste's "Long Upper Shadow (-7.7% / 1:6 — STRONGEST bearish on MES 15m)" therefore describes a trade that LOST 7.7% of equity. On 4h with 7 years of data the same pattern reads -33% to -39%. The pattern fails as a short signal across nearly every TF.

2. **TF-naive selection.** Even if the sign were read correctly, the chosen patterns differ in performance by timeframe. Engulfing (Bull) wins on 30m/4h, Tweezer Bottom (Bull) wins on 4h/30m, Long Lower Shadow (Bull) wins on 30m. None of these are in the hardcoded set.

Per-TF empirical winners and the corrected Top-6 candidate slate live in `docs/research/2026-04-29-candlestick-tf-priority-data.md`. The next-phase plan to replace the hardcoded set with Optuna-tuned selection is `docs/plans/2026-04-29-confirmation-gate-optuna-phase.md`.

**Why this belongs in the anchor doc:** the gap is structurally identical — anchor selection AND pattern selection are both TF-naive AND lock-grounded in evidence that doesn't generalize. Any future fib-anchor plan must coordinate with the confirmation-gate phase, because tuning one with a broken version of the other produces compounded breakage.

## What This Doc Does NOT Do

- Propose any Pine code changes
- Override or replace the 2026-04-10 fix design
- Touch the locked fib core
- Propose Optuna runs on un-fixed code
- Make claims about which strategy version is "best" — that question is now blocked on the evidence collection above

## Sources

Primary evidence: live MES1! TradingView screenshots (1h, 4h, 30m), 2026-04-29 ~16:50 ET, both v7 institutional indicator and `codex/wb-opt-bt-first-structural-fibs` strategy loaded.

Confirmation-gate evidence: six MUQWISHI dashboard screenshots delivered 2026-04-29 (one per timeframe), MUQWISHI source code reviewed and saved at `.references/candlestick-patterns-on-backtest-MUQWISHI.pine`.

Code references: `indicators/v7-warbird-institutional-backtest-strategy.pine` lines 491-552 (structural-pivot block), 605-617 (firstStructural fallback to zzHighPrice), 542-552 (FIB_786 retracement gate), 768-810 (hardcoded "PROVEN PATTERNS" comment block — sign-error origin); `indicators/v7-warbird-institutional.pine` lines 444-445 (pure-ZigZag fib anchor).
