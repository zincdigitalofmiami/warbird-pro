#!/usr/bin/env python3
"""Monte Carlo robustness analysis for Warbird Pro V9 ES binary classifier.

Parquet/CSV-based, no DB dependency. Binary classification on resolved ES entries.
Loads a trained AG predictor, builds a trade dataset from the V9 export CSV,
and runs vectorized Monte Carlo simulation over resampled trade sequences.

Tasks:
  A — Overall P&L distribution, drawdown, win rate, profit factor
  B — Per-direction (long/short) breakdown
  C — Threshold sweep: P(winner_tp_before_sl) >= tau gating
  G — Calibration: predicted vs realized per cohort
  H — Regime stability: early/late half comparison
  I — Win/loss streak profile

Usage:
  python scripts/ag/monte_carlo_v9.py \
      --predictor-path models/warbird_pro_v9/locked_<tag> \
      --csv exports/es_15m_core.csv \
      --split oos \
    [--run-summary models/warbird_pro_v9/locked_<tag>/v9_winner_clf_summary.json] \
      [--n-paths 2000] [--seed 42] \
      [--output-dir artifacts/mc_v9/<tag>]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")
os.environ.setdefault("MKL_NUM_THREADS", "1")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("LIGHTGBM_NUM_THREADS", "1")

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.ag.v9_run_provenance import (
    apply_time_split,
    check_summary_csv_hash,
    discover_run_summary_path,
    load_run_summary,
)

LABEL_COL = "winner_tp_before_sl"
TP_LABEL_COL = "tp_hit"
STOP_LABEL_COL = "stop_hit"
MFE_LABEL_COL = "mfe_points"
MAE_LABEL_COL = "mae_points"
ES_POINT_VALUE = 50.0
ES_TICK_SIZE = 0.25
COMMISSION_ROUND_TRIP = 2.0
DEFAULT_SLIPPAGE_TICKS = 1  # CLAUDE.md ES slippage floor: 1 tick/side
DEFAULT_SL_POINTS = 7.0
DEFAULT_TP_POINTS = 14.0
OOS_START = pd.Timestamp("2025-01-01", tz="UTC")
IS_END = pd.Timestamp("2024-12-31T23:59:59", tz="UTC")
SUITE_HEADS: tuple[str, ...] = ("entry", "tp", "stop", "mfe", "mae")


# Trade dataset semantics (5 TP × 4 SL grid, touch-event labels, same-bar
# collision = pessimistic loss) are defined in
# scripts.ag.train_v9_locked.build_trade_dataset — do not reimplement.
def _build_trades(df: pd.DataFrame) -> pd.DataFrame:
    from scripts.ag.train_v9_locked import build_trade_dataset as build_locked_trade_dataset

    trades = build_locked_trade_dataset(df)
    return trades.sort_values("ts").reset_index(drop=True)


def _predictor_feature_columns(predictor: Any, trades: pd.DataFrame) -> list[str]:
    if hasattr(predictor, "features"):
        expected = list(predictor.features())
    elif hasattr(predictor, "feature_metadata_in"):
        expected = list(predictor.feature_metadata_in.get_features())
    else:
        raise SystemExit("Unable to resolve predictor feature columns")
    missing = [c for c in expected if c not in trades.columns]
    if missing:
        raise SystemExit(
            "Resolved trade dataset missing predictor features: "
            + ", ".join(missing[:20])
            + (" ..." if len(missing) > 20 else "")
        )
    return expected


def _resolve_predictor_path(path: Path) -> Path:
    # Supports both layouts:
    # 1) locked_<tag>/predictor.pkl
    # 2) locked_<tag>/entry/predictor.pkl
    if (path / "predictor.pkl").exists():
        return path
    entry = path / "entry"
    if (entry / "predictor.pkl").exists():
        return entry
    raise SystemExit(
        f"Unable to locate predictor.pkl in {path} or {entry}"
    )


def _persist_predictor(predictor: Any) -> None:
    if hasattr(predictor, "persist"):
        predictor.persist()
    elif hasattr(predictor, "persist_models"):
        predictor.persist_models()


def _is_suite_root(path: Path) -> bool:
    """A run root is a suite if all five head subdirs each carry a predictor.pkl."""
    if (path / "predictor.pkl").exists():
        return False
    return all((path / head / "predictor.pkl").exists() for head in SUITE_HEADS)


def _load_suite_predictors(suite_root: Path) -> dict[str, Any]:
    """Load entry/tp/stop/mfe/mae predictors from a model-suite run directory."""
    from autogluon.tabular import TabularPredictor

    suite: dict[str, Any] = {}
    for head in SUITE_HEADS:
        head_dir = suite_root / head
        pred = TabularPredictor.load(str(head_dir), require_py_version_match=False)
        _persist_predictor(pred)
        suite[head] = pred
    return suite


def _head_proba_or_pred(predictor: Any, X: pd.DataFrame) -> np.ndarray:
    """Return P(class=1) for binary heads or point prediction for regression."""
    problem_type = getattr(predictor, "problem_type", None)
    if problem_type == "regression":
        out = predictor.predict(X)
        return np.asarray(out, dtype=float)
    proba = predictor.predict_proba(X)
    if isinstance(proba, pd.DataFrame):
        labels = list(getattr(predictor, "class_labels", proba.columns))
        if 1 in labels:
            col = labels.index(1)
        elif True in labels:
            col = labels.index(True)
        else:
            col = len(labels) - 1
        return proba.iloc[:, col].to_numpy(dtype=float)
    return np.asarray(proba, dtype=float)


def _suite_feature_columns(suite: dict[str, Any], trades: pd.DataFrame) -> dict[str, list[str]]:
    cols: dict[str, list[str]] = {}
    for head, pred in suite.items():
        if hasattr(pred, "features"):
            expected = list(pred.features())
        else:
            expected = list(pred.feature_metadata_in.get_features())
        missing = [c for c in expected if c not in trades.columns]
        if missing:
            raise SystemExit(
                f"Suite head '{head}' expects features missing from trades: "
                + ", ".join(missing[:10])
            )
        cols[head] = expected
    return cols


def _slippage_cost_rt(slippage_ticks: float) -> float:
    """One-side slippage applied to BOTH entry and exit -> 2 * ticks * tick_value."""
    return 2.0 * float(slippage_ticks) * ES_TICK_SIZE * ES_POINT_VALUE


def _resolve_payoff_arrays(
    trades: pd.DataFrame,
    fallback_sl_pts: float,
    fallback_tp_pts: float,
    slippage_ticks: float = DEFAULT_SLIPPAGE_TICKS,
) -> tuple[np.ndarray, np.ndarray]:
    slip = _slippage_cost_rt(slippage_ticks)
    trade_cost = COMMISSION_ROUND_TRIP + slip
    n = len(trades)
    fallback_win = fallback_tp_pts * ES_POINT_VALUE - trade_cost
    fallback_loss = -(fallback_sl_pts * ES_POINT_VALUE + trade_cost)
    win = np.full(n, fallback_win, dtype=float)
    loss = np.full(n, fallback_loss, dtype=float)
    if not {"entry_price", "target_price", "stop_price"}.issubset(trades.columns):
        return win, loss
    entry = pd.to_numeric(trades["entry_price"], errors="coerce").to_numpy(dtype=float)
    target = pd.to_numeric(trades["target_price"], errors="coerce").to_numpy(dtype=float)
    stop = pd.to_numeric(trades["stop_price"], errors="coerce").to_numpy(dtype=float)
    tp_pts = np.abs(target - entry)
    sl_pts = np.abs(stop - entry)
    valid = np.isfinite(tp_pts) & np.isfinite(sl_pts) & (tp_pts > 0) & (sl_pts > 0)
    win[valid] = tp_pts[valid] * ES_POINT_VALUE - trade_cost
    loss[valid] = -(sl_pts[valid] * ES_POINT_VALUE + trade_cost)
    return win, loss


def _compute_payoffs(
    y_true: np.ndarray,
    sl_pts: float = DEFAULT_SL_POINTS,
    tp_pts: float = DEFAULT_TP_POINTS,
    slippage_ticks: float = DEFAULT_SLIPPAGE_TICKS,
) -> np.ndarray:
    trade_cost = COMMISSION_ROUND_TRIP + _slippage_cost_rt(slippage_ticks)
    win_payoff = tp_pts * ES_POINT_VALUE - trade_cost
    loss_payoff = -(sl_pts * ES_POINT_VALUE + trade_cost)
    return np.where(y_true == 1, win_payoff, loss_payoff)


def simulate_paths(
    proba_pos: np.ndarray,
    payoffs_win: np.ndarray,
    payoffs_loss: np.ndarray,
    n_paths: int,
    rng: np.random.Generator,
) -> dict[str, Any]:
    N = len(proba_pos)
    if N == 0:
        return {"total_pnl": np.zeros(n_paths), "max_drawdown": np.zeros(n_paths),
                "win_rate": np.zeros(n_paths), "n_trades": 0}
    outcomes = rng.random((n_paths, N)) < proba_pos[None, :]
    realized = np.where(outcomes, payoffs_win[None, :], payoffs_loss[None, :])
    running = np.cumsum(realized, axis=1)
    running_max = np.maximum.accumulate(running, axis=1)
    drawdown = (running_max - running).max(axis=1)
    total_pnl = running[:, -1]
    win_rate = outcomes.mean(axis=1)
    return {
        "total_pnl": total_pnl,
        "max_drawdown": drawdown,
        "win_rate": win_rate,
        "n_trades": N,
        "realized": realized,
        "outcomes": outcomes,
    }


def quantiles(arr: np.ndarray, qs=(0.05, 0.25, 0.50, 0.75, 0.95)) -> dict[str, float]:
    if arr.size == 0:
        return {f"p{int(q*100)}": 0.0 for q in qs}
    return {f"p{int(q*100)}": float(np.quantile(arr, q)) for q in qs}


def rollup(
    proba_pos: np.ndarray,
    y_true: np.ndarray,
    payoffs_win: np.ndarray,
    payoffs_loss: np.ndarray,
    n_paths: int,
    rng: np.random.Generator,
) -> dict[str, Any]:
    ev_per_trade = proba_pos * payoffs_win + (1 - proba_pos) * payoffs_loss
    ev_mean = float(ev_per_trade.mean()) if ev_per_trade.size else 0.0
    ev_std = float(ev_per_trade.std(ddof=1)) if ev_per_trade.size > 1 else 0.0
    sharpe = ev_mean / ev_std if ev_std > 0 else 0.0

    sim = simulate_paths(proba_pos, payoffs_win, payoffs_loss, n_paths, rng)
    base_wr = float(y_true.mean()) if y_true.size else 0.0
    gross_wins = float(np.sum(sim["realized"][sim["outcomes"]])) if sim["n_trades"] else 0.0
    gross_losses = float(-np.sum(sim["realized"][~sim["outcomes"]])) if sim["n_trades"] else 0.0
    pf = gross_wins / gross_losses if gross_losses > 0 else float("inf") if gross_wins > 0 else 0.0

    return {
        "n_trades": sim["n_trades"],
        "base_win_rate": base_wr,
        "ev_per_trade": ev_mean,
        "ev_std_per_trade": ev_std,
        "per_trade_sharpe": sharpe,
        "mc_total_pnl": quantiles(sim["total_pnl"]),
        "mc_max_drawdown": quantiles(sim["max_drawdown"]),
        "mc_win_rate_mean": float(sim["win_rate"].mean()),
        "profit_factor": pf,
    }


def task_C_threshold_sweep(
    proba_pos: np.ndarray, y_true: np.ndarray, n_paths: int,
    rng_root: np.random.Generator, payoffs_win: np.ndarray, payoffs_loss: np.ndarray,
    thresholds: list[float] | None = None,
) -> dict[str, Any]:
    if thresholds is None:
        thresholds = [round(x, 2) for x in np.arange(0.40, 0.80, 0.05)]
    results: dict[str, Any] = {}
    for tau in thresholds:
        mask = proba_pos >= tau
        if mask.sum() < 10:
            results[str(tau)] = {"n_gated": int(mask.sum()), "status": "too_few"}
            continue
        rng = np.random.default_rng(rng_root.integers(0, 2**31 - 1))
        r = rollup(
            proba_pos[mask],
            y_true[mask],
            payoffs_win[mask],
            payoffs_loss[mask],
            n_paths,
            rng,
        )
        r["n_gated"] = int(mask.sum())
        r["gated_wr"] = float(y_true[mask].mean())
        r["lift"] = r["gated_wr"] - float(y_true.mean())
        results[str(tau)] = r
    return results


def task_G_calibration(
    proba_pos: np.ndarray, y_true: np.ndarray, n_bins: int = 10,
) -> list[dict[str, Any]]:
    bin_edges = np.linspace(0, 1, n_bins + 1)
    rows: list[dict[str, Any]] = []
    for lo, hi in zip(bin_edges[:-1], bin_edges[1:]):
        mask = (proba_pos >= lo) & (proba_pos < hi)
        n = int(mask.sum())
        if n == 0:
            continue
        predicted = float(proba_pos[mask].mean())
        realized = float(y_true[mask].mean())
        ratio = realized / predicted if predicted > 0 else float("inf")
        if 0.7 <= ratio <= 1.3:
            verdict = "OK"
        elif realized > predicted:
            verdict = "UNDERCONFIDENT"
        else:
            verdict = "OVERCONFIDENT"
        rows.append({
            "bin": f"[{lo:.2f}, {hi:.2f})",
            "n": n,
            "predicted": predicted,
            "realized": realized,
            "ratio": ratio,
            "verdict": verdict,
        })
    return rows


def task_H_regime_stability(
    proba_pos: np.ndarray, y_true: np.ndarray, ts: np.ndarray,
    payoffs_win: np.ndarray, payoffs_loss: np.ndarray,
    n_paths: int, rng_root: np.random.Generator,
) -> dict[str, Any]:
    ts_num = pd.to_datetime(ts, utc=True).astype("int64")
    mid = np.median(ts_num)
    early_mask = ts_num < mid
    late_mask = ~early_mask
    rng_e = np.random.default_rng(rng_root.integers(0, 2**31 - 1))
    rng_l = np.random.default_rng(rng_root.integers(0, 2**31 - 1))
    early = rollup(
        proba_pos[early_mask],
        y_true[early_mask],
        payoffs_win[early_mask],
        payoffs_loss[early_mask],
        n_paths,
        rng_e,
    )
    late = rollup(
        proba_pos[late_mask],
        y_true[late_mask],
        payoffs_win[late_mask],
        payoffs_loss[late_mask],
        n_paths,
        rng_l,
    )
    ev_diff = abs(early["ev_per_trade"] - late["ev_per_trade"])
    verdict = "STABLE" if ev_diff < early["ev_std_per_trade"] else "FRAGILE"
    return {
        "early": early,
        "late": late,
        "ev_absolute_diff": ev_diff,
        "verdict": verdict,
    }


def task_I_streaks(
    proba_pos: np.ndarray, n_paths: int, rng: np.random.Generator,
    payoffs_win: np.ndarray, payoffs_loss: np.ndarray,
) -> dict[str, Any]:
    sim = simulate_paths(proba_pos, payoffs_win, payoffs_loss, n_paths, rng)
    outcomes = sim["outcomes"]
    realized = sim["realized"]
    if sim["n_trades"] == 0:
        return {}

    def _longest_runs(arr_2d: np.ndarray, pred_fn) -> np.ndarray:
        out = np.zeros(arr_2d.shape[0], dtype=np.int32)
        for i in range(arr_2d.shape[0]):
            mask_row = pred_fn(arr_2d[i])
            run, best = 0, 0
            for v in mask_row:
                if v:
                    run += 1
                    best = max(best, run)
                else:
                    run = 0
            out[i] = best
        return out

    win_streaks = _longest_runs(outcomes, lambda a: a)
    loss_streaks = _longest_runs(outcomes, lambda a: ~a)
    max_single_win = np.where(realized > 0, realized, 0).max(axis=1)
    running = np.cumsum(realized, axis=1)
    running_max = np.maximum.accumulate(running, axis=1)
    underwater = running < running_max
    underwater_dur = _longest_runs(underwater, lambda a: a)

    return {
        "winning_streak": quantiles(win_streaks.astype(float)),
        "losing_streak": quantiles(loss_streaks.astype(float)),
        "max_single_win": quantiles(max_single_win),
        "underwater_duration": quantiles(underwater_dur.astype(float)),
    }


def task_J_multi_head(
    trades: pd.DataFrame,
    suite_predictions: dict[str, np.ndarray],
    payoffs_win: np.ndarray,
    payoffs_loss: np.ndarray,
    trade_cost_rt: float,
) -> dict[str, Any]:
    """Per-row multi-head diagnostics + conservative EV decomposition.

    suite_predictions keys: entry, tp, stop (binary P(class=1)) and mfe, mae (regression points).
    """
    n = len(trades)
    if n == 0:
        return {}

    p_entry = suite_predictions.get("entry", np.zeros(n))
    p_tp = suite_predictions.get("tp", np.zeros(n))
    p_stop = suite_predictions.get("stop", np.zeros(n))
    pred_mfe = suite_predictions.get("mfe", np.zeros(n))
    pred_mae = suite_predictions.get("mae", np.zeros(n))

    target_pts = pd.to_numeric(trades.get("target_distance_points", pd.Series(np.zeros(n))), errors="coerce").to_numpy(dtype=float)
    stop_pts = pd.to_numeric(trades.get("stop_distance_points", pd.Series(np.zeros(n))), errors="coerce").to_numpy(dtype=float)

    ev_entry = p_entry * payoffs_win + (1.0 - p_entry) * payoffs_loss
    p_tp_conditional = np.minimum(p_entry, p_tp)
    p_stop_conservative = np.maximum(1.0 - p_entry, p_stop)
    p_tp_conditional_norm = np.where(
        (p_tp_conditional + p_stop_conservative) > 0,
        p_tp_conditional / (p_tp_conditional + p_stop_conservative),
        p_entry,
    )
    ev_conservative = p_tp_conditional_norm * payoffs_win + (1.0 - p_tp_conditional_norm) * payoffs_loss

    realized_mfe = pd.to_numeric(trades.get(MFE_LABEL_COL, pd.Series(np.zeros(n))), errors="coerce").to_numpy(dtype=float)
    realized_mae = pd.to_numeric(trades.get(MAE_LABEL_COL, pd.Series(np.zeros(n))), errors="coerce").to_numpy(dtype=float)

    def _calibration(probs: np.ndarray, hits: np.ndarray, n_bins: int = 10) -> list[dict[str, Any]]:
        if probs.size == 0:
            return []
        edges = np.linspace(0.0, 1.0, n_bins + 1)
        rows: list[dict[str, Any]] = []
        for i in range(n_bins):
            lo, hi = edges[i], edges[i + 1]
            mask = (probs >= lo) & (probs < hi) if i < n_bins - 1 else (probs >= lo)
            cnt = int(mask.sum())
            if cnt == 0:
                continue
            rows.append({
                "bin": f"[{lo:.2f},{hi:.2f})",
                "n": cnt,
                "predicted": float(probs[mask].mean()),
                "realized": float(hits[mask].mean()),
            })
        return rows

    realized_tp_hit = trades[TP_LABEL_COL].to_numpy(dtype=float) if TP_LABEL_COL in trades.columns else np.zeros(n)
    realized_stop_hit = trades[STOP_LABEL_COL].to_numpy(dtype=float) if STOP_LABEL_COL in trades.columns else np.zeros(n)

    def _regression_quality(pred: np.ndarray, actual: np.ndarray) -> dict[str, float]:
        finite = np.isfinite(pred) & np.isfinite(actual)
        if finite.sum() < 5:
            return {"n": int(finite.sum()), "rmse_pts": 0.0, "bias_pts": 0.0, "corr": 0.0}
        residual = pred[finite] - actual[finite]
        rmse = float(np.sqrt(np.mean(residual ** 2)))
        bias = float(np.mean(residual))
        corr = float(np.corrcoef(pred[finite], actual[finite])[0, 1]) if pred[finite].std() > 1e-9 and actual[finite].std() > 1e-9 else 0.0
        return {"n": int(finite.sum()), "rmse_pts": rmse, "bias_pts": bias, "corr": corr}

    head_corr = {}
    for a, b in [("entry", "tp"), ("entry", "stop"), ("tp", "stop"), ("mfe", "mae")]:
        if a in suite_predictions and b in suite_predictions:
            xa, xb = suite_predictions[a], suite_predictions[b]
            if xa.std() > 1e-9 and xb.std() > 1e-9:
                head_corr[f"{a}_vs_{b}"] = float(np.corrcoef(xa, xb)[0, 1])

    return {
        "n_trades": int(n),
        "trade_cost_rt": float(trade_cost_rt),
        "head_correlations": head_corr,
        "ev_entry_only": {
            "mean": float(ev_entry.mean()),
            "p25": float(np.quantile(ev_entry, 0.25)),
            "p50": float(np.quantile(ev_entry, 0.50)),
            "p75": float(np.quantile(ev_entry, 0.75)),
        },
        "ev_multi_head_conservative": {
            "mean": float(ev_conservative.mean()),
            "p25": float(np.quantile(ev_conservative, 0.25)),
            "p50": float(np.quantile(ev_conservative, 0.50)),
            "p75": float(np.quantile(ev_conservative, 0.75)),
            "delta_vs_entry_only_mean": float(ev_conservative.mean() - ev_entry.mean()),
        },
        "tp_head_calibration": _calibration(p_tp, realized_tp_hit),
        "stop_head_calibration": _calibration(p_stop, realized_stop_hit),
        "entry_head_calibration": _calibration(p_entry, trades[LABEL_COL].to_numpy(dtype=float) if LABEL_COL in trades.columns else np.zeros(n)),
        "mfe_regressor_quality": _regression_quality(pred_mfe, realized_mfe),
        "mae_regressor_quality": _regression_quality(pred_mae, realized_mae),
        "target_distance_pts_summary": {
            "mean": float(target_pts.mean()) if target_pts.size else 0.0,
            "p50": float(np.quantile(target_pts, 0.50)) if target_pts.size else 0.0,
        },
        "stop_distance_pts_summary": {
            "mean": float(stop_pts.mean()) if stop_pts.size else 0.0,
            "p50": float(np.quantile(stop_pts, 0.50)) if stop_pts.size else 0.0,
        },
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--predictor-path", type=Path, required=True)
    ap.add_argument("--csv", type=Path, required=True)
    ap.add_argument("--split", choices=["is", "val", "oos", "all"], default="oos")
    ap.add_argument("--run-summary", type=Path, default=None,
                    help="Optional path to v9_winner_clf_summary.json for split/hash enforcement.")
    ap.add_argument("--n-paths", type=int, default=2000)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--sl-points", type=float, default=DEFAULT_SL_POINTS)
    ap.add_argument("--tp-points", type=float, default=DEFAULT_TP_POINTS)
    ap.add_argument("--slippage-ticks", type=float, default=DEFAULT_SLIPPAGE_TICKS,
                    help="One-side ES slippage in ticks; applied to both entry and exit (CLAUDE.md floor=1).")
    ap.add_argument("--model-suite", action="store_true",
                    help="When --predictor-path is a run root containing entry/tp/stop/mfe/mae subdirs, load all five heads for multi-head diagnostics.")
    ap.add_argument("--output-dir", type=Path, default=None)
    args = ap.parse_args()

    from autogluon.tabular import TabularPredictor
    suite_root: Path | None = None
    suite_predictors: dict[str, Any] = {}
    if args.model_suite:
        if _is_suite_root(args.predictor_path):
            suite_root = args.predictor_path.resolve()
        else:
            raise SystemExit(
                f"--model-suite requires a run root containing {list(SUITE_HEADS)} subdirs "
                f"each with a predictor.pkl. Got: {args.predictor_path}"
            )
    predictor_path = _resolve_predictor_path(args.predictor_path)
    pred = TabularPredictor.load(str(predictor_path), require_py_version_match=False)
    _persist_predictor(pred)
    if suite_root is not None:
        print(f"loading model suite from {suite_root}", flush=True)
        suite_predictors = _load_suite_predictors(suite_root)

    tag = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    output_dir = args.output_dir or (REPO_ROOT / "artifacts" / "mc_v9" / f"mc_{tag}")
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"loading {args.csv}", flush=True)
    df = pd.read_csv(args.csv, parse_dates=["ts"])
    trades = _build_trades(df)
    trades["ts"] = pd.to_datetime(trades["ts"], utc=True)
    print(f"  total trades: {len(trades):,}  WR={trades[LABEL_COL].mean():.4f}", flush=True)

    run_summary_path = discover_run_summary_path(args.predictor_path, args.run_summary)
    run_summary = load_run_summary(run_summary_path)
    if run_summary is not None:
        csv_hash_check = check_summary_csv_hash(args.csv, run_summary)
    else:
        csv_hash_check = {
            "checked": False,
            "expected": None,
            "actual": None,
            "matches": None,
            "reason": "no_run_summary",
        }
    if csv_hash_check.get("checked") and not csv_hash_check.get("matches"):
        raise SystemExit(
            "CSV hash mismatch against run summary: "
            f"expected={csv_hash_check.get('expected')} actual={csv_hash_check.get('actual')}"
        )

    trades, split_source = apply_time_split(
        trades,
        split=args.split,
        ts_col="ts",
        summary=run_summary,
        legacy_oos_start=OOS_START,
        legacy_is_end=IS_END,
    )
    print(
        f"  split={args.split} source={split_source} trades={len(trades):,}"
        f"  WR={trades[LABEL_COL].mean():.4f}",
        flush=True,
    )

    if len(trades) < 30:
        print("Too few trades for MC analysis", flush=True)
        return 1

    feature_cols = _predictor_feature_columns(pred, trades)
    y_true = trades[LABEL_COL].to_numpy()
    proba_pos = _head_proba_or_pred(pred, trades[feature_cols])
    payoffs_win, payoffs_loss = _resolve_payoff_arrays(
        trades, args.sl_points, args.tp_points, slippage_ticks=args.slippage_ticks,
    )
    trade_cost_rt = COMMISSION_ROUND_TRIP + _slippage_cost_rt(args.slippage_ticks)

    suite_predictions: dict[str, np.ndarray] = {}
    suite_feature_cols: dict[str, list[str]] = {}
    if suite_predictors:
        suite_feature_cols = _suite_feature_columns(suite_predictors, trades)
        for head, head_pred in suite_predictors.items():
            cols = suite_feature_cols[head]
            suite_predictions[head] = _head_proba_or_pred(head_pred, trades[cols])
        # Pin entry-head outputs to the suite's own entry predictor for consistency.
        if "entry" in suite_predictions:
            proba_pos = suite_predictions["entry"]

    rng_root = np.random.default_rng(args.seed)

    print("\n=== Task A — Overall ===", flush=True)
    rng_a = np.random.default_rng(rng_root.integers(0, 2**31 - 1))
    task_a = rollup(proba_pos, y_true, payoffs_win, payoffs_loss, args.n_paths, rng_a)
    print(f"  EV/trade=${task_a['ev_per_trade']:.2f}  PF={task_a['profit_factor']:.3f}"
          f"  MC p50 PnL=${task_a['mc_total_pnl']['p50']:.0f}", flush=True)

    print("\n=== Task B — Per direction ===", flush=True)
    task_b: dict[str, Any] = {}
    if "direction" in trades.columns:
        for d_val, d_label in [(1, "long"), (-1, "short")]:
            mask = trades["direction"].to_numpy() == d_val
            if mask.sum() < 10:
                task_b[d_label] = {"n_trades": int(mask.sum()), "status": "too_few"}
                continue
            rng_b = np.random.default_rng(rng_root.integers(0, 2**31 - 1))
            task_b[d_label] = rollup(
                proba_pos[mask],
                y_true[mask],
                payoffs_win[mask],
                payoffs_loss[mask],
                args.n_paths,
                rng_b,
            )
            print(f"  {d_label}: EV=${task_b[d_label]['ev_per_trade']:.2f}"
                  f"  n={task_b[d_label]['n_trades']}", flush=True)

    print("\n=== Task C — Threshold sweep ===", flush=True)
    task_c = task_C_threshold_sweep(
        proba_pos,
        y_true,
        args.n_paths,
        rng_root,
        payoffs_win,
        payoffs_loss,
    )
    for tau, r in task_c.items():
        if r.get("status") == "too_few":
            continue
        print(f"  tau={tau}  n={r.get('n_gated',0)}  lift={r.get('lift',0):.4f}"
              f"  EV=${r.get('ev_per_trade',0):.2f}", flush=True)

    print("\n=== Task G — Calibration ===", flush=True)
    task_g = task_G_calibration(proba_pos, y_true)
    for row in task_g:
        print(f"  {row['bin']}  n={row['n']}  pred={row['predicted']:.3f}"
              f"  real={row['realized']:.3f}  {row['verdict']}", flush=True)

    print("\n=== Task H — Regime stability ===", flush=True)
    task_h = task_H_regime_stability(
        proba_pos,
        y_true,
        trades["ts"].to_numpy(),
        payoffs_win,
        payoffs_loss,
        args.n_paths,
        rng_root,
    )
    print(f"  verdict={task_h['verdict']}  EV_diff=${task_h['ev_absolute_diff']:.2f}", flush=True)

    print("\n=== Task I — Streak profile ===", flush=True)
    rng_i = np.random.default_rng(rng_root.integers(0, 2**31 - 1))
    task_i = task_I_streaks(proba_pos, args.n_paths, rng_i, payoffs_win, payoffs_loss)
    if task_i:
        print(f"  win streak p50={task_i['winning_streak']['p50']:.0f}"
              f"  loss streak p50={task_i['losing_streak']['p50']:.0f}", flush=True)

    task_j: dict[str, Any] = {}
    if suite_predictions:
        print("\n=== Task J — Multi-head diagnostics ===", flush=True)
        task_j = task_J_multi_head(
            trades, suite_predictions, payoffs_win, payoffs_loss, trade_cost_rt
        )
        if task_j:
            print(
                f"  EV entry-only mean=${task_j['ev_entry_only']['mean']:.2f}"
                f"  EV multi-head mean=${task_j['ev_multi_head_conservative']['mean']:.2f}"
                f"  delta=${task_j['ev_multi_head_conservative']['delta_vs_entry_only_mean']:+.2f}",
                flush=True,
            )
            for pair, corr in task_j["head_correlations"].items():
                print(f"  corr({pair}) = {corr:+.3f}", flush=True)

    full_output = {
        "generated_at": tag,
        "predictor_path_input": str(args.predictor_path),
        "predictor_path": str(predictor_path),
        "csv": str(args.csv),
        "split": args.split,
        "split_source": split_source,
        "run_summary_path": str(run_summary_path) if run_summary_path else None,
        "csv_hash_check": csv_hash_check,
        "n_paths": args.n_paths,
        "predictor_feature_count": len(feature_cols),
        "sl_points": args.sl_points,
        "tp_points": args.tp_points,
        "slippage_ticks": args.slippage_ticks,
        "trade_cost_rt_usd": trade_cost_rt,
        "model_suite_loaded": bool(suite_predictors),
        "point_value": ES_POINT_VALUE,
        "commission_rt": COMMISSION_ROUND_TRIP,
        "task_A_overall": task_a,
        "task_B_per_direction": task_b,
        "task_C_threshold_sweep": task_c,
        "task_G_calibration": task_g,
        "task_H_regime_stability": task_h,
        "task_I_streaks": task_i,
        "task_J_multi_head": task_j,
    }
    (output_dir / "mc_v9_results.json").write_text(json.dumps(full_output, indent=2, default=str))
    print(f"\nwrote {output_dir / 'mc_v9_results.json'}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
