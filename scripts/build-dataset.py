#!/usr/bin/env python3
import sys
print("=" * 60)
print("DEPRECATED: This script is superseded by scripts/warbird/build-warbird-dataset.ts")
print("and will be replaced by scripts/ag/build-fib-dataset.py in Phase 4.")
print("Do NOT use for new work.")
print("=" * 60)
sys.exit(1)

"""
Build unified MES training dataset from Supabase.

Pulls all tables (MES OHLCV, cross-asset, FRED, news, GPR, Trump Effect),
aligns to 1H bars, derives targets (price, MAE, MFE), and exports CSV.

Usage:
    python scripts/build-dataset.py --output datasets/mes_unified_1h.csv
    python scripts/build-dataset.py --output datasets/mes_unified_1h.csv --days 365
"""

import argparse
import math
import os
import sys
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd
from supabase import create_client

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_SERVICE_ROLE_KEY"]

HORIZONS = {
    "1h": 1,
    "4h": 4,
    "1d": 24,
    "1w": 120,
}

# FRED series → feature column name mapping
FRED_TABLES = {
    "econ_rates_1d": "rates",
    "econ_yields_1d": "yields",
    "econ_vol_1d": "vol",
    "econ_inflation_1d": "inflation",
    "econ_fx_1d": "fx",
    "econ_labor_1d": "labor",
    "econ_activity_1d": "activity",
    "econ_money_1d": "money",
    "econ_commodities_1d": "commodities",
    "econ_indexes_1d": "indexes",
}

# Cross-asset symbols to include as features
CROSS_ASSET_SYMBOLS = [
    "NQ.c.0", "YM.c.0", "RTY.c.0",  # equity indexes
    "ZN.c.0", "ZB.c.0", "ZF.c.0",   # treasuries
    "CL.c.0", "GC.c.0", "SI.c.0",   # commodities
    "6E.c.0", "6J.c.0",              # FX
]


def fetch_all(supabase, table: str, select: str = "*", order: str = "ts",
              filters: dict | None = None, limit: int = 100_000) -> pd.DataFrame:
    """Fetch all rows from a Supabase table with pagination."""
    all_rows = []
    offset = 0
    page_size = 1000

    while offset < limit:
        query = supabase.table(table).select(select).order(order).range(offset, offset + page_size - 1)
        if filters:
            for k, v in filters.items():
                query = query.eq(k, v)
        result = query.execute()
        rows = result.data
        if not rows:
            break
        all_rows.extend(rows)
        offset += len(rows)
        if len(rows) < page_size:
            break

    return pd.DataFrame(all_rows) if all_rows else pd.DataFrame()


def build_mes_1h(supabase) -> pd.DataFrame:
    """Build MES 1H bars from 15m data."""
    print("  Fetching MES 15m data...", end=" ", flush=True)
    df = fetch_all(supabase, "mes_15m")
    if df.empty:
        print("NO DATA")
        return pd.DataFrame()

    df["ts"] = pd.to_datetime(df["ts"], utc=True)
    for col in ["open", "high", "low", "close", "volume"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    df = df.sort_values("ts").reset_index(drop=True)
    print(f"{len(df)} bars")

    # Aggregate to 1H
    df["hour"] = df["ts"].dt.floor("h")
    agg = df.groupby("hour").agg(
        open=("open", "first"),
        high=("high", "max"),
        low=("low", "min"),
        close=("close", "last"),
        volume=("volume", "sum"),
    ).reset_index().rename(columns={"hour": "ts"})

    # Derived features
    agg["range"] = agg["high"] - agg["low"]
    agg["body"] = abs(agg["close"] - agg["open"])
    agg["body_pct"] = agg["body"] / agg["range"].replace(0, np.nan)
    agg["upper_wick"] = agg["high"] - agg[["open", "close"]].max(axis=1)
    agg["lower_wick"] = agg[["open", "close"]].min(axis=1) - agg["low"]
    agg["returns_1h"] = agg["close"].pct_change()
    agg["returns_4h"] = agg["close"].pct_change(4)
    agg["returns_1d"] = agg["close"].pct_change(24)

    # Rolling features
    for w in [5, 10, 20, 50]:
        agg[f"sma_{w}"] = agg["close"].rolling(w).mean()
        agg[f"vol_sma_{w}"] = agg["volume"].rolling(w).mean()
        agg[f"range_sma_{w}"] = agg["range"].rolling(w).mean()

    # Volatility
    agg["realized_vol_20"] = agg["returns_1h"].rolling(20).std() * math.sqrt(252 * 24)
    agg["realized_vol_50"] = agg["returns_1h"].rolling(50).std() * math.sqrt(252 * 24)

    # Price vs SMA
    for w in [20, 50]:
        sma_col = f"sma_{w}"
        agg[f"price_vs_sma_{w}"] = (agg["close"] - agg[sma_col]) / agg[sma_col].replace(0, np.nan)

    # Volume ratio
    agg["vol_ratio_5_20"] = agg["vol_sma_5"] / agg["vol_sma_20"].replace(0, np.nan)

    print(f"  Built {len(agg)} 1H bars with {len(agg.columns)} features")
    return agg


def add_cross_asset_features(df: pd.DataFrame, supabase) -> pd.DataFrame:
    """Add cross-asset price features aligned to 1H bars."""
    print("  Fetching cross-asset data...", end=" ", flush=True)
    ca = fetch_all(supabase, "cross_asset_1h")
    if ca.empty:
        print("NO DATA")
        return df

    ca["ts"] = pd.to_datetime(ca["ts"], utc=True)
    ca["ts_hour"] = ca["ts"].dt.floor("h")

    count = 0
    for sym in CROSS_ASSET_SYMBOLS:
        sym_data = ca[ca["symbol_code"] == sym].copy()
        if sym_data.empty:
            continue
        prefix = sym.replace(".c.0", "").lower()
        for col in ["close", "volume"]:
            sym_data[col] = pd.to_numeric(sym_data[col], errors="coerce")

        sym_hourly = sym_data.groupby("ts_hour").agg(
            close=("close", "last"),
            volume=("volume", "sum"),
        ).reset_index().rename(columns={"ts_hour": "ts"})

        sym_hourly[f"ca_{prefix}_close"] = sym_hourly["close"]
        sym_hourly[f"ca_{prefix}_ret_1h"] = sym_hourly["close"].pct_change()
        sym_hourly[f"ca_{prefix}_ret_4h"] = sym_hourly["close"].pct_change(4)
        sym_hourly[f"ca_{prefix}_vol"] = sym_hourly["volume"]

        merge_cols = ["ts"] + [c for c in sym_hourly.columns if c.startswith("ca_")]
        df = df.merge(sym_hourly[merge_cols], on="ts", how="left")
        count += 1

    print(f"{count} symbols merged")
    return df


def add_fred_features(df: pd.DataFrame, supabase) -> pd.DataFrame:
    """Add FRED economic features, forward-filled to 1H."""
    print("  Fetching FRED data...", end=" ", flush=True)
    total = 0

    for table, prefix in FRED_TABLES.items():
        econ = fetch_all(supabase, table)
        if econ.empty:
            continue

        econ["ts"] = pd.to_datetime(econ["ts"], utc=True)
        econ["value"] = pd.to_numeric(econ["value"], errors="coerce")

        if "series_id" in econ.columns:
            for sid in econ["series_id"].unique():
                series = econ[econ["series_id"] == sid][["ts", "value"]].copy()
                series = series.sort_values("ts").drop_duplicates("ts", keep="last")
                col_name = f"fred_{prefix}_{sid.lower()}"
                series = series.rename(columns={"value": col_name})

                # Align to hourly: forward-fill daily values
                series["ts"] = series["ts"].dt.floor("h")
                df = df.merge(series[["ts", col_name]], on="ts", how="left")
                df[col_name] = df[col_name].ffill()
                total += 1
        else:
            col_name = f"fred_{prefix}"
            econ = econ[["ts", "value"]].sort_values("ts").drop_duplicates("ts", keep="last")
            econ = econ.rename(columns={"value": col_name})
            econ["ts"] = econ["ts"].dt.floor("h")
            df = df.merge(econ[["ts", col_name]], on="ts", how="left")
            df[col_name] = df[col_name].ffill()
            total += 1

    print(f"{total} series merged")
    return df


def add_news_features(df: pd.DataFrame, supabase) -> pd.DataFrame:
    """Add news signals, GPR, and Trump Effect."""
    print("  Fetching news/GPR/Trump data...", end=" ", flush=True)
    count = 0

    # GPR index
    gpr = fetch_all(supabase, "geopolitical_risk_1d")
    if not gpr.empty:
        gpr["ts"] = pd.to_datetime(gpr["ts"], utc=True).dt.floor("h")
        gpr["gpr_index"] = pd.to_numeric(gpr.get("gpr_current", gpr.get("value", 0)), errors="coerce")
        df = df.merge(gpr[["ts", "gpr_index"]].drop_duplicates("ts", keep="last"), on="ts", how="left")
        df["gpr_index"] = df["gpr_index"].ffill()
        count += 1

    # Trump Effect
    trump = fetch_all(supabase, "trump_effect_1d")
    if not trump.empty:
        trump["ts"] = pd.to_datetime(trump["ts"], utc=True).dt.floor("h")
        for col in ["executive_orders", "presidential_memos", "epu_index"]:
            if col in trump.columns:
                trump[f"trump_{col}"] = pd.to_numeric(trump[col], errors="coerce")
                df = df.merge(
                    trump[["ts", f"trump_{col}"]].drop_duplicates("ts", keep="last"),
                    on="ts", how="left"
                )
                df[f"trump_{col}"] = df[f"trump_{col}"].ffill()
                count += 1

    # News signals (count-based features)
    news = fetch_all(supabase, "news_signals")
    if not news.empty:
        news["ts"] = pd.to_datetime(news["ts"], utc=True).dt.floor("h")
        if "direction" in news.columns:
            news_agg = news.groupby("ts").agg(
                news_up=("direction", lambda x: (x == "up").sum()),
                news_down=("direction", lambda x: (x == "down").sum()),
                news_total=("direction", "count"),
            ).reset_index()
            df = df.merge(news_agg, on="ts", how="left")
            for c in ["news_up", "news_down", "news_total"]:
                df[c] = df[c].fillna(0)
            count += 1

    print(f"{count} features added")
    return df


def derive_targets(df: pd.DataFrame) -> pd.DataFrame:
    """Derive price, MAE, MFE targets for all horizons."""
    close = df["close"].to_numpy(dtype=float)
    n = len(close)

    for h_name, h_bars in HORIZONS.items():
        target_price = np.full(n, np.nan)
        mae = np.full(n, np.nan)
        mfe = np.full(n, np.nan)

        limit = n - h_bars
        for i in range(limit):
            c0 = close[i]
            if not np.isfinite(c0) or c0 == 0:
                continue
            future = close[i + 1 : i + h_bars + 1]
            if future.size == 0 or not np.all(np.isfinite(future)):
                continue

            target_price[i] = close[i + h_bars]
            mae[i] = c0 - float(np.min(future))
            mfe[i] = float(np.max(future)) - c0

        df[f"target_price_{h_name}"] = target_price
        df[f"target_mae_{h_name}"] = mae
        df[f"target_mfe_{h_name}"] = mfe

    return df


def main():
    parser = argparse.ArgumentParser(description="Build MES training dataset")
    parser.add_argument("--output", type=str, default="datasets/mes_unified_1h.csv")
    parser.add_argument("--days", type=int, default=365, help="Days of history (default: 365)")
    args = parser.parse_args()

    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

    print("Building MES unified 1H dataset")
    print("=" * 50)

    # 1. MES 1H bars (base)
    df = build_mes_1h(supabase)
    if df.empty:
        print("ERROR: No MES data. Run backfill.py first.")
        sys.exit(1)

    # 2. Cross-asset features
    df = add_cross_asset_features(df, supabase)

    # 3. FRED economic features
    df = add_fred_features(df, supabase)

    # 4. News/GPR/Trump features
    df = add_news_features(df, supabase)

    # 5. Derive targets
    print("  Deriving targets...", end=" ", flush=True)
    df = derive_targets(df)
    target_cols = [c for c in df.columns if c.startswith("target_")]
    print(f"{len(target_cols)} target columns")

    # 6. Add timestamp column
    df["timestamp"] = df["ts"].dt.strftime("%Y-%m-%d %H:%M:%S")

    # 7. Drop rows with no target (tail of dataset)
    min_horizon = max(HORIZONS.values())
    df = df.iloc[:-min_horizon] if len(df) > min_horizon else df

    # 8. Report
    feature_cols = [c for c in df.columns if c not in ["ts", "timestamp"] + target_cols]
    print(f"\nDataset summary:")
    print(f"  Rows: {len(df):,}")
    print(f"  Features: {len(feature_cols)}")
    print(f"  Targets: {len(target_cols)}")
    print(f"  Date range: {df['ts'].min()} → {df['ts'].max()}")
    print(f"  Missing %: {df[feature_cols].isna().mean().mean():.1%}")

    # 9. Save
    os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)
    df.to_csv(args.output, index=False)
    print(f"\n  Saved to {args.output} ({os.path.getsize(args.output) / 1024 / 1024:.1f} MB)")


if __name__ == "__main__":
    main()
