# WARBIRD PRO — CANONICAL SPECIFICATION

**Version:** 1.0 · **Date:** 2026-03-15 · **Author:** Kirk Musick, MS, MBA · **Status:** ACTIVE

This is the single source of truth for Warbird Pro. All other planning docs, AGENTS.md references, and prior specs defer to this document where they conflict.

---

## 1. WHAT WARBIRD IS

Warbird is an ML-powered S&P 500 Micro E-mini (MES) futures intelligence platform. It combines a multi-timeframe conviction system with a machine learning core forecaster to produce trade signals with probabilistic targets, risk-calibrated stops, and runner management.

It is NOT a simple candlestick pattern matcher. The old Touch → Hook → Go state machine (ported from BHG/rabid-raccoon) is legacy scaffolding and does not represent the real methodology.

---

## 2. PLATFORM & STACK

| Layer | Technology |
|-------|-----------|
| Framework | Next.js (App Router) on Vercel |
| Database | Supabase (Postgres, Auth, Realtime, RLS) — NO Prisma, NO ORM |
| UI | Tailwind v4, shadcn/ui (56 components) |
| Chart | Lightweight Charts v5.1.0 (candles), Recharts (dashboard) |
| Live Data | Python sidecar → Databento Live API → Supabase |
| Scheduling | Vercel Cron Jobs (20 of 100 used) |
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
  trigger-15m.ts              # 15M entry confirmation logic
  conviction-matrix.ts        # Multi-layer conviction scoring
```

Existing `scripts/` files (live-feed.py, backfill.py, mes_aggregation.py) stay where they are — they're data pipeline, not Warbird engine.

### Persisted Output Shape — Normalized + API Projection

Engine output is persisted as **normalized Supabase tables** with a clean **API projection layer** on top.

**Why normalized:** Each layer writes its own output independently. No giant JSON blobs. Clean indexes. Queryable. Supabase Realtime works per-table.

**Why API projection:** The WarbirdSignal v1.0 contract is assembled at read time by joining layer outputs. The API route composes the full signal from normalized pieces. Dashboard and future Pine Script consumers hit the API, not raw tables.

```
DB Tables (normalized, each layer writes independently):
  warbird_daily_bias    → daily 200d MA bias + features
  warbird_structure_4h  → 4H trend/swing state
  warbird_forecasts_1h  → core forecaster predictions (price, MAE, MFE)
  warbird_triggers_15m  → 15M GO/NO-GO decisions
  warbird_conviction    → combined conviction assessment
  warbird_setups        → active setup geometry (entry, SL, TP1, TP2)
  warbird_setup_events  → outcome lifecycle (TRIGGERED, TP1_HIT, TP2_HIT, RUNNER_STARTED, RUNNER_EXITED, STOPPED, EXPIRED, PULLBACK_REVERSAL)
  warbird_risk          → GARCH zones, risk context snapshot

API Projection (composed at read time):
  /api/warbird/signal   → assembles WarbirdSignal v1.0 from all tables
  /api/warbird/history  → historical signals for backtesting/review
```

### Legacy Table Cutover — Rebuild in Place

The existing `warbird_setups` and `forecasts` tables are rebuilt in place via migration. No parallel tables, no rename dance. One migration drops the old Touch/Hook/Go schema and replaces it with the new layered engine tables. The old data is stale (wrong methodology) — nothing to preserve.

Migration order:
1. Drop old `warbird_setups` and `forecasts` tables (and associated RLS/Realtime)
2. Create new normalized tables (warbird_daily_bias, warbird_structure_4h, warbird_forecasts_1h, warbird_triggers_15m, warbird_conviction, warbird_setups, warbird_setup_events, warbird_risk)
3. Re-enable RLS on all new tables
4. Re-enable Realtime on warbird_forecasts_1h, warbird_conviction, warbird_setups, warbird_setup_events

`warbird_setups` name is reused but with a completely new schema reflecting actual setup geometry (entry, SL, TP1, TP2, conviction level, fib context, volume confirmation) rather than the old Touch/Hook/Go phases.

---

## 3. THE 4-LAYER CONVICTION ARCHITECTURE

**Layer 1 — DAILY: 200-Day MA Shadow (Rule-Based)**
- Price vs 200d MA → bias LONG or SHORT
- Counter-trend: allowed but penalized (reduced size, T1 only, no runners)
- Features to model: distance_pct, slope, sessions_on_side, daily_ret, daily_range_vs_avg

**Layer 2 — 4H: Trend & Structure (Rule-Based)**
- HH/HL or LH/LL swing structure
- Confirms or denies daily direction
- Does NOT generate trade geometry (4H fibs = 80-150pt, too wide for day trades)
- Answers: "Which way is the current swing moving?"

**Layer 3 — 1H: Core Forecaster + Fib Geometry (ONE ML Model + Rules)**
- THIS IS WHERE THE FIBS LIVE. THIS IS WHERE TRADES ARE IDENTIFIED.
- ML Model (AutoGluon): predicts price levels + MAE/MFE bands, ~150-170 features
- Fib Geometry (Rule-Based): measured moves on 1H candles, retracements, extensions
- Entry / SL / TP1 / TP2 computation, 20-40+ point trade targets
- Model + fibs on SAME canvas — direct comparison possible

**Layer 4 — 15M: Entry Trigger Confirmation (Rule-Based in v1)**
- Candle close confirmation at fib level
- Volume expansion on trigger bar
- Which fib line was used for the drive up/down
- Cross-asset correlation confirmation at trigger moment
- Volatility state at trigger (GARCH regime, VIX level)
- Stoch RSI check
- Uses 1H model output as context (not a separate ML model in v1)
- GO / NO-GO decision

**CRITICAL DESIGN DECISION:** The 15M trigger involves so many factors (volume, specific fib line, correlations, volatility) that much of this complexity is pushed INTO the 1H training model as features. The model learns which fib lines produce the best setups, which volume conditions matter, which correlation states confirm — rather than hardcoding these as rule-based filters. The 15M layer remains rule-based for the final GO/NO-GO, but the model has already scored the setup quality using trigger-context features.

**THE "TELL" MECHANISM — How the Model Distills Complexity for the Trigger:**

15M is too noisy for ML. 1H is where the model lives. But the model's 6 prediction outputs (price, MAE, MFE at 1h and 4h horizons) ARE the distilled tells — they encode 150+ features worth of context into actionable numbers. The 15M trigger and runner logic consume these tells, not raw features:

- **Trigger quality tell:** `mfe_1h / mae_1h` ratio. High ratio = model sees good risk/reward. This single number encodes all the volume, fib, correlation, and volatility context the model trained on. The 15M trigger checks this ratio + candle close confirmation + volume expansion. Three things, not twenty.

- **Runner tell:** `mfe_4h` vs TP2 distance. If the model's 4h MFE exceeds the distance to TP2, the model is saying "there's enough favorable movement for a runner." After TP1 hits, runner decision checks: model's 4h MFE still shows room + volume still expanding post-TP1. Two things, not twenty.

- **No-trade tell:** `mae_1h` exceeds stop distance, or MFE/MAE ratio below threshold. Model is saying "the heat is too high relative to the reward." Skip.

The chart renders none of this processing. The model runs hourly, writes 6 numbers to the DB. Trigger logic reads them. Chart shows the result.

**Conviction Matrix (Rule-Based)**
- All 4 layers agree → MAXIMUM conviction (full position, runners OK)
- Daily+4H+1H agree, 15M weak → WAIT or reduce size
- Daily+4H agree, 1H identifies → READY — watch for 15M entry
- 4H+1H+15M agree, Daily neutral → MODERATE (reduced size, T1, quick mgmt)
- 4H+1H+15M agree, Daily against → LOW / COUNTER-TREND (T1 only, NO runners)
- Daily against + other disagreement → NO TRADE

---

## 4. TRADE TARGETS: TP1, TP2, AND RUNNERS

- **TP1** — 1.236 fib extension. First profit target. Partial exit.
- **TP2** — 1.618 fib extension. Second target. Larger partial exit.
- **Runner** — Position held past TP2 with pullback checks allowing continuation.

Runner eligibility requires: full conviction (all layers agree, with-trend), volume expansion after TP1, pullback checks pass (micro-pullback with volume drop → spike = continuation).

Counter-trend trades: TP1 only, no runners, reduced size. Always.

---

## 5. ONE ML MODEL IN v1

The 1H Core Forecaster is the ONLY ML model in Warbird v1.

**NOT in v1:** 15M ML model (v2), setup outcome scorer (v3), Monte Carlo (v2), pinball/quantile regression (v2/v3).

---

## 6. CANONICAL DATASET — 1H CORE FORECASTER

**Rows:** One per 1H MES candle (~11,688; grows with time)
**Training window:** 2 full years back to January 1, 2024
**Expected columns:** ~150-170 features + 6 targets + 1 sample_weight
**Builder:** `build-warbird-dataset.ts` (all new, Supabase-native)

### 6 Target Labels

- `target_price_1h` — Price level 1 hour forward
- `target_price_4h` — Price level 4 hours forward
- `target_mae_1h` — Max adverse excursion (drawdown) in 1h
- `target_mae_4h` — Max adverse excursion (drawdown) in 4h
- `target_mfe_1h` — Max favorable excursion (runup) in 1h
- `target_mfe_4h` — Max favorable excursion (runup) in 4h

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
    eval_metric='root_mean_squared_error',
    path=output_dir,
)
predictor.fit(
    train_data=train,
    presets='best_quality',
    num_bag_folds=5,                    # LOCKED
    num_stack_levels=1,                 # Not 2
    dynamic_stacking='auto',
    excluded_model_types=['KNN', 'FASTAI', 'RF'],
    ag_args_ensemble={'fold_fitting_strategy': 'sequential_local'},
)
# Active models: GBM, CAT, XGB, XT, NN_TORCH
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

- **Trigger detection (rule-based):** expansion on trigger candle confirms breakout is real
- **Trigger context (model feature):** volume state at trigger moment enters the model — the model learns which volume conditions produce winning setups vs. fakeouts
- **Core forecaster:** vol_ratio, volume profile, abnormal volume as regime indicator
- **Runner decisions (CRITICAL):** expansion after TP1 → hold for TP2; exhaustion at TP1 → take profit; micro-pullback volume drop then spike → continuation → TP2 likely

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
| 1H | Core forecaster + fib geometry | YES | YES |
| 15M | Entry trigger confirmation | No (v1), rule-based | Uses 1H levels |

The fib engine operates on 1H candles to correlate with the 1H training/model/engine. The 15M provides entry triggers using signals and confirmations from the 1H framework. Start with 1H model; figure out 15M trigger point from there.

---

## 14. INFERENCE OUTPUT — WarbirdSignal v1.0

**Persistence:** Normalized Supabase tables (each layer writes independently).
**Projection:** `/api/warbird/signal` assembles the full WarbirdSignal v1.0 at read time by joining layer outputs. Consumers never query raw tables directly.

Versioned schema consumed by API → Dashboard → (future) Pine Script:

- **Metadata:** version, generatedAt, symbol
- **Daily layer:** bias (BULL/BEAR/NEUTRAL), distance_pct, slope
- **4H structure:** bias_4h, agrees_with_daily
- **1H directional:** bias_1h, price_target_1h/4h, mae/mfe_band_1h/4h, confidence
- **Conviction:** level (MAXIMUM/HIGH/MODERATE/LOW/NO_TRADE), counter_trend, runner_eligible
- **Setup:** direction, fibLevel, entry, SL, TP1, TP2, volume_confirmation
- **Risk:** garch_vol, gpr_level, trump_effect, vix_level, regime, days_into_regime
- **GARCH zones:** 1σ and 2σ boundaries
- **Feedback:** win_rate_last20, streak, avg_r, setup_frequency_7d

---

## 15. WHAT EXISTS AND IS VALID

- Fib geometry on chart (FibLinesPrimitive, confluence scoring, 10 levels)
- MES data pipeline (sidecar, mes_1m/15m/1h/4h/1d flowing)
- Supabase schema (9 migrations, all tables)
- Auth flow, protected routes, admin dashboard structure
- 20 cron routes defined (skeleton implementations for most)
- Raw FRED integration (~90-95 cols, P1 done)
- Chart rendering (LiveMesChart.tsx, gap-free mapping, correct colors/fibs)

---

## 16. WHAT IS STALE / TO BE REPLACED

- `setup-engine.ts` (Touch → Hook → Go) — old BHG pattern matcher, not real methodology
- `detect-setups` cron — running wrong logic, producing wrong data
- `setup_phase` enum (TOUCHED/HOOKED/GO_FIRED) — doesn't map to conviction system
- `warbird_setups` table (old schema) — rebuild in place with new layered schema via migration
- `forecasts` table (old schema) — rebuild in place, replaced by warbird_forecasts_1h
- AGENTS.md references to stack_levels=2, 12 models, Inngest — stale
- `train-warbird.py` — exists with stale AG config, needs sync to this spec
- `predict-warbird.py` — exists but doesn't produce WarbirdSignal contract

---

## 17. WHAT NEEDS TO BE BUILT

### PRIORITY (Fix Now)
0a. **Chart fix:** Resolve `Cannot update oldest data` Lightweight Charts error — remove future whitespace from candlestick series, use hidden companion series for future-space rendering. Chart must be stable before engine work.
0b. **Regime anchors on chart:** Add January 20, 2025 regime anchor visualization to the chart.

### Immediate (Dataset + Engine Foundation)
1. Create `scripts/warbird/` directory with all new engine scripts
2. Migration: rebuild `warbird_setups` and `forecasts` in place → new layered tables (warbird_daily_bias, warbird_structure_4h, warbird_forecasts_1h, warbird_triggers_15m, warbird_conviction, warbird_setups, warbird_setup_events, warbird_risk)
3. 1H Fib Engine (`scripts/warbird/fib-engine.ts`) — measured moves, retracements, extensions, confluence on 1H
4. Dataset builder (`scripts/warbird/build-warbird-dataset.ts`) — all feature groups from Supabase data
5. Daily layer (`scripts/warbird/daily-layer.ts`) — 200d MA computation, bias, continuous features
6. 4H structure layer (`scripts/warbird/structure-4h.ts`) — swing detection, trend confirmation
7. API projection route (`/api/warbird/signal`) — assembles WarbirdSignal v1.0 from normalized tables

### Training Pipeline
8. AutoGluon training (`scripts/warbird/train-warbird.py`) — canonical config, 5 folds, stack=1, one model
9. GARCH engine (`scripts/warbird/garch-engine.py`) — GJR-GARCH(1,1), regime-anchored, dual output

### Inference + Integration
10. Inference pipeline (`scripts/warbird/predict-warbird.py`) — hourly WarbirdSignal v1.0 production
11. Conviction matrix (`scripts/warbird/conviction-matrix.ts`) — rule-based scoring combining all 4 layers
12. 15M trigger logic (`scripts/warbird/trigger-15m.ts`) — rule-based entry confirmation with 1H context
13. Dashboard cards — WarbirdPredictionCard, chart primitive updates

### Data Pipelines (Pending)
14. P2: Derived FRED (velocity, percentile, momentum)
15. P3: Cross-asset futures (aligned 1H, ratios, correlations)
16. P4: Calendar events (FOMC/CPI/NFP flags, proximity)
17. P5: News signals (layer counts, sentiment)
18. Surprise z-scores (HIGHEST ROI, requires backfill)
19. Trade feedback features (rolling win rates, R-multiples)
20. Geopolitical risk ingestion (GPR, TrumpEffect)

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
ONE ML model (1H), rule-based layers (Daily/4H/15M/conviction), GARCH, full feature pipeline, regime-anchored features, WarbirdSignal v1.0.

### v2 (After v1 Stable)
15M ML model, Monte Carlo on validated GARCH, pinball loss, fold upgrade (5→8 A/B), Pine Script integration.

### v3 (After Setup Count Grows)
Setup outcome scorer P(T1)/P(T2)/P(Runner|T1), survival model, FinBERT sentiment, hyperparameter optimization.

---

*Designed and architected by Kirk Musick, MS, MBA*
