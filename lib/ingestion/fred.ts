// FRED API client for economic data ingestion.
// Each FRED series is fetched individually and upserted to its category table.

import { createAdminClient } from "@/lib/supabase/admin";

const FRED_BASE = "https://api.stlouisfed.org/fred/series/observations";

// Maps econ_category enum → Supabase table name
const CATEGORY_TABLE: Record<string, string> = {
  rates: "econ_rates_1d",
  yields: "econ_yields_1d",
  vol: "econ_vol_1d",
  inflation: "econ_inflation_1d",
  fx: "econ_fx_1d",
  labor: "econ_labor_1d",
  activity: "econ_activity_1d",
  money: "econ_money_1d",
  commodities: "econ_commodities_1d",
  indexes: "econ_indexes_1d",
};

export const VALID_CATEGORIES = Object.keys(CATEGORY_TABLE);

interface FredObservation {
  date: string;
  value: string;
}

interface FredResponse {
  observations: FredObservation[];
}

// Fetch observations for a single FRED series (last N observations)
async function fetchSeries(
  seriesId: string,
  apiKey: string,
  limit = 100,
): Promise<{ date: string; value: number }[]> {
  const params = new URLSearchParams({
    series_id: seriesId,
    api_key: apiKey,
    file_type: "json",
    sort_order: "desc",
    limit: String(limit),
  });

  const response = await fetch(`${FRED_BASE}?${params}`, {
    signal: AbortSignal.timeout(30_000),
  });

  if (!response.ok) {
    throw new Error(
      `FRED API error for ${seriesId}: ${response.status} ${response.statusText}`,
    );
  }

  const data: FredResponse = await response.json();

  return data.observations
    .filter((obs) => obs.value !== "." && obs.value !== "")
    .map((obs) => ({
      date: obs.date,
      value: parseFloat(obs.value),
    }))
    .filter((obs) => !isNaN(obs.value));
}

// Ingest all active series for a given category.
// Returns the total number of rows written.
export async function ingestCategory(category: string): Promise<{
  series_count: number;
  rows_written: number;
}> {
  const tableName = CATEGORY_TABLE[category];
  if (!tableName) {
    throw new Error(`Unknown category: ${category}`);
  }

  const apiKey = process.env.FRED_API_KEY;
  if (!apiKey) {
    throw new Error("FRED_API_KEY is not set");
  }

  const supabase = createAdminClient();

  // Get active series for this category
  const { data: seriesList, error: listErr } = await supabase
    .from("series_catalog")
    .select("series_id")
    .eq("category", category)
    .eq("is_active", true);

  if (listErr) {
    throw new Error(`Failed to query series_catalog: ${listErr.message}`);
  }

  if (!seriesList || seriesList.length === 0) {
    return { series_count: 0, rows_written: 0 };
  }

  let totalRows = 0;

  for (const { series_id } of seriesList) {
    const observations = await fetchSeries(series_id, apiKey);

    if (observations.length === 0) continue;

    const rows = observations.map((obs) => ({
      ts: `${obs.date}T00:00:00Z`,
      series_id,
      value: obs.value,
    }));

    // Batch upsert in chunks of 100
    for (let i = 0; i < rows.length; i += 100) {
      const chunk = rows.slice(i, i + 100);
      const { error } = await supabase
        .from(tableName)
        .upsert(chunk, { onConflict: "ts,series_id" });
      if (error) {
        throw new Error(
          `Upsert failed for ${series_id} → ${tableName}: ${error.message}`,
        );
      }
    }

    totalRows += rows.length;
  }

  return { series_count: seriesList.length, rows_written: totalRows };
}
