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


# ─────────────────────────────────────────────
# Task 6 — Gate A trajectory drift detection
# ─────────────────────────────────────────────

def test_gate_a_passes_on_fixture():
    from scripts.ag import policy_mc_sweep as m

    result = m.gate_a_trajectory_drift(FIXTURE_RUN_DIR, samples_per_fold=40)
    assert result["status"] == "PASS", (
        f"Gate A FAIL — agreement {result['agreement_rate']:.3f}, "
        f"top disagreements: {result['disagreements'][:5]}"
    )
    assert result["sample_size"] == 200
    assert result["agreement_rate"] >= 0.95, (
        f"agreement {result['agreement_rate']} below 95% — trajectory drift"
    )


# ─────────────────────────────────────────────
# Task 7 — ExitSweeper
# ─────────────────────────────────────────────

def test_exit_sweeper_default_settings_match_baseline():
    """Re-simulating at Pine default exit settings should closely match Phase 1 baseline."""
    from scripts.ag import policy_mc_sweep as m

    baseline = {r["stop_family_id"]: r for r in m.phase1_baseline_per_stop_family(FIXTURE_RUN_DIR)}
    default_combo = {
        "let_fast_runners_run": True,
        "fast_runner_window_bars": 2,
        "fast_runner_target": "TP2",
        "break_even_after_tp1": True,
    }
    exit_results = m.phase2_sweep_combo(FIXTURE_RUN_DIR, combo=default_combo)
    assert len(exit_results) == 6, f"expected 6 stop families, got {len(exit_results)}"
    for sf, base in baseline.items():
        sim = next(r for r in exit_results if r["stop_family_id"] == sf)
        delta_tp1 = abs(sim["tp1_reach_rate"] - base["tp1_reach_rate"])
        assert delta_tp1 < 0.05, (
            f"{sf}: sim tp1_reach {sim['tp1_reach_rate']:.4f} vs baseline "
            f"{base['tp1_reach_rate']:.4f} (delta {delta_tp1:.4f}) — diverged > 5%"
        )


# ─────────────────────────────────────────────
# Task 8 — Ranker
# ─────────────────────────────────────────────

def test_ranker_produces_per_family_top_k():
    from scripts.ag import policy_mc_sweep as m

    mocked = [
        {"stop_family_id": "ATR_1_0", "combo": {"x": 1}, "tp1_reach_rate": 0.5,
         "expected_net_dollars_per_trade": 10.0, "n_trades": 100},
        {"stop_family_id": "ATR_1_0", "combo": {"x": 2}, "tp1_reach_rate": 0.6,
         "expected_net_dollars_per_trade": 15.0, "n_trades": 100},
        {"stop_family_id": "ATR_1_0", "combo": {"x": 3}, "tp1_reach_rate": 0.4,
         "expected_net_dollars_per_trade": 30.0, "n_trades": 30},  # below min_n
    ]
    ranked = m.rank_per_stop_family(mocked, top_k=2, min_combo_n=50)
    assert "ATR_1_0" in ranked
    assert len(ranked["ATR_1_0"]["top_k"]) == 2
    # primary sort: tp1_reach_rate DESC
    assert ranked["ATR_1_0"]["top_k"][0]["tp1_reach_rate"] == 0.6
    assert ranked["ATR_1_0"]["below_min_n_count"] == 1


# ─────────────────────────────────────────────
# Task 9 — Gate F
# ─────────────────────────────────────────────

def test_gate_f_on_clean_fixture():
    """Locked fixture has tp1_dist_pts LEAKAGE_SUSPECT + fold_01 below baseline +
    fold_03 class coverage gap. Gate F must detect all three and block promotion.
    """
    from scripts.ag import policy_mc_sweep as m

    result = m.gate_f_source_integrity(FIXTURE_RUN_DIR)
    assert result["source_run_has_leakage_suspects"] is True, "tp1_dist_pts was flagged"
    assert result["source_run_has_below_baseline_fold"] is True, "fold_01 below baseline"
    assert result["source_run_has_class_coverage_gap"] is True, "fold_03 val=5 test=6"
    assert result["promotion_allowed"] is False


# ─────────────────────────────────────────────
# Task 10 — Output writers + Anti-Pattern B
# ─────────────────────────────────────────────

def test_anti_pattern_b_no_forbidden_strings_on_clean_run():
    """policy_summary.md must NOT contain forbidden bag-leakage prose
    when the source run config says num_bag_folds=0.
    """
    import json
    import shutil
    from scripts.ag import policy_mc_sweep as m

    out_dir = FIXTURE_RUN_DIR / "policy_sweep_test_output"
    if out_dir.exists():
        shutil.rmtree(out_dir)
    m.run_end_to_end(run_dir=FIXTURE_RUN_DIR, out_dir=out_dir, min_combo_n=50, top_k=10)
    summary = (out_dir / "policy_summary.md").read_text()
    forbidden = ["IID bag leakage", "GBM-only", "only LightGBM in leaderboard", "bag-fold leakage"]
    for f in forbidden:
        assert f not in summary, f"forbidden string in clean-run summary: {f!r}"
    integrity = json.loads((out_dir / "integrity.json").read_text())
    assert integrity["narrative_caveat_audit"]["hardcoded_strings_found"] == []


# ─────────────────────────────────────────────
# Task 11 — End-to-end acceptance
# ─────────────────────────────────────────────

def test_end_to_end_acceptance_on_locked_fixture():
    """Full subprocess run against locked fixture. All gates pass, all outputs valid."""
    import json
    import shutil
    import subprocess

    out_dir = FIXTURE_RUN_DIR / "policy_sweep"
    # Remove output (not trajectory_cache — that's preserved under policy_sweep/)
    for f in ["filter_sweep_results.json", "exit_sweep_results.json",
              "recommended_settings.json", "policy_summary.md", "integrity.json",
              "MANIFEST.json"]:
        (out_dir / f).unlink(missing_ok=True)

    r = subprocess.run(
        [sys.executable, SCRIPT,
         "--run-id", FIXTURE_RUN_ID, "--phase", "both",
         "--min-combo-n", "50", "--top-k", "10"],
        capture_output=True, text=True, timeout=1800,
    )
    assert r.returncode == 0, f"exit {r.returncode}. stderr:\n{r.stderr[-2000:]}"
    for f in ["filter_sweep_results.json", "exit_sweep_results.json",
              "recommended_settings.json", "policy_summary.md", "integrity.json"]:
        assert (out_dir / f).exists(), f"missing output: {f}"
    integrity = json.loads((out_dir / "integrity.json").read_text())
    assert integrity["gates"]["H"]["status"] == "PASS"
    assert integrity["gates"]["A"]["status"] == "PASS"
    assert integrity["cross_family_ranking_valid"] is False
    assert integrity["promotion_allowed"] is False
    rec = json.loads((out_dir / "recommended_settings.json").read_text())
    assert "winning_policy_per_stop_family" in rec
    expected_families = {
        "ATR_1_0", "ATR_1_5", "ATR_STRUCTURE_1_25",
        "FIB_0236_ATR_COMPRESS_0_50", "FIB_NEG_0236", "FIB_NEG_0382",
    }
    assert set(rec["winning_policy_per_stop_family"].keys()) == expected_families
