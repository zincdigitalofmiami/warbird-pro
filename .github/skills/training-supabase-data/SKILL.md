---
name: training-supabase-data
description: Read patterns, schema references, and canonical data sources for training. Warbird uses a LOCAL Postgres 17 warehouse (warbird, 127.0.0.1:5432) as source-of-truth; cloud Supabase is serving-only. Points to which tables and views are training-safe, which are legacy, and which belong to the serving layer.
---

# Training — Supabase / Warehouse Data

This skill covers data access for training ONLY. For broader Supabase ops (migrations, RLS, Edge Functions, cron), see the existing `supabase-ml-ops` skill.

## Canonical training source: LOCAL warbird Postgres 17

- Host: `127.0.0.1:5432`
- Database: `warbird`
- Client: `/opt/homebrew/opt/postgresql@17/bin/psql`
- Auth: local trust (no password in scripts)
- Migration dir: `local_warehouse/migrations/`
- Ledger: `local_schema_migrations` table
- DSN env var: `WARBIRD_PG_DSN` (default `host=127.0.0.1 port=5432 dbname=warbird`)

**Cloud Supabase (`qhwgrzqjcdtdqppvhhme`) is serving-only.** Training never reads from cloud, never writes to cloud. The local warehouse is source-of-truth per CLAUDE.md.

## The four canonical AG tables + training view

| Object | Role |
|--------|------|
| `ag_fib_snapshots` | Per-bar context: anchor geometry, indicator values, micro-execution state at `ts` |
| `ag_fib_interactions` | Per-interaction row keyed by `(snapshot_ts, fib_level_touched, direction)`. Stop-AGNOSTIC. |
| `ag_fib_stop_variants` | Per-interaction × stop_family_id expansion. Six rows per interaction (one per family). Contains `sl_dist_pts`, `stop_level_price`, `rr_to_tp1`, etc. |
| `ag_fib_outcomes` | Per-stop_variant outcome: `outcome_label`, `highest_tp_hit`, `hit_tp1..5`, `bars_to_tp1`, `mae_pts`, `mfe_pts`. Keyed by `stop_variant_id`. |
| `ag_training` (VIEW) | Four-way join of the above. This is what trainers read. |

### `ag_training` view has ~80 columns

See `scripts/ag/train_ag_baseline.py::LEAKAGE_COLS` for the canonical exclusion list. Feature-admitted columns:
- Fib geometry: `fib_level_touched`, `fib_level_price`, `touch_distance_*`, `archetype`, `fib_range`, `fib_bull`, `anchor_*`, `atr14`
- TP/SL prices: `entry_price`, `tp1..5_price`, `tp1_dist_pts`
- Candle & volume: `open`, `high`, `low`, `close`, `volume`, `body_pct`, `upper_wick_pct`, `lower_wick_pct`, `rvol`
- Indicators: `rsi14`, `ema9/21/50/200`, `ema_stacked_*`, `ema9_dist_pct`, `macd_hist`, `adx`, `energy`, `confluence_quality`
- Micro execution: `ml_exec_*` family (11 columns — timeframe, state, pattern, pocket, impulse, reclaim, orderflow, delta, absorption, zero_print, imbalance counts, target_leg, direction)
- Stop variant: `stop_family_id`, `stop_level_price`, `stop_distance_ticks`, `sl_dist_pts`, `sl_dist_atr`, `rr_to_tp1`
- Direction / target: `direction`, `outcome_label` (the label)

### Context features attached by the trainer

`scripts/ag/train_ag_baseline.py::attach_context_features` joins:
- **FRED daily** (27 series in `curated_regime_v1` profile): CPI, fed funds, DGS*, DFII*, T10Y2Y, T10YIE, DTWEXBGS, VIXCLS, OVXCLS, GVZCLS, NFCI, SP500, SOFR, DFEDTARL, DFEDTARU (the last two may be missing on recent inference windows — pad with NaN)
- **Econ calendar** (`econ_calendar` + `executive_orders` tables) — per-day event counts by category

## Source data tables (NOT for direct training read; they feed the pipeline)

- `mes_15m` (canonical MES 15-minute bars, parent timeframe)
- `mes_1m` (subordinate micro-execution context, 2.2M+ rows as of 2026-04-14)
- `mes_1h`, `mes_4h` (derived / reference timeframes)
- `cross_asset_1h` (NQ, RTY, CL, HG, 6E, 6J — per cross_asset Edge Function)
- `FRED.*` (one table per FRED series per `series_catalog`)
- `econ_calendar`, `executive_orders`

The pipeline at `scripts/ag/build_ag_pipeline.py` reads these and populates the four AG tables. **Do not query them directly from the trainer.**

## Legacy / do-not-use

Per CLAUDE.md:
- `cross_asset_1d` — removed
- Any `*news*` tables — removed
- Any `*options*` tables — removed
- `warbird_setups`, `news_signals`, `trump_effect_1d` — stale; hard-exit in `scripts/build-dataset.py`
- `indicator_snapshots_15m` — designed but not yet built
- Anything under `supabase/functions/detect-setups` or `score-trades` — referenced App Router routes, no active cron

## Join keys on `ag_training` — `stop_variant_id` is the unique row key, NOT `id`

Critical lesson from 2026-04-15: every per-row join against `ag_training` (calibration, SHAP merges, Monte Carlo prediction alignment) MUST use `stop_variant_id`, never `id`.

Verified counts on the live warehouse:
- `ag_training`: 327,942 rows
- Distinct `id`: 54,657 (from `ag_fib_interactions.id`)
- Distinct `stop_variant_id`: 327,942 (from `ag_fib_stop_variants.id`)

`id` repeats 6× across the stop variants of each interaction. Using `id` under `pandas.merge(..., validate="one_to_one")` either raises, silently collapses 6 rows into 1, or cartesian-expands without the `validate` guard.

**Canonical join key table:**

| Joining to… | Use this key |
|---|---|
| Per-row outcomes / predictions / SHAP values | `stop_variant_id` |
| Per-interaction features (direction, fib_level_touched, archetype, anchor_*) | `id` (interaction_id) — but this loses stop-variant differentiation |
| Backfill `archetype` onto SHAP parquet | `stop_variant_id → ag_fib_stop_variants.interaction_id → ag_fib_interactions.archetype` (two-hop join) |

Example archetype backfill query (used in `scripts/ag/run_diagnostic_shap.py`):

```sql
SELECT v.id AS stop_variant_id, i.archetype
FROM ag_fib_stop_variants v
JOIN ag_fib_interactions i ON i.id = v.interaction_id
WHERE v.id = ANY(%s)
```

Parameterize with the list of `stop_variant_id` values. One batch query. `merge(..., on="stop_variant_id", how="left", validate="many_to_one")`.

## Run lineage (migration 014 + 017)

| Table | What it holds |
|-------|----|
| `ag_training_runs` | One row per training run: run_id, status, presets, rows/sessions/features/folds, started_at, completed_at, error_message |
| `ag_training_run_metrics` | Long-form metrics: per-run × target × fold × split × scope × metric_name. Only BASELINE metrics populated pre-completion; AUTOGLUON metrics written at run end |
| `ag_artifacts` | Registered artifact files: type, fold, split, path, size, sha256 |

Tables for SHAP lineage (also migration 014): `ag_shap_feature_summary`, `ag_shap_cohort_summary`, `ag_shap_interaction_summary`, `ag_shap_temporal_stability`, `ag_shap_feature_decisions`, `ag_shap_run_drift`.

## Read patterns

### Cheapest: psql for row counts and smoke checks

```bash
/opt/homebrew/opt/postgresql@17/bin/psql -d warbird -h 127.0.0.1 -p 5432 -c "..."
```

### From Python (match trainer pattern)

```python
import psycopg2
import pandas as pd

dsn = "host=127.0.0.1 port=5432 dbname=warbird"
with psycopg2.connect(dsn) as conn:
    df = pd.read_sql_query("SELECT * FROM ag_training ORDER BY ts", conn)
```

The pandas / psycopg2 combination emits a SQLAlchemy warning — non-fatal, can be ignored.

### Never use an ORM / Prisma

Hard rule in CLAUDE.md. Direct SQL via psycopg2 only.

## Cloud serving — for reference only

Cloud Supabase tables (published / promoted from local):
- `indicator_runtime_*` — live Pine indicator state
- Published model artifacts — curated subset after approval
- Dashboard read models

**Training never reads or writes these.** Promotion is a manual step, post-audit, per Plan v5 Phase 6.

## Related skills

- `supabase-ml-ops` — broader Supabase operations reference
- `training-pre-audit` — warehouse state checks before training
- `training-quant-trading` — time-series discipline for the training data itself
