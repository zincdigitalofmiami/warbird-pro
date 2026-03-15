import { NextResponse } from "next/server";
import { createAdminClient } from "@/lib/supabase/admin";
import { isMarketOpen } from "@/lib/market-hours";
import { calculateFibonacciMultiPeriod } from "@/lib/fibonacci";
import { detectSwings } from "@/lib/swing-detection";
import { detectMeasuredMoves } from "@/lib/measured-move";
import { detectSetups, type WarbirdSetup } from "@/lib/setup-engine";
import type { CandleData } from "@/lib/types";

export const maxDuration = 60;

// Runs every 15 min on weekdays: :03, :18, :33, :48
// Fetches recent 15m candles, runs the Warbird state machine,
// and upserts any new or updated setups to warbird_setups.

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

  // Skip if market is closed (unless force=1)
  const url = new URL(request.url);
  const force = url.searchParams.get("force") === "1";
  if (!force && !isMarketOpen()) {
    return NextResponse.json({ skipped: true, reason: "market_closed" });
  }

  try {
    // Fetch last 200 15m candles (~50 hours of market data)
    const { data: bars, error } = await supabase
      .from("mes_15m")
      .select("ts, open, high, low, close")
      .order("ts", { ascending: false })
      .limit(200);

    if (error) throw new Error(`mes_15m query failed: ${error.message}`);
    if (!bars || bars.length < 20) {
      return NextResponse.json({ skipped: true, reason: "insufficient_data", bars: bars?.length ?? 0 });
    }

    // Convert to CandleData (chronological order)
    const candles: CandleData[] = bars
      .reverse()
      .map((b) => ({
        time: Math.floor(new Date(b.ts).getTime() / 1000),
        open: Number(b.open),
        high: Number(b.high),
        low: Number(b.low),
        close: Number(b.close),
      }));

    // Run Fibonacci multi-period analysis
    const fibResult = calculateFibonacciMultiPeriod(candles);
    if (!fibResult) {
      return NextResponse.json({ skipped: true, reason: "no_fib_result" });
    }

    // Detect swings and measured moves
    const { highs, lows } = detectSwings(candles);
    const currentPrice = candles[candles.length - 1].close;
    const measuredMoves = detectMeasuredMoves(highs, lows, currentPrice);

    // Run the Warbird state machine
    const setups = detectSetups(candles, fibResult, measuredMoves);

    // Filter to only GO_FIRED, TOUCHED, and HOOKED — these are worth persisting
    const persistable = setups.filter(
      (s) => s.phase === 'GO_FIRED' || s.phase === 'TOUCHED' || s.phase === 'HOOKED'
    );

    let rowsWritten = 0;
    for (const setup of persistable) {
      const row = setupToRow(setup);
      const { error: insertError } = await supabase
        .from("warbird_setups")
        .insert(row);
      if (!insertError) rowsWritten++;
    }

    // Insert active measured moves
    let mmWritten = 0;
    const activeMoves = measuredMoves.filter(
      (m) => m.status === "ACTIVE" || m.status === "FORMING"
    );
    for (const mm of activeMoves) {
      const { error: mmError } = await supabase.from("measured_moves").insert({
        ts: new Date(mm.pointC.time * 1000).toISOString(),
        symbol_code: "MES",
        direction: mm.direction === "BULLISH" ? "LONG" : "SHORT",
        anchor_price: mm.pointA.price,
        target_price: mm.target,
        retracement_price: mm.pointC.price,
        fib_level: mm.retracementRatio,
        status: mm.status === "FORMING" ? "ACTIVE" : "ACTIVE",
      });
      if (!mmError) mmWritten++;
    }

    await supabase.from("job_log").insert({
      job_name: "detect-setups",
      status: "OK",
      rows_written: rowsWritten + mmWritten,
      duration_ms: Date.now() - startTime,
    });

    return NextResponse.json({
      success: true,
      candles: candles.length,
      fib_direction: fibResult.isBullish ? "BULL" : "BEAR",
      setups_total: setups.length,
      setups_persisted: rowsWritten,
      measured_moves: activeMoves.length,
      mm_persisted: mmWritten,
      duration_ms: Date.now() - startTime,
    });
  } catch (e) {
    const message = e instanceof Error ? e.message : "Internal error";
    try {
      await supabase.from("job_log").insert({
        job_name: "detect-setups",
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

function setupToRow(setup: WarbirdSetup) {
  return {
    ts: new Date((setup.goTime ?? setup.hookTime ?? setup.touchTime ?? setup.createdAt) * 1000).toISOString(),
    symbol_code: "MES",
    timeframe: "M15",
    direction: setup.direction,
    phase: setup.phase,
    entry_price: setup.entry ?? null,
    stop_loss: setup.stopLoss ?? null,
    tp1: setup.tp1 ?? null,
    tp2: setup.tp2 ?? null,
    confidence: setup.confidence ?? null,
    pivot_level: setup.pivotLevel ?? setup.fibLevel,
    pivot_type: setup.pivotType ?? `fib_${setup.fibRatio}`,
    measured_move_target: setup.measuredMoveTarget ?? null,
  };
}
