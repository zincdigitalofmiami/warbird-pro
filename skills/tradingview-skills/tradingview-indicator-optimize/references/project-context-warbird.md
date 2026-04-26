# Warbird Project Context

## Dynamic Discovery Rules

1. Read `AGENTS.md` first.
2. Resolve active architecture from `docs/INDEX.md` and `docs/MASTER_PLAN.md`.
3. Treat this file as a convenience summary only; active docs win.

## Current Snapshot (2026-04-26)

### Canonical Contract

- Active plan: Warbird Indicator-Only AG Plan v6.
- Modeling truth: Pine/TradingView outputs only.
- Goal: perfect indicator settings, state machine, and build quality.
- No external feature stacking: no FRED, macro, news, options, cross-asset,
  Databento-ingestion, Supabase, or local `ag_training` joins.

### Current Pine Surfaces

- Live indicator: `indicators/v7-warbird-institutional.pine`
- Strategy Tester mirror: `indicators/v7-warbird-strategy.pine`
- Optuna/backtest wrapper: `indicators/v7-warbird-institutional-backtest-strategy.pine`

### Current Budget Snapshot

- v7 institutional: 58/64 output calls
- v7 strategy: 60/64 output calls
- v7 institutional backtest strategy: 53/64 output calls

### Data Surfaces For Suggestions

Use only Pine/TradingView-derived surfaces:

- TradingView indicator CSV export
- TradingView Strategy Tester trade export
- CDP-read `reportData().trades()`
- deterministic fields derived from the same export

Do not map suggestions to database tables unless the task is explicitly runtime
or bookkeeping work.

## Suggestion Mapping Template

For each recommendation, map:

1. Pine file and logic section
2. Pine input setting or `ml_*` field involved
3. TradingView export/trade evidence required
4. Validation gates required before release
