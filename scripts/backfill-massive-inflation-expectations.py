#!/usr/bin/env python3
"""
Backfill Massive inflation expectations into econ_inflation_1d.

Scope:
- Pull exactly 2 years of history from Massive /fed/v1/inflation-expectations
- Map all published inflation-expectation fields to provider-tagged series_id values
- Upsert to econ_inflation_1d on (ts, series_id)
"""
from __future__ import annotations

import os
import time
from datetime import date, timedelta

import requests
from supabase import create_client

from project_env import load_project_env

ENDPOINT = "https://api.massive.com/fed/v1/inflation-expectations"

FIELD_TO_SERIES_ID = {
    "forward_years_5_to_10": "MASSIVE_IE_FORWARD_YEARS_5_TO_10",
    "market_10_year": "MASSIVE_IE_MARKET_10_YEAR",
    "market_5_year": "MASSIVE_IE_MARKET_5_YEAR",
    "model_10_year": "MASSIVE_IE_MODEL_10_YEAR",
    "model_1_year": "MASSIVE_IE_MODEL_1_YEAR",
    "model_30_year": "MASSIVE_IE_MODEL_30_YEAR",
    "model_5_year": "MASSIVE_IE_MODEL_5_YEAR",
}


def retry_after_seconds(value: str | None) -> float | None:
    if not value:
        return None
    value = value.strip()
    if not value:
        return None
    try:
        return max(float(value), 0.0)
    except ValueError:
        return None


def with_api_key(url: str, api_key: str) -> str:
    if "apiKey=" in url:
        return url
    sep = "&" if "?" in url else "?"
    return f"{url}{sep}apiKey={api_key}"


def fetch_all(api_key: str, start_date: str) -> list[dict]:
    params = {
        "date.gte": start_date,
        "limit": "50000",
        "sort": "date.asc",
    }
    rows: list[dict] = []
    seen: set[str] = set()

    next_url: str | None = ENDPOINT
    next_params: dict | None = params

    while next_url:
        url = with_api_key(next_url, api_key)
        if url in seen:
            break
        seen.add(url)

        max_attempts = 5
        resp = None
        for attempt in range(1, max_attempts + 1):
            current = requests.get(url, params=next_params, timeout=30)
            if current.status_code not in (429, 500, 502, 503, 504):
                resp = current
                break

            if attempt == max_attempts:
                resp = current
                break

            retry_after = retry_after_seconds(current.headers.get("Retry-After"))
            if retry_after is None:
                retry_after = 0.5 * (2 ** (attempt - 1))
            time.sleep(retry_after)

        assert resp is not None
        if resp.status_code >= 400:
            raise RuntimeError(
                f"Massive API error {resp.status_code}: {resp.text}"
            )
        payload = resp.json()

        results = payload.get("results") or []
        if isinstance(results, list):
            rows.extend(results)

        raw_next = payload.get("next_url")
        if raw_next:
            next_url = str(raw_next)
            next_params = None
        else:
            next_url = None
            next_params = None

    return rows


def build_rows(observations: list[dict]) -> list[dict]:
    by_key: dict[str, dict] = {}

    for obs in observations:
        day = obs.get("date")
        if not day:
            continue
        ts = f"{day}T00:00:00Z"

        for field, series_id in FIELD_TO_SERIES_ID.items():
            value = obs.get(field)
            if value is None:
                continue
            try:
                numeric = float(value)
            except (TypeError, ValueError):
                continue

            key = f"{ts}|{series_id}"
            by_key[key] = {"ts": ts, "series_id": series_id, "value": numeric}

    return list(by_key.values())


def main() -> None:
    load_project_env()

    api_key = os.environ["MASSIVE_API_KEY"]
    sb_url = os.environ.get("NEXT_PUBLIC_SUPABASE_URL") or os.environ["SUPABASE_URL"]
    sb_key = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
    supabase = create_client(sb_url, sb_key)

    start_date = (date.today() - timedelta(days=730)).isoformat()

    print(f"Fetching Massive inflation expectations from {start_date}...")
    observations = fetch_all(api_key, start_date)
    print(f"Fetched {len(observations)} observations")

    rows = build_rows(observations)
    print(f"Prepared {len(rows)} rows for upsert")

    written = 0
    for i in range(0, len(rows), 500):
        chunk = rows[i : i + 500]
        supabase.table("econ_inflation_1d").upsert(
            chunk,
            on_conflict="ts,series_id",
        ).execute()
        written += len(chunk)

    print(f"Done. Upserted {written} rows to econ_inflation_1d.")


if __name__ == "__main__":
    main()
