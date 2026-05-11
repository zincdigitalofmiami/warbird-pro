#!/usr/bin/env python3
"""Refresh the local cross-asset 1h parquet from Databento (GLBX.MDP3, continuous).

Source of truth for build_core_dataset.merge_cross_assets. The parquet path is
ingested manually (not by an existing repo script), so this refresher takes
explicit responsibility for safe, atomic, backed-up updates.

Symbols refreshed (CME 179 subscription):
  NQ.c.0   Mag7 / tech beta proxy
  ZN.c.0   10Y rate-pressure proxy (ZN price-derived, not actual 10Y yield)
  HG.c.0   Copper / industrial-growth proxy
  6E.c.0   EUR/USD futures — inverse USD-pressure proxy

Safety:
  - Existing parquet is backed up to <path>.bak-<timestamp> before write.
  - New data is fetched into a temp DataFrame, schema-aligned, and only
    merged in memory; existing rows for the refreshed symbols and any
    ts_event >= --start are replaced.
  - Final parquet is written to <path>.new and atomically renamed.
  - If anything fails, the backup is preserved and the old parquet stays in place.

Usage:
  DATABENTO_API_KEY=db-... python3 scripts/refresh-cross-asset-parquet.py \
      --start 2025-12-15 --end 2026-05-11
  (or pass --api-key inline; defaults to env DATABENTO_API_KEY)
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

# Default refresh targets: 4 cross-asset symbols on GLBX.MDP3.
# Symbol-codes in the parquet drop the .c.0 suffix (matching existing schema).
REFRESH_SYMBOLS = [
    ("NQ.c.0", "NQ"),
    ("ZN.c.0", "ZN"),
    ("HG.c.0", "HG"),
    ("6E.c.0", "6E"),
]

PARQUET_PATH = Path(
    "/Volumes/Satechi Hub/Historical Data/Databento/raw/databento_futures_ohlcv_1h.parquet"
)


def fetch_symbol(client, symbol_full: str, symbol_short: str, start: str, end: str) -> pd.DataFrame:
    """Pull ohlcv-1h continuous bars for one symbol, normalize to parquet schema."""
    print(f"  fetching {symbol_full} ({symbol_short}) {start} -> {end} ...", flush=True)
    data = client.timeseries.get_range(
        dataset="GLBX.MDP3",
        schema="ohlcv-1h",
        symbols=symbol_full,
        stype_in="continuous",
        start=start,
        end=end,
    )
    df = data.to_df()
    if df.empty:
        print(f"    {symbol_full}: 0 rows", flush=True)
        return df
    # Databento DataFrame typically has columns: ts_event (as index or column),
    # open, high, low, close, volume, plus identifiers we don't need.
    if df.index.name == "ts_event" or "ts_event" not in df.columns:
        df = df.reset_index()
    keep = ["ts_event", "open", "high", "low", "close", "volume"]
    df = df[[c for c in keep if c in df.columns]].copy()
    df["symbol"] = symbol_short
    df["ts_event"] = pd.to_datetime(df["ts_event"], utc=True).dt.tz_convert(None)
    df["open_interest"] = 0  # ohlcv schema does not include OI
    df["source"] = "databento_1h_refresh_2026_05"
    df["ingested_at"] = pd.Timestamp.utcnow().tz_localize(None)
    # Match parquet column order: symbol, ts_event, open, high, low, close, volume, open_interest, source, ingested_at
    df = df[
        [
            "symbol",
            "ts_event",
            "open",
            "high",
            "low",
            "close",
            "volume",
            "open_interest",
            "source",
            "ingested_at",
        ]
    ]
    print(f"    {symbol_full}: {len(df)} rows  span {df['ts_event'].min()} -> {df['ts_event'].max()}", flush=True)
    return df


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--start", default="2025-12-15", help="UTC start date (inclusive)")
    ap.add_argument("--end", default=None, help="UTC end date (exclusive); default = today UTC")
    ap.add_argument("--api-key", default=os.environ.get("DATABENTO_API_KEY"))
    ap.add_argument("--parquet", type=Path, default=PARQUET_PATH)
    ap.add_argument("--dry-run", action="store_true", help="fetch but do not write")
    args = ap.parse_args()

    if not args.api_key:
        sys.exit("DATABENTO_API_KEY missing (env or --api-key)")

    end = args.end or datetime.now(timezone.utc).date().isoformat()
    print(f"Refresh window: {args.start} -> {end}", flush=True)
    print(f"Target parquet: {args.parquet}", flush=True)

    import databento as db

    client = db.Historical(args.api_key)

    new_frames: list[pd.DataFrame] = []
    for symbol_full, symbol_short in REFRESH_SYMBOLS:
        df = fetch_symbol(client, symbol_full, symbol_short, args.start, end)
        if not df.empty:
            new_frames.append(df)
    if not new_frames:
        sys.exit("No new rows fetched; aborting (refusing to clobber existing parquet)")

    new_df = pd.concat(new_frames, ignore_index=True)
    print(f"\nFetched total: {len(new_df)} rows across {new_df['symbol'].nunique()} symbols", flush=True)

    # --- Read existing parquet ---
    if not args.parquet.exists():
        sys.exit(f"Existing parquet not found: {args.parquet}")
    existing = pd.read_parquet(args.parquet)
    print(f"Existing parquet: {len(existing)} rows across {existing['symbol'].nunique()} symbols", flush=True)

    # --- Merge: drop existing rows for refresh symbols where ts_event >= --start ---
    refresh_symbols_short = [s for _, s in REFRESH_SYMBOLS]
    cutoff = pd.Timestamp(args.start).tz_localize(None)
    mask_drop = (
        existing["symbol"].isin(refresh_symbols_short)
        & (pd.to_datetime(existing["ts_event"]).dt.tz_localize(None) >= cutoff)
    )
    dropped = int(mask_drop.sum())
    kept = existing.loc[~mask_drop].copy()
    print(f"  Dropping {dropped} overlapping rows from refresh symbols >= {cutoff.date()}", flush=True)

    # Normalize ALL column dtypes on both sides to identical numpy dtypes.
    # The parquet stores DECIMAL(10,4) for OHLC and TIMESTAMP for ts_event/
    # ingested_at; pandas may load these as object/Decimal or datetime64[ns]
    # depending on engine, and any mismatch causes pd.concat to fail with a
    # cryptic shape error. Cast everything explicitly here.
    def _normalize(df: pd.DataFrame) -> pd.DataFrame:
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

    kept = _normalize(kept)
    new_df = _normalize(new_df)

    merged = (
        pd.concat([kept, new_df], ignore_index=True)
        .sort_values(["symbol", "ts_event"])
        .reset_index(drop=True)
    )
    print(f"\nMerged total: {len(merged)} rows ({len(kept)} kept + {len(new_df)} new)", flush=True)

    # Per-symbol post-merge summary
    print("\nPost-merge per-refresh-symbol summary:")
    for sym in refresh_symbols_short:
        s = merged.loc[merged["symbol"] == sym, "ts_event"]
        print(f"  {sym}: {len(s)} rows  first={s.min()}  last={s.max()}")

    if args.dry_run:
        print("\n--dry-run: not writing parquet", flush=True)
        return 0

    # --- Write merged parquet atomically with backup ---
    backup = args.parquet.with_suffix(
        f".bak-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.parquet"
    )
    print(f"\nBacking up existing parquet -> {backup}", flush=True)
    shutil.copy2(args.parquet, backup)

    tmp = args.parquet.with_suffix(".new.parquet")
    print(f"Writing merged parquet -> {tmp}", flush=True)
    merged.to_parquet(tmp, engine="pyarrow", index=False)

    print(f"Atomically renaming {tmp.name} -> {args.parquet.name}", flush=True)
    tmp.replace(args.parquet)

    # Round-trip read sanity
    rt = pd.read_parquet(args.parquet)
    print(f"\nRound-trip read: {len(rt)} rows; symbols={sorted(rt['symbol'].unique())[:8]}...", flush=True)
    print(f"Backup preserved at: {backup}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
