#!/usr/bin/env python3
"""Report exact Warbird Pro V9 Core smoke metrics from a built CSV.

This script is intentionally read-only. It does not build a dataset and does
not train a model. It reads the Core CSV + manifest, recomputes the smoke
label summary through train_v9_locked.build_trade_dataset(), verifies the
locked feature schema, and emits deterministic JSON for gate evidence.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.ag.train_v9_locked import LABEL_COL, ML_FEATURES, build_trade_dataset

COUNT_COLUMNS = [
    "ml_xa_dxy_code",
    "ml_xa_dxy_diverge",
    "ml_xa_corr_nq",
    "ml_fp_delta_pct",
    "ml_cvd_div_bull",
    "ml_cvd_div_bear",
    "ml_absorption_candidate",
    "ml_flush_candidate",
    "ml_volume_spike_ratio",
    "ml_poc_shift",
]
STALE_COLUMNS = ("ml_xa_dx_code", "ml_bar_delta", "ml_net_delta_20")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def finite_bad_columns(df: pd.DataFrame, cols: list[str]) -> list[str]:
    bad: list[str] = []
    for col in cols:
        values = pd.to_numeric(df[col], errors="coerce")
        if np.isinf(values).any():
            bad.append(col)
    return bad


def build_report(csv_path: Path, manifest_path: Path, max_hold_bars: int) -> dict[str, Any]:
    df = pd.read_csv(csv_path, parse_dates=["ts"])
    manifest = json.loads(manifest_path.read_text())

    missing_features = [col for col in ML_FEATURES if col not in df.columns]
    stale_columns = [col for col in STALE_COLUMNS if col in df.columns]
    missing_count_columns = [col for col in COUNT_COLUMNS if col not in df.columns]
    if missing_features or stale_columns or missing_count_columns:
        raise RuntimeError(
            "Smoke CSV schema failure: "
            f"missing_features={missing_features} "
            f"stale_columns={stale_columns} "
            f"missing_count_columns={missing_count_columns}"
        )
    bad_inf = finite_bad_columns(df, ML_FEATURES)
    if bad_inf:
        raise RuntimeError(f"Smoke CSV has +/-inf in feature columns: {bad_inf}")

    trades = build_trade_dataset(df, max_hold_bars=max_hold_bars)
    if len(trades) == 0:
        raise RuntimeError("Smoke CSV produced zero resolved trades")

    counts = {
        col: int((pd.to_numeric(df[col], errors="coerce").fillna(0.0).abs() > 0).sum())
        for col in COUNT_COLUMNS
    }
    label_counts = {
        str(int(label)): int(count)
        for label, count in trades[LABEL_COL].value_counts().sort_index().items()
    }
    report = {
        "csv_path": str(csv_path),
        "manifest_path": str(manifest_path),
        "csv_sha256": sha256_file(csv_path),
        "manifest_sha256": sha256_file(manifest_path),
        "manifest_declared_csv_sha256": manifest.get("sha256"),
        "manifest_sha256_matches_csv": manifest.get("sha256") == sha256_file(csv_path),
        "row_count": int(len(df)),
        "ts_first": pd.to_datetime(df["ts"], utc=True).min().isoformat(),
        "ts_last": pd.to_datetime(df["ts"], utc=True).max().isoformat(),
        "entry_long_count": int(pd.to_numeric(df["ml_entry_long_trigger"], errors="coerce").fillna(0.0).sum()),
        "entry_short_count": int(pd.to_numeric(df["ml_entry_short_trigger"], errors="coerce").fillna(0.0).sum()),
        "resolved_trade_count": int(len(trades)),
        "winner_count": int(trades[LABEL_COL].sum()),
        "loss_count": int((1 - trades[LABEL_COL]).sum()),
        "label_counts": label_counts,
        "winner_rate": float(trades[LABEL_COL].mean()),
        "max_hold_bars": int(max_hold_bars),
        "feature_count_locked": int(len(ML_FEATURES)),
        "missing_features": missing_features,
        "stale_columns": stale_columns,
        "nonzero_counts": counts,
        "manifest_warnings": manifest.get("warnings", []),
    }
    return report


def main() -> int:
    ap = argparse.ArgumentParser(description="Report exact V9 Core smoke metrics")
    ap.add_argument("--csv", type=Path, required=True)
    ap.add_argument("--manifest", type=Path, required=True)
    ap.add_argument("--max-hold-bars", type=int, default=24)
    ap.add_argument("--out-json", type=Path, default=None)
    args = ap.parse_args()

    if not args.csv.exists():
        raise SystemExit(f"CSV not found: {args.csv}")
    if not args.manifest.exists():
        raise SystemExit(f"Manifest not found: {args.manifest}")

    report = build_report(args.csv, args.manifest, args.max_hold_bars)
    payload = json.dumps(report, indent=2, sort_keys=True)
    print(payload)
    if args.out_json:
        args.out_json.parent.mkdir(parents=True, exist_ok=True)
        args.out_json.write_text(payload + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
