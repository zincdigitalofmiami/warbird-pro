Read and follow AGENTS.md at the repository root.

## Quick Reference

- **Active architecture plan:** `/Volumes/Satechi Hub/warbird-pro/docs/plans/2026-03-20-ag-teaches-pine-architecture.md`
- **Live:** deployment URL managed in project operations docs
- **Repo:** github.com/zincdigitalofmiami/warbird-pro
- **DB:** Supabase cloud (check env vars, NOT Prisma)

## Current Status

### What Works
- MES chart pipeline end-to-end (Databento → cron → Supabase → Realtime → chart)
- Lightweight MES minute path: `/api/cron/mes-1m` pulls incremental `ohlcv-1m` and rolls up only touched 15m buckets
- Supabase-owned minute schedule support for MES via `supabase/migrations/20260326000015_mes_1m_supabase_cron.sql` (pg_cron + pg_net + vault secrets)
- Newsfilter primary + Finnhub secondary raw-news schema is now live in Supabase through `supabase/migrations/20260326000019_news_raw_extraction_and_scoring.sql`
- Supabase-owned Newsfilter/Finnhub cron wrappers are now live through `supabase/migrations/20260326000020_supabase_news_raw_cron.sql`, calling `/api/cron/newsfilter-news` and `/api/cron/finnhub-news`
- Live Vault route-url secrets now exist for the raw-news cron workers: `warbird_newsfilter_raw_cron_url` and `warbird_finnhub_raw_cron_url`
- Shared article-body extraction now exists at `lib/news/article-extractor.mjs` using `@mozilla/readability` + `jsdom`; Finnhub uses it for strict article-body capture and Newsfilter uses its official article-content API
- Repo-aligned `news_signals` polarity contract still exists: dedicated market-impact migration at `supabase/migrations/20260326000016_news_signal_direction.sql`, and dataset readers normalize legacy plus new values safely
- Warbird v1 8-table normalized schema (migration 010 + 011 + 012)
- Auth flow, API surface (/warbird/signal, /warbird/history, /live/mes15m, /pivots/mes)
- Live cloud now includes the raw-news schema/tables plus the Supabase cron wrappers for provider pulls; Google raw-news ingestion is removed from the active contract
- Required BigBeluga standalone harness now exists at `indicators/harnesses/bigbeluga-pivot-levels-harness.pine` with hidden `ml_pivot_*` exports staged for training capture
- Required LuxAlgo standalone harness now exists at `indicators/harnesses/luxalgo-msb-ob-probability-toolkit-harness.pine` with hidden `ml_msb_*` and `ml_ob_*` exports staged for training capture
- Required LuxAlgo Luminance standalone harness now exists at `indicators/harnesses/luxalgo-luminance-breakout-engine-harness.pine` with hidden `ml_luminance_*` exports staged for training capture
- `indicators/v6-warbird-complete.pine` is the only active Pine work surface; the paired strategy and parity guard are now legacy scratch/reference only and do not block indicator work
- The current Pine blocker is indicator-only: recover the active contract and operator-approved visuals in `indicators/v6-warbird-complete.pine` after the March 23 rollback plus the narrow `overlay=true` / no-visible-oscillator correction

### What Doesn't Work Yet
- mes_1s ingestion (table exists, nothing writes to it)
- Google News route/poller are restored as dormant research assets (not scheduled and not part of the active ingestion contract)
- Live Supabase Vault is still missing `warbird_newsfilter_api_key` and `warbird_finnhub_api_key`, so `public.run_newsfilter_raw_pull()` and `public.run_finnhub_raw_pull()` currently skip before provider fetch
- ML model training (target `scripts/ag/*` path not built yet)
- Python feature computation layer (not built yet)
- AG training pipeline (not built yet)
- Local PostgreSQL training warehouse application layer (DB now exists locally, but schema/scripts are not built)
- DB-side aggregation (all TypeScript, zero Postgres functions)
- Type generation (manual types, no supabase gen types)
- No active `pinescript-server`, TradingView chart MCP, or TradingView CLI is configured in the current Codex profile, so live-chart read / install / edit / deep-test flows described in older docs are not available from this terminal session
- Cloud publish-up tables for packet / SHAP / report lifecycle (not built)
- `scripts/warbird/fib-engine.ts` still reflects a legacy 1H helper path and is not the target point-in-time fib snapshot surface for AG training
- Legacy `/api/cron/forecast` + `warbird_forecasts_1h` path still exists and does not match the locked MES 15m fib-outcome contract
- `supabase/migrations/20260326000016_news_signal_direction.sql` still needs to be applied to the live database before `news_signals.direction` is guaranteed to accept the locked `BULLISH` / `BEARISH` contract in production

### Architecture Direction
Follow the active architecture plan only.

### Locked Rules
- 15m is the primary model/chart/setup timeframe.
- The canonical trade object is the MES 15m fib setup keyed by MES 15m bar close in `America/Chicago`.
- Any `1H` wording outside archived docs is legacy and must not drive new work.
- Pine is the canonical signal surface; the Next.js dashboard is the mirrored operator surface on the same contract, not a separate decision engine.
- Cloud Supabase is the production system of record; the local warehouse is explicit-snapshot training/research only.
- AG/offline training must consume point-in-time fib snapshots keyed to the MES 15m bar close; repaint-prone live chart reads are not acceptable dataset truth.
- Local machines are for training/calculations/research only.
- Production ingestion, crons, and chart-serving must not depend on local machines.
- No new predicted-price or `warbird_forecasts_1h`-style surfaces. Live model state is TP1/TP2/reversal outcome state on the MES 15m contract.
- `news_signals` is a derived `BULLISH` / `BEARISH` event-response surface that must be paired with price action before it can influence live logic.
- Pivot distance/state is a critical trigger and reversal input, but not the sole decision maker. Intermarket trigger quality must respect each symbol's correlative path with aligned 15m / 1H / 4H state.
- De-duplicate overlapping MA / trend / volume features across the admitted harnesses and base logic by feature family.
- Do not add more indicator settings, assets, or “zoo” modules ahead of training evidence. Build the minimal exportable core first, then let SHAP and feature-admission evidence decide what survives.
- Minimal Pine export surface for training capture: fib lines/state, pivot state/distance, and admitted indicator/harness outputs from the canonical indicator surface.
- TradingView enforces a hard maximum of 64 plot counts per script. Hidden `display.none` plots still count, so local parity or schema completeness never overrides the live plot budget.
- BigBeluga, `Market Structure Break & OB Probability Toolkit`, and `Luminance Breakout Engine` are required exact-copy harnesses. No hand-rolled substitutes.

## Documentation Discipline

After each locked phase or checkpoint:

1. Update the active plan with findings, validations, blockers, and the next blocking item.
2. Update `WARBIRD_MODEL_SPEC.md` if the model contract changed.
3. Update `AGENTS.md` if hard repo rules changed.
4. Update `CLAUDE.md` current status if the operational truth changed.
5. Update memory with the current contract, harness status, and blocker.

## Pine Script Verification Pipeline

Before committing ANY change to `indicators/*.pine`, run ALL of these in order:

```bash
./scripts/guards/pine-lint.sh          # Static analysis (errors block commit)
./scripts/guards/check-contamination.sh # Cross-project leak detection
npm run build                           # TypeScript build gate
```

For major Pine refactors, use the installed Pine skills plus the repo guard scripts below. Do not assume any additional Pine validation agent exists unless it is explicitly configured in the active Codex profile.

Only rely on Pine / TradingView MCP or CLI tooling after confirming it is actually configured in the active Codex profile. In the current profile, no `pinescript-server` or TradingView chart CLI/MCP is configured.

## Absolute Rules

1. NEVER mock data. Real or nothing.
2. NEVER query inactive Databento symbols.
3. NEVER use Prisma or any ORM.
4. `series.update()` for live ticks, `setData()` only on initial load.
5. `npm run build` must pass before every push.
6. `pine-lint.sh` must pass (0 errors) before every Pine commit.
7. One task at a time. Complete fully.
8. **NEVER hand-roll code when a working implementation exists.** Copy the exact working code. Adapt the interface (inputs/outputs), NOT the internals. If you can't explain why your version differs line-by-line from the reference, you don't understand it well enough to rewrite it. This applies to library integrations, API patterns, algorithm ports — everything.
