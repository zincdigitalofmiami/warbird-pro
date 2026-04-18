#!/usr/bin/env python3
"""
SATS Optuna study — Bayesian TPE search over the SATS v1.9.0 parameter space.

Replaces the 6-stage grid sweep (sats_sweep.py) with Optuna TPE, seeded from
the champion config (PF=1.1748). Stores the study in an SQLite DB for
resume-safe runs and optuna-dashboard visualization.

Usage:
  python scripts/sats/sats_optuna.py --n-trials 300 --study-name sats_v1
  python scripts/sats/sats_optuna.py --n-trials 100 --study-name sats_v1 --resume

Study DB: data/sats_ps_optuna/study.db
Dashboard: optuna-dashboard sqlite:///data/sats_ps_optuna/study.db --port 8080
"""

import sys
import json
import argparse
import time
from pathlib import Path

import numpy as np
import pandas as pd
import optuna
from optuna.samplers import TPESampler

optuna.logging.set_verbosity(optuna.logging.WARNING)

REPO_ROOT  = Path(__file__).parents[2]
OPTUNA_DIR = REPO_ROOT / 'data' / 'sats_ps_optuna'
CHAMP_PATH = REPO_ROOT / 'data' / 'sats_ps_sweep' / 'champion.json'

sys.path.insert(0, str(Path(__file__).parent))
from sats_sweep import BOOL_PARAMS, NUMERIC_RANGES, INT_PARAMS
from sats_sim   import load_data, INPUT_DEFAULTS
from sats_backtest import run_sats_bt

MIN_TRADES    = 20    # prune configs that produce fewer trades
SL_FLOOR      = 0.618 # hard constraint from HC (WARBIRD_V8_PLAN)
START_DATE_IS = '2020-01-01'   # in-sample start (IS window)
END_DATE_IS   = '2023-12-31'   # IS end — OOS untouched until config lock


# ── Parameter suggestion ─────────────────────────────────────────────────────

def suggest_params(trial: optuna.Trial) -> dict:
    """Map Optuna trial → SATS params dict (same keys as INPUT_DEFAULTS)."""
    params = {}

    for name in BOOL_PARAMS:
        params[name] = trial.suggest_categorical(name, [False, True])

    for name, (lo, hi) in NUMERIC_RANGES.items():
        if name in INT_PARAMS:
            params[name] = trial.suggest_int(name, int(lo), int(hi))
        else:
            params[name] = trial.suggest_float(name, lo, hi)

    # Hard constraint: SL floor (WARBIRD_V8_PLAN HC)
    if params.get('slAtrMultInput', 1.5) < SL_FLOOR:
        params['slAtrMultInput'] = SL_FLOOR

    # Carry non-swept params from INPUT_DEFAULTS
    for k, v in INPUT_DEFAULTS.items():
        if k not in params:
            params[k] = v

    return params


# ── Objective ────────────────────────────────────────────────────────────────

def make_objective(df: pd.DataFrame, start_date: str):
    """Return an Optuna objective closure over pre-loaded data."""

    def objective(trial: optuna.Trial) -> float:
        params = suggest_params(trial)
        result = run_sats_bt(df, params, start_date=start_date)

        # Record auxiliary metrics for dashboard inspection
        trial.set_user_attr('trades',   result['trades'])
        trial.set_user_attr('win_rate', result['win_rate'])
        trial.set_user_attr('max_dd',   result['max_dd_abs'])
        trial.set_user_attr('gp',       result['gross_profit'])
        trial.set_user_attr('gl',       result['gross_loss'])

        if result['trades'] < MIN_TRADES:
            # Return a low value instead of pruning (backtesting.py runs to completion)
            return 0.0

        return result['pf']

    return objective


# ── Study lifecycle ──────────────────────────────────────────────────────────

def create_or_load_study(study_name: str, storage: str, resume: bool) -> optuna.Study:
    if not resume:
        try:
            optuna.delete_study(study_name=study_name, storage=storage)
        except Exception:
            pass

    study = optuna.create_study(
        study_name=study_name,
        storage=storage,
        direction='maximize',
        sampler=TPESampler(seed=42, n_startup_trials=25, multivariate=True),
        load_if_exists=resume,
    )
    return study


def seed_champion(study: optuna.Study) -> None:
    """Enqueue the grid-sweep champion as the first trial."""
    if not CHAMP_PATH.exists():
        return
    champion = json.loads(CHAMP_PATH.read_text())
    cfg = champion.get('config', {})
    # Only enqueue if study is fresh (no completed trials)
    completed = [t for t in study.trials if t.state == optuna.trial.TrialState.COMPLETE]
    if len(completed) == 0:
        params = {k: v for k, v in cfg.items() if k in NUMERIC_RANGES or k in BOOL_PARAMS}
        study.enqueue_trial(params)
        print(f'  Seeded champion (PF={champion.get("pf")}) as trial 0')


def export_top_n(study: optuna.Study, n: int = 5) -> None:
    """Write top-N configs to data/sats_ps_optuna/top{n}.json."""
    trials = sorted(
        [t for t in study.trials if t.state == optuna.trial.TrialState.COMPLETE and t.value],
        key=lambda t: t.value or 0.0,
        reverse=True,
    )[:n]

    output = []
    for rank, t in enumerate(trials, 1):
        output.append({
            'rank': rank,
            'pf': round(t.value or 0.0, 4),
            'trades': t.user_attrs.get('trades'),
            'win_rate': t.user_attrs.get('win_rate'),
            'max_dd': t.user_attrs.get('max_dd'),
            'params': t.params,
        })

    out_path = OPTUNA_DIR / f'top{n}.json'
    out_path.write_text(json.dumps(output, indent=2))
    print(f'\nTop-{n} configs written to {out_path.relative_to(REPO_ROOT)}')
    for row in output:
        print(f'  #{row["rank"]}  PF={row["pf"]:.4f}  trades={row["trades"]}  '
              f'WR={row["win_rate"]:.2%}  maxDD={row["max_dd"]:.0f}')


# ── CLI ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description='SATS Optuna TPE study')
    parser.add_argument('--n-trials',   type=int, default=100,
                        help='Number of trials to run (default: 100)')
    parser.add_argument('--n-jobs',     type=int, default=1,
                        help='Parallel workers (default: 1; increase with caution)')
    parser.add_argument('--study-name', default='sats_v1',
                        help='Study name in the SQLite DB (default: sats_v1)')
    parser.add_argument('--resume',     action='store_true',
                        help='Resume existing study instead of starting fresh')
    parser.add_argument('--start',      default=START_DATE_IS,
                        help=f'IS start date (default: {START_DATE_IS})')
    parser.add_argument('--top-n',      type=int, default=5,
                        help='Export top-N configs to JSON after run (default: 5)')
    parser.add_argument('--db',         default=str(OPTUNA_DIR / 'study.db'),
                        help='Path to SQLite study DB')
    args = parser.parse_args()

    OPTUNA_DIR.mkdir(parents=True, exist_ok=True)
    storage = f'sqlite:///{args.db}'

    print(f'=== SATS Optuna TPE ===')
    print(f'  Study:    {args.study_name}')
    print(f'  Storage:  {args.db}')
    print(f'  IS start: {args.start}')
    print(f'  Trials:   {args.n_trials}  (n_jobs={args.n_jobs})')
    print(f'  Resume:   {args.resume}')

    print('\nLoading data...')
    df = load_data()
    print(f'  {len(df):,} bars  {df["ts"].min()} → {df["ts"].max()}')

    study = create_or_load_study(args.study_name, storage, args.resume)
    seed_champion(study)

    objective = make_objective(df, args.start)

    t0 = time.perf_counter()
    study.optimize(objective, n_trials=args.n_trials, n_jobs=args.n_jobs,
                   show_progress_bar=True)
    elapsed = time.perf_counter() - t0

    completed = [t for t in study.trials if t.state == optuna.trial.TrialState.COMPLETE]
    print(f'\nDone: {len(completed)} completed trials in {elapsed:.0f}s '
          f'({elapsed/max(len(completed),1):.1f}s/trial)')

    best = study.best_trial
    print(f'\nBest trial #{best.number}:  PF={best.value:.4f}  '
          f'trades={best.user_attrs.get("trades")}')
    print(f'  Params: {json.dumps(best.params, indent=4)}')

    export_top_n(study, n=args.top_n)

    print(f'\nDashboard: optuna-dashboard sqlite:///{args.db} --port 8080')


if __name__ == '__main__':
    main()
