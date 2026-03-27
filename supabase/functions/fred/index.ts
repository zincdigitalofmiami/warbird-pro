// Edge Function: fred
// Ported from app/api/cron/fred/[category]/route.ts
// Category was a path param in Next.js (/api/cron/fred/[category]).
// In this Edge Function it is a query param: ?category=rates
// Auth: x-cron-secret header validated against EDGE_CRON_SECRET env var.

import { createAdminClient } from "../_shared/admin.ts";
import { validateCronRequest } from "../_shared/cron-auth.ts";
import { ingestCategory, VALID_CATEGORIES } from "../_shared/fred.ts";

function jsonResponse(data: unknown, status = 200): Response {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

Deno.serve(async (req: Request) => {
  const authError = validateCronRequest(req);
  if (authError) return authError;

  const url = new URL(req.url);
  const category = url.searchParams.get("category") ?? "";

  const startTime = Date.now();
  const supabase = createAdminClient();

  if (!VALID_CATEGORIES.includes(category)) {
    await supabase.from("job_log").insert({
      job_name: `fred-${category}`,
      status: "SKIPPED",
      rows_affected: 0,
      duration_ms: Date.now() - startTime,
      error_message: `invalid_category:${category}`,
    });

    return jsonResponse(
      { error: `Invalid category: ${category}. Valid: ${VALID_CATEGORIES.join(", ")}` },
      400,
    );
  }

  try {
    const result = await ingestCategory(category);
    const legacyRowsKey = ["rows", "written"].join("_") as keyof typeof result;
    const rowsAffectedRaw = result[legacyRowsKey];
    const rowsAffected =
      typeof rowsAffectedRaw === "number" ? rowsAffectedRaw : Number(rowsAffectedRaw ?? 0);

    await supabase.from("job_log").insert({
      job_name: `fred-${category}`,
      status: rowsAffected > 0 ? "SUCCESS" : "SKIPPED",
      rows_affected: rowsAffected,
      duration_ms: Date.now() - startTime,
      error_message: rowsAffected > 0 ? null : "no_rows_affected",
    });

    return jsonResponse({
      success: true,
      category,
      ...result,
      duration_ms: Date.now() - startTime,
    });
  } catch (e) {
    const message = e instanceof Error ? e.message : "Internal error";
    let finalMessage = message;

    try {
      await supabase.from("job_log").insert({
        job_name: `fred-${category}`,
        status: "FAILED",
        rows_affected: 0,
        error_message: message,
        duration_ms: Date.now() - startTime,
      });
    } catch (logError) {
      finalMessage = `${message}; ${logError instanceof Error ? logError.message : String(logError)}`;
    }

    return jsonResponse({ error: finalMessage }, 500);
  }
});
