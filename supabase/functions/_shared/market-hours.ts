// CME Globex Market Hours — MES (Micro E-mini S&P 500)
// Ported from lib/market-hours.ts — identical logic, no Node.js APIs used.

function getCentralTime(d: Date): { day: number; hour: number; minute: number } {
  const ct = new Intl.DateTimeFormat("en-US", {
    timeZone: "America/Chicago",
    hour: "numeric",
    minute: "numeric",
    weekday: "short",
    hour12: false,
  }).formatToParts(d);

  const dayStr = ct.find((p) => p.type === "weekday")?.value ?? "";
  const hour = parseInt(ct.find((p) => p.type === "hour")?.value ?? "0", 10);
  const minute = parseInt(ct.find((p) => p.type === "minute")?.value ?? "0", 10);

  const dayMap: Record<string, number> = {
    Sun: 0, Mon: 1, Tue: 2, Wed: 3, Thu: 4, Fri: 5, Sat: 6,
  };
  const day = dayMap[dayStr] ?? d.getUTCDay();

  return { day, hour, minute };
}

export function isWeekendBar(ts: number): boolean {
  const d = new Date(ts * 1000);
  const { day, hour } = getCentralTime(d);

  if (day === 6) return true;
  if (day === 0 && hour < 17) return true;
  if (day === 5 && hour >= 16) return true;

  return false;
}

export function isMarketOpen(): boolean {
  const { day, hour } = getCentralTime(new Date());

  if (day === 6) return false;
  if (day === 0 && hour < 17) return false;
  if (day === 5 && hour >= 16) return false;
  if (day >= 1 && day <= 4 && hour === 16) return false;

  return true;
}

export function floorTo15m(ts: number): number {
  return Math.floor(ts / 900) * 900;
}
