---
name: training-quant-trading
description: Quant-trading discipline for time-series ML. Use when designing training splits, setting embargoes, interpreting leakage signals, handling session boundaries, and evaluating whether a model's reported metrics are trustworthy for real trading.
---

# Training — Quant Trading Discipline

Non-negotiable rules for training ML models on financial time-series data. Every rule here has burned real compute or real capital in the project's history.

## Hard rules

### 1. No random shuffle. Ever.

`random_state=42` on `train_test_split()` destroys time-series integrity. Always use walk-forward splits keyed on `session_date_ct`. The pipeline's walk-forward structure is in `scripts/ag/build_ag_pipeline.py::build_walk_forward_structure` and the trainer's in `scripts/ag/train_ag_baseline.py::build_walk_forward_folds`.

### 2. Session embargo ≥ 1 minimum

Between train and val, and between val and test, leave at least ONE full session of gap. MES 15m has 24h of bars per session — without embargo, same-session bars leak across the boundary. Trainer default: `--session-embargo 1`. Never lower.

### 3. AutoGluon's `num_bag_folds` default (5) is UNSAFE for time-series

AG's internal bagging uses IID random shuffle of the training data. On MES 15m, this puts bars from the same session into different bag children → the child's "held-out" fold is IID-adjacent to its training fold → LightGBM's internal `valid_set f1_macro` hits ~0.99 and collapses on real test to ~0.14.

**Always pass `--num-bag-folds 0 --num-stack-levels 0`** to the trainer unless you have a custom `FoldFittingStrategy` that respects session boundaries. This project does NOT yet have that custom splitter — so `0/0` is mandatory.

### 4. Walk-forward expansion, not rolling window (for now)

Each successive fold's training set is a superset of the prior (expanding window, not rolling). This matches the "more data is better" assumption for 2020-2026 which spans multiple regimes. If you believe regime drift is severe, switch to rolling and reduce min_train_sessions — but document the decision.

### 5. Feature-at-prediction-time rule

Every feature in `X` must be computable using only data available at `ts` (the bar close). Violations:
- Anchor features computed using the NEXT pivot (look-ahead)
- Macro features timestamped to calendar day that bleed into RTH open
- Stop variants that encode the outcome somehow

The `LEAKAGE_COLS` set in `scripts/ag/train_ag_baseline.py:72-93` is the canonical exclusion list. Respect it. When adding new features, explicitly audit: "Could this value be known at the interaction's `ts`?"

## Diagnosing leakage signals

### The "0.99 / 0.14 cliff" — observed on run `agtrain_20260415T015005138333Z`

Concrete numbers from the broken run this project has first-hand experience with:
- Per-bag-child `valid_set f1_macro` = 0.99+ during LightGBM fitting
- AG aggregate `Validation score = 0.186` on the fold
- `test_macro_f1 = 0.140`

That ~0.85 gap between bag-child valid_set and true test is **the canonical IID-bag-leakage fingerprint**. Any time you see it, the run's rankings are unreliable and the absolute numbers are meaningless. Canonical causes (in order of likelihood on this project):

1. **IID bag-fold split** (rule 3 above) — `num_bag_folds=5` with AG's default shuffle puts same-session bars in both sides of the child holdout
2. A feature column computed AFTER the outcome (e.g., `bars_to_tp1` accidentally left in features — should be in `LEAKAGE_COLS`)
3. A data join that back-fills future values (FRED "monthly" series joined forward-fill might leak Nov 2026 CPI release info into Oct 2026 rows if release-date convention is wrong)

### The "stacking-collapse" fingerprint

If every fold's leaderboard shows `Ensemble Weights: {'<single_model>': 1.0}` on every `WeightedEnsemble_L2/L3/L4`, stacking added zero diversity. This happens when:

- The L1 models time-truncate and produce low-variance predictions that AG's weighter can't differentiate
- OR the underlying data is contaminated and every model arbitrages the same leakage the same way (correlated errors)

In either case, stacking compute was wasted. This was observed on every fold of `agtrain_20260415T015005138333Z`.

### The "uniform importance across every cohort" fingerprint

When per-cohort SHAP (by fib_level / by direction / by stop_family / by hour_bucket) shows the same feature at roughly the same importance magnitude at **every** cohort slice, that feature is likely being used as a time-identity proxy, not as a genuinely regime-conditional signal. A real regime feature (e.g., VIX for equity vol regime) should have high importance in *some* cohorts and lower in others — uniformity is a tell.

On the broken run, 15 FRED features in the aggregate top-25 with near-identical cohort-level importance were the signal. `training-shap`'s `LEAKAGE_SUSPECT` conjunction (high importance AND low cross-cohort CV) is designed to flag exactly this pattern.

### The "realized class dist matches predicted class dist" trap

In Monte Carlo output, if `realized_class_dist` ≈ `predicted_class_dist` for every class, the model is returning ~marginal-frequency probabilities, not discriminative signal. This is a failure mode even without bagging leakage — means the model didn't learn useful patterns.

### The "best τ too high" signal

In `training-monte-carlo`'s Task C: if every stop family needs τ > 0.5 to flip profitable, the model has high-variance probabilities that rarely assert confidence. Probably overfitting per-fold; won't generalize.

### Schema-join gotcha: `id` vs `stop_variant_id`

Calibration code and any per-row join between SHAP artifacts and `ag_training` MUST use `stop_variant_id` as the unique row key, NOT `id`. On the current normalized AG schema:

- `ag_training` has 327,942 rows, 54,657 distinct `id` values (from `ag_fib_interactions`), 327,942 distinct `stop_variant_id` values (from `ag_fib_stop_variants`)
- `id` repeats 6× (one per stop family per interaction)

Using `id` in `pandas.merge(..., validate="one_to_one")` either raises or silently collapses/cartesian-expands the 6 rows. `stop_variant_id` is correct and is always present in `ag_training` + in every raw SHAP parquet (`META_COLS` includes it).

## Evaluation metric choice

For 6-class STOPPED/TP1..5 with ~78% STOPPED imbalance:

| Metric | Use when |
|--------|----------|
| `f1_macro` | You care equally about all classes (default — current trainer setting) |
| `f1_weighted` | You care proportionally; rare-class recall is not critical |
| `log_loss` | You want well-calibrated probabilities for Monte Carlo gating |
| `accuracy` | Almost never — majority-class baseline dominates |

`f1_macro` is what the trainer currently uses. Don't change without thinking.

## Position sizing discipline

- **Training:** 1 contract per interaction is the label-generating assumption. Do not train on Kelly-sized or volatility-sized labels — the label becomes recursive with the model output.
- **Backtesting:** 1 contract fixed in Monte Carlo. Later phases can apply sizing overlays.
- **Stops:** mechanical, known at entry. See `ag_fib_stop_variants` — six families are defined, model sees stop identity as a feature.

## Commission / friction model

- Canonical friction: **1 tick flat per trade = $1.25 per MES contract** (NinjaTrader Basic free account).
- Do NOT add round-trip commission, slippage, or brokerage spread unless explicitly asked. The user is firm on this.
- See `training-monte-carlo` for how this is applied.

## When in doubt

Before pushing a model forward, ask:
1. Is the val → test gap small (under 2x in log-loss, under 30% absolute in f1_macro)? If no, something is leaking.
2. Does `stop_family_id` SHAP importance make physical sense? Wider stops → more TP hits should be reflected in positive SHAP toward TP classes.
3. Do top Task-D combos (training-monte-carlo) make directional sense? "Longs in thin overnight liquidity with wide stops" being worst is plausible; "fib_level_touched=2 dominates everything" is a leakage warning.

## Related skills

- `training-pre-audit` — catches embargo / bag-fold mistakes at launch time
- `training-monte-carlo` — economic evaluation that exposes leakage via the probability-gating behavior
- `training-shap` — feature-level leakage audit
- `supabase-ml-ops` — broader Supabase + quant-ops reference (already in repo)
