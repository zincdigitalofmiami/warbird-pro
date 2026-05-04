# Warbird Pro

Warbird Pro is now an indicator-only PineScript modeling workspace for MES
TradingView indicator development.

The active work is to perfect the TradingView indicator: settings, signal
logic, stop/target policy, filters, visual/operator state, and exported
indicator behavior. Optuna and local scripts may be used offline, but only to
analyze Pine/TradingView outputs and recommend Pine settings/build changes.

This repo is in an active tuning/training phase. Current triggers, settings,
thresholds, and search spaces are evidence snapshots and may change as new
TradingView/Optuna results land. Accepted changes must update the active
Markdown authority set before another agent treats them as current.

**Repo:** github.com/zincdigitalofmiami/warbird-pro
**Canonical docs index:** `docs/INDEX.md`
**Active plan:** `docs/MASTER_PLAN.md`

## Source Of Truth

Use these in order:

1. `AGENTS.md`
2. `docs/INDEX.md`
3. `docs/runbooks/startup_repo_review.md`
4. `docs/MASTER_PLAN.md`
5. `docs/contracts/pine_indicator_ag_contract.md`
6. `WARBIRD_MODEL_SPEC.md`
7. `CLAUDE.md`

Historical warehouse, macro, and cloud-ingestion plans are reference-only unless
explicitly reopened.

## Agent Startup Review

Every fresh chat, start-of-day session, context reset, or resumed session with
unknown repo state starts with the read-only startup repo review in
`docs/runbooks/startup_repo_review.md`.

This review inspects local docs, recent commits/diffs, working tree status,
stashes, branches/worktrees, and key project surfaces before any planning or
implementation. It does not modify files, run builds/tests/training, or touch
Pine unless the user separately asks for implementation afterward.

The initialization record is
`docs/runbooks/2026-04-29-startup-repo-review-initialization.md`.

## Active Architecture

- Training/modeling source: manifest-backed active-lane data:
  Pine/TradingView outputs, approved Databento ES/MES market-data training rows,
  and Nexus footprint snapshots.
- Main chart indicator: **Warbird Pro V9** at `indicators/warbird-pro-v9.pine`.
- Retained Nexus lane:
  - `indicators/warbird-nexus-machine-learning-rsi-optuna-fast-test.pine`
- Trigger family must be explicit for every run:
  `LIVE_ANCHOR_FOOTPRINT` or `NEXUS_FOOTPRINT_DELTA`.
- Retired Pine variants:
  - `indicators/warbird-pro-indicator.pine`
  - `indicators/Warbird_Pro_v7.pine`
  - `indicators/v7-warbird-institutional.pine`
  - `indicators/v7-warbird-strategy.pine`
  - `indicators/v7-warbird-institutional-backtest-strategy.pine`
  - `indicators/fibs-only.pine`
- Optimizer workspace: `scripts/optuna/`.
- TradingView tuning helpers:
  - `scripts/ag/tv_auto_tune.py`
  - `scripts/ag/tune_strategy_params.py`

## Out Of Scope For Active Training

- cloud daily/hourly runtime ingestion as a training source
- FRED, macro, news, options, and cross-asset feature stacking
- local legacy warehouse rows (`ag_training`)
- server-side model packets that score live alerts
- Supabase as a training database
- Databento rows mislabeled as a TradingView indicator CSV or Pine indicator
  source

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
