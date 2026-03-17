/**
 * Warbird Fib Engine — Canonical 1H Fib Geometry
 *
 * Computes entry, stop, TP1, TP2 from 1H candles using:
 *   1. Multi-period confluence anchor (lib/fibonacci.ts)
 *   2. Trade direction from bias (overrides fib's internal isBullish)
 *   3. Actual retrace depth detection (scans ALL fib levels, not just .5)
 *   4. Measured move alignment (AB=CD patterns)
 *
 * All level prices are computed using TRADE DIRECTION, not fibonacci.ts's
 * isBullish flag, preventing the direction divergence bug where targets
 * end up on the wrong side of entry.
 *
 * Stop = ZERO level (full anchor retrace) per locked methodology.
 * Model learns optimal stop tightening from MAE data.
 */

import { calculateFibonacciMultiPeriod } from "@/lib/fibonacci";
import { detectMeasuredMoves } from "@/lib/measured-move";
import { detectSwings } from "@/lib/swing-detection";
import { fibExtension, roundToTick } from "@/lib/ta/fibonacci";
import type { CandleData, FibResult, MeasuredMove } from "@/lib/types";
import type { WarbirdBias, WarbirdDirection } from "@/lib/warbird/types";

// ─── Constants ──────────────────────────────────────────────────────────────

const MES_TICK = 0.25;
const RETRACE_LOOKBACK = 20;

/** All retrace levels to scan — ascending order (deepest first in Warbird ratio) */
const RETRACE_RATIOS = [0.236, 0.382, 0.5, 0.618, 0.786] as const;

/** Buffer beyond ZERO level for stop placement (fraction of range) */
const STOP_BUFFER_PCT = 0.02;

// ─── Types ──────────────────────────────────────────────────────────────────

export interface WarbirdFibGeometry {
  direction: WarbirdDirection;
  fibLevel: number;
  fibRatio: number;
  actualRetraceRatio: number;
  entry: number;
  stopLoss: number;
  tp1: number;
  tp2: number;
  measuredMoveTarget: number | null;
  quality: number;
  fibResult: FibResult;
  measuredMove: MeasuredMove | null;
}

// ─── Helpers ────────────────────────────────────────────────────────────────

function biasToDirection(bias: WarbirdBias): WarbirdDirection {
  return bias === "BEAR" ? "SHORT" : "LONG";
}

/**
 * Compute a fib level price using TRADE direction.
 *
 * LONG:  price = anchorLow  + range * ratio  (0=bottom, 1=top, extensions above)
 * SHORT: price = anchorHigh - range * ratio  (0=top,    1=bottom, extensions below)
 *
 * This ensures targets are always on the correct side of entry regardless
 * of whether fibonacci.ts's internal isBullish agrees with the trade direction.
 */
function directionalPrice(
  anchorHigh: number,
  anchorLow: number,
  ratio: number,
  direction: WarbirdDirection,
): number {
  const range = anchorHigh - anchorLow;
  return direction === "LONG"
    ? anchorLow + range * ratio
    : anchorHigh - range * ratio;
}

/**
 * Detect which fib retrace level price actually pulled back to.
 *
 * Scans all 5 retrace levels (.236, .382, .5, .618, .786) against recent
 * candle lows (LONG) or highs (SHORT). Returns the DEEPEST level reached.
 *
 * For LONG: deeper retrace = lower Warbird ratio (price dropped further from the 1 level)
 * For SHORT: deeper retrace = lower Warbird ratio (price bounced further from the 1 level)
 *
 * Returns 0 if no retrace level was reached.
 */
function detectRetraceDepth(
  candles: CandleData[],
  anchorHigh: number,
  anchorLow: number,
  direction: WarbirdDirection,
): number {
  const recent = candles.slice(-RETRACE_LOOKBACK);

  // Iterate ascending — first match is the deepest retrace achieved.
  // Lower Warbird ratio = closer to the ZERO level = deeper retrace.
  // If candle reached the .236 level, it also reached .382, .5, .618, .786.
  for (const ratio of RETRACE_RATIOS) {
    const levelPrice = directionalPrice(anchorHigh, anchorLow, ratio, direction);
    const touched = direction === "LONG"
      ? recent.some((c) => c.low <= levelPrice)
      : recent.some((c) => c.high >= levelPrice);
    if (touched) return ratio;
  }

  return 0;
}

function alignMeasuredMove(
  moves: MeasuredMove[],
  direction: WarbirdDirection,
): MeasuredMove | null {
  const alignedDir = direction === "LONG" ? "BULLISH" : "BEARISH";
  return (
    moves.find((m) => m.direction === alignedDir && m.status === "ACTIVE") ??
    moves.find((m) => m.direction === alignedDir) ??
    null
  );
}

// ─── Main ───────────────────────────────────────────────────────────────────

export function buildFibGeometry(
  candles: CandleData[],
  bias: WarbirdBias,
): WarbirdFibGeometry | null {
  if (candles.length < 55) return null;

  const ordered = [...candles].sort((a, b) => a.time - b.time);
  const fibResult = calculateFibonacciMultiPeriod(ordered);
  if (!fibResult) return null;

  const { anchorHigh, anchorLow } = fibResult;
  const range = anchorHigh - anchorLow;
  if (range <= 0) return null;

  const currentPrice = ordered[ordered.length - 1].close;
  const direction = biasToDirection(
    bias === "NEUTRAL" ? (fibResult.isBullish ? "BULL" : "BEAR") : bias,
  );

  const { highs, lows } = detectSwings(ordered);
  const measuredMove = alignMeasuredMove(
    detectMeasuredMoves(highs, lows, currentPrice),
    direction,
  );

  // ── Retrace depth: scan ALL levels, record which one price reached ────
  const actualRetraceRatio = detectRetraceDepth(
    ordered,
    anchorHigh,
    anchorLow,
    direction,
  );
  const entryRatio = actualRetraceRatio > 0 ? actualRetraceRatio : 0.5;

  // ── Entry ─────────────────────────────────────────────────────────────
  const entryLevelPrice = directionalPrice(anchorHigh, anchorLow, entryRatio, direction);
  const entry = measuredMove
    ? roundToTick(measuredMove.entry, MES_TICK)
    : roundToTick(entryLevelPrice, MES_TICK);
  const fibLevel = roundToTick(entryLevelPrice, MES_TICK);

  // ── Stop: ZERO level per locked methodology ───────────────────────────
  // "Stop = price closes back through the 0.0 level (full anchor swing retracement)"
  // LONG stop = just below anchor LOW.  SHORT stop = just above anchor HIGH.
  const zeroPrice = directionalPrice(anchorHigh, anchorLow, 0, direction);
  const stopBuffer = range * STOP_BUFFER_PCT;
  let stopLoss = measuredMove
    ? roundToTick(measuredMove.stop, MES_TICK)
    : direction === "LONG"
      ? roundToTick(zeroPrice - stopBuffer, MES_TICK)
      : roundToTick(zeroPrice + stopBuffer, MES_TICK);

  // ── TP1 / TP2: extensions using TRADE direction ───────────────────────
  let tp1: number;
  let tp2: number;

  if (measuredMove) {
    const { pointA, pointB, pointC } = measuredMove;
    tp1 = roundToTick(
      fibExtension(pointA.price, pointB.price, pointC.price, 1.236),
      MES_TICK,
    );
    tp2 = roundToTick(
      fibExtension(pointA.price, pointB.price, pointC.price, 1.618),
      MES_TICK,
    );
  } else {
    tp1 = roundToTick(directionalPrice(anchorHigh, anchorLow, 1.236, direction), MES_TICK);
    tp2 = roundToTick(directionalPrice(anchorHigh, anchorLow, 1.618, direction), MES_TICK);
  }

  // ── Sanity: targets on correct side, stop on correct side ─────────────
  if (direction === "LONG") {
    if (tp1 <= entry) tp1 = roundToTick(entry + range * 0.236, MES_TICK);
    if (tp2 <= tp1) tp2 = roundToTick(tp1 + range * 0.382, MES_TICK);
    if (stopLoss >= entry) stopLoss = roundToTick(entry - range * 0.15, MES_TICK);
  } else {
    if (tp1 >= entry) tp1 = roundToTick(entry - range * 0.236, MES_TICK);
    if (tp2 >= tp1) tp2 = roundToTick(tp1 - range * 0.382, MES_TICK);
    if (stopLoss <= entry) stopLoss = roundToTick(entry + range * 0.15, MES_TICK);
  }

  return {
    direction,
    fibLevel,
    fibRatio: entryRatio,
    actualRetraceRatio,
    entry,
    stopLoss,
    tp1,
    tp2,
    measuredMoveTarget: measuredMove?.target ?? null,
    quality: measuredMove?.quality ?? 55,
    fibResult,
    measuredMove,
  };
}
