#!/usr/bin/env python3
"""
band_phase_winners.py — derive next-phase tuning bounds from prior-phase top cohort.

Usage
-----
    python scripts/ag/band_phase_winners.py \\
        --from-space scripts/ag/strategy_tuning_space.phase1.json \\
        --to-space   scripts/ag/strategy_tuning_space.phase2.json \\
        --top 20 \\
        --storage postgres

Behavior
--------
1. Load top-N authoritative trials (CSV_FULL or TV_MCP_STRICT) for the FROM
   space's profile, ordered by objective_score DESC.
2. For each parameter in the FROM space's search_parameters, build a band:
     numeric  -> median +/- clipped IQR (or MAD when IQR collapses), clipped to
                 the from-space's original min/max.
     int+list -> retain only the discrete values that fall within the same
                 IQR/MAD window (with a min_keep floor so the band never empties).
     string,
     bool     -> top 1-2 modes; minority retained only if support >= threshold.
3. Inject banded knobs into the TO space's search_parameters (in-place merge).
4. Remove the corresponding key from the TO space's phase_carry_placeholders
   so the banding state is explicit on disk.

The TO space's own native search_parameters (the new phase's knobs) are left
untouched. Re-running the script overwrites prior banding for the same FROM
keys, so it is idempotent.

Storage backends
----------------
postgres : reads from warbird_strategy_tuning_trials filtered by profile_name.
jsonl    : reads from artifacts/tuning/strategy_trials.jsonl filtered by profile.

The script writes a sidecar manifest next to the TO space:
    <to-space>.banding-manifest.json
documenting the FROM profile, top-N count, per-knob statistics, and the exact
trial ids contributing to each band.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.ag import tune_strategy_params as tsp


DEFAULT_LEDGER = REPO_ROOT / "artifacts" / "tuning" / "strategy_trials.jsonl"
DEFAULT_TOP = 20
DEFAULT_K_IQR = 1.5
DEFAULT_MINORITY_SUPPORT = 0.15
DEFAULT_MAX_MODES = 2


# ── helpers ────────────────────────────────────────────────────────────────────


def _percentile(sorted_values: list[float], q: float) -> float | None:
    if not sorted_values:
        return None
    if len(sorted_values) == 1:
        return float(sorted_values[0])
    pos = q * (len(sorted_values) - 1)
    lo = int(pos)
    hi = min(lo + 1, len(sorted_values) - 1)
    frac = pos - lo
    return float(sorted_values[lo] + frac * (sorted_values[hi] - sorted_values[lo]))


def _iqr_or_mad(values: list[float]) -> tuple[float, str]:
    """Return (spread, source) where source is 'iqr' or 'mad'."""
    if len(values) < 2:
        return 0.0, "iqr"
    sorted_v = sorted(values)
    q1 = _percentile(sorted_v, 0.25)
    q3 = _percentile(sorted_v, 0.75)
    iqr = (q3 - q1) if (q1 is not None and q3 is not None) else 0.0
    if iqr > 1e-9:
        return iqr, "iqr"
    median = statistics.median(values)
    deviations = [abs(v - median) for v in values]
    mad = statistics.median(deviations) if deviations else 0.0
    return mad, "mad"


def _objective_score(trial: dict[str, Any]) -> float | None:
    """
    Objective score lives inside trial['objective']['objective_score'] for
    Postgres rows and trial['objective_score'] for some JSONL paths. Handle both.
    """
    obj = trial.get("objective") or {}
    if isinstance(obj, dict) and "objective_score" in obj:
        score = obj["objective_score"]
    else:
        score = trial.get("objective_score")
    if score is None:
        return None
    try:
        return float(score)
    except (TypeError, ValueError):
        return None


def _trial_search_params(trial: dict[str, Any]) -> dict[str, Any]:
    sp = trial.get("search_parameters") or {}
    if isinstance(sp, str):
        try:
            sp = json.loads(sp)
        except json.JSONDecodeError:
            sp = {}
    return sp if isinstance(sp, dict) else {}


# ── trial loaders ──────────────────────────────────────────────────────────────


def load_trials_for_profile(
    storage: str, profile: str, db_dsn: str, ledger: Path
) -> list[dict[str, Any]]:
    if storage == "postgres":
        with tsp.connect_db(db_dsn) as conn:
            return tsp.fetch_db_trials(conn, profile)
    rows = tsp.load_trials_jsonl_csv_full(ledger)
    return [
        r
        for r in rows
        if r.get("profile") == profile or r.get("profile_name") == profile
    ]


def select_top_n(trials: list[dict[str, Any]], top_n: int) -> list[dict[str, Any]]:
    scored = [(t, _objective_score(t)) for t in trials]
    scored = [(t, s) for (t, s) in scored if s is not None]
    scored.sort(key=lambda pair: pair[1], reverse=True)
    return [t for (t, _) in scored[:top_n]]


# ── per-knob banders ───────────────────────────────────────────────────────────


def band_float(
    values: list[float], domain: dict[str, Any], k_iqr: float
) -> dict[str, Any] | None:
    if not values:
        return None
    median = statistics.median(values)
    spread, spread_source = _iqr_or_mad(values)
    step = float(domain.get("step", 0.0) or 0.0)
    if spread <= 1e-9:
        spread = max(step, abs(median) * 0.05, 1e-6)
    raw_lo = median - k_iqr * spread
    raw_hi = median + k_iqr * spread
    orig_min = float(domain["min"])
    orig_max = float(domain["max"])
    lo = max(orig_min, raw_lo)
    hi = min(orig_max, raw_hi)
    if lo > hi:
        lo, hi = orig_min, orig_max
    if step > 0:
        lo = round(lo / step) * step
        hi = round(hi / step) * step
        if hi < lo:
            hi = lo
    return {
        "type": "float",
        "min": lo,
        "max": hi,
        "step": step or 0.01,
        "_band_source": spread_source,
        "_band_median": round(median, 6),
        "_band_n": len(values),
    }


def band_int_range(
    values: list[float], domain: dict[str, Any], k_iqr: float
) -> dict[str, Any] | None:
    if not values:
        return None
    median = statistics.median(values)
    spread, spread_source = _iqr_or_mad(values)
    if spread <= 1e-9:
        spread = max(domain.get("step", 1) or 1, 1.0)
    orig_min = int(domain["min"])
    orig_max = int(domain["max"])
    lo = max(orig_min, int(round(median - k_iqr * spread)))
    hi = min(orig_max, int(round(median + k_iqr * spread)))
    if lo > hi:
        lo, hi = orig_min, orig_max
    return {
        "type": "int",
        "min": lo,
        "max": hi,
        "step": int(domain.get("step", 1) or 1),
        "_band_source": spread_source,
        "_band_median": int(round(median)),
        "_band_n": len(values),
    }


def band_int_values(
    values: list[float], domain: dict[str, Any], k_iqr: float, min_keep: int = 1
) -> dict[str, Any] | None:
    if not values:
        return None
    original = [int(v) for v in domain["values"]]
    median = statistics.median(values)
    spread, spread_source = _iqr_or_mad(values)
    if spread <= 1e-9:
        spread = 1.0
    lo = median - k_iqr * spread
    hi = median + k_iqr * spread
    kept = [v for v in original if lo <= v <= hi]
    if len(kept) < min_keep:
        nearest = min(original, key=lambda v: abs(v - median))
        kept = [nearest]
    return {
        "type": "int",
        "values": sorted(kept),
        "_band_source": spread_source,
        "_band_median": int(round(median)),
        "_band_n": len(values),
    }


def band_categorical(
    values: list[Any],
    domain: dict[str, Any],
    minority_support: float,
    max_modes: int,
) -> dict[str, Any] | None:
    if not values:
        return None
    counts = Counter(values)
    total = sum(counts.values())
    sorted_modes = counts.most_common()
    keep = [sorted_modes[0][0]]
    for mode, count in sorted_modes[1:max_modes]:
        if (count / total) >= minority_support:
            keep.append(mode)
    original_values = list(domain.get("values", []))
    kept_in_order = [v for v in original_values if v in keep] or keep
    return {
        "type": "string",
        "values": kept_in_order,
        "_band_modes": [{"value": m, "count": c} for m, c in sorted_modes[:max_modes]],
        "_band_n": len(values),
    }


def band_bool(values: list[Any], minority_support: float) -> dict[str, Any] | None:
    if not values:
        return None
    truthy = [bool(v) for v in values]
    counts = Counter(truthy)
    total = sum(counts.values())
    if not total:
        return None
    top_value, top_count = counts.most_common(1)[0]
    minority_count = total - top_count
    if minority_count / total >= minority_support:
        return {
            "type": "bool",
            "_band_modes": [{"value": True, "count": counts.get(True, 0)},
                             {"value": False, "count": counts.get(False, 0)}],
            "_band_n": total,
        }
    return {
        "type": "string",
        "values": [str(top_value)],
        "_band_modes": [{"value": top_value, "count": top_count}],
        "_band_n": total,
        "_band_collapsed_to_single_value": True,
    }


# ── orchestration ──────────────────────────────────────────────────────────────


def band_one_knob(
    name: str,
    domain: dict[str, Any],
    trials: list[dict[str, Any]],
    k_iqr: float,
    minority_support: float,
    max_modes: int,
) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    """Return (banded_domain, manifest_entry)."""
    raw_values = []
    contributing_trial_ids: list[str] = []
    for trial in trials:
        sp = _trial_search_params(trial)
        if name in sp and sp[name] is not None:
            raw_values.append(sp[name])
            tid = trial.get("trial_id") or trial.get("id")
            if tid:
                contributing_trial_ids.append(str(tid))
    if not raw_values:
        return None, {
            "name": name,
            "outcome": "skipped",
            "reason": "no trial values found",
            "n_trials": 0,
        }
    domain_type = domain.get("type")
    manifest_entry: dict[str, Any] = {
        "name": name,
        "domain_type": domain_type,
        "n_trials": len(raw_values),
        "trial_ids": contributing_trial_ids,
    }
    if domain_type == "float":
        numeric = [float(v) for v in raw_values]
        banded = band_float(numeric, domain, k_iqr)
    elif domain_type == "int":
        numeric = [float(v) for v in raw_values]
        if "values" in domain:
            banded = band_int_values(numeric, domain, k_iqr)
        else:
            banded = band_int_range(numeric, domain, k_iqr)
    elif domain_type == "string":
        banded = band_categorical(raw_values, domain, minority_support, max_modes)
    elif domain_type == "bool":
        banded = band_bool(raw_values, minority_support)
    else:
        return None, {**manifest_entry, "outcome": "skipped", "reason": f"unknown type {domain_type!r}"}

    if banded is None:
        manifest_entry["outcome"] = "no-band-produced"
        return None, manifest_entry
    manifest_entry["outcome"] = "banded"
    manifest_entry["banded"] = {k: v for k, v in banded.items() if not k.startswith("_band_")}
    manifest_entry["band_meta"] = {k: v for k, v in banded.items() if k.startswith("_band_")}
    public_band = {k: v for k, v in banded.items() if not k.startswith("_band_")}
    return public_band, manifest_entry


def merge_banded_into_to_space(
    to_space: dict[str, Any], banded: dict[str, dict[str, Any]]
) -> None:
    sp = to_space.setdefault("search_parameters", {})
    for name, domain in banded.items():
        sp[name] = domain
    placeholders = to_space.get("phase_carry_placeholders") or {}
    for name in list(placeholders.keys()):
        if name == "_comment":
            continue
        if name in banded:
            placeholders.pop(name, None)
    if not any(k for k in placeholders if k != "_comment"):
        to_space.pop("phase_carry_placeholders", None)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--from-space", required=True, type=Path)
    parser.add_argument("--to-space", required=True, type=Path)
    parser.add_argument("--top", type=int, default=DEFAULT_TOP, help="top-N cohort size (default %(default)s)")
    parser.add_argument(
        "--storage", choices=("postgres", "jsonl"), default="postgres",
        help="trial storage backend",
    )
    parser.add_argument(
        "--db-dsn", default=tsp.DEFAULT_DB_DSN, help="postgres DSN (storage=postgres)",
    )
    parser.add_argument(
        "--ledger", type=Path, default=DEFAULT_LEDGER,
        help="JSONL ledger path (storage=jsonl)",
    )
    parser.add_argument("--k-iqr", type=float, default=DEFAULT_K_IQR)
    parser.add_argument(
        "--minority-support", type=float, default=DEFAULT_MINORITY_SUPPORT,
        help="categorical/bool runner-up retained when support >= threshold",
    )
    parser.add_argument("--max-modes", type=int, default=DEFAULT_MAX_MODES)
    parser.add_argument(
        "--dry-run", action="store_true",
        help="do not write to-space; print resulting search_parameters JSON to stdout",
    )
    args = parser.parse_args(argv)

    if not args.from_space.exists():
        print(f"FAIL: from-space not found: {args.from_space}", file=sys.stderr)
        return 2
    if not args.to_space.exists():
        print(f"FAIL: to-space not found: {args.to_space}", file=sys.stderr)
        return 2

    from_space = json.loads(args.from_space.read_text())
    to_space = json.loads(args.to_space.read_text())
    profile = from_space.get("profile_name")
    if not profile:
        print("FAIL: from-space missing profile_name", file=sys.stderr)
        return 2

    trials = load_trials_for_profile(args.storage, profile, args.db_dsn, args.ledger)
    top = select_top_n(trials, args.top)
    if not top:
        print(
            f"FAIL: no scored trials found for profile {profile!r} via {args.storage}",
            file=sys.stderr,
        )
        return 3

    banded: dict[str, dict[str, Any]] = {}
    manifest_entries: list[dict[str, Any]] = []
    from_search = from_space.get("search_parameters") or {}
    for name, domain in from_search.items():
        public_band, entry = band_one_knob(
            name, domain, top, args.k_iqr, args.minority_support, args.max_modes,
        )
        manifest_entries.append(entry)
        if public_band is not None:
            banded[name] = public_band

    merge_banded_into_to_space(to_space, banded)

    manifest = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "from_space": str(args.from_space),
        "to_space": str(args.to_space),
        "from_profile": profile,
        "to_profile": to_space.get("profile_name"),
        "storage": args.storage,
        "top_n_requested": args.top,
        "top_n_used": len(top),
        "trial_ids": [t.get("trial_id") or t.get("id") for t in top],
        "k_iqr": args.k_iqr,
        "minority_support": args.minority_support,
        "max_modes": args.max_modes,
        "knobs": manifest_entries,
    }

    if args.dry_run:
        print(json.dumps({"to_space_after_band": to_space, "manifest": manifest}, indent=2, default=str))
        return 0

    args.to_space.write_text(json.dumps(to_space, indent=2) + "\n")
    manifest_path = args.to_space.with_suffix(args.to_space.suffix + ".banding-manifest.json")
    manifest_path.write_text(json.dumps(manifest, indent=2, default=str) + "\n")
    print(f"Banded {len(banded)} knobs from top {len(top)} trials of {profile!r}")
    print(f"Wrote: {args.to_space}")
    print(f"Manifest: {manifest_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
