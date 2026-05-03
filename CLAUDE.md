Read and follow `AGENTS.md` at the repository root.

## Quick Reference

- **Canonical docs index:** `/Volumes/Satechi Hub/warbird-pro/docs/INDEX.md`
- **Active architecture plan:** `/Volumes/Satechi Hub/warbird-pro/docs/MASTER_PLAN.md` — Warbird Indicator-Only Optuna Plan v6, narrowed 2026-04-30 to Warbird Pro + Nexus only
- **Indicator contract:** `/Volumes/Satechi Hub/warbird-pro/docs/contracts/pine_indicator_ag_contract.md`
- **Startup review runbook:** `/Volumes/Satechi Hub/warbird-pro/docs/runbooks/startup_repo_review.md`
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

Training/modeling uses Pine/TradingView outputs only:

- TradingView indicator CSV exports for non-Nexus lanes
- TradingView/Pine `request.footprint()` `nexus_fp_*` snapshots for Nexus ML RSI
- deterministic features derived from those Pine outputs

No daily/hourly ingestion, FRED, macro, cross-asset, news, options, Supabase, or
Databento feature stacking is admitted into the active modeling dataset.

### Active Pine Surfaces

- `indicators/warbird-pro-rebuild-fib-ml.pine` — only active main chart indicator;
  trigger family `LIVE_ANCHOR_FOOTPRINT`
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

Budget verification from 2026-05-02:

- Warbird Pro rebuild: 28 output calls (plot family), 0 alertcondition calls,
  3 `request.security()`, and no `request.footprint()` in the main indicator

Checkpoint summary from 2026-04-27 operator TradingView snapshots:

- 15m: +6.74% PnL, PF 1.143, 434 trades, 3.47% max DD
- 5m: -2.55% PnL, PF 0.91, 295 trades, 3.44% max DD
- 1h: -9.26% PnL, PF 0.929, 801 trades, 14.33% max DD

### Modeling Surfaces

- `scripts/optuna/` is the active local optimization workspace.
- `scripts/ag/tv_auto_tune.py` and `scripts/ag/tune_strategy_params.py` remain useful
  for TradingView-driven settings trials.
- Nexus ML RSI Optuna must use TradingView/Pine `request.footprint()`
  `nexus_fp_*` evidence. Do not run Nexus tuning from CSV exports, local OHLCV
  parquet, Databento bars, or synthetic body/wick delta.
- `scripts/ag/train_ag_baseline.py`, local `ag_training`, and FRED-join lineage
  tables are legacy unless explicitly reopened.

### Current Blocker

Execute controlled 5m/15m tuning on
`indicators/warbird-pro-rebuild-fib-ml.pine` with manifest-backed evidence, and
keep Nexus footprint work isolated to the retained
`NEXUS_FOOTPRINT_DELTA` lane. Do not start training/modeling unless the user
explicitly approves it.

## Locked Rules

- Pine is the modeling source of truth.
- Optimize indicator settings and build quality, not external feature stacks.
- No mock data.
- No daily-ingestion training dependency.
- No Pine edits without explicit approval in the current session.
- In `indicators/warbird-pro-rebuild-fib-ml.pine`, fib anchor ownership and ladder
  math are protected scope and must not be changed without explicit approval
  plus before/after evidence.
- Repo-wide fib scanner ban: never reintroduce the pivot-window
  `fibHtfSnapshot` variant using `ta.barssince(...)` with
  `pivotHighInWindow` / `pivotLowInWindow`; this pattern is known to cause
  wide-fib regressions.
- No TradingView Pine Editor push without explicit approval.
- Never force-launch, force-restart, or process-kill TradingView from automation.
- Banned methods: `tv_launch`, `launch_tv_debug_mac.sh`,
  `pkill -f TradingView`, `killall TradingView`.
- Live TV operations are one explicit command at a time, no retry loops.
- On first CDP/bridge failure: stop and report; do not run recovery automation.
- Legacy MCP bridge path (`scripts/ag/run_phase_batch_via_tv_bridge.py` +
  `scripts/ag/tv_bridge_worker.mjs`) is disabled by default; use direct CDP
  flow via `scripts/ag/tv_auto_tune.py`.
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
