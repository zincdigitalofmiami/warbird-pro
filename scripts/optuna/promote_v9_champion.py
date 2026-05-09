#!/usr/bin/env python3
"""DEPRECATED 2026-05-09 — Hybrid+ champion promotion gate.

Promoted champions from the now-retired Hybrid+ 4-card chain. With the chain
deprecated, this promotion logic is obsolete. The Core AutoGluon card is
gated by scripts/ag/train_hard_gate.py (SHAP + MC integrity gates), not by
this script. See docs/MASTER_PLAN.md "V9 Core AutoGluon" section and
.claude/skills/training-hard-gate.

Retained for git history only. Not runnable.
"""
from __future__ import annotations

import sys

raise SystemExit(
    "promote_v9_champion is DEPRECATED (Hybrid+ chain). The Core card is gated "
    "by scripts/ag/train_hard_gate.py instead."
)

# --- legacy code below (unreachable) -----------------------------------------
import argparse
import importlib
import json
from pathlib import Path
from typing import Any

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.optuna.paths import workspace_dir

OOS_START = pd.Timestamp("2025-01-01", tz="UTC")
PF_FLOOR = 1.10
WR_DROP_MAX = 0.25  # absolute drop in WR from IS to OOS

CARDS = [
    ("warbird_pro_v9_exit_cpcv", "scripts.optuna.warbird_pro_v9_exit_cpcv_profile"),
    ("warbird_pro_v9_entry_filter_cpcv", "scripts.optuna.warbird_pro_v9_entry_filter_cpcv_profile"),
    ("warbird_pro_v9_ag_meta_cpcv", "scripts.optuna.warbird_pro_v9_ag_meta_cpcv_profile"),
    ("warbird_pro_v9_joint_challenger", "scripts.optuna.warbird_pro_v9_joint_challenger_profile"),
]


def _load_top_n(card_key: str, top_n: int) -> list[dict[str, Any]]:
    path = workspace_dir(card_key) / "top5.json"
    if not path.exists():
        return []
    try:
        rows = json.loads(path.read_text())
    except json.JSONDecodeError:
        return []
    if not isinstance(rows, list):
        return []
    return rows[:top_n]


def _replay_card(card_key: str, profile_module: str, top_n: int) -> list[dict[str, Any]]:
    candidates = _load_top_n(card_key, top_n)
    if not candidates:
        return []
    profile = importlib.import_module(profile_module)
    df = profile.load_data()
    oos_df = df.loc[pd.to_datetime(df["ts"], utc=True) >= OOS_START].copy()
    if oos_df.empty:
        return []

    out: list[dict[str, Any]] = []
    for cand in candidates:
        params = cand.get("params") or {}
        is_metrics = {
            "win_rate": float(cand.get("win_rate", 0.0) or 0.0),
            "pf": float(cand.get("pf", 0.0) or 0.0),
            "trades": int(cand.get("trades", 0) or 0),
        }
        try:
            oos_result = profile.run_backtest(oos_df, params, start_date=OOS_START.isoformat())
        except Exception as exc:
            oos_result = {"error": str(exc)[:160]}
        out.append({
            "card": card_key,
            "rank": int(cand.get("rank", 0)),
            "params": params,
            "is": is_metrics,
            "oos": oos_result,
            "wr_drop": is_metrics["win_rate"] - float(oos_result.get("win_rate", 0.0) or 0.0),
            "passes_promotion_gate": _passes_gate(is_metrics, oos_result),
        })
    return out


def _passes_gate(is_metrics: dict[str, Any], oos: dict[str, Any]) -> bool:
    if "error" in oos:
        return False
    oos_wr = float(oos.get("win_rate", 0.0) or 0.0)
    oos_pf = float(oos.get("pf", 0.0) or 0.0)
    is_wr = float(is_metrics.get("win_rate", 0.0) or 0.0)
    return (is_wr - oos_wr) <= WR_DROP_MAX and oos_pf >= PF_FLOOR


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--top-n", type=int, default=10)
    parser.add_argument("--allow-challenger", action="store_true",
                        help="Promote Card 4 only if it strictly beats the Card 1+2+3 winner OOS.")
    args = parser.parse_args()

    print("=== V9 champion promotion (locked OOS replay) ===")
    print(f"  run_id:    {args.run_id}")
    print(f"  oos_start: {OOS_START.date()}")
    print(f"  gate:      WR drop ≤ {WR_DROP_MAX:.2f} absolute, PF ≥ {PF_FLOOR}")
    print()

    rows: list[dict[str, Any]] = []
    for card_key, module in CARDS:
        if card_key == "warbird_pro_v9_joint_challenger" and not args.allow_challenger:
            continue
        print(f"replaying {card_key}...", flush=True)
        rows.extend(_replay_card(card_key, module, args.top_n))

    primary_rows = [r for r in rows if r["card"] != "warbird_pro_v9_joint_challenger" and r["passes_promotion_gate"]]
    if not primary_rows:
        print("No primary card candidate passes the OOS gate. Aborting promotion.")
        return 1

    primary_rows.sort(key=lambda r: float(r["oos"].get("pf", 0.0) or 0.0), reverse=True)
    primary_winner = primary_rows[0]

    challenger_winner = None
    if args.allow_challenger:
        chal_rows = [r for r in rows if r["card"] == "warbird_pro_v9_joint_challenger" and r["passes_promotion_gate"]]
        chal_rows.sort(key=lambda r: float(r["oos"].get("pf", 0.0) or 0.0), reverse=True)
        if chal_rows:
            top = chal_rows[0]
            if float(top["oos"].get("pf", 0.0)) > float(primary_winner["oos"].get("pf", 0.0)):
                challenger_winner = top

    champion = challenger_winner or primary_winner

    out_dir = workspace_dir("warbird_pro_v9_ag_meta_cpcv") / f"champions_{args.run_id}"
    out_dir.mkdir(parents=True, exist_ok=True)
    summary = {
        "run_id": args.run_id,
        "primary_winner": primary_winner,
        "challenger_winner": challenger_winner,
        "promoted_champion": champion,
        "all_rows": rows,
    }
    (out_dir / "champion.json").write_text(json.dumps(summary, indent=2, default=str))
    print()
    print(f"Champion: card={champion['card']} rank={champion['rank']}")
    print(f"  IS:  WR={champion['is']['win_rate']:.4f} PF={champion['is']['pf']:.3f} trades={champion['is']['trades']}")
    print(f"  OOS: WR={float(champion['oos'].get('win_rate', 0.0)):.4f} PF={float(champion['oos'].get('pf', 0.0)):.3f} trades={int(champion['oos'].get('trades', 0))}")
    print(f"  WR drop: {champion['wr_drop']:.4f}")
    print(f"Wrote {out_dir / 'champion.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
