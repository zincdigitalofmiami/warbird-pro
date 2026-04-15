#!/usr/bin/env python3
from __future__ import annotations

# Apple Silicon / OpenMP guard — must be set before LightGBM or AutoGluon is imported.
# Without this, LightGBM's OpenMP threads deadlock against AG's parallelism on M-series Macs,
# causing GBM trials to stall indefinitely while holding ~400MB of memory.
import os
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("LIGHTGBM_NUM_THREADS", "1")

import argparse
import json
import subprocess
import sys
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd
import psycopg2
from psycopg2.extras import Json


CHICAGO_TZ = ZoneInfo("America/Chicago")
DEFAULT_DSN = os.environ.get("WARBIRD_PG_DSN", "host=127.0.0.1 port=5432 dbname=warbird")
DEFAULT_OUTPUT_ROOT = "artifacts/ag_runs"
DEFAULT_TIME_LIMIT_SEC = 3600

# ---------------------------------------------------------------------------
# Canonical training contract — drift guards (2026-04-15).
# ---------------------------------------------------------------------------
# CANONICAL_ZOO is the only legal hyperparameters dict for this trainer.
# Any edit that removes or renames a family dies at import time via
# _assert_canonical_zoo(). GBM-only runs do not exist on this project —
# they are scientifically useless for model selection and have silently
# masqueraded as "full zoo" before, wasting wall time.
#
# Thread pins (num_threads=1 / thread_count=1 / n_jobs=1) are load-bearing:
# they prevent LightGBM/OpenMP deadlocks on Apple Silicon.
#
# To change the zoo intentionally: edit both CANONICAL_ZOO and
# CANONICAL_ZOO_FAMILIES together, commit with ZOO_CHANGE_APPROVED: in the
# message (see .githooks/commit-msg), and announce in the session log.
CANONICAL_ZOO_FAMILIES: frozenset[str] = frozenset({
    "GBM", "CAT", "XGB", "RF", "XT", "NN_TORCH", "FASTAI",
})
CANONICAL_ZOO: dict[str, list[dict[str, Any]]] = {
    "GBM":      [{"num_threads": 1}, {"num_threads": 1, "extra_trees": True}],
    "CAT":      [{"thread_count": 1}],
    "XGB":      [{"n_jobs": 1}],
    "RF":       [{"criterion": "gini"}, {"criterion": "entropy"}],
    "XT":       [{"criterion": "gini"}, {"criterion": "entropy"}],
    "NN_TORCH": [{}],
    "FASTAI":   [{}],
}


def _assert_canonical_zoo() -> None:
    """Fail fast at import if the zoo has drifted from the 7-family canon."""
    got = set(CANONICAL_ZOO)
    if got != CANONICAL_ZOO_FAMILIES:
        missing = sorted(CANONICAL_ZOO_FAMILIES - got)
        extra = sorted(got - CANONICAL_ZOO_FAMILIES)
        raise SystemExit(
            "CANONICAL_ZOO drift detected. "
            f"missing={missing} extra={extra}. "
            "Full zoo is mandatory on this project — do NOT launch."
        )


_assert_canonical_zoo()

# ag_training row count floor — pinned 2026-04-15 after migration 016 produced
# 327,972 stop_variants / 327,942 training rows (end-of-history truncation).
# Buffer below true count absorbs minor shifts as data extends forward, but
# still screams if the pipeline loaded only a partial surface.
EXPECTED_AG_TRAINING_ROWS_FLOOR: int = 327_000

ECON_TABLES = (
    "econ_activity_1d",
    "econ_commodities_1d",
    "econ_fx_1d",
    "econ_indexes_1d",
    "econ_inflation_1d",
    "econ_labor_1d",
    "econ_money_1d",
    "econ_rates_1d",
    "econ_vol_1d",
    "econ_yields_1d",
)
CURATED_FRED_SERIES = (
    "SP500",
    "DFF",
    "SOFR",
    "T10Y2Y",
    "DGS2",
    "DGS5",
    "DGS10",
    "DGS30",
    "DGS3MO",
    "DFEDTARL",
    "DFEDTARU",
    "CPIAUCSL",
    "CPILFESL",
    "PCEPILFE",
    "T5YIE",
    "T10YIE",
    "DFII5",
    "DFII10",
    "DTWEXBGS",
    "DEXUSEU",
    "DEXJPUS",
    "VIXCLS",
    "VXNCLS",
    "RVXCLS",
    "OVXCLS",
    "GVZCLS",
    "NFCI",
)
LEAKAGE_COLS = {
    "id",
    "ts",
    "snapshot_ts",
    "stop_variant_id",       # row identity from ag_fib_stop_variants — not a feature
    "outcome_label",
    "highest_tp_hit",
    "hit_tp1",
    "hit_tp2",
    "hit_tp3",
    "hit_tp4",
    "hit_tp5",
    "tp1_before_sl",
    "mae_pts",
    "mfe_pts",
    "bars_to_tp1",
    "bars_to_sl",
    "session_date_ct",
    "hour_ts",
    # stop_family_id, stop_level_price, stop_distance_ticks, sl_dist_pts,
    # sl_dist_atr, rr_to_tp1 are admitted features — do NOT add them here.
}
TUNING_ONLY_PREFIXES = (
    "ml_exh_",
    "ml_cont_",
)
TUNING_ONLY_EXACT_COLS = {
    "ml_reversal_warning_in_trade",
}
TUNING_ONLY_NAME_TOKENS = (
    "diamond",
    "exhaustion",
)


@dataclass
class FoldSpec:
    fold_code: str
    train_start: str
    train_end: str
    val_start: str
    val_end: str
    test_start: str
    test_end: str
    train_sessions: list[str]
    val_sessions: list[str]
    test_sessions: list[str]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Train a contract-safe AutoGluon baseline from local warbird ag_training."
    )
    parser.add_argument("--dsn", default=DEFAULT_DSN, help="PostgreSQL DSN for local warbird.")
    parser.add_argument("--output-root", default=DEFAULT_OUTPUT_ROOT, help="Artifact root.")
    parser.add_argument("--label", default="outcome_label", help="Target column.")
    parser.add_argument(
        "--start-date",
        default=None,
        help="Optional inclusive America/Chicago session-date floor (YYYY-MM-DD).",
    )
    parser.add_argument(
        "--end-date",
        default=None,
        help="Optional inclusive America/Chicago session-date ceiling (YYYY-MM-DD).",
    )
    parser.add_argument("--eval-metric", default="f1_macro", help="AutoGluon evaluation metric.")
    parser.add_argument("--presets", default="best_quality", help="AutoGluon preset.")
    parser.add_argument("--time-limit", type=int, default=DEFAULT_TIME_LIMIT_SEC, help="Per-fold fit limit in seconds.")
    parser.add_argument(
        "--label-count-threshold",
        type=int,
        default=1,
        help="Minimum training rows required to keep a class in AutoGluon.",
    )
    parser.add_argument("--num-bag-folds", type=int, default=0, help="AutoGluon bagging folds.")
    parser.add_argument("--num-stack-levels", type=int, default=0, help="AutoGluon stack depth.")
    parser.add_argument(
        "--dynamic-stacking",
        choices=("off", "auto"),
        default="off",
        help="Dynamic stacking mode.",
    )
    parser.add_argument(
        "--allow-unsafe-internal-ensembling",
        action="store_true",
        help=(
            "Allow AutoGluon internal IID bagging/stacking. Unsafe for the default "
            "MES walk-forward harness unless you have an explicitly approved purged child splitter."
        ),
    )
    parser.add_argument(
        "--excluded-model-types",
        default="",
        help="Comma-separated AutoGluon model types to exclude. Empty string means none.",
    )
    parser.add_argument("--n-folds", type=int, default=5, help="Number of walk-forward folds.")
    parser.add_argument(
        "--min-train-sessions",
        type=int,
        default=252,
        help="Minimum train sessions before the first validation slice.",
    )
    parser.add_argument("--val-sessions", type=int, default=63, help="Validation window size.")
    parser.add_argument("--test-sessions", type=int, default=63, help="Test window size.")
    parser.add_argument("--session-embargo", type=int, default=1, help="Embargo between slices.")
    parser.add_argument("--no-macro", action="store_true", help="Disable FRED/econ joins.")
    parser.add_argument(
        "--allow-single-class-eval",
        action="store_true",
        help="Allow validation/test slices with fewer than 2 target classes.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Build the full dataset/fold manifest without fitting AutoGluon.",
    )
    return parser.parse_args()


def validate_ensemble_args(args: argparse.Namespace) -> None:
    if args.num_bag_folds < 0:
        raise SystemExit("--num-bag-folds must be >= 0.")
    if args.num_stack_levels < 0:
        raise SystemExit("--num-stack-levels must be >= 0.")
    if args.num_stack_levels > 0 and args.num_bag_folds == 0:
        raise SystemExit(
            "--num-stack-levels > 0 requires --num-bag-folds > 0. "
            "For the default time-series harness, keep both at 0."
        )
    if args.dynamic_stacking == "auto" and args.num_bag_folds == 0:
        raise SystemExit(
            "--dynamic-stacking auto requires internal bagging. "
            "Use --dynamic-stacking off for the default time-series-safe path."
        )

    unsafe_internal_ensembling = (
        args.num_bag_folds > 0
        or args.num_stack_levels > 0
        or args.dynamic_stacking == "auto"
    )
    if unsafe_internal_ensembling and not args.allow_unsafe_internal_ensembling:
        raise SystemExit(
            "AutoGluon internal IID bagging/stacking is disabled by default for MES time-series runs "
            "because it violates the outer walk-forward embargo. Keep --num-bag-folds 0, "
            "--num-stack-levels 0, and --dynamic-stacking off unless you have an explicitly approved "
            "purged temporal child splitter."
        )


def fetch_df(
    conn: psycopg2.extensions.connection,
    sql: str,
    params: tuple[Any, ...] | list[Any] | None = None,
) -> pd.DataFrame:
    return pd.read_sql_query(sql, conn, params=params)


def load_base_training(conn: psycopg2.extensions.connection) -> pd.DataFrame:
    df = fetch_df(conn, "SELECT * FROM ag_training ORDER BY ts ASC")
    # Data-floor guard — refuses to train on a truncated / half-loaded surface.
    # See EXPECTED_AG_TRAINING_ROWS_FLOOR at the top of this file. Lift the
    # floor (with evidence) whenever the pipeline legitimately grows the row
    # count; never lower it silently.
    if len(df) < EXPECTED_AG_TRAINING_ROWS_FLOOR:
        raise SystemExit(
            f"ag_training row count {len(df):,} < floor "
            f"{EXPECTED_AG_TRAINING_ROWS_FLOOR:,}. Pipeline did not load the "
            f"full surface — refusing to train on a truncated dataset. "
            f"Re-run scripts/ag/build_ag_pipeline.py and verify counts in "
            f"the training-pre-audit skill before relaunching."
        )
    if df.empty:
        raise SystemExit("ag_training is empty.")
    df["ts"] = pd.to_datetime(df["ts"], utc=True)
    return df


def add_time_context(df: pd.DataFrame) -> pd.DataFrame:
    ts_ct = df["ts"].dt.tz_convert(CHICAGO_TZ)
    session_date_ct = ts_ct.dt.tz_localize(None).dt.normalize()
    df = df.copy()
    df["session_date_ct"] = session_date_ct
    df["hour_ts"] = df["ts"].dt.floor("H")
    df["hour_ct"] = ts_ct.dt.hour.astype("int16")
    df["minute_ct"] = ts_ct.dt.minute.astype("int16")
    df["dow_ct"] = ts_ct.dt.dayofweek.astype("int16")
    df["month_ct"] = ts_ct.dt.month.astype("int16")
    df["is_rth_ct"] = ((df["hour_ct"] >= 8) & (df["hour_ct"] <= 15)).astype("int8")
    df["is_opening_window_ct"] = (
        (df["hour_ct"] == 8) & (df["minute_ct"] >= 30) | ((df["hour_ct"] == 9) & (df["minute_ct"] == 0))
    ).astype("int8")
    df["session_tier_code"] = (
        (df["hour_ct"] >= 8) & (df["hour_ct"] <= 15)
    ).map({True: 1, False: 3}).astype("int8")
    return df


def filter_session_window(df: pd.DataFrame, start_date: str | None, end_date: str | None) -> pd.DataFrame:
    if not start_date and not end_date:
        return df
    if "session_date_ct" not in df.columns:
        raise SystemExit("session_date_ct must exist before filtering the training window.")

    out = df.copy()
    if start_date:
        start_ts = pd.Timestamp(start_date)
        out = out[out["session_date_ct"] >= start_ts]
    if end_date:
        end_ts = pd.Timestamp(end_date)
        out = out[out["session_date_ct"] <= end_ts]
    if out.empty:
        raise SystemExit("Filtered training window is empty.")
    return out


def load_fred_series_ids(conn: psycopg2.extensions.connection) -> list[str]:
    catalog = fetch_df(
        conn,
        """
        SELECT series_id
        FROM economic_series
        WHERE source = 'FRED'
          AND is_active = true
          AND series_id = ANY(%s)
        ORDER BY series_id ASC
        """,
        params=(list(CURATED_FRED_SERIES),),
    )
    series_ids = catalog["series_id"].dropna().astype(str).tolist()
    if not series_ids:
        raise SystemExit("economic_series does not contain the curated active FRED regime set.")
    missing_required = [series_id for series_id in CURATED_FRED_SERIES if series_id not in series_ids]
    if missing_required:
        raise SystemExit(f"economic_series is missing curated FRED series: {', '.join(missing_required)}")
    return series_ids


def load_fred_panel(
    conn: psycopg2.extensions.connection,
    min_date: pd.Timestamp,
    max_date: pd.Timestamp,
    series_ids: list[str],
) -> pd.DataFrame:
    union_sql = "\nUNION ALL\n".join(
        f"SELECT series_id, event_date, value FROM {table}" for table in ECON_TABLES
    )
    econ = fetch_df(conn, union_sql)
    econ = econ[econ["series_id"].isin(series_ids)].copy()
    if econ.empty:
        return pd.DataFrame(columns=["session_date_ct"])

    econ["event_date"] = pd.to_datetime(econ["event_date"])
    econ = econ.sort_values(["series_id", "event_date"])
    calendar = pd.DataFrame({"session_date_ct": pd.date_range(min_date, max_date, freq="D")})

    for series_id in series_ids:
        series_df = econ.loc[econ["series_id"] == series_id, ["event_date", "value"]].drop_duplicates(
            subset=["event_date"], keep="last"
        )
        if series_df.empty:
            calendar[f"fred_{series_id.lower()}"] = pd.NA
            continue
        merged = pd.merge_asof(
            calendar[["session_date_ct"]],
            series_df.sort_values("event_date"),
            left_on="session_date_ct",
            right_on="event_date",
            direction="backward",
        )
        calendar[f"fred_{series_id.lower()}"] = merged["value"]
    return calendar


def high_impact_count(values: pd.Series) -> int:
    return int((values.fillna("").str.lower() == "high").sum())


def load_calendar_features(conn: psycopg2.extensions.connection) -> pd.DataFrame:
    cal = fetch_df(conn, "SELECT event_date, impact_rating, event_type FROM econ_calendar ORDER BY event_date ASC")
    if cal.empty:
        return pd.DataFrame(columns=["session_date_ct"])

    cal["event_date"] = pd.to_datetime(cal["event_date"])
    grouped = cal.groupby("event_date")
    out = grouped.size().rename("econ_event_count_day").to_frame()
    out["econ_high_impact_count_day"] = grouped["impact_rating"].apply(high_impact_count)
    for event_type in ("rates", "rate_decision", "employment", "inflation"):
        out[f"econ_{event_type}_count_day"] = grouped["event_type"].apply(lambda s: int((s == event_type).sum()))
    out = out.reset_index().rename(columns={"event_date": "session_date_ct"})
    out["econ_has_event_day"] = (out["econ_event_count_day"] > 0).astype("int8")
    return out


def attach_context_features(
    conn: psycopg2.extensions.connection,
    base: pd.DataFrame,
    use_macro: bool,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    df = add_time_context(base)
    coverage: dict[str, Any] = {
        "training_zoo_scope": "MES_1m_15m_1h_4h + SP500 + curated_FRED + econ_calendar",
        "cross_asset_enabled": False,
        "macro_enabled": use_macro,
    }

    if use_macro:
        min_date = df["session_date_ct"].min()
        max_date = df["session_date_ct"].max()
        fred_series_ids = load_fred_series_ids(conn)
        fred = load_fred_panel(conn, min_date=min_date, max_date=max_date, series_ids=fred_series_ids)
        calendar = load_calendar_features(conn)
        df = df.merge(fred, on="session_date_ct", how="left")
        df = df.merge(calendar, on="session_date_ct", how="left")
        fred_cols = [col for col in df.columns if col.startswith("fred_")]
        econ_cols = [col for col in df.columns if col.startswith("econ_")]
        coverage["fred_series_profile"] = "curated_regime_v1"
        coverage["fred_series_admitted"] = len(fred_series_ids)
        coverage["sp500_series_present"] = "SP500" in fred_series_ids
        coverage["fred_feature_columns"] = len(fred_cols)
        coverage["fred_rows_with_any_value"] = int(df[fred_cols].notna().any(axis=1).sum()) if fred_cols else 0
        coverage["calendar_feature_columns"] = len(econ_cols)
        coverage["calendar_rows_with_events"] = int(df["econ_has_event_day"].fillna(0).astype(int).sum()) if "econ_has_event_day" in df.columns else 0

    return df, coverage


def label_distribution(values: pd.Series) -> dict[str, int]:
    counts = Counter(str(v) for v in values)
    return dict(sorted(counts.items(), key=lambda item: (-item[1], item[0])))


def build_session_label_map(df: pd.DataFrame, label: str) -> dict[pd.Timestamp, set[str]]:
    session_label_map: dict[pd.Timestamp, set[str]] = {}
    for session, labels in df.groupby("session_date_ct")[label]:
        session_label_map[session] = {str(value) for value in labels.dropna().tolist()}
    return session_label_map


def accuracy_score(y_true: list[str], y_pred: list[str]) -> float:
    if not y_true:
        return 0.0
    return sum(1 for truth, pred in zip(y_true, y_pred, strict=True) if truth == pred) / len(y_true)


def macro_f1_score(y_true: list[str], y_pred: list[str], labels: list[str]) -> float:
    if not y_true:
        return 0.0
    scores: list[float] = []
    for label in labels:
        tp = sum(1 for truth, pred in zip(y_true, y_pred, strict=True) if truth == label and pred == label)
        fp = sum(1 for truth, pred in zip(y_true, y_pred, strict=True) if truth != label and pred == label)
        fn = sum(1 for truth, pred in zip(y_true, y_pred, strict=True) if truth == label and pred != label)
        precision = tp / (tp + fp) if tp + fp else 0.0
        recall = tp / (tp + fn) if tp + fn else 0.0
        scores.append((2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0)
    return sum(scores) / len(scores)


def majority_baseline(train_labels: pd.Series, eval_labels: pd.Series, labels: list[str]) -> dict[str, Any]:
    majority = train_labels.value_counts().idxmax()
    y_true = [str(v) for v in eval_labels.tolist()]
    y_pred = [str(majority)] * len(y_true)
    return {
        "majority_class": str(majority),
        "accuracy": round(accuracy_score(y_true, y_pred), 6),
        "macro_f1": round(macro_f1_score(y_true, y_pred, labels), 6),
        "label_distribution": label_distribution(eval_labels.astype(str)),
    }


def build_walk_forward_folds(
    sessions: list[pd.Timestamp],
    session_label_map: dict[pd.Timestamp, set[str]],
    n_folds: int,
    min_train_sessions: int,
    val_sessions: int,
    test_sessions: int,
    session_embargo: int,
) -> list[FoldSpec]:
    required = min_train_sessions + val_sessions + test_sessions + (session_embargo * 2)
    if len(sessions) < required:
        raise SystemExit(
            f"Need at least {required} sessions for the configured walk-forward plan; found {len(sessions)}."
        )

    def class_count(session_slice: list[pd.Timestamp]) -> int:
        labels: set[str] = set()
        for session in session_slice:
            labels.update(session_label_map.get(session, set()))
        return len(labels)

    max_offset = len(sessions) - required
    step = max(1, max_offset // max(1, n_folds - 1)) if n_folds > 1 else 1
    folds: list[FoldSpec] = []

    for fold_idx in range(n_folds):
        base_train_end_ix = min_train_sessions - 1 + (fold_idx * step)
        base_val_start_ix = base_train_end_ix + 1 + session_embargo
        last_val_start_ix = len(sessions) - (val_sessions + session_embargo + test_sessions)
        if base_val_start_ix > last_val_start_ix:
            break

        chosen_indices: tuple[int, int, int, int, int] | None = None
        for val_start_ix in range(base_val_start_ix, last_val_start_ix + 1):
            train_end_ix = val_start_ix - session_embargo - 1
            if train_end_ix + 1 < min_train_sessions:
                continue
            val_end_ix = val_start_ix + val_sessions - 1
            test_start_ix = val_end_ix + 1 + session_embargo
            test_end_ix = test_start_ix + test_sessions - 1
            if test_end_ix >= len(sessions):
                break

            val_slice = sessions[val_start_ix : val_end_ix + 1]
            test_slice = sessions[test_start_ix : test_end_ix + 1]
            if class_count(val_slice) >= 2 and class_count(test_slice) >= 2:
                chosen_indices = (train_end_ix, val_start_ix, val_end_ix, test_start_ix, test_end_ix)
                break

        if chosen_indices is None:
            train_end_ix = base_train_end_ix
            val_start_ix = train_end_ix + 1 + session_embargo
            val_end_ix = val_start_ix + val_sessions - 1
            test_start_ix = val_end_ix + 1 + session_embargo
            test_end_ix = test_start_ix + test_sessions - 1
            if test_end_ix >= len(sessions):
                break
        else:
            train_end_ix, val_start_ix, val_end_ix, test_start_ix, test_end_ix = chosen_indices

        train_slice = sessions[: train_end_ix + 1]
        val_slice = sessions[val_start_ix : val_end_ix + 1]
        test_slice = sessions[test_start_ix : test_end_ix + 1]
        folds.append(
            FoldSpec(
                fold_code=f"fold_{fold_idx + 1:02d}",
                train_start=train_slice[0].date().isoformat(),
                train_end=train_slice[-1].date().isoformat(),
                val_start=val_slice[0].date().isoformat(),
                val_end=val_slice[-1].date().isoformat(),
                test_start=test_slice[0].date().isoformat(),
                test_end=test_slice[-1].date().isoformat(),
                train_sessions=[session.date().isoformat() for session in train_slice],
                val_sessions=[session.date().isoformat() for session in val_slice],
                test_sessions=[session.date().isoformat() for session in test_slice],
            )
        )

    if not folds:
        raise SystemExit("No valid walk-forward folds were produced.")
    return folds


def coerce_feature_frame(df: pd.DataFrame, label: str) -> tuple[pd.DataFrame, list[str], dict[str, Any]]:
    out = df.copy()
    bool_cols = out.select_dtypes(include=["bool"]).columns.tolist()
    for col in bool_cols:
        out[col] = out[col].astype("int8")

    tuning_only_cols = [
        col
        for col in out.columns
        if col.startswith(TUNING_ONLY_PREFIXES)
        or col in TUNING_ONLY_EXACT_COLS
        or any(token in col for token in TUNING_ONLY_NAME_TOKENS)
    ]
    leakage_or_identity_cols = [col for col in out.columns if col in LEAKAGE_COLS or col == label]
    drop_cols = sorted(set(leakage_or_identity_cols + tuning_only_cols))
    feature_cols = [col for col in out.columns if col not in drop_cols]

    constant_cols: list[str] = []
    for col in feature_cols:
        if out[col].nunique(dropna=False) <= 1:
            constant_cols.append(col)
    feature_cols = [col for col in feature_cols if col not in constant_cols]

    manifest = {
        "label": label,
        "feature_count": len(feature_cols),
        "dropped_leakage_or_identity": sorted(leakage_or_identity_cols),
        "dropped_tuning_only_columns": sorted(tuning_only_cols),
        "dropped_constant_columns": sorted(constant_cols),
        "feature_groups": {
            "core": len([col for col in feature_cols if not col.startswith(("fred_", "econ_"))]),
            "fred": len([col for col in feature_cols if col.startswith("fred_")]),
            "calendar": len([col for col in feature_cols if col.startswith("econ_")]),
        },
    }
    return out, feature_cols, manifest


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, default=str, sort_keys=True) + "\n")


def current_git_commit_sha() -> str | None:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    sha = result.stdout.strip()
    return sha or None


def normalize_artifact_path(path: Path) -> str:
    resolved = path.resolve()
    cwd = Path.cwd().resolve()
    try:
        return str(resolved.relative_to(cwd))
    except ValueError:
        return str(resolved)


def artifact_file_size(path: Path) -> int | None:
    return int(path.stat().st_size) if path.exists() and path.is_file() else None


def upsert_training_run(
    conn: psycopg2.extensions.connection,
    *,
    run_id: str,
    run_status: str,
    dry_run: bool,
    args: argparse.Namespace,
    dataset_summary: dict[str, Any],
    feature_manifest: dict[str, Any],
    started_at: datetime,
    completed_at: datetime | None,
    git_commit_sha: str | None,
    error_message: str | None,
) -> None:
    coverage = dataset_summary.get("coverage", {})
    session_window = dataset_summary.get("session_window", {})
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO ag_training_runs (
              run_id,
              run_status,
              dry_run,
              problem_type,
              label_name,
              eval_metric,
              presets,
              time_limit_sec,
              num_bag_folds,
              num_stack_levels,
              dynamic_stacking_mode,
              excluded_model_types_json,
              training_zoo_scope,
              start_date_ct,
              end_date_ct,
              actual_start_date_ct,
              actual_end_date_ct,
              rows_total,
              sessions_total,
              feature_count,
              fold_count,
              coverage_json,
              feature_manifest_json,
              command_json,
              git_commit_sha,
              error_message,
              started_at,
              completed_at
            ) VALUES (
              %(run_id)s,
              %(run_status)s,
              %(dry_run)s,
              'multiclass',
              %(label_name)s,
              %(eval_metric)s,
              %(presets)s,
              %(time_limit_sec)s,
              %(num_bag_folds)s,
              %(num_stack_levels)s,
              %(dynamic_stacking_mode)s,
              %(excluded_model_types_json)s,
              %(training_zoo_scope)s,
              %(start_date_ct)s,
              %(end_date_ct)s,
              %(actual_start_date_ct)s,
              %(actual_end_date_ct)s,
              %(rows_total)s,
              %(sessions_total)s,
              %(feature_count)s,
              %(fold_count)s,
              %(coverage_json)s,
              %(feature_manifest_json)s,
              %(command_json)s,
              %(git_commit_sha)s,
              %(error_message)s,
              %(started_at)s,
              %(completed_at)s
            )
            ON CONFLICT (run_id) DO UPDATE SET
              run_status = EXCLUDED.run_status,
              dry_run = EXCLUDED.dry_run,
              problem_type = EXCLUDED.problem_type,
              label_name = EXCLUDED.label_name,
              eval_metric = EXCLUDED.eval_metric,
              presets = EXCLUDED.presets,
              time_limit_sec = EXCLUDED.time_limit_sec,
              num_bag_folds = EXCLUDED.num_bag_folds,
              num_stack_levels = EXCLUDED.num_stack_levels,
              dynamic_stacking_mode = EXCLUDED.dynamic_stacking_mode,
              excluded_model_types_json = EXCLUDED.excluded_model_types_json,
              training_zoo_scope = EXCLUDED.training_zoo_scope,
              start_date_ct = EXCLUDED.start_date_ct,
              end_date_ct = EXCLUDED.end_date_ct,
              actual_start_date_ct = EXCLUDED.actual_start_date_ct,
              actual_end_date_ct = EXCLUDED.actual_end_date_ct,
              rows_total = EXCLUDED.rows_total,
              sessions_total = EXCLUDED.sessions_total,
              feature_count = EXCLUDED.feature_count,
              fold_count = EXCLUDED.fold_count,
              coverage_json = EXCLUDED.coverage_json,
              feature_manifest_json = EXCLUDED.feature_manifest_json,
              command_json = EXCLUDED.command_json,
              git_commit_sha = EXCLUDED.git_commit_sha,
              error_message = EXCLUDED.error_message,
              started_at = EXCLUDED.started_at,
              completed_at = EXCLUDED.completed_at
            """,
            {
                "run_id": run_id,
                "run_status": run_status,
                "dry_run": dry_run,
                "label_name": args.label,
                "eval_metric": args.eval_metric,
                "presets": args.presets,
                "time_limit_sec": args.time_limit,
                "num_bag_folds": args.num_bag_folds,
                "num_stack_levels": args.num_stack_levels,
                "dynamic_stacking_mode": args.dynamic_stacking,
                "excluded_model_types_json": Json(
                    [item.strip() for item in args.excluded_model_types.split(",") if item.strip()]
                ),
                "training_zoo_scope": coverage.get("training_zoo_scope"),
                "start_date_ct": session_window.get("start_date"),
                "end_date_ct": session_window.get("end_date"),
                "actual_start_date_ct": session_window.get("actual_start_date"),
                "actual_end_date_ct": session_window.get("actual_end_date"),
                "rows_total": dataset_summary.get("rows_total"),
                "sessions_total": dataset_summary.get("sessions_total"),
                "feature_count": feature_manifest.get("feature_count"),
                "fold_count": None,
                "coverage_json": Json(coverage),
                "feature_manifest_json": Json(feature_manifest),
                "command_json": Json(
                    {
                        "argv": sys.argv,
                        "args": vars(args),
                    }
                ),
                "git_commit_sha": git_commit_sha,
                "error_message": error_message,
                "started_at": started_at,
                "completed_at": completed_at,
            },
        )


def update_training_run_fold_count(
    conn: psycopg2.extensions.connection,
    *,
    run_id: str,
    fold_count: int,
) -> None:
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE ag_training_runs SET fold_count = %s WHERE run_id = %s",
            (fold_count, run_id),
        )


def replace_run_metrics(
    conn: psycopg2.extensions.connection,
    *,
    run_id: str,
    target_name: str,
    fold_summaries: list[dict[str, Any]],
) -> None:
    with conn.cursor() as cur:
        cur.execute("DELETE FROM ag_training_run_metrics WHERE run_id = %s", (run_id,))
        rows: list[tuple[Any, ...]] = []
        for fold in fold_summaries:
            fold_code = fold["fold_code"]
            row_counts = {
                "train": fold["train_rows"],
                "val": fold["val_rows"],
                "test": fold["test_rows"],
            }
            class_counts = {
                "train": fold["train_class_count"],
                "val": fold["val_class_count"],
                "test": fold["test_class_count"],
            }
            for split_code in ("val", "test"):
                baseline = fold["majority_baseline"][split_code]
                rows.append(
                    (
                        run_id,
                        target_name,
                        fold_code,
                        split_code,
                        "BASELINE",
                        "accuracy",
                        baseline["accuracy"],
                        row_counts[split_code],
                        class_counts[split_code],
                        baseline["majority_class"],
                    )
                )
                rows.append(
                    (
                        run_id,
                        target_name,
                        fold_code,
                        split_code,
                        "BASELINE",
                        "macro_f1",
                        baseline["macro_f1"],
                        row_counts[split_code],
                        class_counts[split_code],
                        baseline["majority_class"],
                    )
                )
            autogluon = fold.get("autogluon")
            if autogluon:
                rows.append(
                    (
                        run_id,
                        target_name,
                        fold_code,
                        "test",
                        "AUTOGLUON",
                        "accuracy",
                        autogluon["test_accuracy"],
                        row_counts["test"],
                        class_counts["test"],
                        autogluon.get("best_model"),
                    )
                )
                rows.append(
                    (
                        run_id,
                        target_name,
                        fold_code,
                        "test",
                        "AUTOGLUON",
                        "macro_f1",
                        autogluon["test_macro_f1"],
                        row_counts["test"],
                        class_counts["test"],
                        autogluon.get("best_model"),
                    )
                )
        if rows:
            cur.executemany(
                """
                INSERT INTO ag_training_run_metrics (
                  run_id,
                  target_name,
                  fold_code,
                  split_code,
                  metric_scope,
                  metric_name,
                  metric_value,
                  row_count,
                  class_count,
                  model_name
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                rows,
            )


def replace_artifacts(
    conn: psycopg2.extensions.connection,
    *,
    run_id: str,
    artifacts: list[dict[str, Any]],
) -> None:
    with conn.cursor() as cur:
        cur.execute("DELETE FROM ag_artifacts WHERE run_id = %s", (run_id,))
        rows = [
            (
                run_id,
                artifact["artifact_type"],
                artifact.get("target_name"),
                artifact.get("fold_code"),
                artifact.get("split_code"),
                artifact["artifact_path"],
                artifact.get("media_type"),
                artifact.get("file_size_bytes"),
                artifact.get("sha256"),
            )
            for artifact in artifacts
        ]
        if rows:
            cur.executemany(
                """
                INSERT INTO ag_artifacts (
                  run_id,
                  artifact_type,
                  target_name,
                  fold_code,
                  split_code,
                  artifact_path,
                  media_type,
                  file_size_bytes,
                  sha256
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                rows,
            )


def collect_run_artifacts(run_dir: Path, *, target_name: str, fold_summaries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    artifacts: list[dict[str, Any]] = []

    def add_artifact(
        path: Path,
        artifact_type: str,
        *,
        fold_code: str | None = None,
        split_code: str | None = None,
        media_type: str | None = None,
    ) -> None:
        if not path.exists():
            return
        artifacts.append(
            {
                "artifact_type": artifact_type,
                "target_name": target_name,
                "fold_code": fold_code,
                "split_code": split_code,
                "artifact_path": normalize_artifact_path(path),
                "media_type": media_type,
                "file_size_bytes": artifact_file_size(path),
                "sha256": None,
            }
        )

    add_artifact(run_dir / "dataset_summary.json", "DATASET_SUMMARY", media_type="application/json")
    add_artifact(run_dir / "feature_manifest.json", "FEATURE_MANIFEST", media_type="application/json")
    add_artifact(run_dir / "training_summary.json", "TRAINING_SUMMARY", media_type="application/json")

    for fold in fold_summaries:
        fold_code = fold["fold_code"]
        fold_dir = run_dir / fold_code
        add_artifact(fold_dir / "fold_summary.json", "FOLD_SUMMARY", fold_code=fold_code, media_type="application/json")
        autogluon = fold.get("autogluon")
        if autogluon:
            leaderboard_path = Path(autogluon["leaderboard_path"])
            add_artifact(
                leaderboard_path,
                "LEADERBOARD",
                fold_code=fold_code,
                split_code="test",
                media_type="text/csv",
            )
            add_artifact(
                fold_dir / "predictor",
                "PREDICTOR_DIR",
                fold_code=fold_code,
            )
    return artifacts


def load_tabular_predictor() -> Any:
    try:
        from autogluon.tabular import TabularPredictor
    except ModuleNotFoundError as exc:
        raise SystemExit(
            "autogluon.tabular is not installed in the active Python environment. "
            "Install scripts/requirements.txt before running non-dry training."
        ) from exc
    return TabularPredictor


def fit_fold(
    run_dir: Path,
    fold: FoldSpec,
    df: pd.DataFrame,
    feature_cols: list[str],
    args: argparse.Namespace,
) -> dict[str, Any]:
    train_df = df[df["session_date_ct"].isin(pd.to_datetime(fold.train_sessions))].copy()
    val_df = df[df["session_date_ct"].isin(pd.to_datetime(fold.val_sessions))].copy()
    test_df = df[df["session_date_ct"].isin(pd.to_datetime(fold.test_sessions))].copy()
    labels = sorted(str(v) for v in df[args.label].dropna().unique())

    fold_dir = run_dir / fold.fold_code
    fold_dir.mkdir(parents=True, exist_ok=True)
    baseline = {
        "val": majority_baseline(train_df[args.label], val_df[args.label], labels),
        "test": majority_baseline(train_df[args.label], test_df[args.label], labels),
    }

    summary: dict[str, Any] = {
        **asdict(fold),
        "train_rows": int(len(train_df)),
        "val_rows": int(len(val_df)),
        "test_rows": int(len(test_df)),
        "train_labels": label_distribution(train_df[args.label].astype(str)),
        "val_labels": label_distribution(val_df[args.label].astype(str)),
        "test_labels": label_distribution(test_df[args.label].astype(str)),
        "train_class_count": int(train_df[args.label].nunique()),
        "val_class_count": int(val_df[args.label].nunique()),
        "test_class_count": int(test_df[args.label].nunique()),
        "majority_baseline": baseline,
        "feature_count": len(feature_cols),
    }
    if summary["val_class_count"] < 2 or summary["test_class_count"] < 2:
        summary["class_warning"] = "Validation or test slice has fewer than 2 classes."

    if summary.get("class_warning") and not args.allow_single_class_eval:
        summary["blocked_training"] = True
        write_json(fold_dir / "fold_summary.json", summary)
        return summary

    if args.dry_run:
        write_json(fold_dir / "fold_summary.json", summary)
        return summary

    TabularPredictor = load_tabular_predictor()
    predictor = TabularPredictor(
        label=args.label,
        problem_type="multiclass",
        eval_metric=args.eval_metric,
        path=str(fold_dir / "predictor"),
        verbosity=2,
        log_to_file=True,
        learner_kwargs={"label_count_threshold": args.label_count_threshold},
    )

    excluded_model_types = [item.strip() for item in args.excluded_model_types.split(",") if item.strip()]
    fit_kwargs: dict[str, Any] = {
        "train_data": train_df[feature_cols + [args.label]],
        "tuning_data": val_df[feature_cols + [args.label]],
        "presets": args.presets,
        "time_limit": args.time_limit,
        "num_gpus": 0,
        # Keep the corrected harness simple: no internal IID bagging, no
        # stacking, no weighted ensemble, one clean temporal tuning set, and a
        # bounded LightGBM-only run.
        "fit_weighted_ensemble": False,
        "fit_full_last_level_weighted_ensemble": False,
        # Canonical full zoo — defined at module top, validated at import.
        # Edit CANONICAL_ZOO there, not here. See the Canonical Training
        # Contract block near the top of this file.
        "hyperparameters": CANONICAL_ZOO,
    }
    if args.num_bag_folds is not None:
        fit_kwargs["num_bag_folds"] = args.num_bag_folds
    if args.num_bag_folds and args.num_bag_folds > 0:
        fit_kwargs["ag_args_ensemble"] = {"fold_fitting_strategy": "sequential_local"}
        fit_kwargs["use_bag_holdout"] = True
    if args.num_stack_levels is not None:
        fit_kwargs["num_stack_levels"] = args.num_stack_levels
    if args.dynamic_stacking == "auto":
        fit_kwargs["dynamic_stacking"] = "auto"
    else:
        fit_kwargs["dynamic_stacking"] = False
    if excluded_model_types:
        fit_kwargs["excluded_model_types"] = excluded_model_types

    predictor.fit(**fit_kwargs)
    leaderboard = predictor.leaderboard(test_df[feature_cols + [args.label]], silent=True)
    leaderboard_path = fold_dir / "leaderboard.csv"
    leaderboard.to_csv(leaderboard_path, index=False)

    test_pred = predictor.predict(test_df[feature_cols])
    y_true = [str(v) for v in test_df[args.label].tolist()]
    y_pred = [str(v) for v in test_pred.tolist()]
    summary["autogluon"] = {
        "leaderboard_path": str(leaderboard_path),
        "best_model": None if leaderboard.empty else str(leaderboard.iloc[0]["model"]),
        "test_accuracy": round(accuracy_score(y_true, y_pred), 6),
        "test_macro_f1": round(macro_f1_score(y_true, y_pred, labels), 6),
        "excluded_model_types": excluded_model_types,
        "presets": args.presets,
        "time_limit": args.time_limit,
        "label_count_threshold": args.label_count_threshold,
        "num_bag_folds": args.num_bag_folds,
        "num_stack_levels": args.num_stack_levels,
        "dynamic_stacking": args.dynamic_stacking,
    }
    write_json(fold_dir / "fold_summary.json", summary)
    return summary


def main() -> None:
    args = parse_args()
    validate_ensemble_args(args)
    run_started_at = datetime.now(UTC)
    run_id = run_started_at.strftime("agtrain_%Y%m%dT%H%M%S%fZ")
    run_dir = (Path(args.output_root) / run_id).resolve()
    git_commit_sha = current_git_commit_sha()

    dataset_summary: dict[str, Any] = {}
    feature_manifest: dict[str, Any] = {}
    fold_summaries: list[dict[str, Any]] = []
    blocked_folds: list[str] = []
    planned_fold_count = 0
    run_status = "RUNNING"
    error_message: str | None = None

    try:
        with psycopg2.connect(args.dsn) as conn:
            base = load_base_training(conn)
            base = add_time_context(base)
            base = filter_session_window(base, args.start_date, args.end_date)
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
            enriched, coverage = attach_context_features(
                conn,
                base=base,
                use_macro=not args.no_macro,
            )

        enriched, feature_cols, feature_manifest = coerce_feature_frame(enriched, label=args.label)
        sessions = sorted(enriched["session_date_ct"].drop_duplicates().tolist())
        session_label_map = build_session_label_map(enriched, args.label)
        folds = build_walk_forward_folds(
            sessions=sessions,
            session_label_map=session_label_map,
            n_folds=args.n_folds,
            min_train_sessions=args.min_train_sessions,
            val_sessions=args.val_sessions,
            test_sessions=args.test_sessions,
            session_embargo=args.session_embargo,
        )
        planned_fold_count = len(folds)

        dataset_summary = {
            "run_id": run_id,
            "created_at_utc": datetime.now(UTC).replace(microsecond=0).isoformat(),
            "rows_total": int(len(enriched)),
            "sessions_total": int(len(sessions)),
            "session_window": {
                "start_date": None if args.start_date is None else args.start_date,
                "end_date": None if args.end_date is None else args.end_date,
                "actual_start_date": sessions[0].date().isoformat(),
                "actual_end_date": sessions[-1].date().isoformat(),
            },
            "label_distribution": label_distribution(enriched[args.label].astype(str)),
            "coverage": coverage,
        }
        write_json(run_dir / "dataset_summary.json", dataset_summary)
        write_json(run_dir / "feature_manifest.json", feature_manifest)

        with psycopg2.connect(args.dsn) as conn:
            upsert_training_run(
                conn,
                run_id=run_id,
                run_status="RUNNING",
                dry_run=bool(args.dry_run),
                args=args,
                dataset_summary=dataset_summary,
                feature_manifest=feature_manifest,
                started_at=run_started_at,
                completed_at=None,
                git_commit_sha=git_commit_sha,
                error_message=None,
            )
            update_training_run_fold_count(conn, run_id=run_id, fold_count=planned_fold_count)

        fold_summaries = [fit_fold(run_dir, fold, enriched, feature_cols, args) for fold in folds]
        training_summary = {
            "run_id": run_id,
            "dry_run": bool(args.dry_run),
            "dataset_summary_path": str(run_dir / "dataset_summary.json"),
            "feature_manifest_path": str(run_dir / "feature_manifest.json"),
            "fold_count": len(fold_summaries),
            "folds": fold_summaries,
        }
        write_json(run_dir / "training_summary.json", training_summary)
        blocked_folds = [fold["fold_code"] for fold in fold_summaries if fold.get("blocked_training")]
        run_status = "BLOCKED" if blocked_folds else "SUCCEEDED"
    except Exception as exc:
        run_status = "FAILED"
        error_message = str(exc)
        raise
    finally:
        if dataset_summary and feature_manifest:
            with psycopg2.connect(args.dsn) as conn:
                upsert_training_run(
                    conn,
                    run_id=run_id,
                    run_status=run_status,
                    dry_run=bool(args.dry_run),
                    args=args,
                    dataset_summary=dataset_summary,
                    feature_manifest=feature_manifest,
                    started_at=run_started_at,
                    completed_at=datetime.now(UTC),
                    git_commit_sha=git_commit_sha,
                    error_message=error_message,
                )
                update_training_run_fold_count(conn, run_id=run_id, fold_count=planned_fold_count)
                replace_run_metrics(
                    conn,
                    run_id=run_id,
                    target_name=args.label,
                    fold_summaries=fold_summaries,
                )
                replace_artifacts(
                    conn,
                    run_id=run_id,
                    artifacts=collect_run_artifacts(
                        run_dir,
                        target_name=args.label,
                        fold_summaries=fold_summaries,
                    ),
                )

    console_summary = {
        "run_id": run_id,
        "dry_run": bool(args.dry_run),
        "dataset_summary_path": str(run_dir / "dataset_summary.json"),
        "feature_manifest_path": str(run_dir / "feature_manifest.json"),
        "fold_count": len(fold_summaries),
        "fold_preview": [
            {
                "fold_code": fold["fold_code"],
                "train_rows": fold["train_rows"],
                "val_rows": fold["val_rows"],
                "test_rows": fold["test_rows"],
                "train_class_count": fold["train_class_count"],
                "val_class_count": fold["val_class_count"],
                "test_class_count": fold["test_class_count"],
                "majority_test_accuracy": fold["majority_baseline"]["test"]["accuracy"],
                "majority_test_macro_f1": fold["majority_baseline"]["test"]["macro_f1"],
                "class_warning": fold.get("class_warning"),
            }
            for fold in fold_summaries
        ],
    }
    if blocked_folds:
        console_summary["blocked_folds"] = blocked_folds
    print(json.dumps(console_summary, indent=2, default=str, sort_keys=True))
    if blocked_folds:
        raise SystemExit(
            "Blocked AutoGluon training because one or more validation/test slices have fewer than 2 classes. "
            "Use --allow-single-class-eval only if you explicitly accept misleading multiclass metrics."
        )


if __name__ == "__main__":
    main()
