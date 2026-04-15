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

## Named failure signals (added 2026-04-15 after agtrain_20260415T165437712806Z)

These are the canonical failure signals for this project. Every report that discusses trust/promotion must reference this vocabulary.

### Rank stability ≠ EV stability

A Task-H regime check can report `Spearman rho = 1.0` (rank stable across early vs late halves) AND simultaneously show that every stop family's **absolute EV** collapsed from positive to negative between halves. That is NOT a stability pass — it means the bad families stayed bad and the good families got worse.

Canonical rule: always emit BOTH `rank_stability_verdict` AND `ev_stability_verdict`. Promotion requires both to be STABLE. Evidence: `agtrain_20260415T165437712806Z` — rho 1.0, EV uniformly collapsed late. The run's stability narrative was misleading until this distinction was enforced.

### Below-baseline fold

A fold is "below baseline" when `fold_summary.test.macro_f1 < fold_summary.majority_baseline.test.macro_f1`. This means the model loses to a classifier that always predicts `STOPPED` (the majority class) on that fold.

- 1 fold below → WARN; often regime noise, still a weak-signal candidate
- ≥ 2 folds below → `MODEL_UNDERPERFORMS_BASELINE`; do NOT advance to promotion regardless of mean-fold F1

Evidence: fold_01 on `agtrain_20260415T165437712806Z` (test 0.118 vs baseline 0.150). One fold; combined with other integrity flags, the overall run was not promotable. This signal lives upstream of SHAP/MC — by the time SHAP produces importance, below-baseline folds already mean "this fold's importance is noise."

### LEAKAGE_SUSPECT propagation

SHAP's `drop_candidates.csv` can raise `reason=LEAKAGE_SUSPECT` on a feature that has near-uniform importance across every cohort. When that happens, the feature is either:

- **Actual leakage** (time-identity proxy, future data bled in) — in which case the training surface needs a fix before ANY promotion
- **Real-but-structural signal** that happens to look uniform (e.g., `tp1_dist_pts` is target-derived and shows uniform importance because it's tightly correlated with the stop-family geometry used to generate it)

Either way: do NOT auto-drop the feature. Human-review required. Promotion is blocked until root cause is named and either the feature is removed + retrained, or the human explicitly approves "this is structural, not leakage."

Evidence: `tp1_dist_pts` flagged LEAKAGE_SUSPECT on `agtrain_20260415T165437712806Z` — but `tp1_dist_pts` is entry-time-computable (entry_price vs tp1_price where tp1_price comes from fib geometry at entry). It may be structural-not-leakage; that is a finding requiring human adjudication, not a silent drop.

### Realized = predicted class distribution

If Monte Carlo reports that per-cohort realized class frequency matches predicted class frequency almost exactly, the model is probably returning marginal frequencies (predicting at the prior) rather than discriminative signal. Even without bag leakage, this means the model learned nothing useful about per-cohort conditional distributions. Confirm by inspecting `task_G_calibration.json` — if every cohort's ratio is near 1.0 AND the predicted spread is near 0, the model has no edge.

### Rank-stable + wide-confidence-range trap

A model can be rank-stable across folds AND have a very wide range between its most-confident and least-confident predictions — and still miss all the rare classes entirely. Check `ZERO_PREDICTION_MISS` rows in SHAP `calibration_check.csv`: if the model predicts `P(TP4_HIT) = 0` for every row while TP4_HIT occurs at 0.1% of rows, the model will NEVER trigger TP4 thresholds in MC — even though its overall accuracy looks fine. This is the escape that makes rare-class P&L analysis useless. Hard threshold: if `ZERO_PREDICTION_MISS` count > 0 for any class with realized_freq ≥ 0.005, flag it in summary.md.

## Report-integrity discipline

Every SHAP and MC `summary.md` must be runtime-conditional on actual run metadata. Hardcoded caveats like "num_bag_folds=5 IID leakage" appearing on a `num_bag_folds=0` run make every subsequent report distrust itself.

Rule: grep any narrative source for these strings and wrap them in `if run_metadata["num_bag_folds"] > 0:` (or equivalent) conditions:
- `"IID bag leakage"`
- `"valid_set f1_macro ~0.99"`
- `"bag-fold leakage"`
- `"GBM-only"`
- `"only LightGBM in leaderboard"`

`training-pre-audit` check 15 enforces this statically. `training-hard-gate` enforces it at integrity time.

## Related skills

- `training-pre-audit` — catches embargo / bag-fold mistakes at launch time; check 13 previews per-fold class coverage; checks 14-15 catch SHAP non-bag branch + hardcoded caveats
- `training-monte-carlo` — economic evaluation that exposes leakage via the probability-gating behavior; Gate C enforces rank-vs-EV stability distinction
- `training-shap` — feature-level leakage audit; Gates A-F enforce narrative integrity / below-baseline / class coverage / LEAKAGE_SUSPECT / calibration / non-bag branch
- `training-hard-gate` — single command that runs all gates and blocks promotion on any failure
- `supabase-ml-ops` — broader Supabase + quant-ops reference (already in repo)
