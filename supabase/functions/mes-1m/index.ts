// Edge Function: mes-1m
// Ported from app/api/cron/mes-1m/route.ts
// Triggered every minute by Supabase pg_cron (warbird_mes_1m_pull).
// Auth: x-cron-secret header validated against EDGE_CRON_SECRET env var.

import { createAdminClient } from "../_shared/admin.ts";
import { validateCronRequest } from "../_shared/cron-auth.ts";
import { getContractSegments } from "../_shared/contract-roll.ts";
import { fetchOhlcv, type OhlcvBar } from "../_shared/databento.ts";
import { isMarketOpen, isWeekendBar } from "../_shared/market-hours.ts";

const ONE_MINUTE_MS = 60_000;
const BAR_15M_SEC = 900;
const LOOKBACK_ON_EMPTY_MINUTES = 180;
const MAX_INCREMENTAL_LOOKBACK_MINUTES = 360;
const INGEST_DELAY_SECONDS = 0;
const UPSERT_CHUNK_SIZE = 200;

function floorTo15m(timeSec: number): number {
  return Math.floor(timeSec / BAR_15M_SEC) * BAR_15M_SEC;
}

function aggregate15m(rows: Array<{
  ts: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}>): Array<{
  ts: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}> {
  if (rows.length === 0) return [];

  const byBucket = new Map<
    number,
    {
      tsSec: number;
      open: number;
      high: number;
      low: number;
      close: number;
      volume: number;
    }
  >();

  for (const row of rows) {
    const tsSec = Math.floor(new Date(row.ts).getTime() / 1000);
    const bucketSec = floorTo15m(tsSec);
    const existing = byBucket.get(bucketSec);
    if (!existing) {
      byBucket.set(bucketSec, {
        tsSec: bucketSec,
        open: Number(row.open),
        high: Number(row.high),
        low: Number(row.low),
        close: Number(row.close),
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
      open: bar.open,
      high: bar.high,
      low: bar.low,
      close: bar.close,
      volume: bar.volume,
    }));
}

function jsonResponse(data: unknown, status = 200): Response {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "Content-Type": "application/json" },
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
    } catch {
      // Ignore secondary logging failure to preserve skip response.
    }
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
    const maxLookbackStartMs = now - MAX_INCREMENTAL_LOOKBACK_MINUTES * ONE_MINUTE_MS;
    const defaultStartMs = now - LOOKBACK_ON_EMPTY_MINUTES * ONE_MINUTE_MS;
    const latestStartMs = latest?.ts
      ? new Date(latest.ts).getTime() + ONE_MINUTE_MS
      : defaultStartMs;
    const rangeStartMs = Math.max(latestStartMs, maxLookbackStartMs);
    const rangeEndMs = now - INGEST_DELAY_SECONDS * 1000;

    if (rangeEndMs <= rangeStartMs) {
      try {
        await supabase.from("job_log").insert({
          job_name: "mes-1m-pull",
          status: "SKIPPED",
          rows_affected: 0,
          duration_ms: Date.now() - startMs,
          error_message: "no_gap",
        });
      } catch {
        // Ignore secondary logging failure to preserve skip response.
      }
      return jsonResponse({
        success: true,
        pulled_1m: 0,
        upserted_15m: 0,
        reason: "no_gap",
        duration_ms: Date.now() - startMs,
      });
    }

    const rangeStart = new Date(rangeStartMs);
    const rangeEnd = new Date(rangeEndMs);
    const segments = getContractSegments(rangeStart, rangeEnd);

    let bars: OhlcvBar[] = [];
    for (const seg of segments) {
      const pulled = await fetchOhlcv({
        dataset: "GLBX.MDP3",
        symbol: seg.symbol,
        stypeIn: "raw_symbol",
        schema: "ohlcv-1m",
        start: seg.start.toISOString(),
        end: seg.end.toISOString(),
      });
      bars = bars.concat(pulled);
    }

    const dedupedBars = [...new Map(
      bars
        .filter((bar) => !isWeekendBar(bar.time))
        .map((bar) => [bar.time, bar] as const),
    ).values()].sort((a, b) => a.time - b.time);

    if (dedupedBars.length === 0) {
      await supabase.from("job_log").insert({
        job_name: "mes-1m-pull",
        status: "SUCCESS",
        rows_affected: 0,
        duration_ms: Date.now() - startMs,
      });

      return jsonResponse({
        success: true,
        pulled_1m: 0,
        upserted_15m: 0,
        reason: "no_data",
        duration_ms: Date.now() - startMs,
      });
    }

    const mes1mRows = dedupedBars.map((bar) => ({
      ts: new Date(bar.time * 1000).toISOString(),
      open: bar.open,
      high: bar.high,
      low: bar.low,
      close: bar.close,
      volume: bar.volume,
    }));

    for (let i = 0; i < mes1mRows.length; i += UPSERT_CHUNK_SIZE) {
      const chunk = mes1mRows.slice(i, i + UPSERT_CHUNK_SIZE);
      const { error } = await supabase
        .from("mes_1m")
        .upsert(chunk, { onConflict: "ts" });
      if (error) {
        throw new Error(`mes_1m upsert failed: ${error.message}`);
      }
    }

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

    if (rollupErr) {
      throw new Error(`mes_1m rollup read failed: ${rollupErr.message}`);
    }

    const mes15mRows = aggregate15m((rollupSource ?? []).map((row) => ({
      ts: String(row.ts),
      open: Number(row.open),
      high: Number(row.high),
      low: Number(row.low),
      close: Number(row.close),
      volume: Number(row.volume),
    })));

    if (mes15mRows.length > 0) {
      for (let i = 0; i < mes15mRows.length; i += UPSERT_CHUNK_SIZE) {
        const chunk = mes15mRows.slice(i, i + UPSERT_CHUNK_SIZE);
        const { error } = await supabase
          .from("mes_15m")
          .upsert(chunk, { onConflict: "ts" });
        if (error) {
          throw new Error(`mes_15m upsert failed: ${error.message}`);
        }
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
      segments: segments.map((segment) => segment.symbol),
      from: rangeStart.toISOString(),
      to: rangeEnd.toISOString(),
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
    } catch {
      // ignore secondary logging failures
    }
    return jsonResponse({ error: message }, 500);
  }
});
