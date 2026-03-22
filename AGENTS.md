# Warbird-Pro — Agent Rules

Read this file before any work.

## Active Plan

There is exactly one active architecture plan and one active update area:

- `docs/plans/2026-03-20-ag-teaches-pine-architecture.md`

Everything else is archived or reference-only and should not drive current implementation unless explicitly reopened.

## Stack

- Next.js (App Router) on Vercel — backend/API only (frontend is TradingView)
- Supabase (Postgres, Auth, Realtime, RLS) — NO Prisma, NO ORM
- AutoGluon (local Python) — entry gate model
- TradingView + Rabid Raccoon v2 Pine Script — all visualization
- Vercel Cron Jobs for ingestion scheduling

## Hard Rules

### Data — Zero Tolerance

- NEVER use mock, demo, placeholder, or fake data. Every data point must be real.
- If a feature has no real data yet, show NOTHING.
- NEVER query inactive symbols from Databento. Only `is_active=true AND data_source='DATABENTO'`.

### Naming

- Table prefix: `mes_`, `cross_asset_`, `econ_`, `warbird_`
- NEVER use `bhg_`, `BHG`, `mkt_futures_`, or rabid-raccoon legacy naming
- All database columns: snake_case. No ORM mapping.

### Database

- Supabase client only. Service role for writes, anon for reads.
- SQL migrations in `supabase/migrations/`. No Prisma. No Drizzle.
- RLS on all tables. Admin client: `lib/supabase/admin.ts`

### Scheduling

- All cron routes validate `CRON_SECRET` and log to `job_log`.
- All cron routes: `export const maxDuration = 60`
- Dead schedules must be removed from `vercel.json`.

### Production Boundary

- Local machines: training, calculations, research only.
- Production ingestion/crons/chart-serving must NOT depend on local machines.
- No continuous local runtime for live market data.

### Build & Deploy

- `npm run build` must pass before every push.
- No `/* */` block comments to disable code. Use `//` only.
- No `--no-verify` on git hooks.
- Push to repo → merge to main → Vercel auto-deploys. Never `npx vercel --prod`.

### Process

- One task at a time. Complete fully.
- Less complexity, fewer moving parts, better naming.
- NEVER refactor or "improve" code outside the current task.
- NEVER add or remove dependencies without asking.

## MES Ingestion — Current State

**Current:** `mes-catchup` is a monolithic cron (every 5 min) fetching ohlcv-1m + ohlcv-1h, aggregating in TypeScript.

**Planned:** Split into isolated per-schema routes when the active plan explicitly calls for it.

**Databento free schemas (Standard $179/mo):** ohlcv-1s, ohlcv-1m, ohlcv-1h, ohlcv-1d, definition, statistics. Currently using 2 of 6.
