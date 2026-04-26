# Warbird Project Context

## Dynamic Discovery Rules

1. Read `AGENTS.md` first.
2. Resolve active architecture from `docs/INDEX.md` and `docs/MASTER_PLAN.md`.
3. Treat this file as a convenience summary only; active docs win.

## Current Snapshot (2026-04-26)

This snapshot is intentionally iterative. Warbird is actively tuning and
training the Pine indicator, so trigger families, settings, thresholds, search
spaces, and build recommendations may change after new TradingView exports,
Strategy Tester evidence, Optuna trials, AG analysis, or SHAP review. Re-read
the active docs before each task and update this context when accepted evidence
changes.

### Canonical Contract

- Active plan: Warbird Indicator-Only AG Plan v6.
- Modeling truth: Pine/TradingView outputs only.
- Goal: perfect indicator settings, state machine, and build quality.
- Nexus ML RSI styling and visible outputs are frozen by
  `docs/contracts/nexus_visual_plot_freeze.md`; do not touch colors, watermark,
  dashboard/KNN tables, `barcolor`, visible plots, fills, markers, labels, or
  visible output inventory unless Kirk explicitly requests that exact
  visual/plot edit in the current session.
- No external feature stacking: no FRED, macro, news, options, cross-asset,
  Databento-ingestion, Supabase, or local `ag_training` joins.

### Current Pine Surfaces

- Live indicator: `indicators/v7-warbird-institutional.pine`
- Strategy Tester mirror: `indicators/v7-warbird-strategy.pine`
- Optuna/backtest wrapper: `indicators/v7-warbird-institutional-backtest-strategy.pine`
- Nexus lower-pane research surface:
  `indicators/warbird-nexus-machine-learning-rsi-optuna-fast-test.pine`
  (visual/plot surface frozen)

### Current Budget Snapshot

- v7 institutional: 58/64 output calls
- v7 strategy: 60/64 output calls
- v7 institutional backtest strategy: 53/64 output calls

### Data Surfaces For Suggestions

Use only Pine/TradingView-derived surfaces:

- TradingView indicator CSV export for non-Nexus lanes
- TradingView Strategy Tester trade export
- CDP-read `reportData().trades()`
- TradingView/Pine `request.footprint()` `nexus_fp_*` snapshot for Nexus ML RSI
- deterministic fields derived from the same export

Do not map suggestions to database tables unless the task is explicitly runtime
or bookkeeping work.

## Suggestion Mapping Template

For each recommendation, map:

1. Pine file and logic section
2. Pine input setting or `ml_*` field involved
3. TradingView export/trade evidence required
4. Validation gates required before release
