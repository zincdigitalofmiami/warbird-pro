# Warbird-Pro — Agent Rules

Read this file before any work.

## Agent Bootstrap

This root `AGENTS.md` is the workspace instruction surface. `.github/copilot-instructions.md`
is a thin redirector only; do not expand it into a competing source.

### Read Order

1. `AGENTS.md`
2. `docs/INDEX.md`
3. `docs/MASTER_PLAN.md`
4. `docs/contracts/README.md`
5. `docs/contracts/pine_indicator_ag_contract.md`
6. `docs/runbooks/README.md`
7. `docs/cloud_scope.md`
8. `WARBIRD_MODEL_SPEC.md`
9. `CLAUDE.md`
10. `docs/agent-safety-gates.md`

## Active Plan

The active architecture is **Warbird Indicator-Only AG Plan v6**.

The goal is pure PineScript trading-indicator modeling:

- perfect the TradingView indicator settings
- improve the indicator build and state machine
- use Optuna/AutoGluon/SHAP only as offline analysis tools over Pine outputs
- promote settings/build changes back into Pine after approval

The old warehouse/FRED/macro `ag_training` plan is superseded and reference-only.

## Default Preflight

- Run `git status --short` before edits.
- Use `rg --files` and `rg -n` to scope touched surfaces.
- Read the active docs for the touched surface before changing files.
- Never trust prior summaries, stale docs, or build success as proof of current truth.

## Repo Map

- `indicators/`: Pine indicator and strategy files; primary active surface is
  `indicators/v7-warbird-institutional.pine`.
- `scripts/optuna/`: active local optimization workspaces and runner.
- `scripts/ag/tv_auto_tune.py`, `scripts/ag/tune_strategy_params.py`: TradingView
  settings-trial helpers retained for Pine-derived modeling.
- `artifacts/tuning/`: tuning suggestions, exports, and trial artifacts.
- `app/`, `components/`, `lib/`, `supabase/`: runtime/dashboard/cloud support,
  not active training truth.
- `local_warehouse/`, local `warbird`, and `scripts/ag/train_ag_baseline.py`:
  legacy/reference unless explicitly reopened.

## Contract First

- Pine/TradingView output is the active training truth.
- Modeling inputs come only from TradingView indicator CSV exports, Strategy Tester
  exports, CDP-read Strategy Tester data, and deterministic fields derived from
  those Pine outputs.
- The active modeling object is the indicator behavior, not a server-side model.
- The active output is a Pine settings/build recommendation, not a live scoring packet.
- Every modeling run must declare one trigger family:
  `LIVE_ANCHOR_FOOTPRINT`, `STRATEGY_ACCEPT_SCALP`, or
  `BACKTEST_DIRECT_ANCHOR`.
- No external feature stacking: no FRED, macro, news, options, cross-asset, cloud,
  or Databento-ingestion joins in the active modeling dataset.
- Daily/hourly ingestion is not a training source. It may remain for runtime chart
  support only.
- Local `ag_training` and the four local AG tables are superseded as active model
  truth. Do not train from them unless Kirk explicitly reopens that architecture.

## Stack

- TradingView + Pine Script — canonical live and modeling surface
- Optuna / AutoGluon / SHAP — local offline analysis over Pine-derived rows
- Next.js + Supabase — runtime/dashboard/support only
- Local PG17 `warbird` — legacy/reference for this plan unless explicitly reopened

## Hard Rules

### Data

- No mock, demo, placeholder, or fake data.
- Training/modeling rows must come from real Pine/TradingView exports or CDP-read
  Strategy Tester evidence.
- Do not use daily ingestion, FRED, macro, news, options, or cross-asset joins as
  active training features.
- If an indicator feature is not present in Pine/TradingView output, it is not in
  the active modeling dataset.

### Pine

- Never edit `indicators/v7-warbird-institutional.pine` without explicit approval
  in the current session.
- Never push Pine changes to TradingView Pine Editor without explicit approval.
- `indicators/v8-warbird-live.pine` and `indicators/v8-warbird-prescreen.pine`
  are code-frozen. Only approved `input.*` default changes are allowed.
- Pine budget baselines verified 2026-04-26:
  - `v7-warbird-institutional.pine`: 58/64 output calls
  - `v7-warbird-strategy.pine`: 60/64 output calls
  - `v7-warbird-institutional-backtest-strategy.pine`: 53/64 output calls
- Price every new output or request path before writing Pine code.
- `request.footprint()` is budget-sensitive and must be cached per bar.

### Pine Verification

If any `.pine` file is touched, run:

1. pine-facade compile check
2. `./scripts/guards/pine-lint.sh <file>`
3. `./scripts/guards/check-contamination.sh`
4. `npm run build`
5. `./scripts/guards/check-indicator-strategy-parity.sh` when v7 indicator /
   strategy coupling is touched

### Backtesting And Modeling

- MES commission floor: $1.00/side.
- Slippage floor: 1 tick.
- Use Bar Magnifier when reported results depend on intrabar stop/target behavior.
- Champion settings require IS/OOS or walk-forward-style review.
- Do not accept a settings result without export/CDP evidence, manifest, row/trade
  count, date range, and exact Pine inputs.
- Do not start training/modeling unless explicitly asked.

### Cloud And Database

- Cloud Supabase is runtime/support only. It must not receive raw trials, labels,
  raw SHAP, or full research datasets.
- Local `warbird` warehouse and old AG lineage tables are reference-only for this
  plan.
- No Prisma, Drizzle, or ORM.
- Cloud DDL still belongs in `supabase/migrations/`; local DDL still belongs in
  `local_warehouse/migrations/` if that legacy surface is explicitly reopened.

## Build & Deploy

- `npm run lint` is the standard lint gate.
- `npm run build` must pass before every push.
- No `--no-verify` on git hooks.
- Do not use destructive git commands unless explicitly requested.

## Process

- One task at a time. Complete fully.
- Do not refactor unrelated code.
- Do not revert user changes.
- Update `docs/MASTER_PLAN.md` when architecture changes.
- Update `WARBIRD_MODEL_SPEC.md` when the model contract changes.
- Update `CLAUDE.md` when operational truth changes.
- Update `AGENTS.md` only when repo rules or hard workflow constraints change.
- Update memory when a phase or contract locks.

## Memory & Session Handoff

- `.remember/` files are append-only.
- Durable memory lives under `/Volumes/Satechi Hub/warbird-pro-state/`.
- Persistent cross-session memories resolve through
  `/Users/zincdigital/.claude/projects/-Volumes-Satechi-Hub-warbird-pro/memory/`.
- Always add a pointer line to `MEMORY.md` for durable project memories.

## No Hand-Rolling

When a working implementation exists, copy the proven internals exactly and adapt
only the interface. This applies to Pine patterns, APIs, scripts, and library
integrations.

## Legacy Training Skills

The old warehouse AutoGluon skills and docs remain lineage only. Do not use
`training-full-zoo`, `training-pre-audit`, `training-shap`, `training-monte-carlo`,
or local `ag_training` workflows for active modeling unless Kirk explicitly
reopens the warehouse training architecture.
