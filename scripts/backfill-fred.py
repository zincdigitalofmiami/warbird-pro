#!/usr/bin/env python3
"""
Backfill all active FRED series from series_catalog into their econ domain tables.
"""
from __future__ import annotations

import os
import time
from datetime import date
import requests
from supabase import create_client

from project_env import load_project_env

CATEGORY_TABLE = {
    "rates":       "econ_rates_1d",
    "yields":      "econ_yields_1d",
    "fx":          "econ_fx_1d",
    "vol":         "econ_vol_1d",
    "inflation":   "econ_inflation_1d",
    "labor":       "econ_labor_1d",
    "activity":    "econ_activity_1d",
    "money":       "econ_money_1d",
    "commodities": "econ_commodities_1d",
    "indexes":     "econ_indexes_1d",
}

def fetch_fred_series(series_id: str, api_key: str, start: str = "2020-01-01") -> list[dict]:
    url = "https://api.stlouisfed.org/fred/series/observations"
    params = {
        "series_id": series_id,
        "api_key": api_key,
        "file_type": "json",
        "observation_start": start,
        "observation_end": date.today().isoformat(),
    }
    resp = requests.get(url, params=params, timeout=30)
    resp.raise_for_status()
    observations = resp.json().get("observations", [])
    rows = []
    for obs in observations:
        if obs["value"] == ".":
            continue
        rows.append({
            "ts": obs["date"] + "T00:00:00Z",
            "series_id": series_id,
            "value": float(obs["value"]),
        })
    return rows

def main() -> None:
    load_project_env()
    fred_key = os.environ["FRED_API_KEY"]
    sb_url = os.environ["SUPABASE_URL"]
    sb_key = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
    print(f"Target Supabase: {sb_url}")
    supabase = create_client(sb_url, sb_key)

    # Pull active series from series_catalog
    res = supabase.table("series_catalog").select("series_id, category").eq("is_active", True).execute()
    catalog: list[dict[str, str]] = res.data or []
    print(f"Found {len(catalog)} active series")

    for entry in catalog:
        series_id = entry["series_id"]
        category = entry["category"]
        table = CATEGORY_TABLE.get(category)
        if not table:
            print(f"  SKIP {series_id}: unknown category '{category}'")
            continue

        print(f"Fetching {series_id} → {table}...")
        try:
            rows = fetch_fred_series(series_id, fred_key)
        except Exception as exc:
            print(f"  ERROR {series_id}: {exc}")
            time.sleep(1)
            continue

        if not rows:
            print(f"  SKIP {series_id}: no observations")
            continue

        # Upsert in chunks of 500
        for i in range(0, len(rows), 500):
            chunk = rows[i:i + 500]
            supabase.table(table).upsert(chunk, on_conflict="ts,series_id").execute()

        print(f"  {series_id}: {len(rows)} rows → {table}")
        time.sleep(0.5)  # FRED rate limit: 120 req/min

if __name__ == "__main__":
    main()
