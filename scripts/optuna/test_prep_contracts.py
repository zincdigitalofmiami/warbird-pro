from __future__ import annotations

import hashlib
import importlib
import json
from pathlib import Path

import pandas as pd

from scripts.optuna import paths
from scripts.optuna import warbird_pro_v9_profile as v9_profile

core_card = importlib.import_module(
    "scripts.optuna.cards.core_training.2026_05_09_warbird_pro_autogluon_core"
)


def _write_export(path: Path, *, symbol: str, timeframe: str) -> None:
    rows = []
    start = pd.Timestamp("2026-01-02T14:30:00Z")
    step_minutes = int(str(timeframe).replace("m", ""))
    for idx in range(12):
        base = 5100.0 + idx
        rows.append(
            {
                "time": int((start + pd.Timedelta(minutes=step_minutes * idx)).timestamp()),
                "open": base,
                "high": base + 4.0,
                "low": base - 2.0,
                "close": base + 1.0,
                "volume": 1000 + idx,
                "ml_entry_long_trigger": 1.0 if idx % 3 == 0 else 0.0,
                "ml_entry_short_trigger": 0.0,
                "ml_fib_neg_0236": base - 8.0,
            }
        )
    frame = pd.DataFrame(rows)
    frame.to_csv(path, index=False)
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    manifest = {
        "capture_method": "DATABENTO_OHLCV_CSV",
        "trigger_family": v9_profile.TRIGGER_FAMILY,
        "symbol": symbol,
        "timeframe": timeframe,
        "sha256": digest,
    }
    path.with_suffix(".manifest.json").write_text(json.dumps(manifest))


def test_contract_experiment_paths_are_symbol_and_timeframe_specific() -> None:
    exp_dir = paths.contract_experiment_dir("warbird_pro_core", symbol="ES1!", timeframe="15m")
    assert exp_dir == (
        paths.workspace_dir("warbird_pro_core") / "experiments" / "es_15m"
    )
    assert paths.contract_study_db_path("warbird_pro_core", symbol="ES1!", timeframe="15m") == (
        exp_dir / "study.db"
    )


def test_v9_loader_accepts_es_15m_exports(tmp_path: Path, monkeypatch) -> None:
    export_dir = tmp_path / "exports"
    export_dir.mkdir()
    _write_export(export_dir / "es_15m.csv", symbol="CME_MINI:ES1!", timeframe="15")
    monkeypatch.setattr(v9_profile, "OPTUNA_DIR", tmp_path)

    frame = v9_profile.load_data()

    assert set(frame["symbol_root"]) == {"ES"}
    assert frame["timeframe"].eq("15").all()


def test_core_card_resolves_contract_study_db_from_manifest(tmp_path: Path) -> None:
    manifest_path = tmp_path / "es_15m_core.manifest.json"
    manifest_path.write_text(json.dumps({"symbol": "ES1!", "timeframe": "15"}))

    assert core_card.resolve_study_db_path(None, manifest_path) == (
        paths.workspace_dir(core_card.CARD_KEY) / "experiments" / "es_15m" / "study.db"
    )
