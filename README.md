# Warbird Pro

Warbird Pro is now an indicator-only PineScript modeling workspace for MES
TradingView indicator development.

The active work is to perfect the TradingView indicator: settings, signal
logic, stop/target policy, filters, visual/operator state, and Strategy Tester
performance. AutoGluon, Optuna, SHAP, and local scripts may be used offline, but
only to analyze Pine/TradingView outputs and recommend Pine settings/build
changes.

This repo is in an active tuning/training phase. Current triggers, settings,
thresholds, and search spaces are evidence snapshots and may change as new
TradingView/Optuna/AG/SHAP results land. Accepted changes must update the active
Markdown authority set before another agent treats them as current.

**Repo:** [github.com/zincdigitalofmiami/warbird-pro](https://github.com/zincdigitalofmiami/warbird-pro)  
**Canonical docs index:** `docs/INDEX.md`
**Active plan:** `docs/MASTER_PLAN.md`

## Source Of Truth

Use these in order:

1. `AGENTS.md`
2. `docs/INDEX.md`
3. `docs/MASTER_PLAN.md`
4. `docs/contracts/pine_indicator_ag_contract.md`
5. `WARBIRD_MODEL_SPEC.md`
6. `CLAUDE.md`

Historical warehouse, macro, and cloud-ingestion plans are reference-only unless
explicitly reopened.

## Active Architecture

- Training/modeling source: Pine/TradingView outputs only.
- Primary indicator: `indicators/v7-warbird-institutional.pine`.
- Trigger family must be explicit for every run:
  `LIVE_ANCHOR_FOOTPRINT`, `STRATEGY_ACCEPT_SCALP`, or
  `BACKTEST_DIRECT_ANCHOR`.
- Backtest/modeling files:
  - `indicators/v7-warbird-strategy.pine`
  - `indicators/v7-warbird-institutional-backtest-strategy.pine`
- Optimizer workspace: `scripts/optuna/`.
- TradingView tuning helpers:
  - `scripts/ag/tv_auto_tune.py`
  - `scripts/ag/tune_strategy_params.py`

## Out Of Scope For Active Training

- daily/hourly ingestion as a training source
- FRED, macro, news, options, and cross-asset feature stacking
- local `ag_training` warehouse rows
- server-side model packets that score live alerts
- Supabase as a training database

Runtime ingestion and cloud surfaces may remain for dashboard/chart support, but
they do not define model truth.

## Local Development

```bash
npm install
npm run dev
```

## Verification

```bash
npm run lint
npm run build
```

Before committing Pine edits, run the Pine verification flow in `CLAUDE.md`.
