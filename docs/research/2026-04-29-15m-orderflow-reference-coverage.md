# 15m Reversal/Exhaustion Reference — Coverage Map

**Date:** 2026-04-29
**Status:** Research — coverage map only. NO scope additions to active plan.
**Purpose:** Architect shared a second reference batch (order flow, absorption, CVD, Volume Profile, time-of-day, Better Momentum, emini-watch rules of thumb). This doc maps each item to: already-in-code / explicitly-excluded / candidate-pending-approval. Per `feedback_no_bollinger_bands.md` memory rule, reference reading is context, not a shopping list.
**Active plan:** `docs/plans/2026-04-29-confirmation-gate-optuna-phase.md` — unchanged. No additions made to its scope without explicit per-item approval.

## Coverage Map

| Reference item | Status | Where in paste / why excluded |
|---|---|---|
| **Absorption at key levels** | ✅ in code | `mlExhAbsorption` paste line 1004; gates POC at extreme + rejection candle |
| **0-Tick reversals** (bid=0 at low / ask=0 at high) | ✅ in code | `mlExhZeroPrint` + `zeroPrintVolRatio` input paste lines 153, 1008 |
| **CVD divergence** (cumulative delta vs price) | ❌ NEW — candidate | Paste has per-bar `fpDelta` only. No `ta.cum(...)` aggregation, no divergence detection. Genuinely missing. |
| **Volume Profile / HVN / LVN / Value Area** | ❌ NEW — candidate | Paste has per-bar Footprint POC only. No session-level or daily VP. Adding would consume request budget (`request.security_lower_tf` or equivalent). Material new surface. |
| **Key Reversal Bar pattern** (new extreme + close past prior bar) | ❌ NEW — candidate | Not detected as a named pattern. Could fold into MUQWISHI-style detection cheaply. |
| **Outside Engulfing Bar** | ⚠️ partial | MUQWISHI Engulfing (Bull/Bear) is in the top-6 slate of `2026-04-29-confirmation-gate-optuna-phase.md`. "Outside" variant (full-range engulf, not just body) is a stricter sub-case — could be a tunable threshold on the existing Engulfing detector. |
| **Pre-11 AM CST reversal time filter** | ❌ NEW — candidate | Paste has time primitives (`hourEt = hour(time, "America/New_York")`, line 1022) but only filters 5 PM (`mlExhSessionValid = hourEt != 17`). A clock-cutoff gate at 12:00 PM ET (11 AM CST) is one-line work. |
| **"Wait for second leg" / two-stage exhaustion** | ⚠️ partial | Paste has `cooldownBarsInput` (line 139, default 0 — disabled). That's a hard wait, not a "wait for a second exhaustion signal" two-gate confirmation. The two-stage concept (pre-open signal + day-session signal both required) is genuinely new logic. |
| **ATR stop sized 0.5-1.0× daily ATR** | ⚠️ similar | Paste uses ATR(14) × 1.5 on chart TF (`optStopAtrMult` tunable). Concept aligned, but "daily ATR" specifically is a different reference series. Could be tunable as alternative ATR source. |
| **Volume Profile (Daily Session)** as context | ❌ NEW — candidate | See Volume Profile row above — same item. |
| **Better Momentum Indicator** (emini-watch proprietary) | 🚫 EXCLUDED | Closed-source third-party indicator. Cannot import into Pine. The CONCEPT (require pre-open exhaustion + day-session exhaustion confirmation) is captured in the "two-stage exhaustion" candidate above. |
| **emini-watch Rules of Thumb 1-7** (reversal timing, max 2 trend moves, etc.) | 📚 noted | Empirical rules-of-thumb. Useful as context for labeling work and for understanding what the strategy *should* be doing on a typical day. Not directly implementable as logic — they're operator heuristics. |
| **Bollinger Bands** | 🚫 EXCLUDED | Per `feedback_no_bollinger_bands.md` — never a candidate. |

## Genuinely New Candidates Surfaced (5)

These are not in the active plan. They require explicit per-item Architect approval before becoming scope:

1. **CVD divergence detection** — cumulative delta divergence vs price highs/lows. Adds 1 cumulative tracker + divergence comparator. ~20 lines. Useful exhaustion confirmation that's TF-orthogonal.
2. **Pre-11 AM CST reversal time gate** — clock filter on reversal-direction entries. One-line change. Cheap.
3. **Two-stage exhaustion confirmation** — require either two exhaustion signals (separated by N bars) OR a session-window signal (pre-open + day) before reversal entries fire. Strengthens existing exhaustion-diamond logic without changing trade direction. ~30 lines.
4. **Session/daily Volume Profile context** — HVN/LVN identification with value-area boundaries as confluence signal. Significant new surface (request budget + new state machine). Most expensive item in this list.
5. **Key Reversal Bar / Outside Engulfing pattern detector** — adds 2 named pattern detectors to the existing pattern surface. ~10 lines. Could fold into the confirmation-gate Optuna phase's top-6 slate as a 7th and 8th candidate IF Architect approves expansion.

## Items NOT to add (explicit)

- Bollinger Bands (per memory)
- Better Momentum Indicator (closed-source, can't import; concept captured by two-stage exhaustion)
- Any future-candidate listing without explicit Architect per-item approval

## Architect Decision Required

Per the active plan and locked rules, this doc proposes **NO changes to scope.** It's a parking lot for the new reference batch. To elevate any of the 5 candidates into the confirmation-gate phase or a follow-up phase, Architect must explicitly approve per-item.

Open question: do any of the 5 NEW items belong in the confirmation-gate phase (where they'd add to Top-6 and tunable inputs), or do they wait for a separate phase? Recommendation: **wait** — confirmation gate should land first with patterns + MA only. Adding more knobs now bloats the search space and dilutes Optuna's ability to converge.
