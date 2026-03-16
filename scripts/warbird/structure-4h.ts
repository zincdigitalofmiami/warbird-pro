import type { CandleData } from "@/lib/types";
import type { WarbirdBias, WarbirdStructure4HRow } from "@/lib/warbird/types";
import { WARBIRD_DEFAULT_SYMBOL } from "@/lib/warbird/constants";

function detectHigherHighsAndLows(candles: CandleData[]) {
  if (candles.length < 4) {
    return { higherHighs: false, higherLows: false, lowerHighs: false, lowerLows: false };
  }

  const recent = candles.slice(-4);
  const highs = recent.map((candle) => candle.high);
  const lows = recent.map((candle) => candle.low);

  return {
    higherHighs: highs[3] >= highs[2] && highs[2] >= highs[1],
    higherLows: lows[3] >= lows[2] && lows[2] >= lows[1],
    lowerHighs: highs[3] <= highs[2] && highs[2] <= highs[1],
    lowerLows: lows[3] <= lows[2] && lows[2] <= lows[1],
  };
}

export function buildStructure4H(
  candles: CandleData[],
  dailyBias: WarbirdBias,
  symbolCode: string = WARBIRD_DEFAULT_SYMBOL,
): WarbirdStructure4HRow | null {
  if (candles.length === 0) return null;

  const ordered = [...candles].sort((a, b) => a.time - b.time);
  const last = ordered[ordered.length - 1];
  const recent = ordered.slice(-8);
  const firstClose = recent[0]?.close ?? last.close;
  const trendScore = last.close - firstClose;
  const structure = detectHigherHighsAndLows(recent);

  let bias4h: WarbirdBias = "NEUTRAL";
  let structuralNote = "range";

  if (structure.higherHighs && structure.higherLows && trendScore > 0) {
    bias4h = "BULL";
    structuralNote = "higher-highs-higher-lows";
  } else if (structure.lowerHighs && structure.lowerLows && trendScore < 0) {
    bias4h = "BEAR";
    structuralNote = "lower-highs-lower-lows";
  } else if (trendScore > 8) {
    bias4h = "BULL";
    structuralNote = "positive-trend-score";
  } else if (trendScore < -8) {
    bias4h = "BEAR";
    structuralNote = "negative-trend-score";
  }

  return {
    ts: new Date(last.time * 1000).toISOString(),
    symbol_code: symbolCode,
    bias_4h: bias4h,
    agrees_with_daily: dailyBias !== "NEUTRAL" && bias4h === dailyBias,
    trend_score: trendScore,
    swing_high: Math.max(...recent.map((candle) => candle.high)),
    swing_low: Math.min(...recent.map((candle) => candle.low)),
    structural_note: structuralNote,
  };
}
