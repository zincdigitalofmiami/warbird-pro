# Databento + Economy Backfill & pg_cron Scheduling Plan

**Created:** 2026-03-26
**Updated:** 2026-03-27 (v3 — Jan 1 2024 retention-floor lock)
**Status:** REFERENCE CHECKPOINT — retain and backfill core data only from `2024-01-01` forward
**Scope:** MES 1h/1d backfill, cross-asset backfill, economy data expansion (FRED + Massive), overnight pg_cron scheduling, all constrained to the Jan 1 2024 floor

---

## Goal

1. Retain and backfill MES 1H, 4H, 1D data from Jan 1, 2024 → present only
2. Retain and backfill cross-asset 1H + 1D for ALL 15 active non-MES DATABENTO symbols from Jan 1, 2024 only
3. Cover ALL Massive Economy endpoint fields: 13 via FRED (direct source), 6 via Massive inflation route (includes unique `cpi_year_over_year`)
4. Schedule ALL data ingestion crons via Supabase pg_cron, spread overnight
5. Add MES hourly aggregation to keep 1h/4h/1d tables current going forward

## Retention Floor

- The canonical core data floor is `2024-01-01T00:00:00Z`.
- Pre-2024 core rows are out of scope and were surgically trimmed live on `2026-03-27` by `supabase/migrations/20260327000024_trim_pre_2024_core_history.sql`.
- Remaining work in this document is only the unfinished `2024-01-01` forward backfill/freshness gap, not restoration of older history.

---

## Audit Findings (v2 changes from v1)

| # | Finding | Impact |
|---|---------|--------|
| P1 | **HTTP method mismatch**: All routes except `mes-1m` export GET only. Existing pg_cron pattern uses `net.http_post()`. New migration MUST use `net.http_get()` for GET-only routes. | Migration rewritten |
| P2 | **Schedule inconsistency**: MES hourly correctly runs `0-5` (Sun-Fri, matches market hours). Plan text incorrectly said "all Mon-Fri". Fixed. | Plan text corrected |
| P2 | **Plan drift**: Cross-asset route already has shard logic + daily aggregation. It is NOT untouched — it was built with sharding. Clarified wording. | Wording fixed |
| A5 | **Massive field names verified** from live docs. `cpi_year_over_year` has NO FRED equivalent — only field requiring Massive. | Kept 1 Massive route |
| A7 | `net.http_get(url, params, headers, timeout_ms)` signature differs from `http_post(url, headers, body)`. No `body` param, different param order. | Migration SQL adjusted |
| A8 | Overnight batch (02:00-05:00 UTC) has ZERO overlap with market hours jobs (11:00-23:00 UTC). | No conflict |
| A9 | Backfill script missing SI, NG, SOX — confirmed all 3 active in `seed.sql`. | Script update in Phase 2 |
| A10 | FRED dynamic `[category]` route works with pg_cron URLs. Using 1 parameterized SQL function + 1 base URL vault secret. | Cleaner migration |
| A11 | Massive auth = `?apiKey=` query param. But route reads `process.env.MASSIVE_API_KEY` internally. pg_cron only needs route URL + CRON_SECRET. | No extra vault secret |

---

## Current State

### Existing pg_cron schedules (1 total)
| Job Name | Schedule | Route | HTTP Method |
|----------|----------|-------|-------------|
| `warbird_mes_1m_pull` | `* * * * 0-5` | `/api/cron/mes-1m` | POST (exports GET+POST) |

### NOT scheduled (routes exist but no pg_cron)
- Cross-asset (Databento) — GET only
- FRED ×10 categories — GET only
- Massive inflation-expectations — GET only

### MES pipeline gap
- Live `mes-1m` writes `mes_1m` + `mes_15m` only
- `mes_1h`, `mes_4h`, `mes_1d` only populated by manual `mes-catchup` route

### Cross-asset backfill gap
- `backfill-cross-asset.py` covers 12 of 15 symbols (missing SI, NG, SOX)
- Script does NOT write `cross_asset_1d` (only `cross_asset_1h`)
- Live route already writes both 1h and 1d with shard logic
- `cross_asset_1d` remains the main retained-history gap; the required floor is `2024-01-01`

### Massive Economy — coverage plan
All 4 Massive Economy endpoints and every field accounted for:

| Endpoint | Fields | Source | Reason |
|----------|--------|--------|--------|
| `/fed/v1/treasury-yields` | 11 yield fields | **FRED** (DGS series) | Massive docs cite FRED as underlying source. Go direct. |
| `/fed/v1/inflation` | 6 fields (cpi, cpi_core, cpi_yoy, pce, pce_core, pce_spending) | **Massive** | `cpi_year_over_year` has NO FRED equivalent. Ingest all 6 via Massive. |
| `/fed/v1/inflation-expectations` | 7 fields | **Massive** | Already built. Cleveland Fed model data not in FRED. |
| `/fed/v1/labor-market` | 4 fields | **FRED** (UNRATE, CIVPART, CES0500000003, JTSJOL) | Massive docs literally cite these FRED series IDs. Go direct. |

---

## Phase 1: MES Historical Backfill

**Method:** Run existing `backfill.py` locally
**Command:** `python scripts/backfill.py --start 2024-01-01 --end 2026-03-27`
**Data flow:**
- Databento `ohlcv-1m` → `mes_1m` + derives `mes_15m`
- Databento `ohlcv-1h` → `mes_1h` + derives `mes_4h`, `mes_1d`
**Schemas used:** ohlcv-1m, ohlcv-1h (both free on Standard $179/mo)
**Estimated volume:** ~412K 1m rows, ~12.6K 1h rows, ~3K 4h rows, ~550 1d rows
**No code changes needed** — script already handles this exact workflow

---

## Phase 2: Cross-Asset Historical Backfill

**Method:** Update and run `backfill-cross-asset.py` locally
**Changes to script:**
1. Add missing symbols: `SI.c.0` → SI, `NG.c.0` → NG, `SOX.c.0` → SOX
2. Add `cross_asset_1d` aggregation (derive from 1h bars after upsert, same logic as live route)
3. Update end_date to `2026-03-27`

**Symbols (15 total):**
ES, NQ, YM, RTY, CL, GC, SI, NG, ZN, ZB, ZF, SOX, SR3, 6E, 6J

**Estimated volume:** ~190K cross_asset_1h rows + ~8K cross_asset_1d rows

---

## Phase 3: MES Hourly Aggregation Route

**New file:** `app/api/cron/mes-hourly/route.ts`
**Purpose:** Reads `mes_1m` bars, aggregates to `mes_1h`, then derives `mes_4h` and `mes_1d`
**Exports:** GET only (pg_cron calls via `net.http_get()`)
**Logic:**
1. Validate CRON_SECRET
2. Find latest `mes_1h` timestamp
3. Read all `mes_1m` bars since that timestamp
4. Aggregate 1m → 1h using floor(ts / 3600)
5. Upsert to `mes_1h`
6. Convert Supabase rows to `OhlcvBar` format: `time = Math.floor(new Date(row.ts).getTime() / 1000)`, `Number()` casts on OHLCV fields
7. Aggregate 1h → 4h using `aggregateMes4hFrom1h()`
8. Aggregate 1h → 1d using `aggregateMes1dFrom1h()` (Chicago session-day boundaries)
9. Convert back: `new Date(bar.time * 1000).toISOString()` for upsert
10. Upsert to `mes_4h`, `mes_1d`
11. Log to `job_log`

**Reuses:** `lib/mes-aggregation.ts` (`aggregateMes4hFrom1h`, `aggregateMes1dFrom1h`)
**Copy pattern from:** `app/api/cron/mes-1m/route.ts` (writeJobLog, error handling, CRON_SECRET validation)

---

## Phase 4: Economy Data Expansion

### 4a. Massive Inflation Route (1 new route + 1 new lib function)

**Why Massive:** `cpi_year_over_year` has no direct FRED series. Since we're hitting the Massive inflation endpoint anyway, ingest all 6 fields.

**Extend `lib/ingestion/massive.ts`** — add `ingestInflationFromMassive()`:
- Copy exact pattern of `ingestInflationExpectationsFromMassive()` (same fetch/retry/pagination/upsert logic)
- Endpoint: `GET /fed/v1/inflation`
- Target table: `econ_inflation_1d`
- Field → series_id mapping (verified from Massive docs 2026-03-26):

```typescript
const FIELD_TO_SERIES_ID = {
  cpi: "MASSIVE_CPI",
  cpi_core: "MASSIVE_CPI_CORE",
  cpi_year_over_year: "MASSIVE_CPI_YOY",
  pce: "MASSIVE_PCE",
  pce_core: "MASSIVE_PCE_CORE",
  pce_spending: "MASSIVE_PCE_SPENDING",
} as const;
```

**New file:** `app/api/cron/massive/inflation/route.ts`
- Copy exact pattern of `app/api/cron/massive/inflation-expectations/route.ts`
- Change: job_name = `"massive-inflation"`, call `ingestInflationFromMassive()`

### 4b. FRED Series Additions (migration only — zero code changes)

Add 13 new FRED series to `series_catalog`. The existing FRED cron routes (`/api/cron/fred/[category]`) + `ingestCategory()` in `lib/ingestion/fred.ts` automatically pick up any active series in the catalog. Zero code changes needed.

**Yields category (7 new):**
| series_id | name | frequency |
|-----------|------|-----------|
| `DGS1MO` | 1-Month Treasury Yield | daily |
| `DGS3MO` | 3-Month Treasury Yield | daily |
| `DGS6MO` | 6-Month Treasury Yield | daily |
| `DGS1` | 1-Year Treasury Yield | daily |
| `DGS3` | 3-Year Treasury Yield | daily |
| `DGS7` | 7-Year Treasury Yield | daily |
| `DGS20` | 20-Year Treasury Yield | daily |

**Inflation category (3 new):**
| series_id | name | frequency |
|-----------|------|-----------|
| `PCEPI` | PCE Price Index | monthly |
| `PCEPILFE` | Core PCE Price Index (Fed's preferred) | monthly |
| `PCE` | Personal Consumption Expenditures ($B) | monthly |

**Labor category (3 new):**
| series_id | name | frequency |
|-----------|------|-----------|
| `CIVPART` | Labor Force Participation Rate | monthly |
| `CES0500000003` | Avg Hourly Earnings (All Private) | monthly |
| `JTSJOL` | Job Openings (JOLTS) | monthly |

---

## Phase 5: pg_cron Migration — Overnight Schedule

**New migration:** `supabase/migrations/20260327000022_overnight_data_crons.sql`

### CRITICAL: HTTP Method Rules
- `mes-1m` → `net.http_post()` (exports GET+POST, existing migration already correct)
- **ALL new jobs** → `net.http_get()` (all new routes export GET only)
- `net.http_get(url, params, headers, timeout_ms)` — no `body` param, different param order from `http_post`

### MES Hourly (keeps 1h/4h/1d current)
| Job | Cron | UTC Time | Route | Day |
|-----|------|----------|-------|-----|
| `warbird_mes_hourly_pull` | `5 * * * 0-5` | :05 every hour | `/api/cron/mes-hourly` | Sun-Fri |

### Cross-Asset Databento (4 shards, 10 min apart)
| Job | Cron | UTC Time | Route | Day |
|-----|------|----------|-------|-----|
| `warbird_cross_asset_s0` | `0 2 * * 1-5` | 02:00 | `/api/cron/cross-asset?shard=0` | Mon-Fri |
| `warbird_cross_asset_s1` | `10 2 * * 1-5` | 02:10 | `/api/cron/cross-asset?shard=1` | Mon-Fri |
| `warbird_cross_asset_s2` | `20 2 * * 1-5` | 02:20 | `/api/cron/cross-asset?shard=2` | Mon-Fri |
| `warbird_cross_asset_s3` | `30 2 * * 1-5` | 02:30 | `/api/cron/cross-asset?shard=3` | Mon-Fri |

### FRED Categories (10 pulls, 10 min apart)
| Job | Cron | UTC Time | Route | Day |
|-----|------|----------|-------|-----|
| `warbird_fred_rates` | `45 2 * * 1-5` | 02:45 | `/api/cron/fred/rates` | Mon-Fri |
| `warbird_fred_yields` | `55 2 * * 1-5` | 02:55 | `/api/cron/fred/yields` | Mon-Fri |
| `warbird_fred_vol` | `5 3 * * 1-5` | 03:05 | `/api/cron/fred/vol` | Mon-Fri |
| `warbird_fred_inflation` | `15 3 * * 1-5` | 03:15 | `/api/cron/fred/inflation` | Mon-Fri |
| `warbird_fred_fx` | `25 3 * * 1-5` | 03:25 | `/api/cron/fred/fx` | Mon-Fri |
| `warbird_fred_labor` | `35 3 * * 1-5` | 03:35 | `/api/cron/fred/labor` | Mon-Fri |
| `warbird_fred_activity` | `45 3 * * 1-5` | 03:45 | `/api/cron/fred/activity` | Mon-Fri |
| `warbird_fred_money` | `55 3 * * 1-5` | 03:55 | `/api/cron/fred/money` | Mon-Fri |
| `warbird_fred_commodities` | `5 4 * * 1-5` | 04:05 | `/api/cron/fred/commodities` | Mon-Fri |
| `warbird_fred_indexes` | `15 4 * * 1-5` | 04:15 | `/api/cron/fred/indexes` | Mon-Fri |

### Massive Economy (2 pulls, 10 min apart)
| Job | Cron | UTC Time | Route | Day |
|-----|------|----------|-------|-----|
| `warbird_massive_inflation` | `30 4 * * 1-5` | 04:30 | `/api/cron/massive/inflation` | Mon-Fri |
| `warbird_massive_ie` | `40 4 * * 1-5` | 04:40 | `/api/cron/massive/inflation-expectations` | Mon-Fri |

### Summary: 17 new pg_cron jobs
- MES hourly: 1 job (Sun-Fri, every hour at :05)
- Cross-asset: 4 jobs (Mon-Fri, 02:00-02:30 UTC)
- FRED: 10 jobs (Mon-Fri, 02:45-04:15 UTC)
- Massive: 2 jobs (Mon-Fri, 04:30-04:40 UTC)
- Total overnight window: 02:00 – 04:40 UTC (21:00 – 23:40 CT)
- All within CME Globex hours (market open)
- 10-minute spacing between every job
- Zero Supabase pg_cron schedules
- NO conflict with market hours jobs (11:00-23:00 UTC)

### SQL function patterns

**For GET-only routes (all new jobs):**
```sql
perform net.http_get(
  url := v_url,
  params := '{}'::jsonb,
  headers := jsonb_build_object(
    'authorization', 'Bearer ' || v_secret
  ),
  timeout_milliseconds := 55000
);
```

**For FRED (parameterized function, 1 function → 10 jobs):**
```sql
create or replace function public.run_fred_pull(p_category text)
returns void ...
-- Builds URL: v_base_url || '/' || p_category
-- Then calls net.http_get() with auth header
```

**For cross-asset shards (parameterized function, 1 function → 4 jobs):**
```sql
create or replace function public.run_cross_asset_pull(p_shard int)
returns void ...
-- Builds URL: v_base_url || '?shard=' || p_shard::text
-- Then calls net.http_get() with auth header
```

### Vault secrets needed (4 new)
| Secret Name | Value Pattern |
|-------------|---------------|
| `warbird_mes_hourly_cron_url` | `https://${SUPABASE_FUNCTIONS_BASE_URL}/api/cron/mes-hourly` |
| `warbird_cross_asset_cron_url` | `https://${SUPABASE_FUNCTIONS_BASE_URL}/api/cron/cross-asset` |
| `warbird_fred_cron_base_url` | `https://${SUPABASE_FUNCTIONS_BASE_URL}/api/cron/fred` |
| `warbird_massive_cron_base_url` | `https://${SUPABASE_FUNCTIONS_BASE_URL}/api/cron/massive` |
| `warbird_cron_secret` | *(already exists)* |

---

## Phase 6: series_catalog Registration

**In same migration.** Register 13 FRED series + 6 Massive inflation series:

```sql
INSERT INTO series_catalog (series_id, name, category, frequency, is_active) VALUES
  -- FRED yields (7 new maturities)
  ('DGS1MO', '1-Month Treasury Yield', 'yields', 'daily', true),
  ('DGS3MO', '3-Month Treasury Yield', 'yields', 'daily', true),
  ('DGS6MO', '6-Month Treasury Yield', 'yields', 'daily', true),
  ('DGS1', '1-Year Treasury Yield', 'yields', 'daily', true),
  ('DGS3', '3-Year Treasury Yield', 'yields', 'daily', true),
  ('DGS7', '7-Year Treasury Yield', 'yields', 'daily', true),
  ('DGS20', '20-Year Treasury Yield', 'yields', 'daily', true),
  -- FRED inflation (3 new PCE series)
  ('PCEPI', 'PCE Price Index', 'inflation', 'monthly', true),
  ('PCEPILFE', 'Core PCE Price Index', 'inflation', 'monthly', true),
  ('PCE', 'Personal Consumption Expenditures ($B)', 'inflation', 'monthly', true),
  -- FRED labor (3 new series)
  ('CIVPART', 'Labor Force Participation Rate', 'labor', 'monthly', true),
  ('CES0500000003', 'Avg Hourly Earnings All Private', 'labor', 'monthly', true),
  ('JTSJOL', 'Job Openings JOLTS', 'labor', 'monthly', true),
  -- Massive inflation series (6 fields from /fed/v1/inflation)
  ('MASSIVE_CPI', 'CPI All Urban Consumers (Massive)', 'inflation', 'monthly', true),
  ('MASSIVE_CPI_CORE', 'Core CPI ex food/energy (Massive)', 'inflation', 'monthly', true),
  ('MASSIVE_CPI_YOY', 'CPI Year-over-Year % (Massive)', 'inflation', 'monthly', true),
  ('MASSIVE_PCE', 'PCE Price Index (Massive)', 'inflation', 'monthly', true),
  ('MASSIVE_PCE_CORE', 'Core PCE Price Index (Massive)', 'inflation', 'monthly', true),
  ('MASSIVE_PCE_SPENDING', 'Nominal PCE Spending $B (Massive)', 'inflation', 'monthly', true)
ON CONFLICT (series_id) DO NOTHING;
```

---

## Phase 7: Historical Backfill for Economy Data

After routes are deployed:

**Massive inflation backfill:**
```
curl -H "Authorization: Bearer $CRON_SECRET" \
  "https://${SUPABASE_FUNCTIONS_BASE_URL}/api/cron/massive/inflation?start_date=2024-01-01"
```

**FRED backfill:** The FRED cron routes fetch the last 100 observations by default. For a full retained backfill, manual history loading must be constrained to `2024-01-01` forward. Do not treat any pull that leaves pre-2024 rows in place as complete.

---

## Files Changed

| File | Action | Phase |
|------|--------|-------|
| `scripts/backfill-cross-asset.py` | Update (add SI, NG, SOX + 1d aggregation) | 2 |
| `app/api/cron/mes-hourly/route.ts` | **NEW** | 3 |
| `lib/ingestion/massive.ts` | Extend (add `ingestInflationFromMassive()`) | 4a |
| `app/api/cron/massive/inflation/route.ts` | **NEW** | 4a |
| `supabase/migrations/20260327000022_overnight_data_crons.sql` | **NEW** | 5, 6 |

## Files NOT Changed
- `app/api/cron/mes-1m/route.ts` — untouched
- `app/api/cron/cross-asset/route.ts` — untouched (already has shard logic + daily agg, just gets a pg_cron schedule)
- `app/api/cron/fred/[category]/route.ts` — untouched (automatically picks up new series from catalog)
- `app/api/cron/massive/inflation-expectations/route.ts` — untouched (just gets a pg_cron schedule)
- `lib/ingestion/fred.ts` — untouched
- App-host cron config file — stays empty `{}`
- No new npm dependencies

---

## Execution Order

1. Phase 4a: Build Massive inflation route (lib function + route — copy existing pattern exactly)
2. Phase 3: Build MES hourly aggregation route
3. Phase 5+6: Write migration (series_catalog inserts + pg_cron schedules with `net.http_get()`)
4. `npm run build` — verify everything compiles
5. Phase 2: Update backfill-cross-asset.py (add missing symbols + 1d)
6. Deploy to Supabase (push + merge)
7. Set 4 new vault secrets in Supabase dashboard
8. Apply migration (pg_cron schedules activate)
9. Phase 1: Run MES backfill (local Python) — manual, user-initiated
10. Phase 2: Run cross-asset backfill (local Python) — manual, user-initiated
11. Phase 7: Run Massive inflation backfill via curl — manual, user-initiated

## Current Post-Trim Truth

- MES retained history already starts at `2024-01-01`
- `cross_asset_1h` retained history already starts at `2024-01-01`
- `cross_asset_1d` still needs Jan 1 2024 forward backfill completion
- core econ tables were trimmed to the Jan 1 2024 floor on `2026-03-27`
- `econ_inflation_1d` still needs freshness work inside the Jan 1 2024 forward window

---

## Massive Economy Coverage Verification

Every field from every Massive Economy endpoint is accounted for:

### `/fed/v1/treasury-yields` — 11 fields → ALL via FRED
| Massive Field | FRED series_id | Status |
|---------------|---------------|--------|
| `yield_1_month` | `DGS1MO` | NEW in migration |
| `yield_3_month` | `DGS3MO` | NEW in migration |
| `yield_6_month` | `DGS6MO` | NEW in migration |
| `yield_1_year` | `DGS1` | NEW in migration |
| `yield_2_year` | `DGS2` | Already in catalog |
| `yield_3_year` | `DGS3` | NEW in migration |
| `yield_5_year` | `DGS5` | Already in catalog |
| `yield_7_year` | `DGS7` | NEW in migration |
| `yield_10_year` | `DGS10` | Already in catalog |
| `yield_20_year` | `DGS20` | NEW in migration |
| `yield_30_year` | `DGS30` | Already in catalog |

### `/fed/v1/inflation` — 6 fields → ALL via Massive route
| Massive Field | Massive series_id | Status |
|---------------|------------------|--------|
| `cpi` | `MASSIVE_CPI` | NEW route + migration |
| `cpi_core` | `MASSIVE_CPI_CORE` | NEW route + migration |
| `cpi_year_over_year` | `MASSIVE_CPI_YOY` | NEW route + migration (NO FRED equivalent) |
| `pce` | `MASSIVE_PCE` | NEW route + migration |
| `pce_core` | `MASSIVE_PCE_CORE` | NEW route + migration |
| `pce_spending` | `MASSIVE_PCE_SPENDING` | NEW route + migration |

*Note: CPI and PCE also covered by FRED (CPIAUCSL, CPILFESL, PCEPI, PCEPILFE, PCE) for cross-validation.*

### `/fed/v1/inflation-expectations` — 7 fields → ALL via existing Massive route
| Massive Field | Massive series_id | Status |
|---------------|------------------|--------|
| `forward_years_5_to_10` | `MASSIVE_IE_FORWARD_YEARS_5_TO_10` | Already built |
| `market_10_year` | `MASSIVE_IE_MARKET_10_YEAR` | Already built |
| `market_5_year` | `MASSIVE_IE_MARKET_5_YEAR` | Already built |
| `model_10_year` | `MASSIVE_IE_MODEL_10_YEAR` | Already built |
| `model_1_year` | `MASSIVE_IE_MODEL_1_YEAR` | Already built |
| `model_30_year` | `MASSIVE_IE_MODEL_30_YEAR` | Already built |
| `model_5_year` | `MASSIVE_IE_MODEL_5_YEAR` | Already built |

### `/fed/v1/labor-market` — 4 fields → ALL via FRED
| Massive Field | FRED series_id | Status |
|---------------|---------------|--------|
| `unemployment_rate` | `UNRATE` | Already in catalog |
| `labor_force_participation_rate` | `CIVPART` | NEW in migration |
| `avg_hourly_earnings` | `CES0500000003` | NEW in migration |
| `job_openings` | `JTSJOL` | NEW in migration |

**Total: 28 fields across 4 endpoints. 28/28 covered. 0 gaps.**

---

## Risk Notes

- Cross-asset daily run with 4 shards: each shard processes ~4 symbols at ~3 sec/symbol → ~12 sec total. Well within maxDuration=60.
- Massive API free tier rate limits: unknown. Existing inflation-expectations code has retry logic with exponential backoff (5 attempts). Same pattern applied to new inflation route.
- MES hourly route: reads `mes_1m` (could be thousands of rows for a 1h window). Query limited to latest `mes_1h` timestamp → now, typically ~60 rows.
- FRED categories with no active series return quickly (SKIPPED status).
- `cpi_year_over_year` is monthly, so Massive inflation route handles low volume (~24 observations/year × 6 fields = ~144 rows/year).
- Duplicate coverage (FRED CPI/PCE + Massive CPI/PCE) uses different series_id prefixes so no upsert conflicts. Provides cross-validation.
