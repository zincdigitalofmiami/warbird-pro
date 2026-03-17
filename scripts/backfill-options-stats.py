#!/usr/bin/env python3
"""
Backfill options_stats_1d from Databento statistics schema (free on Standard plan).
Pulls settlement price, open interest, and cleared volume for MES futures.

stat_type values from CME:
  1 = OPENING_PRICE, 2 = INDICATIVE_OPENING_PRICE, 3 = SETTLEMENT_PRICE,
  4 = SESSION_LOW, 5 = SESSION_HIGH, 6 = CLEARED_VOLUME,
  7 = LOWEST_OFFER, 8 = HIGHEST_BID, 9 = OPEN_INTEREST
"""
from __future__ import annotations

import os
from datetime import date, timedelta

import databento as db
from supabase import create_client

STAT_OI = 9
STAT_SETTLEMENT = 3
STAT_CLEARED_VOL = 6

def main() -> None:
    api_key = os.environ["DATABENTO_API_KEY"]
    sb_url = os.environ.get("NEXT_PUBLIC_SUPABASE_URL") or os.environ["SUPABASE_URL"]
    sb_key = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
    supabase = create_client(sb_url, sb_key)
    client = db.Historical(api_key)

    start_date = date(2024, 1, 1)
    end_date = date(2026, 3, 17)
    symbol = "MES.c.0"
    symbol_code = "MES"

    # Check cost first
    cost = client.metadata.get_cost(
        dataset="GLBX.MDP3",
        symbols=[symbol],
        stype_in="continuous",
        schema="statistics",
        start=start_date.isoformat(),
        end=end_date.isoformat(),
    )
    print(f"Cost for MES statistics ({start_date} → {end_date}): ${cost:.4f}")

    # Chunk by quarter
    chunk_start = start_date
    total_rows = 0

    while chunk_start < end_date:
        chunk_end = min(chunk_start + timedelta(days=90), end_date)
        print(f"  {chunk_start} → {chunk_end}...", end=" ", flush=True)

        try:
            data = client.timeseries.get_range(
                dataset="GLBX.MDP3",
                symbols=[symbol],
                stype_in="continuous",
                schema="statistics",
                start=chunk_start.isoformat(),
                end=chunk_end.isoformat(),
            ).to_df()
        except Exception as exc:
            print(f"ERROR: {exc}")
            chunk_start = chunk_end
            continue

        if data.empty:
            print("no data")
            chunk_start = chunk_end
            continue

        # Filter to stat types we care about
        oi = data[data["stat_type"] == STAT_OI]
        settle = data[data["stat_type"] == STAT_SETTLEMENT]
        vol = data[data["stat_type"] == STAT_CLEARED_VOL]

        # Group by date, take last value for each stat type per day
        daily = {}
        for _, row in oi.iterrows():
            ts = row["ts_event"]
            day_key = ts.strftime("%Y-%m-%dT00:00:00Z") if hasattr(ts, "strftime") else str(ts)[:10] + "T00:00:00Z"
            if day_key not in daily:
                daily[day_key] = {"ts": day_key, "symbol_code": symbol_code}
            daily[day_key]["open_interest"] = int(row["quantity"]) if row["quantity"] < 2147483647 else None

        for _, row in settle.iterrows():
            ts = row["ts_event"]
            day_key = ts.strftime("%Y-%m-%dT00:00:00Z") if hasattr(ts, "strftime") else str(ts)[:10] + "T00:00:00Z"
            if day_key not in daily:
                daily[day_key] = {"ts": day_key, "symbol_code": symbol_code}
            # Settlement price is in the 'price' field (already scaled for OHLCV-based schemas)
            daily[day_key]["implied_vol"] = None  # CME doesn't publish IV for futures

        for _, row in vol.iterrows():
            ts = row["ts_event"]
            day_key = ts.strftime("%Y-%m-%dT00:00:00Z") if hasattr(ts, "strftime") else str(ts)[:10] + "T00:00:00Z"
            if day_key not in daily:
                daily[day_key] = {"ts": day_key, "symbol_code": symbol_code}
            daily[day_key]["volume"] = int(row["quantity"]) if row["quantity"] < 2147483647 else None

        rows = list(daily.values())
        if rows:
            for i in range(0, len(rows), 500):
                supabase.table("options_stats_1d").upsert(
                    rows[i:i + 500], on_conflict="ts,symbol_code"
                ).execute()

        print(f"{len(rows)} days")
        total_rows += len(rows)
        chunk_start = chunk_end

    print(f"Done. {total_rows} daily rows upserted to options_stats_1d.")

if __name__ == "__main__":
    main()
