#!/usr/bin/env python3
"""
Convert raw Databento .dbn.zst files into clean parquet files.
Output: /Volumes/Satechi Hub/warbird-pro/data/
"""

import os
import re
import sys
import zipfile
import traceback
from pathlib import Path
from datetime import datetime, timezone

import databento as db
import pandas as pd

# ── Paths ──────────────────────────────────────────────────────────────────────
DATA_DIR = Path("/Volumes/Satechi Hub/warbird-pro/data")
MES_1M_DIR = DATA_DIR / "MES 1m GLBX-20260405-75PD3JMW9Q"
MES_1H_DIR = DATA_DIR / "MES 1h GLBX-20260405-AD9XQKUFAA"
INTERMARKET_ZIP = DATA_DIR / "Intermarket 1h data GLBX-20260405-L6EHD7H3NJ.zip"
INTERMARKET_EXTRACT_DIR = DATA_DIR / "Intermarket 1h data GLBX-20260405-L6EHD7H3NJ"

# ── Month-letter → month-number ────────────────────────────────────────────────
MONTH_LETTER = {
    'F': 1, 'G': 2, 'H': 3, 'J': 4, 'K': 5, 'M': 6,
    'N': 7, 'Q': 8, 'U': 9, 'V': 10, 'X': 11, 'Z': 12
}

PRICE_SCALE = 1e9  # Databento fixed-point prices


def contract_expiry_sort_key(symbol_str: str) -> tuple:
    """
    Return (year, month) sort key for a futures contract symbol like NQH0, 6EU5, RTYZ3.
    Assumes 2-digit year offset from 2020 (0=2020 … 9=2029).
    """
    # Match trailing letter+digit: e.g. H0, U5, Z3
    m = re.search(r'([A-Z])([0-9])$', symbol_str)
    if not m:
        return (9999, 99)
    month = MONTH_LETTER.get(m.group(1), 99)
    year = 2020 + int(m.group(2))
    return (year, month)


def contract_expiry_date(symbol_str: str) -> pd.Timestamp:
    """Return approximate expiry as Timestamp (3rd Friday of expiry month)."""
    year, month = contract_expiry_sort_key(symbol_str)
    if year == 9999:
        return pd.Timestamp.max.tz_localize('UTC')
    # 3rd Friday approximation: day 15 + enough to reach Friday
    import calendar
    # Find the first day of month, walk to 3rd Friday
    first_day = datetime(year, month, 1, tzinfo=timezone.utc)
    # weekday(): Monday=0, Friday=4
    day = first_day
    fridays = 0
    while fridays < 3:
        if day.weekday() == 4:  # Friday
            fridays += 1
            if fridays == 3:
                break
        day = datetime(year, month, day.day + 1, tzinfo=timezone.utc)
    return pd.Timestamp(day)


def read_dbn_file(path: Path, first_file: bool = False) -> pd.DataFrame:
    """Read a single .dbn.zst file and return a normalised raw DataFrame."""
    store = db.DBNStore.from_file(str(path))
    df = store.to_df()

    if first_file:
        print(f"    [inspect] columns: {list(df.columns)}")
        print(f"    [inspect] head(2):\n{df.head(2).to_string()}")
        if "symbol" in df.columns:
            print(f"    [inspect] symbol.unique(): {df['symbol'].unique()}")

    # ── Timestamp ──────────────────────────────────────────────────────────────
    if df.index.name in ("ts_event", "ts"):
        df = df.reset_index()

    ts_candidates = ["ts_event", "ts_recv", "ts"]
    ts_col = next((c for c in ts_candidates if c in df.columns), None)
    if ts_col is None:
        raise ValueError(f"No timestamp column found. Columns: {list(df.columns)}")

    df["ts"] = pd.to_datetime(df[ts_col], utc=True)

    # ── Prices ──────────────────────────────────────────────────────────────────
    for col in ["open", "high", "low", "close"]:
        if col in df.columns:
            sample = df[col].dropna()
            if len(sample) > 0 and float(sample.iloc[0]) > 1_000_000:
                df[col] = df[col].astype("float64") / PRICE_SCALE
            else:
                df[col] = df[col].astype("float64")

    # ── Volume ──────────────────────────────────────────────────────────────────
    if "volume" in df.columns:
        df["volume"] = df["volume"].astype("int64")
    elif "size" in df.columns:
        df["volume"] = df["size"].astype("int64")
    else:
        df["volume"] = 0

    return df


def load_mes_directory(directory: Path) -> pd.DataFrame:
    """Load all MES .dbn.zst files, force symbol='MES'."""
    files = sorted(directory.glob("*.dbn.zst"))
    if not files:
        raise FileNotFoundError(f"No .dbn.zst files found in {directory}")

    print(f"  Found {len(files)} files in {directory.name}")
    frames = []
    first = True

    for f in files:
        try:
            raw = read_dbn_file(f, first_file=first)
            first = False
            raw["symbol"] = "MES"
            out = raw[["ts", "open", "high", "low", "close", "volume", "symbol"]].copy()
            out["volume"] = out["volume"].astype("int64")
            frames.append(out)
            print(f"    {f.name}: {len(out):,} rows")
        except Exception as e:
            print(f"    ERROR reading {f.name}: {e}")
            traceback.print_exc()

    combined = pd.concat(frames, ignore_index=True)
    combined = combined.sort_values("ts").reset_index(drop=True)
    return combined


def build_continuous_from_singles(base: str, single_files: list) -> pd.DataFrame:
    """
    Build a continuous front-month series for `base` from individual contract files.

    Strategy:
    - Load all single contracts
    - Tag each row with its contract expiry date
    - For each timestamp, keep only the contract with the nearest (soonest) expiry
      that is STILL active (i.e., expiry >= bar timestamp)
    - This reconstructs the .c.0 front-month continuous series
    """
    if not single_files:
        raise ValueError(f"No single contract files for {base}")

    print(f"  Building continuous {base}: loading {len(single_files)} contracts ...")
    frames = []
    first = True

    for f in single_files:
        try:
            raw = read_dbn_file(f, first_file=first)
            first = False
            # Extract contract symbol from filename
            stem = f.name.replace(".dbn.zst", "")
            contract_sym = stem.rsplit(".", 1)[-1]  # e.g. NQH0
            expiry = contract_expiry_date(contract_sym)
            raw["_contract"] = contract_sym
            raw["_expiry"] = expiry
            raw["symbol"] = base
            out = raw[["ts", "open", "high", "low", "close", "volume", "symbol", "_contract", "_expiry"]].copy()
            out["volume"] = out["volume"].astype("int64")
            frames.append(out)
        except Exception as e:
            print(f"    ERROR reading {f.name}: {e}")
            traceback.print_exc()

    if not frames:
        raise ValueError(f"No frames loaded for {base}")

    all_bars = pd.concat(frames, ignore_index=True)

    # Filter: only keep bars where ts <= expiry (don't use expired contracts)
    all_bars = all_bars[all_bars["ts"] <= all_bars["_expiry"]].copy()

    # Sort by ts, then by expiry (nearest-expiry first)
    all_bars = all_bars.sort_values(["ts", "_expiry"]).reset_index(drop=True)

    # Keep only the first (nearest-expiry) bar per timestamp
    continuous = all_bars.drop_duplicates(subset=["ts"], keep="first")

    # Drop helper columns
    continuous = continuous[["ts", "open", "high", "low", "close", "volume", "symbol"]].copy()
    continuous = continuous.sort_values("ts").reset_index(drop=True)
    print(f"  {base}: {len(continuous):,} continuous bars from {continuous['ts'].min()} to {continuous['ts'].max()}")
    return continuous


def resample_ohlcv(df: pd.DataFrame, freq: str, closed: str = "left",
                   label: str = "left") -> pd.DataFrame:
    """Resample OHLCV bars to a coarser frequency, grouped by symbol."""
    frames = []
    for sym, grp in df.groupby("symbol"):
        r = (
            grp.set_index("ts")
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
        r["symbol"] = sym
        frames.append(r)

    result = pd.concat(frames, ignore_index=True)
    result = result[["ts", "open", "high", "low", "close", "volume", "symbol"]]
    result["volume"] = result["volume"].astype("int64")
    result = result.sort_values(["symbol", "ts"]).reset_index(drop=True)
    return result


def write_parquet(df: pd.DataFrame, path: Path) -> None:
    """Write DataFrame to parquet and print stats."""
    df.to_parquet(str(path), index=False, engine="pyarrow")
    rows = len(df)
    min_ts = df["ts"].min()
    max_ts = df["ts"].max()
    syms = sorted(df["symbol"].unique().tolist())
    print(f"  WROTE {path.name}: {rows:,} rows | {min_ts} → {max_ts} | symbols: {syms}")


def extract_intermarket_zip() -> Path:
    """Extract the intermarket zip if not already extracted."""
    existing = list(INTERMARKET_EXTRACT_DIR.glob("*.dbn.zst"))
    if INTERMARKET_EXTRACT_DIR.exists() and existing:
        print(f"  Already extracted: {len(existing)} files in {INTERMARKET_EXTRACT_DIR.name}")
        return INTERMARKET_EXTRACT_DIR

    print(f"  Extracting {INTERMARKET_ZIP.name} ...")
    INTERMARKET_EXTRACT_DIR.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(str(INTERMARKET_ZIP), "r") as zf:
        zf.extractall(str(INTERMARKET_EXTRACT_DIR))

    extracted = list(INTERMARKET_EXTRACT_DIR.glob("**/*.dbn.zst"))
    print(f"  Extracted {len(extracted)} .dbn.zst files")
    return INTERMARKET_EXTRACT_DIR


# ── Cross-asset symbol patterns (single contracts only, no dashes) ─────────────
INTERMARKET_PATTERNS = {
    "6E":  r"6E[A-Z][0-9]",
    "6J":  r"6J[A-Z][0-9]",
    "CL":  r"CL[A-Z][0-9]",
    "HG":  r"HG[A-Z][0-9]",
    "NQ":  r"NQ[A-Z][0-9]",
    "RTY": r"RTY[A-Z][0-9]",
}


def get_single_contract_files(base: str, directory: Path) -> list:
    pattern = INTERMARKET_PATTERNS[base]
    return sorted([
        f for f in directory.glob("*.dbn.zst")
        if re.search(r"\." + pattern + r"\.dbn\.zst$", f.name)
    ])


# ══════════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════════

def main():
    print("=" * 70)
    print("Warbird Parquet Converter — DBN → Parquet")
    print("=" * 70)

    results = {}

    # ── 1. MES 1m ────────────────────────────────────────────────────────────
    print("\n[1/6] Loading MES 1m ...")
    df_mes_1m = None
    try:
        df_mes_1m = load_mes_directory(MES_1M_DIR)
        out = DATA_DIR / "mes_1m.parquet"
        write_parquet(df_mes_1m, out)
        results["mes_1m.parquet"] = (len(df_mes_1m), df_mes_1m["ts"].min(), df_mes_1m["ts"].max())
    except Exception as e:
        print(f"  FAILED mes_1m: {e}")
        traceback.print_exc()

    # ── 2. MES 15m (resample from 1m) ────────────────────────────────────────
    print("\n[2/6] Resampling MES 15m from 1m ...")
    if df_mes_1m is not None:
        try:
            df_mes_15m = resample_ohlcv(df_mes_1m, "15min")
            out = DATA_DIR / "mes_15m.parquet"
            write_parquet(df_mes_15m, out)
            results["mes_15m.parquet"] = (len(df_mes_15m), df_mes_15m["ts"].min(), df_mes_15m["ts"].max())
        except Exception as e:
            print(f"  FAILED mes_15m: {e}")
            traceback.print_exc()
    else:
        print("  SKIPPED (no 1m data)")

    # ── 3. MES 1h ────────────────────────────────────────────────────────────
    print("\n[3/6] Loading MES 1h ...")
    df_mes_1h = None
    try:
        df_mes_1h = load_mes_directory(MES_1H_DIR)
        out = DATA_DIR / "mes_1h.parquet"
        write_parquet(df_mes_1h, out)
        results["mes_1h.parquet"] = (len(df_mes_1h), df_mes_1h["ts"].min(), df_mes_1h["ts"].max())
    except Exception as e:
        print(f"  FAILED mes_1h: {e}")
        traceback.print_exc()

    # ── 4. MES 4h (resample from 1h) ─────────────────────────────────────────
    print("\n[4/6] Resampling MES 4h from 1h ...")
    if df_mes_1h is not None:
        try:
            df_mes_4h = resample_ohlcv(df_mes_1h, "4h")
            out = DATA_DIR / "mes_4h.parquet"
            write_parquet(df_mes_4h, out)
            results["mes_4h.parquet"] = (len(df_mes_4h), df_mes_4h["ts"].min(), df_mes_4h["ts"].max())
        except Exception as e:
            print(f"  FAILED mes_4h: {e}")
            traceback.print_exc()
    else:
        print("  SKIPPED (no 1h data)")

    # ── 5. MES 1d (resample from 1h) ─────────────────────────────────────────
    print("\n[5/6] Resampling MES 1d from 1h ...")
    if df_mes_1h is not None:
        try:
            df_mes_1d = resample_ohlcv(df_mes_1h, "1D")
            out = DATA_DIR / "mes_1d.parquet"
            write_parquet(df_mes_1d, out)
            results["mes_1d.parquet"] = (len(df_mes_1d), df_mes_1d["ts"].min(), df_mes_1d["ts"].max())
        except Exception as e:
            print(f"  FAILED mes_1d: {e}")
            traceback.print_exc()
    else:
        print("  SKIPPED (no 1h data)")

    # ── 6. Cross-asset 1h ────────────────────────────────────────────────────
    print("\n[6/6] Building cross-asset 1h (intermarket continuous) ...")
    try:
        intermarket_dir = extract_intermarket_zip()
        cross_frames = []

        for base in ["NQ", "RTY", "CL", "HG", "6E", "6J"]:
            print(f"\n  Processing {base} ...")
            try:
                singles = get_single_contract_files(base, intermarket_dir)
                print(f"  {base}: {len(singles)} single contract files")
                df_sym = build_continuous_from_singles(base, singles)
                cross_frames.append(df_sym)
            except Exception as e:
                print(f"  FAILED {base}: {e}")
                traceback.print_exc()

        if not cross_frames:
            raise ValueError("No cross-asset frames built")

        df_cross = pd.concat(cross_frames, ignore_index=True)
        df_cross = df_cross.sort_values(["symbol", "ts"]).reset_index(drop=True)

        print(f"\n  Symbol counts:\n{df_cross['symbol'].value_counts().to_string()}")

        out = DATA_DIR / "cross_asset_1h.parquet"
        write_parquet(df_cross, out)
        results["cross_asset_1h.parquet"] = (len(df_cross), df_cross["ts"].min(), df_cross["ts"].max())
    except Exception as e:
        print(f"  FAILED cross_asset_1h: {e}")
        traceback.print_exc()

    # ── Verification table ────────────────────────────────────────────────────
    EXPECTED_MIN = {
        "mes_1m.parquet":        2_000_000,
        "mes_15m.parquet":         140_000,
        "mes_1h.parquet":           35_000,
        "mes_4h.parquet":            9_000,
        "mes_1d.parquet":            1_500,
        "cross_asset_1h.parquet":  200_000,
    }

    print("\n" + "=" * 96)
    print("VERIFICATION TABLE")
    print("=" * 96)
    print(f"{'FILE':<28} {'ROWS':>12}  {'MIN_TS':<30} {'MAX_TS':<30}")
    print("-" * 96)

    for fname, expected_min in EXPECTED_MIN.items():
        if fname in results:
            rows, min_ts, max_ts = results[fname]
            warn = "  WARNING: LOW ROW COUNT" if rows < expected_min else ""
            print(f"{fname:<28} {rows:>12,}  {str(min_ts):<30} {str(max_ts):<30}{warn}")
        else:
            print(f"{fname:<28} {'FAILED':>12}  {'—':<30} {'—':<30}  FAILED")

    print("=" * 96)
    print("Done.")


if __name__ == "__main__":
    main()
