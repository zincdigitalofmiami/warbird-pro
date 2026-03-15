import { NextResponse } from "next/server";
import { createAdminClient } from "@/lib/supabase/admin";
import { isMarketOpen } from "@/lib/market-hours";

export const maxDuration = 60;

// Runs every hour on weekdays at :30.
// Reads latest predictions from the forecasts table (written by predict-warbird.py)
// and serves them via API. Also checks for stale predictions and logs status.

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
    // Get latest forecasts (last 4 hours to catch all horizons)
    const cutoff = new Date(Date.now() - 4 * 60 * 60 * 1000).toISOString();
    const { data: forecasts, error } = await supabase
      .from("forecasts")
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
      status: forecasts && forecasts.length > 0 ? "OK" : "NO_DATA",
      rows_written: 0,
      duration_ms: duration,
      meta: {
        forecast_count: forecasts?.length ?? 0,
        stale,
        current_price: currentPrice,
      },
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
      status: "ERROR",
      rows_written: 0,
      duration_ms: duration,
      meta: { error: message },
    });

    return NextResponse.json({ error: message, duration_ms: duration }, { status: 500 });
  }
}
