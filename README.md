# Warbird Pro

Real-time MES futures trading dashboard. Supabase + Next.js + Lightweight Charts.

**Live:** [warbird-pro.vercel.app](https://warbird-pro.vercel.app)
**Repo:** [github.com/zincdigitalofmiami/warbird-pro](https://github.com/zincdigitalofmiami/warbird-pro)
**Plan:** [`~/.claude/plans/gentle-giggling-mccarthy.md`](/Users/zincdigital/.claude/plans/gentle-giggling-mccarthy.md)

---

## Stack

| Layer | Tech |
|-------|------|
| Framework | Next.js (App Router) on Vercel |
| Database | Supabase (Postgres, Auth, Realtime, RLS) |
| UI | Tailwind v4, shadcn/ui (56 components) |
| Chart | Lightweight Charts v5.1.0 |
| Dashboard | Recharts |
| Live data | Python sidecar (Databento Live API) |
| Scheduling | Vercel Cron Jobs (20 jobs) |

## Architecture

```
Databento Live API (MES.c.0, GLBX.MDP3)
  -> Python sidecar (scripts/live-feed.py, ~60MB RAM)
    -> Supabase mes_1m + mes_15m (upsert)
      -> Supabase Realtime (WebSocket push)
        -> LiveMesChart series.update() (instant render)

Vercel Cron (every 5 min)
  -> Databento Historical API
    -> Fills gaps in mes_1m from sidecar downtime
```

End-to-end latency: < 2 seconds venue-to-chart.

## What's Done (Phases 1-4 partial)

### Phase 1 — Developer Tooling
- [x] GitHub repo, Vercel deployment
- [x] Supabase integration (17 env vars)
- [x] 56 shadcn/ui components
- [x] Tailwind v4, build passing
- [x] MCP servers: memory, sequentialthinking, shadcn, supabase
- [x] CLAUDE.md, AGENTS.md

### Phase 2 — Database
- [x] 9 SQL migrations (enums, symbols, MES data, cross-asset, econ, news, trading, RLS, realtime)
- [x] Admin client (`lib/supabase/admin.ts`)
- [x] Seed data: 60 symbols (34 active, 26 inactive), 31 FRED series, sources
- [x] RLS on all tables, Realtime on mes_1m/mes_15m/warbird_setups/forecasts

### Phase 3 — Chart Port
- [x] Lightweight Charts v5.1.0 installed
- [x] All chart library files ported (types, colors, primitives, fibonacci, pivots, etc.)
- [x] LiveMesChart.tsx with gap-free time mapping
- [x] FibLinesPrimitive: 10 levels (ZERO through TARGET 3), multi-period confluence scoring
- [x] Fib colors: white anchors, 50% white retracements, orange pivot, green targets
- [x] No text labels on fibs — clean lines only (matches TradingView)
- [x] Structural break locking (fib anchor persists until price breaks range)
- [x] Pivots removed from chart
- [x] SetupMarkersPrimitive ported (renamed from BhgMarkersPrimitive)
- [x] ForecastTargetsPrimitive ported
- [x] Chart data API (`/api/live/mes15m`)

### Phase 4 — MES Live Data (partial)
- [x] Python sidecar (`scripts/live-feed.py`) — streams Databento Live OHLCV-1m
- [x] Vercel Cron catch-up (`/api/cron/mes-catchup`) — 5-min gap fill
- [x] `lib/market-hours.ts` — isMarketOpen(), isWeekendBar()
- [x] `lib/ingestion/databento.ts` — Historical API client
- [ ] **Supabase Realtime subscription in chart** (chart still uses polling, not WebSocket push)
- [ ] **Sidecar reliability** (systemd/supervisor, auto-restart, health monitoring)

## What's Left

### Phase 4 — MES Live Data (remaining)
- [ ] Wire Supabase Realtime into LiveMesChart for instant `series.update()` on new rows
- [ ] Sidecar process management (systemd or supervisor, not tmux)
- [ ] Health check endpoint for sidecar status

### Phase 5 — Economic & News Data Pipelines
- [ ] 10 FRED cron routes (rates, yields, vol, inflation, fx, labor, activity, commodities, money, indexes)
- [ ] Cross-asset cron (non-MES futures from Databento)
- [ ] News signal cron
- [ ] Economic calendar cron
- [ ] GPR index cron
- [ ] Trump Effect cron (Federal Register + EPU)
- [ ] `lib/ingestion/fred.ts` — FRED API client

### Phase 6 — Signal Engine
- [ ] `/api/cron/detect-setups` — Warbird setup state machine (Touch -> Hook -> Go -> TP/SL)
- [ ] `/api/cron/measured-moves` — Daily measured move scan
- [ ] `/api/cron/score-trades` — Trade outcome scoring
- [ ] `lib/setup-engine.ts` — needs real data wiring (logic ported, not connected)
- [ ] Setup markers rendering on chart from live `warbird_setups` table
- [ ] Pivot lines restored (if desired) from separate data source

### Phase 7 — Dashboard Cards
- [ ] MarketSummaryCard — MES price, change%, sparkline
- [ ] ActiveSetupsCard — setup counts by phase
- [ ] SessionStatsCard — session high/low/range/volume
- [ ] ModelConfidenceCard — hidden until Phase 8

### Phase 8 — Model Integration (deferred)
- [ ] AutoGluon training pipeline (`scripts/train-warbird.py`)
- [ ] Inference cron (`/api/cron/forecast`)
- [ ] Dataset builder (`scripts/build-dataset.py`)
- [ ] ForecastTargetsPrimitive rendering live predictions

## Cron Jobs (20 total, Vercel Pro limit: 100)

| Schedule | Route | Purpose |
|----------|-------|---------|
| `*/5 * * * *` | `/api/cron/mes-catchup` | MES gap fill (backup) |
| `15 * * * *` | `/api/cron/cross-asset` | Non-MES futures |
| `0 5-14 * * *` | `/api/cron/fred/[category]` | 10 FRED series |
| `0 15 * * *` | `/api/cron/econ-calendar` | Econ calendar |
| `0 16 * * *` | `/api/cron/news` | News signals |
| `0 19 * * *` | `/api/cron/gpr` | Geopolitical risk |
| `30 19 * * *` | `/api/cron/trump-effect` | Federal Register + EPU |
| `3,18,33,48 * * * 1-5` | `/api/cron/detect-setups` | Setup detection |
| `0 18 * * 1-5` | `/api/cron/measured-moves` | Measured moves |
| `10,25,40,55 * * * 1-5` | `/api/cron/score-trades` | Trade scoring |
| `30 * * * 1-5` | `/api/cron/forecast` | ML inference |

## Database (9 migrations)

**MES:** `mes_1m`, `mes_15m`, `mes_1h`, `mes_4h`, `mes_1d`
**Cross-asset:** `cross_asset_1h`, `cross_asset_1d`, `options_stats_1d`, `options_ohlcv_1d`
**Economic:** 10 domain tables (rates, yields, vol, inflation, fx, labor, activity, commodities, money, indexes)
**News:** `econ_news_1d`, `policy_news_1d`, `macro_reports_1d`, `econ_calendar`, `news_signals`, `geopolitical_risk_1d`, `trump_effect_1d`
**Trading:** `warbird_setups`, `trade_scores`, `measured_moves`, `vol_states`, `forecasts`
**Meta:** `symbols`, `sources`, `series_catalog`, `models`, `coverage_log`, `job_log`

## Local Development

```bash
npm install
npm run dev          # Next.js on :3000
```

### Live feed sidecar (requires Databento subscription)
```bash
pip install databento supabase
python scripts/live-feed.py
```

### Environment variables
```
NEXT_PUBLIC_SUPABASE_URL
NEXT_PUBLIC_SUPABASE_ANON_KEY
SUPABASE_SERVICE_ROLE_KEY
DATABENTO_API_KEY
FRED_API_KEY
CRON_SECRET
```
