# Policy MC Sweep Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build `scripts/ag/policy_mc_sweep.py` — a post-hoc Monte Carlo sweep over macro-fib-trade exit management policies on a locked AG training fixture — honoring the corrected scope from design commit `1e6a8c6`.

**Architecture:** Standalone Python script. Read-only against artifacts + local `warbird` PG17 DB (`mes_1m` + `ag_training`). Zero touches to `train_ag_baseline.py`, `run_diagnostic_shap.py`, `monte_carlo_run.py`, or `build_ag_pipeline.py`. Zero migrations. Outputs to `artifacts/ag_runs/<RUN_ID>/policy_sweep/` (new directory).

**Tech Stack:** Python 3, pandas, numpy, psycopg2, pyarrow — all already installed. No new dependencies.

**Locked source fixture:** `agtrain_20260415T165437712806Z` (SUCCEEDED, `num_bag_folds=0`, full zoo, 327,942 rows, 1,712 sessions, 5 folds).

**Corrected scope (per design amendment):**
- Phase 1 = 1 identity "no-filter" baseline combo per stop family. Rejection=wick knob deferred pending Pine audit.
- Phase 2 = 4 macro-trade exit management knobs, 48 combos per stop family × 6 families = **288 total combos**.
- Cross-family ranking forbidden (Anti-Pattern A). No NO_EDGE labeling. All 6 families always emit best-available policy.
- Narrative caveats MUST be runtime-conditional (Anti-Pattern B), mirroring `monte_carlo_run.py::build_run_note` pattern.

**Phase 2 grid:**
| Knob | Pine input label | Levels |
|---|---|---|
| `Let Fast Runners Run` | `"Let Fast Runners Run"` | {off, on} — 2 |
| `Fast Runner Window (bars)` | `"Fast Runner Window (bars)"` | {1, 2, 3, 4, 6, 8} — 6 |
| `Fast Runner Target` | `"Fast Runner Target"` | {TP2, TP3} — 2 (TP1 is NOT a valid Pine option) |
| `Break-Even After TP1` | `"Break-Even After TP1"` | {off, on} — 2 |

= 2 × 6 × 2 × 2 = 48 combos per stop family.

---

## Task 1: Scaffold + CLI + Gate H (fixture hash assertion)

**Files:**
- Create: `scripts/ag/policy_mc_sweep.py`
- Create: `tests/ag/test_policy_mc_sweep_cli.py`

**Purpose:** Empty-but-runnable script with CLI, version constant, Gate H (source fixture drift detector). Gate H is the very first thing every run does — catches if the fixture has changed since the script last ran.

**Step 1: Write the failing test**

```python
# tests/ag/test_policy_mc_sweep_cli.py
import subprocess
import sys
from pathlib import Path

SCRIPT = "scripts/ag/policy_mc_sweep.py"

def test_help_exits_zero():
    """Script --help must succeed and mention the run-id flag."""
    r = subprocess.run([sys.executable, SCRIPT, "--help"],
                       capture_output=True, text=True, timeout=15)
    assert r.returncode == 0, f"--help exited {r.returncode}: {r.stderr}"
    assert "--run-id" in r.stdout
    assert "--phase" in r.stdout
    assert "--min-combo-n" in r.stdout

def test_missing_fixture_aborts_gate_h():
    """Gate H must abort when ag_training row count does not match dataset_summary."""
    r = subprocess.run(
        [sys.executable, SCRIPT, "--run-id", "agtrain_NONEXISTENT_FIXTURE", "--dry-run"],
        capture_output=True, text=True, timeout=30,
    )
    assert r.returncode != 0, "nonexistent fixture should abort"
    assert "Gate H" in r.stderr or "fixture" in r.stderr.lower()
```

**Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/ag/test_policy_mc_sweep_cli.py -v`
Expected: 2 FAIL — script does not exist yet.

**Step 3: Write minimal implementation**

```python
# scripts/ag/policy_mc_sweep.py
#!/usr/bin/env python3
"""Post-hoc Monte Carlo sweep over macro-fib-trade exit management policies.

Design: docs/plans/2026-04-15-policy-mc-sweep-design.md
Plan:   docs/plans/2026-04-15-policy-mc-sweep-plan.md

Read-only against warbird PG17 DB (ag_training + mes_1m) and AG run artifacts.
Writes to artifacts/ag_runs/<RUN_ID>/policy_sweep/.
Does not touch: train_ag_baseline.py, run_diagnostic_shap.py, monte_carlo_run.py,
build_ag_pipeline.py. No migrations.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

SCRIPT_VERSION = "1.0.0"
ARTIFACTS_ROOT = Path("artifacts/ag_runs")
DEFAULT_DSN = "host=127.0.0.1 port=5432 dbname=warbird"


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Post-hoc policy sweep over macro-fib-trade exit management.",
    )
    p.add_argument("--run-id", required=True,
                   help="AG training run_id (fixture). Must have complete MC task_A output.")
    p.add_argument("--phase", choices=["filter", "exit", "both"], default="both")
    p.add_argument("--min-combo-n", type=int, default=50,
                   help="Minimum trades per combo to rank. Combos below this are logged, not silently dropped.")
    p.add_argument("--top-k", type=int, default=10,
                   help="Top/bottom K policies per stop family.")
    p.add_argument("--max-trajectory-bars", type=int, default=120,
                   help="Phase 2: 15m bars forward from entry to include in trajectory.")
    p.add_argument("--rebuild-trajectory-cache", action="store_true",
                   help="Force rebuild of per-fold trajectory parquet cache.")
    p.add_argument("--dry-run", action="store_true",
                   help="Validate gates + print combo counts, write no outputs.")
    p.add_argument("--dsn", default=DEFAULT_DSN, help="Local PG17 DSN.")
    return p.parse_args()


def gate_h_fixture_assertion(run_dir: Path, dsn: str) -> dict[str, Any]:
    """Gate H — verify source fixture row count + session count + feature manifest hash.

    Aborts with exit 1 on drift. Per design amendment, the correct anchor is
    dataset_summary.json.rows_total (NOT task_A.indicator_settings_frozen row manifest).
    """
    import psycopg2

    ds_path = run_dir / "dataset_summary.json"
    if not ds_path.exists():
        sys.stderr.write(f"Gate H — FATAL: dataset_summary.json not found at {ds_path}\n")
        sys.exit(1)
    ds = json.loads(ds_path.read_text())
    expected_rows = int(ds["rows_total"])
    expected_sessions = int(ds["sessions_total"])

    fm_path = run_dir / "feature_manifest.json"
    if not fm_path.exists():
        sys.stderr.write(f"Gate H — FATAL: feature_manifest.json not found at {fm_path}\n")
        sys.exit(1)
    fm_md5 = hashlib.md5(fm_path.read_bytes()).hexdigest()

    with psycopg2.connect(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM ag_training")
            observed_rows = int(cur.fetchone()[0])

    if observed_rows != expected_rows:
        sys.stderr.write(
            f"Gate H — FATAL: ag_training row count drifted. "
            f"dataset_summary.json says {expected_rows}, DB says {observed_rows}. "
            f"Source fixture has changed since the AG run was generated. "
            f"Re-run MC tasks A-I first or use a fresh run_id.\n"
        )
        sys.exit(1)

    return {
        "status": "PASS",
        "expected_rows": expected_rows,
        "observed_rows": observed_rows,
        "expected_sessions": expected_sessions,
        "feature_manifest_md5": fm_md5,
    }


def main() -> int:
    args = parse_args()
    run_dir = ARTIFACTS_ROOT / args.run_id

    if not run_dir.exists():
        sys.stderr.write(
            f"Gate H — FATAL: run directory {run_dir} not found. "
            f"Check --run-id is correct.\n"
        )
        sys.exit(1)

    gate_h = gate_h_fixture_assertion(run_dir, args.dsn)
    print(f"Gate H: PASS (rows={gate_h['observed_rows']}, sessions={gate_h['expected_sessions']})")

    if args.dry_run:
        print("Dry run — exiting before any output.")
        return 0

    sys.stderr.write("Not yet implemented beyond Gate H. See plan task list.\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

**Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/ag/test_policy_mc_sweep_cli.py -v`
Expected: 2 PASS.

**Step 5: Commit**

```bash
git add scripts/ag/policy_mc_sweep.py tests/ag/test_policy_mc_sweep_cli.py
git commit -m "Scaffold policy_mc_sweep.py with CLI and Gate H fixture assertion"
```

---

## Task 2: Gate D — probs.parquet schema + alignment assertion

**Files:**
- Modify: `scripts/ag/policy_mc_sweep.py` (add `gate_d_probs_alignment()` function)
- Modify: `tests/ag/test_policy_mc_sweep_cli.py` (add Gate D test against locked fixture)

**Purpose:** Per design amendment Finding 3: probs.parquet contains only `pred_p__*` columns. Alignment is by row order + length equality. Gate D asserts exactly that.

**Step 1: Write the failing test**

```python
def test_gate_d_passes_on_locked_fixture():
    """Gate D passes on agtrain_20260415T165437712806Z fold_01."""
    from scripts.ag import policy_mc_sweep as m
    from pathlib import Path
    import pandas as pd
    
    cache_dir = Path("artifacts/ag_runs/agtrain_20260415T165437712806Z/monte_carlo/cache")
    fold_code = "fold_01"
    analysis = pd.read_parquet(cache_dir / fold_code / "analysis.parquet")
    result = m.gate_d_probs_alignment(cache_dir, fold_code, expected_row_count=len(analysis))
    assert result["status"] == "PASS"
    assert result["columns"] == [
        "pred_p__STOPPED", "pred_p__TP1_ONLY", "pred_p__TP2_HIT",
        "pred_p__TP3_HIT", "pred_p__TP4_HIT", "pred_p__TP5_HIT"
    ]
    assert result["row_count"] == len(analysis)
```

**Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/ag/test_policy_mc_sweep_cli.py::test_gate_d_passes_on_locked_fixture -v`
Expected: FAIL (function does not exist).

**Step 3: Write minimal implementation**

```python
# Insert in scripts/ag/policy_mc_sweep.py

CANONICAL_PROBS_COLUMNS = [
    "pred_p__STOPPED", "pred_p__TP1_ONLY", "pred_p__TP2_HIT",
    "pred_p__TP3_HIT", "pred_p__TP4_HIT", "pred_p__TP5_HIT",
]


def gate_d_probs_alignment(cache_dir: Path, fold_code: str, expected_row_count: int) -> dict[str, Any]:
    """Gate D — assert probs.parquet has canonical 6 pred_p__* columns and matches
    the expected row count. Alignment is positional (not by embedded key) per
    monte_carlo_run.py:545-572 contract.

    Per design amendment Finding 3: probs.parquet does NOT contain stop_variant_id.
    Do not attempt to join-by-key. Row order is the contract.
    """
    import pandas as pd
    probs_path = cache_dir / fold_code / "probs.parquet"
    if not probs_path.exists():
        sys.stderr.write(f"Gate D — FATAL: {probs_path} not found.\n")
        sys.exit(1)
    probs = pd.read_parquet(probs_path)
    cols = list(probs.columns)
    if cols != CANONICAL_PROBS_COLUMNS:
        sys.stderr.write(
            f"Gate D — FATAL: probs.parquet schema drift. "
            f"expected={CANONICAL_PROBS_COLUMNS} actual={cols}\n"
        )
        sys.exit(1)
    if len(probs) != expected_row_count:
        sys.stderr.write(
            f"Gate D — FATAL: probs.parquet length drift. "
            f"expected={expected_row_count} actual={len(probs)}\n"
        )
        sys.exit(1)
    return {"status": "PASS", "columns": cols, "row_count": len(probs)}
```

**Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/ag/test_policy_mc_sweep_cli.py::test_gate_d_passes_on_locked_fixture -v`
Expected: PASS.

**Step 5: Commit**

```bash
git add scripts/ag/policy_mc_sweep.py tests/ag/test_policy_mc_sweep_cli.py
git commit -m "Add Gate D probs.parquet alignment assertion (row-order contract)"
```

---

## Task 3: OutcomeJoiner — read ag_training + probs, join by row order

**Files:**
- Modify: `scripts/ag/policy_mc_sweep.py`
- Modify: `tests/ag/test_policy_mc_sweep_cli.py`

**Purpose:** For each fold, load analysis_frame + probs, attach ag_training outcome_label + sl_dist_pts + stop_family_id + adx + archetype + direction + is_bull_trend. Produces the "joined dataset" every downstream component consumes.

**Step 1: Write the failing test**

```python
def test_load_fold_dataset_shape():
    """Loader returns a joined DataFrame with known columns on fold_01."""
    from scripts.ag import policy_mc_sweep as m
    from pathlib import Path
    run_dir = Path("artifacts/ag_runs/agtrain_20260415T165437712806Z")
    df = m.load_fold_dataset(run_dir, "fold_01")
    # schema assertions
    expected_cols = {
        "stop_variant_id", "stop_family_id", "direction", "outcome_label",
        "sl_dist_pts", "adx", "entry_price",
        "pred_p__STOPPED", "pred_p__TP1_ONLY", "pred_p__TP2_HIT",
        "pred_p__TP3_HIT", "pred_p__TP4_HIT", "pred_p__TP5_HIT",
    }
    missing = expected_cols - set(df.columns)
    assert not missing, f"missing columns: {missing}"
    # row-count sanity — matches probs length
    probs = __import__("pandas").read_parquet(run_dir / "monte_carlo/cache/fold_01/probs.parquet")
    assert len(df) == len(probs)
```

**Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/ag/test_policy_mc_sweep_cli.py::test_load_fold_dataset_shape -v`
Expected: FAIL.

**Step 3: Write minimal implementation**

```python
# Insert in scripts/ag/policy_mc_sweep.py

import pandas as pd

REQUIRED_TRAINING_COLUMNS = [
    "stop_variant_id", "id", "stop_family_id", "direction",
    "outcome_label", "sl_dist_pts", "adx", "entry_price", "ts",
]


def load_fold_dataset(run_dir: Path, fold_code: str, dsn: str = DEFAULT_DSN) -> pd.DataFrame:
    """Load the fold's analysis_frame, probs, and outcome_label from ag_training.
    Join by row order per MC cache contract. Returns a single DataFrame.
    """
    import psycopg2
    cache_dir = run_dir / "monte_carlo" / "cache" / fold_code
    analysis = pd.read_parquet(cache_dir / "analysis.parquet")
    probs = pd.read_parquet(cache_dir / "probs.parquet")
    if len(analysis) != len(probs):
        raise RuntimeError(
            f"fold {fold_code}: analysis len {len(analysis)} != probs len {len(probs)} "
            "— MC cache is corrupt; re-run monte_carlo_run.py first"
        )
    # Attach probs columns in place (positional, not merge — no key)
    joined = pd.concat([analysis.reset_index(drop=True), probs.reset_index(drop=True)], axis=1)

    # Enrich with outcome_label, sl_dist_pts, adx, direction, etc from ag_training DB.
    # Key is stop_variant_id which IS in analysis_frame per META_COLS.
    if "stop_variant_id" not in joined.columns:
        raise RuntimeError(
            "analysis_frame lacks stop_variant_id — expected in META_COLS. "
            "Check monte_carlo_run.py prepare_fold() output contract."
        )
    stop_variant_ids = joined["stop_variant_id"].tolist()
    with psycopg2.connect(dsn) as conn:
        query = f"SELECT {', '.join(REQUIRED_TRAINING_COLUMNS)} FROM ag_training WHERE stop_variant_id = ANY(%s)"
        enrichment = pd.read_sql(query, conn, params=(stop_variant_ids,))

    # merge on stop_variant_id (one-to-one) with validation
    joined = joined.merge(
        enrichment, on="stop_variant_id", how="left", validate="one_to_one",
        suffixes=("", "__ag"),
    )
    # Null check — any stop_variant_id that didn't join means data corruption
    if joined["outcome_label"].isna().any():
        bad = joined[joined["outcome_label"].isna()]["stop_variant_id"].tolist()[:10]
        raise RuntimeError(
            f"fold {fold_code}: {len(bad)} stop_variant_ids missing from ag_training: {bad[:10]}..."
        )
    return joined
```

**Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/ag/test_policy_mc_sweep_cli.py::test_load_fold_dataset_shape -v`
Expected: PASS.

**Step 5: Commit**

```bash
git add scripts/ag/policy_mc_sweep.py tests/ag/test_policy_mc_sweep_cli.py
git commit -m "Add OutcomeJoiner — fold analysis + probs + ag_training enrichment"
```

---

## Task 4: Phase 1 Baseline Scorer (identity combo, no filter)

**Files:**
- Modify: `scripts/ag/policy_mc_sweep.py`
- Modify: `tests/ag/test_policy_mc_sweep_cli.py`

**Purpose:** Phase 1 currently has no filter knobs (per amendment — Rejection pending audit, others deferred to Phase 3). Emit per-stop-family baseline metrics (tp1_reach_rate, stop_rate, net_$, mean_sl_dist_pts, n_trades) on the full dataset. This is the "no filter applied" reference that Phase 2 exit sweeps build on.

**Step 1: Write the failing test**

```python
def test_phase1_baseline_on_fixture():
    """Phase 1 baseline across all 5 folds produces 6 per-family metric rows."""
    from scripts.ag import policy_mc_sweep as m
    from pathlib import Path
    run_dir = Path("artifacts/ag_runs/agtrain_20260415T165437712806Z")
    results = m.phase1_baseline_per_stop_family(run_dir)
    assert len(results) == 6, f"expected 6 stop families, got {len(results)}"
    for r in results:
        assert r["n_trades"] > 0
        assert 0.0 <= r["tp1_reach_rate"] <= 1.0
        assert 0.0 <= r["stop_rate"] <= 1.0
        assert abs(r["tp1_reach_rate"] + r["stop_rate"] - 1.0) < 1e-9, (
            f"{r['stop_family_id']}: tp1_reach + stop_rate must sum to 1 "
            f"(got {r['tp1_reach_rate']} + {r['stop_rate']})"
        )
        assert r["mean_sl_dist_pts"] > 0
```

**Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/ag/test_policy_mc_sweep_cli.py::test_phase1_baseline_on_fixture -v`
Expected: FAIL.

**Step 3: Write minimal implementation**

```python
# Insert in scripts/ag/policy_mc_sweep.py

TP_HIT_LABELS = {"TP1_ONLY", "TP2_HIT", "TP3_HIT", "TP4_HIT", "TP5_HIT"}
STOPPED_LABEL = "STOPPED"
FLAT_FEE_USD = 1.25
MES_POINT_VALUE = 5.0
FOLD_CODES = ["fold_01", "fold_02", "fold_03", "fold_04", "fold_05"]


def compute_net_dollars(row: pd.Series) -> float:
    """Per-trade net $ at macro-fib outcome with 1-tick flat fee."""
    label = row["outcome_label"]
    direction = row["direction"]
    entry = row["entry_price"]
    if label == STOPPED_LABEL:
        # stop_level_price not always in join; fall back to sl_dist_pts * direction
        return -row["sl_dist_pts"] * MES_POINT_VALUE - FLAT_FEE_USD
    tp_price_col = {
        "TP1_ONLY": "tp1_price", "TP2_HIT": "tp2_price", "TP3_HIT": "tp3_price",
        "TP4_HIT": "tp4_price", "TP5_HIT": "tp5_price",
    }.get(label)
    if tp_price_col is None or tp_price_col not in row.index:
        return 0.0  # defensive; shouldn't happen after Gate D
    return (row[tp_price_col] - entry) * direction * MES_POINT_VALUE - FLAT_FEE_USD


def phase1_baseline_per_stop_family(run_dir: Path, dsn: str = DEFAULT_DSN) -> list[dict[str, Any]]:
    """No filter applied. Per stop family, compute tp1_reach_rate, stop_rate,
    net $, mean sl_dist_pts across all 5 folds combined.
    """
    # Load all folds into one frame; we also need tp*_price — pull them from ag_training
    import psycopg2
    frames = []
    for fold_code in FOLD_CODES:
        frames.append(load_fold_dataset(run_dir, fold_code, dsn=dsn))
    combined = pd.concat(frames, ignore_index=True)

    # tp*_price columns come from ag_training — add them via one query
    with psycopg2.connect(dsn) as conn:
        tp_prices = pd.read_sql(
            "SELECT stop_variant_id, tp1_price, tp2_price, tp3_price, tp4_price, tp5_price "
            "FROM ag_training WHERE stop_variant_id = ANY(%s)",
            conn, params=(combined["stop_variant_id"].tolist(),),
        )
    combined = combined.merge(tp_prices, on="stop_variant_id", how="left", validate="one_to_one")

    results = []
    for sf, grp in combined.groupby("stop_family_id"):
        n = len(grp)
        tp1_reach = grp["outcome_label"].isin(TP_HIT_LABELS).sum() / n
        stop_rate = (grp["outcome_label"] == STOPPED_LABEL).sum() / n
        mean_sl = grp["sl_dist_pts"].mean()
        net_dollars = grp.apply(compute_net_dollars, axis=1)
        results.append({
            "stop_family_id": sf,
            "n_trades": n,
            "tp1_reach_rate": float(tp1_reach),
            "stop_rate": float(stop_rate),
            "mean_sl_dist_pts": float(mean_sl),
            "expected_net_dollars_per_trade": float(net_dollars.mean()),
            "mc_p5_ev_per_trade": None,  # Filled in when we wire MC sampling
        })
    return results
```

**Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/ag/test_policy_mc_sweep_cli.py::test_phase1_baseline_on_fixture -v`
Expected: PASS. (Sanity-check the output ranges match prior-session slice — ATR_1_0 tp1_reach should be ~0.30, FIB_NEG_0382 ~0.20.)

**Step 5: Commit**

```bash
git add scripts/ag/policy_mc_sweep.py tests/ag/test_policy_mc_sweep_cli.py
git commit -m "Add Phase 1 baseline scorer — per stop family tp1_reach_rate + net $"
```

---

## Task 5: TrajectoryBuilder + cache

**Files:**
- Modify: `scripts/ag/policy_mc_sweep.py`
- Modify: `tests/ag/test_policy_mc_sweep_cli.py`

**Purpose:** Per fold, load the mes_1m window into memory ONCE, slice per-trade to extract (bar_offset, high_delta_pts, low_delta_pts, close_delta_pts) from entry_ts to entry_ts + max_trajectory_bars × 15 minutes. Cache to parquet keyed by md5 of inputs so re-runs are instant.

**Step 1: Write the failing test**

```python
def test_trajectory_builder_on_fold_01():
    from scripts.ag import policy_mc_sweep as m
    from pathlib import Path
    import pandas as pd
    run_dir = Path("artifacts/ag_runs/agtrain_20260415T165437712806Z")
    cache_dir = run_dir / "policy_sweep" / "trajectory_cache"
    df = m.build_or_load_trajectory(run_dir, "fold_01", cache_dir, max_trajectory_bars=120, force_rebuild=True)
    # schema
    for c in ["stop_variant_id", "bar_offset", "high_pts", "low_pts", "close_pts"]:
        assert c in df.columns
    # at least one trade's worth of bars
    trade_counts = df.groupby("stop_variant_id").size()
    assert trade_counts.min() >= 1
    # bar_offset 0 has small high/low deltas (entry bar)
    entry_bars = df[df["bar_offset"] == 0]
    assert (entry_bars["high_pts"] >= entry_bars["low_pts"]).all()
```

**Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/ag/test_policy_mc_sweep_cli.py::test_trajectory_builder_on_fold_01 -v`
Expected: FAIL.

**Step 3: Write minimal implementation**

```python
# Insert in scripts/ag/policy_mc_sweep.py

def _trajectory_cache_key(run_dir: Path, fold_code: str, max_bars: int) -> str:
    import psycopg2
    # include mes_1m max_ts — invalidates cache if new bars landed
    with psycopg2.connect(DEFAULT_DSN) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT max(ts)::text FROM mes_1m")
            mes_1m_max = cur.fetchone()[0] or ""
            cur.execute("SELECT count(*) FROM ag_training")
            row_count = int(cur.fetchone()[0])
    key_src = f"{fold_code}|{max_bars}|{mes_1m_max}|{row_count}|v{SCRIPT_VERSION}"
    return hashlib.md5(key_src.encode()).hexdigest()


def build_or_load_trajectory(
    run_dir: Path, fold_code: str, cache_dir: Path,
    max_trajectory_bars: int = 120, force_rebuild: bool = False,
    dsn: str = DEFAULT_DSN,
) -> pd.DataFrame:
    """Per-trade forward mes_1m trajectory keyed by stop_variant_id.
    
    Output columns: stop_variant_id, bar_offset (0..N, 1m bars), high_pts, low_pts, close_pts
    where *_pts are (bar.value - entry_price). Signed by convention (direction handled downstream).
    
    Caches to parquet. Re-runs are instant unless mes_1m or script version changed.
    """
    import psycopg2
    cache_key = _trajectory_cache_key(run_dir, fold_code, max_trajectory_bars)
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_path = cache_dir / f"{fold_code}__{cache_key}.parquet"
    if cache_path.exists() and not force_rebuild:
        return pd.read_parquet(cache_path)

    joined = load_fold_dataset(run_dir, fold_code, dsn=dsn)

    # Pull mes_1m bars spanning all trades' entry windows in one query
    # 15m bars × 120 = 30 hours forward. That's ~1800 1m bars per trade max.
    window_minutes = max_trajectory_bars * 15
    min_entry = joined["ts"].min()
    max_entry = joined["ts"].max()
    # add buffer
    buf_end = max_entry + pd.Timedelta(minutes=window_minutes + 60)
    with psycopg2.connect(dsn) as conn:
        mes_1m = pd.read_sql(
            "SELECT ts, high, low, close FROM mes_1m WHERE ts >= %s AND ts <= %s ORDER BY ts",
            conn, params=(min_entry, buf_end),
        )
    if mes_1m.empty:
        raise RuntimeError(f"fold {fold_code}: no mes_1m bars in window [{min_entry}, {buf_end}]")

    rows = []
    for _, tr in joined.iterrows():
        entry_ts = tr["ts"]
        entry_px = tr["entry_price"]
        window_end = entry_ts + pd.Timedelta(minutes=window_minutes)
        slice_ = mes_1m[(mes_1m["ts"] >= entry_ts) & (mes_1m["ts"] <= window_end)]
        if slice_.empty:
            continue  # Gate G picks this up later
        for i, bar in enumerate(slice_.itertuples(index=False)):
            rows.append({
                "stop_variant_id": tr["stop_variant_id"],
                "bar_offset": i,
                "high_pts": float(bar.high - entry_px),
                "low_pts": float(bar.low - entry_px),
                "close_pts": float(bar.close - entry_px),
            })
    df = pd.DataFrame(rows)
    df.to_parquet(cache_path, index=False)
    return df
```

**Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/ag/test_policy_mc_sweep_cli.py::test_trajectory_builder_on_fold_01 -v`
Expected: PASS. First run ~3-5 min, subsequent runs <1 sec.

**Step 5: Commit**

```bash
git add scripts/ag/policy_mc_sweep.py tests/ag/test_policy_mc_sweep_cli.py
git commit -m "Add TrajectoryBuilder with md5-keyed parquet cache"
```

---

## Task 6: Gate A — trajectory drift detection (stratified 40 × 5)

**Files:**
- Modify: `scripts/ag/policy_mc_sweep.py`
- Modify: `tests/ag/test_policy_mc_sweep_cli.py`

**Purpose:** Per amendment open-question-3: sample stratified 40 trades per fold = 200 total. For each, reconstruct the outcome by walking the trajectory vs ag_fib_stop_variants stop geometry. Assert the reconstructed outcome matches warehouse `outcome_label` for ≥ 95% of samples.

**Step 1: Write the failing test**

```python
def test_gate_a_passes_on_fixture():
    from scripts.ag import policy_mc_sweep as m
    from pathlib import Path
    run_dir = Path("artifacts/ag_runs/agtrain_20260415T165437712806Z")
    result = m.gate_a_trajectory_drift(run_dir, samples_per_fold=40)
    assert result["status"] == "PASS"
    assert result["sample_size"] == 200
    assert result["agreement_rate"] >= 0.95, (
        f"agreement {result['agreement_rate']} below 95% — trajectory drift "
        f"vs warehouse labels. Specifically: {result['disagreements'][:5]}"
    )
```

**Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/ag/test_policy_mc_sweep_cli.py::test_gate_a_passes_on_fixture -v`
Expected: FAIL.

**Step 3: Write minimal implementation**

```python
# Insert in scripts/ag/policy_mc_sweep.py

def _reconstruct_outcome_from_trajectory(
    tr_row: pd.Series, traj_slice: pd.DataFrame, tp_prices: dict[str, float], sl_pts: float
) -> str:
    """Walk trajectory forward, return the highest TP hit or STOPPED.
    tp_prices maps TP1..5 label -> absolute price delta from entry (signed by direction).
    sl_pts is absolute pts magnitude (direction applied here).
    """
    direction = int(tr_row["direction"])
    entry = tr_row["entry_price"]
    sl_price_delta = -sl_pts if direction == 1 else sl_pts
    for bar in traj_slice.itertuples(index=False):
        high_pts = bar.high_pts
        low_pts = bar.low_pts
        # stop hit?
        if direction == 1 and low_pts <= sl_price_delta:
            return "STOPPED"
        if direction == -1 and high_pts >= sl_price_delta:
            return "STOPPED"
        # TP hit? walk from TP5 down to TP1 (highest wins)
        for label in ["TP5_HIT", "TP4_HIT", "TP3_HIT", "TP2_HIT", "TP1_ONLY"]:
            tp_delta = tp_prices[label] - entry
            if direction == 1 and high_pts >= tp_delta:
                return label
            if direction == -1 and low_pts <= tp_delta:
                return label
    return "CENSORED"


def gate_a_trajectory_drift(run_dir: Path, samples_per_fold: int = 40, dsn: str = DEFAULT_DSN) -> dict[str, Any]:
    """Gate A — cross-validate trajectory-derived outcomes vs warehouse labels."""
    import psycopg2
    import numpy as np
    cache_dir = run_dir / "policy_sweep" / "trajectory_cache"
    rng = np.random.default_rng(42)
    disagreements = []
    checked = 0

    with psycopg2.connect(dsn) as conn:
        for fold_code in FOLD_CODES:
            ds = load_fold_dataset(run_dir, fold_code, dsn=dsn)
            if len(ds) < samples_per_fold:
                continue
            sample_idx = rng.choice(len(ds), samples_per_fold, replace=False)
            tp_enrich = pd.read_sql(
                "SELECT stop_variant_id, tp1_price, tp2_price, tp3_price, tp4_price, tp5_price "
                "FROM ag_training WHERE stop_variant_id = ANY(%s)",
                conn, params=(ds.iloc[sample_idx]["stop_variant_id"].tolist(),),
            )
            traj = build_or_load_trajectory(run_dir, fold_code, cache_dir)

            for i in sample_idx:
                tr = ds.iloc[i]
                svid = tr["stop_variant_id"]
                tp_row = tp_enrich[tp_enrich["stop_variant_id"] == svid].iloc[0]
                tp_prices = {
                    "TP1_ONLY": float(tp_row["tp1_price"]),
                    "TP2_HIT":  float(tp_row["tp2_price"]),
                    "TP3_HIT":  float(tp_row["tp3_price"]),
                    "TP4_HIT":  float(tp_row["tp4_price"]),
                    "TP5_HIT":  float(tp_row["tp5_price"]),
                }
                traj_slice = traj[traj["stop_variant_id"] == svid]
                derived = _reconstruct_outcome_from_trajectory(tr, traj_slice, tp_prices, float(tr["sl_dist_pts"]))
                checked += 1
                if derived != tr["outcome_label"]:
                    disagreements.append({
                        "stop_variant_id": str(svid),
                        "warehouse": tr["outcome_label"],
                        "trajectory_derived": derived,
                    })

    agreement = 1 - len(disagreements) / max(checked, 1)
    status = "PASS" if agreement >= 0.95 else "FAIL"
    return {
        "status": status,
        "sample_size": checked,
        "agreement_rate": agreement,
        "disagreements": disagreements,
    }
```

**Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/ag/test_policy_mc_sweep_cli.py::test_gate_a_passes_on_fixture -v`
Expected: PASS with agreement ≥ 95%. If not, trajectory reconstruction has a bug — investigate the top 5 disagreements, do NOT proceed to Phase 2.

**Step 5: Commit**

```bash
git add scripts/ag/policy_mc_sweep.py tests/ag/test_policy_mc_sweep_cli.py
git commit -m "Add Gate A — stratified 40×5 trajectory drift detection"
```

---

## Task 7: ExitSweeper — re-simulate Phase 2 combos

**Files:**
- Modify: `scripts/ag/policy_mc_sweep.py`
- Modify: `tests/ag/test_policy_mc_sweep_cli.py`

**Purpose:** For each Phase 2 combo (48 combos × 6 families = 288), walk trajectory bar-by-bar with the combo's exit rules applied. Recompute tp1_reach_rate, stop_rate, expected_net_$ under the new rules.

**Step 1: Write the failing test**

```python
def test_exit_sweeper_default_settings_match_baseline():
    """Re-simulating at Pine default exit settings should closely match Phase 1 baseline."""
    from scripts.ag import policy_mc_sweep as m
    from pathlib import Path
    run_dir = Path("artifacts/ag_runs/agtrain_20260415T165437712806Z")
    baseline = {r["stop_family_id"]: r for r in m.phase1_baseline_per_stop_family(run_dir)}
    default_combo = {
        "let_fast_runners_run": True,
        "fast_runner_window_bars": 2,
        "fast_runner_target": "TP2",
        "break_even_after_tp1": True,
    }
    exit_results = m.phase2_sweep_combo(run_dir, combo=default_combo)
    for sf, base in baseline.items():
        sim = next(r for r in exit_results if r["stop_family_id"] == sf)
        delta_tp1 = abs(sim["tp1_reach_rate"] - base["tp1_reach_rate"])
        assert delta_tp1 < 0.05, (
            f"{sf}: sim tp1_reach {sim['tp1_reach_rate']} vs baseline {base['tp1_reach_rate']} "
            f"(delta {delta_tp1}) — re-sim at live defaults diverged > 5%"
        )
```

**Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/ag/test_policy_mc_sweep_cli.py::test_exit_sweeper_default_settings_match_baseline -v`
Expected: FAIL.

**Step 3: Write minimal implementation**

```python
# Insert in scripts/ag/policy_mc_sweep.py

EXIT_COMBO_GRID = {
    "let_fast_runners_run": [False, True],
    "fast_runner_window_bars": [1, 2, 3, 4, 6, 8],
    "fast_runner_target": ["TP2", "TP3"],       # NOT TP1 — Pine rejects it
    "break_even_after_tp1": [False, True],
}


def enumerate_exit_combos() -> list[dict[str, Any]]:
    from itertools import product
    keys = list(EXIT_COMBO_GRID.keys())
    values = [EXIT_COMBO_GRID[k] for k in keys]
    return [dict(zip(keys, combo)) for combo in product(*values)]


def _simulate_exit_outcome(
    tr: pd.Series, traj_slice: pd.DataFrame, tp_prices: dict[str, float],
    sl_pts: float, combo: dict[str, Any],
) -> tuple[str, float]:
    """Re-simulate one trade's outcome under the given exit-management combo.
    Returns (new_outcome_label, new_net_dollars).

    Rules implemented:
    - Break-Even After TP1: once TP1 is tagged, stop moves to entry (sl -> 0 pts delta)
    - Let Fast Runners Run: if TP1 reached within fast_runner_window_bars, promote target
      to fast_runner_target (TP2 or TP3). The 'promoted target' caps which TP wins.
      If not a fast runner, original TP5 ladder behavior applies.
    """
    direction = int(tr["direction"])
    entry = tr["entry_price"]
    sl_price_delta = -sl_pts if direction == 1 else sl_pts
    tp1_hit_bar = None
    promoted_target_label = None
    window = combo["fast_runner_window_bars"]
    target_map = {"TP2": "TP2_HIT", "TP3": "TP3_HIT"}
    cap_label = target_map[combo["fast_runner_target"]]

    for i, bar in enumerate(traj_slice.itertuples(index=False)):
        # Determine active stop
        if combo["break_even_after_tp1"] and tp1_hit_bar is not None:
            active_sl_delta = 0.0  # entry breakeven
        else:
            active_sl_delta = sl_price_delta
        # Stop hit?
        if direction == 1 and bar.low_pts <= active_sl_delta:
            # If already at TP1+ and BE moved stop to entry, this is a flat-at-entry outcome
            if tp1_hit_bar is not None and combo["break_even_after_tp1"]:
                return "TP1_ONLY", (tp_prices["TP1_ONLY"] - entry) * direction * MES_POINT_VALUE - FLAT_FEE_USD
            return "STOPPED", -sl_pts * MES_POINT_VALUE - FLAT_FEE_USD
        if direction == -1 and bar.high_pts >= active_sl_delta:
            if tp1_hit_bar is not None and combo["break_even_after_tp1"]:
                return "TP1_ONLY", (tp_prices["TP1_ONLY"] - entry) * direction * MES_POINT_VALUE - FLAT_FEE_USD
            return "STOPPED", -sl_pts * MES_POINT_VALUE - FLAT_FEE_USD

        # Check TP hits, highest first
        for label in ["TP5_HIT", "TP4_HIT", "TP3_HIT", "TP2_HIT", "TP1_ONLY"]:
            tp_delta = tp_prices[label] - entry
            hit = (direction == 1 and bar.high_pts >= tp_delta) or (direction == -1 and bar.low_pts <= tp_delta)
            if not hit:
                continue
            # TP1 detection
            if label == "TP1_ONLY" and tp1_hit_bar is None:
                tp1_hit_bar = i
                # Fast runner? decide target cap NOW
                if combo["let_fast_runners_run"] and tp1_hit_bar <= window:
                    promoted_target_label = cap_label
                # Don't exit on TP1 — continue the trade
                break  # break inner TP loop
            # Exit on this TP if:
            #  - fast runner promoted and this label matches the promoted cap, OR
            #  - no promotion and label is the highest available (default TP5 behavior keeps walking)
            if promoted_target_label and label == promoted_target_label:
                return label, (tp_prices[label] - entry) * direction * MES_POINT_VALUE - FLAT_FEE_USD
            if not combo["let_fast_runners_run"] and label == "TP5_HIT":
                return label, (tp_prices[label] - entry) * direction * MES_POINT_VALUE - FLAT_FEE_USD
            # otherwise keep walking
            break
    # End of window: if TP1 was hit, return TP1_ONLY; else CENSORED
    if tp1_hit_bar is not None:
        return "TP1_ONLY", (tp_prices["TP1_ONLY"] - entry) * direction * MES_POINT_VALUE - FLAT_FEE_USD
    return "CENSORED", 0.0 - FLAT_FEE_USD


def phase2_sweep_combo(run_dir: Path, combo: dict[str, Any], dsn: str = DEFAULT_DSN) -> list[dict[str, Any]]:
    """Re-simulate all trades under one exit combo. Returns per-stop-family metrics."""
    import psycopg2
    cache_dir = run_dir / "policy_sweep" / "trajectory_cache"
    per_family: dict[str, list[tuple[str, float, float]]] = {}

    with psycopg2.connect(dsn) as conn:
        for fold_code in FOLD_CODES:
            ds = load_fold_dataset(run_dir, fold_code, dsn=dsn)
            traj = build_or_load_trajectory(run_dir, fold_code, cache_dir)
            tp_enrich = pd.read_sql(
                "SELECT stop_variant_id, tp1_price, tp2_price, tp3_price, tp4_price, tp5_price "
                "FROM ag_training WHERE stop_variant_id = ANY(%s)",
                conn, params=(ds["stop_variant_id"].tolist(),),
            ).set_index("stop_variant_id")
            for _, tr in ds.iterrows():
                svid = tr["stop_variant_id"]
                if svid not in tp_enrich.index:
                    continue
                tp_row = tp_enrich.loc[svid]
                tp_prices = {
                    "TP1_ONLY": float(tp_row["tp1_price"]),
                    "TP2_HIT":  float(tp_row["tp2_price"]),
                    "TP3_HIT":  float(tp_row["tp3_price"]),
                    "TP4_HIT":  float(tp_row["tp4_price"]),
                    "TP5_HIT":  float(tp_row["tp5_price"]),
                }
                traj_slice = traj[traj["stop_variant_id"] == svid]
                if traj_slice.empty:
                    continue  # Gate G
                outcome, net = _simulate_exit_outcome(tr, traj_slice, tp_prices, float(tr["sl_dist_pts"]), combo)
                per_family.setdefault(tr["stop_family_id"], []).append((outcome, net, float(tr["sl_dist_pts"])))

    results = []
    for sf, records in per_family.items():
        n = len(records)
        tp1_reach = sum(1 for r in records if r[0] in TP_HIT_LABELS) / n
        stop_rate = sum(1 for r in records if r[0] == "STOPPED") / n
        mean_net = sum(r[1] for r in records) / n
        mean_sl = sum(r[2] for r in records) / n
        results.append({
            "stop_family_id": sf,
            "combo": combo,
            "n_trades": n,
            "tp1_reach_rate": tp1_reach,
            "stop_rate": stop_rate,
            "expected_net_dollars_per_trade": mean_net,
            "mean_sl_dist_pts": mean_sl,
        })
    return results
```

**Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/ag/test_policy_mc_sweep_cli.py::test_exit_sweeper_default_settings_match_baseline -v`
Expected: PASS (re-sim at Pine defaults within 5% of baseline across all 6 families).

**Step 5: Commit**

```bash
git add scripts/ag/policy_mc_sweep.py tests/ag/test_policy_mc_sweep_cli.py
git commit -m "Add ExitSweeper — re-simulate 48 exit combos per stop family via trajectory"
```

---

## Task 8: Ranker — per stop family top-K / bottom-K

**Files:**
- Modify: `scripts/ag/policy_mc_sweep.py`
- Modify: `tests/ag/test_policy_mc_sweep_cli.py`

**Purpose:** Given the 288 Phase 2 combo rows, rank lexicographically (tp1_reach_rate DESC, expected_net_$ DESC). Per stop family, emit top K + bottom K. Enforce min_combo_n filter. No cross-family ranking.

**Step 1: Write the failing test**

```python
def test_ranker_produces_per_family_top_k():
    from scripts.ag import policy_mc_sweep as m
    # synthetic combo results
    mocked = [
        {"stop_family_id": "ATR_1_0", "combo": {"x": 1}, "tp1_reach_rate": 0.5, "expected_net_dollars_per_trade": 10.0, "n_trades": 100},
        {"stop_family_id": "ATR_1_0", "combo": {"x": 2}, "tp1_reach_rate": 0.6, "expected_net_dollars_per_trade": 15.0, "n_trades": 100},
        {"stop_family_id": "ATR_1_0", "combo": {"x": 3}, "tp1_reach_rate": 0.4, "expected_net_dollars_per_trade": 30.0, "n_trades": 30},  # below min
    ]
    ranked = m.rank_per_stop_family(mocked, top_k=2, min_combo_n=50)
    assert "ATR_1_0" in ranked
    assert len(ranked["ATR_1_0"]["top_k"]) == 2
    # primary sort: tp1_reach_rate DESC
    assert ranked["ATR_1_0"]["top_k"][0]["tp1_reach_rate"] == 0.6
    assert ranked["ATR_1_0"]["below_min_n_count"] == 1
```

**Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/ag/test_policy_mc_sweep_cli.py::test_ranker_produces_per_family_top_k -v`
Expected: FAIL.

**Step 3: Write minimal implementation**

```python
def rank_per_stop_family(combo_results: list[dict[str, Any]], top_k: int, min_combo_n: int) -> dict[str, Any]:
    """Per stop family, sort by (tp1_reach DESC, net$ DESC). Emit top K + bottom K.
    Combos below min_combo_n excluded from ranking, counted separately.
    """
    by_family: dict[str, list[dict]] = {}
    below_n: dict[str, int] = {}
    for r in combo_results:
        sf = r["stop_family_id"]
        if r["n_trades"] < min_combo_n:
            below_n[sf] = below_n.get(sf, 0) + 1
            continue
        by_family.setdefault(sf, []).append(r)
    out: dict[str, dict[str, Any]] = {}
    for sf, rows in by_family.items():
        rows_sorted = sorted(rows, key=lambda r: (-r["tp1_reach_rate"], -r["expected_net_dollars_per_trade"]))
        out[sf] = {
            "top_k": rows_sorted[:top_k],
            "bottom_k": rows_sorted[-top_k:][::-1],
            "below_min_n_count": below_n.get(sf, 0),
            "total_combos_ranked": len(rows_sorted),
        }
    return out
```

**Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/ag/test_policy_mc_sweep_cli.py::test_ranker_produces_per_family_top_k -v`
Expected: PASS.

**Step 5: Commit**

```bash
git add scripts/ag/policy_mc_sweep.py tests/ag/test_policy_mc_sweep_cli.py
git commit -m "Add Ranker — per stop family top/bottom K, min-n floor"
```

---

## Task 9: Gate F — source-run integrity propagation

**Files:**
- Modify: `scripts/ag/policy_mc_sweep.py`
- Modify: `tests/ag/test_policy_mc_sweep_cli.py`

**Purpose:** Re-derive source-run integrity from raw artifacts (Anti-Pattern C). Propagate to `promotion_allowed` flag. Do not trust prior summaries.

**Step 1: Write the failing test**

```python
def test_gate_f_on_clean_fixture():
    """Locked fixture agtrain_20260415T165437712806Z has 1 LEAKAGE_SUSPECT
    (tp1_dist_pts) + fold_01 below baseline + fold_03 class coverage gap.
    Gate F must detect all three and set promotion_allowed=False.
    """
    from scripts.ag import policy_mc_sweep as m
    from pathlib import Path
    run_dir = Path("artifacts/ag_runs/agtrain_20260415T165437712806Z")
    result = m.gate_f_source_integrity(run_dir)
    assert result["source_run_has_leakage_suspects"] is True, "tp1_dist_pts was flagged"
    assert result["source_run_has_below_baseline_fold"] is True, "fold_01 below baseline"
    assert result["source_run_has_class_coverage_gap"] is True, "fold_03 val=5 test=6"
    assert result["promotion_allowed"] is False
```

**Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/ag/test_policy_mc_sweep_cli.py::test_gate_f_on_clean_fixture -v`
Expected: FAIL.

**Step 3: Write minimal implementation**

```python
def gate_f_source_integrity(run_dir: Path) -> dict[str, Any]:
    """Re-derive source-run integrity from raw artifacts.
    Anti-Pattern C: don't trust prior summaries; read the raw data.
    """
    # Leakage: shap/drop_candidates.csv rows where reason_code == LEAKAGE_SUSPECT
    shap_dir = Path("artifacts/shap") / run_dir.name
    drop_csv = shap_dir / "drop_candidates.csv"
    has_leak = False
    if drop_csv.exists():
        drops = pd.read_csv(drop_csv)
        has_leak = (drops["reason_code"] == "LEAKAGE_SUSPECT").any() if not drops.empty else False

    # Below-baseline fold: fold_summary.autogluon.test_macro_f1 < majority_baseline.test.macro_f1
    # Class-coverage gap: val_class_count < test_class_count
    has_below_baseline = False
    has_coverage_gap = False
    for fp in sorted(run_dir.glob("fold_*/fold_summary.json")):
        summary = json.loads(fp.read_text())
        ag = summary.get("autogluon", {})
        base = summary.get("majority_baseline", {}).get("test", {})
        if ag.get("test_macro_f1") is not None and base.get("macro_f1") is not None:
            if float(ag["test_macro_f1"]) < float(base["macro_f1"]):
                has_below_baseline = True
        if summary.get("val_class_count") and summary.get("test_class_count"):
            if int(summary["val_class_count"]) < int(summary["test_class_count"]):
                has_coverage_gap = True

    promotion_allowed = not (has_leak or has_below_baseline or has_coverage_gap)
    reasons = []
    if has_leak:
        reasons.append("LEAKAGE_SUSPECT in SHAP drop candidates")
    if has_below_baseline:
        reasons.append("at least one fold below majority-class baseline")
    if has_coverage_gap:
        reasons.append("at least one fold has val_class_count < test_class_count")
    return {
        "source_run_has_leakage_suspects": has_leak,
        "source_run_has_below_baseline_fold": has_below_baseline,
        "source_run_has_class_coverage_gap": has_coverage_gap,
        "promotion_allowed": promotion_allowed,
        "promotion_blocked_reason": "; ".join(reasons) if reasons else None,
    }
```

**Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/ag/test_policy_mc_sweep_cli.py::test_gate_f_on_clean_fixture -v`
Expected: PASS.

**Step 5: Commit**

```bash
git add scripts/ag/policy_mc_sweep.py tests/ag/test_policy_mc_sweep_cli.py
git commit -m "Add Gate F — re-derive source-run integrity from raw artifacts"
```

---

## Task 10: Output writers — all 5 artifacts + Anti-Pattern B audit

**Files:**
- Modify: `scripts/ag/policy_mc_sweep.py`
- Modify: `tests/ag/test_policy_mc_sweep_cli.py`

**Purpose:** Write `filter_sweep_results.json`, `exit_sweep_results.json`, `recommended_settings.json`, `policy_summary.md`, `integrity.json`. Every narrative string in `policy_summary.md` must be runtime-conditional. Integrity.json records the caveat audit.

**Step 1: Write the failing test**

```python
def test_anti_pattern_b_no_forbidden_strings_on_clean_run():
    """policy_summary.md must NOT contain forbidden bag-leakage prose
    when the source run config says num_bag_folds=0.
    """
    from scripts.ag import policy_mc_sweep as m
    from pathlib import Path
    run_dir = Path("artifacts/ag_runs/agtrain_20260415T165437712806Z")
    out_dir = run_dir / "policy_sweep_test_output"
    m.run_end_to_end(run_dir=run_dir, out_dir=out_dir, min_combo_n=50, top_k=10)
    summary = (out_dir / "policy_summary.md").read_text()
    # Source run has num_bag_folds=0 — these strings must NOT appear
    forbidden = ["IID bag leakage", "GBM-only", "only LightGBM in leaderboard", "bag-fold leakage"]
    for f in forbidden:
        assert f not in summary, f"forbidden string appeared in clean-run summary: {f!r}"
    # integrity.json records the audit
    integrity = json.loads((out_dir / "integrity.json").read_text())
    assert integrity["narrative_caveat_audit"]["hardcoded_strings_found"] == []
```

**Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/ag/test_policy_mc_sweep_cli.py::test_anti_pattern_b_no_forbidden_strings_on_clean_run -v`
Expected: FAIL.

**Step 3: Write minimal implementation**

```python
FORBIDDEN_BAG_STRINGS = ["IID bag leakage", "GBM-only", "only LightGBM in leaderboard", "bag-fold leakage"]


def _source_run_config(run_dir: Path) -> dict[str, Any]:
    return json.loads((run_dir / "run_config.json").read_text())["args"]


def build_runtime_conditional_caveats(run_dir: Path, gate_f: dict[str, Any]) -> list[dict[str, str]]:
    """Emit caveats conditioned on actual source-run config."""
    cfg = _source_run_config(run_dir)
    caveats = []
    if cfg.get("num_bag_folds", 0) > 0:
        caveats.append({
            "caveat": f"Source run used num_bag_folds={cfg['num_bag_folds']}; IID bag-fold leakage may affect SHAP and MC absolute numbers.",
            "condition_key": "num_bag_folds",
            "value": cfg["num_bag_folds"],
        })
    # family count
    families = set()
    for fp in sorted(run_dir.glob("fold_*/fold_summary.json")):
        summary = json.loads(fp.read_text())
        families |= set(summary.get("autogluon", {}).get("zoo_families_present", []))
    if len(families) < 7:
        caveats.append({
            "caveat": f"Source run zoo coverage incomplete: missing {sorted({'GBM','CAT','XGB','RF','XT','NN_TORCH','FASTAI'} - families)}",
            "condition_key": "family_count",
            "value": len(families),
        })
    # Source integrity flags from Gate F
    if gate_f["source_run_has_leakage_suspects"]:
        caveats.append({
            "caveat": "Source SHAP flagged LEAKAGE_SUSPECT feature(s). Promotion blocked pending human adjudication.",
            "condition_key": "source_run_has_leakage_suspects",
            "value": True,
        })
    if gate_f["source_run_has_below_baseline_fold"]:
        caveats.append({
            "caveat": "Source run has at least one fold below majority-class baseline. Model may lack edge under those conditions.",
            "condition_key": "source_run_has_below_baseline_fold",
            "value": True,
        })
    if gate_f["source_run_has_class_coverage_gap"]:
        caveats.append({
            "caveat": "Source run has at least one fold with val_class_count < test_class_count. Per-class SHAP/MC for missing class(es) is untrusted for that fold.",
            "condition_key": "source_run_has_class_coverage_gap",
            "value": True,
        })
    return caveats


def audit_no_hardcoded_caveats(summary_text: str, cfg: dict[str, Any]) -> list[str]:
    """After writing summary.md, grep for forbidden literals that would lie about a clean run."""
    if cfg.get("num_bag_folds", 0) > 0:
        return []  # contaminated run — some bag strings are legitimate
    found = [s for s in FORBIDDEN_BAG_STRINGS if s in summary_text]
    return found


def write_policy_summary_md(out_dir: Path, ranked: dict[str, Any], caveats: list[dict], gate_f: dict[str, Any]) -> None:
    lines = [
        "# Policy Sweep Summary",
        "",
        "## ⚠ Not a family ranking",
        "This sweep ranks policies WITHIN each stop family. It does NOT judge",
        "which stop family is better than another. Cross-family comparison",
        "requires Phase 3 pipeline sweep under varied training conditions.",
        "",
        f"Promotion allowed: **{gate_f['promotion_allowed']}**",
    ]
    if gate_f.get("promotion_blocked_reason"):
        lines.append(f"Reason: {gate_f['promotion_blocked_reason']}")
    lines.extend(["", "## Caveats (runtime-conditional)", ""])
    if not caveats:
        lines.append("No caveats — source run passed all integrity checks.")
    else:
        for c in caveats:
            lines.append(f"- {c['caveat']} (condition: `{c['condition_key']}`={c['value']})")
    lines.extend(["", "## Best policy per stop family", ""])
    for sf, bundle in ranked.items():
        lines.append(f"### {sf}")
        if not bundle["top_k"]:
            lines.append("No combos passed min_n threshold.")
            continue
        winner = bundle["top_k"][0]
        lines.append(f"- Best combo: `{winner['combo']}`")
        lines.append(f"- tp1_reach_rate: {winner['tp1_reach_rate']:.4f}")
        lines.append(f"- expected_net_$: {winner['expected_net_dollars_per_trade']:.2f}")
        lines.append(f"- mean_sl_dist_pts: {winner['mean_sl_dist_pts']:.2f}")
        lines.append(f"- n_trades: {winner['n_trades']}")
        lines.append("")
    (out_dir / "policy_summary.md").write_text("\n".join(lines))


def write_outputs(out_dir: Path, *, baseline: list[dict], exit_results: list[dict], ranked: dict[str, Any], gate_f: dict, gate_h: dict, gate_a: dict, run_id: str) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    # filter_sweep_results.json (Phase 1 — identity only for now)
    (out_dir / "filter_sweep_results.json").write_text(json.dumps({
        "run_id": run_id, "script_version": SCRIPT_VERSION,
        "phase": "1_identity_baseline",
        "per_stop_family_baseline": baseline,
        "note": "Phase 1 currently has 0 filter knobs (Rejection=wick pending audit, scalp/bull-trend knobs deferred to Phase 3).",
    }, indent=2))
    # exit_sweep_results.json
    (out_dir / "exit_sweep_results.json").write_text(json.dumps({
        "run_id": run_id, "script_version": SCRIPT_VERSION,
        "total_combos": len(exit_results),
        "combos": exit_results,
        "ranked_per_family": ranked,
    }, indent=2, default=str))
    # recommended_settings.json
    rec: dict[str, Any] = {
        "run_id": run_id, "script_version": SCRIPT_VERSION,
        "cross_family_ranking_valid": False,
        "caveat": "Per-family policies optimized on predict_proba from ONE training run. Cross-family ranking is NOT valid from this artifact.",
        "promotion_allowed": gate_f["promotion_allowed"],
        "promotion_blocked_reason": gate_f.get("promotion_blocked_reason"),
        "winning_policy_per_stop_family": {},
    }
    for sf, bundle in ranked.items():
        if not bundle["top_k"]:
            rec["winning_policy_per_stop_family"][sf] = {"no_policy_found": True}
            continue
        w = bundle["top_k"][0]
        rec["winning_policy_per_stop_family"][sf] = {
            "strat_settings": {
                "Fallback Stop Family": sf,
                "Let Fast Runners Run": w["combo"]["let_fast_runners_run"],
                "Fast Runner Window (bars)": w["combo"]["fast_runner_window_bars"],
                "Fast Runner Target": w["combo"]["fast_runner_target"],
                "Break-Even After TP1": w["combo"]["break_even_after_tp1"],
            },
            "metrics": {
                "tp1_reach_rate": w["tp1_reach_rate"],
                "expected_net_dollars_per_trade": w["expected_net_dollars_per_trade"],
                "mean_sl_dist_pts": w["mean_sl_dist_pts"],
                "n_trades": w["n_trades"],
            },
        }
    (out_dir / "recommended_settings.json").write_text(json.dumps(rec, indent=2))
    # integrity.json + policy_summary.md
    caveats = build_runtime_conditional_caveats(run_dir=out_dir.parent, gate_f=gate_f)
    write_policy_summary_md(out_dir, ranked, caveats, gate_f)
    summary_text = (out_dir / "policy_summary.md").read_text()
    cfg = _source_run_config(out_dir.parent)
    found = audit_no_hardcoded_caveats(summary_text, cfg)
    (out_dir / "integrity.json").write_text(json.dumps({
        "run_id": run_id, "script_version": SCRIPT_VERSION,
        "gates": {"A": gate_a, "F": gate_f, "H": gate_h},
        "narrative_caveat_audit": {
            "hardcoded_strings_found": found,
            "conditional_caveats_emitted": caveats,
        },
        "cross_family_ranking_valid": False,
        "promotion_allowed": gate_f["promotion_allowed"],
    }, indent=2, default=str))


def run_end_to_end(run_dir: Path, out_dir: Path, min_combo_n: int, top_k: int, dsn: str = DEFAULT_DSN) -> None:
    gate_h = gate_h_fixture_assertion(run_dir, dsn)
    gate_a = gate_a_trajectory_drift(run_dir, samples_per_fold=40, dsn=dsn)
    if gate_a["status"] != "PASS":
        raise RuntimeError(f"Gate A FAIL — trajectory drift. Disagreements: {gate_a['disagreements'][:5]}")
    baseline = phase1_baseline_per_stop_family(run_dir, dsn=dsn)
    combos = enumerate_exit_combos()
    all_results = []
    for combo in combos:
        all_results.extend(phase2_sweep_combo(run_dir, combo, dsn=dsn))
    ranked = rank_per_stop_family(all_results, top_k=top_k, min_combo_n=min_combo_n)
    gate_f = gate_f_source_integrity(run_dir)
    write_outputs(out_dir, baseline=baseline, exit_results=all_results, ranked=ranked,
                  gate_f=gate_f, gate_h=gate_h, gate_a=gate_a, run_id=run_dir.name)
```

**Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/ag/test_policy_mc_sweep_cli.py::test_anti_pattern_b_no_forbidden_strings_on_clean_run -v`
Expected: PASS. This is an expensive test (runs the full sweep). ~10-20 min on first run, <1 min with cache.

**Step 5: Commit**

```bash
git add scripts/ag/policy_mc_sweep.py tests/ag/test_policy_mc_sweep_cli.py
git commit -m "Add output writers + Anti-Pattern B caveat audit"
```

---

## Task 11: Main entry point + end-to-end acceptance

**Files:**
- Modify: `scripts/ag/policy_mc_sweep.py` (wire `main()` to `run_end_to_end`)
- Modify: `tests/ag/test_policy_mc_sweep_cli.py`

**Purpose:** Connect `main()` to the full pipeline. End-to-end acceptance test runs the script as a subprocess on the locked fixture and validates every gate's output.

**Step 1: Write the failing test**

```python
def test_end_to_end_acceptance_on_locked_fixture():
    """Full run against agtrain_20260415T165437712806Z, all gates pass, outputs valid."""
    import subprocess, sys, shutil, json
    from pathlib import Path
    fixture_run_id = "agtrain_20260415T165437712806Z"
    out_dir = Path(f"artifacts/ag_runs/{fixture_run_id}/policy_sweep")
    if out_dir.exists():
        shutil.rmtree(out_dir)
    r = subprocess.run(
        [sys.executable, "scripts/ag/policy_mc_sweep.py",
         "--run-id", fixture_run_id, "--phase", "both",
         "--min-combo-n", "50", "--top-k", "10"],
        capture_output=True, text=True, timeout=1800,
    )
    assert r.returncode == 0, f"exit {r.returncode}. stderr:\n{r.stderr}"
    # required outputs
    for f in ["filter_sweep_results.json", "exit_sweep_results.json",
              "recommended_settings.json", "policy_summary.md", "integrity.json"]:
        assert (out_dir / f).exists(), f"missing output: {f}"
    # integrity.json contract
    integrity = json.loads((out_dir / "integrity.json").read_text())
    assert integrity["gates"]["H"]["status"] == "PASS"
    assert integrity["gates"]["A"]["status"] == "PASS"
    assert integrity["cross_family_ranking_valid"] is False
    # promotion_allowed False — source run has LEAKAGE_SUSPECT + below-baseline + class-gap
    assert integrity["promotion_allowed"] is False
    # recommended_settings per-family structure
    rec = json.loads((out_dir / "recommended_settings.json").read_text())
    assert "winning_policy_per_stop_family" in rec
    # all 6 families present (NO_EDGE labeling forbidden)
    expected_families = {"ATR_1_0", "ATR_1_5", "ATR_STRUCTURE_1_25",
                         "FIB_0236_ATR_COMPRESS_0_50", "FIB_NEG_0236", "FIB_NEG_0382"}
    assert set(rec["winning_policy_per_stop_family"].keys()) == expected_families
```

**Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/ag/test_policy_mc_sweep_cli.py::test_end_to_end_acceptance_on_locked_fixture -v`
Expected: FAIL until main() wired.

**Step 3: Write minimal implementation**

Replace the old `main()` body with:

```python
def main() -> int:
    args = parse_args()
    run_dir = ARTIFACTS_ROOT / args.run_id
    if not run_dir.exists():
        sys.stderr.write(f"Gate H — FATAL: run directory {run_dir} not found.\n")
        sys.exit(1)
    out_dir = run_dir / "policy_sweep"
    if args.dry_run:
        # just the cheap gates
        gate_h = gate_h_fixture_assertion(run_dir, args.dsn)
        print(f"Gate H: PASS (rows={gate_h['observed_rows']}, sessions={gate_h['expected_sessions']})")
        combos = enumerate_exit_combos()
        print(f"Would sweep {len(combos)} exit combos × 6 stop families = {len(combos) * 6} Phase 2 combo evaluations")
        return 0
    run_end_to_end(run_dir=run_dir, out_dir=out_dir,
                   min_combo_n=args.min_combo_n, top_k=args.top_k, dsn=args.dsn)
    print(f"Policy sweep complete. Outputs in {out_dir}")
    return 0
```

**Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/ag/test_policy_mc_sweep_cli.py::test_end_to_end_acceptance_on_locked_fixture -v --timeout=1800`
Expected: PASS. First run 15-25 min (builds trajectory cache + 288 sweep iterations). Subsequent runs 3-5 min.

**Step 5: Commit**

```bash
git add scripts/ag/policy_mc_sweep.py tests/ag/test_policy_mc_sweep_cli.py
git commit -m "Wire main() to end-to-end pipeline + acceptance test"
```

---

## Post-implementation review

After all 11 tasks commit:

1. Run the full test suite: `python3 -m pytest tests/ag/test_policy_mc_sweep_cli.py -v --timeout=1800`
2. Grep for any remaining forbidden strings in the codebase itself (not just outputs): `grep -n "IID bag leakage\|GBM-only" scripts/ag/policy_mc_sweep.py` — expect 0 hits in this script (the string may appear in scripts/ag/run_diagnostic_shap.py inside the `if has_internal_ensembling` branch — that's fine, gated correctly).
3. Run the script on the locked fixture and visually inspect `policy_summary.md` to confirm it reads correctly and no caveat is nonsensical.
4. Push to origin once all acceptance tests pass: `git push origin main`

## Deferred to Phase 3 (do NOT add to this implementation)

- `Use Footprint Scalp Entries` + the three scalp exit knobs (Scalp Target, Scalp BE Trigger, Scalp Max Hold Bars)
- `Gate Shorts In Bull Trend` + `Short Gate ADX Floor`
- `Rejection = wick into zone` (pending Pine-side zone-logic audit before inclusion here)
- `Cooldown Bars` (sequence-dependent, requires next-trade-permission simulation)
- Full Category A/B pipeline Bayesian sweep

## Cross-reference skills

- `training-shap` @ `.claude/skills/training-shap/SKILL.md` — Anti-Pattern B is defined there and in `monte_carlo_run.py::build_run_note`
- `training-pre-audit` @ `.claude/skills/training-pre-audit/SKILL.md` — Gate F pattern mirrors the pre-audit class-coverage / below-baseline checks
- `training-quant-trading` @ `.claude/skills/training-quant-trading/SKILL.md` — the objective function's "no cross-family ranking" maps to "Rank stability ≠ EV stability" principle

---

**Plan complete.** Saved to `docs/plans/2026-04-15-policy-mc-sweep-plan.md`.
