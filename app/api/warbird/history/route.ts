import { NextResponse } from "next/server";
import { createAdminClient } from "@/lib/supabase/admin";
import { fetchWarbirdHistory } from "@/lib/warbird/queries";

export async function GET(request: Request) {
  try {
    const url = new URL(request.url);
    const days = Math.max(1, Math.min(30, Number(url.searchParams.get("days") ?? 7)));
    const limit = Math.max(1, Math.min(200, Number(url.searchParams.get("limit") ?? 50)));
    const symbolCode = url.searchParams.get("symbol") ?? "MES";

    const supabase = createAdminClient();
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
