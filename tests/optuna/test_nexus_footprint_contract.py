from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from scripts.optuna import warbird_nexus_ml_rsi_profile as profile


def test_nexus_profile_rejects_csv_input(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(profile.TV_FOOTPRINT_ENV, "/tmp/nexus-footprint.csv")

    with pytest.raises(ValueError, match="CSV input is disabled"):
        profile._resolve_tv_footprint_path()


def test_nexus_profile_rejects_plain_ohlcv_frame() -> None:
    frame = pd.DataFrame(
        {
            "ts": [pd.Timestamp("2026-04-26T14:00:00Z")],
            "open": [7190.0],
            "high": [7196.5],
            "low": [7185.0],
            "close": [7194.0],
            "volume": [1000.0],
        }
    )

    with pytest.raises(ValueError, match="nexus_fp_bar_delta"):
        profile._prepare_tv_footprint_frame(frame)


def test_nexus_profile_accepts_tv_footprint_frame_and_uses_fp_volume() -> None:
    frame = pd.DataFrame(
        {
            "ts": [pd.Timestamp("2026-04-26T14:00:00Z")],
            "open": [7190.0],
            "high": [7196.5],
            "low": [7185.0],
            "close": [7194.0],
            "volume": [999999.0],
            "nexus_fp_available": [1.0],
            "nexus_fp_bar_delta": [225.0],
            "nexus_fp_total_volume": [1200.0],
        }
    )

    prepared = profile._prepare_tv_footprint_frame(frame)

    assert prepared.loc[0, "volume"] == 1200.0
    assert prepared.loc[0, "nexus_fp_bar_delta"] == 225.0


def test_nexus_manifest_requires_tv_footprint_capture_method(tmp_path: Path) -> None:
    snapshot = tmp_path / "tv_footprint_5m.parquet"
    snapshot.write_bytes(b"not a real parquet; manifest validation happens first")
    manifest = tmp_path / "tv_footprint_5m.manifest.json"
    manifest.write_text('{"capture_method":"LOCAL_OHLCV_PARQUET"}')

    with pytest.raises(ValueError, match="capture_method"):
        profile._load_tv_footprint_manifest(snapshot)
