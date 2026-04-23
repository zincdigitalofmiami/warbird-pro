#!/usr/bin/env python3
"""
VS Code Optuna workspace doctor.

Verifies the editor-facing Optuna workflow for this repo:
- VS Code CLI + Optuna Dashboard extension presence
- repo Python/optuna-dashboard binaries
- study DBs visible from the workspace
- persistent service ports and editor-safe sidecar ports
"""

from __future__ import annotations

import json
import shutil
import socket
import subprocess
import sys
from collections.abc import Sequence
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.optuna.paths import WORKSPACES_ROOT, study_db_path

REGISTRY_PATH = REPO_ROOT / "scripts" / "optuna" / "indicator_registry.json"

PERSISTENT_ENDPOINTS: list[tuple[str, str]] = [
    ("hub", "http://localhost:8090/api/snapshot"),
]

WORKTREE_PATHS: list[str] = [
    "AGENTS.md",
    "CLAUDE.md",
    "docs/MASTER_PLAN.md",
    "docs/runbooks/wbv7_institutional_optuna.md",
    "docs/runbooks/optuna_legacy_strategy_tuning.md",
    "scripts/optuna",
]

VSCODE_PORTS: list[tuple[str, int]] = [
    ("shared-dashboard", 8180),
    ("hub", 8190),
    ("hub-child-start", 8200),
]


def load_registry() -> list[dict[str, Any]]:
    raw = json.loads(REGISTRY_PATH.read_text())
    if not isinstance(raw, list):
        raise SystemExit(f"Invalid registry format: {REGISTRY_PATH}")
    return [row for row in raw if isinstance(row, dict)]


def resolve_db_path(spec: dict[str, Any]) -> Path:
    key = str(spec.get("key", "")).strip()
    return study_db_path(key)


def http_ok(url: str) -> tuple[bool, str]:
    request = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=2) as response:
            return True, str(response.status)
    except urllib.error.HTTPError as exc:
        return False, f"http {exc.code}"
    except Exception as exc:  # pragma: no cover - best effort diagnostics
        return False, str(exc)


def port_open(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.25)
        return sock.connect_ex((host, port)) == 0


def installed_extension_version(code_bin: str | None, extension_id: str) -> str | None:
    if not code_bin:
        return None
    try:
        result = subprocess.run(
            [code_bin, "--list-extensions", "--show-versions"],
            check=True,
            capture_output=True,
            text=True,
        )
    except Exception:
        return None

    for line in result.stdout.splitlines():
        if line.startswith(f"{extension_id}@"):
            return line.split("@", 1)[1].strip()
    return None


def print_section(title: str) -> None:
    print(title)
    print("-" * len(title))


def git_status_lines(paths: Sequence[str]) -> list[str]:
    try:
        result = subprocess.run(
            ["git", "status", "--short", "--untracked-files=all", "--", *paths],
            check=True,
            capture_output=True,
            text=True,
            cwd=str(REPO_ROOT),
        )
    except Exception:
        return ["git status unavailable"]

    lines = [line.rstrip() for line in result.stdout.splitlines() if line.strip()]
    return lines or ["clean"]


def main() -> None:
    print("VS Code Optuna workspace doctor")
    print(f"workspace: {REPO_ROOT}")
    print()

    code_bin = shutil.which("code")
    extension_version = installed_extension_version(code_bin, "optuna.optuna-dashboard")
    python_bin = REPO_ROOT / ".venv" / "bin" / "python"
    optuna_dashboard_bin = REPO_ROOT / ".venv" / "bin" / "optuna-dashboard"

    print_section("Editor")
    print(f"- code CLI: {code_bin or 'missing'}")
    print(
        "- optuna extension: "
        + (
            f"optuna.optuna-dashboard@{extension_version}"
            if extension_version
            else "missing"
        )
    )
    print(
        f"- python interpreter: {python_bin} [{'ok' if python_bin.exists() else 'missing'}]"
    )
    print(
        f"- optuna-dashboard bin: {optuna_dashboard_bin} "
        f"[{'ok' if optuna_dashboard_bin.exists() else 'missing'}]"
    )
    print()

    specs = load_registry()
    registry_db_paths = {resolve_db_path(spec).resolve() for spec in specs}
    active_specs = []
    for spec in specs:
        db_path = resolve_db_path(spec)
        if db_path.exists():
            active_specs.append((str(spec.get("key", "")), db_path))

    all_db_paths = sorted(WORKSPACES_ROOT.glob("**/study.db"))
    extra_db_paths = [
        path for path in all_db_paths if path.resolve() not in registry_db_paths
    ]

    print_section("Study DBs")
    if active_specs:
        print("- registry-backed")
        for key, db_path in active_specs:
            print(f"  {key}: {db_path}")
    else:
        print("- registry-backed: none found")

    if extra_db_paths:
        print("- additional on-disk DBs")
        for db_path in extra_db_paths:
            print(f"  {db_path.relative_to(REPO_ROOT)}")
    else:
        print("- additional on-disk DBs: none")
    print()

    print_section("Persistent Services")
    for label, url in PERSISTENT_ENDPOINTS:
        ok, detail = http_ok(url)
        print(f"- {label}: {url} [{'up' if ok else 'down'}: {detail}]")

    hub_ok, _ = http_ok("http://localhost:8090/api/snapshot")
    if hub_ok:
        try:
            with urllib.request.urlopen(
                "http://localhost:8090/api/snapshot", timeout=2
            ) as response:
                snapshot = json.loads(response.read().decode("utf-8"))
        except Exception:
            snapshot = {}

        cards = snapshot.get("cards", []) if isinstance(snapshot, dict) else []
        child_cards = [
            card
            for card in cards
            if isinstance(card, dict)
            and card.get("db_exists")
            and card.get("dashboard_url")
        ]
        if child_cards:
            print("- hub child dashboards")
            for card in child_cards:
                print(f"  {card.get('key')}: {card.get('dashboard_url')}")
    print()

    print_section("Worktree Truth")
    for line in git_status_lines(WORKTREE_PATHS):
        print(f"- {line}")
    print()

    print_section("VS Code Sidecar Ports")
    for label, port in VSCODE_PORTS:
        status = "busy" if port_open("localhost", port) else "free"
        print(f"- {label}: localhost:{port} [{status}]")
    print()

    print_section("Usage")
    print("- primary live hub: http://localhost:8090/")
    print("- current-runtime-only health: `python scripts/optuna/runtime_health.py`")
    print("- stale log cleanup: `python scripts/optuna/prune_runtime_logs.py --apply`")
    print("- open `.vscode/OPTUNA_WORKSPACE.md` for one-click Simple Browser links")
    print(
        "- right-click any study.db file in Explorer and run `Open in Optuna Dashboard`"
    )
    print("- optional Run and Debug sidecars:")
    print("  `Optuna: Optional Sidecar Hub (8190)`")
    print("  `Optuna: Optional Sidecar V7 Institutional Dashboard (8182)`")
    print("- tasks:")
    print("  `Optuna: Doctor`")
    print("  `Optuna: Print Study Layout`")


if __name__ == "__main__":
    main()
