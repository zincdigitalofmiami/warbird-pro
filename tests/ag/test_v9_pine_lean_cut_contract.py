from __future__ import annotations

import os
from pathlib import Path

import pytest


PINE_PATH = Path("/Volumes/Satechi Hub/warbird-pro/indicators/warbird-pro-v9.pine")
ENFORCE_PINE_LEAN_CUT = os.getenv("WARBIRD_ENFORCE_PINE_LEAN_CUT", "0") == "1"


def _pine_source() -> str:
    return PINE_PATH.read_text()


@pytest.mark.skipif(
    not ENFORCE_PINE_LEAN_CUT,
    reason="Pine lean-cut enforcement disabled until explicit Pine-edit approval",
)
def test_post_cut_removes_zn_vix_exports_and_requests() -> None:
    src = _pine_source()
    assert "request.security(znSymbol" not in src
    assert "request.security(vixSymbol" not in src
    assert '"ml_xa_zn_code"' not in src
    assert '"ml_xa_vix_pressure"' not in src


@pytest.mark.skipif(
    not ENFORCE_PINE_LEAN_CUT,
    reason="Pine lean-cut enforcement disabled until explicit Pine-edit approval",
)
def test_post_cut_removes_footprint_request_and_exports() -> None:
    src = _pine_source()
    assert "request.footprint(" not in src
    assert '"ml_fp_delta_pct"' not in src
    assert '"ml_fp_poc_dist_atr"' not in src
    assert '"ml_fp_va_position"' not in src
    assert '"ml_delta_imbalance_pct"' not in src
    assert '"ml_delta_acceleration"' not in src
    assert '"ml_aggressor_pulse"' not in src
    assert '"ml_absorption_candidate"' not in src
    assert '"ml_flush_candidate"' not in src
    assert '"ml_poc_shift"' not in src


@pytest.mark.skipif(
    not ENFORCE_PINE_LEAN_CUT,
    reason="Pine lean-cut enforcement disabled until explicit Pine-edit approval",
)
def test_post_cut_removes_daily_weekly_level_emissions() -> None:
    src = _pine_source()
    assert '"ml_lvl_pdh_dist_atr"' not in src
    assert '"ml_lvl_pdl_dist_atr"' not in src
    assert '"ml_lvl_pwh_dist_atr"' not in src
    assert '"ml_lvl_pwl_dist_atr"' not in src


@pytest.mark.skipif(
    not ENFORCE_PINE_LEAN_CUT,
    reason="Pine lean-cut enforcement disabled until explicit Pine-edit approval",
)
def test_post_cut_removes_redundant_fib_touch_binary_emissions() -> None:
    src = _pine_source()
    assert '"ml_fib_touch_500_long"' not in src
    assert '"ml_fib_touch_618_long"' not in src
    assert '"ml_fib_touch_786_long"' not in src
    assert '"ml_fib_touch_500_short"' not in src
    assert '"ml_fib_touch_618_short"' not in src
    assert '"ml_fib_touch_786_short"' not in src