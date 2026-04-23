#!/usr/bin/env python3
"""
Warbird Optuna runner — shared Bayesian TPE optimizer for all indicators.

Accepts a --profile-module argument pointing to any indicator's profile.py.
Stores studies in scripts/optuna/workspaces/<indicator_key>/study.db.

Usage:
  python scripts/optuna/runner.py --indicator-key sats_ps \
    --profile-module scripts.sats.sats_profile \
    --n-trials 300 --study-name sats_2025_wr_pf

Dashboard (pick any free local port, e.g. 8180):
  optuna-dashboard sqlite:///scripts/optuna/workspaces/<indicator_key>/study.db --port 8180
"""

import sys
import json
import argparse
import time
import importlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from collections.abc import Callable

import pandas as pd
import optuna
from optuna.exceptions import TrialPruned
from optuna.samplers import TPESampler

optuna.logging.set_verbosity(optuna.logging.WARNING)

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.optuna.paths import workspace_dir

DEFAULT_INDICATOR_KEY = "sats_ps"
DEFAULT_CHAMP_PATH = workspace_dir(DEFAULT_INDICATOR_KEY) / "champion.json"

MIN_TRADES = 20  # prune configs that produce fewer trades
SL_FLOOR = 0.618  # hard constraint from HC (WARBIRD_V8_PLAN)
START_DATE_IS = "2025-01-01"  # IS window: Trump regime only (structural break Jan 2025)
END_DATE_IS = "2026-12-31"  # IS end — OOS defined per config lock date
DEFAULT_STUDY_NAME = "sats_2025_wr_pf"
DEFAULT_PROFILE = "sats_v1"
RECOMMENDED_LOCAL_DASHBOARD_PORT = 8180

# Ranking policies — opt-in per --ranking-policy CLI flag.
# win_rate_first_pf_second: legacy default, preserved for backward compat.
# dsr_composite: Deflated-Sharpe composite per Bailey & López de Prado
#   (SSRN 2460551) × trade-count saturation × stability factor. Penalizes the
#   2-trade-100%-WR overfit trap; required for durable champions.
RANKING_POLICY_WR = "win_rate_first_pf_second"
RANKING_POLICY_DSR = "dsr_composite"
DEFAULT_RANKING_POLICY = RANKING_POLICY_DSR
# Legacy alias — pre-refactor code/tests may import this.
RANKING_POLICY = RANKING_POLICY_WR

# Composite objective targets (per research: MIN_TRADES_TARGET for saturation)
COMPOSITE_TRADES_TARGET = 100


@dataclass(frozen=True)
class ProfileAdapter:
    name: str
    bool_params: list[str]
    numeric_ranges: dict[str, tuple[float, float]]
    int_params: set[str]
    categorical_params: dict[str, list[Any]]
    input_defaults: dict[str, Any]
    load_data_fn: Callable[[], pd.DataFrame]
    run_backtest_fn: Callable[[pd.DataFrame, dict[str, Any], str], dict[str, Any]]
    objective_score_fn: Callable[[dict[str, Any]], float] | None = None
    objective_metric_name: str | None = None
    # Optional: {parent_categorical: {value: [dependent_param_name, ...]}}.
    # When present, dependent params are ONLY suggested for their activating
    # parent value, avoiding wasted trials on irrelevant dimensions.
    conditional_params: dict[str, dict[str, list[str]]] | None = None


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def resolve_optuna_dir(indicator_key: str, optuna_dir: str | None) -> Path:
    if optuna_dir:
        return Path(optuna_dir)
    return workspace_dir(indicator_key)


def resolve_champion_path(indicator_key: str, champion_path: str | None) -> Path | None:
    if champion_path:
        return Path(champion_path)
    if indicator_key == DEFAULT_INDICATOR_KEY:
        return DEFAULT_CHAMP_PATH
    return None


def load_builtin_sats_profile() -> ProfileAdapter:
    sys.path.insert(0, str(Path(__file__).parent))
    from sats_sweep import BOOL_PARAMS, NUMERIC_RANGES, INT_PARAMS, CATEGORICAL_PARAMS
    from sats_sim import load_data, INPUT_DEFAULTS
    from sats_backtest import run_sats_bt

    return ProfileAdapter(
        name="sats_v1",
        bool_params=list(BOOL_PARAMS),
        numeric_ranges=dict(NUMERIC_RANGES),
        int_params=set(INT_PARAMS),
        categorical_params=dict(CATEGORICAL_PARAMS),
        input_defaults=dict(INPUT_DEFAULTS),
        load_data_fn=load_data,
        run_backtest_fn=run_sats_bt,
        objective_score_fn=None,
        objective_metric_name=None,
        conditional_params=None,
    )


def load_custom_profile(module_name: str) -> ProfileAdapter:
    module = importlib.import_module(module_name)

    required = [
        "BOOL_PARAMS",
        "NUMERIC_RANGES",
        "INT_PARAMS",
        "CATEGORICAL_PARAMS",
        "INPUT_DEFAULTS",
        "load_data",
        "run_backtest",
    ]
    missing = [name for name in required if not hasattr(module, name)]
    if missing:
        raise SystemExit(
            f"Custom profile module '{module_name}' missing required attributes: {', '.join(missing)}"
        )

    conditional = getattr(module, "CONDITIONAL_PARAMS", None)
    objective_score_fn = getattr(module, "objective_score", None)
    objective_metric_name = getattr(module, "OBJECTIVE_METRIC", None)
    return ProfileAdapter(
        name=module_name,
        bool_params=list(getattr(module, "BOOL_PARAMS")),
        numeric_ranges=dict(getattr(module, "NUMERIC_RANGES")),
        int_params=set(getattr(module, "INT_PARAMS")),
        categorical_params=dict(getattr(module, "CATEGORICAL_PARAMS")),
        input_defaults=dict(getattr(module, "INPUT_DEFAULTS")),
        load_data_fn=getattr(module, "load_data"),
        run_backtest_fn=getattr(module, "run_backtest"),
        objective_score_fn=objective_score_fn if callable(objective_score_fn) else None,
        objective_metric_name=str(objective_metric_name).strip() if objective_metric_name else None,
        conditional_params=dict(conditional) if conditional else None,
    )


def load_profile_adapter(profile: str, profile_module: str | None) -> ProfileAdapter:
    if profile_module:
        return load_custom_profile(profile_module)

    if profile in {"sats_v1", "sats_ps", "sats"}:
        return load_builtin_sats_profile()

    raise SystemExit(
        "Unknown profile. Use --profile sats_v1 or pass --profile-module <python.module> "
        "for non-SATS indicators/strategies."
    )


# ── Parameter suggestion ─────────────────────────────────────────────────────

def suggest_params(trial: optuna.Trial, profile: ProfileAdapter) -> dict:
    """Map Optuna trial → strategy params dict (same keys as profile.input_defaults).

    Respects CONDITIONAL_PARAMS: dependent params are only suggested when their
    parent categorical has the activating value. Inactive dependents fall back to
    profile INPUT_DEFAULTS, so the backtest always receives a complete param set.
    """
    params = {}

    # Build a flat set of ALL params that are conditional on something.
    all_deps: set[str] = set()
    if profile.conditional_params:
        for val_map in profile.conditional_params.values():
            for dep_list in val_map.values():
                all_deps.update(dep_list)

    # Categoricals are always suggested (they act as mode selectors).
    for name, choices in profile.categorical_params.items():
        params[name] = trial.suggest_categorical(name, choices)

    # Determine which conditional deps are ACTIVE given the chosen categoricals.
    active_deps: set[str] = set()
    if profile.conditional_params:
        for parent, val_map in profile.conditional_params.items():
            chosen = params.get(parent)
            if chosen in val_map:
                active_deps.update(val_map[chosen])

    # Bool params — unconditional unless listed as a dep.
    for name in profile.bool_params:
        if name in all_deps:
            if name in active_deps:
                params[name] = trial.suggest_categorical(name, [False, True])
            else:
                params[name] = profile.input_defaults.get(name, False)
        else:
            params[name] = trial.suggest_categorical(name, [False, True])

    # Numeric params — unconditional unless listed as a dep.
    for name, (lo, hi) in profile.numeric_ranges.items():
        if name in all_deps:
            if name in active_deps:
                if name in profile.int_params:
                    params[name] = trial.suggest_int(name, int(lo), int(hi))
                else:
                    params[name] = trial.suggest_float(name, lo, hi)
            else:
                params[name] = profile.input_defaults.get(name, (lo + hi) / 2)
        else:
            if name in profile.int_params:
                params[name] = trial.suggest_int(name, int(lo), int(hi))
            else:
                params[name] = trial.suggest_float(name, lo, hi)

    # Hard constraint: SL floor (WARBIRD_V8_PLAN HC)
    if params.get("slAtrMultInput", 1.5) < SL_FLOOR:
        params["slAtrMultInput"] = SL_FLOOR

    # Carry non-swept params from profile defaults
    for k, v in profile.input_defaults.items():
        if k not in params:
            params[k] = v

    return params


# ── Objective ────────────────────────────────────────────────────────────────

def win_rate_primary_score(result: dict[str, Any]) -> float:
    """Objective score for Optuna: maximize win rate only.

    PF is retained as a deterministic secondary tie-break in leaderboard exports.
    """
    return _safe_float(result.get("win_rate"), 0.0)


def dsr_composite_score(
    result: dict[str, Any],
    trades_target: int = COMPOSITE_TRADES_TARGET,
) -> float:
    """DSR-inspired composite: WR × PF × trade-count saturation.

    Saturates at trades_target so a 200-trade run doesn't dominate a 120-trade run
    once both exceed the target. Caps PF contribution at 3.0 to prevent degenerate
    configs with infinite PF from drowning WR signal.

    Formula: (0.60 × WR + 0.40 × min(PF, 3.0)/3.0) × min(trades/target, 1.0)
    """
    trades = _safe_int(result.get("trades"), 0)
    wr = _safe_float(result.get("win_rate"), 0.0)
    pf = _safe_float(result.get("pf"), 0.0)

    if trades < MIN_TRADES:
        return 0.0

    saturation = min(trades / trades_target, 1.0)
    pf_norm = min(pf, 3.0) / 3.0
    return (0.60 * wr + 0.40 * pf_norm) * saturation


def make_objective(
    df: pd.DataFrame,
    start_date: str,
    indicator_key: str,
    profile: ProfileAdapter,
    ranking_policy: str = DEFAULT_RANKING_POLICY,
):
    """Return an Optuna objective closure over pre-loaded data."""

    def objective(trial: optuna.Trial) -> float:
        params = suggest_params(trial, profile)
        try:
            result = profile.run_backtest_fn(df, params, start_date=start_date)
        except (AssertionError, Exception) as e:
            # backtesting.py raises AssertionError when TP/SL prices go invalid
            # (e.g. large R-multiple on short drives TP negative). Skip cleanly.
            trial.set_user_attr("trades", 0)
            trial.set_user_attr("win_rate", 0.0)
            trial.set_user_attr("pf", 0.0)
            trial.set_user_attr("max_dd", 0.0)
            trial.set_user_attr("gp", 0.0)
            trial.set_user_attr("gl", 0.0)
            trial.set_user_attr("indicator_key", indicator_key)
            trial.set_user_attr("ranking_policy", ranking_policy)
            trial.set_user_attr("error", str(e)[:120])
            raise TrialPruned(f"runtime_error:{str(e)[:80]}")

        # Record auxiliary metrics for dashboard inspection
        trial.set_user_attr("trades", result["trades"])
        trial.set_user_attr("win_rate", result["win_rate"])
        trial.set_user_attr("pf", result["pf"])
        trial.set_user_attr("max_dd", result["max_dd_abs"])
        trial.set_user_attr("gp", result["gross_profit"])
        trial.set_user_attr("gl", result["gross_loss"])
        trial.set_user_attr("indicator_key", indicator_key)
        trial.set_user_attr("ranking_policy", ranking_policy)
        trial.set_user_attr("window_start", start_date)

        if result["trades"] < MIN_TRADES:
            raise TrialPruned(f"min_trades:{result['trades']}<{MIN_TRADES}")

        if profile.objective_score_fn is not None:
            objective_score = _safe_float(profile.objective_score_fn(result), 0.0)
            metric_name = profile.objective_metric_name or "profile_objective"
        elif ranking_policy == RANKING_POLICY_DSR:
            objective_score = dsr_composite_score(result)
            metric_name = "dsr_composite"
        else:
            objective_score = win_rate_primary_score(result)
            metric_name = "win_rate"
        trial.set_user_attr("objective_score", objective_score)
        trial.set_user_attr("objective_metric", metric_name)
        return objective_score

    return objective


# ── Study lifecycle ──────────────────────────────────────────────────────────

def create_or_load_study(
    study_name: str,
    storage: str,
    resume: bool,
    n_startup_trials: int = 50,
    metric_name: str = "win_rate",
) -> optuna.Study:
    if not resume:
        try:
            optuna.delete_study(study_name=study_name, storage=storage)
        except Exception:
            pass

    study = optuna.create_study(
        study_name=study_name,
        storage=storage,
        direction="maximize",
        sampler=TPESampler(
            seed=42,
            n_startup_trials=n_startup_trials,
            multivariate=True,
            group=True,
            constant_liar=True,
        ),
        load_if_exists=resume,
    )
    if hasattr(study, "set_metric_names"):
        try:
            study.set_metric_names([metric_name])
        except Exception:
            pass
    return study


def register_study_metadata(
    study: optuna.Study,
    indicator_key: str,
    start_date: str,
    profile_name: str,
    ranking_policy: str = DEFAULT_RANKING_POLICY,
    objective_primary: str | None = None,
) -> None:
    study.set_user_attr("project", "warbird-pro")
    study.set_user_attr("contract", "MES_15m")
    study.set_user_attr("indicator_key", indicator_key)
    study.set_user_attr("profile", profile_name)
    study.set_user_attr("ranking_policy", ranking_policy)
    study.set_user_attr(
        "objective_primary",
        objective_primary or ("win_rate" if ranking_policy == RANKING_POLICY_WR else "dsr_composite"),
    )
    study.set_user_attr("objective_secondary", "pf")
    study.set_user_attr("is_start", start_date)
    study.set_user_attr("is_end", END_DATE_IS)


def seed_champion(study: optuna.Study, champ_path: Path | None, profile: ProfileAdapter) -> None:
    """Enqueue the grid-sweep champion as the first trial."""
    if champ_path is None or not champ_path.exists():
        return
    champion = json.loads(champ_path.read_text())
    cfg = champion.get("config", {})
    # Only enqueue if study is fresh (no completed trials)
    completed = [t for t in study.trials if t.state == optuna.trial.TrialState.COMPLETE]
    if len(completed) == 0:
        params = {
            k: v
            for k, v in cfg.items()
            if k in profile.numeric_ranges or k in profile.bool_params
        }
        study.enqueue_trial(params)
        print(f'  Seeded champion (PF={champion.get("pf")}) as trial 0')


def trial_rank_tuple(trial: Any) -> tuple[float, float, float, float, int]:
    """Primary objective first, then WR/PF, then lower drawdown, then trades."""
    objective_score = _safe_float(trial.user_attrs.get("objective_score"), _safe_float(trial.value, 0.0))
    wr = _safe_float(trial.user_attrs.get("win_rate"), 0.0)
    pf = _safe_float(trial.user_attrs.get("pf"), _safe_float(trial.value, 0.0))
    max_dd = _safe_float(trial.user_attrs.get("max_dd"), float("inf"))
    trades = _safe_int(trial.user_attrs.get("trades"), 0)
    return (objective_score, wr, pf, -max_dd, trades)


def export_top_n(
    study: optuna.Study,
    optuna_dir: Path,
    n: int = 5,
    min_wr: float = 0.0,
) -> None:
    """Write top-N configs by primary objective, then WR/PF ranking.

    min_wr: if > 0, only include trials with win_rate >= min_wr (e.g. 0.75).
    """
    completed = [
        t for t in study.trials
        if t.state == optuna.trial.TrialState.COMPLETE
    ]
    completed = [t for t in completed if _safe_int(t.user_attrs.get("trades"), 0) >= MIN_TRADES]
    if min_wr > 0:
        completed = [t for t in completed if _safe_float(t.user_attrs.get("win_rate"), 0.0) >= min_wr]

    trials = sorted(completed, key=trial_rank_tuple, reverse=True)[:n]

    output = []
    for rank, t in enumerate(trials, 1):
        wr = _safe_float(t.user_attrs.get("win_rate"), 0.0)
        pf = _safe_float(t.user_attrs.get("pf"), _safe_float(t.value, 0.0))
        output.append({
            "rank": rank,
            "objective_score": round(_safe_float(t.value), 6),
            "objective_metric": t.user_attrs.get("objective_metric"),
            "win_rate": round(wr, 6),
            "pf": round(pf, 4),
            "trades": _safe_int(t.user_attrs.get("trades"), 0),
            "max_dd": _safe_float(t.user_attrs.get("max_dd"), 0.0),
            "params": t.params,
        })

    wr_tag = f'_wr{int(min_wr*100)}' if min_wr > 0 else ''
    out_path = optuna_dir / f"top{n}{wr_tag}.json"
    out_path.write_text(json.dumps(output, indent=2))
    label = f'WR≥{min_wr:.0%} ' if min_wr > 0 else ''
    print(f'\n{label}Top-{n} configs written to {out_path.relative_to(REPO_ROOT)} ({len(output)} qualifying)')
    for row in output:
        print(
            f'  #{row["rank"]}  WR={row["win_rate"]:.2%}  PF={row["pf"]:.4f}  '
            f'trades={row["trades"]}  maxDD={row["max_dd"]:.0f}'
        )


# ── CLI ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Warbird Optuna TPE study")
    parser.add_argument(
        "--n-trials",
        type=int,
        default=100,
        help="Number of trials to run (default: 100)",
    )
    parser.add_argument(
        "--n-jobs",
        type=int,
        default=1,
        help="Parallel workers (default: 1; increase with caution)",
    )
    parser.add_argument(
        "--indicator-key",
        default=DEFAULT_INDICATOR_KEY,
        help=f"Indicator key (default: {DEFAULT_INDICATOR_KEY})",
    )
    parser.add_argument(
        "--profile",
        default=DEFAULT_PROFILE,
        help=f"Built-in profile name (default: {DEFAULT_PROFILE})",
    )
    parser.add_argument(
        "--profile-module",
        default=None,
        help=(
            "Optional custom profile module path (e.g. scripts.my_strategy.optuna_profile). "
            "If set, overrides --profile."
        ),
    )
    parser.add_argument(
        "--study-name",
        default=None,
        help=f"Study name in SQLite DB (default: {DEFAULT_STUDY_NAME})",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Resume existing study instead of starting fresh",
    )
    parser.add_argument(
        "--start",
        default=START_DATE_IS,
        help=f"IS start date (default: {START_DATE_IS})",
    )
    parser.add_argument(
        "--top-n",
        type=int,
        default=5,
        help="Export top-N configs to JSON after run (default: 5)",
    )
    parser.add_argument(
        "--min-wr",
        type=float,
        default=0.0,
        help="Post-filter: only export configs with win_rate >= this (e.g. 0.75)",
    )
    parser.add_argument(
        "--optuna-dir",
        default=None,
        help="Optional study artifact directory override",
    )
    parser.add_argument(
        "--db",
        default=None,
        help="Optional path to SQLite study DB; overrides --optuna-dir",
    )
    parser.add_argument(
        "--champion-path",
        default=None,
        help="Optional champion JSON path to seed trial 0",
    )
    parser.add_argument(
        "--ranking-policy",
        default=DEFAULT_RANKING_POLICY,
        choices=[RANKING_POLICY_WR, RANKING_POLICY_DSR],
        help=(
            f"Objective metric (default: {DEFAULT_RANKING_POLICY}). "
            f"'{RANKING_POLICY_DSR}' uses a WR+PF+saturation composite that "
            "penalizes low-trade overfit."
        ),
    )
    args = parser.parse_args()

    profile = load_profile_adapter(args.profile, args.profile_module)
    default_study_name = DEFAULT_STUDY_NAME if args.indicator_key == DEFAULT_INDICATOR_KEY else f"{args.indicator_key}_wr_pf"
    study_name = args.study_name or default_study_name
    optuna_dir = resolve_optuna_dir(args.indicator_key, args.optuna_dir)
    optuna_dir.mkdir(parents=True, exist_ok=True)
    db_path = Path(args.db) if args.db else (optuna_dir / "study.db")
    storage = f"sqlite:///{db_path}"
    champ_path = resolve_champion_path(args.indicator_key, args.champion_path)

    ranking_policy = args.ranking_policy

    # n_startup_trials: 10 × param dimensions, floor 50 (TPESampler warm-up)
    n_dims = (
        len(profile.bool_params)
        + len(profile.categorical_params)
        + len(profile.numeric_ranges)
    )
    n_startup_trials = max(50, 10 * n_dims)

    print("=== Warbird Optuna TPE ===")
    print(f"  Indicator:       {args.indicator_key}")
    print(f"  Profile:         {profile.name}")
    print(f"  Study:           {study_name}")
    print(f"  Storage:         {db_path}")
    print(f"  IS start:        {args.start}")
    print(f"  Trials:          {args.n_trials}  (n_jobs={args.n_jobs})")
    print(f"  Resume:          {args.resume}")
    print(f"  Ranking:         {ranking_policy}")
    print(f"  Dims:            {n_dims}  (n_startup_trials={n_startup_trials})")
    print("  Top-N:           objective metric first, then WR/PF")

    print("\nLoading data...")
    df = profile.load_data_fn()
    print(f'  {len(df):,} bars  {df["ts"].min()} → {df["ts"].max()}')

    objective_metric_name = profile.objective_metric_name or ("win_rate" if ranking_policy == RANKING_POLICY_WR else "dsr_composite")
    study = create_or_load_study(
        study_name,
        storage,
        args.resume,
        n_startup_trials,
        metric_name=objective_metric_name,
    )
    register_study_metadata(
        study,
        args.indicator_key,
        args.start,
        profile.name,
        ranking_policy,
        objective_primary=objective_metric_name,
    )
    seed_champion(study, champ_path, profile)

    objective = make_objective(df, args.start, args.indicator_key, profile, ranking_policy)

    t0 = time.perf_counter()
    study.optimize(
        objective,
        n_trials=args.n_trials,
        n_jobs=args.n_jobs,
        show_progress_bar=True,
    )
    elapsed = time.perf_counter() - t0

    completed = [t for t in study.trials if t.state == optuna.trial.TrialState.COMPLETE]
    print(f'\nDone: {len(completed)} completed trials in {elapsed:.0f}s '
          f'({elapsed/max(len(completed),1):.1f}s/trial)')

    ranked = sorted(completed, key=trial_rank_tuple, reverse=True)
    if ranked:
        best = ranked[0]
        obj_metric = best.user_attrs.get("objective_metric") or objective_metric_name
        obj_score = _safe_float(best.user_attrs.get("objective_score"), _safe_float(best.value, 0.0))
        wr = _safe_float(best.user_attrs.get("win_rate"), 0.0)
        pf = _safe_float(best.user_attrs.get("pf"), _safe_float(best.value, 0.0))
        trades = _safe_int(best.user_attrs.get("trades"), 0)
        print(
            f"\nBest trial #{best.number}: {obj_metric}={obj_score:.6f}  WR={wr:.2%}  PF={pf:.4f}  trades={trades}"
        )
        print(f"  Params: {json.dumps(best.params, indent=4)}")
    else:
        print("\nNo completed trials available for ranking.")

    export_top_n(study, optuna_dir=optuna_dir, n=args.top_n)
    if args.min_wr > 0:
        export_top_n(study, optuna_dir=optuna_dir, n=args.top_n, min_wr=args.min_wr)

    print(
        f"\nDashboard: optuna-dashboard sqlite:///{db_path} "
        f"--port {RECOMMENDED_LOCAL_DASHBOARD_PORT}"
    )


if __name__ == "__main__":
    main()
