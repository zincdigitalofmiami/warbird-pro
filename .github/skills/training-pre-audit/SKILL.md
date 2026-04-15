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

### 5. Model zoo expectations vs trainer code (automated)

Run the canonical-zoo guard. It must exit 0:

```bash
./scripts/guards/check-canonical-zoo.sh
```

The guard verifies that `scripts/ag/train_ag_baseline.py` contains:
- An active `_assert_canonical_zoo()` module-level call (the import-time drift guard)
- All 7 required family keys in `CANONICAL_ZOO`: `GBM`, `CAT`, `XGB`, `RF`, `XT`, `NN_TORCH`, `FASTAI`

The commit-msg hook at `.githooks/commit-msg` runs the same guard at commit time; it can only be bypassed with a `ZOO_CHANGE_APPROVED:` token in the commit message. If you find yourself tempted to bypass, stop — full zoo is mandatory on this project. **GBM-only runs do not exist here and have silently masqueraded as "full zoo" before, wasting wall time.**

`--excluded-model-types ""` does NOT add families back to a subset dict. AutoGluon presets are overridden by any explicit `hyperparameters` dict, so the dict itself IS the zoo policy.

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

### 12. Data floor — ag_training row count not truncated

```bash
/opt/homebrew/opt/postgresql@17/bin/psql -d warbird -h 127.0.0.1 -p 5432 -At -c \
  "SELECT count(*) FROM ag_training;"
```

Result must be at least **`EXPECTED_AG_TRAINING_ROWS_FLOOR` = 327,000** (pinned 2026-04-15 after migration 016; the true count was 327,942). Below that, the trainer itself refuses to fit — `load_base_training` raises `SystemExit` with a clear message. Raise the floor in `scripts/ag/train_ag_baseline.py` whenever the pipeline legitimately grows the row count; never lower it silently.

This catches the "pipeline half-loaded" failure mode where filters or joins trim the dataset and the training silently runs on the truncated surface.

### 13. Fold class-coverage preview (added 2026-04-15)

Before training, run the walk-forward splitter offline against the current `ag_training` + embargo + min_train_sessions settings. For each of the 5 planned folds, confirm:

- `val_class_count == test_class_count` for every fold
- Rare classes (TP4_HIT, TP5_HIT) are present in BOTH val and test slices of every fold

If any fold's val slice misses a class the test slice has, the model's early-stopping and family-weighter decisions for that fold will be based on partial class signal — the final per-class SHAP/MC for the missing class is then unreliable for that fold.

Implementation reference: import `build_walk_forward_folds` from `scripts/ag/train_ag_baseline.py`, call it on the loaded `ag_training`, inspect each fold's class distribution. Must complete in < 10 seconds; if it fails, either nudge embargo, expand min_train_sessions, or flag the run as probe-only with reduced SHAP/MC trust.

Evidence: `agtrain_20260415T165437712806Z` fold_03 had `val_class_count=5, test_class_count=6` (missing `TP4_HIT` in validation). Training did not detect this until fold_summary.json was written AFTER the fold completed. The preview catches it 30 minutes earlier.

### 14. Non-bag SHAP explainer branch coverage (added 2026-04-15)

Static grep of `scripts/ag/run_diagnostic_shap.py` for any `isinstance(model, BaggedEnsembleModel)` branch. Every such branch must have an `else:` arm that handles the non-bag case. If the non-bag arm is missing or only `raise NotImplementedError`, the SHAP run WILL fail on the first full-zoo `num_bag_folds=0` run.

Quick check:
```bash
grep -n "BaggedEnsembleModel\|isinstance.*bagg\|\.child_predictor_names" scripts/ag/run_diagnostic_shap.py
```

For every hit, read the surrounding control flow. If the branch assumes bagged-only and there's no else, flag it.

Evidence: SHAP code assumed bagged child models only until `agtrain_20260415T165437712806Z`. The non-bag branch was latent and only got exercised when the trainer finally ran `num_bag_folds=0`. The patch is at `scripts/ag/run_diagnostic_shap.py:267` but is currently uncommitted — the pre-audit must detect that either (a) the fix is committed, or (b) a fresh SHAP run will hit the same latent branch.

### 15. Hardcoded caveat sweep (added 2026-04-15)

SHAP and MC summary.md text MUST be runtime-conditional on actual run metadata. Pre-audit must grep for caveat strings that are unconditionally appended:

```bash
# These strings must appear ONLY inside `if run_metadata["num_bag_folds"] > 0:` or equivalent
grep -n "IID bag leakage\|valid_set f1_macro ~0.99\|GBM-only\|only LightGBM\|bag-fold leakage" \
  scripts/ag/run_diagnostic_shap.py scripts/ag/monte_carlo_run.py
```

For every hit, trace upwards — is the caveat wrapped in a runtime condition? If not, it's hardcoded and will emit on every run regardless of actual state. That is a report-integrity violation.

Known offenders (as of 2026-04-15, uncommitted fix pending):
- `scripts/ag/monte_carlo_run.py:1209` — stale bag-leakage / GBM-only note hardcoded
- `scripts/ag/run_diagnostic_shap.py:1390` — same

If these are still present, the next training run's summary.md will contain contradictory caveats against a clean run. Pre-audit MUST fail the check and demand the runtime-conditional rewrite before launching.

## Failure modes — updated

| Failure | Cost | Prevented by |
|---------|------|--------------|
| CANONICAL_ZOO drift (family removed) | Import-time `SystemExit` + commit-msg hook | Check 5 + module-level `_assert_canonical_zoo()` |
| Data-floor trip (ag_training truncated) | Run refuses to start | Check 12 + trainer `EXPECTED_AG_TRAINING_ROWS_FLOOR` |
| Fold val slice missing a test class | Unreliable per-class SHAP/MC for that fold/class | Check 13 (class-coverage preview) |
| Non-bag SHAP branch latent → SHAP crash on clean `num_bag_folds=0` run | Entire SHAP wasted, must re-run | Check 14 (branch coverage grep) |
| Hardcoded stale caveats in summary.md contradict clean run metadata | Report integrity suspect, user distrusts every subsequent run | Check 15 (caveat sweep) |

## When the checklist fails

Do NOT self-patch migrations, constraints, or trainer code without explicit user approval. Surface findings, options, and reversibility; wait for go.
