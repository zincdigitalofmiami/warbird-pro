# Data Gaps & Schema Rebuild — Agent Execution Instructions

**Date:** 2026-03-27
**Author:** Kirk (via Claude Opus planning session)
**Status:** APPROVED — ready for agent execution
**Governing docs:** `AGENTS.md`, `CLAUDE.md`, `docs/agent-safety-gates.md`
**Prior plan:** `docs/plans/2026-03-27-news-macro-data-pipeline-instructions.md` (COMPLETE)

---

## Context

The news & macro data pipeline is live. This plan covers the remaining data gaps, scheduling fixes, and the warbird trading schema rebuild. The core issue is that the trading pipeline tables (`warbird_setups`, `warbird_setup_events`, `trade_scores`, `measured_moves`) are empty or nearly empty — this is the AG training surface and must be rebuilt.

## Absolute Rules (from AGENTS.md / CLAUDE.md)

1. **ZERO Vercel function invocations for cron/scheduled work.** All crons run via Supabase pg_cron calling Edge Functions.
2. **NEVER mock data.** Real or nothing.
3. **All crons spread out — minimum 10 minutes between jobs.** No stacking.
4. **Core historical retention starts at `2024-01-01T00:00:00Z`.**
5. **`npm run build` must pass before any push.**
6. **Copy working patterns from migration 023 for all new Edge Function + pg_cron wiring.**
7. **Use the completion schema from `docs/agent-safety-gates.md` Section 7 for every task.**

---

## Phase 1: Fix GPR Edge Function Compute Limit

The GPR Edge Function (`supabase/functions/gpr/index.ts`) crashes with `WORKER_LIMIT` because `npm:xlsx` is too heavy for Deno Edge runtime. The XLS file is ~500KB binary Excel from `https://www.matteoiacoviello.com/gpr_files/data_gpr_daily_recent.xls`.

**Table:** `geopolitical_risk_1d` (813 rows exist from old Vercel route)
**pg_cron:** `warbird_gpr_pull` at `0 19 * * 1-5` — scheduled but failing

### Options (pick one):

**Option A: Lightweight XLS parsing** — Replace `npm:xlsx` with a minimal binary XLS reader or convert the fetch to parse CSV if the source offers one. Check if `https://www.matteoiacoviello.com/gpr_files/` has a CSV alternative.

**Option B: Keep GPR as the one Vercel route exception** — The route at `app/api/cron/gpr/route.ts` works. Update the pg_cron helper to call the Vercel URL instead of the Edge Function URL. This violates the zero-Vercel-cron rule but GPR is a single daily call to a public XLS file.

**Option C: Move GPR to a local Python script** — Since GPR is daily and non-time-critical, run it as a local cron job that writes directly to Supabase. This moves it off Edge entirely.

**Recommendation:** Option A first — check for CSV source. If not available, Option B is pragmatic (one exception for a public daily XLS).

**"Done well" means:**
- `geopolitical_risk_1d` gets new rows from automated cron
- `job_log` shows `SUCCESS` for `gpr`

---

## Phase 2: Backfill `cross_asset_1d` from 2024-01-01

`cross_asset_1d` only has data starting 2026-03-15 (163 rows). The 1h table has 131k rows. The daily table needs backfill.

### Task 2.1: Check if rollup can be done from existing 1h data

```sql
-- What's the earliest cross_asset_1h data?
SELECT MIN(ts)::date, MAX(ts)::date, COUNT(*) FROM cross_asset_1h;

-- What symbols are in 1h?
SELECT symbol_code, MIN(ts)::date, MAX(ts)::date, COUNT(*)
FROM cross_asset_1h GROUP BY symbol_code ORDER BY symbol_code;
```

If 1h data goes back to 2024-01-01, roll up to 1d with:
```sql
INSERT INTO cross_asset_1d (ts, symbol_code, open, high, low, close, volume)
SELECT
  date_trunc('day', ts) AS ts,
  symbol_code,
  (array_agg(open ORDER BY ts))[1] AS open,
  MAX(high) AS high,
  MIN(low) AS low,
  (array_agg(close ORDER BY ts DESC))[1] AS close,
  SUM(volume) AS volume
FROM cross_asset_1h
WHERE ts >= '2024-01-01'
GROUP BY date_trunc('day', ts), symbol_code
ON CONFLICT (ts, symbol_code) DO UPDATE SET
  open = EXCLUDED.open, high = EXCLUDED.high, low = EXCLUDED.low,
  close = EXCLUDED.close, volume = EXCLUDED.volume;
```

If 1h data doesn't go back far enough, use the Databento backfill Edge Function (check if `cross-asset` Edge Function supports a date range parameter).

**"Done well" means:**
- `cross_asset_1d` has data from 2024-01-01 forward
- All active Databento symbols represented

---

## Phase 3: Schedule `econ_calendar` as Edge Function

`econ_calendar` has 10,550 rows from backfill but no automated schedule. The Vercel route at `app/api/cron/econ-calendar/route.ts` exists (now FRED-only after TE removal).

### Task 3.1: Create econ-calendar Edge Function

Port `app/api/cron/econ-calendar/route.ts` to `supabase/functions/econ-calendar/index.ts`. Same pattern as other Edge Functions.

**Data source:** FRED releases API (`https://api.stlouisfed.org/fred/releases/dates`)
**Table:** `econ_calendar` (columns: `ts`, `event_name`, `importance`, `actual`, `forecast`, `previous`)
**API key:** `FRED_API_KEY` (already in Edge Function secrets)

### Task 3.2: Add pg_cron schedule

**Spread into the overnight window.** Currently the window is:
```
01:00-01:30  cross-asset
02:00-03:30  FRED (10 categories)
03:50-04:00  Massive
```

Add econ-calendar at **04:20 UTC** (20 min after last Massive job):
```sql
SELECT cron.schedule('warbird_econ_calendar', '20 4 * * 1-5', $$SELECT public.run_econ_calendar_pull()$$);
```

Create helper function following migration 023 pattern: vault lookup → `net.http_post()` → Edge Function URL.

### Task 3.3: Delete old Vercel route

After Edge Function is deployed and verified:
- Delete `app/api/cron/econ-calendar/route.ts`

**"Done well" means:**
- `econ_calendar` gets new rows from automated daily cron
- Schedule is at 04:20 UTC — 20 min gap from prior job
- `npm run build` passes after Vercel route deletion

---

## Phase 4: Fix 3 Bad FRED Series IDs

Three series were deactivated because the FRED API returned 400:

| series_id | Intended | Problem |
|---|---|---|
| `A191RL1A225SBEA` | Annual GDP Growth Rate | May need different series ID |
| `CUSR0000SAH` | CPI Housing | Series ID may be wrong |
| `NYGDPPCAPPPCD` | GDP per Capita PPP (World Bank) | World Bank series may use different API endpoint |

### Task 4.1: Research correct FRED series IDs

For each, search `https://fred.stlouisfed.org/` and find the correct series:

1. **Annual GDP Growth** — try `A191RL1A225SBEA` on FRED website. If it exists, the issue may be the date range. Try `observation_start=2020-01-01` instead of `2024-01-01` (annual series may not have 2024+ data yet).

2. **CPI Housing** — the correct FRED series for CPI Housing/Shelter is likely `CUUR0000SAH1` (CPI Housing, not seasonally adjusted) or `CUSR0000SAH1` (note the `1` at the end). Verify on FRED.

3. **GDP per Capita PPP** — this is a World Bank series. FRED hosts it but the series ID may be `NYGDPPCAPKDUSA` or similar. Search FRED for "GDP per capita PPP United States".

### Task 4.2: Update series_catalog and backfill

For each corrected series:
```sql
UPDATE series_catalog SET series_id = '<correct_id>', is_active = true WHERE series_id = '<old_id>';
```

Then backfill using the FRED API.

**"Done well" means:**
- All 3 series active with correct IDs
- Backfill data present from 2024-01-01 (or earliest available for annual series)

---

## Phase 5: Clean Stale Vault Secrets

Three old Vercel-era secrets remain:
- `warbird_newsfilter_raw_cron_url` — Newsfilter is dead
- `warbird_finnhub_raw_cron_url` — superseded by Edge Function base URL
- `warbird_mes_1m_cron_url` — superseded by Edge Function base URL

```sql
DELETE FROM vault.secrets WHERE name IN (
  'warbird_newsfilter_raw_cron_url',
  'warbird_finnhub_raw_cron_url',
  'warbird_mes_1m_cron_url'
);
```

**"Done well" means:**
- Only active Vault secrets remain: `warbird_edge_base_url`, `warbird_edge_cron_secret`, `warbird_cron_secret`, `warbird_finnhub_api_key`

---

## Phase 6: Spread Daily Pulls Across 24 Hours

Currently all overnight jobs stack between 01:00-04:00 UTC. For daily-frequency data that doesn't need to be fresh by market open, spread across the full day.

**Current overnight window (01:00-04:20 UTC) — keep for market-critical data:**
```
01:00-01:30  cross-asset (needs fresh data for market open)
02:00-03:30  FRED rates/yields/vol/inflation/fx/labor/activity/money/commodities/indexes
03:50-04:00  Massive inflation
04:20        econ-calendar (after Phase 3)
```

**Move non-time-critical pulls to spread across 24h:**
```
06:00  GPR (daily geopolitical index — doesn't change intraday)
08:00  Trump Effect (Federal Register — publishes during business hours)
```

Update the existing cron schedules:
```sql
SELECT cron.unschedule('warbird_gpr_pull');
SELECT cron.schedule('warbird_gpr_pull', '0 6 * * 1-5', $$SELECT public.run_gpr_pull()$$);

SELECT cron.unschedule('warbird_trump_effect_pull');
SELECT cron.schedule('warbird_trump_effect_pull', '0 8 * * 1-5', $$SELECT public.run_trump_effect_pull()$$);
```

**Market hours jobs (unchanged — these need to run during session):**
```
:30 past every hour 11-23 UTC  Finnhub news
:02/:17/:32/:47 11-23 UTC      news_signals refresh
:05 past every hour             MES hourly rollup
every minute                    MES 1m
```

**"Done well" means:**
- No two jobs fire within 10 minutes of each other overnight
- Daily non-critical jobs spread to morning/afternoon slots
- Market hours jobs unchanged

---

## Phase 7: Warbird Trading Schema Rebuild

This is the core AG training surface. All these tables are empty or nearly empty:

| Table | Rows | Purpose |
|---|---|---|
| `warbird_setups` | 0 | Detected fib setup candidates |
| `warbird_setup_events` | 0 | Events within a setup lifecycle |
| `trade_scores` | 0 | AG model scores per setup |
| `measured_moves` | 76 | Fib measured move calculations |
| `warbird_conviction` | 0 | Model conviction scores |
| `warbird_daily_bias` | 4 | Daily directional bias |
| `warbird_risk` | 0 | Risk state per setup |
| `warbird_triggers_15m` | 0 | 15m bar trigger events |
| `warbird_structure_4h` | 12 | 4h market structure |
| `warbird_forecasts_1h` | 0 | Legacy — do NOT use (locked rule) |
| `models` | 0 | AG model metadata |

**This phase requires Kirk's input on the lost schema.** The tables exist but the pipeline that populates them is broken or missing.

### Task 7.1: Audit existing route code

These Vercel routes exist and reference the warbird tables:
- `app/api/cron/detect-setups/route.ts`
- `app/api/cron/measured-moves/route.ts`
- `app/api/cron/score-trades/route.ts`

Read each one. Document:
- What tables they read from and write to
- What the detection/scoring logic does
- What's broken (missing tables, wrong references, stale imports)
- Dependencies between them (order of operations)

Also read:
- `lib/setup-engine.ts`
- `lib/measured-move.ts`
- `lib/setup-candidates.ts`
- `lib/warbird/projection.ts`
- `scripts/warbird/fib-engine.ts`
- `scripts/warbird/build-warbird-dataset.ts`

### Task 7.2: Document the required pipeline

The canonical trade object is the **MES 15m fib setup** keyed by MES 15m bar close in `America/Chicago`. The pipeline should be:

1. **Detect setups** — scan MES 15m bars for fib retracement patterns → write to `warbird_setups`
2. **Measure moves** — calculate fib extensions, TP1/TP2/SL levels → write to `measured_moves`
3. **Track events** — as price hits fib levels, record touch/break/hold/reject → write to `warbird_setup_events`
4. **Score outcomes** — after setup resolves, score TP1 hit / TP2 hit / SL hit / reversal → write to `trade_scores`

Document what exists vs what's missing. **Do NOT implement yet** — report findings to Kirk.

### Task 7.3: Identify the lost schema

Kirk mentioned "lost schema" — there was a schema/pipeline that worked at some point and was lost. Check:
- Git log for deleted migrations or schema changes
- Any `*.sql` files in `scripts/` or `docs/` that reference these tables
- The active plan (`docs/plans/2026-03-20-ag-teaches-pine-architecture.md`) for the fib setup contract

```bash
git log --all --oneline -- 'supabase/migrations/*setup*' 'supabase/migrations/*trade*' 'supabase/migrations/*measured*'
git log --all --diff-filter=D -- 'supabase/migrations/*.sql'
```

**"Done well" means:**
- Complete audit document of what exists, what's broken, what's missing
- Clear gap list between current state and the canonical MES 15m fib setup pipeline
- Recommendation for rebuild approach
- **No code changes** — research and documentation only

---

## Execution Order

| Phase | Depends On | Priority |
|---|---|---|
| 1 (GPR compute fix) | Nothing | P1 — cron is failing daily |
| 2 (cross_asset_1d backfill) | Nothing | P1 — training data gap |
| 3 (econ-calendar Edge Function) | Nothing | P2 |
| 4 (Fix 3 FRED series) | Nothing | P3 |
| 5 (Clean Vault) | Nothing | P3 |
| 6 (Spread daily pulls) | Phase 3 | P2 |
| 7 (Warbird schema rebuild) | Nothing | P0 — this is the AG training surface |

**Phase 7 is the most important but is research-only.** Phases 1-2 are quick fixes that unblock training data. Phases 3-6 are housekeeping.
