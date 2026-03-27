// CME equity index futures auto-roll.
// Ported from lib/contract-roll.ts — identical logic, no Node.js APIs used.

const QUARTERS = [
  { month: 3, code: "H" },
  { month: 6, code: "M" },
  { month: 9, code: "U" },
  { month: 12, code: "Z" },
] as const;

const ROLL_DAYS_BEFORE_EXPIRY = 8;

function thirdFriday(year: number, month: number): Date {
  const first = new Date(Date.UTC(year, month - 1, 1));
  const dayOfWeek = first.getUTCDay();
  const firstFriday = 1 + ((5 - dayOfWeek + 7) % 7);
  return new Date(Date.UTC(year, month - 1, firstFriday + 14));
}

export function activeMesContract(now?: Date): string {
  const today = now ?? new Date();
  const todayMs = Date.UTC(
    today.getUTCFullYear(),
    today.getUTCMonth(),
    today.getUTCDate(),
  );

  const schedule: Array<{ rollMs: number; symbol: string }> = [];

  for (let y = today.getUTCFullYear() - 1; y <= today.getUTCFullYear() + 1; y++) {
    for (let qi = 0; qi < QUARTERS.length; qi++) {
      const exp = thirdFriday(y, QUARTERS[qi].month);
      const rollMs = exp.getTime() - ROLL_DAYS_BEFORE_EXPIRY * 86_400_000;
      const ni = (qi + 1) % 4;
      const ny = ni === 0 ? y + 1 : y;
      schedule.push({ rollMs, symbol: `MES${QUARTERS[ni].code}${ny % 10}` });
    }
  }

  schedule.sort((a, b) => a.rollMs - b.rollMs);

  let active = schedule[0].symbol;
  for (const entry of schedule) {
    if (entry.rollMs <= todayMs) {
      active = entry.symbol;
    } else {
      break;
    }
  }
  return active;
}

export function getContractSegments(
  start: Date,
  end: Date,
): Array<{ start: Date; end: Date; symbol: string }> {
  const segments: Array<{ start: Date; end: Date; symbol: string }> = [];
  let cursor = new Date(start);

  while (cursor < end) {
    const symbol = activeMesContract(cursor);

    let segEnd = new Date(end);
    const check = new Date(cursor);
    while (check < end) {
      check.setUTCDate(check.getUTCDate() + 1);
      if (check >= end) break;
      if (activeMesContract(check) !== symbol) {
        segEnd = new Date(check);
        break;
      }
    }

    segments.push({ start: new Date(cursor), end: segEnd, symbol });
    cursor = segEnd;
  }

  return segments;
}
