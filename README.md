# Warbird Pro

Canonical Warbird v1 MES trading platform on Next.js, Supabase, Databento, Lightweight Charts, and an external-drive local PostgreSQL training warehouse.

**Live:** deployment URL managed in project operations docs  
**Repo:** [github.com/zincdigitalofmiami/warbird-pro](https://github.com/zincdigitalofmiami/warbird-pro)  
**Canonical docs index:** `docs/INDEX.md`
**Active plan:** `docs/MASTER_PLAN.md`

## Source Of Truth

Use these in order:

1. `docs/INDEX.md`
2. `docs/MASTER_PLAN.md`
3. `docs/contracts/README.md`
4. `docs/cloud_scope.md`
5. Live Supabase migrations in `supabase/migrations`
6. Active implementation code

Older plans, audits, checkpoints, and archived specs are not authoritative.

## Current Architecture

### Warbird v1

- Daily bias: macro directional shadow
- 4H structure: confirms or denies trend
- 15m fib-outcome engine: TP1_ONLY / TP2_HIT / STOPPED / REVERSAL classification (unresolved rows remain OPEN)
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
- The external-drive local PostgreSQL warehouse is the single canonical warehouse of record.
- Supabase is the strict runtime subset for ingress, dashboard/operator reads, packet distribution, and curated SHAP/report serving only.
- The external-drive local PostgreSQL warehouse holds deep history, features, labels, experiments, SHAP math, and AG artifacts.
- `/Volumes/Satechi Hub/warbird-pro/data/` is the external-drive raw/archive/artifact surface feeding the local warehouse; it is not GitHub-hosted data.
- Production ingestion, cron jobs, reconciliation, and chart-serving must not depend on local machines.
- Training-only data must not be maintained by daily/hourly cron pulls. Refresh training data by batch pull on retrain day unless the same dataset is needed for the frontend or live indicator/runtime path.
- If bar continuity is not provable, fib/model/setup logic is not safe.
- Retained core historical data starts at `2020-01-01T00:00:00Z`. Pre-2020 core rows are out of scope.

## Current Repo Reality

- Canonical schema is in place, but canonical writer cutover is still pending; the normalized `warbird_*` lifecycle tables exist in cloud and remain empty until the canonical writer lands.
- Active API surface exists at `app/api/warbird/signal`, `app/api/warbird/history`, `app/api/warbird/dashboard`, and `app/api/admin/status`, but the reader cutover is not complete yet.
- `mes-1m` is the primary MES data path — owned by Supabase pg_cron (`warbird_mes_1m_pull`). Edge Functions handle market-closed skips internally. No sidecar dependency.
- The active authority lives in `docs/INDEX.md`, `docs/MASTER_PLAN.md`, `docs/contracts/`, and `docs/cloud_scope.md`.

## Immediate Priorities

1. Keep docs aligned to canonical Warbird v1 and the current MES authority map.
2. Restore and verify hosted MES continuity for `mes_1m`, `mes_1h`, `mes_15m`, `mes_4h`, and `mes_1d`.
3. Fill missing support data needed for trigger and model validation.
4. Dry-test deterministic engine logic before spending time on training.
5. Train only after continuity and upstream data integrity are proven.

## Runtime Components

- App runtime: Next.js App Router (dashboard/API surface)
- Database: Supabase Postgres + Auth + Realtime + RLS
- Local training warehouse: external-drive PostgreSQL on the Satechi drive
- Live market data: Databento
- MES ingestion: Supabase pg_cron `warbird_mes_1m_pull` (every minute Sun-Fri) via Databento Live API, falls back to Historical API for gaps
- Historical backfill: [scripts/backfill.py](/Volumes/Satechi%20Hub/warbird-pro/scripts/backfill.py) (local research only; use explicit ranges, with retained core history `2020-01-01` forward)
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
