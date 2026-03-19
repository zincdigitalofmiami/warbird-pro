import { NextResponse } from "next/server";
import { createAdminClient } from "@/lib/supabase/admin";
import { isMarketOpen } from "@/lib/market-hours";

export const maxDuration = 60;

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

type TeEvent = {
  ts: string;
  event_name: string;
  importance: number;
  actual: number | null;
  forecast: number | null;
  previous: number | null;
};

function parseTeApiResponse(json: unknown[]): TeEvent[] {
  return json.map((item) => {
    const rec = item as Record<string, unknown>;
    const actual = rec.Actual !== "" ? parseFloat(rec.Actual as string) : null;
    const forecast = rec.Forecast !== "" ? parseFloat(rec.Forecast as string) : null;
    return {
      ts: String(rec.Date),
      event_name: String(rec.Event).slice(0, 500),
      importance: rec.Importance === "High" ? 3 : rec.Importance === "Medium" ? 2 : 1,
      actual: Number.isFinite(actual) ? actual : null,
      forecast: Number.isFinite(forecast) ? forecast : null,
      previous: rec.Previous !== "" ? parseFloat(rec.Previous as string) || null : null,
    };
  });
}

async function fetchTeCalendar(): Promise<TeEvent[]> {
  const apiKey = process.env.TRADINGECONOMICS_API_KEY;

  if (apiKey) {
    const url = `https://api.tradingeconomics.com/calendar?c=${apiKey}&country=united states`;
    const resp = await fetch(url, { cache: "no-store", signal: AbortSignal.timeout(30_000) });
    if (!resp.ok) throw new Error(`TE API error: ${resp.status}`);
    const json = await resp.json();
    return parseTeApiResponse(json);
  }

  // Fallback to FRED releases if no TE key
  const fredKey = process.env.FRED_API_KEY;
  if (!fredKey) throw new Error("No TRADINGECONOMICS_API_KEY or FRED_API_KEY set");

  const now = new Date();
  const future = new Date(now.getTime() + 14 * 24 * 60 * 60 * 1000);
  const params = new URLSearchParams({
    api_key: fredKey,
    file_type: "json",
    realtime_start: now.toISOString().split("T")[0],
    realtime_end: future.toISOString().split("T")[0],
    include_release_dates_with_no_data: "true",
  });

  const resp = await fetch(
    `https://api.stlouisfed.org/fred/releases/dates?${params}`,
    { signal: AbortSignal.timeout(30_000) },
  );
  if (!resp.ok) throw new Error(`FRED releases API error: ${resp.status}`);
  const data = await resp.json();
  const releases = data.release_dates || [];

  return releases
    .filter((r: Record<string, unknown>) => r.release_name && r.date)
    .map((r: Record<string, unknown>) => ({
      ts: `${r.date}T00:00:00Z`,
      event_name: String(r.release_name).slice(0, 500),
      importance: 1,
      actual: null,
      forecast: null,
      previous: null,
    }));
}

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
  const force = url.searchParams.get("force") === "1";

  if (!force && !isMarketOpen()) {
    try {
      await writeJobLog(supabase, {
        job_name: "econ-calendar",
        status: "SKIPPED",
        rows_affected: 0,
        duration_ms: Date.now() - startTime,
        error_message: "market_closed",
      });
    } catch {
      // Ignore logging failure to preserve skip response.
    }
    return NextResponse.json({ skipped: true, reason: "market_closed" });
  }

  try {
    const events = await fetchTeCalendar();

    let rowsAffected = 0;
    for (const event of events) {
      // Dedup by event_name + ts (no unique constraint on table)
      const { data: existing } = await supabase
        .from("econ_calendar")
        .select("id")
        .eq("ts", event.ts)
        .eq("event_name", event.event_name)
        .limit(1);

      if (!existing || existing.length === 0) {
        const { error } = await supabase.from("econ_calendar").insert({
          ts: event.ts,
          event_name: event.event_name,
          importance: event.importance,
          actual: event.actual,
          forecast: event.forecast,
          previous: event.previous,
        });
        if (error) throw new Error(`econ_calendar insert: ${error.message}`);
        rowsAffected++;
      }
    }

    const durationMs = Date.now() - startTime;
    await writeJobLog(supabase, {
      job_name: "econ-calendar",
      status: "SUCCESS",
      rows_affected: rowsAffected,
      duration_ms: durationMs,
    });

    return NextResponse.json({
      success: true,
      events: events.length,
      rows_affected: rowsAffected,
      duration_ms: durationMs,
    });
  } catch (error) {
    const message = error instanceof Error ? error.message : "Internal error";
    try {
      await writeJobLog(supabase, {
        job_name: "econ-calendar",
        status: "FAILED",
        rows_affected: 0,
        error_message: message,
        duration_ms: Date.now() - startTime,
      });
    } catch {
      // ignore logging failure
    }
    return NextResponse.json({ error: message }, { status: 500 });
  }
}
