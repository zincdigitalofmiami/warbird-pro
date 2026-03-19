import { writeFile } from "node:fs/promises";
import { createClient } from "@supabase/supabase-js";
import { buildDailyBiasLayer } from "@/scripts/warbird/daily-layer";
import { buildFibGeometry } from "@/scripts/warbird/fib-engine";
import { REGIME_START_ISO, WARBIRD_DEFAULT_SYMBOL } from "@/lib/warbird/constants";
import type { CandleData } from "@/lib/types";
import type { WarbirdBias } from "@/lib/warbird/types";

type OhlcvRow = {
  ts: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
  symbol_code?: string;
};

type EconRow = {
  ts: string;
  series_id: string;
  value: number;
};

type CalendarRow = {
  ts: string;
  category: string | null;
  importance: number;
};

type NewsSignalRow = {
  ts: string;
  direction: string | null;
  confidence: number | null;
};

type SetupRow = {
  ts: string;
  counter_trend: boolean;
};

const FRED_TABLES = [
  "econ_rates_1d",
  "econ_yields_1d",
  "econ_fx_1d",
  "econ_vol_1d",
  "econ_inflation_1d",
  "econ_labor_1d",
  "econ_activity_1d",
  "econ_money_1d",
  "econ_commodities_1d",
  "econ_indexes_1d",
] as const;

function createAdminClient() {
  const url = process.env.NEXT_PUBLIC_SUPABASE_URL ?? process.env.SUPABASE_URL;
  const key = process.env.SUPABASE_SERVICE_ROLE_KEY;
  if (!url || !key) {
    throw new Error("Missing Supabase environment variables");
  }
  return createClient(url, key, { auth: { persistSession: false } });
}

async function fetchAll<T>(table: string, select = "*", filters: Record<string, string> = {}): Promise<T[]> {
  const supabase = createAdminClient();
  const pageSize = 1000;
  let offset = 0;
  const rows: T[] = [];

  while (true) {
    let query = supabase.from(table).select(select).range(offset, offset + pageSize - 1);
    for (const [key, value] of Object.entries(filters)) {
      query = query.eq(key, value);
    }
    const { data, error } = await query;
    if (error) throw new Error(`${table}: ${error.message}`);
    if (!data || data.length === 0) break;
    rows.push(...(data as T[]));
    if (data.length < pageSize) break;
    offset += pageSize;
  }

  return rows;
}

function toCandle(row: OhlcvRow): CandleData {
  return {
    time: Math.floor(new Date(row.ts).getTime() / 1000),
    open: Number(row.open),
    high: Number(row.high),
    low: Number(row.low),
    close: Number(row.close),
    volume: Number(row.volume),
  };
}

function ema(values: number[], length: number): Array<number | null> {
  const result: Array<number | null> = [];
  const multiplier = 2 / (length + 1);
  let prev: number | null = null;
  for (const value of values) {
    prev = prev == null ? value : (value - prev) * multiplier + prev;
    result.push(prev);
  }
  return result;
}

function rsi(values: number[], length: number): Array<number | null> {
  const result: Array<number | null> = Array(values.length).fill(null);
  let gains = 0;
  let losses = 0;
  for (let index = 1; index < values.length; index += 1) {
    const change = values[index] - values[index - 1];
    if (index <= length) {
      gains += Math.max(change, 0);
      losses += Math.max(-change, 0);
      if (index === length) {
        const rs = losses === 0 ? 100 : gains / losses;
        result[index] = 100 - 100 / (1 + rs);
      }
      continue;
    }

    gains = ((gains * (length - 1)) + Math.max(change, 0)) / length;
    losses = ((losses * (length - 1)) + Math.max(-change, 0)) / length;
    const rs = losses === 0 ? 100 : gains / losses;
    result[index] = 100 - 100 / (1 + rs);
  }
  return result;
}

function rollingMean(values: number[], length: number): Array<number | null> {
  const result: Array<number | null> = Array(values.length).fill(null);
  let running = 0;
  for (let index = 0; index < values.length; index += 1) {
    running += values[index];
    if (index >= length) running -= values[index - length];
    if (index >= length - 1) result[index] = running / length;
  }
  return result;
}

function rollingStd(values: number[], length: number): Array<number | null> {
  const result: Array<number | null> = Array(values.length).fill(null);
  for (let index = length - 1; index < values.length; index += 1) {
    const slice = values.slice(index - length + 1, index + 1);
    const mean = slice.reduce((sum, value) => sum + value, 0) / slice.length;
    const variance =
      slice.reduce((sum, value) => sum + (value - mean) ** 2, 0) / slice.length;
    result[index] = Math.sqrt(variance);
  }
  return result;
}

function percentageChange(values: number[], lag: number): Array<number | null> {
  return values.map((value, index) => {
    if (index < lag) return null;
    const prior = values[index - lag];
    return prior === 0 ? null : ((value - prior) / prior) * 100;
  });
}

function percentileRank(values: number[], length: number): Array<number | null> {
  const result: Array<number | null> = Array(values.length).fill(null);
  for (let index = length - 1; index < values.length; index += 1) {
    const slice = values.slice(index - length + 1, index + 1).sort((a, b) => a - b);
    const current = values[index];
    const rank = slice.findIndex((value) => value >= current);
    result[index] = rank >= 0 ? rank / slice.length : 1;
  }
  return result;
}

function rollingCorrelation(
  xValues: number[],
  yValues: number[],
  window: number,
): Array<number | null> {
  const result: Array<number | null> = Array(xValues.length).fill(null);
  for (let i = window - 1; i < xValues.length; i++) {
    const xSlice = xValues.slice(i - window + 1, i + 1);
    const ySlice = yValues.slice(i - window + 1, i + 1);
    const xMean = xSlice.reduce((s, v) => s + v, 0) / window;
    const yMean = ySlice.reduce((s, v) => s + v, 0) / window;
    let num = 0, xDen = 0, yDen = 0;
    for (let j = 0; j < window; j++) {
      const dx = xSlice[j] - xMean;
      const dy = ySlice[j] - yMean;
      num += dx * dy;
      xDen += dx * dx;
      yDen += dy * dy;
    }
    const denom = Math.sqrt(xDen * yDen);
    result[i] = denom === 0 ? null : num / denom;
  }
  return result;
}

function computeTargets(
  bars: OhlcvRow[],
  startIndex: number,
  entry: number,
  stopLoss: number,
  tp1: number,
  tp2: number,
  direction: "LONG" | "SHORT",
): {
  reached_tp1: number;
  reached_tp2: number;
  setup_stopped: number;
  hit_sl_first: number;
  hit_pt1_first: number;
  hit_pt2_after_pt1: number;
  max_extension_reached: number;
  max_favorable_excursion: number;
  max_adverse_excursion: number;
} {
  let reachedTp1 = 0;
  let reachedTp2 = 0;
  let setupStopped = 0;
  let maxFav = 0;
  let maxAdv = 0;
  let firstOutcome: "SL" | "PT1" | "PT2" | null = null;
  const tp1Distance = Math.abs(tp1 - entry);
  const tp2Distance = Math.abs(tp2 - entry);
  const extension2Distance =
    tp2Distance > 0 ? tp2Distance * (2 / 1.618) : tp1Distance * (2 / 1.236);

  for (let i = startIndex + 1; i < bars.length && i < startIndex + 100; i++) {
    const bar = bars[i];
    const high = Number(bar.high);
    const low = Number(bar.low);

    if (direction === "LONG") {
      const stopHit = low <= stopLoss;
      const tp1Hit = high >= tp1;
      const tp2Hit = high >= tp2;
      const fav = high - entry;
      const adv = entry - low;
      maxFav = Math.max(maxFav, fav);
      maxAdv = Math.max(maxAdv, adv);

      if (firstOutcome == null) {
        if (stopHit && !tp1Hit && !tp2Hit) firstOutcome = "SL";
        else if ((tp1Hit || tp2Hit) && !stopHit) firstOutcome = tp2Hit ? "PT2" : "PT1";
        else if (stopHit && (tp1Hit || tp2Hit)) firstOutcome = "SL";
      }

      if (stopHit) {
        setupStopped = 1;
        break;
      }
      if (tp2Hit) {
        reachedTp2 = 1;
        reachedTp1 = 1;
        break;
      }
      if (tp1Hit) {
        reachedTp1 = 1;
      }
    } else {
      const stopHit = high >= stopLoss;
      const tp1Hit = low <= tp1;
      const tp2Hit = low <= tp2;
      const fav = entry - low;
      const adv = high - entry;
      maxFav = Math.max(maxFav, fav);
      maxAdv = Math.max(maxAdv, adv);

      if (firstOutcome == null) {
        if (stopHit && !tp1Hit && !tp2Hit) firstOutcome = "SL";
        else if ((tp1Hit || tp2Hit) && !stopHit) firstOutcome = tp2Hit ? "PT2" : "PT1";
        else if (stopHit && (tp1Hit || tp2Hit)) firstOutcome = "SL";
      }

      if (stopHit) {
        setupStopped = 1;
        break;
      }
      if (tp2Hit) {
        reachedTp2 = 1;
        reachedTp1 = 1;
        break;
      }
      if (tp1Hit) {
        reachedTp1 = 1;
      }
    }
  }

  const maxExtensionReached =
    maxFav >= extension2Distance
      ? 2.0
      : maxFav >= tp2Distance
        ? 1.618
        : maxFav >= tp1Distance
          ? 1.236
          : 1.0;

  return {
    reached_tp1: reachedTp1,
    reached_tp2: reachedTp2,
    setup_stopped: setupStopped,
    hit_sl_first: firstOutcome === "SL" ? 1 : 0,
    hit_pt1_first: firstOutcome === "PT1" || firstOutcome === "PT2" ? 1 : 0,
    hit_pt2_after_pt1: reachedTp2,
    max_extension_reached: maxExtensionReached,
    max_favorable_excursion: maxFav,
    max_adverse_excursion: maxAdv,
  };
}

function chicagoParts(date: Date) {
  const formatter = new Intl.DateTimeFormat("en-US", {
    timeZone: "America/Chicago",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });
  const parts = formatter.formatToParts(date);
  const read = (type: Intl.DateTimeFormatPartTypes) =>
    Number(parts.find((part) => part.type === type)?.value ?? "0");
  return {
    hour: read("hour"),
    month: read("month"),
    day: read("day"),
  };
}

function csvEscape(value: unknown): string {
  if (value == null) return "";
  const stringValue = String(value);
  if (stringValue.includes(",") || stringValue.includes('"') || stringValue.includes("\n")) {
    return `"${stringValue.replaceAll('"', '""')}"`;
  }
  return stringValue;
}

async function buildDataset(outputPath: string) {
  const [mes15mRows, mes1dRows, crossAssetRows, calendarRows, newsRows, gprRows, trumpRows, setups] =
    await Promise.all([
      fetchAll<OhlcvRow>("mes_15m"),
      fetchAll<OhlcvRow>("mes_1d"),
      fetchAll<OhlcvRow>("cross_asset_1h"),
      fetchAll<CalendarRow>("econ_calendar"),
      fetchAll<NewsSignalRow>("news_signals"),
      fetchAll<{ ts: string; series_id: string; value: number }>("geopolitical_risk_1d"),
      fetchAll<{ ts: string; event_type: string }>("trump_effect_1d"),
      fetchAll<SetupRow>("warbird_setups"),
    ]);

  const fredBySeries = new Map<string, Array<{ ts: string; value: number }>>();
  for (const table of FRED_TABLES) {
    const rows = await fetchAll<EconRow>(table);
    for (const row of rows) {
      const seriesRows = fredBySeries.get(row.series_id) ?? [];
      seriesRows.push({ ts: row.ts, value: Number(row.value) });
      fredBySeries.set(row.series_id, seriesRows);
    }
  }

  const ordered15m = [...mes15mRows]
    .filter((row) => new Date(row.ts) >= new Date("2024-01-01T00:00:00Z"))
    .sort((a, b) => new Date(a.ts).getTime() - new Date(b.ts).getTime());
  const ordered1d = [...mes1dRows].sort(
    (a, b) => new Date(a.ts).getTime() - new Date(b.ts).getTime(),
  );

  const closes = ordered15m.map((row) => Number(row.close));
  const highs = ordered15m.map((row) => Number(row.high));
  const lows = ordered15m.map((row) => Number(row.low));
  const opens = ordered15m.map((row) => Number(row.open));
  const volumes = ordered15m.map((row) => Number(row.volume));
  const ranges = highs.map((high, index) => high - lows[index]);
  const trueRanges = ranges.map((range, index) =>
    Math.max(
      range,
      index > 0 ? Math.abs(highs[index] - closes[index - 1]) : range,
      index > 0 ? Math.abs(lows[index] - closes[index - 1]) : range,
    ),
  );
  const BARS_PER_HOUR = 4;
  const BARS_PER_4H = 16;
  const BARS_PER_DAY = 96;
  const bodyRatios = ranges.map((range, index) =>
    range === 0 ? null : Math.abs(closes[index] - opens[index]) / range,
  );
  const ema21 = ema(closes, 21);
  const ema50 = ema(closes, 50);
  const ema200 = ema(closes, 200);
  const rsi14 = rsi(closes, 14);
  const returns1h = percentageChange(closes, BARS_PER_HOUR);
  const returns4h = percentageChange(closes, BARS_PER_4H);
  const returns1d = percentageChange(closes, BARS_PER_DAY);
  const rollingStd20 = rollingStd(closes, 20);
  const rollingStd50 = rollingStd(closes, 50);
  const volumeMean5 = rollingMean(volumes, 5);
  const volumeMean20 = rollingMean(volumes, 20);
  const atr1h = rollingMean(trueRanges, BARS_PER_HOUR);

  const dailyFeatures = ordered1d.map((_, index) =>
    buildDailyBiasLayer(
      ordered1d.slice(0, index + 1).map((row) => ({
        time: Math.floor(new Date(row.ts).getTime() / 1000),
        open: Number(row.open),
        high: Number(row.high),
        low: Number(row.low),
        close: Number(row.close),
        volume: Number(row.volume),
      })),
      WARBIRD_DEFAULT_SYMBOL,
    ),
  );

  const sampleWeight = ordered15m.map((row) => {
    const totalSpan = Date.now() - new Date("2024-01-01T00:00:00Z").getTime();
    const age = Date.now() - new Date(row.ts).getTime();
    const progress = 1 - age / totalSpan;
    return 0.3 + Math.max(0, Math.min(1, progress)) * 0.7;
  });

  // Pre-compute cross-asset data structures
  const crossBySymbol = new Map<string, OhlcvRow[]>();
  for (const row of crossAssetRows) {
    const list = crossBySymbol.get(row.symbol_code ?? "") ?? [];
    list.push(row);
    crossBySymbol.set(row.symbol_code ?? "", list);
  }
  for (const list of crossBySymbol.values()) {
    list.sort((a, b) => new Date(a.ts).getTime() - new Date(b.ts).getTime());
  }

  const crossSymbols = [...new Set(crossAssetRows.map((row) => row.symbol_code).filter(Boolean))] as string[];

  // Pre-compute MES 15m closes for correlation
  const mesCloses = ordered15m.map((r) => Number(r.close));

  // Pre-compute rolling correlations for all cross-asset symbols
  const corrMap = new Map<string, { c20: (number | null)[]; c60: (number | null)[] }>();
  for (const symbol of crossSymbols) {
    const symbolBars = crossBySymbol.get(symbol) ?? [];
    const symbolCloses = ordered15m.map((bar) => {
      const tsMs = new Date(bar.ts).getTime();
      const match = [...symbolBars]
        .filter((sb) => new Date(sb.ts).getTime() <= tsMs)
        .sort((a, b) => new Date(b.ts).getTime() - new Date(a.ts).getTime())[0];
      return match ? Number(match.close) : null;
    });
    let last = symbolCloses.find((v) => v !== null) ?? 0;
    const filled = symbolCloses.map((v) => { if (v !== null) last = v; return last; });
    corrMap.set(symbol, {
      c20: rollingCorrelation(mesCloses, filled, 20),
      c60: rollingCorrelation(mesCloses, filled, 60),
    });
  }

  // Build header
  const header = [
    "timestamp",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "range",
    "body_ratio",
    "returns_1h",
    "returns_4h",
    "returns_1d",
    "rsi_14",
    "ema_21",
    "ema_50",
    "ema_200",
    "dist_ema_21",
    "dist_ema_50",
    "dist_ema_200",
    "rolling_std_20",
    "rolling_std_50",
    "vol_ratio_5_20",
    "atr_1h",
    "daily_bias",
    "price_vs_200d_ma",
    "distance_from_200d_ma_pct",
    "slope_200d_ma",
    "sessions_above_below_200d",
    "daily_ret",
    "daily_range_vs_avg",
    "hour_utc",
    "day_of_week",
    "session_us",
    "session_eu",
    "session_asia",
    "month",
    "days_into_regime",
    "regime_label",
    "gpr_level",
    "trump_events_7d",
    "news_layers_24h",
    "news_net_sentiment_24h",
    "hours_to_next_high_impact",
    "high_impact_today",
    "setup_frequency_7d",
    "counter_trend_recent_20",
    "fib_level",
    "fib_quality",
    "fib_confluence_score",
    "measured_move_present",
    "measured_move_quality",
    "direction",
    "entry_price",
    "stop_loss",
    "tp1_price",
    "tp2_price",
    "stop_distance",
    "tp1_distance",
    "tp2_distance",
    "geometry_status",
  ];

  for (const seriesId of [...fredBySeries.keys()].sort()) {
    header.push(`fred_${seriesId.toLowerCase()}`);
    header.push(`fred_${seriesId.toLowerCase()}_pct_5`);
    header.push(`fred_${seriesId.toLowerCase()}_pctile_20`);
  }

  for (const symbol of crossSymbols) {
    header.push(`ca_${symbol.toLowerCase()}_close`);
    header.push(`ca_${symbol.toLowerCase()}_ret_1h`);
    header.push(`corr_${symbol.toLowerCase()}_20`);
    header.push(`corr_${symbol.toLowerCase()}_60`);
  }

  header.push(
    "reached_tp1",
    "reached_tp2",
    "setup_stopped",
    "hit_sl_first",
    "hit_pt1_first",
    "hit_pt2_after_pt1",
    "max_extension_reached",
    "max_favorable_excursion",
    "max_adverse_excursion",
    "sample_weight",
  );

  const lines: string[] = [];
  lines.push(header.join(","));

  const fredState = new Map<string, number>();
  const fredIndex = new Map<string, number>();
  for (const [seriesId, rows] of fredBySeries.entries()) {
    rows.sort((a, b) => new Date(a.ts).getTime() - new Date(b.ts).getTime());
    fredIndex.set(seriesId, 0);
  }

  // Main loop: only rows where fib geometry fires
  const MIN_LOOKBACK = 55;
  let setupCount = 0;

  for (let index = MIN_LOOKBACK; index < ordered15m.length; index++) {
    const row = ordered15m[index];
    const tsMs = new Date(row.ts).getTime();
    const tsDate = new Date(row.ts);
    const dailyIndex = ordered1d.findLastIndex((daily) => new Date(daily.ts).getTime() <= tsMs);
    const dailyFeature = dailyIndex >= 0 ? dailyFeatures[dailyIndex] : null;
    const currentBias = (dailyFeature?.bias ?? "NEUTRAL") as WarbirdBias;

    // Build fib geometry — skip bars where no setup fires
    const candles = ordered15m.slice(0, index + 1).map(toCandle);
    const geometry = buildFibGeometry(candles, currentBias);
    if (!geometry) continue;

    // Need enough future bars for target computation
    if (index + 10 >= ordered15m.length) continue;

    // Forward-scan targets
    const targets = computeTargets(
      ordered15m,
      index,
      geometry.entry,
      geometry.stopLoss,
      geometry.tp1,
      geometry.tp2,
      geometry.direction,
    );

    const chicago = chicagoParts(tsDate);

    const nextHighImpact = calendarRows
      .filter((event) => event.importance >= 3 && new Date(event.ts).getTime() >= tsMs)
      .sort((a, b) => new Date(a.ts).getTime() - new Date(b.ts).getTime())[0];
    const highImpactToday = calendarRows.some((event) => {
      const eventDate = new Date(event.ts);
      return (
        event.importance >= 3 &&
        eventDate.getUTCFullYear() === tsDate.getUTCFullYear() &&
        eventDate.getUTCMonth() === tsDate.getUTCMonth() &&
        eventDate.getUTCDate() === tsDate.getUTCDate()
      );
    });

    const news24h = newsRows.filter((news) => {
      const delta = tsMs - new Date(news.ts).getTime();
      return delta >= 0 && delta <= 24 * 60 * 60 * 1000;
    });

    const setups20 = setups
      .filter((setup) => new Date(setup.ts).getTime() <= tsMs)
      .slice(-20);
    const setups7d = setups.filter((setup) => {
      const delta = tsMs - new Date(setup.ts).getTime();
      return delta >= 0 && delta <= 7 * 24 * 60 * 60 * 1000;
    });

    const gpr = [...gprRows]
      .filter((gprRow) => new Date(gprRow.ts).getTime() <= tsMs)
      .sort((a, b) => new Date(b.ts).getTime() - new Date(a.ts).getTime())[0];

    const trumpEvents7d = trumpRows.filter((event) => {
      const delta = tsMs - new Date(event.ts).getTime();
      return delta >= 0 && delta <= 7 * 24 * 60 * 60 * 1000;
    }).length;

    const baseRow: Record<string, unknown> = {
      timestamp: row.ts,
      open: row.open,
      high: row.high,
      low: row.low,
      close: row.close,
      volume: row.volume,
      range: ranges[index],
      body_ratio: bodyRatios[index],
      returns_1h: returns1h[index],
      returns_4h: returns4h[index],
      returns_1d: returns1d[index],
      rsi_14: rsi14[index],
      ema_21: ema21[index],
      ema_50: ema50[index],
      ema_200: ema200[index],
      dist_ema_21: ema21[index] ? row.close - (ema21[index] as number) : null,
      dist_ema_50: ema50[index] ? row.close - (ema50[index] as number) : null,
      dist_ema_200: ema200[index] ? row.close - (ema200[index] as number) : null,
      rolling_std_20: rollingStd20[index],
      rolling_std_50: rollingStd50[index],
      vol_ratio_5_20:
        volumeMean5[index] && volumeMean20[index]
          ? (volumeMean5[index] as number) / (volumeMean20[index] as number)
          : null,
      atr_1h: atr1h[index],
      daily_bias: dailyFeature?.bias ?? "NEUTRAL",
      price_vs_200d_ma: dailyFeature?.price_vs_200d_ma ?? null,
      distance_from_200d_ma_pct: dailyFeature?.distance_pct ?? null,
      slope_200d_ma: dailyFeature?.slope_200d_ma ?? null,
      sessions_above_below_200d: dailyFeature?.sessions_on_side ?? null,
      daily_ret: dailyFeature?.daily_return ?? null,
      daily_range_vs_avg: dailyFeature?.daily_range_vs_avg ?? null,
      hour_utc: tsDate.getUTCHours(),
      day_of_week: tsDate.getUTCDay(),
      session_us: chicago.hour >= 8 && chicago.hour <= 15 ? 1 : 0,
      session_eu: chicago.hour >= 2 && chicago.hour <= 7 ? 1 : 0,
      session_asia: chicago.hour >= 18 || chicago.hour <= 1 ? 1 : 0,
      month: chicago.month,
      days_into_regime: Math.max(
        0,
        Math.floor((tsMs - new Date(REGIME_START_ISO).getTime()) / (24 * 60 * 60 * 1000)),
      ),
      regime_label: "trump_2",
      gpr_level: gpr?.value ?? null,
      trump_events_7d: trumpEvents7d,
      news_layers_24h: news24h.length,
      news_net_sentiment_24h: news24h.reduce((sum, news) => {
        if (news.direction === "LONG") return sum + Number(news.confidence ?? 0);
        if (news.direction === "SHORT") return sum - Number(news.confidence ?? 0);
        return sum;
      }, 0),
      hours_to_next_high_impact: nextHighImpact
        ? (new Date(nextHighImpact.ts).getTime() - tsMs) / (60 * 60 * 1000)
        : null,
      high_impact_today: highImpactToday ? 1 : 0,
      setup_frequency_7d: setups7d.length,
      counter_trend_recent_20: setups20.filter((setup) => setup.counter_trend).length,
      fib_level: geometry.fibLevel,
      fib_quality: geometry.quality,
      fib_confluence_score: null,
      measured_move_present: geometry.measuredMove ? 1 : 0,
      measured_move_quality: geometry.measuredMove ? geometry.quality : null,
      direction: geometry.direction,
      entry_price: geometry.entry,
      stop_loss: geometry.stopLoss,
      tp1_price: geometry.tp1,
      tp2_price: geometry.tp2,
      stop_distance: Math.abs(geometry.entry - geometry.stopLoss),
      tp1_distance: Math.abs(geometry.tp1 - geometry.entry),
      tp2_distance: Math.abs(geometry.tp2 - geometry.entry),
      geometry_status: "current",
      ...targets,
      sample_weight: sampleWeight[index],
    };

    // FRED features with forward-fill
    for (const [seriesId, seriesRows] of fredBySeries.entries()) {
      let pointer = fredIndex.get(seriesId) ?? 0;
      while (
        pointer < seriesRows.length &&
        new Date(seriesRows[pointer].ts).getTime() <= tsMs
      ) {
        fredState.set(seriesId, seriesRows[pointer].value);
        pointer += 1;
      }
      fredIndex.set(seriesId, pointer);
      const current = fredState.get(seriesId) ?? null;
      const seriesName = `fred_${seriesId.toLowerCase()}`;
      baseRow[seriesName] = current;
    }

    for (const key of Object.keys(baseRow)) {
      if (!key.startsWith("fred_")) continue;
      const columnValues = lines.length > 1
        ? lines.slice(1).map((line) => {
            const values = line.split(",");
            const columnIndex = header.indexOf(key);
            return Number(values[columnIndex] || "NaN");
          }).filter((value) => Number.isFinite(value))
        : [];
      const current = typeof baseRow[key] === "number" ? Number(baseRow[key]) : null;
      baseRow[`${key}_pct_5`] =
        current != null && columnValues.length >= 5
          ? percentageChange([...columnValues, current], 5).at(-1) ?? null
          : null;
      baseRow[`${key}_pctile_20`] =
        current != null && columnValues.length >= 20
          ? percentileRank([...columnValues, current], 20).at(-1) ?? null
          : null;
    }

    // Cross-asset features + correlations
    for (const symbol of crossSymbols) {
      const caRows = crossBySymbol.get(symbol) ?? [];
      const latest = [...caRows]
        .filter((item) => new Date(item.ts).getTime() <= tsMs)
        .sort((a, b) => new Date(b.ts).getTime() - new Date(a.ts).getTime())[0];
      const previous = [...caRows]
        .filter((item) => new Date(item.ts).getTime() < tsMs)
        .sort((a, b) => new Date(b.ts).getTime() - new Date(a.ts).getTime())[0];
      baseRow[`ca_${symbol.toLowerCase()}_close`] = latest?.close ?? null;
      baseRow[`ca_${symbol.toLowerCase()}_ret_1h`] =
        latest && previous && Number(previous.close) !== 0
          ? ((Number(latest.close) - Number(previous.close)) / Number(previous.close)) * 100
          : null;
      const corr = corrMap.get(symbol);
      baseRow[`corr_${symbol.toLowerCase()}_20`] = corr?.c20[index] ?? null;
      baseRow[`corr_${symbol.toLowerCase()}_60`] = corr?.c60[index] ?? null;
    }

    lines.push(header.map((column) => csvEscape(baseRow[column])).join(","));
    setupCount++;

    if (setupCount % 100 === 0) {
      console.log(`  ${setupCount} setup rows emitted (at bar ${index}/${ordered15m.length})`);
    }
  }

  await writeFile(outputPath, `${lines.join("\n")}\n`, "utf8");
  console.log(`Wrote ${setupCount} setup rows to ${outputPath}`);
}

async function main() {
  const outputArgIndex = process.argv.indexOf("--output");
  const outputPath =
    outputArgIndex >= 0 && process.argv[outputArgIndex + 1]
      ? process.argv[outputArgIndex + 1]
      : "data/warbird-dataset.csv";

  await buildDataset(outputPath);
}

void main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
