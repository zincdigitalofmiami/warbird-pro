import { NextResponse } from "next/server";
import { createAdminClient } from "@/lib/supabase/admin";
import * as XLSX from "xlsx";

export const maxDuration = 60;

// Runs daily at 19:00 UTC. Fetches Caldara-Iacoviello GPR index.
// Source: https://www.matteoiacoviello.com/gpr_files/data_gpr_daily_recent.xls
// File is binary XLS — parsed with xlsx package.

const GPR_URL =
  "https://www.matteoiacoviello.com/gpr_files/data_gpr_daily_recent.xls";

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
    const response = await fetch(GPR_URL, {
      signal: AbortSignal.timeout(30_000),
    });

    if (!response.ok) {
      throw new Error(`GPR fetch failed: ${response.status}`);
    }

    const buffer = await response.arrayBuffer();
    const workbook = XLSX.read(new Uint8Array(buffer), { type: "array" });
    const sheet = workbook.Sheets[workbook.SheetNames[0]];
    const jsonData: Record<string, any>[] = XLSX.utils.sheet_to_json(sheet);

    const rows: {
      ts: string;
      gpr_daily: number;
      gpr_threats: number | null;
      gpr_acts: number | null;
    }[] = [];

    for (const row of jsonData) {
      // Find the date column — could be "DAY", "day", "date", or a number (Excel serial date)
      let dateVal = row["DAY"] ?? row["day"] ?? row["date"] ?? row["Date"];
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
      const gprDaily = parseFloat(row["GPRD"] ?? row["gpr_daily"] ?? row["GPR"] ?? "");
      if (isNaN(gprDaily)) continue;

      const gprThreats = parseFloat(row["GPR_T"] ?? row["gpr_threats"] ?? "");
      const gprActs = parseFloat(row["GPR_A"] ?? row["gpr_acts"] ?? "");

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

    await supabase.from("job_log").insert({
      job_name: "gpr",
      status: "OK",
      rows_written: recentRows.length,
      duration_ms: Date.now() - startTime,
    });

    return NextResponse.json({
      success: true,
      rows_total: rows.length,
      rows_written: recentRows.length,
      duration_ms: Date.now() - startTime,
    });
  } catch (e) {
    const message = e instanceof Error ? e.message : "Internal error";
    try {
      await supabase.from("job_log").insert({
        job_name: "gpr",
        status: "ERROR",
        error_message: message,
        duration_ms: Date.now() - startTime,
      });
    } catch {
      // ignore
    }
    return NextResponse.json({ error: message }, { status: 500 });
  }
}
