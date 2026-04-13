#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import random
import statistics
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import psycopg2
from psycopg2.extras import Json, RealDictCursor


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SPACE_PATH = Path(__file__).with_name("strategy_tuning_space.json")
DEFAULT_LEDGER_PATH = REPO_ROOT / "artifacts" / "tuning" / "strategy_trials.jsonl"
DEFAULT_SUGGESTIONS_DIR = REPO_ROOT / "artifacts" / "tuning" / "suggestions"
DEFAULT_INITIAL_CAPITAL = 50_000.0
DEFAULT_SURVIVAL_STOP_USD = -37.50
DEFAULT_DB_DSN = os.environ.get(
    "WARBIRD_PG_DSN", "host=127.0.0.1 port=5432 dbname=warbird"
)
# TV tick archive boundary for MES1! 15m — bars before this date rarely have footprint data.
# Operator can override per session via --footprint-available-from on the `record` command.
DEFAULT_FOOTPRINT_AVAILABLE_FROM = "2024-01-01"
# Minimum CSV start date: 2020-01-01 per v5 training-data floor.
DEFAULT_REQUIRED_CSV_START = "2020-01-01"
DEFAULT_ROLLING_WINDOW_COUNT = 4

PARAMETER_GROUPS: tuple[tuple[str, ...], ...] = (
    (
        "Footprint Ticks Per Row",
        "Footprint VA %",
        "Footprint Imbalance %",
        "Extreme Rows To Inspect",
        "Zero-Print Volume Ratio",
    ),
    (
        "Exhaustion Z Length",
        "Exhaustion Z Threshold",
        "Extension ATR Tolerance",
    ),
    (
        "Gate Shorts In Bull Trend",
        "Short Gate ADX Floor",
    ),
    (
        "Fallback Stop Family",
        "Tier 1 Hold Bars",
        "Tier 1 Hold Stop ATR",
    ),
)


@dataclass
class Domain:
    name: str
    kind: str
    values: list[Any]


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def normalize_number(value: Any) -> Any:
    if isinstance(value, float):
        rounded = round(value, 10)
        if rounded.is_integer():
            return int(rounded)
        return rounded
    return value


def canonical_json(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


def config_value(mapping: dict[str, Any], key: str, default: Any) -> Any:
    return mapping[key] if key in mapping and mapping[key] is not None else default


def filter_signature_locked_params(
    space: dict[str, Any], locked_params: dict[str, Any]
) -> dict[str, Any]:
    excluded = set(space.get("signature_exclude_locked_parameters", []))
    return {key: value for key, value in locked_params.items() if key not in excluded}


def parameter_constraint_violations(params: dict[str, Any]) -> list[str]:
    issues: list[str] = []

    hold_bars = params.get("Tier 1 Hold Bars")
    hold_atr = params.get("Tier 1 Hold Stop ATR")
    if hold_bars is not None and hold_atr is not None:
        if hold_bars >= 5 and hold_atr > 2.0:
            issues.append("hold_logic_overwide")

    z_len = params.get("Exhaustion Z Length")
    z_threshold = params.get("Exhaustion Z Threshold")
    ext_tol = params.get("Extension ATR Tolerance")
    if z_len is not None and z_threshold is not None and ext_tol is not None:
        if z_len <= 14 and z_threshold <= 2.2 and ext_tol >= 0.12:
            issues.append("exhaustion_gate_too_permissive")
        if z_len >= 30 and z_threshold >= 2.8 and ext_tol <= 0.08:
            issues.append("exhaustion_gate_too_sparse")

    ticks_per_row = params.get("Footprint Ticks Per Row")
    zero_ratio = params.get("Zero-Print Volume Ratio")
    imbalance = params.get("Footprint Imbalance %")
    rows_to_inspect = params.get("Extreme Rows To Inspect")
    if ticks_per_row is not None and zero_ratio is not None:
        if ticks_per_row >= 6 and zero_ratio > 0.14:
            issues.append("zero_print_too_loose_for_row_size")
    if imbalance is not None and rows_to_inspect is not None:
        if imbalance >= 325 and rows_to_inspect < 3:
            issues.append("imbalance_window_too_shallow")

    return issues


def has_valid_parameter_structure(params: dict[str, Any]) -> bool:
    return not parameter_constraint_violations(params)


def params_signature(payload: dict[str, Any]) -> str:
    """Compute a 16-char SHA-256 hex digest of the canonical JSON of payload.

    At suggest time: payload = {"search": search_params, "locked": locked_params}
    At record time:  payload = {"csv_meta": {...}, "locked": locked_params, "search": search_params}
    Including locked_params in both cases prevents signature collisions when the frozen
    fib profile or timeframe changes between evaluation contexts.
    """
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()[:16]


def search_space_hash(space: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_json(space).encode("utf-8")).hexdigest()[:16]


def build_domains(space: dict[str, Any]) -> list[Domain]:
    domains: list[Domain] = []
    for name, spec in space["search_parameters"].items():
        kind = spec["type"]
        if "values" in spec:
            values = [normalize_number(v) for v in spec["values"]]
        elif kind == "bool":
            values = [True, False]
        else:
            step = spec["step"]
            start = spec["min"]
            stop = spec["max"]
            values = []
            cursor = start
            while cursor <= stop + (step / 10.0):
                values.append(normalize_number(cursor))
                cursor += step
        domains.append(Domain(name=name, kind=kind, values=values))
    return domains


def random_choice(domain: Domain, rng: random.Random) -> Any:
    return rng.choice(domain.values)


def neighbor_choice(domain: Domain, current: Any, rng: random.Random) -> Any:
    if current not in domain.values:
        return random_choice(domain, rng)
    if len(domain.values) == 1:
        return current
    index = domain.values.index(current)
    if domain.kind in {"int", "float"}:
        offsets = [
            offset
            for offset in (-2, -1, 1, 2)
            if 0 <= index + offset < len(domain.values)
        ]
        if offsets:
            return domain.values[index + rng.choice(offsets)]
    alternatives = [value for value in domain.values if value != current]
    return rng.choice(alternatives)


def sample_random_params(domains: list[Domain], rng: random.Random) -> dict[str, Any]:
    return {domain.name: random_choice(domain, rng) for domain in domains}


def load_trials_jsonl(ledger_path: Path) -> list[dict[str, Any]]:
    if not ledger_path.exists():
        return []
    trials: list[dict[str, Any]] = []
    with ledger_path.open() as handle:
        for line in handle:
            line = line.strip()
            if line:
                trials.append(json.loads(line))
    return trials


def load_trials_jsonl_csv_full(ledger_path: Path) -> list[dict[str, Any]]:
    """Load authoritative trials from JSONL (both CSV_FULL and TV_MCP_STRICT)."""
    return [
        t
        for t in load_trials_jsonl(ledger_path)
        if t.get("evaluation_mode") in ("CSV_FULL", "TV_MCP_STRICT")
    ]


def append_trial_jsonl(ledger_path: Path, trial: dict[str, Any]) -> None:
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    with ledger_path.open("a") as handle:
        handle.write(json.dumps(trial, sort_keys=True) + "\n")


def connect_db(dsn: str):
    conn = psycopg2.connect(dsn)
    conn.autocommit = True
    return conn


def json_adapter(payload: Any) -> Json:
    return Json(payload, dumps=lambda obj: json.dumps(obj, sort_keys=True))


def fetch_db_trials(conn, profile: str) -> list[dict[str, Any]]:
    """Fetch all authoritative trials (CSV_FULL and TV_MCP_STRICT evaluation modes)."""
    query = """
        SELECT
          trial_id,
          batch_id,
          parent_trial_id,
          profile_name AS profile,
          evaluation_mode,
          origin,
          status,
          params_signature,
          search_parameters,
          locked_parameters,
          runtime_context,
          metrics,
          objective,
          source_csv,
          notes,
          recorded_at,
          created_at
        FROM warbird_strategy_tuning_trials
        WHERE profile_name = %s
          AND evaluation_mode IN ('CSV_FULL', 'TV_MCP_STRICT')
        ORDER BY created_at ASC, trial_id ASC
    """
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(query, (profile,))
        rows = cur.fetchall()
    return [dict(row) for row in rows]


def persist_suggestion_batch(
    conn,
    space: dict[str, Any],
    batch_id: str,
    count: int,
    seed: int | None,
    suggestions: list[dict[str, Any]],
    space_path: Path,
) -> None:
    batch_query = """
        INSERT INTO warbird_strategy_tuning_batches (
          batch_id,
          profile_name,
          generation_seed,
          requested_count,
          search_space_path,
          search_space_hash,
          objective,
          locked_parameters,
          runtime_context
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (batch_id) DO NOTHING
    """
    trial_query = """
        INSERT INTO warbird_strategy_tuning_trials (
          trial_id,
          batch_id,
          parent_trial_id,
          profile_name,
          evaluation_mode,
          origin,
          status,
          params_signature,
          search_parameters,
          locked_parameters,
          runtime_context,
          created_at,
          updated_at
        ) VALUES (%s, %s, %s, %s, 'PENDING', %s, 'SUGGESTED', %s, %s, %s, %s, NOW(), NOW())
        ON CONFLICT (profile_name, params_signature, evaluation_mode) DO NOTHING
    """
    with conn.cursor() as cur:
        cur.execute(
            batch_query,
            (
                batch_id,
                space["profile_name"],
                seed,
                count,
                str(space_path),
                search_space_hash(space),
                json_adapter(space["objective"]),
                json_adapter(space["locked_parameters"]),
                json_adapter(space["runtime_context"]),
            ),
        )
        for suggestion in suggestions:
            cur.execute(
                trial_query,
                (
                    suggestion["trial_id"],
                    batch_id,
                    suggestion["parent_trial_id"],
                    suggestion["profile"],
                    suggestion["origin"],
                    suggestion["params_signature"],
                    json_adapter(suggestion["search_parameters"]),
                    json_adapter(suggestion["locked_parameters"]),
                    json_adapter(suggestion["runtime_context"]),
                ),
            )


def upsert_recorded_trial(conn, trial: dict[str, Any]) -> None:
    metrics = trial["metrics"]
    objective = trial["objective"]
    lookup_query = """
        SELECT trial_id
        FROM warbird_strategy_tuning_trials
        WHERE profile_name = %s
          AND params_signature = %s
          AND evaluation_mode = %s
        LIMIT 1
    """
    query = """
        INSERT INTO warbird_strategy_tuning_trials (
          trial_id,
          profile_name,
          evaluation_mode,
          origin,
          status,
          params_signature,
          search_parameters,
          locked_parameters,
          runtime_context,
          metrics,
          objective,
          source_csv,
          notes,
          objective_score,
          net_pnl,
          profit_factor,
          max_drawdown,
          max_drawdown_pct,
          survival_30_tick_pct,
          total_trades,
          percent_profitable,
          long_net_pnl,
          long_profit_factor,
          short_net_pnl,
          short_profit_factor,
          recorded_at,
          created_at,
          updated_at
        ) VALUES (
          %s, %s, %s, 'manual_record', 'RECORDED', %s, %s, %s, %s, %s, %s, %s, %s,
          %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW(), NOW()
        )
        ON CONFLICT (trial_id)
        DO UPDATE SET
          trial_id = EXCLUDED.trial_id,
          origin = 'manual_record',
          status = 'RECORDED',
          evaluation_mode = EXCLUDED.evaluation_mode,
          params_signature = EXCLUDED.params_signature,
          search_parameters = EXCLUDED.search_parameters,
          locked_parameters = EXCLUDED.locked_parameters,
          runtime_context = EXCLUDED.runtime_context,
          metrics = EXCLUDED.metrics,
          objective = EXCLUDED.objective,
          source_csv = EXCLUDED.source_csv,
          notes = EXCLUDED.notes,
          objective_score = EXCLUDED.objective_score,
          net_pnl = EXCLUDED.net_pnl,
          profit_factor = EXCLUDED.profit_factor,
          max_drawdown = EXCLUDED.max_drawdown,
          max_drawdown_pct = EXCLUDED.max_drawdown_pct,
          survival_30_tick_pct = EXCLUDED.survival_30_tick_pct,
          total_trades = EXCLUDED.total_trades,
          percent_profitable = EXCLUDED.percent_profitable,
          long_net_pnl = EXCLUDED.long_net_pnl,
          long_profit_factor = EXCLUDED.long_profit_factor,
          short_net_pnl = EXCLUDED.short_net_pnl,
          short_profit_factor = EXCLUDED.short_profit_factor,
          recorded_at = EXCLUDED.recorded_at,
          updated_at = NOW()
    """
    with conn.cursor() as cur:
        cur.execute(
            lookup_query,
            (trial["profile"], trial["params_signature"], trial["evaluation_mode"]),
        )
        existing = cur.fetchone()
        if existing and existing[0]:
            trial["trial_id"] = existing[0]
        cur.execute(
            query,
            (
                trial["trial_id"],
                trial["profile"],
                trial["evaluation_mode"],
                trial["params_signature"],
                json_adapter(trial["search_parameters"]),
                json_adapter(trial["locked_parameters"]),
                json_adapter(trial["runtime_context"]),
                json_adapter(metrics),
                json_adapter(objective),
                trial["source_csv"],
                trial["notes"],
                objective["objective_score"],
                metrics["net_pnl"],
                metrics["profit_factor"],
                metrics["max_drawdown"],
                metrics["max_drawdown_pct"],
                metrics["survival_30_tick_pct"],
                metrics["total_trades"],
                metrics["percent_profitable"],
                metrics["long"]["net_pnl"],
                metrics["long"]["profit_factor"],
                metrics["short"]["net_pnl"],
                metrics["short"]["profit_factor"],
                trial["recorded_at"],
            ),
        )


def upsert_failed_trial(conn, trial: dict[str, Any]) -> None:
    """Persist a FAILED trial row to Postgres.

    Requires migration 010 to be applied (adds 'FAILED' to the status CHECK
    and the failure_reason column). Called by tv_auto_tune after Phase C migration.
    """
    query = """
        INSERT INTO warbird_strategy_tuning_trials (
          trial_id,
          profile_name,
          evaluation_mode,
          origin,
          status,
          failure_reason,
          params_signature,
          search_parameters,
          locked_parameters,
          runtime_context,
          notes,
          created_at,
          updated_at
        ) VALUES (
          %s, %s, 'TV_MCP_STRICT', 'tv_auto_tune', 'FAILED',
          %s, %s, %s, %s, %s, %s, NOW(), NOW()
        )
        ON CONFLICT (trial_id) DO UPDATE SET
          status          = 'FAILED',
          evaluation_mode = EXCLUDED.evaluation_mode,
          failure_reason  = EXCLUDED.failure_reason,
          notes           = EXCLUDED.notes,
          updated_at      = NOW()
    """
    with conn.cursor() as cur:
        cur.execute(
            query,
            (
                trial["trial_id"],
                trial.get("profile", ""),
                trial.get("failure_reason"),
                trial.get("params_signature", ""),
                json_adapter(trial.get("search_parameters", {})),
                json_adapter(trial.get("locked_parameters", {})),
                json_adapter(trial.get("runtime_context", {})),
                trial.get("error_message", ""),
            ),
        )


def fetch_db_leaderboard(
    conn, profile: str, top: int, include_failed: bool = False
) -> list[dict[str, Any]]:
    """Fetch top RECORDED trials ranked by objective score.

    With include_failed=True also returns a summary of FAILED rows appended
    after the scored rows (these have no objective score).
    """
    query = """
        SELECT
          trial_id,
          profile_name AS profile,
          evaluation_mode,
          status,
          failure_reason,
          search_parameters,
          metrics,
          objective
        FROM warbird_strategy_tuning_trials
        WHERE profile_name = %s
          AND status = 'RECORDED'
          AND evaluation_mode IN ('CSV_FULL', 'TV_MCP_STRICT')
          AND objective_score IS NOT NULL
        ORDER BY objective_score DESC, recorded_at DESC
        LIMIT %s
    """
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(query, (profile, top))
        rows = [dict(r) for r in cur.fetchall()]

    if include_failed:
        failed_query = """
            SELECT
              trial_id,
              profile_name AS profile,
              evaluation_mode,
              status,
              failure_reason,
              search_parameters,
              NULL::jsonb AS metrics,
              NULL::jsonb AS objective
            FROM warbird_strategy_tuning_trials
            WHERE profile_name = %s
              AND status = 'FAILED'
            ORDER BY created_at DESC
            LIMIT 100
        """
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(failed_query, (profile,))
            rows.extend([dict(r) for r in cur.fetchall()])

    return rows


def parse_float(value: str) -> float:
    return float(value.replace(",", "").strip())


def parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value.strip())


def extract_csv_window_meta(csv_path: Path) -> dict[str, Any]:
    """Read first and last trade timestamps from a TradingView trade-list CSV.

    Returns a dict with start_date, end_date (ISO date strings) and trade_count.
    This metadata is included in the trial identity signature so that runs against
    different date windows never collide under the same signature.
    """
    timestamps: list[datetime] = []
    trade_count = 0
    with csv_path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames:
            reader.fieldnames = [f.strip() for f in reader.fieldnames]
        for row in reader:
            row = {k.strip(): v for k, v in row.items() if k is not None}
            try:
                ts = parse_time(row["Date and time"])
                timestamps.append(ts)
                trade_count += 1
            except (KeyError, ValueError):
                continue
    if not timestamps:
        raise ValueError(f"Could not extract any timestamps from {csv_path}")
    timestamps.sort()
    return {
        "start_date": timestamps[0].date().isoformat(),
        "end_date": timestamps[-1].date().isoformat(),
        "row_count": trade_count,
    }


def validate_csv_window(meta: dict[str, Any], required_start: str) -> None:
    """Refuse ingestion if the CSV window starts after the required floor date.

    TradingView Deep Backtesting From/To is UI-only — this post-hoc check enforces
    that the operator ran the full 2020+ window before exporting the CSV.
    """
    csv_start = date.fromisoformat(meta["start_date"])
    floor = date.fromisoformat(required_start)
    if csv_start > floor:
        raise ValueError(
            f"CSV window starts {meta['start_date']} which is after the required floor "
            f"{required_start}. Set TradingView Deep Backtesting 'From' to {required_start} "
            f"or earlier, re-run, re-export, then re-record."
        )


def summarize_side(rows: list[dict[str, Any]]) -> dict[str, Any]:
    net = sum(row["net_pnl"] for row in rows)
    gross_profit = sum(row["net_pnl"] for row in rows if row["net_pnl"] > 0)
    gross_loss = abs(sum(row["net_pnl"] for row in rows if row["net_pnl"] < 0))
    wins = sum(1 for row in rows if row["net_pnl"] > 0)
    losses = sum(1 for row in rows if row["net_pnl"] < 0)
    count = len(rows)
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else math.inf
    avg_pnl = net / count if count else 0.0
    return {
        "trades": count,
        "net_pnl": round(net, 2),
        "wins": wins,
        "losses": losses,
        "percent_profitable": round((wins / count * 100.0), 2) if count else 0.0,
        "profit_factor": None if math.isinf(profit_factor) else round(profit_factor, 3),
        "avg_pnl": round(avg_pnl, 2),
    }


def max_drawdown_from_rows(rows: list[dict[str, Any]]) -> float:
    if not rows:
        return 0.0
    baseline = rows[0]["cumulative_pnl"] - rows[0]["net_pnl"]
    peak = 0.0
    max_drawdown = 0.0
    for row in rows:
        equity = row["cumulative_pnl"] - baseline
        peak = max(peak, equity)
        max_drawdown = max(max_drawdown, peak - equity)
    return max_drawdown


def summarize_window(
    rows: list[dict[str, Any]],
    initial_capital: float,
) -> dict[str, Any]:
    if not rows:
        return {
            "start_date": None,
            "end_date": None,
            "trades": 0,
            "net_pnl": 0.0,
            "profit_factor": None,
            "expectancy_per_trade": 0.0,
            "max_drawdown_pct": 0.0,
            "return_over_drawdown": 0.0,
            "long_trades": 0,
            "short_trades": 0,
        }

    gross_profit = sum(row["net_pnl"] for row in rows if row["net_pnl"] > 0)
    gross_loss = abs(sum(row["net_pnl"] for row in rows if row["net_pnl"] < 0))
    trades = len(rows)
    net_pnl = round(sum(row["net_pnl"] for row in rows), 2)
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else math.inf
    max_drawdown = max_drawdown_from_rows(rows)
    max_drawdown_pct = round(max_drawdown / initial_capital * 100.0, 2)
    return_pct = round(net_pnl / initial_capital * 100.0, 2)
    return_over_drawdown = (
        max(return_pct, 0.0) / max(max_drawdown_pct, 0.01)
        if max_drawdown_pct > 0
        else 0.0
    )
    long_trades = sum(1 for row in rows if row["side"] == "long")
    short_trades = sum(1 for row in rows if row["side"] == "short")
    return {
        "start_date": rows[0]["exit_time"].date().isoformat(),
        "end_date": rows[-1]["exit_time"].date().isoformat(),
        "trades": trades,
        "net_pnl": net_pnl,
        "profit_factor": None if math.isinf(profit_factor) else round(profit_factor, 3),
        "expectancy_per_trade": round(net_pnl / trades, 4) if trades else 0.0,
        "max_drawdown_pct": max_drawdown_pct,
        "return_over_drawdown": round(return_over_drawdown, 4),
        "long_trades": long_trades,
        "short_trades": short_trades,
    }


def build_time_windows(
    rows: list[dict[str, Any]],
    window_count: int = DEFAULT_ROLLING_WINDOW_COUNT,
) -> list[list[dict[str, Any]]]:
    if not rows or window_count <= 0:
        return []

    start = rows[0]["exit_time"]
    end = rows[-1]["exit_time"]
    if end <= start:
        return [rows]

    total_seconds = (end - start).total_seconds()
    windows: list[list[dict[str, Any]]] = [[] for _ in range(window_count)]
    for row in rows:
        elapsed = (row["exit_time"] - start).total_seconds()
        idx = min(int((elapsed / total_seconds) * window_count), window_count - 1)
        windows[idx].append(row)

    return [window for window in windows if window]


def summarize_closed_trades(
    closed_trades: list[dict[str, Any]],
    initial_capital: float,
    survival_stop_usd: float,
    footprint_available_from: str = DEFAULT_FOOTPRINT_AVAILABLE_FROM,
) -> dict[str, Any]:
    if not closed_trades:
        raise ValueError("No closed trades found")

    closed_trades = sorted(closed_trades, key=lambda row: row["exit_time"])
    total_trades = len(closed_trades)
    gross_profit = sum(row["net_pnl"] for row in closed_trades if row["net_pnl"] > 0)
    gross_loss = abs(sum(row["net_pnl"] for row in closed_trades if row["net_pnl"] < 0))
    wins = sum(1 for row in closed_trades if row["net_pnl"] > 0)
    losses = sum(1 for row in closed_trades if row["net_pnl"] < 0)
    net_pnl = round(sum(row["net_pnl"] for row in closed_trades), 2)
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else math.inf
    percent_profitable = (
        round((wins / total_trades * 100.0), 2) if total_trades else 0.0
    )
    avg_trade = round(net_pnl / total_trades, 2) if total_trades else 0.0
    avg_win = round(gross_profit / wins, 2) if wins else 0.0
    avg_loss = round(gross_loss / losses, 2) if losses else 0.0
    max_drawdown = max_drawdown_from_rows(closed_trades)

    long_rows = [row for row in closed_trades if row["side"] == "long"]
    short_rows = [row for row in closed_trades if row["side"] == "short"]
    survivors = sum(
        1 for row in closed_trades if row["adverse_excursion"] > survival_stop_usd
    )
    survival_rate = (
        round((survivors / total_trades * 100.0), 2) if total_trades else 0.0
    )

    by_year: dict[str, float] = {}
    year_trade_counts: dict[str, int] = {}
    for row in closed_trades:
        year = str(row["exit_time"].year)
        by_year[year] = round(by_year.get(year, 0.0) + row["net_pnl"], 2)
        year_trade_counts[year] = year_trade_counts.get(year, 0) + 1

    fp_from_date = date.fromisoformat(footprint_available_from)
    fp_trades = [
        row for row in closed_trades if row["exit_time"].date() >= fp_from_date
    ]
    rolling_windows = [
        summarize_window(window_rows, initial_capital)
        for window_rows in build_time_windows(closed_trades)
    ]

    positive_years = sum(1 for pnl in by_year.values() if pnl > 0)
    year_positive_ratio = positive_years / float(len(by_year)) if by_year else 0.0

    return {
        "total_trades": total_trades,
        "wins": wins,
        "losses": losses,
        "percent_profitable": percent_profitable,
        "net_pnl": net_pnl,
        "gross_profit": round(gross_profit, 2),
        "gross_loss": round(gross_loss, 2),
        "profit_factor": None if math.isinf(profit_factor) else round(profit_factor, 3),
        "avg_trade": avg_trade,
        "avg_win": avg_win,
        "avg_loss": avg_loss,
        "max_drawdown": round(max_drawdown, 2),
        "max_drawdown_pct": round(max_drawdown / initial_capital * 100.0, 2),
        "return_on_initial_pct": round(net_pnl / initial_capital * 100.0, 2),
        "survival_30_tick_pct": survival_rate,
        "long": summarize_side(long_rows),
        "short": summarize_side(short_rows),
        "by_year": by_year,
        "year_trade_counts": year_trade_counts,
        "year_positive_ratio": round(year_positive_ratio, 4),
        "footprint_cohort": {
            "from_date": footprint_available_from,
            "trades": len(fp_trades),
            "net_pnl": round(sum(row["net_pnl"] for row in fp_trades), 2),
            "profit_factor": summarize_window(fp_trades, initial_capital)[
                "profit_factor"
            ],
            "long": summarize_side([row for row in fp_trades if row["side"] == "long"]),
            "short": summarize_side(
                [row for row in fp_trades if row["side"] == "short"]
            ),
        },
        "rolling_windows": {
            "window_count": DEFAULT_ROLLING_WINDOW_COUNT,
            "windows": rolling_windows,
            "valid_windows": len(rolling_windows),
        },
    }


def calculate_trade_metrics(
    csv_path: Path,
    initial_capital: float,
    survival_stop_usd: float,
    footprint_available_from: str = DEFAULT_FOOTPRINT_AVAILABLE_FROM,
) -> dict[str, Any]:
    """Compute trade metrics from a TradingView trade-list CSV.

    Produces two metric surfaces:
    - All bars (2020+): primary surface used for leaderboard ranking.
    - Footprint cohort (footprint_available_from+): diagnostic surface.
      TV tick archives are bounded — most 2020-2023 bars have no footprint data.
      A knob that looks good only in the footprint-rich tail should not dominate.
    """
    by_trade: dict[int, dict[str, Any]] = {}
    with csv_path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames:
            reader.fieldnames = [field.strip() for field in reader.fieldnames]
        for row in reader:
            row = {key.strip(): value for key, value in row.items() if key is not None}
            trade_id = int(row["Trade #"])
            bucket = by_trade.setdefault(trade_id, {})
            row_type = row["Type"].strip().lower()
            parsed = {
                "trade_id": trade_id,
                "type": row["Type"].strip(),
                "signal": row["Signal"].strip(),
                "time": parse_time(row["Date and time"]),
                "price": parse_float(row["Price USD"]),
                "net_pnl": parse_float(row["Net P&L USD"]),
                "cumulative_pnl": parse_float(row["Cumulative P&L USD"]),
                "adverse_excursion": parse_float(row["Adverse excursion USD"]),
                "favorable_excursion": parse_float(row["Favorable excursion USD"]),
            }
            if row_type.startswith("entry"):
                bucket["entry"] = parsed
            elif row_type.startswith("exit"):
                bucket["exit"] = parsed

    closed_trades: list[dict[str, Any]] = []
    for trade_id, pair in sorted(by_trade.items()):
        entry = pair.get("entry")
        exit_row = pair.get("exit")
        if not entry and not exit_row:
            continue
        anchor = entry if entry is not None else exit_row
        if anchor is None:
            continue
        result_row = exit_row if exit_row is not None else entry
        if result_row is None:
            continue
        excursion_row = entry if entry is not None else exit_row
        if excursion_row is None:
            continue
        side = "long" if "long" in anchor["type"].lower() else "short"
        net_pnl = result_row["net_pnl"]
        cumulative_pnl = result_row["cumulative_pnl"]
        exit_time = result_row["time"]
        adverse_excursion = excursion_row["adverse_excursion"]
        closed_trades.append(
            {
                "trade_id": trade_id,
                "side": side,
                "entry_time": entry["time"] if entry else exit_time,
                "exit_time": exit_time,
                "net_pnl": net_pnl,
                "cumulative_pnl": cumulative_pnl,
                "adverse_excursion": adverse_excursion,
            }
        )
    return summarize_closed_trades(
        closed_trades,
        initial_capital=initial_capital,
        survival_stop_usd=survival_stop_usd,
        footprint_available_from=footprint_available_from,
    )


def score_trial(metrics: dict[str, Any], objective: dict[str, Any]) -> dict[str, Any]:
    """Score a trial for pre-AG parameter tuning with profit-first ranking.

    Richness compatibility is preserved for AG:
      - hard sample gate stays in place (min trades and both directions required)
      - richness/balance/coverage/diversity remain in the weighted score

    Profitability now leads ranking:
      - profit_factor score (primary)
      - expectancy per trade score (secondary)

    A realism gate still penalises unrealistic or structurally weak runs.
    """

    trade_bounds = objective.get("trade_count_bounds", {})
    min_trades = int(config_value(trade_bounds, "min", 200))
    target_trades = int(config_value(trade_bounds, "target", max(min_trades, 400)))
    max_trades = int(config_value(trade_bounds, "max", max(target_trades, 2200)))
    target_trades = max(target_trades, min_trades)
    max_trades = max(max_trades, target_trades)

    weights = objective.get("weights", {})
    pf_range = objective.get("profit_factor_range", {})
    expectancy_cfg = objective.get("expectancy_per_trade", {})
    drawdown_cfg = objective.get("return_over_drawdown", {})
    footprint_cfg = objective.get("footprint_cohort", {})
    rolling_cfg = objective.get("rolling_window_stability", {})
    yearly_cfg = objective.get("yearly_consistency", {})
    suspicious_cfg = objective.get("suspicious_perfection", {})
    side_pf_floor = objective.get("side_profit_factor_floor", {})

    total = metrics["total_trades"]
    long_trades = metrics["long"]["trades"] if metrics["long"] else 0
    short_trades = metrics["short"]["trades"] if metrics["short"] else 0

    def normalized_range_score(
        value: float | None, floor: float, target: float
    ) -> float:
        if value is None:
            return 0.0
        target = max(target, floor + 1e-9)
        return clamp01((float(value) - floor) / (target - floor))

    def pf_score(value: float | None) -> tuple[float, float]:
        pf_floor = float(config_value(pf_range, "floor", 0.9))
        pf_target = float(config_value(pf_range, "target", 1.6))
        if value is None or not math.isfinite(float(value)):
            numeric = float(config_value(pf_range, "realism_cap", 2.4))
        else:
            numeric = float(value)
        return normalized_range_score(numeric, pf_floor, pf_target), numeric

    def expectancy_score_fn(value: float) -> float:
        exp_floor = float(config_value(expectancy_cfg, "floor", 0.0))
        exp_target = float(config_value(expectancy_cfg, "target", 18.0))
        score = normalized_range_score(value, exp_floor, exp_target)
        if value < 0:
            negative_penalty = clamp01(
                float(config_value(expectancy_cfg, "negative_penalty", 0.35))
            )
            score *= negative_penalty
        return score

    def drawdown_efficiency_score(value: float) -> float:
        dd_floor = float(config_value(drawdown_cfg, "floor", 0.25))
        dd_target = float(config_value(drawdown_cfg, "target", 1.5))
        return normalized_range_score(value, dd_floor, dd_target)

    # Hard reject — return score=None so the caller can mark as insufficient sample.
    if total < min_trades or long_trades == 0 or short_trades == 0:
        return {
            "objective_score": None,
            "insufficient_sample": True,
            "components": {
                "total_trades": total,
                "long_trades": long_trades,
                "short_trades": short_trades,
                "min_required": min_trades,
                "target_trades": target_trades,
            },
        }

    # ── Richness components (kept for AG compatibility) ─────────────────────
    if total <= target_trades:
        trade_density = clamp01(
            (total - min_trades) / float(max(target_trades - min_trades, 1))
        )
    else:
        trade_density = clamp01(
            1.0 - (total - target_trades) / float(max(max_trades - target_trades, 1))
        )
    sample_richness = trade_density
    long_share = long_trades / float(total)
    directional_balance = 1.0 - abs(long_share - 0.5) * 2.0

    by_year = metrics.get("by_year") or {}
    year_trade_counts = metrics.get("year_trade_counts") or {}
    expected_years = 6  # 2020-2025 training window
    years_present = sum(
        1
        for year, pnl in by_year.items()
        if year_trade_counts.get(year, 0) >= 20 and pnl != 0
    )
    regime_coverage = min(years_present / float(expected_years), 1.0)

    wins = metrics.get("wins", 0)
    losses = metrics.get("losses", 0)
    if total > 0 and wins > 0 and losses > 0:
        p_w = wins / float(total)
        p_l = losses / float(total)
        entropy_2class = -(p_w * math.log2(p_w) + p_l * math.log2(p_l))
        outcome_diversity = entropy_2class
    else:
        outcome_diversity = 0.0

    # ── Profitability components (profit-first ranking) ─────────────────────
    profit_factor = metrics.get("profit_factor")
    profit_factor_score, pf_numeric = pf_score(profit_factor)

    expectancy = metrics.get("net_pnl", 0.0) / float(total)
    expectancy_score = expectancy_score_fn(expectancy)

    return_pct = float(metrics.get("return_on_initial_pct", 0.0) or 0.0)
    max_drawdown_pct = float(metrics.get("max_drawdown_pct", 0.0) or 0.0)
    return_over_drawdown = (
        max(return_pct, 0.0) / max(max_drawdown_pct, 0.01)
        if max_drawdown_pct > 0
        else 0.0
    )
    drawdown_efficiency = drawdown_efficiency_score(return_over_drawdown)

    fp_metrics = metrics.get("footprint_cohort") or {}
    fp_trades = int(fp_metrics.get("trades") or 0)
    fp_expectancy = (
        fp_metrics.get("net_pnl", 0.0) / float(fp_trades) if fp_trades else 0.0
    )
    fp_pf_score, _ = pf_score(fp_metrics.get("profit_factor"))
    fp_expectancy_score = expectancy_score_fn(fp_expectancy)
    fp_presence = clamp01(
        fp_trades / float(max(int(config_value(footprint_cfg, "min_trades", 60)), 1))
    )
    footprint_stability = clamp01(
        fp_presence
        * (
            1.0
            - 0.5 * abs(fp_pf_score - profit_factor_score)
            - 0.5 * abs(fp_expectancy_score - expectancy_score)
        )
    )

    window_weights = (0.45, 0.35, 0.20)
    min_trades_per_window = int(config_value(rolling_cfg, "min_trades_per_window", 40))
    valid_windows = [
        window
        for window in (metrics.get("rolling_windows", {}).get("windows") or [])
        if int(window.get("trades") or 0) >= min_trades_per_window
    ]
    window_scores: list[float] = []
    positive_windows = 0
    for window in valid_windows:
        win_pf_score, _ = pf_score(window.get("profit_factor"))
        win_exp_score = expectancy_score_fn(
            float(window.get("expectancy_per_trade") or 0.0)
        )
        win_dd_score = drawdown_efficiency_score(
            float(window.get("return_over_drawdown") or 0.0)
        )
        window_score = (
            win_pf_score * window_weights[0]
            + win_exp_score * window_weights[1]
            + win_dd_score * window_weights[2]
        )
        window_scores.append(window_score)
        if float(window.get("net_pnl") or 0.0) > 0 and (
            window.get("profit_factor") is None
            or float(window.get("profit_factor") or 0.0) >= 1.0
        ):
            positive_windows += 1

    if window_scores:
        rolling_mean = sum(window_scores) / len(window_scores)
        rolling_std = (
            statistics.pstdev(window_scores) if len(window_scores) > 1 else 0.0
        )
        max_std = float(config_value(rolling_cfg, "max_score_stddev", 0.18))
        std_score = clamp01(1.0 - rolling_std / max(max_std, 1e-9))
        target_positive_windows = float(
            config_value(rolling_cfg, "target_positive_windows", 0.75)
        )
        positive_ratio = positive_windows / float(len(window_scores))
        positive_score = clamp01(positive_ratio / max(target_positive_windows, 1e-9))
        rolling_stability = clamp01(
            (0.6 * rolling_mean + 0.4 * positive_score) * std_score
        )
    else:
        rolling_mean = 0.0
        rolling_std = 0.0
        positive_ratio = 0.0
        rolling_stability = 0.0

    year_values = list(by_year.values())
    if year_values:
        positive_year_ratio = float(metrics.get("year_positive_ratio") or 0.0)
        target_positive_ratio = float(
            config_value(yearly_cfg, "target_positive_ratio", 0.67)
        )
        positive_year_score = clamp01(
            positive_year_ratio / max(target_positive_ratio, 1e-9)
        )
        total_abs_year_pnl = sum(abs(value) for value in year_values)
        dominance = (
            max(abs(value) for value in year_values) / total_abs_year_pnl
            if total_abs_year_pnl > 0
            else 1.0
        )
        max_dominance = float(config_value(yearly_cfg, "max_dominance", 0.55))
        dominance_score = (
            1.0
            if dominance <= max_dominance
            else clamp01(
                1.0 - (dominance - max_dominance) / max(1.0 - max_dominance, 1e-9)
            )
        )
        yearly_consistency = clamp01(positive_year_score * dominance_score)
    else:
        positive_year_ratio = 0.0
        dominance = 1.0
        yearly_consistency = 0.0

    # ── Realism gate ─────────────────────────────────────────────────────────
    long_pf = metrics.get("long", {}).get("profit_factor")
    short_pf = metrics.get("short", {}).get("profit_factor")
    long_floor = float(config_value(side_pf_floor, "long", 0.95))
    short_floor = float(config_value(side_pf_floor, "short", 0.95))
    long_ok = long_pf is None or long_pf >= long_floor
    short_ok = short_pf is None or short_pf >= short_floor
    pf_floor = float(config_value(pf_range, "floor", 0.9))
    realism_cap = float(config_value(pf_range, "realism_cap", 2.4))
    suspicious_pf = pf_numeric >= float(
        config_value(suspicious_cfg, "profit_factor", realism_cap)
    )
    suspicious_ratio = return_over_drawdown >= float(
        config_value(suspicious_cfg, "return_over_drawdown", 3.5)
    )
    suspicious_perfection = (
        suspicious_pf
        or suspicious_ratio
        or (metrics.get("losses", 0) == 0 and total >= min_trades)
    )
    realism_ok = (
        (pf_floor <= pf_numeric <= realism_cap)
        and (expectancy >= 0)
        and long_ok
        and short_ok
        and not suspicious_perfection
    )
    realism_gate_penalty = float(config_value(weights, "realism_gate_penalty", 0.40))

    rolling_floor = float(config_value(rolling_cfg, "min_score", 0.45))
    footprint_floor = float(config_value(footprint_cfg, "min_score", 0.45))
    yearly_floor = float(config_value(yearly_cfg, "min_score", 0.45))
    regime_fragile = (
        rolling_stability < rolling_floor
        or footprint_stability < footprint_floor
        or yearly_consistency < yearly_floor
    )
    instability_penalty = float(config_value(weights, "instability_penalty", 0.55))

    # ── Weighted sum ─────────────────────────────────────────────────────────
    default_component_weights = {
        "profit_factor": 0.23,
        "expectancy": 0.12,
        "trade_density": 0.12,
        "directional_balance": 0.08,
        "regime_coverage": 0.06,
        "outcome_diversity": 0.04,
        "drawdown_efficiency": 0.14,
        "rolling_stability": 0.12,
        "footprint_stability": 0.05,
        "yearly_consistency": 0.04,
    }
    raw_weights: dict[str, float] = {}
    for key, default_value in default_component_weights.items():
        if key == "trade_density":
            raw_weights[key] = max(
                0.0,
                float(
                    config_value(
                        weights,
                        key,
                        config_value(weights, "sample_richness", default_value),
                    )
                ),
            )
        else:
            raw_weights[key] = max(
                0.0, float(config_value(weights, key, default_value))
            )
    weight_sum = sum(raw_weights.values())
    if weight_sum <= 0.0:
        raw_weights = default_component_weights
        weight_sum = sum(raw_weights.values())
    normalized_weights = {k: v / weight_sum for k, v in raw_weights.items()}

    raw_score = (
        profit_factor_score * normalized_weights["profit_factor"]
        + expectancy_score * normalized_weights["expectancy"]
        + trade_density * normalized_weights["trade_density"]
        + directional_balance * normalized_weights["directional_balance"]
        + regime_coverage * normalized_weights["regime_coverage"]
        + outcome_diversity * normalized_weights["outcome_diversity"]
        + drawdown_efficiency * normalized_weights["drawdown_efficiency"]
        + rolling_stability * normalized_weights["rolling_stability"]
        + footprint_stability * normalized_weights["footprint_stability"]
        + yearly_consistency * normalized_weights["yearly_consistency"]
    )

    score = raw_score
    if not realism_ok:
        score *= realism_gate_penalty
    if regime_fragile:
        score *= instability_penalty
    score = clamp01(score)

    components = {
        "profit_factor_score": round(profit_factor_score, 4),
        "expectancy_score": round(expectancy_score, 4),
        "expectancy_per_trade": round(expectancy, 4),
        "trade_density": round(trade_density, 4),
        "sample_richness": round(sample_richness, 4),
        "directional_balance": round(directional_balance, 4),
        "regime_coverage": round(regime_coverage, 4),
        "outcome_diversity": round(outcome_diversity, 4),
        "drawdown_efficiency": round(drawdown_efficiency, 4),
        "return_over_drawdown": round(return_over_drawdown, 4),
        "rolling_stability": round(rolling_stability, 4),
        "rolling_mean_score": round(rolling_mean, 4),
        "rolling_score_stddev": round(rolling_std, 4),
        "rolling_positive_ratio": round(positive_ratio, 4),
        "footprint_stability": round(footprint_stability, 4),
        "footprint_trades": fp_trades,
        "yearly_consistency": round(yearly_consistency, 4),
        "year_positive_ratio": round(positive_year_ratio, 4),
        "year_pnl_dominance": round(dominance, 4),
        "long_profit_factor": None if long_pf is None else round(float(long_pf), 4),
        "short_profit_factor": None if short_pf is None else round(float(short_pf), 4),
        "suspicious_perfection": suspicious_perfection,
        "realism_ok": realism_ok,
        "regime_fragile": regime_fragile,
        "raw_score": round(raw_score, 4),
        "weights": {k: round(v, 4) for k, v in normalized_weights.items()},
    }

    return {
        "objective_score": round(score, 4),
        "components": components,
    }


def make_trial_record(
    config: dict[str, Any],
    csv_path: Path,
    space: dict[str, Any],
    initial_capital: float,
    survival_stop_usd: float,
    notes: str,
    required_csv_start: str = DEFAULT_REQUIRED_CSV_START,
    footprint_available_from: str = DEFAULT_FOOTPRINT_AVAILABLE_FROM,
) -> dict[str, Any]:
    """Build a CSV_FULL trial record.

    Trial identity signature includes search_parameters + locked_parameters +
    csv_window_metadata so that re-runs against different date windows or frozen
    profile changes produce distinct records rather than colliding on the unique constraint.
    """
    csv_meta = extract_csv_window_meta(csv_path)
    validate_csv_window(csv_meta, required_csv_start)

    metrics = calculate_trade_metrics(
        csv_path, initial_capital, survival_stop_usd, footprint_available_from
    )
    scoring = score_trial(metrics, space["objective"])

    if scoring.get("insufficient_sample"):
        raise ValueError(
            f"Hard reject — insufficient sample for AG training: "
            f"total={scoring['components'].get('total_trades')}, "
            f"long={scoring['components'].get('long_trades')}, "
            f"short={scoring['components'].get('short_trades')}, "
            f"min_required={scoring['components'].get('min_required')}"
        )

    search_params = config["search_parameters"]
    locked_params = config["locked_parameters"]

    # Full identity: search + locked + csv window + pinned commission/slippage from runtime context
    runtime = config.get("runtime_context", space.get("runtime_context", {}))
    sig_payload = {
        "search": search_params,
        "locked": filter_signature_locked_params(space, locked_params),
        "csv_meta": csv_meta,
        "commission": runtime.get("commission_per_contract_usd"),
        "slippage_ticks": runtime.get("slippage_ticks"),
    }

    return {
        "trial_id": config["trial_id"],
        "recorded_at": utc_now(),
        "profile": space["profile_name"],
        "evaluation_mode": "CSV_FULL",
        "params_signature": params_signature(sig_payload),
        "source_csv": str(csv_path),
        "search_parameters": search_params,
        "locked_parameters": locked_params,
        "runtime_context": {**runtime, "csv_meta": csv_meta},
        "metrics": metrics,
        "objective": scoring,
        "notes": notes,
    }


def render_markdown_table(rows: list[dict[str, Any]]) -> str:
    def fmt(value: Any, suffix: str = "") -> str:
        if value is None:
            return "na"
        if isinstance(value, float):
            return f"{value:.2f}{suffix}"
        return f"{value}{suffix}"

    header = "| rank | trial_id | score | net_pnl | pf | dd_pct | survival | fp_pf | params |\n"
    divider = "| --- | --- | --- | --- | --- | --- | --- | --- | --- |\n"
    body = []
    for rank, row in enumerate(rows, start=1):
        metrics = row["metrics"]
        fp_cohort = metrics.get("footprint_cohort", {})
        fp_pf = fp_cohort.get("profit_factor")
        params = ", ".join(f"{k}={v}" for k, v in row["search_parameters"].items())
        score_val = row.get("objective", {}).get("objective_score")
        score_str = f"{score_val:.4f}" if score_val is not None else "na"
        body.append(
            f"| {rank} | {row['trial_id']} | {score_str} | "
            f"{fmt(metrics['net_pnl'])} | {fmt(metrics['profit_factor'])} | "
            f"{fmt(metrics['max_drawdown_pct'], '%')} | {fmt(metrics['survival_30_tick_pct'], '%')} | "
            f"{fmt(fp_pf)} | {params} |"
        )
    return header + divider + "\n".join(body)


def generate_suggestions(
    space: dict[str, Any],
    historical_trials: list[dict[str, Any]],
    count: int,
    rng: random.Random,
) -> list[dict[str, Any]]:
    """Generate candidate configs from the search space.

    Deduplication is based on the suggest-time signature: hash(search + locked).
    This prevents collisions when the frozen fib profile changes between profile versions.
    historical_trials must already be filtered to authoritative scored modes.
    """
    domains = build_domains(space)
    domain_map = {domain.name: domain for domain in domains}
    locked_params = space["locked_parameters"]
    signature_locked_params = filter_signature_locked_params(space, locked_params)

    def suggest_sig(search_params: dict[str, Any]) -> str:
        return params_signature(
            {"locked": signature_locked_params, "search": search_params}
        )

    def historical_sig(trial: dict[str, Any]) -> str:
        return params_signature(
            {
                "locked": filter_signature_locked_params(
                    space, trial.get("locked_parameters", locked_params)
                ),
                "search": trial["search_parameters"],
            }
        )

    def sample_valid_params(max_attempts: int = 256) -> dict[str, Any]:
        for _ in range(max_attempts):
            candidate = sample_random_params(domains, rng)
            if has_valid_parameter_structure(candidate):
                return candidate
        raise RuntimeError(
            "Could not generate a valid parameter set from the current search space"
        )

    def mutate_params(parent_params: dict[str, Any]) -> dict[str, Any]:
        fallback = dict(parent_params)
        for _ in range(128):
            params = dict(parent_params)
            selected_groups = rng.sample(
                PARAMETER_GROUPS,
                k=rng.randint(1, min(2, len(PARAMETER_GROUPS))),
            )
            mutate_domains: list[Domain] = []
            for group in selected_groups:
                members = [domain_map[name] for name in group if name in domain_map]
                if not members:
                    continue
                mutate_domains.extend(
                    rng.sample(members, k=rng.randint(1, min(2, len(members))))
                )
            if not mutate_domains:
                mutate_domains = rng.sample(
                    domains, k=rng.randint(1, min(3, len(domains)))
                )
            seen_names: set[str] = set()
            for domain in mutate_domains:
                if domain.name in seen_names:
                    continue
                seen_names.add(domain.name)
                params[domain.name] = neighbor_choice(domain, params[domain.name], rng)
            if has_valid_parameter_structure(params):
                return params
        return fallback

    seen = {historical_sig(trial) for trial in historical_trials}
    ranked_trials = [
        trial
        for trial in historical_trials
        if trial.get("objective")
        and trial["objective"].get("objective_score") is not None
    ]
    ranked_trials.sort(
        key=lambda row: row["objective"]["objective_score"], reverse=True
    )

    suggestions: list[dict[str, Any]] = []

    def accept(
        params: dict[str, Any], parent_trial_id: str | None, origin: str
    ) -> None:
        if not has_valid_parameter_structure(params):
            return
        signature = suggest_sig(params)
        if signature in seen:
            return
        seen.add(signature)
        suggestions.append(
            {
                "trial_id": f"{space['profile_name']}-{len(suggestions) + 1:03d}",
                "generated_at": utc_now(),
                "profile": space["profile_name"],
                "origin": origin,
                "parent_trial_id": parent_trial_id,
                "params_signature": signature,
                "search_parameters": params,
                "locked_parameters": locked_params,
                "runtime_context": space["runtime_context"],
            }
        )

    if not ranked_trials:
        attempts = 0
        while len(suggestions) < count and attempts < count * 256:
            attempts += 1
            accept(sample_valid_params(), None, "random")
        if len(suggestions) < count:
            raise RuntimeError(
                "Could not generate enough valid suggestions from the current search space"
            )
        return suggestions

    best_score = ranked_trials[0]["objective"]["objective_score"]
    top_trials = [
        trial
        for trial in ranked_trials
        if (trial["objective"]["objective_score"] is not None)
        and trial["objective"]["objective_score"] >= (best_score - 0.35)
    ]
    if not top_trials:
        top_trials = ranked_trials[:1]
    top_trials = top_trials[: min(6, len(top_trials))]
    attempts = 0
    while len(suggestions) < count and attempts < count * 256:
        attempts += 1
        parent = rng.choice(top_trials)
        params = mutate_params(parent["search_parameters"])
        accept(params, parent["trial_id"], "mutated")
        if len(suggestions) < count:
            accept(sample_valid_params(), None, "exploratory")
    if len(suggestions) < count:
        raise RuntimeError(
            "Could not generate enough valid suggestions from the current search space"
        )
    return suggestions[:count]


def load_history(args: argparse.Namespace, profile: str) -> list[dict[str, Any]]:
    if args.storage == "postgres":
        with connect_db(args.db_dsn) as conn:
            return fetch_db_trials(conn, profile)
    return load_trials_jsonl_csv_full(Path(args.ledger))


def command_suggest(args: argparse.Namespace) -> int:
    space_path = Path(args.space)
    space = load_json(space_path)
    history = load_history(args, space["profile_name"])
    rng = random.Random(args.seed)
    suggestions = generate_suggestions(space, history, args.count, rng)
    batch_stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    batch_dir = Path(args.out_dir) / batch_stamp
    batch_dir.mkdir(parents=True, exist_ok=True)
    for index, suggestion in enumerate(suggestions, start=1):
        suggestion["trial_id"] = f"{space['profile_name']}-{batch_stamp}-{index:03d}"
        path = batch_dir / f"trial_{index:03d}.json"
        write_json(path, suggestion)

    if args.storage == "postgres":
        with connect_db(args.db_dsn) as conn:
            persist_suggestion_batch(
                conn, space, batch_stamp, args.count, args.seed, suggestions, space_path
            )

    print(f"Wrote {len(suggestions)} trial configs to {batch_dir}")
    for suggestion in suggestions:
        print(
            f"{suggestion['trial_id']}: "
            + ", ".join(f"{k}={v}" for k, v in suggestion["search_parameters"].items())
        )
    return 0


def command_record(args: argparse.Namespace) -> int:
    config = load_json(Path(args.params_file))
    space = load_json(Path(args.space))
    trial = make_trial_record(
        config=config,
        csv_path=Path(args.trades_csv),
        space=space,
        initial_capital=args.initial_capital,
        survival_stop_usd=args.survival_stop_usd,
        notes=args.notes or "",
        required_csv_start=args.required_csv_start,
        footprint_available_from=args.footprint_available_from,
    )

    if args.storage == "postgres":
        with connect_db(args.db_dsn) as conn:
            upsert_recorded_trial(conn, trial)
    else:
        append_trial_jsonl(Path(args.ledger), trial)

    fp_cohort = trial["metrics"].get("footprint_cohort", {})
    print(json.dumps(trial, indent=2, sort_keys=True, default=str))
    print(
        f"\n[footprint cohort from {fp_cohort.get('from_date')}]: "
        f"{fp_cohort.get('trades')} trades, "
        f"net_pnl={fp_cohort.get('net_pnl')}, "
        f"pf={fp_cohort.get('profit_factor')}"
    )
    return 0


def command_leaderboard(args: argparse.Namespace) -> int:
    space = load_json(Path(args.space))
    include_failed = getattr(args, "include_failed", False)

    if args.storage == "postgres":
        with connect_db(args.db_dsn) as conn:
            rows = fetch_db_leaderboard(
                conn, space["profile_name"], args.top, include_failed=include_failed
            )
    else:
        all_trials = load_trials_jsonl_csv_full(Path(args.ledger))
        scored = sorted(
            [
                t
                for t in all_trials
                if t.get("objective", {}).get("objective_score") is not None
            ],
            key=lambda row: row["objective"]["objective_score"],
            reverse=True,
        )[: args.top]
        rows = scored
        if include_failed:
            failed_rows = [t for t in all_trials if t.get("status") == "FAILED"]
            rows = scored + failed_rows

    if not rows:
        print("No trials recorded yet.")
        return 0

    scored_rows = [
        r
        for r in rows
        if r.get("objective")
        and r["objective"] is not None
        and r.get("status") != "FAILED"
    ]
    failed_rows = [r for r in rows if r.get("status") == "FAILED"]

    if scored_rows:
        print(render_markdown_table(scored_rows))

    if include_failed and failed_rows:
        # Tally by failure_reason
        from collections import Counter

        tally = Counter(r.get("failure_reason", "unknown") for r in failed_rows)
        tally_str = " / ".join(
            f"{count} {reason}" for reason, count in sorted(tally.items())
        )
        print(f"\nFailed trials: {len(failed_rows)} total ({tally_str})")

    if not scored_rows and not failed_rows:
        print("No trials recorded yet.")

    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Warbird v7 strategy tuner — pre-AG settings sweep.\n"
            "Three commands: suggest (emit candidate configs), record (ingest a TV trade CSV),\n"
            "leaderboard (rank recorded scored trials).\n\n"
            "Deep Backtesting date range is UI-only. Before exporting a CSV:\n"
            "  1. Open TradingView Strategy Tester → Properties\n"
            "  2. Set 'From' to 2020-01-01 (or earlier)\n"
            "  3. Enable Bar Magnifier\n"
            "  4. Verify commission = $1.00/contract, slippage = 1 tick\n"
            "  5. Run the backtest fully, then List of Trades → Export\n"
            "The `record` command validates the CSV start date and refuses mismatched windows."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--space", default=str(DEFAULT_SPACE_PATH), help="Search-space JSON path."
    )
    parser.add_argument(
        "--storage",
        choices=["postgres", "jsonl"],
        default="postgres",
        help="Persistence backend for suggestions and results.",
    )
    parser.add_argument(
        "--db-dsn",
        default=DEFAULT_DB_DSN,
        help="Postgres DSN for the local warbird warehouse.",
    )
    parser.add_argument(
        "--ledger",
        default=str(DEFAULT_LEDGER_PATH),
        help="JSONL ledger path when --storage=jsonl.",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    suggest = subparsers.add_parser(
        "suggest", help="Generate new trial configs from the search space."
    )
    suggest.add_argument(
        "--count", type=int, default=10, help="How many trial configs to generate."
    )
    suggest.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Random seed for deterministic suggestions.",
    )
    suggest.add_argument(
        "--out-dir",
        default=str(DEFAULT_SUGGESTIONS_DIR),
        help="Output directory for trial JSON files.",
    )
    suggest.set_defaults(func=command_suggest)

    record = subparsers.add_parser(
        "record",
        help="Score a TradingView trade export against one parameter set.",
        description=(
            "Ingest a TradingView Deep Backtest trade-list CSV.\n"
            "The CSV window start date must be on or before --required-csv-start (default 2020-01-01).\n"
            "The trial identity signature includes search_parameters + locked_parameters + csv_window_metadata\n"
            "so re-recording with a different date window produces a distinct trial, not a collision."
        ),
    )
    record.add_argument(
        "--params-file", required=True, help="Trial config JSON generated by `suggest`."
    )
    record.add_argument(
        "--trades-csv",
        required=True,
        help="TradingView strategy trade-list CSV (List of Trades export).",
    )
    record.add_argument(
        "--initial-capital",
        type=float,
        default=DEFAULT_INITIAL_CAPITAL,
        help="Initial capital used by the strategy report.",
    )
    record.add_argument(
        "--survival-stop-usd",
        type=float,
        default=DEFAULT_SURVIVAL_STOP_USD,
        help="30-tick survival boundary in USD.",
    )
    record.add_argument(
        "--required-csv-start",
        default=DEFAULT_REQUIRED_CSV_START,
        help="Minimum required CSV start date (ISO). Record is rejected if CSV starts later.",
    )
    record.add_argument(
        "--footprint-available-from",
        default=DEFAULT_FOOTPRINT_AVAILABLE_FROM,
        help="Date from which TV tick archive provides footprint data. Trades on/after this date form the footprint-cohort diagnostic metric.",
    )
    record.add_argument(
        "--notes", default="", help="Optional operator notes for this trial."
    )
    record.set_defaults(func=command_record)

    leaderboard = subparsers.add_parser(
        "leaderboard", help="Show the best RECORDED trials by objective score."
    )
    leaderboard.add_argument(
        "--top", type=int, default=10, help="How many trials to display."
    )
    leaderboard.add_argument(
        "--include-failed",
        action="store_true",
        help="Append a FAILED trial summary line: count by failure_reason. "
        "Requires migration 010 for Postgres backend.",
    )
    leaderboard.set_defaults(func=command_leaderboard)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
