from __future__ import annotations

from pathlib import Path

import pandas as pd

from scripts.optuna.warbird_optuna_hub import REGISTRY_PATH, build_run_command, load_registry
from scripts.optuna.warbird_nexus_ml_rsi_profile import _manifest_mode_minutes, _normalize_export_frame


CANONICAL_STUDIES = {
    "v7_warbird_institutional": {
        "profile_module": "scripts.optuna.v7_warbird_institutional_profile",
        "study_name": "Warbird Institutional Signal Optimization",
    },
    "warbird_nexus_ml_rsi": {
        "profile_module": "scripts.optuna.warbird_nexus_ml_rsi_profile",
        "study_name": "Warbird Nexus ML Fast 5m Signal Quality April 25",
    },
}


def _registry_by_key() -> dict[str, object]:
    specs = load_registry(Path(REGISTRY_PATH))
    assert len(specs) == len({spec.key for spec in specs})
    return {spec.key: spec for spec in specs}


def test_registry_uses_canonical_hub_studies_only_for_warbird_and_nexus() -> None:
    specs = _registry_by_key()

    assert "wb7" not in specs

    for key, expected in CANONICAL_STUDIES.items():
        spec = specs[key]
        assert spec.profile_module == expected["profile_module"]
        assert spec.default_study_name == expected["study_name"]


def test_hub_run_command_resumes_existing_canonical_studies() -> None:
    specs = _registry_by_key()

    for key, expected in CANONICAL_STUDIES.items():
        command = build_run_command(specs[key])
        assert f"--indicator-key {key}" in command
        assert f"--profile-module {expected['profile_module']}" in command
        assert f"--study-name '{expected['study_name']}'" in command
        assert "--resume" in command

    nexus_command = build_run_command(specs["warbird_nexus_ml_rsi"])
    assert "--n-trials 1000" in nexus_command


def test_nexus_export_normalizes_numeric_tradingview_epoch_seconds() -> None:
    raw = pd.DataFrame(
        {
            "time": [1_710_000_000],
            "open": [1.0],
            "high": [2.0],
            "low": [0.5],
            "close": [1.5],
            "volume": [100.0],
            "Nexus FP Available": [1.0],
            "Nexus FP Bar Delta": [25.0],
            "Nexus FP Total Volume": [100.0],
            "Nexus Mode Minutes": [5.0],
        }
    )

    frame = _normalize_export_frame(raw)

    assert frame.loc[0, "ts"] == pd.Timestamp(1_710_000_000, unit="s", tz="UTC")


def test_nexus_manifest_mode_minutes_accepts_string_and_numeric_modes() -> None:
    assert _manifest_mode_minutes({"pine_mode": "1H"}) == 60.0
    assert _manifest_mode_minutes({"timeframe": 5.0}) == 5.0
