#!/usr/bin/env python3
"""
CDP Sweep Runner — automates SATS-PS input sweeps via direct Chrome DevTools Protocol.

Approach: monkey-patch study.getInputValues() to always return the saved template,
then call setInputValues() with overrides per trial. No remove/re-add — preserves
the Deep BT data cache and avoids 7+ minute re-fetches per trial.

Requirements:
  - SATS-PS strategy must already be on the chart (entity 7tIwAT or auto-discovered).
  - data/sats_ps_sweep/input_template_stripped.json must exist (built by this script on first run).
  - Pine editor must have SATS-PS loaded (for re-add fallback only).

Usage:
    python scripts/sats/cdp_sweep_runner.py --stage 2 [--wait 120]
    python scripts/sats/cdp_sweep_runner.py --stage 3
    python scripts/sats/cdp_sweep_runner.py --stage 4 --n 250 --seed 42
"""

import argparse
import asyncio
import json
import subprocess
import sys
import time
from pathlib import Path

import requests
import websockets

# ── Config ────────────────────────────────────────────────────────────────────
CDP_HOST   = "localhost"
CDP_PORT   = 9222
REPO_ROOT  = Path(__file__).parent.parent.parent
HARNESS    = REPO_ROOT / "scripts" / "sats" / "sweep_harness.py"
TEMPLATE_PATH        = REPO_ROOT / "data" / "sats_ps_sweep" / "input_template.json"
TEMPLATE_STRIPPED_PATH = REPO_ROOT / "data" / "sats_ps_sweep" / "input_template_stripped.json"
WAIT_SECS  = 120  # seconds to wait for each trial (no Deep BT re-fetch; pure recompute)

# Input name → TV in_N ID mapping (order matches Pine input declarations)
INPUT_MAP = {
    "presetInput":          "in_0",
    "atrLenInput":          "in_1",
    "baseMultInput":        "in_2",
    # in_3 = sourceInput (skipped — not PF-affecting)
    "useAdaptiveInput":     "in_4",
    "erLengthInput":        "in_5",
    "adaptStrengthInput":   "in_6",
    "atrBaselineLenInput":  "in_7",
    "useTqiInput":          "in_8",
    "qualityStrengthInput": "in_9",
    "qualityCurveInput":    "in_10",
    "multSmoothInput":      "in_11",
    "useAsymBandsInput":    "in_12",
    "asymStrengthInput":    "in_13",
    "useEffAtrInput":       "in_14",
    "useCharFlipInput":     "in_15",
    "charFlipMinAgeInput":  "in_16",
    "charFlipHighInput":    "in_17",
    "charFlipLowInput":     "in_18",
    "tqiWeightErInput":     "in_19",
    "tqiWeightVolInput":    "in_20",
    "tqiWeightStructInput": "in_21",
    "tqiWeightMomInput":    "in_22",
    "tqiStructLenInput":    "in_23",
    "tqiMomLenInput":       "in_24",
    # in_25..in_35 = display-only inputs (skipped)
    "slAtrMultInput":       "in_36",
    "tpModeInput":          "in_37",
    "tp1RInput":            "in_38",
    "tp2RInput":            "in_39",
    "tp3RInput":            "in_40",
    "dynTpTqiWeightInput":  "in_41",
    "dynTpVolWeightInput":  "in_42",
    "dynTpMinScaleInput":   "in_43",
    "dynTpMaxScaleInput":   "in_44",
    "dynTpFloorR1Input":    "in_45",
    "dynTpCeilR3Input":     "in_46",
    # in_47 = labelOffsetInput (display only)
    # in_48 = showHitsInput (display only)
    "tradeMaxAgeInput":     "in_49",
}

SATS_NAME_FRAGMENT = "self-aware trend system"

# ── JS Snippets ───────────────────────────────────────────────────────────────

GET_SATS_ENTITIES_JS = """
(function() {
  var chart = window.TradingViewApi._activeChartWidgetWV.value();
  try {
    var all = chart.getAllStudies ? chart.getAllStudies() : [];
    return { entities: all };
  } catch(e) {
    return { error: e.message, entities: [] };
  }
})()
"""

MONKEY_PATCH_JS = """
(function(entityId, templateArray) {
  var chart = window.TradingViewApi._activeChartWidgetWV.value();
  var study = chart.getStudyById(entityId);
  if (!study) return { error: 'Study not found: ' + entityId };
  study.getInputValues = function() {
    return JSON.parse(JSON.stringify(templateArray));
  };
  var test = study.getInputValues();
  return { patched: true, test_len: test.length };
})(ENTITY_ID_PLACEHOLDER, TEMPLATE_PLACEHOLDER)
"""

SET_INPUTS_JS = """
(function(entityId, overrides) {
  var chart = window.TradingViewApi._activeChartWidgetWV.value();
  var study = chart.getStudyById(entityId);
  if (!study) return { error: 'Study not found: ' + entityId };
  var inputs = study.getInputValues();
  if (!inputs || inputs.length === 0) {
    return { error: 'getInputValues empty — monkey-patch may have been lost (page reload?)' };
  }
  var applied = {};
  for (var i = 0; i < inputs.length; i++) {
    if (overrides.hasOwnProperty(inputs[i].id)) {
      inputs[i].value = overrides[inputs[i].id];
      applied[inputs[i].id] = overrides[inputs[i].id];
    }
  }
  study.setInputValues(inputs);
  return { applied: applied, count: Object.keys(applied).length, total_inputs: inputs.length };
})(ENTITY_ID_PLACEHOLDER, OVERRIDES_PLACEHOLDER)
"""

CHECK_LOADING_JS = """
(function() {
  var spinner = document.querySelector('[class*="spinner"]');
  return { loading: !!spinner };
})()
"""

SCRAPE_JS = """
(function() {
  var els = Array.from(document.querySelectorAll('[class*="title-nEWm7_ye"]'));
  var result = {};
  els.forEach(function(el) {
    var label = el.textContent.trim();
    var cont = el.closest('[class*="container-"]');
    var valueEl = cont ? cont.querySelector('[class*="value-"]') : null;
    if (!valueEl) valueEl = el.parentElement ? el.parentElement.nextElementSibling : null;
    if (valueEl) result[label] = valueEl.textContent.trim();
  });
  return result;
})()
"""

# Fallback scraper using broader selectors
SCRAPE_JS_BROAD = """
(function() {
  var result = {};
  var keys = ['Net profit', 'Profit factor', 'Total trades', 'Max equity drawdown', 'Profitable trades'];
  document.querySelectorAll('*').forEach(function(el) {
    var t = el.textContent.trim();
    if (keys.indexOf(t) >= 0) {
      var parent = el.parentElement;
      if (parent) {
        var sib = parent.nextElementSibling || parent.lastElementChild;
        if (sib && sib.textContent.trim() !== t) {
          result[t] = sib.textContent.trim();
        }
      }
    }
  });
  return result;
})()
"""

# ── Helpers ───────────────────────────────────────────────────────────────────

def find_tv_target() -> str:
    targets = requests.get(f"http://{CDP_HOST}:{CDP_PORT}/json").json()
    for t in targets:
        if "tradingview.com/chart" in t.get("url", ""):
            return t["webSocketDebuggerUrl"]
    raise RuntimeError("TradingView chart CDP target not found on port 9222")


def load_stripped_template() -> list:
    """Load template without the 47KB Pine source blob."""
    if TEMPLATE_STRIPPED_PATH.exists():
        return json.loads(TEMPLATE_STRIPPED_PATH.read_text())
    if not TEMPLATE_PATH.exists():
        raise FileNotFoundError(f"Template not found: {TEMPLATE_PATH}")
    full = json.loads(TEMPLATE_PATH.read_text())
    stripped = [x for x in full if x["id"] != "text"]
    TEMPLATE_STRIPPED_PATH.write_text(json.dumps(stripped))
    print(f"Built stripped template → {TEMPLATE_STRIPPED_PATH} ({len(stripped)} fields)")
    return stripped


class CDPClient:
    def __init__(self, ws_url: str):
        self.ws_url = ws_url
        self.ws = None
        self._id = 0

    async def connect(self):
        self.ws = await websockets.connect(self.ws_url, max_size=50_000_000, ping_interval=None)
        await self._send("Runtime.enable", {})

    async def _send(self, method: str, params: dict) -> dict:
        self._id += 1
        msg_id = self._id
        payload = json.dumps({"id": msg_id, "method": method, "params": params})
        await self.ws.send(payload)
        while True:
            raw = await asyncio.wait_for(self.ws.recv(), timeout=60)
            msg = json.loads(raw)
            if msg.get("id") == msg_id:
                if "error" in msg:
                    raise RuntimeError(f"CDP error: {msg['error']}")
                return msg.get("result", {})

    async def evaluate(self, expression: str, timeout: float = 60.0):
        result = await self._send("Runtime.evaluate", {
            "expression": expression,
            "returnByValue": True,
            "awaitPromise": True,
        })
        val = result.get("result", {})
        if val.get("type") == "object" and "value" in val:
            return val["value"]
        return val.get("value")

    async def close(self):
        if self.ws:
            await self.ws.close()


def trial_to_overrides(trial: dict) -> dict:
    overrides = {}
    for param_name, in_id in INPUT_MAP.items():
        if param_name in trial:
            overrides[in_id] = trial[param_name]
    return overrides


def parse_metric(raw: str) -> float:
    if not raw:
        return float("nan")
    import re
    cleaned = raw.replace(",", "").replace("USD", "").replace("%", "")
    for token in cleaned.split():
        try:
            return float(token)
        except ValueError:
            continue
    m = re.search(r"[-+]?[0-9]*\.?[0-9]+", cleaned)
    return float(m.group()) if m else float("nan")


def log_trial(trial: dict, pf: float, trades: int, net_pnl: float,
              gross_profit: float, gross_loss: float, win_rate: float, max_dd: float):
    cmd = [
        sys.executable, str(HARNESS), "log",
        "--trial_json", json.dumps(trial),
        "--pf",           str(round(pf, 6)),
        "--trades",       str(trades),
        "--net_pnl",      str(round(net_pnl, 2)),
        "--gross_profit", str(round(gross_profit, 2)),
        "--gross_loss",   str(round(gross_loss, 2)),
        "--win_rate",     str(round(win_rate, 2)),
        "--max_dd",       str(round(max_dd, 2)),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=str(REPO_ROOT))
    return (result.stdout + result.stderr).strip()


def generate_trials(stage: int, seed: int, n: int) -> list[dict]:
    cmd = [sys.executable, str(HARNESS), "generate", "--stage", str(stage),
           "--seed", str(seed), "--n", str(n)]
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=str(REPO_ROOT))
    if result.returncode != 0:
        raise RuntimeError(f"Harness generate failed: {result.stderr}")
    return json.loads(result.stdout)


async def get_sats_entity_ids(client: CDPClient) -> list[str]:
    result = await client.evaluate(GET_SATS_ENTITIES_JS)
    if not result or "error" in result:
        return []
    entities = result.get("entities", [])
    return [e["id"] for e in entities
            if SATS_NAME_FRAGMENT in e.get("name", "").lower()]


async def apply_monkey_patch(client: CDPClient, entity_id: str, template: list) -> dict | None:
    """Patch study.getInputValues() to always return a clone of template."""
    template_json = json.dumps(template, separators=(",", ":"))
    js = MONKEY_PATCH_JS \
        .replace("ENTITY_ID_PLACEHOLDER", json.dumps(entity_id)) \
        .replace("TEMPLATE_PLACEHOLDER", template_json)
    return await client.evaluate(js)


async def set_inputs(client: CDPClient, entity_id: str, overrides: dict) -> dict | None:
    js = SET_INPUTS_JS \
        .replace("ENTITY_ID_PLACEHOLDER", json.dumps(entity_id)) \
        .replace("OVERRIDES_PLACEHOLDER", json.dumps(overrides))
    return await client.evaluate(js)


async def wait_for_compute(client: CDPClient, wait_secs: int) -> dict | None:
    """
    Poll until:
      (a) loading spinner disappears AND
      (b) strategy metrics appear in DOM.
    Returns scraped metrics dict or None on timeout.
    """
    await asyncio.sleep(3)  # give TV a beat to start computing
    deadline = asyncio.get_event_loop().time() + wait_secs
    poll_interval = 6
    while asyncio.get_event_loop().time() < deadline:
        loading = await client.evaluate(CHECK_LOADING_JS)
        if loading and loading.get("loading", True):
            await asyncio.sleep(poll_interval)
            continue
        # Spinner gone — try to read metrics
        metrics = await client.evaluate(SCRAPE_JS)
        if metrics and metrics.get("Profit factor"):
            return metrics
        # Try broad fallback
        metrics = await client.evaluate(SCRAPE_JS_BROAD)
        if metrics and ("Profit factor" in metrics or "Net profit" in metrics):
            return metrics
        await asyncio.sleep(poll_interval)
    return None


# ── Main sweep loop ───────────────────────────────────────────────────────────

async def run_sweep(stage: int, seed: int, n: int, wait_secs: int):
    ws_url = find_tv_target()
    print(f"Connecting to CDP: {ws_url}")
    client = CDPClient(ws_url)
    await client.connect()

    trials = generate_trials(stage, seed, n)
    print(f"Stage {stage}: {len(trials)} trials to run\n")

    # ── Find SATS-PS entity ───────────────────────────────────────────────────
    entity_ids = await get_sats_entity_ids(client)
    if not entity_ids:
        print("ERROR: No SATS-PS study found on chart.")
        print("  Add the strategy from the Pine editor ('Add to chart') then rerun.")
        await client.close()
        return
    entity_id = entity_ids[0]
    print(f"Found SATS-PS entity: {entity_id}")

    # ── Apply monkey-patch once ───────────────────────────────────────────────
    template = load_stripped_template()
    patch_result = await apply_monkey_patch(client, entity_id, template)
    if not patch_result or "error" in (patch_result or {}):
        print(f"ERROR: Monkey-patch failed: {patch_result}")
        await client.close()
        return
    print(f"Monkey-patch applied — {patch_result['test_len']} fields in template\n")

    skipped = 0
    for idx, trial in enumerate(trials):
        overrides = trial_to_overrides(trial)
        trial_label = f"Trial {idx+1}/{len(trials)}"

        # ── Set inputs (patch makes getInputValues work every time) ───────────
        set_result = await set_inputs(client, entity_id, overrides)
        if not set_result or "error" in (set_result or {}):
            err = (set_result or {}).get("error", "unknown")
            if "monkey-patch may have been lost" in err:
                # Page may have reloaded — re-apply patch
                print(f"  {trial_label}: Re-applying monkey-patch (page reload detected)...")
                patch_result = await apply_monkey_patch(client, entity_id, template)
                if patch_result and "error" not in patch_result:
                    set_result = await set_inputs(client, entity_id, overrides)
                else:
                    print(f"  {trial_label}: Re-patch failed. Skip.")
                    skipped += 1
                    continue
            if not set_result or "error" in (set_result or {}):
                print(f"  {trial_label}: SET FAILED: {set_result}. Skip.")
                skipped += 1
                continue

        n_applied = set_result.get("count", 0)
        print(f"  {trial_label}: entity={entity_id} set={n_applied} inputs, computing...",
              end="", flush=True)
        t0 = time.monotonic()

        # ── Wait for strategy tester to finish ────────────────────────────────
        metrics = await wait_for_compute(client, wait_secs)
        elapsed = time.monotonic() - t0

        if not metrics:
            print(f" TIMEOUT ({wait_secs}s) — skip")
            skipped += 1
            continue

        # ── Parse metrics ─────────────────────────────────────────────────────
        trades_raw = metrics.get("Total trades", "0")
        pf_raw     = metrics.get("Profit factor", "nan")
        pnl_raw    = metrics.get("Net profit", metrics.get("Total P&L", "0"))
        dd_raw     = metrics.get("Max equity drawdown", "0")
        wr_raw     = metrics.get("Profitable trades", "0")

        trades   = int(parse_metric(trades_raw) or 0)
        pf       = parse_metric(pf_raw)
        net_pnl  = parse_metric(pnl_raw)
        max_dd   = parse_metric(dd_raw)
        win_rate = parse_metric(wr_raw)

        if pf > 1.0 and pf != float("inf"):
            gross_loss   = net_pnl / (pf - 1.0)
            gross_profit = pf * gross_loss
        elif 0 < pf < 1.0:
            gross_profit = -net_pnl * pf / (1.0 - pf)
            gross_loss   = gross_profit / pf
        else:
            gross_profit = max(net_pnl, 0)
            gross_loss   = max(-net_pnl, 0)

        # ── Log result ────────────────────────────────────────────────────────
        log_out = log_trial(trial, pf, trades, net_pnl,
                            gross_profit, gross_loss, win_rate, max_dd)
        champ = "★ CHAMPION" if "CHAMPION" in log_out else ""
        print(f" PF={pf:.4f} trades={trades} net=${net_pnl:,.0f} ({elapsed:.0f}s)  {champ}")
        if champ:
            print(f"    {log_out}")

    await client.close()
    print(f"\nSweep complete. Skipped {skipped} trials.")

    status = subprocess.run([sys.executable, str(HARNESS), "status"],
                            capture_output=True, text=True, cwd=str(REPO_ROOT))
    print(status.stdout)


def main():
    parser = argparse.ArgumentParser(description="CDP sweep runner for SATS-PS optimization")
    parser.add_argument("--stage", type=int, required=True, help="Stage number (2, 3, 4, ...)")
    parser.add_argument("--seed",  type=int, default=42,  help="Random seed for LHS (Stage 4)")
    parser.add_argument("--n",     type=int, default=250, help="Number of LHS samples (Stage 4)")
    parser.add_argument("--wait",  type=int, default=WAIT_SECS,
                        help="Seconds to wait per trial for compute to finish")
    args = parser.parse_args()
    asyncio.run(run_sweep(args.stage, args.seed, args.n, args.wait))


if __name__ == "__main__":
    main()
