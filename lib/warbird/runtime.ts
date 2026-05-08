import type { SupabaseClient } from "@supabase/supabase-js";
import { fetchOhlcv } from "@/lib/ingestion/databento";

const DASHBOARD_CORRELATION_SERIES = [
  { code: "NQ", dataset: "GLBX.MDP3", symbol: "NQ.c.0" },
  { code: "ZN", dataset: "GLBX.MDP3", symbol: "ZN.c.0" },
  { code: "CL", dataset: "GLBX.MDP3", symbol: "CL.c.0" },
  // Databento GLBX-derived realized volatility proxy from ES hourly closes.
  { code: "SPXVOL", dataset: "GLBX.MDP3", symbol: "ES.c.0", derived: "spxvol" as const },
  { code: "YM", dataset: "GLBX.MDP3", symbol: "YM.c.0" },
  // "NYSE futures" is mapped to the S&P 500 e-mini front contract.
  { code: "NYSE", dataset: "GLBX.MDP3", symbol: "ES.c.0" },
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

export async function fetchDashboardCorrelations(
  _supabase: SupabaseClient,
): Promise<DashboardCorrelationMap> {
  if (correlationCache && correlationCache.expiresAt > Date.now()) {
    return correlationCache.data;
  }

  const correlations: DashboardCorrelationMap = {};
  const end = new Date();
  const endIso = end.toISOString();
  const barFetches = new Map<string, Promise<Awaited<ReturnType<typeof fetchOhlcv>>>>();

  const seriesResults = await Promise.all(
    DASHBOARD_CORRELATION_SERIES.map(async (series) => {
      try {
        const fetchKey = `${series.dataset}|${series.symbol}`;
        if (!barFetches.has(fetchKey)) {
          const lookbackHours = "derived" in series && series.derived === "spxvol"
            ? SPXVOL_LOOKBACK_HOURS
            : CORRELATION_LOOKBACK_HOURS;
          const startIso = new Date(
            end.getTime() - lookbackHours * 60 * 60 * 1000,
          ).toISOString();

          barFetches.set(
            fetchKey,
            fetchOhlcv({
              dataset: series.dataset,
              symbol: series.symbol,
              stypeIn: "continuous",
              schema: "ohlcv-1h",
              start: startIso,
              end: endIso,
            }),
          );
        }

        const bars = await barFetches.get(fetchKey)!;

        if (bars.length < 2) return null;

        if ("derived" in series && series.derived === "spxvol") {
          const closes = bars.map((bar) => bar.close).filter((price) => Number.isFinite(price) && price > 0);
          const vols = computeRollingRealizedVol(closes, SPXVOL_WINDOW_HOURS);
          if (vols.length < 2) return null;
          const close = vols[vols.length - 1];
          const prevClose = vols[vols.length - 2];
          if (!Number.isFinite(close) || !Number.isFinite(prevClose)) return null;

          return { code: series.code, close, prevClose };
        }

        const last = bars[bars.length - 1];
        const prev = bars[bars.length - 2];
        if (!last || !prev) return null;
        if (!Number.isFinite(last.close) || !Number.isFinite(prev.close)) return null;
        if (last.close <= 0 || prev.close <= 0) return null;

        return {
          code: series.code,
          close: last.close,
          prevClose: prev.close,
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
