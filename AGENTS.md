# Warbird-Pro — Agent Rules

## Stack
- Next.js 16 (App Router) on Vercel
- Supabase (Postgres, Auth, Realtime, RLS) — NO Prisma
- Tailwind v4 + shadcn/ui (56 components)
- Lightweight Charts v5.1.0 (MES 15m candle chart)
- Recharts (dashboard card widgets)
- Python sidecar for Databento Live API → Supabase

## Hard Rules

### Data
- NEVER use mock, demo, placeholder, or fake data. Every data point must be real.
- If a feature has no real data yet, show nothing — not a placeholder.

### Naming
- Table prefix: `mes_` for MES data, `cross_asset_` for non-MES, `econ_` for economic, `warbird_` for trading engine
- NEVER use `bhg_`, `BHG`, or any rabid-raccoon legacy naming
- All database columns: snake_case natively. No ORM mapping.
- Enum names: descriptive (`setup_phase`), not branded (`BhgPhase`)

### Database
- Supabase client only. Service role key for backend writes.
- Supabase SQL migrations in `supabase/migrations/`. No Prisma.
- RLS enabled on all tables. Authenticated = SELECT. Service role = all ops.

### Chart
- Lightweight Charts v5.1.0. Port from rabid-raccoon with import path + naming fixes only.
- Use `series.update()` for intrabar/realtime updates. NEVER `series.setData()` on each tick.
- `series.setData()` only on initial snapshot load.
- Gap-free time mapping for session continuity (no weekend gaps).
- Colors: upColor #26C6DA, downColor #FF0000, white up wicks, gray down wicks, NO borders.
- Chart at top of page, below header nav. Always.

### Scheduling
- Vercel Cron Jobs replace Inngest. No external orchestration service.
- All cron routes validate `CRON_SECRET` header.
- All cron routes log to `job_log` table.

### Realtime
- Supabase Realtime pushes DB changes to browser via WebSocket.
- Python sidecar writes live Databento data to `mes_1m` → `mes_15m`.
- Vercel Cron is catch-up/gap-recovery only, not the primary data path.
- 1-minute MAXIMUM latency for MES data. This is intraday trading.

### Build & Deploy
- ALWAYS run `npm run build` and confirm success before every git push.
- NEVER use `/* */` block comments to disable code. Use `//` line comments.
- NEVER skip git hooks (`--no-verify`).

### Process
- Read docs thoroughly before writing code. Zero errors, zero typos.
- Less complexity, fewer moving parts, better naming.
- Research first, implement second.
- One task at a time. Complete fully before starting next.

## File Structure

```
warbird-pro/
  app/                    # Next.js App Router
    api/
      cron/               # Vercel Cron job routes
      live/               # Chart data API
      setups/             # Trading setup API
      pivots/             # Pivot level API
    auth/                 # Supabase Auth routes
    protected/            # Authenticated pages
  components/
    charts/               # LiveMesChart + chart components
    dashboard/            # Recharts card widgets
    ui/                   # shadcn/ui (56 components)
  lib/
    charts/               # Chart primitives + utilities
    ingestion/            # Databento + FRED clients
    supabase/             # Supabase client setup
    colors.ts             # TradingView color palette
    market-hours.ts       # Market session utilities
    setup-engine.ts       # Warbird setup state machine
    setup-candidates.ts   # Setup evaluation logic
    types.ts              # Shared TypeScript types
  scripts/
    live-feed.py          # Databento live sidecar
  supabase/
    migrations/           # SQL migration files
    seed.sql              # Reference data seed
```

## Plan Reference
Full implementation plan: `/Users/zincdigital/.claude/plans/gentle-giggling-mccarthy.md`
