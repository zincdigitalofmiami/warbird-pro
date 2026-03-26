import { NextResponse } from "next/server";
import { createClient } from "@/lib/supabase/server";
import { composeWarbirdSignal } from "@/lib/warbird/projection";
import { fetchLatestWarbirdState } from "@/lib/warbird/queries";

export async function GET(request: Request) {
  try {
    const url = new URL(request.url);
    const symbolCode = url.searchParams.get("symbol") ?? "MES";
    const supabase = await createClient();
    const { data: authData, error: authError } = await supabase.auth.getClaims();

    if (authError || !authData?.claims) {
      return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
    }

    const state = await fetchLatestWarbirdState(supabase, symbolCode);
    const signal = composeWarbirdSignal(state);

    return NextResponse.json({
      signal,
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
