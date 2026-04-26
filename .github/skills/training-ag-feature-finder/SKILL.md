---
name: training-ag-feature-finder
description: Catalog of AutoGluon 1.5 features NOT yet used on the Warbird project, with pointers to when each might be worth adopting. Use before proposing a trainer extension — check here first to see if AG already has a built-in for what you want.
---

> **2026-04-26 indicator-only reset:** This training skill is legacy unless Kirk explicitly reopens the old warehouse AG architecture. Active modeling uses Pine/TradingView outputs only; do not use FRED, macro, local `ag_training`, or daily-ingestion training flows.


# Training — AutoGluon Feature Finder

Living inventory of AutoGluon Tabular 1.5 capabilities that are available but currently unused in `scripts/ag/train_ag_baseline.py`. Each entry: what it is, when to adopt, adoption cost.

## Not currently used

### `holdout_frac` with no `tuning_data`

Instead of passing `tuning_data=val_df`, let AG carve a holdout from `train_data` via `holdout_frac=0.2`. Simpler single-block training — relevant if you decide the external val_df is redundant.

**Adoption:** trivial (swap args). **Risk:** AG's random holdout is IID — DO NOT use for time-series without `holdout_frac` + a custom time-respecting holdout indexer.

### `time_limit_per_model`

Budget individual models rather than the whole fold. Useful when one family (e.g., NN_TORCH) consistently starves the others.

**Adoption:** low. **Status:** currently `time_limit` is per-fold only; no per-model control.

### `keep_only_best=True`

After fit, AG discards all non-best models to save disk. If disk pressure on the Satechi drive becomes a problem (each `predictor/` dir can be 100+ MB × 5 folds × multiple runs), turn this on for routine runs.

**Caveat:** you lose the ability to compare model families on the same leaderboard. Not for full-zoo runs intended for SHAP.

### `calibrate=True`

Isotonic calibration post-fit. Useful if Monte Carlo's threshold-gating analysis shows the model's probabilities are poorly calibrated (threshold curves are jagged, `realized_class_dist` diverges from `predicted_class_dist`).

**Adoption:** low. **Worth testing:** yes — current MC shows `predicted_mean_P ≈ realized_class_dist` which is expected for calibrated models; might already be near-calibrated.

### `fit_weighted_ensemble_per_stack=False`

Current trainer fits weighted ensemble at every stack level. With `num_stack_levels=0` this is moot, but if stacking ever turns back on (with a custom time-series splitter), setting this to False halves fit time.

### `ag_args_fit={'num_cpus': N, 'num_gpus': 0}`

Fine-grained CPU budgeting per fit. Current trainer doesn't set this. For the 12-core workstation, `num_cpus=8` across AG + reserving 4 cores for the OS might be faster than the default all-cores mode.

**Adoption:** low. Worth experimenting on a non-critical run.

### `hyperparameter_tune_kwargs` (HPO)

AG's built-in HPO. Each model family gets HPO trials within the fold's `time_limit`. Triggers with e.g. `hyperparameter_tune_kwargs={'searcher': 'random', 'scheduler': 'local', 'num_trials': 20}`.

**Adoption:** medium. **Value:** potentially substantial — we haven't tuned a single hyperparameter across any family on this project. Low-hanging fruit after a clean zoo baseline.

### `auxiliary_data` (2+ data sources)

AG can consume multiple DataFrames and stitch them. Possibly useful for combining MES bars + cross-asset bars at different frequencies without hand-joining.

**Status:** nice-to-have, not a priority — our `attach_context_features` already does the join.

### `predictor.persist_models()` + `predictor.unpersist_models()`

Keeps best model in memory between predict calls; avoids the ~30-60 s reload time. Relevant for MC and SHAP runs that call predict many times.

**Adoption:** trivial. **Do it** in `monte_carlo_run.py` — would cut MC wall time noticeably on 5-fold predict cycles.

### `predictor.evaluate()` with custom scoring

AG's built-in `evaluate()` computes scorers AG knows about. For custom metrics (e.g., "simulated EV per trade"), subclass `Scorer` and register it at fit time.

**Adoption:** medium. **Value:** would let AG's HPO optimize directly for EV instead of a proxy metric like f1_macro.

### `predictor.leaderboard(extra_info=True)`

Adds columns for `hyperparameters`, `num_models`, `model_type`, etc. Currently the leaderboards only have score / runtime columns.

**Adoption:** trivial. Worth flipping on for debugging.

### `predictor.fit_pseudolabel(unlabeled_data=...)`

Semi-supervised fit — labels unlabeled MES bars with model predictions and retrains. Potentially useful for the large STOPPED class where labels are abundant but maybe noisy.

**Status:** speculative. Unclear if it helps or hurts on this imbalanced target.

### Text-column handling

If we ever add text features (news headlines, analyst commentary), AG's `ag_text` transformers auto-handle via sentence-embedding models. Currently not needed under the active indicator-only contract.

### Per-row sample weights

`fit(train_data=df, weights='recency_weight_col')` lets AG weight recent sessions higher. Could model regime shift more aggressively than the embargo approach alone.

**Adoption:** medium. **Value:** worth testing for a production model once the baseline is clean.

### `save_space=True`

Drops training data from the predictor after fit. Halves disk without losing predict capability. Analogous to `keep_only_best`.

### Multi-modal fit (tabular + image/text)

Not relevant for this project's scope.

### `infer_limit` / `infer_limit_batch_size`

Constrain model selection by inference latency ceiling. Useful once models are served live from the Pine indicator round-trip, since slow models would blow the alert budget.

**Adoption:** premature — we don't have a live serving path yet.

## How to evaluate adding a feature

1. Write a small dry-run script that tests the feature in isolation (single fold, small time_limit).
2. Compare the fold's `test_f1_macro` against the baseline.
3. If it improves materially AND doesn't slow the zoo run > 2×, add to the trainer's `fit_kwargs` with a comment explaining why.
4. Update this file — move the entry from "Not currently used" to a "Recently adopted" section (create it when needed).

## Related skills

- `training-ag-best-practices` — how to configure features once adopted
- `training-full-zoo` — the canonical run where new features are tested
- `training-pre-audit` — update audit checklist when feature is adopted
