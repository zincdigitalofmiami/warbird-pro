#!/usr/bin/env python3
"""Ingest a Databento parent-stype `ohlcv-1m` zip into the main ES bars parquet.

Sibling of `scripts/ingest-databento-parent-1m-zip.py`. Differences:
  - Output stays at 1-minute resolution (no 1h rollup) — the V9 builder's
    `load_bars()` consumes 1m bars and aggregates to 5m/15m itself.
  - Target schema matches the existing `data/es_1m_<date>.parquet` exactly:
    columns = ts (TIMESTAMP WITH TIME ZONE), open/high/low/close (DOUBLE),
    volume (BIGINT), symbol (VARCHAR). No open_interest / source / ingested_at.
  - Per-minute aggregation = max-volume OUTRIGHT contract wins (spreads filtered).
  - In-place replacement: existing parquet is renamed to .bak-<ts>.parquet,
    new file written to the same path.

Usage:
  python3 scripts/ingest-databento-parent-1m-bars.py \\
    --zip "data/<ES_1m_parent_zip>" \\
    --symbol ES \\
    --target data/es_1m_20260503.parquet
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

DEFAULT_TARGET = Path("/Volumes/Satechi Hub/warbird-pro/data/es_1m_20260503.parquet")


def outright_pattern(root: str) -> re.Pattern[str]:
    """Match Databento outright contracts only (no calendar spreads).

    CME month codes: FGHJKMNQUVXZ. Year is 1-2 digits.
    """
    return re.compile(rf"^{re.escape(root)}[FGHJKMNQUVXZ]\d{{1,2}}$")


def stream_zip_csvs(zip_path: Path) -> pd.DataFrame:
    """Concat every `*.ohlcv-1m.csv.zst` member."""
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
    """Multi-contract -> single row per minute. Max-volume outright wins.

    Output columns match the existing ES bars parquet schema:
      ts (UTC, tz-aware), open, high, low, close, volume, symbol.
    """
    df = df.copy()
    df["ts_event"] = pd.to_datetime(df["ts_event"], utc=True)
    df["volume"] = pd.to_numeric(df["volume"], errors="coerce").fillna(0).astype("int64")
    for col in ("open", "high", "low", "close"):
        df[col] = pd.to_numeric(df[col], errors="coerce").astype("float64")

    pat = outright_pattern(root)
    before, before_syms = len(df), df["symbol"].nunique()
    df = df.loc[df["symbol"].astype(str).str.match(pat)].copy()
    after, after_syms = len(df), df["symbol"].nunique()
    print(
        f"  filter to {root} outrights: {before:,} rows / {before_syms} symbols "
        f"-> {after:,} rows / {after_syms} symbols",
        flush=True,
    )
    if df.empty:
        sys.exit(f"After outright filter, no rows remain for root '{root}'.")

    # Pick max-volume contract per minute; sum total outright volume across contracts.
    df = df.sort_values(["ts_event", "volume", "symbol"], ascending=[True, False, True])
    most_active = df.drop_duplicates(subset=["ts_event"], keep="first").copy()
    total_vol = df.groupby("ts_event", as_index=False)["volume"].sum().rename(columns={"volume": "_total_vol"})
    most_active = most_active.merge(total_vol, on="ts_event", how="left")
    most_active["volume"] = most_active["_total_vol"]
    most_active = most_active.drop(columns=["_total_vol"])

    # Output schema: rename ts_event -> ts; keep only required columns; keep tz.
    out = most_active.rename(columns={"ts_event": "ts"})[
        ["ts", "open", "high", "low", "close", "volume", "symbol"]
    ]
    out["symbol"] = out["symbol"].astype(str)
    return out.sort_values("ts").reset_index(drop=True)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--zip", type=Path, required=True)
    ap.add_argument("--symbol", required=True, help="Symbol root (e.g. ES)")
    ap.add_argument("--target", type=Path, default=DEFAULT_TARGET,
                    help=f"Output parquet path (default: {DEFAULT_TARGET})")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    if not args.zip.exists():
        sys.exit(f"Zip not found: {args.zip}")

    print(f"Source zip: {args.zip}", flush=True)
    print(f"Symbol:     {args.symbol}", flush=True)
    print(f"Target:     {args.target}", flush=True)

    with zipfile.ZipFile(args.zip) as zf:
        if "metadata.json" in zf.namelist():
            q = json.loads(zf.read("metadata.json")).get("query", {})
            print(f"\nZip metadata: schema={q.get('schema')} stype_in={q.get('stype_in')} symbols={q.get('symbols')}", flush=True)

    print("\nReading monthly CSVs ...", flush=True)
    raw = stream_zip_csvs(args.zip)
    print(f"  total 1m rows: {len(raw):,}  unique contracts: {raw['symbol'].nunique()}", flush=True)

    print("\nAggregating to single time-series (max-volume outright per minute) ...", flush=True)
    single = aggregate_to_single_1m(raw, args.symbol)
    print(f"  unique 1m bars: {len(single):,}", flush=True)
    print(f"  date range: {single['ts'].min()} -> {single['ts'].max()}", flush=True)

    if args.target.exists():
        existing = pd.read_parquet(args.target)
        print(f"\nExisting target: {len(existing):,} rows  span {pd.to_datetime(existing['ts']).min()} -> {pd.to_datetime(existing['ts']).max()}", flush=True)
    else:
        print(f"\nNo existing target at {args.target} — will create.", flush=True)

    if args.dry_run:
        print("\n--dry-run: no write", flush=True)
        return 0

    if args.target.exists():
        backup = args.target.with_suffix(
            f".bak-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.parquet"
        )
        print(f"\nBacking up existing -> {backup}", flush=True)
        shutil.copy2(args.target, backup)

    tmp = args.target.with_suffix(".new.parquet")
    print(f"Writing -> {tmp}", flush=True)
    single.to_parquet(tmp, engine="pyarrow", index=False)
    tmp.replace(args.target)

    rt = pd.read_parquet(args.target)
    print(f"\nRound-trip read: {len(rt):,} rows", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
