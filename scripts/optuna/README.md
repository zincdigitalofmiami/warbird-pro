# Warbird Optuna Workspace

Canonical Optuna state now lives under `scripts/optuna/`, not `data/optuna/`.

## Layout

- `runner.py`
  Shared Optuna CLI for registry-backed indicator and strategy profiles.
- `warbird_optuna_hub.py`
  Card dashboard and child `optuna-dashboard` launcher.
- `vscode_doctor.py`
  VS Code extension and sidecar diagnostics.
- `runtime_health.py`
  One-command current-runtime-only pass/fail probe for the live hub + child APIs.
- `prune_runtime_logs.py`
  Archives stale child logs under `/tmp/warbird-optuna-hub/` without touching active lanes.
- `indicator_registry.json`
  Registry of supported Optuna lanes.
- `workspaces/<indicator_key>/`
  Per-indicator canonical Optuna home.

## Per-Indicator Workspace Contract

Each indicator or strategy gets one canonical workspace:

```text
scripts/optuna/workspaces/<indicator_key>/
  study.db
  top*.json
  champion.json            # optional seed artifact
  export.csv               # optional manual TV export
  trial_models/            # optional local model scratch
  experiments/
    <named-study>/
      study.db
      top*.json
      trial_models/
```

Rules:

- The workspace root holds the canonical study DB for that indicator key.
- Additional named studies stay inside `experiments/` for that same indicator.
- Shared mixed-indicator SQLite DBs are retired. Historical mixed DBs belong in `archive/`.
- Legacy `data/*optuna*` directories are deprecated and should stay empty.
- Study names are operator-facing titles in `optuna-dashboard`. Use clear words with spaces that state the study purpose. Do not use snake_case, version labels, or generic names such as `<indicator>_study`.

## Current Runtime Ops

- Current-runtime-only health: `python scripts/optuna/runtime_health.py`
- Stale child-log archive (dry run): `python scripts/optuna/prune_runtime_logs.py`
- Stale child-log archive (apply): `python scripts/optuna/prune_runtime_logs.py --apply`
