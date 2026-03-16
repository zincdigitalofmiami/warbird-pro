import type { CandleData } from "@/lib/types";
import type {
  WarbirdDirection,
  WarbirdForecastRow,
  WarbirdTriggerDecision,
  WarbirdTriggerRow,
} from "@/lib/warbird/types";
import {
  WARBIRD_DEFAULT_SYMBOL,
  WARBIRD_GO_RATIO,
  WARBIRD_TRIGGER_MIN_RATIO,
} from "@/lib/warbird/constants";
import type { WarbirdFibGeometry } from "@/scripts/warbird/fib-engine";

export interface TriggerInputs {
  candles: CandleData[];
  forecast: WarbirdForecastRow;
  geometry: WarbirdFibGeometry;
  correlationScore?: number | null;
}

function computeStochRsi(candles: CandleData[], length: number = 14): number | null {
  if (candles.length < length) return null;
  const closes = candles.slice(-length).map((candle) => candle.close);
  const min = Math.min(...closes);
  const max = Math.max(...closes);
  const last = closes[closes.length - 1];
  if (max === min) return 50;
  return ((last - min) / (max - min)) * 100;
}

function checkCandleConfirmation(
  candle: CandleData,
  direction: WarbirdDirection,
  level: number,
  entry: number,
): boolean {
  if (direction === "LONG") {
    return candle.low <= level && candle.close >= entry;
  }
  return candle.high >= level && candle.close <= entry;
}

export function evaluateTrigger15m(
  inputs: TriggerInputs,
): Omit<WarbirdTriggerRow, "id"> {
  const { candles, forecast, geometry, correlationScore } = inputs;
  const ordered = [...candles].sort((a, b) => a.time - b.time);
  const last = ordered[ordered.length - 1];
  const prior = ordered.slice(-21, -1);
  const averageVolume =
    prior.length > 0
      ? prior.reduce((sum, candle) => sum + (candle.volume ?? 0), 0) / prior.length
      : 0;
  const volumeRatio = averageVolume > 0 ? (last.volume ?? 0) / averageVolume : 0;
  const triggerQualityRatio =
    forecast.mfe_mae_ratio_1h
    ?? (forecast.target_mae_1h > 0
      ? forecast.target_mfe_1h / forecast.target_mae_1h
      : forecast.target_mfe_1h);
  const stopDistance = Math.abs(geometry.entry - geometry.stopLoss);
  const tp2Distance = Math.abs(geometry.tp2 - geometry.entry);
  const runnerHeadroom = forecast.target_mfe_4h - tp2Distance;
  const candleConfirmed = checkCandleConfirmation(
    last,
    geometry.direction,
    geometry.fibLevel,
    geometry.entry,
  );
  const volumeConfirmation = volumeRatio >= 1.1;
  const maeBlocksTrade = forecast.target_mae_1h > stopDistance;
  const badRatio = triggerQualityRatio < WARBIRD_TRIGGER_MIN_RATIO;

  let decision: WarbirdTriggerDecision = "WAIT";
  let noTradeReason: string | null = null;

  if (maeBlocksTrade) {
    decision = "NO_GO";
    noTradeReason = "mae_exceeds_stop_distance";
  } else if (badRatio) {
    decision = "NO_GO";
    noTradeReason = "mfe_mae_ratio_below_threshold";
  } else if (candleConfirmed && volumeConfirmation && triggerQualityRatio >= WARBIRD_GO_RATIO) {
    decision = "GO";
  }

  return {
    ts: new Date(last.time * 1000).toISOString(),
    forecast_id: forecast.id,
    symbol_code: forecast.symbol_code || WARBIRD_DEFAULT_SYMBOL,
    direction: geometry.direction,
    decision,
    fib_level: geometry.fibLevel,
    fib_ratio: geometry.fibRatio,
    entry_price: geometry.entry,
    stop_loss: geometry.stopLoss,
    tp1: geometry.tp1,
    tp2: geometry.tp2,
    candle_confirmed: candleConfirmed,
    volume_confirmation: volumeConfirmation,
    volume_ratio: volumeRatio,
    stoch_rsi: computeStochRsi(ordered),
    correlation_score: correlationScore ?? null,
    trigger_quality_ratio: triggerQualityRatio,
    runner_headroom: runnerHeadroom,
    no_trade_reason: noTradeReason,
  };
}
