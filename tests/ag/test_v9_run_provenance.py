import json
from pathlib import Path

import pandas as pd
import pytest

from scripts.ag.v9_run_provenance import (
    apply_time_split,
    build_csv_provenance,
    check_summary_csv_hash,
)


def _write_csv(path: Path) -> None:
    path.write_text("ts,value\n2026-01-01T00:00:00+00:00,1\n")


def test_build_csv_provenance_reads_manifest_and_validates_hash(tmp_path: Path) -> None:
    csv_path = tmp_path / "es_15m_core.csv"
    _write_csv(csv_path)

    initial = build_csv_provenance(csv_path)
    manifest = {
        "sha256": initial["csv_sha256"],
        "symbol": "ES1!",
        "timeframe": "15",
    }
    csv_path.with_suffix(".manifest.json").write_text(json.dumps(manifest))

    payload = build_csv_provenance(csv_path)

    assert payload["csv_sha256"] == initial["csv_sha256"]
    assert payload["manifest_declared_csv_sha256"] == initial["csv_sha256"]
    assert payload["manifest_csv_sha256_matches"] is True
    assert payload["manifest_sha256"]


def test_check_summary_csv_hash_matches_when_summary_has_run_provenance(tmp_path: Path) -> None:
    csv_path = tmp_path / "es_15m_core.csv"
    _write_csv(csv_path)
    payload = build_csv_provenance(csv_path)

    summary = {
        "run_provenance": {
            "csv_sha256": payload["csv_sha256"],
        }
    }
    check = check_summary_csv_hash(csv_path, summary)
    assert check["checked"] is True
    assert check["matches"] is True


def test_apply_time_split_prefers_summary_ranges_over_legacy_dates() -> None:
    frame = pd.DataFrame(
        {
            "ts": [
                "2024-12-31T23:45:00+00:00",
                "2025-01-02T00:00:00+00:00",
                "2025-02-01T00:00:00+00:00",
                "2025-03-01T00:00:00+00:00",
            ],
            "x": [1, 2, 3, 4],
        }
    )

    summary = {
        "split_ranges_utc": {
            "train": {
                "ts_start": "2024-12-31T00:00:00+00:00",
                "ts_end": "2025-01-15T00:00:00+00:00",
            },
            "val": {
                "ts_start": "2025-01-16T00:00:00+00:00",
                "ts_end": "2025-02-15T00:00:00+00:00",
            },
            "oos": {
                "ts_start": "2025-02-16T00:00:00+00:00",
                "ts_end": "2025-03-31T00:00:00+00:00",
            },
        }
    }

    split_df, source = apply_time_split(
        frame,
        split="oos",
        ts_col="ts",
        summary=summary,
        legacy_oos_start=pd.Timestamp("2025-01-01", tz="UTC"),
        legacy_is_end=pd.Timestamp("2024-12-31T23:59:59", tz="UTC"),
    )

    assert source == "summary_split_ranges_utc"
    assert list(split_df["x"]) == [4]


def test_apply_time_split_all_does_not_require_summary() -> None:
    frame = pd.DataFrame(
        {
            "ts": [
                "2024-12-31T23:45:00+00:00",
                "2025-01-02T00:00:00+00:00",
            ],
            "x": [1, 2],
        }
    )

    split_df, source = apply_time_split(
        frame,
        split="all",
        ts_col="ts",
        summary=None,
    )

    assert source == "all"
    assert list(split_df["x"]) == [1, 2]


def test_apply_time_split_fails_closed_when_summary_missing() -> None:
    frame = pd.DataFrame(
        {
            "ts": [
                "2024-12-31T23:45:00+00:00",
                "2025-01-02T00:00:00+00:00",
            ],
            "x": [1, 2],
        }
    )

    with pytest.raises(RuntimeError, match="requires run summary"):
        apply_time_split(
            frame,
            split="oos",
            ts_col="ts",
            summary=None,
            legacy_oos_start=pd.Timestamp("2025-01-01", tz="UTC"),
        )


def test_apply_time_split_fails_closed_when_summary_missing_ranges() -> None:
    frame = pd.DataFrame(
        {
            "ts": [
                "2024-12-31T23:45:00+00:00",
                "2025-01-02T00:00:00+00:00",
                "2025-03-01T00:00:00+00:00",
            ],
            "x": [1, 2, 3],
        }
    )

    with pytest.raises(RuntimeError, match="missing split_ranges_utc"):
        apply_time_split(
            frame,
            split="is",
            ts_col="ts",
            summary={},
            legacy_is_end=pd.Timestamp("2025-01-15", tz="UTC"),
        )


def test_apply_time_split_val_still_fails_closed_without_summary_ranges() -> None:
    frame = pd.DataFrame(
        {
            "ts": [
                "2024-12-31T23:45:00+00:00",
                "2025-01-02T00:00:00+00:00",
            ],
            "x": [1, 2],
        }
    )

    with pytest.raises(RuntimeError, match="split=val requires run summary"):
        apply_time_split(
            frame,
            split="val",
            ts_col="ts",
            summary=None,
            legacy_oos_start=pd.Timestamp("2025-01-01", tz="UTC"),
            legacy_is_end=pd.Timestamp("2024-12-31T23:59:59", tz="UTC"),
        )
