import { NextResponse } from "next/server";
import { createAdminClient } from "@/lib/supabase/admin";
import {
  calculateTraditionalPivots,
  pivotLevelsToLines,
  type PivotLine,
} from "@/lib/pivots";

/**
 * MES Pivot Levels API
 *
 * Calculates traditional pivot levels from MES daily data.
 * Returns Daily + Weekly pivots for chart rendering.
 */

export async function GET() {
  try {
    const supabase = createAdminClient();

    // Fetch last 5 daily bars for daily pivots + weekly HLC
    const { data: dailyBars, error } = await supabase
      .from("mes_1d")
      .select("ts, open, high, low, close")
      .order("ts", { ascending: false })
      .limit(5);

    if (error || !dailyBars || dailyBars.length === 0) {
      return NextResponse.json({ pivots: [] });
    }

    const pivots: PivotLine[] = [];

    // Daily pivots from yesterday's bar (index 1, since index 0 is today's partial)
    const yesterday = dailyBars.length > 1 ? dailyBars[1] : dailyBars[0];
    const dailyLevels = calculateTraditionalPivots(
      Number(yesterday.high),
      Number(yesterday.low),
      Number(yesterday.close),
    );
    const dailyStartTime = Math.floor(
      new Date(dailyBars[0].ts).getTime() / 1000,
    );
    const dailyLines = pivotLevelsToLines(dailyLevels, "D", 3).map((p) => ({
      ...p,
      startTime: dailyStartTime,
    }));
    pivots.push(...dailyLines);

    // Weekly pivots from last 5 daily bars
    if (dailyBars.length >= 5) {
      const weekBars = dailyBars.slice(0, 5);
      const weekHigh = Math.max(...weekBars.map((b) => Number(b.high)));
      const weekLow = Math.min(...weekBars.map((b) => Number(b.low)));
      const weekClose = Number(weekBars[0].close);

      const weeklyLevels = calculateTraditionalPivots(
        weekHigh,
        weekLow,
        weekClose,
      );
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
