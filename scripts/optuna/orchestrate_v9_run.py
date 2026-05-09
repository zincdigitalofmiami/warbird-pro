#!/usr/bin/env python3
"""DEPRECATED 2026-05-09 — Hybrid+ 4-card orchestrator.

Orchestrated the now-retired Hybrid+ chain (Cards 1-4). Replaced by the single
Core AutoGluon card (scripts/optuna/cards/core_training/2026_05_09_warbird_pro_autogluon_core.py)
+ scripts/ag/train_hard_gate.py for production runs. See docs/MASTER_PLAN.md
"V9 Core AutoGluon" section.

Retained for git history only. Not runnable.
"""
from __future__ import annotations

import sys

raise SystemExit(
    "orchestrate_v9_run is DEPRECATED (Hybrid+ chain). Use scripts/ag/train_hard_gate.py "
    "with the Core card config instead."
)

# --- legacy code below (unreachable) -----------------------------------------
import argparse
import datetime as _dt
import hashlib
import json
import shlex
import subprocess
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.optuna.paths import workspace_dir

CARDS = [
    ("warbird_pro_v9_exit_cpcv", "scripts.optuna.warbird_pro_v9_exit_cpcv_profile",
     "Warbird Pro V9 Exit Policy CPCV"),
    ("warbird_pro_v9_entry_filter_cpcv", "scripts.optuna.warbird_pro_v9_entry_filter_cpcv_profile",
     "Warbird Pro V9 Entry Filter CPCV"),
    ("warbird_pro_v9_ag_meta_cpcv", "scripts.optuna.warbird_pro_v9_ag_meta_cpcv_profile",
     "Warbird Pro V9 AG Meta CPCV"),
    ("warbird_pro_v9_joint_challenger", "scripts.optuna.warbird_pro_v9_joint_challenger_profile",
     "Warbird Pro V9 Joint Challenger"),
]

IS_START = "2020-01-01"
IS_END = "2024-12-31"


def _git_sha() -> str:
    try:
        out = subprocess.run(
            ["git", "-C", str(REPO_ROOT), "rev-parse", "HEAD"],
            capture_output=True, text=True, check=True, timeout=5,
        )
        return out.stdout.strip()
    except Exception:
        return "unknown"


def _read_top_n(card_key: str, top_k: int) -> list[dict[str, Any]]:
    top_path = workspace_dir(card_key) / f"top{top_k}.json"
    if not top_path.exists():
        return []
    try:
        rows = json.loads(top_path.read_text())
    except json.JSONDecodeError:
        return []
    return rows[:top_k] if isinstance(rows, list) else []


def build_candidate_manifest(top_k: int = 5) -> list[dict[str, Any]]:
    """Compose strategy-candidate manifest from Cards 1 + 2 top-K exports.

    The Card 3 AG profile reads this manifest from
    scripts/optuna/workspaces/warbird_pro_v9_ag_meta_cpcv/strategy_candidates.json
    (or the path in env WARBIRD_V9_AG_CANDIDATES). Each entry merges the
    Card 1 exit-policy params with the Card 2 entry-filter params so the AG
    fits one labeled dataset per joint candidate.
    """
    exit_top = _read_top_n("warbird_pro_v9_exit_cpcv", top_k)
    filter_top = _read_top_n("warbird_pro_v9_entry_filter_cpcv", top_k)
    candidates: list[dict[str, Any]] = []
    cid = 0
    for ex_rank, ex in enumerate(exit_top):
        for fl_rank, fl in enumerate(filter_top):
            params: dict[str, Any] = {}
            params.update(ex.get("params") or {})
            params.update(fl.get("params") or {})
            label = f"exit{ex_rank+1}xfilter{fl_rank+1}"
            candidates.append({"id": cid, "label": label, "params": params})
            cid += 1
    if not candidates and exit_top:
        for ex_rank, ex in enumerate(exit_top):
            candidates.append({
                "id": cid, "label": f"exit{ex_rank+1}", "params": ex.get("params") or {},
            })
            cid += 1
    return candidates


def write_run_manifest(
    run_id: str,
    n_trials: dict[str, int],
    candidates: list[dict[str, Any]],
    out_dir: Path,
) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "run_id": run_id,
        "repo_commit": _git_sha(),
        "is_window": {"start": IS_START, "end": IS_END},
        "oos_window": {"start": "2025-01-01", "end": "open"},
        "cards": [
            {
                "key": key,
                "profile_module": module,
                "study_name": name,
                "n_trials": n_trials.get(key, 0),
                "study_db": f"scripts/optuna/workspaces/{key}/study.db",
            }
            for key, module, name in CARDS
        ],
        "candidates_path": str(out_dir / "strategy_candidates.json"),
        "candidate_count": len(candidates),
    }
    path = out_dir / "run.json"
    path.write_text(json.dumps(manifest, indent=2))
    (out_dir / "strategy_candidates.json").write_text(json.dumps(candidates, indent=2))
    return path


def _runner_cmd(card_key: str, profile_module: str, n_trials: int, study_name: str, run_id: str, top_k: int = 5) -> str:
    parts = [
        "python", "scripts/optuna/runner.py",
        "--indicator-key", card_key,
        "--profile-module", profile_module,
        "--n-trials", str(n_trials),
        "--start", IS_START,
        "--end", IS_END,
        "--study-name", study_name,
        "--top-n", str(top_k),
    ]
    return " ".join(shlex.quote(p) for p in parts) + f"   # run_id={run_id}"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--n-trials-exit", type=int, default=500)
    parser.add_argument("--n-trials-filter", type=int, default=1500)
    parser.add_argument("--n-trials-ag", type=int, default=1000)
    parser.add_argument("--n-trials-joint", type=int, default=500)
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--include-joint", action="store_true",
                        help="If set, also schedule Card 4 (joint challenger).")
    args = parser.parse_args()

    run_id = _dt.datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    n_trials = {
        "warbird_pro_v9_exit_cpcv": args.n_trials_exit,
        "warbird_pro_v9_entry_filter_cpcv": args.n_trials_filter,
        "warbird_pro_v9_ag_meta_cpcv": args.n_trials_ag,
    }
    if args.include_joint:
        n_trials["warbird_pro_v9_joint_challenger"] = args.n_trials_joint

    candidates = build_candidate_manifest(top_k=args.top_k)
    out_dir = workspace_dir("warbird_pro_v9_ag_meta_cpcv")

    print(f"=== Warbird Pro V9 Hybrid+ orchestration ===")
    print(f"  run_id:          {run_id}")
    print(f"  is_window:       {IS_START} → {IS_END}")
    print(f"  oos_lock:        2025-01-01+ (untouched, champion selection only)")
    print(f"  candidates:      {len(candidates)}  (cross-product of Cards 1+2 top-{args.top_k})")
    print(f"  manifest path:   {out_dir / 'run.json'}")
    print()

    cmds = []
    for key, module, name in CARDS:
        if key not in n_trials:
            continue
        cmds.append(_runner_cmd(key, module, n_trials[key], name, run_id, top_k=args.top_k))

    if args.dry_run:
        print("Dry run — runner.py commands that would be issued:")
        for c in cmds:
            print(f"  {c}")
        return 0

    write_run_manifest(run_id, n_trials, candidates, out_dir)
    print(f"Wrote run.json + strategy_candidates.json to {out_dir}")
    print()
    print("Now run each card from a separate shell so logs stream cleanly:")
    print()
    for c in cmds:
        print(f"  {c}")
    print()
    print("After ALL active cards finish:")
    print(f"  python scripts/optuna/promote_v9_champion.py --run-id {run_id}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
