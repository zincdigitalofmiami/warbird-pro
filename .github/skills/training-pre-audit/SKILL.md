---
name: training-pre-audit
description: Run BEFORE launching any AutoGluon training run. Verifies warehouse row counts, migration ledger, constraint/trainer consistency, interpreter path, no orphan running rows, and feature zoo expectations match. Catches the bug classes that wasted real compute this project (AUTOGLOON typo, hyperparameters-dict lockout, IID bag leakage, missing venv, stale lineage rows).
---

# Training Pre-Audit

Catches avoidable failures before burning 1-6 hours of compute. Every finding here came from a real failure that cost real time.

## When to use

**Before every training launch.** Skip only for dry-runs of under 60 seconds.

## Checklist — all must pass

### 1. Warehouse state matches last known good

```bash
/opt/homebrew/opt/postgresql@17/bin/psql -d warbird -h 127.0.0.1 -p 5432 -c \
  "SELECT 'snapshots' AS tbl, count(*) FROM ag_fib_snapshots UNION ALL
   SELECT 'interactions', count(*) FROM ag_fib_interactions UNION ALL
   SELECT 'stop_variants', count(*) FROM ag_fib_stop_variants UNION ALL
   SELECT 'outcomes', count(*) FROM ag_fib_outcomes UNION ALL
   SELECT 'ag_training', count(*) FROM ag_training;"
```

`ag_training` must be non-empty and `stop_variants == outcomes == 6 × interactions` (6 stop families per interaction). If counts are off, re-run the pipeline before training.

### 2. No orphan RUNNING rows

```sql
SELECT run_id, started_at FROM ag_training_runs WHERE run_status='RUNNING';
```

Must return zero rows. If not zero, diagnose — a prior run either crashed silently or is still alive. Do NOT launch a new run on top.

### 3. Migration ledger up to date

```sql
SELECT filename, applied_at FROM local_schema_migrations ORDER BY applied_at DESC LIMIT 5;
```

Cross-check against `ls local_warehouse/migrations/*.sql` — every file present must be stamped in the ledger.

### 4. Constraint / code spelling check (AUTOGLOON trap)

`replace_run_metrics` insertion fails silently into a `finally:` rollback when the trainer's `metric_scope` value doesn't match the DB CHECK constraint.

```bash
# What does the constraint enforce?
/opt/homebrew/opt/postgresql@17/bin/psql -d warbird -h 127.0.0.1 -p 5432 -c \
  "SELECT conname, pg_get_constraintdef(oid) FROM pg_constraint
   WHERE conname IN ('ag_training_runs_run_kind_ck','ag_training_run_metrics_metric_scope_ck')"

# What does the trainer write?
grep -n "AUTOGL\|metric_scope\|run_kind" scripts/ag/train_ag_baseline.py
```

Both sides must use the **same** spelling (`AUTOGLUON` / `AUTOGLUON_TABULAR`). If they drift, the metric insert throws `CheckViolation` inside the `finally:` block and psycopg2 rolls back the `SUCCEEDED` upsert — run status stays at `RUNNING` forever.

### 5. Model zoo expectations vs trainer code

Open `scripts/ag/train_ag_baseline.py` around `fit_kwargs["hyperparameters"]`. Read the dict. **If it only contains `"GBM": [...]` that is the ONLY model family that will fit** — `--excluded-model-types ""` does not put other models back in the pool. AutoGluon presets are overridden by an explicit hyperparameters dict.

For a real multi-model comparison, the dict must explicitly list GBM + CAT + XGB + RF + XT + NN_TORCH + FASTAI.

### 6. Python interpreter reality check

```bash
which python3
/usr/local/bin/python3 -c "from autogluon.tabular import TabularPredictor; print('AG OK')"
ls -la .venv-autogluon/bin/python 2>&1  # commonly referenced in handoffs — may not exist
```

`.venv-autogluon` is referenced in several stale handoff notes but does NOT exist in this workspace. The real interpreter is `/usr/local/bin/python3`. Don't trust the handoff.

### 7. OMP guards in place

First 10 lines of `scripts/ag/train_ag_baseline.py` must set:
```python
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("LIGHTGBM_NUM_THREADS", "1")
```
BEFORE any `import` of AutoGluon, LightGBM, PyTorch. Without these, LightGBM deadlocks indefinitely on Apple Silicon.

### 8. Walk-forward / embargo expectations

The trainer's CLI defaults `--num-bag-folds 5 --num-stack-levels 2` are **wrong for time-series and must be overridden on every launch** unless the trainer has been hardened to default to `0 / 0`. AG's internal bag splits are **IID random shuffle** which violates the one-session embargo on MES 15m data. IID neighbors in the same session land in both train and holdout → `valid_set f1_macro ~0.99` → test score collapses to majority-baseline.

**Concrete evidence of the failure mode** — run `agtrain_20260415T015005138333Z` (2026-04-15): `valid_set f1_macro 0.99+` during per-bag-child fitting, aggregate `Validation score = 0.186`, test `f1_macro = 0.140`. The ~0.85 gap between bag-child valid_set and true test is the canonical IID-bag-leakage fingerprint. Every fold's WeightedEnsemble_L2/L3/L4 reported `Ensemble Weights: {'LightGBM_BAG_L1': 1.0}` — stacking added zero value when the data was contaminated.

**Mandatory on every run until the trainer defaults change:**
```bash
--num-bag-folds 0 --num-stack-levels 0
```

If you forget these flags on a time-series run, the run is scientifically useless and you've burned the full training wall time. Re-verify both flags from the command line before launch.

### 9. `ag_training` view four-way join still matches schema

```sql
SELECT column_name FROM information_schema.columns
 WHERE table_name = 'ag_training'
 ORDER BY ordinal_position;
```

Must include `stop_family_id`, `stop_variant_id`, `sl_dist_pts`, `rr_to_tp1`, plus all feature families. Missing → pipeline not rebuilt against migration 016.

### 10. Git status clean of unexpected drift

```bash
git status --short
git diff --stat scripts/ag/ local_warehouse/migrations/
```

If there are uncommitted DDL or trainer edits from a previous session, know what they are before launching. Partially-applied fixes are worse than unfixed bugs.

## Failure modes this skill prevents

| Failure | Cost | Prevented by |
|---------|------|--------------|
| AUTOGLOON constraint rolls back `SUCCEEDED` upsert | 75 min + recovery migration | Check 4 |
| GBM-only run masquerading as "full zoo" | 75 min of non-comparative compute | Check 5 |
| `valid_set 0.99 → test 0.14` IID bag leakage | Entire run scientifically useless | Check 8 |
| LightGBM OMP deadlock | Run hangs indefinitely holding ~400 MB | Check 7 |
| `.venv-autogluon` not found | Launch fails immediately | Check 6 |
| Pipeline not re-run after migration 016 | Wrong schema in training | Check 9 |
| `time_limit=900` with 7-family zoo | NN / FastAI families can't converge, silently early-stop on time | Check 11 |

### 11. Time-limit vs. zoo-size budget math

With the full 7-family zoo (GBM × 2 configs + CAT + XGB + RF × 2 + XT × 2 + NN_TORCH + FASTAI — roughly 11 model fits per fold), AG splits `time_limit` across families. At `--time-limit 900`, that's ~80-100s per fit — tree-based families finish but NN_TORCH and FASTAI time-truncate and contribute noise.

**Budget guidance:**
- GBM-only with `num_bag_folds=0`: `--time-limit 600` fine
- Full zoo with `num_bag_folds=0`: `--time-limit 1800` minimum, `3600` recommended
- If you see `Ran out of time, early stopping on iteration N` in the log for NN families, raise `--time-limit`

Expected wall time per fold for 7-family zoo at `--time-limit 3600`: 30-60 min. Five folds: 2.5-5 h total.

## When the checklist fails

Do NOT self-patch migrations, constraints, or trainer code without explicit user approval. Surface findings, options, and reversibility; wait for go.
