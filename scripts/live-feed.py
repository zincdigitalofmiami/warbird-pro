#!/usr/bin/env python3
"""
Live MES feed sidecar — streams real-time 1m bars from Databento → Supabase.
Runs as a background process. Receives OHLCV-1m, upserts to mes_1m + mes_15m.

Usage: python scripts/live-feed.py
"""
import math, os, signal, sys, time
from datetime import datetime, timezone
import databento as db
from supabase import create_client
from mes_aggregation import floor_interval, mes_session_day_start

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
DATABENTO_KEY = os.environ["DATABENTO_API_KEY"]
DATASET = "GLBX.MDP3"
SYMBOL = "MES.c.0"
SCHEMA = "ohlcv-1m"
PRICE_SCALE = 1_000_000_000
running = True

def stop(sig, frame):
    global running
    print("\nShutting down...")
    running = False

signal.signal(signal.SIGINT, stop)
signal.signal(signal.SIGTERM, stop)

def is_weekend(ts):
    dt = datetime.fromtimestamp(ts, tz=timezone.utc)
    wd = dt.weekday()
    if wd == 5: return True
    if wd == 4 and dt.hour >= 22: return True
    if wd == 6 and dt.hour < 23: return True
    return False

def main():
    print(f"Live MES feed → Supabase")
    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
    bucket_configs = {
        "mes_15m": {"bucket_fn": lambda ts: floor_interval(ts, 900), "retention": 900},
        "mes_1h": {"bucket_fn": lambda ts: floor_interval(ts, 3600), "retention": 3600},
        "mes_4h": {"bucket_fn": lambda ts: floor_interval(ts, 14_400), "retention": 14_400},
        "mes_1d": {"bucket_fn": mes_session_day_start, "retention": 86_400},
    }
    buckets = {table: {} for table in bucket_configs}
    count = 0
    last_flush = time.time()

    client = db.Live(key=DATABENTO_KEY)
    client.subscribe(dataset=DATASET, schema=SCHEMA, stype_in="continuous", symbols=[SYMBOL])
    print("Connected. Streaming...")

    for record in client:
        if not running: break
        if not hasattr(record, "open"): continue
        ts_s = record.ts_event // 1_000_000_000
        if is_weekend(ts_s): continue
        o = record.open / PRICE_SCALE
        h = record.high / PRICE_SCALE
        l = record.low / PRICE_SCALE
        c = record.close / PRICE_SCALE
        v = record.volume
        if o <= 0 or c <= 0: continue
        ts_iso = datetime.fromtimestamp(ts_s, tz=timezone.utc).isoformat()

        try:
            supabase.table("mes_1m").upsert({"ts": ts_iso, "open": round(o,2), "high": round(h,2), "low": round(l,2), "close": round(c,2), "volume": int(v)}, on_conflict="ts").execute()
        except Exception as e:
            print(f"  1m ERR: {e}")
            continue
        count += 1

        for table, config in bucket_configs.items():
            bucket_ts = config["bucket_fn"](ts_s)
            table_buckets = buckets[table]
            if bucket_ts not in table_buckets:
                table_buckets[bucket_ts] = {
                    "ts": datetime.fromtimestamp(bucket_ts, tz=timezone.utc).isoformat(),
                    "open": round(o, 2),
                    "high": round(h, 2),
                    "low": round(l, 2),
                    "close": round(c, 2),
                    "volume": int(v),
                }
            else:
                bucket = table_buckets[bucket_ts]
                bucket["high"] = max(bucket["high"], round(h, 2))
                bucket["low"] = min(bucket["low"], round(l, 2))
                bucket["close"] = round(c, 2)
                bucket["volume"] += int(v)

        now = time.time()
        if now - last_flush >= 60 or len(buckets["mes_15m"]) > 2:
            for table, config in bucket_configs.items():
                current_bucket = config["bucket_fn"](ts_s)
                retention = config["retention"]
                for bucket_ts, bucket_data in list(buckets[table].items()):
                    try:
                        supabase.table(table).upsert(bucket_data, on_conflict="ts").execute()
                    except Exception as e:
                        print(f"  {table} ERR: {e}")
                    if bucket_ts < current_bucket - retention:
                        del buckets[table][bucket_ts]
            last_flush = now

        if count % 15 == 0:
            dt = datetime.fromtimestamp(ts_s, tz=timezone.utc)
            print(f"  [{dt.strftime('%H:%M:%S')}] {count} bars | {c:.2f}")

    for table, table_buckets in buckets.items():
        for bucket_data in table_buckets.values():
            try:
                supabase.table(table).upsert(bucket_data, on_conflict="ts").execute()
            except Exception:
                pass
    print(f"Done. {count} bars.")

if __name__ == "__main__":
    main()
