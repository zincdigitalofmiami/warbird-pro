# Warbird Indicator-Only DuckDB Local Modeling Plan v6

**Date:** 2026-05-05 (renamed 2026-05-12 — Optuna workspace path retired)
**Status:** Active architecture plan

## Summary

Warbird training is a pure PineScript indicator modeling program.

The active goal is to perfect the TradingView indicator itself: settings, state
machine, entries, exits, filters, hidden exports, and visual/operator build.
The local DuckDB / Pandera / AutoGluon stack at `scripts/duckdb_local/`
(renamed from `scripts/optuna/` on 2026-05-12) is used offline to model and
rank PineScript indicator behavior. It does not create a separate data-stack
decision engine. Optuna is not a runtime dependency of the V9 Core path.

Single-surface update (2026-05-02): the only active main chart indicator is
**Warbird Pro V9** at `indicators/warbird-pro-v9.pine`. Nexus remains as the only retained
support/research Pine lane:

- `indicators/warbird-nexus-machine-learning-rsi-optuna-fast-test.pine`

All other Pine indicator, strategy, backtest, and fib-only variants are retired
from the active `indicators/` surface.

V9 lane update (2026-05-02, refined 2026-05-12): `warbird_pro_v9` is the
active modeling lane over the live Warbird Pro V9 indicator. It models ATR/risk
exits from manifest-backed ES training rows (15m and 5m) from TradingView
exports or Databento market data, ignores MES/NQ/MNQ rows, excludes `-.236` and
other negative fib extensions as stop candidates, keeps `-.236` only as
optional context/export data, and freezes fib anchors, fib visuals, and EMA/MA
setup until a champion is approved for Pine promotion. The production trainer
is `scripts/ag/train_v9_locked.py` (AutoGluon full-zoo, calibrated log_loss,
chronological IS/VAL/OOS with embargo). No Optuna search wraps the V9 path.

Data-layer + sequencing update (locked 2026-05-11):

- V9/Core ETL and training is file-based: **DuckDB 1.5.2** (sort/filter/build),
  **Pandera 0.31.1** (schema/contract validation), **fg-data-profiling 4.19.1**
  (`data_profiling` module — profiling reports). Local PG17 `warbird` warehouse
  is legacy-reference only; the V9/Core path does not import psycopg2.
- Build and train ES **15m first**; build and train ES 5m only after 15m
  success (fit + SHAP + Monte Carlo) is documented.

## Current Contract

- The canonical modeling object is the `Warbird Pro` Pine indicator behavior on
  TradingView.
- Training truth comes from manifest-backed active-lane sources: Pine/TradingView
  outputs emitted by `indicators/warbird-pro-v9.pine`, Databento ES
  market-data training rows (5m/15m) when declared as Databento source data, and, for
  Nexus work only, `indicators/warbird-nexus-machine-learning-rsi-optuna-fast-test.pine`.
- Allowed evidence includes TradingView indicator exports, hidden `ml_*` /
  `nexus_fp_*` plots, Nexus TradingView/Pine `request.footprint()` evidence for
  `NEXUS_FOOTPRINT_DELTA`, and deterministic columns derived from approved
  source rows.
- The optimization target is indicator quality: settings, thresholds, module
  toggles, stop/target policy, signal frequency, profit factor, drawdown,
  stability, direction balance, and operator usability.
- External feature stacking is out of scope. No FRED, macro, news, options,
  external cross-asset joins, Supabase, or mislabeled Databento/TradingView
  artifacts are admitted into the active modeling dataset. Pine-native
  NQ/ZN/DXY/VIX values emitted by `warbird-pro-v9.pine` are part of the active
  indicator behavior. NQ is same-direction, DXY is inverse-risk, VIX is
  ATR-normalized movement pressure, and ZN follows the explicit Pine setting
  `ZN Gate Direction`.
- Cloud Supabase is runtime/support only. It is not a model-training mirror and
  does not receive raw trials, raw labels, or full research datasets.

## Active Surfaces

**Canonical paths (2026-05-12):**

| Role | Path |
|------|------|
| Main chart Pine indicator | `indicators/warbird-pro-v9.pine` |
| Retained Nexus research/support Pine | `indicators/warbird-nexus-machine-learning-rsi-optuna-fast-test.pine` |
| Locked 1y 15m Core export (CSV) | `scripts/duckdb_local/workspaces/warbird_pro_core/exports/es_15m_core.csv` |
| Manifest for that export | `scripts/duckdb_local/workspaces/warbird_pro_core/exports/es_15m_core.manifest.json` |
| Pandera profiling report | `scripts/duckdb_local/workspaces/warbird_pro_core/exports/es_15m_core.profile.html` |
| Core ETL builder | `scripts/duckdb_local/workspaces/warbird_pro_core/build_core_dataset.py` |
| **Production V9 trainer** | `scripts/ag/train_v9_locked.py` |
| SHAP gate runner | `scripts/ag/shap_v9.py` |
| Monte Carlo gate runner | `scripts/ag/monte_carlo_v9.py` |
| Smoke-validation card (no AG) | `scripts/duckdb_local/cards/core_training/2026_05_09_warbird_pro_autogluon_core.py` |
| Trade-dataset semantics (single source of truth) | `scripts/ag/train_v9_locked.py::build_trade_dataset` |
| Trained model output root | `models/warbird_pro_v9/locked_<tag>/` |
| SHAP artifacts root | `artifacts/shap_v9/shap_<tag>/` |
| Monte Carlo artifacts root | `artifacts/mc_v9/<tag>/` |
| TV settings/tuning helpers (non-V9) | `scripts/ag/tv_auto_tune.py`, `scripts/ag/tune_strategy_params.py` |
| TradingView readiness doctor | `scripts/ag/tv_connection_doctor.py` |
| Indicator-only AG contract | `docs/contracts/pine_indicator_ag_contract.md` |
| Startup review runbook | `docs/runbooks/startup_repo_review.md` |
| Legacy (do not use without architecture reopen) | `scripts/ag/train_hard_gate.py`, `scripts/ag/train_ag_baseline.py`, local Postgres `warbird` warehouse |

**Workspace layout:**

```
scripts/duckdb_local/                          # renamed from scripts/optuna/ on 2026-05-12
├── cards/core_training/                       # Optuna validation cards (smoke only)
├── cards/side_models/                         # MAE side-model scaffolds (post-Core)
├── workspaces/<indicator_key>/                # per-indicator workspace
│   ├── exports/                               # canonical export CSVs + manifests
│   ├── experiments/<symbol>_<tf>/study.db     # local study DB
│   └── champion.json                          # promoted settings snapshot
├── cpcv.py, cpcv_helpers.py                   # embargoed chronological / CPCV splits
├── paths.py                                   # canonical path helpers
└── runner.py + warbird_optuna_hub.py          # legacy Optuna runner/hub (Nexus + v7 lanes)
```

## Research Reference Surface

- `docs/research/2026-05-02-optuna-unified-platform.md` is a long-form Optuna
  ecosystem research report retained for historical guidance only. The V9
  Core path does not use Optuna; this document is reference-only.
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
  and [continuous contracts](https://databento.com/docs/examples/symbology/continuous?historical=python&live=python&reference=python)
  for the Databento ingest side. The downstream modeling stack is AutoGluon
  Tabular + DuckDB; no Optuna search is wired into the V9 Core path.

## Non-Goals

The following are explicitly retired from the active plan:

- building a daily-ingestion training warehouse
- using local legacy warehouse training tables (`ag_training`) as the model source
- training on FRED, macro, news, options, or external cross-asset features
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
- Databento ES market-data training rows (5m/15m) with a Databento capture/source
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

Run local DuckDB-backed AutoGluon modeling only against approved
manifest-backed trial data.

Permitted modeling questions:

- Which input settings improve profit factor, win rate, expectancy, drawdown,
  trade density, and yearly consistency?
- Which filter/module toggles improve or damage the signal?
- Which stop/target policy works best inside the current Pine state machine?
- In the `warbird_pro_v9` lane only, which ATR/risk exit policy works best for
  existing Warbird Pro V9 entry triggers across ES 5m/15m exports?
- Which Pine states or `ml_*` / `nexus_fp_*` exports explain winners versus
  failures?
- Which settings are robust across IS/OOS windows?

Prohibited modeling questions:

- Which macro/FRED/external cross-asset feature should gate trades?
- Which server-side model should score live alerts?
- Which warehouse feature should be joined into the indicator decision?
- Which external/server-side cross-asset feature should override V9 entries?

### Phase 4 - Explainability And Recommendation

Use feature-importance analysis (SHAP, AG leaderboard, Monte Carlo) to convert
model outputs into actionable Pine settings/build recommendations.

The output is a settings/build brief:

- champion settings
- rejected settings
- feature/module importance
- stability notes
- expected row/trade-state count
- known failure modes
- recommended Pine edits, if any

### Phase 4.5 - Validation Gating Before Live Trade Routing

**Mental model:** a trained classifier that posts strong log_loss / AUC / WR is
**not yet trustworthy**. Those metrics rank predictions but say nothing about
*why* the model is good or whether the apparent edge translates to live P&L.
Two independent gates run between a clean fit and any live TradingView alert
that depends on the model's output:

**Gate 1 — SHAP**
(`scripts/ag/shap_v9.py --predictor-dir <model> --csv <15m-export>`).

Catches feature-level pathology that aggregate metrics hide:

- **Top-feature audit** — is the model leaning on plausibly causal features
  (entry triggers, fib reaction, liquidity, ATR-normalized distances) or on
  proxies that smell like leakage (raw timestamps, label-adjacent fields,
  bar-of-day in a way that codes regime)?
- **Per-class importance** — winners and losers should be driven by an
  overlapping but not identical feature set; total drift between classes
  implies the model is mostly fitting label noise.
- **Temporal stability** (early-half vs. late-half SHAP) — if importances
  shift dramatically, the model is regime-fitting and OOS performance will
  collapse the moment the regime ends.
- **Calibration check** (predicted vs. realized in probability bins) — is the
  `proba > 0.75` gate actually delivering ~75% real WR, or is the isotonic
  calibration miscalibrated for the high-confidence tail?
- **Redundancy + drop candidates** — high-|r| feature pairs and
  DEAD / REDUNDANT / UNSTABLE features inform the next Core feature trim.

**Gate 2 — Monte Carlo**
(`scripts/ag/monte_carlo_v9.py --predictor-path <model> --csv <15m-export> --split oos`).

Catches P&L-level pathology that SHAP can't see:

- **Overall P&L distribution + drawdown + WR + profit factor** under
  realistic resampling — does the OOS distribution have a tail that's
  fundable, or do drawdowns wipe accounts before the edge realizes?
- **Per-direction breakdown** — does the model work both long and short, or
  is it riding one regime?
- **Threshold sweep** (`P(winner_10pt_24bar) >= τ` for τ ∈ [0.50, 0.95]) —
  where is the EV maximum? Is `0.75` (the locked inference threshold)
  near it or far from it?
- **Calibration cohort check** — predicted vs. realized broken out by time
  of day, session, regime quartile. A miscalibrated cohort can dominate
  losses even if global calibration looks fine.
- **Regime stability** (early-half vs. late-half) — does the model survive
  the same period split that SHAP audits structurally?
- **Win/loss streak profile** — serial correlation of outcomes drives
  drawdown depth far more than headline WR.

**Promotion rule:** only after Gate 1 *and* Gate 2 both clear do you
*enable* (toggle from disabled → active) any TradingView alert that depends
on this model's output — i.e., an alert whose firing condition is
"V9 entry trigger AND model_proba >= 0.75" (whether wired via webhook,
TV alert action, or any downstream notification). The phrase "flip an
alert" in operator shorthand means exactly this toggle.

A model that passes log_loss but fails either gate will push high-confidence
"entries" that lose real money. The OOS WR being *higher* than IS WR (the
2026-05-12 baseline showed IS 41.67% / VAL 43.60% / OOS 46.90%) is exactly
the pattern where gating is non-optional: it could mean genuine headroom or
it could mean the OOS window is a friendly regime that won't repeat. The
gates tell you which.

Failure of either gate routes back to Phase 3 or Phase 1 (settings change,
feature change, Pine change) — NOT to "tune the threshold" or "lower the
bar." The threshold is locked at 0.75 per the inference contract.

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
- `warbird_pro_v9` is isolated from `warbird_pro`: it admits ES 5m/15m
  TradingView/Databento exports only, ignores MES/NQ/MNQ, and optimizes ATR/risk exits without touching
  Pine.
- `-.236` is removed as a V9 stop candidate. It may remain only as an optional
  exported context feature.
- No forced TradingView launch/restart/process-kill automation.
- Banned methods: `tv_launch`, `launch_tv_debug_mac.sh`,
  `pkill -f TradingView`, `killall TradingView`.
- Live TradingView operations are one explicit command at a time; no retry loops.
- No champion is accepted without IS/OOS or walk-forward-style review.

## Current State (2026-05-12)

**The V9 Core training surface is ready to launch.** Open blockers below are
operator-gated only.

Recently landed (commit `5e5e6f3`):

- Directory rename `scripts/optuna/ → scripts/duckdb_local/` and
  `tests/optuna/ → tests/duckdb_local/`. Optuna is no longer a runtime
  dependency of the V9 Core path. Optuna methodology + the Python library
  remain in use only for the Nexus footprint research lane and legacy v7
  profile adapters (kept under the renamed directory).
- `scripts/ag/train_v9_locked.py` is the production V9 trainer. Default CSV
  fixed (5m → 15m, pointing at the locked 1y Core export). `--model-suite`
  flag adds the optional TP/SL touch + MFE/MAE side models. Docstring no
  longer points at the smoke card or `train_hard_gate.py`.
- `build_trade_dataset` semantics canonicalized in the docstring: 3×3
  TP/SL grid, touch-event labels for `tp_hit`/`stop_hit`, pessimistic
  same-bar collision for `winner_10pt_24bar`. `monte_carlo_v9.py` and
  `shap_v9.py` both import this function — single source of truth.
- Core ETL/Pandera/fg-data-profiling stack wired. DXY parity (Yahoo
  `DX-Y.NYB`), Databento trade-side CVD/order-flow features, May 2026
  order-flow threshold review (35% absorption/flush delta, 1.5x volume
  spike, 0.75 ATR range split) are in code. Smoke verification recorded
  in `docs/audits/2026-05-10-v9-core-smoke-verification.md`.
- The locked 15m export exists and validates: 23,513 bars (2025-05-11
  22:00 UTC → 2026-05-10 23:45 UTC), 1,414 long triggers, 1,284 short
  triggers, 19,850 resolved trades after the 3×3 grid expansion, WR
  0.4265, chronological IS/VAL/OOS split 13,895 / 2,952 / 2,953 with
  25-bar embargo (WR 41.67% / 43.60% / 46.90%).
- Auxiliary smoke-validation card defaults updated to point at the same
  15m export — passes end-to-end against the new schema.

**Open work, in order:**

1. Launch the entry-only AG training run:
   `python3 scripts/ag/train_v9_locked.py` (≈2h with the locked 7200s
   time budget; produces predictor + leaderboard + feature_importance
   under `models/warbird_pro_v9/locked_<tag>/entry/`).
2. Run the SHAP gate (Phase 4.5, Gate 1) against the 15m export. See the
   *Validation Gating Before Live Trade Routing* section for what
   counts as a pass.
3. Run the Monte Carlo gate (Phase 4.5, Gate 2) against the OOS split.
4. Only after both gates clear, enable any TradingView alert that filters
   on `model_proba >= 0.75`.
5. After the entry classifier is in production, schedule a `--model-suite`
   run to add the auxiliary TP-touch / SL-touch / MFE / MAE side models
   for the downstream EV/policy layer.

Owner/next trigger: Kirk's go for step 1.

The previous "Hybrid+ 4-card" Optuna chain
(`warbird_pro_v9_exit_cpcv`, `warbird_pro_v9_entry_filter_cpcv`,
`warbird_pro_v9_ag_meta_cpcv`, `warbird_pro_v9_joint_challenger`) is
formally deprecated and superseded by the single `train_v9_locked.py`
trainer. Those profile modules remain on disk for archival reference
only; do not invoke them as a chain.

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
| Use EMA/MA Gate | **true** | `useMaGate` |
| MA Length (SMA, slow) | **100** | `lengthMA` |
| EMA Length (close, fast) | **50** | `lengthEMA` |

**Rule:** Before every dataset build, read the live TradingView indicator
inputs panel and verify the dataset-builder constants match exactly. Pine code
`input.float(default, ...)` defaults are NOT authoritative — the user's saved
TV settings are. Contamination incident (2026-05-05) used dev=4.0, depth=20,
floor=0.50 — all wrong; do not repeat.

**MA training rule:** entry-filter HPO may search `lengthMA` from 90-110 and
`lengthEMA` from 40-60 around the live 100/50 defaults. The Pine gate itself is
fixed SMA(close) slow vs EMA(close) fast; do not reintroduce MA type selection.

### V9 Pine Pattern Set (post-2026-05-09 trim)

- **Bull (1):** `patRisingWindow`
- **Bear (3):** `patBearEngulf`, `patMarubozuBlack`, `patTweezerTop`
- **Dropped 2026-05-09:** `patBullEngulf`, `patPiercing`, `patHaramiBull`,
  `patHaramiBear`
- **HOLD for v10:** Three Line Strike (84% vendor citation unverified — validate
  in Python first before reserving Pine plot budget)

### Core Training Dataset Contract

- **Source:** Databento ES — Trades 365d (footprint reconstruction) + OHLCV
  bars 15m (training resolution; ES 5m only after 15m success per locked
  sequence) + OHLCV 1m (microstructure features only). DXY parity uses
  Yahoo `DX-Y.NYB` for AG/ETL; ICE futures DXY is not licensed to the
  operator account, so the V9 Pine reads `TVC:DXY` instead. DXY was
  subsequently removed from the V9 feature set on the 2026-05-11
  gate-as-feature pivot and replaced by 6E momentum z-score and 6E trend
  code as continuous cross-asset signals.
- **Window:** 2025-05-11 → 2026-05-10 (1y, dense feature coverage; the actual
  built export covers that range). The newer Databento OHLCV-1s 2315d
  download is reserved for a future v10 long-horizon ensemble card, NOT
  Core (would NaN 2/3 of feature surface).
- **Feature surface (123 ml_\* + 6 trade-discoverable = 129 total):**
  V9 Pine ml_* + ETL-derived `ml_cvd_div_bull/bear` (CVD divergence,
  Python-only, zero Pine cost) + 1m microstructure features + Initial
  Balance + volume profile HVN/LVN + UTC-anchored economic-event features
  (CPI/NFP/PPI=13:30 UTC, FOMC=19:00/18:00 UTC seasonal) + Pine input
  knobs (43 of them, e.g. `knob_fib_deviation_manual`, `knob_length_ma`).
- **Label (triple barrier):** `winner_10pt_24bar` = 1 if **this combo's**
  TP price touched before its SL price within `max_hold_bars` (24 bars =
  6h on 15m, 2h on 5m); 0 if SL touched first OR if TP and SL touched on
  the same bar (pessimistic same-bar policy — intrabar sequencing is
  unobservable). Rows where neither barrier resolves within the window
  are DROPPED, not relabeled. The literal "10pt" in the column name is
  historical — it denotes the operator's minimum-acceptable winner and
  is only used as the fallback TP1 distance when no `ml_trade_tp` is
  supplied; the actual TP price is derived from the 3-TP fib ladder.
- **Discoverable trade grid:** Each entry candidate expands into 9 rows —
  3 TP ratios {1.000, 1.236, 1.618} × 3 SL ATR multiples {1.0, 1.5, 2.0}.
  Each row carries its own (`sl_atr_mult`, `tp_ratio`, `tp_family_code`,
  `target_distance_points`, `stop_distance_points`, `rr_ratio`) plus
  the resolution label. The classifier learns from the entire grid so
  inference can rank trade-shape variants, not just entry direction.
- **Auxiliary touch-event labels** (`tp_hit`, `stop_hit`) record physical
  barrier touches at the resolution bar, NOT resolution outcomes — see
  the canonical docstring at
  `scripts/ag/train_v9_locked.py::build_trade_dataset`. On same-bar
  collisions both auxiliary flags are 1 even though `winner_10pt_24bar=0`.
  Trained separately under `--model-suite` for the downstream EV layer.

### Kirk's Trade Preferences

- **Target move:** 10 ES points (40 ticks, $500/contract).
- **Target SL:** 1.0 ATR. **Max SL:** 2.0 ATR. `stopAtrMult` range (0.75, 2.0).
- **Target breakeven range:** 1–3R. `targetRiskMultiple` range (1.0, 3.0).
- **Inference threshold:** `proba > 0.75` for Grade A+ entries.
  `eval_metric='log_loss'` + `calibrate=True` ensures the threshold = real WR.
- **Session filter:** feature only (`ml_session_ny/london/asia`,
  `ml_minutes_from_open`), NOT a pre-filter — let AG learn the regime.

### V9 Core Training Surface

| File | Role | Status |
|------|------|--------|
| `scripts/ag/train_v9_locked.py` | Production V9 AutoGluon trainer (entry classifier; `--model-suite` adds TP/SL/MFE/MAE side models) | Ready for live training |
| `scripts/duckdb_local/cards/core_training/2026_05_09_warbird_pro_autogluon_core.py` | Auxiliary smoke-validation card (records validation report to local study DB; does NOT invoke AG) | Live |

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

**Side card (post-Core):** `scripts/duckdb_local/cards/side_models/` will hold a MAE
regression model that predicts maximum adverse excursion per trade. Used for
SL sizing AFTER the Core binary classifier ranks setups. Trained separately;
NOT grafted into Core.

### Production Launch Sequence (2026-05-12)

The V9 Core path is invoked directly — there is no Optuna wrapper, and the
legacy `scripts/ag/train_hard_gate.py` (Postgres `ag_training_runs` table,
`baseline.DEFAULT_DSN`) is on the *legacy* path, not the V9 path. The
training-hard-gate skill describes that legacy flow and does not apply here.

```bash
# 1. Train the entry classifier (default 15m export, 2h time budget)
python3 scripts/ag/train_v9_locked.py
#    → models/warbird_pro_v9/locked_<tag>/entry/predictor.pkl
#    → models/warbird_pro_v9/locked_<tag>/entry/leaderboard.csv
#    → models/warbird_pro_v9/locked_<tag>/entry/feature_importance.csv
#    → models/warbird_pro_v9/locked_<tag>/v9_winner_clf_summary.json

# 2. SHAP gate (Phase 4.5, Gate 1)
python3 scripts/ag/shap_v9.py \
    --predictor-dir models/warbird_pro_v9/locked_<tag> \
    --csv scripts/duckdb_local/workspaces/warbird_pro_core/exports/es_15m_core.csv
#    → artifacts/shap_v9/shap_<ts>/shap_feature_summary.csv (+ per_class,
#      temporal_stability, calibration, redundancy, drop_candidates, summary.md)

# 3. Monte Carlo gate (Phase 4.5, Gate 2)
python3 scripts/ag/monte_carlo_v9.py \
    --predictor-path models/warbird_pro_v9/locked_<tag> \
    --csv scripts/duckdb_local/workspaces/warbird_pro_core/exports/es_15m_core.csv \
    --split oos
#    → artifacts/mc_v9/<tag>/ (overall + per-direction P&L, threshold sweep,
#      calibration, regime stability, streak profile)

# 4. Only after both gates pass — enable the TV alert that filters on
#    model_proba >= 0.75. Until then, the alert stays disabled.
```

The `--model-suite` flag on `train_v9_locked.py` additionally fits TP-touch,
SL-touch, MFE-regression, and MAE-regression predictors (~10h total).
Entry-only first; suite later, once the entry classifier passes both gates.
