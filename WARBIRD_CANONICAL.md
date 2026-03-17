# WARBIRD PRO — CANONICAL SPECIFICATION

**Version:** 1.0 · **Date:** 2026-03-16 · **Author:** Kirk Musick, MS, MBA · **Status:** ACTIVE

This is the single source of truth for Warbird Pro. All other planning docs, AGENTS.md references, and prior specs defer to this document where they conflict.

---

## 1. WHAT WARBIRD IS

Warbird is an ML-powered S&P 500 Micro E-mini (MES) futures intelligence platform. It combines a multi-timeframe conviction system with a machine learning core forecaster to produce trade signals with probabilistic targets and risk-calibrated stops.

It is NOT a simple candlestick pattern matcher. The old Touch → Hook → Go state machine (ported from BHG/rabid-raccoon) is legacy scaffolding and does not represent the real methodology.

---

## 2. PLATFORM & STACK

| Layer | Technology |
|-------|-----------|
| Framework | Next.js (App Router) on Vercel |
| Database | Supabase (Postgres, Auth, Realtime, RLS) — NO Prisma, NO ORM |
| UI | Tailwind v4, shadcn/ui (56 components) |
| Chart | Lightweight Charts v5.1.0 (candles), Recharts (dashboard) |
| Live Data | mes-catchup Vercel Cron (5 min) → Databento Historical API → Supabase |
| Scheduling | Vercel Cron Jobs (21 of 100 used) |
| ML Training | AutoGluon TabularPredictor on Apple M4 Pro |
| Volatility | GJR-GARCH(1,1) with Student-t innovations |
| Repo | github.com/zincdigitalofmiami/warbird-pro |
| Live | warbird-pro.vercel.app |

**All new code lives in Supabase + Vercel.** No legacy rabid-raccoon code carried forward. New TypeScript libraries, new Python scripts, new cron routes. Pine Script exists on a TradingView chart but is NOT bolted into the platform — holding off on Pine integration.

### Script Organization

All new dataset, training, and inference scripts live in `scripts/warbird/`:

```
scripts/warbird/
  build-warbird-dataset.ts    # Canonical dataset builder (Supabase-native)
  train-warbird.py            # AutoGluon training (canonical AG config)
  predict-warbird.py          # Hourly inference → WarbirdSignal v1.0
  fib-engine.ts               # 1H fib geometry (measured moves, retracements, extensions)
  garch-engine.py             # GJR-GARCH(1,1) volatility estimation
  daily-layer.ts              # 200d MA bias + continuous features
  structure-4h.ts             # 4H swing structure detection
  conviction-matrix.ts        # Multi-layer conviction scoring
```

Existing `scripts/` files (backfill.py, mes_aggregation.py) stay for local research. `live-feed.py` is deprecated — replaced by `mes-catchup` Vercel Cron.

### MES Bar Authority Map

Warbird v1 uses a single authority per MES timeframe:

- `mes_1m` — direct from Databento
- `mes_1h` — direct from Databento
- `mes_1d` — direct from Databento for macro bias only
- `mes_15m` — derived from stored `mes_1m`
- `mes_4h` — derived from stored `mes_1h`

This is intentional. Do not create duplicate live writer paths for the same timeframe. Reconciliation is allowed. A second primary writer is not.

### Persisted Output Shape — Normalized + API Projection

Engine output is persisted as **normalized Supabase tables** with a clean **API projection layer** on top.

**Why normalized:** Each layer writes its own output independently. No giant JSON blobs. Clean indexes. Queryable. Supabase Realtime works per-table.

**Why API projection:** The WarbirdSignal v1.0 contract is assembled at read time by joining layer outputs. The API route composes the full signal from normalized pieces. Dashboard and future Pine Script consumers hit the API, not raw tables.

```
DB Tables (normalized, each layer writes independently):
  warbird_daily_bias    → daily 200d MA bias + features
  warbird_structure_4h  → 4H trend/swing state
  warbird_forecasts_1h  → core forecaster predictions (price, MAE, MFE)
  warbird_conviction    → combined conviction assessment
  warbird_setups        → active setup geometry (entry, SL, TP1, TP2)
  warbird_setup_events  → outcome lifecycle (TRIGGERED, TP1_HIT, TP2_HIT, STOPPED, EXPIRED)
  warbird_risk          → GARCH zones, risk context snapshot

API Projection (composed at read time):
  /api/warbird/signal   → assembles WarbirdSignal v1.0 from all tables
  /api/warbird/history  → historical signals for backtesting/review
```

### Legacy Table Cutover — Rebuild in Place

The existing `warbird_setups` and `forecasts` tables are rebuilt in place via migration. No parallel tables, no rename dance. One migration drops the old Touch/Hook/Go schema and replaces it with the new layered engine tables. The old data is stale (wrong methodology) — nothing to preserve.

Migration order:
1. Drop old `warbird_setups` and `forecasts` tables (and associated RLS/Realtime)
2. Create new normalized tables (warbird_daily_bias, warbird_structure_4h, warbird_forecasts_1h, warbird_conviction, warbird_setups, warbird_setup_events, warbird_risk)
3. Re-enable RLS on all new tables
4. Re-enable Realtime on warbird_forecasts_1h, warbird_conviction, warbird_setups, warbird_setup_events

`warbird_setups` name is reused but with a completely new schema reflecting actual setup geometry (entry, SL, TP1, TP2, conviction level, fib context, volume confirmation) rather than the old Touch/Hook/Go phases.

---

## 3. THE 3-LAYER CONVICTION ARCHITECTURE

**Layer 1 — DAILY: 200-Day MA Shadow (Rule-Based)**
- Price vs 200d MA → bias LONG or SHORT
- Counter-trend: allowed but penalized (reduced size, TP1 only)
- Features to model: distance_pct, slope, sessions_on_side, daily_ret, daily_range_vs_avg

**Layer 2 — 4H: Trend & Structure (Rule-Based)**
- HH/HL or LH/LL swing structure
- Confirms or denies daily direction
- Does NOT generate trade geometry (4H fibs = 80-150pt, too wide for day trades)
- Answers: "Which way is the current swing moving?"

**Layer 3 — 1H: Core Forecaster + Fib Geometry (ONE ML Model + Rules)**
- THIS IS WHERE THE FIBS LIVE. THIS IS WHERE TRADES ARE IDENTIFIED.
- ML Model (AutoGluon): predicts 5 fib-relative targets per setup
- Fib Geometry (Rule-Based): measured moves on 1H candles, retracements, extensions
- Entry / SL / TP1 / TP2 computation, 20-40+ point trade targets
- GO/NO-GO determined by fib geometry availability on 1H candles

**Conviction Matrix (Rule-Based)**
- Daily+4H+1H all agree → MAXIMUM conviction (full position)
- Daily+4H agree, 1H weak → HIGH/MODERATE (reduced size)
- 4H+1H agree, Daily neutral → MODERATE (reduced size, TP1 focus)
- 4H+1H agree, Daily against → LOW / COUNTER-TREND (TP1 only)
- Daily against + other disagreement → NO TRADE

---

## 4. TRADE TARGETS: TP1 AND TP2

- **TP1** — 1.236 fib extension. First profit target. Partial exit.
- **TP2** — 1.618 fib extension. Second target. Full exit.

No runner logic in v1. Counter-trend trades: TP1 only, reduced size.

---

## 5. ONE ML MODEL IN v1

The 1H Core Forecaster is the ONLY ML model in Warbird v1.

**NOT in v1:** 15M ML trigger model (v2), runner logic (v2), setup outcome scorer (v3), Monte Carlo (v2), pinball/quantile regression (v2/v3).

---

## 6. CANONICAL DATASET — 1H CORE FORECASTER

**Rows:** One per 1H fib setup (only bars where `buildFibGeometry()` returns non-null)
**Training window:** 2 full years back to January 1, 2024
**Expected columns:** ~150-170 features + 5 targets + 1 sample_weight
**Builder:** `build-warbird-dataset.ts` (all new, Supabase-native)

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
| Raw FRED as-of (47+ series forward-filled) | ~90-95 | P1 Done |
| Derived FRED (velocity, percentile, momentum) | ~30 | P2 Pending |
| Cross-asset futures (ratios, correlations, alignment) | ~15 | P3 Pending |
| Calendar events (FOMC/CPI/NFP flags, proximity) | ~6 | P4 Pending |
| News signals (layer counts, net sentiment) | ~4 | P5 Pending |
| Surprise z-scores (3yr z + regime z + raw per report; HIGHEST ROI) | ~24 | Pending backfill |
| Fib structure (confluence, distance to levels, anchor age, grade) | 12 | Build |
| Fib trigger context (which fib line used, fib ratio at entry, distance to zone edges, fib alignment across windows) | ~8 | Build |
| Cross-asset correlation at trigger (NQ/DXY/VIX/yield alignment at setup moment) | ~8 | Build |
| Yield curve (2s10s, 5s10s, 2s30s, real yield, slope, inversion) | 7 | Build |
| Vol regime (VIX, VX term structure, GARCH sigma, vol-of-vol, vol state at trigger moment) | 12 | Build |
| Geopolitical/risk (GPR, TrumpEffect, EPU, combined regime) | 10 | Pending ingestion |
| Trade feedback (win rates, R-multiples, streaks, frequency) | ~12-15 | Pending |
| Volume features (ratio, expansion on trigger bar, relative to session avg, profile at TP1, trend post-trigger, 15M volume state at entry) | ~12 | Build |
| Regime features (REGIME_START, days_into_regime, label) | 3 | Build |
| Sample weight (exponential decay: newest=1.0, 2yr ago=0.3) | 1 | Build |

### Dual-Lookback Columns (Policy-Sensitive Features)

For every policy-sensitive feature, carry BOTH regime-anchored (since Jan 20, 2025) AND standard rolling (5d, 20d, etc.). Example: `dollar_momentum_5d` + `dollar_momentum_regime`.

### Raw Companion Columns

For every normalized/transformed feature, also carry the raw continuous value. Z-scores compress at extremes. Trees handle raw values at record levels naturally.

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

| Timeframe | Role | ML? | Fibs? |
|-----------|------|-----|-------|
| Daily | 200d MA directional shadow | No | No |
| 4H | Trend/structure confirmation | No (v1) | No (too wide) |
| 1H | Core forecaster + fib geometry + GO/NO-GO | YES | YES |

The fib engine operates on 1H candles only. GO/NO-GO is determined by fib geometry availability on 1H. Daily bars are macro bias only and are not fib anchors in v1.

---

## 14. INFERENCE OUTPUT — WarbirdSignal v1.0

**Persistence:** Normalized Supabase tables (each layer writes independently).
**Projection:** `/api/warbird/signal` assembles the full WarbirdSignal v1.0 at read time by joining layer outputs. Consumers never query raw tables directly.

Versioned schema consumed by API → Dashboard → (future) Pine Script:

- **Metadata:** version, generatedAt, symbol
- **Daily layer:** bias (BULL/BEAR/NEUTRAL), distance_pct, slope
- **4H structure:** bias_4h, agrees_with_daily
- **1H directional:** bias_1h, price_target_1h/4h, mae/mfe_band_1h/4h, confidence
- **Conviction:** level (MAXIMUM/HIGH/MODERATE/LOW/NO_TRADE), counter_trend
- **Setup:** direction, fibLevel, entry, SL, TP1, TP2
- **Risk:** garch_vol, gpr_level, trump_effect, vix_level, regime, days_into_regime
- **GARCH zones:** 1σ and 2σ boundaries
- **Feedback:** win_rate_last20, streak, avg_r, setup_frequency_7d

---

## 15. WHAT EXISTS AND IS VALID

- Fib geometry on chart (FibLinesPrimitive, confluence scoring, 10 levels)
- MES schema and writer paths for `mes_1m`, `mes_15m`, `mes_1h`, `mes_4h`, `mes_1d`
- Supabase schema (10 migrations, including the Warbird v1 cutover)
- Auth flow, protected routes, admin dashboard structure
- Canonical Warbird routes (`/api/warbird/signal`, `/api/warbird/history`)
- Cron route surface defined (with some routes still under audit or incomplete)
- Raw FRED integration (~90-95 cols, P1 done)
- Chart rendering (LiveMesChart.tsx, gap-free mapping, correct colors/fibs)

---

## 16. WHAT IS STALE / TO BE REPLACED

- `setup-engine.ts` (Touch → Hook → Go) — old BHG pattern matcher, not real methodology
- Older pre-cutover docs and plan references that still describe Touch/Hook/Go or retired `/api/setups` and `/api/forecasts` surfaces
- Any duplicate MES writer path that acts like a second primary authority instead of reconciliation

---

## 17. WHAT NEEDS TO BE BUILT

### Operational Priorities
1. Keep docs and control surfaces aligned to canonical Warbird v1.
2. Restore and verify hosted MES continuity for the authority map above.
3. Fill missing support data required for trigger/model validation.
4. Dry-test deterministic engine layers against real historical data.
5. Train only after data continuity and upstream integrity are proven.

---

## 18. HARD RULES

### Data
- NEVER mock data. Real or nothing.
- NEVER query inactive Databento symbols.
- Point-in-time features ONLY (strictly < current_row_timestamp).

### Architecture
- ONE ML model in v1. Period.
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

## 19. WARBIRD ROADMAP

### v1 (Current Scope)
ONE ML model (1H), rule-based layers (Daily/4H/conviction), GARCH, full feature pipeline, regime-anchored features, WarbirdSignal v1.0. 5 fib-relative targets. No runners.

### v2 (After v1 Stable)
15M ML trigger model, runner logic, Monte Carlo on validated GARCH, pinball loss, fold upgrade (5→8 A/B), Pine Script integration.

### v3 (After Setup Count Grows)
Setup outcome scorer P(T1)/P(T2)/P(Runner|T1), survival model, FinBERT sentiment, hyperparameter optimization.

---

*Designed and architected by Kirk Musick, MS, MBA*
