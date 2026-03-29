import { NextResponse } from "next/server";
import { isWeekendBar } from "@/lib/market-hours";
import { createClient } from "@/lib/supabase/server";

/**
 * MES 15m Chart Data API
 *
 * Serves the initial snapshot for LiveMesChart.
 * After initial load, the chart receives updates via Supabase Realtime.
 *
 * Query params:
 *   ?snapshot=1&backfill=5000 — full snapshot
 */

export async function GET(request: Request) {
  try {
    const supabase = await createClient();
    const { data: authData, error: authError } = await supabase.auth.getClaims();

    if (authError || !authData?.claims) {
      return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
    }

    const url = new URL(request.url);
    const backfill = parseInt(url.searchParams.get("backfill") || "5000", 10);

    const { data, error } = await supabase
      .from("mes_15m")
      .select("ts, open, high, low, close, volume")
      .order("ts", { ascending: false })
      .limit(backfill);

    if (error) {
      return NextResponse.json({ error: error.message }, { status: 500 });
    }

    if (!data || data.length === 0) {
      return NextResponse.json({
        points: [],
        live: false,
        meta: { source: "supabase", rows: 0 },
      });
    }

    // Reverse to chronological order (oldest first)
    const rows = data.reverse();

    const points = rows
      .map((row) => {
        const ts = Math.floor(new Date(row.ts).getTime() / 1000);
        return {
          time: ts,
          open: Number(row.open),
          high: Number(row.high),
          low: Number(row.low),
          close: Number(row.close),
          volume: Number(row.volume),
        };
      })
      .filter((p) => !isWeekendBar(p.time));

    // Determine if data is live (latest bar within last 30 minutes)
    const latestTime = points[points.length - 1]?.time ?? 0;
    const nowSec = Math.floor(Date.now() / 1000);
    const isLive = nowSec - latestTime < 1800;

    return NextResponse.json({
      points,
      live: isLive,
      meta: {
        source: "supabase",
        rows: points.length,
        latestTs: latestTime,
      },
    });
  } catch (e) {
    return NextResponse.json(
      { error: e instanceof Error ? e.message : "Internal error" },
      { status: 500 },
    );
  }
}
