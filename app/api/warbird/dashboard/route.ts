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

    // Parallel fetch: state + history + signal events + cross-asset correlations
    // HG, NQ, 6E, CL — all Databento hourly from cross_asset_1h
    const correlationSymbols = ["HG", "NQ", "6E", "CL"];

    const [state, history, signalEventsResult, ...crossAssetResults] = await Promise.all([
      fetchLatestWarbirdState(supabase, symbolCode),
      fetchWarbirdSetupHistory(supabase, { symbolCode, days, limit }),
      supabase
        .from("warbird_signal_events")
        .select("signal_event_id, signal_id, ts, event_type, price, note")
        .order("ts", { ascending: false })
        .limit(50),
      ...correlationSymbols.map((sym) =>
        supabase
          .from("cross_asset_1h")
          .select("ts, close")
          .eq("symbol_code", sym)
          .order("ts", { ascending: false })
          .limit(2),
      ),
    ]);

    // Build signal events array (may not exist yet — table is in migration 037)
    const signalEvents = signalEventsResult.error ? [] : (signalEventsResult.data ?? []);

    // Build correlations map: { symbolCode: { close, prevClose } }
    const correlations: Record<string, { close: number; prevClose: number }> = {};
    correlationSymbols.forEach((sym, i) => {
      const result = crossAssetResults[i];
      if (result.error || !result.data || result.data.length < 2) return;
      correlations[sym] = {
        close: Number(result.data[0].close),
        prevClose: Number(result.data[1].close),
      };
    });

    const activeWindow = history.setups.filter((setup) =>
      setup.status === "ACTIVE" || setup.status === "TP1_HIT",
    );

    return NextResponse.json({
      signal: composeWarbirdSignal(state),
      setup: state.setup,
      setups: history.setups,
      events: history.events,
      signalEvents,
      correlations,
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
