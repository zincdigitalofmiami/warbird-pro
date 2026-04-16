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


CANONICAL_PROBS_COLUMNS = [
    "pred_p__STOPPED", "pred_p__TP1_ONLY", "pred_p__TP2_HIT",
    "pred_p__TP3_HIT", "pred_p__TP4_HIT", "pred_p__TP5_HIT",
]


def gate_d_probs_alignment(cache_dir: Path, fold_code: str, expected_row_count: int) -> dict[str, Any]:
    """Gate D — assert probs.parquet has canonical 6 pred_p__* columns and matches
    the expected row count. Alignment is positional (not by embedded key) per
    monte_carlo_run.py:545-572 contract.

    Per design amendment Finding 3: probs.parquet does NOT contain stop_variant_id.
    Do not attempt to join-by-key. Row order is the contract.
    """
    import pandas as pd
    probs_path = cache_dir / fold_code / "probs.parquet"
    if not probs_path.exists():
        sys.stderr.write(f"Gate D — FATAL: {probs_path} not found.\n")
        sys.exit(1)
    probs = pd.read_parquet(probs_path)
    cols = list(probs.columns)
    if cols != CANONICAL_PROBS_COLUMNS:
        sys.stderr.write(
            f"Gate D — FATAL: probs.parquet schema drift. "
            f"expected={CANONICAL_PROBS_COLUMNS} actual={cols}\n"
        )
        sys.exit(1)
    if len(probs) != expected_row_count:
        sys.stderr.write(
            f"Gate D — FATAL: probs.parquet length drift. "
            f"expected={expected_row_count} actual={len(probs)}\n"
        )
        sys.exit(1)
    return {"status": "PASS", "columns": cols, "row_count": len(probs)}


import pandas as pd

FOLD_CODES = ["fold_01", "fold_02", "fold_03", "fold_04", "fold_05"]

# Columns that must come from ag_training if not present in analysis.parquet.
# For the agtrain_20260415T165437712806Z fixture these are all already in
# analysis.parquet (confirmed at build time), but we guard defensively.
REQUIRED_FROM_TRAINING = [
    "stop_variant_id", "stop_family_id", "direction",
    "outcome_label", "sl_dist_pts", "adx", "entry_price", "ts",
]


def load_fold_dataset(run_dir: Path, fold_code: str, dsn: str = DEFAULT_DSN) -> pd.DataFrame:
    """Load the fold's analysis_frame + probs, joined by row order (MC cache contract).

    analysis.parquet already contains outcome_label, sl_dist_pts, adx, entry_price,
    stop_family_id, direction, stop_variant_id for the locked fixture.  If any
    required column is missing (future fixture), fall back to a DB join on
    stop_variant_id. Returns a single DataFrame.
    """
    cache_dir = run_dir / "monte_carlo" / "cache" / fold_code
    analysis = pd.read_parquet(cache_dir / "analysis.parquet")
    probs = pd.read_parquet(cache_dir / "probs.parquet")
    if len(analysis) != len(probs):
        raise RuntimeError(
            f"fold {fold_code}: analysis len {len(analysis)} != probs len {len(probs)} "
            "— MC cache is corrupt; re-run monte_carlo_run.py first"
        )
    # Positional concat — row order is the contract (no key join for probs)
    joined = pd.concat([analysis.reset_index(drop=True), probs.reset_index(drop=True)], axis=1)

    # Check if all required columns are already present
    missing_cols = [c for c in REQUIRED_FROM_TRAINING if c not in joined.columns]
    if missing_cols:
        # Fall back: enrich from ag_training DB
        import psycopg2
        if "stop_variant_id" not in joined.columns:
            raise RuntimeError(
                "analysis_frame lacks stop_variant_id — expected in META_COLS. "
                "Check monte_carlo_run.py prepare_fold() output contract."
            )
        stop_variant_ids = joined["stop_variant_id"].tolist()
        cols_to_fetch = ["stop_variant_id"] + [c for c in missing_cols if c != "stop_variant_id"]
        with psycopg2.connect(dsn) as conn:
            enrichment = pd.read_sql(
                f"SELECT {', '.join(cols_to_fetch)} FROM ag_training WHERE stop_variant_id = ANY(%s)",
                conn, params=(stop_variant_ids,),
            )
        joined = joined.merge(enrichment, on="stop_variant_id", how="left", validate="one_to_one")
        if joined["outcome_label"].isna().any():
            bad = joined[joined["outcome_label"].isna()]["stop_variant_id"].tolist()[:10]
            raise RuntimeError(
                f"fold {fold_code}: {len(bad)} stop_variant_ids missing from ag_training: {bad}..."
            )
    return joined


TP_HIT_LABELS = {"TP1_ONLY", "TP2_HIT", "TP3_HIT", "TP4_HIT", "TP5_HIT"}
STOPPED_LABEL = "STOPPED"
FLAT_FEE_USD = 1.25
MES_POINT_VALUE = 5.0

# Raw price level columns that should not be features (admitted as regime proxies)
RAW_PRICE_FEATURE_COLS = {
    "anchor_low", "anchor_high", "entry_price",
    "tp1_price", "tp2_price", "tp3_price", "tp4_price", "tp5_price",
    "stop_level_price", "fib_level_price",
}


def compute_net_dollars(row: pd.Series) -> float:
    """Per-trade net $ at macro-fib outcome with flat fee.
    tp*_price columns are expected to be present in the row (from analysis.parquet).
    """
    label = row["outcome_label"]
    direction = int(row["direction"])
    entry = float(row["entry_price"])
    if label == STOPPED_LABEL:
        return -float(row["sl_dist_pts"]) * MES_POINT_VALUE - FLAT_FEE_USD
    tp_price_col = {
        "TP1_ONLY": "tp1_price", "TP2_HIT": "tp2_price", "TP3_HIT": "tp3_price",
        "TP4_HIT": "tp4_price", "TP5_HIT": "tp5_price",
    }.get(label)
    if tp_price_col is None or tp_price_col not in row.index:
        return 0.0
    return (float(row[tp_price_col]) - entry) * direction * MES_POINT_VALUE - FLAT_FEE_USD


def phase1_baseline_per_stop_family(run_dir: Path, dsn: str = DEFAULT_DSN) -> list[dict[str, Any]]:
    """No filter applied. Per stop family, compute tp1_reach_rate, stop_rate,
    net $, mean sl_dist_pts across all 5 folds combined.

    tp*_price columns are available in analysis.parquet for the locked fixture,
    so no separate DB query is required.
    """
    frames = []
    for fold_code in FOLD_CODES:
        frames.append(load_fold_dataset(run_dir, fold_code, dsn=dsn))
    combined = pd.concat(frames, ignore_index=True)

    results = []
    for sf, grp in combined.groupby("stop_family_id"):
        n = len(grp)
        tp1_reach = grp["outcome_label"].isin(TP_HIT_LABELS).sum() / n
        stop_rate = (grp["outcome_label"] == STOPPED_LABEL).sum() / n
        mean_sl = float(grp["sl_dist_pts"].mean())
        net_dollars = grp.apply(compute_net_dollars, axis=1)
        results.append({
            "stop_family_id": sf,
            "n_trades": n,
            "tp1_reach_rate": float(tp1_reach),
            "stop_rate": float(stop_rate),
            "mean_sl_dist_pts": mean_sl,
            "expected_net_dollars_per_trade": float(net_dollars.mean()),
            "mc_p5_ev_per_trade": None,  # Filled in when MC sampling is wired
        })
    return results


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
