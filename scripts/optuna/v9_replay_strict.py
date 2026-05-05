#!/usr/bin/env python3
"""Strict-gated V9 replay: re-emit triggers with Pine's intended gates ON.

Wraps scripts/optuna/v9_replay.py by toggling USE_PATTERN_CONFIRM and
USE_MA_GATE to True before invoking replay(). Produces a smaller, higher-quality
candidate set that better matches what live Pine emits.
"""
from __future__ import annotations
import sys
from pathlib import Path
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1].parent))

from scripts.optuna import v9_replay as base


def main(argv: list[str]) -> int:
    parquet_path = Path(argv[1]) if len(argv) > 1 else Path("data/mes_5m.parquet")
    out_path = Path(argv[2]) if len(argv) > 2 else Path(
        "scripts/optuna/workspaces/warbird_pro/exports/databento_mes_5m_2020-2026_strict.csv"
    )
    base.USE_PATTERN_CONFIRM = True
    base.USE_MA_GATE = True
    base.USE_LIQ_SWEEP = False
    base.USE_ML_FILTER = False

    print(f"loading {parquet_path}", flush=True)
    df = pd.read_parquet(parquet_path)
    print(f"  rows={len(df):,}", flush=True)
    if "symbol" in df.columns:
        df = df[df["symbol"].astype(str).str.startswith("MES")].copy()
        df["symbol"] = "MES1!"

    n_before = len(df)
    floor_mask = (df["open"] < 500) | (df["high"] < 500) | (df["low"] < 500) | (df["close"] < 500)
    df = df.loc[~floor_mask].reset_index(drop=True)
    prev_close = df["close"].shift(1)
    dev_mask = (df["low"] < 0.5 * prev_close) | (df["close"] < 0.5 * prev_close)
    df = df.loc[~dev_mask].reset_index(drop=True)
    print(f"  dropped {n_before - len(df):,} sentinel rows (kept {len(df):,})", flush=True)

    print("running V9 STRICT replay (pattern+MA gates ON)...", flush=True)
    out = base.replay(df.reset_index(drop=True))
    out["ts"] = pd.to_datetime(out["ts"], utc=True)
    print(f"  long={int(out['ml_entry_long_trigger'].sum())} short={int(out['ml_entry_short_trigger'].sum())}", flush=True)
    e = out["ml_last_exit_outcome"]
    print(f"  exits: target={int((e==1).sum())} stop={int((e==-1).sum())} time={int((e==2).sum())}", flush=True)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(out_path, index=False)
    print(f"wrote {out_path}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
