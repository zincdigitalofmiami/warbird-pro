# WARBIRD MODEL SPEC — v3

**Date:** 2026-03-28
**Status:** Reference-Only, aligned to the active plan
**Governing source:** `docs/plans/2026-03-20-ag-teaches-pine-architecture.md`

This document is a subordinate reference for the model contract. It must not override the active plan. If this file and the active plan ever disagree, the active plan wins immediately.

---

## 1. Governing Contract

1. The canonical trade object is the **MES 15m fib setup**.
2. The canonical key is the MES 15m **bar-close timestamp** in `America/Chicago`.
3. Pine is the canonical live signal surface.
4. The Next.js dashboard is the richer mirrored operator surface using the same MES 15m fib contract; it is not a separate decision engine and must not recompute fib geometry locally.
5. AutoGluon is offline only. It trains, calibrates, and emits a Pine-ready packet.
6. The adaptive fib engine snapshot is the canonical base object. The model does **not** invent raw entries from scratch. The Pine fib engine creates the candidate setup first.
7. The model output is MES 15m setup-outcome state: TP1 probability, TP2 probability, reversal risk, and bounded stop-family selection. It is **not** a predicted-price forecast surface.
8. News is not a separate setup engine. It is part of the event-response block that can suppress, delay, confirm, or reclassify a valid 15m fib setup.
9. `news_signals` is a derived `BULLISH` / `BEARISH` market-impact surface. It is not a `LONG` / `SHORT` trade-direction table.
10. News may influence the model only when paired with contemporaneous price action, session timing, volatility state, and cross-asset reaction.
11. AG and offline training must consume point-in-time fib snapshots keyed to the MES 15m bar close, not repaint-prone live chart reads.
12. The retained core historical window for training/support data starts at `2024-01-01T00:00:00Z`. Pre-2024 core rows are out of scope and must not be reintroduced into the canonical dataset.
13. The fib engine must preserve lookback/confluence intelligence; a simple zigzag-only anchor path is insufficient for Warbird.
14. Pivot distance and pivot-state are critical trigger/reversal inputs, but not the sole final decision maker.
15. Intermarket trigger quality must respect each symbol's correlative path and aligned 15m / 1H / 4H state.
16. Overlapping MA / volume / trend features across base logic and admitted harnesses must be de-duplicated by feature family.
17. The minimal Pine export surface for training capture is fib lines/state, pivot state/distance, and admitted indicator/harness outputs from the canonical indicator surface.
18. The canonical flow is `fib_engine_snapshot -> candidate -> outcome -> decision -> signal`.
19. Decision vocabulary is locked to `TAKE_TRADE`, `WAIT`, and `PASS`. Those decision codes are distinct from realized outcome labels.
20. TradingView carries execution-facing visuals, alerts, and the exhaustion precursor diamond. Operator tables, mini charts, and dense diagnostics belong on the dashboard.
21. Cloud core support data remains `2024-01-01T00:00:00Z` forward. By explicit user direction, local offline training research may use up to five years of comparable electronic futures data, but that does not reopen pre-2024 cloud core retention.
22. The operator-approved fib visual spec is a contract. Colors, line widths, line styles, and visible level-label presentation must be reproduced exactly across Pine and dashboard renderers unless explicitly reapproved.

---

## 2. What The Model Is

The model evaluates the quality of a **candidate 15m fib setup** that Pine has already identified.

It does **not** forecast a future MES price level or produce a standalone `1H` price prediction.

For each candidate setup, the model estimates:

- `tp1_before_sl`
- `tp2_before_sl`
- `sl_before_tp1`
- expected `mae_pts`
- expected `mfe_pts`
- reversal risk

The model also selects from a **bounded stop family**. It does not emit an unconstrained stop price.

The model does **not** define the schema. The outcome contract defines the schema; the model stack is chosen to answer that contract.

### 2.1 System Roles

Warbird is split into three separate engines:

1. **Generator**
   - Pine and admitted exact-copy harnesses define the candidate entry object
2. **Selector**
   - offline models score whether a frozen candidate is worth taking
3. **Diagnostician**
   - local research explains why trades won/lost and what should change in features, settings, or entry definition

The same model must not be treated as all three at once.

---

## 3. Fib Engine Snapshot And Candidate Definition

Every training row and live decision must trace back to a frozen MES 15m fib engine snapshot taken at bar close.

The snapshot must carry the resolved adaptive engine state, including the chosen anchor result plus the adaptive decisions that produced it. At minimum, the snapshot family must preserve:

- anchor high / low and anchor timestamps
- direction state and reversal mode
- resolved left / right pivot lookback values
- resolved anchor lookback / spacing policy
- target-eligibility state
- fib / pivot / zone interaction state
- exhaustion precursor state
- engine version and packet version

The exact table/enum contract for these fields is the next schema checkpoint in the active plan.

A setup candidate exists only when all of the following are true:

1. A valid 15m fib engine snapshot exists with a non-degenerate range.
2. A structural leg direction exists and is not midpoint-flip logic.
3. Price touches or crosses one of the tracked retracement levels on the 15m bar.
4. The candidate still has a `20pt+` path to TP1.
5. The live Pine context can compute all required Tier 1 states without violating request limits or lookahead rules.

The setup engine must expose, at minimum:

- direction
- fib level touched
- setup archetype
- stop-family candidate
- confidence score
- event-response state
- exhaustion precursor state
- EMA context (distance + direction)
- decision-support state for `TAKE_TRADE` / `WAIT` / `PASS`
- entry trigger state plus TP hit events

Target viability remains a required internal gate in Pine trigger logic, but it is not a required exported `ml_*` field.

The live indicator trigger predicate may only fire when the shared setup archetype is direction-aligned:

- `1` = accept continuation
- `2` = zone rejection
- `3` = pivot continuation
- `5` = reentry after TP1

Setup archetype `4` is reversal context only. It must not authorize a same-direction continuation entry.

The candidate setup must come from a snapshot-stable fib state that would have existed at that bar close. Historical anchors may not be retro-rewritten for training.

Each candidate must later receive:

- a realized outcome label
- MAE / MFE measurements
- a decision code (`TAKE_TRADE` / `WAIT` / `PASS`)

The model learns from the candidate/outcome truth. The policy layer maps those model outputs into the decision code.

### 3.1 Locked Truth Semantics

These semantics are now binding for the next schema rewrite:

- `warbird_decision_code`
  - `TAKE_TRADE`
  - `WAIT`
  - `PASS`
- realized economic truth must distinguish:
  - TP2 reached before stop
  - TP1 reached before stop while TP2 is not yet realized
  - stop before TP1
  - stop after TP1 but before TP2
  - reversal when the locked reversal rule is satisfied
- unresolved rows at the edge of observation are censored rather than labeled as economic failures
- `EXPIRED` and `NO_REACTION` are not canonical economic outcome labels for model truth
- legacy `hit_*_first` / `prob_hit_*` names in `scripts/warbird/*` are deletion-only local-script debt and must not appear in shared TypeScript types, active APIs, Admin surfaces, packet payloads, or new schema work
- signal lifecycle and UI state are separate from economic truth and may use different vocabulary

Existing `GO` / `NO_GO` vocabulary is legacy and must not drive the next schema.

### 3.2 Locked Canonical Table Families

The canonical operational base remains:

1. `warbird_fib_engine_snapshots_15m`
   - one row per `symbol_code + timeframe + bar_close_ts + fib_engine_version`
   - stores the frozen adaptive fib engine state that existed at the MES 15m bar close
2. `warbird_fib_candidates_15m`
   - one row per tradable candidate derived from a snapshot
   - carries candidate geometry, deterministic Pine score, packet-linked model outputs, and the policy decision code
3. `warbird_candidate_outcomes_15m`
   - one row per candidate, regardless of whether the candidate was published as a signal
   - stores realized path truth, event timestamps, excursion measurements, and censoring metadata
4. `warbird_signals_15m`
   - one row per published signal where `decision_code = TAKE_TRADE`
5. `warbird_signal_events`
   - lifecycle events for published signals only
6. `warbird_packets`
   - AG scoring/model packet registry
7. `warbird_packet_activations`
   - immutable activation and rollback log for packet promotion
8. `warbird_training_runs`
   - published run registry for packet lineage and Admin-page metrics
9. `warbird_training_run_metrics`
   - full training/evaluation metric rows for Admin and model review
10. `warbird_packet_metrics`
   - structured packet KPIs rendered on the Admin page
11. `warbird_packet_feature_importance`
   - published top drivers for the active packet
12. `warbird_packet_setting_hypotheses`
   - structured indicator / entry-definition suggestions for review
13. `warbird_packet_recommendations`
   - structured AI-generated Admin guidance, rendered in UI rather than stored as Markdown

Draft status:

1. `supabase/migrations/20260330000037_canonical_warbird_tables.sql`
2. `supabase/migrations/20260330000038_canonical_warbird_compat_views.sql`

These drafts are now reconciled against the locked 2026-03-28 truth semantics and validated in a disposable Postgres 17 instance, but remain draft/unapplied assets until remote ledger drift is resolved and the canonical writer/API cutover is approved.

Raw research explainability remains local-only:

- `warbird_shap_results`
- `warbird_shap_indicator_settings`

The dashboard/Admin page may read only the distilled cloud publish-up surfaces above, not raw SHAP matrices or Markdown report blobs.

### 3.3 Non-Canonical Surfaces

The following tables exist and may receive writes from legacy bridge code, but they are **not** the canonical AG training truth and must not drive new architecture:

- `warbird_triggers_15m`
- `warbird_conviction`
- `warbird_risk`
- `warbird_setups`
- `warbird_setup_events`
- `measured_moves`
- `warbird_daily_bias`
- `warbird_structure_4h`
- `warbird_forecasts_1h`

These will be retired once the canonical tables above have active writers and all dashboard/API consumers are migrated.

Dashboard/Admin compatibility surfaces such as `warbird_active_signals_v`, `warbird_admin_candidate_rows_v`, `warbird_active_training_run_metrics_v`, `warbird_active_packet_metrics_v`, `warbird_active_packet_feature_importance_v`, `warbird_active_packet_setting_hypotheses_v`, and `warbird_active_packet_recommendations_v` should be derived views over these canonical and publish-up tables, not independent writer-owned base tables.

The following local-only families are research surfaces, not canonical cloud schema:

- `warbird_snapshot_pine_features`
- `warbird_candidate_macro_context`
- `warbird_candidate_microstructure`
- stop-out attribution tables
- feature ablation tables
- entry-definition experiment tables
- SHAP and report artifacts

---

## 4. Target Labels

Each training row is keyed to one MES 15m bar-close setup event and must produce these labels:

| Label | Type | Meaning |
|------|------|---------|
| `tp1_before_sl` | Binary | TP1 reached before stop |
| `tp2_before_sl` | Binary | TP2 reached before stop |
| `sl_before_tp1` | Binary | stop hit before TP1 |
| `is_censored` | Binary | path unresolved at the edge of observation |
| `mae_pts` | Continuous | max adverse excursion in points |
| `mfe_pts` | Continuous | max favorable excursion in points |

Legacy note:

- the old local-only `hit_sl_first`, `hit_pt1_first`, and `hit_pt2_after_pt1` names are scheduled for deletion during the AG workbench rebuild
- no fallback aliasing of those names is allowed in active shared types, API responses, packets, or dashboard/Admin contracts
| `path_outcome` | Categorical | resolved economic outcome only; censoring is tracked separately |

The stop family is bounded to:

1. `fib_invalidation`
2. `fib_atr`
3. `structure`
4. `fixed_atr`

If the expected stop heat required to survive the setup is too wide relative to the expected TP1 / TP2 edge, the correct decision is `PASS`.

The first selector baseline may exclude censored rows if needed for a clean resolved-only classification pass. Later survival / competing-risk work may use censored rows explicitly.

---

## 5. Feature Tiers

### Tier 1 — Pine-Live Features

These are features Pine can compute or request live:

- fib structure states
- intermarket states
- volume and volatility states
- session and timing states
- `request.economic()` macro levels and calendar-proxy states
- hidden harness outputs from approved open-source Pine modules

Only Tier 1 features can become live production logic.

### Tier 2 — Research-Only Features

These are local-research features used by AG for discovery:

- full FRED context from Supabase extracts
- GPR / geopolitical risk
- Trump Effect / policy uncertainty
- bullish/bearish news event and sentiment aggregates
- any other macro or event context without an exact Pine analogue

Tier 2 can influence the research conclusion, but it cannot enter the live Pine path unless Phase 4 proves an exact Pine analogue.

### Model Family Responsibilities

- **AutoGluon tabular**
  - first selector layer for resolved candidate quality
- **SHAP**
  - diagnostics and promotion gate for feature families and indicator-setting changes
- **Quantile / pinball models**
  - excursion and uncertainty-band modeling such as `mae_pts` and `mfe_pts`
- **Monte Carlo**
  - downstream policy and threshold simulation after calibrated probabilities exist
- **Volatility sidecars such as GARCH**
  - optional feature families that must prove additive value
- **Sequence / PyTorch models**
  - later-phase options only if tabular baselines and path diagnostics show clear unmet value

---

## 6. Required Event-Response Layer

The event-response block is mandatory.

It must score or gate at least these families:

1. MES impulse / reversal state
2. NQ confirmation or divergence
3. DXY impulse-and-fade state
4. ZN or `TVC:US10Y` flight-to-safety / reversal state
5. VIX shock / fade state
6. lower-timeframe volume shock / expansion state
7. scheduled macro proximity / release window state
8. breaking-news / narrative shock state paired with MES price reaction
9. pivot interaction state

The purpose of the event-response block is to:

- suppress weak setups
- delay entries
- confirm high-quality setups
- detect shock-failure or de-escalation reversals
- tie macro/news catalysts to observed MES reaction instead of treating text as a separate trade engine
- use pivot-state and pivot-distance as serious exhaustion / reversal context without turning pivots into the only decision surface

It must not become a separate trade engine detached from the fib contract.

---

## 7. Required Third-Party Harnesses

Three standalone exact-copy harnesses are required:

1. `Pivot Levels [BigBeluga]`
2. `Market Structure Break & OB Probability Toolkit [LuxAlgo]`
3. `Luminance Breakout Engine [LuxAlgo]`

Rules:

1. Use the original open-source Pine internals exactly.
2. Allow only interface-layer edits:
   - input grouping
   - visuals off by default
   - hidden `plot()` exports
   - alert payload wiring
   - wrapper glue
3. If exact-copy harnessing is blocked, stop. Do not build a substitute.

---

## 8. Hidden Export Contract

The active `v6` indicator must expose stable machine-readable outputs for local training capture.

TradingView enforces a hard maximum of `64` plot counts per script, and hidden `display.none` plots still count toward that limit.

Any live Pine export surface that exceeds `64` plot counts is invalid even if local parity passes.

Legacy hidden fields `ml_fib_regime`, the `.786` / `1.0` fib-level export families, and session-activity booleans (`ml_session_*_active`) are retired from the canonical packet. Hidden plots are unconditional `display.none`; there is no `showMLData` gating path in the canonical contract.

The inventory below is the desired Warbird export family set. The actual live Pine subset must be prioritized to stay within the `64` plot-count cap.

Minimum required hidden fields:

- `ml_confidence_score`
- `ml_direction_code`
- `ml_setup_archetype_code`
- `ml_fib_level_touched`
- `ml_stop_family_code`
- `ml_event_mode_code`
- `ml_event_shock_score`
- `ml_event_reversal_score`
- `ml_event_nq_state`
- `ml_event_dxy_state`
- `ml_event_zn_state`
- `ml_event_vix_state`
- `ml_event_pivot_interaction_code`
- `ml_ema21_dir`
- `ml_ema50_dir`
- `ml_ema200_dir`
- `ml_ema21_dist_pct`
- `ml_ema50_dist_pct`
- `ml_ema200_dist_pct`
- `ml_entry_long_trigger`
- `ml_entry_short_trigger`
- `ml_tp1_hit_event`
- `ml_tp2_hit_event`
- `ml_pivot_distance_nearest`
- `ml_pivot_cluster_count`
- `ml_pivot_active_zone_code`
- `ml_pivot_layer_length`
- `ml_pivot_volume_nearest`
- `ml_pivot_volume_distribution_pct`
- `ml_msb_direction_code`
- `ml_msb_momentum_zscore`
- `ml_ob_active_count`
- `ml_ob_hpz_active_count`
- `ml_ob_nearest_distance`
- `ml_ob_nearest_quality_score`
- `ml_ob_nearest_poc`
- `ml_ob_nearest_direction_code`
- `ml_ob_nearest_mitigated_code`
- `ml_ob_reliability_pct`
- `ml_luminance_signal`
- `ml_luminance_upper_threshold`
- `ml_luminance_lower_threshold`
- `ml_luminance_intensity`
- `ml_luminance_direction_code`
- `ml_luminance_breakout_code`
- `ml_luminance_bull_ob_active_count`
- `ml_luminance_bear_ob_active_count`
- `ml_luminance_bull_ob_mitigated_count`
- `ml_luminance_bear_ob_mitigated_count`
- `ml_luminance_bull_ob_nearest_distance`
- `ml_luminance_bear_ob_nearest_distance`
- `ml_luminance_bull_ob_nearest_intensity`
- `ml_luminance_bear_ob_nearest_intensity`

The live `v6` indicator exports the minimum subset above. Research-only diagnostics outside this list stay out of the live Pine packet until a later checkpoint re-admits them without breaking the TradingView plot budget.

BigBeluga, MSB/OB, and Luminance harness-family exports are now part of the minimum contract via the `ml_pivot_*`, `ml_msb_*`, `ml_ob_*`, and `ml_luminance_*` fields above.

The export contract must remain always-on and schema-stable for training capture.

---

## 9. Packet Output

AutoGluon must terminate in a Pine-ready packet, not a notebook-only conclusion.

The packet must include:

1. exact Pine input values
2. exact thresholds
3. exact weights
4. module keep/remove decisions
5. stop-family decisions
6. confidence-bin calibration tables
7. bucket-level TP1 / TP2 / reversal statistics
8. event-response thresholds and suppression rules
9. fib snapshot / lookback-family decisions when they are part of the admitted contract
10. decision-policy thresholds for `TAKE_TRADE` / `WAIT` / `PASS`
11. run metadata and sample counts

Packet promotion rule:

1. Packet fields must come from features/modules that survived SHAP review, feature-admission review, and out-of-sample validation.
2. The packet is not permission to preserve every candidate setting or indicator family that existed before training.

Allowed packet statuses:

- `CANDIDATE`
- `PROMOTED`
- `FAILED`
- `SUPERSEDED`

---

## 10. What Is Legacy And Must Not Drive New Work

The following are legacy and must not drive any new implementation:

- 1H-only fib contract
- `warbird_forecasts_1h` and other predicted-price forecast surfaces
- 5-minute cron as the model contract driver
- cloud-to-local sync as a standing subsystem
- unconstrained model-generated stop prices
- hand-rolled replacements for required third-party harnesses

---

## 11. File Surfaces

Primary live planning source:

- `docs/plans/2026-03-20-ag-teaches-pine-architecture.md`

Primary current Pine target:

- `indicators/v6-warbird-complete.pine`

Planned AG build surfaces:

- `scripts/ag/build-fib-snapshots.py`
- `scripts/ag/build-fib-dataset.py`
- `scripts/ag/train-fib-model.py`
- `scripts/ag/evaluate-configs.py`
- `scripts/ag/generate-packet.py`

This file exists to summarize the model contract cleanly. It is not permission to ignore the active plan.
