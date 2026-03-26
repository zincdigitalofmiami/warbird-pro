import { NextResponse } from "next/server";
import { createAdminClient } from "@/lib/supabase/admin";
import { validateCronRequest } from "@/lib/cron-auth";

export const maxDuration = 60;

type JobLogPayload = {
  job_name: string;
  status: "SUCCESS" | "PARTIAL" | "FAILED" | "SKIPPED";
  rows_affected?: number;
  duration_ms: number;
  error_message?: string;
};

async function writeJobLog(
  supabase: ReturnType<typeof createAdminClient>,
  payload: JobLogPayload,
) {
  const { error } = await supabase.from("job_log").insert(payload);
  if (error) {
    throw new Error(`job_log insert failed: ${error.message}`);
  }
}

export async function GET(request: Request) {
  const authError = validateCronRequest(request);
  if (authError) {
    return authError;
  }

  const startTime = Date.now();
  const supabase = createAdminClient();

  try {
    await writeJobLog(supabase, {
      job_name: "forecast-check",
      status: "SKIPPED",
      rows_affected: 0,
      duration_ms: Date.now() - startTime,
      error_message: "legacy_forecast_path_removed",
    });

    return NextResponse.json({
      skipped: true,
      reason: "legacy_forecast_path_removed",
      duration_ms: Date.now() - startTime,
    });
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    const duration = Date.now() - startTime;

    await writeJobLog(supabase, {
      job_name: "forecast-check",
      status: "FAILED",
      rows_affected: 0,
      duration_ms: duration,
      error_message: message,
    });

    return NextResponse.json(
      {
        error: message,
        duration_ms: duration,
      },
      { status: 500 },
    );
  }
}
