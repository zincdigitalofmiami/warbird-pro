#!/usr/bin/env node
import readline from "node:readline";
import { evaluate, getTargetInfo } from "../../.tradingview-mcp/src/connection.js";

function normalizeResult(result) {
  if (result && typeof result === "object") {
    if (result.result && Object.prototype.hasOwnProperty.call(result.result, "value")) {
      return result.result.value;
    }
    if (Object.prototype.hasOwnProperty.call(result, "value")) {
      return result.value;
    }
  }
  return result;
}

async function handle(msg) {
  if (!msg || typeof msg !== "object") {
    return { ok: false, error: "Invalid message payload" };
  }

  if (msg.cmd === "health") {
    const target = await getTargetInfo();
    return { ok: true, target };
  }

  if (msg.cmd === "eval") {
    if (typeof msg.expr !== "string" || msg.expr.length === 0) {
      return { ok: false, error: "eval requires non-empty expr" };
    }
    const raw = await evaluate(msg.expr, msg.opts && typeof msg.opts === "object" ? msg.opts : {});
    return { ok: true, value: normalizeResult(raw) };
  }

  if (msg.cmd === "close") {
    return { ok: true, closing: true };
  }

  return { ok: false, error: `Unknown cmd: ${msg.cmd}` };
}

const rl = readline.createInterface({
  input: process.stdin,
  crlfDelay: Infinity,
});

for await (const line of rl) {
  const trimmed = line.trim();
  if (!trimmed) {
    continue;
  }

  let msg;
  try {
    msg = JSON.parse(trimmed);
  } catch (err) {
    process.stdout.write(JSON.stringify({ ok: false, error: `Invalid JSON: ${err.message}` }) + "\n");
    continue;
  }

  try {
    const out = await handle(msg);
    process.stdout.write(JSON.stringify({ id: msg.id ?? null, ...out }) + "\n");
    if (out.closing) {
      break;
    }
  } catch (err) {
    process.stdout.write(
      JSON.stringify({
        id: msg.id ?? null,
        ok: false,
        error: err instanceof Error ? err.message : String(err),
      }) + "\n"
    );
  }
}
