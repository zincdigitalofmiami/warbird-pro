import { NextResponse } from "next/server";
import { createAdminClient } from "@/lib/supabase/admin";

/**
 * Admin Status API — returns system health, data coverage, job logs, and setup counts.
 * Powers the ShadCN admin dashboard.
 */

interface TableCoverage {
  table: string;
  latestTs: string | null;
  rowCount: number;
  staleness: string;
}

export async function GET() {
  try {
    const supabase = createAdminClient();

    // --- Data Coverage: check latest row + count for each key table ---
    const tablesToCheck = [
      "mes_1m",
      "mes_15m",
      "mes_1h",
      "mes_4h",
      "mes_1d",
      "cross_asset_1h",
      "cross_asset_1d",
      "warbird_setups",
      "measured_moves",
      "forecasts",
      "vol_states",
      "trade_scores",
    ];

    const coverage: TableCoverage[] = [];
    for (const table of tablesToCheck) {
      try {
        const { data: latest, error: latestErr } = await supabase
          .from(table)
          .select("ts")
          .order("ts", { ascending: false })
          .limit(1)
          .single();

        const { count, error: countErr } = await supabase
          .from(table)
          .select("*", { count: "exact", head: true });

        const latestTs =
          !latestErr && latest?.ts ? latest.ts : null;
        const rowCount = !countErr && count != null ? count : 0;

        // Calculate staleness
        let staleness = "unknown";
        if (latestTs) {
          const ageMs = Date.now() - new Date(latestTs).getTime();
          const ageMin = Math.floor(ageMs / 60_000);
          if (ageMin < 60) staleness = `${ageMin}m ago`;
          else if (ageMin < 1440) staleness = `${Math.floor(ageMin / 60)}h ago`;
          else staleness = `${Math.floor(ageMin / 1440)}d ago`;
        } else {
          staleness = "empty";
        }

        coverage.push({ table, latestTs, rowCount, staleness });
      } catch {
        coverage.push({ table, latestTs: null, rowCount: 0, staleness: "error" });
      }
    }

    // --- FRED / Econ tables ---
    const econTables = [
      "econ_rates_1d",
      "econ_yields_1d",
      "econ_fx_1d",
      "econ_vol_1d",
      "econ_inflation_1d",
      "econ_labor_1d",
      "econ_activity_1d",
      "econ_money_1d",
      "econ_commodities_1d",
      "econ_indexes_1d",
    ];

    for (const table of econTables) {
      try {
        const { data: latest } = await supabase
          .from(table)
          .select("ts")
          .order("ts", { ascending: false })
          .limit(1)
          .single();

        const { count } = await supabase
          .from(table)
          .select("*", { count: "exact", head: true });

        const latestTs = latest?.ts ?? null;
        const rowCount = count ?? 0;

        let staleness = "empty";
        if (latestTs) {
          const ageMs = Date.now() - new Date(latestTs).getTime();
          const ageMin = Math.floor(ageMs / 60_000);
          if (ageMin < 60) staleness = `${ageMin}m ago`;
          else if (ageMin < 1440) staleness = `${Math.floor(ageMin / 60)}h ago`;
          else staleness = `${Math.floor(ageMin / 1440)}d ago`;
        }

        coverage.push({ table, latestTs, rowCount, staleness });
      } catch {
        coverage.push({ table, latestTs: null, rowCount: 0, staleness: "error" });
      }
    }

    // --- News / Events tables ---
    const newsTables = [
      "econ_news_1d",
      "policy_news_1d",
      "macro_reports_1d",
      "econ_calendar",
      "news_signals",
      "geopolitical_risk_1d",
      "trump_effect_1d",
    ];

    for (const table of newsTables) {
      try {
        const { data: latest } = await supabase
          .from(table)
          .select("ts")
          .order("ts", { ascending: false })
          .limit(1)
          .single();

        const { count } = await supabase
          .from(table)
          .select("*", { count: "exact", head: true });

        coverage.push({
          table,
          latestTs: latest?.ts ?? null,
          rowCount: count ?? 0,
          staleness: latest?.ts
            ? (() => {
                const ageMin = Math.floor(
                  (Date.now() - new Date(latest.ts).getTime()) / 60_000,
                );
                if (ageMin < 60) return `${ageMin}m ago`;
                if (ageMin < 1440) return `${Math.floor(ageMin / 60)}h ago`;
                return `${Math.floor(ageMin / 1440)}d ago`;
              })()
            : "empty",
        });
      } catch {
        coverage.push({ table, latestTs: null, rowCount: 0, staleness: "error" });
      }
    }

    // --- Job Log: last 50 entries ---
    const { data: jobLogs } = await supabase
      .from("job_log")
      .select("*")
      .order("created_at", { ascending: false })
      .limit(50);

    // --- Active Setups ---
    const { data: activeSetups } = await supabase
      .from("warbird_setups")
      .select("*")
      .in("phase", ["TOUCHED", "HOOKED", "GO_FIRED", "TP1_HIT"])
      .order("ts", { ascending: false })
      .limit(30);

    // --- Recent Setups (last 7d) ---
    const weekAgo = new Date(Date.now() - 7 * 86400_000).toISOString();
    const { data: recentSetups } = await supabase
      .from("warbird_setups")
      .select("*")
      .gte("ts", weekAgo)
      .order("ts", { ascending: false })
      .limit(100);

    // --- Symbols ---
    const { data: symbols } = await supabase
      .from("symbols")
      .select("symbol_code, display_name, data_source, is_active")
      .order("symbol_code");

    // --- Latest Forecasts ---
    const { data: forecasts } = await supabase
      .from("forecasts")
      .select("*")
      .order("created_at", { ascending: false })
      .limit(20);

    // --- Measured Moves ---
    const { data: measuredMoves } = await supabase
      .from("measured_moves")
      .select("*")
      .order("ts", { ascending: false })
      .limit(20);

    return NextResponse.json({
      coverage,
      jobLogs: jobLogs ?? [],
      activeSetups: activeSetups ?? [],
      recentSetups: recentSetups ?? [],
      symbols: symbols ?? [],
      forecasts: forecasts ?? [],
      measuredMoves: measuredMoves ?? [],
      generatedAt: new Date().toISOString(),
    });
  } catch (e) {
    return NextResponse.json(
      { error: e instanceof Error ? e.message : "Internal error" },
      { status: 500 },
    );
  }
}
