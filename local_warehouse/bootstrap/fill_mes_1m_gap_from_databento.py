#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

import databento as db
import pandas as pd
import psycopg2


DEFAULT_DSN = "host=127.0.0.1 port=5432 dbname=warbird"
DATASET = "GLBX.MDP3"
SYMBOL = "MES.c.0"
SCHEMA = "ohlcv-1m"
PRICE_SCALE = 1_000_000_000
DEFAULT_LOOKBACK_START = "2026-04-04T00:00:00+00:00"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Backfill the missing local warbird.mes_1m gap directly from Databento historical ohlcv-1m."
    )
    parser.add_argument("--dsn", default=DEFAULT_DSN, help="PostgreSQL DSN for local warbird warehouse.")
    parser.add_argument(
        "--start",
        default=None,
        help="Inclusive UTC lower bound. Default: local mes_1m max(ts) + 1 minute, or 2026-04-04T00:00:00+00:00 if empty.",
    )
    parser.add_argument(
        "--end",
        default=None,
        help="Exclusive UTC upper bound. Default: current UTC time minus 30 minutes.",
    )
    parser.add_argument(
        "--chunk-days",
        type=int,
        default=1,
        help="Databento historical fetch chunk size in days.",
    )
    return parser.parse_args()


def parse_utc(ts: str) -> datetime:
    value = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def is_weekend_bar(ts: int) -> bool:
    dt = datetime.fromtimestamp(ts, tz=UTC)
    wd = dt.weekday()
    hour = dt.hour
    if wd == 5:
        return True
    if wd == 4 and hour >= 22:
        return True
    if wd == 6 and hour < 23:
        return True
    return False


def fetch_local_max_ts(conn: psycopg2.extensions.connection) -> datetime | None:
    with conn.cursor() as cur:
        cur.execute("SELECT MAX(ts) FROM mes_1m")
        row = cur.fetchone()
    if not row or row[0] is None:
        return None
    return row[0].astimezone(UTC)


def fetch_chunk(client: db.Historical, start: datetime, end: datetime) -> list[dict[str, object]]:
    data = client.timeseries.get_range(
        dataset=DATASET,
        symbols=[SYMBOL],
        stype_in="continuous",
        schema=SCHEMA,
        start=start.isoformat(),
        end=end.isoformat(),
    )
    rows: list[dict[str, object]] = []
    for record in data:
        ts_ns = record.ts_event
        ts_s = ts_ns // 1_000_000_000
        if is_weekend_bar(ts_s):
            continue

        open_ = record.open / PRICE_SCALE
        high = record.high / PRICE_SCALE
        low = record.low / PRICE_SCALE
        close = record.close / PRICE_SCALE
        volume = int(record.volume)

        if open_ <= 0 or high <= 0 or low <= 0 or close <= 0:
            continue
        if high < low:
            continue

        rows.append(
            {
                "ts": datetime.fromtimestamp(ts_s, tz=UTC).isoformat(),
                "open": round(open_, 2),
                "high": round(high, 2),
                "low": round(low, 2),
                "close": round(close, 2),
                "volume": volume,
            }
        )
    return rows


def upsert_rows(conn: psycopg2.extensions.connection, frame: pd.DataFrame) -> None:
    with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False) as handle:
        temp_csv = Path(handle.name)
    frame.to_csv(temp_csv, index=False, header=False)

    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                CREATE TEMP TABLE mes_1m_stage_gap (
                  ts timestamptz,
                  open float8,
                  high float8,
                  low float8,
                  close float8,
                  volume bigint
                ) ON COMMIT DROP
                """
            )
            with temp_csv.open("r", encoding="utf-8") as csv_handle:
                cur.copy_expert(
                    """
                    COPY mes_1m_stage_gap (ts, open, high, low, close, volume)
                    FROM STDIN WITH (FORMAT CSV)
                    """,
                    csv_handle,
                )
            cur.execute(
                """
                INSERT INTO mes_1m (ts, open, high, low, close, volume)
                SELECT ts, open, high, low, close, volume
                FROM mes_1m_stage_gap
                ON CONFLICT (ts) DO UPDATE SET
                  open = EXCLUDED.open,
                  high = EXCLUDED.high,
                  low = EXCLUDED.low,
                  close = EXCLUDED.close,
                  volume = EXCLUDED.volume
                """
            )
        conn.commit()
    finally:
        temp_csv.unlink(missing_ok=True)


def main() -> None:
    args = parse_args()
    api_key = os.environ.get("DATABENTO_API_KEY")
    if not api_key:
        raise SystemExit("DATABENTO_API_KEY is not set")

    end_ts = parse_utc(args.end) if args.end else datetime.now(UTC) - timedelta(minutes=30)

    with psycopg2.connect(args.dsn) as conn:
        conn.autocommit = False
        local_max_ts = fetch_local_max_ts(conn)
        if args.start:
            start_ts = parse_utc(args.start)
        elif local_max_ts:
            start_ts = local_max_ts + timedelta(minutes=1)
        else:
            start_ts = parse_utc(DEFAULT_LOOKBACK_START)

        if start_ts >= end_ts:
            print(
                {
                    "status": "noop",
                    "reason": "start_not_before_end",
                    "start": start_ts.isoformat(),
                    "end": end_ts.isoformat(),
                    "local_max_ts": local_max_ts.isoformat() if local_max_ts else None,
                }
            )
            return

        client = db.Historical(key=api_key)
        rows: list[dict[str, object]] = []
        current = start_ts
        while current < end_ts:
            chunk_end = min(current + timedelta(days=args.chunk_days), end_ts)
            rows.extend(fetch_chunk(client, current, chunk_end))
            current = chunk_end

        if not rows:
            print(
                {
                    "status": "noop",
                    "reason": "no_rows_fetched",
                    "start": start_ts.isoformat(),
                    "end": end_ts.isoformat(),
                    "local_max_ts": local_max_ts.isoformat() if local_max_ts else None,
                }
            )
            return

        frame = pd.DataFrame(rows)
        frame["ts"] = pd.to_datetime(frame["ts"], utc=True)
        frame = (
            frame.groupby("ts", sort=True, as_index=False)
            .agg(
                open=("open", "first"),
                high=("high", "max"),
                low=("low", "min"),
                close=("close", "last"),
                volume=("volume", "sum"),
            )
            .sort_values("ts")
        )

        upsert_rows(conn, frame)

        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*), MIN(ts), MAX(ts) FROM mes_1m")
            count, min_ts, max_ts = cur.fetchone()

    print(
        {
            "status": "ok",
            "rows_fetched": int(len(rows)),
            "rows_upserted": int(len(frame)),
            "start": start_ts.isoformat(),
            "end": end_ts.isoformat(),
            "warehouse_count": int(count),
            "warehouse_min_ts": min_ts.isoformat() if min_ts else None,
            "warehouse_max_ts": max_ts.isoformat() if max_ts else None,
        }
    )


if __name__ == "__main__":
    main()
