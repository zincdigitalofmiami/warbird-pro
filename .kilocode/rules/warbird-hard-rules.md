# Warbird-Pro Hard Rules

These rules are NON-NEGOTIABLE. Violations break the project.

## Data — Zero Tolerance

- NEVER use mock, demo, placeholder, or fake data. Every data point must be real.
- If a feature has no real data yet, show NOTHING. Do not stub or simulate.
- NEVER query inactive symbols from Databento. Only `is_active=true AND data_source='DATABENTO'`.
- Research Databento docs/subscription/symbology BEFORE any API calls. Standard $179 tier only.

## Database

- There are exactly two databases in scope:
  - **Local `warbird`** on PG17 (`127.0.0.1:5432`) — canonical warehouse, training, artifacts, raw SHAP, diagnostics
  - **Cloud Supabase** (`qhwgrzqjcdtdqppvhhme`) — serving-only for frontend, indicator/runtime, packets, dashboard/admin read models, curated SHAP/report surfaces
- Supabase client for cloud. Service role for writes, anon for reads.
- No Prisma. No Drizzle. No ORM.
- Cloud DDL in `supabase/migrations/`. Local warehouse DDL in `local_warehouse/migrations/`.
- RLS on ALL cloud tables. Admin client: `lib/supabase/admin.ts`.
- Table prefix: `mes_`, `cross_asset_`, `econ_`, `warbird_`, `ag_`
- NEVER use `bhg_`, `BHG`, `mkt_futures_`, or rabid-raccoon legacy naming.
- All database columns: snake_case.
- Canonical names never use version suffixes.

## Scheduling / Crons

- All cron routes validate `CRON_SECRET` and log to `job_log`.
- All cron routes: `export const maxDuration = 60`
- Supabase pg_cron is the sole schedule producer for cloud ingestion.
- Dead schedules must be removed by updating the corresponding Supabase cron migration files.

## Production Boundary

- The local `warbird` PG17 warehouse is the canonical long-horizon warehouse. It holds the full data zoo, AG lineage tables and training view, raw SHAP, and all non-serving data.
- Cloud Supabase receives only published serving surfaces after manual promotion.
- Production ingestion/crons/chart-serving must NOT depend on local machines.
- No continuous local runtime for live market data.
- NEVER use a local Python sidecar for production MES ingestion.

## Build & Deploy

- `npm run build` must pass before every push.
- No `/* */` block comments to disable code. Use `//` only.
- No `--no-verify` on git hooks.
- Push to repo, merge to main, deployment pipeline auto-deploys.

## Architecture — v5 Reset Lock

- Cloud serves frontend/dashboard/admin read models and packet/runtime surfaces; cloud is serving-only and must not become a warehouse mirror.
- Pine is the canonical live generator surface for runtime chart/alert state.
- Python in `scripts/ag/` is the training generator and populates the local AG lineage contract.
- Packet promotion is manual: local training and SHAP complete first, then explicit publish-up.
- 15m is the primary model/chart/setup timeframe.
- The model is an entry gate (`TP1`-`TP5`/`STOPPED`/`REVERSAL` outcome state), not a predicted-price surface.
- First model target is multiclass `outcome_label`; first feature scope is `MES + cross-asset + macro`.
