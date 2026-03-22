# WARBIRD PRO — CANONICAL SPECIFICATION

> ARCHIVED REFERENCE ONLY. Do not use this as the active implementation plan.  
> Active plan: `docs/plans/2026-03-20-ag-teaches-pine-architecture.md`

**Version:** 2.0 · **Date:** 2026-03-18 · **Author:** Kirk Musick, MS, MBA · **Status:** ARCHIVED REFERENCE

This document is a historical reference snapshot. It is not the current source of truth.

---

## 1. WHAT WARBIRD IS

Warbird is an ML-powered S&P 500 Micro E-mini (MES) futures intelligence platform. It uses a 15m-primary geometry and probability engine to produce trade signals with probabilistic targets and risk-calibrated stops.

It is NOT a simple candlestick pattern matcher. The old Touch → Hook → Go state machine (`setup-engine.ts`) is legacy scaffolding and does not represent the real methodology.

---

## 2. PLATFORM & STACK

| Layer | Technology | Status |
|-------|-----------|--------|
| Framework | Next.js (App Router) on Vercel | Working |
| Cloud Database | Supabase (Postgres, Auth, Realtime, RLS) — NO Prisma, NO ORM | Working |
| Local Database | Plain PostgreSQL via Homebrew (training warehouse) | Planned |
| UI | Tailwind v4, shadcn/ui (56 components) | Working |
| Chart | Lightweight Charts v5.1.0 (candles), Recharts (dashboard) | Working |
| Live Data | mes-catchup Vercel Cron (5 min) → Databento ohlcv-1m → Supabase | Working |
| Scheduling | Vercel Cron Jobs (13 routes, 23 schedules in vercel.json) | Working |
| ML Training | AutoGluon TabularPredictor on Apple M4 Pro | Scripts exist, not yet trained |
| Volatility | GJR-GARCH(1,1) with Student-t innovations | Script exists |
| Repo | github.com/zincdigitalofmiami/warbird-pro | Active |
| Live | warbird-pro.vercel.app | Deployed |

### Dual-Database Architecture (In Progress)

The project is transitioning to a dual-database model:
- **Cloud Supabase** — auth, dashboard reads, Realtime, published signals, chart serving
- **Local PostgreSQL** — retained training data, feature engineering, model training, inference

This boundary is governed by the active architecture plan (`docs/plans/2026-03-20-ag-teaches-pine-architecture.md`). Current state: everything runs through cloud Supabase. Local PG does not exist yet.

### Script Organization

```
scripts/warbird/
  build-warbird-dataset.ts    # Canonical dataset builder (26 KB, functional)
  trigger-15m.ts              # 1m microstructure + LuxAlgo + TTM Squeeze (24 KB, functional)
  train-warbird.py            # AutoGluon training (functional, not yet run on real data)
  predict-warbird.py          # Inference → warbird_forecasts_1h + warbird_risk (functional)
  fib-engine.ts               # 15m-primary fib geometry (functional)
  garch-engine.py             # GJR-GARCH(1,1) volatility estimation (functional)
  daily-layer.ts              # 200d MA bias + continuous features (functional)
  structure-4h.ts             # 4H swing structure detection (functional)
  conviction-matrix.ts        # Multi-layer conviction scoring (functional)
```

`scripts/live-feed.py` is DEPRECATED. Do not use as a production writer.

### MES Bar Authority Map

**What actually works today:**

| Layer | Table | Source | Status |
|-------|-------|--------|--------|
| `mes_1s` | Exists in DB (migration 011) | **Nothing writes to it** | Planned: ephemeral live-bar formation via ohlcv-1s |
| `mes_1m` | Written by mes-catchup cron | Databento ohlcv-1m (direct fetch) | **Working** |
| `mes_15m` | Derived in TypeScript | Aggregated from mes_1m in mes-catchup cron | **Working** |
| `mes_1h` | Written by mes-catchup cron | Databento ohlcv-1h (direct fetch) | **Working** |
| `mes_4h` | Derived in TypeScript | Aggregated from mes_1h in mes-catchup cron | **Working** |
| `mes_1d` | Derived in TypeScript | Aggregated from mes_1h (session-based, 5 PM CT) | **Working** |

**Planned target state:**

```
mes_1s (Databento ohlcv-1s, ephemeral, 24-48h TTL)
  → mes_1m (DB aggregation from 1s, retained)
  → mes_15m (DB aggregation from 1m, retained)
  → mes_1h, mes_4h, mes_1d (DB aggregation, retained)
```

`mes_1s` is intended to power real-time forming-bar updates on the chart via Supabase Realtime. It will NOT be retained for training. See Checkpoint 2 decision.

### Persisted Output Shape — Normalized + API Projection

Engine output is persisted as **normalized Supabase tables** with a clean **API projection layer** on top.

```
DB Tables (8 warbird tables, each layer writes independently):
  warbird_daily_bias      → daily 200d MA bias + features
  warbird_structure_4h    → 4H trend/swing state
  warbird_forecasts_1h    → model outputs + probability columns (table name retained for compatibility)
  warbird_triggers_15m    → 15m trigger decision + quality metrics
  warbird_conviction      → combined conviction assessment
  warbird_setups          → active setup geometry (entry, SL, TP1, TP2)
  warbird_setup_events    → outcome lifecycle (TRIGGERED, TP1_HIT, TP2_HIT, STOPPED, EXPIRED)
  warbird_risk            → GARCH zones, risk context snapshot

API Projection (composed at read time):
  /api/warbird/signal     → assembles WarbirdSignal v1.0 from all tables
  /api/warbird/history    → historical signals for backtesting/review
```

---

## 3. THE 3-LAYER DECISION ARCHITECTURE

**Layer 1 — DAILY: Context Layer (Rule-Based)**
- Price vs 200d MA → bias LONG or SHORT
- Counter-trend: allowed but penalized (reduced size, TP1 only)
- Features to model: distance_pct, slope, sessions_on_side, daily_ret, daily_range_vs_avg
- **Implementation:** detect-setups cron writes warbird_daily_bias

**Layer 2 — 4H: Context Layer (Rule-Based)**
- HH/HL or LH/LL swing structure
- Confirms or denies daily direction
- Does NOT generate primary trade geometry
- **Implementation:** detect-setups cron writes warbird_structure_4h

**Layer 3 — 15M: Core Geometry + Probability Model (ONE ML Model + Rules)**
- THIS IS WHERE THE FIBS LIVE. THIS IS WHERE TRADES ARE IDENTIFIED.
- ML Model (AutoGluon): scores path probabilities per 15m setup
- Fib Geometry (Rule-Based): measured moves on 15m candles, retracements, extensions
- Entry / SL / TP1 / TP2 computation, 20-40+ point trade targets
- GO/NO-GO determined by 15m geometry + trigger-state confirmation
- **Implementation:** detect-setups cron reads warbird_forecasts_1h, computes trigger, writes warbird_triggers_15m

**Conviction Matrix (Rule-Based)**
- Daily+4H+15m all agree → MAXIMUM conviction (full position)
- Daily+4H agree, 15m weak → HIGH/MODERATE (reduced size)
- 4H+15m agree, Daily neutral → MODERATE (reduced size, TP1 focus)
- 4H+15m agree, Daily against → LOW / COUNTER-TREND (TP1 only)
- Daily against + other disagreement → NO TRADE
- **Implementation:** detect-setups cron writes warbird_conviction

---

## 4. TRADE TARGETS: TP1 AND TP2

- **TP1** — 1.236 fib extension. First profit target. Partial exit.
- **TP2** — 1.618 fib extension. Second target. Full exit.

No runner logic in v1. Counter-trend trades: TP1 only, reduced size.

---

## 5. ONE ML MODEL IN v1 (15M PRIMARY)

The 15m primary geometry scorer is the ONLY ML model in Warbird v1.

**NOT in v1:** secondary model stacks, runner logic (v2), setup outcome scorer (v3), Monte Carlo (v2), pinball/quantile regression (v2/v3).

**Current state:** Model scripts exist (`train-warbird.py`, `predict-warbird.py`). No model has been trained yet. The forecast cron delegates to an external writer URL.

---

## 6. CANONICAL DATASET — 15M PRIMARY MODEL

**Rows:** One per 15m fib setup (only bars where `buildFibGeometry()` returns non-null)
**Training window:** 2 full years back to January 1, 2024
**Expected columns:** ~150-170 features + 5 targets + 1 sample_weight
**Builder:** `scripts/warbird/build-warbird-dataset.ts` (functional, Supabase-native)

### 5 Fib-Relative Target Labels

- `reached_tp1` — Binary: did price reach TP1 within 100 bars?
- `reached_tp2` — Binary: did price reach TP2 within 100 bars?
- `setup_stopped` — Binary: did price hit stop loss within 100 bars?
- `max_favorable_excursion` — Regression: max points in favorable direction within 100 bars
- `max_adverse_excursion` — Regression: max points in adverse direction within 100 bars

### Feature Groups

| Group | ~Cols | Status |
|-------|-------|--------|
| MES technicals (OHLCV, ATR, RSI, MACD, Bollinger, Stoch, ADX, OBV, VWAP) | 22 | Build |
| Daily context (200d MA distance, slope, sessions, daily ret/range) | 6 | Build |
| Time features (hour, dow, session, RTH, rollover, witching) | 8 | Build |
| EMAs (distance to 200/50/21, stack order, spreads, crossover) | 8 | Build |
| Raw FRED as-of (47+ series forward-filled) | ~90-95 | Ingestion working |
| Derived FRED (velocity, percentile, momentum) | ~30 | Pending |
| Cross-asset futures (ratios, correlations, alignment) | ~15 | Ingestion working |
| Calendar events (FOMC/CPI/NFP flags, proximity) | ~6 | Ingestion working |
| News signals (layer counts, net sentiment) | ~4 | Ingestion working |
| Surprise z-scores (3yr z + regime z + raw per report) | ~24 | Pending backfill |
| Fib structure (confluence, distance to levels, anchor age, grade) | 12 | Build |
| Fib trigger context (fib line, ratio at entry, distance to zone edges) | ~8 | Build |
| Cross-asset correlation at trigger (NQ/DXY/VIX/yield alignment) | ~8 | Build |
| Yield curve (2s10s, 5s10s, 2s30s, real yield, slope, inversion) | 7 | Build |
| Vol regime (VIX, VX term structure, GARCH sigma, vol-of-vol) | 12 | Build |
| Geopolitical/risk (GPR, TrumpEffect, EPU, combined regime) | 10 | Ingestion working |
| Trade feedback (win rates, R-multiples, streaks, frequency) | ~12-15 | Pending |
| Volume features (ratio, expansion, session avg, profile, trend) | ~12 | Build |
| Regime features (REGIME_START, days_into_regime, label) | 3 | Build |
| Sample weight (exponential decay: newest=1.0, 2yr ago=0.3) | 1 | Build |

### Dual-Lookback Columns (Policy-Sensitive Features)

For every policy-sensitive feature, carry BOTH regime-anchored (since Jan 20, 2025) AND standard rolling (5d, 20d, etc.).

### Raw Companion Columns

For every normalized/transformed feature, also carry the raw continuous value. Trees handle raw values at record levels naturally.

---

## 7. CANONICAL AUTOGLUON CONFIGURATION

```python
predictor = TabularPredictor(
    label=target_col,
    problem_type=problem_type,          # 'binary' or 'regression' per target
    eval_metric=eval_metric,            # 'roc_auc' or 'root_mean_squared_error'
    path=output_dir,
)
predictor.fit(
    train_data=train,
    presets='best_quality',
    num_bag_folds=5,                    # LOCKED
    num_stack_levels=1,                 # Not 2
    dynamic_stacking='auto',
    excluded_model_types=['KNN', 'FASTAI'],
    ag_args_ensemble={'fold_fitting_strategy': 'sequential_local'},
)
# Active models: GBM, CAT, XGB, XT, RF, NN_TORCH
```

---

## 8. GARCH ENGINE

GJR-GARCH(1,1) with Student-t innovations. Captures leverage effect. Estimation window: regime-anchored from Jan 20, 2025, expanding. Output: raw sigma AND volatility ratio (forecast / realized).

Script: `scripts/warbird/garch-engine.py`

---

## 9. REGIME ANCHOR — JANUARY 20, 2025

```typescript
export const REGIME_START = new Date('2025-01-20T00:00:00Z')
export const REGIME_LABEL = 'trump_2'
```

Training data spans full 2 years (Jan 1, 2024 → present). Model sees both regimes. Regime features tell it which one. Update one constant when regime changes, rebuild.

---

## 10. VOLUME IS LOAD-BEARING

Volume is NOT a generic feature. Specific roles:

- **Core forecaster:** vol_ratio, volume profile, abnormal volume as regime indicator
- **Model feature:** volume state at fib setup moment enters the model — the model learns which volume conditions produce winning setups vs. fakeouts

---

## 11. RISK SIGNALS ARE FEATURES, NOT FILTERS

GPR, TrumpEffect, GARCH, VIX — all enter model as columns. AutoGluon learns weights. No hardcoded filter hierarchy. Binary flags replaced with continuous values (e.g., `jpy_daily_change_pct` not `jpySpikeFlag`).

---

## 12. UNPRECEDENTED MARKET DESIGN

Raw companions for every normalization. No hardcoded ceilings. No clipping. Trees handle record levels naturally. NN_TORCH may struggle at extremes but ensemble downweights it.

---

## 13. TIMEFRAME STRATEGY

| Timeframe | Role | ML? | Fibs? | Status |
|-----------|------|-----|-------|--------|
| 1s | Forming-bar ingestion (ephemeral) | No | No | Table exists, no writer yet |
| 1m | Trigger-resolution + microstructure | No (v1) | Support only | Working (Databento direct) |
| 15m | Core geometry + primary model + GO/NO-GO | YES | YES | Working (derived from 1m) |
| 1h | Context only | No (v1) | No (v1) | Working (Databento direct) |
| 4H | Trend/structure confirmation | No (v1) | No (too wide) | Working (derived from 1h) |
| Daily | 200d MA directional shadow | No | No | Working (derived from 1h) |

---

## 14. INFERENCE OUTPUT — WarbirdSignal v1.0

**Persistence:** Normalized Supabase tables (each layer writes independently).
**Projection:** `/api/warbird/signal` assembles the full WarbirdSignal v1.0 at read time by joining layer outputs.

Versioned schema consumed by API → Dashboard → (future) Pine Script:

- **Metadata:** version, generatedAt, symbol
- **Daily layer:** bias (BULL/BEAR/NEUTRAL), distance_pct, slope
- **4H structure:** bias_4h, agrees_with_daily
- **15m directional:** setup_score, prob_hit_sl_first, prob_hit_pt1_first, prob_hit_pt2_after_pt1, expected_max_extension
- **Conviction:** level (MAXIMUM/HIGH/MODERATE/LOW/NO_TRADE), counter_trend
- **Setup:** direction, fibLevel, entry, SL, TP1, TP2
- **Risk:** garch_sigma, garch_vol_ratio, gpr_level, trump_effect, vix_level, regime, days_into_regime
- **GARCH zones:** 1σ and 2σ boundaries

---

## 15. WHAT WORKS END-TO-END (Verified 2026-03-18)

1. **MES chart pipeline:** Databento → mes-catchup cron (ohlcv-1m + ohlcv-1h) → mes_1m/1h → TS aggregation → mes_15m/4h/1d → Realtime → LiveMesChart
2. **Cross-asset ingestion:** Databento → cross-asset cron (sharded) → cross_asset_1h/1d
3. **FRED ingestion:** FRED API → 10 fred crons (staggered daily) → 10 econ_*_1d tables (38 series)
4. **News/events:** Google News RSS, GPR XLS, Federal Register API, econ calendar → respective tables
5. **Setup detection:** detect-setups cron (6-layer: daily → 4H → forecast gate → 15m fib → 1m trigger → conviction) → warbird_* tables
6. **Trade scoring:** score-trades cron monitors active setups → updates status/events
7. **Chart rendering:** LiveMesChart.tsx + fib lines, forecast targets, setup markers, pivot lines
8. **Auth flow:** Login, signup, forgot-password, middleware session refresh
9. **API surface:** /warbird/signal, /warbird/history, /live/mes15m, /pivots/mes, /admin/status

---

## 16. WHAT DOES NOT WORK YET (Verified 2026-03-18)

1. **mes_1s ingestion** — table + Realtime exist but nothing writes to it. Planned: ohlcv-1s via cron.
2. **1s → 1m derivation** — mes_1m is fetched directly from Databento, not derived from mes_1s.
3. **Forecast writer** — cron route exists but delegates to external URL. No built-in inference pipeline.
4. **ML model training** — scripts exist, no model trained yet. Need data continuity first.
5. **Local training database** — planned (plain PostgreSQL), not set up.
6. **DB-side aggregation** — all aggregation is TypeScript in cron routes. No Postgres functions.
7. **Type generation** — no `supabase gen types`. Types manually defined in lib/warbird/types.ts.
8. **Data continuity validation** — no systematic gap detection.
9. **Feature engineering** — all in scripts, none pre-computed in DB.
10. **coverage_log, models tables** — schemas exist, no active writers.

---

## 17. HARD RULES

### Data
- NEVER mock data. Real or nothing.
- NEVER query inactive Databento symbols.
- Point-in-time features ONLY (strictly < current_row_timestamp).

### Architecture
- ONE ML model in v1. Period.
- 15m is the primary decision/model/chart timeframe.
- No continuous local-machine runtime for price ingestion or chart serving.
- Risk signals are FEATURES, not FILTERS.
- Raw companion for every normalized feature.
- No hardcoded ceilings or clipping.
- Dual-lookback for policy-sensitive features.

### Code
- Supabase client only. NO Prisma. NO ORM.
- `series.update()` for live ticks, `setData()` only on initial load.
- `npm run build` must pass before every push.
- One task at a time. Complete fully.
- No dependencies added without Kirk's approval.

### Training
- 5 folds max. Locked.
- num_stack_levels=1.
- Sequential training on Apple Silicon.
- Close Ollama during training.

### Process
- State understanding before executing.
- Confirm before destructive/irreversible actions.
- No git push --force, no git reset --hard.

---

## 18. WARBIRD ROADMAP

### v1 (Current Scope)
ONE ML model (15m primary), context layers (Daily/4H), GARCH, full feature pipeline, regime-anchored features, WarbirdSignal v1.0. 5 fib-relative targets. No runners.

### v2 (After v1 Stable)
Runner logic, Monte Carlo on validated GARCH, pinball loss, fold upgrade (5→8 A/B), Pine Script integration.

### v3 (After Setup Count Grows)
Setup outcome scorer P(T1)/P(T2)/P(Runner|T1), survival model, FinBERT sentiment, hyperparameter optimization.

---

*Designed and architected by Kirk Musick, MS, MBA*
