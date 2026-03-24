# Warbird-Pro — Agent Rules

Read this file before any work.

## Active Plan

There is exactly one active architecture plan and one active update area:

- `docs/plans/2026-03-20-ag-teaches-pine-architecture.md`

Everything else is archived or reference-only and should not drive current implementation unless explicitly reopened.

## Contract First

- The canonical trade object is the **MES 15m fib setup**.
- The canonical key is the MES 15m bar-close timestamp in `America/Chicago`.
- Any remaining `1H` wording in old docs, specs, scripts, or comments is legacy and must not drive new work.
- Pine is the live production surface.
- AutoGluon is offline only and may only promote Pine-ready packet outputs.

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
- Before each phase or checkpoint, reread the active plan section that governs that work.
- After each locked phase or checkpoint, update the active plan with findings, validations, blockers, and the next blocking item.
- Update `WARBIRD_MODEL_SPEC.md` when the model contract changes.
- Update `CLAUDE.md` when current status or live operational truth changes.
- Update `AGENTS.md` only when repo rules or hard workflow constraints change.
- Update memory with the current canonical contract, required harness status, and current blocker when a phase locks.

### No Hand-Rolling — Copy Working Code

- When a working implementation exists (library example, reference indicator, proven pattern), **COPY IT EXACTLY**.
- Adapt the INTERFACE (inputs, outputs, variable names). Do NOT rewrite the INTERNALS.
- If you can't explain why your version differs line-by-line from the reference, you don't understand it well enough to rewrite it.
- This applies to: library integrations, API call patterns, algorithm ports, Pine Script engine code — EVERYTHING.
- Violating this rule produces broken code that looks right but behaves wrong, wastes hours of debugging, and poisons downstream model training with inaccurate signals.

### Required Open-Source Harnesses

- `Pivot Levels [BigBeluga]` is required.
- `Market Structure Break & OB Probability Toolkit [LuxAlgo]` is required.
- `Luminance Breakout Engine [LuxAlgo]` is later-phase only.
- For required or approved harnesses:
  - confirm the TradingView page shows `OPEN-SOURCE SCRIPT`
  - retrieve code through the script page's `Source code` entry
  - copy internals exactly
  - allow interface-only edits
  - if exact-copy use is blocked, STOP

## MES Ingestion — Current State

**Current:** `mes-catchup` is a monolithic cron (every 5 min) fetching ohlcv-1m + ohlcv-1h, aggregating in TypeScript.

**Planned:** Split into isolated per-schema routes when the active plan explicitly calls for it.

**Databento free schemas (Standard $179/mo):** ohlcv-1s, ohlcv-1m, ohlcv-1h, ohlcv-1d, definition, statistics. Currently using 2 of 6.
