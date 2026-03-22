# Warbird v1 Pipeline Design

> ARCHIVED REFERENCE ONLY. Do not update this file.  
> Active architecture/update doc: `docs/plans/2026-03-20-ag-teaches-pine-architecture.md`

**Date:** 2026-03-16
**Author:** Kirk Musick
**Status:** Approved — ready for implementation planning

---

## 1. Summary

This document defines the complete Warbird v1 data-and-model pipeline. It supersedes all prior phase-plan documents. The architecture is locked to 1H fibs only (no 15M trigger layer), TP1/TP2 only (no runners), and 5 fib-relative binary targets for AutoGluon training.

---

## 2. Architecture Overview

```
MES 1M (source)
MES 1H (source)         →  cross_asset_1h (non-MES Databento symbols)
MES 1D (source)
      ↓                     ↓
MES 15M (derived)       FRED 42 series → 10 econ tables
MES 4H (derived)            ↓
      ↓                 GPR (Caldara-Iacoviello) → geopolitical_risk_1d
Daily Bias Layer            ↓
4H Structure Layer      TE Calendar scraper → econ_calendar
1H Fib Geometry             ↓
      ↓                 Google News RSS → econ_news_1d → news_signals
Dataset Builder (fib-setup rows only)
      ↓
AutoGluon (5 predictors, one per target)
      ↓
warbird_forecasts_1h (written via predict-warbird.py)
      ↓
Vercel Cron (5M) → detect-setups → warbird_conviction → warbird_setups
```

**Non-negotiable rules:**
- 1H is the ONLY fib anchor. 15M fib layer is permanently removed.
- No runner logic. No `runner_eligible`, no `runner_headroom`.
- No time-based setup expiry (`expires_at` driven by outcome, not clock).
- No ORM. Supabase direct only.
- No mock data. Real or nothing.

---

## 3. Data Backfill

### 3.1 MES Bars — `scripts/backfill.py` (existing)

Already exists. Run for full 2-year window:

```
python scripts/backfill.py --start 2024-01-01 --end 2026-03-16
```

Writes to: `mes_1m`, `mes_1h`, `mes_1d` (direct from Databento)
Derived: `mes_15m` from `mes_1m`, `mes_4h` from `mes_1h`

Verify row counts before proceeding to training.

### 3.2 Cross-Asset Bars — `scripts/backfill-cross-asset.py` (NEW)

Backfills all active non-MES Databento symbols (assigned role `correlation`) into `cross_asset_1h`.

Active correlation symbols (from `seed.sql`):
- NQ, ZN, ZF, ZB, SR3, 6E, 6J, DX, VX, ES, YM, RTY, SOX, CL, GC

Uses Databento API key (`DATABENTO_API_KEY`). Same date range: 2024-01-01 → 2026-03-16.

Writes to: `cross_asset_1h(ts, symbol_code, open, high, low, close, volume)`

Vercel Cron continuation: an existing or new cron writes ongoing `cross_asset_1h` bars on a 1H cadence. Confirm this exists before relying on it.

### 3.3 FRED Series — `scripts/backfill-fred.py` (NEW)

Backfills all 42 FRED series into their assigned econ domain tables using the FRED API (`FRED_API_KEY`).

**10 econ domain tables** (all share schema `(ts, series_id, value)`):
`fed_policy_1d`, `inflation_1d`, `employment_1d`, `growth_1d`, `credit_spreads_1d`, `financial_conditions_1d`, `consumer_sentiment_1d`, `recession_indicators_1d`, `volatility_indicators_1d`, `macro_business_cycle_1d`

**31 existing series** (already in `series_catalog`): confirmed present, see `seed.sql`.

**11 new FRED series to add** (require `seed.sql` update first — see §4):
| Series ID | Table |
|---|---|
| VXNCLS | volatility_indicators_1d |
| RVXCLS | volatility_indicators_1d |
| BAMLC0A0CM | credit_spreads_1d |
| BAMLHYH0A0HYM2EY | credit_spreads_1d |
| BAA10Y | credit_spreads_1d |
| NFCI | financial_conditions_1d |
| STLFSI4 | financial_conditions_1d |
| ANFCI | financial_conditions_1d |
| UMCSENT | consumer_sentiment_1d |
| RECPROUSM156N | recession_indicators_1d |
| SAHMCURRENT | recession_indicators_1d |
| EMVMACROBUS | macro_business_cycle_1d |

Script uses `fredapi` or direct FRED HTTP API. No ORM.

### 3.4 GPR — `scripts/backfill-gpr.py` (NEW)

Source: Caldara-Iacoviello GPR historical XLS (download from their website).
Writes to: `geopolitical_risk_1d(ts, series_id, value)` — two rows per date:
- `series_id = 'gpr_acts'` — actual conflict signal
- `series_id = 'gpr_threats'` — rhetoric/threat signal

Both series are already assigned in `series_catalog`. Script reads XLS, maps to schema, upserts.

---

## 4. Seed.sql — Add 11 New FRED Series

**File:** `supabase/seed.sql`

Add 12 rows to `series_catalog` (one insert block), each with:
- `series_id` (FRED series ID)
- `source = 'FRED'`
- `role = 'feature'`
- `active = true`
- `domain_table` mapping per table above

Do NOT touch existing rows. Do NOT alter schema.

Also add `EMVMACROBUS` to series_catalog.

---

## 5. Dataset Builder — `scripts/warbird/build-warbird-dataset.ts`

### 5.1 Row Selection

**Current (wrong):** iterates every 1H candle.
**Fix:** row = a moment when a fib setup fires on the 1H. Selection logic:
1. Run `buildFibGeometry()` over each 1H candle window (rolling, minimum 55 bars of lookback).
2. Emit a row only when `geometry` is non-null AND a valid fib level is touched (entry price within `fib_level` tolerance).
3. Each row represents one historical setup opportunity.

### 5.2 Target Labels (5 binary targets)

Replace all 6 old raw price targets with these 5:

| Column | Type | Definition |
|---|---|---|
| `reached_tp1` | binary (0/1) | Price reached TP1 before stop loss |
| `reached_tp2` | binary (0/1) | Price reached TP2 before stop loss |
| `setup_stopped` | binary (0/1) | Price hit stop loss before TP1 |
| `max_favorable_excursion` | continuous | Max favorable move (points) from entry before stop or TP2 |
| `max_adverse_excursion` | continuous | Max adverse move (points) from entry before stop or exit |

Forward scan window: walk forward 1H bars from setup bar until TP1, TP2, or stop is hit.

### 5.3 Feature Groups

All features are pre-computed values written as columns. No feature engineering inside AutoGluon.

**Fib context (1H):**
- `fib_level` — which fib level triggered (0.382, 0.500, 0.618, 0.786)
- `fib_quality` — fib geometry quality score
- `fib_confluence_score` — multi-lookback confluence (8, 13, 21, 34, 55 bar windows)
- `measured_move_present` — binary, whether a measured move pattern exists
- `measured_move_quality` — quality of measured move if present

**Price structure:**
- `atr_1h` — ATR(14) on 1H
- `range_compression` — recent bar range vs ATR ratio
- `bias_1h`, `bias_4h`, `daily_bias` — BULLISH/BEARISH/NEUTRAL (from conviction layers)
- `conviction_level` — MAXIMUM/HIGH/MODERATE/LOW from conviction matrix

**Cross-asset correlations (pre-computed rolling):**
For each of 15 correlation symbols: `corr_{symbol}_20`, `corr_{symbol}_60`
(20-bar and 60-bar rolling Pearson correlation with MES 1H close)
These MUST be pre-computed in the dataset builder. AutoGluon does NOT compute them.

**GARCH volatility:**
- `garch_vol` — current conditional volatility from GJR-GARCH(1,1) (`scripts/warbird/garch-engine.py`)
- `garch_regime` — low/med/high vol regime label

**FRED econ features (most recent available value for each series at row ts):**
- One column per active FRED series, named by series_id (42 total)
- Left-join on `ts` with forward-fill (FRED data is weekly/monthly; use last known value)

**News/sentiment:**
- `news_sentiment_{segment}` — average sentiment score per Google News segment (6 segments)
- `econ_surprise` — actual vs forecast from `econ_calendar` (surprise direction: +1/0/-1)
- `gpr_acts`, `gpr_threats` — from `geopolitical_risk_1d`
- `trump_effect` — from `trump_effect_1d`

**Remove from builder:**
- `runner_eligible_recent_20` and any other runner-related columns

### 5.4 Output

CSV written to `data/warbird-dataset.csv`. Minimum usable rows: ~500 fib-setup occurrences over 2 years of 1H data. If insufficient, extend lookback or lower fib quality threshold.

---

## 6. AutoGluon — `scripts/warbird/train-warbird.py`

### 6.1 Target Config (CRITICAL FIXES)

Replace the 6 old targets with 5 correct targets and correct AutoGluon settings per type:

| Target | Problem Type | Eval Metric |
|---|---|---|
| `reached_tp1` | `binary` | `roc_auc` |
| `reached_tp2` | `binary` | `roc_auc` |
| `setup_stopped` | `binary` | `roc_auc` |
| `max_favorable_excursion` | `regression` | `root_mean_squared_error` |
| `max_adverse_excursion` | `regression` | `root_mean_squared_error` |

### 6.2 Excluded Models (CRITICAL FIX)

**Remove RF from excluded list.** RF is one of AutoGluon's strongest tabular models.

```python
excluded_model_types=["KNN", "FASTAI"]  # RF removed
```

### 6.3 Other Settings (Confirmed Correct)

- 80/20 temporal split (chronological, not random)
- `presets="best_quality"`
- `num_bag_folds=5`
- `num_stack_levels=1`
- `dynamic_stacking="auto"`
- `ag_args_ensemble={"fold_fitting_strategy": "sequential_local"}` — correct for M4 Pro
- Output: `models/warbird_v1/` with `manifest.json`

---

## 7. Cron: detect-setups — `app/api/cron/detect-setups/route.ts`

### 7.1 Remove 15M Trigger Layer

**Remove entirely:**
- `evaluateTrigger15m()` import and call
- `mes_15m` fetch from Supabase
- `warbird_triggers_15m` upsert
- All references to `trigger_id`, `trigger.ts`, `trigger.decision`, `trigger.fib_*`, `trigger.entry_price`, `trigger.stop_loss`, `trigger.tp1`, `trigger.tp2`, `trigger.volume_*`, `trigger.trigger_quality_ratio`, `trigger.runner_headroom`

### 7.2 Remove Runner Fields

Remove from all payloads:
- `runner_eligible`
- `runner_headroom`
- `runnerEligible` from conviction spread

### 7.3 Remove Time-Based Expiry

Remove: `expires_at: new Date(new Date(trigger.ts).getTime() + 48 * 60 * 60 * 1000).toISOString()`

Setup lifecycle is managed by outcome (TP1 hit, TP2 hit, stopped), not clock.

### 7.4 Revised Flow (after fixes)

```
1. Fetch: mes_1d (240), mes_4h (120), mes_1h (160)
2. Fetch: warbird_forecasts_1h (latest)
3. Build daily bias layer → upsert warbird_daily_bias
4. Build 4H structure → upsert warbird_structure_4h
5. Build 1H fib geometry (from forecast.bias_1h)
6. Evaluate conviction (daily + 4H + 1H agreement)
7. Upsert warbird_conviction
8. If conviction.level != NO_TRADE → create warbird_setups + warbird_setup_events
```

---

## 8. Conviction Matrix — `scripts/warbird/conviction-matrix.ts`

Remove `runnerEligible` from:
- `ConvictionResult` interface
- All return objects in `evaluateConviction()`

Conviction levels and logic are otherwise correct.

---

## 9. Trading Economics Calendar Scraper

**Replaces:** `app/api/cron/econ-calendar/route.ts` (current FRED-only implementation)
**Env var needed:** `TRADINGECONOMICS_API_KEY` (add to `.env.local` and Vercel)

### What to collect:

- US economic releases (all) with: `date`, `event`, `importance` (1-3), `actual`, `forecast`, `previous`, `surprise` (actual - forecast)
- Global central bank events affecting USD: ECB, BOJ, BOE, PBOC, SNB, RBA rate decisions
- Importance filter: only importance >= 2 for non-US events

### Schema target: `econ_calendar`

```sql
-- existing columns confirmed:
ts, event_name, importance, actual, forecast, previous, surprise, source
```

### Approach: TE scraper (not API, API key TBD)

Scrape Trading Economics calendar pages for US + major CB events. Parse HTML for importance stars, actual/forecast/previous values. Run on Vercel Cron daily at 6am Central.

---

## 10. Google News RSS Scraper

**New cron:** Vercel Cron, daily at 7am Central
**Writes to:** `econ_news_1d` → sentiment aggregation → `news_signals`

### 6 topic segments (from `google_news_keywords.md` memory):

| Segment | Keywords (summary) |
|---|---|
| `fed_policy` | Fed rate decisions, Powell speeches, FOMC |
| `inflation_economy` | CPI, PCE, payrolls, GDP, recession |
| `geopolitical_war` | Ukraine, Middle East, Taiwan, tariffs |
| `policy_trump` | Trump tariffs, Treasury, DOGE |
| `market_structure` | S&P 500 crash, VIX, credit, bank failure |
| `earnings_tech` | NVIDIA, Apple, Meta earnings, semiconductors |

### Per-article schema (`econ_news_1d`):

```
ts, title, url, source, segment, sentiment_score, raw_text
```

### Aggregation → `news_signals`:

Daily roll-up: average `sentiment_score` per segment per day → `news_sentiment_{segment}` feature columns used in dataset builder.

---

## 11. Files Changed Summary

| File | Action | What Changes |
|---|---|---|
| `supabase/seed.sql` | Update | Add 12 FRED series rows to `series_catalog` |
| `scripts/backfill.py` | Use as-is | Run for 2024-01-01 → 2026-03-16 |
| `scripts/backfill-cross-asset.py` | Create | Databento non-MES backfill → cross_asset_1h |
| `scripts/backfill-fred.py` | Create | 42 FRED series → 10 econ tables |
| `scripts/backfill-gpr.py` | Create | Caldara-Iacoviello XLS → geopolitical_risk_1d |
| `scripts/warbird/build-warbird-dataset.ts` | Update | Fib-setup row selection, 5 fib-relative targets, rolling correlations, GARCH, news sentiment |
| `scripts/warbird/train-warbird.py` | Update | 5 targets, correct problem_type+eval_metric per target, RF back in excluded_model_types |
| `scripts/warbird/conviction-matrix.ts` | Update | Remove runnerEligible |
| `app/api/cron/detect-setups/route.ts` | Update | Remove 15M trigger layer, remove runner fields, remove time-based expiry |
| `app/api/cron/econ-calendar/route.ts` | Replace | TE scraper with importance + actual/forecast/surprise |
| `app/api/cron/google-news/route.ts` | Create | RSS scraper, 6 segments → econ_news_1d + news_signals |
| `WARBIRD_CANONICAL.md` | Update | Remove 15M refs, remove runner refs, update target labels |
| `AGENTS.md` | Update | Remove trigger-15m.ts, update cron cadence to 5M |

---

## 12. Execution Order

This is the hard dependency chain. Each step must complete and be verified before the next.

```
1. seed.sql update (new FRED series in catalog)
2. Run backfill.py (MES bars — all timeframes)
3. Run backfill-cross-asset.py (correlation symbols)
4. Run backfill-fred.py (42 FRED series)
5. Run backfill-gpr.py (GPR historical)
6. Build econ calendar data (TE scraper or manual seed)
7. Build news signals (Google News scraper or manual seed)
8. Fix conviction-matrix.ts (remove runnerEligible)
9. Fix detect-setups/route.ts (remove 15M, remove runners)
10. Update build-warbird-dataset.ts (fib rows, correct targets)
11. Run dataset builder → verify warbird-dataset.csv row count and label distribution
12. Fix train-warbird.py (targets, metrics, excluded models)
13. Train (python scripts/warbird/train-warbird.py --dataset data/warbird-dataset.csv)
14. Deploy predict endpoint, verify warbird_forecasts_1h writes
15. Verify detect-setups cron end-to-end
16. Update WARBIRD_CANONICAL.md and AGENTS.md
```

---

## 13. Out of Scope (This Phase)

- Live tick streaming upgrades
- Multi-symbol expansion beyond MES
- Automated retraining pipeline
- UI changes beyond what detect-setups enables
- Any new Supabase tables or schema changes
