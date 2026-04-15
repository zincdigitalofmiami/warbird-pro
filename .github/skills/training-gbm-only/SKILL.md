---
name: training-gbm-only
description: Launch a fast, GBM-only AutoGluon run for iteration speed. Use when you need a quick probe of the training surface, a baseline for comparison, or to test pipeline plumbing. Not for final model selection — see training-full-zoo for multi-family comparisons.
---

# Training — GBM Only

## When to use

- Fast iteration while debugging feature engineering or splits
- Baseline to compare against a full-zoo run
- Pipeline smoke test after migration changes
- When time budget is tight (<60 min wall)

## When NOT to use

- Final model selection → use `training-full-zoo`
- Any run whose output will be promoted to production
- Any SHAP or interpretability work meant to claim a multi-family comparison

## Pre-checks (skippable only if you ran them this session)

Run the `training-pre-audit` skill first. Non-negotiable items:
- `ag_training` view row count > 0
- No orphan `RUNNING` rows in `ag_training_runs`
- Trainer's hyperparameters dict explicitly contains only GBM (this is why the run is "GBM-only")
- OMP env vars exported

## Launch command

```bash
cd "/Volumes/Satechi Hub/warbird-pro" && \
  LAUNCH_TS=$(date -u +"%Y-%m-%dT%H:%M:%SZ") && \
  LOG_PATH="/tmp/agtrain_gbm_$(date -u +%Y%m%dT%H%M%SZ).log" && \
  GIT_SHA=$(git rev-parse HEAD) && \
  echo "LAUNCH_TS=$LAUNCH_TS  LOG_PATH=$LOG_PATH  GIT_SHA=$GIT_SHA" && \
  OMP_NUM_THREADS=1 LIGHTGBM_NUM_THREADS=1 \
  /usr/local/bin/python3 scripts/ag/train_ag_baseline.py \
    --excluded-model-types "" \
    --num-bag-folds 0 \
    --num-stack-levels 0 \
    --time-limit 600 \
    > "$LOG_PATH" 2>&1
```

**`--num-bag-folds 0 --num-stack-levels 0` is mandatory.** Default AG bagging is IID random shuffle which destroys the time-series session embargo. Without `0/0` the validation score will look great (f1 ~0.99) and collapse on test (~0.14).

**`--time-limit 600`** caps each fold at 10 min. Total 5-fold wall is ~50-60 min. For faster: drop to 300.

## Temporarily narrowing hyperparameters to GBM

If the trainer's `hyperparameters` dict currently contains the full zoo but you want GBM-only right now WITHOUT editing code, add `--excluded-model-types "CAT,XGB,RF,XT,NN_TORCH,FASTAI,KNN"` to the launch line. The trainer reads this CSV flag and excludes those model types from AG's fit.

To make GBM-only the baked-in default, edit `scripts/ag/train_ag_baseline.py` around the `hyperparameters` key in `fit_kwargs`:

```python
"hyperparameters": {
    "GBM": [
        {"num_threads": 1},
        {"num_threads": 1, "extra_trees": True},
    ]
},
```

Document the reason in a comment so the next session doesn't think it's an accident (we had a 75-min run burn because this was silently the case without anyone noticing).

## Monitoring

Training writes `run_status='RUNNING'` into `ag_training_runs` ~30-120 s after launch. Capture RUN_ID bound to your launch window:

```bash
/opt/homebrew/opt/postgresql@17/bin/psql -d warbird -h 127.0.0.1 -p 5432 -At -c \
  "SELECT run_id FROM ag_training_runs
   WHERE started_at >= '<LAUNCH_TS>'::timestamptz
     AND git_commit_sha = '<GIT_SHA>'
   ORDER BY started_at ASC LIMIT 1"
```

Progress is the count of `fold_0N/fold_summary.json` files under `artifacts/ag_runs/<RUN_ID>/`. DB metrics do NOT populate until the run ends (batch write in the `finally:` block).

## Expected outputs

- `artifacts/ag_runs/<RUN_ID>/dataset_summary.json`
- `artifacts/ag_runs/<RUN_ID>/feature_manifest.json`
- `artifacts/ag_runs/<RUN_ID>/training_summary.json`
- `artifacts/ag_runs/<RUN_ID>/fold_0N/{fold_summary.json, leaderboard.csv, predictor/}` × 5

## Known traps

1. If `run_status` sticks at `RUNNING` after training finishes on disk: `replace_run_metrics` hit a DB CheckViolation inside `finally:` and rolled back. See `training-pre-audit` check 4 (AUTOGLOON trap).
2. AG will print `valid_set f1_macro` ~0.99 during bag-child fitting if bag_folds > 0. This is NOT predictive of test. Trust the `Validation score = X` line AG prints at the end of each model, and the test scores in `leaderboard.csv`.
3. AG's `best_quality` preset assumes multi-model. With GBM-only you lose the ensemble benefit — treat scores as lower-bound.

## Cleanup on failure

If the run failed and you want to retry:
1. `UPDATE ag_training_runs SET run_status='FAILED', error_message='...' WHERE run_id='...'`
2. Leave the on-disk artifacts — they're self-contained
3. Root-cause before retrying: running the same configuration again produces the same failure

## Related skills

- `training-full-zoo` — multi-family comparison run
- `training-pre-audit` — runs before this
- `training-monte-carlo` — P&L analysis on completed predictors
- `training-shap` — feature importance on completed predictors
