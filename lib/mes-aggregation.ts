import type { OhlcvBar } from "@/lib/ingestion/databento";

const CHICAGO_TIME_ZONE = "America/Chicago";

const chicagoFormatter = new Intl.DateTimeFormat("en-US", {
  timeZone: CHICAGO_TIME_ZONE,
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
  hour: "2-digit",
  minute: "2-digit",
  second: "2-digit",
  hour12: false,
});

type ChicagoParts = {
  year: number;
  month: number;
  day: number;
  hour: number;
  minute: number;
  second: number;
};

function getChicagoParts(date: Date): ChicagoParts {
  const parts = chicagoFormatter.formatToParts(date);
  const read = (type: Intl.DateTimeFormatPartTypes) =>
    Number(parts.find((part) => part.type === type)?.value ?? "0");

  return {
    year: read("year"),
    month: read("month"),
    day: read("day"),
    hour: read("hour"),
    minute: read("minute"),
    second: read("second"),
  };
}

function chicagoLocalToUtc(parts: ChicagoParts): Date {
  // Start near the expected UTC time, then correct using the formatted local view.
  let candidate = new Date(
    Date.UTC(
      parts.year,
      parts.month - 1,
      parts.day,
      parts.hour + 6,
      parts.minute,
      parts.second,
    ),
  );

  for (let attempt = 0; attempt < 4; attempt++) {
    const actual = getChicagoParts(candidate);
    const desiredLocalMs = Date.UTC(
      parts.year,
      parts.month - 1,
      parts.day,
      parts.hour,
      parts.minute,
      parts.second,
    );
    const actualLocalMs = Date.UTC(
      actual.year,
      actual.month - 1,
      actual.day,
      actual.hour,
      actual.minute,
      actual.second,
    );
    const diffMs = desiredLocalMs - actualLocalMs;

    if (diffMs === 0) {
      return candidate;
    }

    candidate = new Date(candidate.getTime() + diffMs);
  }

  return candidate;
}

function floorInterval(timeSec: number, intervalSec: number): number {
  return Math.floor(timeSec / intervalSec) * intervalSec;
}

export function getMesSessionDayStart(timeSec: number): number {
  const chicago = getChicagoParts(new Date(timeSec * 1000));
  const localMidnight = new Date(
    Date.UTC(chicago.year, chicago.month - 1, chicago.day),
  );

  if (chicago.hour < 17) {
    localMidnight.setUTCDate(localMidnight.getUTCDate() - 1);
  }

  const sessionStartUtc = chicagoLocalToUtc({
    year: localMidnight.getUTCFullYear(),
    month: localMidnight.getUTCMonth() + 1,
    day: localMidnight.getUTCDate(),
    hour: 17,
    minute: 0,
    second: 0,
  });

  return Math.floor(sessionStartUtc.getTime() / 1000);
}

function aggregateBars(
  bars: OhlcvBar[],
  bucketForTime: (timeSec: number) => number,
): OhlcvBar[] {
  const buckets = new Map<number, OhlcvBar>();

  for (const bar of bars) {
    const bucketTime = bucketForTime(bar.time);
    const existing = buckets.get(bucketTime);

    if (!existing) {
      buckets.set(bucketTime, { ...bar, time: bucketTime });
      continue;
    }

    existing.high = Math.max(existing.high, bar.high);
    existing.low = Math.min(existing.low, bar.low);
    existing.close = bar.close;
    existing.volume += bar.volume;
  }

  return Array.from(buckets.values()).sort((a, b) => a.time - b.time);
}

export function aggregateMesTimeframes(bars: OhlcvBar[]): {
  bars15m: OhlcvBar[];
  bars1h: OhlcvBar[];
  bars4h: OhlcvBar[];
  bars1d: OhlcvBar[];
} {
  return {
    bars15m: aggregateBars(bars, (timeSec) => floorInterval(timeSec, 900)),
    bars1h: aggregateBars(bars, (timeSec) => floorInterval(timeSec, 3600)),
    bars4h: aggregateBars(bars, (timeSec) => floorInterval(timeSec, 14_400)),
    bars1d: aggregateBars(bars, getMesSessionDayStart),
  };
}
