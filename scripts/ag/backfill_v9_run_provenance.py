#!/usr/bin/env python3
"""Backfill run-bound provenance into a V9 Core training summary.

The d4e0df1 contract requires every consumer (SHAP, MC) to bind to the exact
CSV hash and split row ranges captured at training time. Runs completed
under earlier trainer commits (e.g. bc02ab7) emit a summary that lacks
``run_provenance``, ``csv_sha256``, ``split_ranges_utc`` and
``split_contract`` because those fields didn't exist yet. Re-running 5-head
training takes ~10h wall.

This script reproduces the missing fields deterministically: the label
construction in ``scripts.ag.train_v9_locked.build_trade_dataset`` and the
chronological split in ``split_trade_positions`` are bit-identical between
the legacy and HEAD trainer (only summary emission changed), so rebuilding
trades from the same CSV and applying the same fractions yields the exact
same train/val/oos row partition the artifact was fit on.

Safeguards:
  * Manifest hash cross-check (refuses to backfill if the on-disk CSV has
    drifted from the manifest's declared hash).
  * Row-count parity gate (refuses to write if reproduced is_rows/val_rows/
    oos_rows differ from the summary).
  * Idempotent: refuses to overwrite an already-backfilled summary unless
    --force is passed.
  * Writes a ``v9_winner_clf_summary.pre_backfill.json`` backup before
    mutating the summary.

Usage:
  python scripts/ag/backfill_v9_run_provenance.py \
      --predictor-path models/warbird_pro_v9/locked_20260512_083803
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.ag.v9_run_provenance import build_csv_provenance
from scripts.ag.train_v9_locked import (
    EMBARGO_BARS,
    FORWARD_SCAN_BARS,
    build_trade_dataset,
    split_trade_positions,
    validate_input_schema,
)


def _split_bounds_payload(df: pd.DataFrame) -> dict[str, str | None]:
    if df.empty:
        return {"ts_start": None, "ts_end": None}
    ts = pd.to_datetime(df["ts"], utc=True)
    return {
        "ts_start": ts.min().isoformat(),
        "ts_end": ts.max().isoformat(),
    }


def _already_backfilled(summary: dict[str, Any]) -> bool:
    return (
        isinstance(summary.get("run_provenance"), dict)
        and isinstance(summary.get("split_ranges_utc"), dict)
        and isinstance(summary.get("csv_sha256"), str)
        and summary.get("csv_sha256", "").strip() != ""
    )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--predictor-path", type=Path, required=True,
                    help="Run directory containing v9_winner_clf_summary.json")
    ap.add_argument("--summary-name", default="v9_winner_clf_summary.json")
    ap.add_argument("--train-frac", type=float, default=0.70,
                    help="Must match the trainer fractions used for the run.")
    ap.add_argument("--val-frac", type=float, default=0.15)
    ap.add_argument("--force", action="store_true",
                    help="Overwrite a summary that already carries backfilled provenance.")
    args = ap.parse_args()

    summary_path = (args.predictor_path / args.summary_name).resolve()
    if not summary_path.exists():
        raise SystemExit(f"Summary not found: {summary_path}")

    summary = json.loads(summary_path.read_text())
    if _already_backfilled(summary) and not args.force:
        print(f"summary already carries run-bound provenance; pass --force to overwrite ({summary_path})")
        return 0

    csv_path = Path(summary.get("csv_path", "")).resolve()
    if not csv_path.exists():
        raise SystemExit(f"summary.csv_path not found on disk: {csv_path}")

    print(f"backfilling provenance for {summary_path}")
    print(f"  csv_path: {csv_path}")

    csv_provenance = build_csv_provenance(csv_path)
    declared = csv_provenance.get("manifest_declared_csv_sha256")
    actual = csv_provenance.get("csv_sha256")
    matches = csv_provenance.get("manifest_csv_sha256_matches")
    print(f"  csv_sha256: {actual}")
    print(f"  manifest_declared: {declared}  matches: {matches}")
    if declared is not None and matches is False:
        raise SystemExit(
            "CSV has drifted from manifest's declared hash; refusing to backfill. "
            "Either restore the CSV used at training time or re-run training."
        )

    is_rows_summary = int(summary["is_rows"])
    val_rows_summary = int(summary["val_rows"])
    oos_rows_summary = int(summary["oos_rows"])

    print(f"  loading {csv_path}")
    df = pd.read_csv(csv_path, parse_dates=["ts"])
    validate_input_schema(df)
    trades = build_trade_dataset(df)

    train_pos, val_pos, test_pos = split_trade_positions(
        trades,
        train_frac=args.train_frac,
        val_frac=args.val_frac,
        embargo_bars=EMBARGO_BARS,
        label_horizon_bars=FORWARD_SCAN_BARS,
    )
    train_df = trades.iloc[train_pos].copy()
    val_df = trades.iloc[val_pos].copy()
    test_df = trades.iloc[test_pos].copy()

    is_rows_repro = len(train_df)
    val_rows_repro = len(val_df)
    oos_rows_repro = len(test_df)
    print(
        f"  reproduced rows: train={is_rows_repro}  val={val_rows_repro}  oos={oos_rows_repro}"
    )
    print(
        f"  summary rows:    train={is_rows_summary}  val={val_rows_summary}  oos={oos_rows_summary}"
    )

    mismatch = (
        is_rows_repro != is_rows_summary
        or val_rows_repro != val_rows_summary
        or oos_rows_repro != oos_rows_summary
    )
    if mismatch:
        raise SystemExit(
            "Row-count parity gate failed: reproduced splits do not match summary."
            " The CSV, build_trade_dataset, or split fractions must have drifted"
            " from the run-time state. Refusing to write."
        )

    run_provenance = {
        **csv_provenance,
        "repo_commit": summary.get("run_provenance", {}).get("repo_commit", "backfilled_unknown"),
        "backfilled_at": pd.Timestamp.utcnow().isoformat(),
        "backfilled_by": "scripts/ag/backfill_v9_run_provenance.py",
    }
    split_contract = {
        "train_frac": float(args.train_frac),
        "val_frac": float(args.val_frac),
        "label_horizon_bars": int(FORWARD_SCAN_BARS),
        "embargo_bars": int(EMBARGO_BARS),
    }
    split_ranges_utc = {
        "train": _split_bounds_payload(train_df),
        "val": _split_bounds_payload(val_df),
        "oos": _split_bounds_payload(test_df),
    }

    backup_path = summary_path.with_suffix(".pre_backfill.json")
    if not backup_path.exists():
        backup_path.write_text(json.dumps(summary, indent=2, default=str))
        print(f"  wrote backup: {backup_path}")
    else:
        print(f"  backup already exists, not overwriting: {backup_path}")

    summary["csv_sha256"] = csv_provenance["csv_sha256"]
    summary["csv_sha256_assumed_via_manifest"] = declared
    summary["run_provenance"] = run_provenance
    summary["split_contract"] = split_contract
    summary["split_ranges_utc"] = split_ranges_utc

    summary_path.write_text(json.dumps(summary, indent=2, default=str))
    print(f"  wrote {summary_path}")
    for split, payload in split_ranges_utc.items():
        print(f"  {split}_range: {payload['ts_start']} -> {payload['ts_end']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
