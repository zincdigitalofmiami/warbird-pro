import { NextResponse } from "next/server";
import { createClient } from "@/lib/supabase/server";
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
    const supabase = await createClient();
    const { data: authData, error: authError } = await supabase.auth.getClaims();

    if (authError || !authData?.claims) {
      return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
    }

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

    const weekAgo = new Date(Date.now() - 7 * 86400_000).toISOString();
    const [jobLogsResult, activeSetupsResult, recentSetupsResult, symbolsResult, triggersResult, measuredMovesResult] = await Promise.all([
      supabase
        .from("job_log")
        .select("*")
        .order("created_at", { ascending: false })
        .limit(50),
      supabase
        .from("warbird_setups")
        .select("*")
        .eq("status", "ACTIVE")
        .order("bar_close_ts", { ascending: false })
        .limit(30),
      supabase
        .from("warbird_setups")
        .select("*")
        .gte("bar_close_ts", weekAgo)
        .order("bar_close_ts", { ascending: false })
        .limit(100),
      supabase
        .from("symbols")
        .select("code, display_name, data_source, is_active")
        .order("code"),
      supabase
        .from("warbird_triggers_15m")
        .select("*")
        .order("bar_close_ts", { ascending: false })
        .limit(20),
      supabase
        .from("measured_moves")
        .select("*")
        .order("ts", { ascending: false })
        .limit(20),
    ]);

    const jobLogs = jobLogsResult.data ?? [];
    const activeSetups = activeSetupsResult.data ?? [];
    const recentSetups = recentSetupsResult.data ?? [];
    const symbols = symbolsResult.data ?? [];
    const triggers = (triggersResult.data ?? []).map((trigger) => ({
      ...trigger,
      ts: trigger.bar_close_ts,
    }));
    const measuredMovesRaw = measuredMovesResult.data ?? [];

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
          ts: "bar_close_ts" in setup ? String(setup.bar_close_ts) : null,
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
      triggers,
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
