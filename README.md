# Warbird Pro

Canonical Warbird v1 MES trading platform on Next.js, Supabase, Databento, and Lightweight Charts.

**Live:** [warbird-pro.vercel.app](https://warbird-pro.vercel.app)  
**Repo:** [github.com/zincdigitalofmiami/warbird-pro](https://github.com/zincdigitalofmiami/warbird-pro)  
**Canonical spec:** [WARBIRD_CANONICAL.md](/Volumes/Satechi%20Hub/warbird-pro/WARBIRD_CANONICAL.md)

## Source Of Truth

Use these in order:

1. [WARBIRD_CANONICAL.md](/Volumes/Satechi%20Hub/warbird-pro/WARBIRD_CANONICAL.md)
2. Live Supabase migrations in [supabase/migrations](/Volumes/Satechi%20Hub/warbird-pro/supabase/migrations)
3. Active Warbird routes and libs in `app/api/warbird/*` and `lib/warbird/*`

Older build-plan language is not authoritative where it conflicts.

## Current Architecture

### Warbird v1

- Daily bias: macro directional shadow
- 4H structure: confirms or denies trend
- 1H core forecaster: the only ML model in v1
- 1H fib geometry: the only fib-anchor timeframe
- 15M trigger: rule-based entry confirmation against 1H context

### MES Timeframe Authority

- `mes_1m`: direct from Databento
- `mes_1h`: direct from Databento
- `mes_1d`: direct from Databento for macro bias only
- `mes_15m`: derived from stored `mes_1m`
- `mes_4h`: derived from stored `mes_1h`

This is the intended steady-state authority map. Do not create multiple live writer paths for the same timeframe.

### Production Boundary

- Local machines are for training, heavy calculations, and research processing only.
- Production ingestion, cron jobs, reconciliation, and chart-serving must not depend on local machines.
- If bar continuity is not provable, fib/model/setup logic is not safe.

## Current Repo Reality

- Canonical cutover is in place: legacy `forecasts` is gone and Warbird v1 writes to normalized `warbird_*` tables.
- Active API surface is `app/api/warbird/signal` and `app/api/warbird/history`.
- `mes-catchup` Vercel Cron (every 5 min, Sun-Fri) is the primary MES data path — no sidecar dependency.
- The repo still contains some stale legacy scaffolding and documentation from the pre-cutover build plan.

## Immediate Priorities

1. Keep docs aligned to canonical Warbird v1 and the current MES authority map.
2. Restore and verify hosted MES continuity for `mes_1m`, `mes_1h`, `mes_15m`, `mes_4h`, and `mes_1d`.
3. Fill missing support data needed for trigger and model validation.
4. Dry-test deterministic engine logic before spending time on training.
5. Train only after continuity and upstream data integrity are proven.

## Runtime Components

- App runtime: Next.js App Router on Vercel
- Database: Supabase Postgres + Auth + Realtime + RLS
- Live market data: Databento
- MES ingestion: `mes-catchup` Vercel Cron (every 5 min) via Databento Historical API
- Historical backfill: [scripts/backfill.py](/Volumes/Satechi%20Hub/warbird-pro/scripts/backfill.py) (local research only)
- Canonical Warbird engine: [scripts/warbird](/Volumes/Satechi%20Hub/warbird-pro/scripts/warbird)

## Local Development

```bash
npm install
npm run dev
```

### Required environment variables

```text
NEXT_PUBLIC_SUPABASE_URL
NEXT_PUBLIC_SUPABASE_ANON_KEY
SUPABASE_SERVICE_ROLE_KEY
DATABENTO_API_KEY
FRED_API_KEY
CRON_SECRET
WARBIRD_FORECAST_WRITER_URL
WARBIRD_FORECAST_WRITER_TOKEN
```

Optional tuning:

```text
WARBIRD_MAX_FORECAST_AGE_MS
WARBIRD_FORECAST_WRITER_TIMEOUT_MS
WARBIRD_MIN_PROB_HIT_PT1_FIRST
WARBIRD_MIN_PROB_HIT_PT2_AFTER_PT1
WARBIRD_MAX_PROB_HIT_SL_FIRST
WARBIRD_MIN_SETUP_SCORE
CROSS_ASSET_SHARD_COUNT
```
