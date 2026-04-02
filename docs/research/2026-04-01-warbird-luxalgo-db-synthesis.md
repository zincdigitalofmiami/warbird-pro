# Warbird Synthesis — Locked Universe, Storage Boundaries, and DB Endgame

**Date:** 2026-04-01
**Purpose:** Lock the symbol universe, storage boundaries, terminology, and immediate DB/data scope so the Warbird endgame does not fail from scope drift while the local warehouse and Supabase paths are being finalized.

---

## 1. Executive Lock

The LuxAlgo-origin work was useful for **methodology**:

- volume confirmation
- Opening Range context
- liquidity sweeps
- CHoCH / BOS
- FVG / imbalance context
- exhaustion detection
- post-trade reset logic

It was **not** useful as schema authority, storage authority, or symbol-universe authority.

The March 31 break happened because implementation narrowed Warbird into a smaller table story than the active plan allowed. The April 1 work improved DB-truth discipline, local/cloud separation, and warehouse direction, but it did **not** complete the canonical Warbird cutover.

The immediate focus is now narrower and should stay narrower:

1. lock the symbol universe and timeframes
2. lock local vs cloud responsibilities
3. fill the local warehouse correctly
4. keep cloud limited to what the live indicator/dashboard actually needs
5. defer AG packet publishing, SHAP diagnostics, and model optimization details until the DB contract is stable

If these boundaries are not locked first, the later AG / Pine / dashboard endgame fails even if the data volume is large.

---

## 2. Verified Reality As Of 2026-04-01

These points were checked directly against the repo and live databases.

### 2.1 Local and cloud are different

- local Supabase migration ledger max = `20260401000046`
- cloud Supabase migration ledger max = `20260401000048`

They are not the same state and must not be described as one state.

### 2.2 `cross_asset_15m` is still incomplete

- local `cross_asset_15m` = `20553` rows, symbol coverage = `HG` only
- cloud `cross_asset_15m` = `0` rows

So the local 15m training surface is still partial, and the cloud 15m surface should not be the recovery target anyway.

### 2.3 `cross_asset_4h` does not exist

Verified:

- `mes_4h` exists
- `cross_asset_4h` does **not** exist in local or cloud

That matters because the locked direction now requires the 6-symbol basket to have `15m`, `1h`, `4h`, and `1d`.

### 2.4 The `symbols` registry is broader than the approved batch scope

Active Databento futures in `symbols` currently include:

- `MES`, `NQ`, `RTY`, `CL`, `HG`, `6E`, `6J`
- `ES`, `GC`, `NG`, `SI`, `SOX`, `SR3`, `YM`, `ZB`, `ZF`, `ZN`

Active options parents in `symbols` currently include:

- `ES.OPT`, `EUU.OPT`, `HXE.OPT`, `JPU.OPT`, `LO.OPT`, `NQ.OPT`, `OB.OPT`, `OG.OPT`, `OH.OPT`, `OKE.OPT`, `ON.OPT`, `OZB.OPT`, `OZF.OPT`, `OZN.OPT`, `SO.OPT`

Active FRED placeholder symbols in `symbols` currently include:

- `DX`, `US10Y`, `VX`

This proves that `is_active=true` in `symbols` is **not** the same thing as the approved Warbird training scope.

### 2.5 MES symbology still has drift in the registry

The active contract says all futures use rolling continuous Databento symbology:

- `.c.0`
- `stype_in=continuous`

But the live `symbols` registry still has:

- `MES -> MES.v.0`

That is schema/metadata debt and must be corrected before the registry is treated as authoritative.

### 2.6 `series_catalog` is FRED-only and does not own futures

`series_catalog` is the FRED registry. It is not where the 6-pack futures belong.

Verified category samples:

- FX FRED series: `DEXUSEU`, `DEXJPUS`, `DTWEXBGS`
- vol FRED series: `VIXCLS`, `OVXCLS`, `RVXCLS`, `VXNCLS`
- commodities FRED series: `GVZCLS`

The 6-pack futures belong in:

- `symbols`
- `symbol_roles`
- `symbol_role_members`
- `cross_asset_*`

They do **not** belong in `series_catalog`.

### 2.7 SKEW and NYSE A/D have no approved persisted home today

Verified:

- no `series_catalog` entry exists for `SKEW`
- no `series_catalog` entry exists for `USI:ADD`
- no `series_catalog` entry exists for `CBOE:SKEW`

Under the current rule set, if it is not available from FRED or Databento in the approved system, it is out.

### 2.8 RR options tables exist, but options are now out of the active DB scope

Verified RR tables:

- `mkt_options_ohlcv_1d`
- `mkt_options_statistics_1d`

Verified RR parent symbols in `mkt_options_ohlcv_1d`:

- `ES.OPT`
- `EUU.OPT`
- `HXE.OPT`
- `JPU.OPT`
- `LO.OPT`
- `NQ.OPT`
- `OB.OPT`
- `OG.OPT`
- `OH.OPT`
- `OKE.OPT`
- `ON.OPT`
- `OZB.OPT`
- `OZF.OPT`
- `OZN.OPT`
- `SO.OPT`

These are valid archive inputs, but per the current direction they should remain **Local Drive only** for historical backup / later research, not part of the active local Supabase DB plan.

---

## 3. Locked Vocabulary

Do not use vague terms in the plan. Use these exact ones.

### 3.1 Storage names

- **Cloud Supabase Runtime**
  - the production Supabase instance
  - purpose: live dashboard, live chart-serving support, production crons only
- **Local Supabase Warehouse**
  - the local Docker Supabase Postgres instance at `localhost:54322`
  - purpose: historical warehouse, training, research, batch backfill validation
- **Local Drive Archive**
  - the external drive rooted at `/Volumes/Satechi Hub/`
  - purpose: raw Databento batch archives, parquet backups, options historical storage, safety copies

### 3.2 Universe names

- **MES Primary Instrument**
  - only `MES`
  - the traded object
- **Locked Basket**
  - the six approved Databento cross-asset futures:
  - `NQ`, `RTY`, `CL`, `HG`, `6E`, `6J`
- **Extra Futures Universe**
  - approved non-MES Databento futures outside the Locked Basket that may be stored locally at lower frequency
  - exact list from the current active registry:
  - `ES`, `GC`, `NG`, `SI`, `SOX`, `SR3`, `YM`, `ZB`, `ZF`, `ZN`
- **All Active Symbols**
  - every row in `symbols` where `is_active=true`
  - this is a registry state, **not** a batch-pull scope, not a model scope, and not a storage scope

### 3.3 Table-family names

- **Cross Assets**
  - approved non-MES Databento futures stored in `cross_asset_*`
  - not FRED series
  - not options
  - not unsupported external symbols
- **FRED Daily Context**
  - approved daily macro/financial context stored in `econ_*_1d`
  - driven by `series_catalog`

### 3.4 Term to stop using

- **Warbird Core**
  - ambiguous
  - remove it from planning language unless it is explicitly defined

Use the concrete names above instead:

- MES Primary Instrument
- Locked Basket
- Extra Futures Universe
- FRED Daily Context
- Canonical Warbird Truth Tables

---

## 4. Locked Symbol And Timeframe Map

This is the approved symbol map after incorporating the current critique.

### 4.1 Tier 0 — MES Primary Instrument

**Symbol:** `MES`
**Source:** Databento continuous futures only
**Symbology:** `MES.c.0`, `stype_in=continuous`

**Local Supabase Warehouse**

- `mes_1m`
- `mes_15m`
- `mes_1h`
- `mes_4h`
- `mes_1d`

**Cloud Supabase Runtime**

- only the MES tables that directly serve the live indicator/dashboard path
- no training-only MES surfaces belong in cloud

**Critical check**

- the `symbols` registry must be corrected from `MES.v.0` to `MES.c.0`

### 4.2 Tier 1 — Locked Basket

**Symbols:** `NQ`, `RTY`, `CL`, `HG`, `6E`, `6J`
**Source:** Databento continuous futures only
**Symbology:** all use `.c.0`, `stype_in=continuous`

**Purpose**

- the approved cross-asset feature set for Warbird
- these are the only non-MES futures that get the full higher-resolution training treatment

**Local Supabase Warehouse**

- `cross_asset_15m`
- `cross_asset_1h`
- `cross_asset_4h`  **required by the locked direction, currently missing**
- `cross_asset_1d`

**Cloud Supabase Runtime**

- only the cross-asset tables that directly serve the indicator/dashboard path
- current likely survivor: `cross_asset_1h` for the dashboard symbol panel
- `cross_asset_15m`, `cross_asset_4h`, and `cross_asset_1d` do **not** belong in cloud unless an explicit live consumer is reopened and justified

**Critical check**

- `cross_asset_4h` is not implemented today and must be either:
  - added explicitly, or
  - rejected explicitly

No silent omission is acceptable now that the timeframe lock is tighter.

### 4.3 Tier 1B — Extra Futures Universe

**Symbols:** `ES`, `GC`, `NG`, `SI`, `SOX`, `SR3`, `YM`, `ZB`, `ZF`, `ZN`
**Source:** Databento continuous futures only
**Symbology:** all use `.c.0`, `stype_in=continuous`

**Purpose**

- secondary local research context
- not part of the Locked Basket
- not allowed to silently expand the AG 15m baseline

**Local Supabase Warehouse**

- `cross_asset_1h`
- `cross_asset_1d`

**Cloud Supabase Runtime**

- none by default
- only admitted if a concrete dashboard/indicator consumer is approved

**Rule**

- these are the exact symbols that should replace vague phrases like "extra symbols"
- if a future is not on this list, it is not in scope without a deliberate reopening

### 4.4 Tier 2 — Canonical Warbird Truth Tables

These are not extra market symbols. These are the persisted homes for the actual Warbird setup/signal/model contract.

**Point-in-time engine truth**

- `warbird_fib_engine_snapshots_15m`

Must carry the frozen MES 15m fib state that existed at bar close, including:

- anchors and fib geometry
- TP1 / TP2 / stop geometry
- Pine structural state
- liquidity sweep state
- volume / RVOL state
- MTF state
- trigger / decision-support state
- any approved cross-asset and macro features joined at the same canonical key

**Candidate truth**

- `warbird_fib_candidates_15m`

Must carry:

- candidate identity
- deterministic Pine score
- policy decision code
- packet-linked model outputs once AG is live

**Realized outcome truth**

- `warbird_candidate_outcomes_15m`

Must carry:

- realized outcome
- TP1 / TP2 / stop / reversal timestamps where applicable
- MAE / MFE
- realized win/loss truth

**Published signal truth**

- `warbird_signals_15m`
- `warbird_signal_events`

Must carry:

- only published signals
- lifecycle events for those signals

### 4.5 Tier 2A — Later Admin / AG / SHAP Publish-Up

This is later-phase scope, not the immediate DB fill scope.

**Training and packet lineage**

- `warbird_training_runs`
- `warbird_training_run_metrics`
- `warbird_packets`
- `warbird_packet_activations`

**Published metrics and optimization surfaces**

- `warbird_packet_metrics`
- `warbird_packet_feature_importance`
- `warbird_packet_setting_hypotheses`
- `warbird_packet_recommendations`

**Local-only raw explainability**

- `warbird_shap_results`
- `warbird_shap_indicator_settings`

**What belongs here**

- wins
- losses
- percentage winners
- packet win-rate statistics
- promoted feature importance
- SHAP-backed setting hypotheses after training

**What does not belong here yet**

- no raw SHAP matrices in cloud
- no AG cadence work before canonical truth tables are populated
- no model-optimization rabbit hole before the warehouse and recording path are stable

**Cadence**

Per the active plan:

- AG remains offline only
- packet refresh cadence in normal operation is no more than once per week
- SHAP is a diagnostic / promotion gate, not the first step of the current DB project

### 4.6 Tier 3 — FRED Daily Context

These belong in `econ_*_1d`, routed by `series_catalog.category`.

**Examples verified in catalog**

- FX: `DEXUSEU`, `DEXJPUS`, `DTWEXBGS`
- vol: `VIXCLS`, `OVXCLS`, `RVXCLS`, `VXNCLS`
- commodities: `GVZCLS`

**Important clarification**

The 6-pack futures are **not missing** from `series_catalog`.

They are intentionally not there.

- `series_catalog` owns FRED series
- `symbols` + `symbol_roles` own futures
- `cross_asset_*` owns the futures bar history

That is the correct separation.

### 4.7 Tier 4 — Dropped For Now

These do not have an approved persisted source under the current rules and should be removed from the active plan/spec until reopened.

- `SKEW`
- `USI:ADD` / NYSE A/D

### 4.8 Tier 5 — Options Archive Only

Options are out of the active DB plan.

**Keep only on Local Drive Archive for now**

- raw Databento options definition archives
- RR options daily tables if exported to parquet

**Do not add to Local Supabase Warehouse now**

- no options base tables
- no options training path
- no options schema work

This removes needless scope during the DB/data stabilization phase.

---

## 5. What The Plan Must Incorporate Now

These are the changes that matter for the endgame.

### 5.1 Lock the batch scope by whitelist

Do not use:

- `symbols.is_active`
- "all active symbols"
- "pull everything we have"

Use explicit whitelists only.

**Locked Basket whitelist**

- `NQ`
- `RTY`
- `CL`
- `HG`
- `6E`
- `6J`

**Extra Futures Universe whitelist**

- `ES`
- `GC`
- `NG`
- `SI`
- `SOX`
- `SR3`
- `YM`
- `ZB`
- `ZF`
- `ZN`

### 5.2 Keep backfill local-only

Backfill is a **Local Supabase Warehouse** concern.

- no `cross_asset_15m` recovery objective for cloud
- no cross-asset history expansion in cloud unless a live consumer requires it
- cloud should only retain tables that serve the live indicator/dashboard/runtime path

### 5.3 Rewrite the recovery plan objective

The current draft still frames the problem as:

- recover cloud `cross_asset_15m`

The correct objective now is:

- complete and verify the local cross-asset warehouse
- keep cloud limited to runtime-serving data only

### 5.4 Lock `.c.0` continuous everywhere

All futures use rolling continuous Databento contracts:

- `.c.0`
- `stype_in=continuous`

No `.v.0` entries should remain in the authoritative registry for active futures.

### 5.5 Use RR as-is where it is already correct

If RR schema and values are correct, do not reinvent them.

Use RR directly for:

- local `cross_asset_1h`
- local `cross_asset_1d`

unless the audit proves a problem.

Do not "normalize harder" or reshape working RR source data without an actual defect.

### 5.6 Add the missing cross-asset 4h decision

The locked direction now says:

- MES gets `1m`, `15m`, `1h`, `4h`, `1d`
- Locked Basket gets `15m`, `1h`, `4h`, `1d`
- Extra Futures Universe gets `1h`, `1d`

Today the repo has:

- `mes_4h`
- no `cross_asset_4h`

This must be resolved before calling the plan final.

### 5.7 Remove unsupported sources from the active contract

Until a real approved source exists in FRED or Databento:

- drop `SKEW`
- drop `USI:ADD`

Do not leave them lingering in the active plan/spec as implied requirements.

### 5.8 Keep options out of the DB plan

Options are now:

- archive only
- Local Drive only
- future research only

They should not be described as an active migration sector for the current database finish.

### 5.9 Name the local storage targets explicitly

Use these names in the plan:

- **Local Supabase Warehouse**
- **Cloud Supabase Runtime**
- **Local Drive Archive**

Do not alternate between:

- local DB
- local Supabase
- training warehouse
- external drive
- historical dump

without locking the names.

---

## 6. Immediate Scope Versus Later Scope

This split needs to stay visible.

### Immediate scope: database and data completion

- fix registry and migration truth
- lock symbol/timeframe scope
- fill the Local Supabase Warehouse
- retire cloud training storage that does not serve runtime
- stabilize cron / backfill paths that are actually in-bounds
- ensure the indicator/dashboard consumers have the runtime data they truly need

### Later scope: model optimization and operator intelligence

- AG training baselines
- weekly packet refresh
- SHAP diagnostics
- setting optimization
- feature-ablation studies
- win/loss / packet metrics views
- recommendation surfaces

The later scope depends on the immediate scope being right first.

---

## 7. Critical Checks Before Anyone Finalizes The Plan

These are the checks that should be treated as non-negotiable.

1. **Fix the MES registry drift**
   - `MES.v.0` must become `MES.c.0` if the registry is going to represent live truth.
2. **Resolve migration drift first**
   - cloud is at `20260401000048`
   - local is at `20260401000046`
3. **Lock the exact symbol/timeframe matrix**
   - MES
   - Locked Basket
   - Extra Futures Universe
   - FRED Daily Context
4. **Decide the `cross_asset_4h` implementation**
   - add it or reject it explicitly
5. **Remove SKEW / NYSE A/D from the active contract for now**
   - they do not have an approved persisted home
6. **Retire the old 15m backfill script references**
   - the active plan and April 1 local/cloud plan still reference `scripts/backfill-intermarket-15m.py`
   - if the new batch/resample flow is the decision, the old script must be retired everywhere
7. **Keep options out of the active DB scope**
   - archive only
8. **Do not let "all active symbols" leak into code**
   - registry state is not batch scope
9. **Use RR where it is already correct**
   - especially for `1h` / `1d`
10. **Keep cloud limited to live consumers**
   - no symbol/timeframe family belongs in cloud just because it exists locally

---

## 8. Final Position

The correct endgame is still:

`Pine truth -> canonical recorded setup/candidate/outcome/signal lineage -> local AG selector -> promoted packet -> dashboard/admin render`

But that endgame will fail if the data foundation stays fuzzy.

The right immediate finish is:

1. lock the universe
2. lock the names
3. lock the timeframes
4. lock local vs cloud
5. fill the local warehouse correctly
6. stop carrying unsupported or later-phase scope inside the active DB plan

The LuxAlgo methodology still matters, but right now it belongs in the **feature design later**, not in the **storage scope now**.
