# TradingView-First Architecture: The Gate Model

> ARCHIVED REFERENCE ONLY. Do not update this file.  
> Active architecture/update doc: `docs/plans/2026-03-20-ag-teaches-pine-architecture.md`

**Date:** 2026-03-20
**Status:** Approved
**Supersedes:** Custom Next.js dashboard approach

---

## Executive Summary

TradingView becomes the entire frontend. AutoGluon becomes the brain. A local Python server connects them via webhooks. The custom Next.js dashboard, Supabase frontend hosting, and Realtime chart infrastructure are eliminated.

The model's job is NOT price prediction. It is an **entry gate** — it tells you whether RIGHT NOW, at THIS fib level, with THESE market conditions, the entry will be CLEAN (20+ points, 10-15 point stop) or DIRTY (stopped out before target).

---

## Architecture Overview

```
TradingView (UI + Data Source)
  │
  ├─ Rabid Raccoon v2 (Pine Script v6)
  │   ├─ Fib engine (multi-period confluence)
  │   ├─ Intermarket data feeds
  │   ├─ Confidence gauge (arc needle)
  │   ├─ Trade card (gates, win rate, entry/SL/TP)
  │   ├─ Gate oscillator (bottom panel)
  │   └─ Webhook output (JSON per bar + events)
  │
  ├─ Hidden indicators (loaded but not visible)
  │   ├─ Multiple EMA/SMA variants
  │   ├─ RSI variants (7, 14, 21)
  │   ├─ MACD / MACDRe
  │   ├─ TTM Squeeze (default, tight, loose)
  │   ├─ Volume Orderbook (Zeiierman)
  │   ├─ LuxAlgo Market Sentiment Technicals
  │   ├─ LuxAlgo Swing Highs/Lows & Candle Patterns
  │   ├─ Market Structure Break Targets (UAlgo)
  │   ├─ Order Blocks
  │   ├─ Ross Hook Pattern (Expo)
  │   ├─ Super Pivots
  │   ├─ Volume Gaps & Imbalances (Zeiierman)
  │   └─ Heikin Ashi Candles - Actual Close
  │
  └─ Multi-panel layout (model-selected)
      ├─ Main: MES 15m with RR v2
      └─ Side panels: top correlated assets per model
          (e.g., NQ 1H, CL 15m, MES 10m — model decides)

         │ Webhook (HTTPS via Cloudflare Tunnel)
         ▼

Local Python Server (FastAPI)
  │
  ├─ Receives indicator JSON from TradingView
  ├─ Enriches with macro data (from local DB)
  │   ├─ FRED economic data (10 categories)
  │   ├─ News/sentiment signals
  │   ├─ GPR index
  │   ├─ Trump effect / policy
  │   ├─ Economic calendar
  │   ├─ Timing features (computed)
  │   └─ Databento statistics (OI, settlement, volume)
  │
  ├─ Loads frozen AutoGluon model
  ├─ Runs gate check (N of M gates passed)
  │
  └─ Returns JSON response
      {
        "direction": "long",
        "action": "ENTER" | "WAIT" | "NO_TRADE",
        "confidence": 0.82,
        "gates_passed": 47,
        "gates_total": 50,
        "tp1_prob": 0.74,
        "tp2_prob": 0.51,
        "stop_prob": 0.12,
        "historical_win_rate": 0.74,
        "similar_setups": 847,
        "avg_winner_pts": 32,
        "entry_price": 6665.00,
        "stop_price": 6653.00,
        "tp1_price": 6685.00,
        "tp2_price": 6705.00,
        "top_factors": ["volume_at_level", "nq_confirming", "post_sweep"],
        "failed_gates": ["ny_open_4min_away"]
      }

         │ Response
         ▼

RR v2 reads response → updates gauge, card, oscillator
  └─ Trader sees: GO / WAIT / NO — acts accordingly

         │ After trade completes
         ▼

Supabase (Lean)
  ├─ Logs: prediction vs actual outcome
  ├─ Stores: macro enrichment data (FRED, news, econ)
  └─ Feeds: weekly retrain data
```

---

## The Gate Model — What AutoGluon Learns

### Training Target

NOT price direction. NOT price level. **Entry quality classification.**

| Label | Definition | What It Means |
|---|---|---|
| **CLEAN** | Price moved 20+ pts in direction, never came within 10 pts of entry against | Perfect entry — tight stop, clean run to target |
| **SURVIVED** | Price moved 20+ pts but first dipped 8-12 pts against entry | Sweaty but worked — stop held barely |
| **STOPPED** | Price went 15+ pts against (hit stop), then moved 20+ in original direction | Bad timing — right idea, wrong moment |
| **REVERSAL** | Price went 15+ pts against and kept going — never reached target | Correct stop — setup was wrong |

**Primary objective:** Maximize CLEAN rate. Eliminate STOPPED.
**Secondary objective:** Distinguish STOPPED from REVERSAL (should I re-enter after sweep?).

### Target Sizing

| Parameter | Value |
|---|---|
| Minimum target (TP1) | 20 points |
| Sweet spot target (TP2) | 40-60+ points |
| Stop loss goal | 10-15 points |
| Minimum risk/reward | 1.3:1 |
| Sweet spot risk/reward | 4:1+ |

### Feature Universe

AutoGluon receives ALL features. It decides which matter. No pre-filtering. No human bias on what "should" work.

#### A. TradingView Features (via webhook JSON)

**Fib Engine (from Rabid Raccoon):**
- `fib_anchor_high`, `fib_anchor_low` — current fib range boundaries
- `fib_range` — range width (tells expected stop sweep depth)
- `fib_direction` — bullish or bearish
- `fib_confluence_score` — how many multi-period fibs agree (0-45)
- `fib_active_period` — which lookback won (8, 13, 21, 34, 55)
- `price_to_pivot` — distance from 0.5 level
- `price_to_zone_lo` — distance from 0.618
- `price_to_zone_hi` — distance from 0.786
- `price_to_target1` — distance from 1.236
- `price_to_target2` — distance from 1.618
- `price_to_dn_magnet1` — distance from 0.382
- `price_to_dn_magnet2` — distance from 0.236
- `bars_since_struct_break` — freshness of current fib anchor
- `price_in_zone` — boolean: is price inside the decision zone?

**Intermarket (from Rabid Raccoon request.security):**
- `nq_trend` — NQ above/below EMA, slope direction
- `bank_trend` — BANK index trend
- `vix_level` — absolute VIX value
- `vix_trend` — VIX direction
- `dxy_trend` — USD index direction
- `us10y_trend` — 10Y yield direction
- `intermarket_score_on` — weighted bullish score (0-8)
- `intermarket_score_off` — weighted bearish score (0-8)
- `regime` — current intermarket regime (1/0/-1)
- `news_posture` — news proxy state (1/0/-1)
- `hawkish_proxy_score` — news shock magnitude bearish
- `dovish_proxy_score` — news shock magnitude bullish

**OHLCV (standard):**
- `open`, `high`, `low`, `close`, `volume`
- `bar_range` — high minus low (volatility per bar)
- `body_pct` — body vs total range (conviction)
- `upper_wick_pct`, `lower_wick_pct` — wick ratios

**Moving Averages (load multiple, model picks best):**
- `ema_9`, `ema_12`, `ema_17`, `ema_20`, `ema_21`
- `sma_20`, `sma_50`, `sma_200`
- `vwap`
- `price_vs_ema_X` — distance from each MA (normalized)

**Oscillators:**
- `rsi_7`, `rsi_14`, `rsi_21`
- `macd_line`, `macd_signal`, `macd_histogram`
- `squeeze_state` — off/building/firing
- `squeeze_momentum` — directional strength

**Volume/Orderbook:**
- `volume_ratio_20` — current volume vs 20-bar average
- `orderbook_bid_volume` — from Zeiierman Volume Orderbook
- `orderbook_ask_volume`
- `orderbook_delta_pct` — buy/sell imbalance
- `volume_poc` — point of control price level

**Structure (from LuxAlgo / UAlgo / Super Pivots):**
- `swing_high_distance` — distance to nearest swing high
- `swing_low_distance` — distance to nearest swing low
- `structure_label` — HH/HL/LH/LL state
- `msb_detected` — market structure break boolean
- `order_block_distance` — nearest order block
- `daily_pivot`, `daily_r1`, `daily_r2`, `daily_s1`, `daily_s2`
- `monthly_s1`, `monthly_s2`, `monthly_r1`

**LuxAlgo Market Sentiment:**
- `sentiment_gauge` — Strong Bearish to Strong Bullish (numeric)
- `sentiment_rsi`, `sentiment_stoch`, `sentiment_cci`
- `sentiment_bbp`, `sentiment_macd`
- `sentiment_vwap_state`, `sentiment_bb_trend`
- `sentiment_reg_state`, `sentiment_ms`
- `sentiment_oscillator` — composite oscillator value
- `sentiment_divergence` — divergence detected

**Pattern Detection:**
- `ross_hook` — Ross Hook pattern detected
- `heikin_ashi_trend` — HA candle color/direction
- `candle_pattern` — LuxAlgo candle pattern name (hammer, shooting star, etc.)

**Higher Timeframe Context (via request.security in Pine):**
- `htf_1h_trend` — 1H trend direction
- `htf_1h_sr_distance` — distance to nearest 1H S/R
- `htf_4h_trend` — 4H trend direction
- `htf_daily_sr_distance` — distance to nearest daily S/R
- `htf_weekly_sr_distance` — distance to nearest weekly S/R
- `htf_sr_touch_count` — how many times level tested (1H lookback)

#### B. Macro Enrichment Features (from local DB, added by Python server)

**FRED Economic Data (10 categories, already ingested):**
- `fed_funds_rate` — from econ_rates_1d
- `treasury_2y`, `treasury_10y`, `treasury_30y` — from econ_yields_1d
- `yield_curve_2s10s` — computed spread
- `vix_daily` — from econ_vol_1d
- `move_index` — bond volatility from econ_vol_1d
- `cpi_yoy`, `pce_yoy` — from econ_inflation_1d
- `breakeven_5y`, `breakeven_10y` — inflation expectations
- `dxy_daily` — from econ_fx_1d
- `usdjpy`, `eurusd` — key FX pairs
- `nfp_last`, `initial_claims` — from econ_labor_1d
- `ism_pmi`, `chicago_pmi` — from econ_activity_1d
- `m2_yoy` — from econ_money_1d
- `gold_price`, `oil_price` — from econ_commodities_1d
- `sp500_daily`, `nasdaq_daily` — from econ_indexes_1d

**News & Sentiment (already ingested):**
- `news_sentiment_score` — from news_signals
- `news_topic_segment` — fed_policy / inflation / geopolitical / etc.
- `macro_surprise_index` — from macro_reports_1d

**Geopolitical & Policy:**
- `gpr_index` — from geopolitical_risk_1d
- `trump_policy_score` — from trump_effect_1d

**Economic Calendar:**
- `hours_to_next_event` — from econ_calendar
- `next_event_impact` — high/medium/low
- `next_event_type` — FOMC/CPI/NFP/etc.
- `is_fomc_week` — boolean

**Databento Statistics (from existing/planned ingestion):**
- `mes_settlement_price` — from mes_statistics
- `mes_open_interest` — positioning signal
- `mes_cleared_volume` — true volume
- `mes_session_high`, `mes_session_low` — official range
- `oi_change_1d` — OI direction (building/liquidating)

#### C. Computed Timing Features (added by Python server)

- `minutes_since_ny_open` — 0 at 9:30 ET
- `minutes_to_ny_close` — countdown to 16:00 ET
- `session` — pre-market / regular / after-hours / overnight
- `minutes_since_london_close` — 11:30 ET
- `day_of_week` — 0=Mon through 4=Fri
- `is_first_30min` — stop hunt danger zone
- `is_last_30min` — mean reversion zone
- `is_lunch` — 11:30-13:00 ET low volume
- `bars_since_previous_trade` — avoid overtrading

#### D. Estimated Feature Count

| Category | Features |
|---|---|
| Fib engine | ~15 |
| Intermarket | ~12 |
| OHLCV + candle metrics | ~8 |
| Moving averages | ~15 |
| Oscillators | ~8 |
| Volume/orderbook | ~5 |
| Structure | ~12 |
| LuxAlgo sentiment | ~12 |
| Pattern detection | ~3 |
| Higher timeframe | ~6 |
| FRED economic | ~20 |
| News/sentiment | ~3 |
| Geopolitical/policy | ~2 |
| Economic calendar | ~4 |
| Databento statistics | ~6 |
| Timing | ~9 |
| **Total** | **~140** |

AutoGluon receives all ~140. It identifies the 20-100 that matter. The rest are noise.

---

## Rabid Raccoon v2 — Pine Script v6 Indicator

### What Changes From v1

| Aspect | v1 (Current) | v2 (New) |
|---|---|---|
| Signal logic | Hand-coded accept/reject/break rules | Removed — model replaces all signal logic |
| Visual output | Labels everywhere (GO, .618 LONG, .236 TP) | Clean lines only + gauge + card + oscillator |
| Webhook | None | JSON output on every bar close + events |
| Confidence display | None | Arc gauge (like LuxAlgo sentiment) |
| Trade info | None | Trade card (top corner) |
| Entry countdown | None | Gate oscillator (bottom panel) |
| Intermarket data | Feeds + hand-coded regime logic | Feeds stay, regime logic removed (model decides) |
| News proxy | Hand-coded shock thresholds | Data passed to model, model decides thresholds |

### What Stays

- Fib engine (multi-period confluence scoring) — solid math, keep
- Intermarket data feeds (request.security for NQ, BANK, VIX, DXY, US10Y) — keep as data source
- Clean line visuals (yellow decision zone, white pivot, green targets, red stops)
- All configurable ratios (0.236, 0.382, 0.5, 0.618, 0.786, 1.236, 1.618)

### Visual Layout

```
┌──────────────────────────────────────────────────────────┐
│ ┌─────────────────────┐                                  │
│ │ ▲ LONG FORMING      │           Sentiment Panel        │
│ │ Entry: 6,665        │     ┌─────────────────────────┐  │
│ │ SL: 6,653 (12 pts)  │     │ ▌▌▌▐▐▐  Overbought     │  │
│ │ TP1: 6,685 (20 pts) │     │ R S S C B  M V B S R M  │  │
│ │ TP2: 6,705 (40 pts) │     │ S K T R P  A W B T E S  │  │
│ │ Gates: 47/50 ✅      │     │ I   O I P  C A   R G    │  │
│ │ Win Rate: 74%        │     │         Neutral          │  │
│ │ Avg Win: +32 pts     │     │         Oversold         │  │
│ │ Status: READY        │     └─────────────────────────┘  │
│ └─────────────────────┘                                  │
│                                                          │
│  ════════════ green target line ══════════════════════    │
│                                                          │
│  ════════════ green target line ══════════════════════    │
│                                                          │
│       candlesticks / price action                        │
│                                                          │
│  ════════════ yellow decision zone ══════════════════    │
│  ════════════ yellow decision zone ══════════════════    │
│  ════════════ white pivot ═══════════════════════════    │
│                                                          │
│  ════════════ red stop level ════════════════════════    │
│                                                          │
│ ┌──────────────────────────────────────────────────────┐ │
│ │  Confidence Gauge          Gate Oscillator            │ │
│ │     Strong    Strong       ████████░░ 76%             │ │
│ │    Bearish ←──→ Bullish    ▁▂▃▅▆▇█▇▆ (rising)       │ │
│ │         ╲  │  ╱                                      │ │
│ │          ╲ │ ╱                                       │ │
│ │           ╲│╱                                        │ │
│ └──────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────┘
```

### Webhook JSON Output (fires every 15m bar close)

```json
{
  "timestamp": "2026-03-20T14:30:00Z",
  "symbol": "MES1!",
  "timeframe": "15",
  "ohlcv": {
    "open": 6670.25, "high": 6682.50,
    "low": 6668.00, "close": 6680.75, "volume": 48230
  },
  "fib": {
    "anchor_high": 6740.25, "anchor_low": 6605.00,
    "range": 135.25, "direction": "bull",
    "confluence_score": 32, "active_period": 21,
    "pivot": 6672.63, "zone_lo": 6688.54, "zone_hi": 6711.24,
    "target1": 6772.19, "target2": 6823.82,
    "dn_magnet1": 6656.69, "dn_magnet2": 6637.29,
    "bars_since_break": 14, "price_in_zone": false
  },
  "intermarket": {
    "nq": {"price": 24850, "ema20": 24720, "trend": "bull"},
    "bank": {"price": 142.30, "ema20": 141.80, "trend": "bull"},
    "vix": {"price": 19.20, "ema20": 20.10, "trend": "bear"},
    "dxy": {"price": 103.40, "ema20": 103.80, "trend": "bear"},
    "us10y": {"price": 4.28, "ema20": 4.32, "trend": "bear"},
    "score_on": 7, "score_off": 1, "regime": 1,
    "news_posture": 0, "hawkish_score": 0, "dovish_score": 1
  },
  "indicators": {
    "ema_9": 6678.50, "ema_12": 6675.20, "ema_21": 6671.80,
    "sma_50": 6690.00, "sma_200": 6620.00,
    "rsi_7": 62.3, "rsi_14": 55.8, "rsi_21": 51.2,
    "macd_line": 2.4, "macd_signal": 1.8, "macd_hist": 0.6,
    "squeeze": "firing", "squeeze_momentum": 3.2,
    "volume_ratio_20": 1.4
  },
  "structure": {
    "swing_high_dist": 42.50, "swing_low_dist": -18.25,
    "label": "HL", "msb": false,
    "daily_pivot": 6694.00, "daily_s1": 6665.00,
    "monthly_s2": 6635.50
  },
  "sentiment": {
    "gauge": 0.62, "oscillator": 4.8, "divergence": false
  }
}
```

---

## Training Pipeline

### Phase 1: Historical Data Collection

1. **TradingView CSV Export** — 2M bars of MES 15m with ALL indicators loaded
   - Column headers = feature names
   - Includes all hidden indicator values

2. **Macro Enrichment** — Join CSV timestamps with local DB data:
   - 10 FRED category tables (econ_rates_1d through econ_indexes_1d)
   - news_signals, macro_reports_1d
   - geopolitical_risk_1d, trump_effect_1d
   - econ_calendar
   - mes_statistics (OI, settlement, volume)

3. **Label Generation** — For every bar where a fib setup existed:
   - Look forward N bars
   - Did price hit TP1 (20+ pts) before stop (15 pts against)?
   - Classify: CLEAN / SURVIVED / STOPPED / REVERSAL
   - Also record: bars_to_tp1, bars_to_tp2, max_adverse_excursion

### Phase 2: AutoGluon Training

```python
from autogluon.tabular import TabularPredictor

# Load feature matrix (TV CSV + macro enrichment + labels)
train_data = pd.read_csv("warbird_training_set.csv")

# Train with best_quality preset
predictor = TabularPredictor(
    label="entry_quality",           # CLEAN/SURVIVED/STOPPED/REVERSAL
    problem_type="multiclass",
    eval_metric="log_loss",
    path="~/models/warbird-gate/"
).fit(
    train_data,
    presets="best_quality",
    time_limit=14400,                # 4 hours max
    num_bag_folds=5,
    num_stack_levels=1
)

# Feature importance — THE GOLD
importance = predictor.feature_importance(test_data)
print(importance.head(50))           # Top 50 gate features

# Per-class analysis
# What separates CLEAN from STOPPED?
```

### Phase 3: Model Deployment

- Frozen model saved to `~/models/warbird-gate/YYYY-MM-DD/`
- Local Python server loads model on startup (~2-5s)
- Subsequent predictions: <1s each
- Model doesn't change until next weekly retrain

### Phase 4: Weekly Retrain Cycle

```
Saturday 02:00  ─── Sync macro data (FRED, news, econ)
Saturday 02:30  ─── Export latest TV data (or pull from logged webhooks)
Saturday 03:00  ─── Build training set (join TV + macro + labels)
Sunday  02:00   ─── AutoGluon retrain (1-4 hours)
Sunday  06:00   ─── Model frozen, validate against holdout
Monday  06:00   ─── New model live for the week
```

---

## Local Python Server

### Stack

- **FastAPI** — lightweight, async, fast
- **AutoGluon** — model loading and prediction
- **PostgreSQL** (local) — macro data cache, trade log
- **Cloudflare Tunnel** — HTTPS endpoint for TradingView webhooks

### Endpoints

| Endpoint | Method | Purpose |
|---|---|---|
| `/webhook/bar` | POST | Receives 15m bar data from RR v2 |
| `/webhook/event` | POST | Receives fib events (touch, break, accept) |
| `/health` | GET | Server + model status |
| `/stats` | GET | Recent trade log, win rate, model performance |

### Server Flow

```python
@app.post("/webhook/bar")
async def handle_bar(data: BarData):
    # 1. Parse TV webhook JSON
    features = parse_tv_features(data)

    # 2. Enrich with macro data
    features = enrich_with_macro(features, local_db)

    # 3. Add timing features
    features = add_timing_features(features)

    # 4. Run gate check
    prediction = model.predict(features)
    probabilities = model.predict_proba(features)

    # 5. Compute gate status
    gates = compute_gates(features, model)

    # 6. Calculate entry/SL/TP from fib levels
    levels = compute_trade_levels(data.fib)

    # 7. Look up historical win rate for similar gate pattern
    win_rate = lookup_historical(gates, trade_log)

    # 8. Log to local DB
    log_prediction(data, prediction, gates)

    # 9. Return response for RR v2 to display
    return {
        "direction": "long" if data.fib.direction == "bull" else "short",
        "action": determine_action(prediction, gates),
        "confidence": float(probabilities["CLEAN"]),
        "gates_passed": gates.passed,
        "gates_total": gates.total,
        "tp1_prob": float(probabilities["CLEAN"] + probabilities["SURVIVED"]),
        "stop_prob": float(probabilities["STOPPED"] + probabilities["REVERSAL"]),
        "historical_win_rate": win_rate.pct,
        "similar_setups": win_rate.count,
        "avg_winner_pts": win_rate.avg_pts,
        "entry_price": levels.entry,
        "stop_price": levels.stop,
        "tp1_price": levels.tp1,
        "tp2_price": levels.tp2,
        "top_factors": gates.top_contributing,
        "failed_gates": gates.failed_list
    }
```

---

## What Gets Cut From Current Warbird Pro

| Component | Status | Savings |
|---|---|---|
| Next.js frontend (app/ directory) | **Eliminated** | Zero frontend maintenance |
| Supabase hosting (frontend) | **Eliminated** | ~$20-50/mo saved |
| Supabase pg_cron routes (most) | **Reduced to ~3-4** | Fewer function invocations |
| Realtime subscriptions | **Eliminated** | TV handles live data |
| Auth UI (login, signup, password) | **Eliminated** | TV handles auth |
| Custom chart rendering | **Eliminated** | TV charts are superior |
| Indicator replication in TypeScript | **Eliminated** | Pine Script is source of truth |

### What Stays

| Component | Purpose |
|---|---|
| Supabase (lean) | Macro data storage (FRED, news, econ), trade log, model performance tracking |
| pg_cron jobs (~10-15) | FRED/econ/news/GPR/trump-effect ingestion — enrichment data for model |
| Supabase pg_cron (~3-4) | Complex compute that can't be pg_cron (news processing, maybe forecast health check) |
| Local PostgreSQL | Training warehouse, macro data cache, trade log |
| AutoGluon training | Weekly retrain on local machine |
| Local Python server | FastAPI — receives webhooks, runs inference |

---

## Implementation Phases

### Phase 1: Training Data Pipeline (Week 1)
1. Export 2M bars from TradingView with all indicators loaded
2. Build Python script to parse CSV, add labels, join macro data
3. First AutoGluon training run
4. Feature importance analysis — identify the gates

### Phase 2: Local Python Server (Week 1-2)
1. FastAPI server with /webhook/bar endpoint
2. AutoGluon model loading and prediction
3. Macro data enrichment from local PostgreSQL
4. Cloudflare Tunnel setup for HTTPS

### Phase 3: Rabid Raccoon v2 (Week 2-3)
1. Strip all signal logic from current RR
2. Add webhook JSON output (alert with JSON payload)
3. Add confidence gauge (arc needle display)
4. Add trade card (table in top corner)
5. Add gate oscillator (bottom panel)
6. Read model response and update display

### Phase 4: Integration & Testing (Week 3-4)
1. End-to-end test: TV bar → webhook → model → response → display
2. Paper trading with live model for 1-2 weeks
3. Compare model entries vs manual entries
4. Tune gate threshold (how many gates needed for GO?)

### Phase 5: Feedback Loop (Ongoing)
1. Log every prediction and actual outcome
2. Weekly retrain with new data
3. Monitor win rate drift
4. Adjust features/gates as model learns

---

## Risk Mitigation

| Risk | Mitigation |
|---|---|
| Model overfits to training data | 5-fold cross-validation, holdout test set, weekly retrain on fresh data |
| Webhook latency too high | Cloudflare Tunnel is <50ms. Model prediction <1s. Total <2s. |
| TradingView indicator limit (25 on Premium) | Hide most indicators. Consider Ultimate (50) if needed. |
| Local server goes down | RR v2 shows "OFFLINE" in trade card. No false signals. Fail safe. |
| Repaint on RR fib levels | Log fib state per bar via webhook. Training uses live state, not final. |
| Model says GO but market gaps | Add after-hours/pre-market gate. Model learns session timing. |
| Too many features → slow training | 140 features x 2M rows is well within AutoGluon's capability. Hours, not days. |

---

## Success Criteria

1. **Win rate > 65%** on CLEAN entries (model says ENTER → price hits TP1)
2. **Stop loss ≤ 15 points** on average (tight stops because entries are precise)
3. **Average winner ≥ 20 points** (minimum target met)
4. **STOPPED rate < 15%** (entries that get stopped then price goes to target)
5. **Daily max: 3-5 trades** (quality over quantity)
6. **Trader confidence:** "When the system says GO, I enter without hesitation"
