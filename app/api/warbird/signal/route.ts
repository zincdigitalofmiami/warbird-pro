import { NextResponse } from "next/server";
import { createAdminClient } from "@/lib/supabase/admin";
import { composeWarbirdSignal } from "@/lib/warbird/projection";
import { fetchLatestWarbirdState } from "@/lib/warbird/queries";

export async function GET(request: Request) {
  try {
    const url = new URL(request.url);
    const symbolCode = url.searchParams.get("symbol") ?? "MES";
    const supabase = createAdminClient();

    const state = await fetchLatestWarbirdState(supabase, symbolCode);
    const signal = composeWarbirdSignal(state);

    return NextResponse.json({
      signal,
      forecast: state.forecast,
      setup: state.setup,
      trigger: state.trigger,
      conviction: state.conviction,
      risk: state.risk,
    });
  } catch (error) {
    return NextResponse.json(
      { error: error instanceof Error ? error.message : "Internal error" },
      { status: 500 },
    );
  }
}
