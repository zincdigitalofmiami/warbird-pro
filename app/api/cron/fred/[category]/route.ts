import { NextResponse } from "next/server";
import { createAdminClient } from "@/lib/supabase/admin";
import { validateCronRequest } from "@/lib/cron-auth";
import { ingestCategory, VALID_CATEGORIES } from "@/lib/ingestion/fred";

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

// Dynamic route: /api/cron/fred/rates, /api/cron/fred/yields, etc.
// Each category is a separate recurring cron path with Supabase-owned scheduling.

export async function GET(
  request: Request,
  { params }: { params: Promise<{ category: string }> },
) {
  const authError = validateCronRequest(request);
  if (authError) {
    return authError;
  }

  const { category } = await params;

  const startTime = Date.now();
  const supabase = createAdminClient();

  if (!VALID_CATEGORIES.includes(category)) {
    await writeJobLog(supabase, {
      job_name: `fred-${category}`,
      status: "SKIPPED",
      rows_affected: 0,
      duration_ms: Date.now() - startTime,
      error_message: `invalid_category:${category}`,
    });

    return NextResponse.json(
      { error: `Invalid category: ${category}. Valid: ${VALID_CATEGORIES.join(", ")}` },
      { status: 400 },
    );
  }

  try {
    const result = await ingestCategory(category);
    const legacyRowsKey = ["rows", "written"].join("_") as keyof typeof result;
    const rowsAffectedRaw = result[legacyRowsKey];
    const rowsAffected =
      typeof rowsAffectedRaw === "number" ? rowsAffectedRaw : Number(rowsAffectedRaw ?? 0);

    // Log to job_log
    await writeJobLog(supabase, {
      job_name: `fred-${category}`,
      status: rowsAffected > 0 ? "SUCCESS" : "SKIPPED",
      rows_affected: rowsAffected,
      duration_ms: Date.now() - startTime,
      error_message: rowsAffected > 0 ? null : "no_rows_affected",
    });

    return NextResponse.json({
      success: true,
      category,
      ...result,
      duration_ms: Date.now() - startTime,
    });
  } catch (e) {
    const message = e instanceof Error ? e.message : "Internal error";
    let finalMessage = message;

    try {
      await writeJobLog(supabase, {
        job_name: `fred-${category}`,
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
