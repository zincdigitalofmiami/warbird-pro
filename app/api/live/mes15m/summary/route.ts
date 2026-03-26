import { NextResponse } from "next/server";
import { getMesSessionDayStart } from "@/lib/mes-aggregation";
import { createClient } from "@/lib/supabase/server";

export async function GET() {
  try {
    const supabase = await createClient();
    const { data: authData, error: authError } = await supabase.auth.getClaims();

    if (authError || !authData?.claims) {
      return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
    }

    const nowSec = Math.floor(Date.now() / 1000);
    const sessionStartIso = new Date(getMesSessionDayStart(nowSec) * 1000).toISOString();

    const { data, error } = await supabase
      .from("mes_15m")
      .select("ts, open, high, low, close")
      .gte("ts", sessionStartIso)
      .order("ts", { ascending: true })
      .limit(128);

    if (error) {
      return NextResponse.json({ error: error.message }, { status: 500 });
    }

    if (!data || data.length === 0) {
      return NextResponse.json({ summary: null });
    }

    const first = data[0];
    const latest = data[data.length - 1];
    const sessionHigh = Math.max(...data.map((row) => Number(row.high)));
    const sessionLow = Math.min(...data.map((row) => Number(row.low)));
    const open = Number(first.open);
    const close = Number(latest.close);
    const change = close - open;

    return NextResponse.json({
      summary: {
        price: close,
        change,
        changePercent: open === 0 ? 0 : (change / open) * 100,
        high: sessionHigh,
        low: sessionLow,
        ts: String(latest.ts),
      },
    });
  } catch (error) {
    return NextResponse.json(
      { error: error instanceof Error ? error.message : "Internal error" },
      { status: 500 },
    );
  }
}
