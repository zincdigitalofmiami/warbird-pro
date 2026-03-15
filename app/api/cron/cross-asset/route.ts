import { NextResponse } from "next/server";
import { createAdminClient } from "@/lib/supabase/admin";
import { isMarketOpen, isWeekendBar } from "@/lib/market-hours";
import { fetchOhlcv } from "@/lib/ingestion/databento";

export const maxDuration = 60;

// Runs every hour at :15. Fetches 1h OHLCV for all active DATABENTO
// non-MES symbols. Also aggregates to daily bars.

export async function GET(request: Request) {
  const cronSecret = process.env.CRON_SECRET;
  if (cronSecret) {
    const auth = request.headers.get("authorization");
    if (auth !== `Bearer ${cronSecret}`) {
      return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
    }
  }

  if (!isMarketOpen()) {
    return NextResponse.json({ skipped: true, reason: "market_closed" });
  }

  const startTime = Date.now();
  const supabase = createAdminClient();

  try {
    // Get active DATABENTO symbols excluding MES (primary instrument has its own pipeline)
    const { data: symbols, error: symErr } = await supabase
      .from("symbols")
      .select("code, databento_symbol")
      .eq("is_active", true)
      .eq("data_source", "DATABENTO")
      .neq("code", "MES")
      .not("databento_symbol", "is", null)
      // Exclude options — they use a different schema
      .not("code", "like", "%.OPT");

    if (symErr) throw new Error(`Failed to query symbols: ${symErr.message}`);
    if (!symbols || symbols.length === 0) {
      return NextResponse.json({ success: true, symbols_processed: 0, reason: "no_symbols" });
    }

    // Fetch window: last 2 hours with 30-min safety buffer
    const now = new Date();
    const start = new Date(now.getTime() - 2 * 60 * 60 * 1000);
    const end = new Date(now.getTime() - 30 * 60 * 1000);

    let totalRows1h = 0;
    let totalRows1d = 0;
    const errors: string[] = [];

    for (const sym of symbols) {
      try {
        const bars = await fetchOhlcv({
          dataset: "GLBX.MDP3",
          symbol: sym.databento_symbol!,
          stypeIn: "continuous",
          start: start.toISOString(),
          end: end.toISOString(),
          schema: "ohlcv-1h",
        });

        const validBars = bars.filter((b) => !isWeekendBar(b.time));
        if (validBars.length === 0) continue;

        // Upsert 1h bars
        const rows1h = validBars.map((b) => ({
          ts: new Date(b.time * 1000).toISOString(),
          symbol_code: sym.code,
          open: b.open,
          high: b.high,
          low: b.low,
          close: b.close,
          volume: b.volume,
        }));

        const { error } = await supabase
          .from("cross_asset_1h")
          .upsert(rows1h, { onConflict: "ts,symbol_code" });
        if (error) throw new Error(`cross_asset_1h upsert: ${error.message}`);
        totalRows1h += rows1h.length;

        // Aggregate to daily
        const dailyBar = {
          ts: new Date(start.toISOString().split("T")[0] + "T00:00:00Z"),
          open: validBars[0].open,
          high: Math.max(...validBars.map((b) => b.high)),
          low: Math.min(...validBars.map((b) => b.low)),
          close: validBars[validBars.length - 1].close,
          volume: validBars.reduce((s, b) => s + b.volume, 0),
        };

        const { error: dErr } = await supabase.from("cross_asset_1d").upsert(
          {
            ts: dailyBar.ts.toISOString(),
            symbol_code: sym.code,
            open: dailyBar.open,
            high: dailyBar.high,
            low: dailyBar.low,
            close: dailyBar.close,
            volume: dailyBar.volume,
          },
          { onConflict: "ts,symbol_code" },
        );
        if (dErr) throw new Error(`cross_asset_1d upsert: ${dErr.message}`);
        totalRows1d++;
      } catch (e) {
        errors.push(`${sym.code}: ${e instanceof Error ? e.message : String(e)}`);
      }
    }

    await supabase.from("job_log").insert({
      job_name: "cross-asset",
      status: errors.length > 0 ? "PARTIAL" : "OK",
      rows_written: totalRows1h + totalRows1d,
      duration_ms: Date.now() - startTime,
    });

    return NextResponse.json({
      success: true,
      symbols_processed: symbols.length,
      rows_1h: totalRows1h,
      rows_1d: totalRows1d,
      errors: errors.length > 0 ? errors : undefined,
      duration_ms: Date.now() - startTime,
    });
  } catch (e) {
    const message = e instanceof Error ? e.message : "Internal error";
    try {
      await supabase.from("job_log").insert({
        job_name: "cross-asset",
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
