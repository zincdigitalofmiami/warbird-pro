import { NextResponse } from "next/server";
import { createAdminClient } from "@/lib/supabase/admin";
import { ingestCategory, VALID_CATEGORIES } from "@/lib/ingestion/fred";

export const maxDuration = 60;

// Dynamic route: /api/cron/fred/rates, /api/cron/fred/yields, etc.
// Each category is a separate Vercel Cron entry, staggered hourly.

export async function GET(
  request: Request,
  { params }: { params: Promise<{ category: string }> },
) {
  const cronSecret = process.env.CRON_SECRET;
  if (cronSecret) {
    const auth = request.headers.get("authorization");
    if (auth !== `Bearer ${cronSecret}`) {
      return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
    }
  }

  const { category } = await params;

  if (!VALID_CATEGORIES.includes(category)) {
    return NextResponse.json(
      { error: `Invalid category: ${category}. Valid: ${VALID_CATEGORIES.join(", ")}` },
      { status: 400 },
    );
  }

  const startTime = Date.now();

  try {
    const result = await ingestCategory(category);

    // Log to job_log
    const supabase = createAdminClient();
    await supabase.from("job_log").insert({
      job_name: `fred-${category}`,
      status: "OK",
      rows_written: result.rows_written,
      duration_ms: Date.now() - startTime,
    });

    return NextResponse.json({
      success: true,
      category,
      ...result,
      duration_ms: Date.now() - startTime,
    });
  } catch (e) {
    const message = e instanceof Error ? e.message : "Internal error";

    try {
      const supabase = createAdminClient();
      await supabase.from("job_log").insert({
        job_name: `fred-${category}`,
        status: "ERROR",
        error_message: message,
        duration_ms: Date.now() - startTime,
      });
    } catch {
      // ignore logging failure
    }

    return NextResponse.json({ error: message }, { status: 500 });
  }
}
