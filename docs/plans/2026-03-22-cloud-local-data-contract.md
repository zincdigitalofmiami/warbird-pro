# Cloud/Local Data Contract — 2026-03-22 (CORRECTED)

> **Verified:** Triple-checked against actual migrations (12 files), cron route code (12 routes), and grep-audited zombie tables. Replaces original draft.

## Decision

Local PostgreSQL is **not** a strict mirror of cloud Supabase.

- **Cloud (Supabase)** stores everything required by dashboard/ops + all training input data.
- **Local (`warbird_training`)** stores training-working datasets and model-build artifacts.
- Sync is **bidirectional by purpose**, not mirror-by-default.

## Complete Cloud Table Inventory — 47 Tables

Verified against `supabase/migrations/` (files 002-012).

### Symbols (4)
`symbols`, `symbol_roles`, `symbol_role_members`, `symbol_mappings`

### MES OHLCV (6)
`mes_1s`, `mes_1m`, `mes_15m`, `mes_1h`, `mes_4h`, `mes_1d`

- `mes_1s`: schema only, nothing writes yet (chart bar fill, dormant)
- `mes_1m` + `mes_1h`: pulled from Databento (`ohlcv-1m`, `ohlcv-1h`, `raw_symbol`, `GLBX.MDP3`)
- `mes_15m`, `mes_4h`, `mes_1d`: aggregated in TypeScript from 1m/1h — NOT pulled from Databento

### Cross-Asset (4)
`cross_asset_1h`, `cross_asset_1d`, `options_stats_1d`, `options_ohlcv_1d`

- `options_stats_1d`: has backfill script, Databento has schema — keep for future AG features
- `options_ohlcv_1d`: ZOMBIE — no writer, no reader. Drop in migration 013.

### Econ (11)
`series_catalog`, `econ_rates_1d`, `econ_yields_1d`, `econ_fx_1d`, `econ_vol_1d`, `econ_inflation_1d`, `econ_labor_1d`, `econ_activity_1d`, `econ_money_1d`, `econ_commodities_1d`, `econ_indexes_1d`

- `series_catalog`: seed data only — no active writer. If stale, all FRED ingestion stops.

### News/Events (7)
`econ_news_1d`, `policy_news_1d`, `macro_reports_1d`, `econ_calendar`, `news_signals`, `geopolitical_risk_1d`, `trump_effect_1d`

- `policy_news_1d`: ZOMBIE — no writer. Drop in migration 013.
- `macro_reports_1d`: CRITICAL DEPENDENCY — news cron reads it. Wire up AlphaVantage cron writer (see below).

### Trading/Model (5)
`trade_scores`, `measured_moves`, `vol_states`, `sources`, `models`

- `trade_scores`: ZOMBIE — drop in migration 013
- `vol_states`: ZOMBIE — drop in migration 013
- `sources`: ZOMBIE — drop in migration 013
- `models`: DORMANT — keep for AG training phase

### Warbird v2 (8)
`warbird_daily_bias`, `warbird_structure_4h`, `warbird_forecasts_1h`, `warbird_triggers_15m`, `warbird_conviction`, `warbird_setups`, `warbird_setup_events`, `warbird_risk`

- `warbird_forecasts_1h`: written by EXTERNAL service via `WARBIRD_FORECAST_WRITER_URL` (local Mac AG model). No Vercel cron writes to it.

### Ops (2)
`job_log`, `coverage_log`

- `coverage_log`: ZOMBIE — nothing writes. Keep for potential future use.

## Route → Table Write Map

| Cron Route | Writes To | Schedule |
|-----------|----------|---------|
| mes-catchup | mes_1m, mes_15m, mes_1h, mes_4h, mes_1d, job_log | `*/5 * * * 0-5` |
| cross-asset | cross_asset_1h, cross_asset_1d, job_log | `*/15 * * * *` |
| fred/[category] (×10) | econ_{category}_1d, job_log | staggered daily 05-14 UTC |
| econ-calendar | econ_calendar, job_log | `0 15 * * *` |
| google-news | econ_news_1d, news_signals, job_log | `0 13 * * 1-5` |
| news | news_signals, job_log | `0 16 * * *` |
| gpr | geopolitical_risk_1d, job_log | `0 19 * * *` |
| trump-effect | trump_effect_1d, job_log | `30 19 * * *` |
| detect-setups | warbird_daily_bias, warbird_structure_4h, warbird_triggers_15m, warbird_conviction, warbird_setups, warbird_setup_events, measured_moves, job_log | `*/5 12-21 * * 1-5` |
| score-trades | warbird_setups, warbird_setup_events, measured_moves, job_log | `10,25,40,55 * * * 1-5` |
| measured-moves | measured_moves, job_log | `0 18 * * 1-5` |
| forecast | job_log only (calls EXTERNAL writer URL) | `30 * * * 1-5` |

### Orphaned Read Dependencies

| Table Read | Read By | Writer | Status |
|-----------|---------|--------|--------|
| macro_reports_1d | news cron | NONE (manual backfill only) | FIX: wire up AlphaVantage cron |
| warbird_forecasts_1h | detect-setups, forecast | EXTERNAL (local Mac) | OK — by design |
| series_catalog | all fred crons | NONE (seed data) | MONITOR — stale catalog = no FRED |

## Sync Direction Contract

### Cloud → Local (training inputs) — 37 tables

**MES OHLCV (5):** `mes_1m`, `mes_15m`, `mes_1h`, `mes_4h`, `mes_1d`

**Cross-asset (2):** `cross_asset_1h`, `cross_asset_1d`

**Econ (11):** `series_catalog`, `econ_rates_1d`, `econ_yields_1d`, `econ_fx_1d`, `econ_vol_1d`, `econ_inflation_1d`, `econ_labor_1d`, `econ_activity_1d`, `econ_money_1d`, `econ_commodities_1d`, `econ_indexes_1d`

**News/Events (6):** `econ_calendar`, `econ_news_1d`, `news_signals`, `geopolitical_risk_1d`, `trump_effect_1d`, `macro_reports_1d`

**Warbird v2 — training labels + features (9):** `warbird_daily_bias`, `warbird_structure_4h`, `warbird_forecasts_1h`, `warbird_triggers_15m`, `warbird_conviction`, `warbird_setups`, `warbird_setup_events`, `warbird_risk`, `measured_moves`

**Symbols (3):** `symbols`, `symbol_roles`, `symbol_role_members`

**Ops (1):** `job_log`

### Local → Cloud (training outputs) — needs migration 013

`shap_results`, `training_reports`, `model_packets`, `training_runs`

### Local-only

`feature_matrix`, `training_labels`, scratch/intermediate tables

## Migration 013 Scope

### CREATE (4 tables)
- `shap_results`
- `training_reports`
- `model_packets`
- `training_runs`

### DROP (5 zombie tables)
- `trade_scores`
- `vol_states`
- `sources`
- `policy_news_1d`
- `options_ohlcv_1d`

### KEEP (decided)
- `options_stats_1d` — Databento has schema, future AG feature
- `macro_reports_1d` — active dependency, needs AlphaVantage cron writer
- `coverage_log` — dormant, keep for future observability
- `models` — dormant, needed for AG training phase
- `mes_1s` — dormant, chart bar fill intent

## macro_reports_1d: AlphaVantage Fix

**API:** AlphaVantage News Sentiment (`NEWS_SENTIMENT`)
**Key:** `FKNRDPNNDJ8MCJGU`
**Topics:** `financial_markets`, `economy_fiscal`, `economy_monetary`, `economy_macro`, `energy_transportation`, `finance`, `retail_wholesale`, `technology`
**Params:** `time_from`, `time_to` (YYYYMMDDTHHMM), `sort=LATEST`, `limit=50`
**Implementation:** Supabase pg_cron + Edge Function, daily pre-market
**Target table:** `macro_reports_1d`

## econ_indicators View

Keep canonical storage as existing `econ_*` tables. Add normalized view if needed:
```sql
CREATE VIEW econ_indicators AS
SELECT ts, series_id, value, 'rates' as category, created_at FROM econ_rates_1d
UNION ALL SELECT ts, series_id, value, 'yields', created_at FROM econ_yields_1d
-- ... etc for all 10 category tables
```

## Databento Contract

| What | Schema | stype_in | Dataset |
|------|--------|----------|---------|
| MES 1m bars | `ohlcv-1m` (free) | `raw_symbol` | `GLBX.MDP3` |
| MES 1h bars | `ohlcv-1h` (free) | `raw_symbol` | `GLBX.MDP3` |
| Cross-asset 1h | `ohlcv-1h` (free) | `continuous` (volume roll) | `GLBX.MDP3` |

- 15m, 4h, 1d aggregated in TypeScript — not from Databento
- Options stats: Databento schema available, backfill script exists
- Contract roll: 8-day-before-3rd-Friday rule matching TradingView MES1!

## Implementation Guardrails

- No ORM; Supabase/Postgres only.
- Snake_case columns.
- Table prefixes: `mes_`, `cross_asset_`, `econ_`, `warbird_` for canonical tables.
- New training-reporting tables: snake_case, explicit PK/index/watermark fields.
- Local writes training outputs; cloud dashboard reads them.
- All crons currently run on Vercel. Migration to Supabase pg_cron is FUTURE intent, not current state.
