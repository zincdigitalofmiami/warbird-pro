# News & Macro Data Pipeline — Agent Execution Instructions

**Date:** 2026-03-27
**Author:** Kirk (via Claude Opus planning session)
**Status:** COMPLETE — executed 2026-03-27

## Completion Summary

All phases executed. Key outcomes:
- Finnhub live: 20+ articles/hour with body extraction, topic scoring, 58 assessments. `npm:jsdom` → `npm:linkedom` fix applied.
- Newsfilter killed: Edge Function deleted, pg_cron removed, all code references removed.
- TradingEconomics killed: free tier returns zero US data. All wiring removed.
- Google News killed: headlines-only, no body extraction, wrong table/enum.
- 21 new FRED series registered and backfilled (3 deactivated — bad FRED IDs).
- GPR + Trump Effect Edge Functions deployed, pg_cron scheduled.
- 6 dead tables dropped, 3 unique constraints added, 10 FK constraints added.
- `news_signals` converted to materialized view with full provenance. Refreshes every 15 min.
- All crons spread out: overnight 01:00-04:00 UTC with 10-min gaps, market hours hourly.
- `npm run build` passes.

**Known remaining issues (moved to next plan):**
- GPR Edge Function hits compute limit (XLS too heavy for Deno)
- `cross_asset_1d` only starts 2026-03-15, needs backfill
- `econ_calendar` and `macro_reports_1d` not scheduled (no Edge Function)
- 3 FRED series need correct IDs
- Measured moves / fib setup pipeline not resurrected
- Warbird trading tables all empty
**Governing docs:** `AGENTS.md`, `CLAUDE.md`, `docs/agent-safety-gates.md`

---

## Context

Finnhub and Newsfilter Edge Functions are deployed but producing 0 rows. The only news data (751 rows in `econ_news_1d`) came from manual Google News RSS pulls via a broken Vercel route. Newsfilter has no free API key and is dead. FRED covers ~13 of ~65 needed macro indicators. TradingEconomics free tier is untested. GPR and Trump Effect routes exist as Vercel routes but have no schedules and violate the zero-Vercel-cron rule.

Migration 023 cut over MES, cross-asset, FRED, and news crons to Edge Functions, but the old Vercel routes remain as dead code creating drift risk. The econ schema has normalization gaps (unconstrained `series_id` text instead of FK to `series_catalog`, missing unique constraints on upsert targets). `news_signals` is a lossy direct-write table with no provenance link to source articles or scoring decisions.

## Absolute Rules (from AGENTS.md / CLAUDE.md)

1. **ZERO Vercel function invocations for cron/scheduled work.** All crons run via Supabase pg_cron calling Edge Functions.
2. **NEVER mock data.** Real or nothing.
3. **All cron routes validate auth and log to `job_log`.**
4. **All cron routes: `export const maxDuration = 60`.**
5. **`npm run build` must pass before any push.**
6. **One task at a time. Complete fully before starting the next.**
7. **Do NOT add dependencies without explicit approval from Kirk.**
8. **Copy working patterns from migration 023 (`supabase/migrations/20260328000023_edge_function_cron_cutover.sql`) for all new Edge Function + pg_cron wiring.** Do not invent new patterns.
9. **Use the completion schema from `docs/agent-safety-gates.md` Section 7 for every task.**

---

## Phase 1: Unblock Finnhub (news with body extraction)

### What exists
- Edge Function deployed: `supabase/functions/finnhub-news/index.ts` (delegates to `supabase/functions/_shared/news-provider.ts` → `runFinnhubRawIngest()`)
- pg_cron function exists: `public.run_finnhub_raw_pull()` (migration 023)
- pg_cron schedule exists: `5,20,35,50 11-23 * * 1-5` (every 15 min, Mon-Fri market hours)
- Tables exist: `econ_news_finnhub_articles`, `econ_news_finnhub_article_segments`, `econ_news_article_assessments`
- Auth pattern: `x-cron-secret` header validated against `EDGE_CRON_SECRET` Function secret
- API key: read from Deno env `FINNHUB_API_KEY` inside the Edge Function

### What's blocking
The Finnhub API key is not set as a Supabase Edge Function secret. The pg_cron function fires, hits the Edge Function, but the function has no `FINNHUB_API_KEY` and returns early.

### Task 1.1: Set Finnhub API key as Edge Function secret

**This is a manual Supabase dashboard action. Agent cannot do this.**

Kirk must go to: Supabase Dashboard → Project `qhwgrzqjcdtdqppvhhme` → Edge Functions → Secrets → Add:
- Key: `FINNHUB_API_KEY`
- Value: (the API key from the Finnhub dashboard screenshot — `d72m1cpr01qlfd9nnnegd72m1cpr01qlfd9nnnf0`)

Also add to `.env.local` for local development/testing:
```
FINNHUB_API_KEY=d72m1cpr01qlfd9nnnegd72m1cpr01qlfd9nnnf0
```

### Task 1.2: Validate Finnhub Edge Function produces rows

After the key is set, wait for the next cron cycle (runs every 15 min during market hours: `5,20,35,50 11-23 * * 1-5` UTC, Mon-Fri).

**Verification queries (run via Supabase SQL Editor or `psql`):**

```sql
-- Check if cron fired
SELECT * FROM job_log WHERE job_name = 'finnhub-news' ORDER BY created_at DESC LIMIT 5;

-- Check if articles landed
SELECT COUNT(*) FROM econ_news_finnhub_articles;
SELECT id, headline, source, published_at, extraction_status FROM econ_news_finnhub_articles ORDER BY published_at DESC LIMIT 5;

-- Check if assessments landed
SELECT COUNT(*) FROM econ_news_article_assessments WHERE provider = 'finnhub';

-- Check body extraction worked (should see FULL or PARTIAL, not all FAILED)
SELECT extraction_status, COUNT(*) FROM econ_news_finnhub_articles GROUP BY extraction_status;
```

**"Done well" means:**
- `econ_news_finnhub_articles` has rows with non-null `headline`, `source`, `published_at`
- At least 50% of articles have `extraction_status = 'FULL'` (body extracted via Readability)
- `econ_news_article_assessments` has matching assessment rows with scores in [0,1]
- `job_log` shows `SUCCESS` status for `finnhub-news`
- No `FAILED` entries in `job_log` after key is set

### Task 1.3: Tune news contract filters

The Finnhub Edge Function runs (fixed: `npm:jsdom` replaced with `npm:linkedom`) but 0 articles survive the combined quality + topic filter. 329 articles fetched → 185 fail `benchmarkFitScore < 0.55` → rest fail topic keyword match → 0 output. The filters need expansion.

**Contract file:** `supabase/functions/_shared/news-raw-contract.json` (and its mirror `config/news_raw_contract.json` — keep in sync)

**Changes needed:**

1. **Add missing trusted domains:**
   - `refinitiv.com` (Reuters subsidiary — source of high-quality technical market analysis)
   - `investing.com` (major market data/news site)
   - `forexlive.com` (futures/FX market coverage)

2. **Expand topic keywords** — current keywords are too narrowly S&P 500-focused. Many high-value articles reference Nasdaq, E-mini, or general index/futures terms. Add to the relevant topic `keywords` arrays:

   For `sp500_market`:
   - `"Nasdaq"`, `"Dow"`, `"Russell 2000"`, `"E-mini"`, `"key levels"`, `"record close"`, `"opening bell"`, `"traders"`, `"analyst"`

   For `sp500_volatility`:
   - `"VXN"`, `"uncertainty"`, `"swings"`, `"whipsaw"`, `"elevated volatility"`

   For `sp500_geopolitics`:
   - `"Iran war"`, `"uncertainty"`, `"de-escalation"`, `"escalation"`, `"ceasefire"`, `"Hormuz"`

   For `sp500_inflation`:
   - `"stagflation"`, `"disinflation"`, `"hot CPI"`, `"sticky inflation"`

   For `sp500_yields_rates`:
   - `"bonds"`, `"10-year"`, `"2-year"`, `"yield curve"`

   For `sp500_energy_inflation`:
   - `"crude oil"`, `"oil rally"`, `"Brent"`

   For `sp500_credit_liquidity`:
   - `"dollar gains"`, `"dollar strength"`, `"DXY"`

3. **Add Fibonacci/technical terms to `sp500_market` keywords:**
   - `"Fibonacci"`, `"retracement"`, `"support"`, `"resistance"`, `"moving average"`, `"DMA"`, `"200-day"`

4. **Lower `min_benchmark_fit_score` from 0.55 to 0.35** — the current threshold is filtering out useful articles. Lower it and let AG training determine the optimal cutoff later. The scoring pipeline still captures the full score, so lowering the ingest threshold doesn't lose quality information.

5. **CRITICAL — Symbol relevance gate:** Technical/trading keywords (Fibonacci, key levels, support, resistance, moving average, DMA, retracement, analyst, traders) MUST only match when the article also references one of our high-correlated symbols or indices. We do NOT want forex pair analysis, random commodity technicals, or single-stock chart analysis unless it explicitly ties back to our correlated universe.

   **High-correlated symbols that qualify an article:**
   - US equity indices: S&P 500, SPX, Nasdaq, IXIC, Dow, DJI, Russell 2000, RUT, SOX
   - US equity index futures: ES, NQ, YM, RTY, MES, E-mini, E-mini S&P, E-mini Nasdaq
   - Treasuries/rates: 10-year, 2-year, 30-year, ZN, ZB, ZF, Treasury, bonds, yield curve, SOFR
   - Commodities that move equities: crude oil, WTI, CL, gold, GC, natural gas, NG
   - Volatility: VIX, VXN, VVIX
   - Dollar (as cross-asset context only): DXY, dollar index, USD

   **The S&P 500 is the primary qualifying symbol.** MES is the micro contract of the S&P — news never mentions "MES", it mentions S&P 500, SPX, ES, SPY. All of these are MES-equivalent for filtering purposes. The symbol matching must treat any S&P 500 reference as a first-class match.

   **Forex pairs (6E, 6J, EUR/USD, USD/JPY) are NOT qualifying symbols** unless the article explicitly discusses their impact on the S&P 500 or US equity markets (e.g., "dollar strength pressures S&P 500"). An article purely about EUR/GBP Fibonacci levels is noise. Anything that correlates to or moves the S&P qualifies.

   **Implementation:** The existing `watchlistSymbols` + `extractWatchlistSymbols()` pattern in the scoring pipeline already checks for symbol mentions. The topic keyword expansion should lean on this — add technical terms to topic keywords, but the `watchlist_relevance_score` dimension in the scoring pipeline naturally penalizes articles that don't mention watchlist symbols. Verify that `watchlist_relevance_score` is weighted high enough (currently 0.12 — consider raising to 0.18) so symbol-irrelevant technical articles score below threshold even with good keyword matches.

**After updating the contract JSON:**
- Redeploy the Finnhub Edge Function: `npx supabase functions deploy finnhub-news`
- Test with dry_run first to see how many articles now pass
- Target: at least 5-15 articles per hourly run should survive

**"Done well" means:**
- An article like the Refinitiv "Volatility on watch as Nasdaq bulls and bears battle at key levels" example would match at least 2-3 topic codes
- At least 5 articles per hourly run survive into `econ_news_finnhub_articles`
- Both contract JSON files are in sync

### Task 1.4: Test Finnhub bonus endpoints (local curl only)

Run these locally to evaluate what the free tier returns. **Do NOT build anything yet.** Just report the response shape and data quality.

```bash
# Economic calendar
curl -s "https://finnhub.io/api/v1/calendar/economic?token=${FINNHUB_API_KEY}" | jq '.' | head -50

# Senate lobbying (neural net feature candidate)
curl -s "https://finnhub.io/api/v1/stock/lobbying?symbol=AAPL&token=${FINNHUB_API_KEY}" | jq '.' | head -50

# US government spending (neural net feature candidate)
curl -s "https://finnhub.io/api/v1/stock/usa-spending?symbol=AAPL&token=${FINNHUB_API_KEY}" | jq '.' | head -50

# Country metadata
curl -s "https://finnhub.io/api/v1/country?token=${FINNHUB_API_KEY}" | jq '.' | head -20
```

**Report for each endpoint:**
- HTTP status code
- Whether the response contains real data or an error/empty array
- The field names and sample values
- Whether the data is useful for MES futures neural net training

**Do NOT create routes, tables, or Edge Functions for these endpoints yet.** This is reconnaissance only.

---

## Phase 2: Kill Dead Code (Newsfilter + all superseded Vercel routes)

Migration 023 cut over ALL crons to Edge Functions. The old Vercel routes are dead code creating drift risk.

### Pre-review safety check
Before deleting anything, verify these files are truly dead (no live cron calls them, no other code imports from them):

```bash
# Verify no pg_cron job references any Vercel route URL
grep -r "vercel.app" supabase/migrations/20260328000023_edge_function_cron_cutover.sql

# Verify no other code imports from Newsfilter routes
grep -r "newsfilter-news/route" app/ lib/ --include="*.ts" --include="*.tsx"
grep -r "provider-ingest" app/ lib/ supabase/ --include="*.ts" --include="*.tsx" --include="*.mjs"

# Verify no other code imports from the dead cron routes
grep -r "cron/mes-1m/route" app/ lib/ --include="*.ts" --include="*.tsx"
grep -r "cron/cross-asset/route" app/ lib/ --include="*.ts" --include="*.tsx"
grep -r "cron/google-news/route" app/ lib/ --include="*.ts" --include="*.tsx"
```

### Task 2.1: Delete ALL dead Vercel cron routes

These are all superseded by Edge Functions (migration 023) or killed entirely:

| File to delete | Reason |
|---|---|
| `app/api/cron/finnhub-news/route.ts` | Superseded by Edge Function `finnhub-news` |
| `app/api/cron/newsfilter-news/route.ts` | Superseded by Edge Function; provider is dead |
| `app/api/cron/google-news/route.ts` | Killed — headlines-only, no body extraction, wrong table, wrong enum |
| `app/api/cron/mes-1m/route.ts` | Superseded by Edge Function `mes-1m` (migration 023) |
| `app/api/cron/cross-asset/route.ts` | Superseded by Edge Function `cross-asset` (migration 023) |

**After deletion, verify no empty `app/api/cron/*/` directories remain.** Delete empty dirs.

### Task 2.2: Remove Newsfilter Edge Function and cron

Since Newsfilter has no API key and never will (no free tier exists):

1. Delete `supabase/functions/newsfilter-news/index.ts`
2. Remove the `newsfilter-news` entry from `supabase/config.toml`
3. Create a new migration that:
   - Drops the pg_cron job for newsfilter: `SELECT cron.unschedule('warbird_newsfilter_raw_pull');` (verify exact job name first by checking migration 020 or 023)
   - Drops the helper function: `DROP FUNCTION IF EXISTS public.run_newsfilter_raw_pull();`
   - Add a comment: `-- Newsfilter removed: no free API tier exists. Provider access was never obtained.`

### Task 2.3: Decide on `lib/news/provider-ingest.ts`

Read `lib/news/provider-ingest.ts`. If it is ONLY imported by the deleted Vercel routes (`app/api/cron/finnhub-news/route.ts` and `app/api/cron/newsfilter-news/route.ts`), delete it.

If it is imported by anything else, keep it and document what still uses it.

```bash
grep -r "provider-ingest" app/ lib/ supabase/ --include="*.ts" --include="*.tsx" --include="*.mjs"
```

**"Done well" means:**
- All 5 dead Vercel routes deleted
- Newsfilter Edge Function + config.toml entry + pg_cron job + helper function all removed
- `provider-ingest.ts` deleted if orphaned, kept if still imported
- `npm run build` passes after all deletions
- No empty `app/api/cron/*/` directories remain
- No Newsfilter references remain in active (non-archived) code

---

## Phase 3: Add 22 Missing FRED Series

### Task 3.1: Create migration to register new series

Create a new migration file: `supabase/migrations/2026032800XX_fred_macro_expansion.sql` (use next available sequence number).

**Insert these series into `series_catalog`:**

```sql
INSERT INTO series_catalog (series_id, name, category, frequency, is_active) VALUES
  -- GDP (7 series)
  ('GDP',                 'Nominal GDP',                              'activity', 'quarterly', true),
  ('GDPC1',              'Real GDP (Constant Prices)',                'activity', 'quarterly', true),
  ('A191RL1Q225SBEA',    'Real GDP Growth Rate (Quarterly)',          'activity', 'quarterly', true),
  ('A191RL1A225SBEA',    'Real GDP Growth Rate (Annual)',             'activity', 'annual',    true),
  ('GDPDEF',             'GDP Implicit Price Deflator',              'inflation', 'quarterly', true),
  ('A939RX0Q048SBEA',    'Real GDP Per Capita',                      'activity', 'quarterly', true),
  ('GNP',                'Gross National Product',                    'activity', 'quarterly', true),

  -- Trade (2 series)
  ('BOPGSTB',            'Balance of Trade (Goods & Services)',       'activity', 'monthly',   true),
  ('BOPBCA',             'Current Account Balance',                   'activity', 'quarterly', true),

  -- Government fiscal (7 series)
  ('GFDEBTN',            'Federal Debt Total Public',                 'activity', 'quarterly', true),
  ('GFDEGDQ188S',        'Federal Debt as Percent of GDP',           'activity', 'quarterly', true),
  ('FGEXPND',            'Federal Government Expenditures',          'activity', 'quarterly', true),
  ('FGRECPT',            'Federal Government Receipts',              'activity', 'quarterly', true),
  ('FYFSD',              'Federal Surplus or Deficit as Pct of GDP', 'activity', 'annual',    true),
  ('FYOIGDA188S',        'Federal Outlays as Percent of GDP',        'activity', 'annual',    true),
  ('MTSDS133FMS',        'Monthly Treasury Statement Deficit',       'activity', 'monthly',   true),

  -- Prices (3 series)
  ('PPIFIS',             'PPI Final Demand',                         'inflation', 'monthly',   true),
  ('CUSR0000SAH',        'CPI Housing',                              'inflation', 'monthly',   true),
  ('CPIFABSL',           'CPI Food and Beverages',                   'inflation', 'monthly',   true),

  -- Investment proxy (1 series)
  ('GPDI',               'Gross Private Domestic Investment',         'activity', 'quarterly', true),

  -- Expectations (1 series)
  ('MICH',               'U Michigan Inflation Expectations 1Y',     'inflation', 'monthly',   true),

  -- GDP per capita PPP (1 series)
  ('NYGDPPCAPPPCD',      'GDP Per Capita PPP (World Bank)',          'activity', 'annual',    true)
ON CONFLICT (series_id) DO NOTHING;

-- Reactivate breakeven inflation series (were set inactive)
UPDATE series_catalog SET is_active = true WHERE series_id IN ('T5YIE', 'T10YIE');
```

### Pre-review safety check

Before applying:
1. Verify each `series_id` is a real FRED series by checking `https://fred.stlouisfed.org/series/<SERIES_ID>` for each one
2. `activity` IS a confirmed valid value in the `econ_category` enum (verified in `20260315000001_enums.sql`)
3. The existing nightly pg_cron FRED jobs query `series_catalog WHERE category = X AND is_active = true`, so new series are automatically picked up — no cron changes needed

### Task 3.2: Backfill the new series

After the migration is applied, run the existing backfill script with the 2024-01-01 floor:

```bash
python scripts/backfill-fred.py
```

**Verify backfill worked:**
```sql
-- Check each new series has data
SELECT series_id, MIN(ts) as earliest, MAX(ts) as latest, COUNT(*) as rows
FROM econ_activity_1d
WHERE series_id IN ('GDP', 'GDPC1', 'A191RL1Q225SBEA', 'GFDEBTN', 'GFDEGDQ188S', 'FGEXPND', 'FGRECPT', 'BOPGSTB', 'BOPBCA')
GROUP BY series_id
ORDER BY series_id;

SELECT series_id, MIN(ts), MAX(ts), COUNT(*)
FROM econ_inflation_1d
WHERE series_id IN ('PPIFIS', 'CUSR0000SAH', 'CPIFABSL', 'GDPDEF', 'MICH', 'T5YIE', 'T10YIE')
GROUP BY series_id
ORDER BY series_id;
```

**"Done well" means:**
- All 22 series registered in `series_catalog` with `is_active = true`
- `T5YIE` and `T10YIE` reactivated
- Backfill data present from 2024-01-01 forward for all series that FRED reports in that range
- Quarterly/annual series may have fewer rows — that's expected
- The existing nightly pg_cron jobs will automatically pick up these new series
- `npm run build` passes

---

## Phase 4: TradingEconomics — RESOLVED (Dead)

**Tested 2026-03-27. Free tier is useless for US data.**

- Calendar endpoint: returns events only for Sweden, Mexico, New Zealand, Thailand. Zero US events.
- Indicators endpoint: returns the catalog (388 US indicators) but no actual data values.
- Historical endpoint: 403 "No Access to this country as free user."
- GDP sector breakdowns: 403.

**Decision:** Kill TE as a data source. FRED covers US macro. GDP sector breakdowns (manufacturing, services, etc.) are unavailable without a paid TE subscription.

**Remove all TE wiring:**

### Task 4.1: Remove TE from econ-calendar route

The `econ-calendar` route (`app/api/cron/econ-calendar/route.ts`) has a TE primary path that will never work on free tier. Remove the `TRADINGECONOMICS_API_KEY` check and `fetchTeCalendar()` function. Make FRED the only path (not a fallback).

### Task 4.2: Remove TE API key from all environments

- Remove `TRADINGECONOMICS_API_KEY` from `.env.local`
- Remove `warbird_te_api_key` from Supabase Vault:
  ```sql
  DELETE FROM vault.secrets WHERE name = 'warbird_te_api_key';
  ```

### Task 4.3: Remove any TE references in codebase

```bash
grep -r "TRADINGECONOMICS" app/ lib/ supabase/ --include="*.ts" --include="*.tsx" --include="*.mjs" --include="*.json"
grep -r "tradingeconomics" app/ lib/ supabase/ --include="*.ts" --include="*.tsx" --include="*.mjs" --include="*.json"
```

Remove all references found. The econ-calendar route is the primary one — verify no other code touches TE.

**"Done well" means:**
- Zero references to TradingEconomics in active code
- `econ-calendar` route uses FRED only, no TE fallback logic
- TE key removed from `.env.local` and Vault
- `npm run build` passes

---

## Phase 5: GPR + Trump Effect → Edge Functions

These are currently Vercel routes. They must be migrated to Supabase Edge Functions per the zero-Vercel-cron rule.

### Task 5.1: Create GPR Edge Function

**Source route to port:** `app/api/cron/gpr/route.ts`
**External data source:** `https://www.matteoiacoviello.com/gpr_files/data_gpr_daily_recent.xls`
**Table:** `geopolitical_risk_1d` (columns: `ts`, `gpr_daily`, `gpr_threats`, `gpr_acts`)
**Schedule:** Daily at 19:00 UTC, Mon-Fri: `0 19 * * 1-5`
**No API key needed.** Public XLS file.

Steps:
1. Create `supabase/functions/gpr/index.ts`
2. Port the logic from `app/api/cron/gpr/route.ts` exactly — do NOT rewrite the XLS parsing logic, copy it
3. Auth: validate `x-cron-secret` header against `EDGE_CRON_SECRET` env var (same pattern as `finnhub-news`)
4. **Dependency check:** The Vercel route uses the `xlsx` npm package. For Deno Edge Functions, use `https://cdn.sheetjs.com/xlsx-0.20.3/package/xlsx.mjs` (the official SheetJS ESM CDN). **Verify this URL resolves before using it.** If it doesn't, find the correct Deno-compatible SheetJS import.
5. Log to `job_log` with `job_name = 'gpr'`
6. Add to `supabase/config.toml` under `[functions.gpr]` with `verify_jwt = false`

### Task 5.2: Create Trump Effect Edge Function

**Source route to port:** `app/api/cron/trump-effect/route.ts`
**External data source:** `https://www.federalregister.gov/api/v1/documents.json` (free, no key needed)
**Table:** `trump_effect_1d` (columns: `ts`, `event_type`, `title`, `summary`, `source`, `source_url`)
**Schedule:** Daily at 19:30 UTC, Mon-Fri: `30 19 * * 1-5`

Steps:
1. Create `supabase/functions/trump-effect/index.ts`
2. Port the logic from `app/api/cron/trump-effect/route.ts` exactly — copy the Federal Register API query construction
3. Auth: same `x-cron-secret` pattern
4. Log to `job_log` with `job_name = 'trump-effect'`
5. Add to `supabase/config.toml`

### Task 5.3: Create pg_cron migration for GPR + Trump Effect

Create migration: `supabase/migrations/2026032800XX_gpr_trump_effect_edge_crons.sql`

**Copy the exact pattern from migration 023** for the helper functions. The pattern is:
1. Read `warbird_edge_base_url` and `warbird_edge_cron_secret` from Vault
2. Call `net.http_post()` (or `net.http_get()`) with the Edge Function URL and `x-cron-secret` header
3. 55-second timeout

```sql
-- GPR helper function
CREATE OR REPLACE FUNCTION public.run_gpr_pull()
RETURNS void LANGUAGE plpgsql SECURITY DEFINER
SET search_path = public, extensions AS $$
DECLARE
  v_base_url text;
  v_secret   text;
BEGIN
  -- [exact vault lookup pattern from migration 023]
  -- Call: v_base_url || '/gpr'
END;
$$;

-- Trump Effect helper function
CREATE OR REPLACE FUNCTION public.run_trump_effect_pull()
RETURNS void LANGUAGE plpgsql SECURITY DEFINER
SET search_path = public, extensions AS $$
DECLARE
  v_base_url text;
  v_secret   text;
BEGIN
  -- [exact vault lookup pattern from migration 023]
  -- Call: v_base_url || '/trump-effect'
END;
$$;

-- Schedule
SELECT cron.schedule('warbird_gpr_pull', '0 19 * * 1-5', $$SELECT public.run_gpr_pull()$$);
SELECT cron.schedule('warbird_trump_effect_pull', '30 19 * * 1-5', $$SELECT public.run_trump_effect_pull()$$);
```

**"Done well" means:**
- Both Edge Functions deploy without error
- Both respond correctly to a manual `curl` with the `x-cron-secret` header
- pg_cron jobs are scheduled and fire on time
- `geopolitical_risk_1d` gets rows after the first GPR cron run
- `trump_effect_1d` gets rows after the first Trump Effect cron run
- `job_log` shows `SUCCESS` for both
- `npm run build` passes

---

## Phase 6: Schema Fixes & Normalization

This is the ML quant database standards phase. No shortcuts, no "it will do."

### Task 6.1: Drop dead tables

Create migration: `supabase/migrations/2026032800XX_schema_cleanup_and_normalization.sql`

```sql
-- ============================================================
-- Drop dead / orphaned tables
-- ============================================================

-- econ_news_1d: flat junk table, no dedupe, no topic linkage, freeform sentiment text.
-- 751 rows of Google News headlines with no body content. Replaced by structured
-- econ_news_finnhub_articles pipeline. No active writer.
DROP TABLE IF EXISTS econ_news_1d CASCADE;

-- policy_news_1d: zero rows, zero writers, never had a feed.
-- Policy/administration events are covered by trump_effect_1d (Federal Register API).
DROP TABLE IF EXISTS policy_news_1d CASCADE;

-- econ_news_newsfilter_articles + segments: dead provider, no free API tier exists.
-- Provider access was never obtained. Zero rows.
DROP TABLE IF EXISTS econ_news_newsfilter_article_segments CASCADE;
DROP TABLE IF EXISTS econ_news_newsfilter_articles CASCADE;

-- econ_news_rss_articles + segments: well-designed but never written to.
-- Google News route bypassed these entirely. Google News killed as modeling input
-- (headlines-only, no body extraction due to redirect URLs).
DROP TABLE IF EXISTS econ_news_rss_article_segments CASCADE;
DROP TABLE IF EXISTS econ_news_rss_articles CASCADE;
```

### Pre-review safety check for drops

Before applying, verify each table is truly empty or contains only junk data:

```sql
SELECT 'econ_news_1d' as tbl, COUNT(*) FROM econ_news_1d
UNION ALL SELECT 'policy_news_1d', COUNT(*) FROM policy_news_1d
UNION ALL SELECT 'econ_news_newsfilter_articles', COUNT(*) FROM econ_news_newsfilter_articles
UNION ALL SELECT 'econ_news_newsfilter_article_segments', COUNT(*) FROM econ_news_newsfilter_article_segments
UNION ALL SELECT 'econ_news_rss_articles', COUNT(*) FROM econ_news_rss_articles
UNION ALL SELECT 'econ_news_rss_article_segments', COUNT(*) FROM econ_news_rss_article_segments;
```

Expected: `econ_news_1d` = 751 (junk headlines), all others = 0. If any table unexpectedly has rows, STOP and report to Kirk.

Also verify no live code references these tables:

```bash
grep -r "econ_news_1d" app/ lib/ supabase/functions/ --include="*.ts" --include="*.tsx" --include="*.mjs"
grep -r "policy_news_1d" app/ lib/ supabase/functions/ --include="*.ts" --include="*.tsx" --include="*.mjs"
grep -r "econ_news_newsfilter" app/ lib/ supabase/functions/ --include="*.ts" --include="*.tsx" --include="*.mjs"
grep -r "econ_news_rss" app/ lib/ supabase/functions/ --include="*.ts" --include="*.tsx" --include="*.mjs"
```

If any live code references these tables, remove the references first (they should all be in dead routes being deleted in Phase 2).

### Task 6.2: Add missing unique constraints

In the same migration:

```sql
-- ============================================================
-- Add missing unique constraints (required for upsert deduplication)
-- ============================================================

-- news_signals: upsert target is (ts, signal_type) but no constraint enforces it
DO $$ BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'news_signals_ts_signal_type_key'
  ) THEN
    ALTER TABLE news_signals ADD CONSTRAINT news_signals_ts_signal_type_key UNIQUE (ts, signal_type);
  END IF;
END $$;

-- econ_calendar: upsert target is (ts, event_name) but no constraint enforces it
DO $$ BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'econ_calendar_ts_event_name_key'
  ) THEN
    ALTER TABLE econ_calendar ADD CONSTRAINT econ_calendar_ts_event_name_key UNIQUE (ts, event_name);
  END IF;
END $$;

-- trump_effect_1d: route upserts on (ts, title) but no constraint enforces it
DO $$ BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'trump_effect_1d_ts_title_key'
  ) THEN
    ALTER TABLE trump_effect_1d ADD CONSTRAINT trump_effect_1d_ts_title_key UNIQUE (ts, title);
  END IF;
END $$;
```

### Pre-review safety check for unique constraints

Before applying, verify no duplicate rows exist that would block the constraint:

```sql
SELECT 'news_signals' as tbl, ts, signal_type, COUNT(*)
FROM news_signals GROUP BY ts, signal_type HAVING COUNT(*) > 1
UNION ALL
SELECT 'econ_calendar', ts, event_name, COUNT(*)
FROM econ_calendar GROUP BY ts, event_name HAVING COUNT(*) > 1
UNION ALL
SELECT 'trump_effect_1d', ts, title, COUNT(*)
FROM trump_effect_1d GROUP BY ts, title HAVING COUNT(*) > 1;
```

If duplicates exist, deduplicate first (keep the row with the highest `id`), then apply the constraints.

### Task 6.3: Add FK constraints from econ tables to series_catalog

The 10 `econ_*_1d` tables store `series_id` as unconstrained text. This makes `series_catalog` advisory instead of authoritative. Add FK constraints.

In the same migration:

```sql
-- ============================================================
-- Normalize series_id: FK from econ_*_1d tables → series_catalog
-- ============================================================
-- series_catalog.series_id already has a UNIQUE constraint (from migration 005).
-- These FKs enforce that no econ data row can reference a non-existent series.

ALTER TABLE econ_rates_1d       ADD CONSTRAINT fk_rates_series       FOREIGN KEY (series_id) REFERENCES series_catalog(series_id);
ALTER TABLE econ_yields_1d      ADD CONSTRAINT fk_yields_series      FOREIGN KEY (series_id) REFERENCES series_catalog(series_id);
ALTER TABLE econ_inflation_1d   ADD CONSTRAINT fk_inflation_series   FOREIGN KEY (series_id) REFERENCES series_catalog(series_id);
ALTER TABLE econ_labor_1d       ADD CONSTRAINT fk_labor_series       FOREIGN KEY (series_id) REFERENCES series_catalog(series_id);
ALTER TABLE econ_activity_1d    ADD CONSTRAINT fk_activity_series    FOREIGN KEY (series_id) REFERENCES series_catalog(series_id);
ALTER TABLE econ_money_1d       ADD CONSTRAINT fk_money_series       FOREIGN KEY (series_id) REFERENCES series_catalog(series_id);
ALTER TABLE econ_commodities_1d ADD CONSTRAINT fk_commodities_series FOREIGN KEY (series_id) REFERENCES series_catalog(series_id);
ALTER TABLE econ_indexes_1d     ADD CONSTRAINT fk_indexes_series     FOREIGN KEY (series_id) REFERENCES series_catalog(series_id);
ALTER TABLE econ_fx_1d          ADD CONSTRAINT fk_fx_series          FOREIGN KEY (series_id) REFERENCES series_catalog(series_id);
ALTER TABLE econ_vol_1d         ADD CONSTRAINT fk_vol_series         FOREIGN KEY (series_id) REFERENCES series_catalog(series_id);
```

### Pre-review safety check for FK constraints

**CRITICAL:** If any existing row in an econ table references a `series_id` that is NOT in `series_catalog`, the FK will fail. Verify first:

```sql
-- Find orphaned series_ids in each econ table
SELECT 'rates' as tbl, e.series_id FROM econ_rates_1d e LEFT JOIN series_catalog c ON e.series_id = c.series_id WHERE c.series_id IS NULL GROUP BY e.series_id
UNION ALL
SELECT 'yields', e.series_id FROM econ_yields_1d e LEFT JOIN series_catalog c ON e.series_id = c.series_id WHERE c.series_id IS NULL GROUP BY e.series_id
UNION ALL
SELECT 'inflation', e.series_id FROM econ_inflation_1d e LEFT JOIN series_catalog c ON e.series_id = c.series_id WHERE c.series_id IS NULL GROUP BY e.series_id
UNION ALL
SELECT 'labor', e.series_id FROM econ_labor_1d e LEFT JOIN series_catalog c ON e.series_id = c.series_id WHERE c.series_id IS NULL GROUP BY e.series_id
UNION ALL
SELECT 'activity', e.series_id FROM econ_activity_1d e LEFT JOIN series_catalog c ON e.series_id = c.series_id WHERE c.series_id IS NULL GROUP BY e.series_id
UNION ALL
SELECT 'money', e.series_id FROM econ_money_1d e LEFT JOIN series_catalog c ON e.series_id = c.series_id WHERE c.series_id IS NULL GROUP BY e.series_id
UNION ALL
SELECT 'commodities', e.series_id FROM econ_commodities_1d e LEFT JOIN series_catalog c ON e.series_id = c.series_id WHERE c.series_id IS NULL GROUP BY e.series_id
UNION ALL
SELECT 'indexes', e.series_id FROM econ_indexes_1d e LEFT JOIN series_catalog c ON e.series_id = c.series_id WHERE c.series_id IS NULL GROUP BY e.series_id
UNION ALL
SELECT 'fx', e.series_id FROM econ_fx_1d e LEFT JOIN series_catalog c ON e.series_id = c.series_id WHERE c.series_id IS NULL GROUP BY e.series_id
UNION ALL
SELECT 'vol', e.series_id FROM econ_vol_1d e LEFT JOIN series_catalog c ON e.series_id = c.series_id WHERE c.series_id IS NULL GROUP BY e.series_id;
```

If any orphaned `series_id` values are found, add them to `series_catalog` BEFORE adding the FK constraints. Do NOT delete the data rows — add the missing catalog entries.

### Task 6.4: Convert `news_signals` to materialized view

`news_signals` is currently a direct-write table with no provenance link to source articles or scoring decisions. It stores only `ts/signal_type/direction/confidence/headline` — too lossy for ML training.

**Architecture change:** `news_signals` becomes a materialized view that aggregates from all signal sources with full provenance.

In the same migration:

```sql
-- ============================================================
-- Convert news_signals from direct-write table to materialized view
-- ============================================================

-- Step 1: Drop the old table (49 rows of low-quality Google News aggregations)
DROP TABLE IF EXISTS news_signals CASCADE;

-- Step 2: Create materialized view that aggregates ALL signal sources
CREATE MATERIALIZED VIEW news_signals AS

-- Source 1: Finnhub article assessments → per-topic sentiment per 15m bucket
-- Uses benchmark_fit_score as confidence, topic_code as signal_type
SELECT
  date_trunc('hour', a.scored_at) +
    (EXTRACT(minute FROM a.scored_at)::int / 15) * interval '15 min' AS ts,
  a.topic_code AS signal_type,
  'article_assessment' AS source_table,
  a.provider AS source_provider,
  a.dedupe_key AS source_key,
  CASE
    WHEN a.market_relevance_score > 0.6 THEN 'BULLISH'::market_impact_direction
    WHEN a.market_relevance_score < 0.4 THEN 'BEARISH'::market_impact_direction
    ELSE NULL
  END AS direction,
  a.benchmark_fit_score AS confidence,
  NULL::text AS source_headline,
  a.scored_at AS source_ts
FROM econ_news_article_assessments a

UNION ALL

-- Source 2: GPR daily index → geopolitical regime signal
-- GPR > historical mean = BEARISH (elevated risk), below = BULLISH (calm)
SELECT
  g.ts,
  'geopolitical_risk' AS signal_type,
  'geopolitical_risk_1d' AS source_table,
  'caldara_iacoviello' AS source_provider,
  'gpr_' || g.ts::date AS source_key,
  CASE
    WHEN g.gpr_daily > 100 THEN 'BEARISH'::market_impact_direction
    WHEN g.gpr_daily < 80 THEN 'BULLISH'::market_impact_direction
    ELSE NULL
  END AS direction,
  LEAST(1.0, g.gpr_daily / 200.0) AS confidence,
  NULL::text AS source_headline,
  g.ts AS source_ts
FROM geopolitical_risk_1d g

UNION ALL

-- Source 3: Trump Effect → policy event presence signal
SELECT
  t.ts,
  'policy_event' AS signal_type,
  'trump_effect_1d' AS source_table,
  'federal_register' AS source_provider,
  'te_' || t.id AS source_key,
  NULL::market_impact_direction AS direction,
  0.5 AS confidence,
  t.title AS source_headline,
  t.ts AS source_ts
FROM trump_effect_1d t

WITH NO DATA;

-- Step 3: Create indexes on the materialized view
CREATE INDEX idx_news_signals_ts ON news_signals (ts DESC);
CREATE INDEX idx_news_signals_type_ts ON news_signals (signal_type, ts DESC);
CREATE INDEX idx_news_signals_source ON news_signals (source_table, source_ts DESC);

-- Step 4: Initial refresh
REFRESH MATERIALIZED VIEW news_signals;

-- Step 5: Add comment explaining the architecture
COMMENT ON MATERIALIZED VIEW news_signals IS
  'Derived signal surface aggregating all news/event sources with full provenance. '
  'Refresh via: REFRESH MATERIALIZED VIEW CONCURRENTLY news_signals; '
  'Sources: econ_news_article_assessments, geopolitical_risk_1d, trump_effect_1d. '
  'macro_reports_1d will be added when actual/forecast/surprise data is available.';
```

**IMPORTANT NOTES on the materialized view:**

1. The BULLISH/BEARISH thresholds above (market_relevance_score > 0.6, GPR > 100) are **starter heuristics**. They should be reviewed once Finnhub data flows and we can see actual score distributions. The thresholds will be refined by AG training.

2. `macro_reports_1d` is NOT included yet because it has no actual/forecast/surprise data. When TE testing (Phase 4) determines whether we can populate it, add it as a 4th UNION ALL source.

3. The view needs a pg_cron job to refresh periodically. Add to the GPR/Trump Effect cron migration (Phase 5, Task 5.3):

```sql
-- Refresh news_signals materialized view every 15 min during market hours
-- (aligned with MES 15m bar close)
CREATE OR REPLACE FUNCTION public.refresh_news_signals()
RETURNS void LANGUAGE plpgsql SECURITY DEFINER
SET search_path = public AS $$
BEGIN
  REFRESH MATERIALIZED VIEW CONCURRENTLY news_signals;
EXCEPTION WHEN OTHERS THEN
  -- CONCURRENTLY requires a unique index; fall back to full refresh
  REFRESH MATERIALIZED VIEW news_signals;
END;
$$;

SELECT cron.schedule('warbird_refresh_news_signals', '2,17,32,47 11-23 * * 1-5',
  $$SELECT public.refresh_news_signals()$$);
```

Note: `REFRESH MATERIALIZED VIEW CONCURRENTLY` requires a unique index on the view. If the view cannot have a natural unique key, use plain `REFRESH MATERIALIZED VIEW` (locks reads briefly but acceptable at 15m cadence).

4. **Unified news article view** for future cross-provider dedup:

```sql
-- Unified view across all article providers (currently just Finnhub)
-- Add UNION ALL for additional providers when they are added
CREATE OR REPLACE VIEW all_news_articles AS
SELECT
  dedupe_key,
  provider,
  title,
  summary,
  article_body,
  body_word_count,
  extraction_status,
  published_at,
  published_minute,
  publisher_domain,
  url,
  canonical_url,
  related_symbols,
  created_at
FROM econ_news_finnhub_articles;

COMMENT ON VIEW all_news_articles IS
  'Unified read view across all news article providers. Currently Finnhub only. '
  'Deduplication across providers uses dedupe_key (md5 of normalized_title + domain + published_minute).';
```

### "Done well" means (entire Phase 6):
- All 6 dead tables dropped (verified empty/junk first)
- 3 unique constraints added (duplicates resolved first if any exist)
- 10 FK constraints added from `econ_*_1d.series_id` → `series_catalog.series_id` (orphans resolved first)
- `news_signals` converted from table to materialized view with provenance columns
- `all_news_articles` unified view created
- Refresh cron job scheduled for `news_signals`
- `npm run build` passes
- All pre-review safety checks passed before applying

---

## Phase 7: Update Documentation

After all phases complete, update these files:

### CLAUDE.md — Current Status section

Update "What Works":
- Finnhub Edge Function producing scored, body-extracted news articles
- GPR Edge Function producing daily geopolitical risk index
- Trump Effect Edge Function producing executive order/memoranda tracking
- 22 new FRED series registered and backfilled (GDP, trade, government, prices)
- `T5YIE` and `T10YIE` breakeven inflation reactivated
- `news_signals` is now a materialized view aggregating all signal sources with full provenance
- `series_catalog` is now authoritative (FK-enforced from all econ tables)
- Dead tables dropped: `econ_news_1d`, `policy_news_1d`, Newsfilter tables, RSS tables

Update "What Doesn't Work Yet":
- Remove: "Live Supabase Vault is still missing warbird_finnhub_api_key" (if fixed)
- Add: TradingEconomics free tier evaluation results (from Phase 4)
- Update Newsfilter line to: "Newsfilter removed — no free API tier exists"
- Google News RSS route removed — headlines-only was insufficient for neural net training
- `news_signals` materialized view BULLISH/BEARISH thresholds are starter heuristics pending AG training refinement
- `macro_reports_1d` not yet included in `news_signals` view (pending TE actual/forecast data)

### AGENTS.md

No changes needed unless a hard workflow rule changed.

### Memory

Save a memory entry with:
- Finnhub is live and producing rows (or blockers if not)
- Newsfilter is dead and removed
- FRED expanded to ~57 active series
- TE free tier evaluation results
- GPR + Trump Effect are Edge Functions with pg_cron schedules
- `news_signals` is a materialized view, not a direct-write table
- `series_catalog` is FK-enforced from all 10 econ tables
- 6 dead tables dropped: `econ_news_1d`, `policy_news_1d`, 2 Newsfilter, 2 RSS

---

## Execution Order Summary

| Phase | Depends On | Can Parallel? |
|-------|-----------|---------------|
| 1 (Finnhub unblock) | Kirk sets API key in dashboard | No — manual step first |
| 2 (Kill dead code) | Nothing | Yes — independent |
| 3 (FRED expansion) | Nothing | Yes — independent |
| 4 (TE testing) | Kirk sets key in .env.local | No — manual step first |
| 5 (GPR + Trump Effect) | Nothing | Yes — independent |
| 6 (Schema fixes) | Phase 2 (dead tables must be deleted before dropping) and Phase 3 (new series must be in catalog before FK) | After 2 and 3 |
| 7 (Docs update) | All above | No — last |

**Phases 2, 3, and 5 can run in parallel.** Phase 1 and 4 require Kirk to set API keys first. Phase 6 depends on 2 and 3. Phase 7 is always last.
