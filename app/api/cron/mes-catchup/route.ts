import { NextResponse } from "next/server";
import { createAdminClient } from "@/lib/supabase/admin";
import { isMarketOpen, isWeekendBar, floorToMinute, floorTo15m } from "@/lib/market-hours";
import { fetchOhlcv, type OhlcvBar } from "@/lib/ingestion/databento";

export const maxDuration = 60;

// Runs every 5 minutes via Vercel Cron.
// Fills gaps in mes_1m from Databento Historical API.
// This is insurance for sidecar downtime — NOT the primary data path.

export async function GET(request: Request) {
  const cronSecret = process.env.CRON_SECRET;
  if (cronSecret) {
    const auth = request.headers.get("authorization");
    if (auth !== `Bearer ${cronSecret}`) {
      return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
    }
  }

  // Skip market-hours check if manual backfill (?days=N or ?force=1)
  const reqUrl = new URL(request.url);
  const isManual = reqUrl.searchParams.has("days") || reqUrl.searchParams.has("force");
  if (!isManual && !isMarketOpen()) {
    return NextResponse.json({ skipped: true, reason: "market_closed" });
  }

  const startTime = Date.now();
  const supabase = createAdminClient();

  try {
    // Find the latest 1m bar we have
    const { data: latest, error: latestErr } = await supabase
      .from("mes_1m")
      .select("ts")
      .order("ts", { ascending: false })
      .limit(1)
      .single();

    if (latestErr && latestErr.code !== "PGRST116") {
      throw new Error(`Failed to query mes_1m: ${latestErr.message}`);
    }

    const now = new Date();
    // ?days=7 for initial backfill, otherwise 30 min gap fill
    const daysParam = parseInt(reqUrl.searchParams.get("days") || "0", 10);

    let gapStart: Date;
    if (latest?.ts) {
      gapStart = new Date(latest.ts);
    } else if (daysParam > 0) {
      // Initial backfill: go back N days (max 14)
      const days = Math.min(daysParam, 14);
      gapStart = new Date(now.getTime() - days * 24 * 60 * 60 * 1000);
    } else {
      // Default: 7 days when table is empty
      gapStart = new Date(now.getTime() - 7 * 24 * 60 * 60 * 1000);
    }

    // Databento historical API has a short delay; 5 min buffer is plenty
    const gapEnd = new Date(now.getTime() - 5 * 60 * 1000);

    // Nothing to fill if gap window is too small
    if (gapEnd.getTime() - gapStart.getTime() < 60_000) {
      return NextResponse.json({
        success: true,
        gaps_filled: 0,
        reason: "no_gap",
        duration_ms: Date.now() - startTime,
      });
    }

    const bars = await fetchOhlcv({
      dataset: "GLBX.MDP3",
      symbol: "MES.c.0",
      stypeIn: "continuous",
      start: gapStart.toISOString(),
      end: gapEnd.toISOString(),
      schema: "ohlcv-1m",
    });

    // Filter out weekend bars
    const validBars = bars.filter((b) => !isWeekendBar(b.time));

    if (validBars.length === 0) {
      return NextResponse.json({
        success: true,
        gaps_filled: 0,
        reason: "no_data",
        duration_ms: Date.now() - startTime,
      });
    }

    // Upsert 1m bars
    const mes1mRows = validBars.map((b) => ({
      ts: new Date(b.time * 1000).toISOString(),
      open: b.open,
      high: b.high,
      low: b.low,
      close: b.close,
      volume: b.volume,
    }));

    // Batch upsert in chunks of 100
    for (let i = 0; i < mes1mRows.length; i += 100) {
      const chunk = mes1mRows.slice(i, i + 100);
      const { error } = await supabase
        .from("mes_1m")
        .upsert(chunk, { onConflict: "ts" });
      if (error) throw new Error(`mes_1m upsert failed: ${error.message}`);
    }

    // Aggregate to 15m and upsert
    const fifteenMinBars = aggregateTo15m(validBars);
    if (fifteenMinBars.length > 0) {
      const mes15mRows = fifteenMinBars.map((b) => ({
        ts: new Date(b.time * 1000).toISOString(),
        open: b.open,
        high: b.high,
        low: b.low,
        close: b.close,
        volume: b.volume,
      }));

      const { error } = await supabase
        .from("mes_15m")
        .upsert(mes15mRows, { onConflict: "ts" });
      if (error) throw new Error(`mes_15m upsert failed: ${error.message}`);
    }

    // Log to job_log
    await supabase.from("job_log").insert({
      job_name: "mes-catchup",
      status: "OK",
      rows_written: validBars.length,
      duration_ms: Date.now() - startTime,
    });

    return NextResponse.json({
      success: true,
      gaps_filled: validBars.length,
      bars_15m: fifteenMinBars.length,
      duration_ms: Date.now() - startTime,
    });
  } catch (e) {
    const message = e instanceof Error ? e.message : "Internal error";

    // Best-effort error logging — don't fail on logging failure
    try {
      await supabase.from("job_log").insert({
        job_name: "mes-catchup",
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

// Aggregate 1m bars into 15m bars
function aggregateTo15m(bars: OhlcvBar[]): OhlcvBar[] {
  const buckets = new Map<number, OhlcvBar>();

  for (const bar of bars) {
    const key = floorTo15m(bar.time);
    const existing = buckets.get(key);
    if (!existing) {
      buckets.set(key, { ...bar, time: key });
    } else {
      existing.high = Math.max(existing.high, bar.high);
      existing.low = Math.min(existing.low, bar.low);
      existing.close = bar.close;
      existing.volume += bar.volume;
    }
  }

  return Array.from(buckets.values()).sort((a, b) => a.time - b.time);
}
