# Warbird-Pro — Agent Rules

Read this file before any work.

## Repo Location & Source of Truth

The authoritative warbird-pro repository is the **local clone** at:

```
/Volumes/Satechi Hub/warbird-pro/
```

This local path is the source of truth for every code, file, script, study DB,
runbook, `.remember/` note, and migration question. ALWAYS read or grep the
local clone first. The GitHub remote (`github.com/zincdigitalofmiami/warbird-pro`)
is secondary — use it only for PRs, Issues, Actions, and remote-only state.

This rule applies to every Claude surface: Claude Code on the Mac, claude.ai
web, and claude.ai mobile. claude.ai sessions must use Desktop Commander to
reach the Satechi Hub mount. If tooling can't reach the local mount, surface
the blocker — do NOT silently substitute GitHub web fetch as source of truth.

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
7. `docs/runbooks/startup_repo_review.md`
8. `docs/cloud_scope.md`
9. `WARBIRD_MODEL_SPEC.md`
10. `CLAUDE.md`
11. `docs/agent-safety-gates.md`

### Startup / Start-of-Day Review

At the start of every fresh chat, start of day, context reset, or resumed
session where current repo state is unknown, perform the read-only startup
repo review before planning or implementation.

Use `docs/runbooks/startup_repo_review.md` as the checklist. The review must
inspect the local authority docs, recent commit history and diffs, working tree
state, stashes, branch/worktree landscape, and key project surfaces. Report the
current architecture, recent direction, active WIP, notable inconsistencies,
and areas that appear stable vs. in flux.

The startup review is inspection-only: do not modify files, stage/commit,
install dependencies, run builds/tests/training, or touch Pine during this
initialization pass unless the user separately asks for implementation after
the review.

## Active Plan

The active architecture is **Warbird Indicator-Only Optuna Plan v6**, narrowed on
2026-04-30 to one main chart indicator plus the Nexus support/research lane.

The goal is pure PineScript trading-indicator modeling:

- perfect the TradingView indicator settings
- improve the indicator build and state machine
- use Optuna only as the offline analysis tool over Pine outputs
- promote settings/build changes back into Pine after approval
- keep `indicators/warbird-pro-rebuild-fib-ml.pine` as the only active main chart
  indicator
- keep `warbird_pro_v9` as a separate Optuna lane for ES/MES-only ATR/risk exit
  modeling over active Warbird Pro rebuild exports
- keep the Nexus Pine files as the only active support/research indicator lane
- retire and remove all other Pine indicator/strategy variants from the active
  `indicators/` surface

The old warehouse/FRED/macro `ag_training` plan is superseded and reference-only.

## Iterative Tuning Contract

Warbird is actively tuning and training the Pine indicator. Current trigger
families, settings, thresholds, search spaces, and build recommendations are
evidence snapshots, not frozen production truth. Agents must expect these
details to change as TradingView exports and Optuna trials produce stronger
results.

When evidence changes the contract, update the active Markdown in the same
change as the code/settings/artifacts. Do not leave stale plans, runbooks, skill
context, or agent-facing notes pointing at an older trigger or training surface.

## Default Preflight

- Run `git status --short` before edits.
- Use `rg --files` and `rg -n` to scope touched surfaces.
- Read the active docs for the touched surface before changing files.
- Never trust prior summaries, stale docs, or build success as proof of current truth.

## Repo Map

- `indicators/`: active Pine sources:
  - `indicators/warbird-pro-rebuild-fib-ml.pine` — only main chart indicator
  - `indicators/warbird-nexus-machine-learning-rsi-optuna-fast-test.pine` —
    Nexus Optuna/footprint evidence lane (retained support/research lane)
- `scripts/optuna/`: active local optimization workspaces and runner.
  - `warbird_pro_v9` is isolated from `warbird_pro`; it admits ES/MES
    TradingView exports only, ignores NQ/MNQ exports, and models ATR/risk exits
    without Pine edits.
- `scripts/ag/tv_auto_tune.py`, `scripts/ag/tune_strategy_params.py`: TradingView
  settings-trial helpers retained for Pine-derived modeling.
- `artifacts/tuning/`: tuning suggestions, exports, and trial artifacts.
- `app/`, `components/`, `lib/`, `supabase/`: runtime/dashboard/cloud support,
  not active training truth.
- `local_warehouse/`, local `warbird`, and `scripts/ag/train_ag_baseline.py`:
  legacy/reference unless explicitly reopened.

## Contract First

- Pine/TradingView output is the active training truth.
- Modeling inputs come only from TradingView/Pine outputs emitted by
  `indicators/warbird-pro-rebuild-fib-ml.pine` and, for Nexus-only work,
  `indicators/warbird-nexus-machine-learning-rsi-optuna-fast-test.pine`:
  TradingView indicator CSV exports, hidden `ml_*` / `nexus_fp_*` plots,
  TradingView/Pine `request.footprint()` evidence for Nexus, and deterministic
  fields derived from those same Pine outputs.
- The active modeling object is the indicator behavior, not a server-side model.
- The active output is a Pine settings/build recommendation, not a live scoring packet.
- Every modeling run must declare one trigger family:
  `LIVE_ANCHOR_FOOTPRINT` or `NEXUS_FOOTPRINT_DELTA`.
- No external feature stacking: no FRED, macro, news, options, cross-asset, cloud,
  or Databento-ingestion joins in the active modeling dataset.
- Daily/hourly ingestion is not a training source. It may remain for runtime chart
  support only.
- Local legacy warehouse training tables (including `ag_training`) are
  superseded as active model truth. Do not train from them unless Kirk
  explicitly reopens that architecture.

## Stack

- TradingView + Pine Script — canonical live and modeling surface
- Optuna — local offline analysis over Pine-derived rows
- Next.js + Supabase — runtime/dashboard/support only
- Local PG17 `warbird` — legacy/reference for this plan unless explicitly reopened

## Hard Rules

### Data

- No mock, demo, placeholder, or fake data.
- Training/modeling rows must come from real Pine/TradingView exports emitted by
  the active Warbird Pro or Nexus Pine surfaces.
- Do not use daily ingestion, FRED, macro, news, options, or cross-asset joins as
  active training features.
- If an indicator feature is not present in Pine/TradingView output, it is not in
  the active modeling dataset.

### Pine

- Never edit `indicators/warbird-pro-rebuild-fib-ml.pine` without explicit approval
  in the current session.
- Never edit Nexus Pine files without explicit approval in the current session.
- Never push Pine changes to TradingView Pine Editor without explicit approval.
- `indicators/v8-warbird-live.pine`, `indicators/v8-warbird-prescreen.pine`,
  `indicators/warbird-pro-indicator.pine`, `indicators/Warbird_Pro_v7.pine`,
  `indicators/v7-warbird-institutional.pine`, `indicators/v7-warbird-strategy.pine`,
  `indicators/v7-warbird-institutional-backtest-strategy.pine`, and
  `indicators/fibs-only.pine` are retired and removed from the active repo
  surface. Historical references may remain in archived plan docs only.
- The canonical Warbird Pro fib engine in
  `indicators/warbird-pro-rebuild-fib-ml.pine` is protected. Do not modify fib anchor
  ownership, ladder math, or trade-state label semantics without explicit
  approval and before/after TradingView evidence.
- Repo-wide fib scanner guardrail (locked 2026-04-28): never reintroduce the
  pivot-window `fibHtfSnapshot` variant that uses `ta.barssince(...)` and
  `pivotHighInWindow` / `pivotLowInWindow`. That pattern is banned due to
  repeated wide-fib regressions.
- Pine budget baseline verified 2026-05-02:
  - `warbird-pro-rebuild-fib-ml.pine`: 28 output calls (plot family), 0
    alertcondition calls, 3 `request.security()` calls, and no
    `request.footprint()` path in the main indicator
  - Nexus files are retained; price their request/output budget before any
    Nexus edit.
- Price every new output or request path before writing Pine code.
- Nexus `request.footprint()` is budget-sensitive and must be cached per bar.

### TradingView Live Safety Lock

- Never force-launch, force-restart, or process-kill TradingView from automation.
- Banned methods include `tv_launch`, `launch_tv_debug_mac.sh`,
  `pkill -f TradingView`, and `killall TradingView`.
- Live TV operations are one explicit command at a time, no retry loops.
- On the first CDP/bridge failure, stop immediately and report the failure.
- If CDP is unavailable, do not attempt recovery automation; stay read-only
  until the user explicitly requests a manual next step.
- Legacy MCP bridge path (`scripts/ag/run_phase_batch_via_tv_bridge.py` +
  `scripts/ag/tv_bridge_worker.mjs`) is disabled by default; use direct CDP
  flow via `scripts/ag/tv_auto_tune.py`.

### Pine Verification

If any `.pine` file is touched, run:

1. pine-facade compile check
2. `./scripts/guards/pine-lint.sh <file>`
3. `./scripts/guards/check-fib-scanner-guardrails.sh`
4. `./scripts/guards/check-contamination.sh`
5. `./scripts/guards/check-no-tv-force.sh`
6. `npm run build`
7. Do not run indicator/strategy parity unless a new strategy harness is
   explicitly approved; no active strategy Pine file exists in `indicators/`.

### Backtesting And Modeling

- If a strategy/backtest harness is explicitly reopened, MES commission floor is
  $1.00/side and slippage floor is 1 tick.
- If a strategy/backtest harness is explicitly reopened, use Bar Magnifier when
  reported results depend on intrabar stop/target behavior.
- Champion settings require IS/OOS or walk-forward-style review.
- Do not accept a settings result without indicator export evidence, manifest,
  row count, date range, exact Pine inputs, and the emitted label/export fields
  used by the run.
- Warbird Pro V9 must not use `-.236` or other negative fib extensions as stop
  candidates. `-.236` may remain only as a context/export feature while V9
  models ATR/risk exits.
- Warbird Pro V9 must ingest ES/MES TradingView exports only and ignore NQ/MNQ
  exports.
- Do not start training/modeling unless explicitly asked.
- Nexus ML RSI Optuna must use TradingView/Pine `request.footprint()`
  `nexus_fp_*` evidence only. Do not tune Nexus from CSV exports, local OHLCV
  parquet, Databento bars, or synthetic body/wick delta.

### Cloud And Database

- Cloud Supabase is runtime/support only. It must not receive raw trials,
  labels, or full research datasets.
- Local `warbird` warehouse and old local lineage tables are reference-only for
  this plan.
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

The old warehouse modeling skills and docs remain lineage only. Do not use
`training-full-zoo`, `training-pre-audit`, `training-shap`, `training-monte-carlo`,
or local `ag_training` workflows for active modeling unless Kirk explicitly
reopens the warehouse training architecture.
