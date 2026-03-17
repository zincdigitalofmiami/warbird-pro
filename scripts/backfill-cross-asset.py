#!/usr/bin/env python3
"""
Backfill cross-asset 1H bars for all active non-MES Databento correlation symbols.
Writes to cross_asset_1h(ts, symbol_code, open, high, low, close, volume).
"""
from __future__ import annotations

import os
import sys
from datetime import date, timedelta

import databento as db
from supabase import create_client

CORRELATION_SYMBOLS = [
    "NQ.c.0", "ZN.c.0", "ZF.c.0", "ZB.c.0", "SR3.c.0",
    "6E.c.0", "6J.c.0", "ES.c.0", "YM.c.0", "RTY.c.0",
    "CL.c.0", "GC.c.0",
]

# VX and DX are FRED-sourced, not Databento — skip here
# SOX is Databento but may require separate dataset — include, will error-skip if unavailable

SYMBOL_TO_CODE = {
    "NQ.c.0": "NQ", "ZN.c.0": "ZN", "ZF.c.0": "ZF", "ZB.c.0": "ZB",
    "SR3.c.0": "SR3", "6E.c.0": "6E", "6J.c.0": "6J", "ES.c.0": "ES",
    "YM.c.0": "YM", "RTY.c.0": "RTY", "CL.c.0": "CL", "GC.c.0": "GC",
}

def main() -> None:
    api_key = os.environ["DATABENTO_API_KEY"]
    sb_url = os.environ.get("NEXT_PUBLIC_SUPABASE_URL") or os.environ["SUPABASE_URL"]
    sb_key = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
    supabase = create_client(sb_url, sb_key)

    start = "2024-01-01"
    end = "2026-03-17"  # exclusive upper bound for Databento

    client = db.Historical(api_key)

    for db_symbol in CORRELATION_SYMBOLS:
        symbol_code = SYMBOL_TO_CODE[db_symbol]
        print(f"Fetching {symbol_code} ({db_symbol})...")
        try:
            data = client.timeseries.get_range(
                dataset="GLBX.MDP3",
                schema="ohlcv-1h",
                symbols=[db_symbol],
                start=start,
                end=end,
            ).to_df()
        except Exception as exc:
            print(f"  SKIP {symbol_code}: {exc}")
            continue

        if data.empty:
            print(f"  SKIP {symbol_code}: no data returned")
            continue

        rows = []
        for _, bar in data.iterrows():
            rows.append({
                "ts": bar.name.isoformat() if hasattr(bar.name, "isoformat") else str(bar["ts_event"]),
                "symbol_code": symbol_code,
                "open": float(bar["open"]) / 1e9 if bar["open"] > 1e6 else float(bar["open"]),
                "high": float(bar["high"]) / 1e9 if bar["high"] > 1e6 else float(bar["high"]),
                "low": float(bar["low"]) / 1e9 if bar["low"] > 1e6 else float(bar["low"]),
                "close": float(bar["close"]) / 1e9 if bar["close"] > 1e6 else float(bar["close"]),
                "volume": int(bar["volume"]),
            })

        # Upsert in chunks of 500
        chunk_size = 500
        for i in range(0, len(rows), chunk_size):
            chunk = rows[i:i + chunk_size]
            res = supabase.table("cross_asset_1h").upsert(chunk, on_conflict="ts,symbol_code").execute()
            if hasattr(res, "error") and res.error:
                print(f"  ERROR upserting {symbol_code}: {res.error}")
                break

        print(f"  {symbol_code}: {len(rows)} bars upserted")

if __name__ == "__main__":
    main()
