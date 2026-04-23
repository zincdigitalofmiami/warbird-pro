# Legacy Single-Lane Optuna Runbook

## Status

Archived reference only.

The old one-off strategy tuning lane is retired from the active Warbird Optuna
surface. Do not use its historical SQLite layout, champion seed assumptions, or
dedicated sidecar launch pattern as the default for new studies.

## Current Contract

Use the registry-backed workflow instead:

- Workspace contract: `scripts/optuna/README.md`
- Hub: `http://localhost:8090/` (sole surface — 8080 compat redirect retired 2026-04-23)
- VS Code surface: `.vscode/OPTUNA_WORKSPACE.md`

Canonical Optuna state now lives under:

```text
scripts/optuna/workspaces/<indicator_key>/
```

Each active lane owns its own workspace, study DB, and exports under that
directory. Archived single-lane artifacts may remain on disk for lineage, but
they are read-only history and must not be reused as current defaults.
