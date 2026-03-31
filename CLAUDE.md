Read and follow AGENTS.md at the repository root.

## Quick Reference

- **Active architecture plan:** `/Volumes/Satechi Hub/warbird-pro/docs/plans/2026-03-20-ag-teaches-pine-architecture.md`
- **Live:** deployment URL managed in project operations docs
- **Repo:** github.com/zincdigitalofmiami/warbird-pro
- **DB:** Supabase cloud (production) + local Supabase via Docker (training/dev). No Prisma.

## Current Status

### What Works
- MES chart pipeline end-to-end (Databento Live API → cron → Supabase → Realtime → chart)
- Real-time MES minute path: Edge Function `mes-1m` connects to Databento Live API (TCP gateway), streams `ohlcv-1s` for `MES.c.0` (continuous), aggregates 1s → 1m, upserts `mes_1m`, rolls up touched 15m buckets into `mes_15m`. Zero lag — data arrives within the current minute. Falls back to Historical API for gaps > 60 min.
- `mes-hourly` Edge Function pulls `ohlcv-1h` and `ohlcv-1d` directly from Databento Historical API (`MES.c.0`, `stype_in=continuous`). Rolls 1h → 4h locally (no ohlcv-4h schema). No 1m→1h or 1h→1d aggregation.
- All active recurring ingestion runs via Supabase pg_cron → Edge Functions (9 functions in `supabase/functions/`). `detect-setups` and `score-trades` still exist as App Router routes (`app/api/cron/`) but have no active Vercel cron schedule and no Edge Function port yet (plan step 5).
- `mes-1m`, `mes-hourly`, and `cross-asset` Edge Functions handle market-hours skips internally via `isMarketOpen()`. The Postgres SQL helper functions (`run_mes_1m_pull`, `run_mes_hourly_pull`, `run_cross_asset_pull`) are `net.http_*` dispatch wrappers only — no session-hour gating in SQL.
- Cross-asset pipeline: `cross-asset` Edge Function pulls `ohlcv-1h` from Databento Historical API for all active DATABENTO symbols (excl MES, .OPT). 4 shards fire hourly at `:05/:06/:07/:08` Sun-Fri (migration 040). All ~17 symbols updated within 4 minutes each open-market hour. Upserts `cross_asset_1h`, derives `cross_asset_1d`.
- All Databento calls use `.c.0` continuous front-month contracts with `stype_in=continuous`. No manual contract-roll logic. `contract-roll.ts` in `_shared/` is dead code. Databento handles rolls automatically.
- Live core retention floor is now locked to `2018-01-01T00:00:00Z` forward. Previous 2024 floor was lifted; backfill and training may use data back to 2018-01-01.
- GPR (Caldara-Iacoviello Geopolitical Risk Index) is backfill-only training data. Cron, helper function, and Vercel vault secret removed (migration 036 applied 2026-03-31). Data in `geopolitical_risk_1d` is populated by one-time local backfill and refreshed manually monthly.
- Executive Orders Edge Function (`supabase/functions/exec-orders/`) fetches Federal Register executive orders and memoranda. pg_cron schedule: daily 08:00 UTC Mon-Fri. No API key needed. Table: `executive_orders_1d` (renamed from `trump_effect_1d`, migration 043).
- `series_catalog` is now FK-enforced from all 10 `econ_*_1d` tables (migration 028)
- 22 new FRED macro series registered in `series_catalog` (migration 026): GDP, trade, government fiscal, prices, investment, expectations
- `T5YIE` and `T10YIE` breakeven inflation series reactivated
- Dead Vercel cron routes deleted: `mes-1m`, `cross-asset`, `mes-hourly`, `fred`, `massive/inflation`, `massive/inflation-expectations`, `trump-effect`, `forecast`, `measured-moves`, `mes-catchup`, `gpr`
- `detect-setups` and `score-trades` App Router cron routes still exist as legacy reference implementations (`app/api/cron/`). No Vercel cron schedule calls them. Not yet ported to Edge Functions (plan step 5). All active recurring ingestion scheduling is via Supabase pg_cron → Edge Functions.
- Unique constraints added on `econ_calendar(ts, event_name)` and `executive_orders_1d(ts, title)` to enforce upsert deduplication
- ESLint gate passes clean (`npm run lint` = 0 errors, 0 warnings). ESLint 9 native flat config with `_` prefix ignore pattern.
- Auth forms have proper `name`, `autoComplete`, `role="alert"`, `aria-live="polite"` attributes
- Marketing page aligned to MES 15m fib-outcome contract (no ML/forecasting references)
- `/admin` page works end-to-end: `get_admin_table_coverage()` RPC cleaned of dropped tables (`econ_news_1d`, `policy_news_1d`) and PL/pgSQL column-reference ambiguity fixed (migration 035). Applied directly to remote via `psql`.
- Warbird v1 8-table normalized schema (migration 010 + 011 + 012)
- Auth flow, API surface (/warbird/signal, /warbird/history, /warbird/dashboard, /live/mes15m, /pivots/mes)
- `indicators/v7-warbird-institutional.pine` is the active Pine work surface. Compiles clean, TV-validated. Output budget: 63/64 (60 plot + 3 alertcondition, 1 headroom). 11 `request.security()` calls of 40 budget. TA Core Pack exports (7 plots) are AG server-side computable — cut candidates if slots needed.
- v7 intermarket basket is **CME Globex LIVE**: **NQ**, **RTY**, **CL**, **HG**, **6E**, **6J** — all fetched at 60min via `request.security()`. 6J (JPY) INVERTED at state boundary (safe haven). ES chart-native vol (ATR ratio, range expansion, efficiency, VWAP) fills the VIX/VVIX gap. **Daily context** (SKEW via `CBOE:SKEW`, NYSE A/D via `USI:ADD`) are AG training features, NOT gate members.
- v7 regime: Leadership(NQ 25%) + Risk-appetite(RTY/CL/HG 40%) + Macro-FX(6E/6J-inv 15%) + Execution(VWAP/range/eff 20%) → 0-100 score with hysteresis (bull >65, bear <35, exit at 50). Persistence (confirmBars), cooldown, neutralize. Override (direct bull↔bear flip) only when leadership AND risk both extreme same direction. No unanimous gate, no decision model dropdown.
- `cross_asset_15m` table created (migration 039, RLS enabled). HG (Copper) added to symbols (migration 039 + 040). Backfill from 2018-01-01 for all 6 AG symbols via `scripts/backfill-intermarket-15m.py`.
- Intermarket Full Agreement Panel: NQ, RTY, CL, HG, 6E, 6J — 6 boxes from `cross_asset_1h` (Databento 1h, hourly cron). 6J inverted (JPY weakness = MES bullish). Background rule: all six +1 → green, all six -1 → red, otherwise transparent. Weighted IM Score badge: NQ 25%, RTY/CL/HG 13.33% each, 6E/6J 7.5% each. Shows `—` when no data.
- Cross-asset crons switched from nightly (02:00-02:30 UTC) to **hourly** — 4 shards at `:05/:06/:07/:08` past every hour, Sun-Fri (migration 040). All ~16 active Databento symbols updated within 4 minutes each hour.
- Chart container height locked to `80vh`.
- ES execution quality block: VWAP state/event (+2 reclaim, +1 above, 0 band, -1 below, -2 reject), range expansion (clamped, mintick-guarded), intrabar efficiency. Chart-native, zero security calls.
- 6 new ML exports: ml_vwap_code, ml_range_expansion, ml_efficiency, ml_agreement_velocity, ml_impulse_quality, ml_regime_score. Impulse quality is direction-relative (higher = better for THIS setup's direction).
- All signals gated by `barstate.isconfirmed` — bar close only, no mid-bar firing.
- v6 (`indicators/v6-warbird-complete.pine`) is legacy baseline, not active work surface.
- Three standalone harnesses retired (BigBeluga Pivot Levels, LuxAlgo MSB/OB, LuxAlgo Luminance) — zero downstream consumers
- The active architecture lock is now engine-first: `fib_engine_snapshot -> candidate -> outcome -> decision -> signal`, with TradingView kept execution-facing and the dashboard owning operator tables/mini charts from the same contract

### What Doesn't Work Yet
- mes_1s ingestion (table exists, nothing writes to it)
- Backfill scripts ready but **not yet executed**: `scripts/backfill-cross-asset.py` (1h/1d from 2024-01-01) and `scripts/backfill-intermarket-15m.py` (15m/1h/1d from 2018-01-01). Require local env vars `DATABENTO_API_KEY`, `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`. Can target local Supabase directly for training data.
- Ongoing 15m ingestion Edge Function not yet built — `cross_asset_15m` is backfill-populated only.
- Companion pane indicator not yet built (regime_score, impulse_quality, exhaustion_score, agreement_velocity — own 64-plot/40-call budget).
- `econ_inflation_1d` is still stale relative to the live schedule.
- FRED backfill script (`python scripts/backfill-fred.py`) needs to run AFTER migration 026 is applied to production to populate the 22 new series
- TradingEconomics free tier is untested — Kirk must set API key and run curl tests (Phase 4 manual step)
- ML model training (target `scripts/ag/*` path not built yet)
- Python feature computation layer (not built yet)
- AG training pipeline (not built yet)
- Local Supabase running via Docker on external drive. Same schema as production (43 migrations replay clean). Training data backfill scripts can target local directly. AG training workspace (`scripts/ag/*`) not built yet.
- DB-side aggregation (all TypeScript, zero Postgres functions)
- Type generation (manual types, no supabase gen types)
- No active `pinescript-server`, TradingView chart MCP, or TradingView CLI is configured in the current Codex profile, so live-chart read / install / edit / deep-test flows described in older docs are not available from this terminal session
- Canonical warbird tables (13 tables + 8 views) deployed to production via migrations 037+038 (applied 2026-03-31). All empty — no writers active yet. Writers (`detect-setups`, `score-trades`) must be ported to Edge Functions targeting these canonical tables.
- `detect-setups` and `score-trades` exist as App Router routes (`app/api/cron/`) but have no Vercel cron schedule and no pg_cron schedule. No Edge Function port exists yet. They are legacy reference implementations for the setup engine pipeline. Must be ported to Edge Functions writing to the canonical tables (plan step 5) before the setup engine is operational.
- Dashboard fib recompute was cut (commit `77ec03e`). `LiveMesChart.tsx` no longer calls the legacy fib-engine helper. Dashboard is not yet wired to canonical engine state — that's blocking order #4.
- `/admin` now reads candidates from `warbird_admin_candidate_rows_v` (canonical view from migration 038). Table shows all canonical fields: confidence_score, tp1/tp2 probability, reversal_risk, packet lineage. Empty until canonical writer (plan step 5) is deployed. Legacy warbird operational tables (`warbird_triggers_15m`, `warbird_conviction`, `warbird_setups`, `warbird_setup_events`, `warbird_risk`, `measured_moves`) still exist — still read by `/api/warbird/signal`, `/api/warbird/history`, `/api/warbird/dashboard`. Legacy table drop deferred to plan step 8.
- `scripts/warbird/fib-engine.ts` still reflects a legacy 1H helper path and is not the target point-in-time fib snapshot surface for AG training
- Migration ledger fully reconciled (2026-03-31). 43 migrations, 43 local files, zero drift. `supabase db reset` replays clean. `supabase db push` is safe.
- News infrastructure removed (migration 042): finnhub tables, news_signals matview, all_news_articles view, news types, news crons. Keeping: FRED, GPR, econ_calendar, executive_orders.
- 14 legacy tables dropped (migration 043): trade_scores, vol_states, models, sources, coverage_log, symbol_mappings, options_stats_1d, macro_reports_1d, 6x legacy backup tables.
- Security advisor: 0 code warnings. 1 WARN (auth password protection — dashboard setting).
- `/admin` data-quality issues visible: negative `econ_calendar` staleness (not related to migration 035 fix)

### Architecture Direction
Follow the active architecture plan only.

### Locked Rules
- 15m is the primary model/chart/setup timeframe.
- The canonical trade object is the MES 15m fib setup keyed by MES 15m bar close in `America/Chicago`.
- Any `1H` wording outside archived docs is legacy and must not drive new work.
- Pine is the canonical signal surface; the Next.js dashboard is the mirrored operator surface on the same contract, not a separate decision engine.
- The adaptive fib engine snapshot is the canonical base object. It is not a simple zigzag-only anchor path.
- The architecture hierarchy is now locked: objective -> candidate/outcome contract -> canonical schema -> research feature layer -> model stack -> deployment packet.
- Warbird is split into `Generator` (Pine with embedded TA core pack), `Selector` (offline models scoring frozen candidates), and `Diagnostician` (research explaining wins, losses, and improvement paths).
- Cloud Supabase is the production system of record; the local warehouse is explicit-snapshot training/research only.
- AG/offline training must consume point-in-time fib snapshots keyed to the MES 15m bar close; repaint-prone live chart reads are not acceptable dataset truth.
- Retained core historical data starts at `2018-01-01T00:00:00Z`. Pre-2018 core rows are out of scope.
- All MES Databento calls use `MES.c.0` (calendar front-month continuous) with `stype_in=continuous`. No manual contract-roll logic.
- Local machines are for training/calculations/research only.
- Production ingestion, crons, and chart-serving must not depend on local machines.
- No new predicted-price or `warbird_forecasts_1h`-style surfaces. Live model state is TP1/TP2/reversal outcome state on the MES 15m contract.
- `EXPIRED` / `NO_REACTION` are not canonical economic outcome labels for model truth. Unresolved rows remain `OPEN` until they resolve to `TP2_HIT` / `TP1_ONLY` / `STOPPED` / `REVERSAL`.
- Legacy `hit_*_first` / `prob_hit_*` names are scheduled for deletion. They must not appear in shared TypeScript types, active API responses, Admin/dashboard surfaces, packet payloads, or new schema work. No fallback aliases are permitted on new surfaces.
- The Admin page should render structured candidate rows, full training metrics, packet metrics, feature drivers, setting hypotheses, and AI-generated recommendations. Do not use Markdown report blobs as the dashboard contract.
- Decision vocabulary is `TAKE_TRADE`, `WAIT`, and `PASS`. Those are policy decisions, not realized trade outcomes.
- Pivot distance/state is a critical trigger and reversal input, but not the sole decision maker. AG training intermarket basket is 6 CME Globex futures (NQ, RTY, CL, HG, 6E, 6J) all available at 15m from Databento GLBX.MDP3. ES chart-native vol (ATR ratio, range expansion, efficiency, VWAP) covers the volatility signal. Daily VIX (FRED), SKEW, and NYSE A/D are daily-only context features, not gate members. AG decides correlations and weights from data.
- Do not add more indicator settings, assets, or “zoo” modules ahead of training evidence. Build the minimal exportable core first, then let SHAP and feature-admission evidence decide what survives.
- Minimal Pine export surface for training capture: fib lines/state, TA core pack (EMAs/MACD/RSI/ATR/ADX/volume family/OBV/MFI), intermarket state (NQ/RTY/CL/HG/6E/6J + daily VIX/SKEW/ADD), ES execution quality (VWAP/range/efficiency), regime score, agreement velocity, impulse quality, and event/regime state from the canonical indicator surface (`v7-warbird-institutional.pine`).
- TradingView enforces a hard maximum of 64 output calls per script. Hidden `display.none` plots AND `alertcondition()` calls both count toward the cap. Current v7 budget: 60 plot + 3 alertcondition = 63/64 (1 headroom). TA Core Pack exports (7 plots) are AG server-side computable — cut candidates if slots needed.
- TradingView keeps execution-facing visuals and alerts. Only 3 `alertcondition()` calls are kept: `WARBIRD ENTRY LONG`, `WARBIRD ENTRY SHORT`, and `PIVOT BREAK (against) + Regime Opposed` (the .50 reversal warning). All other alerts move to the dashboard. Dense operator tables, mini charts, and decision diagnostics belong on the dashboard, which must render the same stored engine state instead of recomputing fibs.
- The current blocking sequence is: ~~Pine indicator recovery~~ (DONE) -> ~~v7 institutional upgrade~~ (DONE, 64/64) -> ~~intermarket pivot to CME Globex~~ (DONE, 63/64, commit `6f3e7a6`) -> **fib engine hardening** (anchor span, waypoint lines) -> canonical writer cutover -> dashboard/admin reader cutover -> training workbench buildout -> legacy retirement.
- The 15-metric TA core pack is the canonical ML export surface. Do not re-introduce standalone third-party harnesses (BigBeluga, LuxAlgo MSB/OB, LuxAlgo Luminance are retired).

## Documentation Discipline

After each locked phase or checkpoint:

1. Update the active plan with findings, validations, blockers, and the next blocking item.
2. Update `WARBIRD_MODEL_SPEC.md` if the model contract changed.
3. Update `AGENTS.md` if hard repo rules changed.
4. Update `CLAUDE.md` current status if the operational truth changed.
5. Update memory with the current contract, TA pack status, and blocker.

## Pine Script Verification Pipeline

Before committing ANY change to `indicators/*.pine`, run ALL of these in order:

```bash
# 1. Real TradingView compiler — same as the web editor, returns line/column errors
pine_code=$(cat "indicators/<file>.pine")
curl -s -X POST "https://pine-facade.tradingview.com/pine-facade/translate_light?user_name=admin&v=3" \
  -H 'Referer: https://www.tradingview.com/' \
  -F "source=$pine_code" | python3 -c "
import json,sys; d=json.load(sys.stdin)
errs=d.get('result',{}).get('errors',[])
warns=d.get('result',{}).get('warnings',[])
print('success:',d.get('success'),'errors:',len(errs),'warnings:',len(warns))
[print('ERR:',e) for e in errs]; [print('WARN:',w) for w in warns]
"

# 2. Static analysis (errors block commit)
./scripts/guards/pine-lint.sh

# 3. Cross-project leak detection
./scripts/guards/check-contamination.sh

# 4. TypeScript build gate
npm run build
```

The pine-facade curl IS the authoritative compiler check. Run it first. `pine-lint.sh` catches budget/pattern issues the compiler doesn't flag. Both must pass.

For function signatures and syntax lookup, use the `pinescript-server` MCP if configured. What the compiler cannot do: load onto a live chart, show visual output, or run backtests — that's still manual in the TV editor.

## Absolute Rules

1. NEVER mock data. Real or nothing.
2. NEVER query inactive Databento symbols.
3. NEVER use Prisma or any ORM.
4. `series.update()` for live ticks, `setData()` only on initial load.
5. `npm run build` must pass before every push.
6. `pine-lint.sh` must pass (0 errors) before every Pine commit.
7. One task at a time. Complete fully.
8. **NEVER hand-roll code when a working implementation exists.** Copy the exact working code. Adapt the interface (inputs/outputs), NOT the internals. If you can't explain why your version differs line-by-line from the reference, you don't understand it well enough to rewrite it. This applies to library integrations, API patterns, algorithm ports — everything.
