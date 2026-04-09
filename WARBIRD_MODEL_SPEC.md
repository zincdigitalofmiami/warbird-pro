# WARBIRD MODEL SPEC — v3

**Date:** 2026-03-31
**Status:** Reference-Only, aligned to the active plan
**Governing source:** `docs/MASTER_PLAN.md`
**PowerDrill research baseline:** `Powerdrill/reports/2026-04-06-powerdrill-findings.md`

This document is a subordinate reference for the model contract. It must not override `docs/MASTER_PLAN.md`, `docs/contracts/`, or `docs/cloud_scope.md`. If this file disagrees with those authority docs, the authority docs win immediately.

Status note (2026-04-07): this file is not implementation authority for schema placement, runtime scope, or packet-serving topology. The canonical source for those decisions is now the master plan plus the contract set.

---

## 1. Governing Contract

1. The canonical trade object is the **MES 15m fib setup**.
2. The canonical key is the MES 15m **bar-close timestamp** in `America/Chicago`.
3. Pine is the canonical live signal surface.
4. The Next.js dashboard is the richer mirrored operator surface using the same MES 15m fib contract; it is not a separate decision engine and must not recompute fib geometry locally.
5. The external-drive local PostgreSQL warehouse is the canonical database truth. It owns the retained market history, research features, labels, experiments, SHAP artifacts, and all non-serving zoo data.
6. Cloud Supabase is the reduced runtime/published serving database for frontend, indicator-support tables, packet distribution, curated SHAP/admin report surfaces, and other explicitly plan-approved published outputs. It must not become a mirror of local.
7. There are only two databases in scope: the local PostgreSQL warehouse and cloud Supabase.
8. AutoGluon is offline only. It trains, calibrates, and emits a Pine-ready packet.
9. The adaptive fib engine snapshot is the canonical base object. The model does **not** invent raw entries from scratch. The Pine fib engine creates the candidate setup first.
10. The model output is MES 15m setup-outcome state: TP1–TP5 probability distribution, reversal risk, and bounded stop-family selection. It is **not** a predicted-price forecast surface.
11. AG and offline training must consume point-in-time fib snapshots keyed to the MES 15m bar close, not repaint-prone live chart reads.
12. The retained core historical window for training/support data starts at `2020-01-01T00:00:00Z`. Pre-2020 core rows are out of scope and must not be reintroduced into the canonical dataset.
13. The fib engine must preserve lookback/confluence intelligence; a simple zigzag-only anchor path is insufficient for Warbird.
14. Pivot distance and pivot-state are critical trigger/reversal inputs, but not the sole final decision maker.
15. Intermarket trigger quality must respect each symbol's correlative path and aligned 15m / 1H / 4H state.
16. Overlapping MA / volume / trend features across base logic and admitted harnesses must be de-duplicated by feature family.
17. The minimal Pine export surface for training capture is fib lines/state, pivot state/distance, and admitted indicator/harness outputs from the canonical indicator surface.
18. The canonical live flow is `fib_engine_snapshot -> candidate -> AG_decision (against active packet) -> signal -> outcome`. The training flow is `fib_engine_snapshot -> candidate -> outcome -> learn_decision_policy`. Live and training flows are distinct.
19. Decision vocabulary is locked to `TAKE_TRADE`, `WAIT`, and `PASS`. Those decision codes are distinct from realized outcome labels.
20. TradingView carries execution-facing visuals, alerts, and the exhaustion precursor diamond. Operator tables, mini charts, and dense diagnostics belong on the dashboard.
21. Cloud core support data starts at `2020-01-01T00:00:00Z`. All Databento ingestion uses `.c.0` continuous front-month contracts with `stype_in=continuous`. Databento handles contract rolls automatically — no manual roll logic. `contract-roll.ts` is dead code. MES uses `MES.c.0` via Live API (real-time) and Historical API (backfill). Cross-asset symbols (NQ, RTY, CL, HG, 6E, 6J, etc.) use `{SYMBOL}.c.0` via Historical API `ohlcv-1h`, pulled hourly by the `cross-asset` Edge Function.
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
   - Pine defines the candidate entry object using the embedded TA core pack
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
- exhaustion precursor context (proven primitives: bar quality, momentum/volume divergence, range compression, centered MFI — no untested oscillators)
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
- confidence score (chart-visual only in Pine; operator-facing confidence must come from calibrated AG packet output)
- event-response state
- exhaustion precursor context (proven primitives: bar quality, momentum/volume divergence, range compression, centered MFI — no untested oscillators)
- EMA context (distance + direction)
- candidate/context support fields consumed downstream when AG assigns `TAKE_TRADE` / `WAIT` / `PASS`
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
- realized economic truth is locked to:
  - `TP5_HIT`
  - `TP4_HIT`
  - `TP3_HIT`
  - `TP2_HIT`
  - `TP1_ONLY`
  - `STOPPED`
  - `REVERSAL`
  - `OPEN` (operational-only; exclude from training targets)
- `EXPIRED` and `NO_REACTION` are not canonical economic outcome labels for model truth
- legacy `hit_*_first` / `prob_hit_*` names in `scripts/warbird/*` are deletion-only local-script debt and must not appear in shared TypeScript types, active APIs, Admin surfaces, packet payloads, or new schema work
- signal lifecycle and UI state are separate from economic truth and may use different vocabulary

Existing `GO` / `NO_GO` vocabulary is legacy and must not drive the next schema.

### 3.2 Locked Cloud Runtime Subset Families

The canonical warehouse remains local. Cloud is restricted to ingress plus curated serving and publish-up surfaces only.

Allowed cloud families:

1. ingress intake, dedupe, retry, and DLQ surfaces
   - receive Pine alerts
   - expose runtime health
   - must not become canonical candidate truth
2. curated frontend and admin read models
   - recent candidate stream
   - recent signal stream
   - runtime status and health
   - operator-facing packet state
3. packet distribution surfaces
   - active packet pointer
   - minimal published packet metadata
   - packet download reference when required
4. curated SHAP and report serving surfaces
   - top feature summaries
   - report metadata
   - artifact URL or path references
5. operational logging
   - `job_log`
   - ingress and publish-job health aggregates

The following families remain canonical local-only:

- `warbird_fib_engine_snapshots_15m`
- `warbird_fib_candidates_15m`
- `warbird_candidate_outcomes_15m`
- `warbird_signals_15m`
- `warbird_signal_events`
- `warbird_packets`
- `warbird_packet_activations`
- `warbird_training_runs`
- `warbird_training_run_metrics`
- raw SHAP artifacts
- wide experiment, feature, and label tables

The dashboard and Admin page may read only the distilled cloud runtime subset, not raw SHAP matrices, the full zoo, or local canonical base tables directly.

### 3.3 Non-Canonical Surfaces

The following names are legacy bridge surfaces in code and docs, but they are **not** the canonical AG training truth and must not drive new architecture:

- `warbird_triggers_15m`
- `warbird_conviction`
- `warbird_risk`
- `warbird_setups`
- `warbird_setup_events`
- `measured_moves`
- `warbird_daily_bias`
- `warbird_structure_4h`
- `warbird_forecasts_1h` — forecast route deleted; this is explicit retirement debt, not future architecture; the table may still exist remotely until drift reconciliation and final retirement, but must not drive any new work

As of 2026-03-31 DB-truth audit, the legacy operational tables above do not exist on either checked DB. Any remaining code references to them are schema-stale debt, not proof that the tables are still live.

These references will be retired once the canonical tables above have active writers and all dashboard/API consumers are migrated.

Dashboard and Admin compatibility surfaces should be derived over the cloud runtime subset or other explicitly published read models, not over hidden duplicate warehouse tables.

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
| `tp3_before_sl` | Binary | TP3 reached before stop |
| `tp4_before_sl` | Binary | TP4 reached before stop |
| `tp5_before_sl` | Binary | TP5 reached before stop |
| `sl_before_tp1` | Binary | stop hit before TP1 |
| `path_outcome` | Categorical | one of `TP5_HIT`, `TP4_HIT`, `TP3_HIT`, `TP2_HIT`, `TP1_ONLY`, `STOPPED`, `REVERSAL`, `OPEN` |
| `mae_pts` | Continuous | max adverse excursion in points |
| `mfe_pts` | Continuous | max favorable excursion in points |

Legacy note:

- the old local-only `hit_sl_first`, `hit_pt1_first`, and `hit_pt2_after_pt1` names are scheduled for deletion during the AG workbench rebuild
- no fallback aliasing of those names is allowed in active shared types, API responses, packets, or dashboard/Admin contracts

The stop family is bounded to formula-specific IDs:

1. `FIB_NEG_0236` — fib negative 0.236 extension from active range
2. `FIB_NEG_0382` — fib negative 0.382 extension from active range
3. `ATR_1_0` — 1.0× ATR from entry
4. `ATR_1_5` — 1.5× ATR from entry
5. `ATR_STRUCTURE_1_25` — max of structure and 1.25× ATR
6. `FIB_0236_ATR_COMPRESS_0_50` — compressed fib + 0.5× ATR buffer

Each ID binds to a deterministic formula. See `docs/contracts/stop_families.md` for exact formulas.

If the expected stop heat required to survive the setup is too wide relative to the expected TP1–TP5 edge, the correct decision is `PASS`.

The first selector baseline should train on resolved rows only (`TP5_HIT`, `TP4_HIT`, `TP3_HIT`, `TP2_HIT`, `TP1_ONLY`, `STOPPED`, `REVERSAL`) and exclude `OPEN`.

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

- full FRED context from approved retained macro tables
- GPR / geopolitical risk
- approved policy-event context from retained non-NEWS sources
- any other approved macro or event context without an exact Pine analogue and without reopening retired NEWS or sentiment surfaces

NEWS and sentiment aggregates are retired from the active contract unless explicitly reopened. They are not part of the default Tier 2 surface.

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

## 6. Regime Gate + Context Layer

### 6a. Intraday Regime Gate (15m bar close, grouped scoring)

The regime gate produces a continuous score (0-100) from grouped intraday indicators. All update at 15m bar close. AG decides final weights and correlations from training data.

**AG Training Basket — CME Globex (Databento GLBX.MDP3):**

All 6 symbols use `.c.0` continuous contracts with `stype_in=continuous`. Databento handles contract rolls automatically — no manual roll logic needed.

| Group | Symbols | Detection | Databento | Data Pipeline |
|---|---|---|---|---|
| Leadership | NQ (`CME_MINI:NQ1!`) | EMA trend, relative strength vs MES | NQ.c.0 | `cross-asset` Edge Function → `cross_asset_1h` (hourly) |
| Risk Appetite | RTY (`CME_MINI:RTY1!`), CL (`NYMEX:CL1!`), HG (`COMEX:HG1!`) | EMA trend, correlation divergence | RTY.c.0, CL.c.0, HG.c.0 | `cross-asset` Edge Function → `cross_asset_1h` (hourly) |
| Macro-FX | 6E (`CME:6E1!`), 6J (`CME:6J1!`) | EMA trend, risk-on/risk-off flow | 6E.c.0, 6J.c.0 | `cross-asset` Edge Function → `cross_asset_1h` (hourly) |
| Execution | ES VWAP state/event, range expansion, efficiency | Chart-native, zero security calls | N/A | Computed from MES OHLCV directly |

**Dashboard symbol bar:** HG, NQ, 6E, CL displayed as green/red tiles from `cross_asset_1h` (latest 2 rows → hourly change). All positive polarity (up = MES-aligned = green).

**ES chart-native vol fills VIX/VVIX gap:** ATR ratio, range expansion, intrabar efficiency, VWAP state/event — all computed from MES OHLCV directly.

State machine: NEUTRAL(0) → BULL(1) / BEAR(-1). Score > 65 for N bars → BULL. Score < 35 for N bars → BEAR. Exit to NEUTRAL at 50. Override (direct bull↔bear) only when multiple groups extreme same direction.

**Why CME-only:** AG training needs 15m historical data from Databento. NYSE internals (TICK, VOLD), CBOE indices (VIX, VVIX, VIX3M), and ETFs (HYG) are only available on separate exchanges not covered by the CME Standard plan.

**Data tables:** `cross_asset_1h` (hourly, Edge Function), `cross_asset_15m` (15m, backfill script for AG training), `cross_asset_1d` (daily, derived from 1h).

### 6b. Daily Context Exports (NOT gate members)

These are daily-only — same value for all 27 bars in a session. Exported as AG training features, NOT used in the 15m regime gate.

| Symbol | Source | Role |
|---|---|---|
| VIX | FRED (daily) | Vol regime context — AG learns low-vol vs high-vol behavior |
| SKEW | `CBOE:SKEW` | Tail-risk hedging — institutions hedge before selling |
| NYSE A/D | `USI:ADD` | Advance-Decline breadth — divergence = exhaustion warning |

### 6c. MES-Native State (chart OHLCV)

1. MES impulse / reversal state
2. ES execution quality (VWAP state/event, range expansion, intrabar efficiency)
3. lower-timeframe volume shock / expansion state
4. pivot interaction state

### 6d. Macro/Policy Context (server-side)

5. scheduled macro proximity / release window state
6. approved policy-event shock state from retained non-NEWS sources paired with MES price reaction

### Purpose

The regime gate and context layer exist to:

- suppress weak setups via grouped intermarket scoring
- delay entries via hysteresis and persistence requirements
- confirm high-quality setups via impulse quality filtering
- detect shock-failure or de-escalation reversals
- tie approved macro or policy catalysts to observed MES reaction instead of treating text as a separate trade engine
- use pivot-state and pivot-distance as serious exhaustion / reversal context without turning pivots into the only decision surface

It must not become a separate trade engine detached from the fib contract.

---

## 7. TA Core Pack (AG Server-Side, Not Pine Exports)

The three standalone harnesses (BigBeluga Pivot Levels, LuxAlgo MSB/OB Toolkit, LuxAlgo Luminance Engine) have been retired. The 15-metric TA core pack is now **AG-owned and computed server-side from Databento OHLCV**. These metrics are NOT Pine plot exports and must not be re-added to the Pine output budget.

| Metric | Formula |
|---|---|
| EMA(close, 21) | Exponential MA, 21 bar |
| EMA(close, 50) | Exponential MA, 50 bar |
| EMA(close, 100) | Exponential MA, 100 bar |
| EMA(close, 200) | Exponential MA, 200 bar |
| MACD histogram (12, 26, 9) | MACD diff histogram |
| RSI(close, 14) | Relative Strength Index |
| ATR(14) | Average True Range |
| ADX(14) | Average Directional Index |
| Raw bar volume | Volume |
| SMA(volume, 20) | Volume SMA |
| volume / SMA(volume, 20) | Volume ratio |
| Change in vol_ratio bar-over-bar | Volume acceleration |
| (high - low) × volume | Bar spread × volume |
| On-Balance Volume (cumulative) | OBV |
| Money Flow Index(hlc3, 14) | MFI |

All metrics are deterministic, point-in-time safe, and computed from MES 15m OHLCV — no Pine plot budget cost. AG discovers thresholds, weights, and interactions from these primitives via SHAP.

---

## 8. Hidden Export Contract

The active `v7` indicator (`indicators/v7-warbird-institutional.pine`) must expose stable machine-readable outputs for local training capture.

TradingView enforces a hard maximum of `64` plot counts per script, and hidden `display.none` plots still count toward that limit.

Any live Pine export surface that exceeds `64` plot counts is invalid even if local parity passes.

**Current v7 budget: 32 plot + 3 alertcondition = 35/64 (29 headroom).** All server-side-computable features were removed from Pine in the Phase 1E cull. AG owns TA core pack, EMA dist, RVOL, exhaustion, range expansion, efficiency, event_day, and constant-stub IM states — these must NOT be re-added to Pine.

Legacy hidden fields `ml_fib_regime`, the `.786` / `1.0` fib-level export families, and session-activity booleans (`ml_session_*_active`) are retired from the canonical packet. Hidden plots are unconditional `display.none`; there is no `showMLData` gating path in the canonical contract.

AG-eligible hidden fields emitted by Pine (primitive features only):

- `ml_direction_code`
- `ml_setup_archetype_code`
- `ml_fib_level_touched`
- `ml_stop_family_code`
- `ml_event_mode_code`
- `ml_event_nq_state` (stub — value from `cross_asset_1h` server-side)
- `ml_event_rty_state` (stub — value from `cross_asset_1h` server-side)
- `ml_event_cl_state` (stub — value from `cross_asset_1h` server-side)
- `ml_event_hg_state` (stub — value from `cross_asset_1h` server-side)
- `ml_event_eur_state` (stub — value from `cross_asset_1h` server-side)
- `ml_event_jpy_state` (stub — value from `cross_asset_1h` server-side)
- `ml_event_pivot_interaction_code`
- `ml_ema21_dir`
- `ml_ema50_dir`
- `ml_ema200_dir`
- `ml_entry_long_trigger`
- `ml_entry_short_trigger`
- `ml_tp1_hit_event`
- `ml_tp2_hit_event`
- `ml_tp3_hit_event`
- `ml_tp4_hit_event`
- `ml_tp5_hit_event`
- `ml_last_exit_outcome` (7-class: 0=none, 1=TP1, 2=TP2, 3=STOPPED, 4=EXPIRED, 5=TP3, 6=TP4, 7=TP5)
- `ml_vwap_code`
- `ml_or_state` (opening range state)
- `ml_add_slope` (NYSE A/D daily slope)
- (HTF confluence fields — 3 `request.security()` fib calls)

AG-owned features (NOT Pine plot exports — computed server-side from Databento OHLCV):

- TA core pack: EMA(21/50/100/200), MACD hist, RSI(14), ATR(14), ADX(14), volume raw/SMA/ratio/acceleration, bar_spread×vol, OBV, MFI(14)
- EMA dist_pct (21/50/200)
- RVOL, range expansion, intrabar efficiency, exhaustion primitives
- IM basket states: NQ/RTY/CL/HG/6E/6J EMA trend and relative strength (from `cross_asset_1h`)
- Regime components: leader_score, risk_score, macrofx_score, exec_score
- Impulse quality, agreement velocity, regime score (AG learns weights from primitives)
- event_day

Chart-visual/debug-only fields (NOT AG training surface):

- `ml_confidence_score` — hand-coded heuristic composite; operator confidence must come from calibrated AG packet output per binding rule 0.10
- `ml_event_shock_score` — pre-composed from alignment, ROC, and conflict
- `ml_event_reversal_score` — pre-composed from breakAgainst, reject, and conflict booleans
- `ml_impulse_quality` — hand-coded composite; AG learns weights from OHLCV primitives instead
- `ml_exhaustion_score` — retired (HyperWave-based); exhaustion features are server-side computable

These composites may remain in Pine for chart display, but they must NOT appear in the AG training matrix.

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
7. bucket-level TP1–TP5 / reversal statistics
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
- BigBeluga, LuxAlgo MSB/OB, and LuxAlgo Luminance standalone harness files
- `ml_pivot_*`, `ml_msb_*`, `ml_ob_*`, and `ml_luminance_*` export families

---

## 11. File Surfaces

Primary live planning source:

- `docs/MASTER_PLAN.md`
- `docs/contracts/README.md`

Primary current Pine target:

- `indicators/v7-warbird-institutional.pine` (active work surface, v6 is legacy baseline)

Planned AG build surfaces:

- `scripts/ag/build-fib-snapshots.py`
- `scripts/ag/build-fib-dataset.py`
- `scripts/ag/train-fib-model.py`
- `scripts/ag/evaluate-configs.py`
- `scripts/ag/generate-packet.py`

This file exists to summarize the model contract cleanly. It is not permission to ignore the active plan.
