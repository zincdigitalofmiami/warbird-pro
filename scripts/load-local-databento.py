#!/usr/bin/env python3
"""
Unzip Databento batch downloads, normalize, and replace local Supabase tables.

  MES 1m zip  → TRUNCATE + reload mes_1m
  MES 1h zip  → TRUNCATE + reload mes_1h
  IM  1m zip  → aggregate 1m→1h, TRUNCATE + reload cross_asset_1h (NQ/RTY/CL/HG/6E/6J)
"""

from __future__ import annotations

import databento as db
import pandas as pd
import psycopg2
import psycopg2.extras
import zipfile
import tempfile
import os
import logging
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger(__name__)

LOCAL_DB   = "postgresql://postgres:postgres@127.0.0.1:54322/postgres"
BATCH_DIR  = Path("/Volumes/Satechi Hub/Historical Data/Databento/warehouse/batch_jobs")
MES_1M_ZIP = BATCH_DIR / "GLBX-20260405-75PD3JMW9Q" / "MES 1m GLBX-20260405-75PD3JMW9Q.zip"
MES_1H_ZIP = BATCH_DIR / "GLBX-20260405-AD9XQKUFAA" / "MES 1h GLBX-20260405-AD9XQKUFAA.zip"
IM_ZIP     = BATCH_DIR / "GLBX-20260405-EJTKT7UUVK"  / "Intermarket Futures GLBX-20260405-EJTKT7UUVK.zip"

# Contract prefix → symbol_code in DB
PARENT_MAP = {"NQ": "NQ", "RTY": "RTY", "CL": "CL", "HG": "HG", "6E": "6E", "6J": "6J"}


def dbn_files_in_zip(zip_path: Path) -> list[str]:
    with zipfile.ZipFile(zip_path) as zf:
        return sorted(f for f in zf.namelist() if f.endswith(".dbn.zst"))


def load_file_from_zip(zip_path: Path, filename: str) -> pd.DataFrame:
    with zipfile.ZipFile(zip_path) as zf:
        data = zf.read(filename)
    with tempfile.NamedTemporaryFile(suffix=".dbn.zst", delete=False) as tmp:
        tmp.write(data)
        tmp_path = tmp.name
    try:
        store = db.DBNStore.from_file(tmp_path)
        df = store.to_df(pretty_ts=True, map_symbols=True)
        # Drop spreads and extra columns, keep only outright contracts
        df = df[~df["symbol"].str.contains("-", na=False)][["open","high","low","close","volume","symbol"]].copy()
        return df
    finally:
        os.unlink(tmp_path)


def front_month(df: pd.DataFrame) -> pd.DataFrame:
    """Keep only the highest-volume contract (front month)."""
    if df.empty:
        return df
    top = df.groupby("symbol")["volume"].sum().idxmax()
    return df[df["symbol"] == top][["open","high","low","close","volume"]].copy()


def load_mes(conn, zip_path: Path, table: str) -> None:
    files = dbn_files_in_zip(zip_path)
    log.info(f"{table}: loading {len(files)} monthly files")

    frames = []
    for fname in files:
        df = load_file_from_zip(zip_path, fname)
        df = front_month(df)
        if not df.empty:
            frames.append(df)
        log.info(f"  {fname}: {len(df)} rows")

    if not frames:
        log.error(f"{table}: no data loaded")
        return

    full = pd.concat(frames).sort_index()
    full = full[~full.index.duplicated(keep="last")]
    log.info(f"{table}: {len(full)} total rows — replacing table")

    rows = [
        (ts.isoformat(), float(r.open), float(r.high), float(r.low), float(r.close), int(r.volume))
        for ts, r in full.iterrows()
    ]

    with conn.cursor() as cur:
        cur.execute(f"TRUNCATE {table}")
        psycopg2.extras.execute_values(
            cur,
            f"INSERT INTO {table} (ts, open, high, low, close, volume) VALUES %s",
            rows,
            page_size=2000,
        )
    conn.commit()
    log.info(f"✓ {table}: {len(rows)} rows written")


def load_intermarket(conn, zip_path: Path) -> None:
    files = dbn_files_in_zip(zip_path)
    log.info(f"cross_asset_1h: loading {len(files)} intermarket files")

    by_parent: dict[str, list[pd.DataFrame]] = {p: [] for p in PARENT_MAP}

    for fname in files:
        df = load_file_from_zip(zip_path, fname)
        if df.empty:
            continue
        sym = df["symbol"].iloc[0]
        parent = next((p for p in PARENT_MAP if sym.startswith(p)), None)
        if parent is None:
            continue
        by_parent[parent].append(df.drop(columns=["symbol"]))

    rows = []
    for prefix, frames in by_parent.items():
        symbol_code = PARENT_MAP[prefix]
        if not frames:
            log.warning(f"  {symbol_code}: no data")
            continue

        merged = pd.concat(frames).sort_index()
        # Per minute, keep highest-volume row (front month)
        merged = (
            merged.reset_index()
            .sort_values("volume", ascending=False)
            .drop_duplicates(subset=["ts_event"])
            .set_index("ts_event")
            .sort_index()
        )
        # Resample 1m → 1h
        hourly = merged.resample("1h").agg(
            open=("open", "first"),
            high=("high", "max"),
            low=("low", "min"),
            close=("close", "last"),
            volume=("volume", "sum"),
        ).dropna(subset=["open"])

        for ts, r in hourly.iterrows():
            rows.append((
                ts.isoformat(), symbol_code,
                float(r.open), float(r.high), float(r.low), float(r.close), int(r.volume),
            ))
        log.info(f"  {symbol_code}: {len(hourly)} 1h bars")

    log.info(f"cross_asset_1h: {len(rows)} total rows — replacing NQ/RTY/CL/HG/6E/6J")

    with conn.cursor() as cur:
        cur.execute(
            "DELETE FROM cross_asset_1h WHERE symbol_code = ANY(%s)",
            (list(PARENT_MAP.values()),),
        )
        psycopg2.extras.execute_values(
            cur,
            "INSERT INTO cross_asset_1h (ts, symbol_code, open, high, low, close, volume) VALUES %s",
            rows,
            page_size=2000,
        )
    conn.commit()
    log.info(f"✓ cross_asset_1h: {len(rows)} rows written")


def main() -> None:
    conn = psycopg2.connect(LOCAL_DB)
    try:
        load_mes(conn, MES_1M_ZIP, "mes_1m")
        load_mes(conn, MES_1H_ZIP, "mes_1h")
        load_intermarket(conn, IM_ZIP)
    finally:
        conn.close()
    log.info("Done.")


if __name__ == "__main__":
    main()
