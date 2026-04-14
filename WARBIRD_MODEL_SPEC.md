# WARBIRD MODEL SPEC — v4

**Date:** 2026-04-10
**Status:** Active, aligned to Warbird Full Reset Plan v5
**Governing source:** `docs/MASTER_PLAN.md`
**PowerDrill research baseline:** `Powerdrill/reports/2026-04-06-powerdrill-findings.md`

This document is a subordinate reference for the model contract. It must not override `docs/MASTER_PLAN.md`, `docs/contracts/`, or `docs/cloud_scope.md`. If this file disagrees with those authority docs, the authority docs win immediately.

---

## 1. Governing Contract

1. The canonical trade object is the **MES 15m fib setup**.
2. The canonical key is the MES 15m **bar-close timestamp** in `America/Chicago`.
   The MES 15m setup is the parent object even when a lower-timeframe execution
   trigger is used. `5m` / `15m` entry candidates are subordinate micro execution
   states keyed back to that same parent setup; they do not replace it.
3. Pine is the canonical **live generator** (signal surface).
4. The **training generator** is the Python reconstruction pipeline in `scripts/ag/`. It reconstructs snapshots/interactions/outcomes from local warehouse OHLCV/context and is the only local AG training population path.
5. The Next.js dashboard is the richer mirrored operator surface using the same MES 15m fib contract; it is not a separate decision engine and must not recompute fib geometry locally.
6. The local `warbird` database on PG17 (`127.0.0.1:5432`) is the canonical warehouse truth. It owns the full data zoo: market history, AG lineage tables, the canonical training view, features, labels, SHAP artifacts, and all non-serving data.
7. Cloud Supabase (`qhwgrzqjcdtdqppvhhme`) is the reduced runtime/published serving database for frontend, indicator-support tables, packet distribution, curated SHAP/admin report surfaces, and other explicitly plan-approved published outputs. It must not become a mirror of local.
8. There are only two databases in scope: the local `warbird` PG17 warehouse and cloud Supabase.
9. AutoGluon is offline only. It trains, calibrates, and emits a Pine-ready packet.
10. The adaptive fib engine snapshot is the canonical base object. Live/runtime candidate semantics are defined by Pine on chart, while offline/training rows are reconstructed in Python from warehouse OHLCV/context with no Pine dependency.
    Fibs define the map and target ladder. Order-flow at the level defines the
    micro execution trigger.
11. The model output is MES 15m setup-outcome state: TP1–TP5 probability distribution, reversal risk, and bounded stop-family selection. It is **not** a predicted-price forecast surface.
12. AG and offline training must consume point-in-time fib snapshots keyed to the MES 15m bar close, not repaint-prone live chart reads.
13. The retained core historical window for training/support data starts at `2020-01-01T00:00:00Z`. Pre-2020 core rows are out of scope and must not be reintroduced into the canonical dataset.
14. The fib engine must preserve lookback/confluence intelligence; a simple zigzag-only anchor path is insufficient for Warbird.
15. Pivot distance and pivot-state are critical trigger/reversal inputs, but not the sole final decision maker.
16. Intermarket trigger quality must respect each symbol's correlative path and aligned 15m / 1H / 4H state.
17. Overlapping MA / volume / trend features across base logic and admitted harnesses must be de-duplicated by feature family.
18. Canonical AG contract is **three canonical local AG tables and one canonical training view.**
19. Exact local AG schema authority is `docs/contracts/ag_local_training_schema.md`.
20. The canonical live flow is `fib_engine_snapshot -> candidate -> AG_decision (against active packet) -> signal -> outcome`. The training flow is Python reconstruction over local OHLCV/context into AG lineage tables -> `ag_training` view -> model training. Live and training flows are distinct.
    Under the 2026-04-14 execution delta, the candidate stage may carry micro
    execution states `FORMING -> READY -> TRADE_ON -> INVALIDATED -> EXPIRED`
    without changing the parent 15m identity contract.
21. Decision vocabulary is locked to `TAKE_TRADE`, `WAIT`, and `PASS`. Those decision codes are distinct from realized outcome labels.
22. TradingView carries execution-facing visuals, alerts, and the exhaustion precursor diamond. Operator tables, mini charts, and dense diagnostics belong on the dashboard.
23. Cloud core support data starts at `2020-01-01T00:00:00Z`. All Databento ingestion uses `.c.0` continuous front-month contracts with `stype_in=continuous`. Databento handles contract rolls automatically — no manual roll logic. `contract-roll.ts` is dead code. MES uses `MES.c.0` via Live API (real-time) and Historical API (backfill). Cross-asset symbols (NQ, RTY, CL, HG, 6E, 6J) may remain in warehouse/cloud reference surfaces, but they are excluded from the first-run AG training zoo.
24. The operator-approved fib visual spec is a contract. Colors, line widths, line styles, and visible level-label presentation must be reproduced exactly across Pine and dashboard renderers unless explicitly reapproved.
25. First model target is locked to multiclass `outcome_label`.
26. First feature scope is locked to `MES 1m/15m/1h/4h + SP500 spot + macro`.
27. Macro scope is locked to the curated FRED regime set + `econ_calendar` only. No news or narrative sources.
    Curated FRED regime set:
    `SP500`, `DFF`, `SOFR`, `T10Y2Y`, `DGS2`, `DGS5`, `DGS10`, `DGS30`, `DGS3MO`,
    `DFEDTARL`, `DFEDTARU`, `CPIAUCSL`, `CPILFESL`, `PCEPILFE`, `T5YIE`, `T10YIE`,
    `DFII5`, `DFII10`, `DTWEXBGS`, `DEXUSEU`, `DEXJPUS`, `VIXCLS`, `VXNCLS`,
    `RVXCLS`, `OVXCLS`, `GVZCLS`, `NFCI`.
28. Exhaustion context is exported as `ml_*` hidden features in `ag_fib_interactions`.
    It is not a hard gate suppressing candidate row emission.
    Broad candidate emission is preserved. AG discovers the weights.
    Exhaustion has two distinct evidence paths in Pine v7 (2026-04-13):
    (a) **Reversal exhaustion** (`bearishExhaustion` / `bullishExhaustion`): fires at
        extension levels (1.272 / 1.618) when footprint shows counter-direction pressure.
        `exhaustionSignalDir` stores the reversal direction (−1 or +1 opposing `dir`).
        Features: `ml_exh_confidence_tier`, `ml_exh_delta_div`, `ml_exh_absorption`,
        `ml_exh_zero_print`, `ml_exh_z_score`, `ml_reversal_warning_in_trade`.
    (b) **Continuation evidence** (`continuationTier1Fired` / `continuationTier2Fired`):
        evaluated against `tradeDir` during an active trade — same-direction delta +
        stacked buy/sell imbalances confirm absorption at pullback. This path drives
        the hold guard (`continuationHoldActive`) and export features
        `ml_cont_confidence_tier`, `ml_cont_bars_since_trigger`.
        Prior to 2026-04-13 the hold guard was structurally dead (used reversal direction
        `lastTier1ExhDir == tradeDir` which is always false for same-direction continuation).
        Fixed by splitting the two paths into distinct Pine state variables.
29. S/R feature architecture is locked to per-type wide numeric families
    (`dist_*`, `at_*`, `above_*`, `flip_*`, `reject_*`, `vol_at_*`, `*_is_missing`).
    All values normalized by ATR or percent. Raw absolute level prices are
    never used as model features. Consolidated string columns, JSON/list-in-cell
    columns, and single nearest-level columns without type are prohibited.
30. kNN in Pine is not an AutoGluon replacement. If built, it is display-layer
    approximation only. It does not replace the offline AG training pipeline.
31. TV footprint history is not bulk-exportable. Footprint-derived features are
    captured via confirmed-bar alert/webhook from the indicator going forward.
    Historical backfill may use real `mes_1m` OHLCV-derived microstructure plus
    captured footprint where available. Do not claim full-history footprint
    truth until a lower-timeframe capture path exists.
32. Pine v6 capabilities required for exhaustion and hold logic include enums,
    strict boolean chains, dynamic loop boundaries, dynamic request strings,
    `request.footprint()`, and `polyline`-based rendering.
33. Behavioral features are first-class AG inputs. Phase 0.5 behavioral modules
    produce `ml_*` columns in `ag_fib_interactions` encoding session quality,
    momentum state, sizing context, and consecutive-loss context.
34. Live trade loss drivers are model-context inputs. AG must discover directional
    and execution asymmetries from features. They must not be hardcoded as direction gates.
35. Hard stop discipline is a model input, not just an execution rule.
    `ml_adverse_excursion_pts` encodes how far each trade went against the position
    before exit. Trades with excessive adverse excursion form a distinct label-quality signal.
36. Indicator snapshot features are sourced from `indicator_snapshots_15m`, populated
    by the automated Pine alert -> webhook -> Supabase -> local sync pipeline.
    Manual TV CSV export is a one-time historical seed operation only.

---

## 2. What The Model Is

The model evaluates the quality of canonical MES 15m interaction rows from `ag_fib_interactions`.

It does **not** forecast a future MES price level or produce a standalone `1H` price prediction.
It also does **not** turn `5m` / `15m` entry candidates into new standalone trade objects.
Those execution-timeframe states exist only to decide how to enter the parent 15m
setup and whether the map is currently actionable.

For each candidate setup, the model estimates:

- `highest_tp_hit`
- `hit_tp1` through `hit_tp5`
- `hit_sl`
- `tp1_before_sl`
- `bars_to_tp1`
- `bars_to_sl`
- `bars_to_resolution`
- expected `mae_pts`
- expected `mfe_pts`
- `outcome_label`

The model also selects from a **bounded stop family**. It does not emit an unconstrained stop price.

The model does **not** define the schema. The outcome contract defines the schema; the model stack is chosen to answer that contract.

### 2.1 System Roles

Warbird is split into three separate engines:

1. **Generator**
   - **Live generator:** Pine defines the live candidate/signal object on chart runtime
   - **Training generator:** Python reconstruction pipeline in `scripts/ag/` reconstructs snapshots/interactions/outcomes from local warehouse OHLCV/context and populates the three canonical local AG tables; `ag_training` is the read view
2. **Selector**
   - offline models score whether a frozen candidate is worth taking
3. **Diagnostician**
   - local research explains why trades won/lost and what should change in features, settings, or entry definition
   - query key is `run_id + interaction_id`
   - resolves raw SHAP artifact via `ag_artifacts`
   - returns per-trade waterfall and top interaction-pair contributions

The same model must not be treated as all three at once.

---

## 3. Canonical AG Schema

### 3.1 Canonical Local AG Contract

Canonical AG contract is **three canonical local AG tables and one canonical training view.**

- **`ag_fib_snapshots`** — frozen fib engine state at bar close
- **`ag_fib_interactions`** — candidate setups from fib-price interactions
- **`ag_fib_outcomes`** — realized forward path outcomes per interaction
- **`ag_training`** — canonical training view with `WHERE outcome_label != 'CENSORED'`

The exact column/type contract, PK/FK constraints, and full `ag_training` SQL definition are authoritative in `docs/contracts/ag_local_training_schema.md`.

Canonical names never use version suffixes.

The canonical warehouse truth remains the three local AG tables plus supporting market/macro source tables, with `ag_training` as the canonical view for model reads. Stop-family comparisons and SHAP lineage expand around this base contract; they do not replace it.

### 3.2 Fib Engine Snapshot And Candidate Definition

Canonical local training schema is the exact contract in `docs/contracts/ag_local_training_schema.md`.

`ag_fib_snapshots` holds point-in-time snapshot fields keyed by `ts`, including:

- `anchor_high`, `anchor_low`
- `anchor_high_bar_ts`, `anchor_low_bar_ts`
- `fib_range`, `fib_bull`
- `zz_deviation`, `zz_depth`
- `anchor_swing_bars`, `anchor_swing_velocity`, `time_since_anchor`
- `atr14`, `atr_pct`

`ag_fib_interactions` holds candidate interaction and bar-context fields, including:

- `snapshot_ts`, `direction`, `fib_level_touched`, `fib_level_price`
- `touch_distance_pts`, `touch_distance_norm`, `interaction_state`, `archetype`
- `entry_price`, `sl_price`, `tp1_price`, `tp2_price`, `tp3_price`, `tp4_price`, `tp5_price`
- `sl_dist_pts`, `sl_dist_atr`, `tp1_dist_pts`, `rr_to_tp1`
- `open`, `high`, `low`, `close`, `volume`
- `body_pct`, `upper_wick_pct`, `lower_wick_pct`, `rvol`
- `rsi14`, `ema9`, `ema21`, `ema50`, `ema200`
- `ema_stacked_bull`, `ema_stacked_bear`, `ema9_dist_pct`, `macd_hist`, `adx`, `energy`, `confluence_quality`

`ag_fib_interactions` is also the admitted home for micro execution-state
context once the migration lands. Do not create a fourth canonical AG table for
`5m` / `15m` entry candidates. Micro execution features remain attached to the
parent MES 15m setup row. Micro execution direction may oppose the parent
direction when the lower timeframe emits a legal failure / reversal trigger.

`ag_fib_outcomes` holds realized path/outcome fields, including:

- `highest_tp_hit`
- `hit_tp1`, `hit_tp2`, `hit_tp3`, `hit_tp4`, `hit_tp5`, `hit_sl`
- `tp1_before_sl`
- `bars_to_tp1`, `bars_to_sl`, `bars_to_resolution`
- `mae_pts`, `mfe_pts`
- `outcome_label`, `observation_window`

Offline/training semantics are reconstructed in Python from warehouse OHLCV/context into these canonical local AG tables; local training tables are written by Python only.

### 3.3 Locked Truth Semantics

These semantics are now binding:

- `warbird_decision_code`
  - `TAKE_TRADE`
  - `WAIT`
  - `PASS`
- canonical warehouse outcomes are the exact columns in `ag_fib_outcomes` from `docs/contracts/ag_local_training_schema.md`
- `outcome_label` is the locked first target field for training
- `ag_training` excludes rows where `outcome_label = 'CENSORED'`
- `EXPIRED` and `NO_REACTION` are not canonical economic outcome labels for model truth
- legacy `hit_*_first` / `prob_hit_*` names in `scripts/warbird/*` are deletion-only local-script debt and must not appear in shared TypeScript types, active APIs, Admin surfaces, packet payloads, or new schema work
- signal lifecycle and UI state are separate from economic truth and may use different vocabulary

Existing `GO` / `NO_GO` vocabulary is legacy and must not drive the next schema.

### 3.4 Cloud Serving Surfaces

The canonical warehouse remains local. Cloud is restricted to curated serving and publish-up surfaces only.

Cloud receives only these named published surfaces after manual promotion:

- `warbird_signals_15m`
- `warbird_signal_events`
- `warbird_packets`
- `warbird_packet_activations`
- `warbird_packet_metrics`
- `warbird_packet_feature_importance`
- `warbird_packet_recommendations`
- `warbird_packet_setting_hypotheses`
- `warbird_active_packet_metrics_v`
- `warbird_active_training_run_metrics_v`
- `warbird_active_packet_feature_importance_v`
- `warbird_active_packet_recommendations_v`
- `warbird_active_packet_setting_hypotheses_v`
- `warbird_active_signals_v`
- `warbird_admin_candidate_rows_v`
- `warbird_candidate_stats_by_bucket_v`
- `job_log`
- `mes_1m`, `mes_15m`, `mes_1h`, `mes_4h`, `mes_1d`
- `cross_asset_1h`, `cross_asset_15m`
- `econ_calendar`
- `econ_rates_1d`, `econ_yields_1d`, `econ_fx_1d`, `econ_vol_1d`, `econ_inflation_1d`, `econ_labor_1d`, `econ_activity_1d`, `econ_money_1d`, `econ_commodities_1d`, `econ_indexes_1d`

Cloud receives only derived/published read-model outputs; it does not receive direct copies of local lineage tables.

Cloud never receives:

- `ag_fib_snapshots`
- `ag_fib_interactions`
- `ag_fib_outcomes`
- `ag_training`
- `ag_training_runs`
- `ag_training_run_metrics`
- `ag_artifacts`
- `ag_shap_feature_summary`
- `ag_shap_cohort_summary`
- `ag_shap_interaction_summary`
- `ag_shap_temporal_stability`
- `ag_shap_feature_decisions`
- `ag_shap_run_drift`
- raw features
- raw labels
- raw SHAP matrices
- raw SHAP interaction matrices

The dashboard and Admin page may read only the distilled cloud runtime subset, not raw SHAP matrices, the full zoo, or local canonical base tables directly.

### 3.5 Non-Canonical Surfaces

The following names are legacy bridge surfaces in code and docs, but they are **not** the canonical AG training truth and must not drive new architecture:

- `warbird_triggers_15m`
- `warbird_conviction`
- `warbird_risk`
- `warbird_setups`
- `warbird_setup_events`
- `measured_moves`
- `warbird_daily_bias`
- `warbird_structure_4h`
- `warbird_forecasts_1h` — forecast route deleted; explicit retirement debt
- `warbird_fib_engine_snapshots_15m` — replaced by `ag_fib_snapshots`
- `warbird_fib_candidates_15m` — replaced by `ag_fib_interactions`
- `warbird_candidate_outcomes_15m` — replaced by `ag_fib_outcomes`

These references will be retired once the canonical AG tables have active writers and all dashboard/API consumers are migrated.

---

## 4. Target Labels

The locked first training target is `outcome_label` from `ag_fib_outcomes`.

### 4.1 Canonical Warehouse Outcome Columns (`ag_fib_outcomes`)

| Column               | Type      | Contract Role                                    |
| -------------------- | --------- | ------------------------------------------------ |
| `highest_tp_hit`     | `int`     | Highest target reached in the observation window |
| `hit_tp1`            | `boolean` | Target-1 hit flag                                |
| `hit_tp2`            | `boolean` | Target-2 hit flag                                |
| `hit_tp3`            | `boolean` | Target-3 hit flag                                |
| `hit_tp4`            | `boolean` | Target-4 hit flag                                |
| `hit_tp5`            | `boolean` | Target-5 hit flag                                |
| `hit_sl`             | `boolean` | Stop-loss hit flag                               |
| `tp1_before_sl`      | `boolean` | Path fact: TP1 before stop                       |
| `bars_to_tp1`        | `int`     | Bars from interaction to TP1                     |
| `bars_to_sl`         | `int`     | Bars from interaction to SL                      |
| `bars_to_resolution` | `int`     | Bars from interaction to resolved state          |
| `mae_pts`            | `float8`  | Max adverse excursion                            |
| `mfe_pts`            | `float8`  | Max favorable excursion                          |
| `outcome_label`      | `text`    | Primary multiclass training target               |
| `observation_window` | `int`     | Window used for label resolution                 |

`ag_training` excludes censored rows with `WHERE outcome_label != 'CENSORED'`.

### 4.2 Derived Model-Stage Labels (Not Canonical Warehouse Columns)

Additional policy or research labels can be derived downstream, but they are explicitly non-canonical and outside the warehouse schema contract.

The stop family is bounded to formula-specific IDs:

1. `FIB_NEG_0236` — fib negative 0.236 extension from active range
2. `FIB_NEG_0382` — fib negative 0.382 extension from active range
3. `ATR_1_0` — 1.0× ATR from entry
4. `ATR_1_5` — 1.5× ATR from entry
5. `ATR_STRUCTURE_1_25` — max of structure and 1.25× ATR
6. `FIB_0236_ATR_COMPRESS_0_50` — compressed fib + 0.5× ATR buffer

Each ID binds to a deterministic formula. See `docs/contracts/stop_families.md` for exact formulas.

If the expected stop heat required to survive the setup is too wide relative to the expected TP1-TP5 edge, the correct decision is `PASS`.

The first selector baseline should train on resolved rows according to the active `outcome_label` policy and `observation_window` handling in the pipeline configuration.

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
- `econ_calendar` event proximity and impact states
- any other approved macro or event context without an exact Pine analogue

NEWS and sentiment aggregates are retired from the active contract unless explicitly reopened. They are not part of the default Tier 2 surface.

Tier 2 can influence the research conclusion, but it cannot enter the live Pine path unless Phase 4 proves an exact Pine analogue.

### Model Family Responsibilities

- **AutoGluon tabular**
  - first selector layer for resolved candidate quality
- **SHAP**
  - diagnostics and promotion gate for feature families and indicator-setting changes
  - full-surface SHAP is mandatory (see Section 8)
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

These cross-asset futures surfaces remain available for warehouse or cloud reference only. They are not admitted into the first-run AG training zoo after the 2026-04-14 scope cut.

| Group         | Symbols                                                      | Detection                           | Databento               | Data Pipeline                                           |
| ------------- | ------------------------------------------------------------ | ----------------------------------- | ----------------------- | ------------------------------------------------------- |
| Leadership    | NQ (`CME_MINI:NQ1!`)                                         | EMA trend, relative strength vs MES | NQ.c.0                  | `cross-asset` Edge Function → `cross_asset_1h` (hourly) |
| Risk Appetite | RTY (`CME_MINI:RTY1!`), CL (`NYMEX:CL1!`), HG (`COMEX:HG1!`) | EMA trend, correlation divergence   | RTY.c.0, CL.c.0, HG.c.0 | `cross-asset` Edge Function → `cross_asset_1h` (hourly) |
| Macro-FX      | 6E (`CME:6E1!`), 6J (`CME:6J1!`)                             | EMA trend, risk-on/risk-off flow    | 6E.c.0, 6J.c.0          | `cross-asset` Edge Function → `cross_asset_1h` (hourly) |
| Execution     | ES VWAP state/event, range expansion, efficiency             | Chart-native, zero security calls   | N/A                     | Computed from MES OHLCV directly                        |

State machine: NEUTRAL(0) → BULL(1) / BEAR(-1). Score > 65 for N bars → BULL. Score < 35 for N bars → BEAR. Exit to NEUTRAL at 50. Override (direct bull↔bear) only when multiple groups extreme same direction.

**Why CME-only:** AG training needs 15m historical data from Databento. NYSE internals (TICK, VOLD), CBOE indices (VIX, VVIX, VIX3M), and ETFs (HYG) are only available on separate exchanges not covered by the CME Standard plan.

**Data tables:** `cross_asset_1h` (hourly, Edge Function), `cross_asset_15m` (15m, backfill script for AG training).

### 6b. Daily Context Exports (NOT gate members)

These are daily-only — same value for all 27 bars in a session. Exported as AG training features, NOT used in the 15m regime gate.

| Symbol   | Source       | Role                                                        |
| -------- | ------------ | ----------------------------------------------------------- |
| VIX      | FRED (daily) | Vol regime context — AG learns low-vol vs high-vol behavior |
| SKEW     | `CBOE:SKEW`  | Tail-risk hedging — institutions hedge before selling       |
| NYSE A/D | `USI:ADD`    | Advance-Decline breadth — divergence = exhaustion warning   |

### 6c. MES-Native State (chart OHLCV)

1. MES impulse / reversal state
2. ES execution quality (VWAP state/event, range expansion, intrabar efficiency)
3. lower-timeframe volume shock / expansion state
4. pivot interaction state

### 6d. Macro/Policy Context (server-side)

5. scheduled macro proximity / release window state (from `econ_calendar`)
6. FRED daily families admitted by the current contract

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

| Metric                           | Formula                   |
| -------------------------------- | ------------------------- |
| EMA(close, 21)                   | Exponential MA, 21 bar    |
| EMA(close, 50)                   | Exponential MA, 50 bar    |
| EMA(close, 100)                  | Exponential MA, 100 bar   |
| EMA(close, 200)                  | Exponential MA, 200 bar   |
| MACD histogram (12, 26, 9)       | MACD diff histogram       |
| RSI(close, 14)                   | Relative Strength Index   |
| ATR(14)                          | Average True Range        |
| ADX(14)                          | Average Directional Index |
| Raw bar volume                   | Volume                    |
| SMA(volume, 20)                  | Volume SMA                |
| volume / SMA(volume, 20)         | Volume ratio              |
| Change in vol_ratio bar-over-bar | Volume acceleration       |
| (high - low) × volume            | Bar spread × volume       |
| On-Balance Volume (cumulative)   | OBV                       |
| Money Flow Index(hlc3, 14)       | MFI                       |

All metrics are deterministic, point-in-time safe, and computed from MES 15m OHLCV — no Pine plot budget cost. AG discovers thresholds, weights, and interactions from these primitives via SHAP.

---

## 8. Full-Surface SHAP Program

Full SHAP is mandatory and local-only at raw level.

### 8.1 Local Lineage Tables

- `ag_training_runs`
- `ag_training_run_metrics`
- `ag_artifacts`
- `ag_shap_feature_summary`
- `ag_shap_cohort_summary`
- `ag_shap_interaction_summary`
- `ag_shap_temporal_stability`
- `ag_shap_feature_decisions`
- `ag_shap_run_drift`

### 8.2 Raw SHAP Storage

Store append-only raw artifacts in `artifacts/shap/{run_id}/`:

- `shap_values_{fold}_{split}.parquet` — per-row SHAP values
- `shap_interactions_{fold}_{split}.parquet` — per-row SHAP interaction values

Each artifact must include: `interaction_id`, `run_id`, `target_name`, `split_code`, `fold_code`.

### 8.3 SHAP Coverage

SHAP coverage is locked to the full surface:

- all 16 fib levels
- all indicators/features
- both directions
- all outcome classes
- all stop families
- all sessions
- all volatility regimes
- all walk-forward folds

### 8.4 Mandatory Cohort Dimensions

For `ag_shap_cohort_summary`:

- fib level
- direction
- outcome class
- stop family
- session
- volatility regime
- fold

### 8.5 Mandatory Analyses

**SHAP interaction analysis:**

- global pairwise interaction importance
- fold-specific interaction importance
- cohort-specific interaction importance
- prior-run vs current-run interaction drift

**Temporal stability analysis:**

- fold-over-fold rank correlation
- normalized importance drift
- stability bucket per feature

**Baseline drift analysis:**

- compare each retrain's SHAP against the prior approved run
- record rank deltas, importance deltas, cohort deltas, and interaction deltas

### 8.6 Feature Decision Protocol

- First run includes every point-in-time-safe available feature
- No auto-drop after first run
- `REVIEW_DROP` only after 3 consecutive runs of negligible global importance, no cohort prominence, and no strong interaction role
- Actual removal requires explicit approval after SHAP evidence is recorded

---

## 9. Training Discipline

Training discipline is locked:

- walk-forward splits only
- one-session embargo minimum
- no shuffle
- no fit on full dataset
- no tuning on test
- naive baseline required
- full run metadata required

---

## 10. Pine Live-Runtime Output Contract

Pine output fields are live/runtime telemetry for chart behavior, alerting, and runtime compatibility only.

Pine output fields are **NOT** the local AG training ingestion path.

The local AG training ingestion path is only: `scripts/ag/` Python reconstruction from local warehouse OHLCV/context -> `ag_fib_snapshots` / `ag_fib_interactions` / `ag_fib_outcomes` -> `ag_training`.

TradingView enforces a hard maximum of `64` output calls per script, and hidden `display.none` plots count toward that limit.

**Current v7 budget (verified 2026-04-13):**
- Institutional: `51/64` (46 plot + 2 plotshape + 3 alertcondition, 13 headroom)
- Strategy: `52/64` (50 plot + 2 plotshape, 12 headroom)

Any change that exceeds `64` is invalid.

Runtime output families that may remain in Pine:

- live direction/archetype/fib interaction state for chart and alerts
- entry/exit event flags and TP hit event flags for runtime lifecycle tracking
- runtime-only context codes required by the active packet and dashboard compatibility surfaces
- micro execution-state outputs (`FORMING`, `READY`, `TRADE_ON`,
  `INVALIDATED`, `EXPIRED`) and micro pattern codes (`PULLBACK_HOLD`,
  `FAILED_RECLAIM`, `CLIMAX_REVERSAL`, `FAILED_EXPANSION`) for operator use
  once admitted by the active contract
- chart-visual diagnostics that are explicitly marked non-training and non-canonical for warehouse ingestion

AG-owned features remain server-side from Databento OHLCV and local warehouse context; they are not Pine plot exports and must not be backfilled into Pine output budget.

---

## 11. Packet Output

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
11. micro execution feature/timeframe evidence that survived AG/SHAP review,
    including the preferred `5m` / `15m` trigger family when the parent
    15m setup is active
12. run metadata and sample counts

Packet promotion rule:

1. Packet fields must come from features/modules that survived SHAP review, feature-admission review, and out-of-sample validation.
2. The packet is not permission to preserve every candidate setting or indicator family that existed before training.

Allowed packet statuses:

- `CANDIDATE`
- `PROMOTED`
- `FAILED`
- `SUPERSEDED`

---

## 12. What Is Legacy And Must Not Drive New Work

The following are legacy and must not drive any new implementation:

- 1H-only fib contract
- `warbird_forecasts_1h` and other predicted-price forecast surfaces
- 5-minute cron as the model contract driver
- cloud-to-local sync as a standing subsystem
- unconstrained model-generated stop prices
- BigBeluga, LuxAlgo MSB/OB, and LuxAlgo Luminance standalone harness files
- `ml_pivot_*`, `ml_msb_*`, `ml_ob_*`, and `ml_luminance_*` export families
- `warbird_fib_engine_snapshots_15m`, `warbird_fib_candidates_15m`, `warbird_candidate_outcomes_15m` — replaced by canonical AG tables
- all news/options surfaces
- any versioned canonical name

---

## 13. File Surfaces

Primary live planning source:

- `docs/MASTER_PLAN.md`
- `docs/contracts/README.md`
- `docs/contracts/ag_local_training_schema.md`

Primary current Pine target:

- `indicators/v7-warbird-institutional.pine` (active work surface, v6 is legacy baseline)

AG build surfaces:

- `scripts/ag/` — full offline pipeline (extract, reconstruct, generate, label, train, SHAP, publish-up)

Artifact surfaces:

- `artifacts/` — append-only model outputs, reports
- `artifacts/shap/{run_id}/` — raw SHAP parquet artifacts

This file exists to summarize the model contract cleanly. It is not permission to ignore the active plan.
