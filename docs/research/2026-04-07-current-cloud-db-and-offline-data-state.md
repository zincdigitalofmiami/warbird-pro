# Warbird Current Cloud DB And Offline Data State

**Date:** 2026-04-07  
**Status:** Directly verified current-state audit.  
**Purpose:** Record the actual current storage boundary and the actual current data state before handing architecture work to PowerDrill.

---

## 1. Boundary Lock

This audit replaces the old "local Supabase via Docker" shorthand with the verified current boundary:

- **Cloud runtime DB truth:** Supabase cloud Postgres, verified directly via `POSTGRES_URL_NON_POOLING`.
- **Offline local data truth:** the external-drive working copy at `/Volumes/Satechi Hub/warbird-pro/data/`.
- **Public GitHub is not the offline data surface.** Most heavy local datasets are intentionally ignored from Git and are not part of the public repo.
- **Local Docker Supabase is not part of the active local data contract.**

Direct evidence for the retired Docker-local assumption:

- `lsof -nP -iTCP:54322 -sTCP:LISTEN` returned no listener.
- `psql postgresql://zincdigital@localhost:54322/postgres ...` returned `Connection refused`.
- `docker ps` returned Docker daemon/socket unavailable.

Implication:

- Do not describe the current local side as "local Supabase."
- Do not assume PowerDrill can discover the offline training data from GitHub.
- When discussing local storage, say **offline external-drive data/warehouse**.

---

## 2. Public vs Offline Surfaces

### 2.1 Public GitHub surface

Public GitHub contains the code, migrations, plans, and handoff docs.

Within `data/`, only these files are currently tracked:

- `data/gpr_web.xls`
- `data/warbird-dataset.csv`

### 2.2 Offline external-drive surface

The heavyweight local datasets are present in the working copy on the external drive and are intentionally ignored from GitHub by `.gitignore`.

Verified ignored patterns:

- `data/local-db-backups/`
- `data/*.parquet`
- `data/*.zip`
- `data/MES*/`
- `data/Intermarket*/`
- `data/cross_asset*/`

Implication:

- Public repo docs explain the system.
- Offline drive data is the actual local research/training substrate.

---

## 3. Cloud DB Current State

Verification method:

- Connected directly to cloud Postgres with `psql` and `POSTGRES_URL_NON_POOLING`.
- Queried `supabase_migrations.schema_migrations`, `information_schema`, and exact `count(*)` queries against live tables/views.

### 3.1 Migration ledger

- Latest applied migration in cloud: `20260401000048`

### 3.2 Public schema inventory

Verified live cloud inventory:

- `39` public tables
- `8` public views

#### Runtime market and context tables

- `cross_asset_15m`
- `cross_asset_1d`
- `cross_asset_1h`
- `econ_activity_1d`
- `econ_calendar`
- `econ_commodities_1d`
- `econ_fx_1d`
- `econ_indexes_1d`
- `econ_inflation_1d`
- `econ_labor_1d`
- `econ_money_1d`
- `econ_rates_1d`
- `econ_vol_1d`
- `econ_yields_1d`
- `executive_orders_1d`
- `geopolitical_risk_1d`
- `job_log`
- `mes_15m`
- `mes_1d`
- `mes_1h`
- `mes_1m`
- `mes_4h`
- `series_catalog`
- `symbol_role_members`
- `symbol_roles`
- `symbols`

#### Canonical Warbird lifecycle tables

- `warbird_candidate_outcomes_15m`
- `warbird_fib_candidates_15m`
- `warbird_fib_engine_snapshots_15m`
- `warbird_packet_activations`
- `warbird_packet_feature_importance`
- `warbird_packet_metrics`
- `warbird_packet_recommendations`
- `warbird_packet_setting_hypotheses`
- `warbird_packets`
- `warbird_signal_events`
- `warbird_signals_15m`
- `warbird_training_run_metrics`
- `warbird_training_runs`

#### Dashboard/admin views

- `warbird_active_packet_feature_importance_v`
- `warbird_active_packet_metrics_v`
- `warbird_active_packet_recommendations_v`
- `warbird_active_packet_setting_hypotheses_v`
- `warbird_active_signals_v`
- `warbird_active_training_run_metrics_v`
- `warbird_admin_candidate_rows_v`
- `warbird_candidate_stats_by_bucket_v`

### 3.3 Exact cloud row counts

#### Runtime market and context tables

| Table | Exact rows |
| --- | ---: |
| `mes_1m` | 793594 |
| `mes_15m` | 52925 |
| `mes_1h` | 183 |
| `mes_4h` | 31 |
| `mes_1d` | 25 |
| `cross_asset_15m` | 0 |
| `cross_asset_1h` | 168137 |
| `cross_asset_1d` | 66 |
| `econ_calendar` | 10550 |
| `econ_activity_1d` | 1687 |
| `econ_commodities_1d` | 190 |
| `econ_fx_1d` | 282 |
| `econ_indexes_1d` | 202 |
| `econ_inflation_1d` | 1588 |
| `econ_labor_1d` | 704 |
| `econ_money_1d` | 201 |
| `econ_rates_1d` | 298 |
| `econ_vol_1d` | 195 |
| `econ_yields_1d` | 1261 |
| `executive_orders_1d` | 0 |
| `geopolitical_risk_1d` | 0 |
| `job_log` | 18587 |
| `series_catalog` | 86 |
| `symbols` | 61 |
| `symbol_roles` | 7 |
| `symbol_role_members` | 35 |

#### Canonical Warbird lifecycle tables

Every canonical Warbird lifecycle table exists in cloud, but all are currently empty:

| Table | Exact rows |
| --- | ---: |
| `warbird_fib_engine_snapshots_15m` | 0 |
| `warbird_fib_candidates_15m` | 0 |
| `warbird_candidate_outcomes_15m` | 0 |
| `warbird_signals_15m` | 0 |
| `warbird_signal_events` | 0 |
| `warbird_training_runs` | 0 |
| `warbird_training_run_metrics` | 0 |
| `warbird_packets` | 0 |
| `warbird_packet_activations` | 0 |
| `warbird_packet_metrics` | 0 |
| `warbird_packet_feature_importance` | 0 |
| `warbird_packet_setting_hypotheses` | 0 |
| `warbird_packet_recommendations` | 0 |

#### Dashboard/admin views

Every canonical dashboard/admin view exists in cloud, but all are currently empty:

| View | Exact rows |
| --- | ---: |
| `warbird_active_signals_v` | 0 |
| `warbird_admin_candidate_rows_v` | 0 |
| `warbird_candidate_stats_by_bucket_v` | 0 |
| `warbird_active_packet_metrics_v` | 0 |
| `warbird_active_training_run_metrics_v` | 0 |
| `warbird_active_packet_feature_importance_v` | 0 |
| `warbird_active_packet_recommendations_v` | 0 |
| `warbird_active_packet_setting_hypotheses_v` | 0 |

### 3.4 Cloud time coverage

| Table | Exact rows | Min timestamp | Max timestamp |
| --- | ---: | --- | --- |
| `mes_1m` | 793594 | `2024-01-01 23:00:00+00` | `2026-04-07 01:32:00+00` |
| `mes_15m` | 52925 | `2024-01-01 23:00:00+00` | `2026-04-07 01:30:00+00` |
| `mes_1h` | 183 | `2026-03-25 17:00:00+00` | `2026-04-06 23:00:00+00` |
| `mes_4h` | 31 | `2026-03-30 16:00:00+00` | `2026-04-06 20:00:00+00` |
| `mes_1d` | 25 | `2026-03-03 00:00:00+00` | `2026-04-06 00:00:00+00` |
| `cross_asset_15m` | 0 | `NULL` | `NULL` |
| `cross_asset_1h` | 168137 | `2018-01-01 23:00:00+00` | `2026-04-06 23:00:00+00` |
| `cross_asset_1d` | 66 | `2026-04-01 00:00:00+00` | `2026-04-06 00:00:00+00` |
| `econ_calendar` | 10550 | `2024-02-20 00:00:00+00` | `2026-03-30 00:00:00+00` |
| `executive_orders_1d` | 0 | `NULL` | `NULL` |
| `geopolitical_risk_1d` | 0 | `NULL` | `NULL` |
| `econ_activity_1d` | 1687 | `1926-06-30 00:00:00+00` | `2026-02-01 00:00:00+00` |
| `econ_commodities_1d` | 190 | `2025-11-12 00:00:00+00` | `2026-04-01 00:00:00+00` |
| `econ_fx_1d` | 282 | `2025-11-10 00:00:00+00` | `2026-03-27 00:00:00+00` |
| `econ_indexes_1d` | 202 | `2025-11-17 00:00:00+00` | `2026-04-02 00:00:00+00` |
| `econ_inflation_1d` | 1588 | `2001-01-01 00:00:00+00` | `2026-04-03 00:00:00+00` |
| `econ_labor_1d` | 704 | `2017-11-01 00:00:00+00` | `2026-03-28 00:00:00+00` |
| `econ_money_1d` | 201 | `2017-11-01 00:00:00+00` | `2026-04-01 00:00:00+00` |
| `econ_rates_1d` | 298 | `2017-12-01 00:00:00+00` | `2026-04-02 00:00:00+00` |
| `econ_vol_1d` | 195 | `2025-11-12 00:00:00+00` | `2026-04-01 00:00:00+00` |
| `econ_yields_1d` | 1261 | `2025-11-12 00:00:00+00` | `2026-04-03 00:00:00+00` |

### 3.5 Cloud operational notes

Verified symbol registry state:

- `symbols`: `61` total rows
- active symbols: `35`
- `DATABENTO` symbols: `58`
- active `DATABENTO` symbols: `32`

Verified job-log state:

- `mes-1m-pull`: `13318` runs, latest status `SUCCESS`, latest start `2026-04-07 01:32:08.927475+00`
- `cross-asset`: `1227` runs, latest status `SKIPPED`, latest start `2026-04-07 01:08:28.415548+00`
- `mes-hourly`: `218` runs, latest status `SUCCESS`, latest start `2026-04-07 01:05:14.686966+00`
- `fred-activity`: latest status `FAILED`, latest start `2026-04-06 03:00:20.507439+00`
- `econ-calendar`: latest status `FAILED`, latest start `2026-03-26 15:00:40.401657+00`
- legacy writer-era job names are still present in `job_log` history (`detect-setups`, `score-trades`, `news`, `forecast-check`, `measured-moves`), but the canonical Warbird writer tables remain empty

Operational conclusion:

- cloud runtime ingestion is active
- canonical runtime-to-ML lifecycle tables are provisioned but not yet populated
- the current missing piece is the canonical writer path, not the canonical schema

---

## 4. Offline External-Drive Data State

Verification method:

- direct filesystem inspection under `/Volumes/Satechi Hub/warbird-pro/data/`
- `du -sh`, `find`, `git ls-files`, `.gitignore`, `duckdb`, `wc -l`, and direct metadata reads from Databento export folders

### 4.1 Root size and composition

- total `data/` size: `301M`

Largest verified entries:

| Path | Size | Git status | Notes |
| --- | ---: | --- | --- |
| `data/Intermarket 1h data GLBX-20260405-L6EHD7H3NJ/` | `80M` | ignored | extracted Databento 1h intermarket batch |
| `data/Intermarket 1h data GLBX-20260405-L6EHD7H3NJ.zip` | `70M` | ignored | zipped Databento 1h intermarket batch |
| `data/MES 1m GLBX-20260405-75PD3JMW9Q/` | `44M` | ignored | extracted Databento 1m MES batch |
| `data/MES 1m GLBX-20260405-75PD3JMW9Q.zip` | `44M` | ignored | zipped Databento 1m MES batch |
| `data/mes_1m.parquet` | `43M` | ignored | offline MES 1m parquet |
| `data/cross_asset_1h.parquet` | `4.0M` | ignored | offline cross-asset 1h parquet |
| `data/gpr_web.xls` | `3.1M` | tracked | tracked source spreadsheet |
| `data/mes_15m.parquet` | `3.0M` | ignored | offline MES 15m parquet |
| `data/MES 1h GLBX-20260405-AD9XQKUFAA/` | `2.3M` | ignored | extracted Databento 1h MES batch |
| `data/MES 1h GLBX-20260405-AD9XQKUFAA 2/` | `2.3M` | ignored | second extracted copy present |
| `data/MES 1h GLBX-20260405-AD9XQKUFAA.zip` | `2.2M` | ignored | zipped Databento 1h MES batch |
| `data/mes_1h.parquet` | `1.7M` | ignored | offline MES 1h parquet |
| `data/warbird-dataset.csv` | `1.3M` | tracked | tracked legacy bridge dataset |
| `data/mes_4h.parquet` | `328K` | ignored | offline MES 4h parquet |
| `data/mes_1d.parquet` | `72K` | ignored | offline MES 1d parquet |

### 4.2 Offline parquet inventory

| File | Exact rows | Min timestamp | Max timestamp |
| --- | ---: | --- | --- |
| `data/mes_1m.parquet` | 3237058 | `2020-01-01 17:00:00-06` | `2026-04-03 08:14:00-05` |
| `data/mes_15m.parquet` | 147320 | `2020-01-01 17:00:00-06` | `2026-04-03 08:00:00-05` |
| `data/mes_1h.parquet` | 105130 | `2020-01-01 17:00:00-06` | `2026-04-03 08:00:00-05` |
| `data/mes_4h.parquet` | 10009 | `2020-01-01 14:00:00-06` | `2026-04-03 07:00:00-05` |
| `data/mes_1d.parquet` | 1948 | `2019-12-31 18:00:00-06` | `2026-04-02 19:00:00-05` |
| `data/cross_asset_1h.parquet` | 221904 | `2020-01-01 17:00:00-06` | `2026-04-03 10:00:00-05` |

Local coverage conclusion:

- offline parquet coverage is materially deeper than current cloud runtime coverage
- offline local data currently reaches back to the 2020 training floor
- cloud runtime and offline training data must be treated as separate stores with separate purposes

### 4.3 Offline CSV and spreadsheet artifacts

- `data/warbird-dataset.csv`
  - tracked in Git
  - `760` lines total
  - header confirms it is a legacy bridge dataset with mixed MES, FRED, cross-asset, GPR, and old target columns such as `reached_tp1`, `reached_tp2`, `hit_sl_first`, and `hit_pt1_first`
- `data/gpr_web.xls`
  - tracked in Git
  - present as a source spreadsheet artifact

Interpretation:

- these tracked files are reference/bridge artifacts
- they are not the authoritative statement of the current offline warehouse design

### 4.4 Offline Databento batch exports

#### MES 1m batch export

- root: `data/MES 1m GLBX-20260405-75PD3JMW9Q/`
- files present: `79`
- dataset: `GLBX.MDP3`
- schema: `ohlcv-1m`
- requested symbols: `1`
- symbol list in metadata: `MES.FUT`
- query start: `2020-01-01T00:00:00Z`
- query end: `2026-04-04T00:00:00Z`
- monthly split files are present from `2020-01` through `2026-04-04`

#### MES 1h batch export

- root: `data/MES 1h GLBX-20260405-AD9XQKUFAA/`
- files present: `79`
- dataset: `GLBX.MDP3`
- schema: `ohlcv-1h`
- requested symbols: `1`
- query start: `2020-01-01T00:00:00Z`
- query end: `2026-04-04T00:00:00Z`

#### Intermarket 1h batch export

- root: `data/Intermarket 1h data GLBX-20260405-L6EHD7H3NJ/`
- files present: `4526`
- dataset: `GLBX.MDP3`
- schema: `ohlcv-1h`
- requested symbols in metadata: `6`
- query start: `2020-01-01T00:00:00Z`
- query end: `2026-04-04T00:00:00Z`

### 4.5 Local backup artifacts

Verified files under `data/local-db-backups/`:

- `data/local-db-backups/options-2026-04-03/symbol_role_members_options_backup.csv`
- `data/local-db-backups/options-2026-04-03/symbols_options_backup.csv`

---

## 5. Current Contract Implications

### 5.1 What is true right now

- cloud Supabase is the live runtime DB truth
- offline external-drive files are the local research/training truth
- the old Docker-local Supabase path is not active and must not be described as the local store
- the canonical Warbird lifecycle schema exists in cloud but is still unpopulated
- cloud runtime ingestion tables are populated and active

### 5.2 What PowerDrill must not assume

- do not assume offline training data is available from GitHub
- do not assume local data lives in a running local Supabase
- do not assume daily/hourly cron pulls are wanted for training-only data

### 5.3 Binding training-data rule

Training-only data is **not** a cron-refresh surface.

The intended rule is:

- batch pulls on AG retrain day
- batch rebuilds on explicit research refresh
- recurring cloud ingestion only when the data is required for frontend, live indicator/runtime, operator surfaces, or production monitoring

---

## 6. Short Conclusion

The current architecture is now clear:

- **Public code/docs:** GitHub repo
- **Cloud runtime truth:** Supabase cloud Postgres
- **Offline local truth:** external-drive working-copy data under `/Volumes/Satechi Hub/warbird-pro/data/`
- **Not active / not trusted as local truth:** Docker-local Supabase

The repo already has the cloud schema and ingestion layer. The missing implementation path is the canonical writer and the offline AG training pipeline that reads from the correct offline store instead of inventing a Docker-local DB assumption.
