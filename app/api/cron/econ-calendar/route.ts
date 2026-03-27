import { NextResponse } from "next/server";
import { createAdminClient } from "@/lib/supabase/admin";
import { validateCronRequest } from "@/lib/cron-auth";
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

type CalendarEvent = {
  ts: string;
  event_name: string;
  importance: number;
  actual: number | null;
  forecast: number | null;
  previous: number | null;
};

async function fetchFredCalendar(): Promise<CalendarEvent[]> {
  const fredKey = process.env.FRED_API_KEY;
  if (!fredKey) throw new Error("No FRED_API_KEY set");

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
  const authError = validateCronRequest(request);
  if (authError) {
    return authError;
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
    const events = await fetchFredCalendar();

    const rows = Array.from(
      new Map(
        events.map((event) => [
          `${event.ts}::${event.event_name}`,
          {
            ts: event.ts,
            event_name: event.event_name,
            importance: event.importance,
            actual: event.actual,
            forecast: event.forecast,
            previous: event.previous,
          },
        ]),
      ).values(),
    );

    let rowsAffected = 0;
    if (rows.length > 0) {
      const { data: insertedRows, error } = await supabase
        .from("econ_calendar")
        .upsert(rows, {
          onConflict: "ts,event_name",
          ignoreDuplicates: true,
        })
        .select("id");

      if (error) throw new Error(`econ_calendar upsert: ${error.message}`);
      rowsAffected = insertedRows?.length ?? 0;
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
