import { NextResponse } from "next/server";
import { createAdminClient } from "@/lib/supabase/admin";

export const maxDuration = 60;

// Runs daily at 19:30 UTC.
// Fetches executive orders + presidential documents from Federal Register API.
// Also fetches EPU index from FRED for policy uncertainty signal.
// Source: https://www.federalregister.gov/api/v1 (free, no key needed)

const FR_API = "https://www.federalregister.gov/api/v1/documents.json";

type JobLogStatus = "SUCCESS" | "PARTIAL" | "FAILED" | "SKIPPED";

type FrDocument = {
  title?: string;
  abstract?: string;
  publication_date?: string;
  html_url?: string;
};

type FrApiResponse = {
  results?: FrDocument[];
};

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
    // Fetch recent presidential documents (last 7 days)
    const since = new Date();
    since.setDate(since.getDate() - 7);
    const sinceStr = since.toISOString().split("T")[0];

    const fields = ["title", "abstract", "publication_date", "html_url"].map(f => `fields[]=${f}`).join("&");
    const dateCond = `conditions[publication_date][gte]=${sinceStr}`;
    const base = `${FR_API}?per_page=20&order=newest&${fields}&${dateCond}`;

    const eoUrl = `${base}&conditions[presidential_document_type][]=executive_order`;
    const memoUrl = `${base}&conditions[presidential_document_type][]=memorandum`;

    const [eoRes, memoRes] = await Promise.all([
      fetch(eoUrl, { signal: AbortSignal.timeout(30_000) }),
      fetch(memoUrl, { signal: AbortSignal.timeout(30_000) }),
    ]);

    if (!eoRes.ok) throw new Error(`FR API (EO) error: ${eoRes.status}`);
    if (!memoRes.ok) throw new Error(`FR API (memo) error: ${memoRes.status}`);

    const eoData = (await eoRes.json()) as FrApiResponse;
    const memoData = (await memoRes.json()) as FrApiResponse;

    const allDocs = [
      ...(eoData.results || []).map((d) => ({ ...d, event_type: "executive_order" as const })),
      ...(memoData.results || []).map((d) => ({ ...d, event_type: "memorandum" as const })),
    ];

    const rows = allDocs
      .filter((d) => d.title && d.publication_date)
      .map((d) => ({
        ts: `${d.publication_date}T00:00:00Z`,
        event_type: d.event_type,
        title: d.title!.slice(0, 500),
        summary: d.abstract?.slice(0, 1000) || null,
        source: "federal_register",
        source_url: d.html_url || null,
      }));

    let rowsAffected = 0;
    if (rows.length > 0) {
      // Use insert (not upsert) since trump_effect_1d uses auto-increment ID.
      // Check for duplicates by title + ts to avoid re-inserting.
      for (const row of rows) {
        const { data: existing } = await supabase
          .from("trump_effect_1d")
          .select("id")
          .eq("ts", row.ts)
          .eq("title", row.title)
          .limit(1);

        if (!existing || existing.length === 0) {
          const { error } = await supabase.from("trump_effect_1d").insert(row);
          if (error) throw new Error(`trump_effect insert: ${error.message}`);
          rowsAffected++;
        }
      }
    }

    const durationMs = Date.now() - startTime;
    await writeJobLog(supabase, {
      job_name: "trump-effect",
      status: rowsAffected > 0 ? "SUCCESS" : "SKIPPED",
      rows_affected: rowsAffected,
      duration_ms: durationMs,
      error_message: rowsAffected > 0 ? null : "no_new_documents",
    });

    return NextResponse.json({
      success: true,
      docs_found: allDocs.length,
      rows_affected: rowsAffected,
      duration_ms: durationMs,
    });
  } catch (e) {
    const message = e instanceof Error ? e.message : "Internal error";
    let finalMessage = message;
    try {
      await writeJobLog(supabase, {
        job_name: "trump-effect",
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
