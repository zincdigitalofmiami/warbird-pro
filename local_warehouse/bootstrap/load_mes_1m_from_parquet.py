#!/usr/bin/env python3
from __future__ import annotations

import argparse
import tempfile
from pathlib import Path

import pandas as pd
import psycopg2


DEFAULT_DSN = "host=127.0.0.1 port=5432 dbname=warbird"
REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PARQUET = REPO_ROOT / "data" / "mes_1m.parquet"
RETENTION_FLOOR = "2020-01-01T00:00:00Z"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Load local project-home data/mes_1m.parquet into warbird.mes_1m."
    )
    parser.add_argument("--dsn", default=DEFAULT_DSN, help="PostgreSQL DSN for local warbird warehouse.")
    parser.add_argument(
        "--parquet",
        default=str(DEFAULT_PARQUET),
        help="Path to the project-home MES 1m parquet file.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    parquet_path = Path(args.parquet)
    if not parquet_path.exists():
        raise SystemExit(f"Parquet not found: {parquet_path}")

    frame = pd.read_parquet(parquet_path, columns=["ts", "open", "high", "low", "close", "volume", "symbol"])
    if "symbol" in frame.columns:
        frame = frame[frame["symbol"] == "MES"].copy()

    frame["ts"] = pd.to_datetime(frame["ts"], utc=True)
    frame = frame[frame["ts"] >= pd.Timestamp(RETENTION_FLOOR)]
    frame = frame.sort_values(["ts"])

    deduped = (
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

    with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False) as handle:
        temp_csv = Path(handle.name)
    deduped.to_csv(temp_csv, index=False, header=False)

    try:
        with psycopg2.connect(args.dsn) as conn:
            conn.autocommit = False
            with conn.cursor() as cur:
                cur.execute(
                    """
                    CREATE TEMP TABLE mes_1m_stage (
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
                        COPY mes_1m_stage (ts, open, high, low, close, volume)
                        FROM STDIN WITH (FORMAT CSV)
                        """,
                        csv_handle,
                    )
                cur.execute(
                    """
                    INSERT INTO mes_1m (ts, open, high, low, close, volume)
                    SELECT ts, open, high, low, close, volume
                    FROM mes_1m_stage
                    ON CONFLICT (ts) DO UPDATE SET
                      open = EXCLUDED.open,
                      high = EXCLUDED.high,
                      low = EXCLUDED.low,
                      close = EXCLUDED.close,
                      volume = EXCLUDED.volume
                    """
                )
                cur.execute(
                    """
                    SELECT COUNT(*), MIN(ts), MAX(ts)
                    FROM mes_1m
                    """
                )
                count, min_ts, max_ts = cur.fetchone()
            conn.commit()
    finally:
        temp_csv.unlink(missing_ok=True)

    print(
        {
            "parquet": str(parquet_path),
            "rows_loaded": int(len(deduped)),
            "warehouse_count": int(count),
            "warehouse_min_ts": min_ts.isoformat() if min_ts else None,
            "warehouse_max_ts": max_ts.isoformat() if max_ts else None,
        }
    )


if __name__ == "__main__":
    main()
