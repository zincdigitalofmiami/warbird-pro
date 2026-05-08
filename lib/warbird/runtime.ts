import type { SupabaseClient } from "@supabase/supabase-js";

interface CrossAssetCloseRow {
  ts: string;
  close: number | string;
}

const DASHBOARD_CORRELATION_SERIES = [
  { code: "NQ", sourceCode: "NQ" },
  { code: "ZN", sourceCode: "ZN" },
  { code: "CL", sourceCode: "CL" },
  // SPXVOL is derived from ES hourly closes.
  { code: "SPXVOL", sourceCode: "ES", derived: "spxvol" as const },
  { code: "YM", sourceCode: "YM" },
  // "NYSE futures" panel intentionally mirrors ES on this surface.
  { code: "NYSE", sourceCode: "ES" },
] as const;
const CORRELATION_LOOKBACK_HOURS = 36;
const SPXVOL_LOOKBACK_HOURS = 168;
const SPXVOL_WINDOW_HOURS = 24;
const SPXVOL_ANNUALIZATION = Math.sqrt(252 * 24);
const CORRELATION_CACHE_TTL_MS = 55 * 60 * 1000;

let correlationCache: { expiresAt: number; data: DashboardCorrelationMap } | null = null;

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

function computeRollingRealizedVol(closes: number[], window: number): number[] {
  if (closes.length < window + 2) return [];

  const logReturns: number[] = [];
  for (let i = 1; i < closes.length; i += 1) {
    const curr = closes[i];
    const prev = closes[i - 1];
    if (!Number.isFinite(curr) || !Number.isFinite(prev) || curr <= 0 || prev <= 0) {
      return [];
    }
    logReturns.push(Math.log(curr / prev));
  }

  const vols: number[] = [];
  for (let i = window; i <= logReturns.length; i += 1) {
    const slice = logReturns.slice(i - window, i);
    const mean = slice.reduce((sum, v) => sum + v, 0) / slice.length;
    const variance = slice.reduce((sum, v) => sum + (v - mean) ** 2, 0) / slice.length;
    vols.push(Math.sqrt(variance) * SPXVOL_ANNUALIZATION * 100);
  }

  return vols;
}

async function fetchRecentCloses(
  supabase: SupabaseClient,
  symbolCode: string,
  limit: number,
): Promise<number[]> {
  const { data, error } = await supabase
    .from("cross_asset_1h")
    .select("ts, close")
    .eq("symbol_code", symbolCode)
    .order("ts", { ascending: false })
    .limit(limit);

  if (error || !data || data.length === 0) return [];

  return (data as CrossAssetCloseRow[])
    .map((row) => Number(row.close))
    .filter((value) => Number.isFinite(value) && value > 0)
    .reverse();
}

export async function fetchDashboardCorrelations(
  supabase: SupabaseClient,
): Promise<DashboardCorrelationMap> {
  if (correlationCache && correlationCache.expiresAt > Date.now()) {
    return correlationCache.data;
  }

  const correlations: DashboardCorrelationMap = {};
  const closeFetches = new Map<string, Promise<number[]>>();

  const seriesResults = await Promise.all(
    DASHBOARD_CORRELATION_SERIES.map(async (series) => {
      try {
        const fetchKey = `${series.sourceCode}|${"derived" in series ? "spxvol" : "close"}`;
        if (!closeFetches.has(fetchKey)) {
          const lookbackHours = "derived" in series && series.derived === "spxvol"
            ? SPXVOL_LOOKBACK_HOURS
            : CORRELATION_LOOKBACK_HOURS;
          closeFetches.set(
            fetchKey,
            fetchRecentCloses(supabase, series.sourceCode, lookbackHours),
          );
        }

        const closes = await closeFetches.get(fetchKey)!;
        if (closes.length < 2) return null;

        if ("derived" in series && series.derived === "spxvol") {
          const vols = computeRollingRealizedVol(closes, SPXVOL_WINDOW_HOURS);
          if (vols.length < 2) return null;
          const close = vols[vols.length - 1];
          const prevClose = vols[vols.length - 2];
          if (!Number.isFinite(close) || !Number.isFinite(prevClose)) return null;

          return { code: series.code, close, prevClose };
        }

        const close = closes[closes.length - 1];
        const prevClose = closes[closes.length - 2];
        if (!Number.isFinite(close) || !Number.isFinite(prevClose)) return null;
        if (close <= 0 || prevClose <= 0) return null;

        return {
          code: series.code,
          close,
          prevClose,
        };
      } catch {
        return null;
      }
    }),
  );

  for (const result of seriesResults) {
    if (!result) continue;
    correlations[result.code] = {
      close: result.close,
      prevClose: result.prevClose,
    };
  }

  correlationCache = {
    expiresAt: Date.now() + CORRELATION_CACHE_TTL_MS,
    data: correlations,
  };

  return correlations;
}
