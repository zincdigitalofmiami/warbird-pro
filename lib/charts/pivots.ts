/**
 * Client-side pivot calculation from chart bar data.
 *
 * Copies V15 aggregation logic exactly:
 * - Aggregates intraday bars into D/W/M/Y periods
 * - Calculates traditional pivots from the prior completed period
 * - Returns PivotLine[] for chart rendering
 *
 * Re-exports types from lib/pivots.ts for convenience.
 */

import {
  calculateTraditionalPivots,
  pivotLevelsToLines,
  type PivotLine,
  type PivotLevels,
  type PivotTimeframe,
} from "@/lib/pivots";

export type { PivotLine, PivotLevels, PivotTimeframe };

interface PivotSourceBar {
  timestamp: string;
  high: number;
  low: number;
  close: number;
}

interface PeriodAggregate {
  key: string;
  startTime: string;
  high: number;
  low: number;
  close: number;
}

function toDateKey(value: string): string {
  const match = String(value).match(/^(\d{4}-\d{2}-\d{2})/);
  if (match) return match[1];

  const dt = new Date(value);
  if (Number.isNaN(dt.getTime())) return value;
  return dt.toISOString().slice(0, 10);
}

function parseDateKey(value: string): Date {
  return new Date(`${toDateKey(value)}T00:00:00Z`);
}

function toKey(value: Date): string {
  return value.toISOString().slice(0, 10);
}

function weekStartKey(value: string): string {
  const dt = parseDateKey(value);
  const day = dt.getUTCDay() || 7;
  dt.setUTCDate(dt.getUTCDate() - day + 1);
  return toKey(dt);
}

function monthStartKey(value: string): string {
  const dt = parseDateKey(value);
  dt.setUTCDate(1);
  return toKey(dt);
}

function yearStartKey(value: string): string {
  const dt = parseDateKey(value);
  dt.setUTCMonth(0, 1);
  return toKey(dt);
}

function aggregatePeriods(
  bars: PivotSourceBar[],
  keyForBar: (timestamp: string) => string,
): PeriodAggregate[] {
  const periods: PeriodAggregate[] = [];

  for (const bar of bars) {
    const key = keyForBar(bar.timestamp);
    const previous = periods[periods.length - 1];

    if (!previous || previous.key !== key) {
      periods.push({
        key,
        startTime: toDateKey(bar.timestamp),
        high: bar.high,
        low: bar.low,
        close: bar.close,
      });
      continue;
    }

    previous.high = Math.max(previous.high, bar.high);
    previous.low = Math.min(previous.low, bar.low);
    previous.close = bar.close;
  }

  return periods;
}

function buildPeriodPivotLines(
  periods: PeriodAggregate[],
  timeframe: PivotTimeframe,
  maxLevel: number,
): PivotLine[] {
  if (periods.length < 2) return [];

  const source = periods[periods.length - 2];
  const current = periods[periods.length - 1];

  return pivotLevelsToLines(
    calculateTraditionalPivots(source.high, source.low, source.close),
    timeframe,
    maxLevel,
  ).map((line) => ({
    ...line,
    startTime: current.startTime,
  }));
}

/**
 * Build pivot lines from an array of OHLCV bars.
 * Returns W (max R/S 2), M (max R/S 2), Y (max R/S 1) pivot lines.
 * Requires at least 2 bars to produce any pivots.
 */
export function buildPivotLines(
  bars: PivotSourceBar[],
): PivotLine[] {
  if (bars.length < 2) return [];

  const sortedBars = [...bars].sort((a, b) =>
    toDateKey(a.timestamp).localeCompare(toDateKey(b.timestamp)),
  );
  const weekly = buildPeriodPivotLines(
    aggregatePeriods(sortedBars, (timestamp) => weekStartKey(timestamp)),
    "W",
    2,
  );
  const monthly = buildPeriodPivotLines(
    aggregatePeriods(sortedBars, (timestamp) => monthStartKey(timestamp)),
    "M",
    2,
  );
  const yearly = buildPeriodPivotLines(
    aggregatePeriods(sortedBars, (timestamp) => yearStartKey(timestamp)),
    "Y",
    1,
  );

  return [...weekly, ...monthly, ...yearly];
}
