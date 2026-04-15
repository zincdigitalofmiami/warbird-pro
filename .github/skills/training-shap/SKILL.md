---
name: training-shap
description: Hi-def SHAP deep-dive on a completed AutoGluon training run. Produces aggregate + per-class + per-cohort feature importance plus diagnostic reports on leakage, calibration, and feature drift. Core outputs map directly to entry/TP decision rules. Use after every training run; mandatory before promoting any model or proposing indicator changes.
---

# Training — SHAP Deep Dive (Hi-Def)

**Locked execution plan:** `docs/plans/2026-04-15-hi-def-shap-mc-implementation.md`. The bucket cutoffs, leakage conjunction, and strip-list in that plan are authoritative — do not deviate in implementation.

## Project mission this skill serves

**Find when to enter. Find when to TP. Find what's broken.**

Every SHAP artifact this skill produces must answer one of:
1. What features does the model use that I should condition entries on?
2. What features does the model use differently per class — so I know when TP1 is realistic vs when to hold for TP3+?
3. What features are suspicious (dead, redundant, or leakage-shaped) that I should cull before the next run?

If an output doesn't answer one of those, it's noise — drop it.

## Required outputs (not optional)

Every run of this skill must produce ALL of these under `artifacts/ag_runs/<RUN_ID>/shap/`:

### 1. `overall_importance.csv`

Aggregate permutation importance (AG `predictor.feature_importance()`). One row per feature, columns: `rank, feature_name, mean_abs_shap, stddev, p_value, n_samples`. Descending by `mean_abs_shap`.

### 2. `per_class_importance.csv`

Long-form: `(class_name, rank_within_class, feature_name, mean_abs_shap)`. One section per outcome class: `STOPPED, TP1_ONLY, TP2_HIT, TP3_HIT, TP4_HIT, TP5_HIT`. Each class gets top-100.

**Why it matters:** STOPPED-driving features answer "what makes this trade fail"; TP5-driving features answer "what makes this trade run big." They are often DIFFERENT features. Aggregate SHAP dilutes this.

### 3. `per_cohort_importance/` directory

**Mandatory slices** (produce one CSV per cohort + one per cohort-value):

| Cohort dimension | Values |
|---|---|
| `by_fib_level/` | `236.csv, 382.csv, 500.csv, 618.csv, 786.csv, 1000.csv` |
| `by_direction/` | `long.csv, short.csv` |
| `by_stop_family/` | 6 files, one per family |
| `by_hour_bucket/` | 8 files per HOUR_BUCKETS in `scripts/ag/monte_carlo_run.py` |
| `by_archetype/` | one file per distinct archetype value |
| `by_fold/` | `fold_01.csv ... fold_05.csv` for temporal stability |

**Additional slices** (compute on demand when a categorical feature ranks top-5 aggregate):
- `by_<feature>/` with one file per distinct value

**Rule:** if ANY categorical or low-cardinality integer feature appears in the aggregate top-5, you MUST produce a per-cohort slice for it. The aggregate masks U-shapes and extremes (see GPT SHAP finding on `fib_level_touched` — aggregate ranked it #2 at 0.47, but slices showed rank 1 at value 236 [0.92] and value 1000 [0.84], while dropping out of top-10 at value 618).

### 4. `temporal_stability.csv`

Per-feature, across folds: `feature_name, fold_01_rank, fold_02_rank, ..., fold_05_rank, stability_score`.

`stability_score` = (number of folds where this feature is in top-20) / 5. Stable features (≥ 4/5) are trustworthy; unstable features (≤ 2/5) are either regime-conditional (interesting) or overfit artifacts (bad).

### 5. `raw_shap_values.parquet`

Full SHAP matrix for the test slice: shape `(N_rows, N_features, N_classes)`. Persist for future re-analysis without re-running the expensive permutation step.

### 6. `manifest.json`

- `run_id`, `generated_at_utc`, `shap_method` (permutation | TreeExplainer), `time_limit_per_fold`
- Per-cohort row counts (so future readers know sample-size caveats)
- Features that hit zero importance (auto-drop candidates)
- Features with stability_score < 0.4 (review candidates)
- Feature count that entered SHAP (should match `feature_manifest.json` from training)

### 7. `summary.md` — human-readable, opinionated

Required sections:
- **Top-5 actionable findings** — features this run wants you to actually use
- **Kill list** — features with importance < 0.005 OR stability < 0.2 (drop from next training surface)
- **Leakage suspects** — features with uniform-across-time importance, or features that encode time/regime. Flag explicitly.
- **Cohort divergences** — features that flip importance direction or magnitude across cohort values (e.g., `sl_dist_atr` important only at fib_level=236)
- **Entry-condition implications** — translate top features into "take trade when X ∈ range Y" rules
- **TP-condition implications** — translate per-class importance into "exit at TP_n when predicted P(TP_n+) < threshold"
- **Cross-ref to Monte Carlo** — which Task D top combos' feature signatures match high-SHAP conditions

## Method

### Aggregate + per-class — use AG's built-ins

```python
from autogluon.tabular import TabularPredictor
predictor = TabularPredictor.load(predictor_dir, require_py_version_match=False)

# Overall
importance_df = predictor.feature_importance(
    data=test_df,
    time_limit=600,       # 10 min per fold max — scale up for final runs
    num_shuffle_sets=5,   # more = tighter CIs
)

# Per class requires raw SHAP on the underlying model
import shap
best_model_name = predictor.model_best
raw_model = predictor._trainer.load_model(best_model_name).model
explainer = shap.TreeExplainer(raw_model)
shap_values = explainer.shap_values(transformed_test_df)  # list per class
```

### Per-cohort — mask and recompute

```python
for level in [236, 382, 500, 618, 786, 1000]:
    cohort_mask = test_df["fib_level_touched"] == level
    if cohort_mask.sum() < 200:
        continue  # too few rows for stable SHAP
    cohort_df = test_df[cohort_mask]
    cohort_importance = predictor.feature_importance(
        data=cohort_df, time_limit=300, num_shuffle_sets=3
    )
    cohort_importance.to_csv(f"per_cohort_importance/by_fib_level/{level}.csv")
```

### Aligning predictor features to test frame

If the test slice is missing columns the predictor expects (FRED series that dropped out of `attach_context_features`), pad with NaN per `scripts/ag/monte_carlo_run.py::predict_probs_aligned`. AG's feature generator handles NaN imputation.

### Run budget

- Overall SHAP per fold: 10-20 min
- Per-class SHAP per fold: 10-30 min (TreeExplainer is fast but 6 classes + many features)
- Per-cohort SHAP: ~5 min per cohort-value × 5+ cohorts = 30-90 min
- Total per fold: 1-2 h; 5 folds: 5-10 h

Budget accordingly. For exploratory runs, restrict to fold_05 + aggregate cohorts.

## Diagnostic checks this skill performs

### Leakage signals (the critical filter)

If the source training run had IID bag-fold leakage (`valid_set f1_macro ~0.99` with `test ~0.14`), SHAP rankings are corrupted. Detection patterns:

1. **Uniform macro-feature importance across all cohort slices.** If FRED DGS10/DGS30/DEXJPUS show ~identical importance at every fib_level × every hour_bucket × every direction, they're not "regime signal" — they're being used as a time-identity proxy. Flag in summary.md.

2. **High per-class SHAP for time-encoding features.** `ts`, `session_date_ct`, `hour_ts` should NEVER appear with non-zero SHAP. They're in `LEAKAGE_COLS`. If they do, training leaked.

3. **stability_score near 0 for features expected to be stable.** If `fib_range` (structural) has stability < 0.5 across folds, something is wrong. Stable features should be stable.

Always add a **"Leakage Verdict"** paragraph to summary.md: `SUSPECT` / `LIKELY CLEAN` / `CLEAN` with the specific signals that led to that verdict.

### Calibration check (pair with Monte Carlo)

For each class per cohort (stop_family × direction × fib_level), compute: `mean(predicted_P[c]) vs realized_freq[c]` where realized_freq is the empirical fraction of that cohort whose `outcome_label == c`. Diverging systematically means the model's probabilities can't be trusted for MC's threshold-gating analysis.

**Join key is `(fold_code, stop_variant_id)`, NOT `(fold_code, id)`.** On the normalized AG schema, `ag_training.id` comes from `ag_fib_interactions.id` and repeats 6× across stop variants (one row per stop family per interaction). Using `id` would fail `validate="one_to_one"` merges or silently cartesian-expand rows. `stop_variant_id` is the unique row key and is already in `META_COLS`, so it's in every raw SHAP parquet.

Verdict rules (applied to every cohort × class row):

| predicted | realized | ratio | verdict |
|---|---|---|---|
| `> 0` | any | `0.7 ≤ ratio ≤ 1.3` | OK |
| `> 0` | any | `ratio < 0.7` | OVERCONFIDENT |
| `> 0` | any | `ratio > 1.3` | UNDERCONFIDENT |
| `= 0` | `> 0.005` | ∞ | **ZERO_PREDICTION_MISS** |
| `= 0` | `≤ 0.005` | NaN | OK |

**Critical rule, locked** — do NOT short-circuit to "OK" whenever `predicted < 0.005`. That hides the exact failure mode that matters for rare-class P&L (model never predicts TP3/TP4/TP5, class still occurs at a material rate, MC threshold-gating will mis-price). `ZERO_PREDICTION_MISS` must surface explicitly in `calibration_check.csv` for every cohort × class that matches.

### Feature redundancy check

Compute pairwise correlation of raw feature columns (on test slice). Feature pairs with |corr| > 0.95 AND similar SHAP importance are redundant — drop one in the next training surface.

Known redundant candidates on Warbird data: `fred_dfedtarl` / `fred_dfedtaru` / `fred_dff` (all track fed funds); `ema9` / `ema21` at short lookbacks; `fred_cpiaucsl` / `fred_cpilfesl` / `fred_pcepilfe` (inflation variants).

## Mapping SHAP → trade rules (the actionable output)

The summary.md MUST include "Entry rules surfaced by SHAP" section with concrete proposals:

Example format:
```
### Entry rules surfaced by SHAP

- **fib_range > median:** SHAP magnitude ranks #1. Model has 2-3x more conviction on large-range setups. Rule: only take setups with fib_range > 50th percentile.
- **hour_ct ∈ {9-11, 13-15} CT:** SHAP peaks in RTH_MORNING and RTH_AFTERNOON. Avoid ETH_POST_RTH — SHAP importance is high but direction is negative in Task D combos.
- **At fib_level_touched = 236: sl_dist_atr matters disproportionately.** Rule: 236 setups must have sl_dist_atr > some threshold (find in per-cohort SHAP) OR use a wider stop family for 236.
- **When fred_dgs10 is in regime X (quartile):** SHAP flips sign — investigate whether to trade only during specific rate regimes.
```

Every bullet references which SHAP artifact supports it. No hand-waving.

### TP-ladder rules surfaced by SHAP

Per-class SHAP answers "what features predict TP3+?". For each class, identify top-5 features. In summary.md:
```
### TP3+ predictive features (per-class SHAP)

Top features when model predicts TP3+ vs TP1_ONLY:
1. fib_range (much larger in TP3+ predictions)
2. anchor_swing_velocity (higher = more momentum = reaches deeper TPs)
3. confluence_quality (Q4 vs Q1)
...

Implied rule: let winners run to TP3 only when fib_range × anchor_swing_velocity > threshold;
otherwise exit at TP1/TP2.
```

## Kill list / drop list discipline

After every SHAP run, write a `drop_candidates.csv` with columns:
- `feature_name, aggregate_rank, aggregate_importance, stability_score, reason`

Reasons:
- `DEAD` — importance < 0.005 AND stability_score near 0
- `REDUNDANT` — correlated > 0.95 with a higher-importance feature
- `LEAKAGE_SUSPECT` — uniformly important across every cohort (time-identity proxy pattern)
- `UNSTABLE_LOW_VALUE` — stability < 0.4 AND importance < 0.1 (unreliable and weak)

Do NOT auto-drop. Human review before next training surface change.

## Known source-run caveats

- If the source run has IID bag leakage → FRED/macro cluster will appear artificially high. Re-run SHAP on a `--num-bag-folds 0 --num-stack-levels 0` run to validate.
- Per-class SHAP for rare classes (TP4/TP5) is noisy — minimum 200 rows of the class required. If training test slice has < 200 TP5 rows, skip that class's SHAP or note as unreliable.
- AG's feature transform means `stop_family_id` appears as one-hot categorical columns in per-class SHAP (`stop_family_id_ATR_1_0`, etc). Re-aggregate to raw categorical name before reporting.

## Cohort-CV must come from untruncated data

The cross-cohort CV that feeds `LEAKAGE_SUSPECT` must be computed from the **full per-feature per-cohort matrix**, not from the top-N cohort CSVs on disk. `--max-features-per-cohort` truncates the CSV for human scannability — if you re-read those CSVs to compute CV, features that drop below the top-N in some cohorts are silently absent from their CV calculation, which **biases CV downward and falsely promotes LEAKAGE_SUSPECT**.

Implementation pattern: `compute_cohort_importance` returns both `counts` (for the CSVs) AND `full_vectors` (untruncated per-cohort per-feature arrays in memory). The orchestrator collects all `full_vectors` across cohort dimensions into a single dict keyed `"<dim>:<value>"`, then feeds that dict to `compute_cohort_cv_by_feature`. See `scripts/ag/run_diagnostic_shap.py` for the reference implementation.

## `archetype` backfill for runs that predate the META_COLS change

Raw SHAP parquets generated before `archetype` was added to `META_COLS` don't have the column. Backfill via DB join instead of recomputing SHAP:

```sql
SELECT v.id AS stop_variant_id, i.archetype
FROM ag_fib_stop_variants v
JOIN ag_fib_interactions i ON i.id = v.interaction_id
WHERE v.id = ANY(%s)
```

Parameterize with the list of `stop_variant_id` values from the parquet. One query per run, merge left onto combined frame. Idempotent — if `archetype` is already present and non-null, skip.

## `hour_bucket` must match the MC contract

Derive `hour_bucket` from `ts` (always present in META_COLS). Import `HOUR_BUCKETS` from `scripts/ag/monte_carlo_run.py` rather than redefining to prevent contract drift — the two scripts MUST partition hours identically so Task E / Task B / SHAP cohort slices align 1-to-1.

## Related skills

- `training-monte-carlo` — consumes SHAP rankings to build feature-conditional EV analysis
- `training-quant-trading` — leakage signals dictionary
- `training-pre-audit` — catches training problems before they corrupt SHAP
- `training-ag-best-practices` — feature-transform gotchas affecting SHAP interpretation

## Checklist before declaring a SHAP run complete

- [ ] `overall_importance.csv` produced and sorted descending
- [ ] `per_class_importance.csv` produced for all 6 outcome classes
- [ ] Per-cohort slices produced for EVERY categorical feature in aggregate top-5
- [ ] `temporal_stability.csv` produced across all 5 folds
- [ ] `raw_shap_values.parquet` persisted
- [ ] `drop_candidates.csv` produced
- [ ] `summary.md` contains: Top-5 actionable, Kill list, Leakage Verdict, Cohort divergences, Entry rules, TP-ladder rules, Cross-ref to MC
- [ ] Leakage verdict is explicit (`SUSPECT` / `LIKELY CLEAN` / `CLEAN`) with supporting signals
- [ ] Calibration check table in summary.md

If any checkbox is missed, the SHAP run is incomplete — do not promote or report findings to the user as "final."
