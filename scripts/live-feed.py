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
    buckets = {}
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

        bts = (ts_s // 900) * 900
        if bts not in buckets:
            buckets[bts] = {"ts": datetime.fromtimestamp(bts, tz=timezone.utc).isoformat(), "open": round(o,2), "high": round(h,2), "low": round(l,2), "close": round(c,2), "volume": int(v)}
        else:
            b = buckets[bts]
            b["high"] = max(b["high"], round(h,2))
            b["low"] = min(b["low"], round(l,2))
            b["close"] = round(c,2)
            b["volume"] += int(v)

        now = time.time()
        if now - last_flush >= 60 or len(buckets) > 2:
            cur = (ts_s // 900) * 900
            for k, bd in list(buckets.items()):
                try:
                    supabase.table("mes_15m").upsert(bd, on_conflict="ts").execute()
                except Exception as e:
                    print(f"  15m ERR: {e}")
                if k < cur - 900: del buckets[k]
            last_flush = now

        if count % 15 == 0:
            dt = datetime.fromtimestamp(ts_s, tz=timezone.utc)
            print(f"  [{dt.strftime('%H:%M:%S')}] {count} bars | {c:.2f}")

    for bd in buckets.values():
        try: supabase.table("mes_15m").upsert(bd, on_conflict="ts").execute()
        except: pass
    print(f"Done. {count} bars.")

if __name__ == "__main__":
    main()
