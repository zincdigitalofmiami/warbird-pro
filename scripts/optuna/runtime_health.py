#!/usr/bin/env python3
"""Current-runtime-only health probe for the Warbird Optuna hub."""

from __future__ import annotations

import json
import socket
import sqlite3
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import quote, urljoin, urlparse


REPO_ROOT = Path(__file__).resolve().parents[2]
HUB_URL = "http://localhost:8090"
SNAPSHOT_URL = f"{HUB_URL}/api/snapshot"
LEGACY_PORT = 8080
TIMEOUT_SECONDS = 3
CHILD_START_TIMEOUT_SECONDS = 8
CHILD_START_POLL_SECONDS = 0.2


@dataclass
class CheckResult:
    ok: bool
    label: str
    detail: str


def _fetch_json(url: str) -> tuple[int, Any]:
    request = urllib.request.Request(url, method="GET")
    with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
        payload = response.read().decode("utf-8")
        return response.status, json.loads(payload)


def _port_open(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.25)
        return sock.connect_ex((host, port)) == 0


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _open_study_url(key: str) -> str:
    encoded_key = quote(key, safe="")
    request = urllib.request.Request(f"{HUB_URL}/open-study/{encoded_key}", method="GET")
    opener = urllib.request.build_opener(_NoRedirect)
    try:
        with opener.open(request, timeout=TIMEOUT_SECONDS) as response:
            location = response.headers.get("Location") or response.geturl()
            if not location:
                raise RuntimeError(f"{key} launch response did not include a location")
            return urljoin(HUB_URL, location)
    except urllib.error.HTTPError as exc:
        if exc.code not in {301, 302, 303, 307, 308}:
            raise
        location = exc.headers.get("Location")
        if not location:
            raise RuntimeError(f"{key} launch redirect did not include a location")
        return urljoin(HUB_URL, location)


def _wait_for_dashboard(url: str) -> bool:
    parsed = urlparse(url)
    if not parsed.hostname or not parsed.port:
        return False

    deadline = time.monotonic() + CHILD_START_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        if _port_open(parsed.hostname, parsed.port):
            return True
        time.sleep(CHILD_START_POLL_SECONDS)
    return False


def _sqlite_counts(db_path: Path, study_name: str | None = None) -> dict[str, int]:
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        cur = con.cursor()
        studies = cur.execute("SELECT COUNT(*) FROM studies").fetchone()[0]
        where_clause = ""
        params: tuple[Any, ...] = ()
        if study_name:
            where_clause = "WHERE study_id = (SELECT study_id FROM studies WHERE study_name = ?)"
            params = (study_name,)
        total, complete, running, pruned, fail = cur.execute(
            f"""
            SELECT
                COUNT(*),
                SUM(CASE WHEN state = 'COMPLETE' THEN 1 ELSE 0 END),
                SUM(CASE WHEN state = 'RUNNING' THEN 1 ELSE 0 END),
                SUM(CASE WHEN state = 'PRUNED' THEN 1 ELSE 0 END),
                SUM(CASE WHEN state = 'FAIL' THEN 1 ELSE 0 END)
            FROM trials
            {where_clause}
            """,
            params,
        ).fetchone()
        return {
            "study_count": int(studies or 0),
            "trial_count": int(total or 0),
            "complete_count": int(complete or 0),
            "running_count": int(running or 0),
            "pruned_count": int(pruned or 0),
            "fail_count": int(fail or 0),
        }
    finally:
        con.close()


def _study_id(studies_payload: dict[str, Any], target_study_name: str | None = None) -> int | None:
    summaries = studies_payload.get("study_summaries")
    if not isinstance(summaries, list) or not summaries:
        return None
    if target_study_name:
        for summary in summaries:
            if not isinstance(summary, dict):
                continue
            if _text(summary.get("study_name")) != target_study_name:
                continue
            study_id = summary.get("study_id")
            return int(study_id) if isinstance(study_id, int) else None
    first = summaries[0]
    if not isinstance(first, dict):
        return None
    study_id = first.get("study_id")
    return int(study_id) if isinstance(study_id, int) else None


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def run() -> int:
    checks: list[CheckResult] = []
    failures: list[str] = []

    try:
        root_status, _ = (
            urllib.request.urlopen(HUB_URL, timeout=TIMEOUT_SECONDS).status,
            None,
        )
        checks.append(
            CheckResult(root_status == 200, "hub root", f"{HUB_URL} -> {root_status}")
        )
    except Exception as exc:
        checks.append(CheckResult(False, "hub root", f"{HUB_URL} -> {exc}"))
        failures.append("hub root unreachable")

    try:
        snapshot_status, snapshot = _fetch_json(SNAPSHOT_URL)
        cards = snapshot.get("cards") if isinstance(snapshot, dict) else None
        if snapshot_status != 200 or not isinstance(cards, list):
            raise RuntimeError(
                f"unexpected snapshot payload (status={snapshot_status})"
            )
        checks.append(
            CheckResult(
                True,
                "hub snapshot",
                f"cards={len(cards)} active_studies={snapshot.get('active_studies')}",
            )
        )
    except Exception as exc:
        checks.append(CheckResult(False, "hub snapshot", str(exc)))
        snapshot = {"cards": []}
        cards = []
        failures.append("hub snapshot unavailable")

    legacy_open = _port_open("127.0.0.1", LEGACY_PORT)
    checks.append(
        CheckResult(
            not legacy_open,
            "legacy 8080 retired",
            "closed" if not legacy_open else "still listening",
        )
    )
    if legacy_open:
        failures.append("legacy 8080 port still open")

    active_cards = [
        card for card in cards if isinstance(card, dict) and card.get("db_exists")
    ]
    for card in active_cards:
        key = _text(card.get("key")) or "unknown"
        dashboard_url = _text(card.get("dashboard_url"))
        db_path = Path(_text(card.get("db_path")))
        target_study_name = _text(card.get("default_study_name"))

        if not dashboard_url:
            try:
                dashboard_url = _open_study_url(key)
                checks.append(
                    CheckResult(
                        True,
                        f"{key} dashboard launch",
                        f"launched {dashboard_url}",
                    )
                )
            except Exception as exc:
                checks.append(
                    CheckResult(False, f"{key} dashboard launch", str(exc))
                )
                failures.append(f"{key} dashboard launch failed")
                continue

        parsed = urlparse(dashboard_url)
        port = parsed.port
        port_ok = bool(
            parsed.hostname
            and port
            and (_port_open(parsed.hostname, port) or _wait_for_dashboard(dashboard_url))
        )
        if not port_ok:
            try:
                relaunched_url = _open_study_url(key)
                if relaunched_url:
                    dashboard_url = relaunched_url
                    parsed = urlparse(dashboard_url)
                    port = parsed.port
                    port_ok = _wait_for_dashboard(dashboard_url)
            except Exception:
                port_ok = False
        checks.append(
            CheckResult(
                port_ok,
                f"{key} child port",
                f"{dashboard_url} {'open' if port_ok else 'closed'}",
            )
        )
        if not port_ok:
            failures.append(f"{key} child port closed")

        if not db_path.exists():
            checks.append(CheckResult(False, f"{key} sqlite db", f"missing {db_path}"))
            failures.append(f"{key} missing study.db")
            continue

        try:
            sqlite_counts = _sqlite_counts(
                db_path,
                _text(card.get("default_study_name")),
            )
        except Exception as exc:
            checks.append(CheckResult(False, f"{key} sqlite db", f"read failed: {exc}"))
            failures.append(f"{key} sqlite unreadable")
            continue

        snapshot_counts = {
            "study_count": int(card.get("study_count") or 0),
            "trial_count": int(card.get("trial_count") or 0),
            "complete_count": int(card.get("complete_count") or 0),
            "running_count": int(card.get("running_count") or 0),
            "pruned_count": int(card.get("pruned_count") or 0),
            "fail_count": int(card.get("fail_count") or 0),
        }
        counts_match = sqlite_counts == snapshot_counts
        checks.append(
            CheckResult(
                counts_match,
                f"{key} snapshot vs sqlite",
                f"snapshot={snapshot_counts} sqlite={sqlite_counts}",
            )
        )
        if not counts_match:
            failures.append(f"{key} snapshot/sqlite mismatch")

        try:
            meta_status, meta_payload = _fetch_json(f"{dashboard_url}/api/meta")
            studies_status, studies_payload = _fetch_json(
                f"{dashboard_url}/api/studies"
            )
            study_id = _study_id(studies_payload, target_study_name)
            if study_id is None:
                raise RuntimeError("missing study_id from /api/studies")
            detail_status, detail_payload = _fetch_json(
                f"{dashboard_url}/api/studies/{study_id}?after=0"
            )
            importance_status, importance_payload = _fetch_json(
                f"{dashboard_url}/api/studies/{study_id}/param_importances"
            )

            meta_ok = meta_status == 200 and isinstance(meta_payload, dict)
            studies_ok = studies_status == 200 and isinstance(
                studies_payload.get("study_summaries"), list
            )
            detail_ok = (
                detail_status == 200
                and isinstance(detail_payload, dict)
                and "trials" in detail_payload
            )
            importance_ok = (
                importance_status == 200
                and isinstance(importance_payload, dict)
                and "param_importances" in importance_payload
            )
            checks.append(
                CheckResult(meta_ok, f"{key} /api/meta", f"status={meta_status}")
            )
            checks.append(
                CheckResult(
                    studies_ok,
                    f"{key} /api/studies",
                    f"status={studies_status} study_id={study_id}",
                )
            )
            checks.append(
                CheckResult(
                    detail_ok,
                    f"{key} /api/studies/{study_id}",
                    f"status={detail_status} trials={len(detail_payload.get('trials', [])) if isinstance(detail_payload, dict) else 'n/a'}",
                )
            )
            checks.append(
                CheckResult(
                    importance_ok,
                    f"{key} /api/studies/{study_id}/param_importances",
                    f"status={importance_status}",
                )
            )
            if not all((meta_ok, studies_ok, detail_ok, importance_ok)):
                failures.append(f"{key} child API failure")
        except (
            urllib.error.HTTPError,
            urllib.error.URLError,
            RuntimeError,
            ValueError,
        ) as exc:
            checks.append(CheckResult(False, f"{key} child APIs", str(exc)))
            failures.append(f"{key} child API exception")

    print("Warbird Optuna current-runtime health")
    print(f"repo: {REPO_ROOT}")
    print()
    for check in checks:
        badge = "PASS" if check.ok else "FAIL"
        print(f"[{badge}] {check.label}: {check.detail}")

    print()
    if failures:
        print(f"FAILURES: {len(failures)}")
        for failure in failures:
            print(f"- {failure}")
        return 1

    print(f"PASS: runtime healthy across {len(active_cards)} active study lane(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
