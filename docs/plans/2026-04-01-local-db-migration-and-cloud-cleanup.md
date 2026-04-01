# Local DB Migration & Cloud Cleanup Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Strip cloud Supabase down to dashboard-only tables, then migrate all training data from `rabid_raccoon` (local Postgres) into the local Supabase sector by sector with full audit checkpoints.

**Architecture:** Two-database topology. Cloud Supabase serves the live dashboard and production crons only — no training data. Local Supabase (Docker, port 54322) holds all historical training data back to 2020-01-01. Data flows: Databento → cloud (live) and Databento/rabid_raccoon → local (training). Never the other way.

**Tech Stack:** PostgreSQL (psql), Supabase CLI, Python 3, Databento API

---

## ⚠️ IRON RULES FOR THIS PLAN

1. **One sector at a time. Verify before proceeding.** Do not run sector N+1 until sector N is signed off.
2. **Dry-run before every INSERT.** Run a SELECT COUNT first. Review the number. Then run the insert.
3. **Never modify cloud schema.** Cloud DDL changes require a migration file. This plan's cloud work is data deletion only (TRUNCATE/DELETE), not schema changes.
4. **No combined scripts.** Each sector is its own file. Period.
5. **Audit commands are mandatory.** Every checkpoint must be run and output reviewed, not skipped.
6. **Local Supabase = training warehouse.** Cloud = live dashboard. These are separate concerns permanently.

---

## PART 0: SCHEMA REFERENCE GUIDE

Read this entire section before touching anything. It is the ground truth for every decision in this plan.

---

### 0.1 Databento Schema

Databento delivers CME Globex (GLBX.MDP3) futures data. All symbols use the **continuous front-month contract** convention.

**Symbol format:** `{SYMBOL}.c.0` — e.g., `MES.c.0`, `NQ.c.0`, `6E.c.0`
**Parameter:** always pass `stype_in="continuous"` on API calls
**No manual roll logic.** Databento handles contract rolls automatically.

**Available schemas (Standard plan $179/mo):**
| Schema | Description | Used for |
|--------|-------------|----------|
| `ohlcv-1s` | 1-second OHLCV | Live API only (mes-1m Edge Function) |
| `ohlcv-1m` | 1-minute OHLCV | MES historical backfill fallback |
| `ohlcv-1h` | 1-hour OHLCV | Cross-asset ingestion (all symbols) |
| `ohlcv-1d` | Daily OHLCV | Daily bars |
| `definition` | Contract definitions | Symbol lookup |

**AG basket symbols (all on GLBX.MDP3):**
| Symbol | Databento ID | Role |
|--------|-------------|------|
| MES | MES.c.0 | Primary instrument |
| NQ | NQ.c.0 | Leadership (tech) |
| RTY | RTY.c.0 | Risk appetite (small cap) |
| CL | CL.c.0 | Risk appetite (energy) |
| HG | HG.c.0 | Risk appetite (copper/demand) |
| 6E | 6E.c.0 | Macro-FX (EUR/USD) |
| 6J | 6J.c.0 | Macro-FX (JPY — inverted, risk-off) |

**Not on Databento GLBX.MDP3:** VIX, TICK, VOLD, VVIX, HYG, SKEW — these are NYSE/CBOE data and require separate (expensive) subscriptions. Use FRED VIXCLS for daily VIX context.

**Live API vs Historical API:**
- **Live API (TCP gateway):** Used by `mes-1m` Edge Function for real-time 1s bars → aggregated to 1m → rolled to 15m. Zero lag.
- **Historical API:** Used by `mes-hourly` and `cross-asset` Edge Functions. Has ~10-15 min publication delay. Never use for live chart display.

---

### 0.2 Supabase Schema — Cloud vs Local

**Two completely separate Postgres instances:**

| | Cloud | Local |
|--|-------|-------|
| Host | aws-1-us-east-1.pooler.supabase.com | localhost:54322 |
| Purpose | Live dashboard + production crons | Training warehouse only |
| Data floor | 2024-01-01 (recent window) | 2020-01-01 (5-year window) |
| Access | Vercel + Edge Functions | Local scripts only |
| Schema source | `supabase/migrations/` | Same migrations (db reset) |

**Cloud holds:** Live MES chart data, live cross-asset for dashboard, warbird candidate/signal/packet tables, reference tables, job_log.

**Local holds:** Full 2020–present history for MES, all 6 AG symbols, all FRED econ series, GPR, executive orders — everything AG needs for training.

**Critical rule:** Local and cloud diverge in data coverage. When describing "what's in the DB," always name which instance. Never collapse them.

---

### 0.3 Price Table Schema

All price tables follow this exact structure (snake_case, no `id` column):

```sql
-- Example: mes_15m (same shape for mes_1h, mes_1d, mes_4h, cross_asset_*)
ts          TIMESTAMPTZ  NOT NULL  -- bar close time, UTC
open        NUMERIC      NOT NULL
high        NUMERIC      NOT NULL
low         NUMERIC      NOT NULL
close       NUMERIC      NOT NULL
volume      BIGINT       NOT NULL
created_at  TIMESTAMPTZ  DEFAULT now()
PRIMARY KEY (ts)                   -- mes_* tables
PRIMARY KEY (ts, symbol_code)      -- cross_asset_* tables
```

**cross_asset tables also have:** `symbol_code TEXT NOT NULL` — the Warbird symbol code (e.g., `NQ`, `RTY`, not the Databento full symbol).

**rabid_raccoon mapping:** camelCase → snake_case, `eventTime` → `ts`, `symbolCode` → `symbol_code`. Drop: `id`, `source`, `sourceDataset`, `sourceSchema`, `ingestedAt`, `knowledgeTime`, `rowHash`, `metadata`. Cast `volume::bigint`.

**`eventDate` tables** (1d only): `eventDate DATE` in raccoon → cast to `TIMESTAMPTZ` as `eventDate::timestamp AT TIME ZONE 'UTC'` to get midnight UTC.

---

### 0.4 Econ Table Schema

All econ tables follow the same narrow structure:

```sql
ts          TIMESTAMPTZ  NOT NULL  -- observation date at midnight UTC
series_id   TEXT         NOT NULL  -- FRED series ID (e.g., 'DGS10')
value       NUMERIC      NOT NULL
created_at  TIMESTAMPTZ  DEFAULT now()
PRIMARY KEY (ts, series_id)
FOREIGN KEY (series_id) REFERENCES series_catalog(series_id)
```

**The FK is enforced.** Every `series_id` you write must exist in `series_catalog` first. If a series from rabid_raccoon is not in the local `series_catalog`, it will be rejected. Check catalog membership before each econ sector.

**rabid_raccoon mapping:** `seriesId` → `series_id`, `eventDate::timestamp AT TIME ZONE 'UTC'` → `ts`. Drop all metadata columns.

**Econ table routing — which series goes where:**

| Target table | category in series_catalog | Examples |
|-------------|---------------------------|---------|
| `econ_yields_1d` | yields | DGS2, DGS10, T10Y2Y |
| `econ_rates_1d` | rates | DFF, SOFR, FEDFUNDS |
| `econ_fx_1d` | fx | DEXUSEU, DEXJPUS, DTWEXBGS |
| `econ_inflation_1d` | inflation | CPIAUCSL, T5YIE, T10YIE, T5YIFR, EXPINF1YR |
| `econ_vol_1d` | vol | VIXCLS, OVXCLS, GVZCLS, RVXCLS, VXNCLS |
| `econ_indexes_1d` | indexes | BAMLH0A0HYM2, NFCI, USEPUINDXD, EMVMACROBUS |
| `econ_labor_1d` | labor | UNRATE, PAYEMS, ICSA |
| `econ_activity_1d` | activity | GDP, INDPRO, RSXFS |
| `econ_money_1d` | money | M2SL, WALCL |
| `econ_commodities_1d` | commodities | DCOILWTICO, GVZCLS |

**Do NOT use table name as routing logic.** Always look up `series_catalog.category` for the series you're inserting. The category drives the target table.

---

### 0.5 Symbology Schema

**`symbols` table** — master registry:
```
code            TEXT PK   -- Warbird code: 'NQ', 'MES', '6J'
display_name    TEXT
data_source     TEXT      -- 'DATABENTO' or 'FRED'
databento_symbol TEXT     -- 'NQ.c.0', 'MES.c.0', null for FRED
fred_symbol     TEXT      -- null for Databento
is_active       BOOL
```

**`symbol_roles` table** — role definitions: PRIMARY, EQUITY_INDEX, COMMODITY, FX, TREASURY, OPTIONS, VOLATILITY

**`symbol_role_members` table** — many-to-many: symbol_id → role_id

**`series_catalog` table** — FRED series registry:
```
series_id   TEXT PK   -- FRED ID: 'DGS10', 'VIXCLS'
name        TEXT
category    TEXT      -- drives econ table routing
frequency   TEXT      -- 'daily', 'monthly', 'weekly'
is_active   BOOL
```

**Rule:** A series_id must be registered in `series_catalog` before any econ data can be inserted (FK constraint). Check and register missing series before running econ sector migrations.

---

### 0.6 Optimal Cron Scheduling (Cloud Production)

All cloud crons use Supabase pg_cron → `net.http_post()` → Edge Function. No Vercel cron. No local machines.

**Current cloud cron schedule (verified from pg_cron.job):**

| Job | Schedule | Window | Notes |
|-----|----------|--------|-------|
| `warbird_mes_1m_pull` | `* * * * 0-5` | Every minute, Sun-Fri | Live. Never change. |
| `warbird_mes_hourly_pull` | `5 * * * 0-5` | :05 past every hour | Hourly catch-up |
| `warbird_cross_asset_s0-s3` | `5-8 * * * 0-5` | :05-:08 past every hour | 4 shards, 1h data |
| `warbird_fred_yields` | `55 2 * * 1-5` | 02:55 UTC Mon-Fri | ~10pm EST |
| `warbird_fred_rates` | `45 2 * * 1-5` | 02:45 UTC Mon-Fri | |
| `warbird_fred_vol` | `5 3 * * 1-5` | 03:05 UTC Mon-Fri | |
| `warbird_fred_fx` | `15 3 * * 1-5` | 03:15 UTC Mon-Fri | |
| `warbird_fred_labor` | `35 3 * * 1-5` | 03:35 UTC Mon-Fri | |
| `warbird_fred_activity` | `45 3 * * 1-5` | 03:45 UTC Mon-Fri | |
| `warbird_fred_money` | `55 3 * * 1-5` | 03:55 UTC Mon-Fri | |
| `warbird_fred_commodities` | `5 4 * * 1-5` | 04:05 UTC Mon-Fri | |
| `warbird_fred_indexes` | `15 4 * * 1-5` | 04:15 UTC Mon-Fri | |
| `warbird_fred_inflation` | `15 3 * * 1-5` | 03:15 UTC Mon-Fri | |
| `warbird_massive_inflation` | `30 4 * * 1-5` | 04:30 UTC Mon-Fri | |
| `warbird_massive_ie` | `40 4 * * 1-5` | 04:40 UTC Mon-Fri | |
| `warbird_econ_calendar` | `20 4 * * 1-5` | 04:20 UTC Mon-Fri | |
| `warbird_exec_orders_pull` | `0 8 * * 1-5` | 08:00 UTC Mon-Fri | After fed open |
| `warbird_gpr_pull` | `0 6 * * 1-5` | 06:00 UTC Mon-Fri | Manual monthly |

**Scheduling principles:**
- FRED publishes daily data by ~00:00-01:00 UTC. Pull starts at 02:45 UTC to give buffer.
- Spread FRED pulls 10 minutes apart — they're independent, no need to stack them.
- Cross-asset shards fire at :05/:06/:07/:08 to spread DB load across 4 minutes.
- MES 1m fires every minute during market hours — the Edge Function gates on `isMarketOpen()` internally.
- Massive API (paid) and econ calendar go last in the nightly window (04:20-04:40 UTC).
- Executive orders at 08:00 UTC (after Fed opens for business).

**After this plan:** FRED econ crons on cloud become training-data-only pulls. Consider disabling them on cloud once local Supabase is fully populated and a local FRED pull script is in place. For now, leave cloud FRED crons running — they're cheap and keep cloud econ data fresh as a fallback.

---

### 0.7 Research Foundation — Why These Economic Features

The `docs/research/` folder contains the academic papers that justify the econ feature set. Before questioning why a series is included, read the relevant paper first. AG decides the actual correlations — these papers explain what mechanisms to expect.

| Paper | File | What it justifies |
|-------|------|-------------------|
| AI-assisted geopolitical risk index (Caldara-Iacoviello GPR) | `AI_GPR_PAPER.pdf` | `geopolitical_risk_1d` table. GPR shocks correlate with equity vol spikes and risk-off flows. |
| Bayesian analysis of DSGE models | `Bayesian Analysis of DSGE Models.pdf` | Macro state inference framework. Justifies the regime scoring approach — regimes are latent states estimated from observables. |
| Deregulation paper | `DEREGULATION_PAPER.pdf` | Regulatory environment changes (exec orders, policy) affect sector rotation. Justifies `executive_orders_1d` feature. |
| Geopolitical risks and inflation (JIE 2026) | `Do geopolitical risks raise or lower inflation?JIE_2026.pdf` | GPR has nonlinear effects on inflation — rising GPR can reduce inflation expectations even as it raises CPI temporarily. Justifies keeping both GPR and EXPINF series. |
| Economic effects of trade policy (JME 2020) | `EconEffectFromTradePolicyJME2020.pdf` | Trade policy uncertainty shocks suppress ES/MES through investment uncertainty channel. Justifies USEPUINDXD (EPU index) in econ_indexes_1d. |
| International economic sanctions | `INTERNATIONAL_ECONOMIC_SANCTIONS.pdf` | Sanctions create supply chain disruptions and commodity dislocations. Supports CL (crude) and HG (copper) as intermarket basket members sensitive to geopolitical action. |
| Oil elasticity and CCI | `OilElastisityCCI.pdf` | CL price changes have asymmetric effects on equities depending on demand vs supply origin. AG needs CL as a feature; elasticity regime context matters. |
| Deep research report (2026-03-31) | `03-31-2026-deep-research-report.md` | Full ML integration audit: PIT semantics, alert budget, dataset readiness, entry/trigger ontology, TimescaleDB fit. **Read this before Phase 2 Sector 2 (cross-asset data).** |

**Rule:** When a series is in `series_catalog` but you don't understand why, look it up here before deciding it's redundant.

---

## PHASE 1: CLOUD AUDIT & CLEANUP

**Goal:** Remove all training-only data from cloud. Cloud retains only what the live dashboard and production crons need.

### CHECKPOINT 0 — Pre-Cleanup Baseline (run before touching anything)

Run this audit and save the output. This is your before-state proof.

```bash
psql "$CLOUD_DB_URL" -c "
SELECT table_name,
       (xpath('/row/cnt/text()', xml_count))[1]::text::bigint AS row_count
FROM (
  SELECT table_name,
         query_to_xml(format('SELECT count(*) AS cnt FROM public.%I', table_name), false, true, '') AS xml_count
  FROM information_schema.tables
  WHERE table_schema = 'public' AND table_type = 'BASE TABLE'
  ORDER BY table_name
) t;" > /tmp/cloud_baseline_before.txt && cat /tmp/cloud_baseline_before.txt
```

Expected: 39 tables. Record every row count. This is your rollback reference.

---

### Task 1.1 — Identify Frontend-Only Tables

**Tables cloud MUST keep (dashboard + production crons):**

| Table | Why it stays |
|-------|-------------|
| `mes_15m` | Live chart data |
| `mes_1m` | Written by mes-1m Edge Function (aggregated to 15m) |
| `cross_asset_1h` | Dashboard CorrelationsRow (intermarket panel) |
| `warbird_fib_candidates_15m` | Admin/dashboard candidates surface |
| `warbird_fib_engine_snapshots_15m` | Engine state for dashboard |
| `warbird_candidate_outcomes_15m` | Outcome tracking |
| `warbird_signals_15m` | Live signals |
| `warbird_signal_events` | Signal lifecycle events |
| `warbird_packets` | Model deployment packets |
| `warbird_packet_activations` | Packet state |
| `warbird_packet_feature_importance` | Packet metadata |
| `warbird_packet_metrics` | Packet metrics |
| `warbird_packet_recommendations` | Packet recommendations |
| `warbird_packet_setting_hypotheses` | Packet settings |
| `warbird_training_runs` | Training run registry |
| `warbird_training_run_metrics` | Training metrics |
| `econ_calendar` | Event overlay on dashboard |
| `job_log` | Admin monitoring |
| `series_catalog` | Reference (FK source) |
| `symbols` | Reference |
| `symbol_roles` | Reference |
| `symbol_role_members` | Reference |

**Tables that are training-only (data can be removed from cloud):**

| Table | Why it can be cleared |
|-------|----------------------|
| `mes_1h` | Training context only — dashboard reads mes_15m |
| `mes_4h` | Training context only |
| `mes_1d` | Training context only |
| `cross_asset_15m` | Training features — not used by dashboard |
| `cross_asset_1d` | Training features — not used by dashboard |
| `econ_yields_1d` | Training features |
| `econ_rates_1d` | Training features |
| `econ_fx_1d` | Training features |
| `econ_inflation_1d` | Training features |
| `econ_labor_1d` | Training features |
| `econ_activity_1d` | Training features |
| `econ_money_1d` | Training features |
| `econ_vol_1d` | Training features |
| `econ_commodities_1d` | Training features |
| `econ_indexes_1d` | Training features |
| `executive_orders_1d` | Training features |
| `geopolitical_risk_1d` | Training features (manual monthly refresh) |

**Action:** Tables are NOT dropped — the schema stays intact. Only the data (rows) is removed from training-only tables. Schema on cloud stays aligned with migrations.

---

### Task 1.2 — Cloud Training Data Removal

**Step 1: Dry run — confirm row counts you're about to wipe**

```bash
psql "$CLOUD_DB_URL" -c "
SELECT 'mes_1h' as tbl, count(*) FROM mes_1h
UNION ALL SELECT 'mes_4h', count(*) FROM mes_4h
UNION ALL SELECT 'mes_1d', count(*) FROM mes_1d
UNION ALL SELECT 'cross_asset_15m', count(*) FROM cross_asset_15m
UNION ALL SELECT 'cross_asset_1d', count(*) FROM cross_asset_1d
UNION ALL SELECT 'econ_yields_1d', count(*) FROM econ_yields_1d
UNION ALL SELECT 'econ_rates_1d', count(*) FROM econ_rates_1d
UNION ALL SELECT 'econ_fx_1d', count(*) FROM econ_fx_1d
UNION ALL SELECT 'econ_inflation_1d', count(*) FROM econ_inflation_1d
UNION ALL SELECT 'econ_labor_1d', count(*) FROM econ_labor_1d
UNION ALL SELECT 'econ_activity_1d', count(*) FROM econ_activity_1d
UNION ALL SELECT 'econ_money_1d', count(*) FROM econ_money_1d
UNION ALL SELECT 'econ_vol_1d', count(*) FROM econ_vol_1d
UNION ALL SELECT 'econ_commodities_1d', count(*) FROM econ_commodities_1d
UNION ALL SELECT 'econ_indexes_1d', count(*) FROM econ_indexes_1d
UNION ALL SELECT 'executive_orders_1d', count(*) FROM executive_orders_1d
UNION ALL SELECT 'geopolitical_risk_1d', count(*) FROM geopolitical_risk_1d
ORDER BY tbl;"
```

Review these numbers. They should match the baseline from Checkpoint 0. If anything is wildly off, stop and investigate.

**Step 2: Execute truncation**

⚠️ This deletes real data from production cloud. Confirm you have verified the baseline and understand these tables are training-only before running.

```bash
psql "$CLOUD_DB_URL" -c "
TRUNCATE mes_1h, mes_4h, mes_1d,
         cross_asset_15m, cross_asset_1d,
         econ_yields_1d, econ_rates_1d, econ_fx_1d,
         econ_inflation_1d, econ_labor_1d, econ_activity_1d,
         econ_money_1d, econ_vol_1d, econ_commodities_1d, econ_indexes_1d,
         executive_orders_1d, geopolitical_risk_1d;"
```

**Step 3: Verify**

```bash
psql "$CLOUD_DB_URL" -c "
SELECT 'mes_1h' as tbl, count(*) FROM mes_1h
UNION ALL SELECT 'mes_4h', count(*) FROM mes_4h
UNION ALL SELECT 'mes_1d', count(*) FROM mes_1d
UNION ALL SELECT 'econ_yields_1d', count(*) FROM econ_yields_1d
UNION ALL SELECT 'econ_vol_1d', count(*) FROM econ_vol_1d;"
```

Expected: all zeros. If any row count is non-zero, do not proceed.

---

### CHECKPOINT 1 — Post-Cloud-Cleanup Audit

```bash
psql "$CLOUD_DB_URL" -c "
SELECT table_name,
       (xpath('/row/cnt/text()', xml_count))[1]::text::bigint AS row_count
FROM (
  SELECT table_name,
         query_to_xml(format('SELECT count(*) AS cnt FROM public.%I', table_name), false, true, '') AS xml_count
  FROM information_schema.tables
  WHERE table_schema = 'public' AND table_type = 'BASE TABLE'
  ORDER BY table_name
) t;" > /tmp/cloud_baseline_after.txt && cat /tmp/cloud_baseline_after.txt
```

**Pass criteria:**
- `mes_15m`: non-zero (live data intact)
- `cross_asset_1h`: non-zero (dashboard data intact)
- `econ_calendar`: non-zero (events intact)
- All 17 training-only tables: 0 rows
- All `warbird_*` tables: unchanged from baseline
- `series_catalog`, `symbols`, `symbol_roles`, `symbol_role_members`: unchanged

Do not proceed to Phase 2 until all pass criteria are confirmed.

---

## PHASE 2: LOCAL SUPABASE — SECTOR MIGRATION

**Source:** `rabid_raccoon` at `postgresql://zincdigital@localhost:5432/rabid_raccoon`
**Target:** Local Supabase at `postgresql://postgres:postgres@localhost:54322/postgres`
**Floor:** 2020-01-01T00:00:00Z — do not load pre-2020 rows

### CHECKPOINT 2 — Pre-Migration Local Baseline

```bash
psql "postgresql://postgres:postgres@localhost:54322/postgres" -c "
SELECT table_name,
       (xpath('/row/cnt/text()', xml_count))[1]::text::bigint AS row_count
FROM (
  SELECT table_name,
         query_to_xml(format('SELECT count(*) AS cnt FROM public.%I', table_name), false, true, '') AS xml_count
  FROM information_schema.tables
  WHERE table_schema = 'public' AND table_type = 'BASE TABLE'
  ORDER BY table_name
) t;" > /tmp/local_baseline_before.txt && cat /tmp/local_baseline_before.txt
```

Expected: 39 tables, all data tables at 0 rows, `series_catalog` at 89, `symbols` at 61.

---

### SECTOR 1 — MES Price Data

**Tables:** `mes_15m`, `mes_1h`, `mes_1d`
**Source:** `mkt_futures_mes_15m`, `mkt_futures_mes_1h`, `mkt_futures_mes_1d`
**Skip:** `mes_1m` (3,660 rows, 5-day window only — not worth it), `mes_4h` (18 rows — skip)

#### Step S1-A: Dry run

```bash
psql "postgresql://zincdigital@localhost:5432/rabid_raccoon" -c "
SELECT
  'mes_15m' as target,
  count(*) as source_rows,
  min(\"eventTime\")::date as earliest,
  max(\"eventTime\")::date as latest
FROM mkt_futures_mes_15m
WHERE \"eventTime\" >= '2020-01-01'
UNION ALL SELECT
  'mes_1h',
  count(*),
  min(\"eventTime\")::date,
  max(\"eventTime\")::date
FROM mkt_futures_mes_1h
WHERE \"eventTime\" >= '2020-01-01'
UNION ALL SELECT
  'mes_1d',
  count(*),
  min(\"eventDate\")::date,
  max(\"eventDate\")::date
FROM mkt_futures_mes_1d
WHERE \"eventDate\" >= '2020-01-01';"
```

Review output. Note the row counts. Proceed only when satisfied.

#### Step S1-B: Run — mes_15m

```bash
psql "postgresql://postgres:postgres@localhost:54322/postgres" -c "
INSERT INTO mes_15m (ts, open, high, low, close, volume)
SELECT
  \"eventTime\" AS ts,
  open,
  high,
  low,
  close,
  volume::bigint
FROM dblink(
  'host=localhost port=5432 dbname=rabid_raccoon user=zincdigital',
  'SELECT \"eventTime\", open, high, low, close, volume
   FROM mkt_futures_mes_15m
   WHERE \"eventTime\" >= ''2020-01-01''
   ORDER BY \"eventTime\"'
) AS t(eventTime timestamptz, open numeric, high numeric, low numeric, close numeric, volume numeric)
ON CONFLICT (ts) DO NOTHING;"
```

> **Note:** If `dblink` extension isn't available in the local Supabase, use `psql` file export instead:
> ```bash
> psql "postgresql://zincdigital@localhost:5432/rabid_raccoon" \
>   -c "\COPY (SELECT \"eventTime\", open, high, low, close, volume::bigint FROM mkt_futures_mes_15m WHERE \"eventTime\" >= '2020-01-01' ORDER BY \"eventTime\") TO '/tmp/mes_15m.csv' CSV"
> psql "postgresql://postgres:postgres@localhost:54322/postgres" \
>   -c "\COPY mes_15m (ts, open, high, low, close, volume) FROM '/tmp/mes_15m.csv' CSV"
> ```
> The COPY approach is preferred — it's faster and doesn't require dblink.

#### Step S1-C: Run — mes_1h

```bash
psql "postgresql://zincdigital@localhost:5432/rabid_raccoon" \
  -c "\COPY (SELECT \"eventTime\", open, high, low, close, volume::bigint FROM mkt_futures_mes_1h WHERE \"eventTime\" >= '2020-01-01' ORDER BY \"eventTime\") TO '/tmp/mes_1h.csv' CSV"

psql "postgresql://postgres:postgres@localhost:54322/postgres" \
  -c "\COPY mes_1h (ts, open, high, low, close, volume) FROM '/tmp/mes_1h.csv' CSV"
```

#### Step S1-D: Run — mes_1d

```bash
psql "postgresql://zincdigital@localhost:5432/rabid_raccoon" \
  -c "\COPY (SELECT \"eventDate\"::timestamp AT TIME ZONE 'UTC', open, high, low, close, volume::bigint FROM mkt_futures_mes_1d WHERE \"eventDate\" >= '2020-01-01' ORDER BY \"eventDate\") TO '/tmp/mes_1d.csv' CSV"

psql "postgresql://postgres:postgres@localhost:54322/postgres" \
  -c "\COPY mes_1d (ts, open, high, low, close, volume) FROM '/tmp/mes_1d.csv' CSV"
```

#### CHECKPOINT S1 — Verify Sector 1

```bash
psql "postgresql://postgres:postgres@localhost:54322/postgres" -c "
SELECT
  'mes_15m' as tbl, count(*) as rows, min(ts)::date as earliest, max(ts)::date as latest FROM mes_15m
UNION ALL SELECT 'mes_1h', count(*), min(ts)::date, max(ts)::date FROM mes_1h
UNION ALL SELECT 'mes_1d', count(*), min(ts)::date, max(ts)::date FROM mes_1d
ORDER BY tbl;"
```

**Pass criteria:**
- `mes_15m`: ~130,000–140,000 rows, earliest ~2020-01-01, latest ~2026-03-09
- `mes_1h`: ~30,000+ rows, same date range
- `mes_1d`: ~1,500+ rows, same date range

**Spot check — verify a known price (adjust date as needed):**
```bash
psql "postgresql://postgres:postgres@localhost:54322/postgres" -c "
SELECT ts, open, high, low, close, volume
FROM mes_15m
WHERE ts::date = '2020-03-16'  -- COVID crash week
ORDER BY ts LIMIT 5;"
```

MES was trading near 2200-2400 range in March 2020. If values are wildly off, stop.

**Clean up temp files:** `rm /tmp/mes_*.csv`

Sign off on Sector 1 before proceeding.

---

### SECTOR 2 — Cross-Asset 1H (5 AG symbols)

**Table:** `cross_asset_1h`
**Source:** `mkt_futures_1h` WHERE `symbolCode` IN ('NQ','RTY','CL','6E','6J')
**Note:** HG is NOT in rabid_raccoon. It will be filled by Databento backfill in Phase 3.

#### Step S2-A: Dry run

```bash
psql "postgresql://zincdigital@localhost:5432/rabid_raccoon" -c "
SELECT \"symbolCode\" as symbol, count(*) as rows,
       min(\"eventTime\")::date as earliest, max(\"eventTime\")::date as latest
FROM mkt_futures_1h
WHERE \"symbolCode\" IN ('NQ','RTY','CL','6E','6J')
  AND \"eventTime\" >= '2020-01-01'
GROUP BY \"symbolCode\" ORDER BY \"symbolCode\";"
```

Expected: ~28,000-37,000 rows per symbol (6 years × ~250 trading days × ~24h).

#### Step S2-B: Export and load

```bash
psql "postgresql://zincdigital@localhost:5432/rabid_raccoon" \
  -c "\COPY (SELECT \"symbolCode\", \"eventTime\", open, high, low, close, volume::bigint FROM mkt_futures_1h WHERE \"symbolCode\" IN ('NQ','RTY','CL','6E','6J') AND \"eventTime\" >= '2020-01-01' ORDER BY \"symbolCode\", \"eventTime\") TO '/tmp/cross_asset_1h.csv' CSV"

psql "postgresql://postgres:postgres@localhost:54322/postgres" \
  -c "\COPY cross_asset_1h (symbol_code, ts, open, high, low, close, volume) FROM '/tmp/cross_asset_1h.csv' CSV"
```

#### CHECKPOINT S2 — Verify Sector 2

```bash
psql "postgresql://postgres:postgres@localhost:54322/postgres" -c "
SELECT symbol_code, count(*) as rows,
       min(ts)::date as earliest, max(ts)::date as latest
FROM cross_asset_1h
GROUP BY symbol_code ORDER BY symbol_code;"
```

**Pass criteria:** 5 symbols present (NQ, RTY, CL, 6E, 6J), no HG yet, ~28k-37k rows each, dates from 2020-01-01.

**Spot check:**
```bash
psql "postgresql://postgres:postgres@localhost:54322/postgres" -c "
SELECT symbol_code, ts, close FROM cross_asset_1h
WHERE ts::date = '2020-03-16' AND symbol_code IN ('NQ','CL')
ORDER BY symbol_code, ts LIMIT 4;"
```

NQ ~7000-8000, CL ~20-30 range in March 2020. Clean up: `rm /tmp/cross_asset_1h.csv`

---

### SECTOR 3 — Cross-Asset 1D (5 AG symbols)

**Table:** `cross_asset_1d`
**Source:** `mkt_futures_1d` WHERE `symbolCode` IN ('NQ','RTY','CL','6E','6J')

#### Step S3-A: Dry run

```bash
psql "postgresql://zincdigital@localhost:5432/rabid_raccoon" -c "
SELECT \"symbolCode\", count(*), min(\"eventDate\")::date, max(\"eventDate\")::date
FROM mkt_futures_1d
WHERE \"symbolCode\" IN ('NQ','RTY','CL','6E','6J') AND \"eventDate\" >= '2020-01-01'
GROUP BY \"symbolCode\" ORDER BY \"symbolCode\";"
```

#### Step S3-B: Export and load

```bash
psql "postgresql://zincdigital@localhost:5432/rabid_raccoon" \
  -c "\COPY (SELECT \"symbolCode\", \"eventDate\"::timestamp AT TIME ZONE 'UTC', open, high, low, close, volume::bigint FROM mkt_futures_1d WHERE \"symbolCode\" IN ('NQ','RTY','CL','6E','6J') AND \"eventDate\" >= '2020-01-01' ORDER BY \"symbolCode\", \"eventDate\") TO '/tmp/cross_asset_1d.csv' CSV"

psql "postgresql://postgres:postgres@localhost:54322/postgres" \
  -c "\COPY cross_asset_1d (symbol_code, ts, open, high, low, close, volume) FROM '/tmp/cross_asset_1d.csv' CSV"
```

#### CHECKPOINT S3 — Verify Sector 3

```bash
psql "postgresql://postgres:postgres@localhost:54322/postgres" -c "
SELECT symbol_code, count(*), min(ts)::date, max(ts)::date
FROM cross_asset_1d GROUP BY symbol_code ORDER BY symbol_code;"
```

Expected: ~1,500 rows per symbol. Clean up: `rm /tmp/cross_asset_1d.csv`

---

### SECTOR 4 — FRED Yields

**Table:** `econ_yields_1d`
**Source:** `econ_yields_1d` in rabid_raccoon (series: DGS2, DGS5, DGS10, DGS30, DGS3MO)
**Pre-check:** Confirm all 5 are in local series_catalog:

```bash
psql "postgresql://postgres:postgres@localhost:54322/postgres" -c "
SELECT series_id FROM series_catalog
WHERE series_id IN ('DGS2','DGS5','DGS10','DGS30','DGS3MO','DGS1','DGS1MO','DGS6MO','DGS7','DGS20','BAA10Y','T10Y2Y','T10Y3M')
ORDER BY series_id;"
```

Load only series that are confirmed in catalog. T10Y2Y from raccoon maps to `econ_yields_1d` (it's a yield spread — confirm its category in catalog first).

#### Step S4-A: Dry run

```bash
psql "postgresql://zincdigital@localhost:5432/rabid_raccoon" -c "
SELECT \"seriesId\", count(*), min(\"eventDate\")::date, max(\"eventDate\")::date
FROM econ_yields_1d
WHERE \"eventDate\" >= '2020-01-01'
GROUP BY \"seriesId\" ORDER BY \"seriesId\";"
```

Cross-reference with catalog output. Only load series in catalog.

#### Step S4-B: Export and load (adjust IN list to catalog-confirmed series only)

```bash
psql "postgresql://zincdigital@localhost:5432/rabid_raccoon" \
  -c "\COPY (SELECT \"seriesId\", \"eventDate\"::timestamp AT TIME ZONE 'UTC', value FROM econ_yields_1d WHERE \"seriesId\" IN ('DGS2','DGS5','DGS10','DGS30','DGS3MO') AND \"eventDate\" >= '2020-01-01' ORDER BY \"seriesId\", \"eventDate\") TO '/tmp/econ_yields.csv' CSV"

psql "postgresql://postgres:postgres@localhost:54322/postgres" \
  -c "\COPY econ_yields_1d (series_id, ts, value) FROM '/tmp/econ_yields.csv' CSV"
```

#### CHECKPOINT S4

```bash
psql "postgresql://postgres:postgres@localhost:54322/postgres" -c "
SELECT series_id, count(*), min(ts)::date, max(ts)::date
FROM econ_yields_1d GROUP BY series_id ORDER BY series_id;"
```

Expected: ~1,500 rows per series (6 years of daily data). Clean up: `rm /tmp/econ_yields.csv`

---

### SECTOR 5 — FRED Rates

**Table:** `econ_rates_1d`
**Source:** raccoon `econ_rates_1d` — has: DFEDTARL, DFEDTARU, DFF, SOFR, T10Y2Y
**Catalog check:** Local catalog has DFF, FEDFUNDS, SOFR in rates category. DFEDTARL/U and T10Y2Y are NOT in local catalog — do not attempt to load them (FK will reject).

**Pre-check:**
```bash
psql "postgresql://postgres:postgres@localhost:54322/postgres" -c "
SELECT series_id FROM series_catalog WHERE category = 'rates' ORDER BY series_id;"
```

Load only DFF and SOFR from raccoon (the two that exist in both places).

#### Step S5-A: Dry run

```bash
psql "postgresql://zincdigital@localhost:5432/rabid_raccoon" -c "
SELECT \"seriesId\", count(*), min(\"eventDate\")::date, max(\"eventDate\")::date
FROM econ_rates_1d
WHERE \"seriesId\" IN ('DFF','SOFR') AND \"eventDate\" >= '2020-01-01'
GROUP BY \"seriesId\";"
```

#### Step S5-B: Export and load

```bash
psql "postgresql://zincdigital@localhost:5432/rabid_raccoon" \
  -c "\COPY (SELECT \"seriesId\", \"eventDate\"::timestamp AT TIME ZONE 'UTC', value FROM econ_rates_1d WHERE \"seriesId\" IN ('DFF','SOFR') AND \"eventDate\" >= '2020-01-01' ORDER BY \"seriesId\", \"eventDate\") TO '/tmp/econ_rates.csv' CSV"

psql "postgresql://postgres:postgres@localhost:54322/postgres" \
  -c "\COPY econ_rates_1d (series_id, ts, value) FROM '/tmp/econ_rates.csv' CSV"
```

#### CHECKPOINT S5

```bash
psql "postgresql://postgres:postgres@localhost:54322/postgres" -c "
SELECT series_id, count(*), min(ts)::date, max(ts)::date
FROM econ_rates_1d GROUP BY series_id ORDER BY series_id;"
```

Note: FEDFUNDS will remain empty — it's in catalog but not in raccoon. Fill via FRED API pull later.
Clean up: `rm /tmp/econ_rates.csv`

---

### SECTOR 6 — FRED FX

**Table:** `econ_fx_1d`
**Source:** raccoon `econ_fx_1d` — has: DEXCHUS, DEXJPUS, DEXMXUS, DEXUSEU, DTWEXBGS
**Catalog check:** Local catalog has DEXJPUS, DEXUSEU, DTWEXBGS. Load only these 3 (DEXCHUS and DEXMXUS not in catalog).

#### Step S6-A: Dry run

```bash
psql "postgresql://zincdigital@localhost:5432/rabid_raccoon" -c "
SELECT \"seriesId\", count(*), min(\"eventDate\")::date, max(\"eventDate\")::date
FROM econ_fx_1d
WHERE \"seriesId\" IN ('DEXJPUS','DEXUSEU','DTWEXBGS') AND \"eventDate\" >= '2020-01-01'
GROUP BY \"seriesId\";"
```

#### Step S6-B: Export and load

```bash
psql "postgresql://zincdigital@localhost:5432/rabid_raccoon" \
  -c "\COPY (SELECT \"seriesId\", \"eventDate\"::timestamp AT TIME ZONE 'UTC', value FROM econ_fx_1d WHERE \"seriesId\" IN ('DEXJPUS','DEXUSEU','DTWEXBGS') AND \"eventDate\" >= '2020-01-01' ORDER BY \"seriesId\", \"eventDate\") TO '/tmp/econ_fx.csv' CSV"

psql "postgresql://postgres:postgres@localhost:54322/postgres" \
  -c "\COPY econ_fx_1d (series_id, ts, value) FROM '/tmp/econ_fx.csv' CSV"
```

#### CHECKPOINT S6

```bash
psql "postgresql://postgres:postgres@localhost:54322/postgres" -c "
SELECT series_id, count(*), min(ts)::date, max(ts)::date
FROM econ_fx_1d GROUP BY series_id ORDER BY series_id;"
```

Expected: 3 series, ~1,500 rows each. Clean up: `rm /tmp/econ_fx.csv`

---

### SECTOR 7 — FRED Inflation

**Table:** `econ_inflation_1d`
**Source:** raccoon `econ_inflation_1d` — has: CPIAUCSL, CPILFESL, DFII5, DFII10, MICH (check), PCEPILFE, PPIACO, T5YIE, T10YIE, T5YIFR

**Pre-check — which of these are in local catalog:**
```bash
psql "postgresql://postgres:postgres@localhost:54322/postgres" -c "
SELECT series_id FROM series_catalog WHERE category = 'inflation' ORDER BY series_id;"
```

Expected in catalog: CPIAUCSL, CPIFABSL, CPILFESL, CUSR0000SAH1, GDPDEF, MASSIVE_CPI*, MICH, PCE, PCEPI, PCEPILFE, PPIFIS, T5YIE, T10YIE, T5YIFR, EXPINF1YR/5YR/10YR/30YR (from migration 046).

DFII5/DFII10 (TIPS real yields) are NOT in catalog — check and register if needed, or skip.
PPIACO ≠ PPIFIS — different series ID. Do not load PPIACO unless it's registered as PPIACO.

Load only the intersection of raccoon series AND catalog. Use the catalog query output to build your IN list.

#### Step S7-A: Dry run (adjust IN list after catalog check)

```bash
psql "postgresql://zincdigital@localhost:5432/rabid_raccoon" -c "
SELECT \"seriesId\", count(*), min(\"eventDate\")::date, max(\"eventDate\")::date
FROM econ_inflation_1d
WHERE \"seriesId\" IN ('CPIAUCSL','CPILFESL','PCEPILFE','T5YIE','T10YIE','T5YIFR')
  AND \"eventDate\" >= '2020-01-01'
GROUP BY \"seriesId\" ORDER BY \"seriesId\";"
```

#### Step S7-B: Export and load (catalog-confirmed series only)

```bash
psql "postgresql://zincdigital@localhost:5432/rabid_raccoon" \
  -c "\COPY (SELECT \"seriesId\", \"eventDate\"::timestamp AT TIME ZONE 'UTC', value FROM econ_inflation_1d WHERE \"seriesId\" IN ('CPIAUCSL','CPILFESL','PCEPILFE','T5YIE','T10YIE','T5YIFR') AND \"eventDate\" >= '2020-01-01' ORDER BY \"seriesId\", \"eventDate\") TO '/tmp/econ_inflation.csv' CSV"

psql "postgresql://postgres:postgres@localhost:54322/postgres" \
  -c "\COPY econ_inflation_1d (series_id, ts, value) FROM '/tmp/econ_inflation.csv' CSV"
```

#### CHECKPOINT S7

```bash
psql "postgresql://postgres:postgres@localhost:54322/postgres" -c "
SELECT series_id, count(*), min(ts)::date, max(ts)::date
FROM econ_inflation_1d GROUP BY series_id ORDER BY series_id;"
```

Monthly series (CPI, PCE) will have ~72 rows (6 years × 12). Daily series (T5YIE etc) will have ~1,500. Both are correct — frequency varies by series.

Clean up: `rm /tmp/econ_inflation.csv`

---

### SECTOR 8 — Vol/Indexes (Fan-out)

This is the complex sector. rabid_raccoon has 97 series in `econ_vol_indices_1d`. They fan out to two local tables based on `series_catalog.category`.

**Pre-check — which raccoon series are in local catalog:**
```bash
psql "postgresql://postgres:postgres@localhost:54322/postgres" -c "
SELECT series_id, category FROM series_catalog
WHERE category IN ('vol','indexes') ORDER BY category, series_id;"
```

**Expected vol series in catalog:** OVXCLS, RVXCLS, VIXCLS, VXNCLS, GVZCLS (check which 4 are in `vol` category)
**Expected index series in catalog:** ANFCI, BAMLC0A0CM, BAMLH0A0HYM2, BAMLHYH0A0HYM2EY, EMVMACROBUS, NFCI, RECPROUSM156N, SAHMCURRENT, STLFSI4, UMCSENT, USEPUINDXD

Build the exact IN list from the catalog query output.

#### Step S8-A: Dry run for vol target

```bash
psql "postgresql://zincdigital@localhost:5432/rabid_raccoon" -c "
SELECT \"seriesId\", count(*), min(\"eventDate\")::date, max(\"eventDate\")::date
FROM econ_vol_indices_1d
WHERE \"seriesId\" IN ('VIXCLS','OVXCLS','GVZCLS','RVXCLS','VXNCLS')
  AND \"eventDate\" >= '2020-01-01'
GROUP BY \"seriesId\" ORDER BY \"seriesId\";"
```

#### Step S8-B: Load vol series → econ_vol_1d

```bash
psql "postgresql://zincdigital@localhost:5432/rabid_raccoon" \
  -c "\COPY (SELECT \"seriesId\", \"eventDate\"::timestamp AT TIME ZONE 'UTC', value FROM econ_vol_indices_1d WHERE \"seriesId\" IN ('VIXCLS','OVXCLS','GVZCLS','RVXCLS','VXNCLS') AND \"eventDate\" >= '2020-01-01' ORDER BY \"seriesId\", \"eventDate\") TO '/tmp/econ_vol.csv' CSV"

psql "postgresql://postgres:postgres@localhost:54322/postgres" \
  -c "\COPY econ_vol_1d (series_id, ts, value) FROM '/tmp/econ_vol.csv' CSV"
```

#### Step S8-C: Dry run for indexes target

```bash
psql "postgresql://zincdigital@localhost:5432/rabid_raccoon" -c "
SELECT \"seriesId\", count(*), min(\"eventDate\")::date, max(\"eventDate\")::date
FROM econ_vol_indices_1d
WHERE \"seriesId\" IN ('BAMLH0A0HYM2','BAMLC0A0CM','USEPUINDXD','EMVMACROBUS','NFCI','BAMLHYH0A0HYM2EY','STLFSI4','SAHMCURRENT','RECPROUSM156N','UMCSENT','ANFCI')
  AND \"eventDate\" >= '2020-01-01'
GROUP BY \"seriesId\" ORDER BY \"seriesId\";"
```

#### Step S8-D: Load index series → econ_indexes_1d

```bash
psql "postgresql://zincdigital@localhost:5432/rabid_raccoon" \
  -c "\COPY (SELECT \"seriesId\", \"eventDate\"::timestamp AT TIME ZONE 'UTC', value FROM econ_vol_indices_1d WHERE \"seriesId\" IN ('BAMLH0A0HYM2','BAMLC0A0CM','USEPUINDXD','EMVMACROBUS','NFCI','BAMLHYH0A0HYM2EY','STLFSI4','SAHMCURRENT','RECPROUSM156N','UMCSENT','ANFCI') AND \"eventDate\" >= '2020-01-01' ORDER BY \"seriesId\", \"eventDate\") TO '/tmp/econ_indexes.csv' CSV"

psql "postgresql://postgres:postgres@localhost:54322/postgres" \
  -c "\COPY econ_indexes_1d (series_id, ts, value) FROM '/tmp/econ_indexes.csv' CSV"
```

#### CHECKPOINT S8

```bash
psql "postgresql://postgres:postgres@localhost:54322/postgres" -c "
SELECT series_id, count(*), min(ts)::date, max(ts)::date FROM econ_vol_1d GROUP BY series_id ORDER BY series_id;
" && psql "postgresql://postgres:postgres@localhost:54322/postgres" -c "
SELECT series_id, count(*), min(ts)::date, max(ts)::date FROM econ_indexes_1d GROUP BY series_id ORDER BY series_id;"
```

Daily series: ~1,500 rows each. Monthly: ~72 rows. NFCI is weekly (~300 rows). All expected.

Clean up: `rm /tmp/econ_vol.csv /tmp/econ_indexes.csv`

---

## PHASE 3: FILL GAPS (Post-Migration)

These gaps can't be filled from rabid_raccoon. They require live API calls.

### Gap 1 — HG (Copper) cross-asset data

HG was added to the symbol list after rabid_raccoon was last populated. Must pull from Databento.

**Script:** `scripts/backfill-intermarket-15m.py` — run with `--symbol HG --start 2020-01-01`
**Tables:** `cross_asset_1h`, `cross_asset_1d`, `cross_asset_15m` (local only)
**Env vars required:** `DATABENTO_API_KEY`, `SUPABASE_URL` (local), `SUPABASE_SERVICE_ROLE_KEY` (local)

This is a separate session — do not run during this migration. Schedule separately.

### Gap 2 — Remaining FRED series not in raccoon

Series in `series_catalog` with no data (check after Phase 2 completes):
```bash
psql "postgresql://postgres:postgres@localhost:54322/postgres" -c "
SELECT sc.series_id, sc.category, sc.name
FROM series_catalog sc
LEFT JOIN (
  SELECT series_id FROM econ_yields_1d
  UNION ALL SELECT series_id FROM econ_rates_1d
  UNION ALL SELECT series_id FROM econ_fx_1d
  UNION ALL SELECT series_id FROM econ_inflation_1d
  UNION ALL SELECT series_id FROM econ_vol_1d
  UNION ALL SELECT series_id FROM econ_indexes_1d
  UNION ALL SELECT series_id FROM econ_labor_1d
  UNION ALL SELECT series_id FROM econ_activity_1d
  UNION ALL SELECT series_id FROM econ_money_1d
  UNION ALL SELECT series_id FROM econ_commodities_1d
) loaded ON sc.series_id = loaded.series_id
WHERE loaded.series_id IS NULL AND sc.is_active = true
ORDER BY sc.category, sc.series_id;"
```

These gaps (MASSIVE_* series, FEDFUNDS, any activity/labor/money series) will be filled by running the FRED backfill script against the local Supabase. Schedule separately.

---

## PHASE 4: FINAL VERIFICATION

### CHECKPOINT FINAL — Complete Local State

```bash
psql "postgresql://postgres:postgres@localhost:54322/postgres" -c "
SELECT table_name,
       (xpath('/row/cnt/text()', xml_count))[1]::text::bigint AS row_count
FROM (
  SELECT table_name,
         query_to_xml(format('SELECT count(*) AS cnt FROM public.%I', table_name), false, true, '') AS xml_count
  FROM information_schema.tables
  WHERE table_schema = 'public' AND table_type = 'BASE TABLE'
  ORDER BY table_name
) t;" > /tmp/local_final.txt && cat /tmp/local_final.txt
```

**Final pass criteria — local Supabase:**

| Table | Expected |
|-------|----------|
| `mes_15m` | ~130,000+ rows |
| `mes_1h` | ~30,000+ rows |
| `mes_1d` | ~1,500+ rows |
| `cross_asset_1h` | ~150,000+ rows (5 symbols) |
| `cross_asset_1d` | ~7,500+ rows (5 symbols) |
| `econ_yields_1d` | ~7,500+ rows (5 series) |
| `econ_rates_1d` | ~3,000+ rows (2 series from raccoon) |
| `econ_fx_1d` | ~4,500+ rows (3 series) |
| `econ_inflation_1d` | populated, varies by frequency |
| `econ_vol_1d` | ~7,500+ rows (5 series) |
| `econ_indexes_1d` | populated, varies by frequency |
| `series_catalog` | 89 rows |
| `symbols` | 61 rows |
| `warbird_*` | 0 rows (writers not yet active) |

**Final pass criteria — cloud Supabase:**

| Table | Expected |
|-------|----------|
| `mes_15m` | non-zero (live data) |
| `mes_1m` | non-zero (live ingestion buffer) |
| `cross_asset_1h` | non-zero (dashboard panel) |
| `econ_calendar` | non-zero (event overlay) |
| All 17 training tables | 0 rows |
| `warbird_*` | 0 rows (writers not yet active) |
| `series_catalog`, `symbols` | unchanged reference data |

If both pass → migration complete. Log in `docs/plans/update-log.md`.

---

## APPENDIX: QUICK REFERENCE AUDIT COMMANDS

### Check local table state (run any time)
```bash
psql "postgresql://postgres:postgres@localhost:54322/postgres" \
  -c "SELECT table_name, (xpath('/row/cnt/text()', query_to_xml(format('SELECT count(*) AS cnt FROM public.%I', table_name), false, true, '')))[1]::text::bigint AS rows FROM (SELECT table_name FROM information_schema.tables WHERE table_schema='public' AND table_type='BASE TABLE' ORDER BY table_name) t;"
```

### Check series coverage gaps (run after Phase 2)
See Phase 3, Gap 2 query above.

### Verify no pre-2020 data leaked in
```bash
psql "postgresql://postgres:postgres@localhost:54322/postgres" -c "
SELECT 'mes_15m' as tbl, min(ts)::date FROM mes_15m
UNION ALL SELECT 'cross_asset_1h', min(ts)::date FROM cross_asset_1h
UNION ALL SELECT 'econ_yields_1d', min(ts)::date FROM econ_yields_1d
ORDER BY tbl;"
```

All dates must be >= 2020-01-01.

### Verify raccoon source row counts (reference)
```bash
psql "postgresql://zincdigital@localhost:5432/rabid_raccoon" -c "
SELECT 'mes_15m' as src, count(*) FROM mkt_futures_mes_15m WHERE \"eventTime\" >= '2020-01-01'
UNION ALL SELECT 'cross_1h_5sym', count(*) FROM mkt_futures_1h WHERE \"symbolCode\" IN ('NQ','RTY','CL','6E','6J') AND \"eventTime\" >= '2020-01-01'
ORDER BY src;"
```
