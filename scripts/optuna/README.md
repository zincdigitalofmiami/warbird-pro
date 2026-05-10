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
  export.csv               # optional manual TV export for non-Nexus lanes
  tv_footprint_5m.parquet  # required TV request.footprint snapshot for Nexus
  tv_footprint_5m.manifest.json
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
- `warbird_pro` is the only active main chart indicator key and maps to
  **Warbird Pro V9** at `indicators/warbird-pro-v9.pine`.
- `warbird_pro_v9` is a separate Warbird Pro V9 experiment lane for ES-only
  ATR/risk exit modeling. Prep supports both `5m` and `15m` datasets; keep the
  canonical workspace at `workspaces/warbird_pro_v9/`, store exports under
  `exports/`, and keep timeframe-specific studies under `experiments/es_5m/`
  and `experiments/es_15m/` when you need separate study DBs.
- `warbird_pro_core` is the Core AutoGluon card workspace. Prep supports ES
  `5m` and `15m` datasets with the same separation rule: dataset exports at the
  workspace root `exports/`, contract-specific study DBs under
  `experiments/es_5m/` and `experiments/es_15m/`.
- Databento is an approved ES 5m/15m market-data supplier for training rows when
  manifests declare a Databento capture/source kind such as
  `DATABENTO_OHLCV_CSV`. Databento is not the Pine indicator and must not be
  labeled `TRADINGVIEW_INDICATOR_CSV`.
- `warbird_nexus_ml_rsi` is footprint-only: use the TradingView/Pine
  `request.footprint()` parquet + manifest. Do not use CSV exports, plain OHLCV
  parquet, Databento bars, or synthetic body/wick delta for that lane.

## Current Runtime Ops

- Current-runtime-only health: `python scripts/optuna/runtime_health.py`
- Stale child-log archive (dry run): `python scripts/optuna/prune_runtime_logs.py`
- Stale child-log archive (apply): `python scripts/optuna/prune_runtime_logs.py --apply`
