#!/usr/bin/env python3
"""Warbird Pro V9 — SHAP explainability for Core AG predictors.

No DB dependency. Loads a trained AG predictor directory, computes SHAP values
via TreeExplainer (auto-selects best tree model if best_model is NN/ensemble),
and writes:
  - shap_feature_summary.csv      (overall mean |SHAP| per feature, ranked)
  - shap_per_class.csv            (per-class mean |SHAP|)
  - shap_raw_values.parquet       (per-row SHAP values for downstream analysis)
  - shap_temporal_stability.csv   (early/late half comparison)
  - shap_calibration.csv          (predicted vs realized in prob bins)
  - shap_redundancy.csv           (high-correlation feature pairs)
  - shap_drop_candidates.csv      (DEAD / REDUNDANT / UNSTABLE features)
  - shap_summary.md               (human-readable report)

Usage:
  python scripts/ag/shap_v9.py \
      --predictor-dir models/warbird_pro_v9/locked_20260508_... \
      --csv exports/es_15m_core.csv \
      [--max-rows 5000] \
      [--output-dir artifacts/shap_v9/<tag>]
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

DEFAULT_OUTPUT_ROOT = REPO_ROOT / "artifacts" / "shap_v9"
LABEL_COL = "winner_tp_before_sl"

_SHAP_TREE_FAMILIES = {"GBM", "CAT", "XGB", "RF", "XT"}


def _canonical_family(model_name: str) -> str | None:
    name = str(model_name)
    for prefix, family in [
        ("LightGBM", "GBM"), ("CatBoost", "CAT"), ("XGBoost", "XGB"),
        ("RandomForest", "RF"), ("ExtraTrees", "XT"),
        ("NeuralNetTorch", "NN_TORCH"), ("NeuralNetFastAI", "FASTAI"),
    ]:
        if name.startswith(prefix):
            return family
    if "FastAI" in name:
        return "FASTAI"
    return None


def _is_tree_model(model_name: str) -> bool:
    return _canonical_family(model_name) in _SHAP_TREE_FAMILIES


def _resolve_shap_model(predictor: Any) -> str:
    """Auto-select best tree-compatible model from the predictor."""
    best = predictor.model_best
    if _is_tree_model(best):
        print(f"  SHAP model: {best} (AG best, tree-compatible)")
        return best

    lb = predictor.leaderboard(silent=True)
    if "score_val" in lb.columns:
        lb = lb.sort_values("score_val", ascending=False)
    for _, row in lb.iterrows():
        mn = str(row["model"])
        if _is_tree_model(mn):
            print(f"  SHAP model: {mn} (fallback — best={best} is not tree-compatible)")
            return mn

    raise SystemExit(
        f"No tree-compatible model found in predictor. "
        f"Best model is {best}. SHAP TreeExplainer requires GBM/CAT/XGB/RF/XT."
    )


# Trade dataset semantics (3 TP × 3 SL grid, touch-event labels, same-bar
# collision = pessimistic loss) are defined in
# scripts.ag.train_v9_locked.build_trade_dataset — do not reimplement.
def _build_trade_dataset(df: pd.DataFrame) -> pd.DataFrame:
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


def _resolve_predictor_dir(path: Path) -> Path:
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


def _explain_model(
    predictor: Any,
    model_name: str,
    X: pd.DataFrame,
) -> tuple[np.ndarray, list[str]]:
    """Run SHAP TreeExplainer on the selected model.

    Returns (shap_values, feature_names) where shap_values is
    (n_rows, n_features) for binary class-1 SHAP values.
    """
    import shap

    trainer = predictor._trainer
    model = trainer.load_model(model_name)

    transformed = predictor._learner.transform_features(X)

    if hasattr(model, "models") and getattr(model, "models"):
        child_count = len(model.models)
        shap_sum: np.ndarray | None = None
        child_features: list[str] | None = None
        for child_name in model.models:
            child = model.load_child(child_name)
            if child_features is None:
                child_features = list(child.features)
            X_child = transformed[child_features]
            explainer = shap.TreeExplainer(child.model)
            values = explainer.shap_values(X_child, check_additivity=False)
            if isinstance(values, list):
                arr = np.asarray(values[1])
            else:
                arr = np.asarray(values)
                if arr.ndim == 3:
                    arr = arr[:, :, 1]
            if shap_sum is None:
                shap_sum = arr
            else:
                shap_sum += arr
        if child_features is None or shap_sum is None:
            raise ValueError(f"{model_name} did not expose bag children.")
        print(f"  averaged SHAP across {child_count} bag children")
        return (shap_sum / float(child_count)).astype(np.float32), child_features
    else:
        child_features = list(getattr(model, "features", []) or [])
        if not child_features or not hasattr(model, "model"):
            raise ValueError(f"{model_name} has no underlying tree model for SHAP.")
        X_child = transformed[child_features]
        explainer = shap.TreeExplainer(model.model)
        values = explainer.shap_values(X_child, check_additivity=False)
        if isinstance(values, list):
            arr = np.asarray(values[1])
        else:
            arr = np.asarray(values)
            if arr.ndim == 3:
                arr = arr[:, :, 1]
        return arr.astype(np.float32), child_features


def _compute_overall_importance(
    shap_values: np.ndarray, feature_names: list[str]
) -> pd.DataFrame:
    mean_abs = np.abs(shap_values).mean(axis=0)
    df = pd.DataFrame({
        "feature_name": feature_names,
        "mean_abs_shap": mean_abs.astype(np.float64),
    })
    df = df.sort_values("mean_abs_shap", ascending=False).reset_index(drop=True)
    df.insert(0, "rank", np.arange(1, len(df) + 1, dtype=np.int32))
    return df


def _compute_per_class_importance(
    shap_values: np.ndarray,
    feature_names: list[str],
    y_true: np.ndarray,
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for cls_label, cls_val in [("loser", 0), ("winner", 1)]:
        mask = y_true == cls_val
        if mask.sum() == 0:
            continue
        mean_abs = np.abs(shap_values[mask]).mean(axis=0)
        order = np.argsort(-mean_abs)
        for rank, idx in enumerate(order, start=1):
            rows.append({
                "class": cls_label,
                "rank": rank,
                "feature_name": feature_names[idx],
                "mean_abs_shap": float(mean_abs[idx]),
            })
    return pd.DataFrame(rows)


def _compute_temporal_stability(
    shap_values: np.ndarray,
    feature_names: list[str],
) -> pd.DataFrame:
    mid = len(shap_values) // 2
    early_abs = np.abs(shap_values[:mid]).mean(axis=0)
    late_abs = np.abs(shap_values[mid:]).mean(axis=0)

    with np.errstate(divide="ignore", invalid="ignore"):
        shift = np.where(
            early_abs > 0,
            (late_abs - early_abs) / early_abs,
            np.where(late_abs > 0, np.inf, 0.0),
        )

    overall = np.abs(shap_values).mean(axis=0)
    buckets = []
    for i in range(len(feature_names)):
        if max(early_abs[i], late_abs[i]) < 0.005:
            buckets.append("DEAD")
        elif abs(shift[i]) < 0.20:
            buckets.append("STABLE")
        elif abs(shift[i]) < 0.50:
            buckets.append("MODERATE_SHIFT")
        else:
            buckets.append("VOLATILE")

    return pd.DataFrame({
        "feature_name": feature_names,
        "mean_abs_overall": overall.astype(np.float64),
        "mean_abs_early": early_abs.astype(np.float64),
        "mean_abs_late": late_abs.astype(np.float64),
        "pct_shift": shift.astype(np.float64),
        "stability_bucket": buckets,
    }).sort_values("mean_abs_overall", ascending=False).reset_index(drop=True)


def _compute_calibration(
    predictor: Any,
    X: pd.DataFrame,
    y_true: np.ndarray,
    n_bins: int = 10,
) -> pd.DataFrame:
    proba = predictor.predict_proba(X)
    if isinstance(proba, pd.DataFrame):
        proba_pos = proba.iloc[:, 1].to_numpy()
    else:
        proba_pos = np.asarray(proba)

    bin_edges = np.linspace(0, 1, n_bins + 1)
    rows: list[dict[str, Any]] = []
    for i in range(n_bins):
        lo, hi = bin_edges[i], bin_edges[i + 1]
        mask = (proba_pos >= lo) & (proba_pos < hi) if i < n_bins - 1 else (proba_pos >= lo)
        n = int(mask.sum())
        if n == 0:
            continue
        predicted = float(proba_pos[mask].mean())
        realized = float(y_true[mask].mean())
        rows.append({
            "bin_lo": round(float(lo), 2),
            "bin_hi": round(float(hi), 2),
            "n": n,
            "predicted_mean": round(predicted, 4),
            "realized_mean": round(realized, 4),
            "gap": round(realized - predicted, 4),
        })
    return pd.DataFrame(rows)


def _compute_cohort_importance(
    trades: pd.DataFrame,
    shap_values: np.ndarray,
    feature_names: list[str],
) -> pd.DataFrame:
    cohort_cols = [
        "ml_fib_touch_level_code",
        "ml_recent_liq_bull",
        "ml_recent_liq_bear",
        "sl_atr_mult",
        "tp_ratio",
        "tp_family_code",
        "knob_length_ema",
        "knob_length_ma",
        "knob_nq_symbol",
        "knob_zn_symbol",
        "knob_6e_symbol",
        "knob_vix_symbol",
        "ml_absorption_candidate",
        "ml_flush_candidate",
        "ml_fp_va_position",
    ]
    rows: list[dict[str, Any]] = []
    for col in cohort_cols:
        if col not in trades.columns:
            continue
        series = trades[col].fillna("__NA__")
        for value, idx in series.groupby(series).groups.items():
            idx_arr = np.asarray(list(idx), dtype=int)
            if idx_arr.size < 5:
                continue
            mean_abs = np.abs(shap_values[idx_arr]).mean(axis=0)
            top_idx = int(np.argmax(mean_abs))
            rows.append(
                {
                    "cohort_column": col,
                    "cohort_value": str(value),
                    "n": int(idx_arr.size),
                    "top_feature": feature_names[top_idx],
                    "top_mean_abs_shap": float(mean_abs[top_idx]),
                }
            )
    return pd.DataFrame(rows).sort_values(
        ["cohort_column", "top_mean_abs_shap"], ascending=[True, False]
    ).reset_index(drop=True) if rows else pd.DataFrame(
        columns=["cohort_column", "cohort_value", "n", "top_feature", "top_mean_abs_shap"]
    )


def _compute_redundancy(
    X: pd.DataFrame,
    feature_names: list[str],
    threshold: float = 0.95,
) -> pd.DataFrame:
    numeric = X[feature_names].select_dtypes(include=[np.number])
    if len(numeric) > 50_000:
        numeric = numeric.sample(n=50_000, random_state=42)
    corr = numeric.corr(method="pearson").abs()
    pairs: list[dict[str, Any]] = []
    cols = corr.columns.tolist()
    for i in range(len(cols)):
        for j in range(i + 1, len(cols)):
            v = corr.iat[i, j]
            if pd.notna(v) and v >= threshold:
                pairs.append({
                    "feature_a": cols[i],
                    "feature_b": cols[j],
                    "abs_pearson": round(float(v), 4),
                })
    return pd.DataFrame(pairs).sort_values(
        "abs_pearson", ascending=False
    ).reset_index(drop=True) if pairs else pd.DataFrame(
        columns=["feature_a", "feature_b", "abs_pearson"]
    )


def _compute_drop_candidates(
    overall: pd.DataFrame,
    stability: pd.DataFrame,
    redundancy: pd.DataFrame,
) -> pd.DataFrame:
    stab_lookup = stability.set_index("feature_name")["stability_bucket"].to_dict()
    mean_lookup = overall.set_index("feature_name")["mean_abs_shap"].to_dict()

    redundant_losers: dict[str, str] = {}
    if not redundancy.empty:
        for _, row in redundancy.iterrows():
            a, b = row["feature_a"], row["feature_b"]
            if mean_lookup.get(a, 0) <= mean_lookup.get(b, 0):
                redundant_losers.setdefault(a, b)
            else:
                redundant_losers.setdefault(b, a)

    rows: list[dict[str, Any]] = []
    for _, r in overall.iterrows():
        feat = r["feature_name"]
        bucket = stab_lookup.get(feat, "UNKNOWN")
        mean_abs = float(r["mean_abs_shap"])

        if bucket == "DEAD":
            reason = "DEAD"
        elif feat in redundant_losers:
            reason = f"REDUNDANT (pair={redundant_losers[feat]})"
        elif bucket == "VOLATILE" and mean_abs < 0.05:
            reason = "UNSTABLE_LOW_VALUE"
        else:
            continue
        rows.append({
            "feature_name": feat,
            "reason": reason,
            "rank": int(r["rank"]),
            "mean_abs_shap": mean_abs,
            "stability_bucket": bucket,
        })
    return pd.DataFrame(rows)


def _write_summary_md(
    output_dir: Path,
    overall: pd.DataFrame,
    per_class: pd.DataFrame,
    stability: pd.DataFrame,
    calibration: pd.DataFrame,
    drops: pd.DataFrame,
    model_name: str,
    n_rows: int,
    n_features: int,
) -> None:
    lines = [
        "# SHAP Analysis — Warbird Pro V9",
        "",
        f"Model: `{model_name}` | Rows: {n_rows:,} | Features: {n_features}",
        "",
    ]

    lines.append("## Top 10 Features (mean |SHAP|)")
    lines.append("")
    lines.append("| Rank | Feature | mean_abs_shap |")
    lines.append("|---:|---|---:|")
    for _, r in overall.head(10).iterrows():
        lines.append(f"| {int(r['rank'])} | {r['feature_name']} | {r['mean_abs_shap']:.4f} |")
    lines.append("")

    for cls in ["winner", "loser"]:
        sub = per_class[per_class["class"] == cls].head(5)
        if sub.empty:
            continue
        lines.append(f"## Top 5 for {cls}")
        lines.append("")
        for _, r in sub.iterrows():
            lines.append(f"- {r['feature_name']} ({r['mean_abs_shap']:.4f})")
        lines.append("")

    lines.append("## Temporal Stability")
    lines.append("")
    bucket_counts = stability["stability_bucket"].value_counts().to_dict()
    for bucket, count in sorted(bucket_counts.items()):
        lines.append(f"- **{bucket}**: {count}")
    lines.append("")

    lines.append("## Calibration")
    lines.append("")
    if calibration.empty:
        lines.append("No calibration data.")
    else:
        lines.append("| Bin | N | Predicted | Realized | Gap |")
        lines.append("|---|---:|---:|---:|---:|")
        for _, r in calibration.iterrows():
            lines.append(
                f"| [{r['bin_lo']:.2f}, {r['bin_hi']:.2f}) | {r['n']} | "
                f"{r['predicted_mean']:.4f} | {r['realized_mean']:.4f} | {r['gap']:+.4f} |"
            )
    lines.append("")

    if not drops.empty:
        lines.append(f"## Drop Candidates ({len(drops)})")
        lines.append("")
        for _, r in drops.iterrows():
            lines.append(f"- `{r['feature_name']}` — {r['reason']}")
        lines.append("")

    (output_dir / "shap_summary.md").write_text("\n".join(lines) + "\n")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--predictor-dir", type=Path, required=True,
                    help="Path to trained AG predictor directory")
    ap.add_argument("--csv", type=Path, required=True,
                    help="Source CSV with ml_* columns")
    ap.add_argument("--max-rows", type=int, default=None,
                    help="Cap rows for fast smoke runs")
    ap.add_argument("--output-dir", type=Path, default=None)
    ap.add_argument("--label-col", default=LABEL_COL,
                    help="Resolved trade label to explain: winner_tp_before_sl, tp_hit, stop_hit, mfe_points, or mae_points.")
    ap.add_argument("--corr-threshold", type=float, default=0.95,
                    help="Pearson threshold for redundancy detection")
    args = ap.parse_args()

    tag = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    output_dir = args.output_dir or (DEFAULT_OUTPUT_ROOT / f"shap_{tag}")
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"loading {args.csv}", flush=True)
    df = pd.read_csv(args.csv, parse_dates=["ts"])
    print(f"  rows={len(df):,}  range={df['ts'].iloc[0]} → {df['ts'].iloc[-1]}", flush=True)

    trades = _build_trade_dataset(df)
    if args.label_col not in trades.columns:
        raise SystemExit(f"Label column not found in resolved trade dataset: {args.label_col}")
    label_col = args.label_col
    label_mean = trades[label_col].mean() if pd.api.types.is_numeric_dtype(trades[label_col]) else float("nan")
    print(f"  trades={len(trades):,}  {label_col}_mean={label_mean:.4f}", flush=True)

    if args.max_rows and len(trades) > args.max_rows:
        trades = trades.tail(args.max_rows).reset_index(drop=True)
        print(f"  capped to {len(trades):,} rows (most recent)", flush=True)

    from autogluon.tabular import TabularPredictor

    predictor_dir = _resolve_predictor_dir(args.predictor_dir)
    print(f"\nloading predictor from {predictor_dir}", flush=True)
    predictor = TabularPredictor.load(str(predictor_dir))
    predictor.persist_models()
    feature_cols = _predictor_feature_columns(predictor, trades)

    model_name = _resolve_shap_model(predictor)
    X = trades[feature_cols]
    y_true = trades[label_col].to_numpy()

    print(f"\ncomputing SHAP values ({len(trades):,} rows × {len(feature_cols)} features)...", flush=True)
    shap_values, shap_features = _explain_model(predictor, model_name, X)
    print(f"  SHAP shape: {shap_values.shape}", flush=True)

    overall = _compute_overall_importance(shap_values, shap_features)
    overall.to_csv(output_dir / "shap_feature_summary.csv", index=False)
    print(f"\n=== top 10 features ===", flush=True)
    print(overall.head(10).to_string(index=False), flush=True)

    per_class = _compute_per_class_importance(shap_values, shap_features, y_true)
    per_class.to_csv(output_dir / "shap_per_class.csv", index=False)

    raw_df = trades[["ts", label_col]].copy().reset_index(drop=True)
    shap_cols = {f"shap__{feat}": shap_values[:, i] for i, feat in enumerate(shap_features)}
    raw_df = pd.concat([raw_df, pd.DataFrame(shap_cols)], axis=1)
    raw_df.to_parquet(output_dir / "shap_raw_values.parquet", index=False)

    stability = _compute_temporal_stability(shap_values, shap_features)
    stability.to_csv(output_dir / "shap_temporal_stability.csv", index=False)
    print(f"\nstability: {stability['stability_bucket'].value_counts().to_dict()}", flush=True)

    calibration = _compute_calibration(predictor, X, y_true) if set(pd.Series(y_true).dropna().unique()).issubset({0, 1}) else pd.DataFrame()
    calibration.to_csv(output_dir / "shap_calibration.csv", index=False)

    cohort = _compute_cohort_importance(trades, shap_values, shap_features)
    cohort.to_csv(output_dir / "shap_cohort_importance.csv", index=False)

    redundancy = _compute_redundancy(X, feature_cols, threshold=args.corr_threshold)
    redundancy.to_csv(output_dir / "shap_redundancy.csv", index=False)
    if not redundancy.empty:
        print(f"\nredundant pairs (|r| >= {args.corr_threshold}): {len(redundancy)}", flush=True)

    drops = _compute_drop_candidates(overall, stability, redundancy)
    drops.to_csv(output_dir / "shap_drop_candidates.csv", index=False)
    if not drops.empty:
        print(f"\ndrop candidates: {len(drops)}", flush=True)

    _write_summary_md(
        output_dir, overall, per_class, stability, calibration, drops,
        model_name=model_name,
        n_rows=len(trades),
        n_features=len(shap_features),
    )

    manifest = {
        "generated_at": tag,
        "predictor_dir_input": str(args.predictor_dir),
        "predictor_dir": str(predictor_dir),
        "csv": str(args.csv),
        "label_col": label_col,
        "model_name": model_name,
        "n_rows": len(trades),
        "n_features": len(shap_features),
        "top_10": overall.head(10)[["rank", "feature_name", "mean_abs_shap"]].to_dict(orient="records"),
        "stability_summary": stability["stability_bucket"].value_counts().to_dict(),
        "drop_candidate_count": len(drops),
    }
    (output_dir / "shap_manifest.json").write_text(
        json.dumps(manifest, indent=2, default=str) + "\n"
    )
    print(f"\nwrote {output_dir}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
