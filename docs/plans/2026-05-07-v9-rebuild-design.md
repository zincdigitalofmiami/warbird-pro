# V9 Full Tunable Rebuild — Design Doc (REDRAFT)

**Date drafted:** 2026-05-07
**Last updated:** 2026-05-08
**Status:** DRAFT v2 — supersedes the 2026-05-07 reflection draft and the
2026-05-05 WIP. NOT yet approved, NOT yet committed as authoritative,
NOT yet acted on. Awaiting Kirk approval at the Approval Gate.
**Author:** Claude (under Kirk direction, 2026-05-07 reflection-and-flex
session + 2026-05-08 quant second-opinion synthesis)
**Predecessors:**
- `docs/plans/2026-05-05-v9-full-tunable-rebuild-design.md` (5 pending
  decisions, machine-shutdown lock — superseded)
- 2026-05-07 reflection draft (off-repo, on author's workstation; not
  committed) — 30+ tunables, 4 cards, narrow C1 flex — superseded by
  simplification
  directive 2026-05-07: *"we should only be confirming the 1 of 3 levels
  for entry are hit... when hit, there should be entry logic that looks
  at the three symbols, volume, htf structure, liquidity, MAs"* +
  *"I think we overcomplicate things too fast"*)

**Reason for redraft:** The 2026-05-07 draft preserved hand-coded boolean
gates (`requireXaNqAlignment`, `blockShortsInStrongUp`,
`gateShortsInBullTrend`, etc.) and 30+ Optuna tunables. Kirk's
simplification directive plus a quant second-opinion pass collapsed the
shape: hand-coded gates die, AutoGluon (AG) handles weighting, exit
surface drops to 5 knobs, SL becomes per-trade EV-driven, separate
long/short heads with isotonic calibration, expectancy-weighted decision
rule with transaction costs and a hard SL ceiling.

---

## Why This Exists

The current pipeline has two compounding problems:

1. **Decision-baking in `build_v9_dataset.py`.** 17 Pine settings are
   baked into the CSV at build time (`RSI_OVERBOUGHT`, `RSI_OVERSOLD`,
   `RSI_LENGTH`, `SIGNAL_COOLDOWN_BARS`, `LIQ_SWEEP_LOOKBACK`,
   `USE_LIQUIDITY_SWEEP`, `USE_PATTERN_CONFIRM`, `USE_ML_FILTER`,
   `GATE_SHORTS_IN_BULL_TREND`, `SHORT_GATE_RSI_FLOOR`, `ONE_SHOT_EVENT`,
   `EXEC_ANCHOR_RATIO`, `TRADE_STOP_ATR_MULT`, `HTF_CONF_TOL_PCT`,
   `USE_MA_GATE`, `LENGTH_MA`, `LENGTH_EMA`). All 4 prior Optuna cards
   tuned a thin shell of post-trigger filters around a frozen entry
   decision built from one specific (likely wrong) input combination.

2. **Hand-coded entry filters compounding.** The current Pine
   `longCore`/`shortCore` AND-chains require `entryAnchorLong/Short AND
   longStructureOk AND longPatternOk AND longSweepOk AND maLongOk AND
   mlLongOk AND not shortGate AND requireXaNqAlignment AND ...`. Each
   gate is a binary cliff; regime turns where the *signal is the
   divergence* trip the gates and the trade is vetoed precisely when it
   would have worked.

Live result: bleeding capital. Kirk directive (2026-05-05): *"rebuild so
all this is in the fucking training and tuning. fuck"*. Reflection
directive (2026-05-07): *"I'm hemorrhaging cash and need this done
correctly."*. Simplification directive (2026-05-07): *"we should only be
confirming the 1 of 3 levels for entry are hit... entry logic [should
look] at the three symbols, volume, htf structure, liquidity, MAs"* +
*"I think we overcomplicate things too fast"*.

This redraft is the simplification.

---

## Locked Architecture

V9 becomes a four-layer system:

```
[ Trigger ]  →  [ AG Score ]  →  [ EV Rule ]  →  [ Exit ]

Trigger:    Touched any of {0.500, 0.618, 0.786}? (boolean, frozen)
AG Score:   entry_score, tp2_score (calibrated probabilities, per direction)
EV Rule:    argmax_sl EV(sl) over {5, 7, 10}pt; take if EV > 0
Exit:       fib-ladder TP1/TP2 + BE + trail (Optuna-tuned within EV)
```

### Layer 1 — Trigger (frozen, single boolean)

- **Touch of any of {0.500, 0.618, 0.786} fib levels** in the active
  swing context (the swing context is the live fib-ladder Pine already
  computes — frozen, per Kirk).
- One boolean per direction: `triggerLong = touched_618_long OR
  touched_500_long OR touched_786_long`. Same for shorts.
- KILLED: `entryConfirmMode` (touch_only/reclaim_only/both_required from
  prior D10), `optEntryLevelInput` single-select, the
  `entryAnchorLong/Short` reclaim AND-chain, all `*StructureOk`,
  `*PatternOk`, `*SweepOk`, `*MaOk`, `*MlOk`, `shortGate` boolean gates.

### Layer 2 — AG Score (learned, no Optuna over features)

Two AG models per direction (4 fits total: long entry, long TP, short
entry, short TP):

- `entry_score_long  = P(reach_TP1_first | features, long_trigger_fired)`
- `entry_score_short = P(reach_TP1_first | features, short_trigger_fired)`
- `tp2_score_long    = P(reach_TP2 | reached_TP1, features, long)`
- `tp2_score_short   = P(reach_TP2 | reached_TP1, features, short)`

Each fit follows the locked V9 time-series AG discipline (per
`scripts/ag/train_v9_locked.py`): `presets="good_quality"` (NOT
`best_quality` — `best_quality` enables `dynamic_stacking` which
violates time-series ordering), `num_bag_folds=0` (mandatory for
time-series — AG's internal K-fold uses random splits and would
defeat outer CPCV), `num_stack_levels=0` (required when
`num_bag_folds=0`), `dynamic_stacking=False` explicit. Outer CPCV
folds with purge + embargo (López de Prado) provide the cross-
validation; AG's internal validation uses an embargoed chronological
split per fold. Isotonic calibration on a held-out fold post-fit;
calibrated outputs only flow downstream.

### Layer 3 — Decision Rule (EV-maximization, AG-driven SL)

For each candidate SL ∈ {5, 7, 10} points:

```
E[Reward | sl, tp2_score] = 0.5 × R_TP1
                          + tp2_score × 0.5 × R_TP2
                          + (1 − tp2_score) × 0.5 × R_BE_buffer

EV(sl) = entry_score × E[Reward | sl, tp2_score]
       − (1 − entry_score) × sl
       − E[cost_round_trip]
```

Take trade at `argmax_sl EV(sl)`, only if `max_EV > 0`. Direction-
specific (separate calculation per direction, separate AG models,
separate calibrations).

**Frequency guard rail** (operational, not a primary driver): if EV rule
fires more than ~5/RTH-day or fewer than ~3/RTH-week on OOS, halt and
investigate calibration drift before going live.

**Score floor guard rail** (regime-adaptive): `entry_score ≥ top-25% of
trailing-N-day calibrated entry_scores per direction`. Coarse cutoff
against "model in a bad mood" days; primary driver remains EV > 0.

### Layer 4 — Exit (5 Optuna knobs, fib-ladder semantics preserved)

| Knob | Range / Set | Notes |
|---|---|---|
| TP2 default fib | {1.236, 1.618, 2.000, 2.618} | Categorical; AG TP-prob head can override per-trade |
| `breakevenAfterR` | [0.5, 2.0] | Continuous |
| `trailActivationOffsetR` | [0.0, 1.5] | Continuous; effective trail R = `breakevenAfterR + offset` (sequence guaranteed) |
| `trailAtrMult` | [0.5, 2.0] | Continuous |
| `useBreakeven` / `useTrailingStop` | {true, false} | Booleans; disabled-feature dimensions don't waste TPE search |

**Fixed (not tunable):**
- TP1 = fib 1.000, partial close 50%
- BE buffer = entry ± 1pt (Kirk-locked, covers slip)
- SL set = {5, 7, 10} points (AG-driven via EV-maximization, not
  Optuna-tuned; ceiling 10 enforced by construction per Kirk
  2026-05-08: *"sl needs to be capped at 10pt, I'm not about to go
  deeper on a 5m chart, in fact, i'd prefer a 5pt, but let AG find it"*)

**Sequencing rule:** trailing stop activates only AFTER breakeven snaps
in place. Implemented as `effective_trail_R = breakevenAfterR +
trailActivationOffsetR` with `offsetR ≥ 0`.

---

## Decisions Resolved 2026-05-08

### D1. TP Semantics — Tunable Categorical Scale-Out

**Locked (unchanged from 2026-05-07):**
- TP1 fixed at fib 1.000 ("price returns to where it broke from"),
  partial close 50%
- TP2 categorical ∈ {1.236, 1.618, 2.000, 2.618}
- TP-prob AG head can suggest per-trade TP2 override; Optuna-tuned
  default applies when AG conviction is low

Stays inside the locked exit-model semantic: *"exit model are the
fucking fib extensions on the fib ladder, the fibs are frozen, they
disappear when a trade is taken and the sl/entry/tp levels appear using
the same fucking ladder style which is already built."*

### D2. Aggressor Volume Source — OBSOLETE

**Original Path A from 2026-05-07** (IS = OHLCV-derived BSL/SSL only,
OOS = real aggressor as parity check) is **obsolete**. Kirk confirmed
2026-05-08 that MES Trades data covers the IS window in the project data
folder. New ruling:

- **Tick-rule classify all MES Trades data**, IS (2020-01-01 →
  2024-12-31) and OOS (2025-01-01 → present), at the trade level.
- Aggregate per 5m bucket: `signed_delta_5m`, `cum_delta_session`,
  `bull_vol_5m`, `bear_vol_5m`, `delta_divergence_5m`.
- Real aggressor flow is now an **IS feature**, not OOS-only.
- **Tick-rule sanity gate** (one-time, not a promotion gate):
  `corr(signed_delta_per_bar, bar_return) > 0.30` on a deterministic
  10,000-bar sample. Sampling strategy: contiguous window from
  `2024-07-01 00:00:00 UTC` (one full RTH+ETH calendar half spanning
  ~10K 5m bars), no random subselection — this gives byte-identical
  reproduction across runs and machines. If correlation < 0.30,
  classifier or aggregation has a bug; fix before training. Healthy
  implementations land 0.5+; 0.30 is a defensive floor.
- Parity check from D2-original is no longer needed (real flow on both
  sides; nothing to parity-check against).

**Banned (carried from 2026-05-05):**
- Body/wick volume proxy (`closePos = (close - low) / range`)
- OHLCV-derived "delta" (`ml_net_delta_20`)
- Any "VOLUME (primary)" or "LIQUIDITY (primary)" generic phrasing in
  code, docs, or commits — name the exact data primitive.

### D3. Card 1 Existing Trials — Keep as Labeled Baseline

454 trials in
`scripts/optuna/workspaces/warbird_pro_v9_exit_cpcv/study.db` (399
COMPLETE + 54 PRUNED + 1 cleaned-to-FAIL) are preserved as a
contaminated baseline. Tagged in run manifest as
`baseline_contaminated_baked_csv — DO NOT USE FOR PROMOTION`.

**Enforcement mechanism** (newly specified): tag is written to the
study's `user_attrs` AND included as a column in the run manifest. New
post-rebuild trials use a **versioned workspace path**
(`warbird_pro_v9_exit_cpcv_v2/study.db`) so the contaminated and clean
study DBs cannot be accidentally merged. Promotion automation must
filter on workspace name; legacy path is read-only post-rebuild.

### D4. Trial Budgets — Revised

**Card A (exit tuner): ~300 trials** (down from prior 1000 + 1000 + 1000
+ 500 = 3500 total). With SL removed from the Optuna surface and search
space reduced to 4 continuous knobs + 2 booleans, TPE converges faster.

**Card B (AG fits): no Optuna trial count.** Single AG fit per head ×
direction = 4 fits. AG config locked to `good_quality` +
`num_bag_folds=0` + `num_stack_levels=0` + `dynamic_stacking=False`
per the established V9 time-series discipline (see Layer 2 for
rationale).

**Total compute ~10% of original 3500 trials.**

If Card A convergence looks bad, revisit budget in a separate session.

### D5. Currently-Tuned Filter Params — DROPPED

**Reverses the 2026-05-07 ruling** that kept `requireXaNqAlignment`,
`blockShortsInStrongUp`, `minPivotDistAtr`, `maxBslDistAtrLong`,
`maxSslDistAtrShort`, `minHtfConfTotal`, `gateShortsInBullTrend`,
`shortGateRsiFloor`, `useMaGate`, `usePatternConfirm`, `useExhaustion`,
`rejectWick`, `useLiquiditySweepConfirm`, `htfConfTolPct`,
`exhaustionLevelAtrTol`, `retestContextBars`, `liqLookbackBars`,
`signalCooldownBars` as Optuna-tuned booleans/floats.

**New ruling (Kirk 2026-05-08):** *"Let AG do the work."* Every one of
those becomes an AG **feature**, not a hard gate. The model learns the
weighting from data via feature importance. Hard gates fail at regime
turns (the day cross-asset divergence *is* the signal, the gate blocks
the trade); AG learns the conditional weighting natively.

The underlying Pine computations stay (so the features can be exported);
the boolean gates leave the entry decision.

### D6. Breakeven and Trailing Stop — Re-Admitted with Sequence Rule

**Locked tunable:**
- `useBreakeven` (bool), `breakevenAfterR ∈ [0.5, 2.0]`
- `useTrailingStop` (bool), `trailActivationOffsetR ∈ [0.0, 1.5]`
  (offset from BE point, not absolute), `trailAtrMult ∈ [0.5, 2.0]`
- BE buffer: hardcoded entry ± 1pt (Kirk 2026-05-08)

**Sequencing rule (Kirk 2026-05-08):** *"trail needs to activate after
breakeven snaps in place."* Implemented as
`effective_trail_R = breakevenAfterR + trailActivationOffsetR`. With
`offsetR ≥ 0` enforced at sample time, trail can never activate before
BE. Removes the inconsistent-pairing failure mode (where a strict trail
activation R below the BE R would have been logically broken).

**Implementation discipline:** V9 is an indicator (no auto-execution).
Trail/breakeven logic emits `suggestedStopLevel` as a plot value; alert
system fires when SL should move. NO bracket-order interaction in Pine.
Kirk pulls trigger or moves SL manually based on alert.

**Banned SL anchors (preserved from 2026-05-02 contract):** `-0.236`
and any negative fib extension as a stop family/candidate. May be
carried as `fib_neg_0236_context` for AG-context only.

### D7. Candlestick Patterns — Features Only

**Unchanged from 2026-05-07.** `usePatternConfirm` defaults `false`;
pattern detection code stays in V9; `ml_pattern_*` plots stay exported
as AG features; pattern booleans NOT in any entry condition.

Now consistent with the everything-is-a-feature design (D5).

### D8. MA Types and Lengths — Narrowed Types, Wide Lengths

**Locked tunable in Pine (visual + feature pre-compute layer):**
- `maTypeSlow ∈ {SMA, EMA, HMA}` (NEW Pine input — narrowed from prior
  six-option list)
- `maTypeFast ∈ {SMA, EMA, HMA}` (NEW Pine input)
- `lengthMA` (slow): integer range **8–250** (covers Kirk's live setting
  of 200)
- `lengthEMA` (fast): integer range **3–100** (covers Kirk's live
  setting of 50)

These are Pine inputs Kirk picks visually; AG sees the resulting MA
values + slopes + distance-ATR as features. Not Optuna-tuned in the
exit card — Kirk's chart preference is the source.

### D9. Cross-Asset 15m → 5m TF Bug Fix — In Scope

**Unchanged from 2026-05-07.** V9 Pine lines 230-232 currently use
`request.security(symbol, "15", ...)` for NQ/ZN/DX. Change TF from
`"15"` to `"5"` for all three. Aligns with the 5m timeframe lock for
the active V9 lane.

### D10. Entry Trigger — Simplified to Touch-Any

**Reverses the 2026-05-07 ruling** about `entryConfirmMode ∈
{touch_only, reclaim_only, both_required}`. Simplified per Kirk
directive 2026-05-07: *"we should only be confirming the 1 of 3 levels
for entry are hit, right?"*

**Locked:** Trigger = touch of any of {0.500, 0.618, 0.786} fib levels
in the active swing context. Single boolean per direction. No confirm
mode, no anchor select, no AND-chain on top.

The "should I take this touch?" logic moves entirely to Layer 2 (AG
score) and Layer 3 (EV rule).

### D11. Decision Rule — Expectancy-Weighted EV with AG-Driven SL (NEW)

**Source:** Quant second-opinion pass 2026-05-08, Kirk-confirmed.

**Locked:**

1. **AG `predict_proba` is calibrated via isotonic regression** on a
   held-out validation fold post-fit. Without calibration, `entry_score
   = 0.65` is a ranking score, not a probability — EV math is then
   hallucination. Isotonic mapping is a **versioned artifact**:
   `calibration_{long|short}_{entry|tp2}_v{model_version}_{fit_date}.pkl`.
   Mapping table (raw → calibrated at p1/p5/p10/.../p95/p99 deciles)
   logged to run manifest for human auditability.

2. **Separate long/short heads + calibrations.** ES has structural long
   bias and asymmetric volatility ("elevator down, stairs up"). One
   threshold biases direction. Two AG models per layer (entry, TP), per
   direction = 4 fits total.

3. **Decision rule** (per direction, evaluated each bar where trigger
   fires):
   ```
   For each sl ∈ {5, 7, 10}:
     E[Reward | sl, tp2_score] = 0.5 × R_TP1
                                + tp2_score × 0.5 × R_TP2
                                + (1 − tp2_score) × 0.5 × R_BE_buffer
     EV(sl) = entry_score × E[Reward | sl, tp2_score]
            − (1 − entry_score) × sl
            − E[cost_round_trip]
   chosen_sl = argmax_sl EV(sl)
   take_trade = (max_EV > 0) AND (entry_score ≥ p75_trailing)
   ```

4. **Cost in EV** (Kirk-floored from CLAUDE.md commission/slip rules):
   `E[cost_round_trip] = 3 × $1.00 commission + 3 × $1.25 slippage =
   $6.75/contract ≈ 1.35 points on MES`. Reflects 1 entry + 2 exits
   (TP1 partial + TP2/trail/stop). Cost subtracts from total EV
   regardless of outcome (winners and losers both pay).

5. **SL ceiling** (Kirk 2026-05-08): hard cap 10pt, candidate set
   discrete {5, 7, 10}. AG implicitly "finds" the SL via EV
   maximization — high-conviction setups land 5pt, marginal setups
   land 10pt or get rejected.

6. **Score floor guard** (regime-adaptive): `entry_score_calibrated ≥
   top-25% percentile of the trailing N-day per-direction score
   distribution`. Acts as coarse cutoff against calibration drift.
   Static τ rejected (drifts IS→OOS); ATR-regime-conditional τ rejected
   (premature, features already encode regime).

7. **Frequency sanity** (operational guard): expected ~3–5 per RTH-day.
   If outside that band on OOS, investigate before live.

### D12. Authority Amendments — AGENTS.md + MASTER_PLAN.md (NEW)

**Required Phase 0 edits, by Kirk:**

- `AGENTS.md` lines 162, 195: cross-asset feature ban → amend to
  *"Cross-asset features (NQ, ZN, DX 5m closes, MA distances, signed
  delta correlations) are admissible AG inputs. FRED, macro, news,
  options, daily-ingestion joins remain banned."*
- `MASTER_PLAN.md` lines 48–50, 90–103, 198–204: same amendment scope.
  Specifically, prohibited modeling question line 203 ("Which NQ or
  cross-asset feature should gate V9 entries?") is reversed to allow
  cross-asset as AG features (not as hard gates — the gate concept
  itself is dropped per D5).

Kirk authorized 2026-05-07: *"Forget the 'ban', this is a draft by me
and will update the ban list."*

The "no external feature stacking" spirit is preserved by what stays
banned: FRED, macro, news, options, supabase-runtime joins, mislabeled
Databento/TradingView artifacts.

---

## Tunable Surface — Final List

### Frozen (no change)

- Fib core: `autoTuneZZ`, `fibDeviationManual`, `fibDepthManual`,
  `fibThresholdFloorPct`, `fibConfluenceTolPct`, `minFibRangeAtr`,
  `fibHysteresisPct`, `useConfluenceAnchorSpan`
- Visual: all `*ColorInput` / `*WidthInput` / `*LabelSizeInput`,
  `tablePositionInput`, `extendLevelsRight`, `targetLookbackBars`,
  `fibLineStyleInput`, `zoneFillTransparencyInput`,
  `fibLabelOffsetBarsInput`, etc.
- One-shot: `oneShotEvent`
- Trigger: `triggerLong/Short = touched_618 OR touched_500 OR
  touched_786` (deterministic, frozen Pine logic)

### Pine inputs (Kirk-picked, visual; not Optuna-tuned)

- `maTypeSlow` ∈ {SMA, EMA, HMA}, `maTypeFast` ∈ {SMA, EMA, HMA}
- `lengthMA` (slow) int 8–250, `lengthEMA` (fast) int 3–100

These go into Pine as inputs Kirk sets per chart. The resulting MA
values + slope + distance-ATR are exported as AG features.

### AG features (no tuning, learned weighting)

The full feature catalog goes into AG entry + TP heads. Not exhaustive,
but representative:

- **Trigger context:** `triggered_at_fib` (categorical 0.500/0.618/0.786),
  `swing_high_age_bars`, `swing_low_age_bars`, `swing_range_atr`
- **Cross-asset:** `ml_xa_nq_code`, `ml_xa_zn_code`, `ml_xa_dx_code`
  (already exported lines 821-823), plus `nq_close_distance_atr`,
  `zn_close_distance_atr`, `dx_close_distance_atr`, slope/momentum
  deltas at 5m
- **Liquidity:** `ml_swept_bsl/ssl`, `ml_reclaimed_bsl/ssl`,
  `ml_bsl_dist_atr`, `ml_ssl_dist_atr`, `ml_pivot_dist_atr`
- **Real aggressor flow** (from tick-rule on MES Trades, IS+OOS):
  `signed_delta_5m`, `cum_delta_session`, `bull_vol_5m`, `bear_vol_5m`,
  `delta_divergence_5m`
- **MAs:** slow MA value, fast MA value, slow-fast distance ATR, slope
  angles, MA stack alignment (categorical bull/bear/none)
- **RSI:** raw RSI, RSI delta, RSI vs OB/OS context
- **ADX:** `ml_adx_value`, `ml_adx_plus_di`, `ml_adx_minus_di` (NEW —
  Pine export to be added, see Phase 3)
- **ATR:** raw ATR, ATR z-score over rolling window
- **HTF S/R:** distance to 60m + Daily + Monthly pivots in ATR units
- **Patterns:** `ml_pattern_*` (already exported)

### Optuna-tuned (Card A exit tuner, 5 knobs)

- TP2 default fib ∈ {1.236, 1.618, 2.000, 2.618}
- `useBreakeven` ∈ {true, false}
- `breakevenAfterR` ∈ [0.5, 2.0] continuous
- `useTrailingStop` ∈ {true, false}
- `trailActivationOffsetR` ∈ [0.0, 1.5] continuous
- `trailAtrMult` ∈ [0.5, 2.0] continuous

Disabled-feature dimensions (e.g., `breakevenAfterR` while
`useBreakeven=False`) get conditional sampling so TPE doesn't waste
search.

### Per-trade AG-driven (no fixed knob)

- SL ∈ {5, 7, 10} points (chosen by EV-maximization at decision time)
- Per-trade TP2 fib (AG TP-prob head can override Optuna default if
  conviction warrants — implementation TBD in Phase 4)

---

## Generic Terminology BAN (carried forward)

> "YOU ARE BANNED FROM USING GENERIC BULLSHIT: VOLUME (primary) /
> LIQUIDITY (primary — sweep/lookback/pool). YOU WILL FIND AND USE
> REALLLLLLLL FUCKING LIQUIDITY AND BULL/BEAR - BUYER/SELLER VOLUME"

**Banned phrases:** "VOLUME (primary)", "LIQUIDITY (primary — sweep/
lookback/pool)", any handwave that doesn't name the exact data
primitive.

**Real LIQUIDITY = BSL/SSL pivots (OHLCV-derived):**
- Buy-side liquidity (BSL) = pivot highs where stops cluster above
- Sell-side liquidity (SSL) = pivot lows where stops cluster below
- Real sweep = price wicked through pivot then closed back through
- Real reclaim = subsequent close back inside the swept range
- Pine `ml_*` exports: `ml_swept_bsl`, `ml_swept_ssl`,
  `ml_reclaimed_bsl`, `ml_reclaimed_ssl`, `ml_bsl_dist_atr`,
  `ml_ssl_dist_atr`, `ml_pivot_dist_atr`

**Real BULL/BEAR VOLUME = aggressor-classified via tick rule on MES
Trades data (IS + OOS both real):**
- Tick rule: trade above prior trade price = buyer-initiated; below =
  seller-initiated; at-mid trades inherit prior tick direction
- Buy volume = sum of buyer-initiated trade size per 5m bucket
- Sell volume = sum of seller-initiated trade size per 5m bucket
- Signed delta = buy_vol − sell_vol per bar
- Cumulative delta = running sum of signed delta per session
- **NEVER** body/wick proxy. **NEVER** close-vs-open volume split.
  **NEVER** `ml_net_delta_20` derived from OHLCV.

---

## Architecture Decision (carried forward, refined)

**Full Python re-trigger of Pine entry/exit logic.**

- New module: `scripts/optuna/v9_trigger.py` re-implements the trigger
  ("touched any of 3 fib levels?") + exit-bar bookkeeping (TP1, TP2,
  BE, trail) from raw OHLCV + raw fib levels + raw HTF pivots + raw
  BSL/SSL pivots + raw aggressor volume (tick-rule, IS+OOS) + ADX
  components + RSI components.
- `build_v9_dataset.py` strips ALL decision-baking; emits **raw inputs
  only**.
- Card A (Optuna exit tuner) and Card B (AG entry + TP heads) both
  consume the raw-inputs dataset.
- Pine emit: ADD `maTypeSlow`/`maTypeFast` inputs + `select_ma()` switch
  (D8). ADD ADX components export (D11 features). ADD Daily + Monthly
  HTF pivot reads. FIX cross-asset request.security TF "15" → "5" (D9).
  REMOVE all boolean gates from `longCore`/`shortCore` AND-chain.
- Pine source-of-truth parity: snapshot test on **≥10,000 bars**
  comparing Pine trigger output (current CSV) vs Python re-trigger
  output (same params). Tolerance: trigger boolean must match
  bar-by-bar **100%**; `ml_*` feature columns must match within
  **1e-6 absolute** on non-NaN, NaN masks identical. Hard fail if
  parity broken.

### Data Pipeline & Leakage Discipline

The trigger event (fib touch) is intra-bar. To prevent subtle leakage,
features are **shifted by 1 bar at training and inference time**:

```
features_at_decision_time_t = f( OHLCV[t-k : t-1], aggregated to bar t-1 close )
trigger_at_t                = touched_fib_level_during_bar_t
label_y_at_t                = trade_taken_at_t+1_open hit TP1 before SL within M bars
```

This costs ~5 minutes of feature staleness (one bar at 5m). Acceptable
trade-off for clean leakage hygiene.

**Tick-rule signed delta**: aggregate per 5m bucket using only trades
with `ts_event ∈ [bar_open_t, bar_close_t]`. With the 1-bar shift, the
model sees bar `t-1`'s **completed** signed delta when scoring trigger
fired at bar `t`.

**CPCV** (Combinatorial Purged Cross-Validation, López de Prado):
- Train/validation/test folds with embargo of E bars (default E=12 = 1
  hour at 5m) preventing serial-correlation leakage
- Purge: drop training samples whose label horizon (M bars forward)
  overlaps the test fold start
- Calibration fold: held out from both train and test, used only for
  isotonic regression fit, never seen during AG training

**Pine-side discipline** (already in current V9):
- All `request.security` calls use `lookahead=barmerge.lookahead_off`
  (verified at lines 230-232, 269)
- No `lookahead=bar_index` or `lookahead=barmerge.lookahead_on`
  anywhere

**Tick-rule sanity gate** (one-time, not a promotion gate):
- `corr(signed_delta_per_bar, bar_return) > 0.30` on a deterministic
  10,000-bar contiguous sample starting at `2024-07-01 00:00:00 UTC`
  (no random subselection; reproducible across runs/machines)
- If fails: classifier or aggregation has a bug, fix before training
- Healthy implementations land 0.5+; 0.30 is a defensive floor

---

## Pine V9 Edits — Phase 3 Scope

All edits trip the full Pine Verification Pipeline per CLAUDE.md
(in order):

1. pine-facade compile check
2. `./scripts/guards/pine-lint.sh <file>`
3. `./scripts/guards/check-fib-scanner-guardrails.sh`
4. `./scripts/guards/check-contamination.sh`
5. `./scripts/guards/check-no-tv-force.sh`
6. `npm run build`
7. `./scripts/guards/check-indicator-strategy-parity.sh` — only if a
   strategy harness is explicitly reopened and coupled to Warbird Pro
   (skipped here; no strategy harness in active scope)

### Adds

- `maTypeSlow` / `maTypeFast` inputs ∈ {SMA, EMA, HMA} + `select_ma()`
  switch helper (D8)
- `lengthMA` 8–250, `lengthEMA` 3–100 (D8)
- ADX components export plots: `ml_adx_value`, `ml_adx_plus_di`,
  `ml_adx_minus_di` (`display=display.none`, editable=false)
- HTF Daily + Monthly pivot reads via 2 new `request.security(tickerid,
  "D"/"M", ...)` calls; export `ml_htf_d_high_dist_atr`,
  `ml_htf_d_low_dist_atr`, `ml_htf_m_high_dist_atr`,
  `ml_htf_m_low_dist_atr` plots

### Fixes

- Cross-asset request.security TF `"15"` → `"5"` for all three calls at
  lines 230-232 (D9)

### Simplifies (deletes)

- All boolean gates in `longCore`/`shortCore` AND-chains:
  `entryAnchorLong/Short`, `longPatternOk`, `longSweepOk`, `maLongOk`,
  `mlLongOk`, `shortGate`, `requireXaNqAlignment`,
  `blockShortsInStrongUp`, `gateShortsInBullTrend`, etc.
- New `longCore` = `confirmed and isValid and triggerLong`
- New `shortCore` = `confirmed and isValid and triggerShort`
- Where `triggerLong = entryZoneTouched and (touched_618_long OR
  touched_500_long OR touched_786_long)`
- Pine-side AG score evaluation is OUT OF SCOPE — AG runs in Python;
  Pine just exports raw features and renders the fib ladder. Live
  alerts come from a separate alert-routing layer reading AG output.

### Plot Budget

Current count: 53 `plot()` + 2 `alertcondition()` + 5
`request.security()` + 19 `line.new()` + 1 `box.new()` + 1
`table.new()`.

Phase 3 adds:
- 3 ADX plots
- 4 HTF S/R distance plots (D-high, D-low, M-high, M-low)
- 2 new request.security (Daily + Monthly)

Projected: 60 `plot()`, 7 `request.security()`. Both under TradingView
v5/v6 caps (~64 plots, 40 security calls), but tight on plots.

**Mitigation if budget tight:** consolidate via `display=display.none`
on diagnostic plots, or merge correlated features into composite
exports. Plot-budget recount is a hard gate before Phase 3 commit.

CLAUDE.md budget snapshot (line 70–72) currently states "17 plot()" —
**this is stale** and should be refreshed when Phase 3 lands. Audit
artifact: snapshot diff before/after Phase 3.

---

## Cards & Trial Budget (Revised)

**Card A — Exit Tuner (Optuna):**
- 5 knobs (TP2 default, useBE, breakevenAfterR, useTrail,
  trailActivationOffsetR, trailAtrMult)
- ~300 trials, TPE sampler, CPCV folds with purge + embargo
- Objective: expectancy per trade (per CLAUDE.md `target_hit_rate` 0.14
  weight aligns with Kirk's exit preferences); secondary metrics
  reported but not optimized (PF, Sharpe-per-trade, Calmar)
- Bar Magnifier: search at bar resolution (fast), top-K champions
  revalidate intrabar (accuracy), promotion gate uses intrabar metrics
- Top-K = 10 champions revalidated

**Card B — AG Entry + TP-Prob Heads:**
- 4 fits total: long-entry, short-entry, long-tp2, short-tp2
- AG config (locked per `scripts/ag/train_v9_locked.py` discipline):
  `presets="good_quality"`, `num_bag_folds=0`, `num_stack_levels=0`,
  `dynamic_stacking=False`. NOT `best_quality` (time-series
  contamination via dynamic stacking).
- Outer CPCV folds with purge + embargo (same fold structure as Card A)
- Calibration: isotonic regression on held-out validation fold per fit;
  versioned artifact saved
- No Optuna over feature weights — feature importance is the output

**Total compute** ~10% of original 4-card 3500-trial design.

---

## Implementation Phases

Each phase ends with verification (per CLAUDE.md
`superpowers:verification-before-completion`) + Kirk approval gate. No
phase skips ahead.

**Phase 0 — Approve this redraft.**
Kirk reads, marks up, approves. Doc lands at
`docs/plans/2026-05-07-v9-rebuild-design.md` as authoritative.
AGENTS.md + MASTER_PLAN.md amendments per D12 (Kirk to edit). 2026-05-05
predecessor doc gets a SUPERSEDED header. 2026-05-07 reflection draft
discarded.

**Phase 1 — `build_v9_dataset.py` raw-inputs rewrite + tick-rule
pipeline.**
- Strip all decision-baking. Emit OHLCV + fib snapshots + HTF pivots
  (60m + D + M) + BSL/SSL pivots + RSI components + ADX components +
  cross-asset codes (5m).
- Add tick-rule classification stage on MES Trades data: per-trade
  classify, per-5m-bucket aggregate signed delta + cum delta + bull/
  bear vol.
- 1-bar feature shift discipline.
- Verify row count matches existing dataset; verify hashes recorded in
  manifest; verify live Pine settings (dev=3.0, depth=10, floor=0.15)
  applied (per CLAUDE.md contamination history).
- Tick-rule sanity gate: correlation check on the deterministic
  10,000-bar window from 2024-07-01 (per Data Pipeline section).

**Phase 2 — `scripts/optuna/v9_trigger.py` Python re-trigger module.**
- Implement the trigger ("touched any of 3 fib levels?") + exit
  bookkeeping from raw inputs.
- Bar-by-bar parity test against current Pine V9 output on ≥10,000
  bars. Tolerance: trigger boolean 100% match; `ml_*` features 1e-6 abs
  on non-NaN, NaN masks identical.
- Hard fail if parity broken.

**Phase 3 — Pine V9 edits (D8, D9, ADX, HTF D+M, AND-chain
simplification).**
- Full Pine Verification Pipeline per CLAUDE.md, in order:
  pine-facade compile, `pine-lint.sh`,
  `check-fib-scanner-guardrails.sh`, `check-contamination.sh`,
  `check-no-tv-force.sh`, `npm run build`, plus plot-budget recount.
- `check-indicator-strategy-parity.sh` skipped (no strategy harness in
  active scope).

**Phase 4 — Card A (Optuna exit tuner).**
- Use NEW workspace `warbird_pro_v9_exit_cpcv_v2/` (legacy 454 trials
  preserved at `warbird_pro_v9_exit_cpcv/` per D3, untouched).
- 300 Optuna trials, CPCV.
- Bar Magnifier intrabar revalidation on top-10 champions.

**Phase 5 — Card B (AG entry + TP-prob heads).**
- 4 AG fits (2 directions × 2 heads each).
- Isotonic calibration per fit; versioned artifacts.
- Calibration mapping table logged to run manifest.

**Phase 6 — OOS validation + EV-rule integration.**
- Run full pipeline on 2025+ OOS data: trigger fires → AG scores
  computed → EV rule evaluates → trade taken (sim) or rejected.
- Frequency check (~3–5 RTH-day).
- Score floor guard verification (top-25% trailing percentile per
  direction).
- Promotion gate: OOS PF ≥ 1.10, expectancy > 0 net of cost, top-25%
  guard fires reasonable trade count, calibration mapping stable.

**Phase 7 — Promotion (manual).**
Kirk approval. Pine input defaults updated for `maTypeSlow/Fast`,
`lengthMA/EMA`. Card A champion exit knobs set as Pine defaults.
AG model artifacts + calibration artifacts versioned and pinned.
**No live deployment until paper-trade validation completes.** Live
alert routing layer (separate from V9 indicator) reads AG outputs and
emits alerts per the EV rule.

---

## Hard Rules

### Carried Forward (Verbatim from 2026-05-05 / 2026-05-07)

- No "VOLUME (primary)" or "LIQUIDITY (primary)" generic phrasing —
  name the exact primitive.
- No body/wick volume proxy. No OHLCV-derived "delta". Real aggressor
  only.
- No baked decisions in `build_v9_dataset.py`. Raw inputs only.
- Fib core, viz inputs, one-shot, `targetLookbackBars`,
  `extendLevelsRight`, `useConfluenceAnchorSpan` all stay frozen.
- Fib-ladder exit semantic protected: TP and SL appear on the same
  ladder; no time-stop knobs in the core exit surface; no vPOC /
  unfilled-gap TP mechanism (these can be AG features for the TP-prob
  head, but never replace fib TP).
- Banned SL anchor: `-0.236` and any negative fib extension as a stop
  family/candidate.

### New 2026-05-08

- **No live trading on the current Pine V9 build during the rebuild.**
  Sim/paper only. Live capital stays out until Phase 7 promotion + paper
  validation. Estimated rebuild duration: ≥ 4 weeks (Phase 1+2 ≈ 1
  week, Phase 3 ≈ 3 days, Phase 4 ≈ 1 week, Phase 5 ≈ 4 days, Phase 6 ≈
  1 week, Phase 7 ≈ 1 week paper). Kirk plans capital around this
  timeline.
- **Cross-asset is feature input, never a hard gate.** AG sees NQ/ZN/DX
  signals; gating is implicit via learned weighting. The
  `requireXaNqAlignment` boolean is dead.
- **Aggressor data is IS + OOS, not OOS-only.** Tick-rule classified
  from MES Trades data. Body/wick proxies stay banned.
- **Isotonic calibration mandatory.** No raw `predict_proba` flows into
  the EV rule. Calibration artifacts are versioned and audited.
- **Long/short heads are independent.** Separate AG fits, separate
  calibrations, separate score floor guards, separate EV evaluations.
- **1-bar feature shift mandatory.** Belt-and-suspenders against
  intra-bar timing leakage at the trigger event.
- **CPCV with purge + embargo mandatory.** López de Prado standard.
- **SL hard cap 10pt.** Candidate set discrete {5, 7, 10}. No
  continuous SL search; AG implicitly picks via EV-max.
- **BE buffer hardcoded +1pt.** Not tunable; covers slip per Kirk
  2026-05-08.
- **Trail activates only after BE snaps.** Sequencing enforced via
  offset sampling (`trailActivationOffsetR ≥ 0`).

---

## Open Items (not blocking design approval, flagged for follow-ups)

1. **Live alert routing layer.** Outside V9 indicator scope. Needs a
   separate component that consumes AG model outputs (or a serving
   endpoint) and routes alerts per the EV rule. Spec deferred to
   post-Phase 7.

2. **Cadence for retraining AG heads + recalibrating.** Quarterly?
   Trigger-based on OOS PF degradation or calibration drift signal? Pick
   in a separate session post-Phase 7.

3. **Per-SL retraining if {5, 7, 10} approximation degrades.** The
   current design trains entry_score with a fixed-reference SL labeling
   (median candidate ≈ 7pt) and applies the same calibrated score across
   all 3 SL candidates at decision time. If OOS PF shows
   SL-conditional degradation, revisit by training one entry head per
   SL bucket. Out of scope for initial rebuild.

4. **Tick-rule classification quality on illiquid hours.** Overnight
   ETH session has thinner book; tick rule can mis-classify at-mid
   trades more often. Phase 1 should include a per-session-window
   sanity check on classification statistics.

5. **`cross_asset_1h.parquet`** in `data/` directory (predates
   simplifications). Out of scope; deferred to post-champion.

6. **ADX defaults — Kirk hasn't specified preferred ADX
   length / smoothing.** Default to industry-standard 14/14, allow Pine
   inputs.

7. **Phase 4+ feature loop candidates** (post-champion, not in
   rebuild):
   - 1m signed delta in the `[touch_ts − 60s, touch_ts + 60s]` window
     (captures the "reclaim" intuition as data, not as Pine logic)
   - vPOC / unfilled-gap distances + `dist_to_prior_session_high_low_atr`
     (captures volume-node pull as TP-prob features, doesn't replace
     fib TP)
   - Footprint imbalance ratios per 5m bar (richer than aggregated
     signed delta)
   - Cross-asset signed-delta correlations (NQ/ES order-flow alignment)
   - Time-stop comparison config (champion-with vs champion-without on
     OOS, decided by Calmar improvement, not bolted into core)

8. **2026-05-05 predecessor doc** at
   `docs/plans/2026-05-05-v9-full-tunable-rebuild-design.md` needs a
   SUPERSEDED header pointing to this redraft. Phase 0 cleanup task.

---

## Approval Gate

**This is a draft, not yet authoritative.** Posting on branch
`claude/review-v9-design-doc-in0Qp` for Kirk review.

Required Kirk inputs to advance:

1. **Approve / mark up / reject** this redraft as a whole.
2. **Confirm Phase 0 → 1 transition** is the right next move (Phase 0
   is just doc + amendment edits; Phase 1 is the first code work on
   `build_v9_dataset.py` + tick-rule pipeline).
3. **Confirm "no live trading during rebuild" rule** is acceptable
   given the ≥ 4-week estimate.
4. **Confirm AGENTS.md + MASTER_PLAN.md amendments per D12** are yours
   to edit, not mine.
5. **Pick ADX default lengths** (or accept 14/14).

Once approved, this doc becomes authoritative; AGENTS.md +
MASTER_PLAN.md get amended; 2026-05-05 predecessor gets a SUPERSEDED
header; Phase 1 implementation planning begins.
