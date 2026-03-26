import { NextResponse } from "next/server";
import { createClient } from "@/lib/supabase/server";
import { fetchWarbirdHistory } from "@/lib/warbird/queries";

export async function GET(request: Request) {
  try {
    const url = new URL(request.url);
    const days = Math.max(1, Math.min(30, Number(url.searchParams.get("days") ?? 7)));
    const limit = Math.max(1, Math.min(200, Number(url.searchParams.get("limit") ?? 50)));
    const symbolCode = url.searchParams.get("symbol") ?? "MES";

    const supabase = await createClient();
    const { data: authData, error: authError } = await supabase.auth.getClaims();

    if (authError || !authData?.claims) {
      return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
    }

    const history = await fetchWarbirdHistory(supabase, {
      symbolCode,
      days,
      limit,
    });

    return NextResponse.json({
      ...history,
      generatedAt: new Date().toISOString(),
    });
  } catch (error) {
    return NextResponse.json(
      { error: error instanceof Error ? error.message : "Internal error" },
      { status: 500 },
    );
  }
}
