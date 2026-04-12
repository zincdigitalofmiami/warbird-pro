# Warbird-Pro — Agent Rules

Read this file before any work.

## Agent Bootstrap

Use this root `AGENTS.md` as the workspace instruction surface. Do not add a competing `.github/copilot-instructions.md` unless this file is intentionally retired.

### Read Order

- Start here: `AGENTS.md`
- Canonical docs index: `docs/INDEX.md`
- Then follow `docs/INDEX.md` read order exactly:
  - `docs/MASTER_PLAN.md`
  - `docs/contracts/README.md`
  - `docs/contracts/ag_local_training_schema.md`
  - `docs/runbooks/README.md`
  - `docs/contracts/schema_migration_policy.md`
  - `docs/cloud_scope.md`
  - `WARBIRD_MODEL_SPEC.md`
  - `CLAUDE.md`
  - `docs/agent-safety-gates.md`
  - `Powerdrill/reports/2026-04-06-powerdrill-findings.md`

### PowerDrill MCP

- Tracked `/.mcp.json` is the shared non-secret MCP bootstrap only (`memory`, `sequentialthinking`, `pinescript-server`, `tradingview`).
- PowerDrill secret remote config must stay out of tracked files. Kilo uses gitignored `/.kilo/kilo.json`.
- For Claude Code / Cursor after clone, add the PowerDrill MCP entry only to the local untracked `.mcp.json`. Do not commit PowerDrill keys or remote URLs with embedded secrets.
- When PowerDrill-grounded work is requested, use the PowerDrill memorylake first. Treat that memorylake as the PowerDrill retrieval surface before relying on summarized repo notes.

### Default Preflight

- Check repo state with `git status --short` before edits.
- Use `rg --files` and `rg -n` to scope the touched surface before changing code.
- Treat the local `warbird` PG17 warehouse and cloud Supabase as separate databases. Never collapse them.
- Never trust prior agent claims, stale docs, or build success as proof of schema truth.

### Default Verification

- `npm run build` is the baseline gate before every push.
- `npm run lint` is the standard lint gate for TypeScript and Next.js work.
- If any `.pine` file is touched, run the full Pine verification flow in `CLAUDE.md` and `docs/agent-safety-gates.md`.

### Repo Map

- `app/` and `components/`: Next.js App Router runtime and UI.
- `supabase/functions/`: active ingestion and cron-owned Edge Functions.
- `supabase/migrations/`: cloud-serving DDL only. No local warehouse DDL here.
- `local_warehouse/migrations/`: local-only DDL and migration ledger management for the canonical `warbird` PG17 warehouse.
- `scripts/ag/`: Python warehouse build, feature engineering, training, SHAP, publish-up.
- `data/`: raw Databento archives, parquet inputs, HG source files.
- `artifacts/`: append-only model outputs, reports, SHAP artifacts. Raw SHAP in `artifacts/shap/{run_id}/`.
- `lib/`: shared market, setup, chart, and Supabase utilities.
- `indicators/v7-warbird-institutional.pine`: active Pine work surface.
- `docs/MASTER_PLAN.md`, `docs/contracts/`, and `docs/cloud_scope.md`: active architecture, interfaces, and cloud-scope authority.
- `docs/research/`: tracked research baselines and current-state audits that remain referenced by the canonical docs index.

### Common Gotchas

- The canonical contract is MES 15m fib setups keyed to the MES 15m bar-close in `America/Chicago`.
- Pine is the canonical live signal surface; the dashboard mirrors stored engine state and is not a separate decision engine.
- The local `warbird` database on PG17 (`127.0.0.1:5432`) is the canonical warehouse truth. It owns the full data zoo: market history, AG lineage tables, the canonical training view, features, labels, SHAP artifacts, and all non-serving data.
- Supabase (`qhwgrzqjcdtdqppvhhme`) is the reduced cloud serving database for frontend, TradingView/indicator support, packet distribution, curated SHAP/admin reports, and other explicitly plan-approved published surfaces. It must not become a mirror of local.
- `rabid_raccoon` is a bootstrap-only legacy input on the same PG instance. After the one-time bootstrap into `warbird`, it is reference-only and must not be treated as canonical again.
- Canonical AG contract is **three canonical local AG tables and one canonical training view.** No version suffixes are allowed on canonical names.
- Exact local AG schema authority: `docs/contracts/ag_local_training_schema.md`.
- No mock data, no inactive Databento symbols, no Prisma/ORM paths, and no hidden third-database dependency outside the local warehouse and cloud Supabase.
- Cloud promotion is manual. Local training and SHAP must complete first; publish-up happens only after explicit approval.

## Active Plan

There is exactly one active architecture plan and one active documentation entrypoint:

- `docs/INDEX.md`
- `docs/MASTER_PLAN.md` — Warbird Full Reset Plan v5

Everything else is archived or reference-only and should not drive current implementation unless explicitly reopened through the index.

## Contract First

- The canonical trade object is the **MES 15m fib setup**.
- The canonical key is the MES 15m bar-close timestamp in `America/Chicago`.
- Any remaining `1H` wording in old docs, specs, scripts, or comments is legacy and must not drive new work.
- Pine is the canonical **live generator** (signal surface). The Next.js dashboard is the mirrored operator surface on the same contract, not a separate decision engine.
- The **training generator** is the Python reconstruction pipeline in `scripts/ag/`. It reconstructs fib snapshots, generates interactions, labels forward outcomes, and populates the three canonical local AG tables. `ag_training` is a canonical view over those tables.
- Canonical AG contract is **three canonical local AG tables and one canonical training view.**
- The three canonical local AG tables are:
  - `ag_fib_snapshots` — frozen fib engine state at bar close
  - `ag_fib_interactions` — candidate setups from fib-price interactions
  - `ag_fib_outcomes` — realized forward path outcomes per interaction
- The canonical training view is:
  - `ag_training` — canonical flat join of the three tables with `WHERE outcome_label != 'CENSORED'`
- Canonical names never use version suffixes.
- Live model outputs are TP1/TP2/reversal outcome state for the MES 15m fib setup, not predicted-price forecasts.
- `news_signals` and all news/options surfaces are retired from the active contract. Do not build new schema, writer logic, dashboard logic, or training assumptions around them unless the user explicitly reopens it.
- AutoGluon is offline only and may only promote Pine-ready packet outputs.
- First model target is locked to multiclass `outcome_label`.
- First feature scope is locked to `MES + cross-asset + macro`.
- Macro scope is locked to `FRED + econ_calendar` only. No news or narrative sources.

## Stack

- Next.js (App Router) — frontend dashboard and route handlers only (frontend is TradingView)
- Supabase (Postgres, Auth, Realtime, RLS, pg_cron) — cloud serving only, NO Prisma, NO ORM
- Local PG17 `warbird` database — canonical warehouse, training, SHAP, artifacts
- AutoGluon (local Python) — entry gate model, offline only
- TradingView + Rabid Raccoon v2 Pine Script — all visualization
- Supabase pg_cron — sole scheduling and recurring function producer for cloud ingestion

## Hard Rules

### Data — Zero Tolerance

- NEVER use mock, demo, placeholder, or fake data. Every data point must be real.
- If a feature has no real data yet, show NOTHING.
- NEVER query inactive symbols from Databento. Only `is_active=true AND data_source='DATABENTO'`.
- Core historical retention starts at `2020-01-01T00:00:00Z`. Do not preserve, backfill, or train on pre-2020 core rows unless the user explicitly reopens that contract.

### Naming

- Table prefix: `mes_`, `cross_asset_`, `econ_`, `warbird_`, `ag_`
- NEVER use `bhg_`, `BHG`, `mkt_futures_`, or rabid-raccoon legacy naming
- All database columns: snake_case. No ORM mapping.
- Canonical names never use version suffixes.

### Database

- There are exactly two databases in scope:
  - **Local `warbird`** on PG17 (`127.0.0.1:5432`) — canonical warehouse, training, artifacts, raw SHAP, diagnostics
  - **Cloud Supabase** (`qhwgrzqjcdtdqppvhhme`) — serving-only for frontend, indicator/runtime, packets, dashboard/admin read models, curated SHAP/report surfaces
- Local warehouse DDL lives in `local_warehouse/migrations/` with its own `local_schema_migrations` ledger. Not in `supabase/migrations/`.
- Cloud DDL lives in `supabase/migrations/` only.
- Supabase client for cloud. Service role for writes, anon for reads.
- RLS on all cloud tables. Admin client: `lib/supabase/admin.ts`
- No Prisma. No Drizzle. No ORM.
- `rabid_raccoon` is bootstrap-only. After the one-time import into `warbird`, it is legacy reference only.
- Any cloud table that does not serve frontend, indicator/runtime, packet distribution, curated SHAP/admin reports, or another explicitly locked plan surface is retirement debt and should be removed.
- Do not trust docs, status notes, prior agent claims, or `npm run build` as proof of schema truth.
- Before claiming any route, script, table, or view works, verify it against the actual database(s) with direct DB checks (`to_regclass`, `information_schema`, RPC/query checks, migration ledger checks) in the environment that matters.
- If local and cloud differ, say so explicitly. Do not collapse them into one "current state."

### Removed from Canonical Local Build

These are explicitly excluded from the canonical `warbird` warehouse:

- `mes_1m`
- `cross_asset_1d`
- all news surfaces
- all options surfaces
- all legacy setup/trade/news tables (`warbird_setups`, `scored_trades`, `news_signals`, `econ_news_1d`, `policy_news_1d`)

### Scheduling

- All cron routes validate `CRON_SECRET` and log to `job_log`.
- All cron routes: `export const maxDuration = 60`
- Supabase pg_cron is the sole schedule producer for cloud ingestion. No recurring schedules outside `Supabase cron migration files`.
- Dead schedules must be removed by updating the corresponding `Supabase cron migration files` definitions.

### Pine Indicator — Zero Tolerance

- NEVER edit `indicators/v7-warbird-institutional.pine` without explicit approval
  in the current session. State intent, wait for approval, then edit.
- NEVER push Pine changes to TradingView Pine Editor without explicit approval.
- Pine budget baselines (`v7-warbird-institutional.pine`):
  Plot budget: 37 / 64 (33 plot + 1 plotshape + 3 alertcondition; strategy: 34/64)
  Request budget: 4 / 40
  Any implementation must be priced against these baselines before code is written.
- `request.footprint()` must be treated as a tightly budgeted call path.
  All footprint-derived features must be computed from one cached object per bar.
- Pine verification pipeline is mandatory before every Pine commit:
  1. pine-facade curl compiler check (authoritative compiler, run first)
  2. pine-lint.sh (0 errors required, errors block commit)
  3. check-contamination.sh
  4. npm run build
     All four must pass. STATUS: INCOMPLETE if any fail.
- Indicator data capture is automated via Pine alert -> webhook -> Supabase.
  Do not use manual TV CSV export as an ongoing process.
  Manual export is one-time historical seed only.

### Backtest and Execution Minimums

- Commission floor for MES backtesting: $1.00/side minimum.
- Slippage floor: 1 tick minimum. 2 ticks recommended.
- IS/OOS walk-forward splits: minimum one-session embargo between training
  window end and test window start. Not optional.
- Hard stop requirement: structural stop at `0.618 x ATR(14)` from entry.
  Emergency stop at `1.000 x ATR(14)`. Both rendered on chart from entry bar.
- Consecutive loss block: at 2 consecutive losses, signal warning. At 3, halt
  recommended. Prevent revenge re-entry clusters.
- Opening bar suppressor: no new entry signals during 9:30-9:44 ET.

### Production Boundary

- The local `warbird` PG17 warehouse is the canonical long-horizon warehouse. It holds the full data zoo, AG lineage tables and training view, raw SHAP, and all non-serving data.
- Cloud Supabase receives only published serving surfaces after manual promotion.
- Cloud never receives: `ag_fib_snapshots`, `ag_fib_interactions`, `ag_fib_outcomes`, `ag_training`, raw features, raw labels, raw SHAP matrices, raw SHAP interaction matrices.
- Cloud frontend, indicator/runtime, and admin surfaces may read only the reduced Supabase surfaces explicitly published there.
- No local Supabase, no Docker-local runtime DB, and no third database.

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
- When reconciling drift: audit EVERY object each migration should have created against the live DB. Do not assume "applied directly" — verify each one.
- After any DDL change, run `get_advisors` (security type) to catch missing RLS or policy issues.
- Local warehouse migrations use `local_warehouse/migrations/` with the `local_schema_migrations` ledger. These never go through Supabase CLI.

## MES Ingestion — Current State

**Primary (real-time):** `mes-1m` Edge Function, called every minute by Supabase pg_cron (`warbird_mes_1m_pull`). Connects to the **Databento Live API** (TCP gateway, `ohlcv-1s`, `MES.c.0` continuous contract, `stype_in=continuous`). Aggregates 1s → 1m, upserts `mes_1m`, rolls up touched 15m buckets into `mes_15m`. **Zero lag** — data arrives within the current minute.

**Fallback:** For gaps > 60 minutes, falls back to the Databento Historical API (`ohlcv-1m`). Historical API has ~10-15 min publication delay — used only for large catch-ups, never for live chart display.

**Hourly:** `mes-hourly` Edge Function pulls `ohlcv-1h` and `ohlcv-1d` directly from Databento Historical API (`MES.c.0`, `stype_in=continuous`). Rolls 1h → 4h locally (Databento has no `ohlcv-4h` schema). No application-level 1m→1h or 1h→1d aggregation.

**Symbology:** All MES Databento calls use `MES.c.0` (calendar front-month continuous) with `stype_in=continuous`. No manual contract-roll logic. The `contract-roll.ts` files are dead code.

**Retention floor:** `2020-01-01T00:00:00Z`.

**Databento schemas (Standard $179/mo):** ohlcv-1s, ohlcv-1m, ohlcv-1h, ohlcv-1d, definition, statistics. Currently using: ohlcv-1s (Live API for real-time), ohlcv-1m (Historical API fallback), ohlcv-1h, ohlcv-1d.

**Note:** This ingestion feeds cloud Supabase for live chart serving. The local `warbird` warehouse bootstraps its MES data from `rabid_raccoon` (one-time) and does not depend on cloud ingestion for canonical training truth.
