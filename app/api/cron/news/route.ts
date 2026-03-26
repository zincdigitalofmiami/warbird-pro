import { NextResponse } from "next/server";
import { createAdminClient } from "@/lib/supabase/admin";
import { validateCronRequest } from "@/lib/cron-auth";

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

// Runs daily at 16:00 UTC. Generates news signals from macro report surprises.
// Reads macro_reports_1d for surprise values and creates directional signals.

export async function GET(request: Request) {
  const authError = validateCronRequest(request);
  if (authError) {
    return authError;
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
      const durationMs = Date.now() - startTime;
      await writeJobLog(supabase, {
        job_name: "news",
        status: "SKIPPED",
        rows_affected: 0,
        duration_ms: durationMs,
        error_message: "no_recent_reports",
      });

      return NextResponse.json({
        success: true,
        signals_created: 0,
        reason: "no_recent_reports",
        duration_ms: durationMs,
      });
    }

    const rowMap = new Map<
      string,
      {
        ts: string;
        signal_type: string;
        direction: "BULLISH" | "BEARISH";
        confidence: number;
        source_headline: string;
      }
    >();

    for (const report of reports) {
      const surprise = Number(report.surprise);
      if (isNaN(surprise) || surprise === 0) {
        continue;
      }

      const signalType = `macro_${report.report_type}`;
      rowMap.set(`${report.ts}::${signalType}`, {
        ts: report.ts,
        signal_type: signalType,
        direction: surprise > 0 ? "BULLISH" : "BEARISH",
        confidence: Math.min(Math.abs(surprise) / 2, 1),
        source_headline: `${report.report_type}: surprise ${surprise > 0 ? "+" : ""}${surprise.toFixed(2)}`,
      });
    }

    const rows = Array.from(rowMap.values());

    let signalsCreated = 0;
    if (rows.length > 0) {
      const { data: insertedRows, error: insertError } = await supabase
        .from("news_signals")
        .upsert(rows, {
          onConflict: "ts,signal_type",
          ignoreDuplicates: true,
        })
        .select("id");

      if (insertError) throw new Error(`news_signals upsert: ${insertError.message}`);
      signalsCreated = insertedRows?.length ?? 0;
    }

    const durationMs = Date.now() - startTime;
    await writeJobLog(supabase, {
      job_name: "news",
      status: signalsCreated > 0 ? "SUCCESS" : "SKIPPED",
      rows_affected: signalsCreated,
      duration_ms: durationMs,
      error_message: signalsCreated > 0 ? null : "no_new_signals",
    });

    return NextResponse.json({
      success: true,
      reports_processed: reports.length,
      signals_created: signalsCreated,
      duration_ms: durationMs,
    });
  } catch (e) {
    const message = e instanceof Error ? e.message : "Internal error";
    let finalMessage = message;
    try {
      await writeJobLog(supabase, {
        job_name: "news",
        status: "FAILED",
        rows_affected: 0,
        error_message: message,
        duration_ms: Date.now() - startTime,
      });
    } catch (logError) {
      finalMessage = `${message}; ${logError instanceof Error ? logError.message : String(logError)}`;
    }
    return NextResponse.json({ error: finalMessage }, { status: 500 });
  }
}
