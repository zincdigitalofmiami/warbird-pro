/**
 * Auto-Fibonacci Engine — Multi-Period Confluence
 *
 * Ported from ZINC-FUSION-V16 chart logic.
 */

export interface CandleData {
  time: number;
  open: number;
  high: number;
  low: number;
  close: number;
  volume?: number;
}

export interface FibLevel {
  ratio: number;
  price: number;
  label: string;
  color: string;
  isExtension: boolean;
}

export interface FibResult {
  levels: FibLevel[];
  anchorHigh: number;
  anchorLow: number;
  isBullish: boolean;
  anchorHighBarIndex: number;
  anchorLowBarIndex: number;
}

const FIB_COLORS: Record<number, string> = {
  0: "#FFFFFF",
  0.236: "#808080",
  0.382: "#808080",
  0.5: "#FF9800",
  0.618: "#808080",
  0.786: "#808080",
  1.0: "#FFFFFF",
  1.236: "#4CAF50",
  1.618: "#4CAF50",
  2.0: "#4CAF50",
};

const FIB_RATIOS = [0, 0.236, 0.382, 0.5, 0.618, 0.786, 1.0];
const FIB_EXTENSIONS = [1.236, 1.618, 2.0];
const FIB_LOOKBACKS = [8, 13, 21, 34, 55] as const;
const CONFLUENCE_TOLERANCE = 0.001;
const CONFLUENCE_RATIOS = [0.382, 0.5, 0.618];

const FIB_LABELS: Record<number, string> = {
  0: "ZERO",
  0.236: ".236",
  0.382: ".382",
  0.5: "Pivot",
  0.618: ".618",
  0.786: ".786",
  1.0: "1",
  1.236: "TARGET 1",
  1.618: "TARGET 2",
  2.0: "TARGET 3",
};

function buildLevels(anchorHigh: number, anchorLow: number, isBullish: boolean): FibLevel[] {
  const fibRange = anchorHigh - anchorLow;
  const levels: FibLevel[] = [];

  for (const ratio of FIB_RATIOS) {
    const price = isBullish
      ? anchorLow + fibRange * ratio
      : anchorHigh - fibRange * ratio;
    levels.push({
      ratio,
      price,
      label: FIB_LABELS[ratio] || ratio.toString(),
      color: FIB_COLORS[ratio] || "#787b86",
      isExtension: false,
    });
  }

  for (const ratio of FIB_EXTENSIONS) {
    const price = isBullish
      ? anchorLow + fibRange * ratio
      : anchorHigh - fibRange * ratio;
    levels.push({
      ratio,
      price,
      label: FIB_LABELS[ratio] || ratio.toString(),
      color: FIB_COLORS[ratio] || "#787b86",
      isExtension: true,
    });
  }

  return levels;
}

export function calculateFibonacciMultiPeriod(candles: CandleData[]): FibResult | null {
  const n = candles.length;
  if (n < FIB_LOOKBACKS[FIB_LOOKBACKS.length - 1]) {
    return null;
  }

  type PeriodAnchor = {
    period: number;
    high: number;
    low: number;
    highBarIndex: number;
    lowBarIndex: number;
    range: number;
    midLevels: number[];
  };

  const anchors: PeriodAnchor[] = [];

  for (const period of FIB_LOOKBACKS) {
    const startIdx = n - period;
    if (startIdx < 0) continue;

    let high = -Infinity;
    let low = Infinity;
    let highBarIndex = startIdx;
    let lowBarIndex = startIdx;

    for (let i = startIdx; i < n; i++) {
      if (candles[i].high > high) {
        high = candles[i].high;
        highBarIndex = i;
      }
      if (candles[i].low < low) {
        low = candles[i].low;
        lowBarIndex = i;
      }
    }

    const range = high - low;
    if (range <= 0) continue;

    const midLevels = CONFLUENCE_RATIOS.map((r) => low + range * r);
    anchors.push({ period, high, low, highBarIndex, lowBarIndex, range, midLevels });
  }

  if (anchors.length === 0) return null;

  let bestAnchor = anchors[anchors.length - 1];
  let bestScore = -1;

  for (let a = 0; a < anchors.length; a++) {
    const anchor = anchors[a];
    const tolerance = anchor.range * CONFLUENCE_TOLERANCE;

    let confluenceCount = 0;
    for (let b = 0; b < anchors.length; b++) {
      if (a === b) continue;
      for (const levelA of anchor.midLevels) {
        for (const levelB of anchors[b].midLevels) {
          if (Math.abs(levelA - levelB) <= tolerance) {
            confluenceCount++;
          }
        }
      }
    }

    const score = confluenceCount * anchor.range;
    const sameScore = Math.abs(score - bestScore) < 1e-9;
    const widerRange = anchor.range > bestAnchor.range;
    const longerWindow = anchor.period > bestAnchor.period;
    if (score > bestScore || (sameScore && (widerRange || (Math.abs(anchor.range - bestAnchor.range) < 1e-9 && longerWindow)))) {
      bestScore = score;
      bestAnchor = anchor;
    }
  }

  const lastClose = candles[n - 1].close;
  const midpoint = bestAnchor.low + bestAnchor.range * 0.5;
  const isBullish = lastClose >= midpoint;
  const levels = buildLevels(bestAnchor.high, bestAnchor.low, isBullish);

  return {
    levels,
    anchorHigh: bestAnchor.high,
    anchorLow: bestAnchor.low,
    isBullish,
    anchorHighBarIndex: bestAnchor.highBarIndex,
    anchorLowBarIndex: bestAnchor.lowBarIndex,
  };
}
