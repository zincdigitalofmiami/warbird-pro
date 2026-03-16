from __future__ import annotations

from datetime import datetime, time as dt_time, timedelta, timezone
from zoneinfo import ZoneInfo

CHICAGO = ZoneInfo("America/Chicago")


def floor_interval(ts_epoch: int, interval_seconds: int) -> int:
    return (ts_epoch // interval_seconds) * interval_seconds


def mes_session_day_start(ts_epoch: int) -> int:
    dt_utc = datetime.fromtimestamp(ts_epoch, tz=timezone.utc)
    dt_ct = dt_utc.astimezone(CHICAGO)
    session_date = dt_ct.date()

    if dt_ct.hour < 17:
        session_date = session_date - timedelta(days=1)

    session_start_ct = datetime.combine(
        session_date,
        dt_time(hour=17, minute=0),
        tzinfo=CHICAGO,
    )
    return int(session_start_ct.astimezone(timezone.utc).timestamp())


def aggregate_ohlcv(
    bars_1m: list[dict],
    bucket_for_epoch,
    ts_field: str = "ts_epoch",
) -> list[dict]:
    buckets: dict[int, dict] = {}

    for bar in bars_1m:
        ts_epoch = int(bar[ts_field])
        bucket_ts = int(bucket_for_epoch(ts_epoch))
        existing = buckets.get(bucket_ts)

        if existing is None:
            buckets[bucket_ts] = {
                "ts_epoch": bucket_ts,
                "open": float(bar["open"]),
                "high": float(bar["high"]),
                "low": float(bar["low"]),
                "close": float(bar["close"]),
                "volume": int(bar["volume"]),
            }
            continue

        existing["high"] = max(existing["high"], float(bar["high"]))
        existing["low"] = min(existing["low"], float(bar["low"]))
        existing["close"] = float(bar["close"])
        existing["volume"] += int(bar["volume"])

    return sorted(buckets.values(), key=lambda row: row["ts_epoch"])


def aggregate_mes_timeframes(bars_1m: list[dict]) -> dict[str, list[dict]]:
    return {
        "mes_15m": aggregate_ohlcv(bars_1m, lambda ts: floor_interval(ts, 900)),
        "mes_1h": aggregate_ohlcv(bars_1m, lambda ts: floor_interval(ts, 3600)),
        "mes_4h": aggregate_ohlcv(bars_1m, lambda ts: floor_interval(ts, 14_400)),
        "mes_1d": aggregate_ohlcv(bars_1m, mes_session_day_start),
    }
