import { NextResponse } from "next/server";
import { createClient } from "@/lib/supabase/server";
import {
  calculateTraditionalPivots,
  pivotLevelsToLines,
  type PivotLine,
} from "@/lib/pivots";

/**
 * MES Pivot Levels API
 *
 * Calculates traditional pivot levels from MES 15m data aggregated to daily.
 * Falls back to mes_1d if available, otherwise aggregates from mes_15m.
 * Returns Daily + Weekly pivots for chart rendering.
 */

interface DailyBar {
  date: string;
  open: number;
  high: number;
  low: number;
  close: number;
  ts: number;
}

export async function GET() {
  try {
    const supabase = await createClient();
    const { data: authData, error: authError } = await supabase.auth.getClaims();

    if (authError || !authData?.claims) {
      return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
    }

    // Try mes_1d first
    const { data: dailyBars, error: dailyError } = await supabase
      .from("mes_1d")
      .select("ts, open, high, low, close")
      .order("ts", { ascending: false })
      .limit(5);

    let bars: DailyBar[] = [];

    if (!dailyError && dailyBars && dailyBars.length >= 2) {
      bars = dailyBars.map((b) => ({
        date: new Date(b.ts).toISOString().slice(0, 10),
        open: Number(b.open),
        high: Number(b.high),
        low: Number(b.low),
        close: Number(b.close),
        ts: Math.floor(new Date(b.ts).getTime() / 1000),
      }));
    } else {
      // Fallback: aggregate from mes_15m (last 7 days of 15m bars → daily)
      const cutoff = new Date(Date.now() - 7 * 24 * 60 * 60 * 1000).toISOString();
      const { data: bars15m, error: err15m } = await supabase
        .from("mes_15m")
        .select("ts, open, high, low, close")
        .gte("ts", cutoff)
        .order("ts", { ascending: true })
        .limit(2000);

      if (err15m || !bars15m || bars15m.length === 0) {
        return NextResponse.json({ pivots: [] });
      }

      // Group by date
      const byDate = new Map<string, { open: number; high: number; low: number; close: number; ts: number }>();
      for (const b of bars15m) {
        const dt = new Date(b.ts);
        const dateKey = dt.toISOString().slice(0, 10);
        const o = Number(b.open);
        const h = Number(b.high);
        const l = Number(b.low);
        const c = Number(b.close);
        const existing = byDate.get(dateKey);
        if (!existing) {
          byDate.set(dateKey, { open: o, high: h, low: l, close: c, ts: Math.floor(dt.getTime() / 1000) });
        } else {
          existing.high = Math.max(existing.high, h);
          existing.low = Math.min(existing.low, l);
          existing.close = c;
        }
      }

      bars = Array.from(byDate.entries())
        .map(([date, b]) => ({ date, ...b }))
        .sort((a, b) => b.ts - a.ts); // newest first
    }

    if (bars.length === 0) {
      return NextResponse.json({ pivots: [] });
    }

    const pivots: PivotLine[] = [];

    // Daily pivots from yesterday's bar (index 1, since index 0 is today's partial)
    const yesterday = bars.length > 1 ? bars[1] : bars[0];
    const dailyLevels = calculateTraditionalPivots(
      yesterday.high,
      yesterday.low,
      yesterday.close,
    );
    const dailyStartTime = bars[0].ts;
    const dailyLines = pivotLevelsToLines(dailyLevels, "D", 3).map((p) => ({
      ...p,
      startTime: dailyStartTime,
    }));
    pivots.push(...dailyLines);

    // Weekly pivots from last 5 daily bars
    if (bars.length >= 5) {
      const weekBars = bars.slice(0, 5);
      const weekHigh = Math.max(...weekBars.map((b) => b.high));
      const weekLow = Math.min(...weekBars.map((b) => b.low));
      const weekClose = weekBars[0].close;

      const weeklyLevels = calculateTraditionalPivots(weekHigh, weekLow, weekClose);
      const weeklyLines = pivotLevelsToLines(weeklyLevels, "W", 2);
      pivots.push(...weeklyLines);
    }

    return NextResponse.json({ pivots });
  } catch (e) {
    return NextResponse.json(
      { error: e instanceof Error ? e.message : "Internal error" },
      { status: 500 },
    );
  }
}
