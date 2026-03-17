import { NextResponse } from "next/server";
import { createAdminClient } from "@/lib/supabase/admin";
import { isMarketOpen, isWeekendBar } from "@/lib/market-hours";
import { fetchOhlcv, type OhlcvBar } from "@/lib/ingestion/databento";
import { aggregateMesTimeframes } from "@/lib/mes-aggregation";
import { activeMesContract, getContractSegments } from "@/lib/contract-roll";

export const maxDuration = 60;

// Primary MES data path. Runs every 5 minutes via Vercel Cron.
// Fetches ohlcv-1m + ohlcv-1h from Databento Historical API → Supabase.
// Uses explicit contract symbols per time period to match TradingView volume roll.
//
// Manual modes:
//   ?days=N       — forced backfill N days back (max 90)
//   ?purge=1      — DELETE all MES tables first, then backfill (full rebuild)
//   ?force=1      — skip market-hours check

const MES_TABLES = ["mes_1m", "mes_15m", "mes_1h", "mes_4h", "mes_1d"] as const;

export async function GET(request: Request) {
  const cronSecret = process.env.CRON_SECRET;
  if (cronSecret) {
    const auth = request.headers.get("authorization");
    if (auth !== `Bearer ${cronSecret}`) {
      return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
    }
  }

  const reqUrl = new URL(request.url);
  const isManual = reqUrl.searchParams.has("days") || reqUrl.searchParams.has("force") || reqUrl.searchParams.has("purge");
  if (!isManual && !isMarketOpen()) {
    return NextResponse.json({ skipped: true, reason: "market_closed" });
  }

  const startTime = Date.now();
  const supabase = createAdminClient();
  const doPurge = reqUrl.searchParams.get("purge") === "1";

  try {
    const now = new Date();
    const daysParam = parseInt(reqUrl.searchParams.get("days") || "0", 10);

    // Purge: wipe all MES tables before rebuild (batched to avoid statement timeout)
    if (doPurge) {
      for (const table of MES_TABLES) {
        let deleted = 0;
        // Delete in batches of 5000 rows to avoid Supabase statement timeout
        for (;;) {
          const { data, error } = await supabase
            .from(table)
            .select("ts")
            .order("ts", { ascending: true })
            .limit(5000);
          if (error) throw new Error(`Failed to query ${table} for purge: ${error.message}`);
          if (!data || data.length === 0) break;

          const oldest = data[0].ts;
          const newest = data[data.length - 1].ts;
          const { error: delErr } = await supabase
            .from(table)
            .delete()
            .gte("ts", oldest)
            .lte("ts", newest);
          if (delErr) throw new Error(`Failed to purge ${table}: ${delErr.message}`);
          deleted += data.length;
        }
      }
    }

    let gapStart: Date;
    if (daysParam > 0) {
      // Forced backfill: go back N days (max 90)
      const days = Math.min(daysParam, 90);
      gapStart = new Date(now.getTime() - days * 24 * 60 * 60 * 1000);
    } else if (doPurge) {
      // Purge without days param: default 30 days
      gapStart = new Date(now.getTime() - 30 * 24 * 60 * 60 * 1000);
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
        gapStart = new Date(now.getTime() - 7 * 24 * 60 * 60 * 1000);
      }
    }

    // Databento historical API has a short delay; 2 min buffer
    const gapEnd = new Date(now.getTime() - 2 * 60 * 1000);

    if (gapEnd.getTime() <= gapStart.getTime() + 60_000) {
      return NextResponse.json({
        success: true,
        gaps_filled: 0,
        reason: "no_gap",
        duration_ms: Date.now() - startTime,
      });
    }

    // Split the date range into contract segments so each period
    // uses the correct front-month symbol (matches TradingView roll)
    const segments = getContractSegments(gapStart, gapEnd);

    // Fetch data for each contract segment
    let allBars1m: OhlcvBar[] = [];
    let allBars1h: OhlcvBar[] = [];

    for (const seg of segments) {
      const [seg1m, seg1h] = await Promise.all([
        fetchOhlcv({
          dataset: "GLBX.MDP3",
          symbol: seg.symbol,
          stypeIn: "raw_symbol",
          start: seg.start.toISOString(),
          end: seg.end.toISOString(),
          schema: "ohlcv-1m",
        }),
        fetchOhlcv({
          dataset: "GLBX.MDP3",
          symbol: seg.symbol,
          stypeIn: "raw_symbol",
          start: seg.start.toISOString(),
          end: seg.end.toISOString(),
          schema: "ohlcv-1h",
        }),
      ]);

      allBars1m = allBars1m.concat(seg1m);
      allBars1h = allBars1h.concat(seg1h);
    }

    // Filter out weekend bars
    const validBars1m = allBars1m.filter((b) => !isWeekendBar(b.time));
    const validBars1h = allBars1h.filter((b) => !isWeekendBar(b.time));

    if (validBars1m.length === 0 && validBars1h.length === 0) {
      return NextResponse.json({
        success: true,
        gaps_filled: 0,
        segments: segments.map((s) => s.symbol),
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

    for (let i = 0; i < mes1mRows.length; i += 100) {
      const chunk = mes1mRows.slice(i, i + 100);
      const { error } = await supabase
        .from("mes_1m")
        .upsert(chunk, { onConflict: "ts" });
      if (error) throw new Error(`mes_1m upsert failed: ${error.message}`);
    }

    // Upsert 1h bars
    const mes1hRows = validBars1h.map((b) => ({
      ts: new Date(b.time * 1000).toISOString(),
      open: b.open,
      high: b.high,
      low: b.low,
      close: b.close,
      volume: b.volume,
    }));

    if (mes1hRows.length > 0) {
      for (let i = 0; i < mes1hRows.length; i += 100) {
        const chunk = mes1hRows.slice(i, i + 100);
        const { error } = await supabase
          .from("mes_1h")
          .upsert(chunk, { onConflict: "ts" });
        if (error) throw new Error(`mes_1h upsert failed: ${error.message}`);
      }
    }

    // Derive 15m from 1m, 4h and 1d from 1h
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

      for (let i = 0; i < rows.length; i += 100) {
        const chunk = rows.slice(i, i + 100);
        const { error } = await supabase
          .from(tableName)
          .upsert(chunk, { onConflict: "ts" });
        if (error) throw new Error(`${tableName} upsert failed: ${error.message}`);
      }

      aggregatedRows += rows.length;
    }

    // Log to job_log
    await supabase.from("job_log").insert({
      job_name: doPurge ? "mes-rebuild" : "mes-catchup",
      status: "SUCCESS",
      rows_affected: validBars1m.length + mes1hRows.length + aggregatedRows,
      duration_ms: Date.now() - startTime,
    });

    return NextResponse.json({
      success: true,
      purged: doPurge,
      segments: segments.map((s) => ({ symbol: s.symbol, start: s.start.toISOString(), end: s.end.toISOString() })),
      bars_1m: validBars1m.length,
      bars_15m: bars15m.length,
      bars_1h: mes1hRows.length,
      bars_4h: bars4h.length,
      bars_1d: bars1d.length,
      duration_ms: Date.now() - startTime,
    });
  } catch (e) {
    const message = e instanceof Error ? e.message : "Internal error";

    try {
      await supabase.from("job_log").insert({
        job_name: doPurge ? "mes-rebuild" : "mes-catchup",
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
