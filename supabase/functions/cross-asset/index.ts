// Edge Function: cross-asset
// Ported from app/api/cron/cross-asset/route.ts
// Triggered hourly by Supabase pg_cron shard jobs (warbird_cross_asset_s0..s3).
// Market-hours skip logic is handled internally via isMarketOpen().
// Auth: x-cron-secret header validated against EDGE_CRON_SECRET env var.

import { createAdminClient } from "../_shared/admin.ts";
import { validateCronRequest } from "../_shared/cron-auth.ts";
import { isMarketOpen, isWeekendBar } from "../_shared/market-hours.ts";
import { fetchOhlcv } from "../_shared/databento.ts";

const DEFAULT_SHARD_COUNT = 4;
const SHARD_INTERVAL_MINUTES = 15;
const INITIAL_LOOKBACK_HOURS = 6;

function jsonResponse(data: unknown, status = 200): Response {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

Deno.serve(async (req: Request) => {
  const authError = validateCronRequest(req);
  if (authError) return authError;

  const startTime = Date.now();
  const supabase = createAdminClient();
  const url = new URL(req.url);

  if (!isMarketOpen()) {
    try {
      await supabase.from("job_log").insert({
        job_name: "cross-asset",
        status: "SKIPPED",
        rows_affected: 0,
        duration_ms: Date.now() - startTime,
        error_message: "market_closed",
      });
    } catch {
      // Ignore logging failure to preserve skip response.
    }
    return jsonResponse({ skipped: true, reason: "market_closed", duration_ms: Date.now() - startTime });
  }

  try {
    const configuredShardCount = Number(Deno.env.get("CROSS_ASSET_SHARD_COUNT") ?? DEFAULT_SHARD_COUNT);
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
      await supabase.from("job_log").insert({
        job_name: "cross-asset",
        status: "FAILED",
        rows_affected: 0,
        duration_ms: durationMs,
        error_message: `invalid_shard_index shard=${shardIndex} shard_count=${shardCount}`,
      });
      return jsonResponse(
        { error: "invalid_shard_index", shard_index: shardIndex, shard_count: shardCount },
        400,
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
      await supabase.from("job_log").insert({
        job_name: "cross-asset",
        status: "SKIPPED",
        rows_affected: 0,
        duration_ms: durationMs,
        error_message: "no_symbols",
      });
      return jsonResponse({ success: true, symbols_processed: 0, reason: "no_symbols", duration_ms: durationMs });
    }

    if (symbolsForShard.length === 0) {
      const durationMs = Date.now() - startTime;
      await supabase.from("job_log").insert({
        job_name: "cross-asset",
        status: "SKIPPED",
        rows_affected: 0,
        duration_ms: durationMs,
        error_message: `empty_shard shard=${shardIndex}/${shardCount}`,
      });
      return jsonResponse({
        success: true,
        symbols_processed: 0,
        total_symbols: orderedSymbols.length,
        shard_index: shardIndex,
        shard_count: shardCount,
        reason: "empty_shard",
        duration_ms: durationMs,
      });
    }

    const end = new Date(now.getTime() - 30 * 60 * 1000);

    let totalRows1h = 0;
    let totalRows1d = 0;
    const errors: string[] = [];

    for (const sym of symbolsForShard) {
      try {
        const { data: latestBar, error: latestBarError } = await supabase
          .from("cross_asset_1h")
          .select("ts")
          .eq("symbol_code", sym.code)
          .order("ts", { ascending: false })
          .limit(1)
          .maybeSingle();

        if (latestBarError) {
          throw new Error(`cross_asset_1h latest ts query failed: ${latestBarError.message}`);
        }

        const start = latestBar?.ts
          ? new Date(new Date(latestBar.ts).getTime() + 60 * 60 * 1000)
          : new Date(now.getTime() - INITIAL_LOOKBACK_HOURS * 60 * 60 * 1000);

        if (start >= end) {
          continue;
        }

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

        const touchedDays = [...new Set(validBars.map((bar) => new Date(bar.time * 1000).toISOString().slice(0, 10)))];

        for (const day of touchedDays) {
          const dayStartIso = `${day}T00:00:00Z`;
          const dayEnd = new Date(`${day}T00:00:00Z`);
          dayEnd.setUTCDate(dayEnd.getUTCDate() + 1);

          const { data: dayBars, error: dayBarsError } = await supabase
            .from("cross_asset_1h")
            .select("ts, open, high, low, close, volume")
            .eq("symbol_code", sym.code)
            .gte("ts", dayStartIso)
            .lt("ts", dayEnd.toISOString())
            .order("ts", { ascending: true });

          if (dayBarsError) {
            throw new Error(`cross_asset_1h day aggregation read failed: ${dayBarsError.message}`);
          }

          if (!dayBars || dayBars.length === 0) {
            continue;
          }

          const dailyBar = {
            ts: dayStartIso,
            open: Number(dayBars[0].open),
            high: Math.max(...dayBars.map((bar) => Number(bar.high))),
            low: Math.min(...dayBars.map((bar) => Number(bar.low))),
            close: Number(dayBars[dayBars.length - 1].close),
            volume: dayBars.reduce((sum, bar) => sum + Number(bar.volume), 0),
          };

          const { error: dErr } = await supabase.from("cross_asset_1d").upsert(
            {
              ts: dailyBar.ts,
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
        }
      } catch (e) {
        errors.push(`${sym.code}: ${e instanceof Error ? e.message : String(e)}`);
      }
    }

    const durationMs = Date.now() - startTime;
    await supabase.from("job_log").insert({
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

    return jsonResponse({
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
      await supabase.from("job_log").insert({
        job_name: "cross-asset",
        status: "FAILED",
        rows_affected: 0,
        error_message: message,
        duration_ms: Date.now() - startTime,
      });
    } catch (logError) {
      finalMessage = `${message}; ${logError instanceof Error ? logError.message : String(logError)}`;
    }
    return jsonResponse({ error: finalMessage }, 500);
  }
});
