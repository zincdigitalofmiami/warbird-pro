// Edge Function: massive-inflation
// Ported from app/api/cron/massive/inflation/route.ts
// Pulls /fed/v1/inflation from Massive and writes into econ_inflation_1d.
// Auth: x-cron-secret header validated against EDGE_CRON_SECRET env var.

import { createAdminClient } from "../_shared/admin.ts";
import { validateCronRequest } from "../_shared/cron-auth.ts";
import { ingestInflationFromMassive } from "../_shared/massive.ts";

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

  try {
    const url = new URL(req.url);
    const startDate = url.searchParams.get("start_date") ?? undefined;

    const result = await ingestInflationFromMassive({ startDate });
    const durationMs = Date.now() - startTime;

    await supabase.from("job_log").insert({
      job_name: "massive-inflation",
      status: result.rows_written > 0 ? "SUCCESS" : "SKIPPED",
      rows_affected: result.rows_written,
      duration_ms: durationMs,
      error_message: result.rows_written > 0 ? null : "no_rows_affected",
    });

    return jsonResponse({
      success: true,
      source: "massive",
      ...result,
      duration_ms: durationMs,
    });
  } catch (e) {
    const message = e instanceof Error ? e.message : "Internal error";
    let finalMessage = message;
    try {
      await supabase.from("job_log").insert({
        job_name: "massive-inflation",
        status: "FAILED",
        rows_affected: 0,
        duration_ms: Date.now() - startTime,
        error_message: message,
      });
    } catch (logError) {
      finalMessage = `${message}; ${logError instanceof Error ? logError.message : String(logError)}`;
    }
    return jsonResponse({ error: finalMessage }, 500);
  }
});
