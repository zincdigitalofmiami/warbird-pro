#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import json
import math
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Sequence

import psycopg2
import websockets

from tv_auto_tune import (
    apply_inputs,
    discover_study_entity,
    fetch_input_schema,
    find_tv_chart_tab_for_context,
    focus_strategy_report_metrics_tab,
    get_trades,
    refresh_strategy_report,
    verify_inputs_applied,
    wait_for_recalc,
)


DEFAULT_DSN = os.environ.get("WARBIRD_PG_DSN", "host=127.0.0.1 port=5432 dbname=warbird")
DEFAULT_SYMBOL = "CME_MINI:MES1!"
DEFAULT_TIMEFRAME = "15"
DEFAULT_WINDOW_START = "2020-01-01"
DEFAULT_WINDOW_END = "2024-01-01"
DEFAULT_OOS_START = "2024-01-01"
DEFAULT_STRATEGY_DESC = "Self-Aware Trend System [WillyAlgoTrader]"
DEFAULT_STRATEGY_SHORT = "WBPS"

REQUIRED_INPUT_NAMES = (
    "Preset",
    "ATR Length",
    "Base Band Width (xATR)",
    "Source",
    "SL Buffer (xATR)",
    "Backtest Start",
    "Backtest End",
)
ATR_METHOD_INPUT_CANDIDATES = (
    "ATR Method",
    "ATR Calc Method",
    "ATR Smoothing",
    "ATR Type",
)


@dataclass(frozen=True)
class FlipConfig:
    flip_cfg_id: int
    atr_period: int
    atr_mult: float
    atr_method: str
    source_id: str
    sl_atr_mult: float


@dataclass(frozen=True)
class TrialMetrics:
    n_signals: int
    win_rate: float | None
    profit_factor: float | None
    profit_factor_gate: float


@dataclass(frozen=True)
class BatchResult:
    processed: int
    passed: int
    failed: int
    errored: int
    pass_ids: list[int]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Slice 2b prescreen runner: execute all st_flip_configs via TradingView CDP "
            "and upsert pass/fail rows into st_prescreen_ledger."
        )
    )
    parser.add_argument("--dsn", default=DEFAULT_DSN, help="Local PG17 DSN for warbird.")
    parser.add_argument("--run-id", default="", help="Existing run_id to append/resume. Default: auto-generated.")
    parser.add_argument(
        "--notes",
        default="",
        help="Optional st_run_config.notes content. Default auto note if run is newly created.",
    )
    parser.add_argument("--window-start", default=DEFAULT_WINDOW_START, help="In-sample window start (UTC date or ISO ts).")
    parser.add_argument("--window-end", default=DEFAULT_WINDOW_END, help="In-sample window end (exclusive, UTC date or ISO ts).")
    parser.add_argument("--oos-start", default=DEFAULT_OOS_START, help="st_run_config.oos_start (UTC date or ISO ts).")
    parser.add_argument("--symbol", default=DEFAULT_SYMBOL, help="TradingView symbol in runtime context.")
    parser.add_argument("--timeframe", default=DEFAULT_TIMEFRAME, help="TradingView timeframe in runtime context.")
    parser.add_argument(
        "--strategy-description",
        default=DEFAULT_STRATEGY_DESC,
        help="Substring used to discover the strategy entity in TradingView.",
    )
    parser.add_argument(
        "--strategy-short-title",
        default=DEFAULT_STRATEGY_SHORT,
        help="Short title used to discover the strategy entity in TradingView.",
    )
    parser.add_argument(
        "--profit-factor-floor",
        type=float,
        default=1.0,
        help="Pass gate: profit_factor >= this value (default: 1.0).",
    )
    parser.add_argument(
        "--min-signals",
        type=int,
        default=100,
        help="Pass gate: n_signals >= this value (default: 100).",
    )
    parser.add_argument(
        "--recalc-timeout",
        type=int,
        default=120,
        help="Seconds to wait for TradingView recalculation per config (default: 120).",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=2.0,
        help="Seconds between configs (default: 2.0).",
    )
    parser.add_argument(
        "--flip-cfg-id",
        type=int,
        action="append",
        default=[],
        help="Optional specific flip_cfg_id to run (repeatable).",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Optional max number of configs to execute after filtering.",
    )
    parser.add_argument(
        "--strict-atr-method",
        action="store_true",
        help=(
            "Require that a Pine ATR-method input exists and is mappable to st_flip_configs. "
            "Without this flag, atr_method becomes metadata-only if the input is missing."
        ),
    )
    parser.add_argument(
        "--resume",
        dest="resume",
        action="store_true",
        default=True,
        help="Skip flip_cfg_id rows already present in st_prescreen_ledger for this run_id (default: on).",
    )
    parser.add_argument(
        "--no-resume",
        dest="resume",
        action="store_false",
        help="Re-run all selected configs even if ledger rows already exist for this run_id.",
    )
    parser.add_argument(
        "--stop-on-error",
        action="store_true",
        help="Stop batch execution on first trial execution error.",
    )
    parser.add_argument(
        "--summary-path",
        default="",
        help=(
            "Optional summary JSON path. Default: artifacts/st_prescreen/<run_id>/summary.json"
        ),
    )
    return parser.parse_args()


def parse_utc(value: str) -> datetime:
    txt = value.strip()
    if not txt:
        raise ValueError("empty datetime string")
    if "T" not in txt:
        txt = f"{txt}T00:00:00+00:00"
    txt = txt.replace("Z", "+00:00")
    dt = datetime.fromisoformat(txt)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def to_unix_ms(dt: datetime) -> int:
    return int(dt.timestamp() * 1000)


def maybe_float(v: float | None) -> float | None:
    if v is None:
        return None
    return float(v)


def auto_run_id() -> str:
    return datetime.now(UTC).strftime("stpre_%Y%m%dT%H%M%SZ")


def resolve_display_name(schema: dict[str, dict], candidates: Sequence[str]) -> str | None:
    for name in candidates:
        if name in schema:
            return name
    return None


def _option_value(option: Any) -> Any:
    if isinstance(option, dict):
        for key in ("value", "id", "name", "title"):
            if key in option:
                return option[key]
    return option


def _option_labels(option: Any) -> list[str]:
    labels: list[str] = []
    if isinstance(option, dict):
        for key in ("title", "name", "value", "id"):
            if key in option and option[key] is not None:
                labels.append(str(option[key]).strip().lower())
    else:
        labels.append(str(option).strip().lower())
    return labels


def resolve_option(meta: dict, wanted: Any) -> Any:
    options = meta.get("options") or meta.get("values")
    if not options:
        return wanted
    target = str(wanted).strip().lower()
    for option in options:
        labels = _option_labels(option)
        if target in labels:
            return _option_value(option)
    return wanted


def resolve_atr_method_value(meta: dict, atr_method: str) -> Any:
    wanted_map = {
        "atr": ("atr", "rma", "atr (rma)", "true range rma", "ta.atr"),
        "sma_tr": ("sma tr", "sma(tr)", "sma true range", "sma"),
    }
    candidates = wanted_map.get(atr_method, (atr_method,))
    options = meta.get("options") or meta.get("values") or []
    for option in options:
        labels = _option_labels(option)
        for candidate in candidates:
            if candidate in labels:
                return _option_value(option)
    # Fallback to the original string and let verify-after-set catch mismatches.
    return atr_method


def compute_metrics(tv_trades: list[dict[str, Any]]) -> TrialMetrics:
    closed = [t for t in tv_trades if t.get("exit_ts") is not None]
    n_signals = len(closed)
    if n_signals == 0:
        return TrialMetrics(n_signals=0, win_rate=0.0, profit_factor=0.0, profit_factor_gate=0.0)

    net_pnls = [float(t.get("net_pnl") or 0.0) for t in closed]
    wins = [p for p in net_pnls if p > 0.0]
    losses = [p for p in net_pnls if p < 0.0]
    win_rate = len(wins) / n_signals

    wins_sum = sum(wins)
    losses_sum_abs = abs(sum(losses))
    if losses_sum_abs > 0.0:
        pf = wins_sum / losses_sum_abs
        return TrialMetrics(
            n_signals=n_signals,
            win_rate=win_rate,
            profit_factor=pf,
            profit_factor_gate=pf,
        )

    if wins_sum > 0.0:
        # TV can produce no-loss windows; keep DB value finite/null-safe while allowing pass-gate.
        return TrialMetrics(
            n_signals=n_signals,
            win_rate=win_rate,
            profit_factor=None,
            profit_factor_gate=math.inf,
        )

    return TrialMetrics(
        n_signals=n_signals,
        win_rate=win_rate,
        profit_factor=0.0,
        profit_factor_gate=0.0,
    )


def evaluate_pass_fail(metrics: TrialMetrics, pf_floor: float, min_signals: int) -> tuple[bool, str | None]:
    reasons: list[str] = []
    if metrics.n_signals < min_signals:
        reasons.append(f"n_signals<{min_signals}")
    if metrics.profit_factor_gate < pf_floor:
        reasons.append(f"profit_factor<{pf_floor:.2f}")
    return (len(reasons) == 0, "; ".join(reasons) if reasons else None)


def ensure_run_row(conn: psycopg2.extensions.connection, run_id: str, oos_start: datetime, notes: str) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO st_run_config (run_id, oos_start, notes)
            VALUES (%s, %s, %s)
            ON CONFLICT (run_id) DO NOTHING
            """,
            (run_id, oos_start, notes),
        )
    conn.commit()


def fetch_flip_configs(conn: psycopg2.extensions.connection, filter_ids: Sequence[int]) -> list[FlipConfig]:
    sql = """
        SELECT
            flip_cfg_id,
            atr_period,
            atr_mult::double precision,
            atr_method,
            source_id,
            sl_atr_mult::double precision
        FROM st_flip_configs
    """
    params: tuple[Any, ...] = ()
    if filter_ids:
        sql += " WHERE flip_cfg_id = ANY(%s)"
        params = (list(filter_ids),)
    sql += " ORDER BY flip_cfg_id"

    with conn.cursor() as cur:
        cur.execute(sql, params)
        rows = cur.fetchall()
    return [
        FlipConfig(
            flip_cfg_id=int(r[0]),
            atr_period=int(r[1]),
            atr_mult=float(r[2]),
            atr_method=str(r[3]),
            source_id=str(r[4]),
            sl_atr_mult=float(r[5]),
        )
        for r in rows
    ]


def fetch_existing_ids(conn: psycopg2.extensions.connection, run_id: str) -> set[int]:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT flip_cfg_id FROM st_prescreen_ledger WHERE run_id = %s",
            (run_id,),
        )
        return {int(r[0]) for r in cur.fetchall()}


def upsert_ledger_row(
    conn: psycopg2.extensions.connection,
    *,
    run_id: str,
    cfg: FlipConfig,
    window_start: datetime,
    window_end: datetime,
    metrics: TrialMetrics,
    passed: bool,
    fail_reason: str | None,
) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO st_prescreen_ledger (
                run_id,
                flip_cfg_id,
                window_start,
                window_end,
                n_signals,
                win_rate,
                profit_factor,
                avg_r,
                max_drawdown_r,
                pass,
                fail_reason
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
            )
            ON CONFLICT (flip_cfg_id, run_id) DO UPDATE
            SET
                window_start   = EXCLUDED.window_start,
                window_end     = EXCLUDED.window_end,
                n_signals      = EXCLUDED.n_signals,
                win_rate       = EXCLUDED.win_rate,
                profit_factor  = EXCLUDED.profit_factor,
                avg_r          = EXCLUDED.avg_r,
                max_drawdown_r = EXCLUDED.max_drawdown_r,
                pass           = EXCLUDED.pass,
                fail_reason    = EXCLUDED.fail_reason,
                run_ts         = now()
            """,
            (
                run_id,
                cfg.flip_cfg_id,
                window_start,
                window_end,
                metrics.n_signals,
                maybe_float(metrics.win_rate),
                maybe_float(metrics.profit_factor),
                None,  # avg_r is not available from TV reportData() without custom R-series exports
                None,  # max_drawdown_r is not available from TV reportData() without custom R-series exports
                passed,
                fail_reason,
            ),
        )
    conn.commit()


async def preflight(
    ws,
    args: argparse.Namespace,
) -> tuple[str, dict[str, dict], str | None]:
    entity_id = await discover_study_entity(
        ws,
        call_id=10,
        description_substring=args.strategy_description,
        short_title=args.strategy_short_title,
        require_strategy=True,
    )
    schema = await fetch_input_schema(ws, entity_id, call_id=11)

    missing = [name for name in REQUIRED_INPUT_NAMES if name not in schema]
    if missing:
        raise RuntimeError(
            "Missing required strategy inputs in live schema: "
            + ", ".join(missing)
        )

    atr_method_name = resolve_display_name(schema, ATR_METHOD_INPUT_CANDIDATES)
    if atr_method_name is None and args.strict_atr_method:
        raise RuntimeError(
            "strict_atr_method enabled but no ATR-method input exists on the loaded strategy."
        )

    return entity_id, schema, atr_method_name


def build_input_values(
    schema: dict[str, dict],
    cfg: FlipConfig,
    *,
    window_start_ms: int,
    window_end_ms: int,
    atr_method_input_name: str | None,
) -> list[dict[str, Any]]:
    entries: dict[str, Any] = {}

    entries[schema["Preset"]["id"]] = resolve_option(schema["Preset"], "Custom")
    entries[schema["ATR Length"]["id"]] = cfg.atr_period
    entries[schema["Base Band Width (xATR)"]["id"]] = cfg.atr_mult
    entries[schema["Source"]["id"]] = resolve_option(schema["Source"], cfg.source_id)
    entries[schema["SL Buffer (xATR)"]["id"]] = cfg.sl_atr_mult
    entries[schema["Backtest Start"]["id"]] = window_start_ms
    entries[schema["Backtest End"]["id"]] = window_end_ms

    if atr_method_input_name is not None:
        meta = schema[atr_method_input_name]
        entries[meta["id"]] = resolve_atr_method_value(meta, cfg.atr_method)

    return [{"id": k, "value": v} for k, v in sorted(entries.items())]


async def execute_single_config(
    ws,
    *,
    entity_id: str,
    input_values: list[dict[str, Any]],
    recalc_timeout: int,
    call_id_base: int,
) -> TrialMetrics:
    cid = call_id_base

    await focus_strategy_report_metrics_tab(ws, cid)
    cid += 1

    await apply_inputs(ws, entity_id, input_values, cid)
    cid += 1
    await refresh_strategy_report(ws, cid)
    cid += 2

    mismatches = await verify_inputs_applied(ws, entity_id, input_values, cid)
    cid += 1
    if mismatches:
        raise RuntimeError(
            "input_mismatch: getInputValues() mismatch after setInputValues - "
            + "; ".join(mismatches)
        )

    loaded = await wait_for_recalc(ws, entity_id, recalc_timeout, cid)
    cid += 1
    if not loaded:
        raise RuntimeError(
            "no_recalc: strategy never entered loading state after input set"
        )

    await refresh_strategy_report(ws, cid)
    cid += 2
    await focus_strategy_report_metrics_tab(ws, cid)
    cid += 1

    tv_trades = await get_trades(ws, entity_id, cid)
    return compute_metrics(tv_trades)


def write_summary(
    *,
    out_path: Path,
    run_id: str,
    window_start: datetime,
    window_end: datetime,
    oos_start: datetime,
    total_selected: int,
    result: BatchResult,
    atr_method_input_name: str | None,
) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "run_id": run_id,
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "window_start": window_start.isoformat(),
        "window_end_exclusive": window_end.isoformat(),
        "oos_start": oos_start.isoformat(),
        "total_selected_configs": total_selected,
        "processed_configs": result.processed,
        "pass_count": result.passed,
        "fail_count": result.failed,
        "error_count": result.errored,
        "pass_ids": result.pass_ids,
        "atr_method_input_name": atr_method_input_name,
        "atr_method_applied": atr_method_input_name is not None,
    }
    out_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


async def run_batch(
    args: argparse.Namespace,
    *,
    conn: psycopg2.extensions.connection,
    run_id: str,
    cfgs: list[FlipConfig],
    window_start: datetime,
    window_end: datetime,
) -> tuple[BatchResult, str | None]:
    runtime_context = {"symbol": args.symbol, "timeframe": args.timeframe}
    ws_url = await find_tv_chart_tab_for_context(runtime_context)
    print(f"[cdp] {ws_url[:100]}...")

    window_start_ms = to_unix_ms(window_start)
    window_end_ms = to_unix_ms(window_end)

    processed = passed = failed = errored = 0
    pass_ids: list[int] = []
    atr_method_input_name: str | None = None

    async with websockets.connect(ws_url, max_size=64 * 1024 * 1024) as ws:
        entity_id, schema, atr_method_input_name = await preflight(ws, args)
        print(f"[preflight] strategy_entity_id={entity_id}")
        if atr_method_input_name is None:
            print(
                "[preflight] ATR method input not found on strategy; "
                "atr_method will be treated as metadata-only for Slice 2b."
            )
        else:
            print(f"[preflight] ATR method input mapped to '{atr_method_input_name}'")

        total = len(cfgs)
        for idx, cfg in enumerate(cfgs, start=1):
            print(
                f"[{idx}/{total}] flip_cfg_id={cfg.flip_cfg_id} "
                f"(atr_period={cfg.atr_period}, atr_mult={cfg.atr_mult:.2f}, "
                f"atr_method={cfg.atr_method}, source_id={cfg.source_id}, sl_atr_mult={cfg.sl_atr_mult:.2f})"
            )
            try:
                input_values = build_input_values(
                    schema,
                    cfg,
                    window_start_ms=window_start_ms,
                    window_end_ms=window_end_ms,
                    atr_method_input_name=atr_method_input_name,
                )
                metrics = await execute_single_config(
                    ws,
                    entity_id=entity_id,
                    input_values=input_values,
                    recalc_timeout=args.recalc_timeout,
                    call_id_base=1000 + idx * 10,
                )
                row_pass, fail_reason = evaluate_pass_fail(
                    metrics, args.profit_factor_floor, args.min_signals
                )
                upsert_ledger_row(
                    conn,
                    run_id=run_id,
                    cfg=cfg,
                    window_start=window_start,
                    window_end=window_end,
                    metrics=metrics,
                    passed=row_pass,
                    fail_reason=fail_reason,
                )
                processed += 1
                if row_pass:
                    passed += 1
                    pass_ids.append(cfg.flip_cfg_id)
                else:
                    failed += 1
                pf_print = (
                    "INF"
                    if math.isinf(metrics.profit_factor_gate)
                    else f"{metrics.profit_factor_gate:.4f}"
                )
                print(
                    f"  -> n_signals={metrics.n_signals} pf={pf_print} "
                    f"win_rate={metrics.win_rate:.4f} pass={row_pass}"
                    + (f" fail_reason={fail_reason}" if fail_reason else "")
                )
            except Exception as exc:
                errored += 1
                fail_reason = f"execution_error: {str(exc)[:400]}"
                fallback = TrialMetrics(
                    n_signals=0,
                    win_rate=0.0,
                    profit_factor=0.0,
                    profit_factor_gate=0.0,
                )
                upsert_ledger_row(
                    conn,
                    run_id=run_id,
                    cfg=cfg,
                    window_start=window_start,
                    window_end=window_end,
                    metrics=fallback,
                    passed=False,
                    fail_reason=fail_reason,
                )
                print(f"  -> ERROR {fail_reason}")
                if args.stop_on_error:
                    print("  -> stopping batch (--stop-on-error)")
                    break

            if idx < total and args.delay > 0:
                await asyncio.sleep(args.delay)

    return (
        BatchResult(
            processed=processed,
            passed=passed,
            failed=failed,
            errored=errored,
            pass_ids=pass_ids,
        ),
        atr_method_input_name,
    )


def main() -> int:
    args = parse_args()

    window_start = parse_utc(args.window_start)
    window_end = parse_utc(args.window_end)
    oos_start = parse_utc(args.oos_start)
    if window_end <= window_start:
        raise SystemExit("--window-end must be later than --window-start")

    run_id = args.run_id.strip() or auto_run_id()
    notes = args.notes.strip() or (
        f"Slice 2b prescreen window [{window_start.date()} .. {window_end.date()})"
    )

    with psycopg2.connect(args.dsn) as conn:
        ensure_run_row(conn, run_id, oos_start, notes)
        flip_cfgs = fetch_flip_configs(conn, args.flip_cfg_id)
        if not flip_cfgs:
            raise SystemExit("No st_flip_configs rows found for selection.")

        if not args.flip_cfg_id and args.limit <= 0 and len(flip_cfgs) != 480:
            raise SystemExit(
                f"Expected 480 st_flip_configs rows for full Slice 2b run, found {len(flip_cfgs)}."
            )

        if args.resume:
            existing = fetch_existing_ids(conn, run_id)
            if existing:
                before = len(flip_cfgs)
                flip_cfgs = [cfg for cfg in flip_cfgs if cfg.flip_cfg_id not in existing]
                print(
                    f"[resume] skipping {before - len(flip_cfgs)} existing ledger rows for run_id={run_id}"
                )

        if args.limit > 0:
            flip_cfgs = flip_cfgs[: args.limit]

        if not flip_cfgs:
            print("No configs left to process after filters/resume.")
            return 0

        print(
            f"[start] run_id={run_id} configs={len(flip_cfgs)} "
            f"window=[{window_start.isoformat()} .. {window_end.isoformat()}) "
            f"symbol={args.symbol} tf={args.timeframe}"
        )
        result, atr_method_input_name = asyncio.run(
            run_batch(
                args,
                conn=conn,
                run_id=run_id,
                cfgs=flip_cfgs,
                window_start=window_start,
                window_end=window_end,
            )
        )

    summary_path = Path(args.summary_path) if args.summary_path else Path(
        "artifacts/st_prescreen"
    ) / run_id / "summary.json"
    write_summary(
        out_path=summary_path,
        run_id=run_id,
        window_start=window_start,
        window_end=window_end,
        oos_start=oos_start,
        total_selected=len(flip_cfgs),
        result=result,
        atr_method_input_name=atr_method_input_name,
    )

    print(
        "[done] "
        f"processed={result.processed} pass={result.passed} fail={result.failed} "
        f"errors={result.errored} summary={summary_path}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
