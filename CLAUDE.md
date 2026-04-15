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
- `indicators/v7-warbird-strategy.pine` is the AG training data generator. Compiles clean. Output budget: 52/64 (50 plot + 2 plotshape, 12 headroom). Commission floor at $1.00/side. `use_bar_magnifier=true`, `slippage=1` pinned in `strategy()`. Budget verified 2026-04-13. Dead HyperWave oscillator + energy computation blocks removed 2026-04-13 (were live in v6, orphaned in v7). Raw footprint numeric exports added 2026-04-13: `ml_exh_fp_delta`, `ml_exh_trigger_row_delta`, `ml_exh_extreme_vol_ratio`, `ml_exh_stacked_imbalance_count` — AG cannot compute these server-side (TV-exclusive API). First-run contract keeps all `ml_exh_*` / `ml_cont_*` diamond-path fields out of the canonical predictor and production SHAP; they are tuning-only unless explicitly reopened.
- v7 parity guard (`scripts/guards/check-indicator-strategy-parity.sh`) updated for v7: ml_* parity, budget caps, coupled input defaults, strategy execution primitives, pinned TV defaults.
- ESLint gate passes clean (`npm run lint` = 0 errors, 0 warnings).
- Migration reconciliation through `045` is verified local↔remote.
- Security advisor: 0 code warnings.
- Pine Script v6 capability set for the active indicator path is confirmed:
  enums, strict boolean logic, dynamic requests, dynamic loops, `request.footprint()`,
  and `polyline` are available for the exhaustion/hold architecture.
- 2026-04-14 contract delta: the MES 15m fib setup remains the parent object,
  but execution is reopening as a subordinate `5m` / `15m` trigger layer keyed
  back to the same parent setup. `5m` provides execution context only; the
  owning fib map remains `15m`. Fibs are the map; order-flow at the level is
  the trigger.
- 2026-04-14 `15m` fib-owner freeze: live and training now lock the parent map
  to `Deviation=4`, `Depth=20`, `Threshold Floor=0.50`, `Min Fib Range=0.5`.
  Do not let AG train against any other fib-owning timeframe contract.
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
- ~~Four canonical local AG tables and one canonical training view (`ag_training`): not yet created (Phase 3)~~ **DONE 2026-04-11 (three-table original) + migration 016 (stop-variant expansion)** — `ag_fib_snapshots`, `ag_fib_interactions`, `ag_fib_stop_variants`, `ag_fib_outcomes` + view live.
- Python pipeline in `scripts/ag/`:
  - CDP tuner automation built (`tv_auto_tune.py` + `tune_strategy_params.py` + `strategy_tuning_space.json` — applies inputs via CDP, polls recalc, reads trades without CSV export). 2026-04-13 tuner hardening landed: new profile `mes15m_agfit_v3`, narrowed search ranges, non-causal locked inputs removed from trial signatures, coupled-parameter rejection rules added, and objective upgraded to include drawdown efficiency, rolling-window stability, footprint-tail stability, and yearly consistency. No authoritative `mes15m_agfit_v3` recorded trials yet.
- Phase 4 bootstrap pipeline now implemented (`scripts/ag/build_ag_pipeline.py`) and executed on local `warbird` (2026-04-13): `ag_fib_snapshots=3,101`, `ag_fib_interactions=37,450`, `ag_fib_outcomes=37,450`, `ag_training=17,100` rows.
  - 2026-04-14 micro execution follow-on landed:
    - migration `011_mes_1m_micro_execution.sql` adds local `mes_1m` plus micro execution fields on `ag_fib_interactions`
    - `data/mes_1m.parquet` loaded into local `warbird.mes_1m` via `local_warehouse/bootstrap/load_mes_1m_from_parquet.py`
    - local `mes_1m` now holds 2,207,167 rows (`2020-01-01 17:00:00-06` -> `2026-04-03 08:14:00-05`)
    - `build_ag_pipeline.py` now populates micro execution fields (`ml_exec_*`) from local 1m microstructure
    - latest local rebuild (`agfit_20260414T112223Z`) completed with `micro_bars_loaded=2,207,167`
  - Walk-forward split structure now generated at `artifacts/ag_runs/agfit_20260413T192255Z/` (`train.csv`, `val.csv`, `test.csv`, `manifest.json`).
- Repo-native baseline trainer now exists (`scripts/ag/train_ag_baseline.py`). It joins the canonical `ag_training` rows with the curated `FRED/econ_calendar` regime context, enforces the required series set in the FRED catalog, removes label leakage from `ag_training`, writes run artifacts under `artifacts/ag_runs/`, and blocks training when a validation/test slice has fewer than 2 target classes.
  - 2026-04-14 lineage update: migration `014_ag_training_run_lineage.sql` creates the local run/SHAP spine (`ag_training_runs`, `ag_training_run_metrics`, `ag_artifacts`, `ag_shap_feature_summary`, `ag_shap_cohort_summary`, `ag_shap_interaction_summary`, `ag_shap_temporal_stability`, `ag_shap_feature_decisions`, `ag_shap_run_drift`), and the trainer now writes run metadata, fold metrics, and artifact registry rows for dry and real runs.
  - Dry-run verification `agtrain_20260414T183606833153Z` passed: `ag_training_runs` row present (`SUCCEEDED`, `dry_run=true`), baseline fold metrics written, and `DATASET_SUMMARY` / `FEATURE_MANIFEST` / `FOLD_SUMMARY` / `TRAINING_SUMMARY` artifacts registered.
  - 2026-04-14 evaluation-policy repair: the pipeline now censors only end-of-history truncated windows. Full-window rows retain `TP1_ONLY` through `TP4_HIT` instead of being mislabeled `CENSORED`. Current local outcome mix is `STOPPED=35792`, `TP1_ONLY=426`, `TP2_HIT=78`, `TP3_HIT=20`, `TP4_HIT=20`, `TP5_HIT=1114`, `CENSORED=11`.
  - 2026-04-14 fold-policy repair: migration `015_ml_exec_tf_code_scope_cut.sql` aligned the warehouse to `ml_exec_tf_code IN (0, 5, 15)`, and the trainer now does a simple class-aware forward search for validation/test windows. Verified dry run `agtrain_20260414T184346894785Z` on `2020-01-03` through `2020-12-31` is now legal with `train_rows=3243`, `val_rows=682`, `test_rows=354`, `val_class_count=3`, `test_class_count=3`.
  - 2026-04-15 evaluation-integrity repair: trainer defaults now use `time_limit=3600`, `num_bag_folds=0`, `num_stack_levels=0`, and `dynamic_stacking=off`, with weighted ensembling disabled. AutoGluon internal ensembling is blocked by default because IID child folds violate the MES walk-forward embargo and can leak adjacent-session signal.
- Full-surface SHAP program: lineage spine landed; raw SHAP artifacts and summary population are still pending the first corrected fitted run (Phase 5)
- Cloud serving promotion: blocked on Phases 1-5 (Phase 6)
- `artifacts/` directory: now active for AG split/baseline runs. `artifacts/shap/` still not created.
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
- Current tuning harness only optimizes parent 15m strategy knobs. It does not
  choose `5m` trigger policy versus parent-bar `15m` execution or expose
  `FORMING -> READY -> TRADE_ON -> INVALIDATED -> EXPIRED` operator states.
- Local `mes_1m` admission is now complete for subordinate micro-execution
  context. `5m` remains derived on read and does not own fib anchors; `15m`
  remains the parent fib owner and parent-bar execution state.
- Current micro execution layer is a first deterministic 1m OHLCV-derived
  scaffold. Footprint-specific micro fields such as true absorption and
  zero-print remain false until lower-timeframe capture is wired.
- Canonical stale micro-state heuristic: provisional `FORMING` / `READY` rows
  become `EXPIRED` once `ml_exec_reclaim_dist_atr >= 1.5` and
  `ml_exec_impulse_break_atr <= 0.15`.
- Local verification on 2026-04-14: `EXPIRED` yielded `968` rows in
  `ag_fib_interactions`, with `901 STOPPED` and only `1 TP5_HIT`.
- Local `mes_1m` now extends through `2026-04-14 08:40 America/Chicago` via
  direct Databento gap-fill. Local `mes_15m` has been rolled forward from
  canonical `mes_1m` through `2026-04-14 08:15 America/Chicago`.
- First April 14 warehouse audit result: the current micro engine emits only
  parent-aligned long rows at `05:00`, `05:30`, `05:45`, `06:00`, and `06:15`
  CT, with `TRADE_ON` at `06:00` and `06:15`. It does not emit the obvious
  counter-direction failure short the operator marked on tape.
- Direction repair landed: micro execution direction is explicit on the parent
  row, so lower-timeframe failure triggers can oppose the active 15m map
  without creating a second trade object.
- AG-ready scope lock: do not add a second micro routing taxonomy ahead of AG.
  The admitted micro surface is the primitive `ml_exec_*` field family; AG and
  SHAP decide which states/timeframes matter.

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

- 15m is the parent model/chart/setup timeframe.
- `5m` and parent-bar `15m` are the subordinate execution timeframes once the
  2026-04-14 micro-execution delta is implemented.
- The canonical trade object is the MES 15m fib setup keyed by MES 15m bar close in `America/Chicago`.
- Any `1H` wording outside archived docs is legacy and must not drive new work.
- Pine is the canonical **live generator**; the Python reconstruction pipeline is the **training generator**.
- Canonical AG contract is **four canonical local AG tables and one canonical training view.** No version suffixes. Tables: `ag_fib_snapshots`, `ag_fib_interactions` (stop-agnostic), `ag_fib_stop_variants` (stop-specific candidate surface), `ag_fib_outcomes`.
- Exact local AG schema authority: `docs/contracts/ag_local_training_schema.md`.
- The local `warbird` PG17 warehouse is the single canonical database truth; cloud Supabase is the strict runtime/published subset only. No full cloud mirror.
- `rabid_raccoon` is bootstrap-only. After one-time import into `warbird`, it is legacy reference only.
- Local warehouse DDL lives in `local_warehouse/migrations/` with its own `local_schema_migrations` ledger. Not in `supabase/migrations/`.
- Cloud DDL lives in `supabase/migrations/` only.
- Removed from canonical local build: `cross_asset_1d`, all news surfaces, all options surfaces, all legacy setup/trade/news tables.
- `mes_1m` is reopened only as subordinate local micro-execution context for the
  parent MES 15m setup. It is not a new primary trade object and only exists to
  derive `5m` execution context. `15m` remains the owning fib map and may emit
  the parent-bar execution state directly.
- First model target: multiclass `outcome_label`.
- First feature scope: `MES 1m/15m/1h/4h + SP500 spot + macro`.
- Current operational truth: the trainer currently admits `SP500` as the daily FRED regime series. True intraday S&P 500 cash spot is not yet present in local `warbird`.
- Macro scope: curated `FRED + econ_calendar` only. No news or narrative sources.
- Project-home raw parity cleanup completed on 2026-04-14: `data/mes_1m.parquet`
  and `data/mes_1h.parquet` were de-duplicated on `(ts, symbol)`, and the
  legacy options backup CSVs were removed from `data/local-db-backups/`.
- Cloud promotion is manual. Local training and SHAP complete first; publish-up only after explicit approval.
- Cloud never receives: `ag_fib_snapshots`, `ag_fib_interactions`, `ag_fib_outcomes`, `ag_training`, raw features, raw labels, raw SHAP matrices, raw SHAP interaction matrices.
- Full-surface SHAP is mandatory.
- Training discipline: walk-forward splits only, one-session embargo minimum, no shuffle, no fit on full dataset, no tuning on test, naive baseline required, full run metadata required.
- Do not trust docs, prior agent summaries, or build success as proof of schema truth. Verify directly.
- AG owns TA core pack computation server-side from Databento OHLCV. These are NOT Pine plot exports.
- TradingView enforces a hard maximum of 64 output calls per script. Current v7 budget: 51/64 (13 headroom). Strategy: 52/64 (12 headroom).
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
