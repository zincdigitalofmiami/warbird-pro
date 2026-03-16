import { NextResponse } from "next/server";
import { createAdminClient } from "@/lib/supabase/admin";
import { isMarketOpen } from "@/lib/market-hours";

export const maxDuration = 60;

// Runs every hour on weekdays at :30.
// Health-checks the canonical warbird_forecasts_1h table and records staleness.

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

  // Skip outside market hours unless forced
  const force = new URL(request.url).searchParams.get("force") === "1";
  if (!force && !isMarketOpen()) {
    return NextResponse.json({ skipped: true, reason: "market_closed" });
  }

  try {
    // Get latest 1H forecasts from the last 4 hours
    const cutoff = new Date(Date.now() - 4 * 60 * 60 * 1000).toISOString();
    const { data: forecasts, error } = await supabase
      .from("warbird_forecasts_1h")
      .select("*")
      .gte("ts", cutoff)
      .order("ts", { ascending: false });

    if (error) throw error;

    // Get latest MES price for context
    const { data: latestBar } = await supabase
      .from("mes_15m")
      .select("ts, close")
      .order("ts", { ascending: false })
      .limit(1)
      .single();

    const currentPrice = latestBar ? Number(latestBar.close) : null;

    // Check staleness — warn if newest forecast is > 2 hours old
    let stale = false;
    if (forecasts && forecasts.length > 0) {
      const newestTs = new Date(forecasts[0].ts).getTime();
      stale = Date.now() - newestTs > 2 * 60 * 60 * 1000;
    }

    const duration = Date.now() - startTime;

    // Log to job_log
    await supabase.from("job_log").insert({
      job_name: "forecast-check",
      status: forecasts && forecasts.length > 0 ? "SUCCESS" : "SKIPPED",
      rows_affected: forecasts?.length ?? 0,
      duration_ms: duration,
      error_message:
        forecasts && forecasts.length > 0
          ? null
          : `No warbird_forecasts_1h rows found since ${cutoff} (stale=${stale}, current_price=${currentPrice ?? "n/a"})`,
    });

    return NextResponse.json({
      success: true,
      forecasts: forecasts ?? [],
      current_price: currentPrice,
      stale,
      duration_ms: duration,
    });
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    const duration = Date.now() - startTime;

    await supabase.from("job_log").insert({
      job_name: "forecast-check",
      status: "FAILED",
      rows_affected: 0,
      duration_ms: duration,
      error_message: message,
    });

    return NextResponse.json({ error: message, duration_ms: duration }, { status: 500 });
  }
}
