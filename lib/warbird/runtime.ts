import type { SupabaseClient } from "@supabase/supabase-js";

interface HourlyBarRow {
  ts: string;
  close: number | string;
  volume: number | string | null;
}

const DASHBOARD_CORRELATION_SERIES = [
  { code: "NQ", sourceCode: "NQ", weight: 1 / 6 },
  { code: "ZN", sourceCode: "ZN", weight: 1 / 6 },
  { code: "CL", sourceCode: "CL", weight: 1 / 6 },
  // SPXVOL is derived from ES hourly closes.
  { code: "SPXVOL", sourceCode: "ES", derived: "spxvol" as const, weight: 1 / 6 },
  { code: "YM", sourceCode: "YM", weight: 1 / 6 },
  // "NYSE futures" panel intentionally mirrors ES on this surface.
  { code: "NYSE", sourceCode: "ES", weight: 1 / 6 },
] as const;
const FETCH_LOOKBACK_BARS = 240;
const MODEL_WINDOW_BARS = 96;
const RVOL_WINDOW_BARS = 24;
const RVOL_HOUR_OF_DAY_LOOKBACK_BARS = 24 * 28;
const RVOL_MIN_HOD_SAMPLES = 8;
const MIN_MODEL_POINTS = 24;
const SPXVOL_WINDOW_HOURS = 24;
const SPXVOL_ANNUALIZATION = Math.sqrt(252 * 24);
const MAX_RVOL_BOOST = 1.75;
const MIN_RVOL_BOOST = 0.55;
const IMPACT_SATURATION_BPS = 12;
const STALE_HARD_STOP_HOURS = 10;
const CORRELATION_CACHE_TTL_MS = 5 * 60 * 1000;

let correlationCache: { expiresAt: number; data: DashboardCorrelationMap } | null = null;

const SYMBOL_NOTIONAL_MULTIPLIER: Record<string, number> = {
  MES: 5,
  ES: 50,
  NQ: 20,
  ZN: 1000,
  CL: 1000,
  YM: 5,
};

interface DashboardCorrelationPoint {
  close: number;
  prevClose: number;
  changePct: number;
  impact: number;
  mesBps: number;
  mesBpsRaw: number;
  confidence: number;
  betaToMes: number | null;
  corrToMes: number | null;
  rvol: number | null;
  notionalVolume: number | null;
}

interface HourlyBar {
  ts: string;
  close: number;
  volume: number;
  notionalVolume: number;
}

export type DashboardCorrelationMap = Record<string, DashboardCorrelationPoint>;

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

function clamp(value: number, min: number, max: number): number {
  return Math.max(min, Math.min(max, value));
}

function computeStdDev(values: number[]): number {
  if (values.length < 2) return 0;
  const mean = values.reduce((sum, value) => sum + value, 0) / values.length;
  const variance =
    values.reduce((sum, value) => sum + (value - mean) ** 2, 0) / values.length;
  return Math.sqrt(variance);
}

function computeCovariance(a: number[], b: number[]): number {
  if (a.length !== b.length || a.length < 2) return 0;
  const meanA = a.reduce((sum, value) => sum + value, 0) / a.length;
  const meanB = b.reduce((sum, value) => sum + value, 0) / b.length;
  let total = 0;
  for (let i = 0; i < a.length; i += 1) {
    total += (a[i] - meanA) * (b[i] - meanB);
  }
  return total / a.length;
}

function computeMedian(values: number[]): number {
  if (values.length === 0) return 0;
  const sorted = [...values].sort((a, b) => a - b);
  const mid = Math.floor(sorted.length / 2);
  if (sorted.length % 2 === 0) {
    return (sorted[mid - 1] + sorted[mid]) / 2;
  }
  return sorted[mid];
}

function computeRvolAndNotional(
  bars: HourlyBar[],
): { rvol: number | null; notionalVolume: number | null } {
  if (bars.length === 0) return { rvol: null, notionalVolume: null };
  const latest = bars[bars.length - 1];
  const latestHour = new Date(latest.ts).getUTCHours();
  const priorBars = bars.slice(0, -1);
  const sameHourWindow = priorBars
    .slice(-RVOL_HOUR_OF_DAY_LOOKBACK_BARS)
    .filter((bar) => new Date(bar.ts).getUTCHours() === latestHour)
    .map((bar) => bar.notionalVolume)
    .filter((value) => Number.isFinite(value) && value > 0);
  const rollingWindow = priorBars
    .slice(Math.max(0, priorBars.length - RVOL_WINDOW_BARS))
    .map((bar) => bar.notionalVolume)
    .filter((value) => Number.isFinite(value) && value > 0);
  const baselineSource = sameHourWindow.length >= RVOL_MIN_HOD_SAMPLES
    ? sameHourWindow
    : rollingWindow;
  const baseline = computeMedian(baselineSource);
  if (!Number.isFinite(latest.notionalVolume) || latest.notionalVolume <= 0) {
    return { rvol: null, notionalVolume: null };
  }
  if (!Number.isFinite(baseline) || baseline <= 0) {
    return { rvol: 1, notionalVolume: latest.notionalVolume };
  }
  return {
    rvol: latest.notionalVolume / baseline,
    notionalVolume: latest.notionalVolume,
  };
}

function buildReturnByTs(bars: HourlyBar[]): Map<string, number> {
  const result = new Map<string, number>();
  for (let i = 1; i < bars.length; i += 1) {
    const prev = bars[i - 1];
    const curr = bars[i];
    if (prev.close <= 0 || curr.close <= 0) continue;
    const ret = Math.log(curr.close / prev.close);
    if (!Number.isFinite(ret)) continue;
    result.set(curr.ts, ret);
  }
  return result;
}

function alignReturnPairs(
  symbolReturns: Map<string, number>,
  mesReturns: Map<string, number>,
): { symbol: number[]; mes: number[] } {
  const pairs: Array<{ ts: string; symbol: number; mes: number }> = [];
  for (const [ts, symbolRet] of symbolReturns.entries()) {
    const mesRet = mesReturns.get(ts);
    if (mesRet == null || !Number.isFinite(mesRet)) continue;
    pairs.push({ ts, symbol: symbolRet, mes: mesRet });
  }
  pairs.sort((a, b) => a.ts.localeCompare(b.ts));
  const tail = pairs.slice(-MODEL_WINDOW_BARS);
  return {
    symbol: tail.map((row) => row.symbol),
    mes: tail.map((row) => row.mes),
  };
}

function buildSpxVolBarsFromEs(esBars: HourlyBar[]): HourlyBar[] {
  if (esBars.length < SPXVOL_WINDOW_HOURS + 2) return [];

  const result: HourlyBar[] = [];
  const logReturns: number[] = [];
  for (let i = 1; i < esBars.length; i += 1) {
    const prev = esBars[i - 1].close;
    const curr = esBars[i].close;
    if (prev <= 0 || curr <= 0) {
      logReturns.push(NaN);
    } else {
      logReturns.push(Math.log(curr / prev));
    }
  }

  for (let i = SPXVOL_WINDOW_HOURS; i < logReturns.length; i += 1) {
    const slice = logReturns.slice(i - SPXVOL_WINDOW_HOURS, i);
    if (slice.some((value) => !Number.isFinite(value))) continue;
    const mean = slice.reduce((sum, value) => sum + value, 0) / slice.length;
    const variance =
      slice.reduce((sum, value) => sum + (value - mean) ** 2, 0) / slice.length;
    const vol = Math.sqrt(variance) * SPXVOL_ANNUALIZATION * 100;
    const sourceBar = esBars[i];
    result.push({
      ts: sourceBar.ts,
      close: vol,
      volume: sourceBar.volume,
      notionalVolume: sourceBar.notionalVolume,
    });
  }

  return result;
}

function calculateImpactPoint(
  symbolBars: HourlyBar[],
  mesBars: HourlyBar[],
  nowMs: number,
): Omit<DashboardCorrelationPoint, "close" | "prevClose" | "changePct"> & {
  close: number;
  prevClose: number;
  changePct: number;
} {
  if (symbolBars.length < 2 || mesBars.length < 2) {
    return {
      close: NaN,
      prevClose: NaN,
      changePct: 0,
      impact: 0,
      mesBps: 0,
      mesBpsRaw: 0,
      confidence: 0,
      betaToMes: null,
      corrToMes: null,
      rvol: null,
      notionalVolume: null,
    };
  }

  const close = symbolBars[symbolBars.length - 1].close;
  const prevClose = symbolBars[symbolBars.length - 2].close;
  const changePct = prevClose > 0 ? ((close - prevClose) / prevClose) * 100 : 0;

  const symbolReturns = buildReturnByTs(symbolBars);
  const mesReturns = buildReturnByTs(mesBars);
  const paired = alignReturnPairs(symbolReturns, mesReturns);

  if (paired.symbol.length < MIN_MODEL_POINTS) {
    const { rvol, notionalVolume } = computeRvolAndNotional(symbolBars);
    return {
      close,
      prevClose,
      changePct,
      impact: 0,
      mesBps: 0,
      mesBpsRaw: 0,
      confidence: 0,
      betaToMes: null,
      corrToMes: null,
      rvol,
      notionalVolume,
    };
  }

  const cov = computeCovariance(paired.symbol, paired.mes);
  const stdSymbol = computeStdDev(paired.symbol);
  const stdMes = computeStdDev(paired.mes);
  const varSymbol = stdSymbol ** 2;

  if (varSymbol <= 1e-12 || stdMes <= 1e-9) {
    const { rvol, notionalVolume } = computeRvolAndNotional(symbolBars);
    return {
      close,
      prevClose,
      changePct,
      impact: 0,
      mesBps: 0,
      mesBpsRaw: 0,
      confidence: 0,
      betaToMes: null,
      corrToMes: null,
      rvol,
      notionalVolume,
    };
  }

  const betaToMes = cov / varSymbol;
  const corrToMes = cov / (stdSymbol * stdMes);

  const latestSymbolRet = paired.symbol[paired.symbol.length - 1] ?? 0;
  const rawMesRet = betaToMes * latestSymbolRet;
  const mesBpsRaw = rawMesRet * 10_000;

  const { rvol, notionalVolume } = computeRvolAndNotional(symbolBars);
  const rvolBoost = rvol == null
    ? 1
    : clamp(1 + 0.35 * Math.log(Math.max(rvol, 1e-6)), MIN_RVOL_BOOST, MAX_RVOL_BOOST);

  const latestTs = symbolBars[symbolBars.length - 1]?.ts ?? null;
  const ageHours = latestTs
    ? Math.max(0, (nowMs - new Date(latestTs).getTime()) / (60 * 60 * 1000))
    : 999;
  const stalenessWeight = ageHours >= STALE_HARD_STOP_HOURS
    ? 0
    : clamp(24 / (24 + ageHours), 0.15, 1);

  const sampleWeight = clamp(paired.symbol.length / MODEL_WINDOW_BARS, 0.25, 1);
  const corrWeight = clamp(Math.abs(corrToMes), 0, 1);
  const confidence = clamp(corrWeight * sampleWeight * stalenessWeight, 0, 1);

  const mesBps = mesBpsRaw * rvolBoost * confidence;
  const scaledImpact = Math.tanh(mesBps / IMPACT_SATURATION_BPS);
  const impact = scaledImpact * confidence;

  return {
    close,
    prevClose,
    changePct,
    impact: Number.isFinite(impact) ? impact : 0,
    mesBps: Number.isFinite(mesBps) ? mesBps : 0,
    mesBpsRaw: Number.isFinite(mesBpsRaw) ? mesBpsRaw : 0,
    confidence: Number.isFinite(confidence) ? confidence : 0,
    betaToMes: Number.isFinite(betaToMes) ? betaToMes : null,
    corrToMes: Number.isFinite(corrToMes) ? corrToMes : null,
    rvol,
    notionalVolume,
  };
}

async function fetchRecentBars(
  supabase: SupabaseClient,
  symbolCode: string,
): Promise<HourlyBar[]> {
  const query = symbolCode === "MES"
    ? supabase
      .from("mes_1h")
      .select("ts, close, volume")
      .order("ts", { ascending: false })
      .limit(FETCH_LOOKBACK_BARS)
    : supabase
      .from("cross_asset_1h")
      .select("ts, close, volume")
      .eq("symbol_code", symbolCode)
      .order("ts", { ascending: false })
      .limit(FETCH_LOOKBACK_BARS);

  const { data, error } = await query;
  if (error || !data || data.length === 0) return [];

  const multiplier = SYMBOL_NOTIONAL_MULTIPLIER[symbolCode] ?? 1;

  return (data as HourlyBarRow[])
    .map((row) => {
      const close = Number(row.close);
      const volume = Number(row.volume ?? 0);
      return {
        ts: String(row.ts),
        close,
        volume,
        notionalVolume: close * volume * multiplier,
      };
    })
    .filter((bar) =>
      Number.isFinite(bar.close) &&
      bar.close > 0 &&
      Number.isFinite(bar.volume) &&
      bar.volume >= 0,
    )
    .sort((a, b) => a.ts.localeCompare(b.ts));
}

export async function fetchDashboardCorrelations(
  supabase: SupabaseClient,
): Promise<DashboardCorrelationMap> {
  if (correlationCache && correlationCache.expiresAt > Date.now()) {
    return correlationCache.data;
  }

  const correlations: DashboardCorrelationMap = {};
  const baseBarFetches = new Map<string, Promise<HourlyBar[]>>();

  const mesBars = await fetchRecentBars(supabase, "MES");
  const nowMs = Date.now();

  const seriesResults = await Promise.all(
    DASHBOARD_CORRELATION_SERIES.map(async (series) => {
      try {
        const fetchKey = series.sourceCode;
        if (!baseBarFetches.has(fetchKey)) {
          baseBarFetches.set(fetchKey, fetchRecentBars(supabase, series.sourceCode));
        }

        const baseBars = await baseBarFetches.get(fetchKey)!;
        const symbolBars = "derived" in series && series.derived === "spxvol"
          ? buildSpxVolBarsFromEs(baseBars)
          : baseBars;

        const point = calculateImpactPoint(symbolBars, mesBars, nowMs);
        if (!Number.isFinite(point.close) || !Number.isFinite(point.prevClose)) return null;

        // Weight each lane contribution so IM Score is directly summable on the client.
        const weightedImpact = point.impact * series.weight;
        const weightedMesBps = point.mesBps * series.weight;
        return {
          code: series.code,
          ...point,
          impact: weightedImpact,
          mesBps: weightedMesBps,
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
      changePct: result.changePct,
      impact: Number.isFinite(result.impact) ? result.impact : 0,
      mesBps: Number.isFinite(result.mesBps) ? result.mesBps : 0,
      mesBpsRaw: Number.isFinite(result.mesBpsRaw) ? result.mesBpsRaw : 0,
      confidence: Number.isFinite(result.confidence) ? result.confidence : 0,
      betaToMes: result.betaToMes,
      corrToMes: result.corrToMes,
      rvol: result.rvol,
      notionalVolume: result.notionalVolume,
    };
  }

  correlationCache = {
    expiresAt: Date.now() + CORRELATION_CACHE_TTL_MS,
    data: correlations,
  };

  return correlations;
}
