# Warbird-Pro — Agent Rules

Read this ENTIRE file before any work. No exceptions.

## Plan

Plan of record for the current architecture direction:
`/Volumes/Satechi Hub/warbird-pro/docs/plans/2026-03-17-warbird-simplification-handoff.md`

When the plan conflicts with `WARBIRD_CANONICAL.md`, the canonical spec wins.

## Stack

- Next.js (App Router) on Vercel
- Supabase (Postgres, Auth, Realtime, RLS) — NO Prisma, NO ORM
- Tailwind v4 + shadcn/ui (56 components)
- Lightweight Charts v5.1.0 (MES 15m candle chart)
- Recharts (dashboard card widgets)
- Vercel Cron Jobs (21 jobs, replaces Inngest + sidecar)

## Hard Rules

### Data — Zero Tolerance
- NEVER use mock, demo, placeholder, or fake data. Every data point must be real.
- If a feature has no real data yet, show NOTHING — not a placeholder.
- NEVER query inactive symbols from Databento. Only symbols with `is_active=true AND data_source='DATABENTO'` may be requested. Kirk got a massive bill from this.

### Naming — Clean Slate
- Table prefix: `mes_` for MES data, `cross_asset_` for non-MES, `econ_` for economic, `warbird_` for trading engine
- NEVER use `bhg_`, `BHG`, `mkt_futures_`, or any rabid-raccoon legacy naming
- All database columns: snake_case natively. No ORM mapping.
- Enum names: descriptive (`setup_phase`), not branded (`BhgPhase`)

### Database — Supabase Only
- Supabase client only. Service role key for backend writes, anon key for frontend reads.
- Supabase SQL migrations in `supabase/migrations/`. No Prisma. No Drizzle. No ORM.
- RLS enabled on all tables. Authenticated = SELECT. Service role bypasses automatically.
- Admin client: `lib/supabase/admin.ts` (uses `SUPABASE_SERVICE_ROLE_KEY`)

### Chart — TradingView Exact Match
- Lightweight Charts v5.1.0. Ported from rabid-raccoon with import path + naming fixes.
- Use `series.update()` for intrabar/realtime updates. NEVER `series.setData()` on each tick.
- `series.setData()` ONLY on initial snapshot load.
- Gap-free time mapping for session continuity (no weekend gaps).
- Colors: upColor `#26C6DA`, downColor `#FF0000`, white up wicks, gray down wicks, NO borders.
- Fib lines: NO text labels, NO axis labels. Clean colored horizontal lines only.
- Fib colors: white anchors (0, 1), 50% white retracements (.236, .382, .618, .786), orange pivot (.5), green targets (1.236, 1.618, 2.0).
- Chart at top of page, below header nav. Always.
- Autoscale fits CANDLE DATA to viewport. Drag axis to see targets.

### Scheduling — Vercel Cron
- Vercel Cron Jobs replace Inngest. No external orchestration service.
- All cron routes validate `CRON_SECRET` header.
- All cron routes log to `job_log` table.
- All cron routes: `export const maxDuration = 60`
- If a route is paused or under audit, remove it from `vercel.json`. Do not leave dead schedules live.

### Production Boundary
- Local machines are for training, heavy calculations, and research processing only.
- Production ingestion, cron jobs, data pulls, reconciliation, and chart-serving must not depend on local machines.
- No continuous local runtime for live market data or chart serving.
- Market-data completeness is a hard gate. If continuity is not provable, fib/model/setup logic must not be treated as safe.

### MES Data Ingestion
- `mes_1s` is the canonical continuity ingestion layer.
- `mes-catchup` Vercel Cron (every 5 min, Sun–Fri) is the production feed path.
- Uses Databento Historical API with explicit contract symbols (e.g. MESM6) to match TradingView roll timing.
- ohlcv-1m and ohlcv-1h are free schemas on the Standard plan — zero additional data cost.
- Supabase Realtime pushes DB changes to browser via WebSocket.
- 5-minute MAXIMUM acceptable latency (cron interval).

### MES Timeframe Authority
- `mes_1s` is canonical continuity data for ingestion integrity.
- `mes_1m` is trigger-resolution data (derived from `mes_1s` when available).
- `mes_15m` is the primary setup/model/chart timeframe (derived from stored `mes_1m`).
- `mes_1h` and `mes_4h` are optional context layers only.
- `mes_1d` may be direct-source data from Databento for macro context only.

### Build & Deploy
- ALWAYS run `npm run build` and confirm success before every `git push`.
- NEVER use `/* */` block comments to disable code. Use `//` line comments only.
- NEVER skip git hooks (`--no-verify`).

### Process
- Read this file and the plan BEFORE writing code.
- One task at a time. Complete fully before starting next.
- Less complexity, fewer moving parts, better naming.
- NEVER refactor, rename, or "improve" code outside the current task.
- NEVER add or remove dependencies without asking Kirk.

## File Structure

```
warbird-pro/
  app/
    api/
      cron/                 # 21 Vercel Cron job routes
        mes-catchup/        # Primary MES ingestion (every 5 min, Sun-Fri)
        cross-asset/        # Non-MES futures (hourly)
        fred/[category]/    # 10 FRED series (daily, staggered)
        detect-setups/      # Warbird setup engine (every 5 min, weekdays 12-21 UTC)
        score-trades/       # Trade scoring (every 15 min, weekdays)
        measured-moves/     # Daily measured moves (6pm weekdays)
        econ-calendar/      # Economic calendar (daily)
        news/               # News signals (daily)
        google-news/        # Google News RSS scraper (daily, weekdays)
        gpr/                # Geopolitical risk (daily)
        trump-effect/       # Federal Register + EPU (daily)
        forecast/           # ML inference (hourly, weekdays)
      live/
        mes15m/             # Chart initial snapshot API
      admin/
        status/             # System health check
      warbird/
        signal/             # Canonical WarbirdSignal v1 projection API
        history/            # Historical Warbird signal API
      pivots/mes/           # Pivot levels API
    auth/                   # Supabase Auth (login, signup, forgot-password)
    protected/              # Authenticated pages (dashboard, admin)
  components/
    charts/
      LiveMesChart.tsx      # Main MES 15m candle chart
      MesChartWrapper.tsx   # Chart container/loading wrapper
    dashboard/
      MarketSummaryCard.tsx
      ActiveSetupsCard.tsx
      SessionStatsCard.tsx
    ui/                     # 56 shadcn/ui components
  lib/
    charts/
      FibLinesPrimitive.ts        # 10 fib levels, canvas renderer
      ForecastTargetsPrimitive.ts # ML target zone overlay
      SetupMarkersPrimitive.ts    # Warbird setup markers
      PivotLinesPrimitive.ts      # Pivot levels (currently unused)
      blendTargets.ts             # Target blending logic
      ensureFutureWhitespace.ts   # Future whitespace bar management
      types.ts                    # Chart type definitions
    ingestion/
      databento.ts          # Databento Historical API client
      fred.ts               # FRED API client
    supabase/
      admin.ts              # Service role client (backend)
      client.ts             # Browser client
      server.ts             # Server component client
      proxy.ts              # Proxy configuration
    colors.ts               # TradingView color palette + fib colors
    fibonacci.ts            # Multi-period confluence fib engine
    market-hours.ts         # isMarketOpen(), isWeekendBar(), floorTo15m()
    setup-engine.ts         # Warbird setup state machine
    setup-candidates.ts     # Setup candidate evaluation
    pivots.ts               # Pivot calculation
    measured-move.ts        # Measured move detection
    swing-detection.ts      # Swing high/low detection
    event-display.ts        # Event display formatting
    types.ts                # Shared TypeScript types
    utils.ts                # General utilities
  scripts/
    live-feed.py            # DEPRECATED — replaced by mes-catchup Vercel Cron
    train-warbird.py        # AutoGluon training pipeline
    predict-warbird.py      # ML inference
    build-dataset.py        # Feature dataset builder
    backfill.py             # Historical data backfill
    warbird/
      build-warbird-dataset.ts # Canonical dataset builder
      train-warbird.py         # Canonical AutoGluon training
      predict-warbird.py       # Canonical Warbird inference writer
      fib-engine.ts            # 15m-primary fib geometry
      daily-layer.ts           # Daily bias layer
      structure-4h.ts          # 4H structure layer
      conviction-matrix.ts     # Conviction scoring
      garch-engine.py          # GARCH risk context
  supabase/
    migrations/             # 10 SQL migration files
      001_enums.sql         # 9 enums
      002_symbols.sql       # symbols, roles, mappings
      003_mes_data.sql      # mes_1m through mes_1d
      004_cross_asset.sql   # cross_asset_1h, cross_asset_1d, options
      005_econ.sql          # series_catalog + 10 econ domain tables
      006_news.sql          # news, calendar, GPR, trump_effect
      007_trading.sql       # pre-cutover trading tables
      008_rls.sql           # Row Level Security on all tables
      009_realtime.sql      # Realtime on live market/trading tables pre-cutover
      010_warbird_v1_cutover.sql # canonical Warbird v1 layered schema
    seed.sql                # 60 symbols, 31 FRED series, sources
```

## Key Decisions (from plan)

| Topic | Decision | Why |
|-------|----------|-----|
| DB access | Supabase only, no Prisma | Prisma Accelerate caused 5s timeout hell in rabid-raccoon |
| Migrations | Supabase SQL | Native Postgres, no ORM translation layer |
| Scheduling | Vercel Cron (21/100 used) | Replaces all Inngest functions. No external service. |
| Live data | mes_1s continuity + mes-catchup cron (5 min) → Supabase Realtime | No sidecar dependency. No continuous local-machine feed runtime. |
| Chart updates | `series.update()` via Realtime | Not `setData()` polling like rabid-raccoon |
| Mock data | NEVER | Every data point must be real. Period. |

## What NOT to Port from rabid-raccoon

- Prisma Accelerate 5s transaction timeout hacks
- `getDirectPool()` raw Postgres connections
- SSE boilerplate
- Inngest step/retry semantics
- "Owner path" telemetry system
- `mes-live-queries.ts` raw SQL helpers
- `isMainModule()` entry guard workaround
- `series.setData()` on every poll cycle
- `bhg_` / `BHG` naming anywhere
- Any mock, demo, or placeholder data
