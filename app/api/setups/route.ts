import { NextResponse } from "next/server";
import { createAdminClient } from "@/lib/supabase/admin";

// Returns active and recent setups for chart rendering.
// SetupMarkersPrimitive consumes this.

export async function GET() {
  try {
    const supabase = createAdminClient();

    // Active setups: TOUCHED, HOOKED, GO_FIRED, TP1_HIT
    const { data: activeSetups, error: activeError } = await supabase
      .from("warbird_setups")
      .select("*")
      .in("phase", ["TOUCHED", "HOOKED", "GO_FIRED", "TP1_HIT"])
      .order("ts", { ascending: false })
      .limit(20);

    if (activeError) throw new Error(activeError.message);

    // Recent completed setups (last 7 days) for context
    const weekAgo = new Date();
    weekAgo.setDate(weekAgo.getDate() - 7);

    const { data: recentSetups, error: recentError } = await supabase
      .from("warbird_setups")
      .select("*")
      .in("phase", ["STOPPED", "TP1_HIT", "TP2_HIT", "EXPIRED"])
      .gte("ts", weekAgo.toISOString())
      .order("ts", { ascending: false })
      .limit(50);

    if (recentError) throw new Error(recentError.message);

    // Active measured moves
    const { data: measuredMoves, error: mmError } = await supabase
      .from("measured_moves")
      .select("*")
      .in("status", ["ACTIVE", "FORMING"])
      .order("ts", { ascending: false })
      .limit(10);

    if (mmError) throw new Error(mmError.message);

    return NextResponse.json({
      active: activeSetups ?? [],
      recent: recentSetups ?? [],
      measuredMoves: measuredMoves ?? [],
    });
  } catch (e) {
    return NextResponse.json(
      { error: e instanceof Error ? e.message : "Internal error" },
      { status: 500 }
    );
  }
}
