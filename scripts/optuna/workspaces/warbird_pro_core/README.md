# Warbird Pro V9 Core Workspace

Operator-facing workspace for the single Core AutoGluon card:

`2026-05-09 - Warbird Pro Autogluon Core`

Current status:

- Smoke/validation wrapper is wired into Optuna.
- `study.db` is created by the Core card smoke command.
- Full 1y Core build/training is still approval-gated.
- Smoke trials are wiring evidence only; they are not model-quality evidence.

Smoke card command:

```bash
python scripts/optuna/cards/core_training/2026_05_09_warbird_pro_autogluon_core.py \
  --mode smoke \
  --symbol-root ES \
  --timeframe 5
```

Expected default active study DB:

```text
scripts/optuna/workspaces/warbird_pro_core/experiments/es_5m/study.db
```

For the 15m prep lane, use:

```text
scripts/optuna/workspaces/warbird_pro_core/experiments/es_15m/study.db
```

Do not run full AutoGluon training from this workspace until the full 1y Core
dataset gate is green and Kirk approves launch.
