# Corrected Cloud/Local Data Contract — 2026-03-22

**Replaces:** `2026-03-22-cloud-local-data-contract.md` (Kilo draft — had errors)
**Audited by:** Claude Opus, full migration + cloud dump + route audit
**Audit date:** 2026-03-22

---

## CRITICAL: Migration Crisis

**Migrations 010, 011, 012 have NOT been applied to cloud Supabase.**

Cloud is running migrations 001–009 only. This means:

| Migration | Status | Impact |
|-----------|--------|--------|
| 010 (Warbird V1 cutover) | **NOT APPLIED** | 8 new warbird tables DON'T EXIST in cloud. Old `forecasts` + old `warbird_setups` still there. |
| 011 (mes_1s + prob columns + runner removal) | **NOT APPLIED** | No `mes_1s` table. No probability columns on forecasts. Runner enum values still present. |
| 012 (measured_moves.setup_id) | **NOT APPLIED** | No FK link between measured_moves and warbird_setups. |

**Production impact:** Every cron that writes to warbird v1 tables (`detect-setups`, `score-trades`) is failing silently because `warbird_daily_bias`, `warbird_structure_4h`, `warbird_forecasts_1h`, `warbird_triggers_15m`, `warbird_conviction`, `warbird_setup_events`, `warbird_risk` do not exist in cloud.

**Action required BEFORE any other data work:**
```bash
cd warbird-pro
npx supabase db push --linked
```

---

## Cloud Table Inventory (After Migrations Applied)

### MES Price Data (5 active + 1 placeholder)

| Table | PK | Writer | Reader | Timeframe |
|-------|-----|--------|--------|-----------|
| `mes_1m` | ts | mes-catchup (Databento ohlcv-1m) | detect-setups, score-trades, admin/status | 1m |
| `mes_15m` | ts | mes-catchup (aggregated from 1m) | detect-setups, live/mes15m, pivots/mes, admin/status | 15m |
| `mes_1h` | ts | mes-catchup (Databento ohlcv-1h) | measured-moves, admin/status | 1h |
| `mes_4h` | ts | mes-catchup (aggregated from 1h) | detect-setups, admin/status | 4h |
| `mes_1d` | ts | mes-catchup (aggregated from 1h) | detect-setups, pivots/mes, admin/status | 1d |
| `mes_1s` | ts | **NOTHING** (table exists, no ingestion built) | — | 1s |

**Databento schemas used:** ohlcv-1m, ohlcv-1h (both FREE on Standard $179/mo)
**Aggregation:** TypeScript (lib/mes-aggregation.ts): 1m→15m, 1h→4h, 1h→1d
**mes_1s note:** Table created in migration 011. Intended for ephemeral intrabar fill on the 15m chart. Not yet implemented.

### Cross-Asset Data (4 tables)

| Table | PK | Writer | Reader |
|-------|-----|--------|--------|
| `cross_asset_1h` | (ts, symbol_code) | cross-asset cron (Databento ohlcv-1h, non-MES symbols) | admin/status |
| `cross_asset_1d` | (ts, symbol_code) | cross-asset cron (aggregated from 1h) | admin/status |
| `options_stats_1d` | (ts, symbol_code) | **NOTHING** | — |
| `options_ohlcv_1d` | (ts, symbol_code) | **NOTHING** | — |

### Economic Data (11 tables)

| Table | PK | Writer | Reader |
|-------|-----|--------|--------|
| `series_catalog` | id (series_id unique) | fred/[category] cron (seed data) | fred/[category] cron |
| `econ_rates_1d` | (ts, series_id) | fred/rates cron (FRED API) | — |
| `econ_yields_1d` | (ts, series_id) | fred/yields cron | — |
| `econ_fx_1d` | (ts, series_id) | fred/fx cron | — |
| `econ_vol_1d` | (ts, series_id) | fred/vol cron | — |
| `econ_inflation_1d` | (ts, series_id) | fred/inflation cron | — |
| `econ_labor_1d` | (ts, series_id) | fred/labor cron | — |
| `econ_activity_1d` | (ts, series_id) | fred/activity cron | — |
| `econ_money_1d` | (ts, series_id) | fred/money cron | — |
| `econ_commodities_1d` | (ts, series_id) | fred/commodities cron | — |
| `econ_indexes_1d` | (ts, series_id) | fred/indexes cron | — |

### News/Events Data (7 tables)

| Table | PK | Writer | Reader |
|-------|-----|--------|--------|
| `econ_news_1d` | id (auto) | google-news cron (Google News RSS) | admin/status |
| `policy_news_1d` | id (auto) | **NOTHING** | — |
| `macro_reports_1d` | id (auto) | **NOTHING** (intended for Trading Economics) | news cron (reads it) |
| `econ_calendar` | id (auto) | econ-calendar cron (Trading Economics API) | admin/status |
| `news_signals` | id (auto) | news cron + google-news cron | admin/status |
| `geopolitical_risk_1d` | ts | gpr cron (Caldara-Iacoviello XLS) | admin/status |
| `trump_effect_1d` | id (auto) | trump-effect cron (Federal Register API) | admin/status |

### Warbird V1 State Machine (8 tables — REQUIRE migration 010)

| Table | PK | Writer | Reader |
|-------|-----|--------|--------|
| `warbird_daily_bias` | ts | detect-setups cron | admin/status, warbird/signal |
| `warbird_structure_4h` | ts | detect-setups cron | admin/status, warbird/signal |
| `warbird_forecasts_1h` | id (symbol_code+ts unique) | detect-setups cron | detect-setups, forecast cron, warbird/signal |
| `warbird_triggers_15m` | id (symbol_code+ts+forecast_id unique) | detect-setups cron | warbird/signal |
| `warbird_conviction` | id | detect-setups cron | warbird/signal |
| `warbird_setups` | id (setup_key unique) | detect-setups cron, score-trades cron | score-trades, warbird/signal, warbird/history, admin/status |
| `warbird_setup_events` | id | detect-setups cron, score-trades cron | warbird/history, admin/status |
| `warbird_risk` | id | detect-setups cron | warbird/signal |

### Operations (4 active tables)

| Table | PK | Writer | Reader |
|-------|-----|--------|--------|
| `job_log` | id (auto) | **ALL crons** | admin/status |
| `measured_moves` | id (auto) | measured-moves cron, detect-setups cron | score-trades cron, admin/status |
| `symbols` | code | seed data (60 symbols) | cross-asset cron, detect-setups, admin/status |
| `symbol_roles` | id | seed data | — |
| `symbol_role_members` | (role_id, symbol_code) | seed data | — |
| `symbol_mappings` | id | seed data | — |

### ZOMBIE Tables (no active writer — cleanup candidates)

| Table | Created In | Writer | Disposition |
|-------|-----------|--------|-------------|
| `trade_scores` | 007 | **NONE** | DROP — superseded by warbird_setups scoring |
| `vol_states` | 007 | **NONE** | DROP — superseded by warbird_risk |
| `sources` | 007 | **NONE** | DROP — never populated |
| `coverage_log` | 007 | **NONE** | DROP — never populated |
| `models` | 007 | **NONE** | DROP — model registry not implemented |
| `options_stats_1d` | 004 | **NONE** | KEEP — schema correct, writer TBD |
| `options_ohlcv_1d` | 004 | **NONE** | KEEP — schema correct, writer TBD |
| `policy_news_1d` | 006 | **NONE** | KEEP — writer TBD |
| `macro_reports_1d` | 006 | **NONE** (but read by news cron) | KEEP — needs writer |

### STALE Enums (cleanup after migration 010 applied)

| Enum | Status | Notes |
|------|--------|-------|
| `setup_phase` | STALE | From old warbird_setups (007). Unused after 010. |
| `signal_status` | STALE | From old forecasts (007). Unused after 010. |

---

## Training Timeframes

Per Kirk (corrected from Kilo draft):

| Timeframe | Source | Purpose |
|-----------|--------|---------|
| 15m | mes_15m (aggregated from 1m) | PRIMARY model/chart/setup timeframe |
| 4h | mes_4h (aggregated from 1h) | HTF structure confirmation |
| 1d | mes_1d (aggregated from 1h) | Daily bias context |
| 1m | mes_1m (Databento ohlcv-1m) | Training input, trigger detection |
| 1h | mes_1h (Databento ohlcv-1h) | Measured move detection, HTF confluence |
| 1s | mes_1s (Databento ohlcv-1s, not yet built) | Future: intrabar chart fill on 15m bar |

**Databento pull pattern:** ohlcv-1m + ohlcv-1h → aggregate to 15m/4h/1d in TypeScript.

---

## Cloud/Local Ownership Model

### Cloud-Owned (Supabase — dashboard/ops/ingestion)

All 46 tables listed above are cloud-owned. They are the source of truth for:
- Live ingestion (MES, cross-asset, FRED, news, GPR, Trump Effect)
- Warbird state machine (bias → structure → forecast → trigger → conviction → setup → events)
- Operations (job_log, measured_moves)
- API surface (/warbird/signal, /warbird/history, /live/mes15m, /pivots/mes)

### Local-Only (warbird_training PostgreSQL — training warehouse)

These tables will exist ONLY in local PostgreSQL. No cloud migration needed:

| Table | Purpose | Populated By |
|-------|---------|-------------|
| `feature_matrix` | 54-column feature snapshots for AG training | Python build-fib-dataset.py |
| `training_labels` | Outcome labels (TP1_HIT, TP2_HIT, STOPPED) | Python build-fib-dataset.py |
| `features_catalog` | Feature registry with metadata | Python build-fib-dataset.py |
| `shap_indicator_settings` | SHAP-derived indicator parameter overrides | Python SHAP pipeline |
| `inference_results` | 15m prediction snapshots | Python predict-fib-model.py |
| Ad-hoc scratch tables | Intermediate training artifacts | Python scripts |

### Sync Direction

**Cloud → Local (training inputs):**
- `mes_1m`, `mes_15m`, `mes_1h`, `mes_4h`, `mes_1d`
- `cross_asset_1h`
- All 10 `econ_*_1d` tables + `econ_calendar`
- `news_signals`, `geopolitical_risk_1d`, `trump_effect_1d`
- `warbird_setups` + `warbird_setup_events` (for outcome labeling)

**Local → Cloud (ops outputs for dashboard):**

| Table | Schema Needed | Migration Status |
|-------|--------------|-----------------|
| `shap_results` | TBD | NOT IN ANY MIGRATION — needs new migration |
| `training_reports` | TBD | NOT IN ANY MIGRATION — needs new migration |
| `model_packets` | TBD | NOT IN ANY MIGRATION — needs new migration |
| `training_runs` | TBD | NOT IN ANY MIGRATION — needs new migration |

**Rule:** If dashboard needs it, cloud gets it. These 4 tables need schemas designed and migrations written before Phase 4.

---

## Supabase Environment Variables

### Current (from `deployment secrets inventory`)

| Variable | Environments | Status |
|----------|-------------|--------|
| `DATABENTO_API_KEY` | Prod, Dev | Active |
| `FRED_API_KEY` | Prod, Dev | Active |
| `NEXT_PUBLIC_SUPABASE_URL` | All | Active |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY` | All | Active (alias of PUBLISHABLE_KEY) |
| `NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY` | All | **DUPLICATE** of ANON_KEY |
| `SUPABASE_URL` | All | Active |
| `SUPABASE_ANON_KEY` | All | Active |
| `SUPABASE_PUBLISHABLE_KEY` | All | **DUPLICATE** of ANON_KEY |
| `SUPABASE_SERVICE_ROLE_KEY` | All | Active |
| `SUPABASE_SECRET_KEY` | All | **DUPLICATE** of SERVICE_ROLE_KEY |
| `SUPABASE_JWT_SECRET` | All | Active |
| `POSTGRES_URL` | All | Active |
| `POSTGRES_URL_NON_POOLING` | All | Active |
| `POSTGRES_HOST` | All | Active |
| `POSTGRES_USER` | All | Active |
| `POSTGRES_PASSWORD` | All | Active |
| `POSTGRES_DATABASE` | All | Active |
| `POSTGRES_PRISMA_URL` | All | **DEAD — Prisma banned** |

### Missing (referenced in code but not in env)

| Variable | Used By | Status |
|----------|---------|--------|
| `CRON_SECRET` | All cron routes (auth check) | **MISSING** — crons run unauthenticated |
| `WARBIRD_FORECAST_WRITER_URL` | forecast cron (health check) | **MISSING** — forecast health check fails |
| `TRADING_ECONOMICS_API_KEY` | econ-calendar cron | Needs verification |

### Cleanup Needed

1. Remove `POSTGRES_PRISMA_URL` — Prisma is banned
2. Remove `NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY` — duplicate of ANON_KEY
3. Remove `SUPABASE_PUBLISHABLE_KEY` — duplicate of ANON_KEY
4. Remove `SUPABASE_SECRET_KEY` — duplicate of SERVICE_ROLE_KEY
5. Add `CRON_SECRET` — security requirement
6. Add `WARBIRD_FORECAST_WRITER_URL` or remove forecast health check cron

---

## Cron Schedule Summary (23 schedules, 13 routes)

| Route | Schedule | External API | Writes To |
|-------|----------|-------------|-----------|
| mes-catchup | `*/5 * * * 0-5` | Databento (ohlcv-1m, ohlcv-1h) | mes_1m, mes_1h, mes_15m, mes_4h, mes_1d, job_log |
| cross-asset | `*/15 * * * *` | Databento (ohlcv-1h) | cross_asset_1h, cross_asset_1d, job_log |
| fred/[10 categories] | `0 5-14 * * *` (staggered hourly) | FRED API | econ_*_1d (by category), job_log |
| econ-calendar | `0 15 * * *` | Trading Economics | econ_calendar, job_log |
| news | `0 16 * * *` | None (reads DB) | news_signals, job_log |
| gpr | `0 19 * * *` | GPR XLS file | geopolitical_risk_1d, job_log |
| trump-effect | `30 19 * * *` | Federal Register API | trump_effect_1d, job_log |
| detect-setups | `*/5 12-21 * * 1-5` | None (reads DB) | warbird_* (all 8), measured_moves, job_log |
| google-news | `0 13 * * 1-5` | Google News RSS | econ_news_1d, news_signals, job_log |
| measured-moves | `0 18 * * 1-5` | None (reads DB) | measured_moves, job_log |
| score-trades | `10,25,40,55 * * * 1-5` | None (reads DB) | warbird_setups, warbird_setup_events, measured_moves, job_log |
| forecast | `30 * * * 1-5` | External writer URL | job_log (health check only) |

---

## econ_indicators View (Agreed)

Kilo's proposal to create a UNION view over the 10 category tables is reasonable. Keep category-split storage. Add view only when needed for sync/dashboard logic:

```sql
CREATE VIEW econ_indicators AS
SELECT ts, series_id, value, 'rates'::text AS category, created_at FROM econ_rates_1d
UNION ALL
SELECT ts, series_id, value, 'yields', created_at FROM econ_yields_1d
-- ... (all 10 tables)
;
```

**Do not create this view until a consumer needs it.**

---

## Implementation Guardrails (Unchanged)

- No ORM; Supabase/Postgres only.
- Snake_case columns.
- Table prefixes: `mes_`, `cross_asset_`, `econ_`, `warbird_`
- New training-reporting tables follow snake_case and explicit PK/index/watermark fields.
- Local is writer for training outputs; cloud dashboard is read-only consumer for those outputs.

---

## Action Items for Kilo

### P0 — Do First (blocks everything)

1. **Apply migrations 010, 011, 012 to cloud:** `npx supabase db push --linked`
2. **Verify warbird v1 tables exist after push**
3. **Add `CRON_SECRET` to Supabase project secrets**

### P1 — Env Cleanup

4. Remove `POSTGRES_PRISMA_URL` from Supabase env
5. Remove duplicate env vars (PUBLISHABLE_KEY, SECRET_KEY)
6. Add or remove `WARBIRD_FORECAST_WRITER_URL` based on whether forecast health check is needed

### P2 — Zombie Table Cleanup (new migration 013)

7. Write migration to DROP: `trade_scores`, `vol_states`, `sources`, `coverage_log`, `models`
8. Write migration to DROP stale enums: `setup_phase`, `signal_status`
9. Keep: `options_stats_1d`, `options_ohlcv_1d`, `policy_news_1d`, `macro_reports_1d` (future writers TBD)

### P3 — Ops Output Schemas (new migration 014, needed before Phase 4)

10. Design and write schemas for: `shap_results`, `training_reports`, `model_packets`, `training_runs`
11. Add RLS, indexes, and realtime subscription as needed

### P4 — Local DB Setup

12. Create `warbird_training` local PostgreSQL database
13. Write sync scripts (Cloud → Local for training inputs)
14. Write publish scripts (Local → Cloud for ops outputs)
