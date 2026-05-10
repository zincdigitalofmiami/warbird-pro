#!/usr/bin/env python3
"""Canonical path helpers for the Warbird Optuna workspace."""

from __future__ import annotations

from pathlib import Path
from typing import SupportsInt


REPO_ROOT = Path(__file__).resolve().parents[2]
OPTUNA_ROOT = REPO_ROOT / "scripts" / "optuna"
WORKSPACES_ROOT = OPTUNA_ROOT / "workspaces"
ARCHIVE_ROOT = OPTUNA_ROOT / "archive"


def workspace_dir(indicator_key: str) -> Path:
    return WORKSPACES_ROOT / indicator_key


def experiments_dir(indicator_key: str) -> Path:
    return workspace_dir(indicator_key) / "experiments"


def study_db_path(indicator_key: str) -> Path:
    return workspace_dir(indicator_key) / "study.db"


def normalize_symbol_root(symbol: str) -> str:
    token = str(symbol).upper().strip()
    if ":" in token:
        token = token.split(":", 1)[1]
    token = token.replace("!", "")
    root = ""
    for char in token:
        if char.isalpha():
            root += char
        else:
            break
    return root


def normalize_timeframe_label(timeframe: str | int | SupportsInt) -> str:
    text = str(int(timeframe) if not isinstance(timeframe, str) else timeframe).strip().lower()
    if text.endswith("m"):
        text = text[:-1]
    if not text.isdigit():
        raise ValueError(f"Unsupported timeframe label: {timeframe!r}")
    return f"{int(text)}m"


def contract_experiment_name(symbol: str, timeframe: str | int | SupportsInt) -> str:
    root = normalize_symbol_root(symbol).lower()
    if not root:
        raise ValueError(f"Could not derive symbol root from {symbol!r}")
    return f"{root}_{normalize_timeframe_label(timeframe)}"


def contract_experiment_dir(
    indicator_key: str,
    *,
    symbol: str,
    timeframe: str | int | SupportsInt,
) -> Path:
    return experiments_dir(indicator_key) / contract_experiment_name(symbol, timeframe)


def contract_study_db_path(
    indicator_key: str,
    *,
    symbol: str,
    timeframe: str | int | SupportsInt,
) -> Path:
    return contract_experiment_dir(indicator_key, symbol=symbol, timeframe=timeframe) / "study.db"
