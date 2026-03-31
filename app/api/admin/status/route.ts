import { NextResponse } from "next/server";
import { createClient } from "@/lib/supabase/server";

/**
 * Admin Status API — returns system health, data coverage, job logs,
 * and candidate/signal rows from the canonical warbird schema.
 */

interface TableCoverage {
  table: string;
  latestTs: string | null;
  rowCount: number;
  staleness: string;
}

type TargetHitState = "HIT" | "MISS" | "OPEN";
type OutcomeState = "TP2_HIT" | "TP1_ONLY" | "STOPPED" | "REVERSAL" | "OPEN";

interface CandidateRow {
  candidate_id: number;
  signal_id: string | null;
  bar_close_ts: string;
  symbol_code: string;
  direction: string;
  anchor_price: number | null;
  target_price: number | null;
  entry_price: number | null;
  stop_loss: number | null;
  tp1_price: number | null;
  tp2_price: number | null;
  fib_level_touched: string | null;
  fib_ratio: number | null;
  setup_archetype: string | null;
  confidence_score: number | null;
  decision_code: string | null;
  tp1_probability: number | null;
  tp2_probability: number | null;
  reversal_risk: number | null;
  target_hit_state: TargetHitState;
  outcome_state: OutcomeState;
  status: string;
  emitted_at: string | null;
  packet_id: string | null;
}

interface SymbolEntry {
  code: string;
  display_name: string;
  data_source: string;
  is_active: boolean;
}

export async function GET() {
  try {
    const supabase = await createClient();
    const { data: authData, error: authError } = await supabase.auth.getClaims();

    if (authError || !authData?.claims) {
      return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
    }

    // Coverage from RPC
    const { data: coverageRows, error: coverageError } = await supabase.rpc(
      "get_admin_table_coverage",
    );

    if (coverageError) {
      throw new Error(`admin coverage rpc failed: ${coverageError.message}`);
    }

    const coverage = ((coverageRows ?? []) as Array<{
      table_name: string;
      latest_ts: string | null;
      row_count: number | null;
    }>).map((row) => {
      const latestTs = row.latest_ts ?? null;
      let staleness = "empty";

      if (latestTs) {
        const ageMs = Date.now() - new Date(latestTs).getTime();
        const ageMin = Math.floor(ageMs / 60_000);
        if (ageMin < 60) staleness = `${ageMin}m ago`;
        else if (ageMin < 1440) staleness = `${Math.floor(ageMin / 60)}h ago`;
        else staleness = `${Math.floor(ageMin / 1440)}d ago`;
      }

      return {
        table: row.table_name,
        latestTs,
        rowCount: Number(row.row_count ?? 0),
        staleness,
      } satisfies TableCoverage;
    });

    // Parallel queries
    const [jobLogsResult, candidatesResult, symbolsResult] = await Promise.all([
      supabase
        .from("job_log")
        .select("*")
        .order("created_at", { ascending: false })
        .limit(50),
      supabase
        .from("warbird_admin_candidate_rows_v")
        .select("*")
        .order("bar_close_ts", { ascending: false })
        .limit(100),
      supabase
        .from("symbols")
        .select("code, display_name, data_source, is_active")
        .order("code"),
    ]);

    const jobLogs = jobLogsResult.data ?? [];

    if (candidatesResult.error) {
      throw new Error(`candidates query failed: ${candidatesResult.error.message}`);
    }
    if (symbolsResult.error) {
      throw new Error(`symbols query failed: ${symbolsResult.error.message}`);
    }

    const symbols = (symbolsResult.data ?? []) as SymbolEntry[];

    // Map canonical view rows to the admin contract
    const candidates: CandidateRow[] = ((candidatesResult.data ?? []) as Array<Record<string, unknown>>).map((row) => ({
      candidate_id: Number(row.candidate_id),
      signal_id: row.signal_id != null ? String(row.signal_id) : null,
      bar_close_ts: String(row.bar_close_ts),
      symbol_code: String(row.symbol_code ?? "MES"),
      direction: String(row.direction ?? ""),
      anchor_price: row.anchor_price != null ? Number(row.anchor_price) : null,
      target_price: row.target_price != null ? Number(row.target_price) : null,
      entry_price: row.retrace_price != null ? Number(row.retrace_price) : null,
      stop_loss: row.stop_loss != null ? Number(row.stop_loss) : null,
      tp1_price: row.tp1_price != null ? Number(row.tp1_price) : null,
      tp2_price: row.tp2_price != null ? Number(row.tp2_price) : null,
      fib_level_touched: row.fib_level_touched != null ? String(row.fib_level_touched) : null,
      fib_ratio: row.fib_ratio != null ? Number(row.fib_ratio) : null,
      setup_archetype: row.setup_archetype != null ? String(row.setup_archetype) : null,
      confidence_score: row.confidence_score != null ? Number(row.confidence_score) : null,
      decision_code: row.decision_code != null ? String(row.decision_code) : null,
      tp1_probability: row.tp1_probability != null ? Number(row.tp1_probability) : null,
      tp2_probability: row.tp2_probability != null ? Number(row.tp2_probability) : null,
      reversal_risk: row.reversal_risk != null ? Number(row.reversal_risk) : null,
      target_hit_state: (String(row.target_hit_state ?? "OPEN")) as TargetHitState,
      outcome_state: (String(row.outcome_state ?? "OPEN")) as OutcomeState,
      status: String(row.status ?? "OPEN"),
      emitted_at: row.emitted_at != null ? String(row.emitted_at) : null,
      packet_id: row.packet_id != null ? String(row.packet_id) : null,
    }));

    return NextResponse.json({
      coverage,
      jobLogs,
      candidates,
      symbols,
      generatedAt: new Date().toISOString(),
    });
  } catch (e) {
    return NextResponse.json(
      { error: e instanceof Error ? e.message : "Internal error" },
      { status: 500 },
    );
  }
}
