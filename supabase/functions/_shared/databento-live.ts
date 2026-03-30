// Databento Live API client — real-time ohlcv-1s via TCP gateway.
// Protocol: raw TCP, CRAM auth, JSON-encoded data records.
// Host: {dataset_id_lower_dashed}.lsg.databento.com:13000

import type { OhlcvBar } from "./databento.ts";

const LIVE_PORT = 13000;
const FIXED_PRICE_SCALE = 1_000_000_000;
const COLLECT_TIMEOUT_MS = 8_000; // collect for 8 seconds max
const READ_CHUNK_SIZE = 65_536;

function liveHost(dataset: string): string {
  return `${dataset.toLowerCase().replace(/\./g, "-")}.lsg.databento.com`;
}

async function sha256Hex(input: string): Promise<string> {
  const data = new TextEncoder().encode(input);
  const hash = await crypto.subtle.digest("SHA-256", data);
  return [...new Uint8Array(hash)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

// Read lines from a TCP connection until we see a line matching predicate or timeout.
async function readLine(
  conn: Deno.TcpConn,
  buf: { leftover: Uint8Array },
  timeoutMs: number,
): Promise<string> {
  const decoder = new TextDecoder();
  const deadline = Date.now() + timeoutMs;

  while (Date.now() < deadline) {
    // Check leftover buffer for a complete line
    const text = decoder.decode(buf.leftover);
    const nlIdx = text.indexOf("\n");
    if (nlIdx >= 0) {
      const line = text.slice(0, nlIdx);
      buf.leftover = new TextEncoder().encode(text.slice(nlIdx + 1));
      return line;
    }

    // Read more data
    const chunk = new Uint8Array(READ_CHUNK_SIZE);
    const remaining = Math.max(deadline - Date.now(), 100);
    const readPromise = conn.read(chunk);
    const timeoutPromise = new Promise<null>((resolve) => setTimeout(() => resolve(null), remaining));
    const n = await Promise.race([readPromise, timeoutPromise]);

    if (n === null) throw new Error("Live API read timeout");
    if (n === 0 || n === null) throw new Error("Live API connection closed");

    const combined = new Uint8Array(buf.leftover.length + (n as number));
    combined.set(buf.leftover);
    combined.set(chunk.subarray(0, n as number), buf.leftover.length);
    buf.leftover = combined;
  }

  throw new Error("Live API read timeout (deadline)");
}

// Collect JSON lines from the connection until timeout.
async function collectJsonLines(
  conn: Deno.TcpConn,
  buf: { leftover: Uint8Array },
  timeoutMs: number,
): Promise<string[]> {
  const decoder = new TextDecoder();
  const lines: string[] = [];
  const deadline = Date.now() + timeoutMs;

  while (Date.now() < deadline) {
    // Drain any complete lines from the leftover buffer
    let text = decoder.decode(buf.leftover);
    let nlIdx = text.indexOf("\n");
    while (nlIdx >= 0) {
      const line = text.slice(0, nlIdx).trim();
      if (line) lines.push(line);
      text = text.slice(nlIdx + 1);
      nlIdx = text.indexOf("\n");
    }
    buf.leftover = new TextEncoder().encode(text);

    // Read more data
    const chunk = new Uint8Array(READ_CHUNK_SIZE);
    const remaining = Math.max(deadline - Date.now(), 50);
    const readPromise = conn.read(chunk);
    const timeoutPromise = new Promise<null>((resolve) => setTimeout(() => resolve(null), remaining));
    const n = await Promise.race([readPromise, timeoutPromise]);

    if (n === null || n === 0) break; // timeout or closed
    if (typeof n !== "number") break;

    const combined = new Uint8Array(buf.leftover.length + n);
    combined.set(buf.leftover);
    combined.set(chunk.subarray(0, n), buf.leftover.length);
    buf.leftover = combined;
  }

  // Drain remaining lines from leftover
  const finalText = decoder.decode(buf.leftover);
  for (const line of finalText.split("\n")) {
    const trimmed = line.trim();
    if (trimmed) lines.push(trimmed);
  }

  return lines;
}

interface LiveOhlcvRecord {
  hd: { ts_event: string; rtype: number; publisher_id: number; instrument_id: number };
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

function parseOhlcvLine(line: string): OhlcvBar | null {
  try {
    const r: LiveOhlcvRecord = JSON.parse(line);
    if (!r.hd?.ts_event) return null;

    const tsNano = BigInt(r.hd.ts_event);
    const tsSec = Number(tsNano / BigInt(1_000_000_000));
    const open = Number(r.open) / FIXED_PRICE_SCALE;
    const high = Number(r.high) / FIXED_PRICE_SCALE;
    const low = Number(r.low) / FIXED_PRICE_SCALE;
    const close = Number(r.close) / FIXED_PRICE_SCALE;

    if (open > 0 && high > 0 && low > 0 && close > 0 && high >= low) {
      return { time: tsSec, open, high, low, close, volume: Number(r.volume) };
    }
  } catch {
    // skip malformed
  }
  return null;
}

// Aggregate 1-second bars into 1-minute bars.
function aggregate1sTo1m(bars1s: OhlcvBar[]): OhlcvBar[] {
  const byMinute = new Map<number, OhlcvBar>();

  for (const bar of bars1s) {
    const minuteSec = Math.floor(bar.time / 60) * 60;
    const existing = byMinute.get(minuteSec);
    if (!existing) {
      byMinute.set(minuteSec, { ...bar, time: minuteSec });
    } else {
      existing.high = Math.max(existing.high, bar.high);
      existing.low = Math.min(existing.low, bar.low);
      existing.close = bar.close;
      existing.volume += bar.volume;
    }
  }

  return [...byMinute.values()].sort((a, b) => a.time - b.time);
}

// Fetch the latest ohlcv-1s bars via the Databento Live gateway,
// aggregate to 1m, and return.
export async function fetchLiveOhlcv1m(params: {
  dataset: string;
  symbol: string;
  startSec: number; // unix seconds — fetch from this point forward
}): Promise<{ bars1m: OhlcvBar[]; bars1s_count: number }> {
  const apiKey = Deno.env.get("DATABENTO_API_KEY");
  if (!apiKey) throw new Error("DATABENTO_API_KEY is not set");

  const hostname = liveHost(params.dataset);
  const conn = await Deno.connect({ hostname, port: LIVE_PORT });
  const encoder = new TextEncoder();
  const buf = { leftover: new Uint8Array(0) };

  try {
    // 1. Read greeting — may be multi-line, CRAM challenge in a separate message
    const greeting = await readLine(conn, buf, 5_000);
    let cram = "";

    // Check if CRAM is in the greeting line itself
    const cramInGreeting = greeting.match(/cram=([^|\n]+)/);
    if (cramInGreeting) {
      cram = cramInGreeting[1];
    } else {
      // Read the next line which should contain the CRAM challenge
      const challengeLine = await readLine(conn, buf, 5_000);
      const cramInChallenge = challengeLine.match(/cram=([^|\n]+)/);
      if (cramInChallenge) {
        cram = cramInChallenge[1];
      } else {
        throw new Error(`Live API: no CRAM found. greeting=${greeting} next=${challengeLine}`);
      }
    }

    // 2. Compute CRAM response
    const authHash = await sha256Hex(`${cram}|${apiKey}`);
    const bucketId = apiKey.slice(-5);
    const authMsg = `auth=${authHash}-${bucketId}|dataset=${params.dataset}|encoding=json|ts_out=0\n`;
    await conn.write(encoder.encode(authMsg));

    // 3. Read auth response
    const authResp = await readLine(conn, buf, 5_000);
    if (!authResp.includes("success")) {
      throw new Error(`Live API auth failed: ${authResp}`);
    }

    // 4. Subscribe to ohlcv-1s with start time for replay
    const startNs = BigInt(params.startSec) * BigInt(1_000_000_000);
    const subMsg = `schema=ohlcv-1s|stype_in=continuous|symbols=${params.symbol}|start=${startNs}\n`;
    await conn.write(encoder.encode(subMsg));

    // 5. Send start command to begin data flow
    await conn.write(encoder.encode("start_session=0\n"));

    // 6. Collect JSON data lines
    const jsonLines = await collectJsonLines(conn, buf, COLLECT_TIMEOUT_MS);

    // Separate control messages from data records for debugging
    const controlLines = jsonLines.filter((l) => !l.startsWith("{"));
    const dataLines = jsonLines.filter((l) => l.startsWith("{"));

    if (dataLines.length === 0) {
      throw new Error(`Live API: 0 data records. control=${JSON.stringify(controlLines.slice(0, 5))} total_lines=${jsonLines.length}`);
    }

    // 6. Parse ohlcv-1s records
    const bars1s: OhlcvBar[] = [];
    for (const line of dataLines) {
      const bar = parseOhlcvLine(line);
      if (bar) bars1s.push(bar);
    }

    // 7. Aggregate 1s → 1m
    const bars1m = aggregate1sTo1m(bars1s);

    return { bars1m, bars1s_count: bars1s.length };
  } finally {
    try { conn.close(); } catch { /* ignore close errors */ }
  }
}
