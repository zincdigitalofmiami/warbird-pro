#!/usr/bin/env python3
"""
Warbird Model Training Pipeline — AutoGluon Regression

ONE unified MES model. 4 horizons × 3 targets = 12 models.
Walk-forward CV with purge/embargo (Lopez de Prado).
IC ranking + hierarchical cluster dedup per fold.
GJR-GARCH(1,1) + 10K-path Monte Carlo for vol states.

Usage:
    python scripts/train-warbird.py --dataset datasets/mes_unified_1h.csv
    python scripts/train-warbird.py --dataset datasets/mes_unified_1h.csv --horizons 1h,4h
    python scripts/train-warbird.py --dataset datasets/mes_unified_1h.csv --targets price
    python scripts/train-warbird.py --dataset datasets/mes_unified_1h.csv --num-cpus 10
"""

import argparse
import json
import math
import os
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr
from scipy.cluster.hierarchy import linkage, fcluster
from scipy.spatial.distance import squareform

HORIZONS = {
    "1h": 1,
    "4h": 4,
    "1d": 24,
    "1w": 120,
}

TARGET_TYPES = ("price", "mae", "mfe")

# Columns to never use as features
DROP_COLS = {
    "ts", "timestamp", "open", "high", "low", "close", "volume",
}

# Time limits per target type (seconds per fold)
TIME_LIMITS = {
    "price": 14400,  # 4 hours
    "mae": 7200,     # 2 hours
    "mfe": 7200,     # 2 hours
}

MIN_COVERAGE = 0.3  # minimum non-null fraction to keep a feature


@dataclass
class AgConfig:
    presets: str = "best_quality"
    num_bag_folds: int = 5
    num_stack_levels: int = 2
    dynamic_stacking: str = "auto"
    excluded_model_types: list = field(default_factory=lambda: ["KNN", "FASTAI", "RF"])
    early_stopping_rounds: int = 50
    max_memory_ratio: float = 0.8
    fold_fitting_strategy: str = "sequential_local"


# ---------------------------------------------------------------------------
# Walk-forward CV with purge + embargo
# ---------------------------------------------------------------------------

def compute_purge_embargo(horizon_bars: int, feature_max_lookback: int = 50) -> tuple[int, int]:
    """Purge = label overlap + feature lookback. Embargo = 2× purge."""
    label_overlap = max(1, horizon_bars - 1)
    purge = label_overlap + feature_max_lookback
    embargo = purge * 2
    return purge, embargo


def walk_forward_splits(n: int, n_folds: int, purge: int, embargo: int) -> list[tuple[list, list]]:
    """Expanding-window walk-forward CV with purge + embargo gap."""
    fold_size = n // (n_folds + 1)
    splits = []
    for fold in range(n_folds):
        split = fold_size * (fold + 1)
        val_start = split + purge + embargo
        val_end = fold_size * (fold + 2) if fold < n_folds - 1 else n
        if val_start >= val_end or val_start >= n:
            continue
        splits.append((list(range(0, split)), list(range(val_start, val_end))))
    return splits


# ---------------------------------------------------------------------------
# Feature selection: IC ranking + hierarchical cluster dedup
# ---------------------------------------------------------------------------

def rank_features_by_ic(train_df: pd.DataFrame, feature_cols: list[str],
                        target_col: str, top_n: int = 50) -> list[str]:
    """Rank features by absolute Spearman IC on training data."""
    ics = []
    for col in feature_cols:
        vals = train_df[col].dropna()
        if len(vals) < 100:
            ics.append((col, 0.0))
            continue
        shared_idx = vals.index.intersection(train_df[target_col].dropna().index)
        if len(shared_idx) < 100:
            ics.append((col, 0.0))
            continue
        try:
            ic, _ = spearmanr(train_df.loc[shared_idx, col], train_df.loc[shared_idx, target_col])
            ics.append((col, abs(ic) if np.isfinite(ic) else 0.0))
        except Exception:
            ics.append((col, 0.0))
    ics.sort(key=lambda x: -x[1])
    return [col for col, _ in ics[:top_n]]


def cluster_dedup_features(df: pd.DataFrame, feature_cols: list[str],
                           target_col: str, threshold: float = 0.85) -> list[str]:
    """Hierarchical clustering: group correlated features, keep best IC per cluster."""
    numeric = [c for c in feature_cols if df[c].dtype in (np.float64, np.float32, np.int64, float, int)]
    if len(numeric) < 2:
        return feature_cols

    # IC for cluster representative selection
    ics = {}
    for col in numeric:
        valid = df[[col, target_col]].dropna()
        if len(valid) < 100:
            ics[col] = 0.0
            continue
        try:
            ic, _ = spearmanr(valid[col], valid[target_col])
            ics[col] = abs(ic) if np.isfinite(ic) else 0.0
        except Exception:
            ics[col] = 0.0

    # Distance matrix
    corr = df[numeric].corr(method="spearman").abs().values
    np.fill_diagonal(corr, 1.0)
    dist = 1 - corr
    dist = np.clip(dist, 0, 2)
    condensed = squareform(dist, checks=False)

    # Hierarchical clustering (average linkage)
    Z = linkage(condensed, method="average")
    clusters = fcluster(Z, t=(1 - threshold), criterion="distance")

    # Pick best per cluster: highest IC, then lowest missingness
    selected = set()
    for cid in set(clusters):
        members = [numeric[i] for i in range(len(numeric)) if clusters[i] == cid]
        best = max(members, key=lambda c: (ics.get(c, 0), -df[c].isna().sum()))
        selected.add(best)

    return [c for c in feature_cols if c in selected or c not in numeric]


def select_features(train_df: pd.DataFrame, feature_cols: list[str],
                    target_col: str, top_n: int = 50) -> list[str]:
    """Two-stage feature selection: IC ranking → cluster dedup."""
    # Stage 1: IC ranking
    ic_ranked = rank_features_by_ic(train_df, feature_cols, target_col, top_n)
    # Stage 2: cluster dedup
    deduped = cluster_dedup_features(train_df, ic_ranked, target_col, threshold=0.85)
    return deduped


# ---------------------------------------------------------------------------
# GJR-GARCH(1,1) + Monte Carlo
# ---------------------------------------------------------------------------

def fit_garch_sigma(returns: np.ndarray, horizon_bars: int) -> dict:
    """GJR-GARCH(1,1) with t-dist, EWMA fallback."""
    clean = np.asarray(returns, dtype=float)
    clean = clean[np.isfinite(clean)]
    if clean.size < 200:
        sigma = float(np.std(clean)) if clean.size else 0.0
        return {
            "method": "insufficient_data",
            "sigma_1bar": sigma,
            "sigma_horizon": sigma * math.sqrt(max(1, horizon_bars)),
        }
    try:
        from arch import arch_model
        am = arch_model(clean * 100.0, mean="Zero", vol="GARCH", p=1, o=1, q=1, dist="t")
        res = am.fit(disp="off")
        forecast = res.forecast(horizon=1, reindex=False)
        var1 = float(forecast.variance.values[-1, 0]) / (100.0 * 100.0)
        sigma_1 = math.sqrt(max(var1, 1e-12))
        params = res.params.to_dict()
        return {
            "method": "gjr_garch11_t",
            "sigma_1bar": sigma_1,
            "sigma_horizon": sigma_1 * math.sqrt(max(1, horizon_bars)),
            "omega": float(params.get("omega", np.nan)),
            "alpha1": float(params.get("alpha[1]", np.nan)),
            "gamma1": float(params.get("gamma[1]", np.nan)),
            "beta1": float(params.get("beta[1]", np.nan)),
        }
    except Exception:
        lam = 0.94
        var = float(np.var(clean[-500:]))
        for r in clean[-500:]:
            var = lam * var + (1 - lam) * float(r * r)
        sigma_1 = math.sqrt(max(var, 1e-12))
        return {
            "method": "ewma_proxy",
            "sigma_1bar": sigma_1,
            "sigma_horizon": sigma_1 * math.sqrt(max(1, horizon_bars)),
        }


def monte_carlo_summary(
    current_price: float,
    horizon_bars: int,
    drift_total: float,
    sigma_1bar: float,
    n_paths: int = 10_000,
    seed: int = 42,
) -> dict:
    """10,000-path Monte Carlo with quantiles."""
    rng = np.random.default_rng(seed)
    sigma_1bar = max(float(sigma_1bar), 1e-8)
    mu_step = float(drift_total) / max(1, horizon_bars)

    steps = rng.normal(loc=mu_step, scale=sigma_1bar, size=(n_paths, horizon_bars))
    steps = np.clip(steps, -0.99, None)
    total_ret = np.prod(1.0 + steps, axis=1) - 1.0
    end_prices = current_price * (1.0 + total_ret)

    q10, q25, q50, q75, q90 = np.quantile(end_prices, [0.1, 0.25, 0.5, 0.75, 0.9])
    return {
        "mc_q10": float(q10),
        "mc_q25": float(q25),
        "mc_q50": float(q50),
        "mc_q75": float(q75),
        "mc_q90": float(q90),
        "mc_prob_up": float(np.mean(end_prices > current_price)),
        "mc_mean": float(np.mean(end_prices)),
        "mc_std": float(np.std(end_prices)),
    }


# ---------------------------------------------------------------------------
# Training loop
# ---------------------------------------------------------------------------

def train_one(
    df: pd.DataFrame,
    feature_cols: list[str],
    target_col: str,
    horizon_name: str,
    target_type: str,
    output_dir: Path,
    ag: AgConfig,
    num_cpus: int,
    n_folds: int = 5,
):
    """Train one model (1 horizon × 1 target type) with walk-forward CV."""
    from autogluon.tabular import TabularPredictor

    horizon_bars = HORIZONS[horizon_name]
    purge, embargo = compute_purge_embargo(horizon_bars)
    splits = walk_forward_splits(len(df), n_folds, purge, embargo)

    if not splits:
        print(f"    WARNING: not enough data for {n_folds} folds, skipping")
        return

    time_limit = TIME_LIMITS.get(target_type, 7200)
    model_dir = output_dir / f"{horizon_name}_{target_type}"
    model_dir.mkdir(parents=True, exist_ok=True)

    fold_results = []

    for fold_idx, (train_idx, val_idx) in enumerate(splits):
        print(f"    Fold {fold_idx + 1}/{len(splits)} "
              f"(train={len(train_idx):,}, val={len(val_idx):,})")

        train_df = df.iloc[train_idx].copy()
        val_df = df.iloc[val_idx].copy()

        # Drop rows where target is NaN
        train_df = train_df.dropna(subset=[target_col])
        val_df = val_df.dropna(subset=[target_col])

        if len(train_df) < 500 or len(val_df) < 100:
            print(f"      Skipping fold: insufficient data")
            continue

        # Feature selection (per-fold, on training data only)
        selected = select_features(train_df, feature_cols, target_col, top_n=50)
        if not selected:
            print(f"      Skipping fold: no features selected")
            continue

        print(f"      Features selected: {len(selected)}")

        # Prepare data
        train_subset = train_df[selected + [target_col]].copy()
        val_subset = val_df[selected + [target_col]].copy()

        # Replace infinities
        for subset in [train_subset, val_subset]:
            num_cols = subset.select_dtypes(include=[np.number]).columns
            subset[num_cols] = subset[num_cols].replace([np.inf, -np.inf], np.nan)

        fold_dir = model_dir / f"fold_{fold_idx}"
        t0 = time.time()

        predictor = TabularPredictor(
            label=target_col,
            path=str(fold_dir),
            problem_type="regression",
            eval_metric="mean_absolute_error",
        )

        predictor.fit(
            train_data=train_subset,
            tuning_data=val_subset,
            time_limit=time_limit,
            presets=ag.presets,
            num_gpus=0,
            num_bag_folds=ag.num_bag_folds,
            num_stack_levels=ag.num_stack_levels,
            dynamic_stacking=ag.dynamic_stacking,
            excluded_model_types=ag.excluded_model_types,
            ag_args_fit={
                "num_early_stopping_rounds": ag.early_stopping_rounds,
                "ag.max_memory_usage_ratio": ag.max_memory_ratio,
                "num_cpus": num_cpus,
            },
            ag_args_ensemble={
                "fold_fitting_strategy": ag.fold_fitting_strategy,
            },
        )

        elapsed = time.time() - t0

        # Evaluate
        perf = predictor.evaluate(val_subset)
        leaderboard = predictor.leaderboard(val_subset, silent=True)

        fold_result = {
            "fold": fold_idx,
            "train_rows": len(train_subset),
            "val_rows": len(val_subset),
            "features": selected,
            "n_features": len(selected),
            "performance": perf,
            "best_model": leaderboard.iloc[0]["model"] if len(leaderboard) > 0 else None,
            "elapsed_s": round(elapsed, 1),
        }
        fold_results.append(fold_result)

        # Save fold metadata
        with open(fold_dir / "fold_meta.json", "w") as f:
            json.dump(fold_result, f, indent=2, default=str)

        print(f"      MAE: {perf.get('mean_absolute_error', 'N/A')} | "
              f"Time: {elapsed:.0f}s | "
              f"Best: {fold_result['best_model']}")

    # Save model summary
    summary = {
        "horizon": horizon_name,
        "target_type": target_type,
        "target_col": target_col,
        "n_folds_completed": len(fold_results),
        "folds": fold_results,
    }
    with open(model_dir / "model_summary.json", "w") as f:
        json.dump(summary, f, indent=2, default=str)

    print(f"    Completed: {len(fold_results)} folds trained")
    return summary


def main():
    parser = argparse.ArgumentParser(description="Train Warbird models")
    parser.add_argument("--dataset", type=str, required=True, help="Path to CSV dataset")
    parser.add_argument("--output", type=str, default="models/warbird", help="Output directory")
    parser.add_argument("--horizons", type=str, default="1h,4h,1d,1w", help="Comma-separated horizons")
    parser.add_argument("--targets", type=str, default="price,mae,mfe", help="Comma-separated target types")
    parser.add_argument("--num-cpus", type=int, default=10, help="CPUs for AutoGluon")
    parser.add_argument("--n-folds", type=int, default=5, help="Number of CV folds")
    args = parser.parse_args()

    horizons = [h.strip() for h in args.horizons.split(",")]
    targets = [t.strip() for t in args.targets.split(",")]
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 60)
    print("WARBIRD MODEL TRAINING")
    print("=" * 60)
    print(f"Dataset: {args.dataset}")
    print(f"Horizons: {horizons}")
    print(f"Targets: {targets}")
    print(f"Folds: {args.n_folds}")
    print(f"CPUs: {args.num_cpus}")
    print(f"Output: {output_dir}")
    print()

    # Load dataset
    print("Loading dataset...", end=" ", flush=True)
    df = pd.read_csv(args.dataset)
    df = df.sort_values("timestamp").reset_index(drop=True)
    print(f"{len(df):,} rows, {len(df.columns)} columns")

    # Identify feature columns
    target_cols = {c for c in df.columns if c.startswith("target_")}
    feature_cols = [c for c in df.columns if c not in DROP_COLS and c not in target_cols]

    # Drop sparse features globally
    sparse = [c for c in feature_cols if df[c].notna().mean() < MIN_COVERAGE]
    feature_cols = [c for c in feature_cols if c not in set(sparse)]
    print(f"Features: {len(feature_cols)} (dropped {len(sparse)} sparse)")

    # Replace infinities
    num_cols = df[feature_cols].select_dtypes(include=[np.number]).columns.tolist()
    df[num_cols] = df[num_cols].replace([np.inf, -np.inf], np.nan)

    # GARCH vol state (computed once)
    if "returns_1h" in df.columns:
        print("\nFitting GJR-GARCH(1,1)...", end=" ", flush=True)
        returns = df["returns_1h"].dropna().to_numpy()
        for h_name, h_bars in HORIZONS.items():
            if h_name in horizons:
                garch = fit_garch_sigma(returns, h_bars)
                print(f"\n  {h_name}: method={garch['method']}, "
                      f"σ_1bar={garch['sigma_1bar']:.6f}, "
                      f"σ_horizon={garch['sigma_horizon']:.6f}")

                # Save GARCH params
                garch_path = output_dir / f"garch_{h_name}.json"
                with open(garch_path, "w") as f:
                    json.dump(garch, f, indent=2)

    # Train models
    total_models = len(horizons) * len(targets)
    model_idx = 0

    for h_name in horizons:
        for target_type in targets:
            model_idx += 1
            target_col = f"target_{target_type}_{h_name}"

            if target_col not in df.columns:
                print(f"\n[{model_idx}/{total_models}] SKIP {h_name}/{target_type}: "
                      f"column {target_col} not found")
                continue

            valid_count = df[target_col].notna().sum()
            if valid_count < 1000:
                print(f"\n[{model_idx}/{total_models}] SKIP {h_name}/{target_type}: "
                      f"only {valid_count} valid targets")
                continue

            print(f"\n{'=' * 60}")
            print(f"[{model_idx}/{total_models}] Training {h_name} / {target_type}")
            print(f"  Target: {target_col} ({valid_count:,} valid rows)")
            print(f"  Time limit: {TIME_LIMITS.get(target_type, 7200)}s per fold")
            print(f"{'=' * 60}")

            train_one(
                df=df,
                feature_cols=feature_cols,
                target_col=target_col,
                horizon_name=h_name,
                target_type=target_type,
                output_dir=output_dir,
                ag=AgConfig(),
                num_cpus=args.num_cpus,
                n_folds=args.n_folds,
            )

    # Monte Carlo summary (using last price + GARCH)
    if "close" in df.columns:
        current_price = float(df["close"].iloc[-1])
        print(f"\n{'=' * 60}")
        print(f"Monte Carlo Simulation (price={current_price:.2f})")
        print(f"{'=' * 60}")

        for h_name in horizons:
            h_bars = HORIZONS[h_name]
            garch_path = output_dir / f"garch_{h_name}.json"
            if garch_path.exists():
                with open(garch_path) as f:
                    garch = json.load(f)
                drift = float(df["returns_1h"].mean() * h_bars) if "returns_1h" in df.columns else 0.0
                mc = monte_carlo_summary(current_price, h_bars, drift, garch["sigma_1bar"])
                print(f"\n  {h_name}: Q10={mc['mc_q10']:.2f} | Q50={mc['mc_q50']:.2f} | "
                      f"Q90={mc['mc_q90']:.2f} | P(up)={mc['mc_prob_up']:.1%}")

                mc_path = output_dir / f"mc_{h_name}.json"
                with open(mc_path, "w") as f:
                    json.dump(mc, f, indent=2)

    print(f"\n{'=' * 60}")
    print("TRAINING COMPLETE")
    print(f"Models saved to: {output_dir}")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
