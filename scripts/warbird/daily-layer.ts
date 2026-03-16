import type { CandleData } from "@/lib/types";
import type { WarbirdBias, WarbirdDailyBiasRow } from "@/lib/warbird/types";
import { WARBIRD_DEFAULT_SYMBOL } from "@/lib/warbird/constants";

function sma(values: number[], length: number): number | null {
  if (values.length === 0) return null;
  const slice = values.slice(-Math.min(length, values.length));
  if (slice.length === 0) return null;
  return slice.reduce((sum, value) => sum + value, 0) / slice.length;
}

function slope(values: number[], length: number): number | null {
  const slice = values.slice(-Math.min(length, values.length));
  if (slice.length < 2) return null;
  return slice[slice.length - 1] - slice[0];
}

export function inferDailyBias(close: number, ma200: number | null): WarbirdBias {
  if (ma200 == null || !Number.isFinite(ma200)) return "NEUTRAL";
  if (close > ma200) return "BULL";
  if (close < ma200) return "BEAR";
  return "NEUTRAL";
}

export function buildDailyBiasLayer(
  candles: CandleData[],
  symbolCode: string = WARBIRD_DEFAULT_SYMBOL,
): WarbirdDailyBiasRow | null {
  if (candles.length === 0) return null;

  const ordered = [...candles].sort((a, b) => a.time - b.time);
  const closes = ordered.map((candle) => candle.close);
  const highs = ordered.map((candle) => candle.high);
  const lows = ordered.map((candle) => candle.low);

  const last = ordered[ordered.length - 1];
  const ma200 = sma(closes, 200);
  const currentBias = inferDailyBias(last.close, ma200);
  const previousDailyClose = ordered.length > 1 ? ordered[ordered.length - 2].close : last.close;
  const rollingRangeAverage = sma(
    ordered.map((candle) => candle.high - candle.low),
    20,
  );

  let sessionsOnSide = 0;
  for (let index = ordered.length - 1; index >= 0; index -= 1) {
    const bias = inferDailyBias(ordered[index].close, ma200);
    if (bias !== currentBias) break;
    sessionsOnSide += 1;
  }

  return {
    ts: new Date(last.time * 1000).toISOString(),
    symbol_code: symbolCode,
    bias: currentBias,
    close_price: last.close,
    ma_200: ma200,
    price_vs_200d_ma: ma200 != null ? last.close - ma200 : null,
    distance_pct: ma200 != null && ma200 !== 0 ? ((last.close - ma200) / ma200) * 100 : null,
    slope_200d_ma: slope(closes, 20),
    sessions_on_side: currentBias === "NEUTRAL" ? 0 : sessionsOnSide,
    daily_return: previousDailyClose !== 0 ? ((last.close - previousDailyClose) / previousDailyClose) * 100 : null,
    daily_range_vs_avg:
      rollingRangeAverage != null && rollingRangeAverage !== 0
        ? ((highs[highs.length - 1] - lows[lows.length - 1]) / rollingRangeAverage) * 100
        : null,
  };
}
