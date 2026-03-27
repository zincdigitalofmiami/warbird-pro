// Massive Economy API client for inflation and inflation-expectations ingestion.
// Ported from lib/ingestion/massive.ts — process.env → Deno.env, relative imports.

import { createAdminClient } from "./admin.ts";

const MASSIVE_INFLATION_EXPECTATIONS_BASE = "https://api.massive.com/fed/v1/inflation-expectations";
const MASSIVE_INFLATION_BASE = "https://api.massive.com/fed/v1/inflation";
const ECON_INFLATION_TABLE = "econ_inflation_1d";

const FIELD_TO_SERIES_ID = {
  forward_years_5_to_10: "MASSIVE_IE_FORWARD_YEARS_5_TO_10",
  market_10_year: "MASSIVE_IE_MARKET_10_YEAR",
  market_5_year: "MASSIVE_IE_MARKET_5_YEAR",
  model_10_year: "MASSIVE_IE_MODEL_10_YEAR",
  model_1_year: "MASSIVE_IE_MODEL_1_YEAR",
  model_30_year: "MASSIVE_IE_MODEL_30_YEAR",
  model_5_year: "MASSIVE_IE_MODEL_5_YEAR",
} as const;

type MassiveInflationField = keyof typeof FIELD_TO_SERIES_ID;

interface MassiveInflationExpectationResult {
  date: string;
  forward_years_5_to_10?: number | null;
  market_10_year?: number | null;
  market_5_year?: number | null;
  model_10_year?: number | null;
  model_1_year?: number | null;
  model_30_year?: number | null;
  model_5_year?: number | null;
}

interface MassiveInflationExpectationResponse {
  status?: string;
  error?: string;
  message?: string;
  next_url?: string | null;
  results?: MassiveInflationExpectationResult[];
}

const INFLATION_FIELD_TO_SERIES_ID = {
  cpi: "MASSIVE_CPI",
  cpi_core: "MASSIVE_CPI_CORE",
  cpi_year_over_year: "MASSIVE_CPI_YOY",
  pce: "MASSIVE_PCE",
  pce_core: "MASSIVE_PCE_CORE",
  pce_spending: "MASSIVE_PCE_SPENDING",
} as const;

type MassiveInflationField2 = keyof typeof INFLATION_FIELD_TO_SERIES_ID;

interface MassiveInflationResult {
  date: string;
  cpi?: number | null;
  cpi_core?: number | null;
  cpi_year_over_year?: number | null;
  pce?: number | null;
  pce_core?: number | null;
  pce_spending?: number | null;
}

interface MassiveInflationResponse {
  status?: string;
  error?: string;
  message?: string;
  next_url?: string | null;
  results?: MassiveInflationResult[];
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function parseRetryAfterMs(retryAfter: string | null): number | null {
  if (!retryAfter) return null;
  const asNumber = Number.parseInt(retryAfter, 10);
  if (!Number.isNaN(asNumber)) {
    return Math.max(asNumber * 1000, 0);
  }
  const asDateMs = Date.parse(retryAfter);
  if (Number.isNaN(asDateMs)) return null;
  return Math.max(asDateMs - Date.now(), 0);
}

async function fetchWithRetry(url: string): Promise<Response> {
  const maxAttempts = 5;
  for (let attempt = 1; attempt <= maxAttempts; attempt++) {
    const response = await fetch(url, {
      signal: AbortSignal.timeout(30_000),
    });

    if (response.status !== 429 && response.status < 500) {
      return response;
    }

    if (attempt === maxAttempts) {
      return response;
    }

    const retryAfterMs =
      parseRetryAfterMs(response.headers.get("retry-after")) ??
      500 * 2 ** (attempt - 1);
    await sleep(retryAfterMs);
  }

  throw new Error("Unreachable fetch retry state");
}

function toIsoDate(value: Date): string {
  return value.toISOString().slice(0, 10);
}

function withApiKey(rawUrl: string, apiKey: string): string {
  const url = new URL(rawUrl);
  if (!url.searchParams.get("apiKey")) {
    url.searchParams.set("apiKey", apiKey);
  }
  return url.toString();
}

function normalizeStartDate(startDate?: string): string {
  if (startDate) return startDate;
  const d = new Date();
  d.setUTCDate(d.getUTCDate() - 30);
  return toIsoDate(d);
}

function isFiniteNumber(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value);
}

async function fetchInflationExpectations(
  apiKey: string,
  startDate: string,
): Promise<MassiveInflationExpectationResult[]> {
  const allResults: MassiveInflationExpectationResult[] = [];
  const seenPages = new Set<string>();

  const initialUrl = new URL(MASSIVE_INFLATION_EXPECTATIONS_BASE);
  initialUrl.searchParams.set("date.gte", startDate);
  initialUrl.searchParams.set("limit", "50000");
  initialUrl.searchParams.set("sort", "date.asc");
  initialUrl.searchParams.set("apiKey", apiKey);

  let nextUrl: string | null = initialUrl.toString();

  while (nextUrl) {
    if (seenPages.has(nextUrl)) break;
    seenPages.add(nextUrl);

    const response = await fetchWithRetry(nextUrl);

    if (!response.ok) {
      throw new Error(
        `Massive inflation-expectations API error: ${response.status} ${response.statusText}`,
      );
    }

    const payload: MassiveInflationExpectationResponse = await response.json();
    if (payload.status && payload.status !== "OK") {
      const details = payload.error ?? payload.message ?? payload.status;
      throw new Error(`Massive inflation-expectations response error: ${details}`);
    }

    const results = Array.isArray(payload.results) ? payload.results : [];
    allResults.push(...results);

    nextUrl = payload.next_url ? withApiKey(payload.next_url, apiKey) : null;
  }

  return allResults;
}

async function fetchInflation(
  apiKey: string,
  startDate: string,
): Promise<MassiveInflationResult[]> {
  const allResults: MassiveInflationResult[] = [];
  const seenPages = new Set<string>();

  const initialUrl = new URL(MASSIVE_INFLATION_BASE);
  initialUrl.searchParams.set("date.gte", startDate);
  initialUrl.searchParams.set("limit", "50000");
  initialUrl.searchParams.set("sort", "date.asc");
  initialUrl.searchParams.set("apiKey", apiKey);

  let nextUrl: string | null = initialUrl.toString();

  while (nextUrl) {
    if (seenPages.has(nextUrl)) break;
    seenPages.add(nextUrl);

    const response = await fetchWithRetry(nextUrl);

    if (!response.ok) {
      throw new Error(
        `Massive inflation API error: ${response.status} ${response.statusText}`,
      );
    }

    const payload: MassiveInflationResponse = await response.json();
    if (payload.status && payload.status !== "OK") {
      const details = payload.error ?? payload.message ?? payload.status;
      throw new Error(`Massive inflation response error: ${details}`);
    }

    const results = Array.isArray(payload.results) ? payload.results : [];
    allResults.push(...results);

    nextUrl = payload.next_url ? withApiKey(payload.next_url, apiKey) : null;
  }

  return allResults;
}

export async function ingestInflationFromMassive(params?: {
  startDate?: string;
}): Promise<{
  observations_fetched: number;
  rows_written: number;
  unique_days: number;
  start_date: string;
}> {
  const apiKey = Deno.env.get("MASSIVE_API_KEY");
  if (!apiKey) {
    throw new Error("MASSIVE_API_KEY is not set");
  }

  const startDate = normalizeStartDate(params?.startDate);
  const observations = await fetchInflation(apiKey, startDate);

  const rowsByKey = new Map<string, { ts: string; series_id: string; value: number }>();
  const uniqueDays = new Set<string>();

  for (const observation of observations) {
    if (!observation.date) continue;

    const ts = `${observation.date}T00:00:00Z`;
    uniqueDays.add(observation.date);

    const fields = Object.keys(INFLATION_FIELD_TO_SERIES_ID) as MassiveInflationField2[];
    for (const field of fields) {
      const value = observation[field];
      if (!isFiniteNumber(value)) continue;

      const seriesId = INFLATION_FIELD_TO_SERIES_ID[field];
      const key = `${ts}|${seriesId}`;
      rowsByKey.set(key, { ts, series_id: seriesId, value });
    }
  }

  const rows = Array.from(rowsByKey.values());
  if (rows.length === 0) {
    return {
      observations_fetched: observations.length,
      rows_written: 0,
      unique_days: uniqueDays.size,
      start_date: startDate,
    };
  }

  const supabase = createAdminClient();
  for (let i = 0; i < rows.length; i += 500) {
    const chunk = rows.slice(i, i + 500);
    const { error } = await supabase
      .from(ECON_INFLATION_TABLE)
      .upsert(chunk, { onConflict: "ts,series_id" });

    if (error) {
      throw new Error(`Massive inflation upsert failed: ${error.message}`);
    }
  }

  return {
    observations_fetched: observations.length,
    rows_written: rows.length,
    unique_days: uniqueDays.size,
    start_date: startDate,
  };
}

export async function ingestInflationExpectationsFromMassive(params?: {
  startDate?: string;
}): Promise<{
  observations_fetched: number;
  rows_written: number;
  unique_days: number;
  start_date: string;
}> {
  const apiKey = Deno.env.get("MASSIVE_API_KEY");
  if (!apiKey) {
    throw new Error("MASSIVE_API_KEY is not set");
  }

  const startDate = normalizeStartDate(params?.startDate);
  const observations = await fetchInflationExpectations(apiKey, startDate);

  const rowsByKey = new Map<string, { ts: string; series_id: string; value: number }>();
  const uniqueDays = new Set<string>();

  for (const observation of observations) {
    if (!observation.date) continue;

    const ts = `${observation.date}T00:00:00Z`;
    uniqueDays.add(observation.date);

    const fields = Object.keys(FIELD_TO_SERIES_ID) as MassiveInflationField[];
    for (const field of fields) {
      const value = observation[field];
      if (!isFiniteNumber(value)) continue;

      const seriesId = FIELD_TO_SERIES_ID[field];
      const key = `${ts}|${seriesId}`;
      rowsByKey.set(key, { ts, series_id: seriesId, value });
    }
  }

  const rows = Array.from(rowsByKey.values());
  if (rows.length === 0) {
    return {
      observations_fetched: observations.length,
      rows_written: 0,
      unique_days: uniqueDays.size,
      start_date: startDate,
    };
  }

  const supabase = createAdminClient();
  for (let i = 0; i < rows.length; i += 500) {
    const chunk = rows.slice(i, i + 500);
    const { error } = await supabase
      .from(ECON_INFLATION_TABLE)
      .upsert(chunk, { onConflict: "ts,series_id" });

    if (error) {
      throw new Error(`Massive upsert failed: ${error.message}`);
    }
  }

  return {
    observations_fetched: observations.length,
    rows_written: rows.length,
    unique_days: uniqueDays.size,
    start_date: startDate,
  };
}
