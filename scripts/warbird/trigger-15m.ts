/**
 * Warbird 15m Trigger Engine — 1m Microstructure + Proven TA Intelligence
 *
 * NOT a fib line alert. This engine determines WHETHER price is actually
 * reversing at a fib zone using:
 *
 *   1. LuxAlgo Market Sentiment (11 normalized indicators on 1m bars)
 *   2. TTM Squeeze detection (Bollinger inside Keltner = volatility expansion imminent)
 *   3. 1m microstructure (rejection wicks, volume spikes, engulfing, momentum)
 *
 * The 15m fib engine identifies WHERE (the zone).
 * This engine identifies WHEN (the trigger) and HOW GOOD (the quality).
 *
 * Kirk: "Price touched .618 is not a trigger. A trigger is price hit .618,
 * the 15m printed a rejection wick with 2x volume, momentum shifted, and
 * this exact pattern wins 71% of the time at this hour."
 *
 * Input:  1-minute candles (last 30-60 bars), 15m zone info, direction
 * Output: trigger decision, precise entry, tight stop, quality score,
 *         all indicator values as features for model training
 */

import { roundToTick } from "@/lib/ta/fibonacci";
import {
  computeMarketSentiment,
  rsiRaw,
  type SentimentResult,
} from "@/lib/ta/indicators";
import type { CandleData } from "@/lib/types";
import type {
  WarbirdDirection,
  WarbirdTriggerDecision,
  WarbirdTriggerRow,
} from "@/lib/warbird/types";
import { WARBIRD_DEFAULT_SYMBOL } from "@/lib/warbird/constants";
import type { WarbirdFibGeometry } from "@/scripts/warbird/fib-engine";

// ─── Constants ──────────────────────────────────────────────────────────────

const MES_TICK = 0.25;

/** How many 1m bars to look back for trigger detection */
const TRIGGER_LOOKBACK_1M = 30;

/** Minimum bars needed for meaningful indicator computation */
const MIN_BARS = 20;

/** How close price must get to fib level to count as "in the zone" (points) */
const ZONE_PROXIMITY_PTS = 4.0;

/** Volume baseline bars for ratio computation */
const VOLUME_BASELINE_BARS = 20;

/** Wick-to-body ratio threshold for rejection candle */
const REJECTION_WICK_RATIO = 2.0;

/** Minimum trigger score to issue GO */
const TRIGGER_GO_THRESHOLD = 0.55;

/** Minimum trigger score to issue WAIT (below = NO_GO) */
const TRIGGER_WAIT_THRESHOLD = 0.30;

// ─── Types ──────────────────────────────────────────────────────────────────

export interface TriggerInputs {
  /** 1-minute candles — the microstructure data */
  candles1m: CandleData[];
  /** 15m fib geometry (zone, direction, levels) */
  geometry: WarbirdFibGeometry;
  /** Canonical MES 15m bar close for this setup candidate */
  barCloseTs: string;
  /** MES symbol code */
  symbolCode?: string;
  /** Optional expected MAE in points from a promoted model surface */
  expectedMaePts?: number | null;
  /** Cross-asset correlation score (optional) */
  correlationScore?: number | null;
}

export interface TriggerFeatures {
  // ── Proven TA indicators (LuxAlgo-style, all 0-100) ─────────────
  /** Composite sentiment from 10 indicators */
  sentiment: number;
  /** Individual indicators */
  rsi: number;
  stochastic: number;
  stochRsi: number;
  cci: number;
  bbp: number;
  maPosition: number;
  bbPosition: number;
  supertrendPosition: number;
  linearRegression: number;
  marketStructureScore: number;
  /** TTM Squeeze: is volatility compressed? */
  squeezeOn: boolean;
  /** TTM Squeeze: momentum value and direction */
  squeezeMomentum: number;
  squeezeMomentumDirection: number;

  // ── 1m Microstructure ───────────────────────────────────────────
  /** Rejection wick detected at zone? */
  rejectionDetected: boolean;
  /** Wick-to-body ratio of best rejection bar */
  rejectionWickRatio: number;
  /** Volume ratio of trigger bar vs 20-bar average */
  volumeRatio: number;
  /** Was volume above 1.2x? */
  volumeConfirmed: boolean;
  /** Was there a volume spike (1.5x+)? */
  volumeSpike: boolean;
  /** How many 1m bars price spent in the zone */
  barsInZone: number;
  /** Engulfing pattern detected? */
  engulfingDetected: boolean;
  /** Rate of change flipped sign? */
  momentumShift: boolean;
  /** Points moved in first 3 bars after zone touch */
  reversalSpeed: number;
  /** How close did price get to the fib level? */
  zoneProximity: number;
  /** Wicked through zone and closed back? */
  wickThrough: boolean;

  // ── Composite and precision ─────────────────────────────────────
  /** Final trigger quality score (0-1) */
  triggerScore: number;
  /** Hour of day (UTC) — critical for time-of-day learning */
  hourUtc: number;
  /** Precise entry price from 1m trigger bar */
  preciseEntry: number;
  /** Tight stop from 1m structure */
  preciseStop: number;
}

// ─── Microstructure Detection ───────────────────────────────────────────────

function findZoneEntry(
  bars: CandleData[],
  fibLevel: number,
  direction: WarbirdDirection,
): number {
  for (let i = bars.length - 1; i >= 0; i--) {
    const bar = bars[i];
    const inZone = direction === "LONG"
      ? bar.low <= fibLevel + ZONE_PROXIMITY_PTS
      : bar.high >= fibLevel - ZONE_PROXIMITY_PTS;
    if (!inZone) return i + 1;
  }
  return 0;
}

function detectRejection(
  bars: CandleData[],
  fibLevel: number,
  direction: WarbirdDirection,
): { detected: boolean; wickRatio: number; barIndex: number } {
  let bestRatio = 0;
  let bestIndex = -1;

  for (let i = 0; i < bars.length; i++) {
    const bar = bars[i];
    const body = Math.abs(bar.close - bar.open);

    if (direction === "LONG") {
      const lowerWick = Math.min(bar.open, bar.close) - bar.low;
      if (lowerWick <= 0) continue;
      if (bar.low > fibLevel + ZONE_PROXIMITY_PTS) continue;
      if (bar.close < fibLevel - ZONE_PROXIMITY_PTS) continue;
      const ratio = body > MES_TICK ? lowerWick / body : lowerWick / MES_TICK;
      if (ratio > bestRatio) { bestRatio = ratio; bestIndex = i; }
    } else {
      const upperWick = bar.high - Math.max(bar.open, bar.close);
      if (upperWick <= 0) continue;
      if (bar.high < fibLevel - ZONE_PROXIMITY_PTS) continue;
      if (bar.close > fibLevel + ZONE_PROXIMITY_PTS) continue;
      const ratio = body > MES_TICK ? upperWick / body : upperWick / MES_TICK;
      if (ratio > bestRatio) { bestRatio = ratio; bestIndex = i; }
    }
  }

  return {
    detected: bestRatio >= REJECTION_WICK_RATIO,
    wickRatio: Math.round(bestRatio * 100) / 100,
    barIndex: bestIndex,
  };
}

function detectEngulfing(bars: CandleData[], direction: WarbirdDirection): boolean {
  if (bars.length < 2) return false;
  const checkBars = bars.slice(-Math.min(5, bars.length));
  for (let i = 1; i < checkBars.length; i++) {
    const prior = checkBars[i - 1];
    const current = checkBars[i];
    if (direction === "LONG") {
      if (prior.close < prior.open && current.close > current.open &&
          current.open <= prior.close && current.close >= prior.open) return true;
    } else {
      if (prior.close > prior.open && current.close < current.open &&
          current.open >= prior.close && current.close <= prior.open) return true;
    }
  }
  return false;
}

function detectMomentumShift(bars: CandleData[], direction: WarbirdDirection): boolean {
  if (bars.length < 4) return false;
  const window = bars.slice(-Math.min(8, bars.length));
  const rocs: number[] = [];
  for (let i = 1; i < window.length; i++) {
    rocs.push(window[i].close - window[i - 1].close);
  }
  if (rocs.length < 3) return false;
  for (let i = 1; i < rocs.length; i++) {
    if (direction === "LONG" && rocs[i - 1] < 0 && rocs[i] > 0) return true;
    if (direction === "SHORT" && rocs[i - 1] > 0 && rocs[i] < 0) return true;
  }
  return false;
}

function computeVolumeProfile(
  allBars: CandleData[],
  zoneStartIdx: number,
): { ratio: number; confirmed: boolean; spike: boolean } {
  const baselineBars = allBars.slice(
    Math.max(0, zoneStartIdx - VOLUME_BASELINE_BARS),
    zoneStartIdx,
  );
  const zoneBars = allBars.slice(zoneStartIdx);
  if (baselineBars.length === 0 || zoneBars.length === 0) {
    return { ratio: 0, confirmed: false, spike: false };
  }
  const avgBaseline = baselineBars.reduce((s, b) => s + (b.volume ?? 0), 0) / baselineBars.length;
  if (avgBaseline <= 0) return { ratio: 0, confirmed: false, spike: false };
  const peakVolume = Math.max(...zoneBars.map((b) => b.volume ?? 0));
  const ratio = Math.round((peakVolume / avgBaseline) * 100) / 100;
  return { ratio, confirmed: ratio >= 1.2, spike: ratio >= 1.5 };
}

function measureReversalSpeed(
  bars: CandleData[],
  direction: WarbirdDirection,
  fibLevel: number,
): number {
  let touchIdx = -1;
  for (let i = 0; i < bars.length; i++) {
    if (direction === "LONG" && bars[i].low <= fibLevel + ZONE_PROXIMITY_PTS) touchIdx = i;
    if (direction === "SHORT" && bars[i].high >= fibLevel - ZONE_PROXIMITY_PTS) touchIdx = i;
  }
  if (touchIdx < 0 || touchIdx >= bars.length - 1) return 0;
  const lookAhead = Math.min(3, bars.length - touchIdx - 1);
  if (lookAhead <= 0) return 0;
  const touchPrice = direction === "LONG" ? bars[touchIdx].low : bars[touchIdx].high;
  const endPrice = direction === "LONG"
    ? Math.max(...bars.slice(touchIdx + 1, touchIdx + 1 + lookAhead).map((b) => b.high))
    : Math.min(...bars.slice(touchIdx + 1, touchIdx + 1 + lookAhead).map((b) => b.low));
  return Math.abs(endPrice - touchPrice);
}

function computePreciseLevels(
  zoneBars: CandleData[],
  direction: WarbirdDirection,
  geometryStop: number,
): { entry: number; stop: number } {
  if (zoneBars.length === 0) return { entry: 0, stop: geometryStop };
  const lastBar = zoneBars[zoneBars.length - 1];
  const entry = roundToTick(lastBar.close, MES_TICK);
  const stopBuffer = MES_TICK * 2;
  let stop: number;
  if (direction === "LONG") {
    const zoneExtremeLow = Math.min(...zoneBars.map((b) => b.low));
    stop = roundToTick(zoneExtremeLow - stopBuffer, MES_TICK);
    if (stop < geometryStop) stop = geometryStop;
  } else {
    const zoneExtremeHigh = Math.max(...zoneBars.map((b) => b.high));
    stop = roundToTick(zoneExtremeHigh + stopBuffer, MES_TICK);
    if (stop > geometryStop) stop = geometryStop;
  }
  return { entry, stop };
}

// ─── Composite Trigger Scoring ──────────────────────────────────────────────

/**
 * Compute the trigger score — DETECTION, not confirmation.
 *
 * Detection = the indicators are SCREAMING the reversal is imminent.
 * Confirmation = waiting for the reversal to already happen (too late).
 *
 * The trigger fires BEFORE the rejection wick prints. The indicators
 * (RSI oversold at zone, squeeze firing, momentum flipping) ARE the trigger.
 * Microstructure signals (rejection, engulfing) are BONUS confirmation that
 * increase the score but aren't required.
 *
 * Scoring priority:
 *   1. INDICATORS at extreme (60%) — RSI/Stoch/CCI oversold at LONG zone
 *      or overbought at SHORT zone = primary trigger signal
 *   2. SQUEEZE + MOMENTUM (25%) — compressed volatility about to expand
 *      with momentum aligning = high-probability move incoming
 *   3. MICROSTRUCTURE BONUS (15%) — rejection/engulfing/volume add
 *      confidence but the trigger already fired from indicators
 */
function computeTriggerScore(
  sentiment: SentimentResult,
  direction: WarbirdDirection,
  rejection: { detected: boolean; wickRatio: number },
  volumeProfile: { ratio: number; confirmed: boolean; spike: boolean },
  engulfing: boolean,
  momentumShift: boolean,
  reversalSpeed: number,
  wickThrough: boolean,
  barsInZone: number,
  anchorRange: number,
): number {
  let score = 0;

  // ── PRIMARY: Indicator extremes at zone (0-0.60) ────────────────────
  // This IS the trigger. When oscillators hit extreme at a known fib zone,
  // the reversal is imminent — don't wait for the wick to confirm it.

  // Oscillator extreme score: how many oscillators are at extreme levels?
  // For LONG: lower = more oversold = stronger trigger
  // For SHORT: higher = more overbought = stronger trigger
  const oscillators = [sentiment.rsi, sentiment.stochastic, sentiment.stochRsi, sentiment.cci, sentiment.bbp];

  let extremeCount = 0;
  let extremeIntensity = 0;

  for (const osc of oscillators) {
    if (direction === "LONG" && osc < 30) {
      extremeCount++;
      extremeIntensity += (30 - osc) / 30; // 0 = strongest, 30 = threshold
    } else if (direction === "SHORT" && osc > 70) {
      extremeCount++;
      extremeIntensity += (osc - 70) / 30;
    }
  }

  // At least 2 oscillators at extreme = trigger condition met
  if (extremeCount >= 2) {
    const countFactor = Math.min(extremeCount / 4, 1.0); // 4+ oscillators = max
    const intensityFactor = extremeIntensity / oscillators.length;
    score += 0.60 * (0.6 * countFactor + 0.4 * intensityFactor);
  } else if (extremeCount === 1) {
    // Single oscillator at extreme — weak but not nothing
    score += 0.60 * 0.2 * (extremeIntensity);
  }

  // Trend indicators aligning with direction
  const trendIndicators = [sentiment.ma, sentiment.supertrend, sentiment.marketStructure];
  let trendAlignment = 0;
  for (const trend of trendIndicators) {
    // For LONG at zone: trend below 50 means we're buying the dip in context
    // For SHORT at zone: trend above 50 means we're selling the rip in context
    if (direction === "LONG" && trend < 40) trendAlignment++;
    else if (direction === "SHORT" && trend > 60) trendAlignment++;
  }

  // ── SECONDARY: Squeeze + Momentum (0-0.25) ─────────────────────────
  // Squeeze ON = BB inside KC = volatility compressed = about to explode.
  // This is the LazyBear TTM Squeeze. When it fires at a fib zone,
  // the move that follows is typically the strongest.
  if (sentiment.squeeze.squeezeOn) {
    score += 0.12;
    // Momentum direction shifting toward our trade = imminent breakout
    const momAligns = direction === "LONG"
      ? sentiment.squeeze.momentumDirection > 0
      : sentiment.squeeze.momentumDirection < 0;
    if (momAligns) score += 0.13;
  } else {
    // No squeeze — check if momentum is flipping (weaker signal)
    if (momentumShift) score += 0.08;
    // Linear regression slope aligning
    const lrAligns = direction === "LONG"
      ? sentiment.linearRegression < 40 // slope turning up from below
      : sentiment.linearRegression > 60; // slope turning down from above
    if (lrAligns) score += 0.05;
  }

  // ── BONUS: Microstructure confirmation (0-0.15) ─────────────────────
  // These happened AFTER the trigger condition. They add confidence
  // but aren't required — the indicators already said GO.
  if (rejection.detected) score += 0.05;
  if (volumeProfile.spike) score += 0.04;
  else if (volumeProfile.confirmed) score += 0.02;
  if (engulfing) score += 0.03;
  if (wickThrough) score += 0.03;

  // ── Zone time penalty ───────────────────────────────────────────────
  // Price lingering in zone too long = losing momentum, not about to reverse
  if (barsInZone > 10) {
    score -= 0.05 * Math.min((barsInZone - 10) / 10, 1.0);
  }

  return Math.max(0, Math.min(score, 1.0));
}

// ─── Main ───────────────────────────────────────────────────────────────────

/**
 * Evaluate the 15m trigger using 1-minute bars, proven TA indicators,
 * and microstructure signals.
 *
 * Returns complete trigger evaluation with all features for model training.
 */
export function evaluateTrigger(
  inputs: TriggerInputs,
): { trigger: Omit<WarbirdTriggerRow, "id">; features: TriggerFeatures } {
  const { candles1m, geometry, correlationScore, barCloseTs, symbolCode, expectedMaePts } = inputs;

  const ordered = [...candles1m].sort((a, b) => a.time - b.time);
  const recentBars = ordered.slice(-TRIGGER_LOOKBACK_1M);

  if (recentBars.length < MIN_BARS) {
    return buildNoGoResult(inputs, "insufficient_1m_data");
  }

  const lastBar = recentBars[recentBars.length - 1];
  const { direction, fibLevel, stopLoss: geometryStop } = geometry;
  const anchorRange = geometry.fibResult.anchorHigh - geometry.fibResult.anchorLow;

  // ── Check if price is near the fib zone ──────────────────────────────
  const priceNearZone = direction === "LONG"
    ? lastBar.low <= fibLevel + ZONE_PROXIMITY_PTS * 2
    : lastBar.high >= fibLevel - ZONE_PROXIMITY_PTS * 2;

  if (!priceNearZone) {
    return buildNoGoResult(inputs, "price_not_near_zone");
  }

  // ── Extract arrays for indicator computation ─────────────────────────
  const closes = recentBars.map((b) => b.close);
  const highs = recentBars.map((b) => b.high);
  const lows = recentBars.map((b) => b.low);

  // ── Compute proven TA indicators (LuxAlgo-style) ─────────────────────
  const sentiment = computeMarketSentiment(closes, highs, lows);

  // ── Find zone interaction ────────────────────────────────────────────
  const zoneStartIdx = findZoneEntry(recentBars, fibLevel, direction);
  const zoneBars = recentBars.slice(zoneStartIdx);
  const barsInZone = zoneBars.length;

  // ── Zone proximity ───────────────────────────────────────────────────
  let zoneProximity: number;
  if (direction === "LONG") {
    const zoneLow = zoneBars.length > 0 ? Math.min(...zoneBars.map((b) => b.low)) : lastBar.low;
    zoneProximity = Math.max(0, zoneLow - fibLevel);
  } else {
    const zoneHigh = zoneBars.length > 0 ? Math.max(...zoneBars.map((b) => b.high)) : lastBar.high;
    zoneProximity = Math.max(0, fibLevel - zoneHigh);
  }

  // ── Wick-through detection ───────────────────────────────────────────
  const wickThrough = direction === "LONG"
    ? zoneBars.some((b) => b.low < fibLevel && b.close > fibLevel)
    : zoneBars.some((b) => b.high > fibLevel && b.close < fibLevel);

  // ── Microstructure signals ───────────────────────────────────────────
  const rejection = detectRejection(zoneBars, fibLevel, direction);
  const engulfing = detectEngulfing(zoneBars, direction);
  const momentumShift = detectMomentumShift(zoneBars, direction);
  const volumeProfile = computeVolumeProfile(recentBars, zoneStartIdx);
  const reversalSpeed = measureReversalSpeed(zoneBars, direction, fibLevel);

  // ── Precise levels from 1m structure ─────────────────────────────────
  const { entry: preciseEntry, stop: preciseStop } = computePreciseLevels(
    zoneBars, direction, geometryStop,
  );

  // ── Composite trigger score ──────────────────────────────────────────
  const triggerScore = computeTriggerScore(
    sentiment, direction, rejection, volumeProfile,
    engulfing, momentumShift, reversalSpeed, wickThrough,
    barsInZone, anchorRange,
  );

  // ── MAE/MFE risk check ───────────────────────────────────────────────
  const stopDistance = Math.abs(preciseEntry - preciseStop);
  const maeBlocksTrade =
    stopDistance > 0 && expectedMaePts != null && expectedMaePts > stopDistance * 1.5;

  // ── Decision ─────────────────────────────────────────────────────────
  let decision: WarbirdTriggerDecision = "WAIT";
  let noTradeReason: string | null = null;

  if (maeBlocksTrade) {
    decision = "NO_GO";
    noTradeReason = "mae_exceeds_stop_distance";
  } else if (triggerScore >= TRIGGER_GO_THRESHOLD) {
    decision = "GO";
  } else if (triggerScore < TRIGGER_WAIT_THRESHOLD) {
    decision = "NO_GO";
    noTradeReason = `trigger_score_${triggerScore.toFixed(2)}`;
  }

  const hourUtc = new Date(lastBar.time * 1000).getUTCHours();

  // ── Build features for model training ────────────────────────────────
  const features: TriggerFeatures = {
    // Proven TA indicators
    sentiment: sentiment.sentiment,
    rsi: sentiment.rsi,
    stochastic: sentiment.stochastic,
    stochRsi: sentiment.stochRsi,
    cci: sentiment.cci,
    bbp: sentiment.bbp,
    maPosition: sentiment.ma,
    bbPosition: sentiment.bb,
    supertrendPosition: sentiment.supertrend,
    linearRegression: sentiment.linearRegression,
    marketStructureScore: sentiment.marketStructure,
    squeezeOn: sentiment.squeeze.squeezeOn,
    squeezeMomentum: Math.round(sentiment.squeeze.momentum * 100) / 100,
    squeezeMomentumDirection: sentiment.squeeze.momentumDirection,
    // Microstructure
    rejectionDetected: rejection.detected,
    rejectionWickRatio: rejection.wickRatio,
    volumeRatio: volumeProfile.ratio,
    volumeConfirmed: volumeProfile.confirmed,
    volumeSpike: volumeProfile.spike,
    barsInZone,
    engulfingDetected: engulfing,
    momentumShift,
    reversalSpeed: Math.round(reversalSpeed * 100) / 100,
    zoneProximity: Math.round(zoneProximity * 100) / 100,
    wickThrough,
    // Composite
    triggerScore: Math.round(triggerScore * 1000) / 1000,
    hourUtc,
    preciseEntry,
    preciseStop,
  };

  // ── Build trigger row ────────────────────────────────────────────────
  const trigger: Omit<WarbirdTriggerRow, "id"> = {
    bar_close_ts: barCloseTs,
    timeframe: "M15",
    symbol_code: symbolCode ?? WARBIRD_DEFAULT_SYMBOL,
    direction,
    decision,
    fib_level: fibLevel,
    fib_ratio: geometry.fibRatio,
    entry_price: preciseEntry,
    stop_loss: preciseStop,
    tp1: geometry.tp1,
    tp2: geometry.tp2,
    candle_confirmed: rejection.detected || engulfing,
    volume_confirmation: volumeProfile.confirmed,
    volume_ratio: volumeProfile.ratio,
    stoch_rsi: rsiRaw(closes),
    correlation_score: correlationScore ?? null,
    trigger_quality_ratio: Math.round(triggerScore * 1000) / 1000,
    no_trade_reason: noTradeReason,
  };

  return { trigger, features };
}

// ─── Helpers ────────────────────────────────────────────────────────────────

function buildNoGoResult(
  inputs: TriggerInputs,
  reason: string,
): { trigger: Omit<WarbirdTriggerRow, "id">; features: TriggerFeatures } {
  const { geometry, barCloseTs, symbolCode } = inputs;

  const features: TriggerFeatures = {
    sentiment: 50, rsi: 50, stochastic: 50, stochRsi: 50, cci: 50, bbp: 50,
    maPosition: 50, bbPosition: 50, supertrendPosition: 50,
    linearRegression: 50, marketStructureScore: 50,
    squeezeOn: false, squeezeMomentum: 0, squeezeMomentumDirection: 0,
    rejectionDetected: false, rejectionWickRatio: 0,
    volumeRatio: 0, volumeConfirmed: false, volumeSpike: false,
    barsInZone: 0, engulfingDetected: false, momentumShift: false,
    reversalSpeed: 0, zoneProximity: 999, wickThrough: false,
    triggerScore: 0, hourUtc: new Date().getUTCHours(),
    preciseEntry: geometry.entry, preciseStop: geometry.stopLoss,
  };

  const trigger: Omit<WarbirdTriggerRow, "id"> = {
    bar_close_ts: barCloseTs,
    timeframe: "M15",
    symbol_code: symbolCode ?? WARBIRD_DEFAULT_SYMBOL,
    direction: geometry.direction,
    decision: "NO_GO",
    fib_level: geometry.fibLevel,
    fib_ratio: geometry.fibRatio,
    entry_price: geometry.entry,
    stop_loss: geometry.stopLoss,
    tp1: geometry.tp1,
    tp2: geometry.tp2,
    candle_confirmed: false,
    volume_confirmation: false,
    volume_ratio: 0,
    stoch_rsi: null,
    correlation_score: null,
    trigger_quality_ratio: 0,
    no_trade_reason: reason,
  };

  return { trigger, features };
}
