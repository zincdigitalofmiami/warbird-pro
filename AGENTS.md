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

### Governance Precedence (Conflict Resolver)

When docs conflict, precedence is:

1. Hard safety rules are immutable top priority unless Kirk explicitly revokes them.
2. Dated decision records define current direction when summaries lag.
3. Summary docs (`AGENTS.md`, `CLAUDE.md`, `docs/MASTER_PLAN.md`, runbooks) are derived operational views and must not override (1) or (2).

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
- keep `indicators/warbird-pro-v9.pine` as the only active main chart
  indicator, named **Warbird Pro V9** in TradingView
- keep `warbird_pro_v9` as a separate Optuna lane for ES/MES-only ATR/risk exit
  modeling over active Warbird Pro V9 training rows
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
- Before any TradingView CDP/MCP operation, run
  `python3 scripts/ag/tv_connection_doctor.py --json` (read-only). Treat
  `ready: true` as the only "safe to proceed" signal.

## Repo Map

- `indicators/`: active Pine sources:
  - `indicators/warbird-pro-v9.pine` — only main chart indicator
  - `indicators/warbird-nexus-machine-learning-rsi-optuna-fast-test.pine` —
    Nexus Optuna/footprint evidence lane (retained support/research lane)
- `scripts/optuna/`: active local optimization workspaces and runner.
  - `warbird_pro_v9` is isolated from `warbird_pro`; it admits ES/MES
    training rows from TradingView exports or Databento market data, ignores
    NQ/MNQ rows, and models ATR/risk exits without Pine edits.
  - Hybrid+ 4-card chain is deprecated; active direction is the single
    `warbird_pro_core` training card (Core module scaffold under construction).
  - Dataset: `workspaces/warbird_pro_v9/exports/mes_5m.csv` (441,852 5m bars, clean build dd81ebf)
  - Build script: `workspaces/warbird_pro_v9/build_v9_dataset.py` — params MUST match live TV settings
- `scripts/ag/tv_auto_tune.py`, `scripts/ag/tune_strategy_params.py`: TradingView
  settings-trial helpers retained for Pine-derived modeling.
  `tv_auto_tune.py preflight` requires a strategy harness; use
  `tv_auto_tune.py preflight --indicator-only` for V9 indicator-only sessions.
- `artifacts/tuning/`: tuning suggestions, exports, and trial artifacts.
- `app/`, `components/`, `lib/`, `supabase/`: runtime/dashboard/cloud support,
  not active training truth.
- `local_warehouse/`, local `warbird`, and `scripts/ag/train_ag_baseline.py`:
  legacy/reference unless explicitly reopened.

## Live Pine Settings (Authoritative — 2026-05-05)

These are the LIVE values from the TradingView indicator inputs panel.
The Pine code `input.float(default, ...)` values are NOT authoritative.
`build_v9_dataset.py` constants must match these exactly before every dataset build.

| Setting | Live Value |
|---------|-----------|
| ZigZag Deviation (fibDeviationManual) | **3.0** |
| ZigZag Depth (fibDepthManual) | **10** |
| ZigZag Threshold Floor % (fibThresholdFloorPct) | **0.15** |
| Confluence Tolerance % (fibConfluenceTolPct) | **0.05** |
| Min Fib Range ATR (minFibRangeAtr) | **0.5** |
| Midpoint Hysteresis % (fibHysteresisPct) | **2.0** |
| MA Length SMA (lengthMA) | **13** |
| EMA Length (lengthEMA) | **6** |

## Kirk's Exit Trade Preferences (GOAL — Rewarded in Objective)

- **Target SL:** 1.0 ATR. **Max SL:** 2.0 ATR. Search range: `stopAtrMult` (0.75, 2.0).
- **Target breakeven:** 1–3R. `targetRiskMultiple` range: (1.0, 3.0).
- Objective scores `target_hit_rate` (fraction of trades exiting at TARGET) at weight 0.14.
- Never freeze SL or target — Optuna searches the range; the goal values are the reward center.

## Contract First

- Pine/TradingView output is the active training truth.
- Modeling inputs come from manifest-backed training data for the active lane:
  TradingView/Pine outputs emitted by `indicators/warbird-pro-v9.pine`,
  Databento ES/MES market-data training rows when declared as Databento source
  data, and, for Nexus-only work,
  `indicators/warbird-nexus-machine-learning-rsi-optuna-fast-test.pine`
  TradingView/Pine `request.footprint()` evidence.
- The active modeling object is the indicator behavior, not a server-side model.
- The active output is a Pine settings/build recommendation, not a live scoring packet.
- Every modeling run must declare one trigger family:
  `LIVE_ANCHOR_FOOTPRINT` or `NEXUS_FOOTPRINT_DELTA`.
- No external feature stacking: no FRED, macro, news, options, cross-asset, or
  cloud joins in the active modeling dataset.
- Databento is an approved market-data supplier for training rows when the
  manifest honestly declares a Databento capture/source kind. It is not the
  Pine indicator, not a TradingView indicator CSV, and not a substitute for
  V9/Nexus trigger-family identity. Use official Databento
  historical/batch/OHLCV/continuous-contract references
  ([get_range](https://databento.com/docs/api-reference-historical/timeseries/timeseries-get-range?historical=python&live=python&reference=python),
  [batch downloads](https://databento.com/docs/examples/basics-historical/programmatic-batch-download),
  [OHLCV resampling](https://databento.com/docs/examples/basics-historical/ohlcv-resampling?historical=python&live=python&reference=python),
  [continuous contracts](https://databento.com/docs/examples/symbology/continuous?historical=python&live=python&reference=python))
  and keep the manifest honest.
- Daily/hourly ingestion is not a training source. It may remain for runtime chart
  support only.
- Local legacy warehouse training tables (including `ag_training`) are
  superseded as active model truth. Do not train from them unless Kirk
  explicitly reopens that architecture.

## Stack

- TradingView + Pine Script — canonical live and modeling surface
- Optuna — local offline analysis over approved manifest-backed source rows
- Next.js + Supabase — runtime/dashboard/support only
- Local PG17 `warbird` — legacy/reference for this plan unless explicitly reopened

## Hard Rules

### Data

- No mock, demo, placeholder, or fake data.
- Training/modeling rows must come from real manifest-backed active-lane
  sources: Warbird Pro V9 Pine/TradingView exports, approved Databento ES/MES
  market-data training rows, or Nexus Pine/TradingView footprint evidence.
- Do not use daily ingestion, FRED, macro, news, options, or cross-asset joins as
  active training features.
- If an indicator feature is not present in Pine/TradingView output, it is not in
  the active modeling dataset.

### Pine

- Never edit `indicators/warbird-pro-v9.pine` without explicit approval
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
  `indicators/warbird-pro-v9.pine` is protected. Do not modify fib anchor
  ownership, ladder math, or trade-state label semantics without explicit
  approval and before/after TradingView evidence.
- Repo-wide fib scanner guardrail (locked 2026-04-28): never reintroduce the
  pivot-window `fibHtfSnapshot` variant that uses `ta.barssince(...)` and
  `pivotHighInWindow` / `pivotLowInWindow`. That pattern is banned due to
  repeated wide-fib regressions.
- Pine budget baseline verified 2026-05-09 by `scripts/guards/pine-lint.sh`:
  - `warbird-pro-v9.pine`: 53 output-consuming calls
    (51 `plot()` + 2 `alertcondition()`), 9 `request.security()` calls
    after comment-line normalization, 1 `request.footprint()` call,
    19 `line.new()` calls, 1 `box.new()`, and 1 `table.new()`
  - Nexus files are retained; price their request/output budget before any
    Nexus edit.
- Price every new output or request path before writing Pine code.
- Nexus `request.footprint()` is budget-sensitive and must be cached per bar.

### TradingView Live Safety Lock

- **CDP-down protocol — HARD STOP, NO EXCEPTIONS:** If any TradingView MCP
  call fails because CDP is unresponsive, STOP IMMEDIATELY, report "CDP is
  not responding. I'm stopped. Waiting for instructions.", and wait for
  explicit human direction. Do NOT call `tv_health_check` as a recovery
  probe (no "let me just double-check"). Do NOT call `tv_launch` with any
  args (including `kill_existing: false` — Electron's single-instance lock
  kills the running TV regardless of the parameter). Do NOT use
  `mcp__computer-use__request_access` against TradingView. Do NOT attempt
  any recovery automation. The only valid next action is human direction.
  Soft variants of this rule have been rationalized around — this version
  is intentionally absolute. Authorized by Kirk on 2026-05-05 after the
  second tv_launch incident in two days.
- Banned methods, no args make them OK: `tv_launch` (any args),
  `tv_health_check` as a recovery probe, `launch_tv_debug_mac.sh`,
  `pkill -f TradingView`, `killall TradingView`,
  `mcp__computer-use__request_access` for TradingView apps.
- Live TV operations are one explicit command at a time, no retry loops.
- Legacy MCP bridge path (`scripts/ag/run_phase_batch_via_tv_bridge.py` +
  `scripts/ag/tv_bridge_worker.mjs`) is disabled by default; use direct CDP
  flow via `scripts/ag/tv_auto_tune.py`.
- Use `/Users/zincdigital/tradingview-mcp/src/server.js` as the expected
  local TradingView MCP server path for Codex/CLI health checks. The removed
  nested repo path `.tradingview-mcp/src/server.js` is historical only.

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
- Warbird Pro V9 must ingest ES/MES training rows only, whether sourced from
  TradingView exports or Databento market data, and must ignore NQ/MNQ rows.
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
- Hosted platform checks are not part of the local gate. Vercel remains outside
  this precheck path. Codex-owned pre-commit/pre-push verification is enforced
  through `.githooks/pre-commit` and `.githooks/pre-push`, which call
  `./scripts/guards/warbird-agent-precheck.sh`.
- `warbird-agent-precheck.sh` must create a `.git/warbird-prechecks/` audit log
  on every commit/push attempt. Pre-commit runs fast deterministic checks on the
  staged file set only. Pre-push warns on a dirty tree but checks the committed
  range being pushed, then runs the full local quality lane over
  `@{upstream}...HEAD`. Do not run Vercel, GitHub
  hosted checks, Claude, or nested Codex reviews from git hooks.
- Before claiming a PR or branch is mergeable or GitHub-unblocked, run
  `./scripts/guards/check-github-merge-readiness.sh` to inspect remote rulesets,
  PR merge state, status checks, and branch drift.
- Vercel Git rebuilds/comments are disabled by repo config
  (`vercel.json`: `git.deploymentEnabled: false`, `github.silent: true`) and
  by disconnected Vercel Git integration (`vercel git disconnect`).
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
