#!/usr/bin/env python3
"""Build the Warbird Pro V9 Core training dataset.

This is the AG/Core ETL surface, not a Pine edit. It builds manifest-backed
ES rows at 5m or 15m with the locked V9 feature schema, NQ + 6E cross-asset
context, and optional Databento trade-side order-flow reconstruction for
CVD/divergence/absorption.

Core mode:
  - bars: ES OHLCV, normalized to selected timeframe (5m or 15m)
  - cross-asset: NQ + 6E from local Databento 1h bars when available
  - order flow: Databento trades zip, outright contract rows for the selected symbol root only
  - labels are built by scripts/ag/train_v9_locked.py, not here

The builder emits the exact feature names expected by train_v9_locked.ML_FEATURES
and fails hard on stale `ml_xa_dx_code`, OHLCV pseudo-delta columns, or missing
required columns in Core validation mode.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
import subprocess
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import duckdb
import numpy as np
import pandera.pandas as pa
import pandas as pd
from data_profiling import ProfileReport
from pandera.config import ValidationDepth, config_context

REPO_ROOT = Path(__file__).resolve().parents[4]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.ag.train_v9_locked import LABEL_COL, ML_FEATURES

WORKSPACE = REPO_ROOT / "scripts" / "duckdb_local" / "workspaces" / "warbird_pro_core"
EXPORTS_DIR = WORKSPACE / "exports"
DEFAULT_TRADES_ZIP = REPO_ROOT / "data" / "MES ES Trades GLBX-20260508-SAGMRP8P3H.zip"
DEFAULT_CROSS_ASSET_1H = Path(
    "/Volumes/Satechi Hub/Historical Data/Databento/raw/databento_futures_ohlcv_1h.parquet"
)
DEFAULT_VIX_CSV = Path("/Volumes/Satechi Hub/ZINC-FUSION-V15/data/downloads/VIXCLS.csv")
DEFAULT_SOURCE_BY_ROOT = {
    "ES": REPO_ROOT / "data" / "es_1m_20260503.parquet",
    "MES": REPO_ROOT / "data" / "mes_1m.parquet",
}

TRIGGER_FAMILY = "LIVE_ANCHOR_FOOTPRINT"
PINE_FILE = "indicators/warbird-pro-v9.pine"

FIB_236 = 0.236
FIB_382 = 0.382
FIB_PIVOT = 0.5
FIB_618 = 0.618
FIB_786 = 0.786
FIB_ONE = 1.0
FIB_T1 = 1.236
FIB_T2 = 1.618
FIB_T3 = 2.0
FIB_T4 = 2.236

FIB_DEVIATION = 3.0
FIB_DEPTH = 10
FIB_THRESHOLD_FLOOR_PCT = 0.25
MIN_FIB_RANGE_ATR = 0.5
FIB_HYSTERESIS_PCT = 2.0
HTF_CONF_TOL_PCT = 1.5

USE_MA_GATE = True
MA_FAST_BASE = 21
MA_SLOW_BASE = 9
MA_FAST_GRID = tuple(range(max(1, MA_FAST_BASE - 10), MA_FAST_BASE + 11))
MA_SLOW_GRID = tuple(range(max(1, MA_SLOW_BASE - 5), MA_SLOW_BASE + 6))
MA_FAST_LEN = MA_FAST_BASE
MA_SLOW_LEN = MA_SLOW_BASE
XA_MIN_AGREEMENT = 2
VIX_PRESSURE_BAND = 0.35
RSI_LEN = 11
RSI_OVERBOUGHT = 80.0
RSI_OVERSOLD = 20.0
LIQ_LOOKBACK_BARS = 10
LIQ_RECENCY_BARS = 1
EQH_TOL_PCT = 5
EQH_MIN_TAPS = 2
EQH_LOOKBACK = 50
VOL_Z_LEN = 10
CORR_LEN = 5
VIX_MOVE_BARS = 3
VIX_ATR_LEN = 14
ORDERFLOW_ROLLING_LEN = VOL_Z_LEN
ORDERFLOW_ABSORPTION_DELTA_PCT = 20.0
ORDERFLOW_FLUSH_DELTA_PCT = 20.0
ORDERFLOW_EVENT_VOLUME_SPIKE = 1.5
ORDERFLOW_COMPRESSED_RANGE_ATR = 0.75

DEFAULT_INDICATOR_KNOBS: dict[str, Any] = {
    "knob_auto_tune_zz": False,
    "knob_fib_deviation_manual": FIB_DEVIATION,
    "knob_fib_depth_manual": FIB_DEPTH,
    "knob_fib_threshold_floor_pct": FIB_THRESHOLD_FLOOR_PCT,
    "knob_min_fib_range_atr": MIN_FIB_RANGE_ATR,
    "knob_fib_hysteresis_pct": FIB_HYSTERESIS_PCT,
    "knob_htf_conf_tol_pct": HTF_CONF_TOL_PCT,
    "knob_use_pattern_confirm": False,
    "knob_use_liq_gate": True,
    "knob_liq_recency_bars": LIQ_RECENCY_BARS,
    "knob_trade_stop_atr_mult": 1.0,
    # Mirrors Pine's canonical `tradeMaxHoldBars` and the trainer's
    # FORWARD_SCAN_BARS contract.
    "knob_trade_max_hold_bars": 10,
    "knob_use_ma_gate": True,
    "knob_length_ema": MA_FAST_BASE,
    "knob_length_ma": MA_SLOW_BASE,
    "knob_rsi_length": RSI_LEN,
    "knob_rsi_overbought": RSI_OVERBOUGHT,
    "knob_rsi_oversold": RSI_OVERSOLD,
    "knob_liq_lookback_bars": LIQ_LOOKBACK_BARS,
    "knob_eqh_tol_pct": EQH_TOL_PCT,
    "knob_eqh_min_taps": EQH_MIN_TAPS,
    "knob_eqh_lookback": EQH_LOOKBACK,
    "knob_vol_z_length": VOL_Z_LEN,
    "knob_use_session_vwap": True,
    "knob_use_xa_gate": True,
    "knob_nq_symbol": "CME_MINI:NQ1!",
    "knob_zn_symbol": "CBOT:ZN1!",
    "knob_6e_symbol": "CME:6E1!",
    "knob_vix_symbol": "CBOE:VIX",
    "knob_corr_length": CORR_LEN,
    "knob_vix_move_bars": VIX_MOVE_BARS,
    "knob_vix_atr_length": VIX_ATR_LEN,
    "knob_vix_pressure_band": VIX_PRESSURE_BAND,
    "knob_xa_min_agreement": XA_MIN_AGREEMENT,
    "knob_zn_gate_direction": "Same Direction",
    "knob_use_footprint": True,
    "knob_fp_ticks_per_row": 4,
    "knob_fp_va_pct": 70.0,
    "knob_fp_imbalance_pct": 300.0,
    "knob_fp_absorption_delta_pct": ORDERFLOW_ABSORPTION_DELTA_PCT,
    "knob_fp_flush_delta_pct": ORDERFLOW_FLUSH_DELTA_PCT,
    "knob_fp_event_vol_spike": ORDERFLOW_EVENT_VOLUME_SPIKE,
    "knob_fp_compressed_range_atr": ORDERFLOW_COMPRESSED_RANGE_ATR,
}
KNOB_COLUMNS = tuple(DEFAULT_INDICATOR_KNOBS.keys())

# Columns the ETL still computes for historical/diagnostic continuity but
# that the 2026-05-12 lean-cut removes from the export CSV. Dropped before
# the DuckDB COPY in write_outputs(); the manifest's feature_columns_locked
# is sourced from train_v9_locked.ML_FEATURES, so this list only governs
# what reaches disk. The dropped knob_* keys are kept in
# DEFAULT_INDICATOR_KNOBS so the ETL's internal _knob() lookups still
# resolve, but they never reach the CSV.
DROPPED_FEATURES_2026_05_12: tuple[str, ...] = (
    # daily/weekly S/R levels
    "ml_lvl_pdh_dist_atr", "ml_lvl_pdl_dist_atr",
    "ml_lvl_pwh_dist_atr", "ml_lvl_pwl_dist_atr",
    # redundant fib touch binaries (ordinal ml_fib_touch_level_code kept)
    "ml_fib_touch_500_long", "ml_fib_touch_618_long",
    "ml_fib_touch_786_long",
    "ml_fib_touch_500_short", "ml_fib_touch_618_short",
    "ml_fib_touch_786_short",
    # footprint diagnostic kept out of the active feature surface
    "ml_delta_imbalance_pct",
    # CVD divergence
    "ml_cvd_div_bull", "ml_cvd_div_bear",
    # ZN / VIX / HG cross-asset (NQ + 6E only after the cut)
    "ml_xa_zn_code", "ml_xa_zn_rate_pressure",
    "ml_xa_vix_pressure", "ml_xa_hg_growth_proxy",
    # knob settings for removed assets/surfaces (still resolved by _knob()
    # internally but not exported)
    "knob_zn_symbol", "knob_zn_gate_direction",
    "knob_vix_symbol", "knob_vix_move_bars",
    "knob_vix_atr_length", "knob_vix_pressure_band",
)

LOCKED_DUCKDB_VERSION = "1.5.2"
LOCKED_PANDERA_VERSION = "0.31.1"
LOCKED_DATA_PROFILING_VERSION = "4.19.1"
PANDERA_CONTRACT_DEPTH = ValidationDepth.SCHEMA_AND_DATA
FORBIDDEN_LINEAGE_TOKENS = (
    "postgres",
    "psycopg2",
    "ag_training",
    "local_warehouse",
    "optuna",
)

OUTRIGHT_ROOT_PATTERNS = {
    "ES": re.compile(r"^ES[FGHJKMNQUVXZ]\d{1,2}$"),
}
TRADES_MEMBER_RE = re.compile(r"(\d{8})-(\d{8})\.trades\.csv\.zst$")


def generate_indicator_profiles(profile_mode: str = "base") -> list[dict[str, Any]]:
    """Return AG input profiles derived from the Warbird V9 indicator contract."""
    mode = str(profile_mode).strip().lower()
    if mode not in {"base", "ma-grid"}:
        raise ValueError(f"Unsupported profile mode: {profile_mode!r}")
    if mode == "base":
        profile = dict(DEFAULT_INDICATOR_KNOBS)
        profile["profile_id"] = "base_ema21_ema9"
        profile["profile_mode"] = "base"
        profile["profile_is_ma_base"] = True
        profile["profile_ema_offset"] = 0
        profile["profile_ma_offset"] = 0
        return [profile]

    profiles: list[dict[str, Any]] = []
    for ema_len in MA_FAST_GRID:
        for ma_len in MA_SLOW_GRID:
            profile = dict(DEFAULT_INDICATOR_KNOBS)
            profile["knob_length_ema"] = int(ema_len)
            profile["knob_length_ma"] = int(ma_len)
            profile["profile_id"] = f"ma_grid_ema{ema_len}_ema{ma_len}"
            profile["profile_mode"] = "ma-grid"
            profile["profile_is_ma_base"] = ema_len == MA_FAST_BASE and ma_len == MA_SLOW_BASE
            profile["profile_ema_offset"] = int(ema_len - MA_FAST_BASE)
            profile["profile_ma_offset"] = int(ma_len - MA_SLOW_BASE)
            profiles.append(profile)
    return profiles


def _knob(knobs: dict[str, Any], name: str) -> Any:
    return knobs.get(name, DEFAULT_INDICATOR_KNOBS[name])


def _with_knob_columns(df: pd.DataFrame, knobs: dict[str, Any]) -> pd.DataFrame:
    out = df.copy()
    for col in KNOB_COLUMNS:
        out[col] = _knob(knobs, col)
    for col in ("profile_id", "profile_mode", "profile_is_ma_base", "profile_ema_offset", "profile_ma_offset"):
        out[col] = knobs.get(col)
    return out


def repo_commit() -> str:
    try:
        return subprocess.check_output(
            ["git", "-C", str(REPO_ROOT), "rev-parse", "HEAD"], text=True
        ).strip()
    except Exception:
        return "unknown"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def utc_ts(value: str | None) -> pd.Timestamp | None:
    if value is None:
        return None
    return pd.Timestamp(value, tz="UTC")


def normalize_symbol_root(symbol: str) -> str:
    token = str(symbol).upper().strip()
    if ":" in token:
        token = token.split(":", 1)[1]
    token = token.replace("!", "")
    root = ""
    for char in token:
        if char.isalpha():
            root += char
        else:
            break
    if root.startswith("MES"):
        return "MES"
    if root.startswith("ES"):
        return "ES"
    return root


def default_source_for_symbol(symbol: str) -> Path:
    return DEFAULT_SOURCE_BY_ROOT.get(normalize_symbol_root(symbol), DEFAULT_SOURCE_BY_ROOT["ES"])


def rma(values: np.ndarray, period: int) -> np.ndarray:
    out = np.full(len(values), np.nan, dtype=float)
    if len(values) < period:
        return out
    out[period - 1] = np.nanmean(values[:period])
    alpha = 1.0 / period
    for i in range(period, len(values)):
        out[i] = values[i] * alpha + out[i - 1] * (1.0 - alpha)
    return out


def atr_rma(high: np.ndarray, low: np.ndarray, close: np.ndarray, period: int) -> np.ndarray:
    prev_close = np.r_[close[0], close[:-1]]
    tr = np.maximum(high - low, np.maximum(np.abs(high - prev_close), np.abs(low - prev_close)))
    return rma(tr, period)


def sma(values: np.ndarray, period: int) -> np.ndarray:
    return pd.Series(values).rolling(period, min_periods=period).mean().to_numpy(dtype=float)


def ema(values: np.ndarray, period: int) -> np.ndarray:
    return pd.Series(values).ewm(span=period, adjust=False, min_periods=period).mean().to_numpy(dtype=float)


def rsi_rma(close: np.ndarray, period: int) -> np.ndarray:
    diff = np.diff(close, prepend=close[0])
    gain = np.where(diff > 0, diff, 0.0)
    loss = np.where(diff < 0, -diff, 0.0)
    avg_gain = rma(gain, period)
    avg_loss = rma(loss, period)
    rs = np.divide(avg_gain, np.maximum(avg_loss, 1e-12))
    return 100.0 - 100.0 / (1.0 + rs)


def dmi_adx(high: np.ndarray, low: np.ndarray, close: np.ndarray, period: int = 14) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    up = high - np.r_[high[0], high[:-1]]
    down = np.r_[low[0], low[:-1]] - low
    plus_dm = np.where((up > down) & (up > 0), up, 0.0)
    minus_dm = np.where((down > up) & (down > 0), down, 0.0)
    atr = atr_rma(high, low, close, period)
    plus_di = 100.0 * rma(plus_dm, period) / np.maximum(atr, 1e-12)
    minus_di = 100.0 * rma(minus_dm, period) / np.maximum(atr, 1e-12)
    dx = 100.0 * np.abs(plus_di - minus_di) / np.maximum(plus_di + minus_di, 1e-12)
    adx = rma(dx, period)
    return plus_di, minus_di, adx


def zscore(series: pd.Series, length: int) -> pd.Series:
    mean = series.rolling(length, min_periods=length).mean()
    sd = series.rolling(length, min_periods=length).std(ddof=0)
    return ((series - mean) / sd.replace(0, np.nan)).fillna(0.0)


def close_movement_pressure(series: pd.Series, move_bars: int, atr_length: int) -> pd.Series:
    move = series - series.shift(move_bars)
    one_bar_move = series.diff().abs()
    atr_proxy = one_bar_move.ewm(alpha=1.0 / atr_length, adjust=False, min_periods=atr_length).mean()
    return (move / atr_proxy.replace(0, np.nan)).replace([np.inf, -np.inf], np.nan).fillna(0.0)


def xa_code(close: pd.Series) -> pd.Series:
    slow = close.rolling(21, min_periods=21).mean()
    fast = close.ewm(span=9, adjust=False, min_periods=9).mean()
    code = pd.Series(0, index=close.index, dtype="float64")
    code[(fast > slow) & (close > fast)] = 2
    code[(fast > slow) & ~(close > fast)] = 1
    code[(fast < slow) & (close < fast)] = -2
    code[(fast < slow) & ~(close < fast)] = -1
    return code.fillna(0.0)


def duckdb_path_literal(path: Path) -> str:
    return str(path).replace("'", "''")


def read_source_relation(con: duckdb.DuckDBPyConnection, source: Path) -> duckdb.DuckDBPyRelation:
    suffix = "".join(source.suffixes).lower()
    if suffix.endswith(".parquet"):
        return con.read_parquet(str(source))
    if suffix.endswith(".csv") or suffix.endswith(".csv.zst"):
        return con.read_csv(str(source), header=True, auto_detect=True, sample_size=-1)
    raise SystemExit(f"Unsupported source type: {source}")


def load_bars(source: Path) -> pd.DataFrame:
    con = duckdb.connect()
    rel = read_source_relation(con, source)
    lower_cols = {name.lower(): name for name in rel.columns}
    ts_col = lower_cols.get("ts") or lower_cols.get("ts_event")
    required = {
        "open": lower_cols.get("open"),
        "high": lower_cols.get("high"),
        "low": lower_cols.get("low"),
        "close": lower_cols.get("close"),
        "volume": lower_cols.get("volume"),
    }
    if ts_col is None:
        raise SystemExit(f"{source} missing columns: ['ts' or 'ts_event']")
    missing = sorted(name for name, col in required.items() if col is None)
    if missing:
        raise SystemExit(f"{source} missing columns: {missing}")

    projection = (
        f'"{ts_col}" AS ts, '
        f'"{required["open"]}" AS open, '
        f'"{required["high"]}" AS high, '
        f'"{required["low"]}" AS low, '
        f'"{required["close"]}" AS close, '
        f'"{required["volume"]}" AS volume'
    )
    df = rel.project(projection).order("ts").df()

    df["ts"] = pd.to_datetime(df["ts"], utc=True)
    for col in ("open", "high", "low", "close", "volume"):
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.dropna(subset=["ts", "open", "high", "low", "close"]).sort_values("ts")
    return df[["ts", "open", "high", "low", "close", "volume"]].reset_index(drop=True)


def duckdb_sort_filter_frame(
    df: pd.DataFrame,
    start: pd.Timestamp | None,
    end: pd.Timestamp | None,
) -> pd.DataFrame:
    def as_utc(value: pd.Timestamp) -> pd.Timestamp:
        stamp = pd.Timestamp(value)
        return stamp.tz_localize("UTC") if stamp.tzinfo is None else stamp.tz_convert("UTC")

    con = duckdb.connect()
    con.register("bars_df", df)
    where: list[str] = []
    params: list[Any] = []
    if start is not None:
        where.append("ts >= ?")
        params.append(as_utc(start))
    if end is not None:
        where.append("ts <= ?")
        params.append(as_utc(end))
    query = "SELECT ts, open, high, low, close, volume FROM bars_df"
    if where:
        query = f"{query} WHERE {' AND '.join(where)}"
    query = f"{query} ORDER BY ts"
    out = con.execute(query, params).df()
    return out.reset_index(drop=True)


def normalize_to_timeframe(df: pd.DataFrame, timeframe_min: int) -> pd.DataFrame:
    ts = pd.to_datetime(df["ts"], utc=True)
    diffs = ts.sort_values().diff().dropna()
    target_seconds = timeframe_min * 60
    median_seconds = diffs.dt.total_seconds().median() if not diffs.empty else target_seconds
    if median_seconds <= 90:
        s = df.set_index("ts").sort_index()
        out = s.resample(f"{timeframe_min}min", label="left", closed="left").agg(
            open=("open", "first"),
            high=("high", "max"),
            low=("low", "min"),
            close=("close", "last"),
            volume=("volume", "sum"),
        )
        return out.dropna(subset=["close"]).reset_index()
    return df.copy().sort_values("ts").reset_index(drop=True)


def zigzag_anchors(
    high: np.ndarray,
    low: np.ndarray,
    close: np.ndarray,
    atr10: np.ndarray,
    fib_deviation: float = FIB_DEVIATION,
    fib_threshold_floor_pct: float = FIB_THRESHOLD_FLOOR_PCT,
    fib_depth: int = FIB_DEPTH,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    n = len(close)
    anchor_high = np.full(n, np.nan)
    anchor_low = np.full(n, np.nan)
    anchor_high_bar = np.full(n, -1, dtype=np.int64)
    anchor_low_bar = np.full(n, -1, dtype=np.int64)
    pivots: list[tuple[int, float, int]] = []
    swing_high = float(high[0])
    swing_high_idx = 0
    swing_low = float(low[0])
    swing_low_idx = 0
    last_dir = 0
    for i in range(n):
        if close[i] > 0 and np.isfinite(atr10[i]):
            threshold_pct = max((atr10[i] / close[i]) * 100.0 * fib_deviation, fib_threshold_floor_pct)
        else:
            threshold_pct = fib_threshold_floor_pct
        threshold_abs = threshold_pct * 0.01 * close[i]
        if high[i] > swing_high:
            swing_high = float(high[i])
            swing_high_idx = i
        if low[i] < swing_low:
            swing_low = float(low[i])
            swing_low_idx = i
        if last_dir != 1 and (swing_high - low[i]) >= threshold_abs:
            if not pivots or (i - pivots[-1][0]) >= fib_depth:
                pivots.append((swing_high_idx, swing_high, 1))
                last_dir = 1
                swing_low = float(low[i])
                swing_low_idx = i
        elif last_dir != -1 and (high[i] - swing_low) >= threshold_abs:
            if not pivots or (i - pivots[-1][0]) >= fib_depth:
                pivots.append((swing_low_idx, swing_low, -1))
                last_dir = -1
                swing_high = float(high[i])
                swing_high_idx = i
        if len(pivots) >= 2:
            a, b = pivots[-2], pivots[-1]
            hp, lp = (a, b) if a[2] > 0 else (b, a)
            anchor_high[i] = hp[1]
            anchor_low[i] = lp[1]
            anchor_high_bar[i] = hp[0]
            anchor_low_bar[i] = lp[0]
    return anchor_high, anchor_low, anchor_high_bar, anchor_low_bar


def htf_confluence(
    df: pd.DataFrame,
    p_pivot: np.ndarray,
    p_382: np.ndarray,
    p_618: np.ndarray,
    fib_range: np.ndarray,
    htf_conf_tol_pct: float = HTF_CONF_TOL_PCT,
) -> np.ndarray:
    s = df.set_index("ts").sort_index()
    high_1h = s["high"].resample("1h", label="left", closed="left").max()
    low_1h = s["low"].resample("1h", label="left", closed="left").min()
    htf_high = high_1h.rolling(55, min_periods=55).max()
    htf_low = low_1h.rolling(55, min_periods=55).min()
    htf_range = htf_high - htf_low
    htf = pd.DataFrame(index=htf_high.index)
    htf["p382"] = htf_low + htf_range * FIB_382
    htf["p500"] = htf_low + htf_range * FIB_PIVOT
    htf["p618"] = htf_low + htf_range * FIB_618
    aligned = htf.reindex(s.index, method="ffill")
    tol = fib_range * htf_conf_tol_pct * 0.01
    total = np.zeros(len(df), dtype=float)
    for level in (p_pivot, p_382, p_618):
        for col in ("p382", "p500", "p618"):
            ref = aligned[col].to_numpy(dtype=float)
            total += np.where(np.isfinite(level) & np.isfinite(ref) & (np.abs(level - ref) <= tol), 1.0, 0.0)
    return total


def compute_liquidity_state(
    *,
    high: np.ndarray,
    low: np.ndarray,
    close: np.ndarray,
    lookback_bars: int,
    recency_bars: int,
) -> dict[str, np.ndarray]:
    bsl = pd.Series(high).rolling(lookback_bars, min_periods=lookback_bars).max().shift(1).to_numpy()
    ssl = pd.Series(low).rolling(lookback_bars, min_periods=lookback_bars).min().shift(1).to_numpy()
    swept_bsl = (high > bsl) & (close < bsl)
    swept_ssl = (low < ssl) & (close > ssl)
    reclaimed_bsl = np.r_[False, swept_bsl[:-1] & (close[1:] < bsl[1:])]
    reclaimed_ssl = np.r_[False, swept_ssl[:-1] & (close[1:] > ssl[1:])]
    liq_bull = swept_ssl | reclaimed_ssl
    liq_bear = swept_bsl | reclaimed_bsl
    bars_since_liq_bull = bars_since_event(liq_bull)
    bars_since_liq_bear = bars_since_event(liq_bear)
    recent_liq_bull = (bars_since_liq_bull >= 0) & (bars_since_liq_bull < recency_bars)
    recent_liq_bear = (bars_since_liq_bear >= 0) & (bars_since_liq_bear < recency_bars)
    return {
        "bsl": bsl,
        "ssl": ssl,
        "swept_bsl": swept_bsl,
        "swept_ssl": swept_ssl,
        "reclaimed_bsl": reclaimed_bsl,
        "reclaimed_ssl": reclaimed_ssl,
        "bars_since_liq_bull": bars_since_liq_bull,
        "bars_since_liq_bear": bars_since_liq_bear,
        "recent_liq_bull": recent_liq_bull,
        "recent_liq_bear": recent_liq_bear,
    }


def compute_fib_entry_reaction_features(
    *,
    open_: np.ndarray,
    high: np.ndarray,
    low: np.ndarray,
    close: np.ndarray,
    atr: np.ndarray,
    direction: np.ndarray,
    p_pivot: np.ndarray,
    p_618: np.ndarray,
    p_786: np.ndarray,
) -> dict[str, np.ndarray]:
    touched500_long = np.r_[False, (direction[1:] == 1) & np.isfinite(p_pivot[1:]) & (close[:-1] > p_pivot[1:]) & (low[1:] <= p_pivot[1:]) & (close[1:] >= p_pivot[1:])]
    touched618_long = np.r_[False, (direction[1:] == 1) & np.isfinite(p_618[1:]) & (close[:-1] > p_618[1:]) & (low[1:] <= p_618[1:]) & (close[1:] >= p_618[1:])]
    touched786_long = np.r_[False, (direction[1:] == 1) & np.isfinite(p_786[1:]) & (close[:-1] > p_786[1:]) & (low[1:] <= p_786[1:]) & (close[1:] >= p_786[1:])]
    touched500_short = np.r_[False, (direction[1:] == -1) & np.isfinite(p_pivot[1:]) & (close[:-1] < p_pivot[1:]) & (high[1:] >= p_pivot[1:]) & (close[1:] <= p_pivot[1:])]
    touched618_short = np.r_[False, (direction[1:] == -1) & np.isfinite(p_618[1:]) & (close[:-1] < p_618[1:]) & (high[1:] >= p_618[1:]) & (close[1:] <= p_618[1:])]
    touched786_short = np.r_[False, (direction[1:] == -1) & np.isfinite(p_786[1:]) & (close[:-1] < p_786[1:]) & (high[1:] >= p_786[1:]) & (close[1:] <= p_786[1:])]

    selected_entry_level = np.where(
        touched786_long | touched786_short,
        p_786,
        np.where(touched618_long | touched618_short, p_618, np.where(touched500_long | touched500_short, p_pivot, np.nan)),
    )
    fib_touch_level_code = np.where(
        touched786_long | touched786_short,
        786.0,
        np.where(touched618_long | touched618_short, 618.0, np.where(touched500_long | touched500_short, 500.0, 0.0)),
    )
    selected_long = touched500_long | touched618_long | touched786_long
    selected_short = touched500_short | touched618_short | touched786_short
    pierce = np.where(
        selected_long,
        selected_entry_level - low,
        np.where(selected_short, high - selected_entry_level, 0.0),
    )
    reclaim = np.where(
        selected_long,
        close - selected_entry_level,
        np.where(selected_short, selected_entry_level - close, 0.0),
    )
    bar_range = high - low
    body_size = np.abs(close - open_)
    upper_wick = high - np.maximum(open_, close)
    lower_wick = np.minimum(open_, close) - low
    body_ratio = np.where(bar_range > 0, body_size / np.maximum(bar_range, 1e-12), 0.0)
    upper_wick_ratio = np.where(bar_range > 0, upper_wick / np.maximum(bar_range, 1e-12), 0.0)
    lower_wick_ratio = np.where(bar_range > 0, lower_wick / np.maximum(bar_range, 1e-12), 0.0)
    reclaim_atr = safe_div(reclaim, atr)
    reaction_code = np.where(
        fib_touch_level_code == 0.0,
        0.0,
        np.where(reclaim_atr >= 0.10, 1.0, np.where(reclaim_atr >= 0.0, 0.0, -1.0)),
    )
    return {
        "touched500_long": touched500_long,
        "touched618_long": touched618_long,
        "touched786_long": touched786_long,
        "touched500_short": touched500_short,
        "touched618_short": touched618_short,
        "touched786_short": touched786_short,
        "selected_entry_level": selected_entry_level,
        "fib_touch_level_code": fib_touch_level_code,
        "fib_entry_dist_atr": safe_div(close - selected_entry_level, atr),
        "fib_pierce_atr": safe_div(np.maximum(pierce, 0.0), atr),
        "fib_close_reclaim_atr": reclaim_atr,
        "fib_reaction_body_ratio": body_ratio,
        "fib_reaction_upper_wick_ratio": upper_wick_ratio,
        "fib_reaction_lower_wick_ratio": lower_wick_ratio,
        "fib_reaction_code": reaction_code,
    }


def prior_day_week_levels(df: pd.DataFrame) -> pd.DataFrame:
    s = df.set_index("ts").sort_index()
    daily = s.resample("1D").agg(pdh=("high", "max"), pdl=("low", "min")).shift(1)
    weekly = s.resample("1W-MON", label="left", closed="left").agg(pwh=("high", "max"), pwl=("low", "min")).shift(1)
    levels = daily.reindex(s.index, method="ffill").join(weekly.reindex(s.index, method="ffill"))
    return levels.reset_index(drop=True)


def compute_base_features(df_5m: pd.DataFrame, knobs: dict[str, Any] | None = None) -> pd.DataFrame:
    knobs = dict(DEFAULT_INDICATOR_KNOBS if knobs is None else knobs)
    df = df_5m.copy().reset_index(drop=True)
    n = len(df)
    open_ = df["open"].to_numpy(dtype=float)
    high = df["high"].to_numpy(dtype=float)
    low = df["low"].to_numpy(dtype=float)
    close = df["close"].to_numpy(dtype=float)
    volume = df["volume"].fillna(0).to_numpy(dtype=float)

    atr14 = atr_rma(high, low, close, 14)
    atr10 = atr_rma(high, low, close, 10)
    rsi_len = int(_knob(knobs, "knob_rsi_length"))
    rsi_overbought = float(_knob(knobs, "knob_rsi_overbought"))
    rsi_oversold = float(_knob(knobs, "knob_rsi_oversold"))
    fast_ma = ema(close, int(_knob(knobs, "knob_length_ema")))
    slow_ma = ema(fast_ma, int(_knob(knobs, "knob_length_ma")))
    rsi14 = rsi_rma(close, rsi_len)
    ma_bull = (close > fast_ma) & (close > slow_ma)
    ma_bear = (close < fast_ma) & (close < slow_ma)
    plus_di, minus_di, adx = dmi_adx(high, low, close, 14)

    bar_range = high - low
    body_size = np.abs(close - open_)
    bullish = close > open_
    bearish = close < open_
    upper_wick = high - np.maximum(open_, close)
    lower_wick = np.minimum(open_, close) - low
    upper_wick_ratio = np.where(bar_range > 0, upper_wick / np.maximum(bar_range, 1e-12), 0.0)
    lower_wick_ratio = np.where(bar_range > 0, lower_wick / np.maximum(bar_range, 1e-12), 0.0)
    body_ratio = np.where(bar_range > 0, body_size / np.maximum(bar_range, 1e-12), 0.0)

    pat_rising_window = np.r_[False, bullish[1:] & (low[1:] > high[:-1])]
    pat_bear_engulf = np.r_[False, bearish[1:] & bullish[:-1] & (close[1:] < open_[:-1]) & (open_[1:] > close[:-1])]
    pat_marubozu_black = bearish & (body_ratio >= 0.85) & (upper_wick_ratio <= 0.10) & (lower_wick_ratio <= 0.10)
    pat_tweezer_top = np.r_[False, bearish[1:] & (np.abs(high[1:] - high[:-1]) <= atr14[1:] * 0.05) & bullish[:-1]]

    anchors_high, anchors_low, _ahb, _alb = zigzag_anchors(
        high,
        low,
        close,
        atr10,
        fib_deviation=float(_knob(knobs, "knob_fib_deviation_manual")),
        fib_threshold_floor_pct=float(_knob(knobs, "knob_fib_threshold_floor_pct")),
        fib_depth=int(_knob(knobs, "knob_fib_depth_manual")),
    )
    fib_range = anchors_high - anchors_low
    is_valid = np.isfinite(anchors_high) & np.isfinite(anchors_low) & (fib_range >= float(_knob(knobs, "knob_min_fib_range_atr")) * atr14)
    midpoint = anchors_low + fib_range * 0.5
    hyst = fib_range * float(_knob(knobs, "knob_fib_hysteresis_pct")) * 0.01
    fib_bull = np.ones(n, dtype=bool)
    state = True
    for i in range(n):
        if is_valid[i]:
            if close[i] >= midpoint[i] + hyst[i]:
                state = True
            elif close[i] <= midpoint[i] - hyst[i]:
                state = False
        else:
            state = True
        fib_bull[i] = state
    direction = np.where(fib_bull, 1, -1)
    fib_base = np.where(fib_bull, anchors_low, anchors_high)
    fib_dir = np.where(fib_bull, 1.0, -1.0)

    def fib_price(ratio: float) -> np.ndarray:
        return np.where(fib_range > 0, fib_base + fib_dir * fib_range * ratio, np.nan)

    p_382 = fib_price(FIB_382)
    p_pivot = fib_price(FIB_PIVOT)
    p_618 = fib_price(FIB_618)
    p_786 = fib_price(FIB_786)
    # Full ladder TPs at fib 1.000 / 1.236 / 1.618 / 2.000 / 2.236 —
    # emitted as ml_trade_tp1..5 (label-construction inputs mirroring
    # indicators/warbird-pro-v9.pine's pOne/pT1/pT2/pT3/pT4 plots).
    p_one = fib_price(FIB_ONE)
    p_t1 = fib_price(FIB_T1)
    p_t2 = fib_price(FIB_T2)
    p_t3 = fib_price(FIB_T3)
    p_t4 = fib_price(FIB_T4)

    zone_upper = np.maximum(p_618, p_786)
    zone_lower = np.minimum(p_618, p_786)
    break_in_dir = np.zeros(n, dtype=bool)
    break_in_dir[1:] = np.where(
        direction[1:] == 1,
        (close[1:] > zone_upper[1:]) & (close[:-1] <= zone_upper[1:]),
        (close[1:] < zone_lower[1:]) & (close[:-1] >= zone_lower[1:]),
    )
    bars_since_break = np.full(n, -1.0)
    last_break = -1
    for i, flag in enumerate(break_in_dir):
        if flag:
            last_break = i
        bars_since_break[i] = -1.0 if last_break < 0 else float(i - last_break)

    liq_state = compute_liquidity_state(
        high=high,
        low=low,
        close=close,
        lookback_bars=int(_knob(knobs, "knob_liq_lookback_bars")),
        recency_bars=int(_knob(knobs, "knob_liq_recency_bars")),
    )
    bsl = liq_state["bsl"]
    ssl = liq_state["ssl"]
    swept_bsl = liq_state["swept_bsl"]
    swept_ssl = liq_state["swept_ssl"]
    reclaimed_bsl = liq_state["reclaimed_bsl"]
    reclaimed_ssl = liq_state["reclaimed_ssl"]
    bars_since_liq_bull = liq_state["bars_since_liq_bull"]
    bars_since_liq_bear = liq_state["bars_since_liq_bear"]
    recent_liq_bull = liq_state["recent_liq_bull"]
    recent_liq_bear = liq_state["recent_liq_bear"]

    eqh_tol = atr14 * (float(_knob(knobs, "knob_eqh_tol_pct")) / 100.0)
    hi_taps = np.zeros(n, dtype=int)
    lo_taps = np.zeros(n, dtype=int)
    for i in range(n):
        lo_idx = max(0, i - int(_knob(knobs, "knob_eqh_lookback")))
        if i > lo_idx and np.isfinite(eqh_tol[i]):
            hi_taps[i] = int(np.sum(np.abs(high[lo_idx:i] - high[i]) <= eqh_tol[i]))
            lo_taps[i] = int(np.sum(np.abs(low[lo_idx:i] - low[i]) <= eqh_tol[i]))
    last_eqh = pd.Series(np.where(hi_taps >= int(_knob(knobs, "knob_eqh_min_taps")), high, np.nan)).ffill().to_numpy()
    last_eql = pd.Series(np.where(lo_taps >= int(_knob(knobs, "knob_eqh_min_taps")), low, np.nan)).ffill().to_numpy()

    vwap_session = session_vwap(df, volume) if bool(_knob(knobs, "knob_use_session_vwap")) else close
    vol_z = zscore(pd.Series(volume), int(_knob(knobs, "knob_vol_z_length"))).to_numpy(dtype=float)
    htf_conf_total = htf_confluence(df, p_pivot, p_382, p_618, fib_range, float(_knob(knobs, "knob_htf_conf_tol_pct")))
    levels = prior_day_week_levels(df)

    fib_reaction = compute_fib_entry_reaction_features(
        open_=open_,
        high=high,
        low=low,
        close=close,
        atr=atr14,
        direction=direction,
        p_pivot=p_pivot,
        p_618=p_618,
        p_786=p_786,
    )
    touched500_long = fib_reaction["touched500_long"]
    touched618_long = fib_reaction["touched618_long"]
    touched786_long = fib_reaction["touched786_long"]
    touched500_short = fib_reaction["touched500_short"]
    touched618_short = fib_reaction["touched618_short"]
    touched786_short = fib_reaction["touched786_short"]
    trigger_long = touched500_long | touched618_long | touched786_long
    trigger_short = touched500_short | touched618_short | touched786_short
    entry_level = fib_reaction["selected_entry_level"]
    fib_touch_level_code = fib_reaction["fib_touch_level_code"]
    trade_stop = np.where(
        trigger_long,
        entry_level - atr14 * float(_knob(knobs, "knob_trade_stop_atr_mult")),
        np.where(trigger_short, entry_level + atr14 * float(_knob(knobs, "knob_trade_stop_atr_mult")), np.nan),
    )

    out = pd.DataFrame(
        {
            "ts": df["ts"],
            "open": open_,
            "high": high,
            "low": low,
            "close": close,
            "volume": volume,
            "ml_atr14": atr14,
            "ml_dir": direction.astype(float),
            "ml_fib_range": fib_range,
            "ml_pivot_dist_atr": safe_div(close - p_pivot, atr14),
            "ml_p618_dist_atr": safe_div(close - p_618, atr14),
            "ml_bars_since_break": bars_since_break,
            "ml_break_in_dir": break_in_dir.astype(float),
            "ml_rsi_value": rsi14,
            "ml_rsi_stance_code": np.where(rsi14 <= rsi_oversold, 1.0, np.where(rsi14 >= rsi_overbought, -1.0, 0.0)),
            "ml_ma_bias": np.where(ma_bull, 1.0, np.where(ma_bear, -1.0, 0.0)),
            "ml_ma_slow_dist_atr": safe_div(close - slow_ma, atr14),
            "ml_ma_fast_dist_atr": safe_div(close - fast_ma, atr14),
            "ml_adx_value": adx,
            "ml_adx_plus_di": plus_di,
            "ml_adx_minus_di": minus_di,
            "ml_pat_rising_window": pat_rising_window.astype(float),
            "ml_pat_bear_engulf": pat_bear_engulf.astype(float),
            "ml_pat_marubozu_black": pat_marubozu_black.astype(float),
            "ml_pat_tweezer_top": pat_tweezer_top.astype(float),
            "ml_bsl_dist_atr": safe_div(bsl - close, atr14),
            "ml_ssl_dist_atr": safe_div(close - ssl, atr14),
            "ml_swept_bsl": swept_bsl.astype(float),
            "ml_swept_ssl": swept_ssl.astype(float),
            "ml_reclaimed_bsl": reclaimed_bsl.astype(float),
            "ml_reclaimed_ssl": reclaimed_ssl.astype(float),
            "ml_recent_liq_bull": recent_liq_bull.astype(float),
            "ml_recent_liq_bear": recent_liq_bear.astype(float),
            "ml_liq_bars_since_bull": bars_since_liq_bull.astype(float),
            "ml_liq_bars_since_bear": bars_since_liq_bear.astype(float),
            "ml_liq_eqh_dist_atr": safe_div(last_eqh - close, atr14),
            "ml_liq_eql_dist_atr": safe_div(close - last_eql, atr14),
            "ml_liq_vwap_dist_atr": safe_div(close - vwap_session, atr14),
            "ml_liq_vol_zscore": vol_z,
            "ml_htf_conf_total": htf_conf_total,
            "ml_lvl_pdh_dist_atr": safe_div(levels["pdh"].to_numpy(dtype=float) - close, atr14),
            "ml_lvl_pdl_dist_atr": safe_div(close - levels["pdl"].to_numpy(dtype=float), atr14),
            "ml_lvl_pwh_dist_atr": safe_div(levels["pwh"].to_numpy(dtype=float) - close, atr14),
            "ml_lvl_pwl_dist_atr": safe_div(close - levels["pwl"].to_numpy(dtype=float), atr14),
            "ml_trade_entry": entry_level,
            "ml_trade_stop": trade_stop,
            # Fib-ladder TPs (always emitted from current geometry; required
            # label-construction inputs for train_v9_locked.build_trade_dataset).
            "ml_trade_tp1": p_one,
            "ml_trade_tp2": p_t1,
            "ml_trade_tp3": p_t2,
            "ml_trade_tp4": p_t3,
            "ml_trade_tp5": p_t4,
            "ml_fib_touch_level_code": fib_touch_level_code,
            "ml_fib_touch_500_long": touched500_long.astype(float),
            "ml_fib_touch_618_long": touched618_long.astype(float),
            "ml_fib_touch_786_long": touched786_long.astype(float),
            "ml_fib_touch_500_short": touched500_short.astype(float),
            "ml_fib_touch_618_short": touched618_short.astype(float),
            "ml_fib_touch_786_short": touched786_short.astype(float),
            "ml_fib_entry_dist_atr": fib_reaction["fib_entry_dist_atr"],
            "ml_fib_pierce_atr": fib_reaction["fib_pierce_atr"],
            "ml_fib_close_reclaim_atr": fib_reaction["fib_close_reclaim_atr"],
            "ml_fib_reaction_body_ratio": fib_reaction["fib_reaction_body_ratio"],
            "ml_fib_reaction_upper_wick_ratio": fib_reaction["fib_reaction_upper_wick_ratio"],
            "ml_fib_reaction_lower_wick_ratio": fib_reaction["fib_reaction_lower_wick_ratio"],
            "ml_fib_reaction_code": fib_reaction["fib_reaction_code"],
            "__trigger_long": trigger_long.astype(bool),
            "__trigger_short": trigger_short.astype(bool),
            "__recent_liq_bull": recent_liq_bull.astype(bool),
            "__recent_liq_bear": recent_liq_bear.astype(bool),
            "__is_valid": is_valid.astype(bool),
        }
    )
    return _with_knob_columns(out, knobs)


def safe_div(num: np.ndarray, denom: np.ndarray) -> np.ndarray:
    return np.divide(num, denom, out=np.zeros_like(num, dtype=float), where=np.isfinite(denom) & (np.abs(denom) > 1e-12))


def bars_since_event(mask: np.ndarray) -> np.ndarray:
    out = np.full(len(mask), -1, dtype=int)
    last = -1
    for i, flag in enumerate(mask):
        if bool(flag):
            last = i
        out[i] = -1 if last < 0 else i - last
    return out


def session_vwap(df: pd.DataFrame, volume: np.ndarray) -> np.ndarray:
    typical = (df["high"].to_numpy(dtype=float) + df["low"].to_numpy(dtype=float) + df["close"].to_numpy(dtype=float)) / 3.0
    dates = pd.to_datetime(df["ts"], utc=True).dt.date
    pv = pd.Series(typical * volume).groupby(dates).cumsum().to_numpy(dtype=float)
    vv = pd.Series(volume).groupby(dates).cumsum().to_numpy(dtype=float)
    return safe_div(pv, vv)


def align_series_to_index(series: pd.Series, target_index: pd.DatetimeIndex) -> pd.Series:
    # Prediction-time-safe alignment: forward-fill only, never backward-fill.
    # The earlier bfill() at the tail was a lookahead leak for leading bars
    # before the first cross-asset close anchor — bars would pull from a
    # FUTURE cross-asset value. Leading NaN is allowed and imputed by AG's
    # feature generator. Locked 2026-05-11.
    s = series.copy()
    s.index = pd.to_datetime(s.index, utc=True)
    s = s[~s.index.duplicated(keep="last")].sort_index()
    return s.reindex(target_index, method="ffill")


def duckdb_asof_align(
    source_frame: pd.DataFrame,
    ts_col: str,
    value_col: str,
    target_index: pd.DatetimeIndex,
) -> pd.Series:
    if source_frame.empty:
        return pd.Series(np.nan, index=target_index, dtype=float)

    frame = source_frame[[ts_col, value_col]].copy()
    frame[ts_col] = pd.to_datetime(frame[ts_col], utc=True)
    frame[value_col] = pd.to_numeric(frame[value_col], errors="coerce")
    frame = frame.dropna(subset=[ts_col]).sort_values(ts_col)
    if frame.empty:
        return pd.Series(np.nan, index=target_index, dtype=float)

    base = pd.DataFrame({"ts": pd.to_datetime(target_index, utc=True)})
    right = frame.rename(columns={ts_col: "src_ts", value_col: "src_value"})

    con = duckdb.connect()
    con.register("base_ts", base)
    con.register("src_ts", right)
    aligned = con.execute(
        """
        SELECT b.ts AS ts, s.src_value AS value
        FROM base_ts b
        ASOF LEFT JOIN src_ts s
        ON b.ts >= s.src_ts
        ORDER BY b.ts
        """
    ).df()
    return pd.Series(aligned["value"].to_numpy(dtype=float), index=target_index)


def merge_cross_assets(
    df: pd.DataFrame,
    cross_asset_path: Path | None,
    vix_csv: Path | None,
    warnings: list[str],
    knobs: dict[str, Any] | None = None,
) -> pd.DataFrame:
    knobs = dict(DEFAULT_INDICATOR_KNOBS if knobs is None else knobs)
    out = df.copy()
    idx = pd.DatetimeIndex(pd.to_datetime(out["ts"], utc=True))
    start = idx.min()
    end = idx.max()

    # Cross-asset trend codes plus the raw closes that compute_xa_continuous_features
    # needs for NQ rel-strength, ZN rate-pressure, and HG growth proxy (locked
    # 2026-05-11 gate-as-feature pivot).
    out["_nq_close"] = np.nan
    out["_zn_close"] = np.nan
    out["_hg_close"] = np.nan
    out["_6e_close"] = np.nan
    for symbol, col in (("NQ", "ml_xa_nq_code"), ("ZN", "ml_xa_zn_code"), ("6E", "ml_xa_6e_code")):
        out[col] = 0.0
    if cross_asset_path and cross_asset_path.exists():
        xa = pd.read_parquet(cross_asset_path)
        ts_col = "ts" if "ts" in xa.columns else "ts_event"
        xa[ts_col] = pd.to_datetime(xa[ts_col], utc=True)
        xa["close"] = pd.to_numeric(xa["close"], errors="coerce")
        xa = xa.dropna(subset=[ts_col, "close", "symbol"])
        # Cross-asset trend codes + raw closes (gate-as-feature pivot, locked
        # 2026-05-11). NQ/ZN/6E provide BOTH a trend code (for the agreement
        # count feature) AND a raw close (consumed by compute_xa_continuous_features).
        # HG provides close only. DXY (Yahoo) was removed 2026-05-11 — 6E is the
        # CME-native USD-pressure proxy now.
        xa_close_targets = (
            ("NQ", "ml_xa_nq_code", "_nq_close"),
            ("ZN", "ml_xa_zn_code", "_zn_close"),
            ("HG", None, "_hg_close"),  # close only, no trend code in existing schema
            ("6E", "ml_xa_6e_code", "_6e_close"),  # EUR/USD continuous; replaces DXY 2026-05-11
        )
        for symbol, code_col, close_col in xa_close_targets:
            sym = xa.loc[xa["symbol"].astype(str).eq(symbol), [ts_col, "close"]].sort_values(ts_col)
            if sym.empty:
                if code_col is not None:
                    warnings.append(f"cross-asset source missing {symbol}; {code_col}=0")
                else:
                    warnings.append(f"cross-asset source missing {symbol}; {close_col}=NaN")
                continue
            sym = sym.drop_duplicates(ts_col)
            close = sym.set_index(ts_col)["close"]
            if code_col is not None:
                code = xa_code(close)
                code_frame = code.rename("code").to_frame().reset_index()
                code_ts_col = code_frame.columns[0]
                out[code_col] = duckdb_asof_align(code_frame, code_ts_col, "code", idx).to_numpy(dtype=float)
            out[close_col] = duckdb_asof_align(sym, ts_col, "close", idx).to_numpy(dtype=float)
    else:
        warnings.append("cross-asset 1h source unavailable; NQ/ZN codes set to 0; HG/ZN/NQ/6E closes set to NaN")

    # DXY was removed 2026-05-11 — 6E.c.0 (Databento CME) replaces it as the
    # USD-pressure proxy. NQ/ZN/6E codes are computed in the cross-asset for-loop
    # above; 6E momentum z-score is derived in compute_xa_continuous_features.

    if vix_csv and vix_csv.exists():
        vix = pd.read_csv(vix_csv)
        date_col = "observation_date"
        value_col = "VIXCLS"
        vix[date_col] = pd.to_datetime(vix[date_col], utc=True)
        vix[value_col] = pd.to_numeric(vix[value_col], errors="coerce")
        vix_frame = vix.dropna(subset=[value_col])[[date_col, value_col]].sort_values(date_col)
        vix_aligned = duckdb_asof_align(vix_frame, date_col, value_col, idx)
        out["ml_xa_vix_pressure"] = close_movement_pressure(
            vix_aligned,
            int(_knob(knobs, "knob_vix_move_bars")),
            int(_knob(knobs, "knob_vix_atr_length")),
        ).to_numpy(dtype=float)
    else:
        out["ml_xa_vix_pressure"] = 0.0
        warnings.append("VIX CSV unavailable; VIX movement pressure set to 0")

    # nq_close used only for rolling correlation. Forward-fill only (no bfill —
    # bfill is a lookahead leak for the leading bars before the first NQ anchor).
    # Locked 2026-05-11.
    nq_close = pd.Series(out["_nq_close"], index=out.index).replace(0, np.nan).ffill()
    if nq_close.isna().all():
        nq_close = out["ml_xa_nq_code"].replace(0, np.nan).ffill().fillna(0.0)
        warnings.append("NQ close unavailable; ml_xa_corr_nq fell back to NQ trend code")
    out["ml_xa_corr_nq"] = (
        out["close"]
        .rolling(int(_knob(knobs, "knob_corr_length")), min_periods=int(_knob(knobs, "knob_corr_length")))
        .corr(nq_close)
        .replace([np.inf, -np.inf], np.nan)
        .fillna(0.0)
    )
    return out


def compute_xa_continuous_features(
    df: pd.DataFrame,
    warnings: list[str],
    knobs: dict[str, Any] | None = None,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Derive Phase 1 continuous cross-asset features and per-symbol freshness.

    Locked 2026-05-11 gate-as-feature pivot. Replaces the brittle XA boolean
    gate (knob_xa_min_agreement) with normalized continuous features AG can
    weigh per-bar.

    Adds:
      ml_xa_nq_rel_strength_atr   — session-return diff (NQ vs ES), ATR-percent normalized
      ml_xa_dxy_momentum_zscore   — 16-bar rolling Z of DXY log-returns
      ml_xa_zn_rate_pressure      — 4-bar ZN price change normalized by 20-bar return stdev
      ml_xa_hg_growth_proxy       — sma5 of 20-bar HG percent change

    Returns (augmented_df, freshness_dict). The freshness_dict records, per
    cross-asset symbol, max forward-fill age in bars and presence coverage.
    Session boundaries use UTC midnight as a coarse proxy for trading-day open
    (documented limitation; ES Globex session is 23:00 UTC-prior to 22:00 UTC).
    """
    knobs = dict(DEFAULT_INDICATOR_KNOBS if knobs is None else knobs)
    out = df.copy()
    idx = pd.DatetimeIndex(pd.to_datetime(out["ts"], utc=True))
    es_close = out["close"].astype(float).reset_index(drop=True)
    es_atr14 = out["ml_atr14"].astype(float).reset_index(drop=True)
    work_index = pd.RangeIndex(len(out))
    es_close.index = work_index
    es_atr14.index = work_index

    utc_day = pd.Series(idx.floor("D"), index=work_index)

    # --- Symbol-aware freshness ---
    # FF age approximation: count consecutive bars where the value did not
    # change from the prior bar. For 1h cross-asset closes against 15m bars,
    # the "natural" FF age inside a single hour is up to 3 bars; threshold of
    # 5 catches >1h source gaps.
    freshness: dict[str, Any] = {}
    # All four cross-asset sources are CME 1h via Databento (locked 2026-05-11).
    # DXY (Yahoo) was removed; 6E is the USD-pressure proxy.
    SYMBOL_THRESHOLDS = {
        "_nq_close": 5,
        "_zn_close": 5,
        "_hg_close": 5,
        "_6e_close": 5,
    }
    for col, threshold in SYMBOL_THRESHOLDS.items():
        if col not in out.columns:
            freshness[col] = {"present": False}
            continue
        s = out[col].astype(float).reset_index(drop=True)
        s.index = work_index
        present_count = int(s.notna().sum())
        if present_count == 0:
            freshness[col] = {"present": False, "coverage_fraction": 0.0}
            warnings.append(f"freshness: {col} all-NaN")
            continue
        diff = s.diff().fillna(0.0).abs()
        changed = diff > 0
        run_groups = changed.cumsum()
        ff_age = (~changed).astype(int).groupby(run_groups).cumcount()
        max_age = int(ff_age.max())
        freshness[col] = {
            "present": True,
            "coverage_fraction": float(present_count / max(len(s), 1)),
            "max_forward_fill_age_bars": max_age,
        }
        if max_age > threshold:
            warnings.append(
                f"freshness: {col} max forward-fill age {max_age} > {threshold} bars"
            )

    # --- ml_xa_nq_rel_strength_atr ---
    if "_nq_close" in out.columns and out["_nq_close"].notna().any():
        nq_close = out["_nq_close"].astype(float).reset_index(drop=True)
        nq_close.index = work_index
        es_day_open = es_close.groupby(utc_day).transform("first")
        nq_day_open = nq_close.groupby(utc_day).transform("first")
        es_session_return = (es_close / es_day_open.replace(0, np.nan) - 1.0).replace([np.inf, -np.inf], np.nan)
        nq_session_return = (nq_close / nq_day_open.replace(0, np.nan) - 1.0).replace([np.inf, -np.inf], np.nan)
        rel_return = nq_session_return - es_session_return
        atr_pct = (es_atr14 / es_close.replace(0, np.nan)).replace(0, np.nan)
        rel_strength = (rel_return / atr_pct).replace([np.inf, -np.inf], np.nan).fillna(0.0)
        out["ml_xa_nq_rel_strength_atr"] = rel_strength.to_numpy(dtype=float)
    else:
        out["ml_xa_nq_rel_strength_atr"] = 0.0
        warnings.append("ml_xa_nq_rel_strength_atr: NQ close unavailable, set to 0")

    # ml_xa_dxy_momentum_zscore removed 2026-05-11 — 6E momentum (below) replaces.

    # --- ml_xa_zn_rate_pressure ---
    # ZN price down => yields up => tightening; we sign the metric so positive
    # means rates are pressuring risk. Normalized by 20-bar return stdev
    # because the loader has ZN close only (no OHLC for a real ATR).
    if "_zn_close" in out.columns and out["_zn_close"].notna().any():
        zn_close = out["_zn_close"].astype(float).reset_index(drop=True)
        zn_close.index = work_index
        zn_returns = zn_close.pct_change().replace([np.inf, -np.inf], np.nan)
        zn_return_std = zn_returns.rolling(20, min_periods=20).std()
        zn_return_4 = (
            (zn_close.shift(4) - zn_close)
            / zn_close.shift(4).replace(0, np.nan)
        )
        zn_pressure = (zn_return_4 / zn_return_std.replace(0, np.nan)).replace([np.inf, -np.inf], np.nan).fillna(0.0)
        out["ml_xa_zn_rate_pressure"] = zn_pressure.to_numpy(dtype=float)
    else:
        out["ml_xa_zn_rate_pressure"] = 0.0
        warnings.append("ml_xa_zn_rate_pressure: ZN close unavailable, set to 0")

    # --- ml_xa_hg_growth_proxy ---
    if "_hg_close" in out.columns and out["_hg_close"].notna().any():
        hg_close = out["_hg_close"].astype(float).reset_index(drop=True)
        hg_close.index = work_index
        hg_pct20 = hg_close.pct_change(20).replace([np.inf, -np.inf], np.nan)
        out["ml_xa_hg_growth_proxy"] = (
            hg_pct20.rolling(5, min_periods=5).mean().fillna(0.0).to_numpy(dtype=float)
        )
    else:
        out["ml_xa_hg_growth_proxy"] = 0.0
        warnings.append("ml_xa_hg_growth_proxy: HG close unavailable, set to 0")

    # --- ml_xa_6e_momentum_zscore ---
    # 6E (EUR/USD futures) is a CME-native inverse USD-pressure proxy. Same
    # 16-bar rolling Z formula as DXY momentum so AG sees a directly
    # comparable signal from two independent USD sources. Positive z = 6E up
    # = USD weakening; AG learns the sign per regime.
    if "_6e_close" in out.columns and out["_6e_close"].notna().any():
        sixe_close = out["_6e_close"].astype(float).reset_index(drop=True)
        sixe_close.index = work_index
        sixe_logret = np.log(sixe_close.replace(0, np.nan)) - np.log(sixe_close.shift(1).replace(0, np.nan))
        mu_6e = sixe_logret.rolling(16, min_periods=16).mean()
        sigma_6e = sixe_logret.rolling(16, min_periods=16).std()
        z_6e = (sixe_logret - mu_6e) / sigma_6e.replace(0, np.nan)
        out["ml_xa_6e_momentum_zscore"] = (
            z_6e.replace([np.inf, -np.inf], np.nan).fillna(0.0).to_numpy(dtype=float)
        )
    else:
        out["ml_xa_6e_momentum_zscore"] = 0.0
        warnings.append("ml_xa_6e_momentum_zscore: 6E close unavailable, set to 0")

    return out, freshness


def trade_members_for_window(zip_path: Path, start: pd.Timestamp, end: pd.Timestamp) -> list[str]:
    selected: list[str] = []
    with zipfile.ZipFile(zip_path) as zf:
        for name in zf.namelist():
            m = TRADES_MEMBER_RE.search(name)
            if not m:
                continue
            file_start = pd.Timestamp(m.group(1), tz="UTC")
            file_end = pd.Timestamp(m.group(2), tz="UTC") + pd.Timedelta(days=1)
            if file_end >= start and file_start <= end:
                selected.append(name)
    return selected


def _outright_pattern_for_root(symbol_root: str) -> re.Pattern[str]:
    root = str(symbol_root).upper().strip()
    if root not in OUTRIGHT_ROOT_PATTERNS:
        raise ValueError(f"Unsupported symbol root for order-flow filter: {symbol_root!r}")
    return OUTRIGHT_ROOT_PATTERNS[root]


def read_trade_chunks(
    zip_path: Path,
    members: list[str],
    start: pd.Timestamp,
    end: pd.Timestamp,
    symbol_root: str,
):
    import zstandard as zstd

    symbol_re = _outright_pattern_for_root(symbol_root)
    usecols = ["ts_event", "side", "price", "size", "symbol"]
    with zipfile.ZipFile(zip_path) as zf:
        for member in members:
            with zf.open(member) as raw:
                reader = zstd.ZstdDecompressor().stream_reader(raw)
                text = io.TextIOWrapper(reader, encoding="utf-8")
                for chunk in pd.read_csv(text, usecols=usecols, chunksize=500_000):
                    chunk["ts_event"] = pd.to_datetime(chunk["ts_event"], utc=True, format="ISO8601")
                    chunk = chunk.loc[(chunk["ts_event"] >= start) & (chunk["ts_event"] <= end)]
                    if chunk.empty:
                        continue
                    chunk = chunk.loc[chunk["symbol"].astype(str).str.match(symbol_re)]
                    if chunk.empty:
                        continue
                    chunk["price"] = pd.to_numeric(chunk["price"], errors="coerce")
                    chunk["size"] = pd.to_numeric(chunk["size"], errors="coerce").fillna(0.0)
                    chunk = chunk.dropna(subset=["price"])
                    if not chunk.empty:
                        yield chunk


def build_orderflow_features(
    df: pd.DataFrame,
    trades_zip: Path | None,
    gate_mode: str,
    warnings: list[str],
    symbol_root: str,
    bar_freq: str,
    knobs: dict[str, Any] | None = None,
) -> pd.DataFrame:
    knobs = dict(DEFAULT_INDICATOR_KNOBS if knobs is None else knobs)
    out = df.copy()
    idx = pd.DatetimeIndex(pd.to_datetime(out["ts"], utc=True))
    zeros = np.zeros(len(out), dtype=float)
    if not trades_zip or not trades_zip.exists():
        warnings.append("Databento trades zip unavailable; order-flow features set to 0")
        return assign_empty_orderflow(out, zeros)

    freq_delta = pd.to_timedelta(bar_freq)
    start = idx.min()
    end = idx.max() + freq_delta
    members = trade_members_for_window(trades_zip, start, end)
    if not members:
        warnings.append("No trades zip members overlap selected window; order-flow features set to 0")
        return assign_empty_orderflow(out, zeros)

    bar_aggs: list[pd.DataFrame] = []
    price_aggs: list[pd.DataFrame] = []
    for chunk in read_trade_chunks(trades_zip, members, start, end, symbol_root):
        chunk["bar_ts"] = chunk["ts_event"].dt.floor(bar_freq)
        side = chunk["side"].astype(str)
        size = chunk["size"].astype(float)
        chunk["buy_vol"] = np.where(side.eq("B"), size, 0.0)
        chunk["sell_vol"] = np.where(side.eq("A"), size, 0.0)
        chunk["signed_delta"] = chunk["buy_vol"] - chunk["sell_vol"]
        bar_aggs.append(
            chunk.groupby("bar_ts", as_index=True).agg(
                buy_vol=("buy_vol", "sum"),
                sell_vol=("sell_vol", "sum"),
                delta=("signed_delta", "sum"),
                total_trade_volume=("size", "sum"),
                trade_count=("size", "size"),
            )
        )
        price_aggs.append(chunk.groupby(["bar_ts", "price"], as_index=False)["size"].sum())

    if not bar_aggs:
        warnings.append(f"No {symbol_root} outright trade rows after filtering; order-flow features set to 0")
        return assign_empty_orderflow(out, zeros)

    bars = pd.concat(bar_aggs).groupby(level=0).sum().sort_index()
    bars = bars.reindex(idx, fill_value=0.0)
    profile = build_volume_profile(price_aggs, idx)
    bars = bars.join(profile, how="left")

    total = bars["buy_vol"] + bars["sell_vol"]
    delta = bars["delta"].astype(float)
    delta_pct = (delta / total.replace(0, np.nan) * 100.0).fillna(0.0)
    trade_vol = bars["total_trade_volume"].astype(float)
    volume_spike = (trade_vol / trade_vol.rolling(ORDERFLOW_ROLLING_LEN, min_periods=1).mean().replace(0, np.nan)).fillna(0.0)
    atr = out["ml_atr14"].replace(0, np.nan)
    atr_arr = atr.to_numpy(dtype=float)
    poc = bars["poc_price"]
    vah = bars["vah_price"]
    val = bars["val_price"]
    cvd = delta.groupby(idx.date).cumsum()

    close_arr = out["close"].to_numpy(dtype=float)
    high_arr = out["high"].to_numpy(dtype=float)
    low_arr = out["low"].to_numpy(dtype=float)
    vah_arr = vah.to_numpy(dtype=float)
    val_arr = val.to_numpy(dtype=float)
    cvd_arr = cvd.to_numpy(dtype=float)
    cvd_shift_arr = cvd.shift(10).to_numpy(dtype=float)
    delta_pct_arr = delta_pct.to_numpy(dtype=float)
    volume_spike_arr = volume_spike.to_numpy(dtype=float)

    out["ml_fp_delta_pct"] = delta_pct_arr
    poc_arr = poc.to_numpy(dtype=float)
    out["ml_fp_poc_dist_atr"] = ((close_arr - poc_arr) / atr_arr)
    out["ml_fp_poc_dist_atr"] = out["ml_fp_poc_dist_atr"].replace([np.inf, -np.inf], np.nan).fillna(0.0)
    out["ml_fp_va_position"] = np.where(close_arr > vah_arr, 1.0, np.where(close_arr < val_arr, -1.0, 0.0))
    out["ml_cvd_div_bull"] = (
        (low_arr < np.r_[np.full(10, np.nan), low_arr[:-10]])
        & (cvd_arr > cvd_shift_arr)
    ).astype(float)
    out["ml_cvd_div_bear"] = (
        (high_arr > np.r_[np.full(10, np.nan), high_arr[:-10]])
        & (cvd_arr < cvd_shift_arr)
    ).astype(float)

    out["ml_delta_imbalance_pct"] = out["ml_fp_delta_pct"]
    out["ml_delta_acceleration"] = delta.diff().fillna(0.0).to_numpy(dtype=float)
    out["ml_aggressor_pulse"] = (delta / delta.rolling(ORDERFLOW_ROLLING_LEN, min_periods=5).std(ddof=0).replace(0, np.nan)).replace([np.inf, -np.inf], np.nan).fillna(0.0).to_numpy(dtype=float)
    out["ml_volume_spike_ratio"] = volume_spike.to_numpy(dtype=float)
    poc_shift = np.r_[np.nan, np.diff(poc_arr)] / atr_arr
    out["ml_poc_shift"] = np.nan_to_num(poc_shift, nan=0.0, posinf=0.0, neginf=0.0)
    compressed_range = ((high_arr - low_arr) / atr_arr)
    compressed_range = np.nan_to_num(compressed_range, nan=0.0, posinf=0.0, neginf=0.0)
    out["ml_absorption_candidate"] = (
        (np.abs(delta_pct_arr) >= float(_knob(knobs, "knob_fp_absorption_delta_pct")))
        & (volume_spike_arr >= float(_knob(knobs, "knob_fp_event_vol_spike")))
        & (compressed_range <= float(_knob(knobs, "knob_fp_compressed_range_atr")))
    ).astype(float)
    out["ml_flush_candidate"] = (
        (np.abs(delta_pct_arr) >= float(_knob(knobs, "knob_fp_flush_delta_pct")))
        & (volume_spike_arr >= float(_knob(knobs, "knob_fp_event_vol_spike")))
        & (compressed_range > float(_knob(knobs, "knob_fp_compressed_range_atr")))
    ).astype(float)

    if gate_mode in {"smoke", "strict"} and float(out["ml_fp_delta_pct"].abs().sum()) == 0.0:
        raise RuntimeError("Order-flow reconstruction produced all-zero fp delta")
    return out


def assign_empty_orderflow(df: pd.DataFrame, zeros: np.ndarray) -> pd.DataFrame:
    out = df.copy()
    for col in (
        "ml_fp_delta_pct",
        "ml_fp_poc_dist_atr",
        "ml_fp_va_position",
        "ml_cvd_div_bull",
        "ml_cvd_div_bear",
        "ml_delta_imbalance_pct",
        "ml_delta_acceleration",
        "ml_aggressor_pulse",
        "ml_absorption_candidate",
        "ml_flush_candidate",
        "ml_volume_spike_ratio",
        "ml_poc_shift",
    ):
        out[col] = zeros
    return out


def build_volume_profile(price_aggs: list[pd.DataFrame], target_index: pd.DatetimeIndex) -> pd.DataFrame:
    prices = pd.concat(price_aggs, ignore_index=True)
    prices = prices.groupby(["bar_ts", "price"], as_index=False)["size"].sum()
    rows: list[dict[str, Any]] = []
    for bar_ts, group in prices.groupby("bar_ts", sort=True):
        total = float(group["size"].sum())
        if total <= 0:
            continue
        sorted_by_vol = group.sort_values("size", ascending=False)
        poc_price = float(sorted_by_vol.iloc[0]["price"])
        chosen = sorted_by_vol.loc[sorted_by_vol["size"].cumsum() <= total * 0.70]
        if chosen.empty:
            chosen = sorted_by_vol.head(1)
        rows.append(
            {
                "bar_ts": bar_ts,
                "poc_price": poc_price,
                "vah_price": float(chosen["price"].max()),
                "val_price": float(chosen["price"].min()),
            }
        )
    profile = pd.DataFrame(rows)
    if profile.empty:
        return pd.DataFrame(index=target_index, columns=["poc_price", "vah_price", "val_price"], dtype=float)
    profile["bar_ts"] = pd.to_datetime(profile["bar_ts"], utc=True)
    return profile.set_index("bar_ts").reindex(target_index)


def finalize_entries(df: pd.DataFrame, knobs: dict[str, Any] | None = None) -> pd.DataFrame:
    # Gate-as-feature pivot (locked 2026-05-11):
    # - Candidate trigger = fib touch/reclaim at .500/.618/.786 AND MA bias aligned.
    # - XA agreement and liquidity recency are NO LONGER hard filters; they are
    #   continuous ML features (ml_xa_*_agreement, ml_recent_liq_*, ml_liq_*,
    #   ml_swept_*, ml_reclaimed_*, ml_xa_nq_rel_strength_atr, etc.). AG learns
    #   how to weight them per bar.
    # - knob_use_xa_gate and knob_use_liq_gate remain in the schema so a future
    #   V9 Core profile sweep can re-enable them, but their defaults are now False.
    knobs = dict(DEFAULT_INDICATOR_KNOBS if knobs is None else knobs)
    out = df.copy()
    ma_long_ok = (out["ml_ma_bias"] > 0) if bool(_knob(knobs, "knob_use_ma_gate")) else True
    ma_short_ok = (out["ml_ma_bias"] < 0) if bool(_knob(knobs, "knob_use_ma_gate")) else True
    # Agreement features are emitted as ML inputs (not gates), and under the
    # 2026-05-12 lean contract they are computed from NQ + 6E only.
    # DXY was removed 2026-05-11; 6E remains as the FX proxy.
    xa_long_agreement = (
        (out["ml_xa_nq_code"] > 0).astype(int)
        + (out["ml_xa_6e_code"] > 0).astype(int)
    )
    xa_short_agreement = (
        (out["ml_xa_nq_code"] < 0).astype(int)
        + (out["ml_xa_6e_code"] < 0).astype(int)
    )
    # Gate-as-feature pivot: drop xa_*_ok and liq_*_ok from the qualification
    # chain. If the knobs are explicitly re-enabled (defaults are now False),
    # honor them — otherwise pass through.
    use_xa_gate = bool(_knob(knobs, "knob_use_xa_gate"))
    use_liq_gate = bool(_knob(knobs, "knob_use_liq_gate"))
    if use_xa_gate:
        xa_long_ok = xa_long_agreement >= int(_knob(knobs, "knob_xa_min_agreement"))
        xa_short_ok = xa_short_agreement >= int(_knob(knobs, "knob_xa_min_agreement"))
    else:
        xa_long_ok = True
        xa_short_ok = True
    if use_liq_gate:
        liq_long_ok = out["__recent_liq_bull"]
        liq_short_ok = out["__recent_liq_bear"]
    else:
        liq_long_ok = True
        liq_short_ok = True
    long_ok = out["__is_valid"] & out["__trigger_long"] & ma_long_ok & xa_long_ok & liq_long_ok
    short_ok = out["__is_valid"] & out["__trigger_short"] & ma_short_ok & xa_short_ok & liq_short_ok
    out["ml_xa_long_agreement"] = xa_long_agreement.astype(float)
    out["ml_xa_short_agreement"] = xa_short_agreement.astype(float)
    out["ml_entry_long_trigger"] = long_ok.astype(float)
    out["ml_entry_short_trigger"] = short_ok.astype(float)
    return out.drop(columns=[c for c in out.columns if c.startswith("__")])


def validate_core_frame(df: pd.DataFrame, gate_mode: str) -> None:
    stale = [col for col in ("ml_xa_dx_code", "ml_bar_delta", "ml_net_delta_20") if col in df.columns]
    if stale:
        raise RuntimeError(f"stale/banned columns present: {stale}")
    missing = [col for col in ML_FEATURES if col not in df.columns]
    if missing:
        raise RuntimeError(f"missing locked ML_FEATURES: {missing}")
    if "ml_xa_6e_code" not in df.columns:
        raise RuntimeError("6E feature column missing")
    if gate_mode == "strict":
        all_null = [col for col in ML_FEATURES if df[col].isna().all()]
        if all_null:
            raise RuntimeError(f"all-null feature columns: {all_null}")
    if gate_mode == "strict":
        # Current chart-canonical entries are fib triggers filtered by MA,
        # liquidity recency, and NQ/6E agreement. This check only prevents
        # near-dead entry output after contract/default changes.
        entries = int(df["ml_entry_long_trigger"].sum() + df["ml_entry_short_trigger"].sum())
        if entries < 250:
            raise RuntimeError(f"strict gate failed: only {entries} MA-filtered fib trigger candidates (floor 250)")
        if "_nq_close" not in df.columns or df["_nq_close"].isna().all():
            raise RuntimeError("strict gate failed: NQ close unavailable for ml_xa_corr_nq")
        if float(df["ml_fp_delta_pct"].abs().sum()) == 0.0:
            raise RuntimeError("strict gate failed: footprint delta feature is all zero")


def validate_export_with_pandera(df: pd.DataFrame) -> None:
    # Label-construction inputs (not ML_FEATURES, per the Option-B contract
    # locked 2026-05-12). The five fib-ladder TPs are required in the export
    # CSV so train_v9_locked.build_trade_dataset can size combos directly.
    label_input_cols = ["ml_trade_tp1", "ml_trade_tp2", "ml_trade_tp3", "ml_trade_tp4", "ml_trade_tp5"]
    required_cols = ["ts", "open", "high", "low", "close", "volume",
                     *label_input_cols, *ML_FEATURES]
    missing = [col for col in required_cols if col not in df.columns]
    if missing:
        raise RuntimeError(f"pandera export schema missing columns: {missing}")

    bool_cols = {
        "knob_auto_tune_zz",
        "knob_use_pattern_confirm",
        "knob_use_liq_gate",
        "knob_use_ma_gate",
        "knob_use_session_vwap",
        "knob_use_xa_gate",
        "knob_use_footprint",
        "profile_is_ma_base",
    }
    string_cols = {
        "profile_id",
        "profile_mode",
        "knob_nq_symbol",
        "knob_zn_symbol",
        "knob_6e_symbol",
        "knob_vix_symbol",
        "knob_zn_gate_direction",
    }

    schema_cols: dict[str, pa.Column] = {
        "ts": pa.Column(pa.DateTime, nullable=False, coerce=True),
    }
    for col in required_cols:
        if col == "ts":
            continue
        if col in bool_cols:
            schema_cols[col] = pa.Column(pa.Bool, nullable=True, coerce=True)
        elif col in string_cols:
            schema_cols[col] = pa.Column(pa.String, nullable=True, coerce=True)
        else:
            schema_cols[col] = pa.Column(float, nullable=True, coerce=True)

    export_schema = pa.DataFrameSchema(schema_cols, strict=False, coerce=True)
    with config_context(validation_enabled=True, validation_depth=PANDERA_CONTRACT_DEPTH):
        validated = export_schema.validate(df[required_cols].copy(), lazy=True)

    if not validated["ts"].is_monotonic_increasing:
        raise RuntimeError("pandera export schema failed: ts is not monotonically increasing")

    non_numeric = [
        col
        for col in required_cols
        if col not in {"ts", *string_cols, *bool_cols}
        and not pd.api.types.is_numeric_dtype(validated[col])
    ]
    if non_numeric:
        raise RuntimeError(f"pandera export schema failed dtype policy for numeric columns: {non_numeric}")

    required_label_policy = [
        "ml_entry_long_trigger",
        "ml_entry_short_trigger",
        "ml_trade_entry",
        "ml_trade_stop",
        "ml_trade_tp1",
        "ml_trade_tp2",
        "ml_trade_tp3",
        "ml_trade_tp4",
        "ml_trade_tp5",
    ]
    missing_policy = [col for col in required_label_policy if col not in validated.columns]
    if missing_policy:
        raise RuntimeError(f"pandera export schema missing label-policy columns: {missing_policy}")


def generate_profile_artifact(
    df: pd.DataFrame,
    out_dir: Path,
    symbol_root: str,
    timeframe: str,
) -> tuple[Path, int, bool]:
    timeframe_text = str(timeframe).strip().removesuffix("m")
    profile_path = out_dir / f"{symbol_root.lower()}_{timeframe_text}m_core.profile.html"
    profile_limit = 50_000
    sampled = len(df) > profile_limit
    profile_frame = df.head(profile_limit).copy() if sampled else df.copy()

    report = ProfileReport(
        profile_frame,
        title=f"Warbird Pro V9 Core Profile ({symbol_root} {timeframe_text}m)",
        minimal=True,
        progress_bar=False,
    )
    report.to_file(str(profile_path))
    return profile_path, int(len(profile_frame)), sampled


def validate_manifest_contract(manifest: dict[str, Any]) -> None:
    manifest_schema = pa.DataFrameSchema(
        {
            "repo_commit": pa.Column(pa.String, nullable=False, coerce=True),
            "symbol": pa.Column(pa.String, nullable=False, coerce=True),
            "symbol_root": pa.Column(pa.String, nullable=False, coerce=True),
            "timeframe": pa.Column(pa.String, nullable=False, coerce=True),
            "trigger_family": pa.Column(pa.String, nullable=False, coerce=True),
            "source_kind": pa.Column(
                pa.String,
                nullable=False,
                coerce=True,
                checks=pa.Check(lambda s: s.str.startswith("DATABENTO_")),
            ),
            "source_bars": pa.Column(pa.String, nullable=False, coerce=True),
            "label_column": pa.Column(pa.String, nullable=False, coerce=True),
            "feature_count_locked": pa.Column(int, nullable=False, coerce=True, checks=pa.Check.eq(len(ML_FEATURES))),
            "row_count": pa.Column(int, nullable=False, coerce=True, checks=pa.Check.ge(1)),
            "entry_long_count": pa.Column(int, nullable=False, coerce=True, checks=pa.Check.ge(0)),
            "entry_short_count": pa.Column(int, nullable=False, coerce=True, checks=pa.Check.ge(0)),
            "profiling_report_path": pa.Column(pa.String, nullable=False, coerce=True),
            "profiling_rows_profiled": pa.Column(int, nullable=False, coerce=True, checks=pa.Check.ge(1)),
        },
        strict=False,
        coerce=True,
    )
    with config_context(validation_enabled=True, validation_depth=PANDERA_CONTRACT_DEPTH):
        manifest_schema.validate(pd.DataFrame([manifest]), lazy=True)

    serialized = json.dumps(manifest).lower()
    banned = [token for token in FORBIDDEN_LINEAGE_TOKENS if token in serialized]
    if banned:
        raise RuntimeError(f"manifest contract failed forbidden lineage tokens: {sorted(set(banned))}")


def write_outputs(
    df: pd.DataFrame,
    out_dir: Path,
    symbol: str,
    timeframe: str,
    source: Path,
    trades_zip: Path | None,
    profiling_report_path: Path,
    profiling_rows_profiled: int,
    profiling_sampled: bool,
    manifest_extra: dict[str, Any],
) -> tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    symbol_root = normalize_symbol_root(symbol)
    timeframe_text = str(timeframe).strip().removesuffix("m")
    csv_path = out_dir / f"{symbol_root.lower()}_{timeframe_text}m_core.csv"
    manifest_path = csv_path.with_suffix(".manifest.json")
    export = df.copy()
    # 2026-05-12 lean-cut: drop columns the ETL still computes (for diagnostic
    # continuity) but which the trainer's locked ML_FEATURES list excludes.
    # Driving from a single DROPPED_FEATURES_2026_05_12 tuple keeps the CSV
    # column set, manifest feature_columns_locked, and trainer ML_FEATURES
    # in lockstep.
    dropped_present = [c for c in DROPPED_FEATURES_2026_05_12 if c in export.columns]
    if dropped_present:
        export = export.drop(columns=dropped_present)
    export["ts"] = pd.to_datetime(export["ts"], utc=True).dt.strftime("%Y-%m-%dT%H:%M:%S%z")
    con = duckdb.connect()
    con.register("export_df", export)
    order_cols = [col for col in ("ts", "profile_id") if col in export.columns]
    order_clause = f" ORDER BY {', '.join(order_cols)}" if order_cols else ""
    con.execute(
        f"COPY (SELECT * FROM export_df{order_clause}) TO '{duckdb_path_literal(csv_path)}' (HEADER, DELIMITER ',')"
    )
    manifest = {
        "repo_commit": repo_commit(),
        "symbol": symbol_root,
        "symbol_root": symbol_root,
        "timeframe": timeframe_text,
        "trigger_family": TRIGGER_FAMILY,
        "source_kind": f"DATABENTO_{symbol_root}_CORE_ETL",
        "source_bars": str(source),
        "source_trades_zip": str(trades_zip) if trades_zip else None,
        "pine_file": PINE_FILE,
        "label_column": LABEL_COL,
        "feature_count_locked": len(ML_FEATURES),
        "feature_columns_locked": ML_FEATURES,
        "row_count": int(len(df)),
        "entry_long_count": int(df["ml_entry_long_trigger"].sum()),
        "entry_short_count": int(df["ml_entry_short_trigger"].sum()),
        "ts_first": pd.to_datetime(df["ts"], utc=True).min().isoformat(),
        "ts_last": pd.to_datetime(df["ts"], utc=True).max().isoformat(),
        "sha256": sha256_file(csv_path),
        "profiling_report_path": str(profiling_report_path),
        "profiling_rows_profiled": int(profiling_rows_profiled),
        "profiling_sampled": bool(profiling_sampled),
        "data_layer_stack": {
            "duckdb": LOCKED_DUCKDB_VERSION,
            "pandera": LOCKED_PANDERA_VERSION,
            "fg_data_profiling": LOCKED_DATA_PROFILING_VERSION,
        },
        "build_utc": datetime.now(timezone.utc).isoformat(),
        **manifest_extra,
    }
    validate_manifest_contract(manifest)
    manifest_path.write_text(json.dumps(manifest, indent=2, default=str))
    return csv_path, manifest_path


def main() -> int:
    ap = argparse.ArgumentParser(description="Build Warbird Pro V9 Core 5m/15m dataset")
    ap.add_argument("--symbol", choices=["ES"], default="ES")
    ap.add_argument("--timeframe", choices=["5", "15"], default="5")
    ap.add_argument("--source", type=Path, default=None)
    ap.add_argument("--trades-zip", type=Path, default=DEFAULT_TRADES_ZIP)
    ap.add_argument("--cross-asset-1h", type=Path, default=DEFAULT_CROSS_ASSET_1H)
    ap.add_argument("--vix-csv", type=Path, default=DEFAULT_VIX_CSV)
    ap.add_argument("--out-dir", type=Path, default=EXPORTS_DIR)
    ap.add_argument("--start", default=None)
    ap.add_argument("--end", default=None)
    ap.add_argument("--base-regime-only", action="store_true",
                    help="Allow order-flow features to be zero-filled for a base/regime build.")
    ap.add_argument("--gate-mode", choices=["schema", "smoke", "strict"], default="smoke")
    ap.add_argument("--profile-mode", choices=["base", "ma-grid"], default="base",
                    help="Emit one base indicator profile or the full EMA/SMA 10-up/10-down grid.")
    args = ap.parse_args()
    symbol_root = normalize_symbol_root(args.symbol)
    source_path = args.source or default_source_for_symbol(symbol_root)

    if not source_path.exists():
        raise SystemExit(f"Source bars not found: {source_path}")

    start = utc_ts(args.start)
    end = utc_ts(args.end)
    raw = load_bars(source_path)
    raw = duckdb_sort_filter_frame(raw, start, end)
    if raw.empty:
        raise SystemExit("No bar rows in selected window")

    timeframe_min = int(args.timeframe)
    bar_freq = f"{timeframe_min}min"

    bars_tf = normalize_to_timeframe(raw, timeframe_min)
    print(f"bars: {len(raw):,} source rows -> {len(bars_tf):,} {timeframe_min}m rows")
    print(f"range: {bars_tf['ts'].min()} -> {bars_tf['ts'].max()}")

    warnings: list[str] = []
    trades_zip = None if args.base_regime_only else args.trades_zip
    profiles = generate_indicator_profiles(args.profile_mode)
    profile_frames: list[pd.DataFrame] = []
    cross_asset_freshness: dict[str, Any] = {}
    for i, profile in enumerate(profiles):
        profile_features = compute_base_features(bars_tf, profile)
        profile_features = merge_cross_assets(
            profile_features,
            args.cross_asset_1h,
            args.vix_csv,
            warnings,
            profile,
        )
        # All profiles share the same underlying cross-asset data, so freshness
        # is computed once from the first profile (locked 2026-05-11).
        profile_features, freshness = compute_xa_continuous_features(
            profile_features, warnings, profile
        )
        if i == 0:
            cross_asset_freshness = freshness
        profile_features = build_orderflow_features(
            profile_features,
            trades_zip,
            args.gate_mode,
            warnings,
            symbol_root=symbol_root,
            bar_freq=bar_freq,
            knobs=profile,
        )
        profile_frames.append(finalize_entries(profile_features, profile))
    features = pd.concat(profile_frames, ignore_index=True).sort_values(["ts", "profile_id"]).reset_index(drop=True)

    validate_core_frame(features, args.gate_mode)
    validate_export_with_pandera(features)
    profile_path, profile_rows, profile_sampled = generate_profile_artifact(
        features,
        args.out_dir,
        symbol_root,
        args.timeframe,
    )
    csv_path, manifest_path = write_outputs(
        features,
        args.out_dir,
        symbol_root,
        args.timeframe,
        source_path,
        trades_zip,
        profile_path,
        profile_rows,
        profile_sampled,
        {
            "gate_mode": args.gate_mode,
            "base_regime_only": bool(args.base_regime_only),
            "usd_pressure_source": "Databento GLBX.MDP3 6E.c.0 continuous (replaces Yahoo DXY as of 2026-05-11)",
            "cross_asset_source": str(args.cross_asset_1h) if args.cross_asset_1h else None,
            "cross_asset_freshness": cross_asset_freshness,
            "profile_mode": args.profile_mode,
            "profile_count": len(profiles),
            "indicator_knob_columns": KNOB_COLUMNS,
            "ma_fast_base": MA_FAST_BASE,
            "ma_slow_base": MA_SLOW_BASE,
            "ma_fast_grid": MA_FAST_GRID,
            "ma_slow_grid": MA_SLOW_GRID,
            "warnings": warnings,
            "architecture": "chart_canonical_settings_2026_05_16",
            "entry_qualification_rule": "fib_trigger_AND_ma_bias_AND_liquidity_AND_nq_6e_agreement",
            "xa_zn_rate_pressure_denominator": "rolling_20bar_return_stdev",
            "orderflow_candidate_thresholds": {
                "rolling_len": ORDERFLOW_ROLLING_LEN,
                "absorption_delta_pct": ORDERFLOW_ABSORPTION_DELTA_PCT,
                "flush_delta_pct": ORDERFLOW_FLUSH_DELTA_PCT,
                "event_volume_spike": ORDERFLOW_EVENT_VOLUME_SPIKE,
                "compressed_range_atr": ORDERFLOW_COMPRESSED_RANGE_ATR,
            },
            "extra_candidate_features": [
                "ml_delta_imbalance_pct",
                "ml_delta_acceleration",
                "ml_aggressor_pulse",
                "ml_absorption_candidate",
                "ml_flush_candidate",
                "ml_volume_spike_ratio",
                "ml_poc_shift",
                "ml_fib_touch_level_code",
                "ml_fib_pierce_atr",
                "ml_fib_close_reclaim_atr",
                "ml_fib_reaction_code",
                "ml_trade_entry",
                "ml_trade_stop",
                "ml_trade_tp1",
                "ml_trade_tp2",
                "ml_trade_tp3",
                "ml_trade_tp4",
                "ml_trade_tp5",
            ],
        },
    )
    print(f"entries: long={int(features['ml_entry_long_trigger'].sum())} short={int(features['ml_entry_short_trigger'].sum())}")
    if warnings:
        print("warnings:")
        for warning in warnings:
            print(f"  - {warning}")
    print(f"wrote {csv_path}")
    print(f"wrote {manifest_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
