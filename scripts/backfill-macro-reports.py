#!/usr/bin/env python3
"""
Backfill macro_reports_1d from FRED observation data.
Maps key FRED series to report_category enum values.
Computes actual and previous values. Surprise requires consensus data (left null).
"""
from __future__ import annotations

import os
import time
from datetime import date

import requests
from supabase import create_client

# Map FRED series to report_category enum
# Enum values: fomc, cpi, nfp, claims, ppi, retail_sales, gdp, ism, housing, consumer_confidence
SERIES_MAP = {
    "FEDFUNDS":   "fomc",           # Federal Funds Rate (monthly)
    "CPIAUCSL":   "cpi",            # CPI All Urban Consumers (monthly)
    "PAYEMS":     "nfp",            # Total Nonfarm Payrolls (monthly)
    "ICSA":       "claims",         # Initial Jobless Claims (weekly)
    "RSXFS":      "retail_sales",   # Advance Retail Sales (monthly)
    "INDPRO":     "gdp",            # Industrial Production as GDP proxy (monthly)
}


def fetch_fred_observations(series_id: str, api_key: str, start: str, end: str) -> list[dict]:
    """Fetch FRED observations for a series."""
    params = {
        "series_id": series_id,
        "api_key": api_key,
        "file_type": "json",
        "observation_start": start,
        "observation_end": end,
        "sort_order": "asc",
    }
    resp = requests.get(
        "https://api.stlouisfed.org/fred/series/observations",
        params=params,
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    return data.get("observations", [])


def main() -> None:
    fred_key = os.environ["FRED_API_KEY"]
    sb_url = os.environ.get("NEXT_PUBLIC_SUPABASE_URL") or os.environ["SUPABASE_URL"]
    sb_key = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
    supabase = create_client(sb_url, sb_key)

    start_date = "2024-01-01"
    end_date = date.today().isoformat()
    total_rows = 0

    for series_id, report_type in SERIES_MAP.items():
        print(f"Fetching {series_id} ({report_type})...", end=" ", flush=True)

        try:
            observations = fetch_fred_observations(series_id, fred_key, start_date, end_date)
        except Exception as exc:
            print(f"ERROR: {exc}")
            continue

        rows = []
        prev_value = None
        for obs in observations:
            value_str = obs.get("value", ".")
            if value_str == ".":
                continue
            actual = float(value_str)
            obs_date = obs["date"]

            rows.append({
                "ts": f"{obs_date}T00:00:00Z",
                "report_type": report_type,
                "actual": actual,
                "previous": prev_value,
                "forecast": None,
                "surprise": None,
            })
            prev_value = actual

        # Upsert (dedup by ts + report_type)
        inserted = 0
        for row in rows:
            existing = (
                supabase.table("macro_reports_1d")
                .select("id")
                .eq("ts", row["ts"])
                .eq("report_type", row["report_type"])
                .limit(1)
                .execute()
            )
            if not existing.data:
                supabase.table("macro_reports_1d").insert(row).execute()
                inserted += 1

        print(f"{inserted} new / {len(rows)} observations")
        total_rows += inserted
        time.sleep(1)  # FRED rate limit

    print(f"Done. {total_rows} rows inserted to macro_reports_1d.")


if __name__ == "__main__":
    main()
