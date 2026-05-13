from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd
import pytest

from scripts.ag.v9_data_quality_gate import (
    validate_duplicate_real_signals,
    validate_manifest_hash,
    validate_required_columns,
    validate_signal_health,
)


def _write_csv(path: Path) -> None:
    path.write_text("ts,value\n2026-01-01T00:00:00+00:00,1\n")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    digest.update(path.read_bytes())
    return digest.hexdigest()


def test_required_column_detection() -> None:
    frame = pd.DataFrame({"ts": ["2026-01-01T00:00:00+00:00"], "value": [1.0]})

    with pytest.raises(RuntimeError, match="missing required columns"):
        validate_required_columns(frame, ["ts", "value", "ml_entry_long_trigger"])


def test_manifest_hash_mismatch_detection(tmp_path: Path) -> None:
    csv_path = tmp_path / "es_15m_core.csv"
    manifest_path = csv_path.with_suffix(".manifest.json")
    _write_csv(csv_path)

    manifest = {
        "sha256": "deadbeef",
        "symbol": "ES",
        "timeframe": "15",
    }
    manifest_path.write_text(json.dumps(manifest))

    with pytest.raises(RuntimeError, match="manifest hash mismatch"):
        validate_manifest_hash(csv_path, manifest_path)


def test_duplicate_real_signal_columns_are_caught() -> None:
    frame = pd.DataFrame(
        {
            "ml_signal_a": [1.0, 2.0, 3.0, 4.0],
            "ml_signal_b": [1.0, 2.0, 3.0, 4.0],
            "knob_length_ma": [50.0, 50.0, 50.0, 50.0],
        }
    )

    with pytest.raises(RuntimeError, match="duplicate real signal columns"):
        validate_duplicate_real_signals(
            frame,
            signal_columns=["ml_signal_a", "ml_signal_b", "knob_length_ma"],
            allow_constant_columns={"knob_length_ma"},
        )


def test_near_dead_or_constant_continuous_signal_is_caught() -> None:
    frame = pd.DataFrame(
        {
            "ml_signal_near_dead": [1.0] * 99 + [2.0],
            "ml_signal_constant": [5.0] * 100,
        }
    )

    with pytest.raises(RuntimeError, match="near-dead continuous signal"):
        validate_signal_health(
            frame,
            continuous_columns=["ml_signal_near_dead"],
            min_unique_ratio=0.05,
        )

    with pytest.raises(RuntimeError, match="constant continuous signal"):
        validate_signal_health(
            frame,
            continuous_columns=["ml_signal_constant"],
            min_unique_ratio=0.05,
        )


def test_constant_knob_settings_columns_are_whitelisted() -> None:
    frame = pd.DataFrame(
        {
            "knob_length_ma": [50.0, 50.0, 50.0, 50.0],
            "ml_signal_ok": [0.1, 0.2, 0.3, 0.4],
        }
    )

    validate_signal_health(
        frame,
        continuous_columns=["knob_length_ma", "ml_signal_ok"],
        knob_constant_whitelist={"knob_length_ma"},
        min_unique_ratio=0.05,
    )


def test_sparse_event_flags_require_explicit_whitelist() -> None:
    frame = pd.DataFrame(
        {
            "ml_event_sparse_ok": [0] * 99 + [1],
            "ml_event_sparse_blocked": [0] * 99 + [1],
            "ml_signal_ok": [0.1, 0.2, 0.3, 0.4] * 25,
        }
    )

    validate_signal_health(
        frame,
        continuous_columns=["ml_signal_ok"],
        sparse_event_columns=["ml_event_sparse_ok"],
        sparse_event_whitelist={"ml_event_sparse_ok"},
        min_unique_ratio=0.05,
        sparse_event_max_density=0.02,
    )

    with pytest.raises(RuntimeError, match="sparse event flag requires whitelist"):
        validate_signal_health(
            frame,
            continuous_columns=["ml_signal_ok"],
            sparse_event_columns=["ml_event_sparse_blocked"],
            sparse_event_whitelist={"ml_event_sparse_ok"},
            min_unique_ratio=0.05,
            sparse_event_max_density=0.02,
        )


def test_manifest_hash_accepts_matching_digest(tmp_path: Path) -> None:
    csv_path = tmp_path / "es_15m_core.csv"
    manifest_path = csv_path.with_suffix(".manifest.json")
    _write_csv(csv_path)

    manifest = {
        "sha256": _sha256(csv_path),
        "symbol": "ES",
        "timeframe": "15",
    }
    manifest_path.write_text(json.dumps(manifest))

    validate_manifest_hash(csv_path, manifest_path)
