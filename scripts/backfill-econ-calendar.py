#!/usr/bin/env python3
"""
Backfill econ_calendar from FRED releases API.
Maps major economic releases to high importance (3) for CPI, NFP, FOMC, GDP, etc.
Falls back to importance=1 for other releases.
Uses batch inserts and retry logic to avoid connection exhaustion.
"""
from __future__ import annotations

import os
import time
from datetime import date, timedelta

import requests
from supabase import create_client

from project_env import load_project_env

HIGH_IMPORTANCE_RELEASES = {
    10: ("Employment Situation (NFP)", 3),
    22: ("GDP", 3),
    46: ("Consumer Price Index (CPI)", 3),
    53: ("Producer Price Index (PPI)", 3),
    21: ("Personal Income & Outlays (PCE)", 3),
    19: ("Industrial Production", 2),
    13: ("Advance Retail Sales", 3),
    83: ("Durable Goods Orders", 2),
    11: ("Employment Cost Index", 2),
    18: ("Housing Starts", 2),
    86: ("ISM Manufacturing", 3),
    101: ("ISM Services", 3),
    17: ("New Residential Construction", 2),
    326: ("FOMC Press Conference", 3),
    180: ("FOMC Minutes", 3),
    350: ("University of Michigan Consumer Sentiment", 2),
}


def upsert_batch(supabase, rows: list[dict], retries: int = 3) -> int:
    """Insert rows in batch with retry logic."""
    for attempt in range(retries):
        try:
            if rows:
                supabase.table("econ_calendar").insert(rows).execute()
            return len(rows)
        except Exception as exc:
            if attempt < retries - 1:
                time.sleep(2 ** attempt)
                # Reconnect
                continue
            print(f"  BATCH INSERT FAILED after {retries} attempts: {exc}")
            # Fall back to one-by-one
            inserted = 0
            for row in rows:
                try:
                    supabase.table("econ_calendar").insert(row).execute()
                    inserted += 1
                except Exception:
                    pass
            return inserted
    return 0


def main() -> None:
    load_project_env()
    fred_key = os.environ["FRED_API_KEY"]
    sb_url = os.environ.get("NEXT_PUBLIC_SUPABASE_URL") or os.environ["SUPABASE_URL"]
    sb_key = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
    supabase = create_client(sb_url, sb_key)

    start_date = date(2024, 1, 1)
    end_date = date.today() + timedelta(days=14)

    # Check what we already have to skip duplicates
    existing_keys: set[str] = set()
    offset = 0
    while True:
        batch = (
            supabase.table("econ_calendar")
            .select("ts,event_name")
            .range(offset, offset + 999)
            .execute()
        )
        if not batch.data:
            break
        for r in batch.data:
            existing_keys.add(f"{r['ts']}|{r['event_name']}")
        if len(batch.data) < 1000:
            break
        offset += 1000

    print(f"Found {len(existing_keys)} existing rows to skip")

    total_rows = 0
    chunk_start = start_date

    while chunk_start < end_date:
        chunk_end = min(chunk_start + timedelta(days=90), end_date)
        print(f"  {chunk_start} → {chunk_end}...", end=" ", flush=True)

        params = {
            "api_key": fred_key,
            "file_type": "json",
            "realtime_start": chunk_start.isoformat(),
            "realtime_end": chunk_end.isoformat(),
            "include_release_dates_with_no_data": "true",
        }

        try:
            resp = requests.get(
                "https://api.stlouisfed.org/fred/releases/dates",
                params=params,
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()
            releases = data.get("release_dates", [])
        except Exception as exc:
            print(f"ERROR: {exc}")
            chunk_start = chunk_end
            continue

        new_rows: list[dict] = []
        for release in releases:
            release_id = release.get("release_id")
            release_name = release.get("release_name", "")
            release_date = release.get("date", "")

            if not release_name or not release_date:
                continue

            mapped = HIGH_IMPORTANCE_RELEASES.get(release_id)
            if mapped:
                event_name, importance = mapped
            else:
                event_name = release_name[:500]
                importance = 1

            ts = f"{release_date}T00:00:00Z"
            key = f"{ts}|{event_name}"

            if key not in existing_keys:
                new_rows.append({
                    "ts": ts,
                    "event_name": event_name,
                    "importance": importance,
                })
                existing_keys.add(key)

        # Batch insert in chunks of 200
        inserted = 0
        for i in range(0, len(new_rows), 200):
            batch = new_rows[i:i + 200]
            inserted += upsert_batch(supabase, batch)
            time.sleep(0.5)

        print(f"{inserted} new / {len(releases)} releases")
        total_rows += inserted
        chunk_start = chunk_end
        time.sleep(1)

    print(f"Done. {total_rows} rows inserted to econ_calendar.")


if __name__ == "__main__":
    main()
