#!/usr/bin/env python3
"""
SATS Custom-Mode PF Sweep Harness

Manages trial sampling, CSV checkpointing, and champion tracking for the
9-stage Custom-mode PF optimization sweep described in the plan.

CLI commands:
    python scripts/sats/sweep_harness.py generate --stage <N> [--seed 42] [--n 250]
        → Prints JSON array of trial configs for stage N.

    python scripts/sats/sweep_harness.py log --trial_json '<json>' --pf <float> --trades <int>
                                              --net_pnl <float> --gross_profit <float>
                                              --gross_loss <float> --win_rate <float>
                                              --max_dd <float>
        → Appends result to all_trials.csv and updates champion.json if new best.

    python scripts/sats/sweep_harness.py status
        → Print champion and trial count.

    python scripts/sats/sweep_harness.py remaining --stage <N>
        → Print how many trials from this stage are not yet in the checkpoint.
"""

import argparse
import csv
import json
import math
import random
import sys
from itertools import product
from pathlib import Path

# ── Paths ─────────────────────────────────────────────────────────────────────
SWEEP_DIR   = Path(__file__).parent.parent.parent / "data" / "sats_ps_sweep"
TRIALS_CSV  = SWEEP_DIR / "all_trials.csv"
CHAMPION    = SWEEP_DIR / "champion.json"
SWEEP_DIR.mkdir(parents=True, exist_ok=True)

# ── Full parameter space (verified PF-affecting inputs only) ──────────────────
# Anchor = Crypto 24/7 equivalents in Custom mode. Stage 1 verifies these
# reproduce Crypto results bar-for-bar before any sweep begins.
CRYPTO_ANCHOR = {
    "atrLenInput":          14,
    "baseMultInput":        2.8,
    "useAdaptiveInput":     True,
    "erLengthInput":        20,
    "adaptStrengthInput":   0.5,
    "atrBaselineLenInput":  100,
    "useTqiInput":          True,
    "qualityStrengthInput": 0.4,
    "qualityCurveInput":    1.5,
    "multSmoothInput":      True,
    "useAsymBandsInput":    True,
    "asymStrengthInput":    0.5,
    "useEffAtrInput":       True,
    "useCharFlipInput":     True,
    "charFlipMinAgeInput":  5,
    "charFlipHighInput":    0.55,
    "charFlipLowInput":     0.25,
    "tqiWeightErInput":     0.35,
    "tqiWeightVolInput":    0.20,
    "tqiWeightStructInput": 0.25,
    "tqiWeightMomInput":    0.20,
    "tqiStructLenInput":    20,
    "tqiMomLenInput":       10,
    "slAtrMultInput":       2.5,
    "tpModeInput":          "Fixed",
    "tp1RInput":            1.0,
    "tp2RInput":            2.0,
    "tp3RInput":            3.0,
    "tradeMaxAgeInput":     100,
    # Dynamic TP (only used when tpModeInput="Dynamic"):
    "dynTpTqiWeightInput":  0.6,
    "dynTpVolWeightInput":  0.4,
    "dynTpMinScaleInput":   0.5,
    "dynTpMaxScaleInput":   2.0,
    "dynTpFloorR1Input":    0.5,
    "dynTpCeilR3Input":     8.0,
}

BOOLEANS = [
    "useAdaptiveInput", "useTqiInput", "multSmoothInput",
    "useAsymBandsInput", "useEffAtrInput", "useCharFlipInput",
]

NUMERICS = {
    "atrLenInput":          (5,   100,  1),
    "baseMultInput":        (0.5,  5.0, 0.1),
    "erLengthInput":        (5,   100,  1),
    "adaptStrengthInput":   (0.0,  1.0, 0.05),
    "atrBaselineLenInput":  (20,  500,  5),
    "qualityStrengthInput": (0.0,  1.0, 0.05),
    "qualityCurveInput":    (1.0,  3.0, 0.1),
    "asymStrengthInput":    (0.0,  1.0, 0.05),
    "charFlipMinAgeInput":  (1,    50,  1),
    "charFlipHighInput":    (0.30, 0.90, 0.05),
    "charFlipLowInput":     (0.0,  0.50, 0.05),
    "tqiWeightErInput":     (0.0,  1.0, 0.05),
    "tqiWeightVolInput":    (0.0,  1.0, 0.05),
    "tqiWeightStructInput": (0.0,  1.0, 0.05),
    "tqiWeightMomInput":    (0.0,  1.0, 0.05),
    "tqiStructLenInput":    (5,   100,  1),
    "tqiMomLenInput":       (3,    50,  1),
    "slAtrMultInput":       (0.3,  5.0, 0.1),
    "tp1RInput":            (0.5, 10.0, 0.5),
    "tp2RInput":            (0.5, 10.0, 0.5),
    "tp3RInput":            (0.5, 10.0, 0.5),
    "tradeMaxAgeInput":     (10,  500,  10),
    "atrLenInput":          (5,   100,  1),
}

DYN_TP_NUMERICS = {
    "dynTpTqiWeightInput":  (0.0, 1.0, 0.1),
    "dynTpVolWeightInput":  (0.0, 1.0, 0.1),
    "dynTpMinScaleInput":   (0.2, 1.0, 0.1),
    "dynTpMaxScaleInput":   (1.0, 4.0, 0.25),
    "dynTpFloorR1Input":    (0.2, 2.0, 0.2),
    "dynTpCeilR3Input":     (2.0, 20.0, 2.0),
}


def _linspace(lo, hi, n):
    """n evenly spaced values from lo to hi inclusive."""
    if n == 1:
        return [lo]
    step = (hi - lo) / (n - 1)
    return [round(lo + i * step, 6) for i in range(n)]


def _lhs(params: dict[str, tuple], n_samples: int, seed: int = 42) -> list[dict]:
    """Latin-hypercube sampling over named numeric parameters."""
    rng = random.Random(seed)
    keys = list(params.keys())
    k = len(keys)
    # Generate permutation matrix
    perms = [list(range(n_samples)) for _ in range(k)]
    for p in perms:
        rng.shuffle(p)
    samples = []
    for i in range(n_samples):
        config = dict(CRYPTO_ANCHOR)  # start from anchor
        for j, key in enumerate(keys):
            lo, hi, _ = params[key]
            u = (perms[j][i] + rng.random()) / n_samples
            val = lo + u * (hi - lo)
            # Round to step
            step = params[key][2]
            val = round(round(val / step) * step, 6)
            val = max(lo, min(hi, val))
            config[key] = val
        samples.append(config)
    return samples


def _bool_combinations(anchor: dict) -> list[dict]:
    """All 2^6 boolean combinations, numerics held at anchor."""
    configs = []
    for combo in product([False, True], repeat=len(BOOLEANS)):
        c = dict(anchor)
        for key, val in zip(BOOLEANS, combo):
            c[key] = val
        configs.append(c)
    return configs


def _oat_numeric(anchor: dict, n_levels: int = 6) -> list[dict]:
    """One-at-a-time numeric sweep: vary each knob across n_levels, hold others at anchor."""
    configs = []
    for key, (lo, hi, _) in NUMERICS.items():
        for val in _linspace(lo, hi, n_levels):
            c = dict(anchor)
            c[key] = val
            configs.append(c)
    return configs


def _fine_refine(center: dict, dominant_keys: list[str], levels: int = 3) -> list[dict]:
    """
    Tight grid around center: ±1 step on each dominant key (3 values × n keys).
    dominant_keys: list of key names to vary.
    """
    configs = []
    grids = {}
    for key in dominant_keys:
        if key not in NUMERICS:
            continue
        lo, hi, step = NUMERICS[key]
        mid = center.get(key, CRYPTO_ANCHOR[key])
        vals = sorted(set([
            max(lo, min(hi, round((mid - step) / step) * step)),
            round(mid / step) * step,
            max(lo, min(hi, round((mid + step) / step) * step)),
        ]))
        grids[key] = vals
    for combo in product(*grids.values()):
        c = dict(center)
        for key, val in zip(grids.keys(), combo):
            c[key] = round(val, 6)
        configs.append(c)
    return configs


def _tag(config: dict) -> str:
    """Stable string fingerprint for dedup."""
    return json.dumps({k: config[k] for k in sorted(config)}, sort_keys=True)


def _load_done_tags() -> set[str]:
    if not TRIALS_CSV.exists():
        return set()
    tags = set()
    with open(TRIALS_CSV, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            tags.add(row.get("config_tag", ""))
    return tags


def cmd_generate(args) -> None:
    stage = args.stage
    seed  = args.seed
    n     = args.n
    anchor = CRYPTO_ANCHOR.copy()

    if stage == 1:
        configs = [anchor]
    elif stage == 2:
        configs = _bool_combinations(anchor)
    elif stage == 3:
        configs = _oat_numeric(anchor, n_levels=6)
    elif stage == 4:
        configs = _lhs(NUMERICS, n_samples=n or 250, seed=seed)
    elif stage == 5:
        # Expect user to supply --center_json with best-so-far champion
        if not CHAMPION.exists():
            print("ERROR: champion.json not found. Run stages 1-4 first.", file=sys.stderr)
            sys.exit(1)
        with open(CHAMPION) as f:
            champ = json.load(f)["config"]
        dominant = _get_dominant_keys()
        configs = _fine_refine(champ, dominant, levels=3)
    elif stage == 6:
        if not CHAMPION.exists():
            print("ERROR: champion.json not found.", file=sys.stderr)
            sys.exit(1)
        with open(CHAMPION) as f:
            base = json.load(f)["config"]
        base["tpModeInput"] = "Dynamic"
        configs = _lhs(DYN_TP_NUMERICS, n_samples=n or 50, seed=seed)
        for c in configs:
            c["tpModeInput"] = "Dynamic"
    else:
        print(f"ERROR: Unknown stage {stage}. Valid: 1-6.", file=sys.stderr)
        sys.exit(1)

    # Deduplicate against already-completed trials
    done = _load_done_tags()
    new_configs = [c for c in configs if _tag(c) not in done]

    print(json.dumps(new_configs, indent=2))
    print(f"\n# {len(new_configs)} new trials (skipped {len(configs)-len(new_configs)} already done)",
          file=sys.stderr)


def _get_dominant_keys() -> list[str]:
    """
    Read all_trials.csv, compute ΔPF range per numeric key (OAT stage 3 rows),
    return top-8 by sensitivity. Falls back to the known key suspects from theory.
    """
    fallback = [
        "baseMultInput", "slAtrMultInput", "atrLenInput", "qualityStrengthInput",
        "asymStrengthInput", "charFlipMinAgeInput", "tp3RInput", "erLengthInput",
    ]
    if not TRIALS_CSV.exists():
        return fallback
    # Group PF by key-value combos where only one key differs from anchor
    key_pf: dict[str, list[float]] = {k: [] for k in NUMERICS}
    with open(TRIALS_CSV, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if float(row.get("pf", 0)) <= 0:
                continue
            try:
                cfg = json.loads(row.get("config_tag", "{}"))
            except json.JSONDecodeError:
                continue
            for key in NUMERICS:
                if cfg.get(key) != CRYPTO_ANCHOR.get(key):
                    # This trial varied this key (at minimum); record PF
                    key_pf[key].append(float(row["pf"]))

    ranges = {k: (max(v) - min(v)) if len(v) > 1 else 0.0 for k, v in key_pf.items()}
    sorted_keys = sorted(ranges, key=ranges.get, reverse=True)
    top = [k for k in sorted_keys if ranges[k] > 0]
    return (top[:8] if len(top) >= 8 else top + fallback)[:8]


def cmd_log(args) -> None:
    config = json.loads(args.trial_json)
    tag    = _tag(config)
    row = {
        "config_tag":   tag,
        "pf":           args.pf,
        "trades":       args.trades,
        "net_pnl":      args.net_pnl,
        "gross_profit": args.gross_profit,
        "gross_loss":   args.gross_loss,
        "win_rate":     args.win_rate,
        "max_dd":       args.max_dd,
    }
    # Also flatten key inputs for easy CSV analysis
    for key in sorted(CRYPTO_ANCHOR):
        row[f"cfg_{key}"] = config.get(key, CRYPTO_ANCHOR[key])

    write_header = not TRIALS_CSV.exists()
    with open(TRIALS_CSV, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(row.keys()))
        if write_header:
            writer.writeheader()
        writer.writerow(row)

    # Update champion
    champ = {}
    if CHAMPION.exists():
        with open(CHAMPION) as f:
            champ = json.load(f)

    prev_pf = champ.get("pf", 0.0)
    if float(args.pf) > prev_pf:
        champ = {"pf": float(args.pf), "config": config, "row": row}
        with open(CHAMPION, "w") as f:
            json.dump(champ, f, indent=2)
        print(f"NEW CHAMPION: PF={args.pf:.4f} (was {prev_pf:.4f})")
    else:
        print(f"Logged: PF={args.pf:.4f} (champion still {prev_pf:.4f})")


def cmd_status(_args) -> None:
    n_trials = 0
    if TRIALS_CSV.exists():
        with open(TRIALS_CSV, newline="", encoding="utf-8") as f:
            n_trials = sum(1 for _ in csv.reader(f)) - 1  # subtract header

    champ = {}
    if CHAMPION.exists():
        with open(CHAMPION) as f:
            champ = json.load(f)

    print(f"Trials logged:  {n_trials}")
    if champ:
        print(f"Champion PF:    {champ['pf']:.4f}")
        print(f"Champion trades:{champ['row'].get('trades', '?')}")
        print(f"Champion net:   ${float(champ['row'].get('net_pnl', 0)):,.2f}")
        print("\nChampion config (diff from anchor):")
        for k, v in champ["config"].items():
            if v != CRYPTO_ANCHOR.get(k):
                print(f"  {k}: {CRYPTO_ANCHOR.get(k)} → {v}")
    else:
        print("No champion yet.")


def cmd_remaining(args) -> None:
    stage = args.stage
    anchor = CRYPTO_ANCHOR.copy()
    if stage == 2:
        configs = _bool_combinations(anchor)
    elif stage == 3:
        configs = _oat_numeric(anchor, n_levels=6)
    elif stage == 4:
        configs = _lhs(NUMERICS, n_samples=250, seed=42)
    else:
        configs = []
    done = _load_done_tags()
    remaining = [c for c in configs if _tag(c) not in done]
    print(f"Stage {stage}: {len(remaining)} remaining of {len(configs)} total")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    subs = parser.add_subparsers(dest="cmd", required=True)

    gen = subs.add_parser("generate")
    gen.add_argument("--stage", type=int, required=True)
    gen.add_argument("--seed",  type=int, default=42)
    gen.add_argument("--n",     type=int, default=None)

    log = subs.add_parser("log")
    log.add_argument("--trial_json",   required=True)
    log.add_argument("--pf",           type=float, required=True)
    log.add_argument("--trades",       type=int,   required=True)
    log.add_argument("--net_pnl",      type=float, required=True)
    log.add_argument("--gross_profit", type=float, required=True)
    log.add_argument("--gross_loss",   type=float, required=True)
    log.add_argument("--win_rate",     type=float, required=True)
    log.add_argument("--max_dd",       type=float, required=True)

    subs.add_parser("status")

    rem = subs.add_parser("remaining")
    rem.add_argument("--stage", type=int, required=True)

    args = parser.parse_args()
    {"generate": cmd_generate, "log": cmd_log, "status": cmd_status,
     "remaining": cmd_remaining}[args.cmd](args)


if __name__ == "__main__":
    main()
