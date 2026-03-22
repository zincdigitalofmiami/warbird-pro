# Warbird-Pro Repo Audit — Ground Truth

**Date:** 2026-03-18
**Purpose:** Authoritative inventory of what actually exists in the repo. Decisions should be grounded in this, not aspirational docs.

---

## 1. DATABASE SCHEMA (12 migrations + seed)

### Tables That Exist

**MES Data (6 tables):**
| Table | PK | Columns | Realtime | Notes |
|-------|-----|---------|----------|-------|
| `mes_1s` | ts | OHLCV + created_at | Yes | Added in migration 011. Ephemeral continuity layer. |
| `mes_1m` | ts | OHLCV + created_at | Yes | Primary retained bar. Written by mes-catchup cron. |
| `mes_15m` | ts | OHLCV + created_at | Yes | Derived from 1m in TypeScript (mes-aggregation.ts). |
| `mes_1h` | ts | OHLCV + created_at | No | Written directly from Databento ohlcv-1h. |
| `mes_4h` | ts | OHLCV + created_at | No | Derived from 1h in TypeScript. |
| `mes_1d` | ts | OHLCV + created_at | No | Derived from 1h in TypeScript (session-based, 5 PM CT). |

**Cross-Asset (4 tables):**
| Table | PK | Notes |
|-------|-----|-------|
| `cross_asset_1h` | (ts, symbol_code) | Written by cross-asset cron. Sharded fetches. |
| `cross_asset_1d` | (ts, symbol_code) | Derived from 1h in cross-asset cron. |
| `options_stats_1d` | (ts, symbol_code) | Schema exists. Likely empty (backfill only). |
| `options_ohlcv_1d` | (ts, symbol_code) | Schema exists. Likely empty. |

**Econ (11 tables):**
| Table | PK | Notes |
|-------|-----|-------|
| `series_catalog` | id (serial) | 38 FRED series seeded. |
| `econ_rates_1d` | (ts, series_id) | FEDFUNDS, DFF, SOFR |
| `econ_yields_1d` | (ts, series_id) | DGS2, DGS5, DGS10, DGS30, T10Y2Y, etc. |
| `econ_fx_1d` | (ts, series_id) | DTWEXBGS, DEXUSEU, DEXJPUS |
| `econ_vol_1d` | (ts, series_id) | VIXCLS, OVXCLS, VXNCLS, etc. |
| `econ_inflation_1d` | (ts, series_id) | CPIAUCSL, CPILFESL, T5YIE, T10YIE |
| `econ_labor_1d` | (ts, series_id) | UNRATE, PAYEMS, ICSA, CCSA |
| `econ_activity_1d` | (ts, series_id) | INDPRO, RSXFS, DGORDER |
| `econ_money_1d` | (ts, series_id) | M2SL, WALCL |
| `econ_commodities_1d` | (ts, series_id) | DCOILWTICO, GVZCLS |
| `econ_indexes_1d` | (ts, series_id) | USEPUINDXD, NFCI, UMCSENT, SAHMCURRENT, etc. |

**News/Events (7 tables):**
| Table | Notes |
|-------|-------|
| `econ_news_1d` | Written by google-news cron. |
| `policy_news_1d` | Schema exists. Writer unknown. |
| `macro_reports_1d` | Read by news cron for surprise signals. |
| `econ_calendar` | Written by econ-calendar cron. |
| `news_signals` | Written by google-news + news crons. |
| `geopolitical_risk_1d` | Written by gpr cron (XLS parse). |
| `trump_effect_1d` | Written by trump-effect cron (Federal Register API). |

**Warbird v1 Engine (8 tables — migration 010 cutover):**
| Table | PK | Realtime | Writer |
|-------|-----|----------|--------|
| `warbird_daily_bias` | ts | No | detect-setups cron |
| `warbird_structure_4h` | ts | No | detect-setups cron |
| `warbird_forecasts_1h` | id (bigint) | Yes | External forecast writer (predict-warbird.py) |
| `warbird_triggers_15m` | id (bigint) | No | detect-setups cron |
| `warbird_conviction` | id (bigint) | Yes | detect-setups cron |
| `warbird_setups` | id (bigint) | Yes | detect-setups cron |
| `warbird_setup_events` | id (bigint) | Yes | detect-setups + score-trades crons |
| `warbird_risk` | id (bigint) | No | External forecast writer |

**Operations (5 tables):**
| Table | Notes |
|-------|-------|
| `trade_scores` | Schema exists. Written by score-trades cron (partially). |
| `measured_moves` | Written by measured-moves + detect-setups crons. Linked to setups via setup_id (migration 012). |
| `vol_states` | Schema exists. Writer is GARCH engine (local Python). |
| `job_log` | Written by all crons. Operational logging. |
| `coverage_log` | Schema exists. No active writer found. |

**Infrastructure (4 tables):**
| Table | Notes |
|-------|-------|
| `symbols` | 60 seeded (34 active Databento, 3 FRED, 26 inactive). |
| `symbol_roles` | 7 roles seeded. |
| `symbol_role_members` | Memberships seeded. |
| `models` | Schema exists. No active writer in production code. |

**Dropped (migration 010):**
- Old `warbird_setups` (Touch/Hook/Go) — replaced
- Old `forecasts` — replaced by `warbird_forecasts_1h`

### Enums
| Enum | Values | Migration |
|------|--------|-----------|
| `data_source` | DATABENTO, FRED, MANUAL | 001 |
| `econ_category` | rates, yields, fx, vol, inflation, labor, activity, money, commodities, indexes | 001 |
| `report_category` | fomc, cpi, nfp, claims, ppi, retail_sales, gdp, ism, housing, consumer_confidence | 001 |
| `timeframe` | M1, M5, M15, H1, H4, D1 | 001 |
| `signal_direction` | LONG, SHORT | 001 |
| `signal_status` | ACTIVE, EXPIRED, STOPPED, TP1_HIT, TP2_HIT | 001 |
| `setup_phase` | TOUCHED, HOOKED, GO_FIRED, EXPIRED, STOPPED, TP1_HIT, TP2_HIT | 001 |
| `ingestion_status` | SUCCESS, PARTIAL, FAILED, SKIPPED | 001 |
| `vol_state` | EXTREME, CRISIS, ELEVATED, NORMAL, COMPRESSED | 001 |
| `warbird_bias` | BULL, BEAR, NEUTRAL | 010 |
| `warbird_trigger_decision` | GO, WAIT, NO_GO | 010 |
| `warbird_conviction_level` | MAXIMUM, HIGH, MODERATE, LOW, NO_TRADE | 010 |
| `warbird_setup_status_v2` | ACTIVE, TP1_HIT, TP2_HIT, STOPPED, EXPIRED | 011 (replaces v1) |
| `warbird_setup_event_type_v2` | TRIGGERED, TP1_HIT, TP2_HIT, STOPPED, EXPIRED | 011 (replaces v1) |

### RLS
All tables: `ENABLE ROW LEVEL SECURITY` + `authenticated SELECT` policy. Service role bypasses.

### Realtime Subscriptions
`mes_1s`, `mes_1m`, `mes_15m`, `warbird_forecasts_1h`, `warbird_conviction`, `warbird_setups`, `warbird_setup_events`

### DB Functions
Only one: `update_updated_at()` — auto-set updated_at on triggers. **No aggregation functions, no feature engineering, no pg_cron jobs in the DB.**

---

## 2. API ROUTES (17 routes)

### Cron Routes (13, all require CRON_SECRET, maxDuration=60)

| Route | Schedule | External API | Writes To |
|-------|----------|-------------|-----------|
| `mes-catchup` | `*/5 * * * 0-5` | Databento (ohlcv-1m, ohlcv-1h) | mes_1m, mes_1h, mes_15m, mes_4h, mes_1d |
| `cross-asset` | `*/15 * * * *` | Databento (ohlcv-1h) | cross_asset_1h, cross_asset_1d |
| `fred/[category]` | 9 daily schedules (05-14 UTC) | FRED API | econ_*_1d |
| `econ-calendar` | `0 15 * * *` | TradingEconomics / FRED | econ_calendar |
| `news` | `0 16 * * *` | None (reads macro_reports) | news_signals |
| `google-news` | `0 13 * * 1-5` | Google News RSS | econ_news_1d, news_signals |
| `gpr` | `0 19 * * *` | GPR XLS download | geopolitical_risk_1d |
| `trump-effect` | `30 19 * * *` | Federal Register API | trump_effect_1d |
| `detect-setups` | `*/5 12-21 * * 1-5` | None | warbird_daily_bias, structure_4h, triggers_15m, conviction, setups, setup_events, measured_moves |
| `score-trades` | `10,25,40,55 * * * 1-5` | None | warbird_setups, setup_events, measured_moves |
| `measured-moves` | `0 18 * * 1-5` | None | measured_moves |
| `forecast` | `30 * * * 1-5` | Custom writer URL (optional) | job_log only |

### Public Routes (4, no auth required)

| Route | Purpose | Reads From |
|-------|---------|-----------|
| `live/mes15m` | Chart initial snapshot | mes_15m |
| `pivots/mes` | Pivot levels | mes_1d, mes_15m |
| `warbird/signal` | Current signal state | All warbird_* tables |
| `warbird/history` | Setup history | warbird_setups, setup_events, forecasts_1h |

### Admin (1)
| Route | Purpose |
|-------|---------|
| `admin/status` | System health — reads every table |

---

## 3. ACTIVE DATA PIPELINE (what actually runs)

### mes-catchup (PRIMARY — every 5 min)
```
Databento Historical API
  → ohlcv-1m (per contract segment, roll-aware)
  → ohlcv-1h (per contract segment)
  → Supabase cloud: mes_1m, mes_1h (upsert)
  → TypeScript aggregation: mes_15m, mes_4h, mes_1d (upsert)
  → Supabase Realtime pushes to chart
```

**Key detail:** Fetches ohlcv-1m AND ohlcv-1h separately. Does NOT fetch ohlcv-1s. Does NOT write to mes_1s.

### cross-asset (every 15 min)
```
Databento → ohlcv-1h for non-MES symbols (sharded, 4 shards)
  → cross_asset_1h, cross_asset_1d
```

### FRED (daily, staggered)
```
FRED API → 10 category tables (38 series total)
```

### detect-setups (every 5 min, weekdays 12-21 UTC)
```
Reads: mes_1d, mes_4h, mes_15m, mes_1m, warbird_forecasts_1h
Computes: daily bias, 4H structure, 15m fib geometry, 1m trigger, conviction
Writes: 7 warbird_* tables + measured_moves
```

### score-trades (every 15 min, weekdays)
```
Reads: warbird_setups (ACTIVE/TP1_HIT), mes_1m (latest)
Checks: SL hit, TP1 hit, TP2 hit, expiry
Writes: warbird_setups (status), setup_events, measured_moves
```

### forecast (hourly, weekdays)
```
Health check only. Invokes external writer if configured.
Does NOT create forecasts itself.
```

---

## 4. LIBRARY INVENTORY

### Functional (battle-tested)
| File | Purpose |
|------|---------|
| `lib/ingestion/databento.ts` | Databento Historical API client. 422 retry. Price scaling. |
| `lib/ingestion/fred.ts` | FRED API client. Per-category ingestion. |
| `lib/contract-roll.ts` | 8-day roll rule. Per-segment symbol mapping. |
| `lib/mes-aggregation.ts` | 1m→15m, 1h→4h, 1h→1d. Session-based daily (5 PM CT). |
| `lib/fibonacci.ts` | Multi-period confluence. 10 levels. Matches Pine. |
| `lib/market-hours.ts` | CME Globex hours. Weekend filter. CT timezone. |
| `lib/swing-detection.ts` | Ported from Pine ta.pivothigh/ta.pivotlow. |
| `lib/measured-move.ts` | AB=CD detection. Quality scoring. |
| `lib/pivots.ts` | Traditional floor pivots. R1-R5, S1-S5. |
| `lib/warbird/types.ts` | All row types matching DB schema. |
| `lib/warbird/constants.ts` | Regime start, signal version, thresholds. |
| `lib/warbird/queries.ts` | fetchLatestWarbirdState, fetchWarbirdHistory. |
| `lib/warbird/projection.ts` | composeWarbirdSignal, warbirdSignalToTargets. |
| `lib/setup-candidates.ts` | Warbird setup → chart marker mapping. |
| `lib/ta/indicators.ts` | 11 normalized indicators + TTM Squeeze. |
| `lib/ta/fibonacci.ts` | Pure math: retracement, extension, tick rounding. |
| `lib/supabase/admin.ts` | Service role client. |
| `lib/supabase/client.ts` | Browser client. |
| `lib/supabase/server.ts` | Server component client. |
| `lib/supabase/proxy.ts` | Middleware auth proxy. |

### Partial / Legacy
| File | Status |
|------|--------|
| `lib/setup-engine.ts` | Touch→Hook→Go state machine. Legacy methodology. Still used by detect-setups but being replaced by Warbird v1 layers. |

### Chart Primitives
| File | Purpose |
|------|---------|
| `lib/charts/FibLinesPrimitive.ts` | Fib retracement/extension rendering |
| `lib/charts/ForecastTargetsPrimitive.ts` | Entry/TP/SL zone rendering |
| `lib/charts/PivotLinesPrimitive.ts` | Pivot support/resistance |
| `lib/charts/RegimeAnchorPrimitive.ts` | Regime label anchor |
| `lib/charts/SetupMarkersPrimitive.ts` | Setup entry/stop/TP markers |
| `lib/charts/blendTargets.ts` | Target zone blending |
| `lib/charts/ensureFutureWhitespace.ts` | Future gap for projections |

### Scripts (Local Only)
| Script | Purpose | Status |
|--------|---------|--------|
| `scripts/warbird/build-warbird-dataset.ts` | Dataset builder (26 KB) | Functional |
| `scripts/warbird/trigger-15m.ts` | 1m microstructure analysis (24 KB) | Functional |
| `scripts/warbird/fib-engine.ts` | 15m fib geometry | Functional |
| `scripts/warbird/daily-layer.ts` | 200d MA bias | Functional |
| `scripts/warbird/structure-4h.ts` | 4H structure | Functional |
| `scripts/warbird/conviction-matrix.ts` | Conviction scoring | Functional |
| `scripts/warbird/train-warbird.py` | AutoGluon training | Functional |
| `scripts/warbird/predict-warbird.py` | Inference → writes forecasts | Functional |
| `scripts/warbird/garch-engine.py` | GJR-GARCH volatility | Functional |
| `scripts/backfill.py` + variants | Historical data backfill | Research |
| `scripts/live-feed.py` | DEPRECATED | Do not use |

---

## 5. ENVIRONMENT VARIABLES

**Supabase:**
- `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY`, `NEXT_PUBLIC_SUPABASE_ANON_KEY`
- `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `SUPABASE_ANON_KEY`, `SUPABASE_JWT_SECRET`

**Postgres Direct (present in .env.local but not actively used by app code):**
- `POSTGRES_URL`, `POSTGRES_URL_NON_POOLING`, `POSTGRES_HOST`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DATABASE`

**API Keys:**
- `DATABENTO_API_KEY`
- `FRED_API_KEY`

**Cron:**
- `CRON_SECRET`

**Forecast Writer (optional):**
- `WARBIRD_FORECAST_WRITER_URL`, `WARBIRD_FORECAST_WRITER_TOKEN`, `WARBIRD_FORECAST_WRITER_TIMEOUT_MS`

**Forecast Gate Thresholds (env-configurable):**
- `WARBIRD_MAX_PROB_HIT_SL_FIRST` (default 0.45)
- `WARBIRD_MIN_PROB_HIT_PT1_FIRST` (default 0.5)
- `WARBIRD_MIN_PROB_HIT_PT2_AFTER_PT1` (default 0.35)
- `WARBIRD_MIN_SETUP_SCORE` (default 55)

---

## 6. KEY GAPS (what docs claim vs what exists)

| Doc Claim | Reality |
|-----------|---------|
| "mes_1s is canonical continuity ingestion layer" | Table exists (migration 011) but **nothing writes to it**. mes-catchup fetches ohlcv-1m, not ohlcv-1s. |
| "mes_1m derived from mes_1s when available" | mes_1m is written directly from Databento ohlcv-1m. No 1s→1m derivation exists. |
| "pg_cron for DB-internal scheduling" | **Zero pg_cron jobs.** All scheduling is Vercel Cron. |
| "Postgres functions for aggregation" | **One function total** (update_updated_at). All aggregation is TypeScript. |
| "Feature engineering in DB" | **Zero DB-side feature engineering.** All in TypeScript/Python. |
| "Materialized views" | **None.** |
| "Data continuity validation in DB" | **None.** detect-setups does a basic gap check in TypeScript. |
| "supabase gen types" | **Not run.** Types are manually defined in lib/warbird/types.ts. |
| "mes_1s Realtime → forming bar" | mes_1s has Realtime enabled but nothing writes to it, so no data flows. Chart subscribes to mes_1m and mes_15m. |
| "coverage_log active" | Table exists but **no active writer**. |
| "models table populated" | Table exists but **no active writer** in production code. |

---

## 7. WHAT ACTUALLY WORKS END-TO-END

1. **MES chart pipeline:** Databento → mes-catchup cron → mes_1m + mes_1h → TypeScript aggregation → mes_15m/4h/1d → Realtime → LiveMesChart
2. **Cross-asset ingestion:** Databento → cross-asset cron → cross_asset_1h/1d
3. **FRED ingestion:** FRED API → fred crons → 10 econ_*_1d tables
4. **News/events ingestion:** Google News RSS, GPR XLS, Federal Register → respective tables
5. **Setup detection:** detect-setups cron reads MES bars + forecasts → writes warbird_* tables
6. **Trade scoring:** score-trades cron monitors active setups → updates status/events
7. **Chart rendering:** LiveMesChart.tsx with fib lines, forecast targets, setup markers, pivot lines
8. **Auth flow:** Login, signup, forgot-password, middleware session refresh
9. **API surface:** /warbird/signal, /warbird/history, /live/mes15m, /pivots/mes

---

## 8. WHAT DOES NOT WORK YET

1. **mes_1s ingestion** — table exists, Realtime enabled, but nothing writes to it
2. **Forecast writer** — route exists but delegates to external URL. No built-in inference.
3. **Local training pipeline** — scripts exist but no local DB, no automated workflow
4. **DB-side aggregation** — all aggregation is TypeScript, none in Postgres
5. **Type generation** — manual types, no `supabase gen types`
6. **Data continuity validation** — no systematic gap detection
7. **Feature engineering** — all in scripts, none pre-computed in DB
