// Databento Historical HTTP API client — primary MES data path.
// Called by Vercel Cron (mes-catchup) every 5 minutes during market hours.
// Uses ohlcv-1m (free schema on Standard plan) with explicit contract symbols.

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
  const apiKey = process.env.DATABENTO_API_KEY;
  if (!apiKey) {
    throw new Error("DATABENTO_API_KEY is not set");
  }

  const basicAuth = Buffer.from(`${apiKey}:`).toString("base64");
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

    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);

    let response: Response;
    try {
      response = await fetch(`${DATABENTO_BASE}/timeseries.get_range`, {
        method: "POST",
        headers: {
          Authorization: `Basic ${basicAuth}`,
          "Content-Type": "application/x-www-form-urlencoded",
        },
        body: body.toString(),
        signal: controller.signal,
      });
    } catch (error) {
      clearTimeout(timeout);
      const msg = error instanceof Error ? error.message : String(error);
      if (msg.toLowerCase().includes("aborted")) {
        lastStatus = 408;
        lastError = `Request timed out after ${REQUEST_TIMEOUT_MS}ms`;
        continue;
      }
      throw error;
    }
    clearTimeout(timeout);

    if (response.ok) {
      const text = await response.text();
      return parseRecords(text);
    }

    lastStatus = response.status;
    lastError = await response.text().catch(() => "");

    // 422 = data not yet available — try with tighter end boundary
    if (response.status !== 422) break;

    let availableEnd: string | null = null;
    try {
      const detail = JSON.parse(lastError);
      availableEnd = detail?.detail?.payload?.available_end || null;
    } catch {
      availableEnd = null;
    }
    if (!availableEnd || availableEnd === queryEnd) break;

    // If available_end is before our start, data isn't ready yet — return empty
    if (new Date(availableEnd).getTime() <= new Date(params.start).getTime()) {
      return [];
    }
    queryEnd = availableEnd;
  }

  // If we exhausted retries on a 422 (data not yet available), return empty
  // instead of throwing — the next cron run will pick it up
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
