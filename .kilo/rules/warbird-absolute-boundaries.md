# Warbird Absolute Boundaries

These are fixed routing boundaries for Kilo agents working in Warbird-Pro. They
exist to prevent stale architecture drift.

## Source Of Truth

- The local clone at `/Volumes/Satechi Hub/warbird-pro/` is authoritative.
- GitHub is secondary and is only for PRs, issues, actions, or remote-only state.
- If the local clone is unavailable, surface the blocker. Do not silently replace
  local inspection with remote web lookup.

## Active Indicator Boundaries

### Warbird Pro V9

- `indicators/warbird-pro-v9.pine` is the only active main chart indicator.
- Do not edit it without explicit approval in the current session.
- Do not touch fib anchor ownership, ladder math, or trade-state label semantics
  without explicit before/after TradingView evidence and explicit approval.
- Do not add outputs casually. The V9 Pine budget is tight, with only four output
  slots remaining against the 64-call cap at the last recorded baseline.
- Never reintroduce retired V7/V8 indicator variants as active surfaces.

### Nexus

- `indicators/warbird-nexus-machine-learning-rsi-optuna-fast-test.pine` is the
  retained Nexus support/research lane.
- The `optuna` token in the Nexus filename is legacy naming only. It is not a
  workflow selector.
- Nexus V3 work is Nexus-only: no V9 surfaces, no fib scanner/fib-contract lane,
  no Optuna lane unless Kirk explicitly reopens that scope.
- Nexus footprint work must use Pine/TradingView `request.footprint()` evidence,
  not CSV exports, local OHLCV parquet, Databento bars, or synthetic delta.

## Data And Modeling Boundaries

### Local DuckDB V9 Core

- `scripts/duckdb_local/` is the active local V9 modeling workspace.
- V9 Core uses DuckDB, Pandera, fg-data-profiling, and AutoGluon through the file
  pipeline. Do not route V9 Core work through the old local Postgres warehouse.
- V9 Core admits ES 15m/5m rows only. MES/NQ/MNQ rows are not V9 Core training
  rows.
- The ES 15m lane comes first. Do not build/train ES 5m until documented ES 15m
  success exists for fit, SHAP, and Monte Carlo.

### AG Training

- `scripts/ag/train_v9_locked.py` is the production V9 trainer.
- The active target is `winner_tp_before_sl` with `eval_metric='log_loss'` and
  isotonic calibration unless active docs change in the same work package.
- The old `scripts/ag/train_ag_baseline.py`, local warehouse `ag_training`, and
  legacy warehouse modeling skills are reference-only unless Kirk explicitly
  reopens that architecture in the current session.
- Do not start training, SHAP, Monte Carlo, dataset builds, or parameter sweeps
  without explicit user instruction in the current session.

### Optuna

- Optuna is a backup/specialist optimization path, not the default Warbird route.
- Do not set up, resume, repair, or launch Optuna studies unless Kirk explicitly
  requests Optuna in the current session.
- Do not treat historical Optuna docs, legacy filenames, or old study artifacts as
  active routing authority.

### Databento

- Databento is an approved market-data supplier only when manifests honestly
  declare Databento source/capture kind.
- Before any Databento API call, use the Databento research workflow and verify
  docs, subscription tier, and symbology.
- Databento rows are not Pine indicator CSVs and do not replace V9/Nexus trigger
  identity.

## Cloud And Database Boundaries

- Cloud Supabase is runtime/support/serving only.
- Supabase Edge Functions run on Deno. Do not inject Node-native module
  assumptions or `node_modules`-style backend patterns into `supabase/functions/**`.
- Keep Next.js as client/UI integration surface; do not migrate backend
  automation logic from Supabase into app/server routes unless explicitly
  approved.
- Do not send raw trials, labels, full research datasets, or raw SHAP payloads to
  cloud Supabase.
- Cloud DDL belongs in `supabase/migrations/`.
- Legacy local warehouse DDL belongs in `local_warehouse/migrations/` only if that
  surface is explicitly reopened.
- No Prisma, Drizzle, or ORM.
- Keep SQL lanes separated: DuckDB SQL in Python local modeling lanes, Postgres
  SQL in Supabase OLTP lanes.

## TradingView Boundary

- Do not push Pine to TradingView without explicit approval.
- Before any TradingView CDP/MCP operation, run the read-only connection doctor
  from the active docs.
- If CDP is down, stop immediately. Do not recover, relaunch, retry, or probe with
  banned TradingView commands.

## Documentation Boundary

- Update active docs in the same work package when code/settings/artifacts change
  the contract.
- Do not move stale plan text forward into new work. Retired surfaces may stay
  only in historical/archive docs.
