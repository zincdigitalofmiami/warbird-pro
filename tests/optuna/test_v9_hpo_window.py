"""Guards for the V9 HPO window lock — Bug 2 cannot recur.

Bug 2 was a runbook example that ran HPO with --start 2025-01-01, contaminating
the structural-break OOS (Trump regime). These tests enforce two layers:

1. Runtime guard in scripts/optuna/runner.py.assert_v9_oos_lock — refuses any
   V9 lane whose --start or --end leaks into 2025+.
2. Runbook content guard — the Optuna invocation examples in
   docs/runbooks/warbird_pro_v9_optuna_ag_shap.md must use
   --start 2020-01-01 --end 2024-12-31 and must not contain --start 2025-.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from scripts.optuna.runner import (
    V9_OOS_LOCK_START,
    V9_OOS_LOCKED_KEY_PREFIXES,
    assert_v9_oos_lock,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
RUNBOOK_PATH = REPO_ROOT / "docs/runbooks/warbird_pro_v9_optuna_ag_shap.md"


def test_v9_lock_prefixes_present() -> None:
    assert "warbird_pro_v9" in V9_OOS_LOCKED_KEY_PREFIXES
    assert V9_OOS_LOCK_START.tz_convert("UTC").date().isoformat() == "2025-01-01"


def test_runtime_guard_rejects_start_inside_oos() -> None:
    with pytest.raises(SystemExit, match="V9 OOS lock violated"):
        assert_v9_oos_lock("warbird_pro_v9", "2025-01-01", "2025-12-31")


def test_runtime_guard_rejects_end_inside_oos() -> None:
    with pytest.raises(SystemExit, match="reaches into the locked OOS"):
        assert_v9_oos_lock("warbird_pro_v9", "2020-01-01", "2025-06-30")


def test_runtime_guard_requires_end_for_v9() -> None:
    with pytest.raises(SystemExit, match="requires --end"):
        assert_v9_oos_lock("warbird_pro_v9", "2020-01-01", None)


def test_runtime_guard_accepts_canonical_window() -> None:
    # No exception expected.
    assert_v9_oos_lock("warbird_pro_v9", "2020-01-01", "2024-12-31")


def test_runtime_guard_skips_non_v9_keys() -> None:
    # Nexus / other lanes are not under the V9 lock; their windows are owned
    # by their own profile contracts.
    assert_v9_oos_lock("warbird_nexus_ml_rsi", "2025-01-01", None)


def test_runbook_v9_runs_use_canonical_window() -> None:
    """Every Optuna invocation in the V9 runbook must use the canonical
    2020-2024 IS window. Lines containing --start 2025- are forbidden."""
    text = RUNBOOK_PATH.read_text()
    forbidden = re.findall(r"--start\s+2025-\d{2}-\d{2}", text)
    assert forbidden == [], (
        f"Runbook contains forbidden --start 2025-* lines: {forbidden}. "
        "HPO windows must be --start 2020-01-01 --end 2024-12-31."
    )
    # Affirmative: the canonical window must appear at least once for each
    # of the two documented HPO steps.
    assert text.count("--start 2020-01-01") >= 2
    assert text.count("--end 2024-12-31") >= 2


def test_runbook_lock_contract_explicit() -> None:
    """The runbook must explicitly document the OOS lock so a future agent
    cannot regress without clearly editing the contract section."""
    text = RUNBOOK_PATH.read_text()
    assert "IS / OOS window contract" in text
    assert "2025-01-01" in text  # boundary must be referenced
    assert "Bug 2" in text  # reference to the historical regression
