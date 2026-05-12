<!-- markdownlint-disable-file -->

# Task Research Notes: AG Training Failure Review (Read-Only)

## Research Executed

### File Analysis

- scripts/ag/train_v9_locked.py
  - Validate-only execution passed end-to-end on the locked 15m export; schema, trade expansion, and embargoed splits are healthy.
- scripts/ag/train_hard_gate.py
  - Legacy gate still launches scripts/ag/train_ag_baseline.py and keeps legacy defaults (including 3600s time limit), which is inconsistent with V9 direct path.
- scripts/ag/monte_carlo_v9.py
  - OOS/IS splitting uses fixed date constants (OOS_START/IS_END), not the training run's split contract.
- scripts/ag/shap_v9.py
  - SHAP entrypoint has no split selector and runs on all reconstructed trades from CSV by default.
- models/warbird_pro_v9/locked_20260512_083803/v9_winner_clf_summary.json
  - Full model-suite artifact exists with 126 features and IS/VAL/OOS rows 22,654 / 4,830 / 4,830.
- docs/MASTER_PLAN.md
  - Active docs require Phase 4.5 SHAP + Monte Carlo gates tied to the same run before promotion.

### Code Search Results

- train_ag_baseline.py|time-limit|num-bag-folds|num-stack-levels in scripts/ag/train_hard_gate.py
  - Found legacy trainer coupling at lines 271 and 702; found legacy arg defaults including 3600s at line 738.
- OOS_START|IS_END|split in scripts/ag/monte_carlo_v9.py
  - Found hard-coded split constants and date filtering at lines 52, 53, 359, 361.
- add_argument("--predictor-dir"|"--csv"|"--output-dir"|"--label-col") in scripts/ag/shap_v9.py
  - Found no split argument; builds trades directly from full CSV at line 503.
- locked_20260512_083803 references
  - Found run-linked blocker language in docs/MASTER_PLAN.md lines 403, 427, 446.

### External Research

- #githubRepo:"autogluon/autogluon TabularPredictor fit num_bag_folds num_stack_levels dynamic_stacking calibrate predict_proba"
  - Upstream confirms: stacking requires bagging when enabled; best_quality presets use dynamic stacking behavior; predict_proba class-column behavior is explicit and order-sensitive.
- #fetch:https://auto.gluon.ai/stable/api/autogluon.tabular.TabularPredictor.fit.html
  - Upstream fit contract confirms hyperparameters dict controls trained model families, num_stack_levels constraints with bagging, dynamic_stacking behavior, and calibration caveats.
- #fetch:https://auto.gluon.ai/stable/api/autogluon.tabular.TabularPredictor.predict_proba.html
  - Upstream predict_proba contract confirms binary output shape/options and class-label ordering expectations.

### Project Conventions

- Standards referenced: AGENTS.md authority order, docs/MASTER_PLAN.md Phase 4.5 gating, training-ag-best-practices skill, point-in-time-ml-audit skill.
- Instructions followed: read-only audit, no source-code modifications, evidence-first findings.

## Key Discoveries

### Project Structure

V9 production training is direct via scripts/ag/train_v9_locked.py and not via scripts/ag/train_hard_gate.py. The locked model-suite artifact exists at models/warbird_pro_v9/locked_20260512_083803, but promotion is blocked pending SHAP/Monte Carlo provenance closure against the exact run.

### Implementation Patterns

- Trainer contract is strong: schema validation + deterministic split + 24-bar label horizon + 25-bar embargo.
- Gate contract is weak operationally: SHAP/MC are not forced to consume the exact OOS split used at training time.
- Legacy path remains callable and can misroute users into baseline trainer semantics.
- Read-only OOS diagnostics on the locked artifact show entry/tp heads are strong while stop head is weak relative to baseline entropy:
  - entry: log_loss 0.4844, AUC 0.8298 (about 25.3% better than entropy baseline)
  - tp: log_loss 0.4873, AUC 0.8338 (about 25.1% better than entropy baseline)
  - stop: log_loss 0.6433, AUC 0.6882 (about 6.8% better than entropy baseline)

### Complete Examples

```bash
# Read-only validation of V9 training contract (executed)
source .venv/bin/activate && python3 scripts/ag/train_v9_locked.py --validate-only

# Key output:
# validate-only PASS
# features: 126
# IS/VAL/OOS rows: 22654 / 4830 / 4830
```

```python
# Legacy coupling evidence (from scripts/ag/train_hard_gate.py)
cmd = [
    args.python_exec,
    "scripts/ag/train_ag_baseline.py",
    "--time-limit", str(args.time_limit),
    "--num-bag-folds", "0",
    "--num-stack-levels", "0",
]
```

### API and Schema Documentation

- AutoGluon fit API confirms stacking/bagging interplay and dynamic stacking semantics.
- AutoGluon predict_proba API confirms binary output/class-order handling requirements.
- Internal V9 summary confirms run dimensions and per-head score surfaces for entry/tp/stop/mfe/mae.

### Configuration Examples

```yaml
current_v9_state:
  trainer: scripts/ag/train_v9_locked.py
  run: models/warbird_pro_v9/locked_20260512_083803
  features: 126
  split_rows:
    train: 22654
    val: 4830
    oos: 4830
blocking_issue:
  shap_mc_not_bound_to_training_split: true
```

### Technical Requirements

- Preserve V9 direct entrypoint as canonical.
- Prevent accidental legacy gate usage for V9 runs.
- Bind SHAP/MC to the exact run split provenance (same row set used by training OOS).
- Keep read-only audit stance until fix implementation is approved.

## Recommended Approach

Adopt a single run-bound validation contract:

1. Keep scripts/ag/train_v9_locked.py as the only sanctioned V9 trainer.
2. Add split-manifest provenance (train/val/oos row boundaries, CSV hash, commit hash) per run.
3. Require scripts/ag/shap_v9.py and scripts/ag/monte_carlo_v9.py to accept and enforce that split manifest.
4. Gate promotion only when SHAP + MC artifacts are generated from the same run id and same split manifest.
5. Mark scripts/ag/train_hard_gate.py as legacy-only fail-closed for V9 invocations.

## Implementation Guidance

- **Objectives**: Eliminate entrypoint drift, enforce run-linked SHAP/MC validation, and make promotion-proof provenance explicit.
- **Key Tasks**: Add split manifest output in trainer; add split-manifest inputs to SHAP/MC; remove fixed-date OOS logic from MC; add V9 guard in hard-gate path.
- **Dependencies**: Existing locked export CSV, existing run artifact layout, AutoGluon predictor loading behavior, Phase 4.5 contract in docs/MASTER_PLAN.md.
- **Success Criteria**: A single command chain can prove that training, SHAP, and MC all reference the same run id, same CSV hash, and same OOS row slice.