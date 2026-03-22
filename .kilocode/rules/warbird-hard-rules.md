# Warbird-Pro Hard Rules

These rules are NON-NEGOTIABLE. Violations break the project.

## Data — Zero Tolerance

- NEVER use mock, demo, placeholder, or fake data. Every data point must be real.
- If a feature has no real data yet, show NOTHING. Do not stub or simulate.
- NEVER query inactive symbols from Databento. Only `is_active=true AND data_source='DATABENTO'`.
- Research Databento docs/subscription/symbology BEFORE any API calls. Standard $179 tier only.

## Database

- Supabase client ONLY. No Prisma. No Drizzle. No ORM.
- Service role for writes, anon for reads.
- SQL migrations in `supabase/migrations/`. Sequential numbering.
- RLS on ALL tables. Admin client: `lib/supabase/admin.ts`.
- Table prefix: `mes_`, `cross_asset_`, `econ_`, `warbird_`
- NEVER use `bhg_`, `BHG`, `mkt_futures_`, or rabid-raccoon legacy naming.
- All database columns: snake_case.

## Scheduling / Crons

- All cron routes validate `CRON_SECRET` and log to `job_log`.
- All cron routes: `export const maxDuration = 60`
- Dead schedules must be removed from `vercel.json`.
- Minimize Vercel function invocations — they run the bill up fast.

## Production Boundary

- Local machines: training, calculations, research ONLY.
- Production ingestion/crons/chart-serving must NOT depend on local machines.
- No continuous local runtime for live market data.
- NEVER use a local Python sidecar for production MES ingestion.

## Build & Deploy

- `npm run build` must pass before every push.
- No `/* */` block comments to disable code. Use `//` only.
- No `--no-verify` on git hooks.
- Push to repo, merge to main, Vercel auto-deploys. NEVER run `npx vercel --prod`.

## Architecture — TradingView First

- TradingView is the UI. No custom frontend.
- AutoGluon is the brain. AG trains offline, discovers rules/thresholds, bakes into Pine Script.
- Rabid Raccoon v2 is the indicator — pure display layer + alerts.
- 15m is the primary model/chart/setup timeframe.
- The model is an entry GATE (CLEAN/SURVIVED/STOPPED/REVERSAL), NOT a price predictor.
- Fibs/decision zones are training FEATURES, not signals.
- AG decides ALL correlations/weights/importance. No hand-coded logic.
