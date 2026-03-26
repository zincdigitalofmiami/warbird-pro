import {
  REGIME_LABEL,
  WARBIRD_SIGNAL_VERSION,
  getDaysIntoRegime,
} from "@/lib/warbird/constants";
import type {
  WarbirdConvictionRow,
  WarbirdDailyBiasRow,
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
  trigger: WarbirdTriggerRow | null;
  conviction: WarbirdConvictionRow | null;
  risk: WarbirdRiskRow | null;
  setup: WarbirdSetupRow | null;
}): WarbirdSignal | null {
  const { daily, structure, trigger, conviction, risk, setup } = params;

  const generatedAt =
    setup?.bar_close_ts ??
    trigger?.bar_close_ts ??
    conviction?.bar_close_ts ??
    risk?.bar_close_ts ??
    null;
  const symbol =
    setup?.symbol_code ??
    trigger?.symbol_code ??
    conviction?.symbol_code ??
    risk?.symbol_code ??
    null;

  if (!generatedAt || !symbol) {
    return null;
  }

  const directionalBias =
    conviction?.bias_15m ??
    (setup?.direction === "LONG"
      ? "BULL"
      : setup?.direction === "SHORT"
        ? "BEAR"
        : "NEUTRAL");

  return {
    version: WARBIRD_SIGNAL_VERSION,
    generatedAt,
    symbol,
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
      bias_15m: directionalBias,
      prob_hit_sl_first: null,
      prob_hit_pt1_first: risk?.tp1_probability ?? null,
      prob_hit_pt2_after_pt1: risk?.tp2_probability ?? null,
      reversal_risk: risk?.reversal_risk ?? null,
      setup_score: trigger?.trigger_quality_ratio != null ? trigger.trigger_quality_ratio * 100 : null,
      confidence: risk?.confidence_score ?? trigger?.trigger_quality_ratio ?? null,
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
      days_into_regime: risk?.days_into_regime ?? getDaysIntoRegime(generatedAt),
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
      win_rate_last20: null,
      current_streak: null,
      avg_r_recent: null,
      setup_frequency_7d: null,
    },
  };
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
    { id: "tp1", price: signal.setup?.tp1 ?? null },
    { id: "tp2", price: signal.setup?.tp2 ?? null },
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
      bandHalfWidth: 0,
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
  const ts = Math.floor(new Date(setup.bar_close_ts).getTime() / 1000);
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
