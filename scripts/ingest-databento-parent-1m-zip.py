#!/usr/bin/env python3
"""Ingest a Databento parent-stype `ohlcv-1m` zip into cross_asset_1h.parquet.

Why this is different from the continuous-front-month refresh script:
  Databento `stype_in="parent"` zips contain rows for EVERY contract month
  simultaneously. For a sparsely-traded instrument like HG copper, the
  continuous front month is often quiet while another contract trades. Parent
  stype gives 5-10x more bar coverage. To produce a single time-series usable
  by the cross-asset feature pipeline we:
    1. Aggregate per minute across contracts: pick the MAX-volume contract's
       close (most-actively-traded contract). Sum volumes. Use that contract's
       open/high/low.
    2. Roll up 1m -> 1h: first/max/min/last/sum (OHLCV).
    3. Merge the new symbol rows into the cross_asset_1h parquet, replacing
       any existing rows for the symbol within the new date range.

Usage:
  python3 scripts/ingest-databento-parent-1m-zip.py \
    --zip "data/HG 5y GLBX-20260511-XUAJDPVA5J.zip" \
    --symbol HG

  python3 scripts/ingest-databento-parent-1m-zip.py \
    --zip "data/<NQ_1m_parent_zip>" \
    --symbol NQ

The expected zip layout matches Databento's CSV download:
  metadata.json
  condition.json
  glbx-mdp3-YYYYMMDD-YYYYMMDD.ohlcv-1m.csv.zst  (one per month)
"""

from __future__ import annotations

import argparse
import io
import json
import re
import shutil
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import zstandard as zstd

PARQUET_PATH = Path(
    "/Volumes/Satechi Hub/Historical Data/Databento/raw/databento_futures_ohlcv_1h.parquet"
)


def outright_pattern(root: str) -> re.Pattern[str]:
    """Match Databento outright contracts only (no calendar spreads).

    Outright example:  HGZ5 (Dec 2025 copper)
    Spread example:    HGZ5-HGF6 (Dec 2025 / Jan 2026 calendar spread)

    The CME month codes are FGHJKMNQUVXZ. Year is 1-2 digits.
    """
    return re.compile(rf"^{re.escape(root)}[FGHJKMNQUVXZ]\d{{1,2}}$")


def stream_zip_csvs(zip_path: Path) -> pd.DataFrame:
    """Read every `*.ohlcv-1m.csv.zst` member; return one concat'd DataFrame."""
    frames: list[pd.DataFrame] = []
    with zipfile.ZipFile(zip_path) as zf:
        # Two layouts to handle:
        #   split_symbols=false: <prefix>.ohlcv-1m.csv.zst (one file/month, all contracts)
        #   split_symbols=true:  <prefix>.ohlcv-1m.<CONTRACT>.csv.zst (one file/contract/month)
        members = sorted(n for n in zf.namelist() if ".ohlcv-1m." in n and n.endswith(".csv.zst"))
        if not members:
            sys.exit(f"No .ohlcv-1m.*.csv.zst members in {zip_path}")
        for name in members:
            with zf.open(name) as raw:
                reader = zstd.ZstdDecompressor().stream_reader(raw)
                text = io.TextIOWrapper(reader, encoding="utf-8")
                df = pd.read_csv(text)
            frames.append(df)
            print(f"    {name}: {len(df):,} rows", flush=True)
    return pd.concat(frames, ignore_index=True)


def aggregate_to_single_1m(df: pd.DataFrame, root: str) -> pd.DataFrame:
    """Multi-contract -> single row per minute. Max-volume OUTRIGHT contract wins for OHLC.

    Spreads (e.g. HGZ5-HGF6) are filtered out before aggregation because their
    "close" is a price-difference (e.g. $0.005), not a price level. Including
    them would contaminate the close used by downstream features.
    """
    df = df.copy()
    df["ts_event"] = pd.to_datetime(df["ts_event"], utc=True).dt.tz_localize(None)
    df["volume"] = pd.to_numeric(df["volume"], errors="coerce").fillna(0).astype("int64")
    for col in ("open", "high", "low", "close"):
        df[col] = pd.to_numeric(df[col], errors="coerce")

    # Filter to outright contracts only.
    pat = outright_pattern(root)
    before = len(df)
    before_syms = df["symbol"].nunique()
    df = df.loc[df["symbol"].astype(str).str.match(pat)].copy()
    after = len(df)
    after_syms = df["symbol"].nunique()
    print(f"  filter to {root} outrights: {before:,} rows / {before_syms} symbols -> {after:,} rows / {after_syms} symbols", flush=True)
    if df.empty:
        sys.exit(f"After outright filter, no rows remain for root '{root}'.")

    # Per minute, pick the max-volume contract's row (deterministic tiebreak by symbol)
    df = df.sort_values(["ts_event", "volume", "symbol"], ascending=[True, False, True])
    most_active = df.drop_duplicates(subset=["ts_event"], keep="first").copy()
    # Total outright volume across contracts per minute
    total_volume = df.groupby("ts_event", as_index=False)["volume"].sum()
    total_volume = total_volume.rename(columns={"volume": "_total_vol"})
    most_active = most_active.merge(total_volume, on="ts_event", how="left")
    most_active["volume"] = most_active["_total_vol"]
    most_active = most_active.drop(columns=["_total_vol"])
    return most_active[["ts_event", "open", "high", "low", "close", "volume", "symbol"]]


def rollup_1m_to_1h(df: pd.DataFrame, symbol_short: str) -> pd.DataFrame:
    """Standard OHLC + sum-volume aggregation from 1m to 1h."""
    df = df.copy()
    df["bar_1h"] = df["ts_event"].dt.floor("h")
    agg = (
        df.groupby("bar_1h", as_index=False)
        .agg(
            open=("open", "first"),
            high=("high", "max"),
            low=("low", "min"),
            close=("close", "last"),
            volume=("volume", "sum"),
        )
        .rename(columns={"bar_1h": "ts_event"})
    )
    agg["symbol"] = symbol_short
    agg["open_interest"] = 0
    agg["source"] = "databento_1m_parent_rolled_to_1h"
    agg["ingested_at"] = pd.Timestamp.utcnow().tz_localize(None)
    return agg[
        ["symbol", "ts_event", "open", "high", "low", "close", "volume", "open_interest", "source", "ingested_at"]
    ]


def _normalize_dtypes(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    for col in ("symbol", "source"):
        out[col] = out[col].astype(str)
    for col in ("open", "high", "low", "close"):
        out[col] = pd.to_numeric(out[col], errors="coerce").astype("float64")
    for col in ("volume", "open_interest"):
        out[col] = pd.to_numeric(out[col], errors="coerce").fillna(0).astype("int64")
    for col in ("ts_event", "ingested_at"):
        s = pd.to_datetime(out[col])
        if hasattr(s.dt, "tz") and s.dt.tz is not None:
            s = s.dt.tz_convert("UTC").dt.tz_localize(None)
        out[col] = s.astype("datetime64[ns]")
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--zip", type=Path, required=True, help="Path to Databento parent-stype 1m zip")
    ap.add_argument("--symbol", required=True, help="Short symbol code in parquet (e.g. HG, NQ, ZN, 6E)")
    ap.add_argument("--parquet", type=Path, default=PARQUET_PATH)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    if not args.zip.exists():
        sys.exit(f"Zip not found: {args.zip}")
    if not args.parquet.exists():
        sys.exit(f"Parquet not found: {args.parquet}")

    print(f"Source zip:     {args.zip}", flush=True)
    print(f"Symbol code:    {args.symbol}", flush=True)
    print(f"Target parquet: {args.parquet}", flush=True)

    # Verify zip metadata (best-effort)
    with zipfile.ZipFile(args.zip) as zf:
        if "metadata.json" in zf.namelist():
            meta = json.loads(zf.read("metadata.json"))
            q = meta.get("query", {})
            print(f"\nZip metadata: schema={q.get('schema')} stype_in={q.get('stype_in')} symbols={q.get('symbols')}", flush=True)

    print("\nReading monthly CSVs from zip ...", flush=True)
    raw = stream_zip_csvs(args.zip)
    print(f"  total 1m rows across all months: {len(raw):,}", flush=True)
    print(f"  unique contracts: {raw['symbol'].nunique()}  (e.g. {sorted(raw['symbol'].unique())[:6]})", flush=True)

    print("\nAggregating to single time-series (max-volume outright contract per minute) ...", flush=True)
    single_1m = aggregate_to_single_1m(raw, args.symbol)
    print(f"  unique 1m bars after collapse: {len(single_1m):,}", flush=True)
    print(f"  date range: {single_1m['ts_event'].min()} -> {single_1m['ts_event'].max()}", flush=True)

    print("\nRolling up 1m -> 1h ...", flush=True)
    new_1h = rollup_1m_to_1h(single_1m, args.symbol)
    print(f"  1h bars produced: {len(new_1h):,}", flush=True)

    # Read existing parquet
    existing = pd.read_parquet(args.parquet)
    print(f"\nExisting parquet: {len(existing):,} rows across {existing['symbol'].nunique()} symbols", flush=True)

    # Drop existing rows for this symbol within the new data's date range
    new_min = new_1h["ts_event"].min()
    new_max = new_1h["ts_event"].max()
    mask_drop = (
        existing["symbol"].astype(str).eq(args.symbol)
        & (pd.to_datetime(existing["ts_event"]).dt.tz_localize(None) >= new_min)
        & (pd.to_datetime(existing["ts_event"]).dt.tz_localize(None) <= new_max)
    )
    dropped = int(mask_drop.sum())
    kept = existing.loc[~mask_drop].copy()
    print(f"  Dropping {dropped} existing {args.symbol} rows in {new_min.date()} -> {new_max.date()}", flush=True)

    kept = _normalize_dtypes(kept)
    new_1h = _normalize_dtypes(new_1h)

    merged = (
        pd.concat([kept, new_1h], ignore_index=True)
        .sort_values(["symbol", "ts_event"])
        .reset_index(drop=True)
    )
    print(f"\nMerged total: {len(merged):,} rows ({len(kept)} kept + {len(new_1h)} new)", flush=True)

    # Sanity per-symbol summary
    sym_rows = merged.loc[merged["symbol"] == args.symbol]
    print(f"\nPost-merge for {args.symbol}: {len(sym_rows):,} rows")
    print(f"  first: {sym_rows['ts_event'].min()}")
    print(f"  last:  {sym_rows['ts_event'].max()}")

    if args.dry_run:
        print("\n--dry-run: no write", flush=True)
        return 0

    backup = args.parquet.with_suffix(
        f".bak-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.parquet"
    )
    print(f"\nBacking up -> {backup}", flush=True)
    shutil.copy2(args.parquet, backup)

    tmp = args.parquet.with_suffix(".new.parquet")
    print(f"Writing merged -> {tmp}", flush=True)
    merged.to_parquet(tmp, engine="pyarrow", index=False)
    tmp.replace(args.parquet)

    rt = pd.read_parquet(args.parquet)
    print(f"\nRound-trip read: {len(rt):,} rows; backup preserved at {backup}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
