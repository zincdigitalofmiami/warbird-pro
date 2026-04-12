Read and follow AGENTS.md at the repository root.

## Quick Reference

- **Canonical docs index:** `/Volumes/Satechi Hub/warbird-pro/docs/INDEX.md`
- **Active architecture plan:** `/Volumes/Satechi Hub/warbird-pro/docs/MASTER_PLAN.md` — Warbird Full Reset Plan v5
- **Interface authority:** `/Volumes/Satechi Hub/warbird-pro/docs/contracts/README.md`
- **Cloud whitelist:** `/Volumes/Satechi Hub/warbird-pro/docs/cloud_scope.md`
- **PowerDrill research baseline:** `Powerdrill/reports/2026-04-06-powerdrill-findings.md`
- **PowerDrill MCP access:** shared tracked `/.mcp.json` keeps only non-secret MCP servers; Kilo uses gitignored `/.kilo/kilo.json` for the PowerDrill remote entry; Claude Code / Cursor users add PowerDrill to local untracked `.mcp.json` after clone
- **Live:** deployment URL managed in project operations docs
- **Repo:** github.com/zincdigitalofmiami/warbird-pro
- **DB:** Two databases in scope:
  - **Local `warbird`** on PG17 (`127.0.0.1:5432`) — canonical warehouse, training, artifacts, raw SHAP, diagnostics
  - **Cloud Supabase** (`qhwgrzqjcdtdqppvhhme`) — serving-only for frontend, indicator/runtime, packets, dashboard/admin read models, curated SHAP/report surfaces
- **No Prisma. No ORM.**

## Current Status

### Active Plan Phase

**Warbird Full Reset Plan v5** is active. Phases 0–3 are complete and landed. Phase 4 (Python Pipeline) is the current execution front.

Phase execution order:

- Phase 0: Authority Rewrite Order — COMPLETE (landed commit 92ea751)
- Phase 1: Local Warehouse Creation — COMPLETE 2026-04-11
- Phase 2: One-Time Bootstrap from `rabid_raccoon` — COMPLETE 2026-04-11
- Phase 3: Canonical AG Schema — COMPLETE 2026-04-11 (migration 007)
- Phase 4: Python Pipeline in `scripts/ag/` — extract, reconstruct, generate, label, train, SHAP, publish-up
- Phase 5: Full-Surface SHAP Program — lineage tables, raw artifacts, cohort/interaction/temporal/drift analysis
- Phase 6: Cloud Serving and Manual Promotion

### What Works (Cloud Side)

- MES chart pipeline end-to-end (Databento Live API → cron → Supabase → Realtime → chart)
- Real-time MES minute path: Edge Function `mes-1m` connects to Databento Live API (TCP gateway), streams `ohlcv-1s` for `MES.c.0` (continuous), aggregates 1s → 1m, upserts `mes_1m`, rolls up touched 15m buckets into `mes_15m`. Zero lag — data arrives within the current minute. Falls back to Historical API for gaps > 60 min.
- `mes-hourly` Edge Function pulls `ohlcv-1h` and `ohlcv-1d` directly from Databento Historical API. Rolls 1h → 4h locally.
- All active recurring ingestion runs via Supabase pg_cron → Edge Functions (9 functions in `supabase/functions/`).
- Cross-asset pipeline: `cross-asset` Edge Function pulls `ohlcv-1h` from Databento Historical API for all active DATABENTO symbols. 4 shards fire hourly at `:05/:06/:07/:08` Sun-Fri (migration 040).
- All Databento calls use `.c.0` continuous front-month contracts with `stype_in=continuous`. No manual contract-roll logic.
- Live core retention floor is `2020-01-01T00:00:00Z`.
- `indicators/v7-warbird-institutional.pine` is the active Pine work surface. Compiles clean, TV-validated. Output budget: 51/64 (46 plot + 2 plotshape + 3 alertcondition, 13 headroom). 4 `request.security()` calls + 1 `request.footprint()` call (live, implemented). Budget verified 2026-04-13.
- `indicators/v7-warbird-strategy.pine` is the AG training data generator. Compiles clean. Output budget: 48/64 (46 plot + 2 plotshape, 16 headroom). Commission floor at $1.00/side. `use_bar_magnifier=true`, `slippage=1` pinned in `strategy()`. Budget verified 2026-04-13.
- v7 parity guard (`scripts/guards/check-indicator-strategy-parity.sh`) updated for v7: ml_* parity, budget caps, coupled input defaults, strategy execution primitives, pinned TV defaults.
- ESLint gate passes clean (`npm run lint` = 0 errors, 0 warnings).
- Migration reconciliation through `045` is verified local↔remote.
- Security advisor: 0 code warnings.
- Pine Script v6 capability set for the active indicator path is confirmed:
  enums, strict boolean logic, dynamic requests, dynamic loops, `request.footprint()`,
  and `polyline` are available for the exhaustion/hold architecture.
- Automated indicator capture pipeline is designed:
  Pine alert at `barstate.isconfirmed` -> Supabase Edge Function (`indicator-capture`)
  -> cloud relay table `indicator_snapshots_15m` -> nightly local sync to `warbird`.
  Recurring manual TV export is removed after one-time seed ingest.
- Backtesting upgrade path is locked:
  Deep Backtesting + Bar Magnifier + walk-forward with embargo + realistic friction floors.
- Trade loss-driver review is complete and mapped to indicator modules
  (revenge re-entry clustering, premature exits, session-quality degradation, sizing in drawdown).

### What Doesn't Work Yet (v5 Execution)

- ~~Local `warbird` PG17 database: not yet created (Phase 1)~~ **DONE 2026-04-11** — `warbird` created on PG17.
- ~~`local_warehouse/migrations/` directory: not yet created (Phase 1)~~ **DONE 2026-04-11** — 6 migrations applied (001-006). 18 tables + ledger live.
- ~~`local_schema_migrations` ledger table: not yet created (Phase 1)~~ **DONE 2026-04-11**
- ~~One-time bootstrap from `rabid_raccoon`: not yet run (Phase 2)~~ **DONE 2026-04-11** — All surfaces bootstrapped. HG loaded from `data/cross_asset_1h.parquet`. All 6 cross-asset symbols live. 221,954 cross-asset rows through 2026-04-03.
- ~~Three canonical local AG tables and one canonical training view (`ag_training`): not yet created (Phase 3)~~ **DONE 2026-04-11** — migration 007. 3 tables + view live.
- Python pipeline in `scripts/ag/`: not yet built (Phase 4)
- Full-surface SHAP program: not yet built (Phase 5)
- Cloud serving promotion: blocked on Phases 1-5 (Phase 6)
- `artifacts/` and `artifacts/shap/` directories: not yet created
- `data/` directory for raw Databento archives: not yet organized per v5
- Exhaustion diamond v2: designed, not yet implemented. Full spec in Phase 0.5.
  Requires budget audit + explicit approval before touching `v7-warbird-institutional.pine`.
- Behavioral indicator modules from loss-driver review: designed, not yet implemented.
- `indicator-capture` Edge Function: not yet built.
- `indicator_snapshots_15m`: not yet created (cloud or local).
- TV alert webhook for indicator capture: not yet configured.
- S/R feature contract: locked in `docs/contracts/ag_local_training_schema.md`. Phase 0 fully landed in git (commit 92ea751).
- Per-level Fib ladder AG exports: not yet in indicator. Required in Phase 0.5.
- Historical seed ingest for indicator snapshots: not yet executed.
- Trade-review timestamp join into feature lineage surfaces: not yet executed.

### Legacy / Stale Code (Known Debt)

- `detect-setups` and `score-trades` exist as App Router routes (`app/api/cron/`) but have no active cron schedule and reference dropped/renamed tables. Not ported to Edge Functions.
- `lib/warbird/queries.ts` reads missing legacy warbird tables.
- `scripts/warbird/build-warbird-dataset.ts` still references `news_signals`, `trump_effect_1d`, and `warbird_setups`.
- `scripts/build-dataset.py` still references `news_signals` and `trump_effect_1d` (hard-exits as deprecated).
- `scripts/warbird/fib-engine.ts` reflects a legacy 1H helper path, not the target AG training surface.
- Dashboard fib recompute was cut (commit `77ec03e`). Dashboard is not yet wired to canonical engine state.
- Legacy warbird operational tables read by `/api/warbird/signal`, `/api/warbird/history`, `/api/warbird/dashboard` do NOT exist in local or cloud. Runtime containment is in place (returns degradation payload).

### Architecture Direction

Follow Warbird Full Reset Plan v5 only. No other plan drives implementation.

### Locked Rules

- 15m is the primary model/chart/setup timeframe.
- The canonical trade object is the MES 15m fib setup keyed by MES 15m bar close in `America/Chicago`.
- Any `1H` wording outside archived docs is legacy and must not drive new work.
- Pine is the canonical **live generator**; the Python reconstruction pipeline is the **training generator**.
- Canonical AG contract is **three canonical local AG tables and one canonical training view.** No version suffixes.
- Exact local AG schema authority: `docs/contracts/ag_local_training_schema.md`.
- The local `warbird` PG17 warehouse is the single canonical database truth; cloud Supabase is the strict runtime/published subset only. No full cloud mirror.
- `rabid_raccoon` is bootstrap-only. After one-time import into `warbird`, it is legacy reference only.
- Local warehouse DDL lives in `local_warehouse/migrations/` with its own `local_schema_migrations` ledger. Not in `supabase/migrations/`.
- Cloud DDL lives in `supabase/migrations/` only.
- Removed from canonical local build: `mes_1m`, `cross_asset_1d`, all news surfaces, all options surfaces, all legacy setup/trade/news tables.
- First model target: multiclass `outcome_label`.
- First feature scope: `MES + cross-asset + macro`.
- Macro scope: `FRED + econ_calendar` only. No news or narrative sources.
- Cloud promotion is manual. Local training and SHAP complete first; publish-up only after explicit approval.
- Cloud never receives: `ag_fib_snapshots`, `ag_fib_interactions`, `ag_fib_outcomes`, `ag_training`, raw features, raw labels, raw SHAP matrices, raw SHAP interaction matrices.
- Full-surface SHAP is mandatory.
- Training discipline: walk-forward splits only, one-session embargo minimum, no shuffle, no fit on full dataset, no tuning on test, naive baseline required, full run metadata required.
- Do not trust docs, prior agent summaries, or build success as proof of schema truth. Verify directly.
- AG owns TA core pack computation server-side from Databento OHLCV. These are NOT Pine plot exports.
- TradingView enforces a hard maximum of 64 output calls per script. Current v7 budget: 51/64 (13 headroom). Strategy: 48/64 (16 headroom).
- Decision vocabulary: `TAKE_TRADE`, `WAIT`, `PASS`.
- No mock data, no inactive Databento symbols, no Prisma/ORM paths.
- Pine budget audit is required before any indicator implementation workstream.
- Never touch `v7-warbird-institutional.pine` without explicit session approval.
- Exhaustion is `ml_*` feature enrichment only. Never a hard candidate gate.
- S/R features are per-type normalized numeric families. No string columns,
  no raw prices, no JSON/list feature blobs.
- Commission floor for MES backtesting: $1.00/side minimum.
- IS/OOS embargo: one-session minimum (hard rule).
- Hard stop rule: structural stop `0.618 x ATR(14)` and emergency stop `1.0 x ATR(14)`,
  both rendered from entry bar.
- Consecutive loss block: 2 = warning, 3 = halt recommended (visual enforcement).
- Opening bar suppressor: no new entry signals during 9:30-9:44 ET.
- Indicator data capture is automated after one-time setup. Manual TV CSV export
  is one-time historical seed only.
- Direction asymmetry is discovered by AG from features, not hardcoded.

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
