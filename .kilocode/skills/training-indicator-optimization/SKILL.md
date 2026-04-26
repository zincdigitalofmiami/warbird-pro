---
name: training-indicator-optimization
description: Sweep Pine indicator settings from TradingView/Pine outputs under the indicator-only AG contract.
---

> **2026-04-26 indicator-only reset:** This skill remains active only for Pine/TradingView output modeling. Do not join FRED, macro, local `ag_training`, Databento-ingestion, or other external features.
> **Ongoing tuning note:** Current trigger families, settings, thresholds, and
> search spaces are evidence snapshots. Re-read the active docs before each run
> and update Markdown when new TradingView/Optuna/AG/SHAP evidence changes the
> accepted contract.

# Training — Indicator Optimization

Use this skill to optimize Pine indicator settings and module choices from
TradingView/Pine evidence.

## Allowed Inputs

- TradingView indicator CSV export
- TradingView Strategy Tester trade export
- CDP-read Strategy Tester data
- deterministic columns derived from those exports

## Disallowed Inputs

- local `ag_training`
- FRED/macro joins
- Databento/Supabase ingestion tables
- cross-asset or news/options features

## Workflow

1. Lock the Pine source file, commit, symbol, timeframe, and input defaults.
2. Capture or read the TradingView export/trade evidence.
3. Run the settings search with `tv_auto_tune.py`, `tune_strategy_params.py`, or
   the active Optuna profile.
4. Rank settings by PF, expectancy, drawdown, trade count, long/short balance,
   and walk-forward stability.
5. Emit a settings/build recommendation.
6. Apply Pine defaults or code only after explicit approval.

## Output

- champion settings
- rejected settings
- metrics by cohort/window
- failure modes
- Pine edit/default recommendation, if any
