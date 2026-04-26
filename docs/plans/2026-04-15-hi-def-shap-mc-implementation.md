# Hi-Def SHAP + Monte Carlo Implementation Plan

> **Superseded 2026-04-26:** This plan belongs to the retired warehouse
> `ag_training` architecture. Active modeling is indicator-only Pine/TradingView
> output analysis. Use this file for lineage only.

**Date:** 2026-04-15
**Status:** Approved execution note — NOT a new authority doc
**Scope:** `scripts/ag/run_diagnostic_shap.py` + `scripts/ag/monte_carlo_run.py`
**Source of truth:** This file. The conversation that produced it is context-window-ephemeral; this file persists.

## Purpose

Turn the SHAP + Monte Carlo surfaces into hi-def reports that directly answer the project's core trading questions — **when to enter, when to TP, what wins look like, what's broken**. Current scripts produce partial data; this plan lifts them to the output contract specified in `training-shap` and `training-monte-carlo` skills.

Driven by the 2026-04-15 session where the source training run had IID bag-fold leakage, and neither the aggregate SHAP nor the Task A-D MC output was sufficient for decision-making (the per-fib-level SHAP slice revealed a U-shape the aggregate hid; MC couldn't answer TP-ladder or regime-stability questions).

---

## 1. `run_diagnostic_shap.py`

- Split the script into two phases:
  1. raw SHAP compute phase
  2. post-process phase over existing raw parquet
- Add `--postprocess-only` so old runs can be upgraded without recomputing SHAP.
- Keep all current outputs unchanged:
  - `shap_values_fold_*_test.parquet`
  - `shap_feature_summary_fold_*_test.csv`
  - `shap_feature_summary_overall_test.csv`
  - `diagnostic_shap_manifest.json`
- Add metadata enrichment for old runs:
  - use existing parquet columns when present
  - otherwise backfill `archetype` via `stop_variant_id -> ag_fib_stop_variants.interaction_id -> ag_fib_interactions.archetype`
  - derive `hour_bucket` from `ts` using the same bucket contract as `monte_carlo_run.py`
- Add new outputs at `artifacts/shap/<run_id>/`:
  - `overall_importance.csv`
  - `per_class_importance.csv`
  - `per_cohort_importance/by_fib_level/*.csv`
  - `per_cohort_importance/by_direction/*.csv`
  - `per_cohort_importance/by_stop_family/*.csv`
  - `per_cohort_importance/by_hour_bucket/*.csv`
  - `per_cohort_importance/by_archetype/*.csv`
  - `per_cohort_importance/by_fold/*.csv`
  - `temporal_stability.csv`
  - `calibration_check.csv`
  - `redundancy_check.csv`
  - `drop_candidates.csv`
  - `summary.md`
  - refreshed `manifest.json`
- `temporal_stability.csv` columns:
  - `feature_name`
  - `rank_min`
  - `rank_max`
  - `rank_range`
  - `mean_abs_min`
  - `mean_abs_max`
  - `mean_abs_cv`
  - `top20_fold_count`
  - `stability_bucket`
- `drop_candidates.csv` reason rules:
  - `DEAD`: near-zero aggregate importance
  - `REDUNDANT`: high-correlation duplicate with lower importance
  - `LEAKAGE_SUSPECT`: high importance plus suspiciously uniform importance across cohorts
  - `UNSTABLE_LOW_VALUE`: weak and volatile across folds
- Add summary sections in `summary.md`:
  - TL;DR
  - stable core drivers
  - per-class drivers
  - per-cohort drivers
  - leakage verdict
  - calibration check
  - redundancy / drop candidates
  - actionable entry / TP observations with artifact citations
- CLI additions:
  - `--postprocess-only`
  - `--cohort-min-rows`
  - `--max-features-per-cohort`
  - `--skip-cohorts`
  - `--calibrate`
  - `--dry-run`
  - `--leakage-rank-threshold`
  - `--leakage-cv-threshold`

## 2. `monte_carlo_run.py`

- Refactor `prepare_fold()` to return an **analysis frame**, not the old base frame.
- That analysis frame must include:
  - all current trade/payoff fields used by A–D
  - enriched feature columns from the trainer path
  - time-context columns
  - `outcome_label`
- Add fold cache under `artifacts/ag_runs/<run_id>/monte_carlo/cache/`:
  - `analysis.parquet`
  - `probs.parquet`
  - `payoffs.parquet`
- Add `load_or_compute_fold()` wrapper so first run computes and caches, later runs can use `--skip-predict`.
- Keep Tasks A–D behavior unchanged.
- Add task selector:
  - `--tasks A,B,C,D,E,F,G,H,I`
- Add SHAP feature resolver:
  - `--shap-artifact`
  - `--shap-top-features`
  - `--shap-top-n`
- Add Task E:
  - entry rules across `(stop_family × direction × fib_level × hour_bucket × SHAP-top-feature quartiles)`
- Add Task F:
  - TP ladder decision by `(stop_family × fib_level)` and probability band
- Add Task G:
  - calibration table from cached probabilities + realized labels
- Add Task H:
  - regime stability by splitting the test horizon and comparing rule rankings
- Add Task I:
  - win profile from full realized path outputs
- Refactor `simulate_paths()` so it can optionally return realized per-path outcomes for Task I.
- Add new outputs:
  - `task_E_entry_rules.json`
  - `task_F_tp_ladder.json`
  - `task_G_calibration.json`
  - `task_H_regime_stability.json`
  - `task_I_win_profile.json`
  - `summary.md`
  - cache files

## 3. Validation Gates

- `run_diagnostic_shap.py`
  - old-run postprocess works with no raw SHAP recompute
  - per-level cohort files exist for `236, 382, 500, 618, 786, 1000`
  - cohort row counts reconcile to total explained rows
  - archetype backfill works on `agtrain_20260415T015005138333Z`
  - per-level outputs match the manual spot-checks already produced
- `monte_carlo_run.py`
  - run A–D only after refactor
  - compare old vs new outputs after stripping volatile metadata fields like `generated_at_utc`
  - do not proceed to E–I until A–D match semantically
- Runtime expectation:
  - SHAP postprocess: small additive overhead
  - MC E–I: additive after cache, fast on reruns

## 4. Execution Order

1. Extend `run_diagnostic_shap.py`
2. Run `--postprocess-only` on `agtrain_20260415T015005138333Z`
3. Validate cohort and stability artifacts
4. Refactor `monte_carlo_run.py` cache + analysis frame
5. Prove A–D semantic parity
6. Add E–I
7. Re-run on the same bad run
8. Use the same upgraded scripts on the next clean run

---

## Locked contract — do NOT deviate in implementation

### `stability_bucket` rules (checked in this exact order, first match wins)

1. `DEAD`: `mean_abs_max < 0.005`
2. `STABLE_CORE`: `rank_max <= 20` AND `mean_abs_cv < 0.30` AND `top20_fold_count = 5`
3. `STABLE_MID`: `rank_max <= 50` AND `mean_abs_cv < 0.50` AND `top20_fold_count >= 3`
4. `VOLATILE`: `rank_range > 40` OR `mean_abs_cv >= 0.50`
5. `STABLE_WEAK`: `mean_abs_cv < 0.30` AND aggregate `mean_abs_shap < 0.05`
6. fallback: `UNCLASSIFIED`

### `LEAKAGE_SUSPECT` rule (conjunction — both must hold)

- Aggregate rank ≤ `--leakage-rank-threshold` (default 30) OR aggregate `mean_abs_shap > 0.10`
- Cross-cohort `mean_abs_cv < --leakage-cv-threshold` (default 0.10)

"Important everywhere, in nearly the same way" = suspect. "Tiny everywhere" with low CV = `DEAD`, not leakage.

### MC Task A–D semantic-identical parity gate

Before adding Tasks E–I, the refactored script must produce A–D JSON that diffs clean against the current A–D outputs on `agtrain_20260415T015005138333Z` after stripping ONLY:

- `generated_at_utc`
- Any absolute/derived path fields that move between invocations

Do NOT strip these — they are contract, not noise. If they move, diff MUST fail:

- `run_id`
- `seed`
- `note`
- threshold fields
- `n_paths`
- any numeric metric (EV, Sharpe, quantiles, PF, etc.)

### Execution discipline

- Implement step 1 → wait for review → run postprocess → validate → then step 2
- No launch of either script without explicit approval from Kirk
- No commit / push without explicit approval from Kirk
- All changes additive; existing consumers of current outputs keep working unchanged

---

## Cross-references

- `training-shap` skill — output contract this plan satisfies
- `training-monte-carlo` skill — output contract this plan satisfies
- `training-pre-audit` skill — gates before the upstream training run whose predictors feed these scripts
- `training-quant-trading` skill — leakage-detection and time-series discipline underlying the stability/calibration logic
- `AGENTS.md` → Training Skills Registry — registry entry for all of the above
