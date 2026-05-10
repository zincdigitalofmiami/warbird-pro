# V9 Core Smoke Verification

This runbook is the reproducible evidence path for small Core ETL smoke
windows. It is not a full 1y Core build, not AG training, and not a champion
gate.

## Build Smoke CSV

```bash
rm -rf artifacts/v9_core_smoke_may2025
python3 scripts/optuna/workspaces/warbird_pro_core/build_core_dataset.py \
  --symbol MES \
  --source data/mes_1m.parquet \
  --start 2025-05-01 \
  --end 2025-05-31 \
  --out-dir artifacts/v9_core_smoke_may2025 \
  --gate-mode smoke
```

Expected artifact paths:

- `artifacts/v9_core_smoke_may2025/mes_5m_core.csv`
- `artifacts/v9_core_smoke_may2025/mes_5m_core.manifest.json`

## Report Exact Metrics

```bash
python3 scripts/ag/report_v9_core_smoke.py \
  --csv artifacts/v9_core_smoke_may2025/mes_5m_core.csv \
  --manifest artifacts/v9_core_smoke_may2025/mes_5m_core.manifest.json \
  --out-json artifacts/v9_core_smoke_may2025/metrics.json
```

Use the emitted JSON as the source of truth for row counts, entry counts,
feature nonzero counts, label counts, and CSV/manifest checksums. Do not cite
chat-transcribed smoke metrics without this JSON output.

Current reference run from 2026-05-10:

- CSV SHA256: `7e18f2b9fa6135552ebcee3b10ba87919166e09bb5ee91642c3816662a701c15`
- Manifest SHA256: `d3e1158b3e71dfe47d7024279953224e964ad852699f59d49cdffdecfd00e071`
- Rows: `6000`
- Entries: `68` long, `0` short
- Resolved labels: `68` total, `62` winners, `6` losses
- Nonzero counts: DXY code `5980`, DXY divergence `3111`, fp delta `4603`,
  CVD bull `486`, CVD bear `714`, POC shift `4356`

## Smoke Label Validation

```bash
python3 scripts/ag/train_v9_locked.py \
  --csv artifacts/v9_core_smoke_may2025/mes_5m_core.csv \
  --validate-only \
  --smoke-ok
```

`--smoke-ok` is only for small smoke windows. Full Core validation still uses
`--validate-only` without `--smoke-ok`, which preserves the >=200 resolved-trade
and chronological split gates.
