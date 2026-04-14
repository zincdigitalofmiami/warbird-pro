#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd
import psycopg2


CHICAGO_TZ = ZoneInfo("America/Chicago")
DEFAULT_DSN = os.environ.get("WARBIRD_PG_DSN", "host=127.0.0.1 port=5432 dbname=warbird")
DEFAULT_OUTPUT_ROOT = "artifacts/ag_runs"
CROSS_ASSET_SYMBOLS = ("NQ", "RTY", "CL", "HG", "6E", "6J")
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
FRED_SERIES = (
    "DFF",
    "SOFR",
    "T10Y2Y",
    "DGS2",
    "DGS10",
    "DGS30",
    "DGS5",
    "DGS3MO",
    "DFII10",
    "T5YIE",
    "T10YIE",
    "VIXCLS",
    "VXNCLS",
    "GVZCLS",
    "OVXCLS",
    "NFCI",
    "DTWEXBGS",
    "DEXUSEU",
    "DEXJPUS",
    "SP500",
    "NASDAQCOM",
    "DCOILWTICO",
    "DCOILBRENTEU",
)
LEAKAGE_COLS = {
    "id",
    "ts",
    "snapshot_ts",
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
}


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
    parser.add_argument("--eval-metric", default="f1_macro", help="AutoGluon evaluation metric.")
    parser.add_argument("--presets", default="best_quality", help="AutoGluon preset.")
    parser.add_argument("--time-limit", type=int, default=900, help="Per-fold fit limit in seconds.")
    parser.add_argument("--num-bag-folds", type=int, default=5, help="AutoGluon bagging folds.")
    parser.add_argument("--num-stack-levels", type=int, default=2, help="AutoGluon stack depth.")
    parser.add_argument(
        "--dynamic-stacking",
        choices=("off", "auto"),
        default="auto",
        help="Dynamic stacking mode.",
    )
    parser.add_argument(
        "--excluded-model-types",
        default="KNN",
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
    parser.add_argument("--no-cross-asset", action="store_true", help="Disable cross-asset joins.")
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


def fetch_df(conn: psycopg2.extensions.connection, sql: str) -> pd.DataFrame:
    return pd.read_sql_query(sql, conn)


def load_base_training(conn: psycopg2.extensions.connection) -> pd.DataFrame:
    df = fetch_df(conn, "SELECT * FROM ag_training ORDER BY ts ASC")
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


def load_cross_asset_features(conn: psycopg2.extensions.connection) -> pd.DataFrame:
    sql = """
        SELECT symbol, ts, open, high, low, close, volume, open_interest
        FROM cross_asset_1h
        WHERE symbol = ANY(%s)
        ORDER BY symbol ASC, ts ASC
    """
    df = pd.read_sql_query(sql, conn, params=(list(CROSS_ASSET_SYMBOLS),))
    if df.empty:
        return pd.DataFrame(columns=["hour_ts"])

    df["ts"] = pd.to_datetime(df["ts"], utc=True)
    df["bar_ret_pct"] = (df["close"] - df["open"]) / df["open"].replace(0, pd.NA) * 100.0
    df["range_pct"] = (df["high"] - df["low"]) / df["open"].replace(0, pd.NA) * 100.0
    df["close_ret_1h_pct"] = df.groupby("symbol")["close"].pct_change(fill_method=None) * 100.0
    df["oi_change_pct"] = df.groupby("symbol")["open_interest"].pct_change(fill_method=None) * 100.0
    wide = df.pivot_table(
        index="ts",
        columns="symbol",
        values=["bar_ret_pct", "range_pct", "close_ret_1h_pct", "oi_change_pct"],
        aggfunc="last",
    )
    wide.columns = [
        f"xa_{symbol.lower()}_{feature}"
        for feature, symbol in wide.columns.to_flat_index()
    ]
    wide = wide.reset_index().rename(columns={"ts": "hour_ts"})
    return wide


def load_fred_panel(conn: psycopg2.extensions.connection, min_date: pd.Timestamp, max_date: pd.Timestamp) -> pd.DataFrame:
    union_sql = "\nUNION ALL\n".join(
        f"SELECT series_id, event_date, value FROM {table}" for table in ECON_TABLES
    )
    econ = fetch_df(conn, union_sql)
    econ = econ[econ["series_id"].isin(FRED_SERIES)].copy()
    if econ.empty:
        return pd.DataFrame(columns=["session_date_ct"])

    econ["event_date"] = pd.to_datetime(econ["event_date"])
    econ = econ.sort_values(["series_id", "event_date"])
    calendar = pd.DataFrame({"session_date_ct": pd.date_range(min_date, max_date, freq="D")})

    for series_id in FRED_SERIES:
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
    use_cross_asset: bool,
    use_macro: bool,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    df = add_time_context(base)
    coverage: dict[str, Any] = {
        "cross_asset_enabled": use_cross_asset,
        "macro_enabled": use_macro,
    }

    if use_cross_asset:
        cross_asset = load_cross_asset_features(conn)
        df = df.merge(cross_asset, on="hour_ts", how="left")
        xa_cols = [col for col in df.columns if col.startswith("xa_")]
        coverage["cross_asset_feature_columns"] = len(xa_cols)
        coverage["cross_asset_rows_with_all_symbols"] = int(df[xa_cols].notna().all(axis=1).sum()) if xa_cols else 0
        coverage["cross_asset_rows_total"] = int(len(df))

    if use_macro:
        min_date = df["session_date_ct"].min()
        max_date = df["session_date_ct"].max()
        fred = load_fred_panel(conn, min_date=min_date, max_date=max_date)
        calendar = load_calendar_features(conn)
        df = df.merge(fred, on="session_date_ct", how="left")
        df = df.merge(calendar, on="session_date_ct", how="left")
        fred_cols = [col for col in df.columns if col.startswith("fred_")]
        econ_cols = [col for col in df.columns if col.startswith("econ_")]
        coverage["fred_feature_columns"] = len(fred_cols)
        coverage["fred_rows_with_any_value"] = int(df[fred_cols].notna().any(axis=1).sum()) if fred_cols else 0
        coverage["calendar_feature_columns"] = len(econ_cols)
        coverage["calendar_rows_with_events"] = int(df["econ_has_event_day"].fillna(0).astype(int).sum()) if "econ_has_event_day" in df.columns else 0

    return df, coverage


def label_distribution(values: pd.Series) -> dict[str, int]:
    counts = Counter(str(v) for v in values)
    return dict(sorted(counts.items(), key=lambda item: (-item[1], item[0])))


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

    max_offset = len(sessions) - required
    step = max(1, max_offset // max(1, n_folds - 1)) if n_folds > 1 else 1
    folds: list[FoldSpec] = []

    for fold_idx in range(n_folds):
        train_end_ix = min_train_sessions - 1 + (fold_idx * step)
        val_start_ix = train_end_ix + 1 + session_embargo
        val_end_ix = val_start_ix + val_sessions - 1
        test_start_ix = val_end_ix + 1 + session_embargo
        test_end_ix = test_start_ix + test_sessions - 1
        if test_end_ix >= len(sessions):
            break

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

    drop_cols = [col for col in out.columns if col in LEAKAGE_COLS or col == label]
    feature_cols = [col for col in out.columns if col not in drop_cols]

    constant_cols: list[str] = []
    for col in feature_cols:
        if out[col].nunique(dropna=False) <= 1:
            constant_cols.append(col)
    feature_cols = [col for col in feature_cols if col not in constant_cols]

    manifest = {
        "label": label,
        "feature_count": len(feature_cols),
        "dropped_leakage_or_identity": sorted(drop_cols),
        "dropped_constant_columns": sorted(constant_cols),
        "feature_groups": {
            "core": len([col for col in feature_cols if not col.startswith(("xa_", "fred_", "econ_"))]),
            "cross_asset": len([col for col in feature_cols if col.startswith("xa_")]),
            "fred": len([col for col in feature_cols if col.startswith("fred_")]),
            "calendar": len([col for col in feature_cols if col.startswith("econ_")]),
        },
    }
    return out, feature_cols, manifest


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, default=str, sort_keys=True) + "\n")


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
    )

    excluded_model_types = [item.strip() for item in args.excluded_model_types.split(",") if item.strip()]
    fit_kwargs: dict[str, Any] = {
        "train_data": train_df[feature_cols + [args.label]],
        "tuning_data": val_df[feature_cols + [args.label]],
        "presets": args.presets,
        "time_limit": args.time_limit,
        "num_gpus": 0,
        "ag_args_ensemble": {"fold_fitting_strategy": "sequential_local"},
    }
    if args.num_bag_folds is not None:
        fit_kwargs["num_bag_folds"] = args.num_bag_folds
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
        "num_bag_folds": args.num_bag_folds,
        "num_stack_levels": args.num_stack_levels,
        "dynamic_stacking": args.dynamic_stacking,
    }
    write_json(fold_dir / "fold_summary.json", summary)
    return summary


def main() -> None:
    args = parse_args()
    run_id = datetime.now(UTC).strftime("agtrain_%Y%m%dT%H%M%S%fZ")
    run_dir = Path(args.output_root) / run_id

    with psycopg2.connect(args.dsn) as conn:
        base = load_base_training(conn)
        enriched, coverage = attach_context_features(
            conn,
            base=base,
            use_cross_asset=not args.no_cross_asset,
            use_macro=not args.no_macro,
        )

    enriched, feature_cols, feature_manifest = coerce_feature_frame(enriched, label=args.label)
    sessions = sorted(enriched["session_date_ct"].drop_duplicates().tolist())
    folds = build_walk_forward_folds(
        sessions=sessions,
        n_folds=args.n_folds,
        min_train_sessions=args.min_train_sessions,
        val_sessions=args.val_sessions,
        test_sessions=args.test_sessions,
        session_embargo=args.session_embargo,
    )

    dataset_summary = {
        "run_id": run_id,
        "created_at_utc": datetime.now(UTC).replace(microsecond=0).isoformat(),
        "rows_total": int(len(enriched)),
        "sessions_total": int(len(sessions)),
        "label_distribution": label_distribution(enriched[args.label].astype(str)),
        "coverage": coverage,
    }
    write_json(run_dir / "dataset_summary.json", dataset_summary)
    write_json(run_dir / "feature_manifest.json", feature_manifest)

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
