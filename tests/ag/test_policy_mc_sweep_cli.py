"""Tests for policy_mc_sweep.py — executed from project root.

Run:
    python3 -m pytest tests/ag/test_policy_mc_sweep_cli.py -v
    python3 -m pytest tests/ag/test_policy_mc_sweep_cli.py -v --timeout=1800  # for full e2e
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

SCRIPT = "scripts/ag/policy_mc_sweep.py"
FIXTURE_RUN_ID = "agtrain_20260415T165437712806Z"
FIXTURE_RUN_DIR = Path("artifacts/ag_runs") / FIXTURE_RUN_ID


# ─────────────────────────────────────────────
# Task 1 — CLI + Gate H
# ─────────────────────────────────────────────

def test_help_exits_zero():
    """Script --help must succeed and mention the run-id flag."""
    r = subprocess.run([sys.executable, SCRIPT, "--help"],
                       capture_output=True, text=True, timeout=15)
    assert r.returncode == 0, f"--help exited {r.returncode}: {r.stderr}"
    assert "--run-id" in r.stdout
    assert "--phase" in r.stdout
    assert "--min-combo-n" in r.stdout


def test_missing_fixture_aborts_gate_h():
    """Gate H must abort when run directory does not exist."""
    r = subprocess.run(
        [sys.executable, SCRIPT, "--run-id", "agtrain_NONEXISTENT_FIXTURE", "--dry-run"],
        capture_output=True, text=True, timeout=30,
    )
    assert r.returncode != 0, "nonexistent fixture should abort"
    assert "Gate H" in r.stderr or "fixture" in r.stderr.lower()


# ─────────────────────────────────────────────
# Task 2 — Gate D probs.parquet alignment
# ─────────────────────────────────────────────

def test_gate_d_passes_on_locked_fixture():
    """Gate D passes on agtrain_20260415T165437712806Z fold_01."""
    import pandas as pd
    from scripts.ag import policy_mc_sweep as m

    cache_dir = FIXTURE_RUN_DIR / "monte_carlo/cache"
    fold_code = "fold_01"
    analysis = pd.read_parquet(cache_dir / fold_code / "analysis.parquet")
    result = m.gate_d_probs_alignment(cache_dir, fold_code, expected_row_count=len(analysis))
    assert result["status"] == "PASS"
    assert result["columns"] == [
        "pred_p__STOPPED", "pred_p__TP1_ONLY", "pred_p__TP2_HIT",
        "pred_p__TP3_HIT", "pred_p__TP4_HIT", "pred_p__TP5_HIT"
    ]
    assert result["row_count"] == len(analysis)


# ─────────────────────────────────────────────
# Task 3 — OutcomeJoiner
# ─────────────────────────────────────────────

def test_load_fold_dataset_shape():
    """Loader returns a joined DataFrame with known columns on fold_01."""
    import pandas as pd
    from scripts.ag import policy_mc_sweep as m

    df = m.load_fold_dataset(FIXTURE_RUN_DIR, "fold_01")
    expected_cols = {
        "stop_variant_id", "stop_family_id", "direction", "outcome_label",
        "sl_dist_pts", "adx", "entry_price",
        "pred_p__STOPPED", "pred_p__TP1_ONLY", "pred_p__TP2_HIT",
        "pred_p__TP3_HIT", "pred_p__TP4_HIT", "pred_p__TP5_HIT",
    }
    missing = expected_cols - set(df.columns)
    assert not missing, f"missing columns: {missing}"
    # row-count sanity — matches probs length
    probs = pd.read_parquet(FIXTURE_RUN_DIR / "monte_carlo/cache/fold_01/probs.parquet")
    assert len(df) == len(probs)


# ─────────────────────────────────────────────
# Task 4 — Phase 1 Baseline Scorer
# ─────────────────────────────────────────────

def test_phase1_baseline_on_fixture():
    """Phase 1 baseline across all 5 folds produces 6 per-family metric rows."""
    from scripts.ag import policy_mc_sweep as m

    results = m.phase1_baseline_per_stop_family(FIXTURE_RUN_DIR)
    assert len(results) == 6, f"expected 6 stop families, got {len(results)}"
    for r in results:
        assert r["n_trades"] > 0
        assert 0.0 <= r["tp1_reach_rate"] <= 1.0
        assert 0.0 <= r["stop_rate"] <= 1.0
        assert abs(r["tp1_reach_rate"] + r["stop_rate"] - 1.0) < 1e-9, (
            f"{r['stop_family_id']}: tp1_reach + stop_rate must sum to 1 "
            f"(got {r['tp1_reach_rate']} + {r['stop_rate']})"
        )
        assert r["mean_sl_dist_pts"] > 0


# ─────────────────────────────────────────────
# Task 5 — TrajectoryBuilder
# ─────────────────────────────────────────────

def test_trajectory_builder_on_fold_01():
    from scripts.ag import policy_mc_sweep as m

    cache_dir = FIXTURE_RUN_DIR / "policy_sweep" / "trajectory_cache"
    df = m.build_or_load_trajectory(
        FIXTURE_RUN_DIR, "fold_01", cache_dir,
        max_trajectory_bars=120, force_rebuild=True,
    )
    for c in ["stop_variant_id", "bar_offset", "high_pts", "low_pts", "close_pts"]:
        assert c in df.columns, f"missing column: {c}"
    trade_counts = df.groupby("stop_variant_id").size()
    assert trade_counts.min() >= 1
    # entry bar (offset 0) must have high >= low
    entry_bars = df[df["bar_offset"] == 0]
    assert (entry_bars["high_pts"] >= entry_bars["low_pts"]).all()
