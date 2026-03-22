# Checkpoint 6: AutoGluon Training Design + Scheduling Architecture

**Date:** 2026-03-19
**Status:** Decision Made
**Checkpoint:** Supabase Architecture Rethink — Checkpoint 6
**Depends on:** All prior checkpoints (1-5)

---

## Decision

**Three-tier scheduling.** Simple API ingestion moves to `pg_cron` + `http` extension inside Supabase Postgres (cheapest, zero invocation cost). Complex compute stays in Vercel Cron. Training and inference run on local machine cron.

**Two-mode model lifecycle.** Weekly core training (Sunday, full retrain on all data). Fast frequent inference (every 5 min during market hours, ~15s per invocation).

---

## Three-Tier Scheduling Architecture

### Tier 1: pg_cron + http Extension (Supabase Cloud Postgres)

**What:** Simple GET → parse JSON → INSERT. Runs inside Postgres. Zero network hop. Zero invocation cost.

**Why `http` not `pg_net`:**

| | `pg_net` | `http` |
|-|----------|--------|
| Type | Async (fire-and-forget) | **Synchronous** |
| Methods | JSON POST only | **GET/POST/PUT/DELETE/HEAD** |
| Best for | Webhooks | **Fetching APIs + writing results** |
| Transaction | No (async) | **Yes — fetch → parse → INSERT atomic** |

Most data APIs (FRED, Databento Historical, news) are GET requests returning JSON. The `http` extension handles this in one SQL transaction.

**Example — FRED ingestion entirely in Postgres:**

```sql
-- pg_cron scheduled job: fetch FRED rates daily
SELECT cron.schedule(
  'fred-rates',
  '0 5 * * *',  -- 5 AM UTC daily
  $$
    INSERT INTO econ_rates_1d (ts, series_id, value)
    SELECT
      (obs->>'date')::timestamptz AS ts,
      'DFF' AS series_id,
      (obs->>'value')::numeric AS value
    FROM jsonb_array_elements(
      (
        SELECT (content::jsonb)->'observations'
        FROM extensions.http_get(
          'https://api.stlouisfed.org/fred/series/observations?series_id=DFF&api_key='
          || current_setting('app.fred_api_key')
          || '&file_type=json&sort_order=desc&limit=5'
        )
      )
    ) AS obs
    WHERE (obs->>'value') != '.'
    ON CONFLICT (ts, series_id) DO UPDATE SET value = EXCLUDED.value;
  $$
);
```

**Routes that move to pg_cron + http:**

| Current Vercel Route | pg_cron Replacement | Why It Fits |
|---------------------|--------------------|----|
| `cron/fred/[category]` (9 schedules) | 9 pg_cron jobs | Simple GET JSON → INSERT. Perfect fit. |
| `cron/econ-calendar` | 1 pg_cron job | GET JSON → INSERT. |
| `cron/gpr` | 1 pg_cron job | GET → parse → INSERT (XLS parsing may need a helper function). |
| `cron/trump-effect` | 1 pg_cron job | GET JSON → INSERT. |
| `cron/news` | 1 pg_cron job | If logic is simple enough. Otherwise stays Vercel. |
| `cron/google-news` | Maybe | RSS/XML parsing in SQL is possible but ugly. Evaluate. |
| NEW: `mes-1d` | 1 pg_cron job | Databento ohlcv-1d GET → INSERT. |
| NEW: `mes-stats` | 1 pg_cron job | Databento statistics GET → INSERT. |
| NEW: `mes-definition` | 1 pg_cron job | Databento definition GET → INSERT. |
| NEW: `cross-asset-1d` | 1 pg_cron job | All symbols daily bars. |
| NEW: `cross-asset-stats` | 1 pg_cron job | All symbols stats. |
| NEW: `cross-asset-def` | 1 pg_cron job | All symbols definitions. |
| NEW: `options-1d` | 1 pg_cron job | Option daily bars. |
| NEW: `options-stats` | 1 pg_cron job | Option stats. |
| NEW: `options-def` | 1 pg_cron job | Option definitions. |

**API keys in Postgres:** Stored via `ALTER DATABASE postgres SET app.fred_api_key = 'xxx';` and accessed via `current_setting('app.fred_api_key')`. Never exposed to frontend. Vault is another option.

**Constraints:**
- Max 8 concurrent pg_cron jobs (stagger schedules — all are well-spaced)
- Each job must complete within 10 minutes
- Jobs tracked in `cron.job_run_details` (built-in monitoring)

### Tier 2: Vercel Cron (Complex Compute)

**What:** Routes that need heavy TypeScript computation, complex API interactions, or multi-step orchestration.

**Routes that stay Vercel:**

| Route | Schedule | Why It Can't Be pg_cron |
|-------|----------|------------------------|
| `mes-1s` | `*/5 * * * 0-5` | Complex Databento auth + binary + contract roll |
| `mes-1m` | `*/5 * * * 0-5` | Same |
| `mes-1h` | `5 * * * 0-5` | Same |
| `mes-aggregate` | `2,7 * * * 0-5` | TypeScript aggregation (until PG functions built) |
| `detect-setups` | `*/5 12-21 * * 1-5` | 6-layer Warbird engine |
| `score-trades` | `10,25,40,55 * * * 1-5` | Multi-step conditional logic |
| `measured-moves` | `0 18 * * 1-5` | Swing detection algorithms |
| `forecast` | `30 * * * 1-5` | Health check + writer invocation |
| `cross-asset-1h` | `*/15 * * * *` | Databento auth + sharded fetch |
| `google-news` | `0 13 * * 1-5` | RSS parsing + NLP (evaluate pg_cron later) |
| `news` | `0 16 * * *` | Complex processing (evaluate later) |

**Vercel routes reduced from 21 schedules → ~11 schedules.** Simpler, cheaper.

### Tier 3: Local Machine Cron (Training + Inference)

| Job | Schedule | What |
|-----|----------|------|
| `sync-down` | `0 2 * * 0` (weekly full) + `*/5 * * * 1-5` (market hours, incremental) | Pull cloud → local PG |
| `build-features` | `0 2 * * 0` (after sync) | Full feature table rebuild |
| `train-warbird` | `0 3 * * 0` (after features) | AutoGluon full retrain |
| `inference` | `*/5 * * * 1-5` (market hours) | Fast predict → publish |

---

## Two-Mode Model Lifecycle

### Mode 1: Weekly Core Training

```
When:     Sunday 02:00 local time (market closed)
Where:    Local machine
Duration: 1-4 hours
Trigger:  Local cron: 0 2 * * 0
```

**Pipeline:**

```
1. sync-down (full)
   └─ Pull all new data from cloud → local PG
   └─ ~35 tables, incremental by ts watermark
   └─ Duration: 5-15 min

2. refresh materialized views
   └─ REFRESH MATERIALIZED VIEW CONCURRENTLY mes_15m_mv, mes_4h_mv
   └─ Duration: seconds

3. build training_features (full rebuild)
   └─ For every 15m bar in training window:
      - OHLCV all timeframes (1m, 15m, 1h, 4h, 1d)
      - Fibonacci levels (multi-period)
      - Technical indicators (11 LuxAlgo + TTM Squeeze)
      - Settlement price, OI, cleared volume (statistics)
      - Session high/low (statistics)
      - Cross-asset context (ES, NQ, RTY, ZB, ZN, CL, GC)
      - Option OI/volume ratios (put/call)
      - Econ data (rates, yields, FX, vol, inflation, labor, activity)
      - News/sentiment signals, GPR index, trump effect
      - Measured move state
      - Warbird setup outcome labels (supervised target)
   └─ Write to training_features
   └─ Duration: 10-30 min

4. snapshot (immutable)
   └─ Copy training_features → training_snapshots (timestamped)
   └─ Prevents contamination if features are rebuilt mid-week

5. train
   └─ AutoGluon TabularPredictor
   └─ Input: training_snapshots
   └─ Target: setup outcome (TP1 prob, TP2 prob, stop prob)
   └─ Preset: best_quality
   └─ Bagging: 5-fold, Stack levels: 1
   └─ Model types: GBM, NN, RF, XGBoost, CatBoost, LightGBM
   └─ Save: ~/models/warbird/YYYY-MM-DD/
   └─ Write: model_runs metadata to local PG
   └─ Duration: 1-4 hours

6. validate
   └─ Out-of-sample metrics on holdout set
   └─ Compare to previous week's model
   └─ Write validation results to model_runs
```

**Model is FROZEN after step 5. Does not change until next Sunday.**

### Mode 2: Fast Frequent Inference (Market Hours)

```
When:     Mon-Fri, every 5 min during market hours
Where:    Local machine
Duration: <15 seconds per invocation
Trigger:  Local cron: */5 * * * 1-5
```

**Pipeline:**

```
1. check market hours → exit if closed

2. sync-down (incremental)
   └─ Pull only bars newer than last sync ts
   └─ ~5-50 rows, <3s

3. check: new 15m bar since last forecast?
   └─ NO → exit (no work)

4. build ONE feature row
   └─ Same engineering as training, single row
   └─ <1s

5. predict
   └─ Load frozen model (cached after first load)
   └─ model.predict(feature_row)
   └─ Output: direction, confidence, TP1/TP2/stop probabilities
   └─ <5s

6. publish to cloud
   └─ Upsert → cloud warbird_forecasts
   └─ Realtime pushes to dashboard
   └─ <2s

7. log to local PG → inference_results
   └─ Total: <15s
```

**Model loading:** First invocation loads from disk (~2-5s). Start with cron invocation (simple). If 5s overhead matters, switch to persistent daemon.

---

## The Full Weekly Cycle

```
SAT 02:00  ─── sync-down (full week of data)
SAT 02:30  ─── build-features (full rebuild)
SUN 02:00  ─── train-warbird.py (1-4 hours)
SUN 06:00  ─── model frozen, ready for week

MON-FRI market hours:
  Every 5 min (local cron):
    ├─ sync latest bars (incremental, <3s)
    ├─ new 15m bar? NO → exit. YES ↓
    ├─ build 1 feature row (<1s)
    ├─ model.predict() (<5s)
    ├─ publish to cloud (<2s)
    └─ total: <15s per invocation

  Every 30 min (Vercel cron/forecast):
    └─ health-check: is forecast fresh?
       YES → dashboard shows live forecast
       NO  → logs stale_forecast warning
```

---

## Scheduling Migration: Vercel → pg_cron

### pg_cron Jobs (22 total, all well-spaced)

| Job | Schedule (UTC) | Source |
|-----|---------------|--------|
| `fred-rates` | `0 5 * * *` | Migrated from Vercel |
| `fred-yields` | `0 6 * * *` | Migrated |
| `fred-vol` | `0 7 * * *` | Migrated |
| `fred-inflation` | `0 8 * * *` | Migrated |
| `fred-fx` | `0 9 * * *` | Migrated |
| `fred-labor` | `0 10 * * *` | Migrated |
| `fred-activity` | `0 11 * * *` | Migrated |
| `fred-commodities` | `0 12 * * *` | Migrated |
| `fred-money` | `0 1 * * *` | Migrated (moved to 1 AM) |
| `fred-indexes` | `0 2 * * *` | Migrated (moved to 2 AM) |
| `econ-calendar` | `0 15 * * *` | Migrated |
| `gpr` | `0 19 * * *` | Migrated |
| `trump-effect` | `30 19 * * *` | Migrated |
| `mes-daily` | `0 22 * * 0-5` | New |
| `mes-stats` | `30 22 * * 0-5` | New |
| `mes-def` | `0 3 * * 0-5` | New |
| `xa-daily` | `0 23 * * *` | New |
| `xa-stats` | `30 23 * * *` | New |
| `xa-def` | `0 4 * * *` | New |
| `opt-daily` | `0 0 * * 1-5` | New |
| `opt-stats` | `30 0 * * 1-5` | New |
| `opt-def` | `0 1 * * 1-5` | New |

### Vercel Cron (11 schedules remain)

| Route | Schedule |
|-------|----------|
| `mes-1s` | `*/5 * * * 0-5` |
| `mes-1m` | `*/5 * * * 0-5` |
| `mes-1h` | `5 * * * 0-5` |
| `mes-aggregate` | `2,7 * * * 0-5` |
| `cross-asset-1h` | `*/15 * * * *` |
| `detect-setups` | `*/5 12-21 * * 1-5` |
| `score-trades` | `10,25,40,55 * * * 1-5` |
| `measured-moves` | `0 18 * * 1-5` |
| `forecast` | `30 * * * 1-5` |
| `google-news` | `0 13 * * 1-5` |
| `news` | `0 16 * * *` |

### Local Cron (4 jobs)

| Job | Schedule |
|-----|----------|
| `sync-down-full` | `0 2 * * 0` |
| `build-features` | `30 2 * * 0` |
| `train-warbird` | `0 3 * * 0` |
| `inference` | `*/5 * * * 1-5` |

---

## Verification Checklist

| Rule | Passes? | Note |
|------|---------|------|
| Cost boundary | Yes | pg_cron + http = zero extra cost. Reduces Vercel invocations. |
| Production boundary | Yes | Dashboard works without local machine |
| AGENTS.md: no new paid plans | Yes | http extension included in Supabase |
| AGENTS.md: no continuous local runtime for production | Yes | Local is training/inference only |
| Training: reproducibility | Yes | Immutable training_snapshots, frozen weekly model |
| Training: leakage control | Yes | Point-in-time features, no future data |
| Checkpoint 4: pull spacing | Yes | All pg_cron jobs staggered across hours |

---

## Implementation Implications

1. **Enable extensions:** `CREATE EXTENSION IF NOT EXISTS http;` (pg_cron likely already available)
2. **Store API keys:** `ALTER DATABASE postgres SET app.fred_api_key = '...';` or Supabase Vault
3. **Write PL/pgSQL functions** for each data source ingestion
4. **Schedule 22 pg_cron jobs** (well-spaced, staggered)
5. **Remove migrated Vercel routes** from `vercel.json` and delete route files (13 → ~11 Vercel, 9+ FRED routes gone)
6. **Local cron setup:** 4 jobs via macOS launchd or crontab
7. **Update training scripts** to read from local PG training_snapshots
8. **New inference script:** lightweight predict → publish loop
9. **Monitor:** pg_cron in `cron.job_run_details`, Vercel in `job_log`, local in `model_runs`
