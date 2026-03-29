import { NextResponse } from "next/server";
import { createClient } from "@/lib/supabase/server";
import { composeWarbirdSignal } from "@/lib/warbird/projection";
import {
  fetchLatestWarbirdState,
  fetchWarbirdSetupHistory,
} from "@/lib/warbird/queries";

export async function GET(request: Request) {
  try {
    const supabase = await createClient();
    const { data: authData, error: authError } = await supabase.auth.getClaims();

    if (authError || !authData?.claims) {
      return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
    }

    const url = new URL(request.url);
    const symbolCode = url.searchParams.get("symbol") ?? "MES";
    const days = Math.max(1, Math.min(30, Number(url.searchParams.get("days") ?? 7)));
    const limit = Math.max(1, Math.min(200, Number(url.searchParams.get("limit") ?? 100)));

    const [state, history] = await Promise.all([
      fetchLatestWarbirdState(supabase, symbolCode),
      fetchWarbirdSetupHistory(supabase, { symbolCode, days, limit }),
    ]);

    const activeWindow = history.setups.filter((setup) =>
      setup.status === "ACTIVE" || setup.status === "TP1_HIT",
    );

    return NextResponse.json({
      signal: composeWarbirdSignal(state),
      setup: state.setup,
      setups: history.setups,
      events: history.events,
      counts: {
        active: activeWindow.filter((setup) => setup.status === "ACTIVE").length,
        counterTrend: activeWindow.filter((setup) => setup.counter_trend).length,
        tp1Hit: history.events.filter((event) => event.event_type === "TP1_HIT").length,
        tp2Hit: history.events.filter((event) => event.event_type === "TP2_HIT").length,
        stopped: history.events.filter((event) => event.event_type === "STOPPED").length,
        open: history.setups.filter(
          (setup) => setup.status === "ACTIVE" || setup.status === "EXPIRED",
        ).length,
      },
      generatedAt: new Date().toISOString(),
    });
  } catch (error) {
    return NextResponse.json(
      { error: error instanceof Error ? error.message : "Internal error" },
      { status: 500 },
    );
  }
}
