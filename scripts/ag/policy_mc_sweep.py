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

SCRIPT_VERSION = "1.2.0"
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


import pandas as pd

FOLD_CODES = ["fold_01", "fold_02", "fold_03", "fold_04", "fold_05"]

# Columns that must come from ag_training if not present in analysis.parquet.
# For the agtrain_20260415T165437712806Z fixture these are all already in
# analysis.parquet (confirmed at build time), but we guard defensively.
REQUIRED_FROM_TRAINING = [
    "stop_variant_id", "stop_family_id", "direction",
    "outcome_label", "sl_dist_pts", "adx", "entry_price", "ts",
]


def load_fold_dataset(run_dir: Path, fold_code: str, dsn: str = DEFAULT_DSN) -> pd.DataFrame:
    """Load the fold's analysis_frame + probs, joined by row order (MC cache contract).

    analysis.parquet already contains outcome_label, sl_dist_pts, adx, entry_price,
    stop_family_id, direction, stop_variant_id for the locked fixture.  If any
    required column is missing (future fixture), fall back to a DB join on
    stop_variant_id. Returns a single DataFrame.
    """
    cache_dir = run_dir / "monte_carlo" / "cache" / fold_code
    analysis = pd.read_parquet(cache_dir / "analysis.parquet")
    probs = pd.read_parquet(cache_dir / "probs.parquet")
    if len(analysis) != len(probs):
        raise RuntimeError(
            f"fold {fold_code}: analysis len {len(analysis)} != probs len {len(probs)} "
            "— MC cache is corrupt; re-run monte_carlo_run.py first"
        )
    # Positional concat — row order is the contract (no key join for probs)
    joined = pd.concat([analysis.reset_index(drop=True), probs.reset_index(drop=True)], axis=1)

    # Check if all required columns are already present
    missing_cols = [c for c in REQUIRED_FROM_TRAINING if c not in joined.columns]
    if missing_cols:
        # Fall back: enrich from ag_training DB
        import psycopg2
        if "stop_variant_id" not in joined.columns:
            raise RuntimeError(
                "analysis_frame lacks stop_variant_id — expected in META_COLS. "
                "Check monte_carlo_run.py prepare_fold() output contract."
            )
        stop_variant_ids = joined["stop_variant_id"].tolist()
        cols_to_fetch = ["stop_variant_id"] + [c for c in missing_cols if c != "stop_variant_id"]
        with psycopg2.connect(dsn) as conn:
            enrichment = pd.read_sql(
                f"SELECT {', '.join(cols_to_fetch)} FROM ag_training WHERE stop_variant_id = ANY(%s)",
                conn, params=(stop_variant_ids,),
            )
        joined = joined.merge(enrichment, on="stop_variant_id", how="left", validate="one_to_one")
        if joined["outcome_label"].isna().any():
            bad = joined[joined["outcome_label"].isna()]["stop_variant_id"].tolist()[:10]
            raise RuntimeError(
                f"fold {fold_code}: {len(bad)} stop_variant_ids missing from ag_training: {bad}..."
            )
    return joined


TP_HIT_LABELS = {"TP1_ONLY", "TP2_HIT", "TP3_HIT", "TP4_HIT", "TP5_HIT"}
STOPPED_LABEL = "STOPPED"
FLAT_FEE_USD = 1.25
MES_POINT_VALUE = 5.0
TP_PRIORITY = ("TP5_HIT", "TP4_HIT", "TP3_HIT", "TP2_HIT", "TP1_ONLY")
TP_RANK = {label: idx for idx, label in enumerate(TP_PRIORITY)}
WAR_FIRST_BAR_OFFSET = 15
WAR_LAST_BAR_OFFSET = 32 * 15 + 14  # 494

# Raw price level columns that should not be features (admitted as regime proxies)
RAW_PRICE_FEATURE_COLS = {
    "anchor_low", "anchor_high", "entry_price",
    "tp1_price", "tp2_price", "tp3_price", "tp4_price", "tp5_price",
    "stop_level_price", "fib_level_price",
}


def compute_net_dollars(row: pd.Series) -> float:
    """Per-trade net $ at macro-fib outcome with flat fee.
    tp*_price columns are expected to be present in the row (from analysis.parquet).
    """
    label = row["outcome_label"]
    direction = int(row["direction"])
    entry = float(row["entry_price"])
    if label == STOPPED_LABEL:
        return -float(row["sl_dist_pts"]) * MES_POINT_VALUE - FLAT_FEE_USD
    tp_price_col = {
        "TP1_ONLY": "tp1_price", "TP2_HIT": "tp2_price", "TP3_HIT": "tp3_price",
        "TP4_HIT": "tp4_price", "TP5_HIT": "tp5_price",
    }.get(label)
    if tp_price_col is None or tp_price_col not in row.index:
        return 0.0
    return (float(row[tp_price_col]) - entry) * direction * MES_POINT_VALUE - FLAT_FEE_USD


def phase1_baseline_per_stop_family(run_dir: Path, dsn: str = DEFAULT_DSN) -> list[dict[str, Any]]:
    """No filter applied. Per stop family, compute tp1_reach_rate, stop_rate,
    net $, mean sl_dist_pts across all 5 folds combined.

    tp*_price columns are available in analysis.parquet for the locked fixture,
    so no separate DB query is required.
    """
    frames = []
    for fold_code in FOLD_CODES:
        frames.append(load_fold_dataset(run_dir, fold_code, dsn=dsn))
    combined = pd.concat(frames, ignore_index=True)

    results = []
    for sf, grp in combined.groupby("stop_family_id"):
        n = len(grp)
        tp1_reach = grp["outcome_label"].isin(TP_HIT_LABELS).sum() / n
        stop_rate = (grp["outcome_label"] == STOPPED_LABEL).sum() / n
        mean_sl = float(grp["sl_dist_pts"].mean())
        net_dollars = grp.apply(compute_net_dollars, axis=1)
        results.append({
            "stop_family_id": sf,
            "n_trades": n,
            "tp1_reach_rate": float(tp1_reach),
            "stop_rate": float(stop_rate),
            "mean_sl_dist_pts": mean_sl,
            "expected_net_dollars_per_trade": float(net_dollars.mean()),
            "mc_p5_ev_per_trade": None,  # Filled in when MC sampling is wired
        })
    return results


def _trajectory_cache_key(run_dir: Path, fold_code: str, max_bars: int, dsn: str) -> str:
    """md5 key that invalidates when mes_1m grows or script version changes."""
    import psycopg2
    with psycopg2.connect(dsn) as conn:
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

    Output columns: stop_variant_id, bar_offset (0-based, 1m bars),
    high_pts, low_pts, close_pts — where *_pts = bar.value - entry_price.

    Caches to parquet. Re-runs are instant unless mes_1m grows or script
    version changes.
    """
    import numpy as np
    import psycopg2

    cache_key = _trajectory_cache_key(run_dir, fold_code, max_trajectory_bars, dsn)
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_path = cache_dir / f"{fold_code}__{cache_key}.parquet"
    if cache_path.exists() and not force_rebuild:
        return pd.read_parquet(cache_path)

    joined = load_fold_dataset(run_dir, fold_code, dsn=dsn)

    window_minutes = max_trajectory_bars * 15
    min_entry = joined["ts"].min()
    max_entry = joined["ts"].max()
    buf_end = max_entry + pd.Timedelta(minutes=window_minutes + 60)

    with psycopg2.connect(dsn) as conn:
        mes_1m = pd.read_sql(
            "SELECT ts, high, low, close FROM mes_1m WHERE ts >= %s AND ts <= %s ORDER BY ts",
            conn, params=(min_entry, buf_end),
        )
    if mes_1m.empty:
        raise RuntimeError(
            f"fold {fold_code}: no mes_1m bars in window [{min_entry}, {buf_end}]"
        )

    # Pre-sort and convert ts to UTC datetime64 then int64 ns for searchsorted
    mes_1m = mes_1m.sort_values("ts").reset_index(drop=True)
    mes_1m["ts"] = pd.to_datetime(mes_1m["ts"], utc=True)
    mes_ts_ns = mes_1m["ts"].values.view("int64")
    mes_high = mes_1m["high"].values
    mes_low = mes_1m["low"].values
    mes_close = mes_1m["close"].values

    rows: list[dict[str, Any]] = []
    window_ns = int(pd.Timedelta(minutes=window_minutes).value)

    # Convert joined ts to int64 ns for fast comparison (same epoch as mes_ts_ns)
    joined = joined.copy()
    joined["ts"] = pd.to_datetime(joined["ts"], utc=True)
    joined_ts_ns = joined["ts"].values.view("int64")

    for idx, row in enumerate(joined.itertuples(index=False)):
        entry_ts_ns = int(joined_ts_ns[idx])
        svid = row.stop_variant_id
        end_ts_ns = entry_ts_ns + window_ns

        start_idx = int(np.searchsorted(mes_ts_ns, entry_ts_ns, side="left"))
        end_idx = int(np.searchsorted(mes_ts_ns, end_ts_ns, side="right"))

        slice_h = mes_high[start_idx:end_idx]
        slice_l = mes_low[start_idx:end_idx]
        slice_c = mes_close[start_idx:end_idx]

        entry_px = float(row.entry_price)

        for i in range(len(slice_h)):
            rows.append({
                "stop_variant_id": svid,
                "bar_offset": i,
                "high_pts": float(slice_h[i] - entry_px),
                "low_pts": float(slice_l[i] - entry_px),
                "close_pts": float(slice_c[i] - entry_px),
            })

    df = pd.DataFrame(rows)
    df.to_parquet(cache_path, index=False, compression="gzip")
    return df


def _reconstruct_outcome_from_trajectory(
    tr_row: Any, traj_slice: pd.DataFrame, sl_pts: float
) -> str:
    """Reconstruct trade outcome matching build_ag_pipeline.py warehouse labeling.

    Key design decisions derived from warehouse audit:
    1. 15m resolution: aggregate 1m bars into 15m windows (bar_offset // 15) to
       match the 15m-bar granularity used by build_ag_pipeline.py for TP/SL detection.
    2. Highest TP: continue scanning past TP1 to find TP2/TP3/TP4/TP5 — the
       warehouse tracks highest_tp_hit across the full forward window, not just first hit.
    3. STOPPED default: if TP1 not hit before SL (or window ends without TP1 hit),
       return STOPPED — matches warehouse tp1_before_sl=False → STOPPED. ag_training
       has no CENSORED labels so CENSORED is never a valid return value here.
    4. Same-window tie-break: if SL and TP1 both first hit in the same 15m window,
       STOPPED wins (bars_to_sl == bars_to_tp1 → tp1_before_sl=False).
    5. Anchor: high_pts/low_pts in traj_slice are relative to the stored entry_price
       (fib-computed retracement level from ag_training). TP/SL deltas are also
       relative to entry_price, so both sides share the same reference frame.
       NOTE: if mes_1m has been back-adjusted by Databento since build_ag_pipeline.py
       ran, absolute bar prices differ from prices used for warehouse labeling and Gate A
       agreement drops below 95%. The only fix is to rebuild the pipeline.
    """
    import numpy as np

    direction = int(tr_row.direction)
    entry = float(tr_row.entry_price)
    sl_price_delta = -sl_pts if direction == 1 else sl_pts

    # TP priority: highest first (TP5 > TP4 > ... > TP1)
    tp_deltas = {
        "TP5_HIT": float(tr_row.tp5_price) - entry,
        "TP4_HIT": float(tr_row.tp4_price) - entry,
        "TP3_HIT": float(tr_row.tp3_price) - entry,
        "TP2_HIT": float(tr_row.tp2_price) - entry,
        "TP1_ONLY": float(tr_row.tp1_price) - entry,
    }

    if traj_slice.empty:
        return "STOPPED"  # no data → conservative label matches warehouse default

    bars = traj_slice.sort_values("bar_offset")
    bar_offsets = bars["bar_offset"].values
    highs = bars["high_pts"].values
    lows = bars["low_pts"].values

    # Warehouse scans bars 1–32 forward from entry (confirmed: min=1, max=32 in ag_training).
    # The signal bar (bar_offsets 0–14, window 0) is NOT included in the warehouse scan.
    # bar_offset 15–29 = warehouse bar 1; bar_offset 480–494 = warehouse bar 32.
    # Filter to exactly the warehouse-equivalent range: [15, 494].
    in_scan = (bar_offsets >= WAR_FIRST_BAR_OFFSET) & (bar_offsets <= WAR_LAST_BAR_OFFSET)
    bar_offsets = bar_offsets[in_scan]
    highs = highs[in_scan]
    lows  = lows[in_scan]

    if len(bar_offsets) == 0:
        return "STOPPED"  # no forward bars available → conservative

    # Group 1m bars → 15m windows (bar_offset//15 gives warehouse bar number 1–32)
    window_ids = bar_offsets // 15
    unique_windows = np.unique(window_ids)

    first_tp1_window: int | None = None  # first window any TP level was reached
    sl_window: int | None = None
    highest_tp: str | None = None        # highest TP label reached before SL

    for w in unique_windows:
        mask = window_ids == w
        window_high = highs[mask].max()
        window_low = lows[mask].min()

        # Highest TP hit in this window (TP5 checked first — once TP5 is reached,
        # TP1-TP4 are also implied for in-window path continuity).
        tp_this_window: str | None = None
        for label in TP_PRIORITY:
            td = tp_deltas[label]
            if direction == 1 and window_high >= td:
                tp_this_window = label
                break
            if direction == -1 and window_low <= td:
                tp_this_window = label
                break

        sl_this_window = (
            (direction == 1 and window_low <= sl_price_delta)
            or (direction == -1 and window_high >= sl_price_delta)
        )

        if sl_this_window:
            # SL hit this window — record and stop scanning.
            # Any TP hit in THIS same window loses the tie (bars_to_sl == bars_to_tp1
            # → tp1_before_sl=False → STOPPED per warehouse contract).
            sl_window = int(w)
            break

        if tp_this_window is not None:
            if first_tp1_window is None:
                first_tp1_window = int(w)
            # Keep highest TP reached
            if highest_tp is None or (
                TP_RANK[tp_this_window] < TP_RANK[highest_tp]
            ):
                highest_tp = tp_this_window

    # Outcome decision (mirrors warehouse outcome_label_for logic)
    if first_tp1_window is None:
        # TP1 never reached before SL (or within window) → STOPPED
        return "STOPPED"
    if sl_window is None or first_tp1_window < sl_window:
        # TP1 hit on a strictly earlier window than SL (or SL never hit)
        return highest_tp or "TP1_ONLY"
    # sl_window <= first_tp1_window → SL hit first or same window → STOPPED
    return "STOPPED"


def gate_a_trajectory_drift(
    run_dir: Path, samples_per_fold: int = 40, dsn: str = DEFAULT_DSN
) -> dict[str, Any]:
    """Gate A — stratified 40×5 cross-validation of trajectory-derived outcomes
    vs warehouse outcome_label. Requires ≥ 95% agreement to PASS.

    tp*_price columns are read from analysis.parquet (no DB roundtrip needed).
    Trajectory high_pts/low_pts are relative to entry_price (fib level). If mes_1m has
    been back-adjusted since build_ag_pipeline.py ran, agreement will be below 95% and
    the gate will FAIL — this is correct behaviour. Rebuild the pipeline to fix.
    """
    import numpy as np

    cache_dir = run_dir / "policy_sweep" / "trajectory_cache"
    rng = np.random.default_rng(42)
    disagreements: list[dict[str, Any]] = []
    checked = 0

    for fold_code in FOLD_CODES:
        ds = load_fold_dataset(run_dir, fold_code, dsn=dsn)
        if len(ds) < samples_per_fold:
            continue
        traj = build_or_load_trajectory(run_dir, fold_code, cache_dir, dsn=dsn)
        traj_by_svid = {svid: grp for svid, grp in traj.groupby("stop_variant_id")}

        sample_idx = rng.choice(len(ds), samples_per_fold, replace=False)
        for i in sample_idx:
            tr = ds.iloc[i]
            svid = tr["stop_variant_id"]
            traj_slice = traj_by_svid.get(svid, pd.DataFrame())
            derived = _reconstruct_outcome_from_trajectory(
                tr, traj_slice, float(tr["sl_dist_pts"])
            )
            checked += 1
            if derived != tr["outcome_label"]:
                disagreements.append({
                    "stop_variant_id": str(svid),
                    "warehouse": tr["outcome_label"],
                    "trajectory_derived": derived,
                })

    agreement = 1.0 - len(disagreements) / max(checked, 1)
    status = "PASS" if agreement >= 0.95 else "FAIL"
    return {
        "status": status,
        "sample_size": checked,
        "agreement_rate": float(agreement),
        "disagreements": disagreements,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Task 7 — ExitSweeper (Phase 2 re-simulation)
# ─────────────────────────────────────────────────────────────────────────────

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
    tr: Any, traj_slice: tuple[Any, Any, Any] | None, sl_pts: float, combo: dict[str, Any],
) -> tuple[str, float]:
    """Re-simulate one trade under a given exit-management combo.

    Scans bar_offset >= 15 (warehouse-equivalent window; signal bar excluded).
    Uses tr.tp*_price columns (available from analysis.parquet via load_fold_dataset).

    Rules:
    - break_even_after_tp1: after first TP1+ tag, move SL to entry (0 delta).
      A subsequent SL hit at BE returns TP1_ONLY.
    - let_fast_runners_run: if TP1 first tagged within fast_runner_window_bars 15m
      bars, promote exit target to fast_runner_target (TP2 or TP3). Hold until
      promoted target is reached (or end of window → return highest reached).

    Returns (outcome_label, net_dollars).
    """
    direction = int(tr.direction)
    entry = float(tr.entry_price)
    sl_price_delta = -sl_pts if direction == 1 else sl_pts

    tp5_delta = float(tr.tp5_price) - entry
    tp4_delta = float(tr.tp4_price) - entry
    tp3_delta = float(tr.tp3_price) - entry
    tp2_delta = float(tr.tp2_price) - entry
    tp1_delta = float(tr.tp1_price) - entry
    tp_deltas_by_rank = (tp5_delta, tp4_delta, tp3_delta, tp2_delta, tp1_delta)
    target_rank = 3 if combo["fast_runner_target"] == "TP2" else 2
    fast_runner_window_15m = combo["fast_runner_window_bars"]  # in 15m bars
    let_fast_runners_run = bool(combo["let_fast_runners_run"])
    break_even_after_tp1 = bool(combo["break_even_after_tp1"])

    # traj_slice is pre-trimmed to warehouse-equivalent bars 1-32 by
    # _build_fold_sweep_context to avoid per-trade filter/sort overhead.
    if traj_slice is None:
        return "STOPPED", -sl_pts * MES_POINT_VALUE - FLAT_FEE_USD
    bar_offsets, highs, lows = traj_slice
    if len(bar_offsets) == 0:
        return "STOPPED", -sl_pts * MES_POINT_VALUE - FLAT_FEE_USD

    tp1_hit_15m: int | None = None   # 15m bar number when TP1 first tagged
    promoted_target_rank: int | None = None
    highest_tp_rank: int | None = None

    for i in range(len(bar_offsets)):
        bar_15m_num = int(bar_offsets[i] // 15)  # 1 for offsets 15-29, 2 for 30-44, …
        high = highs[i]
        low = lows[i]

        # Active stop: breakeven once TP1 is tagged and combo says so
        active_sl = (
            0.0 if (break_even_after_tp1 and tp1_hit_15m is not None)
            else sl_price_delta
        )

        # SL check
        sl_hit = (
            (direction == 1 and low <= active_sl)
            or (direction == -1 and high >= active_sl)
        )
        if sl_hit:
            if tp1_hit_15m is not None and break_even_after_tp1:
                # Stopped at breakeven after TP1: credit TP1 PnL
                pnl = tp1_delta * direction * MES_POINT_VALUE - FLAT_FEE_USD
                return "TP1_ONLY", pnl
            return "STOPPED", -sl_pts * MES_POINT_VALUE - FLAT_FEE_USD

        # Highest TP hit in this 1m bar by rank (TP5=0 ... TP1=4)
        bar_top_rank: int | None = None
        if direction == 1:
            if high >= tp5_delta:
                bar_top_rank = 0
            elif high >= tp4_delta:
                bar_top_rank = 1
            elif high >= tp3_delta:
                bar_top_rank = 2
            elif high >= tp2_delta:
                bar_top_rank = 3
            elif high >= tp1_delta:
                bar_top_rank = 4
        else:
            if low <= tp5_delta:
                bar_top_rank = 0
            elif low <= tp4_delta:
                bar_top_rank = 1
            elif low <= tp3_delta:
                bar_top_rank = 2
            elif low <= tp2_delta:
                bar_top_rank = 3
            elif low <= tp1_delta:
                bar_top_rank = 4

        if bar_top_rank is None:
            continue

        # First TP1+ hit: record 15m bar number and determine fast-runner status
        if tp1_hit_15m is None:
            tp1_hit_15m = bar_15m_num
            if let_fast_runners_run and tp1_hit_15m <= fast_runner_window_15m:
                promoted_target_rank = target_rank

        # Update highest TP reached so far
        if highest_tp_rank is None or bar_top_rank < highest_tp_rank:
            highest_tp_rank = bar_top_rank

        # Exit decision
        if promoted_target_rank is not None:
            # Fast runner: exit when promoted target (or above) is reached
            if bar_top_rank <= promoted_target_rank:
                pnl = tp_deltas_by_rank[promoted_target_rank] * direction * MES_POINT_VALUE - FLAT_FEE_USD
                return TP_PRIORITY[promoted_target_rank], pnl
            # Promoted target not yet reached — continue scanning
        elif bar_top_rank == 0:
            # No promotion active: exit at TP5 (natural cap)
            pnl = tp5_delta * direction * MES_POINT_VALUE - FLAT_FEE_USD
            return "TP5_HIT", pnl

    # End of scan window
    if tp1_hit_15m is not None:
        exit_rank = highest_tp_rank if highest_tp_rank is not None else 4
        exit_label = TP_PRIORITY[exit_rank]
        pnl = tp_deltas_by_rank[exit_rank] * direction * MES_POINT_VALUE - FLAT_FEE_USD
        return exit_label, pnl
    return "STOPPED", -sl_pts * MES_POINT_VALUE - FLAT_FEE_USD


PreparedTrajectory = tuple[Any, Any, Any]  # (bar_offsets, highs, lows) numpy arrays
FoldSweepContext = dict[str, tuple[pd.DataFrame, dict[Any, PreparedTrajectory]]]


def _build_fold_sweep_context(run_dir: Path, dsn: str = DEFAULT_DSN) -> FoldSweepContext:
    """Load fold datasets + trajectory groups once for reuse across exit combos."""
    cache_dir = run_dir / "policy_sweep" / "trajectory_cache"
    context: FoldSweepContext = {}
    for fold_code in FOLD_CODES:
        ds = load_fold_dataset(run_dir, fold_code, dsn=dsn)
        traj = build_or_load_trajectory(run_dir, fold_code, cache_dir, dsn=dsn)
        traj = traj[
            (traj["bar_offset"] >= WAR_FIRST_BAR_OFFSET)
            & (traj["bar_offset"] <= WAR_LAST_BAR_OFFSET)
        ]
        prepared_traj: dict[Any, PreparedTrajectory] = {}
        for svid, grp in traj.groupby("stop_variant_id", sort=False):
            prepared_traj[svid] = (
                grp["bar_offset"].to_numpy(copy=False),
                grp["high_pts"].to_numpy(copy=False),
                grp["low_pts"].to_numpy(copy=False),
            )
        context[fold_code] = (
            ds,
            prepared_traj,
        )
    return context


def phase2_sweep_combo(
    run_dir: Path,
    combo: dict[str, Any],
    dsn: str = DEFAULT_DSN,
    fold_context: FoldSweepContext | None = None,
) -> list[dict[str, Any]]:
    """Re-simulate all trades under one exit combo. Returns per-stop-family metrics."""
    context = fold_context or _build_fold_sweep_context(run_dir, dsn=dsn)
    per_family: dict[str, list[tuple[str, float, float]]] = {}

    for fold_code in FOLD_CODES:
        ds, traj_by_svid = context[fold_code]

        for tr in ds.itertuples(index=False):
            svid = tr.stop_variant_id
            traj_slice = traj_by_svid.get(svid)
            if traj_slice is None:
                continue
            outcome, net = _simulate_exit_outcome(tr, traj_slice, float(tr.sl_dist_pts), combo)
            per_family.setdefault(tr.stop_family_id, []).append(
                (outcome, net, float(tr.sl_dist_pts))
            )

    results = []
    for sf, records in per_family.items():
        n = len(records)
        tp1_reach = sum(1 for r in records if r[0] in TP_HIT_LABELS) / n
        stop_rate = sum(1 for r in records if r[0] == STOPPED_LABEL) / n
        results.append({
            "stop_family_id": sf,
            "combo": combo,
            "n_trades": n,
            "tp1_reach_rate": float(tp1_reach),
            "stop_rate": float(stop_rate),
            "expected_net_dollars_per_trade": float(sum(r[1] for r in records) / n),
            "mean_sl_dist_pts": float(sum(r[2] for r in records) / n),
        })
    return results


# ─────────────────────────────────────────────────────────────────────────────
# Task 8 — Ranker
# ─────────────────────────────────────────────────────────────────────────────

def rank_per_stop_family(
    combo_results: list[dict[str, Any]], top_k: int, min_combo_n: int,
) -> dict[str, Any]:
    """Per stop family, sort by (tp1_reach DESC, net$ DESC). Emit top K + bottom K.
    Combos below min_combo_n are excluded from ranking (counted separately).
    Cross-family ranking is forbidden — never sort across stop families.
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
        rows_sorted = sorted(
            rows,
            key=lambda r: (-r["tp1_reach_rate"], -r["expected_net_dollars_per_trade"]),
        )
        out[sf] = {
            "top_k": rows_sorted[:top_k],
            "bottom_k": rows_sorted[-top_k:][::-1],
            "below_min_n_count": below_n.get(sf, 0),
            "total_combos_ranked": len(rows_sorted),
        }
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Task 9 — Gate F: source-run integrity propagation (6 checks)
# ─────────────────────────────────────────────────────────────────────────────

def gate_f_source_integrity(run_dir: Path) -> dict[str, Any]:
    """Re-derive source-run integrity from raw artifacts. Anti-Pattern C: don't trust
    prior summaries; read the raw data. Six checks; any failure blocks promotion.

    Checks 1-3 (original): LEAKAGE_SUSPECT, below-baseline fold, class coverage gap.
    Checks 4-6 (audit additions): raw price features, wrong SHAP model, severe calibration.
    """
    shap_dir = Path("artifacts/shap") / run_dir.name

    # Check 1: LEAKAGE_SUSPECT in SHAP drop candidates
    has_leakage = False
    drop_csv = shap_dir / "drop_candidates.csv"
    if drop_csv.exists():
        drops = pd.read_csv(drop_csv)
        has_leakage = bool(
            "reason_code" in drops.columns
            and (drops["reason_code"] == "LEAKAGE_SUSPECT").any()
        )

    # Checks 2 + 3: per-fold fold_summary.json
    has_below_baseline = False
    has_coverage_gap = False
    for fp in sorted(run_dir.glob("fold_*/fold_summary.json")):
        summary = json.loads(fp.read_text())
        ag = summary.get("autogluon", {})
        base_test = summary.get("majority_baseline", {}).get("test", {})
        ag_f1 = ag.get("test_macro_f1")
        base_f1 = base_test.get("macro_f1")
        if ag_f1 is not None and base_f1 is not None and float(ag_f1) < float(base_f1):
            has_below_baseline = True
        val_cc = summary.get("val_class_count")
        test_cc = summary.get("test_class_count")
        if val_cc is not None and test_cc is not None and int(val_cc) < int(test_cc):
            has_coverage_gap = True

    # Check 4: raw price level columns present in actual training features (SHAP feature summary)
    has_raw_price_features = False
    shap_manifest_path = shap_dir / "diagnostic_shap_manifest.json"
    if shap_manifest_path.exists():
        shap_manifest = json.loads(shap_manifest_path.read_text())
        for fa in shap_manifest.get("fold_artifacts", []):
            fs_path = Path(fa.get("feature_summary_path", ""))
            if fs_path.exists():
                fs = pd.read_csv(fs_path)
                if "feature_name" in fs.columns:
                    if any(f in RAW_PRICE_FEATURE_COLS for f in fs["feature_name"].values):
                        has_raw_price_features = True
                        break

    # Check 5: SHAP model != per-fold best model (wrong model used for SHAP)
    has_wrong_shap_model = False
    if shap_manifest_path.exists():
        shap_manifest = json.loads(shap_manifest_path.read_text())
        global_model = shap_manifest.get("model_name")
        for fp in sorted(run_dir.glob("fold_*/fold_summary.json")):
            best = json.loads(fp.read_text()).get("autogluon", {}).get("best_model")
            if best and global_model and global_model != best:
                has_wrong_shap_model = True
                break

    # Check 6: calibration OOR rows (over/underconfident predictions)
    has_severe_calibration = False
    calib_csv = shap_dir / "calibration_check.csv"
    if calib_csv.exists():
        calib = pd.read_csv(calib_csv)
        if "verdict" in calib.columns:
            has_severe_calibration = bool((calib["verdict"] != "OK").any())

    promotion_allowed = not (
        has_leakage or has_below_baseline or has_coverage_gap
        or has_raw_price_features or has_wrong_shap_model or has_severe_calibration
    )
    reasons: list[str] = []
    if has_leakage:
        reasons.append("LEAKAGE_SUSPECT in SHAP drop candidates")
    if has_below_baseline:
        reasons.append("at least one fold below majority-class baseline")
    if has_coverage_gap:
        reasons.append("at least one fold has val_class_count < test_class_count")
    if has_raw_price_features:
        reasons.append("raw price level columns present in training features")
    if has_wrong_shap_model:
        reasons.append("SHAP model does not match per-fold best model")
    if has_severe_calibration:
        reasons.append("calibration OOR rows present")

    return {
        "source_run_has_leakage_suspects": has_leakage,
        "source_run_has_below_baseline_fold": has_below_baseline,
        "source_run_has_class_coverage_gap": has_coverage_gap,
        "source_run_has_raw_price_features": has_raw_price_features,
        "source_run_has_wrong_shap_model": has_wrong_shap_model,
        "source_run_has_severe_calibration": has_severe_calibration,
        "promotion_allowed": promotion_allowed,
        "promotion_blocked_reason": "; ".join(reasons) if reasons else None,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Task 10 — Output writers + Anti-Pattern B
# ─────────────────────────────────────────────────────────────────────────────

# Anti-Pattern B: these strings must NEVER appear unconditionally in policy_summary.md.
# They are only valid when num_bag_folds > 0.
FORBIDDEN_CAVEAT_STRINGS = [
    "IID bag leakage", "GBM-only", "only LightGBM in leaderboard", "bag-fold leakage",
]


def _compute_file_checksums(out_dir: Path, filenames: list[str]) -> dict[str, str]:
    result = {}
    for fname in filenames:
        p = out_dir / fname
        if p.exists():
            result[fname] = hashlib.md5(p.read_bytes()).hexdigest()
    return result


def _generate_policy_summary(
    run_dir: Path,
    gate_h: dict[str, Any],
    gate_a: dict[str, Any],
    gate_f: dict[str, Any],
    baseline: list[dict[str, Any]],
    ranked: dict[str, Any],
    num_bag_folds: int,
) -> str:
    """Generate policy_summary.md. Bag-leakage caveats are emitted ONLY when
    num_bag_folds > 0 (Anti-Pattern B guard). Never hardcode caveat strings.
    """
    lines: list[str] = []
    lines.append(f"# Policy Sweep Summary — {run_dir.name}\n")

    lines.append("## Gate Results\n")
    lines.append(f"- **Gate H** (fixture integrity): {gate_h['status']}")
    lines.append(
        f"- **Gate A** (trajectory drift): {gate_a['status']} "
        f"(agreement={gate_a['agreement_rate']:.3f}, n={gate_a['sample_size']})"
    )
    lines.append(
        f"- **Gate F** (source integrity): promotion_allowed={gate_f['promotion_allowed']}"
    )
    if gate_f.get("promotion_blocked_reason"):
        lines.append(f"  - Blocked: {gate_f['promotion_blocked_reason']}")

    lines.append("\n## Phase 1 Baseline (warehouse labels, no policy)\n")
    lines.append(
        "| stop_family_id | n_trades | tp1_reach_rate | stop_rate "
        "| mean_sl_dist_pts | net_$/trade |"
    )
    lines.append("|---|---|---|---|---|---|")
    for r in sorted(baseline, key=lambda x: x["stop_family_id"]):
        lines.append(
            f"| {r['stop_family_id']} | {r['n_trades']} "
            f"| {r['tp1_reach_rate']:.3f} | {r['stop_rate']:.3f} "
            f"| {r['mean_sl_dist_pts']:.2f} | {r['expected_net_dollars_per_trade']:.2f} |"
        )

    lines.append("\n## Phase 2 Top Policy Per Stop Family\n")
    for sf in sorted(ranked.keys()):
        result = ranked[sf]
        top = result["top_k"][0] if result["top_k"] else None
        lines.append(f"### {sf}")
        if top:
            lines.append(f"- combo: `{top['combo']}`")
            lines.append(f"- tp1_reach_rate: {top['tp1_reach_rate']:.3f}")
            lines.append(f"- net_$/trade: {top['expected_net_dollars_per_trade']:.2f}")
            lines.append(f"- n_trades: {top['n_trades']}")
        else:
            lines.append("- no combos above min_combo_n threshold")
        if result["below_min_n_count"]:
            lines.append(f"- {result['below_min_n_count']} combos below min_combo_n (excluded)")

    # Anti-Pattern B: conditional caveats — only emit when bag folds were used
    if num_bag_folds > 0:
        lines.append("\n## Data Quality Caveats\n")
        lines.append(
            f"> WARNING: This run used num_bag_folds={num_bag_folds}. "
            "AutoGluon internal bag splits are IID random shuffle which violates "
            "the one-session embargo on MES 15m data. "
            "IID bag leakage may inflate validation scores. "
            "GBM-only dominance (only LightGBM in leaderboard) is a known symptom. "
            "bag-fold leakage fingerprint: val f1_macro ~0.99, test collapses. "
            "Re-run with --num-bag-folds 0 before trusting sweep results."
        )

    lines.append(f"\n---\n*Generated by policy_mc_sweep.py v{SCRIPT_VERSION}*\n")
    return "\n".join(lines) + "\n"


def run_end_to_end(
    run_dir: Path,
    out_dir: Path | None = None,
    min_combo_n: int = 50,
    top_k: int = 10,
    phase: str = "both",
    dsn: str = DEFAULT_DSN,
) -> dict[str, Any]:
    """Full pipeline: Gate H → Gate A → Phase 1 baseline → Phase 2 exit sweep →
    Rank → Gate F → write all outputs. Returns integrity dict.

    Outputs written to out_dir (default: run_dir/policy_sweep):
      filter_sweep_results.json  — Phase 1 baseline per stop family
      exit_sweep_results.json    — all Phase 2 combo results (flat list)
      recommended_settings.json  — per-family top-1 winning policy
      policy_summary.md          — narrative (Anti-Pattern B: no hardcoded bag caveats)
      integrity.json             — gate statuses + promotion flag + caveat audit
      MANIFEST.json              — md5 checksums of above files

    Gate A FAIL does NOT abort — results are written and the FAIL is recorded in
    integrity.json. Main() returns non-zero on Gate A FAIL.
    """
    if out_dir is None:
        out_dir = run_dir / "policy_sweep"
    out_dir.mkdir(parents=True, exist_ok=True)

    # Gate H (aborts via sys.exit on fixture drift — by design)
    gate_h = gate_h_fixture_assertion(run_dir, dsn)

    # Gate A (returns FAIL dict; does not abort)
    gate_a = gate_a_trajectory_drift(run_dir, dsn=dsn)

    # Phase 1 baseline
    baseline = phase1_baseline_per_stop_family(run_dir, dsn=dsn)

    # Phase 2 exit sweep — all combos (skip if phase=="filter")
    all_combo_results: list[dict[str, Any]] = []
    if phase in ("exit", "both"):
        fold_context = _build_fold_sweep_context(run_dir, dsn=dsn)
        for combo in enumerate_exit_combos():
            all_combo_results.extend(
                phase2_sweep_combo(run_dir, combo=combo, dsn=dsn, fold_context=fold_context)
            )

    # Rank per stop family
    ranked = rank_per_stop_family(all_combo_results, top_k=top_k, min_combo_n=min_combo_n)

    # Gate F
    gate_f = gate_f_source_integrity(run_dir)

    # Read run_config.json for Anti-Pattern B (num_bag_folds)
    num_bag_folds = 0
    rc_path = run_dir / "run_config.json"
    if rc_path.exists():
        rc = json.loads(rc_path.read_text())
        num_bag_folds = int(rc.get("args", {}).get("num_bag_folds", 0))

    # ── Write outputs ──────────────────────────────────────────────────────────

    (out_dir / "filter_sweep_results.json").write_text(
        json.dumps(baseline, indent=2)
    )

    (out_dir / "exit_sweep_results.json").write_text(
        json.dumps(all_combo_results, indent=2)
    )

    winning: dict[str, Any] = {}
    for sf, result in ranked.items():
        if result["top_k"]:
            winning[sf] = result["top_k"][0]
    (out_dir / "recommended_settings.json").write_text(
        json.dumps({"winning_policy_per_stop_family": winning}, indent=2)
    )

    summary_text = _generate_policy_summary(
        run_dir, gate_h, gate_a, gate_f, baseline, ranked, num_bag_folds
    )
    (out_dir / "policy_summary.md").write_text(summary_text)

    # Narrative caveat audit (Anti-Pattern B)
    found_forbidden = [s for s in FORBIDDEN_CAVEAT_STRINGS if s in summary_text]

    integrity: dict[str, Any] = {
        "gates": {
            "H": gate_h,
            "A": gate_a,
            "F": gate_f,
        },
        "cross_family_ranking_valid": False,   # cross-family ranking is always forbidden
        "promotion_allowed": gate_f["promotion_allowed"],
        "narrative_caveat_audit": {
            "num_bag_folds": num_bag_folds,
            "hardcoded_strings_found": found_forbidden,
        },
    }
    (out_dir / "integrity.json").write_text(json.dumps(integrity, indent=2))

    output_files = [
        "filter_sweep_results.json", "exit_sweep_results.json",
        "recommended_settings.json", "policy_summary.md", "integrity.json",
    ]
    manifest = {
        "run_id": run_dir.name,
        "script_version": SCRIPT_VERSION,
        "files": _compute_file_checksums(out_dir, output_files),
    }
    (out_dir / "MANIFEST.json").write_text(json.dumps(manifest, indent=2))

    return integrity


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

    if args.dry_run:
        gate_h = gate_h_fixture_assertion(run_dir, args.dsn)
        print(f"Gate H: PASS (rows={gate_h['observed_rows']}, sessions={gate_h['expected_sessions']})")
        print("Dry run — exiting before any output.")
        return 0

    out_dir = run_dir / "policy_sweep"
    integrity = run_end_to_end(
        run_dir=run_dir,
        out_dir=out_dir,
        min_combo_n=args.min_combo_n,
        top_k=args.top_k,
        phase=args.phase,
        dsn=args.dsn,
    )

    gate_h_status = integrity["gates"]["H"]["status"]
    gate_a = integrity["gates"]["A"]
    print(f"Gate H: {gate_h_status}")
    print(
        f"Gate A: {gate_a['status']} "
        f"(agreement={gate_a['agreement_rate']:.3f}, n={gate_a['sample_size']})"
    )
    print(f"promotion_allowed: {integrity['promotion_allowed']}")
    print(f"Outputs: {out_dir}")

    if gate_a["status"] == "FAIL":
        sys.stderr.write(
            f"Gate A FAIL — trajectory drift detected "
            f"(agreement={gate_a['agreement_rate']:.3f} < 0.95). "
            f"mes_1m may have been back-adjusted by Databento since build_ag_pipeline.py ran. "
            f"Rebuild the pipeline and fixture to fix.\n"
        )
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
