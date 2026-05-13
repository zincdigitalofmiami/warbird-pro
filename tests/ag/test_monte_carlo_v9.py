from __future__ import annotations

import sys
import types
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from scripts.ag import monte_carlo_v9 as mc


def test_slippage_cost_math() -> None:
    assert mc._slippage_cost_rt(1.0) == 25.0
    assert mc._slippage_cost_rt(2.0) == 50.0


def test_resolve_payoff_arrays_per_row_math() -> None:
    trades = pd.DataFrame(
        {
            "entry_price": [100.0, 200.0],
            "target_price": [101.0, 203.0],
            "stop_price": [99.0, 198.0],
        }
    )

    win, loss = mc._resolve_payoff_arrays(
        trades,
        fallback_sl_pts=7.0,
        fallback_tp_pts=14.0,
        slippage_ticks=1.0,
    )

    np.testing.assert_allclose(win, np.array([23.0, 123.0]))
    np.testing.assert_allclose(loss, np.array([-77.0, -127.0]))


def test_model_suite_detection_requires_all_heads(tmp_path: Path) -> None:
    assert mc._is_suite_root(tmp_path) is False

    for head in mc.SUITE_HEADS:
        head_dir = tmp_path / head
        head_dir.mkdir(parents=True, exist_ok=True)
        (head_dir / "predictor.pkl").write_text("x")

    assert mc._is_suite_root(tmp_path) is True

    # A direct predictor.pkl indicates single-head path, not suite root.
    (tmp_path / "predictor.pkl").write_text("x")
    assert mc._is_suite_root(tmp_path) is False


def test_task_j_output_shape_and_semantics() -> None:
    trades = pd.DataFrame(
        {
            mc.LABEL_COL: [1, 0, 1, 0, 1, 0],
            mc.TP_LABEL_COL: [1, 0, 1, 0, 1, 0],
            mc.STOP_LABEL_COL: [0, 1, 0, 1, 0, 1],
            mc.MFE_LABEL_COL: [3.0, 1.0, 2.5, 1.2, 3.4, 0.9],
            mc.MAE_LABEL_COL: [0.8, 2.0, 1.1, 2.3, 0.7, 2.1],
            "target_distance_points": [4.0, 4.0, 4.0, 4.0, 4.0, 4.0],
            "stop_distance_points": [2.0, 2.0, 2.0, 2.0, 2.0, 2.0],
        }
    )
    suite_predictions = {
        "entry": np.array([0.8, 0.2, 0.7, 0.3, 0.75, 0.25]),
        "tp": np.array([0.7, 0.2, 0.6, 0.3, 0.65, 0.25]),
        "stop": np.array([0.2, 0.8, 0.3, 0.7, 0.25, 0.75]),
        "mfe": np.array([3.1, 1.2, 2.4, 1.0, 3.2, 1.1]),
        "mae": np.array([0.9, 1.9, 1.2, 2.2, 0.8, 2.0]),
    }
    payoffs_win = np.array([100, 100, 100, 100, 100, 100], dtype=float)
    payoffs_loss = np.array([-60, -60, -60, -60, -60, -60], dtype=float)

    out = mc.task_J_multi_head(
        trades=trades,
        suite_predictions=suite_predictions,
        payoffs_win=payoffs_win,
        payoffs_loss=payoffs_loss,
        trade_cost_rt=27.0,
    )

    assert out["n_trades"] == 6
    assert "ev_entry_only" in out
    assert "ev_multi_head_conservative" in out
    assert "tp_head_calibration" in out
    assert "stop_head_calibration" in out
    assert "entry_head_calibration" in out
    assert "mfe_regressor_quality" in out
    assert "mae_regressor_quality" in out
    assert isinstance(out["head_correlations"], dict)
    assert np.isfinite(out["ev_multi_head_conservative"]["delta_vs_entry_only_mean"])


def test_main_enforces_run_summary_hash_binding(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    csv_path = tmp_path / "es_15m_core.csv"
    csv_path.write_text("ts,close\n2026-01-01T00:00:00+00:00,100\n")

    class _FakePredictor:
        problem_type = "binary"

        @staticmethod
        def load(_path: str, require_py_version_match: bool = False) -> "_FakePredictor":
            return _FakePredictor()

        def persist(self) -> None:
            return None

    fake_ag = types.ModuleType("autogluon")
    fake_tabular = types.ModuleType("autogluon.tabular")
    fake_tabular.TabularPredictor = _FakePredictor
    fake_ag.tabular = fake_tabular
    monkeypatch.setitem(sys.modules, "autogluon", fake_ag)
    monkeypatch.setitem(sys.modules, "autogluon.tabular", fake_tabular)

    monkeypatch.setattr(mc, "_resolve_predictor_path", lambda p: p)
    monkeypatch.setattr(
        mc,
        "_build_trades",
        lambda _df: pd.DataFrame(
            {
                "ts": pd.to_datetime(["2026-01-01T00:00:00+00:00"], utc=True),
                mc.LABEL_COL: [1.0],
            }
        ),
    )
    monkeypatch.setattr(mc, "discover_run_summary_path", lambda *_args, **_kwargs: Path("summary.json"))
    monkeypatch.setattr(mc, "load_run_summary", lambda _path: {"run_provenance": {"csv_sha256": "expected"}})
    monkeypatch.setattr(
        mc,
        "check_summary_csv_hash",
        lambda *_args, **_kwargs: {
            "checked": True,
            "matches": False,
            "expected": "expected",
            "actual": "actual",
        },
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "monte_carlo_v9.py",
            "--predictor-path",
            str(tmp_path),
            "--csv",
            str(csv_path),
            "--split",
            "oos",
        ],
    )

    with pytest.raises(SystemExit, match="CSV hash mismatch against run summary"):
        mc.main()