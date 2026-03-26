import { NextResponse } from "next/server";
import { createAdminClient } from "@/lib/supabase/admin";
import { validateCronRequest } from "@/lib/cron-auth";
import { ingestInflationExpectationsFromMassive } from "@/lib/ingestion/massive";

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

// Runs daily. Pulls inflation-expectations from Massive /fed and writes
// provider-tagged series rows into econ_inflation_1d.

export async function GET(request: Request) {
  const authError = validateCronRequest(request);
  if (authError) {
    return authError;
  }

  const startTime = Date.now();
  const supabase = createAdminClient();

  try {
    const url = new URL(request.url);
    const startDate = url.searchParams.get("start_date") ?? undefined;

    const result = await ingestInflationExpectationsFromMassive({ startDate });
    const durationMs = Date.now() - startTime;

    await writeJobLog(supabase, {
      job_name: "massive-inflation-expectations",
      status: result.rows_written > 0 ? "SUCCESS" : "SKIPPED",
      rows_affected: result.rows_written,
      duration_ms: durationMs,
      error_message: result.rows_written > 0 ? null : "no_rows_affected",
    });

    return NextResponse.json({
      success: true,
      source: "massive",
      ...result,
      duration_ms: durationMs,
    });
  } catch (e) {
    const message = e instanceof Error ? e.message : "Internal error";
    let finalMessage = message;
    try {
      await writeJobLog(supabase, {
        job_name: "massive-inflation-expectations",
        status: "FAILED",
        rows_affected: 0,
        duration_ms: Date.now() - startTime,
        error_message: message,
      });
    } catch (logError) {
      finalMessage = `${message}; ${logError instanceof Error ? logError.message : String(logError)}`;
    }
    return NextResponse.json({ error: finalMessage }, { status: 500 });
  }
}
