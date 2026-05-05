#!/usr/bin/env python3
"""Warbird Pro V9 Optuna profile — entry-filter HPO.

This is the active `warbird_pro` lane. It treats the Pine V9 entry triggers
(`ml_entry_long_trigger` / `ml_entry_short_trigger`) as candidate entries and
tunes a post-trigger filter that decides which candidates to TAKE based on the
rich `ml_*` feature surface emitted by `indicators/warbird-pro-v9.pine`.

Companion profile `warbird_pro_v9_profile.py` covers ATR/risk EXIT modeling on
the same triggers. Together they form the V9 entry+exit Optuna pair.

This profile does not mutate Pine. Fib core (anchor ownership, ladder math,
ZigZag, draw span), MA/EMA setup, and visual surface are frozen per the
indicator-only Optuna contract (docs/contracts/pine_indicator_ag_contract.md).
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

PROFILE_KEY = "warbird_pro"
PINE_FILE = "indicators/warbird-pro-v9.pine"
TRIGGER_FAMILY = "LIVE_ANCHOR_FOOTPRINT"

OPTUNA_DIR = workspace_dir(PROFILE_KEY)
EXPORT_ENV = "WARBIRD_PRO_EXPORT"
MANIFEST_ENV = "WARBIRD_PRO_MANIFEST"

ALLOWED_SYMBOL_ROOTS = frozenset({"MES"})
IGNORED_SYMBOL_ROOTS = frozenset({"ES", "NQ", "MNQ"})
ALLOWED_TIMEFRAMES = frozenset({"5", "5m"})
DATABENTO_CAPTURE_METHODS = frozenset(
    {
        "DATABENTO_OHLCV_CSV",
        "DATABENTO_TRAINING_CSV",
        "DATABENTO_BARS_CSV",
    }
)
ALLOWED_CAPTURE_METHODS = DATABENTO_CAPTURE_METHODS

POINT_VALUE_BY_ROOT = {"MES": 5.0}
COMMISSION_SIDE_USD = 1.0
MINTICK = 0.25
DATA_FLOOR = "2020-01-01"
MIN_TRADES = 40
OBJECTIVE_METRIC = "v9_entry_filter_score"

# Pine inputs that must remain frozen (visual + fib-core + MA setup)
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

# Bullish + bearish candlestick pattern columns emitted by Pine
BULL_PATTERN_COLS = (
    "ml_pat_hammer",
    "ml_pat_inv_hammer",
    "ml_pat_dragonfly",
    "ml_pat_bull_engulf",
    "ml_pat_piercing",
    "ml_pat_morning_star",
    "ml_pat_three_white",
)
BEAR_PATTERN_COLS = (
    "ml_pat_shooting_star",
    "ml_pat_hanging_man",
    "ml_pat_gravestone",
    "ml_pat_bear_engulf",
    "ml_pat_dark_cloud",
    "ml_pat_evening_star",
    "ml_pat_three_black",
)

# Required feature columns for filter HPO (raised by load_data on missing)
REQUIRED_FEATURE_COLS = (
    "ml_entry_long_trigger",
    "ml_entry_short_trigger",
    "ml_atr14",
    "ml_dir",
    "ml_rsi_value",
    "ml_in_zone",
    "ml_bars_since_break",
    "ml_pivot_dist_atr",
    "ml_p618_dist_atr",
    "ml_bsl_dist_atr",
    "ml_ssl_dist_atr",
    "ml_swept_bsl",
    "ml_swept_ssl",
    "ml_reclaimed_bsl",
    "ml_reclaimed_ssl",
    "ml_bar_delta",
    "ml_net_delta_20",
    "ml_xa_nq_code",
    "ml_xa_zn_code",
    "ml_xa_dx_code",
    "ml_exhaust_long",
    "ml_exhaust_short",
    "ml_htf_conf_total",
)

# Tunable filter params
BOOL_PARAMS: list[str] = [
    "requireBullPatternLong",
    "requireBearPatternShort",
    "requireSweepConfirmLong",
    "requireSweepConfirmShort",
    "requirePositiveDeltaLong",
    "requireNegativeDeltaShort",
    "blockOnExhaustionLong",
    "blockOnExhaustionShort",
    "requireXaNqAlignment",
    "blockShortsInStrongUp",
]

NUMERIC_RANGES: dict[str, tuple[float, float]] = {
    "minHtfConfTotal":         (0.0, 3.0),
    "maxBslDistAtrLong":       (0.5, 14.0),
    "maxSslDistAtrShort":      (0.5, 38.0),
    "minNetDelta20Long":       (-50000.0, 50000.0),
    "maxNetDelta20Short":      (-50000.0, 50000.0),
    "minPivotDistAtr":         (-7.0, 7.0),
    "rsiUpperBlockLong":       (60.0, 95.0),
    "rsiLowerBlockShort":      (5.0, 40.0),
    "stopAtrMult":             (0.75, 2.75),
    "targetRiskMultiple":      (1.0, 4.0),
    "maxHoldBars":             (12.0, 180.0),
}

INT_PARAMS: set[str] = {
    "maxHoldBars",
}

CATEGORICAL_PARAMS: dict[str, list[Any]] = {
    "exitModel": [
        "ATR_BRACKET",
        "RISK_REWARD_BRACKET",
        "BREAKEVEN_AFTER_R",
        "ATR_TRAIL",
    ],
    "minBullPatternsLong":  [0, 1, 2, 3],
    "minBearPatternsShort": [0, 1, 2, 3],
}

INPUT_DEFAULTS: dict[str, Any] = {
    "requireBullPatternLong":  True,
    "requireBearPatternShort": True,
    "requireSweepConfirmLong":  False,
    "requireSweepConfirmShort": False,
    "requirePositiveDeltaLong":  False,
    "requireNegativeDeltaShort": False,
    "blockOnExhaustionLong":  True,
    "blockOnExhaustionShort": True,
    "requireXaNqAlignment":   False,
    "blockShortsInStrongUp":  False,
    "minHtfConfTotal":   0.0,
    "maxBslDistAtrLong": 8.0,
    "maxSslDistAtrShort": 8.0,
    "minNetDelta20Long":  -5000.0,
    "maxNetDelta20Short":  5000.0,
    "minPivotDistAtr":     -3.0,
    "rsiUpperBlockLong":   80.0,
    "rsiLowerBlockShort":  20.0,
    "stopAtrMult":         1.25,
    "targetRiskMultiple":  2.0,
    "maxHoldBars":         72,
    "minBullPatternsLong":  1,
    "minBearPatternsShort": 1,
    "exitModel":           "ATR_BRACKET",
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
    capture_method = str(manifest.get("capture_method", "")).strip()
    if capture_method and capture_method not in ALLOWED_CAPTURE_METHODS:
        raise ValueError(
            f"Warbird Pro V9 capture_method must be one of {sorted(ALLOWED_CAPTURE_METHODS)}; "
            f"got {capture_method!r}."
        )

    indicator_file = str(manifest.get("indicator_file", "")).strip()
    if indicator_file and indicator_file != PINE_FILE:
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
    if not expected_hash:
        raise ValueError(
            f"Warbird Pro V9 manifest must declare sha256/csv_sha256/export_hash for {csv_path}."
        )
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
            f"Warbird Pro V9 admits MES-only Databento exports; got {symbol!r}."
        )

    required = {"ts", "open", "high", "low", "close", "volume"}
    missing = required.difference(frame.columns)
    if missing:
        raise ValueError(f"Warbird Pro V9 export missing OHLCV columns: {sorted(missing)}")

    feat_missing = [c for c in REQUIRED_FEATURE_COLS if c not in frame.columns]
    if feat_missing:
        raise ValueError(
            "Warbird Pro V9 export missing required ml_* feature columns: "
            f"{feat_missing}. Re-export from the active Pine indicator."
        )

    out = frame.copy()
    numeric_cols = (
        ["open", "high", "low", "close", "volume"]
        + list(REQUIRED_FEATURE_COLS)
        + [c for c in BULL_PATTERN_COLS if c in out.columns]
        + [c for c in BEAR_PATTERN_COLS if c in out.columns]
    )
    for col in numeric_cols:
        out[col] = pd.to_numeric(out[col], errors="coerce")

    out["symbol"] = symbol
    out["symbol_root"] = symbol_root
    out["timeframe"] = str(manifest.get("timeframe", "")).strip()
    out["_source_csv"] = str(source_csv)
    out["_point_value"] = POINT_VALUE_BY_ROOT[symbol_root]

    data_floor = pd.Timestamp(DATA_FLOOR, tz="UTC")
    out = out.loc[out["ts"] >= data_floor].copy()
    return out.sort_values("ts").reset_index(drop=True)


def load_data() -> pd.DataFrame:
    export_files = _discover_export_files()
    if not export_files:
        raise FileNotFoundError(
            "No Warbird Pro V9 exports found. Put MES 5m Databento exports at "
            f"{OPTUNA_DIR / 'export.csv'} or {OPTUNA_DIR / 'exports'}/*.csv, "
            "with a .manifest.json next to each CSV (capture_method must be "
            "DATABENTO_OHLCV_CSV / DATABENTO_TRAINING_CSV / DATABENTO_BARS_CSV)."
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
            f"Warbird Pro V9 found no usable MES 5m export rows. Ignored non-MES files: {ignored}"
        )

    df = pd.concat(frames, ignore_index=True).sort_values(["symbol_root", "ts"]).reset_index(drop=True)
    df.attrs["ignored_exports"] = ignored
    return df


def _count_active(row: pd.Series, cols: tuple[str, ...]) -> int:
    return int(sum(1 for c in cols if c in row.index and float(row.get(c, 0.0) or 0.0) > 0.0))


def _passes_long_filter(row: pd.Series, params: dict[str, Any]) -> bool:
    if bool(params.get("requireBullPatternLong", True)):
        if _count_active(row, BULL_PATTERN_COLS) < int(params.get("minBullPatternsLong", 1)):
            return False
    if bool(params.get("requireSweepConfirmLong", False)):
        if not (float(row.get("ml_swept_ssl", 0.0)) > 0.0 or float(row.get("ml_reclaimed_ssl", 0.0)) > 0.0):
            return False
    if bool(params.get("requirePositiveDeltaLong", False)):
        if float(row.get("ml_net_delta_20", 0.0)) < float(params.get("minNetDelta20Long", -5000.0)):
            return False
    if bool(params.get("blockOnExhaustionLong", True)):
        if float(row.get("ml_exhaust_long", 0.0)) > 0.0:
            return False
    if bool(params.get("requireXaNqAlignment", False)):
        if float(row.get("ml_xa_nq_code", 0.0)) <= 0.0:
            return False
    if float(row.get("ml_htf_conf_total", 0.0)) < float(params.get("minHtfConfTotal", 0.0)):
        return False
    if float(row.get("ml_bsl_dist_atr", 999.0)) > float(params.get("maxBslDistAtrLong", 8.0)):
        return False
    if float(row.get("ml_pivot_dist_atr", 0.0)) < float(params.get("minPivotDistAtr", -3.0)):
        return False
    if float(row.get("ml_rsi_value", 50.0)) >= float(params.get("rsiUpperBlockLong", 80.0)):
        return False
    return True


def _passes_short_filter(row: pd.Series, params: dict[str, Any]) -> bool:
    if bool(params.get("requireBearPatternShort", True)):
        if _count_active(row, BEAR_PATTERN_COLS) < int(params.get("minBearPatternsShort", 1)):
            return False
    if bool(params.get("requireSweepConfirmShort", False)):
        if not (float(row.get("ml_swept_bsl", 0.0)) > 0.0 or float(row.get("ml_reclaimed_bsl", 0.0)) > 0.0):
            return False
    if bool(params.get("requireNegativeDeltaShort", False)):
        if float(row.get("ml_net_delta_20", 0.0)) > float(params.get("maxNetDelta20Short", 5000.0)):
            return False
    if bool(params.get("blockOnExhaustionShort", True)):
        if float(row.get("ml_exhaust_short", 0.0)) > 0.0:
            return False
    if bool(params.get("blockShortsInStrongUp", False)):
        if float(row.get("ml_xa_nq_code", 0.0)) >= 2.0:
            return False
    if float(row.get("ml_htf_conf_total", 0.0)) < float(params.get("minHtfConfTotal", 0.0)):
        return False
    if float(row.get("ml_ssl_dist_atr", 999.0)) > float(params.get("maxSslDistAtrShort", 8.0)):
        return False
    if -float(row.get("ml_pivot_dist_atr", 0.0)) < float(params.get("minPivotDistAtr", -3.0)):
        return False
    if float(row.get("ml_rsi_value", 50.0)) <= float(params.get("rsiLowerBlockShort", 20.0)):
        return False
    return True


def _extract_signals(df: pd.DataFrame, params: dict[str, Any]) -> list[dict[str, Any]]:
    signals: list[dict[str, Any]] = []
    for _, group in df.groupby("symbol_root", sort=False):
        rows = group.sort_values("ts").reset_index(drop=True)
        for idx, row in rows.iterrows():
            atr = float(row.get("ml_atr14", np.nan))
            if not np.isfinite(atr) or atr <= 0:
                continue
            long_hit = float(row.get("ml_entry_long_trigger", 0.0) or 0.0) > 0.0
            short_hit = float(row.get("ml_entry_short_trigger", 0.0) or 0.0) > 0.0
            if long_hit and short_hit:
                continue
            direction: int
            if long_hit and _passes_long_filter(row, params):
                direction = 1
            elif short_hit and _passes_short_filter(row, params):
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

    stop_px = entry_px - direction * stop_distance
    target_px = entry_px + direction * target_distance
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
        stop_hit = (low <= stop_px) if direction == 1 else (high >= stop_px)
        target_hit = (high >= target_px) if direction == 1 else (low <= target_px)
        if stop_hit:
            exit_px = stop_px
            exit_idx = idx
            outcome = "STOP"
            break
        if target_hit:
            exit_px = target_px
            exit_idx = idx
            outcome = "TARGET"
            break
        exit_px = float(row["close"])
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
        OBJECTIVE_METRIC: 0.0,
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

    pf_score = min(pf / 2.25, 1.0)
    wr_score = min(wr / 0.62, 1.0)
    expectancy_score = float(np.clip((avg_r + 0.25) / 1.25, 0.0, 1.0))
    trade_density_score = min(len(trades) / 200.0, 1.0)
    dd_penalty = min(max_dd_pct, 0.35)

    score = 0.35 * pf_score + 0.28 * expectancy_score + 0.22 * wr_score + 0.15 * trade_density_score - dd_penalty
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
        OBJECTIVE_METRIC: round(score, 6),
        "long_trades": long_trades,
        "short_trades": short_trades,
    }


def objective_score(result: dict[str, Any]) -> float:
    return float(result.get(OBJECTIVE_METRIC, 0.0) or 0.0)


def assert_v9_contract() -> None:
    tunable_names = set(BOOL_PARAMS) | set(NUMERIC_RANGES) | set(CATEGORICAL_PARAMS)
    frozen_overlap = FROZEN_PINE_PARAMS.intersection(tunable_names)
    if frozen_overlap:
        raise AssertionError(f"Frozen Pine params exposed as tunables: {sorted(frozen_overlap)}")
    cat_stop = set(CATEGORICAL_PARAMS.get("stopFamilyId", []))
    if "FIB_NEG_0236" in cat_stop or "FIB_NEG_0382" in cat_stop:
        raise AssertionError("Negative-fib stop candidates banned by V9 contract.")


def run_backtest(df: pd.DataFrame, params: dict[str, Any], start_date: str) -> dict[str, Any]:
    assert_v9_contract()

    start_ts = pd.Timestamp(start_date)
    start_ts = start_ts.tz_localize("UTC") if start_ts.tzinfo is None else start_ts.tz_convert("UTC")
    frame = df.loc[pd.to_datetime(df["ts"], utc=True) >= start_ts].copy()
    if frame.empty:
        return _empty_result()

    signals = _extract_signals(frame, params)
    if not signals:
        return _empty_result()

    simulated = [_simulate_signal(signal, params) for signal in signals]
    return _score_trades(simulated)
