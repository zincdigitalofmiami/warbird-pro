// Executive Orders Edge Function — Federal Register executive orders + memoranda
// Source: https://www.federalregister.gov/api/v1 (free, no key needed)
// Schedule: daily at 08:00 UTC Mon-Fri

import { validateCronRequest } from "../_shared/cron-auth.ts";
import { createAdminClient } from "../_shared/admin.ts";
import { writeJobLog } from "../_shared/job-log.ts";

const FR_API = "https://www.federalregister.gov/api/v1/documents.json";

type FrDocument = {
  title?: string;
  abstract?: string;
  publication_date?: string;
  html_url?: string;
};

type FrApiResponse = {
  results?: FrDocument[];
};

Deno.serve(async (req: Request) => {
  const authError = validateCronRequest(req);
  if (authError) return authError;

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

    const dedupedRows = Array.from(
      new Map(rows.map((row) => [`${row.ts}::${row.title}`, row])).values(),
    );

    let rowsAffected = 0;
    if (dedupedRows.length > 0) {
      const { data: insertedRows, error } = await supabase
        .from("executive_orders_1d")
        .upsert(dedupedRows, {
          onConflict: "ts,title",
          ignoreDuplicates: true,
        })
        .select("id");

      if (error) throw new Error(`executive_orders upsert: ${error.message}`);
      rowsAffected = insertedRows?.length ?? 0;
    }

    const durationMs = Date.now() - startTime;
    await writeJobLog({
      job_name: "exec-orders",
      status: rowsAffected > 0 ? "SUCCESS" : "SKIPPED",
      rows_affected: rowsAffected,
      duration_ms: durationMs,
      error_message: rowsAffected > 0 ? null : "no_new_documents",
    });

    return new Response(
      JSON.stringify({
        success: true,
        docs_found: allDocs.length,
        rows_affected: rowsAffected,
        duration_ms: durationMs,
      }),
      { status: 200, headers: { "Content-Type": "application/json" } },
    );
  } catch (e) {
    const message = e instanceof Error ? e.message : "Internal error";
    let finalMessage = message;
    try {
      await writeJobLog({
        job_name: "exec-orders",
        status: "FAILED",
        rows_affected: 0,
        duration_ms: Date.now() - startTime,
        error_message: message,
      });
    } catch (logError) {
      finalMessage = `${message}; ${logError instanceof Error ? logError.message : String(logError)}`;
    }
    return new Response(
      JSON.stringify({ error: finalMessage }),
      { status: 500, headers: { "Content-Type": "application/json" } },
    );
  }
});
