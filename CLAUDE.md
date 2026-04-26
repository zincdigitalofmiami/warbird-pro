Read and follow `AGENTS.md` at the repository root.

## Quick Reference

- **Canonical docs index:** `/Volumes/Satechi Hub/warbird-pro/docs/INDEX.md`
- **Active architecture plan:** `/Volumes/Satechi Hub/warbird-pro/docs/MASTER_PLAN.md` — Warbird Indicator-Only AG Plan v6
- **Indicator contract:** `/Volumes/Satechi Hub/warbird-pro/docs/contracts/pine_indicator_ag_contract.md`
- **Repo:** github.com/zincdigitalofmiami/warbird-pro

## Current Status

### Active Contract

Warbird is now an indicator-only PineScript AG modeling project.

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

Budget verification from 2026-04-26:

- institutional: 58/64 output calls, 4 `request.security()` + 1 `request.footprint()`
- v7 strategy: 60/64 output calls, 4 `request.security()` + 1 `request.footprint()`
- backtest strategy: 53/64 output calls, 4 `request.security()` + 1 `request.footprint()`

### Modeling Surfaces

- `scripts/optuna/` is the active local optimization workspace.
- `scripts/ag/tv_auto_tune.py` and `scripts/ag/tune_strategy_params.py` remain useful
  for TradingView-driven settings trials.
- `scripts/ag/train_ag_baseline.py`, local `ag_training`, FRED joins, and SHAP lineage
  tables are legacy unless explicitly reopened.

### Current Blocker

Refresh the Pine-derived baseline export and align the active optimization
scripts/runbooks to the new indicator-only contract before launching modeling.
Do not start training until the user explicitly approves it.

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
