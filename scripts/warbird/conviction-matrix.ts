/**
 * Warbird Conviction Matrix — Multi-Layer Bias Alignment
 *
 * Canonical spec Section 3:
 *   MAXIMUM  — Daily + 4H + 1H all agree (full position)
 *   HIGH     — Daily + 4H agree, 1H neutral (reduced size)
 *   MODERATE — 4H + 1H agree, daily neutral (TP1 focus)
 *   LOW      — 4H + 1H agree, daily against (counter-trend, TP1 only)
 *   NO_TRADE — insufficient alignment or daily against with no support
 *
 * Conviction is purely about bias alignment — it answers "how confident
 * are we in the DIRECTION?" The trigger engine separately answers
 * "is price actually reversing at this zone?"
 */

import type {
  WarbirdBias,
  WarbirdConvictionLevel,
} from "@/lib/warbird/types";

export interface ConvictionInput {
  dailyBias: WarbirdBias;
  bias4h: WarbirdBias;
  bias1h: WarbirdBias;
}

export interface ConvictionResult {
  level: WarbirdConvictionLevel;
  counterTrend: boolean;
  allLayersAgree: boolean;
}

export function evaluateConviction(input: ConvictionInput): ConvictionResult {
  const { dailyBias, bias4h, bias1h } = input;

  // ── MAXIMUM: all three layers agree on direction ──────────────────────
  if (
    dailyBias !== "NEUTRAL" &&
    dailyBias === bias4h &&
    bias4h === bias1h
  ) {
    return {
      level: "MAXIMUM",
      counterTrend: false,
      allLayersAgree: true,
    };
  }

  // ── HIGH: daily + 4H agree, 1H neutral (not yet confirming) ──────────
  if (
    dailyBias !== "NEUTRAL" &&
    dailyBias === bias4h &&
    bias1h === "NEUTRAL"
  ) {
    return {
      level: "HIGH",
      counterTrend: false,
      allLayersAgree: false,
    };
  }

  // ── MODERATE: 4H + 1H agree, daily neutral ───────────────────────────
  if (
    dailyBias === "NEUTRAL" &&
    bias4h !== "NEUTRAL" &&
    bias4h === bias1h
  ) {
    return {
      level: "MODERATE",
      counterTrend: false,
      allLayersAgree: false,
    };
  }

  // ── LOW: 4H + 1H agree, daily AGAINST (counter-trend) ────────────────
  if (
    dailyBias !== "NEUTRAL" &&
    bias4h !== "NEUTRAL" &&
    bias4h === bias1h &&
    dailyBias !== bias1h
  ) {
    return {
      level: "LOW",
      counterTrend: true,
      allLayersAgree: false,
    };
  }

  // ── NO_TRADE: everything else ─────────────────────────────────────────
  return {
    level: "NO_TRADE",
    counterTrend: false,
    allLayersAgree: false,
  };
}
