# Warbird v1 Pipeline Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build the complete Warbird v1 data pipeline — from backfill through training — using 1H-only fibs, TP1/TP2-only targets, and 5 fib-relative binary labels.

**Architecture:** All data flows through Supabase. Dataset builder reads Supabase, outputs a local CSV. AutoGluon trains locally from that CSV. Inference is written back to Supabase via predict-warbird.py. Vercel cron reads from Supabase to run the conviction engine.

**Tech Stack:** Python (Databento SDK, fredapi/requests, openpyxl, arch), TypeScript/Node (Supabase JS client), AutoGluon TabularPredictor, Vercel Cron, Supabase Postgres.

---

## Hard Rules (read before writing a single line)

- NO ORM. Supabase client only.
- NO mock data. Real or nothing.
- NO new tables or schema changes — the schema is locked.
- `series_catalog` uses `category` column (enum), NOT `domain_table`.
- Econ table names from migration: `econ_rates_1d`, `econ_yields_1d`, `econ_fx_1d`, `econ_vol_1d`, `econ_inflation_1d`, `econ_labor_1d`, `econ_activity_1d`, `econ_money_1d`, `econ_commodities_1d`, `econ_indexes_1d`.
- 1H is the ONLY fib anchor. Do not reference 15M fibs anywhere.
- `npm run build` must pass before every push.

---

## Task 1: Add 12 New FRED Series to seed.sql

**Files:**
- Modify: `supabase/seed.sql`

**Step 1: Open seed.sql and find the series_catalog insert block**

It ends around line 207 with `on conflict (series_id) do nothing;`.
The `category` values must match the `econ_category` enum. Valid values (from the insert pattern already present): `'rates'`, `'yields'`, `'fx'`, `'vol'`, `'inflation'`, `'labor'`, `'activity'`, `'money'`, `'commodities'`, `'indexes'`.

**Step 2: Append new series to the insert block**

Add these 12 rows immediately before `on conflict (series_id) do nothing;`:

```sql
  -- Volatility (additional)
  ('VXNCLS', 'Nasdaq-100 Volatility Index (VXN)', null, 'vol', 'daily', true),
  ('RVXCLS', 'Russell 2000 Volatility Index (RVX)', null, 'vol', 'daily', true),

  -- Credit spreads
  ('BAMLC0A0CM', 'ICE BofA IG Corporate OAS', null, 'indexes', 'daily', true),
  ('BAMLHYH0A0HYM2EY', 'ICE BofA HY Option-Adjusted Spread', null, 'indexes', 'daily', true),
  ('BAA10Y', 'Baa Corporate Bond Spread', null, 'yields', 'daily', true),

  -- Financial conditions
  ('NFCI', 'Chicago Fed National Financial Conditions Index', null, 'indexes', 'weekly', true),
  ('STLFSI4', 'St. Louis Fed Financial Stress Index', null, 'indexes', 'weekly', true),
  ('ANFCI', 'Adjusted NFCI', null, 'indexes', 'weekly', true),

  -- Consumer sentiment
  ('UMCSENT', 'University of Michigan Consumer Sentiment', null, 'indexes', 'monthly', true),

  -- Recession indicators
  ('RECPROUSM156N', 'Smoothed US Recession Probabilities', null, 'indexes', 'monthly', true),
  ('SAHMCURRENT', 'Sahm Rule Recession Indicator', null, 'indexes', 'monthly', true),

  -- Macro business cycle
  ('EMVMACROBUS', 'Equity Market Macro Business Cycle Uncertainty', null, 'indexes', 'daily', true)
```

**Step 3: Verify no duplicate series_id conflicts**

Run: `grep -n "VXNCLS\|RVXCLS\|BAMLC0A0CM\|UMCSENT\|SAHMCURRENT" supabase/seed.sql`
Expected: only your new lines match.

**Step 4: Commit**

```bash
git add supabase/seed.sql
git commit -m "feat: add 12 new FRED series to series_catalog seed"
```

---

## Task 2: Run MES Backfill

**Files:**
- Use as-is: `scripts/backfill.py`

**Step 1: Verify the script exists and check its arguments**

```bash
python scripts/backfill.py --help
```

**Step 2: Run the full 2-year backfill**

```bash
python scripts/backfill.py --start 2024-01-01 --end 2026-03-16
```

This runs locally. It writes `mes_1m`, `mes_1h`, `mes_1d` (direct from Databento), then derives `mes_15m` and `mes_4h`.

**Step 3: Verify row counts in Supabase**

Connect to Supabase and run:
```sql
select 'mes_1m' as t, count(*) from mes_1m
union all select 'mes_1h', count(*) from mes_1h
union all select 'mes_1d', count(*) from mes_1d
union all select 'mes_15m', count(*) from mes_15m
union all select 'mes_4h', count(*) from mes_4h;
```

Expected (approximate, US trading hours only, 2024-01-01 → 2026-03-16):
- `mes_1h`: ~4,000+ rows
- `mes_1d`: ~550+ rows
- `mes_4h`: ~1,000+ rows

Do NOT proceed until all 5 tables have data.

---

## Task 3: Create `scripts/backfill-cross-asset.py`

**Files:**
- Create: `scripts/backfill-cross-asset.py`

**Step 1: Write the script**

```python
#!/usr/bin/env python3
"""
Backfill cross-asset 1H bars for all active non-MES Databento correlation symbols.
Writes to cross_asset_1h(ts, symbol_code, open, high, low, close, volume).
"""
from __future__ import annotations

import os
import sys
from datetime import date, timedelta

import databento as db
from supabase import create_client

CORRELATION_SYMBOLS = [
    "NQ.c.0", "ZN.c.0", "ZF.c.0", "ZB.c.0", "SR3.c.0",
    "6E.c.0", "6J.c.0", "ES.c.0", "YM.c.0", "RTY.c.0",
    "CL.c.0", "GC.c.0",
]

# VX and DX are FRED-sourced, not Databento — skip here
# SOX is Databento but may require separate dataset — include, will error-skip if unavailable

SYMBOL_TO_CODE = {
    "NQ.c.0": "NQ", "ZN.c.0": "ZN", "ZF.c.0": "ZF", "ZB.c.0": "ZB",
    "SR3.c.0": "SR3", "6E.c.0": "6E", "6J.c.0": "6J", "ES.c.0": "ES",
    "YM.c.0": "YM", "RTY.c.0": "RTY", "CL.c.0": "CL", "GC.c.0": "GC",
}

def main() -> None:
    api_key = os.environ["DATABENTO_API_KEY"]
    sb_url = os.environ.get("NEXT_PUBLIC_SUPABASE_URL") or os.environ["SUPABASE_URL"]
    sb_key = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
    supabase = create_client(sb_url, sb_key)

    start = "2024-01-01"
    end = "2026-03-17"  # exclusive upper bound for Databento

    client = db.Historical(api_key)

    for db_symbol in CORRELATION_SYMBOLS:
        symbol_code = SYMBOL_TO_CODE[db_symbol]
        print(f"Fetching {symbol_code} ({db_symbol})...")
        try:
            data = client.timeseries.get_range(
                dataset="GLBX.MDP3",
                schema="ohlcv-1h",
                symbols=[db_symbol],
                start=start,
                end=end,
            ).to_df()
        except Exception as exc:
            print(f"  SKIP {symbol_code}: {exc}")
            continue

        if data.empty:
            print(f"  SKIP {symbol_code}: no data returned")
            continue

        rows = []
        for _, bar in data.iterrows():
            rows.append({
                "ts": bar.name.isoformat() if hasattr(bar.name, "isoformat") else str(bar["ts_event"]),
                "symbol_code": symbol_code,
                "open": float(bar["open"]) / 1e9 if bar["open"] > 1e6 else float(bar["open"]),
                "high": float(bar["high"]) / 1e9 if bar["high"] > 1e6 else float(bar["high"]),
                "low": float(bar["low"]) / 1e9 if bar["low"] > 1e6 else float(bar["low"]),
                "close": float(bar["close"]) / 1e9 if bar["close"] > 1e6 else float(bar["close"]),
                "volume": int(bar["volume"]),
            })

        # Upsert in chunks of 500
        chunk_size = 500
        for i in range(0, len(rows), chunk_size):
            chunk = rows[i:i + chunk_size]
            res = supabase.table("cross_asset_1h").upsert(chunk, on_conflict="ts,symbol_code").execute()
            if hasattr(res, "error") and res.error:
                print(f"  ERROR upserting {symbol_code}: {res.error}")
                break

        print(f"  {symbol_code}: {len(rows)} bars upserted")

if __name__ == "__main__":
    main()
```

**Step 2: Run it**

```bash
python scripts/backfill-cross-asset.py
```

**Step 3: Verify**

```sql
select symbol_code, count(*), min(ts), max(ts)
from cross_asset_1h
group by symbol_code
order by symbol_code;
```

Expected: 12 symbols, each with 3,000–5,000 rows spanning 2024 → 2026.

**Step 4: Commit**

```bash
git add scripts/backfill-cross-asset.py
git commit -m "feat: add cross-asset 1H backfill script for correlation symbols"
```

---

## Task 4: Create `scripts/backfill-fred.py`

**Files:**
- Create: `scripts/backfill-fred.py`

**Step 1: Write the script**

The script reads all active series from `series_catalog`, fetches each from FRED, and upserts into the correct `econ_*_1d` table based on the `category` column.

Category → table mapping:
- `rates` → `econ_rates_1d`
- `yields` → `econ_yields_1d`
- `fx` → `econ_fx_1d`
- `vol` → `econ_vol_1d`
- `inflation` → `econ_inflation_1d`
- `labor` → `econ_labor_1d`
- `activity` → `econ_activity_1d`
- `money` → `econ_money_1d`
- `commodities` → `econ_commodities_1d`
- `indexes` → `econ_indexes_1d`

```python
#!/usr/bin/env python3
"""
Backfill all active FRED series from series_catalog into their econ domain tables.
"""
from __future__ import annotations

import os
import time
import requests
from supabase import create_client

CATEGORY_TABLE = {
    "rates":       "econ_rates_1d",
    "yields":      "econ_yields_1d",
    "fx":          "econ_fx_1d",
    "vol":         "econ_vol_1d",
    "inflation":   "econ_inflation_1d",
    "labor":       "econ_labor_1d",
    "activity":    "econ_activity_1d",
    "money":       "econ_money_1d",
    "commodities": "econ_commodities_1d",
    "indexes":     "econ_indexes_1d",
}

def fetch_fred_series(series_id: str, api_key: str, start: str = "2020-01-01") -> list[dict]:
    url = "https://api.stlouisfed.org/fred/series/observations"
    params = {
        "series_id": series_id,
        "api_key": api_key,
        "file_type": "json",
        "observation_start": start,
        "observation_end": "2026-03-16",
    }
    resp = requests.get(url, params=params, timeout=30)
    resp.raise_for_status()
    observations = resp.json().get("observations", [])
    rows = []
    for obs in observations:
        if obs["value"] == ".":
            continue
        rows.append({
            "ts": obs["date"] + "T00:00:00Z",
            "series_id": series_id,
            "value": float(obs["value"]),
        })
    return rows

def main() -> None:
    fred_key = os.environ["FRED_API_KEY"]
    sb_url = os.environ.get("NEXT_PUBLIC_SUPABASE_URL") or os.environ["SUPABASE_URL"]
    sb_key = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
    supabase = create_client(sb_url, sb_key)

    # Pull active series from series_catalog
    res = supabase.table("series_catalog").select("series_id, category").eq("is_active", True).execute()
    catalog = res.data or []
    print(f"Found {len(catalog)} active series")

    for entry in catalog:
        series_id = entry["series_id"]
        category = entry["category"]
        table = CATEGORY_TABLE.get(category)
        if not table:
            print(f"  SKIP {series_id}: unknown category '{category}'")
            continue

        print(f"Fetching {series_id} → {table}...")
        try:
            rows = fetch_fred_series(series_id, fred_key)
        except Exception as exc:
            print(f"  ERROR {series_id}: {exc}")
            time.sleep(1)
            continue

        if not rows:
            print(f"  SKIP {series_id}: no observations")
            continue

        # Upsert in chunks of 500
        for i in range(0, len(rows), 500):
            chunk = rows[i:i + 500]
            supabase.table(table).upsert(chunk, on_conflict="ts,series_id").execute()

        print(f"  {series_id}: {len(rows)} rows → {table}")
        time.sleep(0.5)  # FRED rate limit: 120 req/min

if __name__ == "__main__":
    main()
```

**Step 2: Run it (after Task 1 commit is applied to Supabase)**

```bash
python scripts/backfill-fred.py
```

If Supabase seed hasn't been re-applied yet, the new 12 series won't be in `series_catalog`. Apply seed first or insert them manually.

**Step 3: Verify**

```sql
select table_name, count(*)
from (
  select 'econ_rates_1d' as table_name, count(*) from econ_rates_1d
  union all select 'econ_yields_1d', count(*) from econ_yields_1d
  union all select 'econ_vol_1d', count(*) from econ_vol_1d
  union all select 'econ_indexes_1d', count(*) from econ_indexes_1d
) t
group by table_name;
```

**Step 4: Commit**

```bash
git add scripts/backfill-fred.py
git commit -m "feat: add FRED backfill script for all 42 series"
```

---

## Task 5: Create `scripts/backfill-gpr.py`

**Files:**
- Create: `scripts/backfill-gpr.py`

**Context:** GPR data comes from Caldara-Iacoviello (matteoiacoviello.com). Download the historical XLS manually and place it at `data/gpr_web.xls`. The file has columns for date, GPR, GPRACT (actual conflict), GPRTHREAT (threats).

**Step 1: Download the XLS**

Go to: https://www.matteoiacoviello.com/gpr.htm
Download the daily GPR data file. Save to `data/gpr_web.xls`.

**Step 2: Write the script**

```python
#!/usr/bin/env python3
"""
Backfill GPR (Geopolitical Risk) data from Caldara-Iacoviello XLS.
Writes two series to geopolitical_risk_1d: gpr_acts and gpr_threats.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import openpyxl
from supabase import create_client

def main() -> None:
    xls_path = Path(sys.argv[1] if len(sys.argv) > 1 else "data/gpr_web.xls")
    if not xls_path.exists():
        print(f"ERROR: {xls_path} not found. Download from matteoiacoviello.com/gpr.htm")
        sys.exit(1)

    sb_url = os.environ.get("NEXT_PUBLIC_SUPABASE_URL") or os.environ["SUPABASE_URL"]
    sb_key = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
    supabase = create_client(sb_url, sb_key)

    # openpyxl handles both .xls (via xlrd fallback) and .xlsx
    # If .xls format, use xlrd:
    try:
        import xlrd
        book = xlrd.open_workbook(str(xls_path))
        sheet = book.sheet_by_index(0)
        headers = [sheet.cell_value(0, c) for c in range(sheet.ncols)]
        rows_raw = [
            {headers[c]: sheet.cell_value(r, c) for c in range(sheet.ncols)}
            for r in range(1, sheet.nrows)
        ]
    except ImportError:
        wb = openpyxl.load_workbook(str(xls_path))
        ws = wb.active
        headers = [cell.value for cell in ws[1]]
        rows_raw = [
            {headers[i]: row[i].value for i in range(len(headers))}
            for row in ws.iter_rows(min_row=2)
        ]

    # Map column names (may vary by version): date, GPRACT, GPRTHREAT
    date_col = next((h for h in headers if h and "date" in str(h).lower()), None)
    acts_col = next((h for h in headers if h and "ACT" in str(h).upper()), None)
    threat_col = next((h for h in headers if h and "THREAT" in str(h).upper()), None)

    if not date_col:
        print(f"ERROR: can't find date column. Headers: {headers}")
        sys.exit(1)

    rows_acts = []
    rows_threats = []
    for raw in rows_raw:
        date_val = raw.get(date_col)
        if not date_val:
            continue
        # date may be a float (Excel serial) or string
        if isinstance(date_val, float):
            import datetime
            date_str = (datetime.date(1899, 12, 30) + datetime.timedelta(days=int(date_val))).isoformat()
        else:
            date_str = str(date_val)[:10]

        ts = date_str + "T00:00:00Z"

        if acts_col and raw.get(acts_col) is not None:
            rows_acts.append({"ts": ts, "series_id": "gpr_acts", "value": float(raw[acts_col])})
        if threat_col and raw.get(threat_col) is not None:
            rows_threats.append({"ts": ts, "series_id": "gpr_threats", "value": float(raw[threat_col])})

    all_rows = rows_acts + rows_threats
    print(f"Upserting {len(all_rows)} GPR rows...")

    for i in range(0, len(all_rows), 500):
        chunk = all_rows[i:i + 500]
        supabase.table("geopolitical_risk_1d").upsert(chunk, on_conflict="ts,series_id").execute()

    print(f"Done. {len(rows_acts)} gpr_acts, {len(rows_threats)} gpr_threats.")

if __name__ == "__main__":
    main()
```

**Step 3: Install xlrd if needed**

```bash
pip install xlrd openpyxl
```

**Step 4: Run it**

```bash
python scripts/backfill-gpr.py data/gpr_web.xls
```

**Step 5: Verify**

```sql
select series_id, count(*), min(ts), max(ts)
from geopolitical_risk_1d
group by series_id;
```

Expected: 2 rows (gpr_acts, gpr_threats), each with hundreds of daily entries.

**Step 6: Commit**

```bash
git add scripts/backfill-gpr.py
git commit -m "feat: add GPR backfill script for Caldara-Iacoviello data"
```

---

## Task 6: Fix `conviction-matrix.ts` — Remove runnerEligible

**Files:**
- Modify: `scripts/warbird/conviction-matrix.ts`

**Step 1: Read the current file** (already read — 87 lines)

The `ConvictionResult` interface has `runnerEligible: boolean`. All 5 return objects include `runnerEligible`.

**Step 2: Remove `runnerEligible` from the interface**

```typescript
// BEFORE
export interface ConvictionResult {
  level: WarbirdConvictionLevel;
  counterTrend: boolean;
  allLayersAgree: boolean;
  runnerEligible: boolean;
}

// AFTER
export interface ConvictionResult {
  level: WarbirdConvictionLevel;
  counterTrend: boolean;
  allLayersAgree: boolean;
}
```

**Step 3: Remove `runnerEligible` from all 5 return objects**

Each return statement currently has `runnerEligible: true` or `runnerEligible: false` or `runnerEligible: triggerAligned`. Remove that field from all of them.

**Step 4: Verify build passes**

```bash
npm run build 2>&1 | tail -20
```

Expected: no TypeScript errors.

**Step 5: Commit**

```bash
git add scripts/warbird/conviction-matrix.ts
git commit -m "fix: remove runnerEligible from conviction matrix (no runner logic)"
```

---

## Task 7: Fix `detect-setups/route.ts` — Remove 15M Layer, Runners, Time Expiry

**Files:**
- Modify: `app/api/cron/detect-setups/route.ts`

This is the most involved code change. Read the file carefully before editing (already read — 309 lines).

**Step 1: Remove the 15M fetch from the Promise.all**

In the `Promise.all([...])` block (lines 57–87), remove the `mes_15m` query entirely. Keep: `dailyBarsRes`, `fourHourBarsRes`, `oneHourBarsRes`, `forecastRes`.

**Step 2: Remove the 15M import and related guards**

Remove: `import { evaluateTrigger15m } from "@/scripts/warbird/trigger-15m";`
Remove the `fifteenBarsRes.error` check.
Remove: `const fifteenBars = toCandles(fifteenBarsRes.data);`
Remove the `fifteenBars.length < 20` from the data guard condition.
Remove: `const triggerPayload = evaluateTrigger15m(...)` block entirely.
Remove: The entire `warbird_triggers_15m` upsert block (lines 143–151).

**Step 3: Rebuild trigger variables from forecast directly**

The cron no longer has a `trigger` object from `warbird_triggers_15m`. Replace all `trigger.*` references with values derived from `forecast` and `geometry`:

```typescript
// After removing the trigger upsert, build conviction directly from forecast + geometry:
const convictionInput = {
  dailyBias: daily.bias,
  bias4h: structure.bias_4h,
  bias1h: forecast.bias_1h,
  triggerDecision: geometry ? "GO" : "NO_TRADE",
} as const;

const convictionResult = evaluateConviction(convictionInput);
```

**Step 4: Upsert warbird_conviction without trigger_id**

The conviction payload no longer has a `trigger_id`. Use only: `ts`, `forecast_id`, `symbol_code`, plus spread of `convictionResult`, plus the bias fields.

```typescript
const convictionTs = new Date().toISOString();
const convictionPayload = {
  ts: convictionTs,
  forecast_id: forecast.id,
  symbol_code: WARBIRD_DEFAULT_SYMBOL,
  ...convictionResult,
  daily_bias: daily.bias,
  bias_4h: structure.bias_4h,
  bias_1h: forecast.bias_1h,
  trigger_decision: geometry ? "GO" : "NO_TRADE",
};
```

Check if `warbird_conviction` has a `trigger_id` column (from the migration). If it does, pass `null`. Do NOT drop the column — schema is locked.

**Step 5: Build the setup from geometry + forecast + conviction directly**

The setup payload previously used `trigger.*` values. Replace with values from `forecast` and `geometry`:

```typescript
const setupPayload = {
  setup_key: setupKey,
  ts: convictionTs,
  symbol_code: WARBIRD_DEFAULT_SYMBOL,
  forecast_id: forecast.id,
  trigger_id: null,           // no trigger row anymore
  conviction_id: conviction.id,
  direction: geometry.direction,
  status: "ACTIVE",
  conviction_level: conviction.level,
  counter_trend: convictionResult.counterTrend,
  runner_eligible: null,      // removed, pass null if column exists
  fib_level: geometry.fibLevel,
  fib_ratio: geometry.fibRatio,
  entry_price: geometry.entry,
  stop_loss: geometry.stopLoss,
  tp1: geometry.tp1,
  tp2: geometry.tp2,
  volume_confirmation: null,
  volume_ratio: null,
  trigger_quality_ratio: null,
  runner_headroom: null,
  current_event: "TRIGGERED",
  trigger_bar_ts: convictionTs,
  // No expires_at — removed time-based expiry
  notes: geometry.measuredMove
    ? `Measured move quality ${geometry.quality}`
    : "Canonical fib setup",
};
```

**Step 6: Update the setup_key to not depend on trigger fields**

```typescript
const setupKey = [
  forecast.id,
  convictionTs.slice(0, 13), // hour-level dedup
  geometry.direction,
  Number(geometry.fibRatio ?? 0).toFixed(3),
].join(":");
```

**Step 7: Remove runner_eligible and runner_headroom from setup_events metadata**

In the `warbird_setup_events` insert, remove `runner_eligible` from metadata.

**Step 8: Verify build passes**

```bash
npm run build 2>&1 | tail -20
```

If TypeScript complains about `trigger_id` being required in the conviction or setup table type, check the Supabase types. Pass `null` for any removed fields that exist in the DB schema.

**Step 9: Commit**

```bash
git add app/api/cron/detect-setups/route.ts
git commit -m "fix: remove 15M trigger layer, runner fields, and time-based expiry from detect-setups"
```

---

## Task 8: Fix `train-warbird.py` — Targets, Metrics, RF

**Files:**
- Modify: `scripts/warbird/train-warbird.py`

**Step 1: Replace TARGETS and add TARGET_CONFIG**

```python
# Remove old TARGETS list. Replace with:

TARGET_CONFIG = {
    "reached_tp1":           {"problem_type": "binary",     "eval_metric": "roc_auc"},
    "reached_tp2":           {"problem_type": "binary",     "eval_metric": "roc_auc"},
    "setup_stopped":         {"problem_type": "binary",     "eval_metric": "roc_auc"},
    "max_favorable_excursion": {"problem_type": "regression", "eval_metric": "root_mean_squared_error"},
    "max_adverse_excursion":   {"problem_type": "regression", "eval_metric": "root_mean_squared_error"},
}
```

**Step 2: Update the training loop**

Replace the `for target in TARGETS:` loop with:

```python
for target, config in TARGET_CONFIG.items():
    feature_cols = [
        col
        for col in df.columns
        if col not in DROP_COLS and not col.startswith("target_") and col != target
    ]
    predictor_path = output_dir / target
    predictor = TabularPredictor(
        label=target,
        problem_type=config["problem_type"],
        eval_metric=config["eval_metric"],
        path=str(predictor_path),
    )
    predictor.fit(
        train_data=train[feature_cols + [target]],
        tuning_data=valid[feature_cols + [target]],
        presets="best_quality",
        num_bag_folds=5,
        num_stack_levels=1,
        dynamic_stacking="auto",
        excluded_model_types=["KNN", "FASTAI"],  # RF removed from exclusion list
        ag_args_ensemble={"fold_fitting_strategy": "sequential_local"},
    )
    ...
```

**Step 3: Update DROP_COLS to include all old raw targets**

```python
DROP_COLS = {
    "timestamp",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "target_price_1h",
    "target_price_4h",
    "target_mae_1h",
    "target_mae_4h",
    "target_mfe_1h",
    "target_mfe_4h",
}
```

**Step 4: Commit**

```bash
git add scripts/warbird/train-warbird.py
git commit -m "fix: update train-warbird to 5 fib-relative targets with correct AG problem_type and eval_metric"
```

---

## Task 9: Rewrite `build-warbird-dataset.ts` — Fib-Setup Rows, Correct Targets

**Files:**
- Modify: `scripts/warbird/build-warbird-dataset.ts`

This is the largest single task. The existing builder iterates every 1H candle. It must be rewritten to:
1. Select only rows where `buildFibGeometry()` fires a valid setup.
2. Forward-scan to compute 5 fib-relative target labels.
3. Pre-compute rolling correlations for 15 symbols × 2 windows.
4. Remove `runner_eligible_recent_20` and other runner columns.
5. Correct FRED table names (they match migration: `econ_rates_1d` etc. — already correct in existing file).

**Step 1: Add `buildFibGeometry` import**

```typescript
import { buildFibGeometry } from "@/scripts/warbird/fib-engine";
import { buildStructure4H } from "@/scripts/warbird/structure-4h";
import type { CandleData } from "@/lib/types";
```

**Step 2: Add a helper to convert OhlcvRow → CandleData**

```typescript
function toCandle(row: OhlcvRow): CandleData {
  return {
    time: Math.floor(new Date(row.ts).getTime() / 1000),
    open: Number(row.open),
    high: Number(row.high),
    low: Number(row.low),
    close: Number(row.close),
    volume: Number(row.volume),
  };
}
```

**Step 3: Add rolling correlation helper**

```typescript
function rollingCorrelation(
  xValues: number[],
  yValues: number[],
  window: number,
): Array<number | null> {
  const result: Array<number | null> = Array(xValues.length).fill(null);
  for (let i = window - 1; i < xValues.length; i++) {
    const xSlice = xValues.slice(i - window + 1, i + 1);
    const ySlice = yValues.slice(i - window + 1, i + 1);
    const xMean = xSlice.reduce((s, v) => s + v, 0) / window;
    const yMean = ySlice.reduce((s, v) => s + v, 0) / window;
    let num = 0, xDen = 0, yDen = 0;
    for (let j = 0; j < window; j++) {
      const dx = xSlice[j] - xMean;
      const dy = ySlice[j] - yMean;
      num += dx * dy;
      xDen += dx * dx;
      yDen += dy * dy;
    }
    const denom = Math.sqrt(xDen * yDen);
    result[i] = denom === 0 ? null : num / denom;
  }
  return result;
}
```

**Step 4: Add target computation helper**

```typescript
function computeTargets(
  bars: OhlcvRow[],
  startIndex: number,
  entry: number,
  stopLoss: number,
  tp1: number,
  tp2: number,
  direction: "LONG" | "SHORT",
): {
  reached_tp1: number;
  reached_tp2: number;
  setup_stopped: number;
  max_favorable_excursion: number;
  max_adverse_excursion: number;
} {
  let reachedTp1 = 0;
  let reachedTp2 = 0;
  let setupStopped = 0;
  let maxFav = 0;
  let maxAdv = 0;

  for (let i = startIndex + 1; i < bars.length && i < startIndex + 100; i++) {
    const bar = bars[i];
    const high = Number(bar.high);
    const low = Number(bar.low);

    if (direction === "LONG") {
      const fav = high - entry;
      const adv = entry - low;
      maxFav = Math.max(maxFav, fav);
      maxAdv = Math.max(maxAdv, adv);

      if (low <= stopLoss) { setupStopped = 1; break; }
      if (high >= tp2) { reachedTp2 = 1; reachedTp1 = 1; break; }
      if (high >= tp1) { reachedTp1 = 1; }
    } else {
      const fav = entry - low;
      const adv = high - entry;
      maxFav = Math.max(maxFav, fav);
      maxAdv = Math.max(maxAdv, adv);

      if (high >= stopLoss) { setupStopped = 1; break; }
      if (low <= tp2) { reachedTp2 = 1; reachedTp1 = 1; break; }
      if (low <= tp1) { reachedTp1 = 1; }
    }
  }

  return {
    reached_tp1: reachedTp1,
    reached_tp2: reachedTp2,
    setup_stopped: setupStopped,
    max_favorable_excursion: maxFav,
    max_adverse_excursion: maxAdv,
  };
}
```

**Step 5: Rewrite buildDataset main loop**

The outer loop changes from "every 1H candle" to "only candles where fib geometry fires":

```typescript
// Inside buildDataset(), after computing ordered1h and cross-asset arrays:

// Pre-compute MES 1H closes for correlation
const mesCloses = ordered1h.map((r) => Number(r.close));

// Pre-compute rolling correlations for all cross-asset symbols
const corrMap = new Map<string, { c20: (number | null)[]; c60: (number | null)[] }>();
for (const symbol of crossSymbols) {
  const symbolBars = crossBySymbol.get(symbol) ?? [];
  // Align symbol bars to ordered1h timestamps by nearest available value
  const symbolCloses = ordered1h.map((bar) => {
    const tsMs = new Date(bar.ts).getTime();
    const match = [...symbolBars]
      .filter((sb) => new Date(sb.ts).getTime() <= tsMs)
      .sort((a, b) => new Date(b.ts).getTime() - new Date(a.ts).getTime())[0];
    return match ? Number(match.close) : null;
  });
  // Fill nulls with last known value
  let last = symbolCloses.find((v) => v !== null) ?? 0;
  const filled = symbolCloses.map((v) => { if (v !== null) last = v; return last; });
  corrMap.set(symbol, {
    c20: rollingCorrelation(mesCloses, filled, 20),
    c60: rollingCorrelation(mesCloses, filled, 60),
  });
}

// Min lookback for fib engine
const MIN_LOOKBACK = 55;
const setupRows: string[] = [];

for (let index = MIN_LOOKBACK; index < ordered1h.length; index++) {
  const candles = ordered1h.slice(0, index + 1).map(toCandle);
  const geometry = buildFibGeometry(candles, /* need bias */ "NEUTRAL"); // placeholder

  // Get the daily bias for this bar
  const tsMs = new Date(ordered1h[index].ts).getTime();
  const dailyIndex = ordered1d.findLastIndex(
    (d) => new Date(d.ts).getTime() <= tsMs
  );
  const dailyFeature = dailyIndex >= 0 ? dailyFeatures[dailyIndex] : null;
  const currentBias = (dailyFeature?.bias ?? "NEUTRAL") as WarbirdBias;

  // Re-run fib geometry with actual bias
  const geoWithBias = buildFibGeometry(candles, currentBias);
  if (!geoWithBias) continue;

  // Forward-scan targets
  const targets = computeTargets(
    ordered1h,
    index,
    geoWithBias.entry,
    geoWithBias.stopLoss,
    geoWithBias.tp1,
    geoWithBias.tp2,
    geoWithBias.direction,
  );

  // Only emit rows where setup can resolve (enough future bars)
  if (index + 10 >= ordered1h.length) continue;

  // Build the feature row
  const row = buildFeatureRow({
    index, ordered1h, ordered1d, closes, volumes, ranges, bodyRatios,
    ema21, ema50, ema200, rsi14, returns1h, returns4h, returns1d,
    rollingStd20, rollingStd50, volumeMean5, volumeMean20, rangeMean20,
    dailyFeature, tsMs, geoWithBias, corrMap, crossSymbols,
    fredBySeries, fredState, fredIndex,
    calendarRows, newsRows, gprRows, trumpRows, setups,
    targets,
  });

  setupRows.push(row);
}
```

**Step 6: Update the header to remove runner columns and add new fib + corr + target columns**

Remove from header:
- `runner_eligible_recent_20`
- `target_price_1h`, `target_price_4h`, `target_mae_1h`, `target_mae_4h`, `target_mfe_1h`, `target_mfe_4h`

Add to header:
- `fib_level`, `fib_quality`, `fib_confluence_score` (from geometry)
- `measured_move_present`, `measured_move_quality`
- `atr_1h`
- `corr_{symbol}_20`, `corr_{symbol}_60` for each symbol
- `reached_tp1`, `reached_tp2`, `setup_stopped`, `max_favorable_excursion`, `max_adverse_excursion`

**Step 7: Update the output path default**

```typescript
const outputPath = ... : "data/warbird-dataset.csv";
```

Create `data/` directory if needed: `mkdir -p data`

**Step 8: Test with a small run**

```bash
npx ts-node -r tsconfig-paths/register scripts/warbird/build-warbird-dataset.ts --output data/warbird-dataset.csv
```

Monitor row count and CSV structure. Expected: hundreds to thousands of setup rows.

**Step 9: Inspect output**

```bash
head -2 data/warbird-dataset.csv
wc -l data/warbird-dataset.csv
```

Check that 5 target columns are present and binary targets are 0 or 1.

**Step 10: Commit**

```bash
git add scripts/warbird/build-warbird-dataset.ts
git commit -m "feat: rewrite dataset builder for fib-setup rows and 5 fib-relative targets"
```

---

## Task 10: Build TE Calendar Scraper — `app/api/cron/econ-calendar/route.ts`

**Files:**
- Modify: `app/api/cron/econ-calendar/route.ts`

The current route uses FRED releases (no importance, no actual/forecast). Replace with a Trading Economics scraper.

**Step 1: Write the scraper function**

Trading Economics provides an RSS/JSON endpoint. Without the API key confirmed, use their public calendar page. The scraper targets: `https://tradingeconomics.com/calendar`

```typescript
import { NextResponse } from "next/server";
import { createAdminClient } from "@/lib/supabase/admin";
import { isMarketOpen } from "@/lib/market-hours";

export const maxDuration = 60;

const TE_BASE = "https://tradingeconomics.com";

type TeEvent = {
  ts: string;
  event_name: string;
  country: string;
  importance: number;
  actual: number | null;
  forecast: number | null;
  previous: number | null;
  surprise: number | null;
  source: string;
};

async function scrapeTeCalendar(daysAhead: number = 7): Promise<TeEvent[]> {
  const apiKey = process.env.TRADINGECONOMICS_API_KEY;

  if (apiKey) {
    // Use TE API if key is available
    const url = `https://api.tradingeconomics.com/calendar?c=${apiKey}&country=united states`;
    const resp = await fetch(url, { cache: "no-store" });
    if (!resp.ok) throw new Error(`TE API error: ${resp.status}`);
    const json = await resp.json();
    return parseTeApiResponse(json);
  }

  // Fallback: TE public JSON endpoint (no auth, limited)
  const today = new Date().toISOString().slice(0, 10);
  const future = new Date(Date.now() + daysAhead * 86400000).toISOString().slice(0, 10);
  const url = `${TE_BASE}/calendar`;

  const resp = await fetch(url, {
    headers: {
      "User-Agent": "Mozilla/5.0",
      "Accept": "application/json",
    },
    cache: "no-store",
  });
  if (!resp.ok) throw new Error(`TE scrape failed: ${resp.status}`);

  // TE returns HTML; parse embedded JSON or use structured data
  const text = await resp.text();
  const match = text.match(/window\.__INITIAL_STATE__\s*=\s*({.+?});/s);
  if (!match) return [];

  const state = JSON.parse(match[1]);
  const events = state?.calendar?.events ?? [];
  return events.map(parseTeEvent).filter(Boolean) as TeEvent[];
}

function parseTeApiResponse(json: unknown[]): TeEvent[] {
  return json.map((item: Record<string, unknown>) => {
    const actual = item.Actual !== "" ? parseFloat(item.Actual as string) : null;
    const forecast = item.Forecast !== "" ? parseFloat(item.Forecast as string) : null;
    const surprise = actual !== null && forecast !== null ? actual - forecast : null;
    return {
      ts: String(item.Date),
      event_name: String(item.Event),
      country: String(item.Country),
      importance: item.Importance === "High" ? 3 : item.Importance === "Medium" ? 2 : 1,
      actual,
      forecast,
      previous: item.Previous !== "" ? parseFloat(item.Previous as string) : null,
      surprise,
      source: "trading_economics",
    };
  });
}

function parseTeEvent(item: Record<string, unknown>): TeEvent | null {
  if (!item.date || !item.name) return null;
  const actual = item.actual != null ? Number(item.actual) : null;
  const forecast = item.forecast != null ? Number(item.forecast) : null;
  const surprise = actual !== null && forecast !== null ? actual - forecast : null;
  return {
    ts: String(item.date),
    event_name: String(item.name),
    country: String(item.country ?? "US"),
    importance: Number(item.importance ?? 1),
    actual,
    forecast,
    previous: item.previous != null ? Number(item.previous) : null,
    surprise,
    source: "trading_economics",
  };
}

export async function GET(request: Request) {
  const cronSecret = process.env.CRON_SECRET;
  if (cronSecret) {
    const auth = request.headers.get("authorization");
    if (auth !== `Bearer ${cronSecret}`) {
      return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
    }
  }

  const startTime = Date.now();
  const supabase = createAdminClient();
  const url = new URL(request.url);
  const force = url.searchParams.get("force") === "1";

  if (!force && !isMarketOpen()) {
    return NextResponse.json({ skipped: true, reason: "market_closed" });
  }

  try {
    const events = await scrapeTeCalendar(14);

    // Filter: US events (all) + major CB events importance >= 2
    const filtered = events.filter(
      (e) => e.country.toLowerCase().includes("united states") ||
             (e.importance >= 2 && ["eurozone", "japan", "united kingdom", "china", "australia"].some(
               (c) => e.country.toLowerCase().includes(c)
             ))
    );

    if (filtered.length > 0) {
      await supabase.from("econ_calendar").upsert(filtered, { onConflict: "ts,event_name" });
    }

    await supabase.from("job_log").insert({
      job_name: "econ-calendar",
      status: "SUCCESS",
      rows_affected: filtered.length,
      duration_ms: Date.now() - startTime,
    });

    return NextResponse.json({ success: true, events: filtered.length, duration_ms: Date.now() - startTime });
  } catch (error) {
    const message = error instanceof Error ? error.message : "Internal error";
    await supabase.from("job_log").insert({
      job_name: "econ-calendar",
      status: "FAILED",
      error_message: message,
      duration_ms: Date.now() - startTime,
    }).catch(() => {});
    return NextResponse.json({ error: message }, { status: 500 });
  }
}
```

**Step 2: Verify build**

```bash
npm run build 2>&1 | tail -20
```

**Step 3: Commit**

```bash
git add app/api/cron/econ-calendar/route.ts
git commit -m "feat: replace econ-calendar cron with TE scraper (importance + actual/forecast/surprise)"
```

---

## Task 11: Create Google News RSS Scraper — `app/api/cron/google-news/route.ts`

**Files:**
- Create: `app/api/cron/google-news/route.ts`

**Step 1: Write the route**

```typescript
import { NextResponse } from "next/server";
import { createAdminClient } from "@/lib/supabase/admin";

export const maxDuration = 60;

const SEGMENTS = {
  fed_policy: [
    `"Federal Reserve" interest rate decision`,
    `Jerome Powell speech testimony`,
    `FOMC minutes statement`,
  ],
  inflation_economy: [
    `CPI inflation report surprise`,
    `nonfarm payrolls jobs report`,
    `GDP recession contraction`,
  ],
  geopolitical_war: [
    `Ukraine Russia war escalation`,
    `Middle East oil supply military`,
    `trade war tariffs sanctions`,
  ],
  policy_trump: [
    `Trump tariff executive order markets`,
    `Treasury deficit debt ceiling`,
    `DOGE federal spending cuts`,
  ],
  market_structure: [
    `S&P 500 crash selloff correction`,
    `VIX volatility spike fear`,
    `bank failure contagion systemic`,
  ],
  earnings_tech: [
    `NVIDIA Apple Microsoft Meta earnings`,
    `semiconductor AI chip demand`,
  ],
} as const;

type Segment = keyof typeof SEGMENTS;

function googleNewsUrl(query: string): string {
  return `https://news.google.com/rss/search?q=${encodeURIComponent(query)}&hl=en-US&gl=US&ceid=US:en`;
}

async function fetchSegmentArticles(segment: Segment): Promise<Array<{
  ts: string;
  title: string;
  url: string;
  source: string;
  segment: string;
  sentiment_score: number;
}>> {
  const keywords = SEGMENTS[segment];
  const articles: Array<{ts: string; title: string; url: string; source: string; segment: string; sentiment_score: number}> = [];

  for (const keyword of keywords) {
    const rssUrl = googleNewsUrl(keyword);
    try {
      const resp = await fetch(rssUrl, {
        headers: { "User-Agent": "Mozilla/5.0" },
        signal: AbortSignal.timeout(10000),
      });
      if (!resp.ok) continue;
      const xml = await resp.text();

      // Parse RSS items
      const items = xml.match(/<item>[\s\S]*?<\/item>/g) ?? [];
      for (const item of items.slice(0, 5)) {
        const title = item.match(/<title><!\[CDATA\[(.*?)\]\]><\/title>/)?.[1]
          ?? item.match(/<title>(.*?)<\/title>/)?.[1] ?? "";
        const link = item.match(/<link>(.*?)<\/link>/)?.[1] ?? "";
        const pubDate = item.match(/<pubDate>(.*?)<\/pubDate>/)?.[1] ?? "";
        const source = item.match(/<source[^>]*>(.*?)<\/source>/)?.[1] ?? "";

        if (!title || !pubDate) continue;

        const ts = new Date(pubDate).toISOString();
        // Naive sentiment: financial keyword matching
        const lower = title.toLowerCase();
        const bullish = ["surge", "gain", "rally", "rise", "recovery", "beat", "strong"].filter(w => lower.includes(w)).length;
        const bearish = ["crash", "fall", "plunge", "fear", "recession", "weak", "miss", "collapse"].filter(w => lower.includes(w)).length;
        const sentiment_score = bullish > bearish ? 0.5 + bullish * 0.1 :
                                bearish > bullish ? -(0.5 + bearish * 0.1) : 0;

        articles.push({ ts, title: title.slice(0, 500), url: link.slice(0, 1000), source: source.slice(0, 200), segment, sentiment_score });
      }
    } catch {
      // Skip failed keyword fetch
    }
  }

  return articles;
}

export async function GET(request: Request) {
  const cronSecret = process.env.CRON_SECRET;
  if (cronSecret) {
    const auth = request.headers.get("authorization");
    if (auth !== `Bearer ${cronSecret}`) {
      return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
    }
  }

  const startTime = Date.now();
  const supabase = createAdminClient();

  try {
    const segments = Object.keys(SEGMENTS) as Segment[];
    const allArticles = (
      await Promise.all(segments.map(fetchSegmentArticles))
    ).flat();

    if (allArticles.length > 0) {
      await supabase.from("econ_news_1d").upsert(allArticles, { onConflict: "url" });
    }

    // Aggregate sentiment by segment into news_signals
    const today = new Date().toISOString().slice(0, 10) + "T00:00:00Z";
    const sentimentBySegment = new Map<string, number[]>();
    for (const article of allArticles) {
      const scores = sentimentBySegment.get(article.segment) ?? [];
      scores.push(article.sentiment_score);
      sentimentBySegment.set(article.segment, scores);
    }

    for (const [segment, scores] of sentimentBySegment.entries()) {
      const avg = scores.reduce((s, v) => s + v, 0) / scores.length;
      await supabase.from("news_signals").upsert({
        ts: today,
        segment,
        sentiment_score: avg,
        article_count: scores.length,
      }, { onConflict: "ts,segment" });
    }

    await supabase.from("job_log").insert({
      job_name: "google-news",
      status: "SUCCESS",
      rows_affected: allArticles.length,
      duration_ms: Date.now() - startTime,
    });

    return NextResponse.json({ success: true, articles: allArticles.length, duration_ms: Date.now() - startTime });
  } catch (error) {
    const message = error instanceof Error ? error.message : "Internal error";
    await supabase.from("job_log").insert({
      job_name: "google-news",
      status: "FAILED",
      error_message: message,
      duration_ms: Date.now() - startTime,
    }).catch(() => {});
    return NextResponse.json({ error: message }, { status: 500 });
  }
}
```

**Step 2: Add to vercel.json**

Find the `crons` array in `vercel.json` and add:
```json
{ "path": "/api/cron/google-news", "schedule": "0 13 * * 1-5" }
```
(7am Central = 13:00 UTC on weekdays)

**Step 3: Check `econ_news_1d` and `news_signals` schemas match the insert**

From `supabase/migrations/20260315000006_news.sql`, verify columns:
- `econ_news_1d`: needs at minimum `ts, title, url, source, segment, sentiment_score`
- `news_signals`: needs at minimum `ts, segment, sentiment_score`

If columns don't match, adjust the insert to match what exists. Do NOT add columns.

**Step 4: Verify build**

```bash
npm run build 2>&1 | tail -20
```

**Step 5: Commit**

```bash
git add app/api/cron/google-news/route.ts vercel.json
git commit -m "feat: add Google News RSS scraper cron for 6 topic segments"
```

---

## Task 12: Run Dataset Builder and Verify Output

**Step 1: Ensure all data is backfilled**

Spot-check these counts:
```sql
select count(*) from mes_1h where ts >= '2024-01-01';
select count(*) from cross_asset_1h;
select count(*) from econ_vol_1d;
select count(*) from geopolitical_risk_1d;
```

**Step 2: Run the dataset builder**

```bash
npx ts-node -r tsconfig-paths/register scripts/warbird/build-warbird-dataset.ts --output data/warbird-dataset.csv
```

**Step 3: Inspect the output**

```bash
wc -l data/warbird-dataset.csv
head -1 data/warbird-dataset.csv | tr ',' '\n' | head -30
```

Check:
- Row count: target >500 setup rows (excluding header)
- Headers include: `reached_tp1`, `reached_tp2`, `setup_stopped`, `max_favorable_excursion`, `max_adverse_excursion`
- No `runner_eligible_recent_20` or `target_price_*` columns

**Step 4: Check target distribution**

```bash
python3 -c "
import pandas as pd
df = pd.read_csv('data/warbird-dataset.csv')
print('Rows:', len(df))
for col in ['reached_tp1', 'reached_tp2', 'setup_stopped']:
    print(f'{col}: {df[col].value_counts().to_dict()}')
print('MFE mean:', df['max_favorable_excursion'].mean())
print('MAE mean:', df['max_adverse_excursion'].mean())
"
```

If binary targets are all-0 or all-1, the forward scan logic has a bug. Fix before training.

---

## Task 13: Train the Model

**Step 1: Run training locally (this takes 30-120 minutes per target)**

```bash
python scripts/warbird/train-warbird.py --dataset data/warbird-dataset.csv --output models/warbird_v1
```

Monitor for errors. If a target fails, check:
- Minimum rows (AutoGluon needs at least 100 rows per target with non-null labels)
- Binary targets must have both 0 and 1 labels in training set

**Step 2: Verify the manifest**

```bash
cat models/warbird_v1/manifest.json | python3 -m json.tool | head -50
```

Check that all 5 targets have leaderboard entries with reasonable scores.

---

## Task 14: Update `WARBIRD_CANONICAL.md` and `AGENTS.md`

**Files:**
- Modify: `WARBIRD_CANONICAL.md`
- Modify: `AGENTS.md`

**WARBIRD_CANONICAL.md changes:**
- Remove all references to 15M trigger layer
- Remove runner_eligible, runner_headroom from WarbirdSignal type
- Update target labels section to show 5 fib-relative targets
- Remove `warbird_triggers_15m` from table list references

**AGENTS.md changes:**
- In File Structure section: remove `trigger-15m.ts` from the scripts/warbird/ list
- Update detect-setups cron note from "every 15 min" to "every 5 min"
- Remove any runner references

**Step 1: Edit WARBIRD_CANONICAL.md**

Search for: `trigger-15m`, `runner_eligible`, `runner_headroom`, `warbird_triggers_15m`, `target_price_`, `target_mae_`, `target_mfe_`
Remove or update each reference.

**Step 2: Edit AGENTS.md**

Remove `trigger-15m.ts` from the file structure. Update cadence comment on detect-setups.

**Step 3: Verify build is still clean**

```bash
npm run build 2>&1 | tail -5
```

**Step 4: Commit**

```bash
git add WARBIRD_CANONICAL.md AGENTS.md
git commit -m "docs: align canonical spec and agent rules to 1H-only, no runner, 5-target architecture"
```

---

## Task 15: Update vercel.json Cron Cadence for detect-setups

**Files:**
- Modify: `vercel.json`

**Step 1: Find detect-setups cron entry**

```bash
grep -n "detect-setups" vercel.json
```

**Step 2: Change schedule to every 5 minutes (weekdays, 6am–4pm Central)**

Vercel Cron format. Every 5 minutes during market hours:
```json
{ "path": "/api/cron/detect-setups", "schedule": "*/5 12-21 * * 1-5" }
```
(12:00–21:00 UTC = 6am–3pm Central standard / 7am–4pm CDT)

**Step 3: Commit**

```bash
git add vercel.json
git commit -m "config: update detect-setups cron to 5-minute cadence"
```

---

## Task 16: Build Verification and Deploy

**Step 1: Final build check**

```bash
npm run build
```

Must pass with zero errors.

**Step 2: Deploy to Vercel**

```bash
git push origin main
```

**Step 3: Verify detect-setups cron runs**

After deploy, test manually:
```
GET /api/cron/detect-setups?force=1
Authorization: Bearer {CRON_SECRET}
```

Check `job_log` for a SUCCESS entry. Check `warbird_conviction` for a new row.

**Step 4: Verify the new cron routes appear in Vercel dashboard**

Go to Vercel → Project → Cron Jobs. Confirm `google-news` and updated `detect-setups` cadence are visible.

---

## Dependency Chain (must follow this order)

```
Task 1  (seed.sql)
    ↓
Task 2  (MES backfill)
Task 3  (cross-asset backfill)    ← parallel with Task 2
Task 4  (FRED backfill)           ← after Task 1 applied to DB
Task 5  (GPR backfill)            ← parallel with Task 4
    ↓ (all data ready)
Task 6  (conviction-matrix fix)
Task 7  (detect-setups fix)       ← parallel with Task 6
Task 8  (train-warbird fix)
    ↓
Task 9  (dataset builder rewrite)
    ↓
Task 12 (run builder, verify CSV)
    ↓
Task 13 (train model)
    ↓
Task 10 (TE calendar scraper)     ← parallel with Task 11
Task 11 (Google News scraper)
Task 14 (doc updates)
Task 15 (vercel.json cron timing)
    ↓
Task 16 (build + deploy)
```

Tasks 2/3 can run in parallel. Tasks 4/5 can run in parallel. Tasks 6/7 can run in parallel. Tasks 10/11/14/15 can run in parallel after Task 13.
