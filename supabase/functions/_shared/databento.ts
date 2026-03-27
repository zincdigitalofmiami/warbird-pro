// Databento Historical HTTP API client.
// Ported from lib/ingestion/databento.ts — Buffer.from().toString("base64") → btoa(),
// process.env → Deno.env.

const DATABENTO_BASE = "https://hist.databento.com/v0";
const FIXED_PRICE_SCALE = 1_000_000_000;
const REQUEST_TIMEOUT_MS = 90_000;
const MAX_ATTEMPTS = 4;

export interface OhlcvBar {
  time: number; // unix seconds
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

interface DatabentoRecord {
  hd: { ts_event: string; rtype: number; publisher_id: number; instrument_id: number };
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

export async function fetchOhlcv(params: {
  dataset: string;
  symbol: string;
  stypeIn: string;
  start: string;
  end: string;
  schema?: string;
}): Promise<OhlcvBar[]> {
  const apiKey = Deno.env.get("DATABENTO_API_KEY");
  if (!apiKey) {
    throw new Error("DATABENTO_API_KEY is not set");
  }

  const basicAuth = btoa(`${apiKey}:`);
  let queryEnd = params.end;
  let lastError = "";
  let lastStatus = 500;

  for (let attempt = 0; attempt < MAX_ATTEMPTS; attempt++) {
    const body = new URLSearchParams({
      dataset: params.dataset,
      symbols: params.symbol,
      schema: params.schema || "ohlcv-1m",
      stype_in: params.stypeIn,
      start: params.start,
      end: queryEnd,
      encoding: "json",
    });

    let response: Response;
    try {
      response = await fetch(`${DATABENTO_BASE}/timeseries.get_range`, {
        method: "POST",
        headers: {
          Authorization: `Basic ${basicAuth}`,
          "Content-Type": "application/x-www-form-urlencoded",
        },
        body: body.toString(),
        signal: AbortSignal.timeout(REQUEST_TIMEOUT_MS),
      });
    } catch (error) {
      const msg = error instanceof Error ? error.message : String(error);
      if (msg.toLowerCase().includes("aborted") || msg.toLowerCase().includes("timed out")) {
        lastStatus = 408;
        lastError = `Request timed out after ${REQUEST_TIMEOUT_MS}ms`;
        continue;
      }
      throw error;
    }

    if (response.ok) {
      const text = await response.text();
      return parseRecords(text);
    }

    lastStatus = response.status;
    lastError = await response.text().catch(() => "");

    if (response.status !== 422) break;

    let availableEnd: string | null = null;
    try {
      const detail = JSON.parse(lastError);
      availableEnd = detail?.detail?.payload?.available_end || null;
    } catch {
      availableEnd = null;
    }
    if (!availableEnd || availableEnd === queryEnd) break;

    if (new Date(availableEnd).getTime() <= new Date(params.start).getTime()) {
      return [];
    }
    queryEnd = availableEnd;
  }

  if (lastStatus === 422) {
    return [];
  }

  throw new Error(`Databento API error ${lastStatus}: ${lastError.slice(0, 500)}`);
}

function parseRecords(text: string): OhlcvBar[] {
  if (!text.trim()) return [];

  const bars: OhlcvBar[] = [];
  for (const line of text.trim().split("\n")) {
    if (!line.trim()) continue;
    try {
      const r: DatabentoRecord = JSON.parse(line);
      const tsNano = BigInt(r.hd.ts_event);
      const tsSec = Number(tsNano / BigInt(1_000_000_000));
      const open = Number(r.open) / FIXED_PRICE_SCALE;
      const high = Number(r.high) / FIXED_PRICE_SCALE;
      const low = Number(r.low) / FIXED_PRICE_SCALE;
      const close = Number(r.close) / FIXED_PRICE_SCALE;

      if (
        open > 0 && high > 0 && low > 0 && close > 0 &&
        high >= low &&
        !isNaN(open) && !isNaN(high) && !isNaN(low) && !isNaN(close) && !isNaN(r.volume)
      ) {
        bars.push({ time: tsSec, open, high, low, close, volume: Number(r.volume) });
      }
    } catch {
      // Skip malformed lines
    }
  }
  return bars.sort((a, b) => a.time - b.time);
}
