#!/usr/bin/env python3
"""Warbird Pro V9 Optuna profile.

This lane models ATR/risk exits from manifest-backed ES/MES training rows for
Warbird Pro V9. TradingView exports may provide Pine trigger telemetry, and
Databento may provide market-data training rows. Databento is a data supplier,
not the Pine indicator source. This profile intentionally does not mutate Pine
or optimize fib-anchor, visual, or EMA/MA setup inputs.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.optuna.paths import workspace_dir

PROFILE_KEY = "warbird_pro_v9"
PINE_FILE = "indicators/warbird-pro-v9.pine"
TRIGGER_FAMILY = "LIVE_ANCHOR_FOOTPRINT"

OPTUNA_DIR = workspace_dir(PROFILE_KEY)
EXPORT_ENV = "WARBIRD_PRO_V9_EXPORT"
MANIFEST_ENV = "WARBIRD_PRO_V9_MANIFEST"

ALLOWED_SYMBOL_ROOTS = frozenset({"ES", "MES"})
IGNORED_SYMBOL_ROOTS = frozenset({"NQ", "MNQ"})
ALLOWED_TIMEFRAMES = frozenset({"5", "15", "5m", "15m"})
TRADINGVIEW_CAPTURE_METHODS = frozenset(
    {
        "TRADINGVIEW_INDICATOR_CSV",
        "TV_INDICATOR_CSV",
        "TRADINGVIEW_CSV",
        "CSV_EXPORT",
    }
)
DATABENTO_CAPTURE_METHODS = frozenset(
    {
        "DATABENTO_OHLCV_CSV",
        "DATABENTO_TRAINING_CSV",
        "DATABENTO_BARS_CSV",
    }
)
ALLOWED_CAPTURE_METHODS = TRADINGVIEW_CAPTURE_METHODS | DATABENTO_CAPTURE_METHODS

POINT_VALUE_BY_ROOT = {"MES": 5.0, "ES": 50.0}
COMMISSION_SIDE_USD = 1.0
MINTICK = 0.25
DATA_FLOOR = "2020-01-01"
MIN_TRADES = 20
OBJECTIVE_METRIC = "v9_risk_exit_score"

FROZEN_PINE_PARAMS = frozenset(
    {
        "autoTuneZZ",
        "fibDeviationManual",
        "fibDepthManual",
        "fibConfluenceTolPct",
        "fibThresholdFloorPct",
        "minFibRangeAtr",
        "fibHysteresisPct",
        "targetLookbackBars",
        "extendLevelsRight",
        "useConfluenceAnchorSpan",
        "fibLineStyleInput",
        "showFibLevelLabelsInput",
        "fibLabelOffsetBarsInput",
        "fibLabelSizeInput",
        "zoneFillTransparencyInput",
        "useMaGate",
        "lengthMA",
        "lengthEMA",
        "showMaLines",
    }
)

BOOL_PARAMS: list[str] = ["allowLongs", "allowShorts"]

NUMERIC_RANGES: dict[str, tuple[float, float]] = {
    "atrPeriod": (7.0, 28.0),
    "stopAtrMult": (0.75, 2.75),
    "targetRiskMultiple": (1.0, 4.0),
    "maxHoldBars": (12.0, 180.0),
    "breakevenAfterR": (0.75, 2.0),
    "trailActivationR": (0.75, 2.5),
    "trailAtrMult": (0.50, 2.50),
}

INT_PARAMS: set[str] = {"atrPeriod", "maxHoldBars"}

CATEGORICAL_PARAMS: dict[str, list[Any]] = {
    "exitModel": [
        "ATR_BRACKET",
        "RISK_REWARD_BRACKET",
        "BREAKEVEN_AFTER_R",
        "ATR_TRAIL",
    ],
}

INPUT_DEFAULTS: dict[str, Any] = {
    "allowLongs": True,
    "allowShorts": True,
    "atrPeriod": 14,
    "stopAtrMult": 1.25,
    "targetRiskMultiple": 2.0,
    "maxHoldBars": 72,
    "breakevenAfterR": 1.0,
    "trailActivationR": 1.25,
    "trailAtrMult": 1.0,
    "exitModel": "ATR_BRACKET",
}


def _normalise_symbol_root(symbol: str) -> str:
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
    if root.startswith("MNQ"):
        return "MNQ"
    if root.startswith("ES"):
        return "ES"
    if root.startswith("NQ"):
        return "NQ"
    return root


def _manifest_candidates(csv_path: Path) -> list[Path]:
    return [
        csv_path.with_suffix(".manifest.json"),
        csv_path.with_name(csv_path.name + ".manifest.json"),
    ]


def _sha256_file(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def _load_manifest(csv_path: Path) -> dict[str, Any]:
    configured = os.environ.get(MANIFEST_ENV, "").strip()
    if configured:
        manifest_path = Path(configured).expanduser()
    else:
        manifest_path = next((path for path in _manifest_candidates(csv_path) if path.exists()), None)

    if manifest_path is None or not manifest_path.exists():
        raise FileNotFoundError(
            "Warbird Pro V9 exports require a manifest next to each CSV. "
            f"Missing manifest for {csv_path}."
        )

    manifest = json.loads(manifest_path.read_text())
    capture_method = str(manifest.get("capture_method") or manifest.get("source_kind") or "").strip()
    if capture_method and capture_method not in ALLOWED_CAPTURE_METHODS:
        raise ValueError(
            "Warbird Pro V9 capture_method must be a TradingView CSV method or "
            "Databento training data method; "
            f"got {capture_method!r}."
        )
    source_kind = capture_method or "TRADINGVIEW_INDICATOR_CSV"
    manifest["_source_kind"] = source_kind

    indicator_file = str(manifest.get("indicator_file", "")).strip()
    if source_kind in DATABENTO_CAPTURE_METHODS and indicator_file:
        raise ValueError(
            "Warbird Pro V9 Databento training manifests must not declare "
            "indicator_file as the data source. Use capture_method/source_kind "
            "to identify Databento data and keep Pine identity out of the data "
            "source field."
        )
    if source_kind not in DATABENTO_CAPTURE_METHODS and indicator_file and indicator_file != PINE_FILE:
        raise ValueError(
            f"Warbird Pro V9 manifest indicator_file must be {PINE_FILE!r}; "
            f"got {indicator_file!r}."
        )

    trigger_family = str(manifest.get("trigger_family", "")).strip()
    if trigger_family and trigger_family != TRIGGER_FAMILY:
        raise ValueError(
            f"Warbird Pro V9 trigger_family must be {TRIGGER_FAMILY!r}; "
            f"got {trigger_family!r}."
        )

    timeframe = str(manifest.get("timeframe", "")).strip()
    if timeframe and timeframe not in ALLOWED_TIMEFRAMES:
        raise ValueError(
            f"Warbird Pro V9 timeframe must be one of {sorted(ALLOWED_TIMEFRAMES)}; "
            f"got {timeframe!r}."
        )

    expected_hash = manifest.get("sha256") or manifest.get("csv_sha256") or manifest.get("export_hash")
    if expected_hash:
        actual_hash = _sha256_file(csv_path)
        if str(expected_hash).lower() != actual_hash.lower():
            raise ValueError(
                f"Warbird Pro V9 export hash mismatch for {csv_path}: "
                f"manifest={expected_hash} actual={actual_hash}"
            )

    return manifest


def _discover_export_files(root: Path | None = None) -> list[Path]:
    configured = os.environ.get(EXPORT_ENV, "").strip()
    if configured:
        path = Path(configured).expanduser()
        if path.is_file():
            return [path]
        root = path

    root = root or OPTUNA_DIR
    candidates: list[Path] = []
    root_export = root / "export.csv"
    if root_export.exists():
        candidates.append(root_export)
    exports_dir = root / "exports"
    if exports_dir.exists():
        candidates.extend(sorted(exports_dir.glob("*.csv")))
    return sorted(dict.fromkeys(candidates))


def _parse_tv_csv(csv_path: Path) -> pd.DataFrame:
    raw = pd.read_csv(csv_path)
    raw.columns = [str(c).strip().lower().replace(" ", "_") for c in raw.columns]

    time_col = next((c for c in ("ts", "time", "timestamp") if c in raw.columns), None)
    if time_col is None:
        raise ValueError(f"V9 export {csv_path} is missing ts/time/timestamp.")
    if time_col != "ts":
        raw = raw.rename(columns={time_col: "ts"})

    if pd.api.types.is_numeric_dtype(raw["ts"]):
        raw["ts"] = pd.to_datetime(raw["ts"], unit="s", utc=True)
    else:
        raw["ts"] = pd.to_datetime(raw["ts"], utc=True)

    return raw.sort_values("ts").reset_index(drop=True)


def _prepare_export_frame(frame: pd.DataFrame, manifest: dict[str, Any], source_csv: Path) -> pd.DataFrame:
    symbol = str(manifest.get("symbol", "")).strip()
    if not symbol and "symbol" in frame.columns:
        symbol = str(frame["symbol"].dropna().iloc[0])
    if not symbol:
        raise ValueError(f"Warbird Pro V9 manifest for {source_csv} must declare symbol.")

    symbol_root = _normalise_symbol_root(symbol)
    if symbol_root in IGNORED_SYMBOL_ROOTS:
        empty = frame.iloc[0:0].copy()
        empty["symbol"] = symbol
        empty["symbol_root"] = symbol_root
        return empty
    if symbol_root not in ALLOWED_SYMBOL_ROOTS:
        raise ValueError(
            f"Warbird Pro V9 only admits ES/MES exports and ignores NQ; got {symbol!r}."
        )

    required = {"ts", "open", "high", "low", "close", "volume"}
    missing = required.difference(frame.columns)
    if missing:
        raise ValueError(f"Warbird Pro V9 export missing required columns: {sorted(missing)}")

    long_col = next((c for c in ("ml_entry_long_trigger", "entry_long_trigger") if c in frame.columns), None)
    short_col = next((c for c in ("ml_entry_short_trigger", "entry_short_trigger") if c in frame.columns), None)
    if long_col is None or short_col is None:
        raise ValueError(
            "Warbird Pro V9 export must contain ml_entry_long_trigger and "
            "ml_entry_short_trigger from the active Pine indicator."
        )

    out = frame.copy()
    for col in ("open", "high", "low", "close", "volume", long_col, short_col):
        out[col] = pd.to_numeric(out[col], errors="coerce")

    out = out.rename(columns={long_col: "ml_entry_long_trigger", short_col: "ml_entry_short_trigger"})
    out["symbol"] = symbol
    out["symbol_root"] = symbol_root
    out["timeframe"] = str(manifest.get("timeframe", "")).strip()
    out["_source_csv"] = str(source_csv)
    out["_source_kind"] = str(manifest.get("_source_kind", "")).strip()
    out["_point_value"] = POINT_VALUE_BY_ROOT[symbol_root]

    context_col = next(
        (
            c
            for c in (
                "fib_neg_0236_context",
                "ml_fib_neg_0236",
                "p_neg_0236",
                "pneg236",
            )
            if c in out.columns
        ),
        None,
    )
    if context_col and context_col != "fib_neg_0236_context":
        out["fib_neg_0236_context"] = pd.to_numeric(out[context_col], errors="coerce")
    elif "fib_neg_0236_context" not in out.columns:
        out["fib_neg_0236_context"] = np.nan

    data_floor = pd.Timestamp(DATA_FLOOR, tz="UTC")
    out = out.loc[out["ts"] >= data_floor].copy()
    return out.sort_values("ts").reset_index(drop=True)


def _atr(high: np.ndarray, low: np.ndarray, close: np.ndarray, period: int) -> np.ndarray:
    n = len(close)
    result = np.full(n, np.nan)
    if n < period:
        return result
    prev_close = np.roll(close, 1)
    prev_close[0] = close[0]
    tr = np.maximum(high - low, np.maximum(np.abs(high - prev_close), np.abs(low - prev_close)))
    result[period - 1] = float(np.nanmean(tr[:period]))
    alpha = 1.0 / period
    for i in range(period, n):
        result[i] = tr[i] * alpha + result[i - 1] * (1.0 - alpha)
    return result


def _with_trial_atr(df: pd.DataFrame, period: int) -> pd.DataFrame:
    chunks: list[pd.DataFrame] = []
    for _, group in df.groupby("symbol_root", sort=False):
        work = group.sort_values("ts").copy()
        work["_atr_trial"] = _atr(
            work["high"].to_numpy(dtype=float),
            work["low"].to_numpy(dtype=float),
            work["close"].to_numpy(dtype=float),
            period=period,
        )
        chunks.append(work)
    return pd.concat(chunks, ignore_index=True).sort_values(["symbol_root", "ts"]).reset_index(drop=True)


def load_data() -> pd.DataFrame:
    export_files = _discover_export_files()
    if not export_files:
        raise FileNotFoundError(
            "No Warbird Pro V9 ES/MES training exports found. Put TradingView "
            "CSV or Databento training CSV files at "
            f"{OPTUNA_DIR / 'export.csv'} or {OPTUNA_DIR / 'exports'}/*.csv, with "
            "a .manifest.json next to each CSV. NQ exports are ignored."
        )

    frames: list[pd.DataFrame] = []
    ignored: list[str] = []
    for csv_path in export_files:
        manifest = _load_manifest(csv_path)
        prepared = _prepare_export_frame(_parse_tv_csv(csv_path), manifest, csv_path)
        if prepared.empty:
            ignored.append(str(csv_path))
            continue
        frames.append(prepared)

    if not frames:
        raise ValueError(
            "Warbird Pro V9 found no usable ES/MES export rows. "
            f"Ignored NQ/MNQ files: {ignored}"
        )

    df = pd.concat(frames, ignore_index=True).sort_values(["symbol_root", "ts"]).reset_index(drop=True)
    df.attrs["ignored_exports"] = ignored
    return df


def _extract_signals(df: pd.DataFrame, params: dict[str, Any]) -> list[dict[str, Any]]:
    allow_longs = bool(params.get("allowLongs", True))
    allow_shorts = bool(params.get("allowShorts", True))
    signals: list[dict[str, Any]] = []

    for _, group in df.groupby("symbol_root", sort=False):
        rows = group.sort_values("ts").reset_index(drop=True)
        for idx, row in rows.iterrows():
            atr = float(row.get("_atr_trial", np.nan))
            if not np.isfinite(atr) or atr <= 0:
                continue

            long_hit = float(row.get("ml_entry_long_trigger", 0.0) or 0.0) > 0.0
            short_hit = float(row.get("ml_entry_short_trigger", 0.0) or 0.0) > 0.0
            if long_hit and short_hit:
                continue
            if long_hit and allow_longs:
                direction = 1
            elif short_hit and allow_shorts:
                direction = -1
            else:
                continue

            signals.append(
                {
                    "rows": rows,
                    "entry_idx": int(idx),
                    "entry_ts": row["ts"],
                    "direction": direction,
                    "entry_px": float(row["close"]),
                    "atr": atr,
                    "symbol_root": str(row["symbol_root"]),
                    "symbol": str(row["symbol"]),
                    "point_value": float(row["_point_value"]),
                    "fib_neg_0236_context": float(row.get("fib_neg_0236_context", np.nan)),
                }
            )
    return signals


def _simulate_signal(signal: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
    rows: pd.DataFrame = signal["rows"]
    entry_idx = int(signal["entry_idx"])
    direction = int(signal["direction"])
    entry_px = float(signal["entry_px"])
    atr = max(float(signal["atr"]), MINTICK)
    point_value = float(signal["point_value"])

    stop_distance = max(float(params.get("stopAtrMult", 1.25)) * atr, MINTICK)
    target_distance = max(float(params.get("targetRiskMultiple", 2.0)) * stop_distance, MINTICK)
    max_hold = max(int(params.get("maxHoldBars", 72)), 1)
    exit_model = str(params.get("exitModel", "ATR_BRACKET"))
    breakeven_after_r = float(params.get("breakevenAfterR", 1.0))
    trail_activation_r = float(params.get("trailActivationR", 1.25))
    trail_atr_mult = float(params.get("trailAtrMult", 1.0))

    stop_px = entry_px - direction * stop_distance
    target_px = entry_px + direction * target_distance
    active_stop = stop_px
    best_favorable = 0.0
    exit_px = float(rows.iloc[min(entry_idx + max_hold, len(rows) - 1)]["close"])
    exit_idx = min(entry_idx + max_hold, len(rows) - 1)
    outcome = "TIME_EXIT"

    for offset in range(1, max_hold + 1):
        idx = entry_idx + offset
        if idx >= len(rows):
            break
        row = rows.iloc[idx]
        high = float(row["high"])
        low = float(row["low"])
        close = float(row["close"])

        favorable = (high - entry_px) if direction == 1 else (entry_px - low)
        best_favorable = max(best_favorable, favorable)

        if exit_model == "BREAKEVEN_AFTER_R" and best_favorable >= breakeven_after_r * stop_distance:
            active_stop = max(active_stop, entry_px) if direction == 1 else min(active_stop, entry_px)
        elif exit_model == "ATR_TRAIL" and best_favorable >= trail_activation_r * stop_distance:
            if direction == 1:
                active_stop = max(active_stop, high - trail_atr_mult * atr)
            else:
                active_stop = min(active_stop, low + trail_atr_mult * atr)

        stop_hit = (low <= active_stop) if direction == 1 else (high >= active_stop)
        target_hit = (high >= target_px) if direction == 1 else (low <= target_px)

        if stop_hit:
            exit_px = active_stop
            exit_idx = idx
            outcome = "STOP"
            break
        if target_hit:
            exit_px = target_px
            exit_idx = idx
            outcome = "TARGET"
            break

        exit_px = close
        exit_idx = idx

    gross_points = direction * (exit_px - entry_px)
    gross_usd = gross_points * point_value
    pnl_usd = gross_usd - COMMISSION_SIDE_USD * 2.0
    risk_usd = stop_distance * point_value
    r_multiple = pnl_usd / max(risk_usd, 1e-9)

    return {
        "entry_ts": signal["entry_ts"],
        "exit_ts": rows.iloc[exit_idx]["ts"],
        "symbol": signal["symbol"],
        "symbol_root": signal["symbol_root"],
        "direction": direction,
        "entry_px": round(entry_px, 2),
        "exit_px": round(exit_px, 2),
        "stop_distance": round(stop_distance, 4),
        "target_distance": round(target_distance, 4),
        "outcome": outcome,
        "bars_held": exit_idx - entry_idx,
        "pnl_usd": pnl_usd,
        "r_multiple": r_multiple,
        "fib_neg_0236_context": signal["fib_neg_0236_context"],
    }


def _empty_result() -> dict[str, Any]:
    return {
        "trades": 0,
        "win_rate": 0.0,
        "pf": 0.0,
        "gross_profit": 0.0,
        "gross_loss": 1.0,
        "max_dd_abs": 0.0,
        "max_dd_pct": 0.0,
        "avg_r": 0.0,
        "total_r": 0.0,
        "v9_risk_exit_score": 0.0,
        "long_trades": 0,
        "short_trades": 0,
    }


def _score_trades(trades: list[dict[str, Any]]) -> dict[str, Any]:
    if len(trades) < MIN_TRADES:
        return _empty_result()

    r_values = np.array([float(t["r_multiple"]) for t in trades], dtype=float)
    pnl_values = np.array([float(t["pnl_usd"]) for t in trades], dtype=float)
    winners = r_values > 0.0

    gross_profit = float(pnl_values[pnl_values > 0.0].sum())
    gross_loss = abs(float(pnl_values[pnl_values < 0.0].sum()))
    pf = gross_profit / max(gross_loss, 1e-9)
    wr = float(winners.mean())
    total_r = float(r_values.sum())
    avg_r = float(r_values.mean())

    equity = np.cumsum(pnl_values)
    peak = np.maximum.accumulate(np.concatenate([[0.0], equity]))
    dd = peak[1:] - equity
    max_dd = float(dd.max()) if len(dd) else 0.0
    max_dd_pct = max_dd / peak.max() if peak.max() > 0 else 0.0

    long_trades = sum(1 for t in trades if int(t["direction"]) == 1)
    short_trades = len(trades) - long_trades
    side_balance = min(long_trades, short_trades) / max(max(long_trades, short_trades), 1)

    pf_score = min(pf / 2.25, 1.0)
    wr_score = min(wr / 0.62, 1.0)
    expectancy_score = float(np.clip((avg_r + 0.25) / 1.25, 0.0, 1.0))
    trade_density_score = min(len(trades) / 150.0, 1.0)
    dd_penalty = min(max_dd_pct, 0.35)

    score = (
        0.32 * pf_score
        + 0.25 * expectancy_score
        + 0.18 * wr_score
        + 0.15 * trade_density_score
        + 0.10 * side_balance
        - dd_penalty
    )
    score = float(np.clip(score, 0.0, 1.0))

    return {
        "trades": len(trades),
        "win_rate": round(wr, 6),
        "pf": round(pf, 6),
        "gross_profit": round(gross_profit, 2),
        "gross_loss": round(gross_loss, 2),
        "max_dd_abs": round(max_dd, 2),
        "max_dd_pct": round(float(max_dd_pct), 6),
        "avg_r": round(avg_r, 6),
        "total_r": round(total_r, 6),
        "v9_risk_exit_score": round(score, 6),
        "long_trades": long_trades,
        "short_trades": short_trades,
    }


def objective_score(result: dict[str, Any]) -> float:
    return float(result.get("v9_risk_exit_score", 0.0) or 0.0)


def assert_v9_contract() -> None:
    tunable_names = set(BOOL_PARAMS) | set(NUMERIC_RANGES) | set(CATEGORICAL_PARAMS)
    frozen_overlap = FROZEN_PINE_PARAMS.intersection(tunable_names)
    if frozen_overlap:
        raise AssertionError(f"Frozen Pine params exposed as V9 tunables: {sorted(frozen_overlap)}")
    stop_candidates = set(CATEGORICAL_PARAMS.get("stopFamilyId", []))
    if "FIB_NEG_0236" in stop_candidates or "FIB_NEG_0382" in stop_candidates:
        raise AssertionError("V9 must not expose fib-negative stop candidates.")


def run_backtest(df: pd.DataFrame, params: dict[str, Any], start_date: str) -> dict[str, Any]:
    assert_v9_contract()

    start_ts = pd.Timestamp(start_date)
    start_ts = start_ts.tz_localize("UTC") if start_ts.tzinfo is None else start_ts.tz_convert("UTC")
    frame = df.loc[pd.to_datetime(df["ts"], utc=True) >= start_ts].copy()
    if frame.empty:
        return _empty_result()

    atr_period = int(params.get("atrPeriod", INPUT_DEFAULTS["atrPeriod"]))
    work = _with_trial_atr(frame, atr_period)
    signals = _extract_signals(work, params)
    if not signals:
        return _empty_result()

    simulated = [_simulate_signal(signal, params) for signal in signals]
    return _score_trades(simulated)
