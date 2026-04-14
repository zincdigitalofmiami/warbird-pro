#!/usr/bin/env python3
from __future__ import annotations

import argparse
import tempfile
from datetime import UTC, timedelta
from pathlib import Path
from typing import Any

import pandas as pd
import psycopg2
from psycopg2.extras import RealDictCursor


DEFAULT_DSN = "host=127.0.0.1 port=5432 dbname=warbird"
REPO_ROOT = Path(__file__).resolve().parents[2]


def floor_interval(ts_epoch: int, interval_seconds: int) -> int:
    return (ts_epoch // interval_seconds) * interval_seconds


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Roll forward local warbird.mes_15m from canonical local mes_1m with closed-bucket enforcement."
    )
    parser.add_argument("--dsn", default=DEFAULT_DSN, help="PostgreSQL DSN for local warbird warehouse.")
    parser.add_argument(
        "--start",
        default=None,
        help="Inclusive UTC lower bound. Default: max mes_15m ts minus 14 minutes, or min mes_1m ts.",
    )
    return parser.parse_args()


def fetch_one(conn: psycopg2.extensions.connection, sql: str, params: tuple[Any, ...] = ()) -> tuple[Any, ...]:
    with conn.cursor() as cur:
        cur.execute(sql, params)
        return cur.fetchone()


def fetch_mes_1m_rows(conn: psycopg2.extensions.connection, start_ts: str | None) -> list[dict[str, Any]]:
    where_sql = "WHERE ts >= %s::timestamptz" if start_ts else ""
    params: tuple[Any, ...] = (start_ts,) if start_ts else ()
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            f"""
            SELECT ts, open, high, low, close, volume
            FROM mes_1m
            {where_sql}
            ORDER BY ts ASC
            """,
            params,
        )
        return cur.fetchall()


def upsert_mes_15m(conn: psycopg2.extensions.connection, frame: pd.DataFrame) -> None:
    with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False) as handle:
        temp_csv = Path(handle.name)
    frame.to_csv(temp_csv, index=False, header=False)

    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                CREATE TEMP TABLE mes_15m_stage_rollup (
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
                    COPY mes_15m_stage_rollup (ts, open, high, low, close, volume)
                    FROM STDIN WITH (FORMAT CSV)
                    """,
                    csv_handle,
                )
            cur.execute(
                """
                INSERT INTO mes_15m (ts, open, high, low, close, volume)
                SELECT ts, open, high, low, close, volume
                FROM mes_15m_stage_rollup
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
    with psycopg2.connect(args.dsn) as conn:
        conn.autocommit = False
        max_15m_ts = fetch_one(conn, "SELECT MAX(ts) FROM mes_15m")[0]
        min_1m_ts = fetch_one(conn, "SELECT MIN(ts) FROM mes_1m")[0]
        max_1m_ts = fetch_one(conn, "SELECT MAX(ts) FROM mes_1m")[0]

        if min_1m_ts is None or max_1m_ts is None:
            raise SystemExit("mes_1m is empty")

        if args.start:
            start_ts = pd.Timestamp(args.start, tz=UTC)
        elif max_15m_ts is not None:
            start_ts = max_15m_ts.astimezone(UTC) - timedelta(minutes=14)
        else:
            start_ts = min_1m_ts.astimezone(UTC)

        rows = fetch_mes_1m_rows(conn, start_ts.isoformat())
        if not rows:
            print(
                {
                    "status": "noop",
                    "reason": "no_mes_1m_rows",
                    "start": start_ts.isoformat(),
                }
            )
            return

        frame = pd.DataFrame(rows)
        frame["ts"] = pd.to_datetime(frame["ts"], utc=True)
        frame["ts_epoch"] = (frame["ts"].view("int64") // 1_000_000_000).astype("int64")
        frame["bucket_epoch"] = frame["ts_epoch"].map(lambda ts: floor_interval(int(ts), 900))

        bucketed = (
            frame.groupby("bucket_epoch", sort=True, as_index=False)
            .agg(
                ts=("ts", "first"),
                open=("open", "first"),
                high=("high", "max"),
                low=("low", "min"),
                close=("close", "last"),
                volume=("volume", "sum"),
                minute_count=("ts", "count"),
                max_minute_ts=("ts", "max"),
            )
            .sort_values("bucket_epoch")
        )

        closed = bucketed[
            (bucketed["minute_count"] == 15)
            & ((bucketed["ts"] + pd.Timedelta(minutes=14)) <= bucketed["max_minute_ts"])
        ][["ts", "open", "high", "low", "close", "volume"]].copy()

        if closed.empty:
            print(
                {
                    "status": "noop",
                    "reason": "no_closed_buckets",
                    "start": start_ts.isoformat(),
                    "max_1m_ts": max_1m_ts.isoformat(),
                }
            )
            return

        upsert_mes_15m(conn, closed)
        count, min_ts, max_ts = fetch_one(conn, "SELECT COUNT(*), MIN(ts), MAX(ts) FROM mes_15m")

    print(
        {
            "status": "ok",
            "start": start_ts.isoformat(),
            "rollup_rows": int(len(closed)),
            "warehouse_count": int(count),
            "warehouse_min_ts": min_ts.isoformat() if min_ts else None,
            "warehouse_max_ts": max_ts.isoformat() if max_ts else None,
        }
    )


if __name__ == "__main__":
    main()
