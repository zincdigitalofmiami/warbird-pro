---
name: training-hard-gate
description: Single-command hard gate for AutoGluon training + SHAP + Monte Carlo. Runs strict preflight checks, launches safe full-zoo training, then blocks if lineage/zoo/class-coverage/SHAP/MC integrity contracts fail. Use this instead of calling train_ag_baseline.py directly.
---

> **2026-04-26 indicator-only reset:** This training skill is legacy unless Kirk explicitly reopens the old warehouse AG architecture. Active modeling uses Pine/TradingView outputs only; do not use FRED, macro, local `ag_training`, or daily-ingestion training flows.


# Training Hard Gate

This skill enforces one deterministic command path that **blocks bad runs** before they waste more compute.

## Use this when

- Launching any real (non-dry) AG run
- You need train + SHAP + MC in one controlled execution
- You want hard failure on integrity drift

## Do not use

- `scripts/ag/train_ag_baseline.py` directly for production-candidate runs
- Manual train → SHAP → MC chains without gates

## Command

```bash
python3 scripts/ag/train_hard_gate.py
```

Recommended launcher:

```bash
python3 scripts/ag/train_hard_gate.py \
  --python-exec /usr/local/bin/python3 \
  --time-limit 3600 \
  --ag-max-memory-usage-ratio 2.5
```

Preflight only:

```bash
python3 scripts/ag/train_hard_gate.py --preflight-only
```

## What it blocks

1. Preflight contract breaches
- Canonical zoo guard failure
- Missing trainer safeguards (`allow_exact_matches=False`, lineage checks, provenance writes)
- Unresolved active `RUNNING` rows in `ag_training_runs` (stale rows are auto-reconciled first)
- `ag_training` row count below `EXPECTED_AG_TRAINING_ROWS_FLOOR`
- Stale hardcoded SHAP/MC caveat text in source scripts (grep per `training-pre-audit` check 15)
- Non-bag SHAP explainer branch coverage missing (per `training-pre-audit` check 14)
- Fold class-coverage preview shows any fold with `val_class_count < test_class_count` (per `training-pre-audit` check 13)

2. Unsafe training overrides
- Refuses passthrough flags that re-enable unsafe behavior:
`--allow-single-class-eval`, `--allow-partial-class-coverage`,
`--allow-unsafe-internal-ensembling`, `--num-bag-folds`,
`--num-stack-levels`, `--dynamic-stacking`, `--excluded-model-types`

3. Post-train integrity failures
- Missing top-level run artifacts (`command.txt`, `git_hash.txt`, `pip_freeze.txt`, etc.)
- Fold leaderboard not full-zoo / memory-skipped families
- Best-model lineage mismatch (`best_model` vs `score_test` vs persisted DB metrics)
- Validation/test class coverage gaps — any fold where `val_class_count < test_class_count`
- DB run status mismatch
- **Below-baseline fold escalation (added 2026-04-15):** for every fold, compute `test_macro_f1 - baseline_macro_f1`. 1 fold below baseline is a WARN; **≥ 2 folds below baseline BLOCKS** as `MODEL_UNDERPERFORMS_BASELINE` (no edge over majority-class prediction, regardless of mean-fold F1).

4. SHAP failures (consumes `artifacts/ag_runs/<RUN_ID>/shap/integrity.json`; see `training-shap` Gates A–F)
- Missing required SHAP outputs
- Invalid fold artifacts
- Gate A: stale bag / GBM-only / `valid_set f1_macro ~0.99` narrative in `summary.md` when `num_bag_folds == 0` AND full zoo is present
- Gate B: `MODEL_UNDERPERFORMS_BASELINE` (≥ 2 folds below baseline)
- Gate C: `FOLD_CLASS_COVERAGE_GAP` (any fold with val slice missing a class the test slice has)
- Gate D: `LEAKAGE_SUSPECT` count ≥ 1 → promotion blocked pending human review (do NOT auto-drop; root-cause first)
- Gate E: calibration off-rate. `< 0.30` OK; `0.30–0.70` → `CALIBRATION_UNRELIABLE` (summary.md must say so prominently; MC threshold-gating findings tagged suspect); `≥ 0.70` → `CALIBRATION_CATASTROPHIC` (promotion blocked)
- Gate F: non-bag explainer branch latent (SHAP script would `AttributeError` on non-bag full-zoo run)

5. Monte Carlo failures (consumes `artifacts/ag_runs/<RUN_ID>/monte_carlo/integrity.json`; see `training-monte-carlo` Gates A–E)
- Missing task outputs A–I
- **Gate A — Task E contract:**
  - `top_k_take` must have ≥ 10 rules (floor)
  - `top_k_take` must have ≥ 5 **positive-EV** rules (not an all-negative "take" list)
  - `top_k_take ∩ top_k_avoid = ∅` (zero overlap)
  - `top_k_avoid` must have ≥ 10 rules
  - Adaptive `min_rule_n` fallback must be documented (50 → 30 → 15, with `min_rule_n_final` emitted)
- Gate B: stale bag / GBM-only narrative in `summary.md` when run metadata says otherwise
- Gate C: Task H missing BOTH `rank_stability_verdict` AND `ev_stability_verdict` — or Spearman rho = 1.0 while ≥ 3 stop_families show `|ev_early - ev_late| / |ev_early| > 0.5` (rank-stable + EV-drifting MUST be flagged; it is NOT "STABLE")
- Gate D: Task G calibration off-rate ≥ 0.30 (same threshold as SHAP Gate E)
- Gate E: `summary.md` does not inherit upstream SHAP promotion block when SHAP blocked

## Report integrity cross-check

After SHAP + MC complete, hard-gate does a final content grep against both `summary.md` files to catch stale caveats that are emitted unconditionally from source:

```bash
RUN_CFG="artifacts/ag_runs/<RUN_ID>/run_config.json"
NBF=$(jq -r '.num_bag_folds' "$RUN_CFG")
FAM=$(jq -r '.family_count'   "$RUN_CFG")
for f in artifacts/ag_runs/<RUN_ID>/shap/summary.md \
         artifacts/ag_runs/<RUN_ID>/monte_carlo/summary.md; do
  [ "$NBF" = "0" ] && \
    grep -q "IID bag leakage\|valid_set f1_macro ~0.99\|bag-fold leakage" "$f" && \
    echo "REPORT_INTEGRITY_VIOLATION in $f — stale bag caveat on non-bag run"
  [ "$FAM" -gt 1 ] && \
    grep -q "GBM-only\|only LightGBM in leaderboard" "$f" && \
    echo "REPORT_INTEGRITY_VIOLATION in $f — stale GBM-only caveat on multi-family run"
done
```

Any `REPORT_INTEGRITY_VIOLATION` → `integrity_passed=false`, exit non-zero. The fix is ALWAYS to rewrite the caveat emission as runtime-conditional in `scripts/ag/run_diagnostic_shap.py` / `scripts/ag/monte_carlo_run.py` — NOT to silence the check.

## Success condition

The command exits 0 and prints:
- `run_id`
- `run_dir`
- `shap_dir`
- `monte_carlo_dir`
- `integrity_passed=true`
- `promotion_allowed=true` (false if LEAKAGE_SUSPECT, MODEL_UNDERPERFORMS_BASELINE, CALIBRATION_CATASTROPHIC, TASK_E_DEGRADED, or REPORT_INTEGRITY_VIOLATION is present, even when `integrity_passed=true` for informational purposes)

Any breach exits non-zero (`[gate] BLOCKED:` message).

## Known anti-patterns — the gate WILL NOT yield to any of these

- "The run is 99% done, let's just skip the check this time." No.
- "The stale caveat is just a cosmetic issue." No — it makes every report distrust the previous one, compounding over runs.
- "The Task E output is fine, there are just few rules." If `top_k_take = top_k_avoid` and all EV is negative, the rule surface is degenerate. That is not a find, that is a failure.
- "Rank is stable, so regime is stable." Rank stability with EV collapse is a regime failure. Both verdicts are required.
- "Fold 03 missed TP4_HIT but the other folds were fine." Per-class SHAP/MC for fold_03 × TP4_HIT is untrusted. Flag it; do not aggregate silently.

## Evidence log — what the tightened gates would have caught on `agtrain_20260415T165437712806Z`

| Gate | Would it have fired? | Why |
|------|---------------------|------|
| SHAP Gate A | YES | summary.md had bag-leakage caveat despite `num_bag_folds=0` + 7 families |
| SHAP Gate B | YES | fold_01 test_macro_f1 0.118 < baseline 0.150 (1 fold below — WARN, not block) |
| SHAP Gate C | YES | fold_03 val=5 classes, test=6 classes (TP4_HIT missing) |
| SHAP Gate D | YES | `tp1_dist_pts` flagged LEAKAGE_SUSPECT (would block promotion) |
| SHAP Gate E | YES | 67/84 off-calibration = 79.8% → CALIBRATION_CATASTROPHIC |
| SHAP Gate F | Pre-run | Non-bag branch was latent; pre-audit would have caught |
| MC Gate A | YES | top_k_take = top_k_avoid = 6 combos all-negative — BLOCK |
| MC Gate B | YES | Same hardcoded bag-leakage text in MC summary.md |
| MC Gate C | YES | Spearman rho = 1.0 but EV collapsed across all families late regime |
| MC Gate D | YES | Same 79.8% off-calibration → DRIFTING + CATASTROPHIC |
| MC Gate E | YES | SHAP block (LEAKAGE_SUSPECT + CATASTROPHIC) did not propagate to MC summary |
