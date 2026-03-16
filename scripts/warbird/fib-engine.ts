import { calculateFibonacciMultiPeriod } from "@/lib/fibonacci";
import { detectMeasuredMoves } from "@/lib/measured-move";
import { detectSwings } from "@/lib/swing-detection";
import { fibExtension, roundToTick } from "@/lib/ta/fibonacci";
import type { CandleData, FibResult, MeasuredMove } from "@/lib/types";
import type { WarbirdBias, WarbirdDirection } from "@/lib/warbird/types";

export interface WarbirdFibGeometry {
  direction: WarbirdDirection;
  fibLevel: number;
  fibRatio: number;
  entry: number;
  stopLoss: number;
  tp1: number;
  tp2: number;
  measuredMoveTarget: number | null;
  quality: number;
  fibResult: FibResult;
  measuredMove: MeasuredMove | null;
}

function ratioPrice(fib: FibResult, ratio: number): number | null {
  const level = fib.levels.find((item) => Math.abs(item.ratio - ratio) < 0.001);
  return level?.price ?? null;
}

function biasToDirection(bias: WarbirdBias): WarbirdDirection {
  return bias === "BEAR" ? "SHORT" : "LONG";
}

function alignMeasuredMove(
  moves: MeasuredMove[],
  direction: WarbirdDirection,
): MeasuredMove | null {
  const alignedDirection = direction === "LONG" ? "BULLISH" : "BEARISH";
  return moves.find((move) => move.direction === alignedDirection && move.status === "ACTIVE")
    ?? moves.find((move) => move.direction === alignedDirection)
    ?? null;
}

export function buildFibGeometry(
  candles: CandleData[],
  bias: WarbirdBias,
): WarbirdFibGeometry | null {
  if (candles.length < 55) return null;

  const ordered = [...candles].sort((a, b) => a.time - b.time);
  const fibResult = calculateFibonacciMultiPeriod(ordered);
  if (!fibResult) return null;

  const currentPrice = ordered[ordered.length - 1].close;
  const { highs, lows } = detectSwings(ordered);
  const measuredMove = alignMeasuredMove(
    detectMeasuredMoves(highs, lows, currentPrice),
    biasToDirection(bias),
  );

  const direction = biasToDirection(bias === "NEUTRAL" ? (fibResult.isBullish ? "BULL" : "BEAR") : bias);
  const entryRatio = 0.5;
  const stopRatio = direction === "LONG" ? 0.786 : 0.786;
  const entry = measuredMove
    ? roundToTick(measuredMove.entry, 0.25)
    : roundToTick(ratioPrice(fibResult, entryRatio) ?? currentPrice, 0.25);
  const fibLevel = roundToTick(ratioPrice(fibResult, entryRatio) ?? entry, 0.25);
  const stopLoss = measuredMove
    ? roundToTick(measuredMove.stop, 0.25)
    : roundToTick(
        ratioPrice(fibResult, stopRatio)
          ?? (direction === "LONG" ? entry - 8 : entry + 8),
        0.25,
      );

  const moveA = measuredMove?.pointA.price ?? fibResult.anchorLow;
  const moveB = measuredMove?.pointB.price ?? fibResult.anchorHigh;
  const moveC = measuredMove?.pointC.price ?? entry;

  const rawTp1 = measuredMove
    ? fibExtension(moveA, moveB, moveC, 1.236)
    : ratioPrice(fibResult, 1.236) ?? entry;
  const rawTp2 = measuredMove
    ? fibExtension(moveA, moveB, moveC, 1.618)
    : ratioPrice(fibResult, 1.618) ?? entry;

  return {
    direction,
    fibLevel,
    fibRatio: entryRatio,
    entry,
    stopLoss,
    tp1: roundToTick(rawTp1, 0.25),
    tp2: roundToTick(rawTp2, 0.25),
    measuredMoveTarget: measuredMove?.target ?? null,
    quality: measuredMove?.quality ?? 55,
    fibResult,
    measuredMove,
  };
}
