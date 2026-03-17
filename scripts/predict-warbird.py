#!/usr/bin/env python3
"""
Legacy Warbird inference entrypoint.

This wrapper preserves the historical script path while delegating execution to
the canonical Warbird v1 inference writer in scripts/warbird/predict-warbird.py.
"""

from __future__ import annotations

import runpy
import sys
from pathlib import Path


def main() -> None:
    canonical_script = Path(__file__).resolve().parent / "warbird" / "predict-warbird.py"
    if not canonical_script.exists():
        raise SystemExit(f"Canonical predictor not found: {canonical_script}")

    print("Deprecated entrypoint: delegating to scripts/warbird/predict-warbird.py")
    sys.argv[0] = str(canonical_script)
    runpy.run_path(str(canonical_script), run_name="__main__")


if __name__ == "__main__":
    main()
