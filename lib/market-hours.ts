/**
 * CME Globex Market Hours — MES (Micro E-mini S&P 500)
 *
 * Trading hours (Central Time):
 *   Sunday 5:00 PM – Friday 4:00 PM CT
 *   Daily maintenance break: 4:00 PM – 5:00 PM CT (Mon–Thu)
 *
 * CT offset changes with daylight saving:
 *   CST (Nov–Mar): UTC-6  → open 23:00 UTC, close 22:00 UTC, break 22:00–23:00
 *   CDT (Mar–Nov): UTC-5  → open 22:00 UTC, close 21:00 UTC, break 21:00–22:00
 *
 * We use America/Chicago to handle this correctly.
 */

// Get Central Time components from a Date
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

/**
 * Returns true if the given UTC timestamp falls outside CME Globex hours.
 * (Weekend or daily maintenance break)
 */
export function isWeekendBar(ts: number): boolean {
  const d = new Date(ts * 1000);
  const { day, hour } = getCentralTime(d);

  // Saturday all day
  if (day === 6) return true;
  // Sunday before 5:00 PM CT (17:00)
  if (day === 0 && hour < 17) return true;
  // Friday after 4:00 PM CT (16:00)
  if (day === 5 && hour >= 16) return true;

  return false;
}

/**
 * Returns true if the market is currently open (right now).
 * Includes daily maintenance break check.
 */
export function isMarketOpen(): boolean {
  const { day, hour } = getCentralTime(new Date());

  // Saturday all day — closed
  if (day === 6) return false;
  // Sunday before 5:00 PM CT — closed
  if (day === 0 && hour < 17) return false;
  // Friday after 4:00 PM CT — closed
  if (day === 5 && hour >= 16) return false;

  // Daily maintenance break: 4:00 PM – 5:00 PM CT (Mon–Thu)
  if (day >= 1 && day <= 4 && hour === 16) return false;

  return true;
}

/**
 * Returns the next market open time as a Date.
 */
export function getNextMarketOpen(): Date {
  const now = new Date();
  const { day, hour } = getCentralTime(now);

  // Calculate UTC offset for CT right now
  // We do this by comparing UTC hour to CT hour
  const utcHour = now.getUTCHours();
  const ctHour = hour;
  let ctOffset = utcHour - ctHour;
  if (ctOffset < 0) ctOffset += 24;
  // ctOffset is 5 (CDT) or 6 (CST)

  const next = new Date(now);
  next.setUTCMinutes(0, 0, 0);

  // Daily maintenance break (4 PM CT, Mon-Thu) — opens at 5 PM CT
  if (day >= 1 && day <= 4 && hour === 16) {
    next.setUTCHours(17 + ctOffset);
    return next;
  }

  // Friday after close → Sunday 5 PM CT
  if (day === 5 && hour >= 16) {
    next.setUTCDate(next.getUTCDate() + 2);
    next.setUTCHours(17 + ctOffset);
    return next;
  }

  // Saturday → Sunday 5 PM CT
  if (day === 6) {
    next.setUTCDate(next.getUTCDate() + 1);
    next.setUTCHours(17 + ctOffset);
    return next;
  }

  // Sunday before open → 5 PM CT today
  if (day === 0 && hour < 17) {
    next.setUTCHours(17 + ctOffset);
    return next;
  }

  // Market is open
  return now;
}

/**
 * Floor a unix timestamp to the start of its 1-minute bar.
 */
export function floorToMinute(ts: number): number {
  return Math.floor(ts / 60) * 60;
}

/**
 * Floor a unix timestamp to the start of its 15-minute bar.
 */
export function floorTo15m(ts: number): number {
  return Math.floor(ts / 900) * 900;
}
