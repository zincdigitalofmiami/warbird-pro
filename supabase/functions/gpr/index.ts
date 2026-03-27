// GPR Edge Function — Caldara-Iacoviello Geopolitical Risk Index
// Ported from app/api/cron/gpr/route.ts — NextResponse → Response, xlsx → npm:xlsx
// Schedule: daily at 19:00 UTC Mon-Fri (0 19 * * 1-5)
// Source: https://www.matteoiacoviello.com/gpr_files/data_gpr_daily_recent.xls
// No API key needed — public XLS file.

import * as XLSX from "npm:xlsx";
import { validateCronRequest } from "../_shared/cron-auth.ts";
import { createAdminClient } from "../_shared/admin.ts";
import { writeJobLog } from "../_shared/job-log.ts";

const GPR_URL =
  "https://www.matteoiacoviello.com/gpr_files/data_gpr_daily_recent.xls";

type XlsxRow = Record<string, string | number | null | undefined>;

function toNumber(value: string | number | null | undefined): number {
  if (typeof value === "number") return value;
  if (typeof value === "string") return Number.parseFloat(value);
  return Number.NaN;
}

Deno.serve(async (req: Request) => {
  const authError = validateCronRequest(req);
  if (authError) return authError;

  const startTime = Date.now();
  const supabase = createAdminClient();

  try {
    const response = await fetch(GPR_URL, {
      signal: AbortSignal.timeout(30_000),
    });

    if (!response.ok) {
      throw new Error(`GPR fetch failed: ${response.status}`);
    }

    const buffer = await response.arrayBuffer();
    const workbook = XLSX.read(new Uint8Array(buffer), { type: "array" });
    const sheet = workbook.Sheets[workbook.SheetNames[0]];
    const jsonData = XLSX.utils.sheet_to_json<XlsxRow>(sheet);

    const rows: {
      ts: string;
      gpr_daily: number;
      gpr_threats: number | null;
      gpr_acts: number | null;
    }[] = [];

    for (const row of jsonData) {
      // Find the date column — could be "DAY", "day", "date", or a number (Excel serial date)
      const dateVal = row["DAY"] ?? row["day"] ?? row["date"] ?? row["Date"];
      if (dateVal === undefined) continue;

      let ts: string;
      if (typeof dateVal === "number") {
        // Excel serial date → JS Date
        const d = XLSX.SSF.parse_date_code(dateVal);
        ts = `${d.y}-${String(d.m).padStart(2, "0")}-${String(d.d).padStart(2, "0")}T00:00:00Z`;
      } else {
        const dayStr = String(dateVal).trim();
        if (/^\d{8}$/.test(dayStr)) {
          ts = `${dayStr.slice(0, 4)}-${dayStr.slice(4, 6)}-${dayStr.slice(6, 8)}T00:00:00Z`;
        } else if (/^\d{4}-\d{2}-\d{2}/.test(dayStr)) {
          ts = dayStr.slice(0, 10) + "T00:00:00Z";
        } else {
          continue;
        }
      }

      // GPR columns: GPRD or gpr_daily, GPR_T or gpr_threats, GPR_A or gpr_acts
      const gprDaily = toNumber(row["GPRD"] ?? row["gpr_daily"] ?? row["GPR"]);
      if (isNaN(gprDaily)) continue;

      const gprThreats = toNumber(row["GPR_T"] ?? row["gpr_threats"]);
      const gprActs = toNumber(row["GPR_A"] ?? row["gpr_acts"]);

      rows.push({
        ts,
        gpr_daily: gprDaily,
        gpr_threats: isNaN(gprThreats) ? null : gprThreats,
        gpr_acts: isNaN(gprActs) ? null : gprActs,
      });
    }

    // Only upsert last 30 days
    const cutoff = new Date();
    cutoff.setDate(cutoff.getDate() - 30);
    const recentRows = rows.filter((r) => new Date(r.ts) >= cutoff);

    if (recentRows.length > 0) {
      const { error } = await supabase
        .from("geopolitical_risk_1d")
        .upsert(recentRows, { onConflict: "ts" });
      if (error) throw new Error(`GPR upsert failed: ${error.message}`);
    }

    const durationMs = Date.now() - startTime;
    await writeJobLog({
      job_name: "gpr",
      status: recentRows.length > 0 ? "SUCCESS" : "SKIPPED",
      rows_affected: recentRows.length,
      duration_ms: durationMs,
      error_message: recentRows.length > 0 ? null : "no_recent_rows",
    });

    return new Response(
      JSON.stringify({
        success: true,
        rows_total: rows.length,
        rows_affected: recentRows.length,
        duration_ms: durationMs,
      }),
      { status: 200, headers: { "Content-Type": "application/json" } },
    );
  } catch (e) {
    const message = e instanceof Error ? e.message : "Internal error";
    let finalMessage = message;
    try {
      await writeJobLog({
        job_name: "gpr",
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
