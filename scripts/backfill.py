#!/usr/bin/env python3
"""
Historical MES data backfill from Databento → Supabase.

Pulls canonical OHLCV data for MES continuous front-month:
- 1m from Databento ohlcv-1m
- 1h from Databento ohlcv-1h
- 15m derived from canonical 1m
- 4h and 1d derived from canonical 1h

Usage:
    python scripts/backfill.py --days 30
    python scripts/backfill.py --start 2025-01-01 --end 2025-03-15
"""

import argparse
import math
import os
import sys
from datetime import datetime, timedelta, timezone

import databento as db
from supabase import create_client
from mes_aggregation import aggregate_mes_from_1h, aggregate_mes_timeframes

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
DATABENTO_KEY = os.environ["DATABENTO_API_KEY"]

PRICE_SCALE = 1_000_000_000
DATASET = "GLBX.MDP3"
SYMBOL = "MES.c.0"
BATCH_SIZE = 500


def is_weekend_bar(ts: int) -> bool:
    """Filter weekend bars (Fri 22:00 UTC → Sun 23:00 UTC)."""
    dt = datetime.fromtimestamp(ts, tz=timezone.utc)
    wd = dt.weekday()
    h = dt.hour
    if wd == 5:  # Saturday
        return True
    if wd == 4 and h >= 22:  # Friday after close
        return True
    if wd == 6 and h < 23:  # Sunday before open
        return True
    return False


def backfill(start: datetime, end: datetime):
    print(f"Backfilling MES canonical data: {start.date()} → {end.date()}")

    client = db.Historical(key=DATABENTO_KEY)
    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

    # Databento has daily limits on request size, chunk by day
    current = start
    total_1m = 0
    total_15m = 0
    total_1h = 0
    total_4h = 0
    total_1d = 0

    while current < end:
        chunk_end = min(current + timedelta(days=1), end)
        start_str = current.strftime("%Y-%m-%dT%H:%M:%S+00:00")
        end_str = chunk_end.strftime("%Y-%m-%dT%H:%M:%S+00:00")

        print(f"  Fetching {current.date()}...", end=" ", flush=True)

        try:
            data_1m = client.timeseries.get_range(
                dataset=DATASET,
                symbols=[SYMBOL],
                stype_in="continuous",
                schema="ohlcv-1m",
                start=start_str,
                end=end_str,
            )

            data_1h = client.timeseries.get_range(
                dataset=DATASET,
                symbols=[SYMBOL],
                stype_in="continuous",
                schema="ohlcv-1h",
                start=start_str,
                end=end_str,
            )

            bars_1m = []
            for record in data_1m:
                ts_ns = record.ts_event
                ts_s = ts_ns // 1_000_000_000
                if is_weekend_bar(ts_s):
                    continue

                o = record.open / PRICE_SCALE
                h = record.high / PRICE_SCALE
                l = record.low / PRICE_SCALE
                c = record.close / PRICE_SCALE
                v = record.volume

                if o <= 0 or h <= 0 or l <= 0 or c <= 0:
                    continue
                if h < l:
                    continue

                ts_iso = datetime.fromtimestamp(ts_s, tz=timezone.utc).isoformat()
                bars_1m.append({
                    "ts": ts_iso,
                    "ts_epoch": ts_s,
                    "open": round(o, 2),
                    "high": round(h, 2),
                    "low": round(l, 2),
                    "close": round(c, 2),
                    "volume": int(v),
                })

            bars_1h = []
            for record in data_1h:
                ts_ns = record.ts_event
                ts_s = ts_ns // 1_000_000_000
                if is_weekend_bar(ts_s):
                    continue

                o = record.open / PRICE_SCALE
                h = record.high / PRICE_SCALE
                l = record.low / PRICE_SCALE
                c = record.close / PRICE_SCALE
                v = record.volume

                if o <= 0 or h <= 0 or l <= 0 or c <= 0:
                    continue
                if h < l:
                    continue

                ts_iso = datetime.fromtimestamp(ts_s, tz=timezone.utc).isoformat()
                bars_1h.append({
                    "ts": ts_iso,
                    "ts_epoch": ts_s,
                    "open": round(o, 2),
                    "high": round(h, 2),
                    "low": round(l, 2),
                    "close": round(c, 2),
                    "volume": int(v),
                })

            if not bars_1m and not bars_1h:
                print("no data (weekend/holiday)")
                current = chunk_end
                continue

            # Upsert 1m bars in batches
            for i in range(0, len(bars_1m), BATCH_SIZE):
                batch = bars_1m[i : i + BATCH_SIZE]
                rows = [{k: v for k, v in b.items() if k != "ts_epoch"} for b in batch]
                supabase.table("mes_1m").upsert(rows).execute()

            timeframe_counts: dict[str, int] = {}

            for i in range(0, len(bars_1h), BATCH_SIZE):
                batch = bars_1h[i : i + BATCH_SIZE]
                rows = [{k: v for k, v in b.items() if k != "ts_epoch"} for b in batch]
                supabase.table("mes_1h").upsert(rows, on_conflict="ts").execute()

            aggregated_from_1m = aggregate_mes_timeframes(bars_1m)
            aggregated_from_1h = aggregate_mes_from_1h(bars_1h)
            aggregated = {**aggregated_from_1m, **aggregated_from_1h}

            for table_name, timeframe_bars in aggregated.items():
                timeframe_counts[table_name] = len(timeframe_bars)
                for i in range(0, len(timeframe_bars), BATCH_SIZE):
                    batch = timeframe_bars[i : i + BATCH_SIZE]
                    rows = [
                        {
                            "ts": datetime.fromtimestamp(
                                b["ts_epoch"], tz=timezone.utc
                            ).isoformat(),
                            "open": b["open"],
                            "high": b["high"],
                            "low": b["low"],
                            "close": b["close"],
                            "volume": b["volume"],
                        }
                        for b in batch
                    ]
                    supabase.table(table_name).upsert(rows, on_conflict="ts").execute()

            total_1m += len(bars_1m)
            total_15m += timeframe_counts.get("mes_15m", 0)
            total_1h += len(bars_1h)
            total_4h += timeframe_counts.get("mes_4h", 0)
            total_1d += timeframe_counts.get("mes_1d", 0)
            print(
                f"{len(bars_1m)} 1m | "
                f"{timeframe_counts.get('mes_15m', 0)} 15m | "
                f"{len(bars_1h)} 1h | "
                f"{timeframe_counts.get('mes_4h', 0)} 4h | "
                f"{timeframe_counts.get('mes_1d', 0)} 1d"
            )

        except Exception as e:
            print(f"ERROR: {e}")

        current = chunk_end

    print(
        "\nDone. Total: "
        f"{total_1m} 1m bars, "
        f"{total_15m} 15m bars, "
        f"{total_1h} 1h bars, "
        f"{total_4h} 4h bars, "
        f"{total_1d} 1d bars"
    )


def main():
    parser = argparse.ArgumentParser(description="Backfill MES historical data")
    parser.add_argument("--days", type=int, default=30, help="Days to backfill (default: 30)")
    parser.add_argument("--start", type=str, help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end", type=str, help="End date (YYYY-MM-DD)")
    args = parser.parse_args()

    if args.start and args.end:
        start = datetime.strptime(args.start, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        end = datetime.strptime(args.end, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    else:
        end = datetime.now(timezone.utc)
        start = end - timedelta(days=args.days)

    backfill(start, end)


if __name__ == "__main__":
    main()
