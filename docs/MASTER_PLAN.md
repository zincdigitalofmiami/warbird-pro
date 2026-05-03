# Warbird Indicator-Only Optuna Plan v6

**Date:** 2026-05-02
**Status:** Active architecture plan

## Summary

Warbird training is a pure PineScript indicator modeling program.

The active goal is to perfect the TradingView indicator itself: settings, state
machine, entries, exits, filters, hidden exports, and visual/operator build.
Optuna and supporting scripts may be used offline, but only to model and rank
PineScript indicator behavior. They do not create a separate data-stack
decision engine.

Single-surface update (2026-05-02): the only active main chart indicator is
`indicators/warbird-pro-rebuild-fib-ml.pine`. Nexus remains as the only retained
support/research Pine lane:

- `indicators/warbird-nexus-machine-learning-rsi-optuna-fast-test.pine`

All other Pine indicator, strategy, backtest, and fib-only variants are retired
from the active `indicators/` surface.

V9 lane update (2026-05-02): `warbird_pro_v9` is a separate Optuna lane for the
same active Warbird Pro rebuild indicator. It models ATR/risk exits from
manifest-backed TradingView exports on ES/MES only, ignores NQ/MNQ exports,
excludes `-.236` and other negative fib extensions as stop candidates, keeps
`-.236` only as optional context/export data, and freezes fib anchors, fib
visuals, and EMA/MA setup until a champion is approved for Pine promotion.

## Current Contract

- The canonical modeling object is the `Warbird Pro` Pine indicator behavior on
  TradingView.
- Training truth comes from Pine/TradingView outputs emitted by
  `indicators/warbird-pro-rebuild-fib-ml.pine` and, for Nexus work only,
  `indicators/warbird-nexus-machine-learning-rsi-optuna-fast-test.pine`.
- Allowed evidence includes TradingView indicator exports, hidden `ml_*` /
  `nexus_fp_*` plots, Nexus TradingView/Pine `request.footprint()` evidence for
  `NEXUS_FOOTPRINT_DELTA`, and deterministic Pine-derived state columns.
- The optimization target is indicator quality: settings, thresholds, module
  toggles, stop/target policy, signal frequency, profit factor, drawdown,
  stability, direction balance, and operator usability.
- External feature stacking is out of scope. No FRED, macro, news, options,
  cross-asset, Supabase, or Databento-derived feature joins are admitted into
  the active modeling dataset.
- Cloud Supabase is runtime/support only. It is not a model-training mirror and
  does not receive raw trials, raw labels, or full research datasets.

## Active Surfaces

- Main chart indicator:
  - `indicators/warbird-pro-rebuild-fib-ml.pine`
- Retained Nexus support/research lane:
  - `indicators/warbird-nexus-machine-learning-rsi-optuna-fast-test.pine`
- Optimization and modeling tools:
  - `scripts/optuna/`
  - `scripts/optuna/warbird_pro_v9_profile.py`
  - `scripts/optuna/workspaces/warbird_pro_v9/`
  - `scripts/ag/tv_auto_tune.py`
  - `scripts/ag/tune_strategy_params.py`
- Artifacts:
  - `artifacts/tuning/`
  - `scripts/optuna/workspaces/<indicator_key>/`

## Research Reference Surface

- `docs/research/2026-05-02-optuna-unified-platform.md` is the current
  long-form Optuna platform research report for ecosystem-level guidance
  (samplers, pruners, storage, orchestration, walk-forward design patterns).
- This file is reference-only and does not supersede active contract rules:
  Pine/TradingView-only modeling rows, explicit trigger-family declaration,
  and no out-of-scope feature stacking without an architecture reopen.

## Non-Goals

The following are explicitly retired from the active plan:

- building a daily-ingestion training warehouse
- using local legacy warehouse training tables (`ag_training`) as the model source
- training on FRED, macro, news, options, or cross-asset features
- reconstructing Pine behavior from Python OHLCV as the canonical label path
- promoting a live model packet that scores separate server-side features
- using cloud Supabase as a training database
- reviving deleted Pine strategy, backtest, or fib-only variants without an
  explicit architecture reopen

## Trigger Families

Every modeling run must declare exactly one trigger family:

- `LIVE_ANCHOR_FOOTPRINT`: entries from `warbird-pro-rebuild-fib-ml.pine`
  `entryLongTrigger` / `entryShortTrigger` (legacy trigger-family identifier;
  rebuild lane does not require footprint inputs).
- `NEXUS_FOOTPRINT_DELTA`: Nexus lower-pane footprint-delta evidence from the
  retained Nexus Pine files. Rows must come from TradingView/Pine
  `request.footprint()` `nexus_fp_*` evidence.

Deleted strategy/backtest trigger families are inactive unless Kirk explicitly
reopens them in a new plan update.

## Plan Phases

### Phase 0 - Authority Reset

Keep the active authority docs aligned with the single main indicator plus
retained Nexus lane.

Required surfaces:

- `AGENTS.md`
- `docs/INDEX.md`
- `docs/MASTER_PLAN.md`
- `docs/contracts/`
- `docs/runbooks/`
- `docs/cloud_scope.md`
- `WARBIRD_MODEL_SPEC.md`
- `CLAUDE.md`
- `README.md`

### Phase 1 - Pine Baseline Lock

Before modeling any settings, lock the exact Pine build being optimized.

Required facts:

- source file path
- TradingView symbol and timeframe
- indicator version / commit
- exported columns
- Pine input defaults
- trigger family
- plot/request budget
- compile/lint status

No Pine code changes are allowed without explicit session approval.

### Phase 2 - Pine Output Capture

Capture training rows from TradingView/Pine only.

Allowed sources:

- TradingView indicator CSV export from `warbird-pro-rebuild-fib-ml.pine`
- hidden `ml_*` export fields emitted by that indicator
- retained Nexus `nexus_fp_*` footprint exports for `NEXUS_FOOTPRINT_DELTA`
- deterministic artifacts produced from those Pine outputs

Required manifest fields:

- indicator file
- repo commit
- symbol
- timeframe
- TradingView export range
- Pine input settings
- trigger family and source Pine file
- row count
- export hash
- notes on missing or platform-limited fields

### Phase 3 - Settings And Build Modeling

Run Optuna modeling only against Pine-derived trial data.

Permitted modeling questions:

- Which input settings improve profit factor, win rate, expectancy, drawdown,
  trade density, and yearly consistency?
- Which filter/module toggles improve or damage the signal?
- Which stop/target policy works best inside the current Pine state machine?
- In the `warbird_pro_v9` lane only, which ATR/risk exit policy works best for
  existing Warbird Pro rebuild entry triggers across ES/MES exports?
- Which Pine states or `ml_*` / `nexus_fp_*` exports explain winners versus
  failures?
- Which settings are robust across IS/OOS windows?

Prohibited modeling questions:

- Which macro/FRED/cross-asset feature should gate trades?
- Which server-side model should score live alerts?
- Which warehouse feature should be joined into the indicator decision?
- Which NQ or cross-asset feature should gate V9 entries?

### Phase 4 - Explainability And Recommendation

Use feature-importance analysis from Optuna results to convert model outputs
into actionable Pine settings/build recommendations.

The output is a settings/build brief:

- champion settings
- rejected settings
- feature/module importance
- stability notes
- expected row/trade-state count
- known failure modes
- recommended Pine edits, if any

### Phase 5 - Pine Implementation

Only after Kirk approval, apply Pine changes or default-setting changes.

Required gates after any `.pine` edit:

1. pine-facade compile check
2. `./scripts/guards/pine-lint.sh <file>`
3. `./scripts/guards/check-fib-scanner-guardrails.sh`
4. `./scripts/guards/check-contamination.sh`
5. `./scripts/guards/check-no-tv-force.sh`
6. `npm run build`

Indicator/strategy parity is inactive because no active strategy Pine file
exists in `indicators/`.

### Phase 6 - Promotion

Promotion is manual. A champion means:

- the TradingView indicator settings/build are approved
- the evidence and artifacts are saved
- docs and runbooks are updated
- no separate server-side scoring engine is implied

## Pine Budget Baseline

Verified 2026-05-02:

- `warbird-pro-rebuild-fib-ml.pine`: 28 output calls (plot family), 0
  `alertcondition()` calls, 3 `request.security()` calls, and no
  `request.footprint()` path in the main indicator.

Any Pine addition must be priced before code is written. Nexus request/output
budgets must be repriced before any Nexus edit.

## Verification Locks

- No mock data.
- No external feature stacking.
- No daily-ingestion training dependency.
- No Pine edits without explicit approval.
- Canonical fib and trade-state semantics are locked in
  `indicators/warbird-pro-rebuild-fib-ml.pine`: anchor ownership, fib ladder
  construction (`fibPrice` + canonical levels), entry/stop/target state, and
  `ml_last_exit_outcome` semantics are protected scope.
- Banned regression pattern (repo-wide): do not use the pivot-window
  `fibHtfSnapshot` variant with `ta.barssince(...)` and
  `pivotHighInWindow` / `pivotLowInWindow`; it has repeatedly produced wide-fib
  failures.
- No settings result is trusted without TradingView indicator export evidence.
- `warbird_pro_v9` is isolated from `warbird_pro`: it admits ES/MES TradingView
  exports only, ignores NQ/MNQ, and optimizes ATR/risk exits without touching
  Pine.
- `-.236` is removed as a V9 stop candidate. It may remain only as an optional
  exported context feature.
- No forced TradingView launch/restart/process-kill automation.
- Banned methods: `tv_launch`, `launch_tv_debug_mac.sh`,
  `pkill -f TradingView`, `killall TradingView`.
- Live TradingView operations are one explicit command at a time; no retry loops.
- No champion is accepted without IS/OOS or walk-forward-style review.

## Current Blocker

Run controlled 5m/15m tuning from manifest-backed TradingView exports on
`indicators/warbird-pro-rebuild-fib-ml.pine`, then promote only evidence-backed
settings. Keep Nexus available only for its retained footprint/research lane.
