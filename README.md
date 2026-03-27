# Warbird Pro

Canonical Warbird v1 MES trading platform on Next.js, Supabase, Databento, and Lightweight Charts.

**Live:** deployment URL managed in project operations docs  
**Repo:** [github.com/zincdigitalofmiami/warbird-pro](https://github.com/zincdigitalofmiami/warbird-pro)  
**Active plan:** `docs/plans/2026-03-20-ag-teaches-pine-architecture.md`

## Source Of Truth

Use these in order:

1. `docs/plans/2026-03-20-ag-teaches-pine-architecture.md`
2. Live Supabase migrations in `supabase/migrations`
3. Active implementation code

Older plans, audits, checkpoints, and archived specs are not authoritative.

## Current Architecture

### Warbird v1

- Daily bias: macro directional shadow
- 4H structure: confirms or denies trend
- 15m fib-outcome engine: TP1_ONLY / TP2_HIT / STOPPED / REVERSAL / NO_TRADE classification
- 15m fib geometry: multi-period confluence with 5-window family (8/13/21/34/55)
- 15m trigger: oscillator extremes at fib zones with mechanical stop-loss (SL = -0.236 fib extension)

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
- Retained core historical data starts at `2024-01-01T00:00:00Z`. Anything earlier is out of scope for the canonical live/training dataset.

## Current Repo Reality

- Canonical cutover is in place: legacy `forecasts` is gone and Warbird v1 writes to normalized `warbird_*` tables.
- Active API surface is `app/api/warbird/signal` and `app/api/warbird/history`.
- `mes-1m` is the primary MES data path — called every minute by Supabase pg_cron (`warbird_mes_1m_pull`), no sidecar dependency.
- The repo still contains some stale legacy scaffolding and documentation from the pre-cutover build plan.

## Immediate Priorities

1. Keep docs aligned to canonical Warbird v1 and the current MES authority map.
2. Restore and verify hosted MES continuity for `mes_1m`, `mes_1h`, `mes_15m`, `mes_4h`, and `mes_1d`.
3. Fill missing support data needed for trigger and model validation.
4. Dry-test deterministic engine logic before spending time on training.
5. Train only after continuity and upstream data integrity are proven.

## Runtime Components

- App runtime: Next.js App Router (dashboard/API surface)
- Database: Supabase Postgres + Auth + Realtime + RLS
- Live market data: Databento
- MES ingestion: Supabase pg_cron `warbird_mes_1m_pull` (every minute, Sun–Fri) via Databento ohlcv-1m
- Historical backfill: [scripts/backfill.py](/Volumes/Satechi%20Hub/warbird-pro/scripts/backfill.py) (local research only, `2024-01-01` forward)
- Canonical Warbird engine: [scripts/warbird](/Volumes/Satechi%20Hub/warbird-pro/scripts/warbird)

## Local Development

```bash
npm install
npm run dev
```

### Required environment variables

```text
NEXT_PUBLIC_SUPABASE_URL
NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY
SUPABASE_SERVICE_ROLE_KEY
DATABENTO_API_KEY
FRED_API_KEY
CRON_SECRET
```

Optional tuning:

```text
WARBIRD_MIN_PROB_HIT_PT1_FIRST
WARBIRD_MIN_PROB_HIT_PT2_AFTER_PT1
WARBIRD_MAX_PROB_HIT_SL_FIRST
WARBIRD_MIN_SETUP_SCORE
CROSS_ASSET_SHARD_COUNT
```
