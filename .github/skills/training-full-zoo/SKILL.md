---
name: training-full-zoo
description: Launch a full-model-zoo AutoGluon run (GBM + CAT + XGB + RF + XT + NN_TORCH + FASTAI) for real multi-family comparison. Use for final model selection, SHAP-comparison runs, and any production-candidate training. Mandatory num-bag-folds=0 for time-series correctness.
---

# Training — Full Zoo

Real multi-family model comparison with explicit OpenMP guards so LightGBM doesn't deadlock Apple Silicon.

## When to use

- Final model selection for a training surface
- Comparing tree-based vs NN approaches on the same features
- SHAP / feature-importance work that claims cross-family validity
- Any run feeding into promotion decisions

## When NOT to use

- Fast iteration (use `training-gbm-only`)
- You have no time budget for 3-6 h of compute

## Pre-checks

**MUST run `training-pre-audit` first.** Critical checks for this run type:
- Trainer's `hyperparameters` dict in `scripts/ag/train_ag_baseline.py` explicitly includes GBM + CAT + XGB + RF + XT + NN_TORCH + FASTAI (see canonical block below)
- OMP guards active (lines 7-9 of trainer)
- `/usr/local/bin/python3` imports `from autogluon.tabular import TabularPredictor` cleanly
- Migration ledger includes 014 + 017 (AUTOGLUON typo fix)

## Canonical hyperparameters dict

`scripts/ag/train_ag_baseline.py` `fit_kwargs["hyperparameters"]` should look like:

```python
"hyperparameters": {
    "GBM": [
        {"num_threads": 1},
        {"num_threads": 1, "extra_trees": True},
    ],
    "CAT": {"thread_count": 1},
    "XGB": {"n_jobs": 1},
    "RF": [{"criterion": "gini"}, {"criterion": "entropy"}],
    "XT": [{"criterion": "gini"}, {"criterion": "entropy"}],
    "NN_TORCH": {},
    "FASTAI": {},
},
```

Every family that uses OpenMP is pinned to 1 thread. The module-level `OMP_NUM_THREADS=1` env var is belt-and-suspenders.

**If the dict contains only `"GBM": [...]`, you are about to run GBM-only masquerading as full-zoo.** `--excluded-model-types ""` does NOT put models back in the pool. This was a real 75-min waste in the project's history. Read the dict. Don't assume.

## Launch command

```bash
cd "/Volumes/Satechi Hub/warbird-pro" && \
  LAUNCH_TS=$(date -u +"%Y-%m-%dT%H:%M:%SZ") && \
  LOG_PATH="/tmp/agtrain_zoo_$(date -u +%Y%m%dT%H%M%SZ).log" && \
  GIT_SHA=$(git rev-parse HEAD) && \
  echo "LAUNCH_TS=$LAUNCH_TS  LOG_PATH=$LOG_PATH  GIT_SHA=$GIT_SHA" && \
  OMP_NUM_THREADS=1 LIGHTGBM_NUM_THREADS=1 \
  /usr/local/bin/python3 scripts/ag/train_ag_baseline.py \
    --excluded-model-types "" \
    --num-bag-folds 0 \
    --num-stack-levels 0 \
    --time-limit 1800 \
    > "$LOG_PATH" 2>&1
```

Launch in background (`run_in_background: true` on the Bash tool).

**`--num-bag-folds 0 --num-stack-levels 0`** is mandatory. AG's default IID bag splitting breaks session embargo on MES 15m — leads to `valid_set f1_macro ~0.99` that collapses on test.

**`--time-limit 1800` minimum; `3600` recommended** for this 7-family zoo. AG splits the budget across families — at 900s/fold (the stale default) each family gets ~80-100s and NN_TORCH / FASTAI silently time-truncate before convergence, contributing noise rather than signal. Budget 30-60 min per fold × 5 folds = 2.5-5 h total.

**`--dynamic-stacking`** should be `off` explicitly, not the AG `"auto"` default. With `num_bag_folds=0 --num_stack_levels=0` the setting is moot for model selection but `"auto"` introduces non-determinism in AG 1.5's fit timing. For reproducibility, pin it off.

## Monitoring

```bash
# Status
/opt/homebrew/opt/postgresql@17/bin/psql -d warbird -h 127.0.0.1 -p 5432 -c \
  "SELECT run_status, fold_count, completed_at, error_message
   FROM ag_training_runs WHERE run_id = '<RUN_ID>'"

# Progress (authoritative — DB metrics land only at completion)
ls artifacts/ag_runs/<RUN_ID>/fold_*/fold_summary.json | wc -l

# Per-fold activity
tail -n 40 <LOG_PATH>
```

## GBM-presence verification (non-negotiable for zoo runs)

```bash
for f in artifacts/ag_runs/<RUN_ID>/fold_*/leaderboard.csv; do
  fold=$(basename "$(dirname "$f")")
  python3 -c "
import csv
with open('$f') as fh:
    r = csv.DictReader(fh)
    families = set()
    for row in r:
        m = row.get('model','')
        for fam in ['LightGBM','CatBoost','XGBoost','RandomForest','ExtraTrees','NeuralNet','FastAI']:
            if fam in m: families.add(fam)
    print('$fold:', sorted(families))
"
done
```

Each fold's leaderboard must contain **at least GBM, CAT, XGB** and ideally RF/XT/NN_TORCH/FASTAI. Missing families = zoo silently didn't run → audit hyperparameters dict.

## Expected wall time on the current workstation

| Model family | ~per-fold |
|---|---|
| LightGBM (2 configs) | 3-10 min |
| CatBoost | 15-40 min |
| XGBoost | 5-15 min |
| RandomForest (2 configs) | 3-8 min |
| ExtraTrees (2 configs) | 3-8 min |
| NN_TORCH | 10-30 min |
| FastAI | 10-30 min |
| **Total per fold** | ~50-140 min |
| **5 folds** | ~4-12 h |

Budget accordingly. If the run goes past 6 h without a fold completing, something is stalling — check log for OMP deadlock signs.

## Known traps

1. **The hyperparameters lockout.** If the dict is wrong, zoo doesn't run. Read the dict before every zoo launch.
2. **CatBoost's internal threading.** Even with `thread_count=1`, CatBoost spawns worker processes. Tune `CAT_thread_count` if CPU pressure is an issue.
3. **XGBoost OpenMP.** `XGB: {"n_jobs": 1}` + `OMP_NUM_THREADS=1` env var both required.
4. **NN_TORCH GPU autodetect.** `num_gpus=0` in fit_kwargs forces CPU. If you see "CUDA device not found", that's expected (we train on CPU).
5. **AG stack-level interaction with `num_bag_folds=0`.** AG requires bag folds for meaningful stacking OOF predictions. With `num_bag_folds=0` you must also set `num_stack_levels=0` or AG errors.
6. **NN / FastAI starvation at low `--time-limit`.** With 7 families sharing 900s, neural families can't converge. Set `--time-limit 1800` minimum, `3600` preferred. If NN families still time-truncate, either drop them from the zoo (tree models usually dominate tabular MES anyway) or raise further.

## What a BROKEN zoo run looks like — concrete fingerprints

If any of these show up in leaderboard / logs, the run's conclusions are NOT trustworthy:

1. **`valid_set f1_macro` during LightGBM fit is 0.95+** but AG-reported `Validation score` is < 0.30. The gap is IID-bag leakage (`num_bag_folds > 0` on time-series). Source run `agtrain_20260415T015005138333Z` showed exactly 0.99 → 0.186.
2. **`Ensemble Weights: {'<single_model>': 1.0}`** at every `WeightedEnsemble_L2/L3/L4`. Stacking added zero diversity — either the data is noisy/contaminated or the L2+ families time-truncated before fitting.
3. **Only LightGBM in leaderboards** despite passing `--excluded-model-types ""`. The `hyperparameters` dict is locking the zoo to GBM-only. Re-read `fit_kwargs["hyperparameters"]` in the trainer.
4. **Test f1_macro ~ majority-baseline f1_macro (fold_summary `majority_baseline.test.macro_f1`).** Model has no edge. Either the training surface is unlearnable, the split leaked, or the features are all uninformative. Run SHAP to diagnose before rerunning.

## After successful completion

Run in sequence:
1. `training-shap` — feature importance per family (your GPT may handle this separately)
2. `training-monte-carlo` — P&L analysis on the predictors
3. Compare multi-family leaderboards: does the winning model change across folds? If yes, use the median-winner; if no, you have a clean preference

## Related skills

- `training-pre-audit` — MUST run before
- `training-gbm-only` — faster baseline
- `training-monte-carlo` — P&L analysis post-completion
- `training-shap` — feature importance post-completion
- `training-quant-trading` — time-series discipline (walk-forward, embargo)
