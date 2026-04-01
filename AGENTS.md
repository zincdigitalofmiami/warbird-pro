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
- Pine is the canonical signal surface. The Next.js dashboard is the mirrored operator surface on the same contract, not a separate decision engine.
- Live model outputs are TP1/TP2/reversal outcome state for the MES 15m fib setup, not predicted-price forecasts.
- `news_signals` is retired from the active contract. Do not build new schema, writer logic, dashboard logic, or training assumptions around NEWS unless the user explicitly reopens it.
- AutoGluon is offline only and may only promote Pine-ready packet outputs.

## Stack

- Next.js (App Router) — frontend dashboard and route handlers only (frontend is TradingView)
- Supabase (Postgres, Auth, Realtime, RLS, pg_cron) — NO Prisma, NO ORM
- AutoGluon (local Python) — entry gate model
- TradingView + Rabid Raccoon v2 Pine Script — all visualization
- Supabase pg_cron — sole scheduling and recurring function producer

## Hard Rules

### Data — Zero Tolerance

- NEVER use mock, demo, placeholder, or fake data. Every data point must be real.
- If a feature has no real data yet, show NOTHING.
- NEVER query inactive symbols from Databento. Only `is_active=true AND data_source='DATABENTO'`.
- Core historical retention starts at `2020-01-01T00:00:00Z`. Do not preserve, backfill, or train on pre-2020 core rows unless the user explicitly reopens that contract.

### Naming

- Table prefix: `mes_`, `cross_asset_`, `econ_`, `warbird_`
- NEVER use `bhg_`, `BHG`, `mkt_futures_`, or rabid-raccoon legacy naming
- All database columns: snake_case. No ORM mapping.

### Database

- Supabase client only. Service role for writes, anon for reads.
- SQL migrations in `supabase/migrations/`. No Prisma. No Drizzle.
- RLS on all tables. Admin client: `lib/supabase/admin.ts`
- Do not trust docs, status notes, prior agent claims, or `npm run build` as proof of schema truth.
- Before claiming any route, script, table, or view works, verify it against the actual database(s) with direct DB checks (`to_regclass`, `information_schema`, RPC/query checks, migration ledger checks) in the environment that matters.
- If local and cloud differ, say so explicitly. Do not collapse them into one “current state.”

### Scheduling

- All cron routes validate `CRON_SECRET` and log to `job_log`.
- All cron routes: `export const maxDuration = 60`
- Supabase pg_cron is the sole schedule producer. No recurring schedules outside `Supabase cron migration files`.
- Dead schedules must be removed by updating the corresponding `Supabase cron migration files` definitions.

### Production Boundary

- Local machines: training, calculations, research only.
- Production ingestion/crons/chart-serving must NOT depend on local machines.
- No continuous local runtime for live market data.

### Build & Deploy

- `npm run build` must pass before every push.
- No `/* */` block comments to disable code. Use `//` only.
- No `--no-verify` on git hooks.
- Push to repo → merge to main → deployment pipeline auto-deploys.

### Process

- One task at a time. Complete fully.
- Less complexity, fewer moving parts, better naming.
- NEVER refactor or "improve" code outside the current task.
- NEVER add or remove dependencies without asking.
- Before each phase or checkpoint, reread the active plan section that governs that work.
- Before proposing writer, schema, or training architecture, map every required fact to an exact plan line and an exact persisted home (`table.column`, view field, or explicitly named local research entity). If you cannot point to where a fact lives, mark it missing before proposing implementation.
- Do not collapse the contract into shorthand like "candidates + signals + outcomes" when the plan requires separate point-in-time setup truth, realized path truth, published signal lineage, and a distinct explanatory/research layer.
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

### Migration Discipline — Non-Negotiable

- **NEVER apply DDL to remote Supabase outside a migration file.** Every `execute_sql` that runs DDL creates ledger drift.
- If DDL was applied directly (MCP, psql, SQL editor), **immediately stamp the version into `supabase_migrations.schema_migrations`** and ensure a corresponding local migration file exists.
- Before running `supabase db push`, **verify the remote ledger matches local files** via `list_migrations` or `supabase db diff --linked`.
- When reconciling drift: audit EVERY object each migration should have created against the live DB. Do not assume "applied directly" — verify each one. Previous sessions incorrectly claimed 018-036 were all applied when 4 of them never ran.
- After any DDL change, run `get_advisors` (security type) to catch missing RLS or policy issues.


## MES Ingestion — Current State

**Primary (real-time):** `mes-1m` Edge Function, called every minute by Supabase pg_cron (`warbird_mes_1m_pull`). Connects to the **Databento Live API** (TCP gateway, `ohlcv-1s`, `MES.c.0` continuous contract, `stype_in=continuous`). Aggregates 1s → 1m, upserts `mes_1m`, rolls up touched 15m buckets into `mes_15m`. **Zero lag** — data arrives within the current minute.

**Fallback:** For gaps > 60 minutes, falls back to the Databento Historical API (`ohlcv-1m`). Historical API has ~10-15 min publication delay — used only for large catch-ups, never for live chart display.

**Hourly:** `mes-hourly` Edge Function pulls `ohlcv-1h` and `ohlcv-1d` directly from Databento Historical API (`MES.c.0`, `stype_in=continuous`). Rolls 1h → 4h locally (Databento has no `ohlcv-4h` schema). No application-level 1m→1h or 1h→1d aggregation.

**Symbology:** All MES Databento calls use `MES.c.0` (calendar front-month continuous) with `stype_in=continuous`. No manual contract-roll logic. The `contract-roll.ts` files are dead code.

**Retention floor:** `2020-01-01T00:00:00Z`.

**Databento schemas (Standard $179/mo):** ohlcv-1s, ohlcv-1m, ohlcv-1h, ohlcv-1d, definition, statistics. Currently using: ohlcv-1s (Live API for real-time), ohlcv-1m (Historical API fallback), ohlcv-1h, ohlcv-1d.
