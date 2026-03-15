#!/usr/bin/env python3
"""
Databento Live Feed → Supabase

Primary data path for MES 1m and 15m candle data.
Subscribes to Databento Live API for MES continuous contract,
receives 1m OHLCV bars, and upserts to Supabase mes_1m + mes_15m.

RAM: ~50-80MB (Python 30MB + databento 20MB + supabase-py 10MB)
CPU: Zero — pure I/O (receive bytes, parse, HTTP write)

Usage:
  pip install -r requirements.txt
  export DATABENTO_API_KEY=...
  export SUPABASE_URL=...
  export SUPABASE_SERVICE_ROLE_KEY=...
  python live-feed.py

Run as tmux session or systemd service on M4 Pro.
"""

import os
import sys
import time
import signal
import logging
from datetime import datetime, timezone, timedelta

import databento as db
from supabase import create_client

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

DATASET = "GLBX.MDP3"
SYMBOL = "MES.c.0"
STYPE = "continuous"
SCHEMA = "ohlcv-1m"
PRICE_SCALE = 1_000_000_000

# CME Globex hours (UTC)
# Opens: Sunday 23:00 UTC
# Closes: Friday 22:00 UTC
# Daily maintenance: 22:00-23:00 UTC Mon-Thu

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("live-feed")

# Graceful shutdown
shutdown = False

def handle_signal(signum, frame):
    global shutdown
    log.info("Shutdown signal received")
    shutdown = True

signal.signal(signal.SIGINT, handle_signal)
signal.signal(signal.SIGTERM, handle_signal)

# ---------------------------------------------------------------------------
# Market hours
# ---------------------------------------------------------------------------

def is_market_open() -> bool:
    now = datetime.now(timezone.utc)
    day = now.weekday()  # 0=Mon, 6=Sun
    hour = now.hour

    # Saturday (5) all day — closed
    if day == 5:
        return False
    # Sunday (6) before 23:00 UTC — closed
    if day == 6 and hour < 23:
        return False
    # Friday (4) after 22:00 UTC — closed
    if day == 4 and hour >= 22:
        return False
    # Daily maintenance 22:00-23:00 UTC Mon-Thu (0-3)
    if 0 <= day <= 3 and hour == 22:
        return False

    return True


def seconds_until_market_open() -> int:
    now = datetime.now(timezone.utc)
    day = now.weekday()
    hour = now.hour

    target = now.replace(minute=0, second=0, microsecond=0)

    # Daily maintenance break (Mon-Thu 22:00 UTC) — opens at 23:00
    if 0 <= day <= 3 and hour == 22:
        target = target.replace(hour=23)
        return max(1, int((target - now).total_seconds()))

    # Friday after close → Sunday 23:00 UTC
    if day == 4 and hour >= 22:
        days_ahead = 2  # Sat + Sun
        target += timedelta(days=days_ahead)
        target = target.replace(hour=23)
        return max(1, int((target - now).total_seconds()))

    # Saturday → Sunday 23:00 UTC
    if day == 5:
        target += timedelta(days=1)
        target = target.replace(hour=23)
        return max(1, int((target - now).total_seconds()))

    # Sunday before open → 23:00 UTC today
    if day == 6 and hour < 23:
        target = target.replace(hour=23)
        return max(1, int((target - now).total_seconds()))

    # Market is open
    return 0


# ---------------------------------------------------------------------------
# 15m aggregation
# ---------------------------------------------------------------------------

class FifteenMinAggregator:
    """Aggregates 1m bars into 15m bars."""

    def __init__(self):
        self.current_key: int = 0
        self.bar: dict | None = None

    def _floor_15m(self, ts: int) -> int:
        return (ts // 900) * 900

    def add(self, ts: int, o: float, h: float, l: float, c: float, v: int) -> dict | None:
        """Add a 1m bar. Returns a completed 15m bar if a new 15m period starts, else None."""
        key = self._floor_15m(ts)

        if key != self.current_key:
            # New 15m period — emit previous bar (if any) and start fresh
            prev = self.bar
            self.current_key = key
            self.bar = {"ts": key, "open": o, "high": h, "low": l, "close": c, "volume": v}
            return prev

        # Same 15m period — update in place
        if self.bar is None:
            self.bar = {"ts": key, "open": o, "high": h, "low": l, "close": c, "volume": v}
        else:
            self.bar["high"] = max(self.bar["high"], h)
            self.bar["low"] = min(self.bar["low"], l)
            self.bar["close"] = c
            self.bar["volume"] += v

        return None

    def flush(self) -> dict | None:
        """Return current partial bar (for upsert on each 1m tick)."""
        return self.bar


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------

def run():
    supabase_url = os.environ.get("SUPABASE_URL")
    supabase_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    databento_key = os.environ.get("DATABENTO_API_KEY")

    if not supabase_url or not supabase_key:
        log.error("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set")
        sys.exit(1)
    if not databento_key:
        log.error("DATABENTO_API_KEY must be set")
        sys.exit(1)

    supabase = create_client(supabase_url, supabase_key)
    agg = FifteenMinAggregator()

    while not shutdown:
        # Sleep during market-closed hours
        if not is_market_open():
            wait = seconds_until_market_open()
            log.info(f"Market closed. Sleeping {wait}s until next open.")
            # Sleep in chunks so we can respond to shutdown signals
            for _ in range(wait):
                if shutdown:
                    return
                time.sleep(1)
            continue

        log.info("Market open. Connecting to Databento Live API...")

        try:
            client = db.Live(key=databento_key)
            client.subscribe(
                dataset=DATASET,
                schema=SCHEMA,
                symbols=[SYMBOL],
                stype_in=STYPE,
            )

            bars_written = 0

            for record in client:
                if shutdown:
                    break

                # Check market hours periodically
                if not is_market_open():
                    log.info("Market closed during session. Disconnecting.")
                    break

                # OHLCVMsg has: open, high, low, close, volume, ts_event
                if not hasattr(record, "open"):
                    continue

                ts_nano = record.ts_event
                ts_sec = ts_nano // 1_000_000_000
                ts_iso = datetime.fromtimestamp(ts_sec, tz=timezone.utc).isoformat()

                o = record.open / PRICE_SCALE
                h = record.high / PRICE_SCALE
                l = record.low / PRICE_SCALE
                c = record.close / PRICE_SCALE
                v = record.volume

                # Skip invalid bars
                if o <= 0 or h <= 0 or l <= 0 or c <= 0 or h < l:
                    continue

                # Upsert 1m bar
                row_1m = {
                    "ts": ts_iso,
                    "open": o,
                    "high": h,
                    "low": l,
                    "close": c,
                    "volume": v,
                }
                supabase.table("mes_1m").upsert(row_1m).execute()

                # Aggregate to 15m
                completed_15m = agg.add(ts_sec, o, h, l, c, v)
                if completed_15m:
                    # A full 15m bar completed — upsert it
                    row_15m = {
                        "ts": datetime.fromtimestamp(completed_15m["ts"], tz=timezone.utc).isoformat(),
                        "open": completed_15m["open"],
                        "high": completed_15m["high"],
                        "low": completed_15m["low"],
                        "close": completed_15m["close"],
                        "volume": completed_15m["volume"],
                    }
                    supabase.table("mes_15m").upsert(row_15m).execute()

                # Also upsert partial 15m bar (intrabar update for chart)
                partial = agg.flush()
                if partial:
                    row_15m_partial = {
                        "ts": datetime.fromtimestamp(partial["ts"], tz=timezone.utc).isoformat(),
                        "open": partial["open"],
                        "high": partial["high"],
                        "low": partial["low"],
                        "close": partial["close"],
                        "volume": partial["volume"],
                    }
                    supabase.table("mes_15m").upsert(row_15m_partial).execute()

                bars_written += 1
                if bars_written % 15 == 0:
                    log.info(f"Bars written: {bars_written} (latest: {ts_iso}, close: {c:.2f})")

        except Exception as e:
            log.error(f"Connection error: {e}")
            if not shutdown:
                log.info("Reconnecting in 5s...")
                time.sleep(5)


if __name__ == "__main__":
    log.info("Warbird Pro — MES Live Feed starting")
    run()
    log.info("Live feed stopped.")
