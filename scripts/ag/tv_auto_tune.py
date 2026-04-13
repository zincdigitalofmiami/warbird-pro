#!/usr/bin/env python3
"""
tv_auto_tune.py — Hardened CDP automation layer for the Warbird v7 strategy tuner.

Replaces the manual "set knobs -> export CSV -> record" loop with full automation:
each trial applies inputs via Chrome DevTools Protocol, waits for recalculation,
reads reportData().trades() directly, scores, and stores -- no CSV file needed.

Requires:
  - TradingView Desktop running with CDP enabled (--remote-debugging-port=9222)
  - Warbird v7 Strategy loaded on the active chart (CME_MINI:MES1! 15m)
  - Deep Backtesting configured from 2020-01-01 in Strategy Tester -> Properties
  - pip install requests websockets (psycopg2 already required by tune_strategy_params)

Usage:
  # Run preflight checks only (verify chart, entity discovery, input schema, canary)
  python scripts/ag/tv_auto_tune.py preflight

  # Run a full suggestion batch
  python scripts/ag/tv_auto_tune.py run --batch-dir artifacts/tuning/suggestions/<ts>/

  # Run a single trial
  python scripts/ag/tv_auto_tune.py run --trial-file artifacts/tuning/suggestions/<ts>/trial_001.json

  # JSONL storage fallback
  python scripts/ag/tv_auto_tune.py run --batch-dir ... --storage jsonl

HARDENING NOTES (Phase A):
  - Tab selection: enumerates all CDP targets, selects the one whose symbol/timeframe
    matches runtime_context. Fails if zero or >=2 match.
  - Entity discovery: walks chartModel().dataSources() for the strategy by name.
    No more hardcoded STRATEGY_ENTITY_ID.
  - Input schema: fetched live via getInputsInfo() at preflight. Static INPUT_NAME_TO_ID
    map removed. Any param name absent from the live schema is a schema_drift failure.
  - Verify-after-set: after setInputValues, re-reads getInputValues() and diffs field
    by field. Mismatch = invalid_input failure row.
  - Two-phase freshness gate: (1) requires isLoading()→true within 5s of setInputValues
    (loading-state transition), then (2) polls until isLoading()→false. "Never entered
    loading" = no_recalc failure row (inputs were likely no-op'd or silently rejected).
  - Trade extraction: entity-scoped JS using discovered entity_id, not window globals.
  - FAILED rows: written to JSONL ledger regardless of --storage. DB persistence
    of FAILED rows requires migration 010 (Phase C).
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
    filter_signature_locked_params,
    load_json,
    params_signature,
    score_trial,
    summarize_closed_trades,
    upsert_failed_trial,
    upsert_recorded_trial,
    utc_now,
    validate_csv_window,
)

# -- CDP config ---------------------------------------------------------------
CDP_HOST = "localhost"
CDP_PORT = 9222

# STRATEGY_ENTITY_ID and INPUT_NAME_TO_ID have been removed.
# Both are now resolved at runtime during preflight via discover_strategy_entity()
# and fetch_input_schema(). This prevents silent misalignment after Pine input changes
# or chart reloads.

# -- Tab discovery ------------------------------------------------------------


async def find_tv_chart_tab_for_context(runtime_context: dict) -> str:
    """Find the WebSocket URL for a TradingView chart matching runtime_context.

    Enumerates all CDP targets at the configured port, checks symbol and timeframe
    on each TradingView tab by evaluating TradingViewApi.activeChart(), and returns
    the URL of the one matching runtime_context["symbol"] and runtime_context["timeframe"].

    Raises RuntimeError if zero or >=2 tabs match (safety: prevents silent wrong-chart runs).
    """
    target_symbol = str(runtime_context.get("symbol", "")).upper()
    target_tf = str(runtime_context.get("timeframe", ""))

    try:
        resp = requests.get(f"http://{CDP_HOST}:{CDP_PORT}/json", timeout=5)
        resp.raise_for_status()
    except Exception as exc:
        raise RuntimeError(
            f"Cannot reach CDP at {CDP_HOST}:{CDP_PORT}. "
            "Ensure TradingView Desktop is running with --remote-debugging-port=9222."
        ) from exc

    candidates = [
        t
        for t in resp.json()
        if "tradingview.com" in t.get("url", "") and t.get("webSocketDebuggerUrl")
    ]

    if not candidates:
        raise RuntimeError(
            f"No TradingView tabs found at {CDP_HOST}:{CDP_PORT}. "
            "Open TradingView Desktop and load the MES1! 15m chart."
        )

    state_js = """
(() => {
    try {
        const c = window.TradingViewApi.activeChart();
        return JSON.stringify({
            symbol: c.symbol().toUpperCase(),
            timeframe: String(c.resolution())
        });
    } catch(e) {
        return JSON.stringify({err: String(e)});
    }
})()"""

    matched: list[str] = []
    for t in candidates:
        ws_url = t["webSocketDebuggerUrl"]
        try:
            async with websockets.connect(
                ws_url, max_size=2 * 1024 * 1024, open_timeout=5
            ) as ws:
                result = await cdp_run(ws, state_js, call_id=1)
                if isinstance(result, dict) and not result.get("err"):
                    sym_ok = (
                        not target_symbol or result.get("symbol", "") == target_symbol
                    )
                    tf_ok = (
                        not target_tf or str(result.get("timeframe", "")) == target_tf
                    )
                    if sym_ok and tf_ok:
                        matched.append(ws_url)
        except Exception:
            continue  # tab not accessible or not a chart tab — skip

    if not matched:
        raise RuntimeError(
            f"No TradingView chart tab found with symbol={target_symbol} timeframe={target_tf}. "
            "Ensure the correct chart is open and the strategy is loaded."
        )
    if len(matched) > 1:
        raise RuntimeError(
            f"Multiple TradingView chart tabs match symbol={target_symbol} timeframe={target_tf}. "
            "Close duplicate chart tabs and retry."
        )

    return matched[0]


# -- CDP communication --------------------------------------------------------


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
        raise RuntimeError(
            f"compile_error: JS exception: {exc_detail.get('text', exc_detail)}"
        )
    result = resp.get("result", {}).get("result", {})
    if result.get("type") == "string":
        try:
            return json.loads(result["value"])
        except json.JSONDecodeError:
            return result["value"]
    return result.get("value")


# -- Strategy discovery -------------------------------------------------------


async def discover_strategy_entity(ws, call_id: int) -> str:
    """Discover the entity ID of 'Warbird v7 Strategy' from chartModel().dataSources().

    Walks all data sources on the active chart and finds the one whose metaInfo()
    marks it as a strategy with a name containing 'Warbird v7 Strategy'.
    Raises RuntimeError with available strategy names if not found.
    """
    js = """
(() => {
    try {
        const chart = window.TradingViewApi.activeChart();
        const model = chart.chartModel();
        if (!model || typeof model.dataSources !== 'function') {
            return JSON.stringify({err: 'chartModel().dataSources() not available'});
        }
        const sources = model.dataSources();
        const isStrat = (meta) => meta.isTVScriptStrategy === true || meta.is_strategy === true;
        const nameMatch = (meta) => {
            const desc = meta.description || meta.shortDescription || '';
            return desc.includes('Warbird v7 Strategy');
        };
        const strategy = sources.find(s => {
            try {
                const meta = s.metaInfo ? s.metaInfo() : null;
                return meta && isStrat(meta) && nameMatch(meta);
            } catch(e) { return false; }
        });
        if (!strategy) {
            const allStrats = sources
                .filter(s => {
                    try { const m = s.metaInfo ? s.metaInfo() : null; return m && isStrat(m); }
                    catch(e) { return false; }
                })
                .map(s => {
                    try { const m = s.metaInfo(); return {id: s.id(), name: m.description || m.shortDescription}; }
                    catch(e) { return {err: String(e)}; }
                });
            return JSON.stringify({err: 'Warbird v7 Strategy not found', available: allStrats});
        }
        return JSON.stringify({entity_id: strategy.id()});
    } catch(e) {
        return JSON.stringify({err: String(e)});
    }
})()
"""
    result = await cdp_run(ws, js, call_id)
    if isinstance(result, dict) and result.get("err"):
        available = result.get("available", [])
        diag = f". Available strategies on chart: {available}" if available else ""
        raise RuntimeError(f"Strategy entity discovery failed: {result['err']}{diag}")
    return result["entity_id"]


# -- Input schema -------------------------------------------------------------


async def fetch_input_schema(ws, entity_id: str, call_id: int) -> dict[str, dict]:
    """Fetch the live input schema from getInputsInfo().

    Returns: {display_name: {id: str, type: str, defval: ..., ...}}
    Each entry has at minimum 'id' (the in_N runtime ID) and 'name' (display name).
    """
    js = f"""
(() => {{
    try {{
        const chart = window.TradingViewApi.activeChart();
        const study = chart.getStudyById('{entity_id}');
        if (!study) return JSON.stringify({{err: 'study not found: {entity_id}'}});
        const info = study.getInputsInfo();
        return JSON.stringify({{inputs: info}});
    }} catch(e) {{
        return JSON.stringify({{err: String(e)}});
    }}
}})()
"""
    result = await cdp_run(ws, js, call_id)
    if isinstance(result, dict) and result.get("err"):
        raise RuntimeError(f"getInputsInfo failed: {result['err']}")

    schema: dict[str, dict] = {}
    for inp in result.get("inputs", []):
        # TV input objects use 'name' for display name, 'id' for in_N
        name = inp.get("name") or inp.get("title") or inp.get("displayName")
        if name and inp.get("id"):
            schema[name] = inp
    return schema


# -- Input validation ---------------------------------------------------------


def _values_match(expected: Any, actual: Any) -> bool:
    """Loose equality that handles float precision and bool/int coercion."""
    if expected == actual:
        return True
    if isinstance(expected, bool) and isinstance(actual, bool):
        return expected == actual
    if isinstance(expected, (int, float)) and isinstance(actual, (int, float)):
        return abs(float(expected) - float(actual)) < 1e-9
    if isinstance(expected, str) and isinstance(actual, str):
        return expected == actual
    return False


def validate_trial_params(params: dict[str, Any], schema: dict[str, dict]) -> list[str]:
    """Validate trial parameter names and values against the live TV input schema.

    Returns list of error strings (empty = valid).
    Each error is prefixed with its failure_reason: 'schema_drift' or 'invalid_input'.
    """
    errors: list[str] = []
    for name, value in params.items():
        if name not in schema:
            errors.append(f"schema_drift: '{name}' not found in live TV input schema")
            continue
        inp = schema[name]
        inp_type = (inp.get("type") or "").lower()

        # Enum/options validation for string/categorical inputs
        options = inp.get("options") or inp.get("values")
        if options is not None and inp_type in ("text", "string", "source", ""):
            allowed_strs = [str(o) for o in options]
            if str(value) not in allowed_strs:
                errors.append(
                    f"invalid_input: '{name}' value '{value}' not in allowed options {allowed_strs}"
                )

        # Numeric range validation
        if inp_type in ("float", "integer", "int", "resolution", "price"):
            mn = inp.get("min") if inp.get("min") is not None else inp.get("minval")
            mx = inp.get("max") if inp.get("max") is not None else inp.get("maxval")
            try:
                num_val = float(value)
                if mn is not None and num_val < float(mn):
                    errors.append(f"invalid_input: '{name}' value {value} < min {mn}")
                if mx is not None and num_val > float(mx):
                    errors.append(f"invalid_input: '{name}' value {value} > max {mx}")
            except (TypeError, ValueError):
                pass  # non-numeric value will surface as a type mismatch after set

    return errors


# -- Input control ------------------------------------------------------------


def build_input_values(
    search_params: dict, locked_params: dict, schema: dict[str, dict]
) -> list[dict]:
    """Build [{id, value}] list for setInputValues() using runtime-resolved schema.

    Applies locked params first, then search params (search wins on overlap).
    Forces debug outputs off by name lookup in live schema.
    Skips any param not found in schema (schema_drift errors caught at validate step).
    """
    overrides: dict[str, Any] = {}
    for name, val in locked_params.items():
        inp = schema.get(name)
        if inp:
            overrides[inp["id"]] = val
    for name, val in search_params.items():
        inp = schema.get(name)
        if inp:
            overrides[inp["id"]] = val
    # Force debug outputs off -- find by display name in live schema
    for debug_name in ("Enable Debug Logs", "Show Footprint Audit Table"):
        inp = schema.get(debug_name)
        if inp:
            overrides[inp["id"]] = False
    return [{"id": k, "value": v} for k, v in sorted(overrides.items())]


async def apply_inputs(
    ws, entity_id: str, input_values: list[dict], call_id: int
) -> None:
    """Call setInputValues() on the strategy study with the resolved [{id, value}] list."""
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


async def verify_inputs_applied(
    ws, entity_id: str, expected: list[dict], call_id: int
) -> list[str]:
    """Re-read getInputValues() and diff against expected [{id, value}] list.

    Returns list of mismatch descriptions (empty = all applied correctly).
    """
    js = f"""
(() => {{
    try {{
        const chart = window.TradingViewApi.activeChart();
        const study = chart.getStudyById('{entity_id}');
        if (!study) return JSON.stringify({{err: 'study not found'}});
        const vals = study.getInputValues();
        return JSON.stringify({{values: vals}});
    }} catch(e) {{
        return JSON.stringify({{err: String(e)}});
    }}
}})()
"""
    result = await cdp_run(ws, js, call_id)
    if isinstance(result, dict) and result.get("err"):
        raise RuntimeError(f"getInputValues failed: {result['err']}")

    actual_map = {v["id"]: v["value"] for v in result.get("values", [])}
    mismatches: list[str] = []
    for exp in expected:
        inp_id = exp["id"]
        exp_val = exp["value"]
        act_val = actual_map.get(inp_id)
        if not _values_match(exp_val, act_val):
            mismatches.append(f"{inp_id}: expected={exp_val!r} actual={act_val!r}")
    return mismatches


# -- Recalc freshness gate ----------------------------------------------------


async def wait_for_recalc(
    ws,
    entity_id: str,
    timeout_sec: int,
    call_id: int,
    enter_loading_timeout: float = 5.0,
) -> None:
    """Two-phase freshness gate.

    Phase 1: Require at least one isLoading()=true within enter_loading_timeout seconds.
             If the study never enters loading state, inputs were likely silently no-op'd
             (out-of-range value, duplicate of current state, or TV glitch).
             Raises RuntimeError with 'failed_no_recalc' prefix.

    Phase 2: Poll isLoading()=false up to timeout_sec.
             Raises TimeoutError if recalc does not complete.

    NOTE: The loading-state transition can be missed if TV recalcs faster than the first
    poll interval (0.2s). If false-failures appear in the 10-trial batch smoke test,
    the mitigation is to subscribe to the study's change event via CDP before
    setInputValues and require the event to fire instead.
    """
    loading_js = f"""
(() => {{
    const chart = window.TradingViewApi.activeChart();
    const study = chart.getStudyById('{entity_id}');
    if (!study) return null;
    return study.isLoading();
}})()
"""
    # Phase 1: confirm loading state was entered
    deadline_1 = asyncio.get_event_loop().time() + enter_loading_timeout
    entered_loading = False
    while asyncio.get_event_loop().time() < deadline_1:
        await asyncio.sleep(0.2)
        loading = await cdp_run(ws, loading_js, call_id)
        if loading is None:
            raise RuntimeError(f"Study {entity_id} disappeared during recalc wait")
        if loading:
            entered_loading = True
            break

    if not entered_loading:
        raise RuntimeError(
            "failed_no_recalc: strategy never entered loading state after setInputValues. "
            "Inputs may have been silently rejected (out-of-range, type mismatch, or no-op "
            "because submitted values match the current live values). "
            "If this is a deterministic identical-input rerun, this failure is expected — "
            "change at least one parameter value to force a recalc."
        )

    # Phase 2: wait for loading to complete
    deadline_2 = asyncio.get_event_loop().time() + timeout_sec
    while asyncio.get_event_loop().time() < deadline_2:
        await asyncio.sleep(0.75)
        loading = await cdp_run(ws, loading_js, call_id)
        if loading is None:
            raise RuntimeError(f"Study {entity_id} disappeared during recalc wait")
        if not loading:
            return

    raise TimeoutError(
        f"Strategy did not finish recalculating within {timeout_sec}s. "
        "Try increasing --recalc-timeout or check that Deep Backtesting is enabled."
    )


# -- Trade data extraction ----------------------------------------------------


def make_get_trades_js(entity_id: str) -> str:
    """Build entity-scoped JS to extract trades from reportData().trades().

    Targets the specific entity_id discovered at preflight rather than scanning
    window globals for any strategy source. Falls back to window-globals scan
    scoped to the same entity_id if chartModel().dataSources() is unavailable.
    """
    return f"""
(() => {{
    let stratSrc = null;

    try {{
        const chart = window.TradingViewApi.activeChart();
        const model = chart.chartModel();
        if (model && typeof model.dataSources === 'function') {{
            stratSrc = model.dataSources().find(
                s => s.id && typeof s.id === 'function' && s.id() === '{entity_id}'
            );
        }}
    }} catch(e) {{}}

    // Fallback: scan window globals for the specific entity_id
    if (!stratSrc) {{
        for (const k of Object.keys(window)) {{
            try {{
                const v = window[k];
                if (v && typeof v === 'object' && typeof v.dataSources === 'function') {{
                    const found = v.dataSources().find(
                        s => s.id && typeof s.id === 'function' && s.id() === '{entity_id}'
                    );
                    if (found) {{ stratSrc = found; break; }}
                }}
            }} catch(e) {{}}
        }}
    }}

    if (!stratSrc) return JSON.stringify({{err: 'strategy source not found for entity: {entity_id}'}});

    const rd = stratSrc.reportData();
    if (!rd) return JSON.stringify({{err: 'reportData() returned null'}});
    const trades = typeof rd.trades === 'function' ? rd.trades() : rd.trades;
    if (!trades || !trades.length) return JSON.stringify({{err: 'no trades', count: 0}});

    return JSON.stringify({{
        count: trades.length,
        trades: trades.map((t, idx) => ({{
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
        }}))
    }});
}})()
"""


async def get_trades(ws, entity_id: str, call_id: int) -> list[dict]:
    result = await cdp_run(ws, make_get_trades_js(entity_id), call_id)
    if isinstance(result, dict) and result.get("err"):
        raise RuntimeError(f"get_trades: {result['err']}")
    return result["trades"]


# -- Diagnostics --------------------------------------------------------------


async def snapshot_strategy_metrics(
    ws, entity_id: str, call_id: int
) -> dict[str, Any] | None:
    """Snapshot current trade count and net profit for pre/post diagnostic comparison.

    Used to verify that inputs produced a genuine recalc (different results).
    Returns None if snapshot cannot be obtained (non-blocking).
    """
    js = f"""
(() => {{
    try {{
        const chart = window.TradingViewApi.activeChart();
        const model = chart.chartModel();
        if (!model || typeof model.dataSources !== 'function') return null;
        const strat = model.dataSources().find(
            s => s.id && typeof s.id === 'function' && s.id() === '{entity_id}'
        );
        if (!strat) return null;
        const rd = strat.reportData();
        if (!rd) return null;
        const trades = typeof rd.trades === 'function' ? rd.trades() : rd.trades;
        const perf = typeof rd.performance === 'function' ? rd.performance() : rd.performance;
        return JSON.stringify({{
            trade_count: trades ? trades.length : null,
            last_exit_ts: trades && trades.length ? (trades[trades.length - 1].x ? trades[trades.length - 1].x.tm : null) : null,
            net_profit: perf && perf.netProfit !== undefined ? perf.netProfit : null
        }});
    }} catch(e) {{ return null; }}
}})()
"""
    try:
        return await cdp_run(ws, js, call_id)
    except Exception:
        return None


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
    closed: list[dict] = []

    for t in tv_trades:
        if t.get("exit_ts") is None:
            continue  # skip open trades
        exit_dt = datetime.fromtimestamp(t["exit_ts"] / 1000, tz=UTC)
        entry_dt = (
            datetime.fromtimestamp(t["entry_ts"] / 1000, tz=UTC)
            if t.get("entry_ts")
            else exit_dt
        )
        closed.append(
            {
                "trade_num": t["trade_num"],
                "side": t["side"],
                "entry_time": entry_dt,
                "exit_time": exit_dt,
                "net_pnl": t["net_pnl"],
                "cumulative_pnl": t["cumulative_pnl"],
                # Negate: TV gives positive magnitude; survival check uses signed convention.
                "adverse_excursion": -t["adverse_excursion_mag"],
            }
        )
    return summarize_closed_trades(
        closed,
        initial_capital=initial_capital,
        survival_stop_usd=survival_stop_usd,
        footprint_available_from=footprint_available_from,
    )


# -- Trial record building ----------------------------------------------------


def make_tv_trial_record(
    config: dict,
    tv_trades: list[dict],
    space: dict,
    initial_capital: float,
    survival_stop_usd: float,
    notes: str,
    required_csv_start: str = DEFAULT_REQUIRED_CSV_START,
    footprint_available_from: str = DEFAULT_FOOTPRINT_AVAILABLE_FROM,
) -> dict[str, Any]:
    metrics = calculate_metrics_from_tv(
        tv_trades, initial_capital, survival_stop_usd, footprint_available_from
    )

    csv_meta = {
        "source": "tv_auto_tune:cdp",
        "start_date": required_csv_start,
        "end_date": utc_now()[:10],
    }

    validate_csv_window(csv_meta, required_csv_start)

    scoring = score_trial(metrics, space["objective"])

    if scoring.get("insufficient_sample"):
        raise ValueError(
            f"invalid_input: insufficient sample for AG training — "
            f"total={scoring['components'].get('total_trades')}, "
            f"long={scoring['components'].get('long_trades')}, "
            f"short={scoring['components'].get('short_trades')}, "
            f"min_required={scoring['components'].get('min_required')}"
        )

    search_params = config["search_parameters"]
    locked_params = config["locked_parameters"]
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
        "evaluation_mode": "TV_MCP_STRICT",
        "params_signature": params_signature(sig_payload),
        "source_csv": "tv_auto_tune:cdp",
        "search_parameters": search_params,
        "locked_parameters": locked_params,
        "runtime_context": {**runtime, "csv_meta": csv_meta},
        "metrics": metrics,
        "objective": scoring,
        "notes": notes,
    }


# -- FAILED row persistence ---------------------------------------------------


def classify_failure_reason(exc: Exception) -> str:
    """Map exception message to a canonical failure_reason string.

    These align with the CHECK constraint added in migration 010.
    Checks prefixes/substrings in the exception message.
    """
    msg = str(exc)
    for prefix, reason in [
        ("failed_no_recalc", "no_recalc"),
        ("schema_drift", "schema_drift"),
        ("invalid_input", "invalid_input"),
        ("compile_error", "compile_error"),
    ]:
        if prefix in msg:
            return reason
    return "tv_disconnected"


def record_failed_trial(
    ledger_path: Path,
    trial_id: str,
    failure_reason: str,
    config: dict,
    message: str,
) -> None:
    """Write a FAILED trial row to JSONL ledger.

    DB persistence of FAILED rows is gated on migration 010 (Phase C) which adds
    'FAILED' to the status CHECK and the failure_reason column to
    warbird_strategy_tuning_trials. Until that migration is applied, FAILED rows
    are written to JSONL only and do not flow into the Postgres upsert path.
    """
    row = {
        "trial_id": trial_id,
        "status": "FAILED",
        "failure_reason": failure_reason,
        "failed_at": utc_now(),
        "profile": config.get("profile", ""),
        "search_parameters": config.get("search_parameters", {}),
        "locked_parameters": config.get("locked_parameters", {}),
        "error_message": message,
    }
    append_trial_jsonl(ledger_path, row)


# -- Preflight ----------------------------------------------------------------


async def run_preflight_checks(ws, space: dict) -> tuple[str, dict[str, dict]]:
    """Run all preflight checks. Returns (entity_id, schema).

    Steps:
    1. Discover strategy entity ID by name in dataSources().
    2. Fetch live input schema via getInputsInfo().
    3. Cross-check all search_parameters names exist in schema.
    4. Canary round-trip: set 'Target Line Lookback Bars' to a test value,
       verify via getInputValues(), restore.
    5. Snapshot initial strategy-result metrics for diagnostic baseline.

    Raises RuntimeError on any failure.
    """
    cid = 10  # start at 10 to avoid collision with tab-discovery call_id=1

    print("Preflight [1/5]: discovering strategy entity...")
    entity_id = await discover_strategy_entity(ws, cid)
    cid += 1
    print(f"  entity_id: {entity_id}")

    print("Preflight [2/5]: fetching live input schema...")
    schema = await fetch_input_schema(ws, entity_id, cid)
    cid += 1
    print(f"  {len(schema)} input(s) found in live schema.")

    print("Preflight [3/5]: cross-checking search_parameters names...")
    search_params = space.get("search_parameters", {})
    locked_params = space.get("locked_parameters", {})
    missing_search = [n for n in search_params if n not in schema]
    missing_locked = [n for n in locked_params if n not in schema]
    if missing_search:
        raise RuntimeError(
            f"Preflight FAILED: search_parameters not in live schema: {missing_search}\n"
            "Pine inputs may have been renamed or removed. Update strategy_tuning_space.json."
        )
    if missing_locked:
        print(
            f"  WARNING: locked_parameters not in live schema (will be skipped): {missing_locked}"
        )
    print(f"  All {len(search_params)} search params found. OK.")

    print("Preflight [4/5]: canary round-trip...")
    canary_name = "Target Line Lookback Bars"
    if canary_name in schema:
        canary_id = schema[canary_name]["id"]
        # Read current value
        read_js = f"""
(() => {{
    const chart = window.TradingViewApi.activeChart();
    const study = chart.getStudyById('{entity_id}');
    if (!study) return null;
    const vals = study.getInputValues();
    const v = vals.find(x => x.id === '{canary_id}');
    return v ? v.value : null;
}})()
"""
        canary_orig = await cdp_run(ws, read_js, cid)
        cid += 1
        canary_test = 40 if canary_orig != 40 else 45
        canary_inputs = [{"id": canary_id, "value": canary_test}]

        await apply_inputs(ws, entity_id, canary_inputs, cid)
        cid += 1
        await asyncio.sleep(0.4)
        mismatches = await verify_inputs_applied(ws, entity_id, canary_inputs, cid)
        cid += 1

        # Restore before any possible raise
        await apply_inputs(
            ws, entity_id, [{"id": canary_id, "value": canary_orig}], cid
        )
        cid += 1

        if mismatches:
            raise RuntimeError(
                f"Preflight canary round-trip FAILED — getInputValues() mismatch: {mismatches}. "
                "setInputValues may not be applying correctly on this TV build."
            )
        print(f"  Canary: set {canary_test}, verified, restored to {canary_orig}. OK.")
    else:
        print(
            f"  Canary input '{canary_name}' not found in schema — skipping round-trip."
        )

    print("Preflight [5/5]: snapshotting initial strategy metrics...")
    snap = await snapshot_strategy_metrics(ws, entity_id, cid)
    cid += 1
    if snap:
        print(
            f"  trades={snap.get('trade_count')} last_exit={snap.get('last_exit_ts')} net_profit={snap.get('net_profit')}"
        )
    else:
        print("  Snapshot unavailable (non-blocking).")

    print("Preflight: PASSED")
    return entity_id, schema


# -- Automation loop ----------------------------------------------------------


async def run_trial(
    ws,
    entity_id: str,
    schema: dict[str, dict],
    config: dict,
    space: dict,
    args: argparse.Namespace,
    cid_base: int,
) -> dict:
    """Execute one tuning trial with full validation and freshness gating.

    Steps:
    1. Validate params against live schema.
    2. Pre-snapshot metrics (diagnostic).
    3. Build resolved [{id, value}] from names using runtime schema.
    4. Apply inputs + verify-after-set.
    5. Two-phase freshness gate.
    6. Read trades; compute metrics and score.
    """
    cid = cid_base

    search_params = config["search_parameters"]
    locked_params = config["locked_parameters"]

    # 1. Validate params
    errors = validate_trial_params({**locked_params, **search_params}, schema)
    schema_drift_errors = [e for e in errors if e.startswith("schema_drift")]
    invalid_input_errors = [e for e in errors if e.startswith("invalid_input")]
    if schema_drift_errors:
        raise RuntimeError(schema_drift_errors[0])
    if invalid_input_errors:
        raise RuntimeError(invalid_input_errors[0])

    # 2. Pre-snapshot
    pre_snap = await snapshot_strategy_metrics(ws, entity_id, cid)
    cid += 1

    # 3. Build resolved input list
    input_values = build_input_values(search_params, locked_params, schema)
    print(f"  -> applying {len(input_values)} inputs ... ", end="", flush=True)

    # 4a. Apply
    await apply_inputs(ws, entity_id, input_values, cid)
    cid += 1

    # 4b. Verify-after-set
    mismatches = await verify_inputs_applied(ws, entity_id, input_values, cid)
    cid += 1
    if mismatches:
        raise RuntimeError(
            f"invalid_input: getInputValues() mismatch after setInputValues — {mismatches}"
        )

    # 5. Two-phase freshness gate
    print("recalc ... ", end="", flush=True)
    await wait_for_recalc(ws, entity_id, args.recalc_timeout, cid)
    cid += 1

    # 6. Read trades
    print("reading ... ", end="", flush=True)
    tv_trades = await get_trades(ws, entity_id, cid)
    cid += 1
    print(f"{len(tv_trades)} trades.", flush=True)

    # Diagnostic: log if trade count unchanged (may indicate a silent no-op)
    if pre_snap and pre_snap.get("trade_count") == len(tv_trades):
        print(
            f"  NOTE: trade count unchanged ({len(tv_trades)}) vs pre-snapshot. "
            "If params were identical to prior trial this is expected."
        )

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


async def command_preflight_async(args: argparse.Namespace) -> int:
    """Run preflight checks and print results. No trial execution."""
    space = load_json(Path(args.space))
    runtime_context = space.get("runtime_context", {})

    print(
        f"Connecting to TradingView (symbol={runtime_context.get('symbol')} "
        f"tf={runtime_context.get('timeframe')})..."
    )
    ws_url = await find_tv_chart_tab_for_context(runtime_context)
    print(f"CDP: {ws_url[:70]}...")

    async with websockets.connect(ws_url, max_size=64 * 1024 * 1024) as ws:
        entity_id, schema = await run_preflight_checks(ws, space)

    print(f"\nEntity ID:   {entity_id}")
    print(f"Schema size: {len(schema)} inputs")
    print("\nSearch parameter → live input ID mapping:")
    for name in sorted(space.get("search_parameters", {})):
        inp = schema.get(name)
        inp_id = inp["id"] if inp else "NOT FOUND"
        print(f"  {inp_id}  {name}")
    return 0


def command_preflight(args: argparse.Namespace) -> int:
    return asyncio.run(command_preflight_async(args))


async def command_run_async(args: argparse.Namespace) -> int:
    space = load_json(Path(args.space))
    runtime_context = space.get("runtime_context", {})

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
    ws_url = await find_tv_chart_tab_for_context(runtime_context)
    print(f"CDP: {ws_url[:70]}...")

    conn = connect_db(args.db_dsn) if args.storage == "postgres" else None
    success = failed = 0

    async with websockets.connect(ws_url, max_size=64 * 1024 * 1024) as ws:
        # Run preflight once per batch
        print("\nRunning preflight checks...")
        entity_id, schema = await run_preflight_checks(ws, space)
        print()

        for i, config in enumerate(configs, 1):
            trial_id = config.get("trial_id", f"trial_{i:03d}")
            print(f"[{i}/{len(configs)}] {trial_id}")
            try:
                record = await run_trial(
                    ws, entity_id, schema, config, space, args, cid_base=i * 100
                )
                m = record["metrics"]
                o = record["objective"]
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
                reason = classify_failure_reason(exc)
                print(f"  FAILED [{reason}]: {exc}")
                # Always write to JSONL for durability.
                record_failed_trial(
                    Path(args.ledger), trial_id, reason, config, str(exc)
                )
                # Also persist to Postgres if migration 010 has been applied.
                if conn:
                    try:
                        failed_row = {
                            "trial_id": trial_id,
                            "profile": space.get("profile_name", ""),
                            "failure_reason": reason,
                            "params_signature": config.get("params_signature", ""),
                            "search_parameters": config.get("search_parameters", {}),
                            "locked_parameters": config.get("locked_parameters", {}),
                            "runtime_context": config.get("runtime_context", {}),
                            "error_message": str(exc),
                        }
                        upsert_failed_trial(conn, failed_row)
                    except Exception as db_exc:
                        # Likely migration 010 not yet applied — JSONL is the fallback.
                        print(
                            f"  NOTE: DB FAILED write skipped (migration 010 required): {db_exc}"
                        )
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


def command_run(args: argparse.Namespace) -> int:
    return asyncio.run(command_run_async(args))


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

    # -- preflight subcommand --
    preflight_p = sub.add_parser(
        "preflight",
        help="Run preflight checks: tab discovery, entity ID, input schema, canary round-trip.",
    )
    preflight_p.set_defaults(func=command_preflight)

    # -- run subcommand --
    run_p = sub.add_parser("run", help="Run trial(s) via CDP automation.")

    src = run_p.add_mutually_exclusive_group(required=True)
    src.add_argument("--batch-dir", help="Directory of trial_*.json files.")
    src.add_argument("--trial-file", help="Single trial JSON file.")

    run_p.add_argument("--initial-capital", type=float, default=DEFAULT_INITIAL_CAPITAL)
    run_p.add_argument(
        "--survival-stop-usd", type=float, default=DEFAULT_SURVIVAL_STOP_USD
    )
    run_p.add_argument("--required-csv-start", default=DEFAULT_REQUIRED_CSV_START)
    run_p.add_argument(
        "--footprint-available-from", default=DEFAULT_FOOTPRINT_AVAILABLE_FROM
    )
    run_p.add_argument(
        "--recalc-timeout",
        type=int,
        default=90,
        help="Seconds to wait for strategy recalculation per trial (default: 90).",
    )
    run_p.add_argument(
        "--delay",
        type=float,
        default=3.0,
        help="Seconds between trials (default: 3.0).",
    )
    run_p.add_argument(
        "--notes", default="", help="Operator notes stored on every trial."
    )
    run_p.add_argument(
        "--stop-on-error",
        action="store_true",
        help="Halt the batch on the first trial failure.",
    )
    run_p.set_defaults(func=command_run)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
