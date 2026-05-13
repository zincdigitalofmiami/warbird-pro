from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd
import pytest

from scripts.ag import backfill_v9_run_provenance as backfill


def _write_csv(path: Path) -> None:
    path.write_text(
        "ts,value\n"
        "2026-01-01T00:00:00+00:00,1\n"
        "2026-01-01T00:15:00+00:00,2\n"
        "2026-01-01T00:30:00+00:00,3\n"
        "2026-01-01T00:45:00+00:00,4\n"
    )


def _summary_path(tmp_path: Path) -> tuple[Path, Path, Path]:
    run_dir = tmp_path / "run"
    run_dir.mkdir(parents=True, exist_ok=True)
    csv_path = tmp_path / "es_15m_core.csv"
    _write_csv(csv_path)
    summary_path = run_dir / "v9_winner_clf_summary.json"
    return run_dir, csv_path, summary_path


def test_backfill_idempotent_when_summary_already_has_provenance(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run_dir, csv_path, summary_path = _summary_path(tmp_path)
    summary_path.write_text(
        json.dumps(
            {
                "csv_path": str(csv_path),
                "csv_sha256": "abc",
                "run_provenance": {"csv_sha256": "abc"},
                "split_ranges_utc": {"train": {"ts_start": None, "ts_end": None}},
                "is_rows": 2,
                "val_rows": 1,
                "oos_rows": 1,
            }
        )
    )

    monkeypatch.setattr(
        sys,
        "argv",
        ["backfill_v9_run_provenance.py", "--predictor-path", str(run_dir)],
    )

    rc = backfill.main()
    assert rc == 0
    assert not summary_path.with_suffix(".pre_backfill.json").exists()


def test_backfill_refuses_manifest_hash_drift(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run_dir, csv_path, summary_path = _summary_path(tmp_path)
    summary_path.write_text(
        json.dumps(
            {
                "csv_path": str(csv_path),
                "is_rows": 2,
                "val_rows": 1,
                "oos_rows": 1,
            }
        )
    )

    monkeypatch.setattr(
        backfill,
        "build_csv_provenance",
        lambda _p: {
            "csv_sha256": "actual",
            "manifest_declared_csv_sha256": "declared",
            "manifest_csv_sha256_matches": False,
        },
    )
    monkeypatch.setattr(
        sys,
        "argv",
        ["backfill_v9_run_provenance.py", "--predictor-path", str(run_dir)],
    )

    with pytest.raises(SystemExit, match="CSV has drifted from manifest's declared hash"):
        backfill.main()


def test_backfill_refuses_row_count_parity_drift(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run_dir, csv_path, summary_path = _summary_path(tmp_path)
    summary_path.write_text(
        json.dumps(
            {
                "csv_path": str(csv_path),
                "is_rows": 10,
                "val_rows": 10,
                "oos_rows": 10,
            }
        )
    )

    monkeypatch.setattr(
        backfill,
        "build_csv_provenance",
        lambda _p: {
            "csv_sha256": "actual",
            "manifest_declared_csv_sha256": "actual",
            "manifest_csv_sha256_matches": True,
        },
    )
    monkeypatch.setattr(backfill, "validate_input_schema", lambda _df: None)
    monkeypatch.setattr(
        backfill,
        "build_trade_dataset",
        lambda _df: pd.DataFrame(
            {
                "ts": pd.to_datetime(
                    [
                        "2026-01-01T00:00:00+00:00",
                        "2026-01-01T00:15:00+00:00",
                        "2026-01-01T00:30:00+00:00",
                        "2026-01-01T00:45:00+00:00",
                    ],
                    utc=True,
                )
            }
        ),
    )
    monkeypatch.setattr(backfill, "split_trade_positions", lambda *_args, **_kwargs: ([0, 1], [2], [3]))
    monkeypatch.setattr(
        sys,
        "argv",
        ["backfill_v9_run_provenance.py", "--predictor-path", str(run_dir)],
    )

    with pytest.raises(SystemExit, match="Row-count parity gate failed"):
        backfill.main()


def test_backfill_writes_backup_and_updates_summary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run_dir, csv_path, summary_path = _summary_path(tmp_path)
    summary_path.write_text(
        json.dumps(
            {
                "csv_path": str(csv_path),
                "is_rows": 2,
                "val_rows": 1,
                "oos_rows": 1,
            }
        )
    )

    monkeypatch.setattr(
        backfill,
        "build_csv_provenance",
        lambda _p: {
            "csv_sha256": "actual",
            "manifest_declared_csv_sha256": "actual",
            "manifest_csv_sha256_matches": True,
            "manifest_sha256": "manifest",
        },
    )
    monkeypatch.setattr(backfill, "validate_input_schema", lambda _df: None)
    monkeypatch.setattr(
        backfill,
        "build_trade_dataset",
        lambda _df: pd.DataFrame(
            {
                "ts": pd.to_datetime(
                    [
                        "2026-01-01T00:00:00+00:00",
                        "2026-01-01T00:15:00+00:00",
                        "2026-01-01T00:30:00+00:00",
                        "2026-01-01T00:45:00+00:00",
                    ],
                    utc=True,
                )
            }
        ),
    )
    monkeypatch.setattr(backfill, "split_trade_positions", lambda *_args, **_kwargs: ([0, 1], [2], [3]))
    monkeypatch.setattr(
        sys,
        "argv",
        ["backfill_v9_run_provenance.py", "--predictor-path", str(run_dir)],
    )

    rc = backfill.main()
    assert rc == 0

    backup_path = summary_path.with_suffix(".pre_backfill.json")
    assert backup_path.exists()

    updated = json.loads(summary_path.read_text())
    assert updated["csv_sha256"] == "actual"
    assert isinstance(updated.get("run_provenance"), dict)
    assert isinstance(updated.get("split_ranges_utc"), dict)
    assert isinstance(updated.get("split_contract"), dict)