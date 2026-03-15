import { NextResponse } from "next/server";
import { createAdminClient } from "@/lib/supabase/admin";
import { detectSwings } from "@/lib/swing-detection";
import { detectMeasuredMoves } from "@/lib/measured-move";
import type { CandleData } from "@/lib/types";

export const maxDuration = 60;

// Runs daily at 18:00 UTC on weekdays.
// Scans 1h candles for AB=CD measured move patterns.

export async function GET(request: Request) {
  const cronSecret = process.env.CRON_SECRET;
  if (cronSecret) {
    const auth = request.headers.get("authorization");
    if (auth !== `Bearer ${cronSecret}`) {
      return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
    }
  }

  const startTime = Date.now();
  const supabase = createAdminClient();

  try {
    // Fetch last 200 1h candles (~8 days of market data)
    const { data: bars, error } = await supabase
      .from("mes_1h")
      .select("ts, open, high, low, close")
      .order("ts", { ascending: false })
      .limit(200);

    if (error) throw new Error(`mes_1h query failed: ${error.message}`);
    if (!bars || bars.length < 20) {
      return NextResponse.json({
        skipped: true,
        reason: "insufficient_data",
        bars: bars?.length ?? 0,
      });
    }

    const candles: CandleData[] = bars.reverse().map((b) => ({
      time: Math.floor(new Date(b.ts).getTime() / 1000),
      open: Number(b.open),
      high: Number(b.high),
      low: Number(b.low),
      close: Number(b.close),
    }));

    const { highs, lows } = detectSwings(candles, 5, 5, 50);
    const currentPrice = candles[candles.length - 1].close;
    const measuredMoves = detectMeasuredMoves(highs, lows, currentPrice);

    let rowsWritten = 0;
    for (const mm of measuredMoves) {
      // Map status to signal_status enum
      const dbStatus =
        mm.status === "TARGET_HIT" ? "TP1_HIT" :
        mm.status === "STOPPED_OUT" ? "STOPPED" :
        "ACTIVE";
      const { error: insertError } = await supabase
        .from("measured_moves")
        .insert({
          ts: new Date(mm.pointC.time * 1000).toISOString(),
          symbol_code: "MES",
          direction: mm.direction === "BULLISH" ? "LONG" : "SHORT",
          anchor_price: mm.pointA.price,
          target_price: mm.target,
          retracement_price: mm.pointC.price,
          fib_level: mm.retracementRatio,
          status: dbStatus,
        });
      if (!insertError) rowsWritten++;
    }

    await supabase.from("job_log").insert({
      job_name: "measured-moves",
      status: "OK",
      rows_written: rowsWritten,
      duration_ms: Date.now() - startTime,
    });

    return NextResponse.json({
      success: true,
      candles: candles.length,
      swings: { highs: highs.length, lows: lows.length },
      moves_found: measuredMoves.length,
      rows_written: rowsWritten,
      duration_ms: Date.now() - startTime,
    });
  } catch (e) {
    const message = e instanceof Error ? e.message : "Internal error";
    try {
      await supabase.from("job_log").insert({
        job_name: "measured-moves",
        status: "ERROR",
        error_message: message,
        duration_ms: Date.now() - startTime,
      });
    } catch {
      // ignore
    }
    return NextResponse.json({ error: message }, { status: 500 });
  }
}
