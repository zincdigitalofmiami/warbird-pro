#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import tempfile
import zipfile
from pathlib import Path

import databento as db
import pandas as pd
import psycopg2


DEFAULT_DSN = "host=127.0.0.1 port=5432 dbname=warbird"
REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_1M_ZIP = REPO_ROOT / "data" / "MESGLBX-20260414-DCWTP3EFFR.zip"
DEFAULT_1H_ZIP = REPO_ROOT / "data" / "MESGLBX-20260414-ECSQYLDQH3.zip"
DEFAULT_1D_ZIP = REPO_ROOT / "data" / "MESGLBX-20260414-VHY3JGN4XJ.zip"
RETENTION_FLOOR = "2020-01-01T00:00:00Z"
PRICE_SCALE = 1e9


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Reset local warbird MES OHLCV tables from Databento DBN zip exports."
    )
    parser.add_argument("--dsn", default=DEFAULT_DSN, help="PostgreSQL DSN for local warbird warehouse.")
    parser.add_argument("--zip-1m", default=str(DEFAULT_1M_ZIP), help="Path to the MES 1m Databento DBN zip.")
    parser.add_argument("--zip-1h", default=str(DEFAULT_1H_ZIP), help="Path to the MES 1h Databento DBN zip.")
    parser.add_argument("--zip-1d", default=str(DEFAULT_1D_ZIP), help="Path to the MES 1d Databento DBN zip.")
    return parser.parse_args()


def dbn_files_in_zip(zip_path: Path) -> list[str]:
    with zipfile.ZipFile(zip_path) as zf:
        return sorted(name for name in zf.namelist() if name.endswith(".dbn.zst"))


def load_file_from_zip(zip_path: Path, filename: str) -> pd.DataFrame:
    with zipfile.ZipFile(zip_path) as zf:
        data = zf.read(filename)

    with tempfile.NamedTemporaryFile(suffix=".dbn.zst", delete=False) as tmp:
        tmp.write(data)
        tmp_path = tmp.name

    try:
        store = db.DBNStore.from_file(tmp_path)
        df = store.to_df(pretty_ts=True, map_symbols=True)
    finally:
        os.unlink(tmp_path)

    if df.index.name in ("ts_event", "ts"):
        df = df.reset_index()

    ts_col = "ts_event" if "ts_event" in df.columns else "ts"
    if ts_col not in df.columns:
        raise ValueError(f"No timestamp column found in {filename}")
    if "symbol" not in df.columns:
        raise ValueError(f"No symbol column found in {filename}")

    df["ts"] = pd.to_datetime(df[ts_col], utc=True)

    for col in ["open", "high", "low", "close"]:
        sample = df[col].dropna()
        if len(sample) > 0 and float(sample.iloc[0]) > 1_000_000:
            df[col] = df[col].astype("float64") / PRICE_SCALE
        else:
            df[col] = df[col].astype("float64")

    if "volume" in df.columns:
        df["volume"] = df["volume"].astype("int64")
    elif "size" in df.columns:
        df["volume"] = df["size"].astype("int64")
    else:
        df["volume"] = 0

    return df[["ts", "symbol", "open", "high", "low", "close", "volume"]].copy()


def keep_highest_volume_outright(raw: pd.DataFrame) -> pd.DataFrame:
    filtered = raw[
        raw["symbol"].astype(str).str.startswith("MES")
        & ~raw["symbol"].astype(str).str.contains("-", na=False)
    ].copy()
    if filtered.empty:
        return filtered

    filtered = filtered.sort_values(["ts", "volume", "symbol"], ascending=[True, False, True])
    filtered = filtered.drop_duplicates(subset=["ts"], keep="first")
    filtered = filtered[["ts", "open", "high", "low", "close", "volume"]].copy()
    filtered = filtered.sort_values("ts").reset_index(drop=True)
    return filtered


def load_mes_zip(zip_path: Path) -> pd.DataFrame:
    if not zip_path.exists():
        raise FileNotFoundError(f"Zip not found: {zip_path}")

    files = dbn_files_in_zip(zip_path)
    if not files:
        raise ValueError(f"No .dbn.zst files found in {zip_path}")

    frames: list[pd.DataFrame] = []
    for name in files:
        raw = load_file_from_zip(zip_path, name)
        picked = keep_highest_volume_outright(raw)
        if not picked.empty:
            frames.append(picked)

    combined = pd.concat(frames, ignore_index=True)
    combined = combined[combined["ts"] >= pd.Timestamp(RETENTION_FLOOR)]
    combined = combined.sort_values("ts")
    combined = combined.drop_duplicates(subset=["ts"], keep="last").reset_index(drop=True)
    return combined


def resample_ohlcv(df: pd.DataFrame, freq: str, closed: str = "left", label: str = "left") -> pd.DataFrame:
    result = (
        df.set_index("ts")
        .resample(freq, closed=closed, label=label)
        .agg(
            open=("open", "first"),
            high=("high", "max"),
            low=("low", "min"),
            close=("close", "last"),
            volume=("volume", "sum"),
        )
        .dropna(subset=["close"])
        .reset_index()
    )
    result["volume"] = result["volume"].astype("int64")
    return result


def write_time_table(conn: psycopg2.extensions.connection, table_name: str, frame: pd.DataFrame) -> None:
    with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False) as handle:
        temp_csv = Path(handle.name)
    frame.to_csv(temp_csv, index=False, header=False)

    try:
        with conn.cursor() as cur:
            cur.execute("DROP TABLE IF EXISTS mes_stage_time")
            cur.execute(
                """
                CREATE TEMP TABLE mes_stage_time (
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
                    COPY mes_stage_time (ts, open, high, low, close, volume)
                    FROM STDIN WITH (FORMAT CSV)
                    """,
                    csv_handle,
                )
            cur.execute(f"TRUNCATE {table_name}")
            cur.execute(
                f"""
                INSERT INTO {table_name} (ts, open, high, low, close, volume)
                SELECT ts, open, high, low, close, volume
                FROM mes_stage_time
                ORDER BY ts
                """
            )
    finally:
        temp_csv.unlink(missing_ok=True)


def write_daily_table(conn: psycopg2.extensions.connection, frame: pd.DataFrame) -> None:
    with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False) as handle:
        temp_csv = Path(handle.name)
    frame.to_csv(temp_csv, index=False, header=False)

    try:
        with conn.cursor() as cur:
            cur.execute("DROP TABLE IF EXISTS mes_stage_day")
            cur.execute(
                """
                CREATE TEMP TABLE mes_stage_day (
                  date date,
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
                    COPY mes_stage_day (date, open, high, low, close, volume)
                    FROM STDIN WITH (FORMAT CSV)
                    """,
                    csv_handle,
                )
            cur.execute("TRUNCATE mes_1d")
            cur.execute(
                """
                INSERT INTO mes_1d (date, open, high, low, close, volume)
                SELECT date, open, high, low, close, volume
                FROM mes_stage_day
                ORDER BY date
                """
            )
    finally:
        temp_csv.unlink(missing_ok=True)


def fetch_table_stats(conn: psycopg2.extensions.connection, table_name: str) -> tuple[int, object, object]:
    with conn.cursor() as cur:
        if table_name == "mes_1d":
            cur.execute("SELECT COUNT(*), MIN(date), MAX(date) FROM mes_1d")
        else:
            cur.execute(f"SELECT COUNT(*), MIN(ts), MAX(ts) FROM {table_name}")
        return cur.fetchone()


def main() -> None:
    args = parse_args()
    zip_1m = Path(args.zip_1m)
    zip_1h = Path(args.zip_1h)
    zip_1d = Path(args.zip_1d)

    mes_1m = load_mes_zip(zip_1m)
    mes_15m = resample_ohlcv(mes_1m, "15min")
    mes_1h = load_mes_zip(zip_1h)
    mes_4h = resample_ohlcv(mes_1h, "4h")
    mes_1d_raw = load_mes_zip(zip_1d)
    mes_1d = mes_1d_raw.copy()
    mes_1d["date"] = mes_1d["ts"].dt.date
    mes_1d = mes_1d[["date", "open", "high", "low", "close", "volume"]].copy()
    mes_1d = mes_1d.sort_values("date").drop_duplicates(subset=["date"], keep="last").reset_index(drop=True)

    with psycopg2.connect(args.dsn) as conn:
        conn.autocommit = False
        write_time_table(conn, "mes_1m", mes_1m)
        write_time_table(conn, "mes_15m", mes_15m)
        write_time_table(conn, "mes_1h", mes_1h)
        write_time_table(conn, "mes_4h", mes_4h)
        write_daily_table(conn, mes_1d)
        conn.commit()

        stats = {
            "mes_1m": fetch_table_stats(conn, "mes_1m"),
            "mes_15m": fetch_table_stats(conn, "mes_15m"),
            "mes_1h": fetch_table_stats(conn, "mes_1h"),
            "mes_4h": fetch_table_stats(conn, "mes_4h"),
            "mes_1d": fetch_table_stats(conn, "mes_1d"),
        }

    print(
        {
            "zip_1m": str(zip_1m),
            "zip_1h": str(zip_1h),
            "zip_1d": str(zip_1d),
            "mes_1m_rows": int(len(mes_1m)),
            "mes_15m_rows": int(len(mes_15m)),
            "mes_1h_rows": int(len(mes_1h)),
            "mes_4h_rows": int(len(mes_4h)),
            "mes_1d_rows": int(len(mes_1d)),
            "warehouse": {
                name: {
                    "count": int(count),
                    "min": str(min_v) if min_v is not None else None,
                    "max": str(max_v) if max_v is not None else None,
                }
                for name, (count, min_v, max_v) in stats.items()
            },
        }
    )


if __name__ == "__main__":
    main()
