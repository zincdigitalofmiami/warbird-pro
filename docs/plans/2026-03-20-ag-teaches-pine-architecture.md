# Warbird Pro — AF Struct+IM Indicator Plan

**Date:** 2026-03-20
**Status:** Active Plan — Single Source of Truth
**Scope:** MES 15m fib-outcome contract: indicator + dashboard operator surface + AG training pipeline
**PowerDrill research baseline:** `docs/research/2026-04-06-powerdrill-findings.md` — 57-artifact synthesis: backtest diagnosis, trigger gate spec, stop families, regime filters, ML packet design.

**THIS IS THE ONLY PLAN TO UPDATE.**

- All architecture changes, implementation phases, UI decisions, and status updates for this indicator live in this file.
- Do not create new architecture or plan docs for this indicator without explicit approval.
- All other plan docs are archived under `docs/plans/archive/`.

Historical note: any remaining references below to the paired strategy, parity-only checkpoints, or Deep Backtesting are archived execution history unless a newer update-log entry explicitly reactivates them.

Historical retention note: cloud runtime storage stays lean and runtime-driven, while the external-drive local PostgreSQL warehouse plus the external-drive `/data/` archive extend to `2020-01-01T00:00:00Z` for offline AG training depth, covering COVID crash, recovery, inflation cycle, and rate hike cycle.

Binding note: the 2026-03-28 update-log entries supersede older references below to right-side TradingView tables, `LONG READY` / `SHORT READY` action labels, dashboard-local fib computation, Markdown report blobs, and any schema language that still treats `EXPIRED` / `NO_REACTION` as canonical economic model truth.

### Next Blocking Order (2026-03-31 updated — fib engine hardening complete)

1. ~~**Pine indicator recovery**~~ — **DONE.** v7 institutional upgrade complete (commit `fe51412`).
2. ~~**v7 institutional upgrade**~~ — **DONE.** Flow-based intermarket, grouped regime scoring, ES execution quality. 64/64.
3. ~~**Intermarket pivot to CME Globex**~~ — **DONE.** NQ/RTY/CL/HG/6E/6J replace TICK/VOLD/VVIX/VIX/VIX3M/HYG. Leadership/Risk-appetite/Macro-FX/Exec regime groups. 60 plot + 3 alert = 63/64 (1 headroom). 11 security calls. Commit `6f3e7a6`.
4. ~~**Fib engine hardening**~~ — **DONE.** Commit `4a25806`. Three changes: (a) direction logic replaced midpoint-hysteresis with ZigZag swing-sequence — fibBull only changes on confirmed pivots, eliminates spurious flips; (b) HTF directional agreement gate — 1H/4H security tuples expanded to `[high, low, close, ema21]` (0 extra calls), entry triggers gated on `htfDirAgrees`; (c) exhaustion diamond visual via `label.new()` with `label.style_none` + `"◆"` at fib zone interaction. Plot budget unchanged at 63/64. Anchor quality, left/right bar space, anchor-span visual gap, and waypoint lines (1.382/1.50/1.786) confirmed correct — no changes needed. Forensic review passed. Known residual: `htfDirAgrees` gates alerts only, not the trade state machine (pre-existing architecture split). Header comments (HTF tuple shape, no-repaint audit date) are stale — documentation-only nits.
5. **Canonical writer checkpoint** — port or replace the legacy `detect-setups` / `score-trades` Vercel routes as Supabase Edge Functions that write to the reconciled canonical tables. Fix CME continuity-gap handling before calling the writer live.
6. **Dashboard/admin/API reader cutover** — cut `/admin`, `/api/admin/status`, and dashboard consumers off legacy tables and onto the canonical snapshot/candidate surfaces plus the new Admin packet views. TradingView webhook alerts (entry long, entry short, pivot break reversal) can drive real-time dashboard state via Supabase Edge Function webhook receiver.
7. **Local warehouse / selector buildout** — stand up the AG workbench (`scripts/ag/*`), the external-drive local PostgreSQL training warehouse, the `/data/` raw/archive surface, diagnostic tables, and the packet publish-up lifecycle. Do not build a full cloud mirror.
8. **Legacy table retirement** — drop `warbird_triggers_15m`, `warbird_conviction`, `warbird_risk`, `warbird_setups`, `warbird_setup_events`, `measured_moves`, `warbird_forecasts_1h` only after all readers/writers are migrated.

Runtime-truth gate (2026-03-31, updated after Checkpoint 1): migration `20260331000045` is now reconciled and replay-verified, but phases 5-7 remain blocked. Do not proceed with canonical writer design, dashboard/admin cutover, schema/table recording design, action/event recording design, or local training buildout from a narrow `candidates + signals + outcomes` framing. The active plan already requires a larger contract: point-in-time setup truth, realized path truth, published signal lineage, and a distinct explanatory/research layer. Admin page assumptions, schema assumptions, and action/event recording assumptions must be re-audited against the plan before Checkpoint 2 resumes.

Runtime-safety checkpoint (2026-03-31 locked): `/api/warbird/dashboard`, `/api/warbird/signal`, and `/api/warbird/history` now run an explicit service-role runtime guard before touching the stale legacy reader path. When the legacy reader objects are absent, the routes return `200` with an explicit `runtime` degradation payload instead of throwing `500`s, and the dashboard surfaces that degraded state visibly. This is containment only. It is not the step-6 reader cutover, and it does not change the requirement that canonical rows must exist before reader migration is claimed complete.

MES minute-efficiency checkpoint (2026-03-31 locked in repo): the `mes-1m` Edge Function now treats the last closed minute boundary as the incremental cutoff and filters out the current in-progress 1m bar before persistence. This removes the alternating `SUCCESS` / `SKIPPED no_gap` churn caused by writing partial current-minute bars, while preserving the minute cron cadence and the 1m-driven forming 15m chart path.

---

## Reset Context — Why We're Here (2026-04-07)

This section records the causal chain that produced the current blocking order. Future agents must understand this or they will make the same wrong turns.

### The original problem

The project was built on the wrong foundations:

- **Wrong database location** — training and development was running against the wrong Postgres instance (cloud Supabase, Docker, and local machine were all conflated)
- **Wrong training location** — no clean separation between the production system of record and the offline training environment
- **Wrong tools** — the toolchain assumed a live-inference server model; the architecture needed to be offline-only AG with a Pine-safe packet

Everything needed a reset.

### The decision: external drive PostgreSQL

The decision was made to put the training PostgreSQL database on the external Satechi drive — not Docker, not the local machine internal disk, not cloud Supabase. This gives a clean dedicated offline training warehouse that survives machine restores and stays physically separate from production.

### The blocker: can't design the warehouse without knowing what we need

As soon as the warehouse move was scoped, a deeper blocker surfaced: **we cannot design the schema, table structure, or data requirements for the training warehouse until we know what the canonical candidate object actually is.** You can't build the warehouse for data you haven't defined.

### The dependency: the indicator defines the schema

To define the canonical candidate object, we had to look at the indicator — because Pine is the canonical signal surface. The indicator defines what a setup IS. The schema follows from that.

### The discovery: the indicator was broken

When we looked at the indicator closely and ran backtests on TradingView, the results were bad across all timeframes:

- 15m: PF 0.903, -8.46%, 374 trades — losing money
- 1H: PF 0.995 — essentially flat
- 4H: PF 1.192 — marginally profitable, but only longs work (PF 2.243). Shorts bleed everywhere (PF 0.731).

The root causes (documented fully in `docs/research/2026-04-06-powerdrill-findings.md`):

- Stop-lock bug: `strategy.exit()` used live-recalculating fib prices instead of locked entry prices — stops drifted silently mid-trade
- Trigger bar laxity: no body filter, no RSI gate, volume threshold too loose — the system took any weak fib touch
- Structural stop geometry: avg loss was 2× avg win across all timeframes; the -0.236 fib extension stop doesn't adapt to volatility
- Short side broken: directionally asymmetric in ways the indicator didn't account for

### The correct sequence

This is why the blocking order looks the way it does:

```
Fix the indicator first
  → defines what a valid candidate actually IS
  → defines what data the training warehouse needs to store
  → defines what schema the canonical tables need
  → enables the canonical writer to be built correctly
  → enables AG to train on clean, well-defined candidates
  → enables the dashboard to mirror real engine state
```

**Nothing downstream of Pine can be correctly built until the indicator produces valid, reliable candidates.** The warehouse schema, the canonical writer, the AG training pipeline, and the dashboard reader cutover all depend on knowing what the indicator is actually saying.

The PowerDrill research session (2026-04-06) produced the diagnosis and fix specifications. The implementation specs live in `docs/research/2026-04-06-powerdrill-findings.md` Section 11. The three fixes (stop-lock, trigger gate, ATR stop toggle) are the current pre-Step-5 gate.

## PowerDrill Consolidated Execution Sequence (2026-04-07)

This section consolidates the active plan, the 2026-04-06 PowerDrill findings, the canonical schema drafts, and the current repo/runtime reality into one execution order. Use this section to sequence work across Pine, cloud Supabase, the local training warehouse, and the AG publish-up path. If a subordinate plan or scratch note disagrees with this section, this section wins immediately.

### Current Repo-Truth Blockers

These blockers were re-verified from the repository before writing this sequence:

- the pre-Step-5 PowerDrill strategy repairs are still open on `indicators/v7-warbird-strategy.pine`; `strategy.exit()` still uses drifting `slLevel` / `tp1Level` / `tp2Level` instead of the locked `slPrice` / `tp1Price` / `tp2Price`
- the legacy writer surfaces still target dropped or retired schema:
  - `app/api/cron/detect-setups/route.ts` still reads `trump_effect_1d`, `econ_vol_1d` and writes `warbird_triggers_15m`, `warbird_conviction`, `warbird_risk`, `warbird_setups`, `warbird_setup_events`, `measured_moves`
  - `app/api/cron/score-trades/route.ts` still reads and writes `warbird_setups`, `warbird_setup_events`, `measured_moves`
  - `lib/warbird/queries.ts` still reads the same legacy Warbird tables
- the local ML workbench surface is not built yet; `scripts/ag/` currently contains only `local_warehouse_schema.sql`
- the current local dataset/training scripts are still bridge assets, not the target Phase 4 implementation:
  - `scripts/warbird/build-warbird-dataset.ts` still depends on retired sources such as `news_signals`, `trump_effect_1d`, and `warbird_setups`
  - `scripts/warbird/train-warbird.py` still trains against legacy local-only target names
- local warehouse direction has conflicting subordinate docs; the active contract for the end-state remains:
  - cloud Supabase = lean runtime canonical store, not a mirror
  - external-drive local PostgreSQL = heavy offline training/feature warehouse
  - external-drive `/data/` = raw snapshots, parquet archives, datasets, manifests, and AG run artifacts feeding the local warehouse
  - local Docker Supabase is not part of the active local contract; direct checks on 2026-04-07 showed port `54322` closed, `psql` connection refused, and Docker daemon unavailable

### Phase 0: Contract And Storage Freeze

Purpose:

- freeze the MES 15m fib contract before any more writer, admin, or training buildout
- freeze cloud runtime vs local training responsibilities
- prevent the project from drifting back into `candidates + signals + outcomes` shorthand or mixed cloud/local assumptions

Entry criteria:

- active plan, `CLAUDE.md`, `WARBIRD_MODEL_SPEC.md`, and `docs/research/2026-04-06-powerdrill-findings.md` re-read
- migration `20260331000045` remains reconciled and replay-verified

Deliverables:

- canonical contract restatement: `fib_engine_snapshot -> candidate -> outcome -> decision -> signal`
- explicit storage boundary restatement:
  - cloud Supabase owns runtime truth, symbol registry, operator surfaces, canonical signal state, and publish-up views
  - the external-drive local PostgreSQL warehouse owns deep historical OHLCV, feature engineering, labels, folds, experiments, and AG artifacts
  - the external-drive `/data/` root owns raw batch exports, parquet snapshots, manifests, and run outputs that feed the local warehouse
  - local Docker Supabase is not the active local data surface and must not be used as shorthand for local truth
- audited inventory of all legacy writer and reader dependencies that must be removed

### Data Residency Matrix (Locked 2026-04-07)

Cloud Required:

- `symbols`, `symbol_roles`, `symbol_role_members`
- runtime-required market/context tables and slices used by Pine support surfaces or dashboards
- canonical Warbird runtime truth:
  - `warbird_fib_engine_snapshots_15m`
  - `warbird_fib_candidates_15m`
  - `warbird_candidate_outcomes_15m`
  - `warbird_signals_15m`
  - `warbird_signal_events`
- packet publish-up and operator views:
  - `warbird_training_runs`
  - `warbird_training_run_metrics`
  - `warbird_packets`
  - `warbird_packet_activations`
  - `warbird_packet_metrics`
  - `warbird_packet_feature_importance`
  - `warbird_packet_setting_hypotheses`
  - `warbird_packet_recommendations`
  - compat/admin views derived from them

Local Required:

- external-drive PostgreSQL database `warbird_training`
- deep OHLCV history
- wide feature tables
- label tables, folds, diagnostics, SHAP outputs, and experiment tables
- AG artifacts and run manifests on the external drive

Published / Promoted Only:

- versioned packet rows
- run metrics and curated publish-up summaries
- activation / rollback records

Rules:

- Supabase is not a full mirror of the local warehouse
- local PostgreSQL is not a second runtime environment
- recurring cloud ingestion is justified only for runtime-critical datasets
- training-only refreshes remain explicit batch rebuilds

Exit gate:

- no open ambiguity remains about the canonical key, outcome vocabulary, or cloud/local boundary

Risk gate:

- stop immediately if any proposed schema, API, or dashboard path collapses the contract back into a narrow legacy table story

### Phase 1: PowerDrill Entry-Surface Repair

Purpose:

- finish the pre-Step-5 gate by fixing the strategy/backtest surface that defines what a valid candidate is

Scope:

- apply and re-test the PowerDrill Section 11 repairs on `indicators/v7-warbird-strategy.pine`
- keep the live indicator contract aligned with the resulting candidate semantics

Required work:

- fix the stop-lock bug so exits use the frozen entry-time prices
- add the four-factor trigger gate and bar-close acceptance requirement
- add the bounded ATR stop-family toggle for comparative testing
- keep `PASS` / `WAIT` / `TAKE_TRADE` as the policy vocabulary and preserve long/short asymmetry as a first-class test axis

Deliverables:

- a clean pre/post backtest comparison against the 2026-04-06 baseline
- documented trade-count, win-rate, PF, and loss-geometry changes on `15m`
- narrowed stop-family decision set for later AG admission

Exit gate:

- one candidate definition is selected as the post-PowerDrill baseline for writer design

Risk gate:

- do not start canonical writer work while the strategy surface still has drifting exits or unresolved candidate semantics

### Phase 2: Canonical Cloud Schema And Writer Cutover

Purpose:

- replace the legacy cron-owned writer path with canonical recording against the reconciled cloud schema

Scope:

- activate and use the canonical table families defined in migrations `037` and `038`
- move writer behavior into Supabase-owned paths only: Edge Functions and the TradingView webhook receiver

Required work:

- port or replace `detect-setups` and `score-trades` as canonical writers
- record frozen fib snapshots, candidates, outcomes, decisions, published signals, and signal events
- preserve idempotency on the natural contract key
- fix CME continuity-gap handling before any writer is called live
- keep cron auth, `maxDuration = 60`, `job_log`, and RLS discipline intact

Deliverables:

- runtime writers that write only to:
  - `warbird_fib_engine_snapshots_15m`
  - `warbird_fib_candidates_15m`
  - `warbird_candidate_outcomes_15m`
  - `warbird_signals_15m`
  - `warbird_signal_events`
- direct DB verification that the canonical objects exist in the environment being claimed
- removal of all writer dependence on retired sources such as `trump_effect_1d`, `news_signals`, `warbird_setups`, and `measured_moves`

Exit gate:

- the cloud runtime can produce canonical rows without touching any legacy Warbird operational table

Risk gate:

- no writer claim is valid until direct DB checks prove the target tables, constraints, and views exist in the exact environment being tested

### Phase 3: Dashboard, Admin, And API Reader Cutover

Purpose:

- migrate every reader surface off the stale legacy tables and onto the canonical views plus packet publish-up views

Scope:

- `/admin`
- `/api/admin/status`
- `/api/warbird/dashboard`
- `/api/warbird/signal`
- `/api/warbird/history`
- dashboard realtime consumers

Required work:

- rewire readers to canonical snapshot/candidate/outcome/signal views
- keep TradingView as the signal source and the dashboard as the render surface
- keep the dashboard from recomputing fib geometry locally
- surface packet metrics, feature drivers, setting hypotheses, and recommendations via structured publish-up views only

Deliverables:

- reader cutover to `warbird_admin_candidate_rows_v`, `warbird_active_signals_v`, and the active packet/training views
- webhook-to-Realtime path functioning for live dashboard updates
- removal of runtime degradation as the normal operating path

Exit gate:

- the operator surfaces render the canonical stored engine state and no longer depend on legacy Warbird tables

Risk gate:

- do not publish fallback aliases for deleted outcome names or legacy table semantics on new reader surfaces

### Phase 4: Local Training Warehouse And Feature Pipeline

Purpose:

- stand up the offline training store and feature pipeline required for AG without reintroducing cloud/local confusion

Scope:

- build the local PostgreSQL warehouse as the explicit offline research/training surface on the external drive, fed by explicit exports and local raw archives instead of full cloud mirroring
- treat Databento batches, TradingView exports/capture, and verified cloud snapshots as source inputs, not as the final training contract themselves

Required work:

- create the durable local training store for the Phase 4 entities already named in this plan, including:
  - source snapshot surfaces for MES, cross-asset, and approved daily context
  - research child tables from `scripts/ag/local_warehouse_schema.sql`
- build the source-loading and feature-computation path under `scripts/ag/*`
- normalize all joins to the MES 15m bar-close contract
- keep `cross_asset_1h` / `cross_asset_1d` as the minimum locked basket training surfaces until SHAP clears any lower-timeframe expansion

Deliverables:

- working Phase 4 scripts for:
  - loading source snapshots
  - building fib snapshots
  - building the canonical training dataset
  - computing features
- a verified local PostgreSQL warehouse with 2020-forward retained history and no reliance on repaint-prone live chart reads

Exit gate:

- the local PostgreSQL warehouse can build a deterministic training dataset from canonical point-in-time export snapshots plus approved local-only research tables

Risk gate:

- no recurring cloud-to-local sync layer
- no training truth sourced from local dashboard recomputation
- no `cross_asset_15m` or `cross_asset_1m` expansion before the first SHAP pass proves it is warranted

### Phase 5: AutoGluon Training, Evaluation, And Packet Publish-Up

Purpose:

- train the offline selector and publish a Pine-safe packet only after the candidate and warehouse contracts are stable

Required work:

- train the staged baseline in this order:
  1. fib + event-response + TA core pack baseline
  2. parameter admission inside surviving feature families
  3. joint configuration on surviving feature families only
- treat TP1, TP2-conditional, and runner-quality as separate learning problems where required by the data
- generate a compact, versioned packet with bounded stop-family decisions, calibrated bucket outputs, and publish-up metadata

Deliverables:

- `warbird_training_runs`
- `warbird_training_run_metrics`
- `warbird_packets`
- `warbird_packet_activations`
- `warbird_packet_metrics`
- `warbird_packet_feature_importance`
- `warbird_packet_setting_hypotheses`
- `warbird_packet_recommendations`

Exit gate:

- at least one packet candidate exists with stable sample counts, calibration evidence, and documented fallback-bucket coverage

Risk gate:

- AutoGluon remains offline only
- packet refresh remains batch-promoted, not live-served
- AG chooses among the bounded stop family; it does not emit arbitrary per-trade stop floats

### Phase 6: Integration, Walk-Forward Validation, And Legacy Retirement

Purpose:

- prove the end-to-end path works and only then remove the dead legacy surfaces

Required work:

- verify the full live path:
  - Pine alert
  - webhook receiver
  - canonical cloud write
  - Realtime push
  - dashboard render
- run out-of-sample and walk-forward validation against the post-PowerDrill baseline
- promote only additive changes over the fib + event-response baseline
- retire legacy tables only after all readers and writers are migrated

Deliverables:

- end-to-end validation report
- promoted or rejected packet decision with reasons
- legacy retirement migration for:
  - `warbird_triggers_15m`
  - `warbird_conviction`
  - `warbird_risk`
  - `warbird_setups`
  - `warbird_setup_events`
  - `measured_moves`
  - `warbird_forecasts_1h`

Exit gate:

- the canonical path is live, validated, and the legacy path is fully removable

Risk gate:

- if walk-forward validation fails, leave the packet unpromoted and keep the legacy retirement blocked

---

## Update Log

See [update-log.md](update-log.md) for the full historical record.

---

<!-- Supabase Edge Cutover Guardrails (completed) + Security Remediation (completed) → archived 2026-03-31 -->

---

## Canonical Goal

Deliver the best possible **fib continuation/reversal entry indicator** on TradingView for MES, with:

- actionable entries on chart
- TP1 (1.236 extension) and TP2 (1.618 extension) path visualization
- an early-warning exhaustion diamond that can lead a later trigger by a few bars
- a mirrored dashboard operator surface that renders the same fib engine state with probabilities, audit stats, and richer cross-asset visuals than Pine can support
- AG used aggressively to improve it offline
- manual chart validation plus point-in-time dataset checks used to prove it

The goal is canonical. Whatever it takes to get there is what we do.

---

## Canonical Outputs (split by surface)

These are the required outputs. Each must map to a defined calculation. Each must come from real data.

### TradingView / Pine

| Output | Definition |
|--------|-----------|
| **Entry marker** | Exact bar where the indicator publishes a trade signal at a fib pullback level |
| **Decision state** | `TAKE_TRADE`, `WAIT`, or `PASS` for the current candidate. This is a policy decision, not a realized outcome. |
| **Target eligibility** | 20pt+ pass/fail |
| **Stop level** | From a bounded, deterministic stop family — not a per-trade model output |
| **TP1 / TP2 levels** | The 1.236 and 1.618 fib extension prices |
| **Fib / pivot / zone lines** | The operator-visible execution geometry from the canonical fib engine, rendered with the operator-approved colors, line widths, line styles, and level labeling contract |
| **Exhaustion diamond** | A precursor visual that can warn ahead of a later trigger when exhaustion context is active at a fib or pivot interaction |
| **Re-entry signal** | When a pullback after TP1 is a continuation opportunity |

### Dashboard / Operator Surface

| Output | Definition |
|--------|-----------|
| **TP1 probability** | Probability the current setup reaches the 1.236 fib extension. Must be defensible and calibrated — when it says 70%, it should be right about 70% of the time. |
| **TP2 probability** | Probability the current setup reaches the 1.618 fib extension. Same calibration standard. |
| **Reversal risk** | Probability that the continuation fails into a reversal or shock-failure path. |
| **Win rate** | Historical hit rate for the current setup bucket (fib level, regime, session, direction). Based on real backtested data, not a guess. |
| **Stats window** | What history/regime/sample the displayed numbers are based on |
| **MAE / MFE context** | Expected and bounded excursion context used to support the displayed probabilities |
| **Decision reasons** | Why the policy is currently `TAKE_TRADE`, `WAIT`, or `PASS` |
| **Cross-asset visuals** | Time-synced operator charts and regime state that Pine cannot carry as chart tables |

---

## Canonical Standards

1. Every stat on the chart must come from real data — never mocked, never fabricated.
2. Every probability/win rate must be defensible and calibrated.
3. Whatever appears in TradingView or the dashboard must map to a defined calculation.
4. Pine must remain the visible production surface.
5. AG is offline only — never in the live signal path.
6. The dashboard may be visually richer than Pine, but it must render the same canonical fib engine state rather than compute a second fib engine locally.
7. Visual chart validation and local point-in-time dataset checks must agree closely enough before a fib or trigger mechanic is trusted.
8. The operator-approved fib presentation is a visual contract. Colors, line thicknesses, line styles, and level-label presentation may not change without explicit approval.
9. Deep Backtesting and paired-strategy parity are optional research tools only; they are not active blockers for the indicator path unless explicitly reopened.
10. **NEVER hand-roll code when a working implementation exists.** Copy the exact working code. Adapt the interface, not the internals. If you can't explain why your version differs line-by-line, you don't understand it well enough to rewrite it. Hand-rolled library integrations produce broken signals that poison AG training data.

---

## Hierarchy Lock (2026-03-28)

This hierarchy is now binding for the active path:

1. **Trading objective**
   - improve MES 15m fib-based entries so more valid setups reach TP1 / TP2 and fewer low-quality entries stop out
2. **Canonical trade object**
   - one frozen MES 15m fib candidate at bar close
3. **Truth contract**
   - the primary economic questions are extension attainment versus stop failure on that frozen candidate
   - unresolved rows remain `OPEN` until they resolve; `OPEN` is operational-only and excluded from training labels
4. **Canonical schema**
   - stores point-in-time setup truth, realized path truth, and published signal lineage
5. **Feature / research layer**
   - stores explanatory and experimental context that may change over time
6. **Model stack**
   - selected to answer the truth contract, not to redefine it

Warbird is split into three engines:

- **Generator**
  - Pine and admitted exact-copy harnesses define the candidate entry object
- **Selector**
  - offline models score whether a candidate is worth taking
- **Diagnostician**
  - local research explains why trades won/lost and what should change in features, settings, or entry definition

Boundary rules:

1. Canonical cloud tables must not become feature soup.
2. SHAP outputs, ablation results, stop-out attribution, and parameter-search artifacts are research-only until explicitly promoted.
3. AutoGluon is the first selector layer. It is not the owner of the canonical schema.
4. Quantile/pinball models are for excursions and uncertainty bands, not primary extension-hit truth.
5. Monte Carlo is downstream policy simulation, not label definition.
6. Volatility sidecars such as GARCH are optional feature families that must earn inclusion through lift and stability evidence.

---

## Locked v1 Mechanisms

The chart-output surface is canonical. The v1 mechanism for producing those outputs is now locked.

### Primary v1 delivery path

Use a **hybrid Pine + AG packet** architecture:

1. Pine computes the canonical adaptive fib engine snapshot, candidate state, precursor visuals, and the deterministic `confidence_score` from current bar context.
2. AG trains offline on point-in-time fib engine snapshots, calibrates the score, and produces a Pine-ready packet of:
   - score-to-probability mappings
   - win-rate tables
   - reversal-risk tables
   - stop-family decisions
   - module keep/remove calls
   - exact Pine input values
3. Pine renders only the execution-facing chart surface:
   - fib / pivot / zone lines
   - entry markers
   - bounded stop and target levels
   - exhaustion precursor diamond
   - alertconditions
4. The dashboard renders the operator-facing stats and visuals by:
   - identifying the current setup bucket
   - identifying the current confidence bin
   - looking up the calibrated TP1 / TP2 / reversal / win-rate stats from the latest promoted packet
   - rendering cross-asset and sentiment views from the same MES 15m contract

This is the primary v1 path.

### Allowed fallback

If the full bucketed calibration surface is too sparse in early testing, the fallback is:

- Pine-embedded probability bands keyed off fewer variables
- coarser confidence bins
- coarser bucket hierarchy

Fallback is allowed only if it preserves defensible calibration and real sample counts.

### Update cadence

The packet update cadence for v1 is:

- offline retrain / recalibration on demand during development
- promoted packet refresh no more than once per week in normal operation

No intraday live model serving.

### Locked dashboard-stat formulas

These definitions are canonical for v1:

- `confidence_score`
  - deterministic Pine score on a `0-100` scale computed from live Pine features and rules
- `tp1_probability_display`
  - empirical TP1 hit rate for the current `setup_bucket x confidence_bin`, calibrated offline by AG
- `tp2_probability_display`
  - empirical TP2 hit rate for the current `setup_bucket x confidence_bin`, calibrated offline by AG
- `reversal_risk_display`
  - empirical `REVERSAL` rate for the current `setup_bucket x confidence_bin`
- `win_rate_display`
  - empirical rate of `TP1_ONLY OR TP2_HIT` for the current `setup_bucket x confidence_bin`
- `stats_window_display`
  - training date range + sample count used for the displayed bucketed stats

### Locked bucket hierarchy

#### Confidence bins

Use 5 bins for v1:

- `BIN_1 = 0-19`
- `BIN_2 = 20-39`
- `BIN_3 = 40-59`
- `BIN_4 = 60-79`
- `BIN_5 = 80-100`

#### Setup bucket key

The primary bucket key is:

- `direction`
- `setup_archetype`
- `fib_level_touched`
- `regime_bucket`
- `session_bucket`

#### Setup archetype values

Use these v1 archetypes:

- `ACCEPT_CONTINUATION`
- `ZONE_REJECTION`
- `PIVOT_CONTINUATION`
- `FAILED_MOVE_REVERSAL`
- `REENTRY_AFTER_TP1`

#### Regime bucket values

Use these v1 regime buckets:

- `RISK_ON`
- `NEUTRAL`
- `RISK_OFF`
- `CONFLICT`

#### Session bucket values

Use these v1 session buckets in `America/Chicago`:

- `RTH_OPEN = 08:30-09:30`
- `RTH_CORE = 09:30-11:30`
- `LUNCH = 11:30-13:00`
- `RTH_PM = 13:00-15:00`
- `ETH = all other bars`

### Locked bucket fallback ladder

If the current `setup_bucket x confidence_bin` does not meet the minimum sample floor, Pine must walk this fallback ladder:

1. `direction x setup_archetype x fib_level_touched x regime_bucket x session_bucket x confidence_bin` with `n >= 40`
2. `direction x fib_level_touched x regime_bucket x session_bucket x confidence_bin` with `n >= 60`
3. `direction x fib_level_touched x regime_bucket x confidence_bin` with `n >= 80`
4. `direction x fib_level_touched x confidence_bin` with `n >= 120`
5. `direction x confidence_bin` with `n >= 200`
6. global confidence-bin baseline

If even the final fallback is under-sampled, Pine must display `LOW SAMPLE` and suppress the stat as actionable.

### Stop logic — bounded Pine-implementable family

AG does NOT invent a per-trade stop. AG chooses among a **bounded family** of deterministic stop methods that Pine can implement:

1. Fib invalidation (break below the fib level touched)
2. Fib invalidation + ATR buffer
3. Structure breach (break of swing low/high)
4. Fixed ATR multiple from entry

AG's job: evaluate which stop family member works best for which fib level / regime, and output that as a Pine config decision. Not a learned float.

---

## Scope (updated 2026-03-27)

This plan covers the full MES 15m fib-outcome contract:

- the live Pine indicator (`indicators/v6-warbird-complete.pine`)
- the mirrored dashboard operator surface (render-only consumer of the canonical fib engine state)
- the canonical Supabase schema for snapshots, candidates, outcomes, signals, and packets
- the Edge Function writers that produce canonical rows
- the offline AG optimization loop that tunes the indicator and produces packets
- the local training warehouse and publish-up lifecycle

This plan does not include:

- the paired Pine strategy (research-only unless explicitly reopened)
- Deep Backtesting as an active delivery blocker
- FastAPI
- Cloudflare Tunnel
- live AG inference
- browser extensions that inject TradingView inputs

---

## Core Architecture

### Live Trading

The live chart runs a Pine **indicator**.

That indicator must:

- calculate all live signal logic inside Pine
- pull all permitted live external series through TradingView-supported `request.*()` calls
- draw the fib structure and entry context on the chart
- keep dense operator tables off-chart and emit only the execution-facing TradingView surface
- fire alerts from Pine only

### Validation

Validation for the active path is indicator-only.

Active validation exists to:

- verify live chart behavior on the canonical MES `15m` surface
- confirm the operator-visible table/levels/labels are correct
- check point-in-time dataset alignment for AG and offline analysis
- reject regressions before they contaminate offline calibration work

### Optimization

AutoGluon is not connected live to the chart.

AutoGluon exists only to:

- rank which settings and features improve entry quality
- identify noisy settings to remove
- suggest tighter parameter ranges
- help choose the next Pine parameter set to test

The live chart never waits on AG.

---

## Non-Negotiable Rules

1. If Pine cannot compute it or request it live from TradingView-supported data, it cannot be part of the live signal.
2. Every live entry must be explainable from Pine-visible state on that bar.
3. No hidden server-side decision engine.
4. No dynamic input injection hacks.
5. The indicator is the only active Pine surface. Any strategy file is research-only and cannot block indicator work unless explicitly reopened.
6. The optimization target is not “looks smart.” It is entry quality:
   - reaches TP1 / TP2 with the `20pt+` eligibility gate satisfied
   - acceptable adverse excursion
   - acceptable signal count

---

<!-- "What Must Change" section archived — all items DONE -->


<!-- Forensic Review archived — all critical items resolved, see archive -->


## Live Data Boundary

### Pine Can Pull Live

The indicator may use TradingView-supported live pulls such as:

- `request.security()` for market symbols and proxies
- `request.economic()` for supported economic series
- built-in chart OHLCV and any requested symbol OHLCV

### Pine Cannot Pull Live

The indicator cannot depend on:

- arbitrary HTTP APIs
- local files
- Supabase rows
- Python outputs
- custom AG predictions

### Implication

All “advanced” logic must be built from:

- MES price and volume
- requested intermarket symbols
- requested economic series
- Pine-computed derived features

---

## Live Inputs To Build

### A. Fib Structure Engine

Keep and improve:

- confluence anchor selection
- active fib period selection
- structural break re-anchoring
- zone logic
- lookback intelligence beyond a simple zigzag
- point-in-time anchor stability suitable for offline snapshot materialization

Add:

- `0` line
- `1` line
- explicit distance to 0 / 1 / pivot / zone / target
- target-size eligibility gate for the 20-point requirement

### B. Intermarket Engine

**SUPERSEDED (2026-03-30):** v1 basket (NQ1!, BANK, VIX, DXY, US10Y, HYG, LQD) — REPLACED
**SUPERSEDED (2026-03-30):** v7a flow basket (TICK, VOLD, VVIX, VIX/VIX3M, HYG, RTY) — REPLACED (NYSE/CBOE not on Databento)

**Current v7b intermarket basket (CME Globex, Databento GLBX.MDP3) — LOCKED 2026-03-31:**

AG training basket (all available at 15m from Databento, $0 OHLCV on Standard plan):
- `CME_MINI:NQ1!` (NQ.c.0) — Tech leadership correlation
- `CME_MINI:RTY1!` (RTY.c.0) — Small-cap risk appetite
- `NYMEX:CL1!` (CL.c.0) — Energy/inflation proxy
- `COMEX:HG1!` (HG.c.0) — Copper = industrial demand leading indicator
- `CME:6E1!` (6E.c.0) — EUR/USD macro-FX flow
- `CME:6J1!` (6J.c.0) — JPY/USD risk-off flow

ES chart-native vol (fills VIX/VVIX gap, zero security calls):
- ATR ratio, range expansion, intrabar efficiency, VWAP state/event

Daily context (NOT gate members, same value all 27 session bars):
- VIX (FRED daily), SKEW (`CBOE:SKEW`), NYSE A/D (`USI:ADD`)

**Why CME-only:** AG needs 15m historical data from Databento. NYSE internals (TICK/VOLD), CBOE indices (VIX/VVIX/VIX3M/SKEW), and ETFs (HYG) are NOT on GLBX.MDP3. CFE (VX futures) is $750+/mo separate subscription.

**Data:** `cross_asset_1h` and `cross_asset_1d` are the current minimum training timeframes for the Locked Basket. `cross_asset_15m` table exists (migration 039), but 15m backfill for NQ/RTY/CL/6E/6J is **intentionally deferred** — gated on the first AG training run + full SHAP validation (see Phase 4 rule 5 below). `scripts/backfill-intermarket-15m.py` is ready but must not run for the Locked Basket until the SHAP gate clears.

Regime gate: grouped weighted scoring → 0-100 with hysteresis. AG decides final group structure, weights, and correlations from data.

<!-- Section C archived — superseded by CME Globex basket -->


### D. Volume Engine

“Volume of all types” will be interpreted as Pine-available volume state, not fictional order-book access.

Planned volume features:

- chart volume
- relative volume vs rolling baseline
- volume acceleration
- bar spread x volume interaction
- cross-asset volume proxies where the requested symbols expose volume

No unsupported order-book assumptions will be baked into v1.

### E. Session / Market State Engine

Planned live session features:

- regular session / overnight state
- session opening shock window
- lunch/noise window
- time-since-break
- bars-since-zone-touch
- bars-since-regime-flip

---

## Entry System Definition

The entry system is not “any accept/reject event.”

It becomes a scored entry predicate that must answer one question:

**Is this bar an entry worth taking if it passes the `20pt+` eligibility gate and has a credible path to TP1 / TP2?**

### Entry Predicate v1

A valid entry must include:

1. valid fib anchor and non-degenerate range
2. valid 20+ point path to target
3. acceptable structure event
4. acceptable intermarket regime
5. acceptable volatility / credit / macro state
6. acceptable volume state
7. no explicit conflict state

### Structure Event Candidates

The strategy will compare at least these structure archetypes:

- break -> retest -> accept
- rejection from decision zone
- pivot reclaim / pivot loss
- continuation after one clean pullback
- reversal after regime-aligned failed move

### Decision States

The policy layer should output one clear decision state:

- `TAKE_TRADE`
- `WAIT`
- `PASS`

These are decision codes only. Realized outcome labels remain separate.

---

## Shared Pine Architecture

One Pine artifact is active on the live path:

### 1. Live Indicator

Purpose:

- chart visualization
- live entry markers
- exhaustion precursor diamond
- alerts
- hidden export packet

Required outputs:

- 0 / 1 / pivot / zone / target lines
- entry markers
- stop
- target 1
- target 2
- exhaustion precursor diamond
- alertconditions
- hidden export packet

### 2. Research Strategy Surface — RETIRED (2026-03-26)


### Shared Core

These must remain identical between any research strategy and the live indicator whenever the strategy path is reopened:

- fib anchor selection
- external series pulls
- feature calculations
- entry predicate
- target eligibility logic

---

## Dashboard Operator Surface Plan

TradingView chart tables are retired from the active path. The dashboard is the operator-facing surface for dense state, stats, and cross-asset visuals, but it must render the same MES 15m fib engine state rather than recompute fib geometry locally.

### Dashboard Contents v1

Top block:

- symbol
- timeframe
- active fib engine version
- direction

Signal block:

- decision state
- target eligibility (`20pt+` pass/fail)
- entry price
- stop level
- target 1
- target 2
- exhaustion precursor state

Regime block:

- intermarket regime
- volatility state
- credit state
- macro posture

Component block:

- NQ (CME Globex)
- RTY (CME Globex)
- CL (CME Globex)
- HG (CME Globex)
- 6E (CME Globex)
- 6J (CME Globex)
- ES chart-native vol state

Structure block:

- break / accept / reject state
- bars since event
- active score

### Visual Direction

The dashboard should feel dense and intentional, not like default Pine debug output:

- compact
- synchronized around the main MES chart
- readable at trading size
- color-coded state bars
- minimal wasted text

Mini charts for correlation symbols and richer sentiment/regime visuals are explicitly allowed here. Arc gauges are optional. Decision reasons, state bars, and synchronized context are the priority.


### TradingView → Dashboard Webhook Architecture

The dashboard is the command center. TradingView webhook alerts are the live event bridge from Pine to the dashboard. This replaces the need for a server-side setup detection cron.

#### Flow

```
Pine alertcondition() fires
  → TradingView sends POST to webhook URL
    → Supabase Edge Function (tv-alert-webhook) receives POST
      → validates payload + shared secret
      → writes to canonical tables (warbird_fib_candidates_15m, warbird_signals_15m, etc.)
        → Supabase Realtime pushes change to dashboard
          → dashboard renders live state
```

#### Alert payload contract

TradingView webhook alerts send JSON in the POST body. The `message` field in `alertcondition()` supports `{{close}}`, `{{time}}`, `{{exchange}}`, `{{ticker}}`, and other placeholders. The 3 kept alerts and their payloads:

| Alert | Pine trigger | Webhook payload purpose |
|-------|-------------|------------------------|
| `WARBIRD ENTRY LONG` | `entryLongTrigger` | Create candidate + signal row with direction=LONG, entry/stop/TP levels from current fib state |
| `WARBIRD ENTRY SHORT` | `entryShortTrigger` | Create candidate + signal row with direction=SHORT, entry/stop/TP levels from current fib state |
| `PIVOT BREAK (against) + Regime Opposed` | `breakAgainstEvent` | Write reversal warning event to signal_events, update candidate decision state |

#### Edge Function: `tv-alert-webhook`

Required implementation:

1. Validate webhook secret (TradingView supports custom headers or URL-embedded tokens)
2. Parse alert name and `{{close}}` / `{{time}}` from payload
3. For entry alerts: snapshot current fib engine state from the latest `warbird_fib_engine_snapshots_15m` row, create `warbird_fib_candidates_15m` + `warbird_signals_15m` rows
4. For pivot break alert: find the active signal, write a `REVERSAL_DETECTED` event to `warbird_signal_events`
5. Log to `job_log`

#### Dashboard consumption

- Supabase Realtime subscription on `warbird_signals_15m` and `warbird_signal_events`
- Dashboard receives INSERT/UPDATE events in real-time — no polling
- The 8 alerts cut from Pine (ACCEPT, REJECT, TARGET HITs, CONFLICT, RISK-ON/OFF flips) can be reconstituted as dashboard-side derived state from the stored fib engine snapshot + intermarket regime data — no Pine budget cost

#### Rules

1. The webhook Edge Function writes to canonical tables (037 schema), not legacy tables
2. Pine is the signal source — the dashboard renders, it does not re-derive entry decisions
3. The webhook secret must be stored in Supabase Vault, not hardcoded
4. Webhook delivery is best-effort (TradingView retries but does not guarantee exactly-once) — the writer must be idempotent on natural key

---

<!-- AutoGluon Optimization Loop archived — content consolidated into AG Model Concept section below -->


<!-- AutoGluon Model Specification archived — content consolidated into AG Model Concept section below -->

<!-- Claude Handoff Constraints + Execution Brief archived — meta-instructions, not plan content -->


<!-- AG Work Product archived — content in AG Model Concept sections 10-12 -->


## Build Phases


#### Contract First

1. The canonical trade object is now the **MES 15m fib setup**, keyed by the MES 15m bar-close timestamp in `America/Chicago`.
2. Any remaining `1H` wording in older drafts or reference files is legacy and must not drive new implementation.
3. Pine is the canonical signal surface.
4. The Next.js dashboard is the mirrored operator surface and may render the same fib engine/state alongside TradingView, but it must consume the same 15m contract rather than acting as a separate decision engine.
5. Every live, strategy, dataset, AG, and dashboard artifact must map back to the same 15m setup contract before any module work continues.
6. If a candidate feature or script cannot align exactly to the 15m bar-close contract, it is research-only and cannot enter the production path.

#### Data Flow Rule

1. Production ownership is cloud-first:
   - `provider -> cloud Supabase -> live routes/dashboard`
2. Local work is training/research only:
   - `explicit cloud export snapshots + TradingView exports/capture + /data raw archives -> local PostgreSQL warehouse -> publish approved artifacts back to cloud`
3. Do **not** build or extend a standing cloud-to-local sync subsystem or a local-first production ingestion path.
4. Use local capture only for explicit training inputs:
   - TradingView chart exports
   - validated local TradingView CLI / MCP capture only after the exact server or binary is installed and documented in the active environment
   - explicit cloud snapshot loads into the local PostgreSQL warehouse
   - local research datasets
5. Publish promoted artifacts **from local to cloud** only:
   - promoted packets
   - training reports
   - SHAP summaries
   - approved feature metrics
6. Cloud Supabase remains the production system of record for recurring ingestion, cron ownership, dashboard state, and operator-facing live tables.
7. Training-only data must **not** be maintained through daily, hourly, or standing cron pulls. Refresh training data only by batch pull on the scheduled retrain day or explicit research run, unless that dataset is also required for the frontend, live indicator contract, or runtime/operator surfaces.

#### Third-Party Pine Admission Gate

Third-party scripts are allowed only through this gate:

1. Source must be open-source and reviewable.
2. Internal logic must be copied exactly. Interface-only adaptation is allowed:
   - input naming/grouping
   - visual disabling
   - hidden `plot()` exports
   - alert payload wiring
   - wrapper glue for strategy / export harnesses
3. No internal math rewrites, no partial reimplementations, no "clean-room" approximations.
4. Every admitted script must first land as a **standalone feature harness**, not inside the main indicator.
5. Harness output must be timestamp-aligned to the MES 15m bar close and exported for local AG training before any promotion decision.
6. Only modules that survive out-of-sample admission may be folded into the main indicator / strategy pair.
7. If exact-copy harnessing is not possible, stop the work. Do not substitute a hand-rolled internal copy.

#### Required Harness Modules — SUPERSEDED (2026-03-28)

The three standalone harnesses (BigBeluga Pivot Levels, LuxAlgo MSB/OB Toolkit, LuxAlgo Luminance Engine) were retired on 2026-03-28 (commit `c506c48`) and replaced by the embedded 15-metric TA core pack. The harness files were deleted from the repo (`indicators/harnesses/` directory removed). The TA core pack provides: EMAs (21/50/100/200), MACD histogram, RSI(14), ATR(14), ADX(14), volume raw, vol SMA(20), vol ratio, vol acceleration, bar spread × vol, OBV, MFI(14). All 15 are exported as `ml_*` hidden plots. Zero downstream consumers in TypeScript, API routes, or DB used the harness exports — the TA core pack covers the same feature space more efficiently within the 64-output budget.

<!-- Third-Party Source Acquisition Guide archived — all harnesses retired 2026-03-28 -->


#### Event-Response Module Requirement

The main indicator must gain an always-on hidden event-response block. This block is not optional after the March 23, 2026 failure mode review.

Minimum candidate inputs:

1. MES / NQ / RTY / CL / HG / 6E / 6J reaction state (CME Globex basket)
2. lower-timeframe volume shock / expansion state
3. reversal-vs-continuation state after the impulse
4. scheduled macro proximity / release windows
5. inflation / rates / geopolitical regime context
6. pivot interaction state

The event-response block's purpose is to suppress, delay, confirm, or reclassify a valid 15m fib setup. It is not allowed to become a separate trade engine detached from the fib contract.

Required Phase 2 event-response export interface:

| Hidden export | Meaning | Encoding rule |
| --- | --- | --- |
| `ml_event_mode_code` | current event regime | `0=none`, `1=shock_continuation`, `2=shock_failure`, `3=deescalation_squeeze`, `4=inflation_scare`, `5=rates_relief`, `6=headline_conflict` |
| `ml_event_shock_score` | normalized shock intensity | `0-100` deterministic Pine score |
| `ml_event_reversal_score` | reversal risk after impulse | `0-100` deterministic Pine score |
| ~~`ml_event_volume_shock`~~ | lower-timeframe volume shock state | cut from Pine exports during budget reduction — AG computes from `ml_vol_ratio` + `ml_vol_acceleration` server-side |
| ~~`ml_event_macro_window_code`~~ | scheduled macro window state | cut from Pine exports during budget reduction — AG computes from `econ_calendar` data server-side |
| `ml_event_nq_state` | NQ tech leadership trend state | `-1`, `0`, `1` |
| `ml_event_rty_state` | RTY small-cap risk appetite state | `-1`, `0`, `1` |
| `ml_event_cl_state` | CL energy/inflation proxy state | `-1`, `0`, `1` |
| `ml_event_hg_state` | HG copper/industrial demand state | `-1`, `0`, `1` |
| `ml_event_eur_state` | 6E EUR/USD macro-FX flow state | `-1`, `0`, `1` |
| `ml_event_jpy_state` | 6J JPY/USD risk-off flow state | `-1`, `0`, `1` |
| `ml_event_skew_state` | SKEW tail-risk state (daily) | `-1`, `0`, `1` |
| `ml_event_pivot_interaction_code` | interaction with pivot state | `0=none`, `1=support`, `2=resistance`, `3=rejection`, `4=breakthrough`, `5=cluster_conflict` |


### Phase 1: Series Inventory Freeze — COMPLETED


### Phase 2: Refactor The Current Script — COMPLETED


#### Phase 2 Completion Summary

Phase 2 completed 2026-03-24 (5 checkpoints). Three standalone harnesses retired 2026-03-28, replaced by TA core pack.

### Phase 3: Strategy Path — RETIRED (2026-03-26)


### Phase 4: Dataset + AG Loop

1. Export chart data with the final feature columns.
2. Build labels tied to TP1 / TP2 / outcome, with `20pt+` used as an eligibility gate.
3. Train AG on settings and feature robustness.
4. Select the best candidate rule set.
5. Train module admission first, then parameter admission, then joint configuration.
6. Treat each required third-party script as a standalone exported feature family before main-indicator promotion.
7. Publish results upward from local after evaluation; do not add a recurring cloud-to-local sync layer.

Phase 4 decision rule:

1. Phase 4 is the filter for what truly earns its way into the live indicator.
2. SHAP, admission reports, and out-of-sample validation decide which assets, modules, and setting families survive.
3. Do not expand the live indicator with additional settings or “zoo” modules ahead of that evidence.
4. Minimal exportability comes before expansion; evidence-driven promotion comes before UI/config sprawl.
5. **Cross-asset basket minimum training timeframe is 1h until SHAP completes full feature validation.** SHAP scope is the full feature set — EMA lengths, event-response module, session context, pivot state, volume family, intermarket symbols (NQ/RTY/CL/HG/6E/6J), module families, and all parameter settings. Not just the 6 symbols. Only after SHAP returns feature importance across the entire first training run and confirms which features and symbols survive pruning do we schedule 15m or 1m backfills. The surviving symbols and their required training timeframes are determined from that evidence, not assumed in advance.

Phase 4 exact local targets:

- local PostgreSQL database: `warbird_training`
- local raw/archive root: `/Volumes/Satechi Hub/warbird-pro/data/`
- local AG scripts:
  - `scripts/ag/build-fib-snapshots.py`
  - `scripts/ag/load-source-snapshots.py`
  - `scripts/ag/build-fib-dataset.py`
  - `scripts/ag/compute-features.py`
  - `scripts/ag/train-fib-model.py`
  - `scripts/ag/evaluate-configs.py`
  - `scripts/ag/generate-packet.py`
  - `scripts/ag/publish-artifacts.py`
Phase 4 exact training order:

1. fib + event-response + TA core pack baseline
2. parameter admission inside surviving feature families
3. joint configuration on surviving feature families only

Phase 4 training refresh rule:

1. Do **not** add daily or hourly recurring ingestion for training-only datasets.
2. Training refreshes are batch-only on the day the AG retrain runs, or on an explicit research rebuild.
3. Recurring cloud ingestion is justified only when the data is needed by the frontend, live indicator/runtime contract, dashboard state, or operator-facing surfaces.
4. Do **not** build a full runtime-to-local mirror. Load only named cloud export snapshots and approved local raw files into `warbird_training`.

Historical note: the original order included 3 standalone harness admission steps (BigBeluga, MSB/OB, Luminance) — those harnesses were retired on 2026-03-28 and replaced by the embedded TA core pack.

Phase 4 exact local warehouse entities:

- source-snapshot tables:
  - `mes_1m`
  - `mes_15m`
  - `mes_1h`
  - `mes_4h`
  - `mes_1d`
  - `cross_asset_1h`
  - `cross_asset_1d`
  - `econ_rates_1d`
  - `econ_yields_1d`
  - `econ_fx_1d`
  - `econ_vol_1d`
  - `econ_inflation_1d`
  - `econ_labor_1d`
  - `econ_activity_1d`
  - `econ_money_1d`
  - `econ_commodities_1d`
  - `econ_indexes_1d`
  - `econ_calendar`
  - `geopolitical_risk_1d`
  - `executive_orders_1d`
- `warbird_training_runs`
- `warbird_training_run_metrics`
- `warbird_shap_results`
- `warbird_shap_indicator_settings`
- `warbird_snapshot_pine_features`
- `warbird_candidate_macro_context`
- `warbird_candidate_microstructure`
- `warbird_candidate_path_diagnostics`
- `warbird_candidate_stopout_attribution`
- `warbird_feature_ablation_runs`
- `warbird_entry_definition_experiments`

Phase 4 exact cloud publish-up entities:

- `warbird_training_runs`
- `warbird_training_run_metrics`
- `warbird_packets`
- `warbird_packet_activations`
- `warbird_packet_metrics`
- `warbird_packet_feature_importance`
- `warbird_packet_setting_hypotheses`
- `warbird_packet_recommendations`
- realtime dashboard/Admin surfaces:
  - `mes_1m`
  - `mes_15m`
  - `warbird_active_signals_v`
  - `warbird_admin_candidate_rows_v`
  - `warbird_active_training_run_metrics_v`
  - `warbird_active_packet_metrics_v`
  - `warbird_active_packet_feature_importance_v`
  - `warbird_active_packet_setting_hypotheses_v`
  - `warbird_active_packet_recommendations_v`

### Phase 5: Indicator UI Build

1. Inventory and lock the exact operator-approved fib visual spec first: colors, line widths, line styles, level labels, and exhaustion-diamond presentation.
2. Build the execution-facing TradingView surface only: entry markers, level lines, exhaustion precursor diamond, and concise alertconditions.
3. Keep operator tables and rich diagnostics in the dashboard.
4. Ensure the indicator remains within Pine limits.
5. Keep pivots, required harness intelligence, and candidate bolt-on intelligence hidden unless explicitly promoted to the visible surface.

Phase 5 must not begin until Phase 4 has produced at least one packet candidate with stable bucket outputs and documented sample counts.

The mirrored dashboard operator surface must map exactly to:

- decision state
- TP1 probability
- TP2 probability
- reversal risk
- win rate
- stats window
- regime
- conflict
- stop family
- TP1 / TP2 path

### Phase 6: Walk-Forward Validation

1. Re-test the candidate settings out of sample.
2. Compare against prior settings.
3. Promote only if entry-quality metrics improve.
4. Require every promoted required harness module or candidate bolt-on to prove additive value over the fib + event-response baseline.

Phase 6 closeout must update:

- active plan status
- `WARBIRD_MODEL_SPEC.md` if packet or contract semantics changed
- `CLAUDE.md` current status
- memory with the promoted / rejected module decision

---

<!-- Success Metrics archived — restore when AG training begins -->


## Open Research Items

1. Anchor quality scoring: current confluence chooser vs explicit continuation-leg method.
2. Fib direction stability: hysteresis band vs ordered swing-leg.
3. Optimal CME intermarket timeframe: 15m vs 60m vs mixed. **GATED on Phase 4 SHAP run** — do not expand below 1h until SHAP returns feature importance across the full feature set and confirms which symbols and timeframes survive. See Phase 4 rule 5.
4. Whether CL/HG polarity is unconditionally positive or regime-dependent (AG decides from data).

---


## AG Model Concept

The full AG specification is in [`WARBIRD_MODEL_SPEC.md`](../../WARBIRD_MODEL_SPEC.md).

Detailed training protocol, feature tables, packet format, and implementation files archived to [`archive/2026-03-31-ag-model-concept-archive.md`](archive/2026-03-31-ag-model-concept-archive.md).


### 19. Immediate Next Steps (updated 2026-03-31)

Current blocking order is at the top of this plan.

1. ~~**Pine indicator recovery**~~ — DONE.
2. ~~**v7 institutional upgrade**~~ — DONE. Grouped regime scoring, ES execution quality, 64/64.
3. ~~**Intermarket pivot to CME Globex**~~ — DONE. NQ/RTY/CL/HG/6E/6J. 63/64 (1 headroom). Commit `6f3e7a6`.
4. ~~**Supabase pg_cron sole schedule producer**~~ — DONE.
   Runtime note locked 2026-03-31: `mes-1m`, `mes-hourly`, and `cross-asset` Edge Functions handle market-hours skips internally via `isMarketOpen()`. SQL helper functions are `net.http_*` dispatch wrappers only — no session-hour gating in Postgres.
5. **Companion pane indicator** — regime_score, impulse_quality, exhaustion_score, agreement_velocity lines + event markers. Own 64-plot / 40-call budget. Discusses after main indicator is stable.
6. **Fib engine hardening** — anchor-span visual gap, intermediate waypoint lines (1.382, 1.50, 1.786), direction logic, MTF alignment.
7. **Canonical writer checkpoint** — port `detect-setups` / `score-trades` to Supabase Edge Functions writing canonical tables.
8. **Dashboard/admin reader cutover** — cut off legacy tables, webhook alerts from TradingView → Edge Function → Supabase Realtime → dashboard.
9. **Stand up the local AG workbench** — venv, `scripts/ag/*.py`.
10. **Train the staged baseline** — fib + event-response + TA core pack baseline → parameter admission.
11. **Legacy table retirement** — only after all readers/writers are migrated.
