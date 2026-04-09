# Warbird Master Execution Plan

**Date:** 2026-04-07
**Status:** Active Plan - Single Source of Truth
**Scope:** MES 15m fib contract, Pine signal surface, local canonical warehouse, curated cloud runtime subset, AutoGluon packet publish-up

This file is the only planning authority for Warbird.

If any other plan, decision note, scratch doc, or archived checkpoint disagrees with this file, this file wins immediately.

## 0. Binding Rules

### 0.1 Canonical database boundary

- The external-drive local PostgreSQL warehouse is the single canonical database truth.
- The local warehouse owns the full retained data zoo:
  - raw market bars
  - macro and context inputs
  - canonical Warbird lifecycle tables
  - training datasets
  - feature tables
  - label tables
  - training runs
  - metrics
  - SHAP artifacts
  - packet registry
  - activation and rollback history
- This local warehouse is not a mirror of cloud Supabase.
- Still banned:
  - local Supabase
  - Docker-local runtime
  - a third database

### 0.2 Cloud runtime boundary

- Cloud Supabase is runtime-only.
- Cloud contains only what must stay online for:
  - frontend and dashboard UX
  - indicator and alert runtime contract handling
  - operator monitoring
  - packet distribution
  - curated SHAP and report serving
- Cloud must not become a second warehouse.
- Any cloud object not whitelisted in `docs/cloud_scope.md` is retirement debt.

### 0.3 Runtime dependency rule

- Pine remains the canonical live signal surface.
- Cloud ingress must remain durable even if the local warehouse is temporarily unavailable.
- If local canonical write-through is delayed, cloud may queue, retry, and expose degraded runtime status, but it must not silently promote cloud intake rows into warehouse truth.
- The canonical write happens in local PostgreSQL only.

### 0.4 Training refresh rule

- Offline training and research rebuilds are on-demand only.
- No scheduled training-data refreshes.
- Approved triggers:
  - explicit research rebuild
  - explicit retrain run
  - explicit backfill command

### 0.5 Retention and contract rule

- The canonical trade object is the MES 15m fib setup.
- The canonical key is the MES 15m bar close in `America/Chicago`, derived deterministically from the ingress timestamp.
- Core retained history starts at `2020-01-01T00:00:00Z`.
- Pine emits the live candidate surface.
- AutoGluon is offline only and may publish only Pine-safe packet outputs.

### 0.6 Indicator-first and known-data-first dependency rule

- The indicator comes first.
- Pine defines the candidate object, the feature surface boundary, the stop-family semantics, and the minimum transport surface that every downstream system must honor.
- Local canonical schema, cloud published surfaces, extraction, labels, AutoGluon, packets, admin views, and runtime readers must be derived from the stabilized indicator contract, not invented ahead of it.
- Local canonical bootstrap is not complete until it contains known base data with explicit meaning, not just empty tables.
- Known base data means:
  - verified source
  - verified timeframe
  - verified symbology
  - verified retention floor
  - verified row presence
  - verified refresh ownership
  - explicit local-versus-cloud ownership
- No downstream phase may lock schema, readers, or AG surfaces against guessed indicator fields or guessed base data families.

### 0.7 AG feature engineering rule

- Do not export pre-composed scores to the AG training surface. Export primitive components only.
- AG discovers weights, thresholds, and interactions from primitive features. SHAP attributes importance to individual primitives.
- Pre-composed scores (such as composite confidence, impulse quality, shock, reversal, or exhaustion scores) may remain in Pine for chart-visual or debug display, but must NOT be exported as `ml_*` features or appear in the AG training matrix.
- Boolean features are acceptable only when the phenomenon is inherently binary (such as engulfing pattern detection). When a continuous measurement exists (such as volume ratio or regime score), export the continuous value and let AG find the threshold.
- Exhaustion is a mandatory first-class feature family. It must be built from proven technical analysis primitives — candlestick bar quality, momentum divergence, volume divergence, range compression, and centered MFI — not from untested third-party oscillators. No composite exhaustion score in Pine. AG learns the interaction.

### 0.8 Visual contract

- No chart-wide background color or regime tint on the indicator.
- The existing fib zone fill box (`.382–.618` zone) remains exactly as currently defined.
- The fib line color, width, label, and styling contract is locked:
  - Anchors (0, .50, 1.0): `#FFFFFF` white, width 1
  - Core zone (.382, .618): `#E65100` dark orange, width 1
  - Waypoints (.236, .786, 1.382, 1.50, 1.786): `#808080` mid-gray, width 1
  - Pivot (.50): `#FFFFFF` white, width 2
  - Targets (TP1, TP2, TP3): `#4CAF50` green, width 2
  - Stop loss: `#FF1744` red, width 2
  - Zone fill: `#FF9800` at 86% transparency, invisible border
- Any refactor of the indicator must preserve this exact visual output unless explicitly reapproved.

### 0.9 Alert architecture

- Candidate transport and operator signals are separate tiers.
- Tier 1 — structured candidate event from Pine: fires on every structural candidate at bar close. Feeds the ingress pipeline only. Not operator-visible. Transport is architecturally flexible and not locked to a specific Pine alertcondition primitive.
- Tier 2 — operator signal from server-side: fires only after AG promotes a candidate to TAKE_TRADE. Source is server-side scoring, not Pine. Operator sees only promoted signals.
- One manual TradingView webhook-alert setup step for Tier 1 transport is acknowledged and acceptable.

### 0.10 Operator confidence and table rule

- An operator-facing table or surface is required showing human-readable trade state:
  - Possible Reversal (exhaustion context active at fib level)
  - Open Trade (with entry price, SL, TP1, TP2)
  - Waiting For Next Trade (no active candidate or position)
  - Recent win/loss summary
- The confidence value displayed to the operator must come from calibrated AG packet output — specifically calibrated TP1/TP2/reversal probabilities from the active packet. It must NOT come from any Pine heuristic composite.
- PASS remains in the DDL as an internal scored-rejection code. It does NOT appear on the operator-facing chart surface.
- If this surface lives in Pine, it can only show Pine-local state. AG-backed confidence must be injected from the server-scored surface.

## 1. Documentation Authority Reset

### 1.1 Canonical documentation surfaces

- `docs/INDEX.md` is the only entrypoint.
- `docs/MASTER_PLAN.md` is the only planning authority.
- `docs/contracts/` is the only interface authority.
- `docs/cloud_scope.md` is the only cloud-whitelist authority.

### 1.2 Legacy document handling

Every other plan or decision document must be treated as one of the following:

- archived historical reference
- refactored into this master plan
- converted into a contract document under `docs/contracts/`

No new architecture plan, checkpoint plan, or sidecar decision note may be treated as authoritative unless it is linked from `docs/INDEX.md`.

## 2. Architecture Summary

### 2.1 Two-database architecture

- Local PostgreSQL warehouse
  - canonical normalized warehouse
  - owns the full lifecycle, training, features, labels, metrics, SHAP, packets, and historical zoo
- Cloud Supabase
  - minimal runtime ingress
  - curated frontend read models
  - packet distribution metadata
  - curated SHAP and report surfaces
  - operational health logging

### 2.2 Controlled one-way publish model

The allowed direction of truth is:

1. Pine or TradingView emits an alert to cloud ingress.
2. Cloud ingress validates and stores the minimum runtime intake record.
3. Cloud ingress forwards to the local canonical writer or queues a reliable retry.
4. Local canonical writer validates and writes authoritative normalized rows into local PostgreSQL.
5. Local publish jobs push a curated runtime subset back to cloud Supabase.

Cloud is not a canonical lifecycle store.

### 2.3 Required components

- Cloud ingress endpoint
  - Supabase Edge Function or approved Next.js API route
  - validates payload
  - records minimal intake and monitoring rows
  - forwards or queues for local canonical write
- Local canonical writer
  - validates contracts
  - writes canonical normalized tables
  - enforces idempotency
  - records reconciliation state
- Cloud publish job
  - publishes only curated read models, packet metadata, and curated SHAP or report outputs

## 3. Cloud Whitelist

Cloud is allowed to contain only these categories:

1. ingress tables
2. ingress idempotency and retry ledgers
3. runtime frontend read models
4. active packet distribution metadata
5. curated SHAP and report serving tables
6. operator-facing runtime aggregates
7. operational logs and health views

Anything else belongs in local PostgreSQL or on the external-drive file surface.

The enforceable whitelist lives in `docs/cloud_scope.md`.

## 4. Phased Correction Plan

The target architecture remains:

- local PostgreSQL is the intended canonical warehouse
- cloud Supabase is the intended curated runtime and published subset
- Pine is the intended canonical live signal surface
- AutoGluon is offline only
- the entire downstream stack is derived from the stabilized indicator contract plus known local base data

The 2026-04-07 audits proved that implementation does not yet match that target. The phases below are corrective and must be followed in order. Work may not skip ahead of a blocked earlier phase.

The plan-wide dependency order is:

1. stabilize and refactor the indicator
2. stand up local canonical with known base data
3. clean environment and ownership boundaries
4. reconcile cloud runtime truth
5. build ingress and canonical writer
6. build extraction, labels, and AG from canonical truth
7. publish the curated runtime subset
8. cut readers and retire drift

### Phase 0: Reality Lock, Drift Cleanup, And Contract Reconciliation

Purpose:

- stop doc drift
- stop environment drift
- stop plan execution against false assumptions
- reconcile contract vocabulary before any local canonical schema is hardened

Required work:

- treat `docs/INDEX.md`, this plan, `docs/contracts/`, and `docs/cloud_scope.md` as the only authority surfaces
- merge the active 2026-04-07 audit outputs into one baseline fact pattern
- move active audit artifacts under `docs/audits/`
- update `CLAUDE.md` so it reflects proven runtime truth only
- remove stale `2024` retention-floor references and stale forecast wording
- reconcile stop-family vocabulary to formula-specific IDs across all authority surfaces:
  - migrate the DDL enum from coarse category buckets (`FIB_INVALIDATION`, `FIB_ATR`, `STRUCTURE`, `FIXED_ATR`) to formula-specific IDs: `FIB_NEG_0236`, `FIB_NEG_0382`, `ATR_1_0`, `ATR_1_5`, `ATR_STRUCTURE_1_25`, `FIB_0236_ATR_COMPRESS_0_50`
  - each ID must bind to a deterministic stop formula so AG can compare specific stop placements, not generic categories
  - update `docs/contracts/stop_families.md`, `supabase/migrations/` (new migration), `lib/warbird/canonical-types.ts`, `WARBIRD_MODEL_SPEC.md`, and Pine implementation assumptions together in one pass
- mark legacy docs, scratch notes, and drifted implementation notes as reference-only

Exit criteria:

- authority docs match proven runtime truth
- stop-family vocabulary is unified before local canonical schema work begins
- no active authority doc claims local canonical is already live if it is not

### Phase 1: Indicator Contract, Logic Stabilization, And Export Refactor

Purpose:

- treat the indicator as the highest-priority production surface
- preserve the fib-engine-first system while turning the Pine contract from documentation into an implementable export design
- lock signal logic, candidate identity, feature surfaces, and export feasibility before local DB, cloud runtime, writer, or AG work proceeds

Required work:

- keep the fib engine as the base object and do not collapse the system into a generic ML signal emitter
- preserve the PowerDrill-reinforced repair order on the indicator side:
  - trigger-gate repair
  - stable candidate identity
  - export and payload design
  - then downstream writer and AG work
- prove confirmed-bar-only behavior on every entry, exit, and export path
- prove no-repaint behavior under replay and historical refresh
- verify that candidate identity is stable across reloads and repeat evaluations
- reconcile stop-family implementation in Pine with the unified contract vocabulary
- lock the indicator-defined feature and surface boundary before local canonical schema and AG extraction work proceed
- decide the export strategy under TradingView limits:
  - what remains internal-only
  - what is exported directly
  - what is emitted via alert payload
  - what must be reconstructed server-side
  - whether a companion script is required
- reduce, reallocate, or redesign the current output budget so contract-critical fields can move without relying on accidental headroom
- prove the exact minimal payload Pine can emit from the current indicator
- decide which contract fields are:
  - emitted directly by Pine
  - reconstructed server-side
  - deferred behind a companion script if required
- lock transport for:
  - version fields
  - identity fields
  - stop fields
  - gate decision fields
  - audit metadata
- define the exact idempotency-key construction path used by ingress and writer
- keep the following backtest truths explicit while refactoring the indicator:
  - 15m is currently losing
  - 1H is roughly break-even
  - 4H is the only profitable timeframe in the current strategy conversion
  - average loss is still roughly 2x average win across all tested timeframes
  - short-side performance is structurally weak

Phase 1 must be executed as explicit indicator workstreams, not as one blurred Pine cleanup pass.

#### Phase 1A: Swing Detection, ZigZag, And Fibonacci Geometry Lock

- Lock one production swing detector before any downstream schema or payload field names are hardened.
- Evaluate the repeated PowerDrill anchor family directly:
  - ZigZag deviation centered around `3x ATR`
  - ZigZag depth centered around `10`
  - pivot age maturity `>= 3 bars`
  - entry zone centered on `0.382-0.786`
  - `0.618` treated as the highest-confidence core zone
- Test the nearby regime-adaptive variants surfaced in PowerDrill instead of pretending one fixed value is already proven:
  - depth `8-12`
  - volatility-sensitive deviation around the equivalent of `2.5x-3.5x ATR`
  - high-volatility tightening vs low-volatility loosening
- Lock how sweep invalidation interacts with anchor formation:
  - if price breaks prior swing structure but closes back inside, reject the swing and reset directional state
  - require minimum spacing between pivots so micro-noise does not become trade structure
- Lock the long-vs-short asymmetry in the geometry instead of assuming mirrored fib behavior.

#### Phase 1B: Entry Bar Quality, Exhaustion Primitives, And Candidate Floor

Pine is a candidate generator. Its job is to emit every structurally valid fib setup at bar close. Filters that decide whether a candidate is worth trading belong to AG, not Pine.

Structural gates that remain in Pine (physics, not opinions):
- valid fib engine snapshot with non-degenerate range
- confirmed bar close (`barstate.isconfirmed`)
- direction from ZigZag swing sequence
- fib level touched within tracked retracement levels
- target viable (`>= 20pt` path to TP1)

Features exported for AG (not live Pine gates):
- entry bar quality: `body_pct`, `close_position`, `upper_wick_pct`, `lower_wick_pct`, `is_engulfing`
- exhaustion primitives: `price_velocity_atr`, `volume_velocity`, `atr_ratio_3_14`, `vol_price_corr_14`, `centered_mfi`, `range_compression`
- volume family: `vol_ratio`, `vol_acceleration`, `signed_vol`, `clv`
- all server-side computable from MES 15m OHLCV + volume — zero Pine plot budget cost

What Pine does NOT gate in the candidate-generator role:
- no volume gate (volume ratio is exported as a feature, not used as a trigger threshold)
- no body-percent filter gate
- no session-window blocking (session bucket is a feature and labeling dimension)
- no regime gating (regime score and components are features)
- no direction-specific rules (direction is a feature, AG learns asymmetry)

Validate the PowerDrill entry bar quality research as AG feature priors:
- engulfing, pin bar, rejection candle hierarchy (Fibonacci Trading System lake)
- body >= 65% threshold (PowerDrill Section 11.2)
- volume > 120% of 20-bar average baseline (PowerDrill Section 6.1)
- these are AG feature starting points, not Pine hardcoded gates

#### Phase 1C: PASS / WAIT / TAKE_TRADE And AE/MAE State Design

- Treat `PASS / WAIT / TAKE_TRADE` as a production state machine, not a UI label.
- Compare and collapse the competing PowerDrill policy families into one contract:
  - AE band state logic
  - MAE confidence / size logic
  - fib-zone scoring logic
- Validate the repeatedly proposed threshold families:
  - `PASS` for lowest-confidence, low-expectancy entries
  - `WAIT` for partial alignment requiring extra confirmation
  - `TAKE_TRADE` for high-conviction aligned entries
- Explicitly test the candidate threshold bands that keep appearing:
  - sub-`15%` adverse-excursion style low-conviction bucket
  - mid-band `15-35%` or similar `WAIT` bucket
  - `35-60%` or equivalent high-conviction bucket
- Lock whether AE/MAE state is:
  - pure indicator logic
  - server-reconstructed from exported primitives
  - or a hybrid where Pine emits only the minimal ingredients
- Lock one reason-bucket taxonomy so `PASS`, `WAIT`, and `TAKE_TRADE` always carry auditable cause codes.

#### Phase 1D: Stop-Loss Geometry, MAE-to-Risk, And Position Geometry

- Fix the current asymmetric R-multiple problem as a first-class indicator task.
- Evaluate the repeated stop-geometry proposals from PowerDrill:
  - fixed fib invalidation
  - compressed `0.236 fib + 0.5 ATR`
  - ATR-scaled structure stops
  - short-side-specific wider or differently anchored stops
- Lock one production stop family baseline for v1 and push alternatives into controlled A/B research.
- Define how MAE and MFE affect:
  - stop placement
  - sizing confidence
  - `PASS / WAIT / TAKE_TRADE`
  - later outcome analysis
- Do not let packet, schema, or writer work invent stop-family semantics before this phase resolves them.

#### Phase 1E: Regime, Intermarket, And Confluence As AG Features

Regime, intermarket, and confluence are AG training features, not Pine live gates. Pine computes and exports the raw regime and intermarket state for AG; AG decides what matters and at what thresholds.

- Export the regime score and its grouped components as separate AG features:
  - `leader_score` (NQ leadership)
  - `risk_score` (RTY, CL, HG risk appetite)
  - `macrofx_score` (6E, 6J macro-FX flow)
  - `exec_score` (VWAP, range expansion, efficiency)
- Export the 7 atomic intermarket states (NQ, RTY, CL, HG, 6E, 6J, SKEW) as individual signed features
- Export HTF confluence counts as AG features
- Pine may keep a visual regime state machine for chart display, but the regime state must NOT gate the candidate trigger
- The PowerDrill regime tradeoff data (Section 6.5: 1H trend → 58% WR, +VIX<20 → 61% WR, +NQ corr → 64% WR) is AG feature prior input, not Pine gate configuration
- SHAP determines which regime components actually matter and at what thresholds
- Session, time-window, VIX, and ATR regime context stay as exported features and labeling dimensions, not as live suppression rules

#### Phase 1F: Short-Side Recovery Program

- Treat short-side underperformance as its own repair track, not a parameter footnote.
- Validate the repeated short-side proposals from PowerDrill:
  - bearish HTF bias required
  - VIX-banded short rules
  - `0.382` short-zone preference
  - stronger volume confirmation
  - stronger structure or momentum confirmation
  - short-specific stop geometry
- Lock whether shorts remain continuation-focused, selective mean-reversion, or a narrowed failure-pattern class.
- Require short-side backtests and diagnostics to be reported separately from long-side metrics at every checkpoint.

#### Phase 1G: Execution Timing, Slippage, And Fill Model

- Lock one operational execution assumption set before downstream expectancy or AG labeling is trusted.
- Validate the entry timing tradeoff mined from PowerDrill:
  - immediate bar-close entry
  - delayed `2-5s` entry
  - market vs shallow limit offset
- Lock one fill and slippage model by session:
  - RTH `09:30-16:00 ET` execution boundary
  - session-aware slippage: `0.25pt` A-session, `0.50pt` lunch, `0.75pt` edge
  - fill formula: `fill = Close(trigger_bar) +/- cost(session)`
- Session and time are features and labeling cost dimensions, not live suppression rules:
  - no lunch suppression gate in Pine
  - no premarket suppression gate in Pine
  - session bucket is exported as an AG feature
  - slippage cost is baked into label construction, not into live trade gating
  - if SHAP determines lunch setups are unprofitable, that finding drives AG scoring, not a Pine hardcoded block
- Ensure all backtest interpretations and later ML labels are tied to the same execution and slippage model.

#### Phase 1H: Indicator Contract, Export Surface, And Alert Architecture

- Produce one explicit indicator contract document from the stabilized candidate-generator design.
- The Pine candidate payload must lock:
  - payload version and indicator version
  - symbol and timeframe
  - bar-close timestamp (UTC) — the ingress timestamp authority
  - direction and setup archetype
  - fib anchor high/low prices and timestamps
  - fib level touched
  - stop-family identity (formula-specific ID)
  - candidate idempotency key material
- The Pine candidate payload must NOT include:
  - `gate_decision` or `gate_reason_bucket` — these are AG-assigned after scoring, not Pine-emitted
  - pre-composed confidence, impulse, shock, or reversal scores
  - research-only confluence fields
  - any field that cannot be guaranteed point-in-time at confirmed bar close
- Implement the two-tier alert architecture (binding rule 0.9):
  - Tier 1: Pine emits a structured candidate event for every structural candidate at bar close. This feeds the ingress pipeline only.
  - Tier 2: Server-side scoring promotes candidates to TAKE_TRADE and emits operator-visible signals. Confidence comes from calibrated AG packet output.
- Anything not guaranteed point-in-time must either be removed from the Pine payload or explicitly marked as server-side reconstruction material.
- Prove the exact minimal payload Pine can emit within the TradingView plot/alert budget constraints.

#### Phase 1 Required Validation Harness

- Every Phase 1 subtrack must be validated with:
  - bar-close-only proof
  - no-repaint proof
  - side-separated long vs short metrics
  - timeframe-separated metrics
  - volatility-regime slices
  - session-window slices
  - explicit comparison of current baseline vs proposed rule family
- Candidate production defaults may be proposed during this phase, but Phase 1 does not close until one locked rule set exists for:
  - swing detector
  - entry bar confirmation (structural candidate floor, not a live gate)
  - fib zone
  - AG feature surface (volume, regime, session, and direction exported as features, not Pine gates)
  - PASS / WAIT / TAKE_TRADE state machine (PASS backend-only)
  - stop family baseline (formula-specific IDs)
  - short-side rules (direction as AG feature, AG learns asymmetry)
  - export contract and two-tier alert architecture

#### Phase 1 Contract Outputs

- This phase must end with exact locked artifacts, not just “indicator improved” language:
  - one indicator rule specification
  - one payload and transport specification
  - one stop-family baseline decision (formula-specific IDs)
  - one AG feature surface specification (volume, regime, session, direction as features)
  - one research-only field list
  - one candidate identity derivation
  - one validation report proving the rule set is stable enough for schema and writer work

Exit criteria:

- one stabilized indicator contract exists and is treated as the highest-priority upstream dependency
- confirmed-bar and no-repaint behavior are re-verified on the active indicator surface
- candidate identity is stable and reproducible from Pine output plus approved server-side reconstruction
- the feature/export surface is locked before local schema or AG extraction is finalized
- the export surface fits TradingView constraints without leaving contract-critical fields implied
- one implementable Pine payload design is locked
- ingress can deterministically construct or validate the candidate identity key

### Phase 2: Local Canonical Warehouse Bootstrap

Purpose:

- create and prove the real local canonical warehouse instead of treating it as documentation-only
- stand up the local canonical warehouse with known base data, not empty schema theater

Required work:

- choose and lock the canonical local database name
- create the local canonical database
- apply versioned canonical lifecycle schema there
- apply versioned packet, admin, and lifecycle-support schema there where required
- add and verify a local schema version ledger
- stand up and verify the required known base data families in local canonical:
  - MES base set:
    - `mes_1m`
    - `mes_15m`
    - `mes_1h`
    - `mes_4h`
    - `mes_1d`
  - econ base set:
    - retained active `econ_*` families required by the active contract
    - `econ_calendar`
    - other approved macro/context tables still in contract
  - cross-symbol base set:
    - retained intraday cross-symbol families required by the active indicator and AG plan
    - at minimum the currently locked basket and its approved timeframes
  - canonical lifecycle base set:
    - fib snapshots
    - candidates
    - outcomes
    - signals
    - signal and event lineage
    - training runs
  - packet base set:
    - packets
    - packet activations
    - packet metrics
    - packet feature importance
    - packet recommendations
    - packet setting hypotheses
- verify for each required local base family:
  - source of truth
  - timeframe
  - symbology
  - retention floor
  - row presence
  - refresh ownership
  - local vs cloud ownership boundary
- keep `/Volumes/Satechi Hub/warbird-pro/data/` as a companion raw/archive surface, not a second truth
- quarantine Rabid Raccoon overlap and block it from being treated as Warbird truth

Do not apply `scripts/ag/local_warehouse_schema.sql` as-is in this phase. That file is stale and must be regenerated from current contracts before any local research schema is relied on.

Exit criteria:

- one proven local canonical database exists
- versioned canonical lifecycle schema is applied there
- required MES, econ, cross-symbol, lifecycle, and packet base families exist with proven row reality
- each required local base family has explicit ownership, timeframe, retention, and source meaning
- Rabid Raccoon contamination path is documented and blocked

### Phase 3: Environment And Connection Hygiene

Purpose:

- stop local scripts and jobs from silently targeting the wrong database

Required work:

- remove dead Docker-local DB assumptions
- remove or replace hardcoded `54322` paths
- stop default cloud bleed in local scripts
- introduce explicit environment wiring for:
  - local canonical DB
  - cloud Supabase
- classify every active script and route as:
  - local only
  - cloud only
  - ambiguous and must be fixed

Exit criteria:

- no active script silently targets cloud when it is supposed to target local
- no active script depends on dead Docker-local DB ports
- every data-touching script has explicit environment ownership

### Phase 4: Cloud Runtime, Scheduler, And Published-Surface Reconciliation

Purpose:

- restore or explicitly redefine runtime ownership in cloud from live truth

Required work:

- verify cloud scheduler truth directly
- restore the required schedules if `cron.job` is empty and pg_cron remains the owning scheduler
- if scheduler ownership is changed away from pg_cron, update the authority docs first, including `AGENTS.md` and `CLAUDE.md`
- reconcile deployed function drift against repo ownership
- classify cloud objects into:
  - keep
  - change
  - retire
- keep only the cloud surfaces actually required for runtime and published serving, including:
  - MES and cross-asset runtime feeds still required by the active UI
  - published packet serving surfaces (curated subset of local packet truth):
    - `warbird_active_packet_summary_v`
    - `warbird_active_packet_metrics_v`
    - `warbird_active_packet_feature_importance_v`
    - `warbird_active_packet_recommendations_v`
    - `warbird_active_packet_setting_hypotheses_v`
  - operator-facing candidate and signal surfaces:
    - `warbird_admin_candidate_rows_v`
  - required job health and operator-monitoring surfaces
- packet ownership boundary:
  - local AG owns full packet build truth, training lineage, and complete packet registry (`warbird_packets`, `warbird_packet_activations`, `warbird_training_runs`, `warbird_training_run_metrics`, raw SHAP artifacts)
  - cloud owns only the published serving views derived from the active packet
  - full `warbird_packets` and `warbird_packet_activations` tables in cloud are retirement candidates — cloud should serve the published views only, not mirror local packet internals
- mark all cloud-only orphan deployments and out-of-scope warehouse surfaces as retirement debt unless explicitly re-owned

Exit criteria:

- scheduler truth is real and re-verified
- deployed cloud functions match repo ownership
- cloud keep/change/retire list is locked from live truth

### Phase 5: Minimum Ingress, Idempotency, And Live Canonical Write Path

Purpose:

- create the first real path from Pine alerts to canonical ingest-time truth

Required work:

- implement a real cloud ingress endpoint
- implement ingress storage families:
  - intake
  - idempotency ledger
  - conflict storage
  - retry and DLQ
  - ingress health
- implement the minimum canonical write ordering:
  - snapshot
  - candidate
  - signal and event lineage
- make failures visible instead of silent
- prove replay safety and conflict handling
- do not reuse legacy `detect-setups` or `score-trades` paths as canonical truth

Exit criteria:

- one Pine alert can produce one canonical local snapshot and candidate path
- replay is safe
- signal and event lineage is persisted
- cloud intake is not mistaken for canonical warehouse truth

### Phase 6: Post-Resolution Truth, Extraction, And Local AG Rebuild

Purpose:

- add resolved outcome truth after ingestion and replace the legacy cloud-bound workbench with a local-canonical training path

Required work:

- implement post-resolution scoring that persists outcome truth after ingest-time writes
- keep ingest-time truth separate from resolved outcome truth
- rewrite extraction to use canonical local tables only
- enforce the `2020-01-01T00:00:00Z` floor end-to-end
- remove retired table dependencies and legacy labels
- lock deterministic label generation against the active label contract
- regenerate the local research schema from current contracts before use
- rebuild the minimum AG path:
  - extract
  - label
  - train
  - evaluate
  - SHAP
  - packet
- keep Tier 1 packet features distinct from Tier 2 research-only features

Exit criteria:

- outcome truth is resolved after, not during, ingest-time canonical writes
- the local extractor no longer depends on legacy cloud warehouse tables
- the minimum AG run can complete locally with deterministic lineage

### Phase 7: Publish-Up And Curated Cloud Serving

Purpose:

- publish only the approved serving subset back to cloud after local truth exists

Required work:

- publish only approved runtime and packet/report surfaces back to cloud
- verify every published object against `docs/cloud_scope.md`
- keep cloud serving minimal and derived from local truth only

Exit criteria:

- cloud is serving a curated derived subset from local truth
- cloud is not drifting toward a second warehouse

### Phase 8: Dashboard And Admin Cutover

Purpose:

- move readers onto curated cloud runtime truth only after the canonical path is real

Required work:

- cut dashboard and admin readers away from retired legacy tables
- cut degraded legacy Warbird routes over to curated runtime surfaces
- fix known contract bugs in reader code, including ID typing drift
- ensure admin and dashboard surfaces reflect:
  - candidate stream health
  - runtime freshness
  - packet state
  - curated model and report summaries

Exit criteria:

- active readers no longer depend on dropped legacy Warbird tables
- dashboard and admin surfaces operate from curated runtime truth only

### Phase 9: Retirement And Enforcement

Purpose:

- remove stale surfaces and prevent the same drift from reappearing

Required work:

- retire out-of-scope cloud tables and functions in approved order
- retire stale extractor and prediction scripts
- retire dead legacy comments, copy, and helper paths
- enforce review checks so new schema or runtime surfaces cannot bypass:
  - contracts
  - cloud scope
  - migration policy
  - environment ownership

Exit criteria:

- stale warehouse debt is retired
- local/cloud boundaries are enforced
- plan drift is materially reduced

## 5. Blocking Rule

Implementation may not skip ahead of blocked phases.

The entire plan inherits two non-negotiable dependencies:

1. indicator-defined surfaces come before schema, writer, and AG assumptions
2. known local base data comes before extraction, training, packet, admin, or reader work

The minimum blockers before feature implementation resumes are:

1. one stabilized indicator contract with locked stop-family and export design
2. one proven local canonical database
3. one corrected environment and connection model
4. one restored or explicitly redefined cloud scheduler/runtime truth
5. one minimum ingress plus idempotent canonical writer
6. one local extractor and AG path aligned to canonical outcomes and the 2020 retention floor

## 6. Non-Negotiable Outcome

Warbird is complete only when:

- local PostgreSQL is the single canonical warehouse
- cloud Supabase is reduced to the strict curated runtime subset
- Pine emits the live contract from a stabilized, no-repaint, contract-compliant indicator surface
- local canonical writes are idempotent and auditable
- resolved outcome truth is scored after ingest-time writes, not collapsed into the same step
- AutoGluon trains locally from canonical local truth
- published packets and curated SHAP/report surfaces are served safely from cloud
- cloud can no longer drift back into a second warehouse
