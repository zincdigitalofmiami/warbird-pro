import { NextResponse } from "next/server";
import { createAdminClient } from "@/lib/supabase/admin";

export const maxDuration = 60;

// Runs daily at 15:00 UTC. Populates econ_calendar with upcoming events.
// Uses FRED release calendar as primary source.

const FRED_RELEASES_URL = "https://api.stlouisfed.org/fred/releases/dates";

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

  try {
    const apiKey = process.env.FRED_API_KEY;
    if (!apiKey) throw new Error("FRED_API_KEY is not set");

    // Fetch upcoming releases for next 7 days
    const now = new Date();
    const future = new Date(now.getTime() + 7 * 24 * 60 * 60 * 1000);

    const params = new URLSearchParams({
      api_key: apiKey,
      file_type: "json",
      realtime_start: now.toISOString().split("T")[0],
      realtime_end: future.toISOString().split("T")[0],
      include_release_dates_with_no_data: "true",
    });

    const response = await fetch(`${FRED_RELEASES_URL}?${params}`, {
      signal: AbortSignal.timeout(30_000),
    });

    if (!response.ok) {
      throw new Error(`FRED releases API error: ${response.status}`);
    }

    const data = await response.json();
    const releases = data.release_dates || [];

    const rows = releases
      .filter((r: any) => r.release_name && r.date)
      .map((r: any) => ({
        ts: `${r.date}T00:00:00Z`,
        event_name: r.release_name.slice(0, 500),
        importance: 1,
      }));

    let rowsWritten = 0;
    for (const row of rows) {
      // Dedup by event_name + ts
      const { data: existing } = await supabase
        .from("econ_calendar")
        .select("id")
        .eq("ts", row.ts)
        .eq("event_name", row.event_name)
        .limit(1);

      if (!existing || existing.length === 0) {
        const { error } = await supabase.from("econ_calendar").insert(row);
        if (error) throw new Error(`econ_calendar insert: ${error.message}`);
        rowsWritten++;
      }
    }

    await supabase.from("job_log").insert({
      job_name: "econ-calendar",
      status: "OK",
      rows_written: rowsWritten,
      duration_ms: Date.now() - startTime,
    });

    return NextResponse.json({
      success: true,
      releases_found: releases.length,
      rows_written: rowsWritten,
      duration_ms: Date.now() - startTime,
    });
  } catch (e) {
    const message = e instanceof Error ? e.message : "Internal error";
    try {
      await supabase.from("job_log").insert({
        job_name: "econ-calendar",
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
