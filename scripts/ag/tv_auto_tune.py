#!/usr/bin/env python3
"""
tv_auto_tune.py — CDP automation layer for the Warbird v7 strategy tuner.

Replaces the manual "set knobs -> export CSV -> record" loop with full automation:
each trial applies inputs via Chrome DevTools Protocol, waits for recalculation,
reads reportData().trades() directly, scores, and stores -- no CSV file needed.

Requires:
  - TradingView Desktop running with CDP enabled (--remote-debugging-port=9222)
  - Warbird v7 Strategy loaded on the active chart
  - Deep Backtesting configured from 2020-01-01 in Strategy Tester -> Properties
  - pip install requests websockets (psycopg2 already required by tune_strategy_params)

Usage:
  # Run a full suggestion batch
  python scripts/ag/tv_auto_tune.py run --batch-dir artifacts/tuning/suggestions/<ts>/

  # Run a single trial
  python scripts/ag/tv_auto_tune.py run --trial-file artifacts/tuning/suggestions/<ts>/trial_001.json

  # JSONL storage fallback
  python scripts/ag/tv_auto_tune.py run --batch-dir ... --storage jsonl
"""
from __future__ import annotations

import argparse
import asyncio
import json
import math
import sys
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import requests
import websockets

# Re-use scoring and storage from the existing tuner -- zero duplication.
sys.path.insert(0, str(Path(__file__).parent))
from tune_strategy_params import (
    DEFAULT_DB_DSN,
    DEFAULT_FOOTPRINT_AVAILABLE_FROM,
    DEFAULT_INITIAL_CAPITAL,
    DEFAULT_LEDGER_PATH,
    DEFAULT_REQUIRED_CSV_START,
    DEFAULT_SURVIVAL_STOP_USD,
    append_trial_jsonl,
    connect_db,
    load_json,
    params_signature,
    score_trial,
    summarize_side,
    upsert_recorded_trial,
    utc_now,
    validate_csv_window,
)

# -- CDP config ---------------------------------------------------------------
CDP_HOST = "localhost"
CDP_PORT = 9222

# Entity ID of Warbird v7 Strategy on the active chart.
# Re-run chart_get_state (or inspect TV) if the chart is reloaded and this changes.
STRATEGY_ENTITY_ID = "kGnTgb"

# -- Input ID map -------------------------------------------------------------
# Display name (as shown in TV settings) -> Pine input ID (in_N).
# Derived from getInputsInfo() on the strategy study. Covers all 28 user inputs.
# Strategy execution inputs (in_28+: pyramiding, commission, etc.) are locked in
# strategy() and must NOT be set -- TV rejects or ignores them.
INPUT_NAME_TO_ID: dict[str, str] = {
    "Auto-tune ZigZag by Timeframe":                    "in_0",
    "ZigZag Deviation (manual)":                        "in_1",
    "ZigZag Depth (manual)":                            "in_2",
    "Confluence Tolerance (%)":                         "in_3",
    "ZigZag Threshold Floor (%)":                       "in_4",
    "Min Fib Range (ATR)":                              "in_5",
    "Acceptance Retest Window (bars)":                  "in_6",
    "Rejection = wick into zone then close back out":   "in_7",
    "One-shot event markers/alerts":                    "in_8",
    "Exhaustion ATR Multiplier":                        "in_9",
    "Gate Shorts In Bull Trend":                        "in_10",
    "Short Gate ADX Floor":                             "in_11",
    "Fallback Stop Family":                             "in_12",
    "Tier 1 Hold Stop ATR":                             "in_13",
    "Footprint Ticks Per Row":                          "in_14",
    "Footprint VA %":                                   "in_15",
    "Footprint Imbalance %":                            "in_16",
    "Exhaustion Z Length":                              "in_17",
    "Exhaustion Z Threshold":                           "in_18",
    "Extension ATR Tolerance":                          "in_19",
    "Zero-Print Volume Ratio":                          "in_20",
    "Extreme Rows To Inspect":                          "in_21",
    "Tier 1 Hold Bars":                                 "in_22",
    "Target Line Lookback Bars":                        "in_23",
    "Extend Levels Right":                              "in_24",
    "Anchor Span = Active Fib Window":                  "in_25",
    "Enable Debug Logs":                                "in_26",
    "Show Footprint Audit Table":                       "in_27",
}

# -- CDP connection -----------------------------------------------------------

def find_tv_ws_url() -> str:
    """Find the WebSocket debugger URL for the active TradingView tab."""
    try:
        resp = requests.get(f"http://{CDP_HOST}:{CDP_PORT}/json", timeout=5)
        resp.raise_for_status()
    except Exception as exc:
        raise RuntimeError(
            f"Cannot reach CDP at {CDP_HOST}:{CDP_PORT}. "
            "Ensure TradingView Desktop is running with --remote-debugging-port=9222."
        ) from exc
    for target in resp.json():
        if "tradingview.com" in target.get("url", ""):
            return target["webSocketDebuggerUrl"]
    raise RuntimeError(
        f"No TradingView tab found at {CDP_HOST}:{CDP_PORT}. "
        "Open TradingView Desktop and load the MES1! 15m chart."
    )


async def cdp_run(ws, expression: str, call_id: int = 1) -> Any:
    """Execute a JS expression via CDP Runtime.evaluate and return the value.

    Complex objects must be JSON.stringify'd in the expression -- CDP's
    returnByValue only serializes primitives and plain objects natively.
    When the result is a JSON string, it is automatically parsed back.
    """
    msg = {
        "id": call_id,
        "method": "Runtime.evaluate",
        "params": {
            "expression": expression,
            "returnByValue": True,
            "awaitPromise": False,
        },
    }
    await ws.send(json.dumps(msg))
    resp = json.loads(await ws.recv())
    exc_detail = resp.get("result", {}).get("exceptionDetails")
    if exc_detail:
        raise RuntimeError(f"JS exception: {exc_detail.get('text', exc_detail)}")
    result = resp.get("result", {}).get("result", {})
    if result.get("type") == "string":
        try:
            return json.loads(result["value"])
        except json.JSONDecodeError:
            return result["value"]
    return result.get("value")


# -- Study input control ------------------------------------------------------

def build_input_values(search_params: dict, locked_params: dict) -> list[dict]:
    """Build [{id, value}] list for setInputValues().

    Applies locked params first, then search params (search wins on overlap).
    Forces debug outputs off -- no log noise during tuning runs.
    """
    overrides: dict[str, Any] = {}
    for name, val in locked_params.items():
        input_id = INPUT_NAME_TO_ID.get(name)
        if input_id:
            overrides[input_id] = val
    for name, val in search_params.items():
        input_id = INPUT_NAME_TO_ID.get(name)
        if input_id:
            overrides[input_id] = val
    overrides["in_26"] = False   # Enable Debug Logs -- force off
    overrides["in_27"] = False   # Show Footprint Audit Table -- force off
    return [{"id": k, "value": v} for k, v in sorted(overrides.items())]


async def apply_inputs(ws, entity_id: str, input_values: list[dict], call_id: int) -> None:
    vals_json = json.dumps(input_values)
    expr = f"""
(() => {{
    const chart = window.TradingViewApi.activeChart();
    const study = chart.getStudyById('{entity_id}');
    if (!study) return JSON.stringify({{err: 'study not found: {entity_id}'}});
    study.setInputValues({vals_json});
    return JSON.stringify({{ok: true}});
}})()
"""
    result = await cdp_run(ws, expr, call_id)
    if isinstance(result, dict) and result.get("err"):
        raise RuntimeError(f"setInputValues failed: {result['err']}")


async def wait_for_recalc(ws, entity_id: str, timeout_sec: int, call_id: int) -> None:
    """Poll isLoading() until the strategy finishes recalculating."""
    expr = f"""
(() => {{
    const chart = window.TradingViewApi.activeChart();
    const study = chart.getStudyById('{entity_id}');
    if (!study) return null;
    return study.isLoading();
}})()
"""
    # Give TV a moment to register the input change before polling.
    await asyncio.sleep(1.5)
    deadline = asyncio.get_event_loop().time() + timeout_sec
    while asyncio.get_event_loop().time() < deadline:
        loading = await cdp_run(ws, expr, call_id)
        if loading is None:
            raise RuntimeError(f"Study {entity_id} disappeared during recalc wait")
        if not loading:
            return
        await asyncio.sleep(0.75)
    raise TimeoutError(
        f"Strategy did not finish recalculating within {timeout_sec}s. "
        "Try increasing --recalc-timeout or check that Deep Backtesting is enabled."
    )


# -- Trade data extraction ----------------------------------------------------

# Two fallback paths to reach reportData():
#   Path 1 -- chart.chartModel().dataSources() (public API, preferred)
#   Path 2 -- scan window globals for dataSources() (fallback for older TV builds)
_GET_TRADES_JS = """
(() => {
    let stratSrc = null;

    try {
        const chart = window.TradingViewApi.activeChart();
        const model = chart.chartModel();
        if (model && typeof model.dataSources === 'function') {
            stratSrc = model.dataSources().find(
                s => s.reportData && typeof s.reportData === 'function'
            );
        }
    } catch(e) {}

    if (!stratSrc) {
        for (const k of Object.keys(window)) {
            try {
                const v = window[k];
                if (v && typeof v === 'object' && typeof v.dataSources === 'function') {
                    const found = v.dataSources().find(
                        s => s.reportData && typeof s.reportData === 'function'
                    );
                    if (found) { stratSrc = found; break; }
                }
            } catch(e) {}
        }
    }

    if (!stratSrc) return JSON.stringify({err: 'no strategy source with reportData'});

    const rd = stratSrc.reportData();
    if (!rd) return JSON.stringify({err: 'reportData() returned null'});
    const trades = rd.trades();
    if (!trades || !trades.length) return JSON.stringify({err: 'no trades', count: 0});

    return JSON.stringify({
        count: trades.length,
        trades: trades.map((t, idx) => ({
            trade_num: idx + 1,
            // e.c is the entry signal name: "Long", "Short", etc.
            side: (t.e && t.e.c && t.e.c.toLowerCase().includes('short')) ? 'short' : 'long',
            entry_ts: t.e ? t.e.tm : null,
            exit_ts:  t.x ? t.x.tm : null,
            net_pnl:              t.tp ? t.tp.v : 0,
            cumulative_pnl:       t.cp ? t.cp.v : 0,
            // dd.v = max adverse excursion magnitude in USD (positive number).
            // Negated in calculate_metrics_from_tv to match signed CSV convention.
            adverse_excursion_mag: t.dd ? t.dd.v : 0,
            favorable_excursion:   t.rn ? t.rn.v : 0
        }))
    });
})()
"""


async def get_trades(ws, call_id: int) -> list[dict]:
    result = await cdp_run(ws, _GET_TRADES_JS, call_id)
    if isinstance(result, dict) and result.get("err"):
        raise RuntimeError(f"get_trades: {result['err']}")
    return result["trades"]


# -- Metrics computation ------------------------------------------------------

def calculate_metrics_from_tv(
    tv_trades: list[dict],
    initial_capital: float,
    survival_stop_usd: float,
    footprint_available_from: str,
) -> dict[str, Any]:
    """Compute metrics from TV reportData().trades() -- same output shape as
    calculate_trade_metrics() in tune_strategy_params.py.

    TV dd.v (adverse_excursion_mag) is a positive magnitude (e.g., 117.25 USD).
    survival_stop_usd is a negative threshold (e.g., -37.50 = 30 ticks x $1.25).
    A trade survives if -adverse_excursion_mag > survival_stop_usd,
    i.e., the max adverse move was less than abs(survival_stop_usd).
    """
    fp_from_date = date.fromisoformat(footprint_available_from)
    closed: list[dict] = []
    exit_curve: list[dict] = []

    for t in tv_trades:
        if t.get("exit_ts") is None:
            continue  # skip open trades
        exit_dt  = datetime.fromtimestamp(t["exit_ts"] / 1000, tz=UTC)
        entry_dt = (
            datetime.fromtimestamp(t["entry_ts"] / 1000, tz=UTC)
            if t.get("entry_ts") else exit_dt
        )
        closed.append({
            "trade_num":        t["trade_num"],
            "side":             t["side"],
            "entry_time":       entry_dt,
            "exit_time":        exit_dt,
            "net_pnl":          t["net_pnl"],
            "cumulative_pnl":   t["cumulative_pnl"],
            # Negate: TV gives positive magnitude; survival check uses signed convention.
            "adverse_excursion": -t["adverse_excursion_mag"],
        })
        exit_curve.append({"time": exit_dt, "cumulative_pnl": t["cumulative_pnl"]})

    closed.sort(key=lambda r: r["exit_time"])
    exit_curve.sort(key=lambda r: r["time"])

    total = len(closed)
    if total == 0:
        raise ValueError("No closed trades found in TV reportData")

    gross_profit  = sum(r["net_pnl"] for r in closed if r["net_pnl"] > 0)
    gross_loss    = abs(sum(r["net_pnl"] for r in closed if r["net_pnl"] < 0))
    wins          = sum(1 for r in closed if r["net_pnl"] > 0)
    losses        = total - wins
    net_pnl       = round(sum(r["net_pnl"] for r in closed), 2)
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else math.inf

    peak = max_drawdown = 0.0
    for pt in exit_curve:
        eq = pt["cumulative_pnl"]
        peak = max(peak, eq)
        max_drawdown = max(max_drawdown, peak - eq)

    long_rows  = [r for r in closed if r["side"] == "long"]
    short_rows = [r for r in closed if r["side"] == "short"]

    survivors     = sum(1 for r in closed if r["adverse_excursion"] > survival_stop_usd)
    survival_rate = round(survivors / total * 100.0, 2)

    by_year: dict[str, float] = {}
    for r in closed:
        yr = str(r["exit_time"].year)
        by_year[yr] = round(by_year.get(yr, 0.0) + r["net_pnl"], 2)

    fp_trades = [r for r in closed if r["exit_time"].date() >= fp_from_date]
    fp_long   = [r for r in fp_trades if r["side"] == "long"]
    fp_short  = [r for r in fp_trades if r["side"] == "short"]
    fp_net    = sum(r["net_pnl"] for r in fp_trades)
    fp_gp     = sum(r["net_pnl"] for r in fp_trades if r["net_pnl"] > 0)
    fp_gl     = abs(sum(r["net_pnl"] for r in fp_trades if r["net_pnl"] < 0))
    fp_pf     = fp_gp / fp_gl if fp_gl > 0 else math.inf

    return {
        "total_trades":          total,
        "wins":                  wins,
        "losses":                losses,
        "percent_profitable":    round(wins / total * 100.0, 2),
        "net_pnl":               net_pnl,
        "gross_profit":          round(gross_profit, 2),
        "gross_loss":            round(gross_loss, 2),
        "profit_factor":         None if math.isinf(profit_factor) else round(profit_factor, 3),
        "avg_trade":             round(net_pnl / total, 2),
        "avg_win":               round(gross_profit / wins, 2) if wins else 0.0,
        "avg_loss":              round(gross_loss / losses, 2) if losses else 0.0,
        "max_drawdown":          round(max_drawdown, 2),
        "max_drawdown_pct":      round(max_drawdown / initial_capital * 100.0, 2),
        "return_on_initial_pct": round(net_pnl / initial_capital * 100.0, 2),
        "survival_30_tick_pct":  survival_rate,
        "long":                  summarize_side(long_rows),
        "short":                 summarize_side(short_rows),
        "by_year":               by_year,
        "footprint_cohort": {
            "from_date":     footprint_available_from,
            "trades":        len(fp_trades),
            "net_pnl":       round(fp_net, 2),
            "profit_factor": None if math.isinf(fp_pf) else round(fp_pf, 3),
            "long":          summarize_side(fp_long),
            "short":         summarize_side(fp_short),
        },
    }


def validate_tv_window(tv_trades: list[dict], required_start: str) -> dict[str, Any]:
    """Extract window metadata from TV trades and validate against required floor."""
    entry_tms = [t["entry_ts"] for t in tv_trades if t.get("entry_ts")]
    exit_tms  = [t["exit_ts"]  for t in tv_trades if t.get("exit_ts")]
    if not entry_tms:
        raise ValueError("No trade entry timestamps in TV data")
    earliest_ms = min(entry_tms)
    latest_ms   = max(exit_tms) if exit_tms else max(entry_tms)
    meta = {
        "start_date": datetime.fromtimestamp(earliest_ms / 1000, tz=UTC).date().isoformat(),
        "end_date":   datetime.fromtimestamp(latest_ms   / 1000, tz=UTC).date().isoformat(),
        "row_count":  len(tv_trades),
    }
    validate_csv_window(meta, required_start)
    return meta


def make_tv_trial_record(
    config: dict,
    tv_trades: list[dict],
    space: dict,
    initial_capital: float,
    survival_stop_usd: float,
    notes: str,
    required_csv_start: str,
    footprint_available_from: str,
) -> dict[str, Any]:
    csv_meta      = validate_tv_window(tv_trades, required_csv_start)
    metrics       = calculate_metrics_from_tv(tv_trades, initial_capital, survival_stop_usd, footprint_available_from)
    scoring       = score_trial(metrics, space["objective"])
    search_params = config["search_parameters"]
    locked_params = config["locked_parameters"]
    runtime       = config.get("runtime_context", space.get("runtime_context", {}))

    sig_payload = {
        "search":         search_params,
        "locked":         locked_params,
        "csv_meta":       csv_meta,
        "commission":     runtime.get("commission_per_contract_usd"),
        "slippage_ticks": runtime.get("slippage_ticks"),
    }

    return {
        "trial_id":          config["trial_id"],
        "recorded_at":       utc_now(),
        "profile":           space["profile_name"],
        "evaluation_mode":   "CSV_FULL",
        "params_signature":  params_signature(sig_payload),
        "source_csv":        "tv_auto_tune:cdp",
        "search_parameters": search_params,
        "locked_parameters": locked_params,
        "runtime_context":   {**runtime, "csv_meta": csv_meta},
        "metrics":           metrics,
        "objective":         scoring,
        "notes":             notes,
    }


# -- Automation loop ----------------------------------------------------------

async def run_trial(ws, config: dict, space: dict, args: argparse.Namespace, cid_base: int) -> dict:
    cid = cid_base
    input_values = build_input_values(config["search_parameters"], config["locked_parameters"])
    print(f"  -> applying {len(input_values)} inputs ... ", end="", flush=True)
    await apply_inputs(ws, STRATEGY_ENTITY_ID, input_values, cid); cid += 1
    print("recalc ... ", end="", flush=True)
    await wait_for_recalc(ws, STRATEGY_ENTITY_ID, args.recalc_timeout, cid); cid += 1
    print("reading ... ", end="", flush=True)
    tv_trades = await get_trades(ws, cid)
    print(f"{len(tv_trades)} trades.", flush=True)
    return make_tv_trial_record(
        config=config,
        tv_trades=tv_trades,
        space=space,
        initial_capital=args.initial_capital,
        survival_stop_usd=args.survival_stop_usd,
        notes=args.notes or "tv_auto_tune CDP",
        required_csv_start=args.required_csv_start,
        footprint_available_from=args.footprint_available_from,
    )


async def command_run(args: argparse.Namespace) -> int:
    space = load_json(Path(args.space))

    if args.trial_file:
        configs = [load_json(Path(args.trial_file))]
    else:
        batch_dir = Path(args.batch_dir)
        if not batch_dir.exists():
            print(f"ERROR: batch dir not found: {batch_dir}")
            return 1
        configs = sorted(
            [load_json(p) for p in batch_dir.glob("trial_*.json")],
            key=lambda c: c.get("trial_id", ""),
        )

    if not configs:
        print("No trial configs found.")
        return 1

    print(f"Loaded {len(configs)} trial(s).")
    ws_url = find_tv_ws_url()
    print(f"CDP: {ws_url[:70]}...")

    conn = connect_db(args.db_dsn) if args.storage == "postgres" else None
    success = failed = 0

    async with websockets.connect(ws_url, max_size=64 * 1024 * 1024) as ws:
        for i, config in enumerate(configs, 1):
            trial_id = config.get("trial_id", f"trial_{i:03d}")
            print(f"\n[{i}/{len(configs)}] {trial_id}")
            try:
                record = await run_trial(ws, config, space, args, cid_base=i * 100)
                m  = record["metrics"]
                o  = record["objective"]
                fp = m["footprint_cohort"]
                print(
                    f"  score={o['objective_score']:.4f}  "
                    f"net={m['net_pnl']:+.0f}  pf={m['profit_factor']}  "
                    f"dd={m['max_drawdown_pct']:.1f}%  "
                    f"surv={m['survival_30_tick_pct']:.1f}%  "
                    f"trades={m['total_trades']}  "
                    f"fp_pf={fp['profit_factor']}"
                )
                if conn:
                    upsert_recorded_trial(conn, record)
                else:
                    append_trial_jsonl(Path(args.ledger), record)
                success += 1
            except Exception as exc:
                print(f"  FAILED: {exc}")
                failed += 1
                if args.stop_on_error:
                    print("Stopping batch (--stop-on-error).")
                    break
            if i < len(configs):
                await asyncio.sleep(args.delay)

    if conn:
        conn.close()

    print(f"\n{'─' * 50}")
    print(f"Done: {success} succeeded, {failed} failed.")
    return 0 if failed == 0 else 1


# -- CLI ----------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--space",
        default=str(Path(__file__).with_name("strategy_tuning_space.json")),
        help="Search-space JSON path.",
    )
    parser.add_argument(
        "--storage",
        choices=["postgres", "jsonl"],
        default="postgres",
        help="Persistence backend (default: postgres).",
    )
    parser.add_argument("--db-dsn", default=DEFAULT_DB_DSN)
    parser.add_argument("--ledger", default=str(DEFAULT_LEDGER_PATH))

    sub = parser.add_subparsers(dest="command", required=True)
    run_p = sub.add_parser("run", help="Run trial(s) via CDP automation.")

    src = run_p.add_mutually_exclusive_group(required=True)
    src.add_argument("--batch-dir",   help="Directory of trial_*.json files.")
    src.add_argument("--trial-file",  help="Single trial JSON file.")

    run_p.add_argument("--initial-capital",           type=float, default=DEFAULT_INITIAL_CAPITAL)
    run_p.add_argument("--survival-stop-usd",         type=float, default=DEFAULT_SURVIVAL_STOP_USD)
    run_p.add_argument("--required-csv-start",        default=DEFAULT_REQUIRED_CSV_START)
    run_p.add_argument("--footprint-available-from",  default=DEFAULT_FOOTPRINT_AVAILABLE_FROM)
    run_p.add_argument(
        "--recalc-timeout", type=int, default=90,
        help="Seconds to wait for strategy recalculation per trial (default: 90).",
    )
    run_p.add_argument(
        "--delay", type=float, default=3.0,
        help="Seconds between trials (default: 3.0).",
    )
    run_p.add_argument("--notes",         default="", help="Operator notes stored on every trial.")
    run_p.add_argument(
        "--stop-on-error", action="store_true",
        help="Halt the batch on the first trial failure.",
    )
    run_p.set_defaults(func=lambda a: asyncio.run(command_run(a)))

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
