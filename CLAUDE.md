Read and follow `AGENTS.md` at the repository root.

## Quick Reference

- **Canonical docs index:** `/Volumes/Satechi Hub/warbird-pro/docs/INDEX.md`
- **Active architecture plan:** `/Volumes/Satechi Hub/warbird-pro/docs/MASTER_PLAN.md` — Warbird Indicator-Only AG Plan v6
- **Indicator contract:** `/Volumes/Satechi Hub/warbird-pro/docs/contracts/pine_indicator_ag_contract.md`
- **Repo:** github.com/zincdigitalofmiami/warbird-pro
- **Optuna Hub:** `http://127.0.0.1:8090/`
- **Nexus Optuna lane:** `http://127.0.0.1:8090/studies/warbird_nexus_ml_rsi`

## Current Status

### Active Contract

Warbird is now an indicator-only PineScript AG modeling project.

This status is a live tuning snapshot. Trigger families, settings, thresholds,
search spaces, and build recommendations may change as TradingView exports,
Strategy Tester evidence, Optuna trials, AG analysis, and SHAP review continue.
When that happens, update the active docs before treating the new result as
agent-ready.

Training/modeling uses Pine/TradingView outputs only:

- TradingView indicator CSV exports
- TradingView Strategy Tester trade exports
- CDP-read Strategy Tester data from local tooling
- deterministic features derived from those Pine outputs

No daily/hourly ingestion, FRED, macro, cross-asset, news, options, Supabase, or
Databento feature stacking is admitted into the active modeling dataset.

### Active Pine Surfaces

- `indicators/v7-warbird-institutional.pine` — live indicator work surface;
  trigger family `LIVE_ANCHOR_FOOTPRINT`
- `indicators/v7-warbird-strategy.pine` — Strategy Tester / export-compatible
  surface; trigger family `STRATEGY_ACCEPT_SCALP`
- `indicators/v7-warbird-institutional-backtest-strategy.pine` —
  Optuna/backtest wrapper; trigger family `BACKTEST_DIRECT_ANCHOR` when
  `Backtest Fib Anchor Hits Directly` is enabled
- `indicators/warbird-nexus-machine-learning-rsi-optuna-fast-test.pine` —
  Nexus lower-pane footprint-delta research surface; trigger family
  `NEXUS_FOOTPRINT_DELTA`

Budget verification from 2026-04-26:

- institutional: 58/64 output calls, 4 `request.security()` + 1 `request.footprint()`
- v7 strategy: 60/64 output calls, 4 `request.security()` + 1 `request.footprint()`
- backtest strategy: 53/64 output calls, 4 `request.security()` + 1 `request.footprint()`

### Modeling Surfaces

- `scripts/optuna/` is the active local optimization workspace.
- The canonical local hub is `http://127.0.0.1:8090/`. Do not create sidecar
  hubs or alternate workspaces for active Warbird lanes.
- Nexus ML RSI tuning uses the existing lane
  `http://127.0.0.1:8090/studies/warbird_nexus_ml_rsi`, the existing workspace
  `scripts/optuna/workspaces/warbird_nexus_ml_rsi`, the existing default study
  name `Warbird Nexus ML Fast 5m Signal Quality April 25`, and `1000` trials
  for the current batch size.
- `scripts/ag/tv_auto_tune.py` and `scripts/ag/tune_strategy_params.py` remain useful
  for TradingView-driven settings trials.
- `scripts/ag/train_ag_baseline.py`, local `ag_training`, FRED joins, and SHAP lineage
  tables are legacy unless explicitly reopened.

### Current Blocker

Active optimization scripts and runbooks must point at the canonical hub before
any run is launched. Nexus work must resume the existing hub lane; do not create
a new hub, workspace, or study name for the current Nexus tuning batch.

## Locked Rules

- Pine is the modeling source of truth.
- Optimize indicator settings and build quality, not external feature stacks.
- No mock data.
- No daily-ingestion training dependency.
- No Pine edits without explicit approval in the current session.
- No TradingView Pine Editor push without explicit approval.
- Commission floor for MES Strategy Tester evidence: $1.00/side.
- Slippage floor: 1 tick.
- Bar Magnifier must be enabled when reported results depend on intrabar stop or
  target behavior.
- Walk-forward or IS/OOS-style validation is required before a champion setting
  is accepted.
- Cloud Supabase is runtime/support only and must not receive raw training
  trials, labels, or SHAP artifacts.

## Pine Verification Pipeline

Before committing any `.pine` edit:

1. pine-facade compile check
2. `./scripts/guards/pine-lint.sh <file>`
3. `./scripts/guards/check-contamination.sh`
4. `npm run build`
5. `./scripts/guards/check-indicator-strategy-parity.sh` when v7 indicator /
   strategy coupling is touched

For docs-only work, run `npm run lint` and `npm run build` before pushing when
the docs claim repo operational truth.
