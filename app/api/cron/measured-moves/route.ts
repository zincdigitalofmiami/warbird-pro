import { NextResponse } from "next/server";
import { createAdminClient } from "@/lib/supabase/admin";
import { validateCronRequest } from "@/lib/cron-auth";

export const maxDuration = 60;

// Retired as a writer path.
// detect-setups is the canonical measured_moves writer.

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
      job_name: "measured-moves",
      status: "SKIPPED",
      rows_affected: 0,
      duration_ms: Date.now() - startTime,
      error_message: "retired_canonical_writer_detect_setups",
    });

    return NextResponse.json({
      skipped: true,
      reason: "retired_canonical_writer_detect_setups",
      duration_ms: Date.now() - startTime,
    });
  } catch (e) {
    const message = e instanceof Error ? e.message : "Internal error";
    try {
      await writeJobLog(supabase, {
        job_name: "measured-moves",
        status: "FAILED",
        error_message: message,
        duration_ms: Date.now() - startTime,
      });
    } catch {
      // ignore
    }
    return NextResponse.json({ error: message }, { status: 500 });
  }
}
