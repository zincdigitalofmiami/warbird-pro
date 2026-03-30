// Edge Function: mes-hourly
// Triggered at :05 past every hour (Sun-Fri) by Supabase pg_cron (warbird_mes_hourly_pull).
// Pulls ohlcv-1h and ohlcv-1d directly from Databento (MES.c.0 continuous).
// Aggregates 1h → 4h locally (Databento has no ohlcv-4h schema).
// Auth: x-cron-secret header validated against EDGE_CRON_SECRET env var.

import { createAdminClient } from "../_shared/admin.ts";
import { validateCronRequest } from "../_shared/cron-auth.ts";
import { fetchOhlcv, type OhlcvBar } from "../_shared/databento.ts";
import { isMarketOpen, isWeekendBar } from "../_shared/market-hours.ts";

const BAR_1H_SEC = 3600;
const BAR_4H_SEC = 14_400;
const LOOKBACK_ON_EMPTY_HOURS = 168; // 7 days
const MAX_INCREMENTAL_LOOKBACK_HOURS = 720; // 30 days
const UPSERT_CHUNK_SIZE = 200;

function floorTo4h(timeSec: number): number {
  return Math.floor(timeSec / BAR_4H_SEC) * BAR_4H_SEC;
}

function aggregate4hFrom1h(bars: OhlcvBar[]): OhlcvBar[] {
  const buckets = new Map<number, OhlcvBar>();
  for (const bar of bars) {
    const bucketTime = floorTo4h(bar.time);
    const existing = buckets.get(bucketTime);
    if (!existing) {
      buckets.set(bucketTime, { ...bar, time: bucketTime });
      continue;
    }
    existing.high = Math.max(existing.high, bar.high);
    existing.low = Math.min(existing.low, bar.low);
    existing.close = bar.close;
    existing.volume += bar.volume;
  }
  return Array.from(buckets.values()).sort((a, b) => a.time - b.time);
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
  const supabase = createAdminClient();

  if (!isMarketOpen()) {
    try {
      await supabase.from("job_log").insert({
        job_name: "mes-hourly",
        status: "SKIPPED",
        rows_affected: 0,
        duration_ms: Date.now() - startMs,
        error_message: "market_closed",
      });
    } catch {
      // Ignore secondary logging failure.
    }
    return jsonResponse({ skipped: true, reason: "market_closed" });
  }

  try {
    // ── 1h: pull from Databento directly ────────────────────────────────
    const { data: latest1h, error: latest1hErr } = await supabase
      .from("mes_1h")
      .select("ts")
      .order("ts", { ascending: false })
      .limit(1)
      .single();

    if (latest1hErr && latest1hErr.code !== "PGRST116") {
      throw new Error(`Failed to query mes_1h latest ts: ${latest1hErr.message}`);
    }

    const now = Date.now();
    const maxLookbackStartMs = now - MAX_INCREMENTAL_LOOKBACK_HOURS * BAR_1H_SEC * 1000;
    const defaultStartMs = now - LOOKBACK_ON_EMPTY_HOURS * BAR_1H_SEC * 1000;
    const latestStartMs = latest1h?.ts
      ? new Date(latest1h.ts).getTime() + BAR_1H_SEC * 1000
      : defaultStartMs;
    const rangeStartMs = Math.max(latestStartMs, maxLookbackStartMs);
    const rangeEndMs = now;

    let rows1h = 0;
    let rows4h = 0;
    let rows1d = 0;

    if (rangeEndMs > rangeStartMs) {
      const bars1h = await fetchOhlcv({
        dataset: "GLBX.MDP3",
        symbol: "MES.c.0",
        stypeIn: "continuous",
        schema: "ohlcv-1h",
        start: new Date(rangeStartMs).toISOString(),
        end: new Date(rangeEndMs).toISOString(),
      });

      const valid1h = bars1h.filter((b) => !isWeekendBar(b.time));

      if (valid1h.length > 0) {
        const mes1hRows = valid1h.map((b) => ({
          ts: new Date(b.time * 1000).toISOString(),
          open: b.open,
          high: b.high,
          low: b.low,
          close: b.close,
          volume: b.volume,
        }));

        for (let i = 0; i < mes1hRows.length; i += UPSERT_CHUNK_SIZE) {
          const chunk = mes1hRows.slice(i, i + UPSERT_CHUNK_SIZE);
          const { error } = await supabase
            .from("mes_1h")
            .upsert(chunk, { onConflict: "ts" });
          if (error) throw new Error(`mes_1h upsert failed: ${error.message}`);
        }
        rows1h = mes1hRows.length;

        // ── 4h: aggregate from the 1h bars we just pulled ──────────────
        // Read a 48h window of 1h bars so partial 4h buckets are correct
        const wideStartMs = now - 48 * BAR_1H_SEC * 1000;
        const { data: wide1hData, error: wide1hErr } = await supabase
          .from("mes_1h")
          .select("ts, open, high, low, close, volume")
          .gte("ts", new Date(wideStartMs).toISOString())
          .order("ts", { ascending: true });

        if (wide1hErr) throw new Error(`mes_1h wide read failed: ${wide1hErr.message}`);

        const wideBars: OhlcvBar[] = (wide1hData ?? []).map((row) => ({
          time: Math.floor(new Date(String(row.ts)).getTime() / 1000),
          open: Number(row.open),
          high: Number(row.high),
          low: Number(row.low),
          close: Number(row.close),
          volume: Number(row.volume),
        }));

        const bars4h = aggregate4hFrom1h(wideBars);
        const mes4hRows = bars4h.map((b) => ({
          ts: new Date(b.time * 1000).toISOString(),
          open: b.open,
          high: b.high,
          low: b.low,
          close: b.close,
          volume: b.volume,
        }));

        for (let i = 0; i < mes4hRows.length; i += UPSERT_CHUNK_SIZE) {
          const chunk = mes4hRows.slice(i, i + UPSERT_CHUNK_SIZE);
          const { error } = await supabase
            .from("mes_4h")
            .upsert(chunk, { onConflict: "ts" });
          if (error) throw new Error(`mes_4h upsert failed: ${error.message}`);
        }
        rows4h = mes4hRows.length;
      }
    }

    // ── 1d: pull from Databento directly ────────────────────────────────
    const { data: latest1d, error: latest1dErr } = await supabase
      .from("mes_1d")
      .select("ts")
      .order("ts", { ascending: false })
      .limit(1)
      .single();

    if (latest1dErr && latest1dErr.code !== "PGRST116") {
      throw new Error(`Failed to query mes_1d latest ts: ${latest1dErr.message}`);
    }

    const defaultStart1dMs = now - 30 * 24 * BAR_1H_SEC * 1000; // 30 days
    const latestStart1dMs = latest1d?.ts
      ? new Date(latest1d.ts).getTime() + 24 * BAR_1H_SEC * 1000
      : defaultStart1dMs;
    const rangeStart1dMs = Math.max(latestStart1dMs, defaultStart1dMs);

    if (now > rangeStart1dMs) {
      const bars1d = await fetchOhlcv({
        dataset: "GLBX.MDP3",
        symbol: "MES.c.0",
        stypeIn: "continuous",
        schema: "ohlcv-1d",
        start: new Date(rangeStart1dMs).toISOString(),
        end: new Date(now).toISOString(),
      });

      const valid1d = bars1d.filter((b) => !isWeekendBar(b.time));

      if (valid1d.length > 0) {
        const mes1dRows = valid1d.map((b) => ({
          ts: new Date(b.time * 1000).toISOString(),
          open: b.open,
          high: b.high,
          low: b.low,
          close: b.close,
          volume: b.volume,
        }));

        for (let i = 0; i < mes1dRows.length; i += UPSERT_CHUNK_SIZE) {
          const chunk = mes1dRows.slice(i, i + UPSERT_CHUNK_SIZE);
          const { error } = await supabase
            .from("mes_1d")
            .upsert(chunk, { onConflict: "ts" });
          if (error) throw new Error(`mes_1d upsert failed: ${error.message}`);
        }
        rows1d = mes1dRows.length;
      }
    }

    const totalRows = rows1h + rows4h + rows1d;
    await supabase.from("job_log").insert({
      job_name: "mes-hourly",
      status: "SUCCESS",
      rows_affected: totalRows,
      duration_ms: Date.now() - startMs,
    });

    return jsonResponse({
      success: true,
      symbol: "MES.c.0",
      rows_1h: rows1h,
      rows_4h: rows4h,
      rows_1d: rows1d,
      duration_ms: Date.now() - startMs,
    });
  } catch (e) {
    const message = e instanceof Error ? e.message : "Internal error";
    try {
      await supabase.from("job_log").insert({
        job_name: "mes-hourly",
        status: "FAILED",
        rows_affected: 0,
        duration_ms: Date.now() - startMs,
        error_message: message,
      });
    } catch {
      // ignore secondary logging failures
    }
    return jsonResponse({ error: message }, 500);
  }
});
