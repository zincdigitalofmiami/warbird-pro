# Warbird Indicator-Only Optuna Plan v6

**Date:** 2026-05-05
**Status:** Active architecture plan

## Summary

Warbird training is a pure PineScript indicator modeling program.

The active goal is to perfect the TradingView indicator itself: settings, state
machine, entries, exits, filters, hidden exports, and visual/operator build.
Optuna and supporting scripts may be used offline, but only to model and rank
PineScript indicator behavior. They do not create a separate data-stack
decision engine.

Single-surface update (2026-05-02): the only active main chart indicator is
**Warbird Pro V9** at `indicators/warbird-pro-v9.pine`. Nexus remains as the only retained
support/research Pine lane:

- `indicators/warbird-nexus-machine-learning-rsi-optuna-fast-test.pine`

All other Pine indicator, strategy, backtest, and fib-only variants are retired
from the active `indicators/` surface.

V9 lane update (2026-05-02): `warbird_pro_v9` is a separate Optuna lane over the
same active Warbird Pro V9 indicator. It models ATR/risk exits from
manifest-backed ES/MES training rows from TradingView exports or Databento
market data, ignores NQ/MNQ rows,
excludes `-.236` and other negative fib extensions as stop candidates, keeps
`-.236` only as optional context/export data, and freezes fib anchors, fib
visuals, and EMA/MA setup until a champion is approved for Pine promotion.

## Current Contract

- The canonical modeling object is the `Warbird Pro` Pine indicator behavior on
  TradingView.
- Training truth comes from manifest-backed active-lane sources: Pine/TradingView
  outputs emitted by `indicators/warbird-pro-v9.pine`, Databento ES/MES
  market-data training rows when declared as Databento source data, and, for
  Nexus work only, `indicators/warbird-nexus-machine-learning-rsi-optuna-fast-test.pine`.
- Allowed evidence includes TradingView indicator exports, hidden `ml_*` /
  `nexus_fp_*` plots, Nexus TradingView/Pine `request.footprint()` evidence for
  `NEXUS_FOOTPRINT_DELTA`, and deterministic columns derived from approved
  source rows.
- The optimization target is indicator quality: settings, thresholds, module
  toggles, stop/target policy, signal frequency, profit factor, drawdown,
  stability, direction balance, and operator usability.
- External feature stacking is out of scope. No FRED, macro, news, options,
  cross-asset, Supabase, or mislabeled Databento/TradingView artifacts are
  admitted into the active modeling dataset.
- Cloud Supabase is runtime/support only. It is not a model-training mirror and
  does not receive raw trials, raw labels, or full research datasets.

## Active Surfaces

- Main chart indicator:
  - `indicators/warbird-pro-v9.pine`
- Retained Nexus support/research lane:
  - `indicators/warbird-nexus-machine-learning-rsi-optuna-fast-test.pine`
- Optimization and modeling tools:
  - `scripts/optuna/`
  - `scripts/optuna/warbird_pro_v9_profile.py`
  - `scripts/optuna/workspaces/warbird_pro_v9/`
  - `scripts/ag/tv_auto_tune.py`
  - `scripts/ag/tune_strategy_params.py`
  - `scripts/ag/tv_connection_doctor.py`
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
- Databento is an approved market-data supplier for training rows when the
  manifest declares a Databento capture/source kind. Databento is not the
  Pine indicator, not a TradingView indicator CSV, and not a substitute for
  trigger-family identity. Use Databento historical
  [`get_range`](https://databento.com/docs/api-reference-historical/timeseries/timeseries-get-range?historical=python&live=python&reference=python),
  [programmatic batch downloads](https://databento.com/docs/examples/basics-historical/programmatic-batch-download),
  [OHLCV resampling](https://databento.com/docs/examples/basics-historical/ohlcv-resampling?historical=python&live=python&reference=python),
  [continuous contracts](https://databento.com/docs/examples/symbology/continuous?historical=python&live=python&reference=python),
  Optuna [`create_study`](https://optuna.readthedocs.io/en/stable/reference/generated/optuna.create_study.html),
  and Optuna [`TPESampler`](https://optuna.readthedocs.io/en/stable/reference/samplers/generated/optuna.samplers.TPESampler.html).

## Non-Goals

The following are explicitly retired from the active plan:

- building a daily-ingestion training warehouse
- using local legacy warehouse training tables (`ag_training`) as the model source
- training on FRED, macro, news, options, or cross-asset features
- reconstructing Pine behavior from Python OHLCV as the canonical label path
- recording Databento market-data rows as `TRADINGVIEW_INDICATOR_CSV` or as a
  Pine indicator source
- promoting a live model packet that scores separate server-side features
- using cloud Supabase as a training database
- reviving deleted Pine strategy, backtest, or fib-only variants without an
  explicit architecture reopen

## Trigger Families

Every modeling run must declare exactly one trigger family:

- `LIVE_ANCHOR_FOOTPRINT`: entries from `warbird-pro-v9.pine`
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

### Phase 2 - Training Row Capture

Capture training rows from manifest-backed active-lane sources.

Allowed sources:

- TradingView indicator CSV export from `warbird-pro-v9.pine`
- Databento ES/MES market-data training rows with a Databento capture/source
  kind in the manifest
- hidden `ml_*` export fields emitted by that indicator
- retained Nexus `nexus_fp_*` footprint exports for `NEXUS_FOOTPRINT_DELTA`
- deterministic artifacts produced from approved source rows

Required manifest fields:

- indicator file when the source is Pine/TradingView
- repo commit
- symbol
- timeframe
- source/export date range
- Pine input settings when the source is Pine/TradingView
- trigger family and source Pine file when applicable
- source kind / capture method
- row count
- export hash
- notes on missing or platform-limited fields

### Phase 3 - Settings And Build Modeling

Run Optuna modeling only against approved manifest-backed trial data.

Permitted modeling questions:

- Which input settings improve profit factor, win rate, expectancy, drawdown,
  trade density, and yearly consistency?
- Which filter/module toggles improve or damage the signal?
- Which stop/target policy works best inside the current Pine state machine?
- In the `warbird_pro_v9` lane only, which ATR/risk exit policy works best for
  existing Warbird Pro V9 entry triggers across ES/MES exports?
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

TradingView preflight split:

- `python3 scripts/ag/tv_auto_tune.py --storage jsonl preflight --indicator-only`
  for V9 indicator-only sessions
- `python3 scripts/ag/tv_auto_tune.py --storage jsonl preflight` only when a
  strategy harness is explicitly reopened and loaded on chart

### Phase 6 - Promotion

Promotion is manual. A champion means:

- the TradingView indicator settings/build are approved
- the evidence and artifacts are saved
- docs and runbooks are updated
- no separate server-side scoring engine is implied

## Pine Budget Baseline

Verified 2026-05-10 by `scripts/guards/pine-lint.sh`:

- `warbird-pro-v9.pine`: 60 output-consuming calls
  (58 `plot()` + 2 `alertcondition()`), 9 `request.security()` calls after
  comment-line normalization, 1 `request.footprint()` call, 19 `line.new()`
  calls, 1 `box.new()`, and 1 `table.new()`. Session VWAP is intentionally
  modeling/export-only through `ml_liq_vwap_dist_atr`; it is not a visible
  chart overlay.

Any Pine addition must be priced before code is written. Nexus request/output
budgets must be repriced before any Nexus edit.

## Verification Locks

- No mock data.
- No external feature stacking.
- No daily-ingestion training dependency.
- No Pine edits without explicit approval.
- Canonical fib and trade-state semantics are locked in
  `indicators/warbird-pro-v9.pine`: anchor ownership, fib ladder
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

Core ETL/trainer partial — DXY parity, fixed 10/-5/24 labels, strict feature
schema, Yahoo `DX-Y.NYB`, and Databento trade-side CVD/order-flow features are
wired in code. The May smoke order-flow threshold review lowered
absorption/flush candidate delta thresholds to `35%` with the existing `1.5x`
volume-spike and `0.75 ATR` range split, producing nonzero smoke candidates.
Pending: full 1y Core build, 1y order-flow distribution confirmation, Core card
body + hard-gate launch wiring, Optuna hub wiring, and pre-launch gate report.
Owner/next trigger: Codex resumes when Kirk approves the full 1y Core
build/training path.

Smoke verification evidence is recorded in
`docs/audits/2026-05-10-v9-core-smoke-verification.md`; use
`scripts/ag/report_v9_core_smoke.py` for exact reproducible metrics.

---

## V9 Core AutoGluon — Active Plan (2026-05-09)

The earlier Hybrid+ 4-card system (`warbird_pro_v9_exit_cpcv`,
`warbird_pro_v9_entry_filter_cpcv`, `warbird_pro_v9_ag_meta_cpcv`,
`warbird_pro_v9_joint_challenger`) is **deprecated**. Path went 4 → 2 → single
Core card. The Core card supersedes all four.

### Live Pine Settings (authoritative — must match dataset builder exactly)

| Parameter | Value | Pine input name |
|-----------|-------|-----------------|
| ZigZag Deviation | **3.0** | `fibDeviationManual` |
| ZigZag Depth | **10** | `fibDepthManual` |
| ZigZag Threshold Floor % | **0.15** | `fibThresholdFloorPct` |
| Confluence Tolerance % | **0.05** | `fibConfluenceTolPct` |
| Min Fib Range (ATR) | **0.5** | `minFibRangeAtr` |
| Midpoint Hysteresis % | **2.0** | `fibHysteresisPct` |
| MA Length (SMA) | **13** | `lengthMA` |
| EMA Length | **6** | `lengthEMA` |

**Rule:** Before every dataset build, read the live TradingView indicator
inputs panel and verify the dataset-builder constants match exactly. Pine code
`input.float(default, ...)` defaults are NOT authoritative — the user's saved
TV settings are. Contamination incident (2026-05-05) used dev=4.0, depth=20,
floor=0.50 — all wrong; do not repeat.

### V9 Pine Pattern Set (post-2026-05-09 trim)

- **Bull (1):** `patRisingWindow`
- **Bear (3):** `patBearEngulf`, `patMarubozuBlack`, `patTweezerTop`
- **Dropped 2026-05-09:** `patBullEngulf`, `patPiercing`, `patHaramiBull`,
  `patHaramiBear`
- **HOLD for v10:** Three Line Strike (84% vendor citation unverified — validate
  in Python first before reserving Pine plot budget)

### Core Training Dataset Contract

- **Source:** Databento MES — Trades 365d (footprint reconstruction) + OHLCV
  bars 5m (training resolution) + OHLCV 1m (microstructure features only).
- **Window:** 2025-05-01 → 2026-05-09 (1y, dense feature coverage).
  The newer Databento OHLCV-1s 2315d download is reserved for a future v10
  long-horizon ensemble card, NOT Core (would NaN 2/3 of feature surface).
- **Feature surface:** V9 Pine ml_* + ETL-derived `ml_cvd_div_bull/bear` (CVD
  divergence, Python-only, zero Pine cost) + 1m microstructure features +
  Initial Balance + volume profile HVN/LVN + UTC-anchored economic-event
  features (CPI/NFP/PPI=13:30 UTC, FOMC=19:00/18:00 UTC seasonal).
- **Label (triple barrier):** `winner_10pt_24bar` = 1 if +10 pts before -5 pts
  within 24 5m bars (2:1 R:R, 2-hour window); 0 otherwise; rows where neither
  barrier hits within the window are DROPPED (not relabeled as loss).

### Kirk's Trade Preferences

- **Target move:** 10 MES points (40 ticks, $50/contract).
- **Target SL:** 1.0 ATR. **Max SL:** 2.0 ATR. `stopAtrMult` range (0.75, 2.0).
- **Target breakeven range:** 1–3R. `targetRiskMultiple` range (1.0, 3.0).
- **Inference threshold:** `proba > 0.75` for Grade A+ entries.
  `eval_metric='log_loss'` + `calibrate=True` ensures the threshold = real WR.
- **Session filter:** feature only (`ml_session_ny/london/asia`,
  `ml_minutes_from_open`), NOT a pre-filter — let AG learn the regime.

### Single Core Training Card

| Card | Profile | Status |
|------|---------|--------|
| Core | `scripts/optuna/cards/core_training/2026_05_09_warbird_pro_autogluon_core.py` | Smoke/validation Optuna wrapper wired; full 1y AG launch pending |

**AG config (locked):**

- `preset='best_quality'`
- Full zoo (7 families) via explicit `hyperparameters` dict:
  GBM (×2: standard + extra_trees), CAT, XGB, RF (×2: gini + entropy),
  XT (×2: gini + entropy), NN_TORCH, FASTAI
- `num_bag_folds=0`, `num_stack_levels=0` — no bagging, time-series safe
- `dynamic_stacking=False` — override preset default for reproducibility
- `eval_metric='log_loss'`, `calibrate=True`
- `time_limit=7200s` (2h, full zoo lets NN_TORCH + FASTAI converge)
- `ag_args_ensemble={'fold_fitting_strategy': 'sequential_local'}`
- All OpenMP families single-threaded; `OMP_NUM_THREADS=1` env guard at top

**Side card (post-Core):** `scripts/optuna/cards/side_models/` will hold a MAE
regression model that predicts maximum adverse excursion per trade. Used for
SL sizing AFTER the Core binary classifier ranks setups. Trained separately;
NOT grafted into Core.

### Hard Gate

Production runs go through `scripts/ag/train_hard_gate.py`. Manual chains of
train → SHAP → MC are forbidden. See `.claude/skills/training-hard-gate`.
