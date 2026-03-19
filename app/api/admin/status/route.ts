import { NextResponse } from "next/server";
import { createAdminClient } from "@/lib/supabase/admin";
import type { WarbirdSetupEventType } from "@/lib/warbird/types";

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

type TargetResult = "HIT" | "MISS" | "OPEN";
type OutcomeResult = "WIN" | "LOSS" | "EXPIRED" | "OPEN";
type SetupEventAuditRow = {
  setup_id: number;
  event_type: WarbirdSetupEventType;
  ts: string;
};

interface SetupOutcomeEvidence {
  status: string;
  tp1_hit_at: string | null;
  tp2_hit_at: string | null;
  event_types: Set<WarbirdSetupEventType>;
}

function classifySetupResults(evidence: SetupOutcomeEvidence): {
  pt1_result: TargetResult;
  pt2_result: TargetResult;
  outcome_result: OutcomeResult;
} {
  const status = evidence.status;
  const eventTypes = evidence.event_types;

  const pt1Hit =
    Boolean(evidence.tp1_hit_at) ||
    Boolean(evidence.tp2_hit_at) ||
    eventTypes.has("TP1_HIT") ||
    eventTypes.has("TP2_HIT") ||
    status === "TP1_HIT" ||
    status === "TP2_HIT";
  const pt2Hit =
    Boolean(evidence.tp2_hit_at) || eventTypes.has("TP2_HIT") || status === "TP2_HIT";

  const stopped = eventTypes.has("STOPPED") || status === "STOPPED";
  const expired = eventTypes.has("EXPIRED") || status === "EXPIRED";
  const tp1Closed = status === "TP1_HIT" || eventTypes.has("TP1_HIT");

  const pt1_result: TargetResult = pt1Hit ? "HIT" : stopped || expired ? "MISS" : "OPEN";
  const pt2_result: TargetResult = pt2Hit
    ? "HIT"
    : stopped || expired || tp1Closed
      ? "MISS"
      : "OPEN";

  const outcome_result: OutcomeResult = pt2Hit || tp1Closed
    ? "WIN"
    : stopped
      ? "LOSS"
      : expired
        ? "EXPIRED"
        : "OPEN";

  return { pt1_result, pt2_result, outcome_result };
}

function classifyMeasuredMoveResults(status: string): {
  target_result: TargetResult;
  outcome_result: OutcomeResult;
} {
  if (status === "TP1_HIT" || status === "TP2_HIT") {
    return { target_result: "HIT", outcome_result: "WIN" };
  }
  if (status === "STOPPED") {
    return { target_result: "MISS", outcome_result: "LOSS" };
  }
  if (status === "EXPIRED") {
    return { target_result: "MISS", outcome_result: "EXPIRED" };
  }
  return { target_result: "OPEN", outcome_result: "OPEN" };
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
      "warbird_daily_bias",
      "warbird_structure_4h",
      "warbird_forecasts_1h",
      "warbird_triggers_15m",
      "warbird_conviction",
      "warbird_setups",
      "warbird_setup_events",
      "warbird_risk",
      "measured_moves",
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
      .eq("status", "ACTIVE")
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

    const setupIds = [
      ...new Set([...(activeSetups ?? []).map((s) => s.id), ...(recentSetups ?? []).map((s) => s.id)]),
    ];

    let setupEvents: SetupEventAuditRow[] = [];
    if (setupIds.length > 0) {
      const { data } = await supabase
        .from("warbird_setup_events")
        .select("setup_id, event_type, ts")
        .in("setup_id", setupIds)
        .order("ts", { ascending: false })
        .limit(5000);

      setupEvents = (data as SetupEventAuditRow[] | null) ?? [];
    }

    const eventsBySetup = new Map<number, Set<WarbirdSetupEventType>>();
    const latestEventBySetup = new Map<number, { event_type: WarbirdSetupEventType; ts: string }>();
    for (const event of setupEvents) {
      const bucket = eventsBySetup.get(event.setup_id) ?? new Set<WarbirdSetupEventType>();
      bucket.add(event.event_type);
      eventsBySetup.set(event.setup_id, bucket);
      if (!latestEventBySetup.has(event.setup_id)) {
        latestEventBySetup.set(event.setup_id, { event_type: event.event_type, ts: event.ts });
      }
    }

    const enrichSetups = (
      rows:
        | Array<{ id: number; status: string; tp1_hit_at: string | null; tp2_hit_at: string | null }>
        | null
        | undefined,
    ) =>
      (rows ?? []).map((setup) => {
        const setupId = Number(setup.id);
        const latestEvent = latestEventBySetup.get(setupId) ?? null;
        return {
          ...setup,
          last_event_type: latestEvent?.event_type ?? null,
          last_event_ts: latestEvent?.ts ?? null,
          ...classifySetupResults({
            status: setup.status,
            tp1_hit_at: setup.tp1_hit_at,
            tp2_hit_at: setup.tp2_hit_at,
            event_types: eventsBySetup.get(setupId) ?? new Set<WarbirdSetupEventType>(),
          }),
        };
      });

    // --- Symbols ---
    const { data: symbols } = await supabase
      .from("symbols")
      .select("code, display_name, data_source, is_active")
      .order("code");

    // --- Latest Forecasts ---
    const { data: forecasts } = await supabase
      .from("warbird_forecasts_1h")
      .select("*")
      .order("ts", { ascending: false })
      .limit(20);

    // --- Measured Moves ---
    const { data: measuredMovesRaw } = await supabase
      .from("measured_moves")
      .select("*")
      .order("ts", { ascending: false })
      .limit(20);

    const measuredMoveSetupIds = [
      ...new Set(
        (measuredMovesRaw ?? [])
          .map((move) => Number(move.setup_id))
          .filter((id) => Number.isFinite(id) && id > 0),
      ),
    ];

    const measuredMoveSetups = new Map<
      number,
      { status: string; tp1_hit_at: string | null; tp2_hit_at: string | null }
    >();
    const measuredMoveEvents = new Map<number, Set<WarbirdSetupEventType>>();

    if (measuredMoveSetupIds.length > 0) {
      const { data: setupRows } = await supabase
        .from("warbird_setups")
        .select("id, status, tp1_hit_at, tp2_hit_at")
        .in("id", measuredMoveSetupIds);

      for (const row of setupRows ?? []) {
        measuredMoveSetups.set(Number(row.id), {
          status: String(row.status),
          tp1_hit_at: row.tp1_hit_at ?? null,
          tp2_hit_at: row.tp2_hit_at ?? null,
        });
      }

      const { data: eventRows } = await supabase
        .from("warbird_setup_events")
        .select("setup_id, event_type")
        .in("setup_id", measuredMoveSetupIds)
        .limit(5000);

      for (const row of eventRows ?? []) {
        const setupId = Number(row.setup_id);
        const bucket = measuredMoveEvents.get(setupId) ?? new Set<WarbirdSetupEventType>();
        bucket.add(row.event_type as WarbirdSetupEventType);
        measuredMoveEvents.set(setupId, bucket);
      }
    }

    const measuredMoves = (measuredMovesRaw ?? []).map((move) => {
      const setupId = Number(move.setup_id);
      const linkedSetup = measuredMoveSetups.get(setupId);

      if (linkedSetup) {
        const setupResults = classifySetupResults({
          status: linkedSetup.status,
          tp1_hit_at: linkedSetup.tp1_hit_at,
          tp2_hit_at: linkedSetup.tp2_hit_at,
          event_types: measuredMoveEvents.get(setupId) ?? new Set<WarbirdSetupEventType>(),
        });
        return {
          ...move,
          target_result: setupResults.pt1_result,
          outcome_result: setupResults.outcome_result,
        };
      }

      return {
        ...move,
        ...classifyMeasuredMoveResults(String(move.status ?? "")),
      };
    });

    return NextResponse.json({
      coverage,
      jobLogs: jobLogs ?? [],
      activeSetups: enrichSetups(
        activeSetups as Array<{ id: number; status: string; tp1_hit_at: string | null; tp2_hit_at: string | null }> | null | undefined,
      ),
      recentSetups: enrichSetups(
        recentSetups as Array<{ id: number; status: string; tp1_hit_at: string | null; tp2_hit_at: string | null }> | null | undefined,
      ),
      recentEvents: setupEvents,
      symbols: symbols ?? [],
      forecasts: forecasts ?? [],
      measuredMoves,
      generatedAt: new Date().toISOString(),
    });
  } catch (e) {
    return NextResponse.json(
      { error: e instanceof Error ? e.message : "Internal error" },
      { status: 500 },
    );
  }
}
