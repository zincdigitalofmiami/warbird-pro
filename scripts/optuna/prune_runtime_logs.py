#!/usr/bin/env python3
"""Archive stale Optuna hub child logs under /tmp without touching active lanes."""

from __future__ import annotations

import argparse
import shutil
from datetime import datetime
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
WORKSPACES_ROOT = REPO_ROOT / "scripts" / "optuna" / "workspaces"
LOG_ROOT = Path("/tmp/warbird-optuna-hub")


def active_keys() -> set[str]:
    return {path.name for path in WORKSPACES_ROOT.iterdir() if path.is_dir()}


def stale_logs() -> list[Path]:
    if not LOG_ROOT.exists():
        return []

    live_keys = active_keys()
    stale: list[Path] = []
    for path in sorted(LOG_ROOT.glob("*.log")):
        if path.name == "hub.log" and path.stat().st_size == 0:
            stale.append(path)
            continue
        if path.stem not in live_keys and path.name != "hub.log":
            stale.append(path)
    return stale


def archive_dir() -> Path:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return LOG_ROOT / "archive" / stamp


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Archive stale Optuna runtime logs under /tmp"
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Move stale log files into a timestamped archive directory",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    targets = stale_logs()
    print("Warbird Optuna runtime log pruning")
    print(f"log root: {LOG_ROOT}")
    print(f"active keys: {sorted(active_keys())}")
    print()

    if not targets:
        print("No stale logs found.")
        return 0

    print("Stale logs:")
    for path in targets:
        print(f"- {path} ({path.stat().st_size} bytes)")

    if not args.apply:
        print()
        print("Dry run only. Re-run with --apply to archive these files.")
        return 0

    destination = archive_dir()
    destination.mkdir(parents=True, exist_ok=True)
    for path in targets:
        shutil.move(str(path), str(destination / path.name))

    print()
    print(f"Archived {len(targets)} stale log(s) to {destination}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
