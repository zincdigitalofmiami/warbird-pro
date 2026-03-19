import { NextResponse } from "next/server";
import { createAdminClient } from "@/lib/supabase/admin";
import { isMarketOpen, isWeekendBar } from "@/lib/market-hours";
import { fetchOhlcv } from "@/lib/ingestion/databento";

export const maxDuration = 60;

type JobLogStatus = "SUCCESS" | "PARTIAL" | "FAILED" | "SKIPPED";

const DEFAULT_SHARD_COUNT = 4;
const SHARD_INTERVAL_MINUTES = 15;

async function writeJobLog(
  supabase: ReturnType<typeof createAdminClient>,
  params: {
    job_name: string;
    status: JobLogStatus;
    rows_affected: number;
    duration_ms: number;
    error_message?: string | null;
  },
) {
  const { error } = await supabase.from("job_log").insert({
    ...params,
    error_message: params.error_message ?? null,
  });

  if (error) {
    throw new Error(`job_log insert failed: ${error.message}`);
  }
}

// Runs on a 15m cadence and processes one deterministic shard per run.
// Fetches 1h OHLCV for active DATABENTO non-MES symbols in that shard and
// aggregates to daily bars.

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
  const url = new URL(request.url);

  if (!isMarketOpen()) {
    try {
      await writeJobLog(supabase, {
        job_name: "cross-asset",
        status: "SKIPPED",
        rows_affected: 0,
        duration_ms: Date.now() - startTime,
        error_message: "market_closed",
      });
    } catch {
      // Ignore logging failure to preserve skip response.
    }
    return NextResponse.json({ skipped: true, reason: "market_closed", duration_ms: Date.now() - startTime });
  }

  try {
    const configuredShardCount = Number(process.env.CROSS_ASSET_SHARD_COUNT ?? DEFAULT_SHARD_COUNT);
    const shardCount = Number.isInteger(configuredShardCount) && configuredShardCount > 0
      ? configuredShardCount
      : DEFAULT_SHARD_COUNT;

    const explicitShard = url.searchParams.get("shard");
    const explicitShardIndex = explicitShard == null ? null : Number(explicitShard);

    const now = new Date();
    const autoShardIndex = Math.floor(now.getUTCMinutes() / SHARD_INTERVAL_MINUTES) % shardCount;
    const shardIndex = explicitShardIndex != null && Number.isInteger(explicitShardIndex)
      ? explicitShardIndex
      : autoShardIndex;

    if (shardIndex < 0 || shardIndex >= shardCount) {
      const durationMs = Date.now() - startTime;
      await writeJobLog(supabase, {
        job_name: "cross-asset",
        status: "FAILED",
        rows_affected: 0,
        duration_ms: durationMs,
        error_message: `invalid_shard_index shard=${shardIndex} shard_count=${shardCount}`,
      });
      return NextResponse.json(
        { error: "invalid_shard_index", shard_index: shardIndex, shard_count: shardCount },
        { status: 400 },
      );
    }

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
    const orderedSymbols = [...(symbols ?? [])].sort((a, b) => a.code.localeCompare(b.code));
    const symbolsForShard = orderedSymbols.filter((_, index) => index % shardCount === shardIndex);

    if (orderedSymbols.length === 0) {
      const durationMs = Date.now() - startTime;
      await writeJobLog(supabase, {
        job_name: "cross-asset",
        status: "SKIPPED",
        rows_affected: 0,
        duration_ms: durationMs,
        error_message: "no_symbols",
      });
      return NextResponse.json({ success: true, symbols_processed: 0, reason: "no_symbols", duration_ms: durationMs });
    }

    if (symbolsForShard.length === 0) {
      const durationMs = Date.now() - startTime;
      await writeJobLog(supabase, {
        job_name: "cross-asset",
        status: "SKIPPED",
        rows_affected: 0,
        duration_ms: durationMs,
        error_message: `empty_shard shard=${shardIndex}/${shardCount}`,
      });
      return NextResponse.json({
        success: true,
        symbols_processed: 0,
        total_symbols: orderedSymbols.length,
        shard_index: shardIndex,
        shard_count: shardCount,
        reason: "empty_shard",
        duration_ms: durationMs,
      });
    }

    // Fetch window: last 2 hours with 30-min safety buffer
    const start = new Date(now.getTime() - 2 * 60 * 60 * 1000);
    const end = new Date(now.getTime() - 30 * 60 * 1000);

    let totalRows1h = 0;
    let totalRows1d = 0;
    const errors: string[] = [];

    for (const sym of symbolsForShard) {
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

    const durationMs = Date.now() - startTime;
    await writeJobLog(supabase, {
      job_name: "cross-asset",
      status: errors.length > 0 ? "PARTIAL" : totalRows1h + totalRows1d > 0 ? "SUCCESS" : "SKIPPED",
      rows_affected: totalRows1h + totalRows1d,
      duration_ms: durationMs,
      error_message: errors.length > 0
        ? `shard=${shardIndex}/${shardCount} | ${errors.join(" | ")}`
        : totalRows1h + totalRows1d === 0
          ? `no_valid_bars shard=${shardIndex}/${shardCount}`
          : null,
    });

    return NextResponse.json({
      success: true,
      symbols_processed: symbolsForShard.length,
      total_symbols: orderedSymbols.length,
      shard_index: shardIndex,
      shard_count: shardCount,
      rows_1h: totalRows1h,
      rows_1d: totalRows1d,
      rows_affected: totalRows1h + totalRows1d,
      errors: errors.length > 0 ? errors : undefined,
      duration_ms: durationMs,
    });
  } catch (e) {
    const message = e instanceof Error ? e.message : "Internal error";
    let finalMessage = message;
    try {
      await writeJobLog(supabase, {
        job_name: "cross-asset",
        status: "FAILED",
        rows_affected: 0,
        error_message: message,
        duration_ms: Date.now() - startTime,
      });
    } catch (logError) {
      finalMessage = `${message}; ${logError instanceof Error ? logError.message : String(logError)}`;
    }
    return NextResponse.json({ error: finalMessage }, { status: 500 });
  }
}
