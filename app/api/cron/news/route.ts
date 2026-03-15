import { NextResponse } from "next/server";
import { createAdminClient } from "@/lib/supabase/admin";

export const maxDuration = 60;

// Runs daily at 16:00 UTC. Generates news signals from macro report surprises.
// Reads macro_reports_1d for surprise values and creates directional signals.

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
    // Look at recent macro reports with surprise values
    const since = new Date();
    since.setDate(since.getDate() - 1);

    const { data: reports, error: repErr } = await supabase
      .from("macro_reports_1d")
      .select("*")
      .gte("ts", since.toISOString())
      .not("surprise", "is", null);

    if (repErr) throw new Error(`macro_reports query: ${repErr.message}`);

    if (!reports || reports.length === 0) {
      return NextResponse.json({
        success: true,
        signals_created: 0,
        reason: "no_recent_reports",
        duration_ms: Date.now() - startTime,
      });
    }

    let signalsCreated = 0;

    for (const report of reports) {
      const surprise = Number(report.surprise);
      if (isNaN(surprise) || surprise === 0) continue;

      // Generate signal: positive surprise → BULLISH, negative → BEARISH
      const direction = surprise > 0 ? "BULLISH" : "BEARISH";
      const confidence = Math.min(Math.abs(surprise) / 2, 1); // Normalize to 0-1

      // Dedup
      const { data: existing } = await supabase
        .from("news_signals")
        .select("id")
        .eq("ts", report.ts)
        .eq("signal_type", `macro_${report.report_type}`)
        .limit(1);

      if (!existing || existing.length === 0) {
        const { error } = await supabase.from("news_signals").insert({
          ts: report.ts,
          signal_type: `macro_${report.report_type}`,
          direction,
          confidence,
          source_headline: `${report.report_type}: surprise ${surprise > 0 ? "+" : ""}${surprise.toFixed(2)}`,
        });
        if (error) throw new Error(`news_signals insert: ${error.message}`);
        signalsCreated++;
      }
    }

    await supabase.from("job_log").insert({
      job_name: "news",
      status: "OK",
      rows_written: signalsCreated,
      duration_ms: Date.now() - startTime,
    });

    return NextResponse.json({
      success: true,
      reports_processed: reports.length,
      signals_created: signalsCreated,
      duration_ms: Date.now() - startTime,
    });
  } catch (e) {
    const message = e instanceof Error ? e.message : "Internal error";
    try {
      await supabase.from("job_log").insert({
        job_name: "news",
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
