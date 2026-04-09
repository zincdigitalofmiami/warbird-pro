Read and follow AGENTS.md at the repository root.

## Quick Reference

- **Canonical docs index:** `/Volumes/Satechi Hub/warbird-pro/docs/INDEX.md`
- **Active architecture plan:** `/Volumes/Satechi Hub/warbird-pro/docs/MASTER_PLAN.md`
- **Interface authority:** `/Volumes/Satechi Hub/warbird-pro/docs/contracts/README.md`
- **Cloud whitelist:** `/Volumes/Satechi Hub/warbird-pro/docs/cloud_scope.md`
- **PowerDrill research baseline:** `Powerdrill/reports/2026-04-06-powerdrill-findings.md`
- **PowerDrill MCP access:** shared tracked `/.mcp.json` keeps only non-secret MCP servers; Kilo uses gitignored `/.kilo/kilo.json` for the PowerDrill remote entry; Claude Code / Cursor users add PowerDrill to local untracked `.mcp.json` after clone
- **Live:** deployment URL managed in project operations docs
- **Repo:** github.com/zincdigitalofmiami/warbird-pro
- **DB:** The external-drive local PostgreSQL warehouse is the single canonical database truth. Cloud Supabase is the strict runtime subset for ingress, frontend and operator read models, packet distribution, and curated SHAP/report serving. `/Volumes/Satechi Hub/warbird-pro/data/` remains the raw/archive companion surface. No Prisma.

## Current Status

### What Works
- MES chart pipeline end-to-end (Databento Live API → cron → Supabase → Realtime → chart)
- Real-time MES minute path: Edge Function `mes-1m` connects to Databento Live API (TCP gateway), streams `ohlcv-1s` for `MES.c.0` (continuous), aggregates 1s → 1m, upserts `mes_1m`, rolls up touched 15m buckets into `mes_15m`. Zero lag — data arrives within the current minute. Falls back to Historical API for gaps > 60 min.
- Current tree hardening: `mes-1m` now keys incremental pulls to the last fully closed 1m boundary and filters out the in-progress current minute before persistence. This removes the alternating `SUCCESS` / `SKIPPED no_gap` churn seen when partial current-minute bars were written and the next cron found no real closed-minute gap. This repo change is validated by `npm run build`; a direct `deno check` could not be run in this shell because `deno` is unavailable.
- `mes-hourly` Edge Function pulls `ohlcv-1h` and `ohlcv-1d` directly from Databento Historical API (`MES.c.0`, `stype_in=continuous`). Rolls 1h → 4h locally (no ohlcv-4h schema). No 1m→1h or 1h→1d aggregation.
- All active recurring ingestion runs via Supabase pg_cron → Edge Functions (9 functions in `supabase/functions/`). `detect-setups` and `score-trades` still exist as App Router routes (`app/api/cron/`) but have no active Vercel cron schedule and no Edge Function port yet (plan step 5).
- `mes-1m`, `mes-hourly`, and `cross-asset` Edge Functions handle market-hours skips internally via `isMarketOpen()`. The Postgres SQL helper functions (`run_mes_1m_pull`, `run_mes_hourly_pull`, `run_cross_asset_pull`) are `net.http_*` dispatch wrappers only — no session-hour gating in SQL.
- Cross-asset pipeline: `cross-asset` Edge Function pulls `ohlcv-1h` from Databento Historical API for all active DATABENTO symbols (excl MES, .OPT). 4 shards fire hourly at `:05/:06/:07/:08` Sun-Fri (migration 040). All ~17 symbols updated within 4 minutes each open-market hour. Upserts `cross_asset_1h`, derives `cross_asset_1d`.
- All Databento calls use `.c.0` continuous front-month contracts with `stype_in=continuous`. No manual contract-roll logic. `contract-roll.ts` in `_shared/` is dead code. Databento handles rolls automatically.
- Live core retention floor is now locked to `2020-01-01T00:00:00Z` forward. Previous 2024 floor was lifted, then narrowed to 2020-01-01 (5-year training window); backfill and training may use data back to 2020-01-01.
- GPR (Caldara-Iacoviello Geopolitical Risk Index) is backfill-only training data. Cron, helper function, and Vercel vault secret removed (migration 036 applied 2026-03-31). Data in `geopolitical_risk_1d` is populated by one-time local backfill and refreshed manually monthly.
- Executive Orders Edge Function (`supabase/functions/exec-orders/`) fetches Federal Register executive orders and memoranda. pg_cron schedule: daily 08:00 UTC Mon-Fri. No API key needed. Table: `executive_orders_1d` (renamed from `trump_effect_1d`, migration 043).
- `series_catalog` is now FK-enforced from all 10 `econ_*_1d` tables (migration 028)
- 22 new FRED macro series registered in `series_catalog` (migration 026): GDP, trade, government fiscal, prices, investment, expectations
- `T5YIE` and `T10YIE` breakeven inflation series reactivated
- Dead Vercel cron routes deleted: `mes-1m`, `cross-asset`, `mes-hourly`, `fred`, `massive/inflation`, `massive/inflation-expectations`, `trump-effect`, `forecast`, `measured-moves`, `mes-catchup`, `gpr`
- `detect-setups` and `score-trades` App Router cron routes still exist as legacy reference implementations (`app/api/cron/`). No Vercel cron schedule calls them. Not yet ported to Edge Functions (plan step 5). All active recurring ingestion scheduling is via Supabase pg_cron → Edge Functions.
- Migration reconciliation checkpoint locked: `supabase/migrations/20260331000045_drop_legacy_warbird_tables.sql` has been restored from the recovered Codex session log, local replay via `supabase db reset` validated cleanly through `20260331000045`, the 9 dropped legacy objects are absent after replay, the canonical admin/candidate tables and views still exist, and `supabase migration list` is aligned local↔remote through `045`.
- Unique constraints added on `econ_calendar(ts, event_name)` and `executive_orders_1d(ts, title)` to enforce upsert deduplication
- ESLint gate passes clean (`npm run lint` = 0 errors, 0 warnings). ESLint 9 native flat config with `_` prefix ignore pattern.
- Auth forms have proper `name`, `autoComplete`, `role="alert"`, `aria-live="polite"` attributes
- Marketing page aligned to MES 15m fib-outcome contract (no ML/forecasting references)
- `/admin` page works end-to-end: `get_admin_table_coverage()` RPC cleaned of dropped tables (`econ_news_1d`, `policy_news_1d`) and PL/pgSQL column-reference ambiguity fixed (migration 035). Applied directly to remote via `psql`.
- Warbird v1 8-table normalized schema (migration 010 + 011 + 012)
- Auth flow, API surface (/warbird/signal, /warbird/history, /warbird/dashboard, /live/mes15m, /pivots/mes)
- `indicators/v7-warbird-institutional.pine` is the active Pine work surface. Compiles clean, TV-validated. Output budget: 35/64 (32 plot + 3 alertcondition, 29 headroom). 4 `request.security()` calls of 40 budget. Pine owns only fib-engine-exclusive outputs; all server-side-computable features (TA core pack, EMA dist, RVOL, exhaustion, range expansion, efficiency, event_day) and constant-stub IM states are AG-owned and not exported from Pine. Fib engine hardened (commit `4a25806`): direction logic uses ZigZag swing-sequence (not midpoint-hysteresis), exhaustion diamond visual renders via `label.new()` at fib zone interaction. Five target levels: T1=1.236, T2=1.618, T3=2.0, T4=2.236, T5=2.618 — all tracked as full exit states and AG label outcomes.
- v7 intermarket basket (NQ/RTY/CL/HG/6E/6J) is AG-owned: all 6 symbols sourced server-side from `cross_asset_1h` (Databento hourly). Pine carries only IM state stubs (`ml_event_*_state`) for packet identity; live `request.security()` calls were removed in the plot cull. ES chart-native vol (ATR ratio, range expansion, efficiency, VWAP) fills the VIX/VVIX gap — computed from MES OHLCV directly. **Daily context** (NYSE A/D via `USI:ADD`, 1 security call) remains as AG feature input.
- v7 regime: visual regime state machine kept for chart display only. Grouped scores (leader/risk/macrofx/exec) are AG training features exported as primitives. Pine does NOT gate candidates on regime score.
- `cross_asset_15m` table created (migration 039, RLS enabled). HG (Copper) added to symbols (migration 039 + 040). Local warehouse has 20,553 rows for HG only. 15m backfill for NQ/RTY/CL/6E/6J is **intentionally deferred — SHAP-gated** (see Locked Rules).
- Intermarket Full Agreement Panel: NQ, RTY, CL, HG, 6E, 6J — 6 boxes from `cross_asset_1h` (Databento 1h, hourly cron). 6J inverted (JPY weakness = MES bullish). Background rule: all six +1 → green, all six -1 → red, otherwise transparent. Weighted IM Score badge: NQ 25%, RTY/CL/HG 13.33% each, 6E/6J 7.5% each. Shows `—` when no data.
- Cross-asset crons switched from nightly (02:00-02:30 UTC) to **hourly** — 4 shards at `:05/:06/:07/:08` past every hour, Sun-Fri (migration 040). All ~16 active Databento symbols updated within 4 minutes each hour.
- Chart container height locked to `80vh`.
- ES execution quality block: VWAP state/event (+2 reclaim, +1 above, 0 band, -1 below, -2 reject), range expansion (clamped, mintick-guarded), intrabar efficiency. Chart-native, zero security calls.
- Active Pine ML exports (32 plots): fib engine state, trade state machine, HTF fib confluence, VWAP code, OR state, IM state stubs, NYSE A/D slope, entry/exit trigger events, and TP1-TP5 hit events. All server-side-computable TA metrics (TA core pack, EMA dist, RVOL, exhaustion, range expansion, efficiency, impulse quality, regime score, agreement velocity) are AG-owned and computed from Databento OHLCV — not exported from Pine. AG label encoding: 0=none, 1=TP1_HIT, 2=TP2_HIT, 3=STOPPED, 4=EXPIRED, 5=TP3_HIT, 6=TP4_HIT, 7=TP5_HIT.
- All signals gated by `barstate.isconfirmed` — bar close only, no mid-bar firing.
- v6 (`indicators/v6-warbird-complete.pine`) is legacy baseline, not active work surface.
- Three standalone harnesses retired (BigBeluga Pivot Levels, LuxAlgo MSB/OB, LuxAlgo Luminance) — zero downstream consumers
- The active architecture lock is now engine-first: `fib_engine_snapshot -> candidate -> outcome -> decision -> signal`, with TradingView kept execution-facing and the dashboard owning operator tables/mini charts from the same contract

### What Doesn't Work Yet
- mes_1s ingestion (table exists, nothing writes to it)
- `cross_asset_15m` for NQ/RTY/CL/6E/6J not backfilled — SHAP-gated. `scripts/backfill-intermarket-15m.py` is ready but must not run for the Locked Basket until SHAP returns feature importance across the full training feature set and confirms which symbols/timeframes warrant 15m or 1m backfill. Current local minimum is 1h. See Locked Rules.
- Ongoing 15m ingestion Edge Function not yet built — `cross_asset_15m` is backfill-only (HG only in local warehouse).
- Companion pane indicator not yet built (regime_score, impulse_quality, exhaustion_score, agreement_velocity — own 64-plot/40-call budget).
- `econ_inflation_1d` is still stale relative to the live schedule.
- FRED backfill script (`python scripts/backfill-fred.py`) needs to run AFTER migration 026 is applied to production to populate the 22 new series
- TradingEconomics free tier is untested — Kirk must set API key and run curl tests (Phase 4 manual step)
- ML model training (target `scripts/ag/*` path not built yet)
- Python feature computation layer (not built yet)
- AG training pipeline (not built yet)
- PowerDrill MCP connectivity is verified from this workspace. The PowerDrill remote surface is a memorylake-backed MCP server; use that memorylake first for PowerDrill-grounded retrieval. Verified tools: `search_memory`, `fetch_memory`, `get_memorylake_metadata`, `create_memory_code_runner`, `run_memory_code`.
- The old Docker-local Supabase assumption is retired. Direct checks on 2026-04-07 showed no listener on `localhost:54322`, `psql` returned `Connection refused`, and `docker ps` could not reach a running daemon. Treat the external-drive local PostgreSQL warehouse as the canonical DB truth and the `/data/` raw/archive surface as its companion file layer instead.
- DB-side aggregation (all TypeScript, zero Postgres functions)
- Type generation (manual types, no supabase gen types)
- No active `pinescript-server`, TradingView chart MCP, or TradingView CLI is configured in the current Codex profile, so live-chart read / install / edit / deep-test flows described in older docs are not available from this terminal session
- Canonical admin/candidate surfaces are present, but the checked candidate/admin surfaces are empty because no canonical writer is active yet. Writers (`detect-setups`, `score-trades`) must be ported to Edge Functions targeting the canonical tables.
- `detect-setups` and `score-trades` exist as App Router routes (`app/api/cron/`) but have no Vercel cron schedule and no pg_cron schedule. No Edge Function port exists yet. Both are canonical writer-port reference code only. `detect-setups` still references renamed/dropped tables (`trump_effect_1d`, legacy warbird operational tables), and `score-trades` still references missing legacy tables (`warbird_setups`, `warbird_setup_events`, `measured_moves`), so neither is a trustworthy current-schema reference.
- Dashboard fib recompute was cut (commit `77ec03e`). `LiveMesChart.tsx` no longer calls the legacy fib-engine helper. Dashboard is not yet wired to canonical engine state — that's blocking order #5 (canonical writer cutover).
- `/admin` reads candidates from `warbird_admin_candidate_rows_v` (canonical view from migration 038). The canonical candidate surface is currently empty because no canonical writer is active yet. Separately, the legacy warbird operational tables read by `/api/warbird/signal`, `/api/warbird/history`, `/api/warbird/dashboard` do NOT exist in local or cloud, so those legacy reader paths are schema-stale right now. Runtime containment is now in place: those three routes run a service-role guard first and return `200` with an explicit `runtime` degradation payload plus empty Warbird state when the legacy objects are absent, and `DashboardLiveClient.tsx` surfaces that degraded mode visibly. This is not the reader cutover in plan step 6.
- `scripts/warbird/fib-engine.ts` still reflects a legacy 1H helper path and is not the target point-in-time fib snapshot surface for AG training
- The next step is intentionally PAUSED after Checkpoint 1. Do not continue canonical writer design, dashboard/admin cutover, schema/table recording design, or action/event recording design from a narrow `candidates + signals + outcomes` framing. The active plan already requires a larger contract: point-in-time setup truth, realized path truth, published signal lineage, and a separate explanatory/research layer. Admin page assumptions, schema assumptions, and action/event recording assumptions are not design-locked yet and must be re-audited against the plan before Checkpoint 2 resumes.
- Do not model the local side as "local Supabase." The current local contract is a canonical external-drive PostgreSQL warehouse plus the external-drive `/data/` raw/archive surface, separate from cloud Supabase.
- Cloud scope cleanup is still pending: any cloud table that does not serve frontend, indicator/runtime, packet distribution, curated SHAP/admin reports, or another explicitly plan-approved published surface should be retired.
- News infrastructure removed (migration 042): finnhub tables, news_signals matview, all_news_articles view, news types, news crons. Keeping: FRED, GPR, econ_calendar, executive_orders. NEWS is retired from the active contract and must not drive new schema, writer, admin, or training design unless explicitly reopened.
- 14 legacy tables dropped (migration 043): trade_scores, vol_states, models, sources, coverage_log, symbol_mappings, options_stats_1d, macro_reports_1d, 6x legacy backup tables.
- Stale code still references dropped/renamed schema: `lib/warbird/queries.ts` reads missing legacy warbird tables, `app/api/cron/detect-setups/route.ts` still queries `trump_effect_1d`, `app/api/cron/score-trades/route.ts` still reads missing legacy setup tables, `scripts/warbird/build-warbird-dataset.ts` still reads `news_signals`, `trump_effect_1d`, and `warbird_setups`, and `scripts/build-dataset.py` still references `news_signals` and `trump_effect_1d` even though it hard-exits as deprecated.
- `scripts/warbird/build-warbird-dataset.ts` is the current local extractor target, not dead legacy. It is still contract-dirty: hardcoded `2024-01-01` floor instead of the current 2020 local-training floor, ambiguous cloud/local env targeting (`NEXT_PUBLIC_SUPABASE_URL ?? SUPABASE_URL`), unordered `warbird_setups` fetch used as a recent-history window, stale dropped/renamed source tables, and non-deterministic `sample_weight` based on `Date.now()`.
- Current blocker: broader contract/admin/schema/action-event recording audit. Migration `045` is reconciled and replay-verified, but phases 5-7 remain paused until the plan-grounded architecture for point-in-time setup truth, realized path truth, published signal lineage, admin surfaces, and explanatory/research-layer recording is re-audited and explicitly locked.
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
- The external-drive local PostgreSQL warehouse is the single canonical database truth; cloud Supabase is the strict runtime/published subset only. No full cloud mirror.
- Do not trust docs, prior agent summaries, or build success as proof of schema truth. Verify table/view existence, row reality, and migration ledger directly against the actual database(s) first.
- Local and cloud must be described separately when their schema or data differs.
- Do not reduce the active contract to the current admin page columns or to shorthand like `candidates + signals + outcomes`. The plan requires separate point-in-time setup truth, realized path truth, published signal lineage, and a distinct explanatory/research layer for why trades reached TP1/TP2/SL.
- Do not treat the current admin page, the current canonical cloud tables, or current action/event route ideas as the finished recording contract. The plan still requires a larger architecture audit before writer/admin/schema/training implementation resumes.
- AG/offline training must consume point-in-time fib snapshots keyed to the MES 15m bar close; repaint-prone live chart reads are not acceptable dataset truth.
- Retained core historical data starts at `2020-01-01T00:00:00Z`. Pre-2020 core rows are out of scope.
- All MES Databento calls use `MES.c.0` (calendar front-month continuous) with `stype_in=continuous`. No manual contract-roll logic.
- The external-drive local PostgreSQL warehouse is the only approved local database and the canonical warehouse of record.
- Cloud frontend, indicator/runtime, and admin surfaces read only from Supabase runtime subset surfaces explicitly allowed by `docs/cloud_scope.md`.
- Cloud ingress may queue or retry delivery to local canonical, but cloud intake rows are not canonical lifecycle truth.
- No local Supabase, no Docker-local runtime DB, and no third database.
- No new predicted-price or `warbird_forecasts_1h`-style surfaces. Live model state is TP1/TP2/reversal outcome state on the MES 15m contract.
- `EXPIRED` / `NO_REACTION` are not canonical economic outcome labels for model truth. Unresolved rows remain `OPEN` until they resolve to `TP5_HIT` / `TP4_HIT` / `TP3_HIT` / `TP2_HIT` / `TP1_ONLY` / `STOPPED` / `REVERSAL`.
- Legacy `hit_*_first` / `prob_hit_*` names are scheduled for deletion. They must not appear in shared TypeScript types, active API responses, Admin/dashboard surfaces, packet payloads, or new schema work. No fallback aliases are permitted on new surfaces.
- The Admin page should render structured candidate rows, full training metrics, packet metrics, feature drivers, setting hypotheses, and AI-generated recommendations. Do not use Markdown report blobs as the dashboard contract.
- Decision vocabulary is `TAKE_TRADE`, `WAIT`, and `PASS`. Those are policy decisions, not realized trade outcomes.
- Pivot distance/state is a critical trigger and reversal input, but not the sole decision maker. AG training intermarket basket is 6 CME Globex futures (NQ, RTY, CL, HG, 6E, 6J) all available at 15m from Databento GLBX.MDP3. ES chart-native vol (ATR ratio, range expansion, efficiency, VWAP) covers the volatility signal. Daily VIX (FRED), SKEW, and NYSE A/D are daily-only context features, not gate members. AG decides correlations and weights from data.
- Do not add more indicator settings, assets, or “zoo” modules ahead of training evidence. Build the minimal exportable core first, then let SHAP and feature-admission evidence decide what survives.
- Minimal Pine export surface for training capture: fib engine state, trade state machine (entry/exit/TP1-TP5 hit events), HTF confluence (3 `request.security()` fib calls), VWAP code, OR state, IM state stubs, and NYSE A/D slope. All other features (TA core pack, EMA dist, RVOL, exhaustion, range expansion, efficiency, regime components, agreement velocity, impulse quality) are server-side computable by AG from Databento OHLCV — not Pine plot budget items.
- TradingView enforces a hard maximum of 64 output calls per script. Hidden `display.none` plots AND `alertcondition()` calls both count toward the cap. Current v7 budget: 32 plot + 3 alertcondition = 35/64 (29 headroom). AG owns all server-side-computable features from Databento OHLCV — these must NOT be re-exported from Pine.
- TradingView keeps execution-facing visuals and alerts. Only 3 `alertcondition()` calls are kept: `WARBIRD ENTRY LONG`, `WARBIRD ENTRY SHORT`, and `PIVOT BREAK (against) + Regime Opposed` (the .50 reversal warning). All other alerts move to the dashboard. Dense operator tables, mini charts, and decision diagnostics belong on the dashboard, which must render the same stored engine state instead of recomputing fibs.
- The current blocking sequence is: ~~Pine indicator recovery~~ (DONE) -> ~~v7 institutional upgrade~~ (DONE, 64/64) -> ~~intermarket pivot to CME Globex~~ (DONE, 63/64, commit `6f3e7a6`) -> ~~fib engine hardening~~ (DONE, commit `4a25806`) -> ~~Pine AG export surface cull + TP3/TP4/TP5 targets~~ (DONE, 35/64, 5 exit states) -> **canonical writer cutover** -> dashboard/admin reader cutover -> training workbench buildout -> legacy retirement.
- AG owns TA core pack computation server-side from Databento OHLCV. The 15 metrics (EMAs/MACD/RSI/ATR/ADX/volume family/OBV/MFI) are not Pine plot exports — they are AG-computed features. Do not re-introduce standalone third-party harnesses (BigBeluga, LuxAlgo MSB/OB, LuxAlgo Luminance are retired). Do not re-add TA core pack plots to Pine.
- **Cross-asset basket minimum training timeframe is 1h until post-SHAP validation.** SHAP must run across the full feature set — EMA lengths, event-response module, session context, pivot state, volume family, intermarket symbols (NQ/RTY/CL/HG/6E/6J), module families, and parameter settings. Not just which of the 6 symbols survive. Only after the first AG training run + SHAP returns feature importance and confirms surviving features/symbols do we determine which backfills (15m, 1m) are warranted. Do not run `scripts/backfill-intermarket-15m.py` for the Locked Basket before this gate clears.

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
