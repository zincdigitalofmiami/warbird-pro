#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parents[1]

if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from tune_strategy_params import (  # noqa: E402
    DEFAULT_DB_DSN,
    DEFAULT_LEDGER_PATH,
    append_trial_jsonl,
    connect_db,
    load_json,
    upsert_failed_trial,
    upsert_recorded_trial,
)
from tv_auto_tune import (  # noqa: E402
    build_input_values,
    classify_failure_reason,
    make_get_trades_js,
    make_tv_trial_record,
    record_failed_trial,
    validate_trial_params,
)


class BridgeClient:
    def __init__(self, repo_root: Path):
        self._proc = subprocess.Popen(
            ["node", str(repo_root / "scripts" / "ag" / "tv_bridge_worker.mjs")],
            cwd=repo_root,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
        self._seq = 0

    def close(self) -> None:
        try:
            self.send({"cmd": "close"})
        except Exception:
            pass
        try:
            self._proc.terminate()
        except Exception:
            pass

    def send(self, payload: dict[str, Any]) -> dict[str, Any]:
        if not self._proc.stdin or not self._proc.stdout:
            raise RuntimeError("bridge worker pipes are unavailable")

        self._seq += 1
        msg = {"id": self._seq, **payload}
        self._proc.stdin.write(json.dumps(msg) + "\n")
        self._proc.stdin.flush()
        line = self._proc.stdout.readline()
        if not line:
            stderr = ""
            if self._proc.stderr:
                stderr = self._proc.stderr.read()
            raise RuntimeError(f"bridge worker exited unexpectedly: {stderr.strip()}")
        resp = json.loads(line)
        if not resp.get("ok"):
            raise RuntimeError(str(resp.get("error", "unknown bridge error")))
        return resp

    def health(self) -> dict[str, Any]:
        return self.send({"cmd": "health"})

    def eval(self, expr: str, *, await_promise: bool = False) -> Any:
        resp = self.send({"cmd": "eval", "expr": expr, "opts": {"awaitPromise": await_promise}})
        return resp.get("value")


def maybe_parse_json(value: Any) -> Any:
    if isinstance(value, str):
        stripped = value.strip()
        if stripped.startswith("{") or stripped.startswith("["):
            try:
                return json.loads(stripped)
            except json.JSONDecodeError:
                return value
    return value


def discover_strategy_and_schema(bridge: BridgeClient) -> tuple[str, dict[str, dict[str, Any]]]:
    js = r"""
(() => {
  try {
    const chart = window.TradingViewApi.activeChart();
    if (!chart) return { err: "activeChart unavailable" };
    const studies = chart.getAllStudies().map(s => {
      try {
        const rawName = (typeof s.name === "function") ? s.name() : (s.name || "");
        const rawId = (typeof s.id === "function") ? s.id() : s.id;
        const m = s.metaInfo ? s.metaInfo() : null;
        return {
          id: rawId,
          name: rawName,
          description: m ? (m.description || "") : "",
          shortDescription: m ? (m.shortDescription || "") : "",
          isStrategy: !!(m && m.strategy),
        };
      } catch (e) {
        return { id: null, name: "", description: "", shortDescription: "", isStrategy: false };
      }
    });

    const strategy = studies.find(s => /Warbird Pro Optuna Backtest/i.test(
      [s.name, s.description, s.shortDescription].join(" ")
    ));
    if (!strategy) {
      return { err: "strategy not found", studies };
    }

    const study = chart.getStudyById(strategy.id);
    if (!study) return { err: "strategy id not resolvable", strategy };

    const inputs = study.getInputsInfo ? study.getInputsInfo() : [];
    return { entity_id: strategy.id, strategy, inputs };
  } catch (e) {
    return { err: String(e) };
  }
})()
"""
    result = maybe_parse_json(bridge.eval(js))
    if isinstance(result, dict) and result.get("err"):
        raise RuntimeError(f"preflight strategy discovery failed: {result['err']}")
    if not isinstance(result, dict) or not result.get("entity_id"):
        raise RuntimeError("preflight strategy discovery failed: malformed response")

    schema: dict[str, dict[str, Any]] = {}
    for inp in result.get("inputs", []):
        name = inp.get("name") or inp.get("title") or inp.get("displayName")
        if name and inp.get("id"):
            schema[name] = inp
    return str(result["entity_id"]), schema


def ensure_backtesting_panel_visible(bridge: BridgeClient) -> None:
    js = r"""
(() => {
  const out = { attempted: [] };
  try {
    const bwb = window.TradingView && window.TradingView.bottomWidgetBar;
    if (!bwb) return { err: "bottomWidgetBar not available" };
    if (typeof bwb.showWidget === "function") { try { bwb.showWidget("backtesting"); out.attempted.push("showWidget"); } catch (e) { out.showWidgetErr = String(e); } }
    if (typeof bwb.activateWidget === "function") { try { bwb.activateWidget("backtesting"); out.attempted.push("activateWidget"); } catch (e) { out.activateWidgetErr = String(e); } }
    if (typeof bwb.open === "function") { try { bwb.open("backtesting"); out.attempted.push("open"); } catch (e) { out.openErr = String(e); } }
    if (typeof bwb.show === "function") { try { bwb.show("backtesting"); out.attempted.push("show"); } catch (e) { out.showErr = String(e); } }
    return out;
  } catch (e) {
    return { err: String(e) };
  }
})()
"""
    result = maybe_parse_json(bridge.eval(js))
    if isinstance(result, dict) and result.get("err"):
        raise RuntimeError(f"unable to open backtesting panel: {result['err']}")


def apply_inputs(bridge: BridgeClient, entity_id: str, input_values: list[dict[str, Any]]) -> None:
    js = f"""
(() => {{
  try {{
    const chart = window.TradingViewApi.activeChart();
    const study = chart.getStudyById('{entity_id}');
    if (!study) return {{ err: 'study not found: {entity_id}' }};
    study.setInputValues({json.dumps(input_values)});
    return {{ ok: true }};
  }} catch (e) {{
    return {{ err: String(e) }};
  }}
}})()
"""
    result = maybe_parse_json(bridge.eval(js))
    if isinstance(result, dict) and result.get("err"):
        raise RuntimeError(f"setInputValues failed: {result['err']}")


def wait_for_recalc(bridge: BridgeClient, entity_id: str, timeout_sec: int, enter_loading_timeout: float = 5.0) -> None:
    js = f"""
(() => {{
  const chart = window.TradingViewApi.activeChart();
  const study = chart ? chart.getStudyById('{entity_id}') : null;
  if (!study) return null;
  return study.isLoading();
}})()
"""

    deadline_enter = time.time() + enter_loading_timeout
    entered_loading = False
    while time.time() < deadline_enter:
        state = maybe_parse_json(bridge.eval(js))
        if state is None:
            raise RuntimeError("failed_no_recalc: strategy study disappeared during loading gate")
        if state is True:
            entered_loading = True
            break
        time.sleep(0.2)

    if not entered_loading:
        raise RuntimeError("failed_no_recalc: strategy did not enter loading state after setInputValues")

    deadline_done = time.time() + timeout_sec
    while time.time() < deadline_done:
        state = maybe_parse_json(bridge.eval(js))
        if state is None:
            raise RuntimeError("failed_no_recalc: strategy study disappeared during recalc")
        if state is False:
            return
        time.sleep(0.75)

    raise RuntimeError(f"failed_no_recalc: strategy did not finish recalculation within {timeout_sec}s")


def refresh_update_report_if_present(bridge: BridgeClient) -> None:
    click_js = r"""
(() => {
  const btn = Array.from(document.querySelectorAll('button,[role="button"]')).find(
    el => (el.innerText || el.textContent || '').trim() === 'Update report'
  );
  if (!btn) return { clicked: false };
  btn.click();
  return { clicked: true };
})()
"""
    state = maybe_parse_json(bridge.eval(click_js))
    if not isinstance(state, dict) or not state.get("clicked"):
        return

    present_js = r"""
(() => ({
  present: !!Array.from(document.querySelectorAll('button,[role="button"]')).find(
    el => (el.innerText || el.textContent || '').trim() === 'Update report'
  )
}))()
"""
    for _ in range(80):
        now = maybe_parse_json(bridge.eval(present_js))
        if not isinstance(now, dict) or not now.get("present"):
            return
        time.sleep(0.25)


def get_trades(bridge: BridgeClient, entity_id: str) -> list[dict[str, Any]]:
    payload = maybe_parse_json(bridge.eval(make_get_trades_js(entity_id)))
    if isinstance(payload, dict) and payload.get("err"):
        raise RuntimeError(f"get_trades: {payload['err']}")
    trades = payload.get("trades") if isinstance(payload, dict) else None
    if not isinstance(trades, list) or not trades:
        raise RuntimeError("get_trades: no trades returned")
    return trades


def iter_trial_files(batch_dir: Path) -> list[Path]:
    files = sorted(batch_dir.glob("trial_*.json"))
    if not files:
        raise RuntimeError(f"No trial_*.json files found in {batch_dir}")
    return files


def build_failed_row(config: dict[str, Any], reason: str, message: str) -> dict[str, Any]:
    return {
        "trial_id": config.get("trial_id", ""),
        "profile": config.get("profile", ""),
        "failure_reason": reason,
        "params_signature": config.get("params_signature", ""),
        "search_parameters": config.get("search_parameters", {}),
        "locked_parameters": config.get("locked_parameters", {}),
        "runtime_context": config.get("runtime_context", {}),
        "error_message": message,
    }


def run(args: argparse.Namespace) -> int:
    space = load_json(args.space)
    trial_files = iter_trial_files(args.batch_dir)

    bridge = BridgeClient(REPO_ROOT)
    conn = None
    processed = 0
    recorded = 0
    failed = 0

    try:
        health = bridge.health()
        target = health.get("target", {})
        print(f"[bridge] connected target={target.get('title')} url={target.get('url')}")

        ensure_backtesting_panel_visible(bridge)
        entity_id, schema = discover_strategy_and_schema(bridge)
        print(f"[preflight] strategy entity_id={entity_id} input_count={len(schema)}")

        if args.storage == "postgres":
            conn = connect_db(args.db_dsn)
            print(f"[storage] postgres dsn={args.db_dsn}")
        else:
            print(f"[storage] jsonl ledger={args.ledger}")

        selected = trial_files[: args.max_trials] if args.max_trials else trial_files
        print(f"[run] batch_dir={args.batch_dir} trials={len(selected)} profile={space.get('profile_name')}")

        for trial_path in selected:
            processed += 1
            config = json.loads(trial_path.read_text())
            trial_id = config.get("trial_id", trial_path.stem)
            print(f"[trial {processed}/{len(selected)}] {trial_id}")

            try:
                errors = validate_trial_params(config.get("search_parameters", {}), schema)
                if errors:
                    raise RuntimeError("; ".join(errors))

                input_values = build_input_values(
                    config.get("search_parameters", {}),
                    config.get("locked_parameters", {}),
                    schema,
                )

                apply_inputs(bridge, entity_id, input_values)
                wait_for_recalc(
                    bridge,
                    entity_id,
                    timeout_sec=args.recalc_timeout,
                    enter_loading_timeout=args.enter_loading_timeout,
                )
                refresh_update_report_if_present(bridge)
                trades = get_trades(bridge, entity_id)

                trial_record = make_tv_trial_record(
                    config=config,
                    tv_trades=trades,
                    space=space,
                    initial_capital=args.initial_capital,
                    survival_stop_usd=args.survival_stop_usd,
                    notes=args.notes,
                    required_csv_start=args.required_csv_start,
                    footprint_available_from=args.footprint_available_from,
                )

                if args.storage == "postgres":
                    assert conn is not None
                    upsert_recorded_trial(conn, trial_record)
                else:
                    append_trial_jsonl(args.ledger, trial_record)

                recorded += 1
                score = trial_record["objective"]["objective_score"]
                tcount = trial_record["metrics"]["total_trades"]
                print(f"  recorded score={score:.4f} trades={tcount}")

            except Exception as exc:
                failed += 1
                reason = classify_failure_reason(exc)
                msg = str(exc)
                print(f"  failed reason={reason} error={msg}")
                record_failed_trial(
                    args.ledger,
                    trial_id=trial_id,
                    failure_reason=reason,
                    config=config,
                    message=msg,
                )
                if args.storage == "postgres" and conn is not None:
                    try:
                        upsert_failed_trial(conn, build_failed_row(config, reason, msg))
                    except Exception as db_exc:
                        print(f"  warning: failed to upsert FAILED row: {db_exc}")

        print(
            json.dumps(
                {
                    "processed": processed,
                    "recorded": recorded,
                    "failed": failed,
                    "profile": space.get("profile_name"),
                    "space": str(args.space),
                    "batch_dir": str(args.batch_dir),
                },
                indent=2,
            )
        )
        return 0 if recorded > 0 else 1

    finally:
        if conn is not None:
            conn.close()
        bridge.close()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run a phase batch via TradingView bridge (MCP connection.js path) and record authoritative TV_MCP_STRICT trials."
    )
    parser.add_argument("--space", type=Path, required=True)
    parser.add_argument("--batch-dir", type=Path, required=True)
    parser.add_argument("--storage", choices=["postgres", "jsonl"], default="postgres")
    parser.add_argument("--db-dsn", default=DEFAULT_DB_DSN)
    parser.add_argument("--ledger", type=Path, default=DEFAULT_LEDGER_PATH)
    parser.add_argument("--notes", default="phase batch via tv bridge")
    parser.add_argument("--max-trials", type=int, default=0)
    parser.add_argument("--recalc-timeout", type=int, default=90)
    parser.add_argument("--enter-loading-timeout", type=float, default=5.0)
    parser.add_argument("--initial-capital", type=float, default=50000.0)
    parser.add_argument("--survival-stop-usd", type=float, default=-37.5)
    parser.add_argument("--required-csv-start", default="2020-01-01")
    parser.add_argument("--footprint-available-from", default="2024-01-01")
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(run(parse_args()))
