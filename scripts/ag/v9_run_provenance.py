from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pandas as pd

HASH_KEYS: tuple[str, ...] = ("sha256", "csv_sha256", "export_hash")


def sha256_file(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def manifest_path_for_csv(csv_path: Path) -> Path:
    return csv_path.with_suffix(".manifest.json")


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def _manifest_declared_csv_sha256(manifest: dict[str, Any]) -> str | None:
    for key in HASH_KEYS:
        value = manifest.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def build_csv_provenance(csv_path: Path) -> dict[str, Any]:
    csv_hash = sha256_file(csv_path)
    manifest_path = manifest_path_for_csv(csv_path)

    payload: dict[str, Any] = {
        "csv_path": str(csv_path),
        "csv_sha256": csv_hash,
        "manifest_path": str(manifest_path) if manifest_path.exists() else None,
        "manifest_sha256": None,
        "manifest_declared_csv_sha256": None,
        "manifest_csv_sha256_matches": None,
    }

    if not manifest_path.exists():
        return payload

    payload["manifest_sha256"] = sha256_file(manifest_path)
    manifest = _load_json(manifest_path)
    declared = _manifest_declared_csv_sha256(manifest)
    payload["manifest_declared_csv_sha256"] = declared
    if declared:
        payload["manifest_csv_sha256_matches"] = declared.lower() == csv_hash.lower()
    return payload


def discover_run_summary_path(
    predictor_path_input: Path,
    explicit_run_summary: Path | None,
) -> Path | None:
    if explicit_run_summary is not None:
        return explicit_run_summary

    candidates = [
        predictor_path_input / "v9_winner_clf_summary.json",
        predictor_path_input.parent / "v9_winner_clf_summary.json",
    ]
    for candidate in candidates:
        resolved = candidate.resolve(strict=False)
        if resolved.exists():
            return resolved
    return None


def load_run_summary(path: Path | None) -> dict[str, Any] | None:
    if path is None:
        return None
    if not path.exists():
        raise RuntimeError(f"Run summary not found: {path}")
    summary = _load_json(path)
    if not isinstance(summary, dict):
        raise RuntimeError(f"Run summary is not a JSON object: {path}")
    return summary


def _summary_csv_sha256(summary: dict[str, Any]) -> str | None:
    run_provenance = summary.get("run_provenance")
    if isinstance(run_provenance, dict):
        value = run_provenance.get("csv_sha256")
        if isinstance(value, str) and value.strip():
            return value.strip()

    value = summary.get("csv_sha256")
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def check_summary_csv_hash(csv_path: Path, summary: dict[str, Any]) -> dict[str, Any]:
    actual = sha256_file(csv_path)
    expected = _summary_csv_sha256(summary)
    if not expected:
        return {
            "checked": False,
            "expected": None,
            "actual": actual,
            "matches": None,
            "reason": "summary_missing_csv_sha256",
        }

    matches = expected.lower() == actual.lower()
    return {
        "checked": True,
        "expected": expected,
        "actual": actual,
        "matches": matches,
    }


def split_bounds_from_summary(
    summary: dict[str, Any],
    split: str,
) -> tuple[pd.Timestamp | None, pd.Timestamp | None]:
    split_key = {
        "is": "train",
        "train": "train",
        "val": "val",
        "oos": "oos",
    }.get(split)
    if split_key is None:
        raise RuntimeError(f"Unsupported split: {split}")

    ranges = summary.get("split_ranges_utc")
    if not isinstance(ranges, dict):
        raise RuntimeError("Run summary missing split_ranges_utc")

    range_item = ranges.get(split_key)
    if not isinstance(range_item, dict):
        raise RuntimeError(f"Run summary missing split range for '{split_key}'")

    ts_start_raw = range_item.get("ts_start")
    ts_end_raw = range_item.get("ts_end")
    ts_start = pd.to_datetime(ts_start_raw, utc=True) if ts_start_raw else None
    ts_end = pd.to_datetime(ts_end_raw, utc=True) if ts_end_raw else None
    return ts_start, ts_end


def _filter_by_bounds(
    frame: pd.DataFrame,
    *,
    ts_col: str,
    ts_start: pd.Timestamp | None,
    ts_end: pd.Timestamp | None,
) -> pd.DataFrame:
    ts = pd.to_datetime(frame[ts_col], utc=True)
    mask = pd.Series(True, index=frame.index)
    if ts_start is not None:
        mask &= ts >= ts_start
    if ts_end is not None:
        mask &= ts <= ts_end
    return frame.loc[mask].copy().reset_index(drop=True)


def apply_time_split(
    frame: pd.DataFrame,
    *,
    split: str,
    ts_col: str,
    summary: dict[str, Any] | None,
    legacy_oos_start: pd.Timestamp | None = None,
    legacy_is_end: pd.Timestamp | None = None,
) -> tuple[pd.DataFrame, str]:
    split = str(split).lower().strip()
    if split == "all":
        return frame.copy().reset_index(drop=True), "all"

    if summary is None:
        raise RuntimeError(
            f"split={split} requires run summary with split_ranges_utc"
        )

    ts_start, ts_end = split_bounds_from_summary(summary, split)
    filtered = _filter_by_bounds(
        frame,
        ts_col=ts_col,
        ts_start=ts_start,
        ts_end=ts_end,
    )
    return filtered, "summary_split_ranges_utc"
