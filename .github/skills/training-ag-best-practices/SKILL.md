---
name: training-ag-best-practices
description: AutoGluon Tabular 1.5 configuration best-practices and gotchas learned the hard way on this project. Covers hyperparameters dict semantics, num_bag_folds/num_stack_levels interaction, presets vs explicit model dicts, OpenMP handling on Apple Silicon, feature drift between train and inference.
---

# Training — AutoGluon 1.5 Best Practices

Config patterns that work, anti-patterns that have cost real compute, and specific AG 1.5 quirks that are not obvious from the docs.

## Model-zoo configuration

### The `hyperparameters` dict is a LOCKOUT, not an ADDITION

Passing `hyperparameters={"GBM": [...]}` does NOT add GBM configs on top of the preset's defaults — it **replaces** the entire model zoo with only the keys you listed. This is the single most expensive trap on this project (75-minute GBM-only run that was intended to be full zoo).

**Rule of thumb:** the preset sets the *default* zoo; the dict, if present, *defines* the zoo. Never rely on "preset plus overrides" because there is no such thing.

### Canonical full-zoo dict for Warbird

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
}
```

Every OpenMP-using family is single-threaded. Do not touch this without a reason documented in a comment.

### Alternative: `hyperparameters="default"` (string, not dict)

If you trust AG's curated defaults: pass the STRING `"default"` (valid values: `'default'`, `'light'`, `'very_light'`, `'toy'`, `'multimodal'`, `'zeroshot'`, `'zeroshot_2023'`). This uses the preset's full zoo.

**Caveat:** the string-form gives up per-family thread control. The env var `OMP_NUM_THREADS=1` (set at top of `scripts/ag/train_ag_baseline.py`) usually covers the deadlock risk, but some model families (PyTorch-NN) may spawn additional worker processes. Monitor the first run carefully.

## `num_bag_folds` / `num_stack_levels` / `use_bag_holdout` interaction

| Config | Meaning |
|--------|---------|
| `num_bag_folds=0, num_stack_levels=0` | Train one model per family. Uses `tuning_data` (val_df) for early stopping. Fastest, safest for time-series. **Warbird default.** |
| `num_bag_folds=K>0, num_stack_levels=0` | K-fold IID bag with internal shuffle → TIME-SERIES LEAKAGE. Do NOT use. |
| `num_bag_folds=K>0, num_stack_levels=L>0` | Bagged ensembles across L stack levels, uses OOF predictions as L+1 features. Only safe with a custom time-series splitter. |
| `use_bag_holdout=True` | Uses `tuning_data` as external holdout for bag evaluation. Only meaningful when `num_bag_folds > 0`. |

**If `num_bag_folds=0`, set `num_stack_levels=0`** — AG can error if you ask for stacking without bagging.

## OpenMP deadlock on Apple Silicon

LightGBM, XGBoost, and PyTorch all use OpenMP. AutoGluon's parallelism creates thread pools that can deadlock with OpenMP's own thread pool on M-series Macs, holding 400+ MB of memory and producing zero progress.

**Mandatory guards at top of any training script (before any `import` of AG/LightGBM/PyTorch):**
```python
import os
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("LIGHTGBM_NUM_THREADS", "1")
```

Add on the launch command line as belt-and-suspenders:
```bash
OMP_NUM_THREADS=1 LIGHTGBM_NUM_THREADS=1 /usr/local/bin/python3 scripts/ag/...
```

## `predictor.fit()` argument reference (current Warbird usage)

| Arg | Warbird value | Note |
|-----|---------------|------|
| `train_data` | `train_df[feature_cols + [label]]` | Must include target column |
| `tuning_data` | `val_df[feature_cols + [label]]` | External holdout for early stopping |
| `presets` | `"best_quality"` (overridden by explicit hyperparameters dict) | Consider `"good_quality"` when bagging is off — best_quality's bag+stack benefits are disabled anyway |
| `time_limit` | **1800-3600 sec per fold for full 7-family zoo**; 600 fine for GBM-only | 900 is the AG default; with 7 families sharing it each gets ~130s average — NN_TORCH / FASTAI will silently time-truncate. See budget math below. |
| `num_gpus` | `0` | CPU-only on this workstation |
| `ag_args_ensemble` | `{"fold_fitting_strategy": "sequential_local"}` | Prevents multi-process AG worker explosion |
| `use_bag_holdout` | `True` | No-op when `num_bag_folds=0` but harmless |
| `hyperparameters` | (explicit dict — see above) | |
| `num_bag_folds` | **`0` for time-series — MANDATORY** | Trainer CLI default is currently `5` which destroys session embargo. Every launch must override until trainer defaults are hardened. |
| `num_stack_levels` | **`0` when bag_folds=0 — MANDATORY** | Required because AG stacking needs bag-fold OOF predictions; also: stacking added zero ensemble weight on the broken run this project debugged. |
| `dynamic_stacking` | **`False` (explicit)** | `"auto"` is non-deterministic in AG 1.5 — pin off for reproducibility. |
| `excluded_model_types` | CSV string, empty string = none | Note: `""` does NOT "put models back in the pool" — the `hyperparameters` dict defines the zoo (see The `hyperparameters` dict is a LOCKOUT above). |

## Time-limit budget math for the full zoo

With 7 families (GBM × 2 configs, CAT, XGB, RF × 2 configs, XT × 2 configs, NN_TORCH, FASTAI = 11 model fits per fold), AG divides `time_limit` across them:

| `time_limit` | ~per-model budget | Likely NN / FastAI outcome |
|---:|---:|---|
| 600 | ~55 s | Silent early-stop on time; NN noise |
| 900 (default) | ~80 s | Same; tree families fine |
| 1800 | ~165 s | Marginal for NN_TORCH; FASTAI usable |
| 3600 | ~325 s | All families converge on 15m MES data |

**Rule of thumb:** `3600` for production full-zoo training; raise further if log shows `Ran out of time, early stopping on iteration N` in the final fit. For a GBM-only smoke test, `600` is plenty.

## Predictor feature drift handling

Between training and a later inference run (SHAP / MC), the feature set that `attach_context_features` produces may shrink — e.g., a FRED series with all-NaN on recent test windows gets dropped by `coerce_feature_frame`. The trained predictor still expects those columns.

**Pattern (used in `scripts/ag/monte_carlo_run.py::predict_probs_aligned`):**

```python
try:
    expected = list(predictor.features())
except AttributeError:
    expected = list(predictor.feature_metadata_in.get_features())
X = X.copy()
for col in expected:
    if col not in X.columns:
        X[col] = np.nan                    # AG's feature generator imputes
X = X[expected]                             # reorder to predictor's expected order
pp = predictor.predict_proba(X)
```

AG's feature generator handles NaN imputation natively. This pattern avoids the `KeyError: "N required columns are missing"` that the transform pipeline raises otherwise. Log the padded columns for transparency.

## Predictor feature drift between training and inference

Between training and a later SHAP/MC run, the FRED series admitted by `attach_context_features` may change (e.g., a series with all-NaN in the inference window gets dropped). The predictor was trained with those columns; it expects them at `predict_proba` time.

**Solution:** before calling `predict_proba`, align X to the predictor's feature list and pad missing columns with NaN:
```python
expected = list(predictor.features())  # or predictor.feature_metadata_in.get_features()
for col in expected:
    if col not in X.columns:
        X[col] = np.nan
X = X[expected]  # reorder
pp = predictor.predict_proba(X)
```
AG's feature generator handles NaN via imputation. See `scripts/ag/monte_carlo_run.py::predict_probs_aligned` for the working pattern.

## `require_py_version_match=False` when reloading predictors

If the Python version changes between training and inference, `TabularPredictor.load()` refuses by default. Pass `require_py_version_match=False` when you know the interpreter changed but AG major version is the same.

## `finally:` block transaction safety

Do NOT put multiple DB writes inside a single `with psycopg2.connect() as conn:` block in a `finally:` handler. If any write fails (e.g., CheckViolation), psycopg2 rolls back the entire transaction — including earlier writes like `UPDATE run_status = 'SUCCEEDED'`. Split each logical write into its own connection block, or wrap the ones you want to commit individually.

This cost the project a 75-min run's DB bookkeeping. The trainer's current `finally:` block at `scripts/ag/train_ag_baseline.py:1091-1154` bundles `upsert_training_run`, `update_training_run_fold_count`, `replace_run_metrics`, and `replace_artifacts` in one transaction. If any fails, run_status stays stuck at `RUNNING`.

## Known 1.5-specific quirks

1. **`predictor.feature_importance()` uses transformed feature names.** Categorical columns appear one-hot-encoded as `<col>_<value>`. Map back to raw names when reporting to humans.
2. **`predictor.predict_proba()` returns a DataFrame with class columns sorted alphabetically by default.** If you zero-pad a missing class, you must re-sort; better to `reindex(columns=CANONICAL_ORDER, fill_value=0)`.
3. **`dynamic_stacking="auto"` is non-deterministic.** AG decides stack depth based on timing; same data, different run can produce different stack levels. Set explicitly for reproducibility.
4. **`best_quality` preset turns on `dynamic_stacking`.** If you want a deterministic run, either use a lower-quality preset or pass `dynamic_stacking=False`.

## Related skills

- `training-pre-audit` — checks hyperparameters dict + OMP guards at launch time
- `training-ag-feature-finder` — AG features not yet used on this project
- `training-full-zoo` / `training-gbm-only` — the two launch profiles this project uses
