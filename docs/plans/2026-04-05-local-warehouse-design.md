# Local Training Warehouse Design

**Date:** 2026-04-05  
**Status:** Approved  
**Scope:** Local training data architecture and load pipeline

---

## Architecture

Two Supabase instances only:

**Cloud Supabase** — production. Live MES feed, current cross_asset for dashboard. Nothing else.

**Local Supabase (Docker)** — schema dev and migration testing only. Thin. No training data ever loaded into it. Exists because Supabase CLI requires Docker for the local dev server.

**Satechi drive (`data/`)** — all training data as files. Parquet from Databento batches. Python reads directly. No Postgres dependency for training.

---

## Training Data Layout

```
warbird-pro/data/
  mes_1m.parquet
  mes_15m.parquet
  mes_1h.parquet
  mes_4h.parquet
  mes_1d.parquet
  cross_asset_1h.parquet
  cross_asset_1d.parquet
  econ_activity_1d.parquet
  econ_commodities_1d.parquet
  econ_fx_1d.parquet
  econ_indexes_1d.parquet
  econ_inflation_1d.parquet
  econ_labor_1d.parquet
  econ_money_1d.parquet
  econ_rates_1d.parquet
  econ_vol_1d.parquet
  econ_yields_1d.parquet
  econ_calendar.parquet
  geopolitical_risk_1d.parquet
  executive_orders_1d.parquet
```

---

## Current Gaps (verified 2026-04-05)

| Table | State | Source |
|-------|-------|--------|
| `cross_asset_1h` | 1 month only (needs 6yr) | `GLBX-20260405-EJTKT7UUVK` batch zip |
| `mes_15m` | Stale 3.5 weeks | Derive from `mes_1m` (current to Apr 3) |
| `mes_1d` | Stale 4 weeks | Derive from `mes_1h` |
| `mes_4h` | Empty | Derive from `mes_1h` |
| `econ_calendar` | 0 rows | `scripts/backfill-econ-calendar.py` |
| `geopolitical_risk_1d` | 0 rows | Manual monthly backfill |
| `executive_orders_1d` | 0 rows | `scripts/backfill-exec-orders` (TBD) |

MES source data is good: `mes_1m` and `mes_1h` both 2020-01-01 → 2026-04-03.

---

## Loader Pipeline

### Step 1 — Fix `scripts/load-local-databento.py`

Bug: intermarket section uses `df.iloc[0]` to get the parent symbol per file. Each batch file contains ALL intermarket symbols, so all data gets grouped under the first symbol only.

Fix: group by actual symbol per row before aggregating.

### Step 2 — Output to `data/` as parquet

Change loader output from Postgres upsert → `data/<table>.parquet`. Python training scripts read parquet directly. No Docker dependency for training.

### Step 3 — Derive rollup tables

- `mes_15m` — resample from `mes_1m` parquet
- `mes_4h` — resample from `mes_1h` parquet  
- `mes_1d` — resample from `mes_1h` parquet

### Step 4 — Backfill empty econ tables

- `econ_calendar` — run `scripts/backfill-econ-calendar.py` against local Supabase, export to parquet
- `geopolitical_risk_1d` — manual monthly pull, export to parquet
- `executive_orders_1d` — backfill script TBD

---

## Batch Files (on drive, unloaded)

```
warehouse/batch_jobs/GLBX-20260405-75PD3JMW9Q/  → MES 1m (full history)
warehouse/batch_jobs/GLBX-20260405-AD9XQKUFAA/  → MES 1h (full history)
warehouse/batch_jobs/GLBX-20260405-EJTKT7UUVK/  → Intermarket 1m (NQ/RTY/CL/HG/6E/6J, full history)
```

---

## Not In Scope

- Phase 4 AG training scripts (`scripts/ag/*.py`) — blocked per plan until phases 5-6 complete
- `cross_asset_15m` backfill — SHAP-gated
- Live ingestion changes — cloud only, not affected
