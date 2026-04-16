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
