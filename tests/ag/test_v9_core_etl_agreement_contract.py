from __future__ import annotations

from pathlib import Path

import pandas as pd

from scripts.duckdb_local.workspaces.warbird_pro_core import build_core_dataset as core


def _entry_row(
    *,
    nq_code: float,
    sixe_code: float,
    zn_code: float,
    vix_pressure: float,
) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "ts": pd.Timestamp("2026-01-01T00:00:00Z"),
                "__is_valid": True,
                "__trigger_long": True,
                "__trigger_short": True,
                "__recent_liq_bull": True,
                "__recent_liq_bear": True,
                "ml_ma_bias": 1.0,
                "ml_xa_nq_code": float(nq_code),
                "ml_xa_6e_code": float(sixe_code),
                "ml_xa_zn_code": float(zn_code),
                "ml_xa_vix_pressure": float(vix_pressure),
            }
        ]
    )


def test_agreement_count_uses_only_nq_and_6e_votes() -> None:
    row = _entry_row(nq_code=1.0, sixe_code=-1.0, zn_code=1.0, vix_pressure=-10.0)
    out = core.finalize_entries(row)

    # Locked 2026-05-12 lean contract: agreement counts are NQ + 6E only.
    assert float(out.loc[0, "ml_xa_long_agreement"]) == 1.0
    assert float(out.loc[0, "ml_xa_short_agreement"]) == 1.0


def test_zn_and_vix_changes_do_not_affect_agreement_output() -> None:
    left = _entry_row(nq_code=1.0, sixe_code=1.0, zn_code=1.0, vix_pressure=-10.0)
    right = _entry_row(nq_code=1.0, sixe_code=1.0, zn_code=-1.0, vix_pressure=10.0)

    out_left = core.finalize_entries(left)
    out_right = core.finalize_entries(right)

    assert float(out_left.loc[0, "ml_xa_long_agreement"]) == float(
        out_right.loc[0, "ml_xa_long_agreement"]
    )
    assert float(out_left.loc[0, "ml_xa_short_agreement"]) == float(
        out_right.loc[0, "ml_xa_short_agreement"]
    )
    assert float(out_left.loc[0, "ml_xa_long_agreement"]) == 2.0
    assert float(out_left.loc[0, "ml_xa_short_agreement"]) == 0.0


def test_write_outputs_drops_removed_columns(tmp_path: Path) -> None:
    source_path = tmp_path / "source.csv"
    source_path.write_text("dummy\n")
    profile_path = tmp_path / "profile.html"
    profile_path.write_text("<html></html>")

    frame = pd.DataFrame(
        [
            {
                "ts": pd.Timestamp("2026-01-01T00:00:00Z"),
                "ml_entry_long_trigger": 0.0,
                "ml_entry_short_trigger": 0.0,
                "ml_fp_delta_pct": 1.23,
                "ml_xa_long_agreement": 2.0,
                "ml_xa_short_agreement": 1.0,
            }
        ]
    )

    csv_path, _ = core.write_outputs(
        frame,
        out_dir=tmp_path,
        symbol="ES",
        timeframe="15",
        source=source_path,
        trades_zip=None,
        profiling_report_path=profile_path,
        profiling_rows_profiled=1,
        profiling_sampled=False,
        manifest_extra={},
    )

    exported = pd.read_csv(csv_path)
    assert "ml_fp_delta_pct" not in set(exported.columns)


def test_write_outputs_keeps_agreement_columns(tmp_path: Path) -> None:
    source_path = tmp_path / "source.csv"
    source_path.write_text("dummy\n")
    profile_path = tmp_path / "profile.html"
    profile_path.write_text("<html></html>")

    frame = pd.DataFrame(
        [
            {
                "ts": pd.Timestamp("2026-01-01T00:00:00Z"),
                "ml_entry_long_trigger": 1.0,
                "ml_entry_short_trigger": 0.0,
                "ml_xa_long_agreement": 2.0,
                "ml_xa_short_agreement": 0.0,
            }
        ]
    )

    csv_path, _ = core.write_outputs(
        frame,
        out_dir=tmp_path,
        symbol="ES",
        timeframe="15",
        source=source_path,
        trades_zip=None,
        profiling_report_path=profile_path,
        profiling_rows_profiled=1,
        profiling_sampled=False,
        manifest_extra={},
    )

    exported = pd.read_csv(csv_path)
    assert "ml_xa_long_agreement" in set(exported.columns)
    assert "ml_xa_short_agreement" in set(exported.columns)