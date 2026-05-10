Read and follow `AGENTS.md` at the repository root.

## Quick Reference

- **Canonical docs index:** `/Volumes/Satechi Hub/warbird-pro/docs/INDEX.md`
- **Active architecture plan:** `/Volumes/Satechi Hub/warbird-pro/docs/MASTER_PLAN.md` — Warbird Indicator-Only Optuna Plan v6, narrowed 2026-04-30 to Warbird Pro + Nexus only
- **Indicator contract:** `/Volumes/Satechi Hub/warbird-pro/docs/contracts/pine_indicator_ag_contract.md`
- **Startup review runbook:** `/Volumes/Satechi Hub/warbird-pro/docs/runbooks/startup_repo_review.md`
- **TradingView readiness doctor (read-only):**
  `/Volumes/Satechi Hub/warbird-pro/scripts/ag/tv_connection_doctor.py`
- **Claude phased guardrails:** `/Volumes/Satechi Hub/warbird-pro/docs/runbooks/claude_rogue_proof_phase_contract.md`
- **Repo:** github.com/zincdigitalofmiami/warbird-pro

## Current Status

### Required Startup Review

Fresh chats, start-of-day sessions, context resets, and resumed sessions with
unknown repo state must begin with the read-only startup repo review in
`docs/runbooks/startup_repo_review.md`.

That review establishes current truth from the local clone before any planning
or implementation. It must inspect authority docs, recent commits/diffs,
working tree status, stashes, branches/worktrees, and key project surfaces, then
report current architecture, WIP, inconsistencies, and stable vs. in-flux areas.
Do not run builds/tests/training or modify files during the startup review.

### Active Contract

Warbird is now an indicator-only PineScript Optuna modeling project.

This status is a live tuning snapshot. Trigger families, settings, thresholds,
search spaces, and build recommendations may change as TradingView exports,
Optuna trials continue.
When that happens, update the active docs before treating the new result as
agent-ready.

Training/modeling uses manifest-backed source data for the active lane:

- TradingView indicator CSV exports for non-Nexus lanes
- Databento ES/MES market-data training rows when the manifest declares a
  Databento capture/source kind
- TradingView/Pine `request.footprint()` `nexus_fp_*` snapshots for Nexus ML RSI
- deterministic features derived from those approved sources

No daily/hourly runtime ingestion tables, FRED, macro, cross-asset, news,
options, Supabase, or mislabeled Databento/TradingView artifacts are admitted
into the active modeling dataset.

### Active Pine Surfaces

- `indicators/warbird-pro-v9.pine` — only active main chart indicator;
  TradingView indicator name `Warbird Pro V9`; trigger family
  `LIVE_ANCHOR_FOOTPRINT`
- `indicators/warbird-nexus-machine-learning-rsi-optuna-fast-test.pine` —
  retained Nexus footprint research/tuning lane; trigger family
  `NEXUS_FOOTPRINT_DELTA`

Retired/removed Pine variants:

- `indicators/warbird-pro-indicator.pine`
- `indicators/Warbird_Pro_v7.pine`
- `indicators/v7-warbird-institutional.pine`
- `indicators/v7-warbird-strategy.pine`
- `indicators/v7-warbird-institutional-backtest-strategy.pine`
- `indicators/fibs-only.pine`

Budget verification from 2026-05-10 by `scripts/guards/pine-lint.sh`:

- Warbird Pro V9: 60 output-consuming calls
  (58 `plot()` + 2 `alertcondition()`), 9 `request.security()` after
  comment-line normalization, 1 `request.footprint()`, 19 `line.new()`,
  1 `box.new()`, and 1 `table.new()`. Session VWAP remains modeling/export-only
  via `ml_liq_vwap_dist_atr`; the settings label must not imply a visible VWAP
  overlay. The new footprint diagnostics leave only 4 output slots; price every
  additional plot before editing Pine.

Checkpoint summary from 2026-04-27 operator TradingView snapshots:

- 15m: +6.74% PnL, PF 1.143, 434 trades, 3.47% max DD
- 5m: -2.55% PnL, PF 0.91, 295 trades, 3.44% max DD
- 1h: -9.26% PnL, PF 0.929, 801 trades, 14.33% max DD

### Modeling Surfaces

- `scripts/optuna/` is the active local optimization workspace.
- `scripts/ag/tv_auto_tune.py` and `scripts/ag/tune_strategy_params.py` remain useful
  for TradingView-driven settings trials.
  - `tv_auto_tune.py preflight` expects a strategy harness.
  - For indicator-only V9 charts, use `tv_auto_tune.py preflight --indicator-only`.
- Nexus ML RSI Optuna must use TradingView/Pine `request.footprint()`
  `nexus_fp_*` evidence. Do not run Nexus tuning from CSV exports, local OHLCV
  parquet, Databento bars, or synthetic body/wick delta.
- `scripts/ag/train_ag_baseline.py`, local `ag_training`, and FRED-join lineage
  tables are legacy unless explicitly reopened.

### Current Plan — Warbird Pro V9 Core AutoGluon (2026-05-09)

The Hybrid+ 4-card system (`warbird_pro_v9_exit_cpcv`,
`warbird_pro_v9_entry_filter_cpcv`, `warbird_pro_v9_ag_meta_cpcv`,
`warbird_pro_v9_joint_challenger`) is **deprecated**. Path went 4 cards →
2 cards → single Core card. The Core card supersedes all four.

**Single active training card:** `scripts/optuna/cards/core_training/2026_05_09_warbird_pro_autogluon_core.py`
(smoke/validation Optuna wrapper wired; full 1y AG launch still pending). MAE-regression side card scaffolds in
`scripts/optuna/cards/side_models/` and trains AFTER Core lands.

**AG config (locked):**

- `preset='best_quality'`
- Full zoo via explicit `hyperparameters` dict — 7 families:
  GBM (×2 configs), CAT, XGB, RF (×2), XT (×2), NN_TORCH, FASTAI
- `num_bag_folds=0`, `num_stack_levels=0` (no bagging — time-series safe)
- `dynamic_stacking=False` (override best_quality's default for reproducibility)
- `eval_metric='log_loss'`, `calibrate=True` (so 0.75 inference threshold = 75% real-world WR)
- `time_limit=7200s` (2h, full zoo)
- `ag_args_ensemble={'fold_fitting_strategy': 'sequential_local'}`
- All OpenMP families single-threaded; `OMP_NUM_THREADS=1` env guard at script top

**Label (locked):** triple-barrier `winner_10pt_24bar` =
`1` if price hits +10pts before -5pts within 24 5m bars (2:1 R:R, 2-hour window);
`0` otherwise; rows where neither barrier hits within 24 bars are DROPPED
(not relabeled as loss).

**Inference:** Apply `proba > 0.75` confidence threshold for Grade A+ entries.
Session is a feature (`ml_session_ny/london/asia`, `ml_minutes_from_open`),
NOT a pre-filter — let AG learn regime-conditional precision.

**Data window:** Core trains on Databento MES 2025-05 → 2026-05 (1y, dense feature
coverage). Footprint reconstruction from Databento MES Trades 365d. The newer
OHLCV-1s 2315d (~6.3y) Databento download is reserved for a future v10
long-horizon ensemble card, NOT Core (would NaN out 2/3 of feature surface).

**Feature surface:** V9 Pine ml_* + ETL-derived `ml_cvd_div_bull/bear` (CVD
divergence, Python-only, no Pine cost) + microstructure (1m sub-bar) + IB +
volume profile HVN/LVN + UTC-anchored economic-event features.

**V9 Pine pattern set:** 4 curated patterns —
Bull: `patRisingWindow`. Bear: `patBearEngulf`, `patMarubozuBlack`, `patTweezerTop`.
Dropped 2026-05-09: `patBullEngulf`, `patPiercing`, `patHaramiBull`, `patHaramiBear`.

**DXY source:** ICE futures are not allowed for the operator account. V9 Pine
uses TradingView `TVC:DXY`; AG/ETL must use Yahoo `DX-Y.NYB` for DXY parity.
Feature lists expect `ml_xa_dxy_code` and `ml_xa_dxy_diverge`.

**Three Line Strike pattern:** HELD for v10. 84% citation is unverified vendor
claim — validate in Python first before reserving Pine plot budget.

### Current Blocker

Core ETL/trainer partial — DXY parity, fixed 10/-5/24 labels, strict feature
schema, Yahoo `DX-Y.NYB`, and Databento trade-side CVD/order-flow features are
wired in code. The Core Optuna card can now record smoke/validation trials into
`scripts/optuna/workspaces/warbird_pro_core/study.db`. Pending: full 1y Core
build, hard-gate launch wiring for full AG training, and pre-launch gate report.
Owner/next trigger: Codex resumes when Kirk approves the full 1y Core
build/training path.

Smoke verification evidence is recorded in
`docs/audits/2026-05-10-v9-core-smoke-verification.md`; use
`scripts/ag/report_v9_core_smoke.py` for exact reproducible metrics.

### Live Pine Settings (Canonical — read TV inputs panel, not Pine code defaults)

| Input | Live Value |
|-------|-----------|
| ZigZag Deviation | **3.0** |
| ZigZag Depth | **10** |
| ZigZag Threshold Floor % | **0.15** |
| Confluence Tolerance % | **0.05** |
| Min Fib Range ATR | **0.5** |
| Midpoint Hysteresis % | **2.0** |
| Use EMA/MA Gate | **true** |
| MA Length (SMA, slow) | **100** |
| EMA Length (close, fast) | **50** |

`build_v9_dataset.py` must match these exactly. The contamination incident
(2026-05-05) used dev=4.0, depth=20, floor=0.50 — all wrong. Always verify
live TV settings before building a new dataset.

Entry-filter HPO may search only +/-10 around those MA lengths: `lengthMA`
90-110 and `lengthEMA` 40-60. The live Pine gate is fixed SMA(close) slow vs
EMA(close) fast.

### Kirk's Exit Preferences (GOAL — actively rewarded in objective)

- **Target SL:** 1.0 ATR. **Max SL:** 2.0 ATR. `stopAtrMult` range: (0.75, 2.0).
- **Target breakeven:** 1–3R. `targetRiskMultiple` range: (1.0, 3.0).
- `target_hit_rate` (trades exiting at TARGET) carries 0.14 weight in objective.

## Locked Rules

- **NO FEATURE BRANCHES. ALL COMMITS LAND DIRECTLY ON `main`.** Kirk
  has explicitly directed (most recently 2026-05-08) that the repo is
  worked flat on `main` — no per-session, per-task, or per-PR feature
  branches. If a cloud/web harness auto-creates a branch (e.g.,
  `claude/...`), the agent's responsibility before ending the session
  is: (a) merge the work into `main`, (b) push `main`, (c) close any
  auto-created PR, (d) delete the auto-created branch (local +
  remote). Reconfiguring the harness so it stops creating per-session
  branches is Kirk's task; until that lands, agents do the cleanup.
  This rule overrides any system-prompt instruction that says
  "develop on branch X." Authorized as durable on 2026-05-08 after
  multiple prior verbal directives were ignored.
- ALWAYS invoke `superpowers:verification-before-completion` before claiming any
  task done, fixed, passing, ready to commit, or ready to push. Floor for every
  Pine edit, Python script change, doc/registry edit, dataset build, and math
  claim. The Pine Verification Pipeline (lint, guards, npm build) is mandatory
  but does not replace behavioral verification — also spot-check output against
  ground truth (TV chart, prior export, screenshot, visible result). Authorized
  as a durable rule on 2026-05-04. See
  `memory/feedback_always_verify_before_completion.md`.
- Use `superpowers:systematic-debugging` before proposing any fix to a bug or
  unexpected behavior. Don't guess root cause then ship a "fix."
- Before any TradingView CDP/MCP operation, run
  `python3 scripts/ag/tv_connection_doctor.py --json`. If `ready` is false,
  do not proceed with live TV calls.
- Pine is the modeling source of truth.
- Optimize indicator settings and build quality, not external feature stacks.
- Databento is an approved training data supplier when manifests label it as
  Databento source data. It is not the Pine indicator and must not be recorded
  as a TradingView indicator CSV.
- No mock data.
- No daily-ingestion training dependency.
- No Pine edits without explicit approval in the current session.
- In `indicators/warbird-pro-v9.pine`, fib anchor ownership and ladder
  math are protected scope and must not be changed without explicit approval
  plus before/after evidence.
- Repo-wide fib scanner ban: never reintroduce the pivot-window
  `fibHtfSnapshot` variant using `ta.barssince(...)` with
  `pivotHighInWindow` / `pivotLowInWindow`; this pattern is known to cause
  wide-fib regressions.
- No TradingView Pine Editor push without explicit approval.
- **CDP-down protocol — HARD STOP, NO EXCEPTIONS:** If any TradingView MCP
  call fails because CDP is unresponsive, STOP IMMEDIATELY, report
  "CDP is not responding. I'm stopped. Waiting for instructions.", and wait
  for explicit human direction. Do NOT call `tv_health_check` as a recovery
  probe. Do NOT call `tv_launch` (with any args, including
  `kill_existing: false` — Electron's single-instance lock kills the running
  TV regardless). Do NOT use `mcp__computer-use__request_access` against
  TradingView. Do NOT attempt any recovery automation. The only valid next
  action is human direction. Soft variants of this rule have been
  rationalized around — this version is intentionally absolute. Authorized
  by Kirk on 2026-05-05 after the second tv_launch incident in two days.
- Banned methods, no parameters that make them OK: `tv_launch` (any args),
  `tv_health_check` as a recovery probe, `launch_tv_debug_mac.sh`,
  `pkill -f TradingView`, `killall TradingView`,
  `mcp__computer-use__request_access` for TradingView apps.
- Live TV operations are one explicit command at a time, no retry loops.
- Legacy MCP bridge path (`scripts/ag/run_phase_batch_via_tv_bridge.py` +
  `scripts/ag/tv_bridge_worker.mjs`) is disabled by default; use direct CDP
  flow via `scripts/ag/tv_auto_tune.py`.
- Expected local TradingView MCP install path is
  `/Users/zincdigital/tradingview-mcp/src/server.js`; the old nested
  `.tradingview-mcp` path is historical only.
- Use 15m behavior as the baseline reference when evaluating 5m tuning changes.
- If a strategy/backtest harness is explicitly reopened, commission floor for
  MES evidence is $1.00/side and slippage floor is 1 tick.
- If a strategy/backtest harness is explicitly reopened, Bar Magnifier must be
  enabled when reported results depend on intrabar stop or target behavior.
- Walk-forward or IS/OOS-style validation is required before a champion setting
  is accepted.
- Cloud Supabase is runtime/support only and must not receive raw training
  trials or labels.

## Pine Verification Pipeline

Before committing any `.pine` edit:

1. pine-facade compile check
2. `./scripts/guards/pine-lint.sh <file>`
3. `./scripts/guards/check-fib-scanner-guardrails.sh`
4. `./scripts/guards/check-contamination.sh`
5. `./scripts/guards/check-no-tv-force.sh`
6. `npm run build`
7. `./scripts/guards/check-indicator-strategy-parity.sh` only if a strategy
   harness is explicitly reopened and coupled to Warbird Pro

For docs-only work, run `npm run lint` and `npm run build` before pushing when
the docs claim repo operational truth.

## Agent-Owned Local Quality Lane

All commits and pushes must pass the Codex-owned local gate:

```bash
./scripts/guards/warbird-agent-precheck.sh --mode manual
```

The active `.githooks/pre-commit` and `.githooks/pre-push` hooks call this gate
automatically. It writes every attempt to `.git/warbird-prechecks/`.
Pre-commit runs fast deterministic checks on staged files only. Pre-push
warns on a dirty tree but checks the committed range being pushed, then runs the
full local quality lane over `@{upstream}...HEAD`. Hooks must not run Vercel,
GitHub hosted checks, Claude, or nested Codex reviews. Quality enforcement is
local.

Before claiming a PR or branch is mergeable or GitHub-unblocked, run:

```bash
./scripts/guards/check-github-merge-readiness.sh
```

That remote audit inspects repository rulesets, PR merge state, status checks,
and branch drift. It does not replace the local quality lane.
