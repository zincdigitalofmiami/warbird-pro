# AG-Teaches-Pine Implementation Design

**Date:** 2026-03-22
**Status:** Design — Pending Approval
**Parent Plan:** `2026-03-20-ag-teaches-pine-architecture.md` (single source of truth)
**Purpose:** This doc captures ALL research findings, confirmed decisions, phase expansions, and operational contracts so nothing is lost. It folds INTO the parent plan's 6 phases — it does NOT replace them.

---

## Confirmed Decisions (Locked)

### Decision: Approach C — Pine Authority + Dashboard Advisory with Sync Alerts

- Pine has the promoted packet as static lookups (maps/matrices in Pine v6)
- Dashboard refreshes every 15m from local Mac via `predict_proba()`
- When dashboard probability differs from Pine's static lookup by >15%, dashboard shows **"SYNC RECOMMENDED"**
- Dashboard displays the exact Pine input values the trader should update IF they choose to sync
- Pine is independent. Dashboard fills the freshness gap. Sync is the trader's call.

### Decision: Cadence Hierarchy (Pine Packet Promotion Only)

| Cadence | Action | Where |
|---------|--------|-------|
| **Weekly** (Sunday) | Full retrain + SHAP + new packet candidate | Local Mac |
| **Daily** (pre-session) | SHAP refresh on existing model → dashboard advisory update | Local Mac |
| **Every 15m** (market hours) | `predict_proba()` refresh → dashboard only | Local Mac → Supabase cloud |
| **Pine inputs** | Updated manually when a new packet is promoted | Trader manually |

### Decision: Local PostgreSQL (Plain, No TimescaleDB)

- `brew install postgresql@16`
- Monthly declarative partitions on `mes_1m`
- Materialized views for 15m/1h/4h/1d aggregation
- `pg_cron` for periodic refresh
- Feature engineering in PL/pgSQL
- BRIN indexes on `ts`
- ~700K rows over 2 years — no compression needed

### Decision: Cloud vs Local DB Topology

| | **Supabase Cloud** | **Local PostgreSQL** |
|---|---|---|
| **Role** | Frontend/ops/publish | Training/research/inference |
| **Tables** | warbird_forecasts, warbird_setups, warbird_risk, mes_15m, mes_1d, cross_asset_1h, econ_*, news_signals, geopolitical_risk_1d, trump_effect_1d | All cloud tables synced down + training_features, training_snapshots, model_runs, inference_results, shap_results, shap_indicator_settings, features_catalog |
| **Writes from** | Supabase crons (pg_cron + Edge Functions), local inference publish | sync-down from cloud, feature builder, AG training |
| **Who reads** | Dashboard (Vercel Next.js), API routes | AG training, SHAP pipeline, feature engineering |

### Decision: Two-Tier Architecture (Supabase + Local Mac)

**All server-side crons and functions run on Supabase. Vercel is UI + API only.**

- **Tier 1 (Supabase):** ALL crons, ALL ingestion, ALL background compute
  - pg_cron + http extension: simple GET→INSERT (FRED, econ-calendar, GPR, trump-effect)
  - Supabase Edge Functions (Deno): complex logic (MES/Databento ingestion, detect-setups, score-trades, forecast, cross-asset)
  - Database functions (PL/pgSQL): aggregation, feature engineering, materialized view refresh
- **Tier 2 (Local Mac):** Training + research only — sync-down, build-features, AG train, SHAP, inference, packet generation

**Vercel (Next.js):** Dashboard UI + API routes for frontend + auth. No crons. No background compute.

**Why:** Data gravity — compute sits next to the database. Zero network round-trips for pg_cron. Kills Vercel invocation costs. Clean separation of concerns.

---

## Research Findings (Evidence-Based)

### AutoGluon Constraints (Confirmed)

| Question | Answer | Source |
|----------|--------|--------|
| Incremental training? | **No.** `fit_extra()` adds model types, not new data. Full retrain required. | [fit_extra docs](https://auto.gluon.ai/stable/api/autogluon.tabular.TabularPredictor.fit_extra.html) |
| Single-row inference speed? | 10-200ms warm (with `persist()`), 1-2s cold | [GitHub #376](https://github.com/autogluon/autogluon/issues/376) |
| Walk-forward CV? | **Manual.** Use `tuning_data` param. No built-in time-series splits. | [GitHub #4492](https://github.com/autogluon/autogluon/issues/4492) |
| Calibration? | Temperature scaling, auto-enabled with `log_loss` eval metric | [fit docs](https://auto.gluon.ai/stable/api/autogluon.tabular.TabularPredictor.fit.html) |
| `distill()`? | Ensemble → simpler model. Can distill to single LightGBM → extract thresholds | [distill docs](https://auto.gluon.ai/stable/api/autogluon.tabular.TabularPredictor.distill.html) |
| Feature importance? | Permutation importance + group importance built-in | [feature_importance docs](https://auto.gluon.ai/stable/api/autogluon.tabular.TabularPredictor.feature_importance.html) |
| Batch vs single inference? | Batch 100 rows = sub-second. Single-row = painful overhead. Use batch at bar close. | [In-depth tutorial](https://auto.gluon.ai/stable/tutorials/tabular/tabular-indepth.html) |

### TradingView / Pine Script v6 Constraints (Confirmed)

| Constraint | Limit | Implication |
|------------|-------|-------------|
| `request.*()` calls | **40 unique** (64 on Ultimate) | Budget: 11 planned, 5 reserve. Tight but workable. |
| `request.seed()` | **Dead.** New repos suspended. Daily OHLCV only. | Cannot load model packets via request.seed(). Hard-code into Pine. |
| Maps | 50,000 key-value pairs | Calibration lookup tables (setup_bucket × confidence_bin → probability) fit trivially. |
| Matrices | 100,000 elements | 2D calibration grids (20 setup types × 5 bins = 100 elements) — no issue. |
| Memory | ~10 MB per script | Calibration tables are bytes, not MB. |
| Execution time | 40 seconds (paid) | Table rendering + lookups well within budget. |
| Compiled tokens | 100,000 | Must monitor as indicator grows. |
| `alert()` | Dynamic `series string` | Can embed probabilities, fib levels, confidence in alert text. |
| Inputs | No hard limit | Grouped inputs via `group` parameter for organized settings panel. |
| Tables | No hard row/col limit | Practical limit is screen space. Target: 12-15 rows max. |

### SHAP Pipeline (Confirmed — 5-Step Process)

**Daily path: TreeExplainer on best single tree model. Under 5 minutes on M4 Pro.**

1. **Compute SHAP values** — Extract best LightGBM/XGBoost from AG leaderboard, run `shap.TreeExplainer(model)`
2. **Identify golden zones** — Bin feature values into quantiles, find contiguous positive-SHAP regions
3. **Validate with surrogate tree** — Train shallow `DecisionTreeRegressor(max_depth=4)` on SHAP values → extract if-then rules
4. **Cross-validate thresholds** — Rolling median of last 4 weekly retrains dampens noise
5. **Encode as Pine inputs** — Generate `input.*()` values from stable thresholds

**Key stability finding:** Top 5 features have Kendall's W = 0.93 across retrains (highly stable). Mid-tier features (6-11) have W = 0.34 (unstable). Only extract Pine thresholds from top 5-8 features. Update Pine only when threshold shifts >10%.

**Two SHAP modes:**
- **TreeExplainer** (daily): Fast (1-3 min), explains best single tree model, gives interaction values
- **KernelExplainer** (quarterly): Slow (2-8 hours), explains full ensemble, use for deep validation only

### SHAP for Indicator Settings Discovery

Feed every candidate indicator length as a separate feature column:
```python
features = {
    "RSI_8": ta.rsi(close, 8),
    "RSI_14": ta.rsi(close, 14),
    "SMA_21": ta.sma(close, 21),
    "SMA_50": ta.sma(close, 50),
    # etc.
}
```
SHAP bar plot directly shows which variant matters most. Handle multicollinearity by retraining with only the winning length after discovery.

---

## Phase Expansions (Fold Into Parent Plan)

The parent plan has 6 phases. These expansions add explicit sub-steps for elements the plan references but doesn't detail.

### P0: Prerequisites (NEW — Before Phase 1)

**Anti-Contamination Safeguards:**
1. Audit all `lib/setup-engine.ts` Rabid Raccoon lineage — document, do NOT delete yet (may contain useful logic)
2. Add `source_project: "warbird-pro"` tag to all dataset artifacts
3. Add training script assertion: reject any data path containing "rabid-raccoon"
4. Add CI-style grep check: fail if forbidden path patterns appear in new code

**Pipeline De-Duplication:**
1. Mark `scripts/build-dataset.py` and `scripts/train-warbird.py` as DEPRECATED with clear error messages pointing to canonical path
2. Canonical path: `scripts/warbird/*` (existing) → will become `scripts/ag/*` per parent plan
3. Update admin UI text that references ambiguous script paths (`app/(workspace)/admin/page.tsx:696`)

**Gate:** Repo clean, no ambiguous pipelines, contamination safeguards in place.

### Phase 1: Series Inventory Freeze (No Changes)

Existing plan is sufficient. Quick verification pass against live TradingView.

### Phase 2: Refactor Current Script (No Changes)

Existing forensic review + 8 high-risk problems are the work. No additions needed.

### Phase 3: Strategy Build (No Changes)

Port shared logic, implement stop/target, +20 gate, Deep Backtesting baseline.

### Phase 4: Dataset + AG Loop (EXPANDED)

Add these explicit sub-steps:

**4.1 Local PostgreSQL Setup**
- `brew install postgresql@16`
- Create local training database
- Apply schema: training_features, training_snapshots, model_runs, inference_results
- Apply SHAP schema: shap_results, shap_indicator_settings, features_catalog, training_features (per draft §5.2)
- Set up `pg_cron` for materialized view refresh
- Monthly partitions on `mes_1m`

**4.2 Sync-Down Pipeline**
- Script to pull Supabase cloud → local PG (incremental by `ts` watermark)
- ~35 tables, all existing cloud tables
- Full sync weekly (Sunday), incremental every 5m during market hours

**4.3 Feature Export + Dataset Build**
- `scripts/ag/build-fib-dataset.py` (per parent plan §13)
- Supabase 2-year data + TradingView CSV indicator columns
- Walk-forward splits: expanding window, 3-month min training, 1-month validation, 40-bar purge, 80-bar embargo, 5 folds
- Leakage audit: confirm no joined feature timestamp exceeds MES row timestamp

**4.4 AG Training**
- `scripts/ag/train-fib-model.py` (per parent plan §13)
- TP1/TP2 probability models + stop-family evaluation
- `eval_metric="log_loss"` for calibrated probabilities
- `presets="best_quality"`, `num_bag_folds=5`, `num_stack_levels=2`
- Walk-forward validation per parent plan §8
- Use `predictor.persist()` for inference speed

**4.5 SHAP Discovery + Packet Generation**
- TreeExplainer on best tree model (daily path, <5 min)
- Golden zone extraction via quantile binning
- Surrogate decision tree for rule extraction
- Rolling median across 4 weekly retrains for stability
- `scripts/ag/generate-packet.py` → Pine-ready optimization packet (format per parent plan §12)
- Store results in `shap_results` and `shap_indicator_settings` tables

**4.6 Outcome Feedback Loop**
- `score-trades` Vercel cron already captures TP1_HIT, TP2_HIT, STOPPED, EXPIRED
- Close the loop: feed scored outcomes back into training labels
- Add `label_origin` field: `forward_scan` (synthetic) vs `setup_event` (real outcome)
- Prioritize `setup_event` labels when available; fall back to `forward_scan` for history

**Gate:** First AG model trained, calibration passing (error ≤ 10%), first packet generated, SHAP pipeline producing stable thresholds.

### Phase 5: Indicator UI Build (EXPANDED)

Add:

**5.5 Dashboard Advisory System (Approach C)**
- 15m `predict_proba()` refresh from local Mac → Supabase `warbird_forecasts`
- Dashboard reads `warbird_forecasts` and compares to Pine's static packet
- When probability differs >15% → show "SYNC RECOMMENDED"
- Dashboard displays exact Pine input values to update
- Dashboard shows: open trade state, entry/exit levels, probabilities, win rates
- Win rates pulled from most recent training results — real stats only, no fabricated metrics
- 80%+ probability threshold for actionable display; below that = informational only with sample count shown

**Gate:** Indicator renders all canonical outputs, dashboard advisory working, SYNC alerts firing.

### Phase 6: Walk-Forward Validation (EXPANDED)

Add:

**6.5 Rollback Triggers (Hard-Fail Conditions)**
1. Cross-project data contamination detected → immediate rollback to last clean model
2. Forecast staleness >90 minutes during active session → rollback to prior promoted packet
3. Calibration drift: probability bucket error exceeds 15% for ≥ 2 consecutive weeks → rollback
4. Pine/backend contract mismatch (Pine outputs don't match packet values) → rollback
5. False-positive rate on high-confidence calls (BIN_5) exceeds 50% over 20+ samples → rollback

**6.6 Operational Cadence Policy**
- Weekly: Full retrain + SHAP + new packet candidate
- Daily (pre-session): SHAP refresh → dashboard update
- Every 15m (market hours): predict_proba() → dashboard
- Pine inputs: Updated manually on promotion (weekly or on-demand)
- Packet promotion requires: all Phase 6 metrics passing, manual trader review

**Gate:** Out-of-sample validation passing, rollback triggers documented and testable, operational cadence validated.

---

## Schema Additions Needed (Local DB)

These tables exist in the draft (§5.2) but are not yet in any migration:

```sql
-- Training run metadata
CREATE TABLE training_runs (
    run_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    preset_used TEXT NOT NULL,
    dataset_date_range TSTZRANGE NOT NULL,
    feature_count INT NOT NULL,
    model_accuracy NUMERIC,
    tp1_auc NUMERIC,
    tp2_auc NUMERIC,
    calibration_error NUMERIC,
    notes TEXT,
    packet_status TEXT CHECK (packet_status IN ('CANDIDATE', 'PROMOTED', 'FAILED', 'SUPERSEDED'))
);

-- Feature registry
CREATE TABLE features_catalog (
    feature_id SERIAL PRIMARY KEY,
    feature_name TEXT NOT NULL UNIQUE,
    indicator_type TEXT,
    indicator_length INT,
    timeframe TEXT,
    data_source TEXT,
    tier TEXT CHECK (tier IN ('1_pine_live', '2_research_only')),
    is_active BOOLEAN DEFAULT true
);

-- SHAP results per feature per run
CREATE TABLE shap_results (
    id SERIAL PRIMARY KEY,
    run_id UUID REFERENCES training_runs(run_id),
    feature_id INT REFERENCES features_catalog(feature_id),
    golden_zone_min NUMERIC,
    golden_zone_max NUMERIC,
    mean_abs_shap NUMERIC,
    positive_contribution_pct NUMERIC,
    rank_in_run INT
);

-- SHAP-discovered optimal indicator settings
CREATE TABLE shap_indicator_settings (
    id SERIAL PRIMARY KEY,
    run_id UUID REFERENCES training_runs(run_id),
    indicator_type TEXT NOT NULL,
    optimal_length INT,
    optimal_timeframe TEXT,
    shap_weight NUMERIC,
    stable_threshold_value NUMERIC,
    rolling_median_4wk NUMERIC,
    notes TEXT
);

-- Inference results (every 15m prediction)
CREATE TABLE inference_results (
    id SERIAL PRIMARY KEY,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    bar_close_ts TIMESTAMPTZ NOT NULL,
    run_id UUID REFERENCES training_runs(run_id),
    direction TEXT,
    confidence_score NUMERIC,
    tp1_probability NUMERIC,
    tp2_probability NUMERIC,
    reversal_risk NUMERIC,
    features_json JSONB,
    published_to_cloud BOOLEAN DEFAULT false
);
```

---

## Indicator Settings Reference

Current indicator settings (from memory, verified 2026-03-20):

| Indicator | Setting | Source |
|-----------|---------|--------|
| RSI | Length 8 | Kirk's chart |
| MACDRe | 8/17/9, T3 0.7 | Kirk's chart |
| DPMO | 35/20/10 | Kirk's chart |
| VFI | 130 | Kirk's chart |
| OBPI | 60min MTF | Kirk's chart |
| ESSTOCH | 14/3 | Kirk's chart |
| SQZMOM | BB20/KC20 | Kirk's chart |
| Synthetic OB | Default | Kirk's chart |

**AG's job:** Validate these settings. SHAP will tell us if RSI(8) beats RSI(14), if MACD(8/17/9) beats (12/26/9), etc. These are the STARTING values. AG optimizes from here.

---

## Open Questions Resolved by Research

| Draft Question (§12) | Answer | Evidence |
|---|---|---|
| Can AG warm-start/incrementally update? | **No.** Full retrain required. fit_extra adds model types only. | AG docs |
| Can Pine read external data for auto-update? | **No.** request.seed() is dead. Hard-code values. | TV docs, Pine Seeds suspended |
| How many Pine inputs are practical? | **No hard limit.** Use `group` parameter for organization. | TV docs |
| Can prediction run in <60s for single candle? | **Yes.** 10-200ms warm with persist(). Batch 100 rows = sub-second. | AG docs, GitHub #376 |
| Should dashboard be "single pane of glass"? | **Yes — as advisory.** Approach C: Pine is authority, dashboard is advisory with SYNC alerts. | Confirmed decision |
| Is SHAP stable across retraining? | **Top 5 features yes** (W=0.93). Mid-tier no (W=0.34). Only extract Pine thresholds from top features. | SHAP stability research |

---

## What This Doc Does NOT Cover

- The actual Pine Script code (Phase 2-3 work)
- Specific TradingView CSV export procedures
- The exact dashboard UI layout/design
- Monte Carlo integration (v2 research item, not v1)
- Indicator color scheme / visual design
- Alert sound configuration

---

## Next Step

This design doc gets committed. Then invoke `writing-plans` to break each phase into checkpointed sub-tasks for the VSCode agent to execute with superpowers discipline.
