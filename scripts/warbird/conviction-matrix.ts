import type {
  WarbirdBias,
  WarbirdConvictionLevel,
  WarbirdTriggerDecision,
} from "@/lib/warbird/types";

export interface ConvictionInput {
  dailyBias: WarbirdBias;
  bias4h: WarbirdBias;
  bias1h: WarbirdBias;
  triggerDecision: WarbirdTriggerDecision;
}

export interface ConvictionResult {
  level: WarbirdConvictionLevel;
  counterTrend: boolean;
  allLayersAgree: boolean;
  runnerEligible: boolean;
}

export function evaluateConviction(input: ConvictionInput): ConvictionResult {
  const { dailyBias, bias4h, bias1h, triggerDecision } = input;
  const triggerAligned = triggerDecision === "GO";
  const allLayersAgree =
    triggerAligned &&
    dailyBias !== "NEUTRAL" &&
    dailyBias === bias4h &&
    bias4h === bias1h;

  if (allLayersAgree) {
    return {
      level: "MAXIMUM",
      counterTrend: false,
      allLayersAgree: true,
      runnerEligible: true,
    };
  }

  if (
    dailyBias !== "NEUTRAL" &&
    dailyBias === bias4h &&
    bias4h === bias1h
  ) {
    return {
      level: triggerAligned ? "HIGH" : "MODERATE",
      counterTrend: false,
      allLayersAgree: false,
      runnerEligible: triggerAligned,
    };
  }

  if (
    dailyBias === "NEUTRAL" &&
    bias4h !== "NEUTRAL" &&
    bias4h === bias1h &&
    triggerAligned
  ) {
    return {
      level: "MODERATE",
      counterTrend: false,
      allLayersAgree: false,
      runnerEligible: false,
    };
  }

  if (
    dailyBias !== "NEUTRAL" &&
    bias4h !== "NEUTRAL" &&
    bias4h === bias1h &&
    dailyBias !== bias1h &&
    triggerAligned
  ) {
    return {
      level: "LOW",
      counterTrend: true,
      allLayersAgree: false,
      runnerEligible: false,
    };
  }

  return {
    level: "NO_TRADE",
    counterTrend: false,
    allLayersAgree: false,
    runnerEligible: false,
  };
}
