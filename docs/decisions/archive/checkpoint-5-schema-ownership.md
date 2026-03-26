# Checkpoint 5: Schema Ownership Map

**Date:** 2026-03-19
**Status:** Decision Made
**Checkpoint:** Supabase Architecture Rethink — Checkpoint 5
**Depends on:** Checkpoint 1 (local PG), Checkpoint 2 (mes_1s ephemeral), Checkpoint 3 (DB URL topology), Checkpoint 4 (API scaffolding + data enrichment)

---

## Decision

Every table classified into one of four ownership categories. Most data tables exist in **both** cloud and local — cloud is the publication/dashboard layer, local is the training warehouse. The sync direction is explicit: cloud crons ingest → local syncs down for training → local inference publishes up to cloud.

---

## Ownership Categories

| Category | Purpose | Retention | Sync Direction |
|----------|---------|-----------|----------------|
| **Cloud Ephemeral** | Live chart forming bar | 24-48h TTL | Never synced to local |
| **Cloud Only** | Operational/reference, not training-relevant | Permanent in cloud | Never synced to local |
| **Both (Cloud + Local)** | Cloud = publication, Local = training warehouse | Permanent both | Cloud → Local (pull down for training) |
| **Local Only** | Training artifacts, feature engineering | Permanent in local | Local → Cloud (publish inference results up) |

---

## Complete Table Map

### MES Data

| Table | Cloud | Local | Category | Notes |
|-------|-------|-------|----------|-------|
| `mes_1s` | Ephemeral (24-48h TTL) | — | **Cloud Ephemeral** | Powers forming 15m bar. Realtime enabled. Not training data. |
| `mes_1m` | Yes (chart history) | Yes (retained raw) | **Both** | Canonical raw bar. Cloud ingested from Databento. Local synced for training. |
| `mes_15m` | Yes (chart primary, Realtime) | Yes (materialized view) | **Both** | Cloud: derived from 1m in TS. Local: mat view from local 1m. |
| `mes_1h` | Yes (direct from Databento) | Yes (retained) | **Both** | Cloud ingested. Local synced. |
| `mes_4h` | Yes (derived from 1h) | Yes (mat view) | **Both** | Cloud: TS aggregation. Local: mat view from local 1h. |
| `mes_1d` | Yes (from Databento ohlcv-1d) | Yes (retained) | **Both** | Target: direct Databento pull, not aggregated. |

### MES Enrichment (NEW — from Checkpoint 4)

| Table | Cloud | Local | Category | Notes |
|-------|-------|-------|----------|-------|
| `mes_statistics` | Yes | Yes | **Both** | Settlement, OI, volume, session H/L. Daily. High training value. |
| `mes_definition` | Yes | Yes | **Both** | Contract specs, expiry, tick size. Daily refresh. |

### Cross-Asset Data

| Table | Cloud | Local | Category | Notes |
|-------|-------|-------|----------|-------|
| `cross_asset_1h` | Yes (sharded ingestion) | Yes (retained) | **Both** | Non-MES futures hourly bars. |
| `cross_asset_1d` | Yes (aggregated from 1h) | Yes (retained) | **Both** | Target: direct Databento ohlcv-1d pull. |

### Cross-Asset Enrichment (NEW — from Checkpoint 4)

| Table | Cloud | Local | Category | Notes |
|-------|-------|-------|----------|-------|
| `cross_asset_statistics` | Yes | Yes | **Both** | Settlement, OI, volume per symbol. Daily. |
| `cross_asset_definition` | Yes | Yes | **Both** | Contract specs per symbol. Daily refresh. |

### Options Data (Existing tables, currently empty)

| Table | Cloud | Local | Category | Notes |
|-------|-------|-------|----------|-------|
| `options_ohlcv_1d` | Yes | Yes | **Both** | Daily option price bars. Currently empty — populated by new crons. |
| `options_stats_1d` | Yes | Yes | **Both** | Option settlement, OI, volume. Currently empty. |

### Options Enrichment (NEW — from Checkpoint 4)

| Table | Cloud | Local | Category | Notes |
|-------|-------|-------|----------|-------|
| `options_definition` | Yes | Yes | **Both** | Strike, expiry, put/call, underlying. Maps option → future. |

### Economic Data (10 FRED categories)

| Table | Cloud | Local | Category | Notes |
|-------|-------|-------|----------|-------|
| `econ_rates_1d` | Yes | Yes | **Both** | Fed funds, T-bill, etc. |
| `econ_yields_1d` | Yes | Yes | **Both** | Treasury yields. |
| `econ_fx_1d` | Yes | Yes | **Both** | USD pairs. |
| `econ_vol_1d` | Yes | Yes | **Both** | VIX, MOVE, etc. |
| `econ_inflation_1d` | Yes | Yes | **Both** | CPI, PPI, breakevens. |
| `econ_labor_1d` | Yes | Yes | **Both** | NFP, claims, etc. |
| `econ_activity_1d` | Yes | Yes | **Both** | PMI, ISM, etc. |
| `econ_money_1d` | Yes | Yes | **Both** | M2, reserves, etc. |
| `econ_commodities_1d` | Yes | Yes | **Both** | Gold, oil, etc. |
| `econ_indexes_1d` | Yes | Yes | **Both** | SP500, NDX, etc. |
| `series_catalog` | Yes | — | **Cloud Only** | FRED series reference metadata. |

### News & Events

| Table | Cloud | Local | Category | Notes |
|-------|-------|-------|----------|-------|
| `econ_news_1d` | Yes | Yes | **Both** | Google News scraper output. Training: sentiment features. |
| `policy_news_1d` | Yes | Yes | **Both** | Policy news. |
| `macro_reports_1d` | Yes | Yes | **Both** | Macro report summaries. |
| `econ_calendar` | Yes | Yes | **Both** | Economic event calendar. Training: event timing features. |
| `news_signals` | Yes | Yes | **Both** | Derived news signals. Training: directional sentiment. |
| `geopolitical_risk_1d` | Yes | Yes | **Both** | GPR index. Training: risk regime feature. |
| `trump_effect_1d` | Yes | Yes | **Both** | Federal Register policy tracker. Training: policy feature. |

### Warbird Signal Tables (8 — migration 010)

| Table | Cloud | Local | Category | Notes |
|-------|-------|-------|----------|-------|
| `warbird_daily_bias` | Yes (published) | Yes | **Both** | 200d MA bias. Training: outcome analysis. |
| `warbird_structure_4h` | Yes (published) | Yes | **Both** | 4H structure. Training: outcome analysis. |
| `warbird_forecasts_1h` | Yes (published, Realtime) | Yes | **Both** | Model forecasts. Training: model feedback loop. |
| `warbird_triggers_15m` | Yes (published) | Yes | **Both** | Trigger evaluations. Training: trigger quality analysis. |
| `warbird_conviction` | Yes (published, Realtime) | Yes | **Both** | Conviction scoring. Training: conviction calibration. |
| `warbird_setups` | Yes (published, Realtime) | Yes | **Both** | Active/completed setups. Training: setup outcome analysis. |
| `warbird_setup_events` | Yes (published, Realtime) | Yes | **Both** | Setup lifecycle events. Training: outcome timing analysis. |
| `warbird_risk` | Yes (published) | Yes | **Both** | Risk parameters. Training: risk calibration. |

### Pattern Detection

| Table | Cloud | Local | Category | Notes |
|-------|-------|-------|----------|-------|
| `measured_moves` | Yes (published) | Yes | **Both** | AB=CD patterns. Training: pattern outcome analysis. |

### Operational / Reference (Cloud Only)

| Table | Cloud | Local | Category | Notes |
|-------|-------|-------|----------|-------|
| `symbols` | Yes | — | **Cloud Only** | Symbol reference. 60 seeded. Read by crons. |
| `job_log` | Yes | — | **Cloud Only** | Cron job execution log. Operational only. |
| `sources` | Yes | — | **Cloud Only** | Data source reference. |
| `coverage_log` | Yes | — | **Cloud Only** | Data coverage tracking. |
| `models` | Yes | — | **Cloud Only** | Model registry (future). |
| `trade_scores` | Yes | — | **Cloud Only** | Legacy scoring. May be superseded by warbird_setups. |
| `vol_states` | Yes | — | **Cloud Only** | Volatility state tracking. |

### Training-Specific (Local Only)

| Table | Cloud | Local | Category | Notes |
|-------|-------|-------|----------|-------|
| `training_features` | — | Yes | **Local Only** | Pre-computed feature rows for AutoGluon. Built from all local tables. |
| `training_snapshots` | — | Yes | **Local Only** | Immutable point-in-time feature snapshots per training run. |
| `model_runs` | — | Yes | **Local Only** | Training run metadata (hyperparams, metrics, model path). |
| `inference_results` | — | Yes | **Local Only** | Raw inference output before publication to cloud. |

---

## Sync Topology

```
┌─────────────────────────────────────────────────────────┐
│                    CLOUD SUPABASE                        │
│                                                          │
│  Ingestion Crons ──→ Raw Tables (mes_*, cross_asset_*,  │
│                       econ_*, news_*, options_*)          │
│                                                          │
│  Warbird Crons ──→ Signal Tables (warbird_*)             │
│                                                          │
│  Forecast Writer ──→ warbird_forecasts_1h                │
│                                                          │
│  Dashboard/Chart ←── Realtime ←── Signal + MES tables    │
├─────────────────────────────────────────────────────────┤
│                    SYNC BOUNDARY                         │
│                                                          │
│  sync-down job:  Cloud raw + signal tables → Local PG    │
│                  (periodic pull, not realtime)            │
│                                                          │
│  sync-up job:    Local inference_results → Cloud          │
│                  warbird_forecasts_1h (publish)           │
└─────────────────────────────────────────────────────────┘
┌─────────────────────────────────────────────────────────┐
│                    LOCAL POSTGRESQL                       │
│                                                          │
│  Synced Tables ──→ All "Both" tables (retained copy)     │
│                                                          │
│  Materialized Views ──→ mes_15m_mv, mes_4h_mv from 1m   │
│                                                          │
│  Feature Engineering ──→ training_features               │
│                                                          │
│  AutoGluon ──→ training_snapshots → model_runs           │
│                                                          │
│  Inference ──→ inference_results → sync-up → Cloud       │
└─────────────────────────────────────────────────────────┘
```

### Sync-Down Job (Cloud → Local)

Runs locally (not a Supabase pg_cron). Pulls from cloud Supabase into local PG:
- All "Both" tables: incremental sync by `ts` watermark
- Frequency: daily (overnight) for most tables, more frequent for MES during market hours if needed
- Uses `LOCAL_DATABASE_URL` + `SUPABASE_URL` (per Checkpoint 3, `.env.training`)

### Sync-Up Job (Local → Cloud)

Runs locally. Publishes inference results to cloud:
- `inference_results` → `warbird_forecasts_1h` (cloud)
- This is what the `cron/forecast` route's health check monitors
- Uses `LOCAL_DATABASE_URL` + `SUPABASE_URL` + `SUPABASE_SERVICE_ROLE_KEY`

---

## Summary Counts

| Category | Table Count | Examples |
|----------|------------|---------|
| Cloud Ephemeral | 1 | mes_1s |
| Cloud Only | 8 | symbols, job_log, sources, coverage_log, models, trade_scores, vol_states, series_catalog |
| Both (Cloud + Local) | ~35 | All MES, cross-asset, options, econ, news, warbird, measured_moves + new enrichment tables |
| Local Only | 4 | training_features, training_snapshots, model_runs, inference_results |
| **Total** | **~48** | |

---

## Verification Checklist

| Rule | Passes? | Note |
|------|---------|------|
| Plan: training tables belong local | Yes | training_features, snapshots, model_runs all local-only |
| Plan: auth/dashboard/published signals belong cloud | Yes | warbird_* published in cloud, dashboard reads cloud |
| Plan: ephemeral not retained for training | Yes | mes_1s ephemeral cloud only, not synced to local |
| AGENTS.md: production boundary | Yes | Dashboard depends only on cloud. Training depends only on local. |
| AGENTS.md: no mock data | Yes | All tables populated from real sources |
| Cost boundary | Yes | No new paid schemas. All enrichment from free Databento schemas. |
| Checkpoint 3: clear DB target per runtime | Yes | Sync jobs are the only dual-target code (explicitly designed for this) |

---

## Implementation Implications

1. **New cloud tables needed:** mes_statistics, mes_definition, cross_asset_statistics, cross_asset_definition, options_definition (5 new migrations)
2. **New local-only tables:** training_features, training_snapshots, model_runs, inference_results (local DDL, not Supabase migrations)
3. **Sync-down script:** New local script that pulls "Both" tables from cloud → local PG
4. **Sync-up script:** New local script that publishes inference_results → cloud warbird_forecasts_1h
5. **Local materialized views:** mes_15m_mv, mes_4h_mv from local mes_1m (per Checkpoint 1)
6. **RLS:** New cloud tables need RLS (authenticated = SELECT, service role bypasses)
7. **Realtime:** No new Realtime subscriptions needed (existing mes_1m, mes_15m, warbird_* cover dashboard)
