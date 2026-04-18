#!/usr/bin/env python3
"""
SATS parameter sweep — Stages 2-6.

Stage 2: 32 boolean combos (useCharFlip excluded — proven no-op)
Stage 3: OAT numeric sensitivity screen (~114 trials)
Stage 4: Latin-hypercube on dominant knobs (~250 trials)
Stage 5: Fine grid refine around Stage-4 top-3 (~80 trials)
Stage 6: TP-mode Dynamic sub-sweep at Stage-5 winner (~50 trials)

All results appended to data/sats_ps_sweep/all_trials.csv after every trial.
Champion updated in data/sats_ps_sweep/champion.json after every trial.
Resume-safe: skips trials already in CSV by config_tag signature.
"""

import itertools
import json
import time
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from sats_sim import simulate_sats, load_data, CRYPTO_ANCHOR, INPUT_DEFAULTS

REPO_ROOT   = Path(__file__).parents[2]
SWEEP_DIR   = REPO_ROOT / 'data' / 'sats_ps_sweep'
CSV_PATH    = SWEEP_DIR / 'all_trials.csv'
CHAMP_PATH  = SWEEP_DIR / 'champion.json'
START_DATE  = '2025-01-01'

BOOL_PARAMS = [
    'useAdaptiveInput',
    'useTqiInput',
    'multSmoothInput',
    'useAsymBandsInput',
    'useEffAtrInput',
]

# Active numeric ranges [lo, hi] for OAT + LHS
NUMERIC_RANGES = {
    'atrLenInput':          (5,    100),
    'baseMultInput':        (0.5,  5.0),
    'erLengthInput':        (5,    100),
    'adaptStrengthInput':   (0.0,  1.0),
    'atrBaselineLenInput':  (20,   500),
    'qualityStrengthInput': (0.0,  1.0),
    'qualityCurveInput':    (1.0,  3.0),
    'asymStrengthInput':    (0.0,  1.0),
    'tqiWeightErInput':     (0.0,  1.0),
    'tqiWeightVolInput':    (0.0,  1.0),
    'tqiWeightStructInput': (0.0,  1.0),
    'tqiWeightMomInput':    (0.0,  1.0),
    'tqiStructLenInput':    (5,    100),
    'tqiMomLenInput':       (3,    50),
    'slAtrMultInput':       (0.3,  5.0),
    'tp1RInput':            (0.5,  10.0),
    'tp2RInput':            (0.5,  10.0),
    'tp3RInput':            (0.5,  10.0),
    'tradeMaxAgeInput':     (10,   500),
}

INT_PARAMS = {'atrLenInput', 'erLengthInput', 'atrBaselineLenInput',
              'tqiStructLenInput', 'tqiMomLenInput', 'tradeMaxAgeInput'}


# ── CSV helpers ─────────────────────────────────────────────────────────────

def _cfg_tag(cfg: dict) -> str:
    """Stable JSON signature for dedup."""
    clean = {k: v for k, v in cfg.items()
             if k not in ('stage', 'trial_idx', 'presetInput')}
    return json.dumps(clean, sort_keys=True)


def _load_existing() -> set:
    """Return set of already-run config signatures."""
    if not CSV_PATH.exists():
        return set()
    df = pd.read_csv(CSV_PATH, usecols=["config_tag"], on_bad_lines="skip")
    return set(df['config_tag'].tolist())


def _append_result(cfg: dict, result: dict, stage: int, trial_idx: int):
    tag = _cfg_tag(cfg)
    row = {'config_tag':  tag,
           'pf':           result['pf'],
           'trades':       result['trades'],
           'net_pnl':      round(result['gross_profit'] - result['gross_loss'], 2),
           'gross_profit': result['gross_profit'],
           'gross_loss':   result['gross_loss'],
           'win_rate':     result['win_rate'],
           'max_dd':       result['max_dd_abs']}
    for k in sorted(cfg):
        row[f'cfg_{k}'] = cfg[k]
    row['stage'] = stage  # stage LAST to avoid column-shift against old headers
    df_row = pd.DataFrame([row])
    if CSV_PATH.exists():
        # Align to existing header to prevent column shift
        existing_cols = pd.read_csv(CSV_PATH, nrows=0).columns.tolist()
        for col in existing_cols:
            if col not in df_row.columns:
                df_row[col] = np.nan
        # Add new columns not in original header (appended at end)
        df_row = df_row[existing_cols + [c for c in df_row.columns if c not in existing_cols]]
        df_row.to_csv(CSV_PATH, mode='a', header=False, index=False)
    else:
        df_row.to_csv(CSV_PATH, mode='a', header=True, index=False)


def _update_champion(cfg: dict, result: dict):
    champ = {}
    if CHAMP_PATH.exists():
        champ = json.loads(CHAMP_PATH.read_text())
    if result['pf'] > champ.get('pf', 0.0):
        champ = {'pf': result['pf'], 'trades': result['trades'],
                 'config': cfg, 'result': result}
        CHAMP_PATH.write_text(json.dumps(champ, indent=2))
        return True
    return False


# ── Trial runner ─────────────────────────────────────────────────────────────

def run_trial(df: pd.DataFrame, cfg: dict, stage: int, trial_idx: int,
              done: set, total: int) -> dict | None:
    tag = _cfg_tag(cfg)
    if tag in done:
        return None
    t0 = time.perf_counter()
    result = simulate_sats(df, cfg, start_date=START_DATE)
    elapsed = time.perf_counter() - t0
    is_new_champ = _update_champion(cfg, result)
    _append_result(cfg, result, stage, trial_idx)
    done.add(tag)
    marker = ' *** NEW CHAMPION ***' if is_new_champ else ''
    print(f"  [{trial_idx+1:>4}/{total}] S{stage} PF={result['pf']:.4f} "
          f"trades={result['trades']:>5} [{elapsed:.1f}s]{marker}")
    return result


# ── LHS sampler ──────────────────────────────────────────────────────────────

def latin_hypercube(knobs: list[tuple[str, float, float]], n: int,
                    seed: int = 42) -> list[dict]:
    """
    Generate n LHS samples over the given (name, lo, hi) knobs.
    Returns list of {name: value} dicts.
    """
    rng = np.random.default_rng(seed)
    k = len(knobs)
    # Permutation matrix: each column is a permutation of 0..n-1
    perm = np.column_stack([rng.permutation(n) for _ in range(k)])
    # Uniform draw within each stratum
    pts = (perm + rng.uniform(size=(n, k))) / n  # [0, 1]
    samples = []
    for row in pts:
        cfg = {}
        for j, (name, lo, hi) in enumerate(knobs):
            v = lo + row[j] * (hi - lo)
            if name in INT_PARAMS:
                v = int(round(v))
            else:
                v = round(v, 4)
            cfg[name] = v
        samples.append(cfg)
    return samples


# ── Stage 2: boolean sweep ────────────────────────────────────────────────────

def _lookup_pf_from_csv(tag: str) -> float | None:
    """Return PF for a given config_tag from CSV, or None if not found."""
    if not CSV_PATH.exists():
        return None
    df = pd.read_csv(CSV_PATH, usecols=["config_tag","pf"], on_bad_lines="skip")
    row = df[df['config_tag'] == tag]
    return float(row['pf'].iloc[0]) if not row.empty else None


def stage2(df: pd.DataFrame, base: dict, done: set) -> dict:
    combos = list(itertools.product([False, True], repeat=len(BOOL_PARAMS)))
    total = len(combos)
    print(f"\n=== Stage 2: {total} boolean combos ===")
    best = {'pf': -1, 'config': base}
    for idx, vals in enumerate(combos):
        cfg = {**base}
        for p, v in zip(BOOL_PARAMS, vals):
            cfg[p] = v
        result = run_trial(df, cfg, stage=2, trial_idx=idx, done=done, total=total)
        if result is None:
            # Already done — look up PF from CSV for champion tracking
            pf = _lookup_pf_from_csv(_cfg_tag(cfg))
            if pf is not None and pf > best['pf']:
                best = {'pf': pf, 'config': cfg}
        elif result['pf'] > best['pf']:
            best = {**result, 'config': cfg}
    print(f"\nStage 2 best: PF={best['pf']:.4f} config={json.dumps({k: v for k, v in best['config'].items() if k in BOOL_PARAMS})}")
    return best['config']


# ── Stage 3: OAT numeric sensitivity ─────────────────────────────────────────

def stage3(df: pd.DataFrame, base: dict, done: set) -> dict:
    n_vals = 6
    params = list(NUMERIC_RANGES.keys())
    total  = len(params) * n_vals
    print(f"\n=== Stage 3: OAT sensitivity ({len(params)} params × {n_vals} = {total} trials) ===")
    sensitivity: dict[str, float] = {}
    best_per_param: dict[str, tuple[float, float]] = {}  # param → (best_val, best_pf)
    trial_idx = 0
    for pname in params:
        lo, hi = NUMERIC_RANGES[pname]
        if pname in INT_PARAMS:
            vals = [int(round(v)) for v in np.linspace(lo, hi, n_vals)]
            vals = sorted(set(vals))  # deduplicate for narrow int ranges
        else:
            vals = [round(v, 4) for v in np.linspace(lo, hi, n_vals)]
        pfs = []
        best_v = base.get(pname)
        best_pf = -1.0
        for v in vals:
            cfg = {**base, pname: v}
            result = run_trial(df, cfg, stage=3, trial_idx=trial_idx,
                               done=done, total=total)
            trial_idx += 1
            if result:
                pfs.append(result['pf'])
                if result['pf'] > best_pf:
                    best_pf = result['pf']
                    best_v = v
        if result is None:
            # Already done — recover from CSV for sensitivity calc
            pf = _lookup_pf_from_csv(_cfg_tag(cfg))
            if pf is not None:
                pfs.append(pf)
                if pf > best_pf:
                    best_pf = pf
                    best_v = v
        if pfs:
            sensitivity[pname] = max(pfs) - min(pfs)
            best_per_param[pname] = (best_v, best_pf)
    # Rank
    ranked = sorted(sensitivity.items(), key=lambda x: x[1], reverse=True)
    print("\nStage 3 sensitivity ranking:")
    for i, (p, delta) in enumerate(ranked):
        bv, bpf = best_per_param.get(p, (None, None))
        print(f"  {i+1:>2}. {p:<30} ΔPF={delta:.4f}  best_val={bv}  best_PF={bpf:.4f}")
    # Build best config: set each numeric to its best value
    best_cfg = {**base}
    for p, (best_v, _) in best_per_param.items():
        if best_v is not None:
            best_cfg[p] = best_v
    return best_cfg, ranked


# ── Stage 4: LHS on dominant knobs ───────────────────────────────────────────

def stage4(df: pd.DataFrame, base: dict, ranked: list, done: set,
           n_lhs: int = 250, n_dominant: int = 8) -> dict:
    dominant = [p for p, _ in ranked[:n_dominant] if p in NUMERIC_RANGES]
    knobs = [(p, *NUMERIC_RANGES[p]) for p in dominant]
    samples = latin_hypercube(knobs, n_lhs)
    total = len(samples)
    print(f"\n=== Stage 4: {n_lhs} LHS trials on {len(dominant)} dominant knobs ===")
    print(f"  Knobs: {dominant}")
    best = {'pf': -1, 'config': base}
    for idx, sample in enumerate(samples):
        cfg = {**base, **sample}
        result = run_trial(df, cfg, stage=4, trial_idx=idx, done=done, total=total)
        if result is None:
            pf = _lookup_pf_from_csv(_cfg_tag(cfg))
            if pf is not None and pf > best['pf']:
                best = {'pf': pf, 'config': cfg}
        elif result['pf'] > best['pf']:
            best = {**result, 'config': cfg}
    print(f"\nStage 4 best: PF={best['pf']:.4f}")
    return best['config']


# ── Stage 5: fine local refine around top-3 LHS winners ─────────────────────

def stage5(df: pd.DataFrame, stage4_winner: dict, done: set,
           n_steps: int = 2) -> dict:
    print(f"\n=== Stage 5: fine refine (±{n_steps} steps around Stage-4 winner) ===")
    # Collect all Stage 4 results sorted by PF
    if not CSV_PATH.exists():
        return stage4_winner
    all_df = pd.read_csv(CSV_PATH, on_bad_lines='skip')
    s4 = all_df.sort_values('pf', ascending=False).head(3)
    if s4.empty:
        return stage4_winner
    step_sizes = {
        'atrLenInput': 1, 'baseMultInput': 0.2, 'erLengthInput': 2,
        'adaptStrengthInput': 0.1, 'atrBaselineLenInput': 10,
        'qualityStrengthInput': 0.1, 'qualityCurveInput': 0.2,
        'asymStrengthInput': 0.1, 'tqiWeightErInput': 0.1,
        'tqiWeightVolInput': 0.1, 'tqiWeightStructInput': 0.1,
        'tqiWeightMomInput': 0.1, 'tqiStructLenInput': 5,
        'tqiMomLenInput': 2, 'slAtrMultInput': 0.2,
        'tp1RInput': 0.5, 'tp2RInput': 0.5, 'tp3RInput': 0.5,
        'tradeMaxAgeInput': 20,
    }
    all_configs = []
    dominant = list(NUMERIC_RANGES.keys())[:8]
    for _, row in s4.iterrows():
        # Parse config from config_tag (reliable JSON) rather than misaligned cfg_* columns
        try:
            seed_cfg = json.loads(row['config_tag'])
        except Exception:
            continue
        ranges = [
            np.linspace(
                max(NUMERIC_RANGES[p][0], float(seed_cfg.get(p, NUMERIC_RANGES[p][0])) - n_steps * step_sizes.get(p, 0.1)),
                min(NUMERIC_RANGES[p][1], float(seed_cfg.get(p, NUMERIC_RANGES[p][1])) + n_steps * step_sizes.get(p, 0.1)),
                2 * n_steps + 1
            )
            for p in dominant
        ]
        for combo in itertools.product(*[range(len(r)) for r in ranges[:3]]):  # 3^3 = 27 per seed
            cfg = {**seed_cfg}
            for j, idx in enumerate(combo):
                p = dominant[j]
                v = ranges[j][idx]
                cfg[p] = int(round(v)) if p in INT_PARAMS else round(float(v), 4)
            all_configs.append(cfg)
    total = len(all_configs)
    print(f"  {total} fine-grid trials across top-3 Stage-4 seeds")
    best = {'pf': -1, 'trades': 0, 'config': stage4_winner}
    for idx, cfg in enumerate(all_configs):
        tag = _cfg_tag(cfg)
        if tag in done:
            pf = _lookup_pf_from_csv(tag)
            if pf is not None and pf > best['pf']:
                best = {'pf': pf, 'trades': 0, 'config': cfg}
            continue
        result = run_trial(df, cfg, stage=5, trial_idx=idx, done=done, total=total)
        if result and result['pf'] > best['pf']:
            best = {**result, 'config': cfg}
    print(f"\nStage 5 best: PF={best['pf']:.4f} trades={best['trades']}")
    return best.get('config', stage4_winner)


# ── Stage 6: Dynamic TP sub-sweep ────────────────────────────────────────────

def stage6(df: pd.DataFrame, base: dict, done: set, n_lhs: int = 50) -> dict:
    print(f"\n=== Stage 6: Dynamic TP sub-sweep ({n_lhs} LHS trials) ===")
    dyn_knobs = [
        ('dynTpTqiWeightInput', 0.0, 1.0),
        ('dynTpVolWeightInput',  0.0, 1.0),
        ('dynTpMinScaleInput',   0.2, 1.0),
        ('dynTpMaxScaleInput',   1.0, 4.0),
        ('dynTpFloorR1Input',    0.2, 2.0),
        ('dynTpCeilR3Input',     2.0, 20.0),
    ]
    samples = latin_hypercube(dyn_knobs, n_lhs)
    best_fixed_pf = simulate_sats(df, base, start_date=START_DATE)['pf']
    best = {'pf': -1}
    for idx, sample in enumerate(samples):
        cfg = {**base, 'tpModeInput': 'Dynamic', **sample}
        result = run_trial(df, cfg, stage=6, trial_idx=idx, done=done, total=n_lhs)
        if result and result['pf'] > best['pf']:
            best = {**result, 'config': cfg}
    print(f"\nStage 6 best Dynamic PF: {best['pf']:.4f}")
    print(f"Stage 5 Fixed PF:         {best_fixed_pf:.4f}")
    if best['pf'] > best_fixed_pf:
        print("  → Dynamic TP wins")
        return best['config']
    else:
        print("  → Fixed TP wins")
        return base


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--stages', default='2,3,4,5,6',
                        help='Comma-separated list of stages to run (e.g. 2,3,4)')
    parser.add_argument('--lhs-n',  type=int, default=250)
    parser.add_argument('--dominant-k', type=int, default=8)
    parser.add_argument('--s6-n',   type=int, default=50)
    args = parser.parse_args()
    stages = [int(s) for s in args.stages.split(',')]

    print("Loading MES 15m data...")
    df = load_data()
    print(f"  {len(df):,} bars  {df['ts'].min()} → {df['ts'].max()}")

    done = _load_existing()
    print(f"  {len(done)} trials already in CSV (will skip)")

    # Champion baseline
    champ = {}
    if CHAMP_PATH.exists():
        champ = json.loads(CHAMP_PATH.read_text())
    print(f"  Current champion PF: {champ.get('pf', 'none')}")

    stage2_winner = CRYPTO_ANCHOR
    stage3_winner = CRYPTO_ANCHOR
    ranked        = []
    stage4_winner = CRYPTO_ANCHOR
    stage5_winner = CRYPTO_ANCHOR

    if 2 in stages:
        stage2_winner = stage2(df, CRYPTO_ANCHOR, done)

    if 3 in stages:
        stage3_winner, ranked = stage3(df, stage2_winner, done)

    if 4 in stages:
        if not ranked:
            # Fallback: use NUMERIC_RANGES order as sensitivity proxy
            ranked = [(p, 0.0) for p in NUMERIC_RANGES]
        stage4_winner = stage4(df, stage3_winner, ranked, done,
                               n_lhs=args.lhs_n, n_dominant=args.dominant_k)

    if 5 in stages:
        stage5_winner = stage5(df, stage4_winner, done)

    if 6 in stages:
        final = stage6(df, stage5_winner, done, n_lhs=args.s6_n)
    else:
        final = stage5_winner if 5 in stages else stage4_winner

    print("\n=== SWEEP COMPLETE ===")
    champ = json.loads(CHAMP_PATH.read_text()) if CHAMP_PATH.exists() else {}
    print(f"Champion PF:     {champ.get('pf', 'N/A')}")
    print(f"Champion trades: {champ.get('trades', 'N/A')}")
    print(f"Champion config: {json.dumps(champ.get('config', {}), indent=2)}")

    # Summary by stage
    if CSV_PATH.exists():
        all_df = pd.read_csv(CSV_PATH, on_bad_lines='skip')
        print(f"\nTotal trials in CSV: {len(all_df)}")
        print(f"Overall best PF: {all_df['pf'].max():.4f}")
        for s in range(2, 7):
            sd = all_df[all_df['stage'] == s] if 'stage' in all_df.columns else pd.DataFrame()
            if not sd.empty:
                print(f"\nStage {s}: {len(sd)} trials  "
                      f"best_PF={sd['pf'].max():.4f}  "
                      f"median_PF={sd['pf'].median():.4f}")


if __name__ == '__main__':
    main()
