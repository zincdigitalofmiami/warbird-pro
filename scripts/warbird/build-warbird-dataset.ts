import { writeFile } from "node:fs/promises";
import { createClient } from "@supabase/supabase-js";
import { buildDailyBiasLayer } from "@/scripts/warbird/daily-layer";
import { REGIME_START_ISO, WARBIRD_DEFAULT_SYMBOL } from "@/lib/warbird/constants";

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

type MacroReportRow = {
  ts: string;
  report_type: string;
  surprise: number | null;
};

type SetupRow = {
  ts: string;
  counter_trend: boolean;
  runner_eligible: boolean;
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
  const [mes1hRows, mes1dRows, crossAssetRows, calendarRows, newsRows, macroRows, gprRows, trumpRows, setups] =
    await Promise.all([
      fetchAll<OhlcvRow>("mes_1h"),
      fetchAll<OhlcvRow>("mes_1d"),
      fetchAll<OhlcvRow>("cross_asset_1h"),
      fetchAll<CalendarRow>("econ_calendar"),
      fetchAll<NewsSignalRow>("news_signals"),
      fetchAll<MacroReportRow>("macro_reports_1d"),
      fetchAll<{ ts: string; gpr_daily: number }>("geopolitical_risk_1d"),
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

  const ordered1h = [...mes1hRows]
    .filter((row) => new Date(row.ts) >= new Date("2024-01-01T00:00:00Z"))
    .sort((a, b) => new Date(a.ts).getTime() - new Date(b.ts).getTime());
  const ordered1d = [...mes1dRows].sort(
    (a, b) => new Date(a.ts).getTime() - new Date(b.ts).getTime(),
  );

  const closes = ordered1h.map((row) => Number(row.close));
  const highs = ordered1h.map((row) => Number(row.high));
  const lows = ordered1h.map((row) => Number(row.low));
  const opens = ordered1h.map((row) => Number(row.open));
  const volumes = ordered1h.map((row) => Number(row.volume));
  const ranges = highs.map((high, index) => high - lows[index]);
  const bodyRatios = ranges.map((range, index) =>
    range === 0 ? null : Math.abs(closes[index] - opens[index]) / range,
  );
  const ema21 = ema(closes, 21);
  const ema50 = ema(closes, 50);
  const ema200 = ema(closes, 200);
  const rsi14 = rsi(closes, 14);
  const returns1h = percentageChange(closes, 1);
  const returns4h = percentageChange(closes, 4);
  const returns1d = percentageChange(closes, 24);
  const rollingStd20 = rollingStd(closes, 20);
  const rollingStd50 = rollingStd(closes, 50);
  const volumeMean5 = rollingMean(volumes, 5);
  const volumeMean20 = rollingMean(volumes, 20);
  const rangeMean20 = rollingMean(ranges, 20);

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

  const sampleWeight = ordered1h.map((row) => {
    const totalSpan = Date.now() - new Date("2024-01-01T00:00:00Z").getTime();
    const age = Date.now() - new Date(row.ts).getTime();
    const progress = 1 - age / totalSpan;
    return 0.3 + Math.max(0, Math.min(1, progress)) * 0.7;
  });

  const lines: string[] = [];
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
    "runner_eligible_recent_20",
    "target_price_1h",
    "target_price_4h",
    "target_mae_1h",
    "target_mae_4h",
    "target_mfe_1h",
    "target_mfe_4h",
    "sample_weight",
  ];

  for (const seriesId of [...fredBySeries.keys()].sort()) {
    header.push(`fred_${seriesId.toLowerCase()}`);
    header.push(`fred_${seriesId.toLowerCase()}_pct_5`);
    header.push(`fred_${seriesId.toLowerCase()}_pctile_20`);
  }

  const crossSymbols = [...new Set(crossAssetRows.map((row) => row.symbol_code).filter(Boolean))] as string[];
  for (const symbol of crossSymbols) {
    header.push(`ca_${symbol.toLowerCase()}_close`);
    header.push(`ca_${symbol.toLowerCase()}_ret_1h`);
  }

  lines.push(header.join(","));

  const fredState = new Map<string, number>();
  const fredIndex = new Map<string, number>();
  for (const [seriesId, rows] of fredBySeries.entries()) {
    rows.sort((a, b) => new Date(a.ts).getTime() - new Date(b.ts).getTime());
    fredIndex.set(seriesId, 0);
  }

  const crossBySymbol = new Map<string, OhlcvRow[]>();
  for (const row of crossAssetRows) {
    const list = crossBySymbol.get(row.symbol_code ?? "") ?? [];
    list.push(row);
    crossBySymbol.set(row.symbol_code ?? "", list);
  }
  for (const list of crossBySymbol.values()) {
    list.sort((a, b) => new Date(a.ts).getTime() - new Date(b.ts).getTime());
  }

  for (let index = 0; index < ordered1h.length; index += 1) {
    const row = ordered1h[index];
    const tsMs = new Date(row.ts).getTime();
    const tsDate = new Date(row.ts);
    const chicago = chicagoParts(tsDate);
    const dailyIndex = ordered1d.findLastIndex((daily) => new Date(daily.ts).getTime() <= tsMs);
    const dailyFeature = dailyIndex >= 0 ? dailyFeatures[dailyIndex] : null;

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
      gpr_level: gpr?.gpr_daily ?? null,
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
      runner_eligible_recent_20: setups20.filter((setup) => setup.runner_eligible).length,
      target_price_1h: ordered1h[index + 1]?.close ?? null,
      target_price_4h: ordered1h[index + 4]?.close ?? null,
      target_mae_1h:
        index + 1 < ordered1h.length
          ? Math.max(0, row.close - Math.min(...ordered1h.slice(index + 1, index + 2).map((item) => Number(item.low))))
          : null,
      target_mae_4h:
        index + 4 < ordered1h.length
          ? Math.max(0, row.close - Math.min(...ordered1h.slice(index + 1, index + 5).map((item) => Number(item.low))))
          : null,
      target_mfe_1h:
        index + 1 < ordered1h.length
          ? Math.max(0, Math.max(...ordered1h.slice(index + 1, index + 2).map((item) => Number(item.high))) - row.close)
          : null,
      target_mfe_4h:
        index + 4 < ordered1h.length
          ? Math.max(0, Math.max(...ordered1h.slice(index + 1, index + 5).map((item) => Number(item.high))) - row.close)
          : null,
      sample_weight: sampleWeight[index],
    };

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

    for (const symbol of crossSymbols) {
      const rows = crossBySymbol.get(symbol) ?? [];
      const latest = [...rows]
        .filter((item) => new Date(item.ts).getTime() <= tsMs)
        .sort((a, b) => new Date(b.ts).getTime() - new Date(a.ts).getTime())[0];
      const previous = [...rows]
        .filter((item) => new Date(item.ts).getTime() < tsMs)
        .sort((a, b) => new Date(b.ts).getTime() - new Date(a.ts).getTime())[0];
      baseRow[`ca_${symbol.toLowerCase()}_close`] = latest?.close ?? null;
      baseRow[`ca_${symbol.toLowerCase()}_ret_1h`] =
        latest && previous && Number(previous.close) !== 0
          ? ((Number(latest.close) - Number(previous.close)) / Number(previous.close)) * 100
          : null;
    }

    lines.push(header.map((column) => csvEscape(baseRow[column])).join(","));
  }

  await writeFile(outputPath, `${lines.join("\n")}\n`, "utf8");
  console.log(`Wrote ${ordered1h.length} rows to ${outputPath}`);
}

async function main() {
  const outputArgIndex = process.argv.indexOf("--output");
  const outputPath =
    outputArgIndex >= 0 && process.argv[outputArgIndex + 1]
      ? process.argv[outputArgIndex + 1]
      : "datasets/warbird_dataset_1h.csv";

  await buildDataset(outputPath);
}

void main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
