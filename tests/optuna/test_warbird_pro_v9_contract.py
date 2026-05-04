from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd
import pytest

from scripts.optuna import warbird_pro_v9_profile as profile


def _write_export(
    path: Path,
    *,
    symbol: str,
    trigger_every: int = 3,
    capture_method: str = "TRADINGVIEW_INDICATOR_CSV",
    indicator_file: str | None = profile.PINE_FILE,
) -> None:
    rows = []
    start = pd.Timestamp("2026-01-02T14:30:00Z")
    for idx in range(40):
        base = 4800.0 + idx
        rows.append(
            {
                "time": int((start + pd.Timedelta(minutes=5 * idx)).timestamp()),
                "open": base,
                "high": base + 3.0,
                "low": base - 1.0,
                "close": base + 1.0,
                "volume": 1000 + idx,
                "ml_entry_long_trigger": 1.0 if idx % trigger_every == 0 else 0.0,
                "ml_entry_short_trigger": 0.0,
                "ml_fib_neg_0236": base - 12.0,
            }
        )
    frame = pd.DataFrame(rows)
    frame.to_csv(path, index=False)
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    manifest = {
        "capture_method": capture_method,
        "trigger_family": profile.TRIGGER_FAMILY,
        "symbol": symbol,
        "timeframe": "5",
        "sha256": digest,
    }
    if indicator_file is not None:
        manifest["indicator_file"] = indicator_file
    path.with_suffix(".manifest.json").write_text(json.dumps(manifest))


def test_v9_contract_excludes_fib_negative_stop_candidates() -> None:
    profile.assert_v9_contract()

    stop_families = set(profile.CATEGORICAL_PARAMS.get("stopFamilyId", []))
    assert "FIB_NEG_0236" not in stop_families
    assert "FIB_NEG_0382" not in stop_families


def test_v9_contract_keeps_fib_visuals_and_ma_setup_frozen() -> None:
    tunables = (
        set(profile.BOOL_PARAMS)
        | set(profile.NUMERIC_RANGES)
        | set(profile.CATEGORICAL_PARAMS)
    )

    assert profile.FROZEN_PINE_PARAMS.isdisjoint(tunables)


def test_v9_loader_accepts_es_mes_and_ignores_nq(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    export_dir = tmp_path / "exports"
    export_dir.mkdir()
    _write_export(export_dir / "mes.csv", symbol="CME_MINI:MES1!")
    _write_export(export_dir / "es.csv", symbol="CME_MINI:ES1!")
    _write_export(export_dir / "nq.csv", symbol="CME_MINI:NQ1!")

    monkeypatch.setattr(profile, "OPTUNA_DIR", tmp_path)

    frame = profile.load_data()

    assert set(frame["symbol_root"]) == {"MES", "ES"}
    assert all("nq.csv" not in source for source in frame["_source_csv"].unique())
    assert len(frame.attrs["ignored_exports"]) == 1


def test_v9_loader_keeps_neg236_as_context_not_stop(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    export_dir = tmp_path / "exports"
    export_dir.mkdir()
    _write_export(export_dir / "mes.csv", symbol="MES1!")
    monkeypatch.setattr(profile, "OPTUNA_DIR", tmp_path)

    frame = profile.load_data()

    assert "fib_neg_0236_context" in frame.columns
    assert frame["fib_neg_0236_context"].notna().any()
    assert "stopFamilyId" not in profile.CATEGORICAL_PARAMS


def test_v9_loader_accepts_databento_training_data_without_indicator_source(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    export_dir = tmp_path / "exports"
    export_dir.mkdir()
    _write_export(
        export_dir / "mes_databento.csv",
        symbol="MES1!",
        capture_method="DATABENTO_OHLCV_CSV",
        indicator_file=None,
    )
    monkeypatch.setattr(profile, "OPTUNA_DIR", tmp_path)

    frame = profile.load_data()

    assert set(frame["symbol_root"]) == {"MES"}
    assert frame["_source_kind"].eq("DATABENTO_OHLCV_CSV").all()
