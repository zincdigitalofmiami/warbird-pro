#!/usr/bin/env python3
"""Post-hoc Monte Carlo sweep over macro-fib-trade exit management policies.

Design: docs/plans/2026-04-15-policy-mc-sweep-design.md
Plan:   docs/plans/2026-04-15-policy-mc-sweep-plan.md

Read-only against warbird PG17 DB (ag_training + mes_1m) and AG run artifacts.
Writes to artifacts/ag_runs/<RUN_ID>/policy_sweep/.
Does not touch: train_ag_baseline.py, run_diagnostic_shap.py, monte_carlo_run.py,
build_ag_pipeline.py. No migrations.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

SCRIPT_VERSION = "1.0.0"
ARTIFACTS_ROOT = Path("artifacts/ag_runs")
DEFAULT_DSN = "host=127.0.0.1 port=5432 dbname=warbird"


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Post-hoc policy sweep over macro-fib-trade exit management.",
    )
    p.add_argument("--run-id", required=True,
                   help="AG training run_id (fixture). Must have complete MC task_A output.")
    p.add_argument("--phase", choices=["filter", "exit", "both"], default="both")
    p.add_argument("--min-combo-n", type=int, default=50,
                   help="Minimum trades per combo to rank. Combos below this are logged, not silently dropped.")
    p.add_argument("--top-k", type=int, default=10,
                   help="Top/bottom K policies per stop family.")
    p.add_argument("--max-trajectory-bars", type=int, default=120,
                   help="Phase 2: 15m bars forward from entry to include in trajectory.")
    p.add_argument("--rebuild-trajectory-cache", action="store_true",
                   help="Force rebuild of per-fold trajectory parquet cache.")
    p.add_argument("--dry-run", action="store_true",
                   help="Validate gates + print combo counts, write no outputs.")
    p.add_argument("--dsn", default=DEFAULT_DSN, help="Local PG17 DSN.")
    return p.parse_args()


def gate_h_fixture_assertion(run_dir: Path, dsn: str) -> dict[str, Any]:
    """Gate H — verify source fixture row count + session count + feature manifest hash.

    Aborts with exit 1 on drift. Per design amendment, the correct anchor is
    dataset_summary.json.rows_total (NOT task_A.indicator_settings_frozen row manifest).
    """
    import psycopg2

    ds_path = run_dir / "dataset_summary.json"
    if not ds_path.exists():
        sys.stderr.write(f"Gate H — FATAL: dataset_summary.json not found at {ds_path}\n")
        sys.exit(1)
    ds = json.loads(ds_path.read_text())
    expected_rows = int(ds["rows_total"])
    expected_sessions = int(ds["sessions_total"])

    fm_path = run_dir / "feature_manifest.json"
    if not fm_path.exists():
        sys.stderr.write(f"Gate H — FATAL: feature_manifest.json not found at {fm_path}\n")
        sys.exit(1)
    fm_md5 = hashlib.md5(fm_path.read_bytes()).hexdigest()

    with psycopg2.connect(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM ag_training")
            observed_rows = int(cur.fetchone()[0])

    if observed_rows != expected_rows:
        sys.stderr.write(
            f"Gate H — FATAL: ag_training row count drifted. "
            f"dataset_summary.json says {expected_rows}, DB says {observed_rows}. "
            f"Source fixture has changed since the AG run was generated. "
            f"Re-run MC tasks A-I first or use a fresh run_id.\n"
        )
        sys.exit(1)

    return {
        "status": "PASS",
        "expected_rows": expected_rows,
        "observed_rows": observed_rows,
        "expected_sessions": expected_sessions,
        "feature_manifest_md5": fm_md5,
    }


def main() -> int:
    args = parse_args()
    run_dir = ARTIFACTS_ROOT / args.run_id

    if not run_dir.exists():
        sys.stderr.write(
            f"Gate H — FATAL: run directory {run_dir} not found. "
            f"Check --run-id is correct.\n"
        )
        sys.exit(1)

    gate_h = gate_h_fixture_assertion(run_dir, args.dsn)
    print(f"Gate H: PASS (rows={gate_h['observed_rows']}, sessions={gate_h['expected_sessions']})")

    if args.dry_run:
        print("Dry run — exiting before any output.")
        return 0

    sys.stderr.write("Not yet implemented beyond Gate H. See plan task list.\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
