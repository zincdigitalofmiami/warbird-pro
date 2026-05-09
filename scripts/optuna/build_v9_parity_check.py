#!/usr/bin/env python3
"""DEPRECATED 2026-05-09 — Pine V9 ↔ Python replay parity check (Hybrid+ chain).

This parity-check artifact verified that scripts/optuna/v9_replay.py matched
the live V9 Pine output. Retired with the Hybrid+ chain; the Core ETL builds
features directly from Databento and does not use a Pine↔Python replay path.

Original implementation preserved in git history. See commit history pre-2026-05-09
for the legacy 50-long / 50-short sampler.
"""
from __future__ import annotations

import sys

raise SystemExit(
    "build_v9_parity_check is DEPRECATED (Hybrid+ chain). The Core ETL builds "
    "features directly from Databento; no Pine↔Python replay parity check needed."
)
