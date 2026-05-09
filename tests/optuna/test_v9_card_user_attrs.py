"""DEPRECATED 2026-05-09 — Hybrid+ 4-card structural contract tests.

Original tests verified the four Hybrid+ profile modules
(warbird_pro_v9_exit_cpcv, warbird_pro_v9_entry_filter_cpcv,
warbird_pro_v9_ag_meta_cpcv, warbird_pro_v9_joint_challenger) satisfied the
runner.py contract and emitted required ag_* user_attrs.

The Hybrid+ chain was retired in favor of the single Core AutoGluon card
(scripts/optuna/cards/core_training/2026_05_09_warbird_pro_autogluon_core.py).
All four profile modules now raise SystemExit on import. These tests are
skipped wholesale.

Replacement test target: a Core-card structural contract test will be added
when the Core card body lands (currently under construction). It will verify:
  * AG config matches the locked spec (preset='best_quality',
    num_bag_folds=0, num_stack_levels=0, dynamic_stacking=False,
    eval_metric='log_loss', calibrate=True, time_limit=7200)
  * Full 7-family hyperparameters dict is present (GBM x2, CAT, XGB, RF x2,
    XT x2, NN_TORCH, FASTAI)
  * Triple-barrier label spec (+10 / -5 / 24 bars / drop neither-hit)
  * Inference threshold = 0.75
  * Session as feature, not pre-filter
"""
from __future__ import annotations

import pytest

pytest.skip(
    "Hybrid+ 4-card chain deprecated 2026-05-09. Replaced by Core AutoGluon card. "
    "See docs/MASTER_PLAN.md and scripts/optuna/indicator_registry.json (warbird_pro_core).",
    allow_module_level=True,
)
