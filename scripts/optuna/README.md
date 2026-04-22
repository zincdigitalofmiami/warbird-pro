# Warbird Optuna Workspace

Canonical Optuna state now lives under `scripts/optuna/`, not `data/optuna/`.

## Layout

- `runner.py`
  Shared Optuna CLI for registry-backed indicator and strategy profiles.
- `warbird_optuna_hub.py`
  Card dashboard and child `optuna-dashboard` launcher.
- `vscode_doctor.py`
  VS Code extension and sidecar diagnostics.
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
- `data/optuna/` and `data/sats_ps_optuna/` are deprecated and should stay empty.
