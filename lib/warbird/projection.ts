import {
  REGIME_LABEL,
  WARBIRD_SIGNAL_VERSION,
  getDaysIntoRegime,
} from "@/lib/warbird/constants";
import type {
  WarbirdConvictionRow,
  WarbirdDailyBiasRow,
  WarbirdForecastRow,
  WarbirdRiskRow,
  WarbirdSetupEventRow,
  WarbirdSetupRow,
  WarbirdSignal,
  WarbirdStructure4HRow,
  WarbirdTriggerRow,
} from "@/lib/warbird/types";
import type { ForecastTarget } from "@/lib/charts/types";
import type { SetupCandidate } from "@/lib/setup-candidates";
import TV from "@/lib/colors";

export function composeWarbirdSignal(params: {
  daily: WarbirdDailyBiasRow | null;
  structure: WarbirdStructure4HRow | null;
  forecast: WarbirdForecastRow | null;
  conviction: WarbirdConvictionRow | null;
  risk: WarbirdRiskRow | null;
  setup: WarbirdSetupRow | null;
}): WarbirdSignal | null {
  const { daily, structure, forecast, conviction, risk, setup } = params;
  if (!forecast) return null;

  return {
    version: WARBIRD_SIGNAL_VERSION,
    generatedAt: forecast.ts,
    symbol: forecast.symbol_code,
    daily: {
      bias: daily?.bias ?? "NEUTRAL",
      price_vs_200d_ma: daily?.price_vs_200d_ma ?? null,
      distance_pct: daily?.distance_pct ?? null,
      slope_200d_ma: daily?.slope_200d_ma ?? null,
    },
    structure: {
      bias_4h: structure?.bias_4h ?? "NEUTRAL",
      agrees_with_daily: structure?.agrees_with_daily ?? false,
    },
    directional: {
      bias_1h: forecast.bias_1h,
      price_target_1h: forecast.target_price_1h,
      price_target_4h: forecast.target_price_4h,
      mae_band_1h: forecast.target_mae_1h,
      mae_band_4h: forecast.target_mae_4h,
      mfe_band_1h: forecast.target_mfe_1h,
      mfe_band_4h: forecast.target_mfe_4h,
      prob_hit_sl_first:
        forecast.prob_hit_sl_first ?? numberFromFeatureSnapshot(forecast, "prob_hit_sl_first"),
      prob_hit_pt1_first:
        forecast.prob_hit_pt1_first ?? numberFromFeatureSnapshot(forecast, "prob_hit_pt1_first"),
      prob_hit_pt2_after_pt1:
        forecast.prob_hit_pt2_after_pt1 ?? numberFromFeatureSnapshot(forecast, "prob_hit_pt2_after_pt1"),
      expected_max_extension:
        forecast.expected_max_extension ?? numberFromFeatureSnapshot(forecast, "expected_max_extension"),
      setup_score:
        forecast.setup_score ?? numberFromFeatureSnapshot(forecast, "setup_score"),
      confidence: forecast.confidence ?? null,
    },
    conviction: {
      level: conviction?.level ?? "NO_TRADE",
      counter_trend: conviction?.counter_trend ?? false,
      all_layers_agree: conviction?.all_layers_agree ?? false,
    },
    setup: setup
      ? {
          id: setup.id,
          direction: setup.direction,
          status: setup.status,
          fibLevel: setup.fib_level,
          fibRatio: setup.fib_ratio,
          entry: setup.entry_price,
          stopLoss: setup.stop_loss,
          tp1: setup.tp1,
          tp2: setup.tp2,
          volume_confirmation: setup.volume_confirmation,
          trigger_quality_ratio: setup.trigger_quality_ratio,
        }
      : undefined,
    risk: {
      garch_vol_forecast: risk?.garch_sigma ?? null,
      garch_vol_ratio: risk?.garch_vol_ratio ?? null,
      gpr_level: risk?.gpr_level ?? null,
      trump_effect_active: risk?.trump_effect_active ?? null,
      vix_level: risk?.vix_level ?? null,
      vix_percentile_20d: risk?.vix_percentile_20d ?? null,
      vix_percentile_regime: risk?.vix_percentile_regime ?? null,
      regime: risk?.regime_label ?? REGIME_LABEL,
      days_into_regime:
        risk?.days_into_regime ??
        getDaysIntoRegime(forecast.ts),
    },
    zones: risk
      ? {
          zone_1_upper: risk.zone_1_upper,
          zone_1_lower: risk.zone_1_lower,
          zone_2_upper: risk.zone_2_upper,
          zone_2_lower: risk.zone_2_lower,
        }
      : undefined,
    feedback: {
      win_rate_last20: numberFromFeatureSnapshot(forecast, "win_rate_last20"),
      current_streak: numberFromFeatureSnapshot(forecast, "current_streak"),
      avg_r_recent: numberFromFeatureSnapshot(forecast, "avg_r_recent"),
      setup_frequency_7d: numberFromFeatureSnapshot(forecast, "setup_frequency_7d"),
    },
  };
}

function numberFromFeatureSnapshot(
  forecast: Pick<WarbirdForecastRow, "feature_snapshot"> & { feature_snapshot?: unknown },
  key: string,
): number | null {
  const snapshot = (forecast as { feature_snapshot?: Record<string, unknown> }).feature_snapshot;
  const value = snapshot?.[key];
  return typeof value === "number" ? value : null;
}

export function warbirdSignalToTargets(
  signal: WarbirdSignal | null,
  lastCandleTime: number,
  futureEndTime: number,
): ForecastTarget[] {
  if (!signal) return [];

  const targets: ForecastTarget[] = [];
  const confidence = signal.directional.confidence ?? 0;
  const hitProb = Math.max(0, Math.min(1, confidence));

  if (signal.setup?.entry != null) {
    targets.push({
      id: `entry-${signal.generatedAt}`,
      kind: "ENTRY",
      label: `ENTRY ${signal.setup.entry.toFixed(2)}`,
      startTime: lastCandleTime,
      endTime: futureEndTime,
      price: signal.setup.entry,
      bandHalfWidth: 0,
      tags: ["WARBIRD", signal.conviction.level],
      color: TV.blue.primary,
    });
  }

  const tpTargets = [
    { id: "tp1", price: signal.setup?.tp1 ?? signal.directional.price_target_1h, band: signal.directional.mae_band_1h },
    { id: "tp2", price: signal.setup?.tp2 ?? signal.directional.price_target_4h, band: signal.directional.mae_band_4h },
  ];

  for (const target of tpTargets) {
    if (target.price == null) continue;
    targets.push({
      id: `${target.id}-${signal.generatedAt}`,
      kind: "TP",
      label: `${target.id.toUpperCase()} ${target.price.toFixed(2)}`,
      startTime: lastCandleTime,
      endTime: futureEndTime,
      price: target.price,
      bandHalfWidth: target.band ?? 0,
      tags: ["WARBIRD", signal.conviction.level],
      color: TV.bull.primary,
      mcProbTouch: hitProb,
    });
  }

  if (signal.setup?.stopLoss != null) {
    targets.push({
      id: `sl-${signal.generatedAt}`,
      kind: "SL",
      label: `SL ${signal.setup.stopLoss.toFixed(2)}`,
      startTime: lastCandleTime,
      endTime: futureEndTime,
      price: signal.setup.stopLoss,
      bandHalfWidth: 0,
      tags: ["WARBIRD", "STOP"],
      color: TV.bear.primary,
    });
  }

  return targets;
}

export function warbirdSetupToCandidate(
  setup: WarbirdSetupRow,
): SetupCandidate {
  const ts = Math.floor(new Date(setup.ts).getTime() / 1000);
  const isBullish = setup.direction === "LONG";

  return {
    id: String(setup.id),
    sourceFamily: "MEASURED_MOVE",
    triggerType: "MEASURED_MOVE_RETRACE",
    direction: isBullish ? "BULLISH" : "BEARISH",
    phase: setup.status === "ACTIVE" || setup.status === "TP1_HIT" || setup.status === "TP2_HIT"
      ? "TRIGGERED"
      : "EXPIRED",
    thesis: setup.notes ?? "",
    structuralReason: setup.conviction_level,
    candidateTime: ts,
    referenceLevel: setup.fib_level ?? setup.entry_price,
    entryZoneLow: setup.entry_price,
    entryZoneHigh: setup.entry_price,
    invalidationLevel: setup.stop_loss,
    impulseContext: setup.counter_trend ? "REVERSAL" : "CONTINUATION",
    liquidityContext: setup.volume_confirmation ? "EXPANSION" : "UNSPECIFIED",
    structureContext: "MEASURED_MOVE",
    fibLevel: setup.fib_level ?? setup.entry_price,
    fibRatio: setup.fib_ratio ?? 0.5,
    goTime: ts,
    goBarIndex: undefined,
    entry: setup.entry_price,
    stopLoss: setup.stop_loss,
    tp1: setup.tp1,
    tp2: setup.tp2,
    createdAt: Math.floor(new Date(setup.created_at).getTime() / 1000),
    expiryBars: 16,
  };
}

export function buildSetupEventSummary(events: WarbirdSetupEventRow[]) {
  return {
    triggered: events.filter((event) => event.event_type === "TRIGGERED").length,
    tp1Hit: events.filter((event) => event.event_type === "TP1_HIT").length,
    tp2Hit: events.filter((event) => event.event_type === "TP2_HIT").length,
    stopped: events.filter((event) => event.event_type === "STOPPED").length,
    expired: events.filter((event) => event.event_type === "EXPIRED").length,
  };
}
