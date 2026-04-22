#!/usr/bin/env python3
"""Canonical path helpers for the Warbird Optuna workspace."""

from __future__ import annotations

from pathlib import Path


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
