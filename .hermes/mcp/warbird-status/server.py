#!/usr/bin/env python3
# pyright: reportMissingImports=false
"""Read-only Warbird status MCP server."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any, Literal

from mcp.server.fastmcp import FastMCP

REPO = Path("/Volumes/Satechi Hub/warbird-pro")
CHARACTER_LIMIT = 25000

mcp = FastMCP(
    "warbird_status_mcp",
    instructions=(
        "Read-only Warbird-Pro status tools. Do not use these tools to edit Pine, "
        "launch TradingView, run training, or mutate Supabase."
    ),
)


def _run(args: list[str], timeout: int = 30) -> dict[str, Any]:
    try:
        result = subprocess.run(
            args,
            cwd=REPO,
            text=True,
            capture_output=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        return {
            "ok": False,
            "error": f"Timed out after {timeout}s: {exc}",
            "stdout": "",
            "stderr": "",
        }
    return {
        "ok": result.returncode == 0,
        "returncode": result.returncode,
        "stdout": _truncate(result.stdout),
        "stderr": _truncate(result.stderr),
    }


def _truncate(text: str) -> str:
    if len(text) <= CHARACTER_LIMIT:
        return text
    return text[:CHARACTER_LIMIT] + f"\n[truncated at {CHARACTER_LIMIT} characters]"


def _format(
    payload: dict[str, Any], response_format: Literal["json", "markdown"]
) -> str | dict[str, Any]:
    if response_format == "json":
        return payload
    return "```json\n" + json.dumps(payload, indent=2, sort_keys=True) + "\n```"


@mcp.tool()
def warbird_git_status(
    response_format: Literal["json", "markdown"] = "markdown",
) -> str | dict[str, Any]:
    """Return concise git branch, upstream, status, and recent commit information."""
    payload = {
        "branch": _run(["git", "branch", "--show-current"]),
        "upstream": _run(
            ["git", "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"]
        ),
        "status_short": _run(["git", "status", "--short"]),
        "recent_commits": _run(["git", "log", "--oneline", "-10"]),
    }
    return _format(payload, response_format)


@mcp.tool()
def warbird_validator_summary(
    response_format: Literal["json", "markdown"] = "markdown",
) -> str | dict[str, Any]:
    """Return read-only validator availability and precheck-log summary."""
    precheck_dir = REPO / ".git" / "warbird-prechecks"
    logs = []
    if precheck_dir.exists():
        logs = [
            p.name
            for p in sorted(
                precheck_dir.glob("*"), key=lambda p: p.stat().st_mtime, reverse=True
            )[:10]
        ]
    payload = {
        "tc_validator_path": _run(["bash", "-lc", "command -v tc_validator || true"]),
        "precheck_log_dir_exists": precheck_dir.exists(),
        "recent_precheck_logs": logs,
        "guards": {
            "pine_lint": (REPO / "scripts/guards/pine-lint.sh").exists(),
            "fib_guardrails": (
                REPO / "scripts/guards/check-fib-scanner-guardrails.sh"
            ).exists(),
            "contamination": (REPO / "scripts/guards/check-contamination.sh").exists(),
            "no_tv_force": (REPO / "scripts/guards/check-no-tv-force.sh").exists(),
        },
    }
    return _format(payload, response_format)


@mcp.tool()
def warbird_dataset_manifest_summary(
    response_format: Literal["json", "markdown"] = "markdown",
) -> str | dict[str, Any]:
    """Return summary fields from the locked V9 Core manifest if present."""
    manifest = (
        REPO
        / "scripts/duckdb_local/workspaces/warbird_pro_core/exports/es_15m_core.manifest.json"
    )
    if not manifest.exists():
        payload = {
            "ok": False,
            "manifest": str(manifest),
            "error": "manifest not found",
        }
        return _format(payload, response_format)
    data = json.loads(manifest.read_text())
    keys = [
        "source_kind",
        "symbol",
        "timeframe",
        "row_count",
        "candidate_count",
        "start_ts",
        "end_ts",
        "feature_count_locked",
        "trigger_family",
    ]
    payload = {
        "ok": True,
        "manifest": str(manifest),
        "fields": {k: data.get(k) for k in keys},
    }
    return _format(payload, response_format)


@mcp.tool()
def warbird_tv_doctor_status(
    response_format: Literal["json", "markdown"] = "markdown",
) -> str | dict[str, Any]:
    """Run the read-only TradingView connection doctor and return its JSON output."""
    result = _run(
        ["python3", "scripts/ag/tv_connection_doctor.py", "--json"], timeout=45
    )
    payload: dict[str, Any] = {
        "command": "python3 scripts/ag/tv_connection_doctor.py --json",
        "result": result,
    }
    if result["stdout"]:
        try:
            payload["doctor_json"] = json.loads(result["stdout"])
        except json.JSONDecodeError:
            payload["doctor_json_parse_error"] = True
    return _format(payload, response_format)


if __name__ == "__main__":
    mcp.run()
