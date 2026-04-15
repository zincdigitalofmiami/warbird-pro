#!/usr/bin/env python3
"""Monte Carlo P&L hi-def deep-dive on a completed AG training run.

Task A — per stop_family_id roll-up of expected value, Sharpe, cumulative P&L
         path quantiles, max drawdown, win rate, profit factor.
Task B — per-stop_family × entry-dimension breakdowns (direction, archetype,
         fib_level_touched, is_rth_ct, is_opening_window_ct, ml_exec_*,
         hour_bucket, quartile-bucketed confluence/rvol/atr14/adx/rsi14).
Task C — threshold sweep (P(TP any) >= tau) × stop_family.
Task D — top/bottom cross-feature combos by analytical EV/trade.
Task E — entry rules scored across (stop_family × direction × fib_level ×
         hour_bucket × SHAP-top-feature quartiles). Takes/avoid lists.
Task F — TP-ladder decision tree per (stop_family × fib_level). For each
         probability-band and each TP level n in {1..5}, analytical EV of
         holding for TP_n. Emits modal-best-n per band.
Task G — per-cohort calibration (predicted vs realized per class) with
         OK / OVERCONFIDENT / UNDERCONFIDENT / ZERO_PREDICTION_MISS verdicts.
Task H — regime stability: split test slice by median ts, re-run A/C on
         each half, compare with Spearman rank correlation.
Task I — win profile: streaks, time-to-TP, max single win, underwater
         duration per stop_family.

Reads each fold's TabularPredictor + the fold's test slice from ag_training,
predicts class probabilities, simulates per-row outcome sampling. 1 contract
per trade. MES multiplier $5/pt. Flat 1-tick fee ($1.25) per trade
(NinjaTrader Basic free account).

Read-only on DB and predictors. Writes to
  artifacts/ag_runs/<RUN_ID>/monte_carlo/{task_{A..I}.json, summary.md, cache/}

Locked execution plan: docs/plans/2026-04-15-hi-def-shap-mc-implementation.md

Not a silver bullet — if the source run has IID bag leakage, the probabilities
are noisy. Relative ranking across stop_family_id / threshold / entry features
may still be informative but absolute EV numbers should be read skeptically.
"""
from __future__ import annotations

# OMP guards mirror the trainer — LightGBM predictor reload on Apple Silicon.
import os
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("LIGHTGBM_NUM_THREADS", "1")

import argparse
import json
import math
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd
import psycopg2

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from train_ag_baseline import (  # noqa: E402
    CHICAGO_TZ,
    DEFAULT_DSN,
    add_time_context,
    attach_context_features,
    coerce_feature_frame,
    load_base_training,
)

CLASSES = ["STOPPED", "TP1_ONLY", "TP2_HIT", "TP3_HIT", "TP4_HIT", "TP5_HIT"]
TP_CLASS_INDICES = [1, 2, 3, 4, 5]  # all TP_* classes
MES_POINT_VALUE = 5.0           # $ per point per contract (MES)
MES_TICK_VALUE = 1.25           # $ per tick per contract (MES 0.25 pt × $5/pt)
FLAT_FEE_PER_TRADE = MES_TICK_VALUE  # NinjaTrader Basic (free) fee model: 1 tick flat per trade
DEFAULT_THRESHOLDS = [round(x, 2) for x in np.arange(0.05, 0.95, 0.05)]
# Categorical / small-cardinality integer columns worth breaking down per stop_family.
ENTRY_BREAKDOWN_DIMS_CATEGORICAL = [
    "direction",
    "archetype",
    "fib_level_touched",
    "is_rth_ct",
    "is_opening_window_ct",
    "ml_exec_state_code",
    "ml_exec_pattern_code",
    "ml_exec_pocket_code",
    "ml_exec_target_leg_code",
]
# Float columns bucketed to quartiles then broken down per stop_family.
ENTRY_BREAKDOWN_DIMS_NUMERIC = [
    "confluence_quality",
    "rvol",
    "atr14",
    "adx",
    "rsi14",
]
# Hour-of-day buckets (RTH-centric) applied to hour_ct column.
HOUR_BUCKETS = [
    (0, 5, "ETH_OVERNIGHT"),
    (5, 8, "ETH_PRE_RTH"),
    (8, 9, "RTH_OPEN"),
    (9, 11, "RTH_MORNING"),
    (11, 13, "RTH_MIDDAY"),
    (13, 15, "RTH_AFTERNOON"),
    (15, 16, "RTH_CLOSE"),
    (16, 24, "ETH_POST_RTH"),
]
# Dimensions included in the cross-feature combo finder.
COMBO_DIMS = ["stop_family_id", "direction", "hour_bucket", "archetype"]
COMBO_TOP_K = 15
COMBO_MIN_TRADES = 50
# Indicator settings frozen in this training surface (see CLAUDE.md 15m fib-owner freeze).
INDICATOR_SETTINGS_FROZEN = {
    "fib_owner_timeframe": "15m",
    "zigzag_deviation": 4,
    "zigzag_depth": 20,
    "threshold_floor": 0.50,
    "min_fib_range": 0.5,
}
# Default set of tasks to run. Override via --tasks.
DEFAULT_TASKS = "A,B,C,D,E,F,G,H,I"
# Default SHAP-top feature count for Task E quartile expansion.
DEFAULT_SHAP_TOP_N = 3
# Columns the analysis_frame MUST contain for downstream tasks.
REQUIRED_ANALYSIS_COLS = [
    "ts",
    "stop_variant_id",
    "stop_family_id",
    "direction",
    "fib_level_touched",
    "entry_price",
    "tp1_price",
    "tp2_price",
    "tp3_price",
    "tp4_price",
    "tp5_price",
    "sl_dist_pts",
    "outcome_label",
]


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--run-id", required=True, help="e.g. agtrain_20260415T015005138333Z")
    p.add_argument("--artifacts-root", default="artifacts/ag_runs")
    p.add_argument("--n-paths", type=int, default=2000, help="Monte Carlo paths per roll-up")
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--dsn", default=DEFAULT_DSN)
    p.add_argument("--no-macro", action="store_true", help="Skip FRED/econ joins (diagnostic only)")
    p.add_argument(
        "--tasks",
        default=DEFAULT_TASKS,
        help="Comma-separated task selector (A,B,C,D,E,F,G,H,I). Default: all.",
    )
    p.add_argument(
        "--shap-artifact",
        default=None,
        help="Path to SHAP overall-importance CSV. Default: artifacts/shap/<run-id>/overall_importance.csv",
    )
    p.add_argument(
        "--shap-top-features",
        default=None,
        help="Comma-separated list of feature names for Task E quartile expansion; overrides --shap-artifact.",
    )
    p.add_argument(
        "--shap-top-n",
        type=int,
        default=DEFAULT_SHAP_TOP_N,
        help=f"Number of top SHAP features to use for Task E (default: {DEFAULT_SHAP_TOP_N}).",
    )
    p.add_argument(
        "--skip-predict",
        action="store_true",
        help="Load cached analysis_frame/probs/payoffs instead of re-predicting. Requires populated cache.",
    )
    p.add_argument(
        "--cache-dir",
        default=None,
        help="Cache dir. Default: artifacts/ag_runs/<run-id>/monte_carlo/cache",
    )
    p.add_argument(
        "--regime-split-method",
        choices=("median_ts", "midpoint_rows"),
        default="median_ts",
        help="Task H: how to split aggregated test slice in half.",
    )
    p.add_argument("--min-rule-n", type=int, default=50, help="Task E: minimum trades per combo.")
    p.add_argument(
        "--task-e-min-required-rules",
        type=int,
        default=10,
        help="Task E: minimum eligible rules required before fallback dims are accepted.",
    )
    p.add_argument(
        "--min-stable-corr",
        type=float,
        default=0.7,
        help="Task H: Spearman ρ threshold for STABLE verdict.",
    )
    return p.parse_args()


def load_fold_summary(fold_dir: Path) -> dict[str, Any]:
    return json.loads((fold_dir / "fold_summary.json").read_text())


def load_predictor(fold_dir: Path):
    from autogluon.tabular import TabularPredictor
    return TabularPredictor.load(str(fold_dir / "predictor"), require_py_version_match=False)


def predict_probs_aligned(predictor, X: pd.DataFrame) -> np.ndarray:
    """predict_proba → (N, 6) aligned to canonical CLASSES order.

    Pads any predictor-expected feature columns missing from X with NaN so AG's
    feature generator can transform cleanly (AG handles NaN via imputation).
    Re-normalizes the probability simplex in case AG returns fewer than 6 classes.
    """
    try:
        expected = list(predictor.features())
    except AttributeError:
        expected = list(predictor.feature_metadata_in.get_features())
    X = X.copy()
    missing = [col for col in expected if col not in X.columns]
    if missing:
        print(f"    padding {len(missing)} missing predictor features with NaN: {missing[:5]}{'...' if len(missing) > 5 else ''}")
    for col in missing:
        X[col] = np.nan
    X = X[expected]  # reorder to match predictor expectations
    pp = predictor.predict_proba(X)
    pp = pp.reindex(columns=CLASSES, fill_value=0.0)
    probs = pp.to_numpy(dtype=np.float64)
    row_sums = probs.sum(axis=1, keepdims=True)
    row_sums[row_sums == 0] = 1.0
    return probs / row_sums


def compute_payoff_matrix(base: pd.DataFrame) -> np.ndarray:
    """Return (N, 6) dollar payoff matrix. Column order matches CLASSES.

    STOPPED     → -sl_dist_pts * $5
    TP1_ONLY    → (tp1_price - entry_price) * direction * $5
    TP2_HIT..5  → same formula with tp2..5
    Minus flat 1-tick fee ($1.25) per trade (NinjaTrader Basic free account).
    """
    entry = base["entry_price"].to_numpy()
    direction = base["direction"].to_numpy()
    tp1 = (base["tp1_price"].to_numpy() - entry) * direction
    tp2 = (base["tp2_price"].to_numpy() - entry) * direction
    tp3 = (base["tp3_price"].to_numpy() - entry) * direction
    tp4 = (base["tp4_price"].to_numpy() - entry) * direction
    tp5 = (base["tp5_price"].to_numpy() - entry) * direction
    sl_loss = -base["sl_dist_pts"].to_numpy()
    pts = np.stack([sl_loss, tp1, tp2, tp3, tp4, tp5], axis=1)  # (N, 6)
    dollars = pts * MES_POINT_VALUE
    return dollars - FLAT_FEE_PER_TRADE


def simulate_paths(
    probs: np.ndarray,
    payoffs: np.ndarray,
    n_paths: int,
    rng: np.random.Generator,
    *,
    return_realized: bool = False,
) -> dict[str, Any]:
    """Vectorized Monte Carlo. probs and payoffs are both (N, 6). Returns per-path arrays + class realization counts.

    If return_realized=True, additionally returns `realized_per_path` (P, N) and
    `outcomes_per_path` (P, N) for downstream streak / time-to-TP analysis (Task I).
    """
    N = probs.shape[0]
    if N == 0:
        result = {
            "total_pnl": np.zeros(n_paths),
            "max_drawdown": np.zeros(n_paths),
            "win_rate": np.zeros(n_paths),
            "realized_class_counts": np.zeros(6, dtype=np.int64),
            "realized_class_payoff_sum": np.zeros(6),
            "n_trades": 0,
        }
        if return_realized:
            result["realized_per_path"] = np.zeros((n_paths, 0))
            result["outcomes_per_path"] = np.zeros((n_paths, 0), dtype=np.int8)
        return result
    cumprobs = np.cumsum(probs, axis=1)
    cumprobs[:, -1] = 1.0  # numerical safety
    uniforms = rng.random((n_paths, N))  # (P, N)
    outcomes = np.empty((n_paths, N), dtype=np.int8)
    for r in range(N):
        outcomes[:, r] = np.searchsorted(cumprobs[r], uniforms[:, r])
    realized = payoffs[np.arange(N)[None, :], outcomes]  # (P, N)
    running = np.cumsum(realized, axis=1)
    running_max = np.maximum.accumulate(running, axis=1)
    drawdown = (running_max - running).max(axis=1)
    total_pnl = running[:, -1]
    win_rate = (realized > 0).mean(axis=1)
    # Class realization counts and payoff sums across ALL paths × all trades
    realized_class_counts = np.bincount(outcomes.ravel(), minlength=6).astype(np.int64)
    realized_class_payoff_sum = np.zeros(6)
    for c in range(6):
        mask_c = outcomes == c
        if mask_c.any():
            realized_class_payoff_sum[c] = realized[mask_c].sum()
    result = {
        "total_pnl": total_pnl,
        "max_drawdown": drawdown,
        "win_rate": win_rate,
        "realized_class_counts": realized_class_counts,
        "realized_class_payoff_sum": realized_class_payoff_sum,
        "n_trades": N,
    }
    if return_realized:
        result["realized_per_path"] = realized
        result["outcomes_per_path"] = outcomes
    return result


def per_trade_ev_var(probs: np.ndarray, payoffs: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    ev = (probs * payoffs).sum(axis=1)
    ev_sq = (probs * payoffs ** 2).sum(axis=1)
    var = ev_sq - ev ** 2
    return ev, np.sqrt(var.clip(min=0))


def quantiles(arr: np.ndarray, qs=(0.05, 0.25, 0.50, 0.75, 0.95)) -> dict[str, float]:
    if arr.size == 0:
        return {f"p{int(q*100)}": None for q in qs}
    return {f"p{int(q*100)}": float(np.quantile(arr, q)) for q in qs}


def rollup(probs: np.ndarray, payoffs: np.ndarray, n_paths: int, rng: np.random.Generator) -> dict[str, Any]:
    ev, _std = per_trade_ev_var(probs, payoffs)
    trade_ev_mean = float(ev.mean()) if ev.size else 0.0
    trade_ev_std = float(ev.std(ddof=1)) if ev.size > 1 else 0.0
    trade_sharpe = trade_ev_mean / trade_ev_std if trade_ev_std > 0 else None

    sim = simulate_paths(probs, payoffs, n_paths, rng)
    N = sim["n_trades"]
    realized_wins_mean = float(sim["win_rate"].mean()) if N else None

    # Predicted class distribution (mean probability per class across rows)
    predicted_class_dist = {c: float(probs[:, i].mean()) if probs.size else 0.0
                            for i, c in enumerate(CLASSES)}

    # Realized class distribution across all paths × trades
    total_samples = int(sim["realized_class_counts"].sum()) or 1
    realized_class_dist = {c: float(sim["realized_class_counts"][i] / total_samples)
                           for i, c in enumerate(CLASSES)}

    # Win anatomy: for each TP class, count + mean win $ + total $ contribution
    win_anatomy = {}
    for i, c in enumerate(CLASSES):
        cnt = int(sim["realized_class_counts"][i])
        total_dollar = float(sim["realized_class_payoff_sum"][i])
        mean_dollar = total_dollar / cnt if cnt > 0 else None
        win_anatomy[c] = {
            "count_across_paths": cnt,
            "mean_$_when_realized": mean_dollar,
            "total_$_contribution_across_paths": total_dollar,
        }

    # Profit factor: gross wins / |gross losses| — all classes except STOPPED are wins
    gross_wins = sum(sim["realized_class_payoff_sum"][i] for i in TP_CLASS_INDICES)
    gross_losses = -sim["realized_class_payoff_sum"][0]  # STOPPED has negative payoff
    profit_factor = float(gross_wins / gross_losses) if gross_losses > 0 else None

    return {
        "n_trades": int(N),
        "analytical_ev_per_trade": trade_ev_mean,
        "analytical_ev_stdev_per_trade": trade_ev_std,
        "analytical_per_trade_sharpe": trade_sharpe,
        "mc_total_pnl": quantiles(sim["total_pnl"]),
        "mc_max_drawdown": quantiles(sim["max_drawdown"]),
        "mc_win_rate_mean": realized_wins_mean,
        "predicted_class_dist": predicted_class_dist,
        "realized_class_dist": realized_class_dist,
        "win_anatomy": win_anatomy,
        "profit_factor": profit_factor,
    }


def breakdown_by_dimension(
    probs: np.ndarray,
    payoffs: np.ndarray,
    base: pd.DataFrame,
    dim_col: str,
    n_paths: int,
    rng_root: np.random.Generator,
    min_trades: int = 50,
) -> dict[str, dict[str, Any]]:
    """Group rows by base[dim_col] value, rollup per group. Skips groups under min_trades."""
    if dim_col not in base.columns:
        return {}
    values = base[dim_col].to_numpy()
    result: dict[str, dict[str, Any]] = {}
    for val in pd.unique(pd.Series(values)):
        mask = values == val
        if int(mask.sum()) < min_trades:
            continue
        fam_probs = probs[mask]
        fam_payoffs = payoffs[mask]
        rng = np.random.default_rng(rng_root.integers(0, 2**31 - 1))
        key = "<NA>" if pd.isna(val) else str(val)
        result[key] = rollup(fam_probs, fam_payoffs, n_paths, rng)
    return result


def add_hour_bucket_column(base: pd.DataFrame) -> pd.DataFrame:
    """Add hour_bucket string column derived from hour_ct ∈ [0,24)."""
    if "hour_ct" not in base.columns:
        # Derive from ts if hour_ct not present (analysis_frame may have it stripped)
        if "ts" in base.columns:
            ts = pd.to_datetime(base["ts"], utc=True)
            hour_ct = ts.dt.tz_convert(CHICAGO_TZ).dt.hour.to_numpy()
        else:
            base["hour_bucket"] = "UNKNOWN"
            return base
    else:
        hour_ct = base["hour_ct"].to_numpy()
    labels = np.full(hour_ct.shape, "UNKNOWN", dtype=object)
    for lo, hi, label in HOUR_BUCKETS:
        mask = (hour_ct >= lo) & (hour_ct < hi)
        labels[mask] = label
    base["hour_bucket"] = labels
    return base


def add_quartile_buckets(base: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    """Add `<col>_q` quartile bucket column for each col in cols (based on full aggregated data)."""
    for col in cols:
        if col not in base.columns:
            continue
        arr = base[col].to_numpy(dtype=np.float64)
        valid = ~np.isnan(arr)
        if valid.sum() < 4:
            base[f"{col}_q"] = "NA"
            continue
        q = np.quantile(arr[valid], [0.25, 0.5, 0.75])
        bucketed = np.full(arr.shape, "NA", dtype=object)
        bucketed[valid & (arr <= q[0])] = "Q1"
        bucketed[valid & (arr > q[0]) & (arr <= q[1])] = "Q2"
        bucketed[valid & (arr > q[1]) & (arr <= q[2])] = "Q3"
        bucketed[valid & (arr > q[2])] = "Q4"
        base[f"{col}_q"] = bucketed
    return base


def top_combos(
    probs: np.ndarray,
    payoffs: np.ndarray,
    base: pd.DataFrame,
    dims: list[str],
    n_paths: int,
    rng_root: np.random.Generator,
    top_k: int = COMBO_TOP_K,
    min_trades: int = COMBO_MIN_TRADES,
) -> dict[str, Any]:
    """Find top-K combinations of feature values by analytical EV/trade."""
    missing = [d for d in dims if d not in base.columns]
    if missing:
        return {"error": f"missing columns: {missing}"}
    combo_series = base[dims].astype(str).agg(" | ".join, axis=1).to_numpy()
    scored: dict[str, dict[str, Any]] = {}
    for combo in np.unique(combo_series):
        mask = combo_series == combo
        if int(mask.sum()) < min_trades:
            continue
        fam_probs = probs[mask]
        fam_payoffs = payoffs[mask]
        rng = np.random.default_rng(rng_root.integers(0, 2**31 - 1))
        scored[combo] = rollup(fam_probs, fam_payoffs, n_paths, rng)
    ranked_ev_desc = sorted(
        scored.items(), key=lambda kv: kv[1]["analytical_ev_per_trade"], reverse=True
    )
    ranked_ev_asc = sorted(
        scored.items(), key=lambda kv: kv[1]["analytical_ev_per_trade"]
    )
    return {
        "dims": dims,
        "min_trades": min_trades,
        "top_k_by_ev": {k: v for k, v in ranked_ev_desc[:top_k]},
        "bottom_k_by_ev": {k: v for k, v in ranked_ev_asc[:top_k]},
    }


# ---------------------------------------------------------------------------
# Refactored: analysis_frame + cache
# ---------------------------------------------------------------------------

def prepare_fold(
    conn: psycopg2.extensions.connection,
    fold_dir: Path,
    use_macro: bool,
) -> tuple[pd.DataFrame, np.ndarray, list[str]]:
    """Fresh compute for a fold — returns (analysis_frame, probs, feature_cols).

    analysis_frame is the enriched frame (base + time-context + FRED/econ + outcome_label),
    positionally aligned with probs. Downstream tasks (A–I) all slice from analysis_frame.
    Enriched superset is required so Task E can quartile-bucket SHAP-top features that may
    live in the FRED/econ join (not in the pre-enrichment base).
    """
    fs = load_fold_summary(fold_dir)
    test_sessions = pd.to_datetime(fs["test_sessions"])
    base = load_base_training(conn)
    base = add_time_context(base)
    base = base[base["session_date_ct"].isin(test_sessions)].copy()
    if base.empty:
        raise RuntimeError(f"No test rows found for fold {fold_dir.name}")
    enriched_full, _cov = attach_context_features(conn, base=base, use_macro=use_macro)
    feature_frame, feature_cols, _manifest = coerce_feature_frame(enriched_full, label="outcome_label")
    predictor = load_predictor(fold_dir)
    probs = predict_probs_aligned(predictor, feature_frame[feature_cols])
    if len(enriched_full) != len(feature_frame):
        raise RuntimeError(
            f"row count mismatch after coerce_feature_frame: "
            f"enriched_full={len(enriched_full)} feature_frame={len(feature_frame)}"
        )
    # Use enriched_full (pre-coerce) as analysis_frame so FRED/econ + outcome_label are present.
    # outcome_label is in LEAKAGE_COLS but still in the DataFrame — coerce_feature_frame only
    # drops it from the feature_cols list, not from the DataFrame's columns.
    analysis_frame = enriched_full.reset_index(drop=True)
    missing = [c for c in REQUIRED_ANALYSIS_COLS if c not in analysis_frame.columns]
    if missing:
        raise RuntimeError(f"analysis_frame missing required columns: {missing}")
    return analysis_frame, probs, feature_cols


def fold_cache_paths(cache_dir: Path, fold_code: str) -> dict[str, Path]:
    base = cache_dir / fold_code
    return {
        "analysis": base / "analysis.parquet",
        "probs": base / "probs.parquet",
        "payoffs": base / "payoffs.parquet",
    }


def write_fold_cache(
    cache_dir: Path,
    fold_code: str,
    analysis_frame: pd.DataFrame,
    probs: np.ndarray,
    payoffs: np.ndarray,
) -> None:
    paths = fold_cache_paths(cache_dir, fold_code)
    paths["analysis"].parent.mkdir(parents=True, exist_ok=True)
    # Parquet requires typed columns; write analysis_frame as-is (pandas handles it).
    analysis_frame.to_parquet(paths["analysis"], index=False)
    # probs and payoffs are 2D float arrays — wrap as DataFrames with named columns.
    pd.DataFrame(probs, columns=[f"pred_p__{c}" for c in CLASSES]).to_parquet(
        paths["probs"], index=False
    )
    pd.DataFrame(payoffs, columns=[f"payoff__{c}" for c in CLASSES]).to_parquet(
        paths["payoffs"], index=False
    )


def read_fold_cache(
    cache_dir: Path, fold_code: str
) -> tuple[pd.DataFrame, np.ndarray, np.ndarray] | None:
    paths = fold_cache_paths(cache_dir, fold_code)
    if not all(p.exists() for p in paths.values()):
        return None
    analysis_frame = pd.read_parquet(paths["analysis"])
    probs_df = pd.read_parquet(paths["probs"])
    payoffs_df = pd.read_parquet(paths["payoffs"])
    expected_prob_cols = [f"pred_p__{c}" for c in CLASSES]
    expected_payoff_cols = [f"payoff__{c}" for c in CLASSES]
    probs = probs_df[expected_prob_cols].to_numpy(dtype=np.float64)
    payoffs = payoffs_df[expected_payoff_cols].to_numpy(dtype=np.float64)
    if not (len(analysis_frame) == len(probs) == len(payoffs)):
        raise RuntimeError(
            f"Cached row count mismatch for {fold_code}: "
            f"analysis={len(analysis_frame)} probs={len(probs)} payoffs={len(payoffs)}"
        )
    return analysis_frame, probs, payoffs


def load_or_compute_fold(
    *,
    conn: psycopg2.extensions.connection | None,
    fold_dir: Path,
    use_macro: bool,
    cache_dir: Path,
    skip_predict: bool,
) -> tuple[pd.DataFrame, np.ndarray, np.ndarray]:
    """Return (analysis_frame, probs, payoffs) for a fold, from cache if available else fresh."""
    fold_code = fold_dir.name
    cached = read_fold_cache(cache_dir, fold_code)
    if cached is not None:
        print(f"  {fold_code}: cache hit ({len(cached[0])} rows)")
        return cached
    if skip_predict:
        raise SystemExit(
            f"--skip-predict set but no cache found for {fold_code} at {cache_dir / fold_code}. "
            "Run once without --skip-predict to warm the cache."
        )
    if conn is None:
        raise SystemExit("DB connection required when cache miss and --skip-predict not set.")
    print(f"  {fold_code}: cache miss — computing predict_proba...")
    analysis_frame, probs, _feature_cols = prepare_fold(conn, fold_dir, use_macro=use_macro)
    payoffs = compute_payoff_matrix(analysis_frame)
    write_fold_cache(cache_dir, fold_code, analysis_frame, probs, payoffs)
    return analysis_frame, probs, payoffs


# ---------------------------------------------------------------------------
# SHAP feature resolver (Task E dependency)
# ---------------------------------------------------------------------------

def resolve_shap_top_features(
    args: argparse.Namespace, run_id: str, shap_top_n: int
) -> list[str]:
    """Return a list of SHAP-top numeric feature names for Task E quartile expansion.

    Precedence: --shap-top-features (comma-separated) → --shap-artifact CSV → default path.
    """
    if args.shap_top_features:
        feats = [f.strip() for f in args.shap_top_features.split(",") if f.strip()]
        if not feats:
            raise SystemExit("--shap-top-features parsed to empty list.")
        return feats[:shap_top_n]
    shap_path = Path(args.shap_artifact) if args.shap_artifact else (
        Path("artifacts/shap") / run_id / "overall_importance.csv"
    )
    if not shap_path.exists():
        raise SystemExit(
            f"Task E requires a SHAP top-feature list. "
            f"Pass --shap-top-features <csv> or --shap-artifact <path>, or ensure {shap_path} exists."
        )
    df = pd.read_csv(shap_path)
    if "feature_name" not in df.columns or "mean_abs_shap" not in df.columns:
        raise SystemExit(f"SHAP artifact at {shap_path} missing feature_name / mean_abs_shap columns.")
    df_sorted = df.sort_values("mean_abs_shap", ascending=False)
    # Only numeric features can be quartile-bucketed — infer from presence in base later.
    return df_sorted["feature_name"].tolist()[: max(shap_top_n * 3, 10)]  # oversample; filter downstream


def filter_numeric_features(feat_list: list[str], analysis_frame: pd.DataFrame, top_n: int) -> list[str]:
    numeric_feats: list[str] = []
    for feat in feat_list:
        if feat not in analysis_frame.columns:
            continue
        if pd.api.types.is_numeric_dtype(analysis_frame[feat]) and not pd.api.types.is_bool_dtype(
            analysis_frame[feat]
        ):
            numeric_feats.append(feat)
        if len(numeric_feats) >= top_n:
            break
    return numeric_feats


# ---------------------------------------------------------------------------
# Task E — Entry rules
# ---------------------------------------------------------------------------

def task_E_entry_rules(
    probs: np.ndarray,
    payoffs: np.ndarray,
    base: pd.DataFrame,
    *,
    shap_top_features: list[str],
    n_paths: int,
    rng_root: np.random.Generator,
    min_rule_n: int,
    min_required_rules: int,
    top_k: int = 30,
) -> dict[str, Any]:
    """Entry rules across (stop_family × direction × fib_level × hour_bucket × SHAP-top-feature quartiles).

    Score = 0.5 × MC_p5_EV + 0.3 × Sharpe × 100 + 0.2 × (n_trades / max_n_trades).
    Top-30 'take' + bottom-30 'avoid' rules with n_trades >= min_rule_n.
    """
    static_dims = ["stop_family_id", "direction", "fib_level_touched", "hour_bucket"]
    missing_static = [d for d in static_dims if d not in base.columns]
    if missing_static:
        return {"error": f"missing columns: {missing_static}", "requested_dims": static_dims}

    quartile_dims = []
    for feat in shap_top_features:
        q_col = f"{feat}_q"
        if q_col in base.columns:
            quartile_dims.append(q_col)

    dim_plans: list[list[str]] = []
    for keep_count in range(len(quartile_dims), -1, -1):
        dim_plans.append(static_dims + quartile_dims[:keep_count])

    chosen_dims: list[str] | None = None
    chosen_scored: dict[str, dict[str, Any]] = {}
    fallback_steps: list[dict[str, Any]] = []
    best_by_count: tuple[int, list[str], dict[str, dict[str, Any]]] = (-1, static_dims, {})

    for dims in dim_plans:
        combo_series = base[dims].astype(str).agg(" | ".join, axis=1).to_numpy()
        scored: dict[str, dict[str, Any]] = {}
        max_n = 0
        for combo in np.unique(combo_series):
            mask = combo_series == combo
            n = int(mask.sum())
            if n < min_rule_n:
                continue
            max_n = max(max_n, n)
            rng = np.random.default_rng(rng_root.integers(0, 2**31 - 1))
            r = rollup(probs[mask], payoffs[mask], n_paths, rng)
            scored[combo] = r

        for combo, r in scored.items():
            p5 = r["mc_total_pnl"].get("p5") or 0.0
            sharpe = r.get("analytical_per_trade_sharpe") or 0.0
            coverage_norm = (r["n_trades"] / max_n) if max_n else 0.0
            r["entry_score"] = 0.5 * p5 + 0.3 * sharpe * 100.0 + 0.2 * coverage_norm

        fallback_steps.append(
            {
                "dims": dims,
                "eligible_combo_count": len(scored),
            }
        )
        if len(scored) > best_by_count[0]:
            best_by_count = (len(scored), dims, scored)
        if len(scored) >= min_required_rules:
            chosen_dims = dims
            chosen_scored = scored
            break

    if chosen_dims is None:
        chosen_dims = best_by_count[1]
        chosen_scored = best_by_count[2]

    ranked_desc = sorted(chosen_scored.items(), key=lambda kv: kv[1]["entry_score"], reverse=True)
    ranked_asc = sorted(chosen_scored.items(), key=lambda kv: kv[1]["entry_score"])
    overlap_keys = sorted(set(k for k, _ in ranked_desc[:top_k]).intersection(k for k, _ in ranked_asc[:top_k]))
    degraded = bool(len(chosen_scored) < min_required_rules or overlap_keys)
    return {
        "requested_dims": static_dims + quartile_dims,
        "dims": chosen_dims,
        "min_rule_n": min_rule_n,
        "min_required_rules": min_required_rules,
        "eligible_combo_count": len(chosen_scored),
        "degraded": degraded,
        "overlap_keys": overlap_keys,
        "fallback_steps": fallback_steps,
        "shap_top_features": shap_top_features,
        "top_k_take": {k: v for k, v in ranked_desc[:top_k]},
        "top_k_avoid": {k: v for k, v in ranked_asc[:top_k]},
    }


# ---------------------------------------------------------------------------
# Task F — TP-ladder decision tree
# ---------------------------------------------------------------------------

def _analytical_hold_ev(probs: np.ndarray, payoffs: np.ndarray, tp_target: int) -> np.ndarray:
    """Per-row analytical EV of 'hold for TP_target'.

    If outcome ∈ {STOPPED} → take sl_loss payoff.
    If outcome ∈ {TP_1..TP_target} reached → assume exit at TP_target payoff
      (this is a simplification — the true exit would be at outcome class's TP_n;
      for the ladder decision we score the CAP we're committing to).
    If outcome > TP_target → we exited at TP_target payoff.

    For tp_target = n, payoff vector is:
      idx 0: payoffs[:, 0] (STOPPED)
      idx 1..n: payoffs[:, n]     # we committed to hold to n, so exit at TP_n regardless of which TP hit first
      idx n+1..5: payoffs[:, n]   # hit higher TP but we already exited at n

    Equivalently: EV = P(STOPPED) * payoffs[:, 0] + (1 - P(STOPPED)) * payoffs[:, tp_target]
    """
    p_stopped = probs[:, 0]
    p_tp_any = 1.0 - p_stopped
    return p_stopped * payoffs[:, 0] + p_tp_any * payoffs[:, tp_target]


def task_F_tp_ladder(
    probs: np.ndarray,
    payoffs: np.ndarray,
    base: pd.DataFrame,
    *,
    thresholds: list[float] = (0.05, 0.10, 0.15, 0.25, 0.40),
) -> dict[str, Any]:
    """Per (stop_family × fib_level) decision tree: given P(TP_any), best TP target to hold for."""
    result: dict[str, Any] = {"thresholds_used": list(thresholds)}
    tp_total = probs[:, TP_CLASS_INDICES].sum(axis=1)
    families = base["stop_family_id"].to_numpy()
    levels = base["fib_level_touched"].to_numpy()
    per_cohort: dict[str, dict[str, Any]] = {}
    for fam in pd.unique(pd.Series(families)):
        for lvl in pd.unique(pd.Series(levels)):
            cohort_mask = (families == fam) & (levels == lvl)
            if cohort_mask.sum() < 50:
                continue
            cohort_key = f"{fam} | fib_{lvl}"
            per_band: dict[str, Any] = {}
            for t in thresholds:
                band_mask = cohort_mask & (tp_total >= t)
                n = int(band_mask.sum())
                if n == 0:
                    per_band[f"tau_{t}"] = {"n_rows": 0}
                    continue
                p_band = probs[band_mask]
                pay_band = payoffs[band_mask]
                ev_by_target = {
                    f"hold_TP{n_tp}": float(_analytical_hold_ev(p_band, pay_band, n_tp).mean())
                    for n_tp in TP_CLASS_INDICES
                }
                best_n = max(ev_by_target, key=ev_by_target.get)
                per_band[f"tau_{t}"] = {
                    "n_rows": n,
                    "ev_by_target": ev_by_target,
                    "best_target": best_n,
                    "best_ev": ev_by_target[best_n],
                }
            per_cohort[cohort_key] = per_band
    result["per_cohort"] = per_cohort
    return result


# ---------------------------------------------------------------------------
# Task G — Calibration
# ---------------------------------------------------------------------------

def task_G_calibration(
    probs: np.ndarray,
    base: pd.DataFrame,
    *,
    min_rows: int = 200,
) -> list[dict[str, Any]]:
    """Per-cohort calibration: predicted vs realized frequency per class with verdict."""
    rows: list[dict[str, Any]] = []
    cohort_dims = ["stop_family_id", "direction", "fib_level_touched"]
    outcome_labels = base["outcome_label"].astype(str).to_numpy() if "outcome_label" in base.columns else None
    if outcome_labels is None:
        return rows
    for dim in cohort_dims:
        if dim not in base.columns:
            continue
        values = base[dim].to_numpy()
        for val in pd.unique(pd.Series(values)):
            mask = values == val
            if mask.sum() < min_rows:
                continue
            sub_probs = probs[mask]
            sub_labels = outcome_labels[mask]
            for i, cls in enumerate(CLASSES):
                predicted = float(sub_probs[:, i].mean())
                realized = float((sub_labels == cls).mean())
                if predicted > 0:
                    ratio = realized / predicted
                    if 0.7 <= ratio <= 1.3:
                        verdict = "OK"
                    elif realized > predicted:
                        verdict = "UNDERCONFIDENT"
                    else:
                        verdict = "OVERCONFIDENT"
                else:
                    ratio = math.inf if realized > 0 else math.nan
                    if realized > 0.005:
                        verdict = "ZERO_PREDICTION_MISS"
                    else:
                        verdict = "OK"
                rows.append(
                    {
                        "cohort_dim": dim,
                        "cohort_value": str(val),
                        "n_rows": int(mask.sum()),
                        "class": cls,
                        "predicted_mean_p": predicted,
                        "realized_freq": realized,
                        "ratio": ratio if not math.isnan(ratio) else None,
                        "verdict": verdict,
                    }
                )
    return rows


# ---------------------------------------------------------------------------
# Task H — Regime stability
# ---------------------------------------------------------------------------

def task_H_regime_stability(
    probs: np.ndarray,
    payoffs: np.ndarray,
    base: pd.DataFrame,
    ts: np.ndarray,
    *,
    n_paths: int,
    rng_root: np.random.Generator,
    split_method: str,
    min_stable_corr: float,
) -> dict[str, Any]:
    """Split chronologically, re-run per-stop-family rollup on each half, compare ranks."""
    ts_num = pd.to_datetime(ts, utc=True).astype("int64").to_numpy()
    if split_method == "median_ts":
        cutoff = np.median(ts_num)
        early_mask = ts_num < cutoff
    else:  # midpoint_rows
        cutoff_idx = len(ts_num) // 2
        order = np.argsort(ts_num)
        early_mask = np.zeros(len(ts_num), dtype=bool)
        early_mask[order[:cutoff_idx]] = True

    families = base["stop_family_id"].to_numpy()
    fam_unique = sorted(pd.unique(pd.Series(families)).tolist())

    def half_rollups(mask: np.ndarray) -> dict[str, dict[str, Any]]:
        out: dict[str, dict[str, Any]] = {}
        for fam in fam_unique:
            fam_mask = mask & (families == fam)
            if fam_mask.sum() < 30:
                continue
            rng = np.random.default_rng(rng_root.integers(0, 2**31 - 1))
            out[fam] = rollup(probs[fam_mask], payoffs[fam_mask], n_paths, rng)
        return out

    early = half_rollups(early_mask)
    late = half_rollups(~early_mask)

    # Spearman correlation on EV/trade ranking across halves
    shared_fams = sorted(set(early.keys()) & set(late.keys()))
    if len(shared_fams) < 2:
        rho = None
        verdict = "INSUFFICIENT"
    else:
        early_ranks = pd.Series(
            {f: early[f]["analytical_ev_per_trade"] for f in shared_fams}
        ).rank()
        late_ranks = pd.Series(
            {f: late[f]["analytical_ev_per_trade"] for f in shared_fams}
        ).rank()
        rho = float(early_ranks.corr(late_ranks, method="spearman"))
        verdict = "STABLE" if rho >= min_stable_corr else "FRAGILE"

    return {
        "split_method": split_method,
        "cutoff_ts_ns": float(cutoff) if split_method == "median_ts" else None,
        "early_n": int(early_mask.sum()),
        "late_n": int((~early_mask).sum()),
        "early_by_stop_family": early,
        "late_by_stop_family": late,
        "spearman_rho_ev_rank": rho,
        "min_stable_corr": min_stable_corr,
        "verdict": verdict,
    }


# ---------------------------------------------------------------------------
# Task I — Win profile
# ---------------------------------------------------------------------------

def task_I_win_profile(
    probs: np.ndarray,
    payoffs: np.ndarray,
    base: pd.DataFrame,
    *,
    n_paths: int,
    rng_root: np.random.Generator,
) -> dict[str, Any]:
    """Per stop_family: streaks, time-to-TP, max single win, underwater duration."""
    families = base["stop_family_id"].to_numpy()
    fam_unique = sorted(pd.unique(pd.Series(families)).tolist())
    per_family: dict[str, Any] = {}
    for fam in fam_unique:
        mask = families == fam
        if mask.sum() < 100:
            continue
        rng = np.random.default_rng(rng_root.integers(0, 2**31 - 1))
        sim = simulate_paths(
            probs[mask], payoffs[mask], n_paths, rng, return_realized=True
        )
        realized = sim["realized_per_path"]  # (P, N)
        outcomes = sim["outcomes_per_path"]  # (P, N)
        # Winning streaks per path: longest run of realized > 0
        def _longest_runs(arr: np.ndarray, predicate) -> np.ndarray:
            """Return longest run of True values per path row."""
            out = np.zeros(arr.shape[0], dtype=np.int32)
            for i in range(arr.shape[0]):
                mask_row = predicate(arr[i])
                if not mask_row.any():
                    continue
                run = 0
                best = 0
                for v in mask_row:
                    if v:
                        run += 1
                        if run > best:
                            best = run
                    else:
                        run = 0
                out[i] = best
            return out

        win_streaks = _longest_runs(realized, lambda a: a > 0)
        loss_streaks = _longest_runs(realized, lambda a: a < 0)
        # Max single win (largest positive realized payoff per path)
        max_single_win = np.where(realized > 0, realized, 0).max(axis=1)
        # Underwater duration: longest stretch where running P&L below its running max
        running = np.cumsum(realized, axis=1)
        running_max = np.maximum.accumulate(running, axis=1)
        underwater = running < running_max
        underwater_durations = _longest_runs(underwater, lambda a: a)
        # Time-to-TP per path: mean index at which any TP class realized
        tp_mask = outcomes > 0  # class idx 1..5 all TPs
        ttt_means = np.zeros(outcomes.shape[0])
        for i in range(outcomes.shape[0]):
            hits = np.where(tp_mask[i])[0]
            ttt_means[i] = hits.mean() if hits.size else np.nan

        per_family[fam] = {
            "n_trades": int(mask.sum()),
            "winning_streak_quantiles": quantiles(win_streaks.astype(float)),
            "losing_streak_quantiles": quantiles(loss_streaks.astype(float)),
            "max_single_win_quantiles": quantiles(max_single_win),
            "underwater_duration_bars_quantiles": quantiles(underwater_durations.astype(float)),
            "time_to_first_tp_bars_mean": float(np.nanmean(ttt_means)) if ttt_means.size else None,
        }
    return per_family


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

CANONICAL_ZOO_FAMILIES = {"GBM", "CAT", "XGB", "RF", "XT", "NN_TORCH", "FASTAI"}


def canonical_family_for_model(model_name: str | None) -> str | None:
    if not model_name:
        return None
    name = str(model_name)
    if name.startswith("LightGBM"):
        return "GBM"
    if name.startswith("CatBoost"):
        return "CAT"
    if name.startswith("XGBoost"):
        return "XGB"
    if name.startswith("RandomForest"):
        return "RF"
    if name.startswith("ExtraTrees"):
        return "XT"
    if name.startswith("NeuralNetTorch"):
        return "NN_TORCH"
    if name.startswith("NeuralNetFastAI") or "FastAI" in name:
        return "FASTAI"
    return None


def infer_run_integrity(run_dir: Path) -> dict[str, Any]:
    has_internal_ensembling = False
    missing_families_by_fold: dict[str, list[str]] = {}
    lineage_failures: dict[str, str] = {}
    partial_class_folds: list[str] = []

    for fold_dir in sorted(p for p in run_dir.glob("fold_*") if p.is_dir()):
        fold_code = fold_dir.name
        summary_path = fold_dir / "fold_summary.json"
        if not summary_path.exists():
            continue
        summary = json.loads(summary_path.read_text())
        autogluon = summary.get("autogluon") or {}
        num_bag = int(autogluon.get("num_bag_folds") or 0)
        num_stack = int(autogluon.get("num_stack_levels") or 0)
        dynamic_stacking = str(autogluon.get("dynamic_stacking") or "").lower()
        if num_bag > 0 or num_stack > 0 or dynamic_stacking == "auto":
            has_internal_ensembling = True

        families = set(autogluon.get("zoo_families_present") or [])
        missing = sorted(CANONICAL_ZOO_FAMILIES - families)
        if missing:
            missing_families_by_fold[fold_code] = missing
        else:
            leaderboard_path = fold_dir / "leaderboard.csv"
            if leaderboard_path.exists():
                try:
                    lb = pd.read_csv(leaderboard_path)
                    lb_models = lb.get("model", pd.Series(dtype=str)).dropna().astype(str).tolist()
                    lb_families = {
                        fam
                        for model_name in lb_models
                        if (fam := canonical_family_for_model(model_name)) is not None
                    }
                    lb_missing = sorted(CANONICAL_ZOO_FAMILIES - lb_families)
                    if lb_missing:
                        missing_families_by_fold[fold_code] = lb_missing
                except Exception:
                    missing_families_by_fold[fold_code] = sorted(CANONICAL_ZOO_FAMILIES)

        if summary.get("val_missing_labels") or summary.get("test_missing_labels"):
            partial_class_folds.append(fold_code)

        best_model = autogluon.get("best_model")
        test_macro = autogluon.get("test_macro_f1")
        leaderboard_file = autogluon.get("leaderboard_path")
        if best_model and test_macro is not None and leaderboard_file:
            try:
                lb = pd.read_csv(leaderboard_file)
                row = lb.loc[lb["model"].astype(str) == str(best_model)]
                if row.empty:
                    lineage_failures[fold_code] = f"best_model_missing:{best_model}"
                elif "score_test" in row.columns:
                    score_test = float(row["score_test"].iloc[0])
                    if abs(score_test - float(test_macro)) > 1e-6:
                        lineage_failures[fold_code] = (
                            f"score_test={score_test:.6f} test_macro_f1={float(test_macro):.6f}"
                        )
            except Exception as exc:
                lineage_failures[fold_code] = f"lineage_check_error:{exc}"

    passed = (
        (not has_internal_ensembling)
        and (not missing_families_by_fold)
        and (not lineage_failures)
        and (not partial_class_folds)
    )
    return {
        "passed": passed,
        "has_internal_ensembling": has_internal_ensembling,
        "missing_families_by_fold": missing_families_by_fold,
        "lineage_failures": lineage_failures,
        "partial_class_folds": sorted(partial_class_folds),
    }


def build_run_note(run_integrity: dict[str, Any]) -> str:
    if run_integrity.get("passed"):
        return (
            "Source run passed integrity checks: no internal IID bagging/stacking, "
            "canonical full zoo present in every fold, strict class coverage, and consistent "
            "model↔metric lineage. Absolute $ figures still depend on calibration and regime drift."
        )

    issues: list[str] = []
    if run_integrity.get("has_internal_ensembling"):
        issues.append("internal IID bagging/stacking detected")
    if run_integrity.get("missing_families_by_fold"):
        issues.append("partial zoo detected")
    if run_integrity.get("lineage_failures"):
        issues.append("model↔metric lineage mismatches detected")
    if run_integrity.get("partial_class_folds"):
        issues.append("validation/test class coverage gaps detected")
    issue_text = ", ".join(issues) if issues else "unspecified run-integrity warnings"
    return (
        f"Source run integrity warnings: {issue_text}. Relative rankings across stop_family / "
        "threshold / entry features may still be informative; absolute $ numbers should be read skeptically."
    )


def main() -> None:
    args = parse_args()
    run_dir = Path(args.artifacts_root) / args.run_id
    if not run_dir.exists():
        raise SystemExit(f"Run dir not found: {run_dir}")
    out_dir = run_dir / "monte_carlo"
    out_dir.mkdir(parents=True, exist_ok=True)
    cache_dir = Path(args.cache_dir) if args.cache_dir else (out_dir / "cache")
    cache_dir.mkdir(parents=True, exist_ok=True)

    tasks_enabled = {t.strip().upper() for t in args.tasks.split(",") if t.strip()}

    fold_dirs = sorted(p for p in run_dir.glob("fold_*") if p.is_dir())
    if not fold_dirs:
        raise SystemExit(f"No fold_* directories under {run_dir}")
    run_integrity = infer_run_integrity(run_dir)

    print(f"[{datetime.now(UTC).isoformat()}] run_id={args.run_id} folds={len(fold_dirs)} tasks={sorted(tasks_enabled)}")

    # Task A — per stop_family; Task B — entry-feature breakdowns per family;
    # Task C — threshold sweep; Task D — top-N cross-feature combos overall
    task_A = {"per_fold": {}, "aggregated_by_stop_family": {}}
    task_B = {"aggregated_entry_breakdowns": {}}
    task_C = {"per_fold": {}, "aggregated_by_threshold_and_stop_family": {}}
    task_D: dict[str, Any] = {}
    task_E: dict[str, Any] = {}
    task_F: dict[str, Any] = {}
    task_G: list[dict[str, Any]] = []
    task_H: dict[str, Any] = {}
    task_I: dict[str, Any] = {}

    all_probs = []
    all_payoffs = []
    all_families = []
    all_ts = []
    all_tp_total = []  # P(any TP hit) per row, used by Task C
    all_bases = []

    rng_root = np.random.default_rng(args.seed)

    # Load (or compute) per-fold data
    conn_ctx = None if args.skip_predict else psycopg2.connect(args.dsn)
    try:
        for fold_dir in fold_dirs:
            fold_code = fold_dir.name
            analysis_frame, probs, payoffs = load_or_compute_fold(
                conn=conn_ctx,
                fold_dir=fold_dir,
                use_macro=not args.no_macro,
                cache_dir=cache_dir,
                skip_predict=args.skip_predict,
            )
            families = analysis_frame["stop_family_id"].to_numpy()
            ts = analysis_frame["ts"].to_numpy()
            tp_total = probs[:, TP_CLASS_INDICES].sum(axis=1)

            # Task A per fold
            if "A" in tasks_enabled:
                task_A["per_fold"][fold_code] = {}
                for fam in np.unique(families):
                    mask = families == fam
                    fam_probs = probs[mask]
                    fam_payoffs = payoffs[mask]
                    order = np.argsort(ts[mask])
                    fam_probs = fam_probs[order]
                    fam_payoffs = fam_payoffs[order]
                    rng = np.random.default_rng(rng_root.integers(0, 2**31 - 1))
                    task_A["per_fold"][fold_code][fam] = rollup(
                        fam_probs, fam_payoffs, args.n_paths, rng
                    )

            # Task C per fold
            if "C" in tasks_enabled:
                task_C["per_fold"][fold_code] = {}
                for tau in DEFAULT_THRESHOLDS:
                    task_C["per_fold"][fold_code][str(tau)] = {}
                    gate = tp_total >= tau
                    for fam in np.unique(families):
                        mask = (families == fam) & gate
                        if not mask.any():
                            task_C["per_fold"][fold_code][str(tau)][fam] = {"n_trades": 0}
                            continue
                        fam_probs = probs[mask]
                        fam_payoffs = payoffs[mask]
                        order = np.argsort(ts[mask])
                        fam_probs = fam_probs[order]
                        fam_payoffs = fam_payoffs[order]
                        rng = np.random.default_rng(rng_root.integers(0, 2**31 - 1))
                        task_C["per_fold"][fold_code][str(tau)][fam] = rollup(
                            fam_probs, fam_payoffs, args.n_paths, rng
                        )

            all_probs.append(probs)
            all_payoffs.append(payoffs)
            all_families.append(families)
            all_ts.append(ts)
            all_tp_total.append(tp_total)
            all_bases.append(analysis_frame.reset_index(drop=True))
    finally:
        if conn_ctx is not None:
            conn_ctx.close()

    # Aggregated across folds, chronological
    cat_probs = np.concatenate(all_probs)
    cat_payoffs = np.concatenate(all_payoffs)
    cat_families = np.concatenate(all_families)
    cat_ts = np.concatenate(all_ts)
    cat_tp_total = np.concatenate(all_tp_total)
    cat_base = pd.concat(all_bases, ignore_index=True)
    # Bucket numeric entry features on aggregated data
    cat_base = add_quartile_buckets(cat_base, ENTRY_BREAKDOWN_DIMS_NUMERIC)
    cat_base = add_hour_bucket_column(cat_base)

    # Task A aggregated
    if "A" in tasks_enabled:
        for fam in np.unique(cat_families):
            mask = cat_families == fam
            order = np.argsort(cat_ts[mask])
            rng = np.random.default_rng(rng_root.integers(0, 2**31 - 1))
            task_A["aggregated_by_stop_family"][fam] = rollup(
                cat_probs[mask][order], cat_payoffs[mask][order], args.n_paths, rng
            )

    # Task B — entry-feature breakdowns per stop_family × dimension
    if "B" in tasks_enabled:
        per_family_dims = (
            ENTRY_BREAKDOWN_DIMS_CATEGORICAL
            + [f"{c}_q" for c in ENTRY_BREAKDOWN_DIMS_NUMERIC]
            + ["hour_bucket"]
        )
        for fam in np.unique(cat_families):
            mask = cat_families == fam
            task_B["aggregated_entry_breakdowns"][fam] = {}
            for dim in per_family_dims:
                task_B["aggregated_entry_breakdowns"][fam][dim] = breakdown_by_dimension(
                    cat_probs[mask],
                    cat_payoffs[mask],
                    cat_base.loc[mask].reset_index(drop=True),
                    dim,
                    args.n_paths,
                    rng_root,
                    min_trades=50,
                )

    # Task D — top / bottom combinations across {stop_family, direction, hour_bucket, archetype}
    if "D" in tasks_enabled:
        task_D = top_combos(
            cat_probs,
            cat_payoffs,
            cat_base,
            COMBO_DIMS,
            args.n_paths,
            rng_root,
        )

    # Task C aggregated
    if "C" in tasks_enabled:
        for tau in DEFAULT_THRESHOLDS:
            task_C["aggregated_by_threshold_and_stop_family"][str(tau)] = {}
            gate = cat_tp_total >= tau
            for fam in np.unique(cat_families):
                mask = (cat_families == fam) & gate
                if not mask.any():
                    task_C["aggregated_by_threshold_and_stop_family"][str(tau)][fam] = {"n_trades": 0}
                    continue
                order = np.argsort(cat_ts[mask])
                rng = np.random.default_rng(rng_root.integers(0, 2**31 - 1))
                task_C["aggregated_by_threshold_and_stop_family"][str(tau)][fam] = rollup(
                    cat_probs[mask][order], cat_payoffs[mask][order], args.n_paths, rng
                )

    # Task E — entry rules
    if "E" in tasks_enabled:
        candidate_feats = resolve_shap_top_features(args, args.run_id, args.shap_top_n)
        # Filter to numeric features available in analysis_frame
        shap_numeric = filter_numeric_features(candidate_feats, cat_base, args.shap_top_n)
        # Quartile-bucket the selected SHAP features
        cat_base = add_quartile_buckets(cat_base, shap_numeric)
        task_E = task_E_entry_rules(
            cat_probs,
            cat_payoffs,
            cat_base,
            shap_top_features=shap_numeric,
            n_paths=args.n_paths,
            rng_root=rng_root,
            min_rule_n=args.min_rule_n,
            min_required_rules=args.task_e_min_required_rules,
        )

    # Task F — TP ladder
    if "F" in tasks_enabled:
        task_F = task_F_tp_ladder(cat_probs, cat_payoffs, cat_base)

    # Task G — calibration
    if "G" in tasks_enabled:
        task_G = task_G_calibration(cat_probs, cat_base)

    # Task H — regime stability
    if "H" in tasks_enabled:
        task_H = task_H_regime_stability(
            cat_probs,
            cat_payoffs,
            cat_base,
            cat_ts,
            n_paths=args.n_paths,
            rng_root=rng_root,
            split_method=args.regime_split_method,
            min_stable_corr=args.min_stable_corr,
        )

    # Task I — win profile
    if "I" in tasks_enabled:
        task_I = task_I_win_profile(
            cat_probs, cat_payoffs, cat_base, n_paths=args.n_paths, rng_root=rng_root
        )

    # Write outputs
    meta = {
        "run_id": args.run_id,
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "n_paths": args.n_paths,
        "seed": args.seed,
        "flat_fee_per_trade_usd": FLAT_FEE_PER_TRADE,
        "mes_point_value": MES_POINT_VALUE,
        "classes": CLASSES,
        "thresholds": DEFAULT_THRESHOLDS,
        "indicator_settings_frozen": INDICATOR_SETTINGS_FROZEN,
        "tasks_enabled": sorted(tasks_enabled),
        "min_rule_n": args.min_rule_n,
        "shap_top_n": args.shap_top_n,
        "regime_split_method": args.regime_split_method,
        "min_stable_corr": args.min_stable_corr,
        "run_integrity": run_integrity,
        "note": build_run_note(run_integrity),
    }

    def _write(name: str, payload: Any) -> None:
        (out_dir / name).write_text(json.dumps({**meta, **payload} if isinstance(payload, dict) else {"data": payload, **meta}, indent=2, default=str))

    if "A" in tasks_enabled:
        _write("task_A.json", task_A)
    if "B" in tasks_enabled:
        _write("task_B.json", task_B)
    if "C" in tasks_enabled:
        _write("task_C.json", task_C)
    if "D" in tasks_enabled:
        _write("task_D.json", task_D)
    if "E" in tasks_enabled:
        _write("task_E_entry_rules.json", task_E)
    if "F" in tasks_enabled:
        _write("task_F_tp_ladder.json", task_F)
    if "G" in tasks_enabled:
        _write("task_G_calibration.json", task_G)
    if "H" in tasks_enabled:
        _write("task_H_regime_stability.json", task_H)
    if "I" in tasks_enabled:
        _write("task_I_win_profile.json", task_I)

    # Summary markdown — top-line pick per task
    fam_ev = (
        {
            f: d["analytical_ev_per_trade"]
            for f, d in task_A.get("aggregated_by_stop_family", {}).items()
        }
        if "A" in tasks_enabled else {}
    )
    ranked = sorted(fam_ev.items(), key=lambda kv: kv[1], reverse=True)

    summary: list[str] = []
    summary += ["# Monte Carlo Summary", ""]
    summary += [f"run_id: `{args.run_id}`", f"generated: {meta['generated_at_utc']}", ""]
    summary += [f"Friction: ${FLAT_FEE_PER_TRADE:.2f} flat per trade (NinjaTrader Basic free — 1 tick).",
                f"MES multiplier: ${MES_POINT_VALUE:.2f}/point.", "1 contract fixed sizing.", ""]
    summary += ["**Indicator settings frozen in this training surface:**",
                f"- timeframe: {INDICATOR_SETTINGS_FROZEN['fib_owner_timeframe']}",
                f"- ZigZag Deviation: {INDICATOR_SETTINGS_FROZEN['zigzag_deviation']}",
                f"- ZigZag Depth: {INDICATOR_SETTINGS_FROZEN['zigzag_depth']}",
                f"- Threshold Floor: {INDICATOR_SETTINGS_FROZEN['threshold_floor']}",
                f"- Min Fib Range: {INDICATOR_SETTINGS_FROZEN['min_fib_range']}", ""]

    # --- Task A table ---
    if "A" in tasks_enabled:
        summary += ["## Task A — EV per trade by stop_family (aggregated across 5 folds)", ""]
        summary += ["| stop_family | n_trades | EV/trade ($) | stdev/trade ($) | per-trade Sharpe | MC total_pnl p50 | MC max_dd p95 | profit factor |"]
        summary += ["|-------------|---------:|-------------:|---------------:|-----------------:|-----------------:|---------------:|--------------:|"]
        for fam, _ev in ranked:
            d = task_A["aggregated_by_stop_family"][fam]
            sharpe = d.get("analytical_per_trade_sharpe")
            pf = d.get("profit_factor")
            sharpe_s = f"{sharpe:.4f}" if sharpe is not None else "-"
            pf_s = f"{pf:.3f}" if pf is not None else "-"
            summary.append(
                f"| {fam} | {d['n_trades']} | {d['analytical_ev_per_trade']:.2f} | "
                f"{d['analytical_ev_stdev_per_trade']:.2f} | {sharpe_s} | "
                f"{d['mc_total_pnl']['p50']:.0f} | {d['mc_max_drawdown']['p95']:.0f} | {pf_s} |"
            )
        summary.append("")

        summary += ["### Win anatomy per stop_family (realized class frequencies × mean $ per class)", ""]
        for fam, _ in ranked:
            d = task_A["aggregated_by_stop_family"][fam]
            summary.append(f"**{fam}** (win_rate_mean={d['mc_win_rate_mean']:.4f})")
            summary.append("")
            summary.append("| class | realized freq | mean $ when realized | predicted mean P |")
            summary.append("|-------|--------------:|---------------------:|-----------------:|")
            for c in CLASSES:
                rf = d["realized_class_dist"][c]
                wa = d["win_anatomy"][c]
                mean_dollar = wa["mean_$_when_realized"]
                mean_dollar_s = f"{mean_dollar:.2f}" if mean_dollar is not None else "-"
                pp = d["predicted_class_dist"][c]
                summary.append(f"| {c} | {rf:.4f} | {mean_dollar_s} | {pp:.4f} |")
            summary.append("")

    # --- Task C best threshold per family ---
    if "C" in tasks_enabled:
        summary += ["## Task C — Best threshold per stop_family by MC total_pnl p50 (aggregated)", ""]
        summary += ["| stop_family | best_tau | n_trades | MC total_pnl p50 | MC total_pnl p5 | MC max_dd p95 |"]
        summary += ["|-------------|---------:|---------:|-----------------:|----------------:|---------------:|"]
        for fam in sorted(fam_ev.keys()):
            best_tau, best_entry = None, None
            for tau, per_fam in task_C["aggregated_by_threshold_and_stop_family"].items():
                entry = per_fam.get(fam, {})
                if entry.get("n_trades", 0) == 0:
                    continue
                p50 = entry["mc_total_pnl"]["p50"]
                if best_entry is None or p50 > best_entry["mc_total_pnl"]["p50"]:
                    best_entry, best_tau = entry, tau
            if best_entry is None:
                summary.append(f"| {fam} | - | 0 | - | - | - |")
            else:
                summary.append(
                    f"| {fam} | {best_tau} | {best_entry['n_trades']} | "
                    f"{best_entry['mc_total_pnl']['p50']:.0f} | "
                    f"{best_entry['mc_total_pnl']['p5']:.0f} | "
                    f"{best_entry['mc_max_drawdown']['p95']:.0f} |"
                )
        summary.append("")

    # --- Task D top/bottom combos ---
    if "D" in tasks_enabled and task_D:
        summary += ["## Task D — Top / bottom entry-condition combos by EV/trade", ""]
        summary += [f"Dimensions: {task_D.get('dims', [])} — min_trades={task_D.get('min_trades', COMBO_MIN_TRADES)}", ""]
        summary += ["### Top combos by analytical EV/trade", ""]
        summary += ["| combo | n_trades | EV/trade ($) | Sharpe | MC total_pnl p50 | profit factor |"]
        summary += ["|-------|---------:|-------------:|-------:|-----------------:|--------------:|"]
        for combo, d in (task_D.get("top_k_by_ev") or {}).items():
            sharpe = d.get("analytical_per_trade_sharpe")
            pf = d.get("profit_factor")
            sharpe_s = f"{sharpe:.4f}" if sharpe is not None else "-"
            pf_s = f"{pf:.3f}" if pf is not None else "-"
            summary.append(
                f"| {combo} | {d['n_trades']} | {d['analytical_ev_per_trade']:.2f} | "
                f"{sharpe_s} | {d['mc_total_pnl']['p50']:.0f} | {pf_s} |"
            )
        summary.append("")
        summary += ["### Bottom combos by analytical EV/trade (avoid list)", ""]
        summary += ["| combo | n_trades | EV/trade ($) | Sharpe | MC total_pnl p50 |"]
        summary += ["|-------|---------:|-------------:|-------:|-----------------:|"]
        for combo, d in (task_D.get("bottom_k_by_ev") or {}).items():
            sharpe = d.get("analytical_per_trade_sharpe")
            sharpe_s = f"{sharpe:.4f}" if sharpe is not None else "-"
            summary.append(
                f"| {combo} | {d['n_trades']} | {d['analytical_ev_per_trade']:.2f} | "
                f"{sharpe_s} | {d['mc_total_pnl']['p50']:.0f} |"
            )
        summary.append("")

    # --- Task E entry rules ---
    if "E" in tasks_enabled and task_E.get("top_k_take"):
        summary += ["## Task E — Entry Rules", ""]
        summary += [
            f"Requested dims: {task_E.get('requested_dims', [])}",
            f"Effective dims: {task_E.get('dims', [])} — min_rule_n={task_E.get('min_rule_n')} "
            f"min_required_rules={task_E.get('min_required_rules')} eligible={task_E.get('eligible_combo_count')}",
            f"Task E degraded: {task_E.get('degraded')} overlap_keys={len(task_E.get('overlap_keys', []))}",
            "",
        ]
        summary += ["### Top 10 TAKE rules (ranked by entry_score)", ""]
        summary += ["| combo | n_trades | EV/trade ($) | MC p5 PnL | Sharpe | entry_score |"]
        summary += ["|-------|---------:|-------------:|----------:|-------:|------------:|"]
        for combo, d in list(task_E["top_k_take"].items())[:10]:
            sharpe = d.get("analytical_per_trade_sharpe")
            sharpe_s = f"{sharpe:.3f}" if sharpe is not None else "-"
            summary.append(
                f"| {combo} | {d['n_trades']} | {d['analytical_ev_per_trade']:.2f} | "
                f"{d['mc_total_pnl'].get('p5', 0):.0f} | {sharpe_s} | {d['entry_score']:.2f} |"
            )
        summary.append("")
        summary += ["### Top 10 AVOID rules (ranked by entry_score ascending)", ""]
        summary += ["| combo | n_trades | EV/trade ($) | MC p5 PnL | Sharpe | entry_score |"]
        summary += ["|-------|---------:|-------------:|----------:|-------:|------------:|"]
        for combo, d in list(task_E["top_k_avoid"].items())[:10]:
            sharpe = d.get("analytical_per_trade_sharpe")
            sharpe_s = f"{sharpe:.3f}" if sharpe is not None else "-"
            summary.append(
                f"| {combo} | {d['n_trades']} | {d['analytical_ev_per_trade']:.2f} | "
                f"{d['mc_total_pnl'].get('p5', 0):.0f} | {sharpe_s} | {d['entry_score']:.2f} |"
            )
        summary.append("")

    # --- Task F TP ladder summary ---
    if "F" in tasks_enabled and task_F.get("per_cohort"):
        summary += ["## Task F — TP-Ladder Decision Tree (per stop_family × fib_level)", ""]
        summary += [f"Thresholds: {task_F.get('thresholds_used', [])}. Per cohort: best TP target per probability band.", ""]
        summary += ["| cohort | tau band | n_rows | best_TP | best_EV |"]
        summary += ["|--------|---------:|-------:|---------|--------:|"]
        for cohort, bands in task_F["per_cohort"].items():
            for band, d in bands.items():
                if d.get("n_rows", 0) == 0:
                    continue
                summary.append(
                    f"| {cohort} | {band} | {d['n_rows']} | "
                    f"{d.get('best_target', '-')} | {d.get('best_ev', 0):.2f} |"
                )
        summary.append("")

    # --- Task G calibration summary ---
    if "G" in tasks_enabled and task_G:
        bad = [r for r in task_G if r["verdict"] != "OK"]
        summary += ["## Task G — Calibration", ""]
        if not bad:
            summary += ["All cohort × class pairs within [0.7, 1.3] ratio range. Calibration looks clean.", ""]
        else:
            summary += [f"{len(bad)} cohort × class pairs flagged off-calibration (verdict != OK).", ""]
            summary += ["| cohort_dim | cohort_value | class | predicted | realized | ratio | verdict |"]
            summary += ["|-----------|--------------|-------|----------:|---------:|------:|---------|"]
            for r in bad[:25]:
                ratio_s = f"{r['ratio']:.3f}" if r.get("ratio") is not None else "∞"
                summary.append(
                    f"| {r['cohort_dim']} | {r['cohort_value']} | {r['class']} | "
                    f"{r['predicted_mean_p']:.4f} | {r['realized_freq']:.4f} | "
                    f"{ratio_s} | {r['verdict']} |"
                )
            summary.append("")

    # --- Task H regime stability ---
    if "H" in tasks_enabled and task_H:
        summary += ["## Task H — Regime Stability", ""]
        rho = task_H.get("spearman_rho_ev_rank")
        rho_s = f"{rho:.3f}" if rho is not None else "-"
        summary += [
            f"Split method: `{task_H.get('split_method')}`. Early N: {task_H.get('early_n')}. Late N: {task_H.get('late_n')}.",
            f"Spearman ρ on stop_family EV rank across halves: {rho_s}. "
            f"Threshold for STABLE: ≥{task_H.get('min_stable_corr')}. **Verdict: {task_H.get('verdict')}**.", "",
        ]

    # --- Task I win profile ---
    if "I" in tasks_enabled and task_I:
        summary += ["## Task I — Win Profile (per stop_family)", ""]
        summary += ["| stop_family | n_trades | win streak p50 | loss streak p50 | max_single_win p50 | underwater bars p95 | mean time-to-first-TP bars |"]
        summary += ["|-------------|---------:|---------------:|----------------:|-------------------:|--------------------:|---------------------------:|"]
        for fam in sorted(task_I.keys()):
            d = task_I[fam]
            ws = d["winning_streak_quantiles"]["p50"]
            ls = d["losing_streak_quantiles"]["p50"]
            msw = d["max_single_win_quantiles"]["p50"]
            udp95 = d["underwater_duration_bars_quantiles"]["p95"]
            tt = d.get("time_to_first_tp_bars_mean")
            tt_s = f"{tt:.1f}" if tt is not None and not math.isnan(tt) else "-"
            summary.append(
                f"| {fam} | {d['n_trades']} | {ws:.0f} | {ls:.0f} | "
                f"{msw:.0f} | {udp95:.0f} | {tt_s} |"
            )
        summary.append("")

    summary += ["## Caveats", ""]
    summary += [f"- {meta['note']}"]
    summary += ["- Indicator SETTINGS are not varied here. Use `scripts/ag/tv_auto_tune.py` to sweep Deviation/Depth/Threshold/MinFibRange and compare training outputs."]
    (out_dir / "summary.md").write_text("\n".join(summary) + "\n")

    print(f"[{datetime.now(UTC).isoformat()}] wrote outputs to {out_dir}/")
    if "A" in tasks_enabled and ranked:
        print(f"Ranked stop_family by EV/trade: {ranked}")


if __name__ == "__main__":
    main()
