import { NextResponse } from "next/server";
import { createAdminClient } from "@/lib/supabase/admin";
import { validateCronRequest } from "@/lib/cron-auth";
import { isMarketOpen } from "@/lib/market-hours";
import { aggregateMes4hFrom1h, aggregateMes1dFrom1h } from "@/lib/mes-aggregation";
import type { OhlcvBar } from "@/lib/ingestion/databento";

export const maxDuration = 60;

const BAR_1H_SEC = 3600;
const LOOKBACK_ON_EMPTY_HOURS = 168; // 7 days
const INGEST_DELAY_SECONDS = 90;
const WIDE_AGG_LOOKBACK_HOURS = 48;
const UPSERT_CHUNK_SIZE = 200;

type JobLogStatus = "SUCCESS" | "PARTIAL" | "FAILED" | "SKIPPED";

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

// Runs at :05 past every hour (Sun-Fri). Reads mes_1m bars since the latest
// mes_1h bar, aggregates to 1h, then re-aggregates a 48h window to keep
// mes_4h and mes_1d current.

export async function GET(request: Request) {
  const authError = validateCronRequest(request);
  if (authError) {
    return authError;
  }

  const startMs = Date.now();
  const supabase = createAdminClient();

  if (!isMarketOpen()) {
    try {
      await writeJobLog(supabase, {
        job_name: "mes-hourly",
        status: "SKIPPED",
        rows_affected: 0,
        duration_ms: Date.now() - startMs,
        error_message: "market_closed",
      });
    } catch {
      // Ignore secondary logging failure to preserve skip response.
    }
    return NextResponse.json({ skipped: true, reason: "market_closed" });
  }

  try {
    // 1. Find latest mes_1h timestamp
    const { data: latest, error: latestErr } = await supabase
      .from("mes_1h")
      .select("ts")
      .order("ts", { ascending: false })
      .limit(1)
      .single();

    if (latestErr && latestErr.code !== "PGRST116") {
      throw new Error(`Failed to query mes_1h latest timestamp: ${latestErr.message}`);
    }

    const now = Date.now();
    const rangeEndMs = now - INGEST_DELAY_SECONDS * 1000;
    const rangeStartMs = latest?.ts
      ? new Date(latest.ts).getTime()
      : now - LOOKBACK_ON_EMPTY_HOURS * BAR_1H_SEC * 1000;

    // 2. Read mes_1m bars in range
    const { data: mes1mData, error: mes1mErr } = await supabase
      .from("mes_1m")
      .select("ts, open, high, low, close, volume")
      .gte("ts", new Date(rangeStartMs).toISOString())
      .lt("ts", new Date(rangeEndMs).toISOString())
      .order("ts", { ascending: true });

    if (mes1mErr) {
      throw new Error(`mes_1m read failed: ${mes1mErr.message}`);
    }

    if (!mes1mData || mes1mData.length === 0) {
      try {
        await writeJobLog(supabase, {
          job_name: "mes-hourly",
          status: "SKIPPED",
          rows_affected: 0,
          duration_ms: Date.now() - startMs,
          error_message: "no_1m_data",
        });
      } catch {
        // Ignore secondary logging failure to preserve skip response.
      }
      return NextResponse.json({ success: true, reason: "no_1m_data", duration_ms: Date.now() - startMs });
    }

    // 3. Aggregate 1m → 1h buckets
    const byBucket = new Map<number, {
      tsSec: number;
      open: number;
      high: number;
      low: number;
      close: number;
      volume: number;
    }>();

    for (const row of mes1mData) {
      const tsSec = Math.floor(new Date(String(row.ts)).getTime() / 1000);
      const bucketSec = Math.floor(tsSec / BAR_1H_SEC) * BAR_1H_SEC;
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
      } else {
        existing.high = Math.max(existing.high, Number(row.high));
        existing.low = Math.min(existing.low, Number(row.low));
        existing.close = Number(row.close);
        existing.volume += Number(row.volume);
      }
    }

    const mes1hRows = [...byBucket.values()]
      .sort((a, b) => a.tsSec - b.tsSec)
      .map((bar) => ({
        ts: new Date(bar.tsSec * 1000).toISOString(),
        open: bar.open,
        high: bar.high,
        low: bar.low,
        close: bar.close,
        volume: bar.volume,
      }));

    // 4. Upsert to mes_1h
    for (let i = 0; i < mes1hRows.length; i += UPSERT_CHUNK_SIZE) {
      const chunk = mes1hRows.slice(i, i + UPSERT_CHUNK_SIZE);
      const { error } = await supabase
        .from("mes_1h")
        .upsert(chunk, { onConflict: "ts" });
      if (error) {
        throw new Error(`mes_1h upsert failed: ${error.message}`);
      }
    }

    // 5. Read a 48h window of mes_1h bars to re-aggregate 4h and 1d buckets
    //    (wide window ensures full session days and 4h buckets are always correct)
    const wideStartMs = now - WIDE_AGG_LOOKBACK_HOURS * BAR_1H_SEC * 1000;
    const { data: wide1hData, error: wide1hErr } = await supabase
      .from("mes_1h")
      .select("ts, open, high, low, close, volume")
      .gte("ts", new Date(wideStartMs).toISOString())
      .lte("ts", new Date(rangeEndMs).toISOString())
      .order("ts", { ascending: true });

    if (wide1hErr) {
      throw new Error(`mes_1h wide read failed: ${wide1hErr.message}`);
    }

    const bars1h: OhlcvBar[] = (wide1hData ?? []).map((row) => ({
      time: Math.floor(new Date(String(row.ts)).getTime() / 1000),
      open: Number(row.open),
      high: Number(row.high),
      low: Number(row.low),
      close: Number(row.close),
      volume: Number(row.volume),
    }));

    // 6. Aggregate 1h → 4h and upsert
    const bars4h = aggregateMes4hFrom1h(bars1h);
    const mes4hRows = bars4h.map((bar) => ({
      ts: new Date(bar.time * 1000).toISOString(),
      open: bar.open,
      high: bar.high,
      low: bar.low,
      close: bar.close,
      volume: bar.volume,
    }));

    for (let i = 0; i < mes4hRows.length; i += UPSERT_CHUNK_SIZE) {
      const chunk = mes4hRows.slice(i, i + UPSERT_CHUNK_SIZE);
      const { error } = await supabase
        .from("mes_4h")
        .upsert(chunk, { onConflict: "ts" });
      if (error) {
        throw new Error(`mes_4h upsert failed: ${error.message}`);
      }
    }

    // 7. Aggregate 1h → 1d (Chicago session-day boundaries) and upsert
    const bars1d = aggregateMes1dFrom1h(bars1h);
    const mes1dRows = bars1d.map((bar) => ({
      ts: new Date(bar.time * 1000).toISOString(),
      open: bar.open,
      high: bar.high,
      low: bar.low,
      close: bar.close,
      volume: bar.volume,
    }));

    for (let i = 0; i < mes1dRows.length; i += UPSERT_CHUNK_SIZE) {
      const chunk = mes1dRows.slice(i, i + UPSERT_CHUNK_SIZE);
      const { error } = await supabase
        .from("mes_1d")
        .upsert(chunk, { onConflict: "ts" });
      if (error) {
        throw new Error(`mes_1d upsert failed: ${error.message}`);
      }
    }

    const totalRows = mes1hRows.length + mes4hRows.length + mes1dRows.length;
    await writeJobLog(supabase, {
      job_name: "mes-hourly",
      status: "SUCCESS",
      rows_affected: totalRows,
      duration_ms: Date.now() - startMs,
    });

    return NextResponse.json({
      success: true,
      rows_1h: mes1hRows.length,
      rows_4h: mes4hRows.length,
      rows_1d: mes1dRows.length,
      rows_affected: totalRows,
      duration_ms: Date.now() - startMs,
    });
  } catch (e) {
    const message = e instanceof Error ? e.message : "Internal error";
    let finalMessage = message;
    try {
      await writeJobLog(supabase, {
        job_name: "mes-hourly",
        status: "FAILED",
        rows_affected: 0,
        duration_ms: Date.now() - startMs,
        error_message: message,
      });
    } catch (logError) {
      finalMessage = `${message}; ${logError instanceof Error ? logError.message : String(logError)}`;
    }
    return NextResponse.json({ error: finalMessage }, { status: 500 });
  }
}
