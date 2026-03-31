#!/usr/bin/env python3
"""
Backfill intermarket 15m OHLCV for AG training basket.

Pulls ohlcv-1m from Databento GLBX.MDP3, aggregates to 15m, upserts to cross_asset_15m.
Also backfills cross_asset_1h and cross_asset_1d for the same symbols/range.

AG training basket: NQ, RTY, CL, HG, 6E, 6J — all CME Globex continuous front-month.

Usage:
    python scripts/backfill-intermarket-15m.py
    python scripts/backfill-intermarket-15m.py --start 2020-01-01 --end 2022-01-01
    python scripts/backfill-intermarket-15m.py --symbol NQ
    python scripts/backfill-intermarket-15m.py --cost-only
"""

from __future__ import annotations

import argparse
import os
from datetime import date, datetime, timedelta, timezone

import databento as db
from supabase import create_client

# AG training basket — 6 CME Globex intermarket symbols
INTERMARKET_SYMBOLS = {
    "NQ": "NQ.c.0",
    "RTY": "RTY.c.0",
    "CL": "CL.c.0",
    "HG": "HG.c.0",
    "6E": "6E.c.0",
    "6J": "6J.c.0",
}

DATASET = "GLBX.MDP3"
PRICE_SCALE = 1_000_000_000
BATCH_SIZE = 500

# Default range: 2018-01-01 to today
DEFAULT_START = date(2018, 1, 1)


def is_weekend_bar(ts_epoch: int) -> bool:
    """Filter weekend bars (Fri 22:00 UTC -> Sun 23:00 UTC)."""
    dt = datetime.fromtimestamp(ts_epoch, tz=timezone.utc)
    wd = dt.weekday()
    h = dt.hour
    if wd == 5:  # Saturday
        return True
    if wd == 4 and h >= 22:  # Friday after close
        return True
    if wd == 6 and h < 23:  # Sunday before open
        return True
    return False


def floor_15m(ts_epoch: int) -> int:
    """Floor timestamp to 15-minute boundary (900 seconds)."""
    return (ts_epoch // 900) * 900


def aggregate_1m_to_15m(bars_1m: list[dict]) -> list[dict]:
    """Aggregate 1m bars into 15m bars. Same logic as mes_aggregation.py."""
    buckets: dict[int, dict] = {}

    for bar in bars_1m:
        ts_epoch = bar["ts_epoch"]
        bucket_ts = floor_15m(ts_epoch)
        existing = buckets.get(bucket_ts)

        if existing is None:
            buckets[bucket_ts] = {
                "ts_epoch": bucket_ts,
                "open": bar["open"],
                "high": bar["high"],
                "low": bar["low"],
                "close": bar["close"],
                "volume": bar["volume"],
            }
        else:
            existing["high"] = max(existing["high"], bar["high"])
            existing["low"] = min(existing["low"], bar["low"])
            existing["close"] = bar["close"]
            existing["volume"] += bar["volume"]

    return sorted(buckets.values(), key=lambda r: r["ts_epoch"])


def aggregate_1h_from_1m(bars_1m: list[dict]) -> list[dict]:
    """Aggregate 1m bars into 1h bars."""
    buckets: dict[int, dict] = {}

    for bar in bars_1m:
        ts_epoch = bar["ts_epoch"]
        bucket_ts = (ts_epoch // 3600) * 3600
        existing = buckets.get(bucket_ts)

        if existing is None:
            buckets[bucket_ts] = {
                "ts_epoch": bucket_ts,
                "open": bar["open"],
                "high": bar["high"],
                "low": bar["low"],
                "close": bar["close"],
                "volume": bar["volume"],
            }
        else:
            existing["high"] = max(existing["high"], bar["high"])
            existing["low"] = min(existing["low"], bar["low"])
            existing["close"] = bar["close"]
            existing["volume"] += bar["volume"]

    return sorted(buckets.values(), key=lambda r: r["ts_epoch"])


def aggregate_1d_from_1h(bars_1h: list[dict]) -> list[dict]:
    """Aggregate 1h bars into 1d bars by UTC calendar day."""
    buckets: dict[str, dict] = {}

    for bar in bars_1h:
        dt = datetime.fromtimestamp(bar["ts_epoch"], tz=timezone.utc)
        day_key = dt.strftime("%Y-%m-%d")
        day_ts = int(
            datetime(dt.year, dt.month, dt.day, tzinfo=timezone.utc).timestamp()
        )
        existing = buckets.get(day_key)

        if existing is None:
            buckets[day_key] = {
                "ts_epoch": day_ts,
                "open": bar["open"],
                "high": bar["high"],
                "low": bar["low"],
                "close": bar["close"],
                "volume": bar["volume"],
            }
        else:
            existing["high"] = max(existing["high"], bar["high"])
            existing["low"] = min(existing["low"], bar["low"])
            existing["close"] = bar["close"]
            existing["volume"] += bar["volume"]

    return sorted(buckets.values(), key=lambda r: r["ts_epoch"])


def scale_price(raw: float) -> float:
    """Databento fixed-point to decimal. Handles both scaled and unscaled values."""
    if raw > 1e6:
        return round(raw / PRICE_SCALE, 6)
    return round(raw, 6)


def estimate_cost(client: db.Historical, symbols: dict[str, str], start: date, end: date) -> None:
    """Estimate Databento cost for the pull. OHLCV should be $0 on Standard plan."""
    print("\n=== COST ESTIMATION ===")
    db_symbols = list(symbols.values())

    for schema in ["ohlcv-1m"]:
        try:
            cost = client.metadata.get_cost(
                dataset=DATASET,
                symbols=db_symbols,
                stype_in="continuous",
                schema=schema,
                start=start.isoformat(),
                end=end.isoformat(),
            )
            print(f"  {schema}: ${cost:.2f}")
        except Exception as e:
            print(f"  {schema}: ERROR estimating cost — {e}")

    print("  (OHLCV schemas are FREE on Standard plan — $0.00 expected)")
    print("======================\n")


def backfill_symbol(
    client: db.Historical,
    supabase,
    symbol_code: str,
    db_symbol: str,
    start: date,
    end: date,
) -> dict[str, int]:
    """Backfill one symbol: pull 1m, aggregate to 15m/1h/1d, upsert all."""
    totals = {"1m_pulled": 0, "15m": 0, "1h": 0, "1d": 0}

    # Chunk by 7 days — 1m data is much larger than 1h, smaller chunks are safer
    chunk_start = start
    while chunk_start < end:
        chunk_end = min(chunk_start + timedelta(days=7), end)
        print(f"  {chunk_start} -> {chunk_end}...", end=" ", flush=True)

        try:
            data = client.timeseries.get_range(
                dataset=DATASET,
                symbols=[db_symbol],
                stype_in="continuous",
                schema="ohlcv-1m",
                start=chunk_start.isoformat(),
                end=chunk_end.isoformat(),
            )

            bars_1m = []
            for record in data:
                ts_ns = record.ts_event
                ts_s = ts_ns // 1_000_000_000
                if is_weekend_bar(ts_s):
                    continue

                o = scale_price(record.open)
                h = scale_price(record.high)
                l = scale_price(record.low)
                c = scale_price(record.close)
                v = int(record.volume)

                if o <= 0 or h <= 0 or l <= 0 or c <= 0:
                    continue
                if h < l:
                    continue

                bars_1m.append({
                    "ts_epoch": ts_s,
                    "open": o,
                    "high": h,
                    "low": l,
                    "close": c,
                    "volume": v,
                })

        except Exception as exc:
            print(f"ERROR: {exc}")
            chunk_start = chunk_end
            continue

        if not bars_1m:
            print("no data")
            chunk_start = chunk_end
            continue

        totals["1m_pulled"] += len(bars_1m)

        # Aggregate 1m -> 15m
        bars_15m = aggregate_1m_to_15m(bars_1m)
        # Aggregate 1m -> 1h
        bars_1h = aggregate_1h_from_1m(bars_1m)
        # Aggregate 1h -> 1d
        bars_1d = aggregate_1d_from_1h(bars_1h)

        # Upsert 15m
        for i in range(0, len(bars_15m), BATCH_SIZE):
            batch = bars_15m[i : i + BATCH_SIZE]
            rows = [
                {
                    "ts": datetime.fromtimestamp(b["ts_epoch"], tz=timezone.utc).isoformat(),
                    "symbol_code": symbol_code,
                    "open": b["open"],
                    "high": b["high"],
                    "low": b["low"],
                    "close": b["close"],
                    "volume": b["volume"],
                }
                for b in batch
            ]
            supabase.table("cross_asset_15m").upsert(
                rows, on_conflict="ts,symbol_code"
            ).execute()
        totals["15m"] += len(bars_15m)

        # Upsert 1h
        for i in range(0, len(bars_1h), BATCH_SIZE):
            batch = bars_1h[i : i + BATCH_SIZE]
            rows = [
                {
                    "ts": datetime.fromtimestamp(b["ts_epoch"], tz=timezone.utc).isoformat(),
                    "symbol_code": symbol_code,
                    "open": b["open"],
                    "high": b["high"],
                    "low": b["low"],
                    "close": b["close"],
                    "volume": b["volume"],
                }
                for b in batch
            ]
            supabase.table("cross_asset_1h").upsert(
                rows, on_conflict="ts,symbol_code"
            ).execute()
        totals["1h"] += len(bars_1h)

        # Upsert 1d
        for i in range(0, len(bars_1d), BATCH_SIZE):
            batch = bars_1d[i : i + BATCH_SIZE]
            rows = [
                {
                    "ts": datetime.fromtimestamp(b["ts_epoch"], tz=timezone.utc).isoformat(),
                    "symbol_code": symbol_code,
                    "open": b["open"],
                    "high": b["high"],
                    "low": b["low"],
                    "close": b["close"],
                    "volume": b["volume"],
                }
                for b in batch
            ]
            supabase.table("cross_asset_1d").upsert(
                rows, on_conflict="ts,symbol_code"
            ).execute()
        totals["1d"] += len(bars_1d)

        print(f"{len(bars_1m)} 1m -> {len(bars_15m)} 15m | {len(bars_1h)} 1h | {len(bars_1d)} 1d")
        chunk_start = chunk_end

    return totals


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Backfill intermarket 15m OHLCV for AG training"
    )
    parser.add_argument(
        "--start", type=str, default=DEFAULT_START.isoformat(),
        help="Start date YYYY-MM-DD (default: 2018-01-01)"
    )
    parser.add_argument(
        "--end", type=str, default=None,
        help="End date YYYY-MM-DD (default: today)"
    )
    parser.add_argument(
        "--symbol", type=str, default=None,
        help="Single symbol code to backfill (e.g., NQ, HG). Default: all 6"
    )
    parser.add_argument(
        "--cost-only", action="store_true",
        help="Only estimate cost, don't pull data"
    )
    args = parser.parse_args()

    api_key = os.environ["DATABENTO_API_KEY"]
    sb_url = os.environ.get("NEXT_PUBLIC_SUPABASE_URL") or os.environ["SUPABASE_URL"]
    sb_key = os.environ["SUPABASE_SERVICE_ROLE_KEY"]

    start = date.fromisoformat(args.start)
    end = date.fromisoformat(args.end) if args.end else date.today()

    symbols = INTERMARKET_SYMBOLS
    if args.symbol:
        code = args.symbol.upper()
        if code not in INTERMARKET_SYMBOLS:
            print(f"ERROR: {code} not in intermarket basket: {list(INTERMARKET_SYMBOLS.keys())}")
            return
        symbols = {code: INTERMARKET_SYMBOLS[code]}

    client = db.Historical(key=api_key)

    # Always estimate cost first
    estimate_cost(client, symbols, start, end)

    if args.cost_only:
        return

    supabase = create_client(sb_url, sb_key)

    print(f"Backfilling {list(symbols.keys())} from {start} to {end}")
    print(f"Tables: cross_asset_15m, cross_asset_1h, cross_asset_1d\n")

    grand_totals = {"1m_pulled": 0, "15m": 0, "1h": 0, "1d": 0}

    for symbol_code, db_symbol in symbols.items():
        print(f"\n{'='*60}")
        print(f"  {symbol_code} ({db_symbol})")
        print(f"{'='*60}")

        totals = backfill_symbol(client, supabase, symbol_code, db_symbol, start, end)

        for k, v in totals.items():
            grand_totals[k] += v

        print(f"  {symbol_code} done: {totals['1m_pulled']} 1m pulled -> "
              f"{totals['15m']} 15m | {totals['1h']} 1h | {totals['1d']} 1d")

    print(f"\n{'='*60}")
    print(f"  GRAND TOTAL")
    print(f"{'='*60}")
    print(f"  1m pulled: {grand_totals['1m_pulled']:,}")
    print(f"  15m upserted: {grand_totals['15m']:,}")
    print(f"  1h upserted: {grand_totals['1h']:,}")
    print(f"  1d upserted: {grand_totals['1d']:,}")


if __name__ == "__main__":
    main()
