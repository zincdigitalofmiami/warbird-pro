import { NextResponse } from "next/server";
import { createAdminClient } from "@/lib/supabase/admin";
import { isMarketOpen, isWeekendBar } from "@/lib/market-hours";
import { fetchOhlcv, type OhlcvBar } from "@/lib/ingestion/databento";
import { aggregateMesTimeframes } from "@/lib/mes-aggregation";
import { activeMesContract } from "@/lib/contract-roll";

export const maxDuration = 60;

// Primary MES data path. Runs every 5 minutes via Vercel Cron.
// Fetches ohlcv-1m + ohlcv-1h from Databento Historical API → Supabase.
// Uses explicit contract symbols (e.g. MESM6) to match TradingView roll timing.

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
    const now = new Date();
    const daysParam = parseInt(reqUrl.searchParams.get("days") || "0", 10);

    let gapStart: Date;
    if (daysParam > 0) {
      // Forced backfill: go back N days (max 14), overwriting existing data
      const days = Math.min(daysParam, 14);
      gapStart = new Date(now.getTime() - days * 24 * 60 * 60 * 1000);
    } else {
      // Normal cron: find the latest 1m bar and fill from there
      const { data: latest, error: latestErr } = await supabase
        .from("mes_1m")
        .select("ts")
        .order("ts", { ascending: false })
        .limit(1)
        .single();

      if (latestErr && latestErr.code !== "PGRST116") {
        throw new Error(`Failed to query mes_1m: ${latestErr.message}`);
      }

      if (latest?.ts) {
        gapStart = new Date(latest.ts);
      } else {
        // Empty table: default 7 days
        gapStart = new Date(now.getTime() - 7 * 24 * 60 * 60 * 1000);
      }
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

    const mesSymbol = activeMesContract();

    const bars1m = await fetchOhlcv({
      dataset: "GLBX.MDP3",
      symbol: mesSymbol,
      stypeIn: "raw_symbol",
      start: gapStart.toISOString(),
      end: gapEnd.toISOString(),
      schema: "ohlcv-1m",
    });

    const bars1h = await fetchOhlcv({
      dataset: "GLBX.MDP3",
      symbol: mesSymbol,
      stypeIn: "raw_symbol",
      start: gapStart.toISOString(),
      end: gapEnd.toISOString(),
      schema: "ohlcv-1h",
    });

    // Filter out weekend bars
    const validBars1m = bars1m.filter((b) => !isWeekendBar(b.time));
    const validBars1h = bars1h.filter((b) => !isWeekendBar(b.time));

    if (validBars1m.length === 0 && validBars1h.length === 0) {
      return NextResponse.json({
        success: true,
        gaps_filled: 0,
        reason: "no_data",
        duration_ms: Date.now() - startTime,
      });
    }

    // Upsert 1m bars
    const mes1mRows = validBars1m.map((b) => ({
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

    const mes1hRows = validBars1h.map((b) => ({
      ts: new Date(b.time * 1000).toISOString(),
      open: b.open,
      high: b.high,
      low: b.low,
      close: b.close,
      volume: b.volume,
    }));

    if (mes1hRows.length > 0) {
      const { error } = await supabase
        .from("mes_1h")
        .upsert(mes1hRows, { onConflict: "ts" });
      if (error) throw new Error(`mes_1h upsert failed: ${error.message}`);
    }

    const { bars15m, bars4h, bars1d } = aggregateMesTimeframes(validBars1m, validBars1h);

    const aggregatedTables = [
      ["mes_15m", bars15m],
      ["mes_4h", bars4h],
      ["mes_1d", bars1d],
    ] as const;

    let aggregatedRows = 0;
    for (const [tableName, tableBars] of aggregatedTables) {
      if (tableBars.length === 0) continue;

      const rows = tableBars.map((bar) => ({
        ts: new Date(bar.time * 1000).toISOString(),
        open: bar.open,
        high: bar.high,
        low: bar.low,
        close: bar.close,
        volume: bar.volume,
      }));

      const { error } = await supabase
        .from(tableName)
        .upsert(rows, { onConflict: "ts" });
      if (error) throw new Error(`${tableName} upsert failed: ${error.message}`);

      aggregatedRows += rows.length;
    }

    // Log to job_log
    await supabase.from("job_log").insert({
      job_name: "mes-catchup",
      status: "SUCCESS",
      rows_affected: validBars1m.length + mes1hRows.length + aggregatedRows,
      duration_ms: Date.now() - startTime,
    });

    return NextResponse.json({
      success: true,
      gaps_filled: validBars1m.length,
      bars_15m: bars15m.length,
      bars_1h: mes1hRows.length,
      bars_4h: bars4h.length,
      bars_1d: bars1d.length,
      duration_ms: Date.now() - startTime,
    });
  } catch (e) {
    const message = e instanceof Error ? e.message : "Internal error";

    // Best-effort error logging — don't fail on logging failure
    try {
      await supabase.from("job_log").insert({
        job_name: "mes-catchup",
        status: "FAILED",
        error_message: message,
        duration_ms: Date.now() - startTime,
      });
    } catch {
      // ignore
    }

    return NextResponse.json({ error: message }, { status: 500 });
  }
}
