// Edge Function: mes-1m
// Triggered by Supabase pg_cron (warbird_mes_1m_pull).
// Market-hours skip logic is handled internally via isMarketOpen().
// Uses Databento Live API (real-time TCP gateway) for ohlcv-1s → aggregates to 1m/15m.
// Falls back to Historical API for gaps > 10 minutes.
// Auth: x-cron-secret header validated against EDGE_CRON_SECRET env var.

import { createAdminClient } from "../_shared/admin.ts";
import { validateCronRequest } from "../_shared/cron-auth.ts";
import { fetchOhlcv } from "../_shared/databento.ts";
import { fetchLiveOhlcv1m } from "../_shared/databento-live.ts";
import { isMarketOpen, isWeekendBar } from "../_shared/market-hours.ts";
import type { OhlcvBar } from "../_shared/databento.ts";

const ONE_MINUTE_MS = 60_000;
const BAR_15M_SEC = 900;
const LOOKBACK_ON_EMPTY_MINUTES = 180;
const MAX_INCREMENTAL_LOOKBACK_MINUTES = 360;
const LIVE_API_MAX_GAP_MINUTES = 60; // use Live API for gaps <= 60 min (24h replay)
const UPSERT_CHUNK_SIZE = 200;

function floorTo15m(timeSec: number): number {
  return Math.floor(timeSec / BAR_15M_SEC) * BAR_15M_SEC;
}

function floorToMinute(timeMs: number): number {
  return Math.floor(timeMs / ONE_MINUTE_MS) * ONE_MINUTE_MS;
}

function aggregate15m(rows: Array<{
  ts: string; open: number; high: number; low: number; close: number; volume: number;
}>): Array<{
  ts: string; open: number; high: number; low: number; close: number; volume: number;
}> {
  if (rows.length === 0) return [];

  const byBucket = new Map<number, {
    tsSec: number; open: number; high: number; low: number; close: number; volume: number;
  }>();

  for (const row of rows) {
    const tsSec = Math.floor(new Date(row.ts).getTime() / 1000);
    const bucketSec = floorTo15m(tsSec);
    const existing = byBucket.get(bucketSec);
    if (!existing) {
      byBucket.set(bucketSec, {
        tsSec: bucketSec,
        open: Number(row.open), high: Number(row.high),
        low: Number(row.low), close: Number(row.close),
        volume: Number(row.volume),
      });
      continue;
    }
    existing.high = Math.max(existing.high, Number(row.high));
    existing.low = Math.min(existing.low, Number(row.low));
    existing.close = Number(row.close);
    existing.volume += Number(row.volume);
  }

  return [...byBucket.values()]
    .sort((a, b) => a.tsSec - b.tsSec)
    .map((bar) => ({
      ts: new Date(bar.tsSec * 1000).toISOString(),
      open: bar.open, high: bar.high, low: bar.low, close: bar.close, volume: bar.volume,
    }));
}

function jsonResponse(data: unknown, status = 200): Response {
  return new Response(JSON.stringify(data), {
    status, headers: { "Content-Type": "application/json" },
  });
}

Deno.serve(async (req: Request) => {
  const authError = validateCronRequest(req);
  if (authError) return authError;

  const startMs = Date.now();
  const url = new URL(req.url);
  const force = url.searchParams.get("force") === "1";
  const supabase = createAdminClient();

  if (!force && !isMarketOpen()) {
    try {
      await supabase.from("job_log").insert({
        job_name: "mes-1m-pull",
        status: "SKIPPED",
        rows_affected: 0,
        duration_ms: Date.now() - startMs,
        error_message: "market_closed",
      });
    } catch { /* ignore */ }
    return jsonResponse({ skipped: true, reason: "market_closed" });
  }

  try {
    const { data: latest, error: latestErr } = await supabase
      .from("mes_1m")
      .select("ts")
      .order("ts", { ascending: false })
      .limit(1)
      .single();

    if (latestErr && latestErr.code !== "PGRST116") {
      throw new Error(`Failed to query mes_1m latest timestamp: ${latestErr.message}`);
    }

    const now = Date.now();
    const lastClosedMinuteStartMs = floorToMinute(now) - ONE_MINUTE_MS;
    const maxLookbackStartMs = now - MAX_INCREMENTAL_LOOKBACK_MINUTES * ONE_MINUTE_MS;
    const defaultStartMs = now - LOOKBACK_ON_EMPTY_MINUTES * ONE_MINUTE_MS;
    const latestStartMs = latest?.ts
      ? new Date(latest.ts).getTime() + ONE_MINUTE_MS
      : defaultStartMs;
    const rangeStartMs = Math.max(latestStartMs, maxLookbackStartMs);

    if (rangeStartMs > lastClosedMinuteStartMs) {
      try {
        await supabase.from("job_log").insert({
          job_name: "mes-1m-pull",
          status: "SKIPPED",
          rows_affected: 0,
          duration_ms: Date.now() - startMs,
          error_message: "no_gap",
        });
      } catch { /* ignore */ }
      return jsonResponse({ success: true, pulled_1m: 0, upserted_15m: 0, reason: "no_gap", duration_ms: Date.now() - startMs });
    }

    const gapMinutes = (lastClosedMinuteStartMs - rangeStartMs) / ONE_MINUTE_MS + 1;

    // ── Fetch bars ──────────────────────────────────────────────────────
    let bars: OhlcvBar[] = [];
    let source = "live";

    if (gapMinutes <= LIVE_API_MAX_GAP_MINUTES) {
      // Live API — real-time, zero lag
      try {
        const startSec = Math.floor(rangeStartMs / 1000);
        const result = await fetchLiveOhlcv1m({
          dataset: "GLBX.MDP3",
          symbol: "MES.c.0",
          startSec,
        });
        bars = result.bars1m;
        source = `live(1s=${result.bars1s_count})`;
      } catch (liveErr) {
        // Fall back to Historical API if Live fails
        const msg = liveErr instanceof Error ? liveErr.message : String(liveErr);
        source = `hist(live_err=${msg.slice(0, 80)})`;
        bars = await fetchOhlcv({
          dataset: "GLBX.MDP3",
          symbol: "MES.c.0",
          stypeIn: "continuous",
          schema: "ohlcv-1m",
          start: new Date(rangeStartMs).toISOString(),
          end: new Date(now).toISOString(),
        });
      }
    } else {
      // Large gap — use Historical API for catch-up
      source = "hist";
      bars = await fetchOhlcv({
        dataset: "GLBX.MDP3",
        symbol: "MES.c.0",
        stypeIn: "continuous",
        schema: "ohlcv-1m",
        start: new Date(rangeStartMs).toISOString(),
        end: new Date(now).toISOString(),
      });
    }

    const lastClosedMinuteSec = Math.floor(lastClosedMinuteStartMs / 1000);
    const dedupedBars = [...new Map(
      bars
        .filter((bar) => !isWeekendBar(bar.time))
        .filter((bar) => bar.time <= lastClosedMinuteSec)
        .map((bar) => [bar.time, bar] as const),
    ).values()].sort((a, b) => a.time - b.time);

    if (dedupedBars.length === 0) {
      await supabase.from("job_log").insert({
        job_name: "mes-1m-pull",
        status: "SUCCESS",
        rows_affected: 0,
        duration_ms: Date.now() - startMs,
        error_message: `${source}:no_data`,
      });
      return jsonResponse({
        success: true, pulled_1m: 0, upserted_15m: 0,
        reason: "no_data", source, duration_ms: Date.now() - startMs,
      });
    }

    // ── Upsert 1m bars ─────────────────────────────────────────────────
    const mes1mRows = dedupedBars.map((bar) => ({
      ts: new Date(bar.time * 1000).toISOString(),
      open: bar.open, high: bar.high, low: bar.low, close: bar.close, volume: bar.volume,
    }));

    for (let i = 0; i < mes1mRows.length; i += UPSERT_CHUNK_SIZE) {
      const chunk = mes1mRows.slice(i, i + UPSERT_CHUNK_SIZE);
      const { error } = await supabase.from("mes_1m").upsert(chunk, { onConflict: "ts" });
      if (error) throw new Error(`mes_1m upsert failed: ${error.message}`);
    }

    // ── Rollup touched 15m buckets ──────────────────────────────────────
    const minBarSec = dedupedBars[0].time;
    const maxBarSec = dedupedBars[dedupedBars.length - 1].time;
    const minBucketSec = floorTo15m(minBarSec);
    const maxBucketExclusiveSec = floorTo15m(maxBarSec) + BAR_15M_SEC;

    const { data: rollupSource, error: rollupErr } = await supabase
      .from("mes_1m")
      .select("ts, open, high, low, close, volume")
      .gte("ts", new Date(minBucketSec * 1000).toISOString())
      .lt("ts", new Date(maxBucketExclusiveSec * 1000).toISOString())
      .order("ts", { ascending: true });

    if (rollupErr) throw new Error(`mes_1m rollup read failed: ${rollupErr.message}`);

    const mes15mRows = aggregate15m((rollupSource ?? []).map((row) => ({
      ts: String(row.ts),
      open: Number(row.open), high: Number(row.high),
      low: Number(row.low), close: Number(row.close), volume: Number(row.volume),
    })));

    if (mes15mRows.length > 0) {
      for (let i = 0; i < mes15mRows.length; i += UPSERT_CHUNK_SIZE) {
        const chunk = mes15mRows.slice(i, i + UPSERT_CHUNK_SIZE);
        const { error } = await supabase.from("mes_15m").upsert(chunk, { onConflict: "ts" });
        if (error) throw new Error(`mes_15m upsert failed: ${error.message}`);
      }
    }

    await supabase.from("job_log").insert({
      job_name: "mes-1m-pull",
      status: "SUCCESS",
      rows_affected: mes1mRows.length + mes15mRows.length,
      duration_ms: Date.now() - startMs,
    });

    return jsonResponse({
      success: true,
      pulled_1m: mes1mRows.length,
      upserted_15m: mes15mRows.length,
      source,
      symbol: "MES.c.0",
      from: new Date(rangeStartMs).toISOString(),
      duration_ms: Date.now() - startMs,
    });
  } catch (error) {
    const message = error instanceof Error ? error.message : "Internal error";
    try {
      await supabase.from("job_log").insert({
        job_name: "mes-1m-pull",
        status: "FAILED",
        error_message: message,
        duration_ms: Date.now() - startMs,
      });
    } catch { /* ignore */ }
    return jsonResponse({ error: message }, 500);
  }
});
