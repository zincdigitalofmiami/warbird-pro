#!/usr/bin/env python3
"""Diagnostic SHAP + hi-def postprocess for an AutoGluon training run.

Two phases:
  1. Compute phase — explain one AG model per fold (existing behavior, preserved).
  2. Postprocess phase — aggregate raw SHAP parquets into cohort / per-class /
     temporal-stability / calibration / redundancy / drop-candidates / summary.md.

The postprocess phase can run against an EXISTING compute output via
`--postprocess-only`, which skips the SHAP recompute entirely.

Contract and design decisions are pinned in
`docs/plans/2026-04-15-hi-def-shap-mc-implementation.md`.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
import warnings
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd
import psycopg2
import shap
from autogluon.tabular import TabularPredictor

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import scripts.ag.train_ag_baseline as baseline
from scripts.ag.monte_carlo_run import HOUR_BUCKETS as MC_HOUR_BUCKETS

warnings.filterwarnings(
    "ignore",
    message="pandas only supports SQLAlchemy connectable",
    category=UserWarning,
)

DEFAULT_OUTPUT_ROOT = "artifacts/shap"
DEFAULT_SPLIT_CODE = "test"
DEFAULT_MODEL_NAME = "LightGBM_BAG_L1"
# `archetype` added forward-looking; old runs backfill via DB join in postprocess.
META_COLS = [
    "id",
    "stop_variant_id",
    "ts",
    "session_date_ct",
    "direction",
    "fib_level_touched",
    "stop_family_id",
    "outcome_label",
    "archetype",
]

CHICAGO_TZ = baseline.CHICAGO_TZ

# Cohort dimensions available in postprocess. Each maps to a column in the
# combined enriched parquet (after archetype backfill + hour_bucket derivation).
COHORT_DIMS = {
    "by_fib_level": "fib_level_touched",
    "by_direction": "direction",
    "by_stop_family": "stop_family_id",
    "by_hour_bucket": "hour_bucket",
    "by_archetype": "archetype",
    "by_fold": "fold_code",
}


@dataclass
class FoldArtifact:
    fold_code: str
    split_code: str
    model_name: str
    row_count: int
    feature_count: int
    class_count: int
    child_count: int
    raw_path: str
    feature_summary_path: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compute diagnostic SHAP from an already-fitted AutoGluon run."
    )
    parser.add_argument("--run-id", required=True, help="Existing AG run id under artifacts/ag_runs/.")
    parser.add_argument("--dsn", default=baseline.DEFAULT_DSN, help="PostgreSQL DSN for local warbird.")
    parser.add_argument("--output-root", default=DEFAULT_OUTPUT_ROOT, help="Raw SHAP artifact root.")
    parser.add_argument(
        "--model-name",
        default=DEFAULT_MODEL_NAME,
        help="AutoGluon model name to explain per fold. Default: LightGBM_BAG_L1",
    )
    parser.add_argument(
        "--split-code",
        choices=("test",),
        default=DEFAULT_SPLIT_CODE,
        help="Fold split to explain. Currently only test is supported.",
    )
    parser.add_argument(
        "--max-rows-per-fold",
        type=int,
        default=None,
        help="Optional cap for fast smoke runs. Default: full split.",
    )
    # --- hi-def postprocess flags ---
    parser.add_argument(
        "--postprocess-only",
        action="store_true",
        help="Skip SHAP compute; postprocess existing raw parquets under output-root/run-id.",
    )
    parser.add_argument(
        "--cohort-min-rows",
        type=int,
        default=200,
        help="Minimum rows per cohort value to emit a cohort CSV.",
    )
    parser.add_argument(
        "--max-features-per-cohort",
        type=int,
        default=100,
        help="Truncate each cohort CSV to top-N features by mean_abs_shap.",
    )
    parser.add_argument(
        "--skip-cohorts",
        default="",
        help="Comma-separated cohort dimensions to skip (e.g., by_archetype).",
    )
    parser.add_argument(
        "--calibrate",
        action="store_true",
        default=True,
        help="Compute calibration (predicted vs realized per cohort × class). Default on.",
    )
    parser.add_argument(
        "--no-calibrate",
        dest="calibrate",
        action="store_false",
        help="Disable calibration step (skips extra predict_proba passes).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report planned cohort sizes + outputs; compute nothing.",
    )
    parser.add_argument(
        "--leakage-rank-threshold",
        type=int,
        default=30,
        help="Aggregate rank threshold (or mean_abs_shap > 0.10) above which features can be flagged LEAKAGE_SUSPECT.",
    )
    parser.add_argument(
        "--leakage-cv-threshold",
        type=float,
        default=0.10,
        help="Cross-cohort mean_abs_cv BELOW which a high-importance feature is flagged LEAKAGE_SUSPECT.",
    )
    parser.add_argument(
        "--redundancy-corr-threshold",
        type=float,
        default=0.95,
        help="Absolute Pearson correlation above which feature pairs are flagged REDUNDANT.",
    )
    return parser.parse_args()


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def standardize_shap_values(
    values: Any,
    *,
    row_count: int,
    feature_count: int,
    class_count: int,
) -> np.ndarray:
    if isinstance(values, list):
        if len(values) != class_count:
            raise ValueError(f"Expected {class_count} class arrays, got {len(values)}.")
        arr = np.stack(values, axis=-1)
    else:
        arr = np.asarray(values)

    if arr.ndim == 2:
        arr = arr[:, :, np.newaxis]

    if arr.shape != (row_count, feature_count, class_count):
        raise ValueError(
            "Unexpected SHAP value shape "
            f"{arr.shape}; expected {(row_count, feature_count, class_count)}."
        )
    return arr.astype(np.float32, copy=False)


def load_run_context(run_id: str) -> tuple[Path, dict[str, Any], dict[str, Any], dict[str, Any]]:
    run_dir = (Path("artifacts/ag_runs") / run_id).resolve()
    if not run_dir.exists():
        raise SystemExit(f"Run directory not found: {run_dir}")

    dataset_summary = read_json(run_dir / "dataset_summary.json")
    feature_manifest = read_json(run_dir / "feature_manifest.json")
    training_summary = read_json(run_dir / "training_summary.json")
    return run_dir, dataset_summary, feature_manifest, training_summary


def load_enriched_dataset(
    *,
    dsn: str,
    dataset_summary: dict[str, Any],
    label: str,
) -> pd.DataFrame:
    session_window = dataset_summary.get("session_window", {})
    use_macro = bool(dataset_summary.get("coverage", {}).get("macro_enabled", False))

    with psycopg2.connect(dsn) as conn:
        base = baseline.load_base_training(conn)
        base = baseline.add_time_context(base)
        base = baseline.filter_session_window(
            base,
            session_window.get("start_date"),
            session_window.get("end_date"),
        )
        base = base.drop(
            columns=[
                "hour_ts",
                "hour_ct",
                "minute_ct",
                "dow_ct",
                "month_ct",
                "is_rth_ct",
                "is_opening_window_ct",
                "session_tier_code",
            ],
            errors="ignore",
        )
        enriched, _coverage = baseline.attach_context_features(
            conn,
            base=base,
            use_macro=use_macro,
        )

    enriched, _feature_cols, _manifest = baseline.coerce_feature_frame(enriched, label=label)
    return enriched


def build_fold_frame(
    enriched: pd.DataFrame,
    *,
    split_sessions: list[str],
    max_rows: int | None,
) -> pd.DataFrame:
    fold_df = enriched[enriched["session_date_ct"].isin(pd.to_datetime(split_sessions))].copy()
    if max_rows is not None:
        fold_df = fold_df.head(max_rows).copy()
    if fold_df.empty:
        raise ValueError("Fold split resolved to zero rows.")
    return fold_df.reset_index(drop=True)


def explain_fold(
    *,
    run_dir: Path,
    out_dir: Path,
    fold_code: str,
    split_code: str,
    fold_df: pd.DataFrame,
    model_name: str,
) -> FoldArtifact:
    predictor = TabularPredictor.load(str(run_dir / fold_code / "predictor"))
    trainer = predictor._trainer
    bag_model = trainer.load_model(model_name)
    class_labels = [str(label) for label in predictor.class_labels]

    transformed = predictor._learner.transform_features(fold_df[predictor.features()])
    child_features: list[str] | None = None
    shap_sum: np.ndarray | None = None

    for child_name in bag_model.models:
        child = bag_model.load_child(child_name)
        if child_features is None:
            child_features = list(child.features)
        elif list(child.features) != child_features:
            raise ValueError(
                f"{fold_code}: child feature mismatch in {model_name}. "
                f"{child_name} differs from the prior child feature set."
            )

        X_child = transformed[child_features]
        explainer = shap.TreeExplainer(child.model)
        values = explainer.shap_values(X_child, check_additivity=False)
        arr = standardize_shap_values(
            values,
            row_count=len(X_child),
            feature_count=len(child_features),
            class_count=len(class_labels),
        )
        if shap_sum is None:
            shap_sum = arr
        else:
            shap_sum += arr

    if child_features is None or shap_sum is None:
        raise ValueError(f"{fold_code}: {model_name} did not expose any bag children.")

    shap_avg = shap_sum / float(len(bag_model.models))
    raw = fold_df[[col for col in META_COLS if col in fold_df.columns]].copy().reset_index(drop=True)
    raw.insert(0, "split_code", split_code)
    raw.insert(0, "fold_code", fold_code)
    raw.insert(0, "model_name", model_name)

    shap_columns: dict[str, np.ndarray] = {}
    for class_idx, class_label in enumerate(class_labels):
        for feature_idx, feature_name in enumerate(child_features):
            shap_columns[f"shap__{class_label}__{feature_name}"] = shap_avg[:, feature_idx, class_idx]

    raw = pd.concat([raw, pd.DataFrame(shap_columns)], axis=1)

    raw_path = out_dir / f"shap_values_{fold_code}_{split_code}.parquet"
    raw.to_parquet(raw_path, index=False)

    mean_abs_by_feature = np.abs(shap_avg).mean(axis=(0, 2))
    mean_abs_by_class = np.abs(shap_avg).mean(axis=0)
    summary = pd.DataFrame(
        {
            "feature_name": child_features,
            "mean_abs_shap": mean_abs_by_feature.astype(np.float64),
        }
    )
    for class_idx, class_label in enumerate(class_labels):
        summary[f"mean_abs_shap__{class_label}"] = mean_abs_by_class[:, class_idx].astype(np.float64)
    summary = summary.sort_values("mean_abs_shap", ascending=False).reset_index(drop=True)
    summary.insert(0, "importance_rank", np.arange(1, len(summary) + 1, dtype=np.int32))
    summary.insert(0, "model_name", model_name)
    summary.insert(0, "split_code", split_code)
    summary.insert(0, "fold_code", fold_code)

    summary_path = out_dir / f"shap_feature_summary_{fold_code}_{split_code}.csv"
    summary.to_csv(summary_path, index=False)

    return FoldArtifact(
        fold_code=fold_code,
        split_code=split_code,
        model_name=model_name,
        row_count=len(fold_df),
        feature_count=len(child_features),
        class_count=len(class_labels),
        child_count=len(bag_model.models),
        raw_path=str(raw_path),
        feature_summary_path=str(summary_path),
    )


def write_overall_summary(out_dir: Path, fold_summaries: list[FoldArtifact]) -> None:
    ranked_frames: list[pd.DataFrame] = []
    weights: list[int] = []
    for fold in fold_summaries:
        df = pd.read_csv(fold.feature_summary_path)
        ranked_frames.append(df)
        weights.append(fold.row_count)

    combined = ranked_frames[0][["feature_name"]].copy()
    overall = np.zeros(len(combined), dtype=np.float64)
    per_class_cols = [col for col in ranked_frames[0].columns if col.startswith("mean_abs_shap__")]
    per_class = {col: np.zeros(len(combined), dtype=np.float64) for col in per_class_cols}

    total_weight = float(sum(weights))
    for df, weight in zip(ranked_frames, weights, strict=True):
        aligned = df.set_index("feature_name").loc[combined["feature_name"]].reset_index()
        overall += aligned["mean_abs_shap"].to_numpy(dtype=np.float64) * weight
        for col in per_class_cols:
            per_class[col] += aligned[col].to_numpy(dtype=np.float64) * weight

    combined["mean_abs_shap"] = overall / total_weight
    for col in per_class_cols:
        combined[col] = per_class[col] / total_weight
    combined = combined.sort_values("mean_abs_shap", ascending=False).reset_index(drop=True)
    combined.insert(0, "importance_rank", np.arange(1, len(combined) + 1, dtype=np.int32))
    combined.to_csv(out_dir / "shap_feature_summary_overall_test.csv", index=False)


# ---------------------------------------------------------------------------
# Hi-def postprocess phase
# ---------------------------------------------------------------------------

def derive_hour_bucket(ts_series: pd.Series) -> pd.Series:
    """Convert UTC ts to Chicago-hour and bucket via monte_carlo_run HOUR_BUCKETS."""
    ts = pd.to_datetime(ts_series, utc=True)
    hour_ct = ts.dt.tz_convert(CHICAGO_TZ).dt.hour.to_numpy()
    labels = np.full(hour_ct.shape, "UNKNOWN", dtype=object)
    for lo, hi, label in MC_HOUR_BUCKETS:
        mask = (hour_ct >= lo) & (hour_ct < hi)
        labels[mask] = label
    return pd.Series(labels, index=ts_series.index, name="hour_bucket")


def backfill_archetype(combined: pd.DataFrame, dsn: str) -> pd.DataFrame:
    """Join archetype onto combined via stop_variant_id → interaction_id → archetype.

    Idempotent: if `archetype` column already present AND has no NaN, do nothing.
    """
    if "archetype" in combined.columns and not combined["archetype"].isna().any():
        return combined

    needed = combined["stop_variant_id"].dropna().astype("Int64").unique().tolist()
    if not needed:
        combined["archetype"] = pd.NA
        return combined

    query = (
        "SELECT v.id AS stop_variant_id, i.archetype "
        "FROM ag_fib_stop_variants v "
        "JOIN ag_fib_interactions i ON i.id = v.interaction_id "
        "WHERE v.id = ANY(%s)"
    )
    with psycopg2.connect(dsn) as conn:
        mapping = pd.read_sql_query(query, conn, params=(needed,))

    combined = combined.drop(columns=["archetype"], errors="ignore")
    combined = combined.merge(
        mapping, on="stop_variant_id", how="left", validate="many_to_one"
    )
    return combined


def load_combined_parquet(out_dir: Path, fold_codes: Iterable[str], split_code: str) -> pd.DataFrame:
    """Concatenate all per-fold SHAP parquets. Raw SHAP columns named shap__<class>__<feature>."""
    frames: list[pd.DataFrame] = []
    for fold_code in fold_codes:
        path = out_dir / f"shap_values_{fold_code}_{split_code}.parquet"
        if not path.exists():
            raise SystemExit(f"Missing SHAP parquet: {path}. Run compute phase first (no --postprocess-only).")
        frames.append(pd.read_parquet(path))
    combined = pd.concat(frames, ignore_index=True)
    return combined


def shap_columns_from_frame(df: pd.DataFrame) -> list[str]:
    return [c for c in df.columns if c.startswith("shap__")]


def parse_shap_column(col: str) -> tuple[str, str]:
    """shap__<class>__<feature> → (class, feature). Tolerates class names containing '__'."""
    assert col.startswith("shap__")
    rest = col[len("shap__"):]
    # Feature names never contain '__' in our feature manifest, so split from the right.
    parts = rest.rsplit("__", 1)
    if len(parts) != 2:
        raise ValueError(f"Malformed SHAP column: {col}")
    return parts[0], parts[1]


def feature_names_from_frame(df: pd.DataFrame) -> list[str]:
    feats: dict[str, None] = {}
    for col in shap_columns_from_frame(df):
        _, feat = parse_shap_column(col)
        feats.setdefault(feat, None)
    return list(feats)


def class_labels_from_frame(df: pd.DataFrame) -> list[str]:
    classes: dict[str, None] = {}
    for col in shap_columns_from_frame(df):
        cls, _ = parse_shap_column(col)
        classes.setdefault(cls, None)
    return list(classes)


def mean_abs_by_feature(df: pd.DataFrame, feature_names: list[str], class_labels: list[str]) -> np.ndarray:
    """Return (N_features,) array of mean |shap| across rows and classes."""
    out = np.zeros(len(feature_names), dtype=np.float64)
    if df.empty:
        return out
    for i, feat in enumerate(feature_names):
        acc = 0.0
        for cls in class_labels:
            col = f"shap__{cls}__{feat}"
            if col in df.columns:
                acc += np.abs(df[col].to_numpy(dtype=np.float64)).mean()
        out[i] = acc / max(len(class_labels), 1)
    return out


def mean_abs_by_feature_class(
    df: pd.DataFrame, feature_names: list[str], class_labels: list[str]
) -> np.ndarray:
    """Return (N_features, N_classes) mean |shap| per (feature, class) across rows."""
    out = np.zeros((len(feature_names), len(class_labels)), dtype=np.float64)
    if df.empty:
        return out
    for i, feat in enumerate(feature_names):
        for j, cls in enumerate(class_labels):
            col = f"shap__{cls}__{feat}"
            if col in df.columns:
                out[i, j] = np.abs(df[col].to_numpy(dtype=np.float64)).mean()
    return out


def compute_overall_importance(
    combined: pd.DataFrame,
    *,
    feature_names: list[str],
    class_labels: list[str],
    per_fold_summaries: list[pd.DataFrame],
) -> pd.DataFrame:
    """Weighted overall mean_abs_shap across all rows, plus per-fold cross-std."""
    overall = mean_abs_by_feature(combined, feature_names, class_labels)
    per_class = mean_abs_by_feature_class(combined, feature_names, class_labels)

    # Cross-fold stddev of mean_abs (a noise band on the aggregate).
    fold_vals = np.zeros((len(per_fold_summaries), len(feature_names)), dtype=np.float64)
    for fi, fdf in enumerate(per_fold_summaries):
        lookup = fdf.set_index("feature_name")["mean_abs_shap"].to_dict()
        for i, feat in enumerate(feature_names):
            fold_vals[fi, i] = float(lookup.get(feat, 0.0))
    cross_fold_std = fold_vals.std(axis=0, ddof=0)

    # top20_fold_count derived from per-fold ranks
    top20 = np.zeros(len(feature_names), dtype=np.int32)
    for fdf in per_fold_summaries:
        top_feats = fdf.nsmallest(20, "importance_rank")["feature_name"].tolist()
        top_set = set(top_feats)
        for i, feat in enumerate(feature_names):
            if feat in top_set:
                top20[i] += 1

    df = pd.DataFrame({"feature_name": feature_names, "mean_abs_shap": overall})
    for j, cls in enumerate(class_labels):
        df[f"mean_abs_shap__{cls}"] = per_class[:, j]
    df["cross_fold_std"] = cross_fold_std
    df["top20_fold_count"] = top20
    df = df.sort_values("mean_abs_shap", ascending=False).reset_index(drop=True)
    df.insert(0, "rank", np.arange(1, len(df) + 1, dtype=np.int32))
    return df


def compute_per_class_importance(
    combined: pd.DataFrame,
    *,
    feature_names: list[str],
    class_labels: list[str],
    top_n: int = 100,
) -> pd.DataFrame:
    """Long-form per-class importance table: (class_name, rank_within_class, feature, mean_abs_shap)."""
    rows: list[dict[str, Any]] = []
    for cls in class_labels:
        vals = np.array(
            [
                np.abs(combined.get(f"shap__{cls}__{feat}", pd.Series(dtype=float)).to_numpy(dtype=np.float64)).mean()
                if f"shap__{cls}__{feat}" in combined.columns
                else 0.0
                for feat in feature_names
            ],
            dtype=np.float64,
        )
        order = np.argsort(-vals)
        for rank, idx in enumerate(order[:top_n], start=1):
            rows.append(
                {
                    "class_name": cls,
                    "rank_within_class": rank,
                    "feature_name": feature_names[idx],
                    "mean_abs_shap": float(vals[idx]),
                }
            )
    return pd.DataFrame(rows)


def compute_cohort_importance(
    combined: pd.DataFrame,
    *,
    feature_names: list[str],
    class_labels: list[str],
    group_col: str,
    out_subdir: Path,
    min_rows: int,
    max_features: int,
) -> tuple[dict[str, int], dict[str, np.ndarray]]:
    """Write one CSV per unique value of `group_col`.

    Returns:
        counts: {cohort_value -> row_count}
        full_vectors: {cohort_value -> (N_features,) mean_abs_shap vector, UNTRUNCATED}

    The CSV is truncated to `max_features` for human scannability, but the full
    per-feature vector is returned in memory so downstream cross-cohort variance
    computation (feeding LEAKAGE_SUSPECT) sees every feature, not just the ones
    that happened to rank in the CSV top-N. Without this, a feature that drops
    out of one cohort's top-N would be silently missing from its CV input,
    biasing the CV downward and producing false leakage flags.
    """
    counts: dict[str, int] = {}
    full_vectors: dict[str, np.ndarray] = {}
    out_subdir.mkdir(parents=True, exist_ok=True)
    if group_col not in combined.columns:
        return counts, full_vectors
    for value in pd.unique(combined[group_col].dropna()):
        mask = combined[group_col] == value
        n = int(mask.sum())
        if n < min_rows:
            continue
        sub = combined.loc[mask]
        overall = mean_abs_by_feature(sub, feature_names, class_labels)
        per_class = mean_abs_by_feature_class(sub, feature_names, class_labels)
        df = pd.DataFrame({"feature_name": feature_names, "mean_abs_shap": overall})
        for j, cls in enumerate(class_labels):
            df[f"mean_abs_shap__{cls}"] = per_class[:, j]
        df = df.sort_values("mean_abs_shap", ascending=False).head(max_features).reset_index(drop=True)
        df.insert(0, "rank", np.arange(1, len(df) + 1, dtype=np.int32))
        df.insert(1, "cohort_value", str(value))
        df.insert(1, "n_rows", n)
        safe_value = str(value).replace("/", "_")
        df.to_csv(out_subdir / f"{safe_value}.csv", index=False)
        counts[str(value)] = n
        full_vectors[str(value)] = overall
    return counts, full_vectors


def compute_temporal_stability(
    per_fold_summaries: list[pd.DataFrame], feature_names: list[str]
) -> pd.DataFrame:
    """Build (rank_min/max/range, mean_abs_min/max/cv, top20_fold_count, stability_bucket).

    Bucket rules (checked in order, first match wins) locked in
    docs/plans/2026-04-15-hi-def-shap-mc-implementation.md:
      DEAD         : mean_abs_max < 0.005
      STABLE_CORE  : rank_max <= 20 AND mean_abs_cv < 0.30 AND top20_fold_count = 5
      STABLE_MID   : rank_max <= 50 AND mean_abs_cv < 0.50 AND top20_fold_count >= 3
      VOLATILE     : rank_range > 40 OR mean_abs_cv >= 0.50
      STABLE_WEAK  : mean_abs_cv < 0.30 AND aggregate mean_abs_shap < 0.05
      fallback     : UNCLASSIFIED
    """
    n_feats = len(feature_names)
    n_folds = len(per_fold_summaries)
    rank_matrix = np.full((n_folds, n_feats), np.nan, dtype=np.float64)
    val_matrix = np.zeros((n_folds, n_feats), dtype=np.float64)

    for fi, fdf in enumerate(per_fold_summaries):
        rank_lookup = fdf.set_index("feature_name")["importance_rank"].to_dict()
        val_lookup = fdf.set_index("feature_name")["mean_abs_shap"].to_dict()
        for i, feat in enumerate(feature_names):
            rank_matrix[fi, i] = float(rank_lookup.get(feat, np.nan))
            val_matrix[fi, i] = float(val_lookup.get(feat, 0.0))

    with np.errstate(invalid="ignore"):
        rank_min = np.nanmin(rank_matrix, axis=0)
        rank_max = np.nanmax(rank_matrix, axis=0)
    rank_range = rank_max - rank_min

    val_min = val_matrix.min(axis=0)
    val_max = val_matrix.max(axis=0)
    val_mean = val_matrix.mean(axis=0)
    val_std = val_matrix.std(axis=0, ddof=0)
    with np.errstate(divide="ignore", invalid="ignore"):
        mean_abs_cv = np.where(val_mean > 0, val_std / val_mean, np.inf)

    top20_count = (rank_matrix <= 20).sum(axis=0)
    aggregate_mean = val_mean

    buckets = np.empty(n_feats, dtype=object)
    for i in range(n_feats):
        if val_max[i] < 0.005:
            buckets[i] = "DEAD"
        elif (rank_max[i] <= 20) and (mean_abs_cv[i] < 0.30) and (top20_count[i] == n_folds):
            buckets[i] = "STABLE_CORE"
        elif (rank_max[i] <= 50) and (mean_abs_cv[i] < 0.50) and (top20_count[i] >= 3):
            buckets[i] = "STABLE_MID"
        elif (rank_range[i] > 40) or (mean_abs_cv[i] >= 0.50):
            buckets[i] = "VOLATILE"
        elif (mean_abs_cv[i] < 0.30) and (aggregate_mean[i] < 0.05):
            buckets[i] = "STABLE_WEAK"
        else:
            buckets[i] = "UNCLASSIFIED"

    return pd.DataFrame(
        {
            "feature_name": feature_names,
            "rank_min": rank_min,
            "rank_max": rank_max,
            "rank_range": rank_range,
            "mean_abs_min": val_min,
            "mean_abs_max": val_max,
            "mean_abs_cv": mean_abs_cv,
            "top20_fold_count": top20_count.astype(np.int32),
            "stability_bucket": buckets,
        }
    ).sort_values(["stability_bucket", "mean_abs_max"], ascending=[True, False]).reset_index(drop=True)


def compute_calibration(
    combined: pd.DataFrame,
    *,
    run_dir: Path,
    fold_codes: list[str],
    feature_manifest: dict[str, Any],
    dsn: str,
    dataset_summary: dict[str, Any],
    class_labels: list[str],
) -> pd.DataFrame:
    """For each (stop_family × direction × fib_level) cohort × class, compute predicted vs realized.

    Runs predict_proba per fold against its test split from the reloaded enriched frame.
    Merges predictions with combined SHAP metadata by (fold_code, stop_variant_id) — this
    is the true row key on the normalized AG schema. `id` alone is interaction_id and
    repeats 6× across stop variants (would collapse 6 rows into 1 under one_to_one merge
    or cartesian-expand without it).
    """
    label = str(feature_manifest["label"])
    enriched = load_enriched_dataset(dsn=dsn, dataset_summary=dataset_summary, label=label)
    training_summary = read_json(run_dir / "training_summary.json")

    predicted_rows: list[pd.DataFrame] = []
    for fold in training_summary["folds"]:
        fc = str(fold["fold_code"])
        if fc not in fold_codes:
            continue
        split_sessions = pd.to_datetime(list(fold["test_sessions"]))
        fold_df = enriched[enriched["session_date_ct"].isin(split_sessions)].reset_index(drop=True)
        if fold_df.empty:
            continue
        predictor = TabularPredictor.load(str(run_dir / fc / "predictor"), require_py_version_match=False)
        try:
            expected = list(predictor.features())
        except AttributeError:
            expected = list(predictor.feature_metadata_in.get_features())
        X = fold_df.copy()
        for col in expected:
            if col not in X.columns:
                X[col] = np.nan
        pp = predictor.predict_proba(X[expected])
        pp = pp.reindex(columns=class_labels, fill_value=0.0)
        pp.columns = [f"pred_p__{c}" for c in class_labels]
        pp["stop_variant_id"] = fold_df["stop_variant_id"].to_numpy()
        pp["fold_code"] = fc
        predicted_rows.append(pp)

    if not predicted_rows:
        return pd.DataFrame()

    preds = pd.concat(predicted_rows, ignore_index=True)
    merged = combined.merge(
        preds, on=["fold_code", "stop_variant_id"], how="inner", validate="one_to_one"
    )

    rows: list[dict[str, Any]] = []
    cohort_dims = ["stop_family_id", "direction", "fib_level_touched"]
    for dim in cohort_dims:
        for value in pd.unique(merged[dim].dropna()):
            sub = merged[merged[dim] == value]
            if len(sub) < 200:
                continue
            for cls in class_labels:
                predicted = float(sub[f"pred_p__{cls}"].mean())
                realized = float((sub["outcome_label"].astype(str) == cls).mean())
                # P1 fix: the old `OK if predicted < 0.005` short-circuit hid the
                # exact rare-class failure we care about (model basically never
                # predicts TP3/TP4/TP5 yet class still occurs). Split predicted==0
                # into its own explicit verdict; rare but realized → ZERO_PREDICTION_MISS.
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
                        "cohort_value": str(value),
                        "n_rows": int(len(sub)),
                        "class": cls,
                        "predicted_mean_p": predicted,
                        "realized_freq": realized,
                        "ratio": ratio,
                        "verdict": verdict,
                    }
                )
    return pd.DataFrame(rows)


def compute_redundancy(
    *,
    run_dir: Path,
    fold_codes: list[str],
    feature_manifest: dict[str, Any],
    dsn: str,
    dataset_summary: dict[str, Any],
    corr_threshold: float,
) -> pd.DataFrame:
    """Find feature pairs with |Pearson| > threshold across pooled transformed fold frames."""
    label = str(feature_manifest["label"])
    enriched = load_enriched_dataset(dsn=dsn, dataset_summary=dataset_summary, label=label)
    training_summary = read_json(run_dir / "training_summary.json")

    pooled: list[pd.DataFrame] = []
    for fold in training_summary["folds"]:
        fc = str(fold["fold_code"])
        if fc not in fold_codes:
            continue
        split_sessions = pd.to_datetime(list(fold["test_sessions"]))
        fold_df = enriched[enriched["session_date_ct"].isin(split_sessions)].reset_index(drop=True)
        if fold_df.empty:
            continue
        predictor = TabularPredictor.load(str(run_dir / fc / "predictor"), require_py_version_match=False)
        transformed = predictor._learner.transform_features(fold_df[predictor.features()])
        pooled.append(transformed)

    if not pooled:
        return pd.DataFrame()

    df = pd.concat(pooled, ignore_index=True)
    # Numeric-only columns for Pearson
    numeric = df.select_dtypes(include=[np.number])
    # Sample if very large (correlation is O(F^2 × N))
    if len(numeric) > 50_000:
        numeric = numeric.sample(n=50_000, random_state=42)
    corr = numeric.corr(method="pearson").abs()
    pairs: list[dict[str, Any]] = []
    cols = corr.columns.tolist()
    for i in range(len(cols)):
        for j in range(i + 1, len(cols)):
            v = corr.iat[i, j]
            if pd.notna(v) and v >= corr_threshold:
                pairs.append(
                    {
                        "feature_a": cols[i],
                        "feature_b": cols[j],
                        "abs_pearson": float(v),
                    }
                )
    return pd.DataFrame(pairs).sort_values("abs_pearson", ascending=False).reset_index(drop=True)


def compute_drop_candidates(
    *,
    overall: pd.DataFrame,
    stability: pd.DataFrame,
    redundancy: pd.DataFrame,
    cohort_importance_cv: pd.Series,
    leakage_rank_threshold: int,
    leakage_cv_threshold: float,
) -> pd.DataFrame:
    """Label drop candidates with one reason per feature.

    Reason codes (first match wins):
      DEAD                : stability_bucket == 'DEAD'
      LEAKAGE_SUSPECT     : (overall rank <= leakage_rank_threshold OR mean_abs_shap > 0.10)
                            AND cross-cohort mean_abs_cv < leakage_cv_threshold
      REDUNDANT           : in a high-corr pair AND lower mean_abs_shap than its partner
      UNSTABLE_LOW_VALUE  : stability_bucket in {'VOLATILE','UNCLASSIFIED'} AND mean_abs_shap < 0.10
    """
    stab_lookup = stability.set_index("feature_name")["stability_bucket"].to_dict()
    rank_lookup = overall.set_index("feature_name")["rank"].to_dict()
    mean_lookup = overall.set_index("feature_name")["mean_abs_shap"].to_dict()
    cohort_cv_lookup = cohort_importance_cv.to_dict()

    # Redundancy partners: for each pair, whichever has the smaller mean_abs_shap is redundant.
    redundant_rows: list[tuple[str, str]] = []
    if not redundancy.empty:
        for _, row in redundancy.iterrows():
            a, b = row["feature_a"], row["feature_b"]
            mean_a = mean_lookup.get(a, 0.0)
            mean_b = mean_lookup.get(b, 0.0)
            if mean_a <= mean_b:
                redundant_rows.append((a, b))
            else:
                redundant_rows.append((b, a))
    redundant_to_partner: dict[str, str] = {}
    for loser, winner in redundant_rows:
        redundant_to_partner.setdefault(loser, winner)

    rows: list[dict[str, Any]] = []
    for feat in overall["feature_name"].tolist():
        bucket = stab_lookup.get(feat, "UNCLASSIFIED")
        rank = int(rank_lookup.get(feat, 9_999))
        mean_abs = float(mean_lookup.get(feat, 0.0))
        cohort_cv = float(cohort_cv_lookup.get(feat, math.nan))

        if bucket == "DEAD":
            reason = "DEAD"
            detail = f"mean_abs_max below 0.005 across all folds"
        elif (
            (rank <= leakage_rank_threshold or mean_abs > 0.10)
            and not math.isnan(cohort_cv)
            and cohort_cv < leakage_cv_threshold
        ):
            reason = "LEAKAGE_SUSPECT"
            detail = f"rank={rank} mean_abs={mean_abs:.4f} cohort_cv={cohort_cv:.4f}"
        elif feat in redundant_to_partner:
            reason = "REDUNDANT"
            detail = f"pair={redundant_to_partner[feat]}"
        elif bucket in ("VOLATILE", "UNCLASSIFIED") and mean_abs < 0.10:
            reason = "UNSTABLE_LOW_VALUE"
            detail = f"bucket={bucket} mean_abs={mean_abs:.4f}"
        else:
            continue  # not a drop candidate

        rows.append(
            {
                "feature_name": feat,
                "reason_code": reason,
                "rank": rank,
                "mean_abs_shap": mean_abs,
                "stability_bucket": bucket,
                "cohort_cv": cohort_cv,
                "detail": detail,
            }
        )
    return pd.DataFrame(rows)


def compute_cohort_cv_by_feature(
    all_cohort_vectors: dict[str, np.ndarray], feature_names: list[str]
) -> pd.Series:
    """Compute cross-cohort coefficient of variation per feature.

    Takes the UNTRUNCATED per-cohort per-feature mean_abs_shap matrix
    assembled in `run_postprocess_phase` from the second return value of
    `compute_cohort_importance`. Reading from the top-N CSVs would bias CV
    downward by omitting each feature's value in cohorts where it didn't
    make the top-N — falsely promoting those features to LEAKAGE_SUSPECT.
    """
    if not all_cohort_vectors:
        return pd.Series({feat: math.nan for feat in feature_names}, name="cohort_cv")
    matrix = np.stack(list(all_cohort_vectors.values()), axis=0)  # (N_cohorts, N_features)
    means = matrix.mean(axis=0)
    stds = matrix.std(axis=0, ddof=0)
    with np.errstate(divide="ignore", invalid="ignore"):
        cvs = np.where(means > 0, stds / means, math.nan)
    return pd.Series(cvs, index=feature_names, name="cohort_cv")


def write_summary_md(
    out_dir: Path,
    *,
    run_id: str,
    overall: pd.DataFrame,
    per_class: pd.DataFrame,
    stability: pd.DataFrame,
    calibration: pd.DataFrame,
    redundancy: pd.DataFrame,
    drops: pd.DataFrame,
    cohort_row_counts: dict[str, dict[str, int]],
    leakage_rank_threshold: int,
    leakage_cv_threshold: float,
) -> None:
    lines: list[str] = []
    lines.append(f"# SHAP Deep-Dive — `{run_id}`")
    lines.append("")
    lines.append(f"Generated by `scripts/ag/run_diagnostic_shap.py` postprocess phase.")
    lines.append("")

    # TL;DR
    lines.append("## TL;DR")
    top5 = overall.head(5)
    lines.append("")
    lines.append("Top 5 drivers by mean_abs_shap:")
    for _, r in top5.iterrows():
        lines.append(f"- **{r['feature_name']}** (rank {int(r['rank'])}, mean_abs={r['mean_abs_shap']:.4f})")
    lines.append("")

    # Stable core
    core = stability[stability["stability_bucket"] == "STABLE_CORE"].head(10)
    lines.append("## Stable core drivers (STABLE_CORE)")
    lines.append("")
    if core.empty:
        lines.append("None.")
    else:
        lines.append("| feature | rank_max | mean_abs_cv | top20 | mean_abs_max |")
        lines.append("|---|---:|---:|---:|---:|")
        for _, r in core.iterrows():
            lines.append(
                f"| {r['feature_name']} | {int(r['rank_max']) if not pd.isna(r['rank_max']) else '-'} | "
                f"{r['mean_abs_cv']:.3f} | {int(r['top20_fold_count'])} | {r['mean_abs_max']:.4f} |"
            )
    lines.append("")

    # Per-class
    lines.append("## Per-class top drivers")
    lines.append("")
    for cls in sorted(per_class["class_name"].unique()):
        sub = per_class[per_class["class_name"] == cls].head(5)
        lines.append(f"**{cls}**")
        for _, r in sub.iterrows():
            lines.append(
                f"- {r['feature_name']} (rank_within_class={int(r['rank_within_class'])}, "
                f"mean_abs={r['mean_abs_shap']:.4f})"
            )
        lines.append("")

    # Per-cohort summary — row counts
    lines.append("## Per-cohort coverage")
    lines.append("")
    for dim, counts in cohort_row_counts.items():
        if not counts:
            continue
        lines.append(f"- **{dim}**: " + ", ".join(f"{k}={v}" for k, v in sorted(counts.items())))
    lines.append("")

    # Leakage verdict
    leak = drops[drops["reason_code"] == "LEAKAGE_SUSPECT"]
    verdict = "SUSPECT" if not leak.empty else "LIKELY CLEAN"
    lines.append(f"## Leakage verdict: **{verdict}**")
    lines.append("")
    lines.append(
        f"Criteria: rank ≤ {leakage_rank_threshold} (or mean_abs_shap > 0.10) "
        f"AND cross-cohort mean_abs_cv < {leakage_cv_threshold}."
    )
    lines.append("")
    if not leak.empty:
        lines.append("Suspect features:")
        for _, r in leak.iterrows():
            lines.append(
                f"- `{r['feature_name']}` — rank {int(r['rank'])}, "
                f"mean_abs={r['mean_abs_shap']:.4f}, cohort_cv={r['cohort_cv']:.4f}"
            )
        lines.append("")
        lines.append(
            "**Interpretation:** these features have high importance that is suspiciously uniform "
            "across every cohort slice. That pattern matches IID bag-fold leakage (model uses the "
            "feature as a time-identity proxy). Re-run SHAP on a clean `--num-bag-folds 0` training "
            "run to confirm; if the same features stay flagged there, treat as real regime signal."
        )
    else:
        lines.append("No features passed both leakage gates.")
    lines.append("")

    # Calibration
    lines.append("## Calibration check")
    lines.append("")
    if calibration.empty:
        lines.append("Calibration step did not run (use `--calibrate`).")
    else:
        bad = calibration[calibration["verdict"] != "OK"]
        if bad.empty:
            lines.append("All cohort × class ratios within [0.7, 1.3]. Calibration looks acceptable.")
        else:
            lines.append(f"{len(bad)} cohort × class pairs fall outside [0.7, 1.3]:")
            lines.append("")
            lines.append("| cohort | value | class | predicted | realized | ratio | verdict |")
            lines.append("|---|---|---|---:|---:|---:|---|")
            for _, r in bad.head(25).iterrows():
                lines.append(
                    f"| {r['cohort_dim']} | {r['cohort_value']} | {r['class']} | "
                    f"{r['predicted_mean_p']:.4f} | {r['realized_freq']:.4f} | "
                    f"{r['ratio']:.3f} | {r['verdict']} |"
                )
    lines.append("")

    # Redundancy / drop candidates
    lines.append("## Redundancy & drop candidates")
    lines.append("")
    lines.append(
        f"Total drop candidates: {len(drops)}. "
        f"Full table at `drop_candidates.csv`; redundancy pairs at `redundancy_check.csv`."
    )
    lines.append("")
    if not drops.empty:
        by_reason = drops["reason_code"].value_counts().to_dict()
        for reason, n in by_reason.items():
            lines.append(f"- **{reason}**: {n}")
    lines.append("")

    # Actionable observations
    lines.append("## Actionable entry / TP observations")
    lines.append("")
    lines.append("Derivable from the top-5 drivers (above) + per-class + per-cohort tables:")
    lines.append("")
    lines.append(
        "- Features appearing in multiple cohorts' top-5 (e.g., across fib_level × hour_bucket × "
        "stop_family) are the most structurally important for entry gating. Cross-ref the "
        "per-cohort CSVs under `per_cohort_importance/`."
    )
    lines.append(
        "- Features whose per-class importance peaks at TP3_HIT / TP4_HIT / TP5_HIT indicate "
        "TP-ladder decision signal. Use `per_class_importance.csv` filtered by class to surface."
    )
    lines.append(
        "- Leakage suspects (if any) must be validated on a clean re-run before entry rules "
        "condition on them."
    )
    lines.append(
        "- MC cross-ref: top SHAP features should feed `monte_carlo_run.py --shap-top-features` "
        "for Task E entry-rule expansion (see `training-monte-carlo` skill)."
    )
    lines.append("")

    (out_dir / "summary.md").write_text("\n".join(lines) + "\n")


def write_manifest(
    out_dir: Path,
    *,
    run_id: str,
    source_run_dir: Path,
    split_code: str,
    model_name: str,
    fold_artifacts: list[dict[str, Any]] | None,
    cohort_row_counts: dict[str, dict[str, int]],
    leakage_verdict: str,
    drop_candidates_count: int,
    calibration_ran: bool,
    postprocess_only: bool,
) -> None:
    manifest = {
        "run_id": run_id,
        "source_run_dir": str(source_run_dir),
        "split_code": split_code,
        "model_name": model_name,
        "diagnostic_only": True,
        "postprocess_only": postprocess_only,
        "cohort_row_counts": cohort_row_counts,
        "leakage_verdict": leakage_verdict,
        "drop_candidates_count": drop_candidates_count,
        "calibration_ran": calibration_ran,
        "new_outputs": [
            "overall_importance.csv",
            "per_class_importance.csv",
            "per_cohort_importance/",
            "temporal_stability.csv",
            "calibration_check.csv",
            "redundancy_check.csv",
            "drop_candidates.csv",
            "summary.md",
        ],
        "notes": [
            "Diagnostic SHAP only. Source run used internal AutoGluon IID bagging/stacking "
            "and is not promotion-safe.",
            "SHAP values were averaged across the saved bag children of the selected AutoGluon model.",
            "Raw artifacts live under artifacts/shap/{run_id}/ and do not modify the source predictor.",
        ],
    }
    if fold_artifacts is not None:
        manifest["fold_artifacts"] = fold_artifacts
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")


def run_postprocess_phase(
    args: argparse.Namespace,
    *,
    run_dir: Path,
    out_dir: Path,
    fold_codes: list[str],
    feature_manifest: dict[str, Any],
    dataset_summary: dict[str, Any],
) -> None:
    skip_cohorts = {c.strip() for c in args.skip_cohorts.split(",") if c.strip()}

    print(f"[postprocess] loading combined SHAP parquet from {out_dir}...")
    combined = load_combined_parquet(out_dir, fold_codes, args.split_code)
    print(f"[postprocess] combined rows = {len(combined)}")

    # Metadata enrichment
    combined = backfill_archetype(combined, args.dsn)
    if "ts" in combined.columns:
        combined["hour_bucket"] = derive_hour_bucket(combined["ts"])
    else:
        combined["hour_bucket"] = "UNKNOWN"

    # Per-fold summaries (existing files)
    per_fold_summaries: list[pd.DataFrame] = []
    for fc in fold_codes:
        per_fold_summaries.append(
            pd.read_csv(out_dir / f"shap_feature_summary_{fc}_{args.split_code}.csv")
        )

    feature_names = feature_names_from_frame(combined)
    class_labels = class_labels_from_frame(combined)
    print(f"[postprocess] {len(feature_names)} features × {len(class_labels)} classes")

    if args.dry_run:
        print("[postprocess] dry run — reporting cohort sizes and exiting.")
        for subdir, col in COHORT_DIMS.items():
            if subdir in skip_cohorts or col not in combined.columns:
                continue
            counts = combined[col].value_counts(dropna=True).to_dict()
            filtered = {k: v for k, v in counts.items() if v >= args.cohort_min_rows}
            print(f"  {subdir} ({col}): {filtered}")
        return

    # Overall importance
    overall = compute_overall_importance(
        combined,
        feature_names=feature_names,
        class_labels=class_labels,
        per_fold_summaries=per_fold_summaries,
    )
    overall.to_csv(out_dir / "overall_importance.csv", index=False)
    print(f"[postprocess] wrote overall_importance.csv ({len(overall)} features)")

    # Per-class importance (long-form)
    per_class = compute_per_class_importance(
        combined,
        feature_names=feature_names,
        class_labels=class_labels,
    )
    per_class.to_csv(out_dir / "per_class_importance.csv", index=False)
    print(f"[postprocess] wrote per_class_importance.csv ({len(per_class)} rows)")

    # Per-cohort importance — capture full (untruncated) per-feature vectors
    # so LEAKAGE_SUSPECT CV is computed without top-N truncation bias (see P2).
    cohort_row_counts: dict[str, dict[str, int]] = {}
    all_cohort_vectors: dict[str, np.ndarray] = {}  # keys are "<dim>:<value>"
    cohort_root = out_dir / "per_cohort_importance"
    for subdir, col in COHORT_DIMS.items():
        if subdir in skip_cohorts:
            cohort_row_counts[subdir] = {}
            continue
        counts, full_vectors = compute_cohort_importance(
            combined,
            feature_names=feature_names,
            class_labels=class_labels,
            group_col=col,
            out_subdir=cohort_root / subdir,
            min_rows=args.cohort_min_rows,
            max_features=args.max_features_per_cohort,
        )
        cohort_row_counts[subdir] = counts
        for value, vec in full_vectors.items():
            all_cohort_vectors[f"{subdir}:{value}"] = vec
        print(f"[postprocess] wrote {subdir}: {len(counts)} cohort files")

    # Temporal stability
    stability = compute_temporal_stability(per_fold_summaries, feature_names)
    stability.to_csv(out_dir / "temporal_stability.csv", index=False)
    print(
        f"[postprocess] wrote temporal_stability.csv "
        f"({stability['stability_bucket'].value_counts().to_dict()})"
    )

    # Calibration
    calibration = pd.DataFrame()
    if args.calibrate:
        try:
            calibration = compute_calibration(
                combined,
                run_dir=run_dir,
                fold_codes=fold_codes,
                feature_manifest=feature_manifest,
                dsn=args.dsn,
                dataset_summary=dataset_summary,
                class_labels=class_labels,
            )
            calibration.to_csv(out_dir / "calibration_check.csv", index=False)
            print(f"[postprocess] wrote calibration_check.csv ({len(calibration)} rows)")
        except Exception as exc:  # calibration is expensive; surface but do not abort
            print(f"[postprocess] WARNING: calibration failed: {exc}")
            calibration = pd.DataFrame()

    # Redundancy
    try:
        redundancy = compute_redundancy(
            run_dir=run_dir,
            fold_codes=fold_codes,
            feature_manifest=feature_manifest,
            dsn=args.dsn,
            dataset_summary=dataset_summary,
            corr_threshold=args.redundancy_corr_threshold,
        )
    except Exception as exc:
        print(f"[postprocess] WARNING: redundancy failed: {exc}")
        redundancy = pd.DataFrame()
    redundancy.to_csv(out_dir / "redundancy_check.csv", index=False)
    print(f"[postprocess] wrote redundancy_check.csv ({len(redundancy)} pairs)")

    # Cross-cohort CV per feature (feeds LEAKAGE_SUSPECT). Uses the UNTRUNCATED
    # full-feature cohort vectors gathered above, not the top-N cohort CSVs.
    cohort_cv = compute_cohort_cv_by_feature(all_cohort_vectors, feature_names)

    # Drop candidates
    drops = compute_drop_candidates(
        overall=overall,
        stability=stability,
        redundancy=redundancy,
        cohort_importance_cv=cohort_cv,
        leakage_rank_threshold=args.leakage_rank_threshold,
        leakage_cv_threshold=args.leakage_cv_threshold,
    )
    drops.to_csv(out_dir / "drop_candidates.csv", index=False)
    print(
        f"[postprocess] wrote drop_candidates.csv: "
        f"{drops['reason_code'].value_counts().to_dict() if not drops.empty else {}}"
    )

    # Summary + manifest
    write_summary_md(
        out_dir,
        run_id=args.run_id,
        overall=overall,
        per_class=per_class,
        stability=stability,
        calibration=calibration,
        redundancy=redundancy,
        drops=drops,
        cohort_row_counts=cohort_row_counts,
        leakage_rank_threshold=args.leakage_rank_threshold,
        leakage_cv_threshold=args.leakage_cv_threshold,
    )
    leak_suspect_count = int((drops["reason_code"] == "LEAKAGE_SUSPECT").sum()) if not drops.empty else 0
    leakage_verdict = "SUSPECT" if leak_suspect_count > 0 else "LIKELY CLEAN"
    write_manifest(
        out_dir,
        run_id=args.run_id,
        source_run_dir=run_dir,
        split_code=args.split_code,
        model_name=args.model_name,
        fold_artifacts=None,
        cohort_row_counts=cohort_row_counts,
        leakage_verdict=leakage_verdict,
        drop_candidates_count=int(len(drops)),
        calibration_ran=not calibration.empty,
        postprocess_only=args.postprocess_only,
    )
    print(f"[postprocess] complete. leakage verdict: {leakage_verdict}. summary.md + manifest.json written.")


def run_compute_phase(args: argparse.Namespace) -> tuple[Path, dict[str, Any], dict[str, Any], list[str]]:
    run_dir, dataset_summary, feature_manifest, training_summary = load_run_context(args.run_id)
    label = str(feature_manifest["label"])
    enriched = load_enriched_dataset(
        dsn=args.dsn,
        dataset_summary=dataset_summary,
        label=label,
    )

    out_dir = (Path(args.output_root) / args.run_id).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    fold_artifacts: list[FoldArtifact] = []
    for fold in training_summary["folds"]:
        fold_code = str(fold["fold_code"])
        split_sessions = list(fold[f"{args.split_code}_sessions"])
        fold_df = build_fold_frame(
            enriched,
            split_sessions=split_sessions,
            max_rows=args.max_rows_per_fold,
        )
        fold_artifacts.append(
            explain_fold(
                run_dir=run_dir,
                out_dir=out_dir,
                fold_code=fold_code,
                split_code=args.split_code,
                fold_df=fold_df,
                model_name=args.model_name,
            )
        )

    write_overall_summary(out_dir, fold_artifacts)
    # Preserve the existing diagnostic_shap_manifest.json so backward-compat readers still work.
    manifest = {
        "run_id": args.run_id,
        "source_run_dir": str(run_dir),
        "split_code": args.split_code,
        "model_name": args.model_name,
        "diagnostic_only": True,
        "notes": [
            "Diagnostic SHAP only. Source run used internal AutoGluon IID bagging/stacking and is not promotion-safe.",
            "SHAP values were averaged across the saved bag children of the selected AutoGluon model.",
            "Raw artifacts live under artifacts/shap/{run_id}/ and do not modify the source predictor.",
        ],
        "fold_artifacts": [asdict(item) for item in fold_artifacts],
    }
    (out_dir / "diagnostic_shap_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    fold_codes = [fa.fold_code for fa in fold_artifacts]
    return run_dir, feature_manifest, dataset_summary, fold_codes


def main() -> None:
    args = parse_args()

    out_dir = (Path(args.output_root) / args.run_id).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    if args.postprocess_only:
        run_dir, dataset_summary, feature_manifest, training_summary = load_run_context(args.run_id)
        existing_manifest_path = out_dir / "diagnostic_shap_manifest.json"
        if not existing_manifest_path.exists():
            raise SystemExit(
                f"Missing existing diagnostic_shap_manifest.json at {existing_manifest_path}. "
                "Cannot postprocess without prior compute phase."
            )
        manifest = read_json(existing_manifest_path)
        fold_codes = [fa["fold_code"] for fa in manifest["fold_artifacts"]]
    else:
        run_dir, feature_manifest, dataset_summary, fold_codes = run_compute_phase(args)

    run_postprocess_phase(
        args,
        run_dir=run_dir,
        out_dir=out_dir,
        fold_codes=fold_codes,
        feature_manifest=feature_manifest,
        dataset_summary=dataset_summary,
    )


if __name__ == "__main__":
    main()
