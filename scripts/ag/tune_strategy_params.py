#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import random
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
DEFAULT_DB_DSN = os.environ.get("WARBIRD_PG_DSN", "host=127.0.0.1 port=5432 dbname=warbird")
# TV tick archive boundary for MES1! 15m — bars before this date rarely have footprint data.
# Operator can override per session via --footprint-available-from on the `record` command.
DEFAULT_FOOTPRINT_AVAILABLE_FROM = "2024-01-01"
# Minimum CSV start date: 2020-01-01 per v5 training-data floor.
DEFAULT_REQUIRED_CSV_START = "2020-01-01"


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
        offsets = [offset for offset in (-2, -1, 1, 2) if 0 <= index + offset < len(domain.values)]
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
    return [t for t in load_trials_jsonl(ledger_path) if t.get("evaluation_mode") == "CSV_FULL"]


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
    """Fetch only CSV_FULL trials — authoritative evaluation mode."""
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
          AND evaluation_mode = 'CSV_FULL'
        ORDER BY created_at ASC, trial_id ASC
    """
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(query, (profile,))
        rows = cur.fetchall()
    return [dict(row) for row in rows]


def persist_suggestion_batch(conn, space: dict[str, Any], batch_id: str, count: int, seed: int | None, suggestions: list[dict[str, Any]], space_path: Path) -> None:
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


def fetch_db_leaderboard(conn, profile: str, top: int) -> list[dict[str, Any]]:
    """Fetch top CSV_FULL trials ranked by objective score."""
    query = """
        SELECT
          trial_id,
          profile_name AS profile,
          evaluation_mode,
          search_parameters,
          metrics,
          objective
        FROM warbird_strategy_tuning_trials
        WHERE profile_name = %s
          AND status = 'RECORDED'
          AND evaluation_mode = 'CSV_FULL'
          AND objective_score IS NOT NULL
        ORDER BY objective_score DESC, recorded_at DESC
        LIMIT %s
    """
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(query, (profile, top))
        rows = cur.fetchall()
    return [dict(row) for row in rows]


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
    fp_from_date = date.fromisoformat(footprint_available_from)
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
    exit_curve: list[dict[str, Any]] = []
    for trade_id, pair in sorted(by_trade.items()):
        entry = pair.get("entry")
        exit_row = pair.get("exit")
        if not entry and not exit_row:
            continue
        anchor = entry or exit_row
        side = "long" if "long" in anchor["type"].lower() else "short"
        net_pnl = (exit_row or entry)["net_pnl"]
        cumulative_pnl = (exit_row or entry)["cumulative_pnl"]
        exit_time = (exit_row or entry)["time"]
        adverse_excursion = (entry or exit_row)["adverse_excursion"]
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
        exit_curve.append({"time": exit_time, "cumulative_pnl": cumulative_pnl})

    closed_trades.sort(key=lambda row: row["exit_time"])
    exit_curve.sort(key=lambda row: row["time"])

    gross_profit = sum(row["net_pnl"] for row in closed_trades if row["net_pnl"] > 0)
    gross_loss = abs(sum(row["net_pnl"] for row in closed_trades if row["net_pnl"] < 0))
    wins = sum(1 for row in closed_trades if row["net_pnl"] > 0)
    losses = sum(1 for row in closed_trades if row["net_pnl"] < 0)
    total_trades = len(closed_trades)
    net_pnl = round(sum(row["net_pnl"] for row in closed_trades), 2)
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else math.inf
    percent_profitable = round((wins / total_trades * 100.0), 2) if total_trades else 0.0
    avg_trade = round(net_pnl / total_trades, 2) if total_trades else 0.0
    avg_win = round(gross_profit / wins, 2) if wins else 0.0
    avg_loss = round(gross_loss / losses, 2) if losses else 0.0

    peak = 0.0
    max_drawdown = 0.0
    for point in exit_curve:
        equity = point["cumulative_pnl"]
        peak = max(peak, equity)
        max_drawdown = max(max_drawdown, peak - equity)

    long_rows = [row for row in closed_trades if row["side"] == "long"]
    short_rows = [row for row in closed_trades if row["side"] == "short"]
    survivors = sum(1 for row in closed_trades if row["adverse_excursion"] > survival_stop_usd)
    survival_rate = round((survivors / total_trades * 100.0), 2) if total_trades else 0.0

    by_year: dict[str, float] = {}
    for row in closed_trades:
        year = str(row["exit_time"].year)
        by_year[year] = round(by_year.get(year, 0.0) + row["net_pnl"], 2)

    # ── Footprint cohort (diagnostic — TV tick archive boundary) ──
    fp_trades = [t for t in closed_trades if t["exit_time"].date() >= fp_from_date]
    fp_long = [t for t in fp_trades if t["side"] == "long"]
    fp_short = [t for t in fp_trades if t["side"] == "short"]
    fp_net = sum(t["net_pnl"] for t in fp_trades)
    fp_gp = sum(t["net_pnl"] for t in fp_trades if t["net_pnl"] > 0)
    fp_gl = abs(sum(t["net_pnl"] for t in fp_trades if t["net_pnl"] < 0))
    fp_pf = fp_gp / fp_gl if fp_gl > 0 else math.inf
    footprint_cohort = {
        "from_date": footprint_available_from,
        "trades": len(fp_trades),
        "net_pnl": round(fp_net, 2),
        "profit_factor": None if math.isinf(fp_pf) else round(fp_pf, 3),
        "long": summarize_side(fp_long),
        "short": summarize_side(fp_short),
    }

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
        "footprint_cohort": footprint_cohort,
    }


def score_trial(metrics: dict[str, Any], objective: dict[str, Any]) -> dict[str, float]:
    weights = objective["weights"]
    profit_factor = metrics["profit_factor"] or 0.0
    long_pf = metrics["long"]["profit_factor"] or 0.0
    short_pf = metrics["short"]["profit_factor"] or 0.0
    survival_pct = metrics.get("survival_30_tick_pct")
    components = {
        "net_pnl": metrics["net_pnl"] / 1000.0,
        "profit_factor": profit_factor - 1.0,
        "drawdown": -(metrics["max_drawdown_pct"] / 10.0),
        "survival": 0.0 if survival_pct is None else (survival_pct - 50.0) / 10.0,
        "long_pf": long_pf - 1.0,
        "short_pf": short_pf - 1.0,
    }

    trade_bounds = objective.get("trade_count_bounds", {})
    trade_penalty = 0.0
    trade_count = metrics["total_trades"]
    min_trades = trade_bounds.get("min")
    max_trades = trade_bounds.get("max")
    if min_trades and trade_count < min_trades:
        trade_penalty = (min_trades - trade_count) / float(min_trades)
    elif max_trades and trade_count > max_trades:
        trade_penalty = (trade_count - max_trades) / float(max_trades)
    components["trade_penalty"] = -trade_penalty

    score = 0.0
    for name, weight in weights.items():
        score += components.get(name, 0.0) * weight
    return {
        "objective_score": round(score, 4),
        "components": {name: round(value, 4) for name, value in components.items()},
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

    metrics = calculate_trade_metrics(csv_path, initial_capital, survival_stop_usd, footprint_available_from)
    scoring = score_trial(metrics, space["objective"])
    search_params = config["search_parameters"]
    locked_params = config["locked_parameters"]

    # Full identity: search + locked + csv window + pinned commission/slippage from runtime context
    runtime = config.get("runtime_context", space.get("runtime_context", {}))
    sig_payload = {
        "search": search_params,
        "locked": locked_params,
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
        body.append(
            f"| {rank} | {row['trial_id']} | {row['objective']['objective_score']:.4f} | "
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
    historical_trials must already be filtered to CSV_FULL evaluation_mode.
    """
    domains = build_domains(space)
    locked_params = space["locked_parameters"]

    def suggest_sig(search_params: dict[str, Any]) -> str:
        return params_signature({"locked": locked_params, "search": search_params})

    seen = {suggest_sig(trial["search_parameters"]) for trial in historical_trials}
    ranked_trials = [
        trial
        for trial in historical_trials
        if trial.get("objective") and trial["objective"].get("objective_score") is not None
    ]
    ranked_trials.sort(key=lambda row: row["objective"]["objective_score"], reverse=True)

    suggestions: list[dict[str, Any]] = []

    def accept(params: dict[str, Any], parent_trial_id: str | None, origin: str) -> None:
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
        while len(suggestions) < count:
            accept(sample_random_params(domains, rng), None, "random")
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
    while len(suggestions) < count:
        parent = rng.choice(top_trials)
        params = dict(parent["search_parameters"])
        mutate_count = rng.randint(1, min(3, len(domains)))
        mutate_domains = rng.sample(domains, k=mutate_count)
        for domain in mutate_domains:
            params[domain.name] = neighbor_choice(domain, params[domain.name], rng)
        accept(params, parent["trial_id"], "mutated")
        if len(suggestions) < count:
            accept(sample_random_params(domains, rng), None, "exploratory")
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
            persist_suggestion_batch(conn, space, batch_stamp, args.count, args.seed, suggestions, space_path)

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
    if args.storage == "postgres":
        with connect_db(args.db_dsn) as conn:
            ranked = fetch_db_leaderboard(conn, space["profile_name"], args.top)
    else:
        trials = load_trials_jsonl_csv_full(Path(args.ledger))
        ranked = sorted(
            [t for t in trials if t.get("objective", {}).get("objective_score") is not None],
            key=lambda row: row["objective"]["objective_score"],
            reverse=True,
        )[: args.top]
    if not ranked:
        print("No CSV_FULL trials recorded yet.")
        return 0
    print(render_markdown_table(ranked))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Warbird v7 strategy tuner — pre-AG settings sweep.\n"
            "Three commands: suggest (emit candidate configs), record (ingest a TV trade CSV),\n"
            "leaderboard (rank recorded CSV_FULL trials).\n\n"
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
    parser.add_argument("--space", default=str(DEFAULT_SPACE_PATH), help="Search-space JSON path.")
    parser.add_argument("--storage", choices=["postgres", "jsonl"], default="postgres", help="Persistence backend for suggestions and results.")
    parser.add_argument("--db-dsn", default=DEFAULT_DB_DSN, help="Postgres DSN for the local warbird warehouse.")
    parser.add_argument("--ledger", default=str(DEFAULT_LEDGER_PATH), help="JSONL ledger path when --storage=jsonl.")

    subparsers = parser.add_subparsers(dest="command", required=True)

    suggest = subparsers.add_parser("suggest", help="Generate new trial configs from the search space.")
    suggest.add_argument("--count", type=int, default=10, help="How many trial configs to generate.")
    suggest.add_argument("--seed", type=int, default=42, help="Random seed for deterministic suggestions.")
    suggest.add_argument("--out-dir", default=str(DEFAULT_SUGGESTIONS_DIR), help="Output directory for trial JSON files.")
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
    record.add_argument("--params-file", required=True, help="Trial config JSON generated by `suggest`.")
    record.add_argument("--trades-csv", required=True, help="TradingView strategy trade-list CSV (List of Trades export).")
    record.add_argument("--initial-capital", type=float, default=DEFAULT_INITIAL_CAPITAL, help="Initial capital used by the strategy report.")
    record.add_argument("--survival-stop-usd", type=float, default=DEFAULT_SURVIVAL_STOP_USD, help="30-tick survival boundary in USD.")
    record.add_argument("--required-csv-start", default=DEFAULT_REQUIRED_CSV_START, help="Minimum required CSV start date (ISO). Record is rejected if CSV starts later.")
    record.add_argument("--footprint-available-from", default=DEFAULT_FOOTPRINT_AVAILABLE_FROM, help="Date from which TV tick archive provides footprint data. Trades on/after this date form the footprint-cohort diagnostic metric.")
    record.add_argument("--notes", default="", help="Optional operator notes for this trial.")
    record.set_defaults(func=command_record)

    leaderboard = subparsers.add_parser("leaderboard", help="Show the best CSV_FULL recorded trials.")
    leaderboard.add_argument("--top", type=int, default=10, help="How many trials to display.")
    leaderboard.set_defaults(func=command_leaderboard)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
