// Edge Function: econ-calendar
// Ported from app/api/cron/econ-calendar/route.ts
// Fetches upcoming FRED release dates and upserts into econ_calendar.
// Auth: x-cron-secret header validated against EDGE_CRON_SECRET env var.
// Schedule: daily at 04:20 UTC Mon-Fri.

import { createAdminClient } from "../_shared/admin.ts";
import { validateCronRequest } from "../_shared/cron-auth.ts";
import { isMarketOpen } from "../_shared/market-hours.ts";
import { writeJobLog } from "../_shared/job-log.ts";

type CalendarEvent = {
  ts: string;
  event_name: string;
  importance: number;
  actual: number | null;
  forecast: number | null;
  previous: number | null;
};

async function fetchFredCalendar(): Promise<CalendarEvent[]> {
  const fredKey = Deno.env.get("FRED_API_KEY");
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
  const force = url.searchParams.get("force") === "1";

  if (!force && !isMarketOpen()) {
    try {
      await writeJobLog({
        job_name: "econ-calendar",
        status: "SKIPPED",
        rows_affected: 0,
        duration_ms: Date.now() - startTime,
        error_message: "market_closed",
      });
    } catch {
      // Ignore logging failure to preserve skip response.
    }
    return jsonResponse({ skipped: true, reason: "market_closed" });
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
    await writeJobLog({
      job_name: "econ-calendar",
      status: "SUCCESS",
      rows_affected: rowsAffected,
      duration_ms: durationMs,
    });

    return jsonResponse({
      success: true,
      events: events.length,
      rows_affected: rowsAffected,
      duration_ms: durationMs,
    });
  } catch (e) {
    const message = e instanceof Error ? e.message : "Internal error";
    let finalMessage = message;
    try {
      await writeJobLog({
        job_name: "econ-calendar",
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
