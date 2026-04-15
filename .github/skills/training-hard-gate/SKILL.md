---
name: training-hard-gate
description: Single-command hard gate for AutoGluon training + SHAP + Monte Carlo. Runs strict preflight checks, launches safe full-zoo training, then blocks if lineage/zoo/class-coverage/SHAP/MC integrity contracts fail. Use this instead of calling train_ag_baseline.py directly.
---

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
- Orphan `RUNNING` rows in `ag_training_runs`
- `ag_training` row count below `EXPECTED_AG_TRAINING_ROWS_FLOOR`
- Stale hardcoded SHAP/MC caveat text in source scripts

2. Unsafe training overrides
- Refuses passthrough flags that re-enable unsafe behavior:
`--allow-single-class-eval`, `--allow-partial-class-coverage`,
`--allow-unsafe-internal-ensembling`, `--num-bag-folds`,
`--num-stack-levels`, `--dynamic-stacking`, `--excluded-model-types`

3. Post-train integrity failures
- Missing top-level run artifacts (`command.txt`, `git_hash.txt`, `pip_freeze.txt`, etc.)
- Fold leaderboard not full-zoo / memory-skipped families
- Best-model lineage mismatch (`best_model` vs `score_test` vs persisted DB metrics)
- Validation/test class coverage gaps
- DB run status mismatch

4. SHAP failures
- Missing required SHAP outputs
- Invalid fold artifacts
- Stale bagging warning text emitted for a clean run

5. Monte Carlo failures
- Missing task outputs A-I
- Task E degraded rule surface, overlap between take/avoid, or too few rules
- Task G calibration row floor not met
- Task H missing stability metrics
- Stale bagging/GBM-only warning emitted for a clean run

## Success condition

The command exits 0 and prints:
- `run_id`
- `run_dir`
- `shap_dir`
- `monte_carlo_dir`
- `integrity_passed=true`

Any breach exits non-zero (`[gate] BLOCKED:` message).
