import type { SupabaseClient } from "@supabase/supabase-js";

const DASHBOARD_CORRELATION_SYMBOLS = ["NQ", "RTY", "CL", "HG", "6E", "6J"] as const;

export type DashboardCorrelationMap = Record<string, { close: number; prevClose: number }>;

export function emptyDashboardCounts() {
  return {
    active: 0,
    counterTrend: 0,
    tp1Hit: 0,
    tp2Hit: 0,
    stopped: 0,
    open: 0,
  };
}

export async function fetchDashboardCorrelations(
  supabase: SupabaseClient,
): Promise<DashboardCorrelationMap> {
  const results = await Promise.all(
    DASHBOARD_CORRELATION_SYMBOLS.map((symbolCode) =>
      supabase
        .from("cross_asset_1h")
        .select("ts, close")
        .eq("symbol_code", symbolCode)
        .order("ts", { ascending: false })
        .limit(2),
    ),
  );

  const correlations: DashboardCorrelationMap = {};

  DASHBOARD_CORRELATION_SYMBOLS.forEach((symbolCode, index) => {
    const result = results[index];
    if (result.error || !result.data || result.data.length < 2) {
      return;
    }

    correlations[symbolCode] = {
      close: Number(result.data[0].close),
      prevClose: Number(result.data[1].close),
    };
  });

  return correlations;
}
