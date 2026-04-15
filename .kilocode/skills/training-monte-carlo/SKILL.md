---
name: training-monte-carlo
description: Hi-def Monte Carlo P&L deep-dive on a completed AutoGluon training run. Produces entry-rule tables, per-stop-family TP-ladder decisions, probability-threshold sweeps, calibration diagnostics, win-profile anatomy, and regime-stability checks. Outputs directly answer the project's core trading questions — when to enter, when to TP, what wins look like, what's broken. NinjaTrader Basic (free) flat 1-tick fee. MES $5/point. 1-contract fixed sizing.
---

# Training — Monte Carlo Deep Dive (Hi-Def)

**Locked execution plan:** `docs/plans/2026-04-15-hi-def-shap-mc-implementation.md`. Strip-list for A-D parity + cache format + task contracts are authoritative in that plan — do not deviate.

## Project mission this skill serves

**When to enter. When to take profit. What wins look like. What's broken.**

Every MC artifact must map to one of four trading decisions:
1. **Entry gate:** under what market conditions should the model even consider a trade?
2. **Stop-family choice:** given the setup, which stop_family maximizes risk-adjusted EV?
3. **TP-ladder decision:** at what model confidence does it make sense to hold for TP2, TP3, TP5 vs exit at TP1?
4. **Rejection list:** what conditions must be explicitly avoided (negative-EV even after gating)?

If an output doesn't inform one of those decisions, it's noise. Drop it.

## Economic model — fixed, do not negotiate

- **Friction:** 1 tick flat per trade = **$1.25** per contract (NinjaTrader Basic free account)
- **Position size:** 1 contract, fixed
- **MES multiplier:** $5/point
- **Payoff per class:** exit at named TP/SL price exactly (matches training-label assumption)

Do not add commission, slippage, per-side doubling, or broker-tier fees. User has been explicit. This is non-negotiable across every MC run.

## Required outputs

All under `artifacts/ag_runs/<RUN_ID>/monte_carlo/`:

### Existing (must still be produced)

| File | Content |
|------|---------|
| `task_A.json` | Per-fold + aggregated stop_family rollups: EV/trade, Sharpe, MC cumulative P&L quantiles, max drawdown, win rate, profit factor, predicted vs realized class distribution, win anatomy |
| `task_B.json` | Per-stop_family × entry-dimension breakdowns: direction, archetype, fib_level_touched, is_rth_ct, is_opening_window_ct, ml_exec_state_code, hour_bucket, quartile-bucketed confluence_quality/rvol/atr14/adx/rsi14 |
| `task_C.json` | Threshold sweep: τ ∈ {0.05, 0.10, …, 0.90} × stop_family, gated by P(TP any) ≥ τ |
| `task_D.json` | Top / bottom K combos across {stop_family_id, direction, hour_bucket, archetype}, ranked by EV/trade |

### Hi-def additions (new or bolstered)

| File | Content |
|------|---------|
| `task_E_entry_rules.json` | Per-cohort actionable entry rules: (stop_family × direction × fib_level × hour_bucket × top-SHAP-feature quartile) tuples with n_trades ≥ 50, sorted by (5th-percentile EV, Sharpe). Top 30 rules + bottom 30 rejections |
| `task_F_tp_ladder.json` | Per-stop_family × per-fib-level: at probability threshold τ for each TP class, what's the expected exit EV if we hold for that level vs exit earlier? Dynamic TP-target decision tree |
| `task_G_calibration.json` | Per-cohort calibration: predicted_mean_P vs realized_frequency per class. Over/underconfidence flags |
| `task_H_regime_stability.json` | Split test slice into early/late halves. Does the top stop_family × best τ from task_C flip between halves? If yes, model doesn't generalize through regime shifts |
| `task_I_win_profile.json` | What wins look like per stop_family: streaks, runs, time-to-TP distribution, mean $ per TP class, max-single-win, dollar-time-under-water |
| `summary.md` | Human-readable, opinionated. Sections mandated below. |

## `summary.md` required sections

The summary is the primary deliverable for a human reader. It MUST include, in this order:

### 1. `## TL;DR — What to trade`

Top 5 actionable rules from task_E, each with:
- The rule (stop_family + direction + hour_bucket + fib_level + feature gate)
- n_trades per year (extrapolated from test slice)
- MC 5th-percentile EV (worst-case P&L floor)
- Implied max drawdown p95
- One-sentence "why this works per MC"

### 2. `## TL;DR — What to avoid`

Top 5 rejection conditions from task_E bottom list. Format same as above but with negative EV called out.

### 3. `## Stop-family verdict`

Ranked table from task_A aggregated by (EV/trade, Sharpe, profit factor, best_tau_needed). One-sentence recommendation per family — "use as default" / "avoid except when X" / "only at τ > 0.40 which rarely fires".

### 4. `## TP-ladder decision trees`

Per stop_family, a compact decision tree from task_F:
```
If stop_family = ATR_1_0:
    If P(TP_any) < 0.10 → DON'T TAKE
    If 0.10 ≤ P(TP_any) < 0.25 → exit at TP1
    If 0.25 ≤ P(TP_any) < 0.40 AND P(TP3+) > 0.04 → hold for TP2
    If P(TP3+) > 0.08 AND anchor_swing_velocity Q4 → let run to TP3+
```

Rules MUST be driven by task_F calibration-validated probabilities.

### 5. `## Diagnostics — what's broken`

Required sub-sections:

**Calibration verdict** (from task_G):
| cohort | class | predicted | realized | ratio | verdict |
|---|---|---|---|---|---|

Flag ratios outside [0.7, 1.3] as POORLY CALIBRATED. These cohorts' MC numbers are unreliable.

**Regime stability verdict** (from task_H):
Does early-half best config match late-half best config? If not, model is regime-fragile. Flag specific features whose importance flipped (requires SHAP cross-ref).

**Leakage signal** (cross-ref with SHAP summary.md):
If SHAP flagged leakage SUSPECT, add: "MC absolute $ figures are unreliable. Trust rankings only."
If SHAP flagged LIKELY CLEAN, add: "MC figures are reportable; proceed with entry/TP rules."

**Confidence/conviction gap**:
At the best τ per stop_family, does realized EV match analytical EV? If realized << analytical, model is overconfident → MC rule outputs should be discounted by the gap ratio.

### 6. `## Win profile (what wins look like)`

Per stop_family, from task_I:
- Typical winning trade: size, duration, which TP level hit
- Winning streak distribution (consecutive wins mean, max, quantiles)
- Time-to-TP by class (how long does a TP3 hit take on average)
- Max single win $
- Worst time-under-water (longest losing streak $ drawdown)

### 7. `## Cross-ref to SHAP`

Table mapping MC-surfaced edges to SHAP-surfaced features:
| MC finding | Supporting SHAP |
|---|---|
| ATR_1_0 + shorts + ETH_PRE_RTH is best | SHAP: direction #X, hour_ct #Y, fib_level_touched cohort behavior |
| FIB_NEG_0382 + longs + ETH_POST_RTH is worst | SHAP: direction sign flip in cohort |

If SHAP didn't run, note "SHAP cross-ref missing — run training-shap before finalizing."

### 8. `## Caveats`

Always include:
- Source run leakage status (SUSPECT / LIKELY CLEAN / CLEAN — pull from SHAP verdict)
- Minimum trade-count threshold used (rules with n < threshold dropped)
- Friction model ($1.25 flat, confirm)
- Indicator settings FROZEN (D=4/Depth=20/T=0.50/MinFib=0.5 currently — link to `training-indicator-optimization` to vary)

## Method additions for hi-def outputs

### Task E — Entry rules (builds on task_D combos)

Extend the combo-finder dimensions beyond `{stop_family, direction, hour_bucket, archetype}` to include quartile-bucketed versions of the top-SHAP-identified numeric features (`confluence_quality_q`, `rvol_q`, `atr14_q`, `fib_range_q`).

For each combo with n_trades ≥ 50:
- Compute analytical EV + MC quantiles
- Compute MC 5th-percentile (conservative worst-case)
- Compute implied Sharpe (analytical EV / analytical stdev)
- Score = 0.5 × MC_p5_EV + 0.3 × Sharpe + 0.2 × (n_trades / max_n_trades)

Top 30 by score → "take" list. Bottom 30 by score → "avoid" list.

### Task F — TP-ladder decision

Per stop_family × fib_level, build a decision surface. For each row in test slice:
- Model emits P(STOPPED), P(TP1_ONLY), ..., P(TP5_HIT) via predict_proba
- Compute cumulative P(TP_n or better) = Σ_{c ≥ n} P(c)
- Analytical EV assuming "hold for TP_n" = Σ_{c ≥ n} P(c) × payoff(c) + P(STOPPED) × -sl_dist − (1 − Σ) × payoff(TP_{n−1})
- Best TP target = argmax_n EV(hold_for_TP_n)

Bin by threshold τ on P(TP_any): for each bin, what's the modal best-TP-target? Emit as decision tree.

### Task G — Calibration

Per-cohort (stop_family × fib_level × direction):
- `predicted_freq[c]` = mean of predicted probabilities across rows in cohort
- `realized_freq[c]` = empirical frequency from ground-truth outcome labels
- Ratio = realized / predicted (target = 1.0)
- Chi-square test on distribution equality

Log all cohorts to JSON. Flag cohorts with |ratio − 1| > 0.3 for any class with realized_freq > 0.01.

### Task H — Regime stability

Split aggregated test slice in half chronologically (by `ts`). Run task_A + task_C on each half separately. Compare:
- Best stop_family: same or different?
- Best τ: same or different?
- EV rank correlation: Spearman ρ across halves

ρ < 0.7 → regime-fragile. Document specific flips.

### Task I — Win profile

Per stop_family:
- From MC paths: streaks of consecutive winning / losing trades → histogram + quantiles
- From realized class distribution: mean $ per class, combined into "what wins look like" summary
- Compute cumulative_pnl trajectory per path; extract underwater durations

## Implementation notes

- Extend `scripts/ag/monte_carlo_run.py` to produce tasks E-I — script additions should be additive, not replacing existing task_A-D behavior
- Cache `predict_proba` output per fold — running all 9 tasks + cohort variants on fresh predicts would take hours; one predict + reuse arrays is minutes
- `task_F` requires per-row `predict_proba` for ALL 6 classes — already produced for task_A
- `task_G` requires raw `outcome_label` column to compare against — pull from analysis frame before feature drop
- `task_H` halving: use `ts` median as the split; log actual boundary in task_H.json
- `task_I` streaks: compute per simulated path, aggregate quantiles across paths

### `prepare_fold()` MUST return an analysis frame, not the old base frame

The legacy `prepare_fold()` returned `(base, probs, feature_cols)` — but `base` is pre-feature-engineering and lacks the enriched columns (FRED series, econ_calendar, time-context derivations like `hour_ct`, `dow_ct`). Task E needs to slice by top-SHAP features that may live in the enriched frame. Refactor contract:

```
prepare_fold() -> (analysis_frame, probs, feature_cols)
```

Where `analysis_frame` contains:
- All fields currently used by tasks A–D (direction, stop_family_id, entry_price, tp1..5_price, sl_dist_pts, ts, outcome_label, fib_level_touched, archetype, stop_variant_id)
- **Plus enriched columns** from the trainer path (FRED series, econ_calendar) — so Task E can filter on any SHAP-top feature
- **Plus time-context columns** (`hour_ct`, `dow_ct`, `hour_bucket`) — so breakdowns work without re-derivation
- Positionally aligned with `probs` (same row count and order)

Without this refactor, Task E breaks as soon as SHAP's top features include `fred_*` or `econ_*` columns.

### Cache format (per fold)

Under `artifacts/ag_runs/<RUN_ID>/monte_carlo/cache/fold_0N/`:

| File | Content |
|---|---|
| `analysis.parquet` | The analysis_frame described above |
| `probs.parquet` | (N_rows, 6) class-probability DataFrame with columns `pred_p__STOPPED`, `pred_p__TP1_ONLY`, ... (or equivalent `.npy` if memory-mapped) |
| `payoffs.parquet` | (N_rows, 6) dollar-payoff matrix computed via `compute_payoff_matrix` |

With `--skip-predict`, subsequent task E-I runs load from cache instead of reloading predictors. First full run warms the cache; subsequent iterations on tasks E-I complete in under 10 min.

### A–D semantic-identical parity gate (regression required before E-I)

Before adding tasks E-I, the refactored script must produce task_A-D JSON that diffs CLEAN against the existing `agtrain_20260415T015005138333Z` task_A-D after stripping ONLY:

- `generated_at_utc`
- Any absolute/derived path fields (`*_path`) that move between invocations

Do NOT strip — every field below is contract, and if it moves, the parity diff MUST fail:
- `run_id`
- `seed`
- `note` (free-text caveat)
- threshold fields (`thresholds`, `min_rule_n`, etc.)
- `n_paths`
- every numeric metric (EV, Sharpe, MC quantiles, PF, win_rate, etc.)

The parity check is the gate: if diffs appear beyond the narrow strip-list, the refactor introduced a behavior change, and E-I work does NOT start until A-D diffs clean.

## What each task answers for the trader

| Task | Trader's question it answers |
|------|------------------------------|
| A | "Which stop family is least bad overall?" |
| B | "In which market conditions does each stop family hold up?" |
| C | "At what model confidence does each stop family flip to positive EV?" |
| D | "What specific (stop × direction × hour × archetype) combos should I target / avoid?" |
| **E** | **"If I take all trades matching THIS rule, what's my worst-case annual P&L?"** |
| **F** | **"When the model predicts X probabilities, should I exit at TP1 or hold for TP3?"** |
| **G** | **"Can I trust the model's probabilities as calibrated real-world frequencies?"** |
| **H** | **"Did the best rule from early 2025 still work in late 2025, or do I need to re-train per regime?"** |
| **I** | **"What does a typical winning trade / losing streak actually look like for this stop family?"** |

## Post-run integrity gates (added 2026-04-15 after agtrain_20260415T165437712806Z)

Every MC run MUST produce a top-level `integrity.json` alongside `summary.md` capturing these verdicts. `training-hard-gate` consumes this file. MC is NOT complete until every gate is evaluated.

### Gate A — Task E viability (the gate that would have caught the degraded April-15 run)

Task E output must satisfy ALL of:

1. `top_k_take` contains **at least 10 rules** (floor).
2. `top_k_take` contains **at least 5 positive-EV rules** (not all-negative — a "take" list full of negative EV is not a take list, it's the least-bad rejection list).
3. `top_k_take ∩ top_k_avoid = ∅` (zero overlap — same rule cannot be both taken and avoided).
4. `top_k_avoid` contains at least 10 rules.

If any fails → `integrity.json.task_e_verdict = "DEGRADED"`, `summary.md` leads with "NO DEPLOYABLE ENTRY RULES — task_e degraded" banner, `promotion_allowed=false`.

**Adaptive min_rule_n fallback is mandatory.** Task E must try `min_rule_n = 50`, then drop to 30, then 15, emitting a `min_rule_n_final` value and a dimension-reduction log. If 15 still fails to produce 10 positive-EV rules, the rule surface is genuinely barren — that's a finding, not an error, but `TASK_E_DEGRADED` fires either way.

Evidence from `agtrain_20260415T165437712806Z`: `top_k_take = top_k_avoid = 6 combos, all negative EV`. That's not "no edge available" — the scan space was too narrow and the take/avoid sets collapsed onto the same degenerate combos. Adaptive fallback + dimension expansion would have surfaced this.

### Gate B — Narrative caveat contract (same rule as training-shap Gate A)

`summary.md` text MUST NOT contain stale caveats that contradict run metadata:

- `"IID bag leakage"` / `"valid_set f1_macro ~0.99"` / `"bag-fold"` — only if `run_metadata["num_bag_folds"] > 0`.
- `"GBM-only"` — only if `run_metadata["family_count"] == 1`.

Every caveat must be runtime-conditional in `monte_carlo_run.py`, not a hardcoded string. Evidence: `agtrain_20260415T165437712806Z` summary.md still emitted bag-leakage warnings despite `num_bag_folds=0` + 7 families. Source: `scripts/ag/monte_carlo_run.py:1209`. The skill can't fix the script but MUST fail the gate at integrity time.

### Gate C — Rank stability vs EV stability (task_H)

Spearman rho = 1.0 on stop-family ranks is NOT proof of model stability. The absolute EV values can collapse from +$60/trade early to -$10/trade late while still preserving rank order (every family loses equally). Rank-stable + EV-unstable means "the bad families stayed bad and the good families got worse" — that is a regime failure, not a regime pass.

MC Task H MUST emit BOTH verdicts:

- `rank_stability_verdict ∈ {STABLE, FRAGILE, UNKNOWN}` (Spearman rho ≥ 0.7 → STABLE)
- `ev_stability_verdict ∈ {STABLE, DRIFTING, COLLAPSING}` — compute per-stop-family `|ev_early - ev_late| / max(|ev_early|, 1e-6)`. If ≥ 3 families show drift > 0.5 → DRIFTING; if ≥ 3 families show drift > 1.0 (sign flip) → COLLAPSING.

Final verdict table in summary.md MUST show both columns. Promotion is blocked if `ev_stability_verdict != STABLE` regardless of rank stability.

Evidence from `agtrain_20260415T165437712806Z`: rho = 1.0 (STABLE), but "absolute EV shifted sharply down from early to late regime for every stop family" per the report. That IS drift — the current skill language didn't name the distinction, so the verdict read STABLE and the finding was buried.

### Gate D — Calibration threshold (same contract as training-shap Gate E)

`task_G_calibration.json` off-calibration count:

- `off_rate < 0.30` → `calibration_verdict = OK`
- `0.30 <= off_rate < 0.70` → `calibration_verdict = UNRELIABLE`, MC threshold-gating findings must be tagged suspect in summary.md
- `off_rate >= 0.70` → `calibration_verdict = CATASTROPHIC`, MC absolute EV numbers must not be reported as edge; run is probe-only

Evidence: 67 of 84 rows (79.8%) off-calibration on `agtrain_20260415T165437712806Z` — should have tripped CATASTROPHIC.

### Gate E — Model-level promotion block propagation

If SHAP's `integrity.json.promotion_allowed = false` (from LEAKAGE_SUSPECT or MODEL_UNDERPERFORMS_BASELINE), MC's summary.md MUST inherit that block visibly:

```
## PROMOTION BLOCKED — upstream SHAP integrity failed
Reason: <SHAP.integrity.json.promotion_blocked_reason>
MC findings below are INFORMATIONAL ONLY. Do NOT deploy rules from this run.
```

MC can still run for diagnostic value, but its rules cannot be promoted.

## Quality gates — checklist before declaring complete

- [ ] All 9 tasks (A-I) produce JSON output files
- [ ] `summary.md` contains all 8 required sections
- [ ] Calibration verdict table populated with cohorts
- [ ] TP-ladder decision tree present per stop_family
- [ ] Top-5 "what to trade" rules have numerical risk/reward
- [ ] Top-5 "what to avoid" rules have numerical loss floors
- [ ] Regime stability verdict explicit — **BOTH rank and EV**: `rank_stability_verdict` AND `ev_stability_verdict`
- [ ] Leakage verdict pulled from SHAP or explicitly marked "SHAP not run — rerun required"
- [ ] Win profile quantiles present per stop_family
- [ ] Cross-ref to SHAP table (or explicit "missing" note)
- [ ] `integrity.json` produced with Gates A–E verdicts
- [ ] `integrity.json.task_e_verdict` ∈ {OK, DEGRADED} with `top_k_take_count`, `positive_ev_count`, `take_avoid_overlap_count`, `min_rule_n_final`
- [ ] `integrity.json.promotion_allowed` is populated and propagates SHAP's block if present
- [ ] No hardcoded bag-leakage / GBM-only strings appear in `summary.md` for `num_bag_folds=0` + full-zoo runs
- [ ] If Task E is DEGRADED, summary.md LEADS with the degraded banner (not buried in diagnostics)

If any checkbox misses → MC run is incomplete. Do not promote or report findings to the user as "final" until complete.

## Known source-run caveats

- **Leakage contamination.** If source run has IID bag-fold leakage (`valid_set f1_macro ~0.99` with test `~0.14`), MC absolute $ figures are unreliable. Rankings may still be directionally useful. Always quote the leakage status upfront in summary.md.
- **Low-sample cohorts.** `--min-trades` defaults to 50. Cohorts below this are dropped from rules. For rare levels (fib_level_touched = 236 has ~9k rows aggregate but per-fold × per-hour cuts can dip below 50).
- **Predictor feature drift.** NaN-pad missing FRED columns per `predict_probs_aligned`. Do NOT error on missing columns.

## Related skills

- `training-shap` — upstream input; MC references SHAP top features for task_E dimension expansion and cross-ref table
- `training-quant-trading` — time-series discipline explaining why val→test gaps exist
- `training-pre-audit` — catches training problems before MC inherits them
- `training-indicator-optimization` — what to do when every stop_family is negative-EV even after gating (change the data, not the model)
- `training-tv-backtesting` — manual validation of MC-surfaced rules on TV strategy tester

## When MC shows no tradeable edge

If after task_C threshold-gating and task_E entry-rule filtering, no rule achieves positive 5th-percentile EV with n ≥ 200 trades/year → the model has no deployable edge on this indicator surface. Two options:

1. **Retrain on cleaner / better-engineered data.** Run `training-indicator-optimization` to find better fib settings; re-run pipeline.
2. **Accept defeat and iterate feature engineering.** Look at SHAP for the weakest high-importance features — are they noisy? Can they be replaced with something cleaner?

Do NOT deploy a "best of worst" rule from a run with no positive-EV options. Flag explicitly in summary.md.
