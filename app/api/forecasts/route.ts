import { NextResponse } from "next/server";
import { createAdminClient } from "@/lib/supabase/admin";

// Serves latest forecasts to the chart's ForecastTargetsPrimitive.
// Returns predictions grouped by horizon with MC bands.

export async function GET() {
  const supabase = createAdminClient();

  try {
    // Get forecasts from last 6 hours
    const cutoff = new Date(Date.now() - 6 * 60 * 60 * 1000).toISOString();
    const { data: forecasts, error } = await supabase
      .from("forecasts")
      .select("*")
      .gte("ts", cutoff)
      .order("ts", { ascending: false });

    if (error) throw error;

    // Get latest price
    const { data: latestBar } = await supabase
      .from("mes_15m")
      .select("ts, close")
      .order("ts", { ascending: false })
      .limit(1)
      .single();

    const currentPrice = latestBar ? Number(latestBar.close) : null;
    const lastBarTime = latestBar?.ts ?? null;

    // Group by horizon, take most recent per horizon
    const byHorizon: Record<string, typeof forecasts[0]> = {};
    if (forecasts) {
      for (const f of forecasts) {
        if (!byHorizon[f.horizon]) {
          byHorizon[f.horizon] = f;
        }
      }
    }

    // Transform to ForecastTarget format for the chart
    const horizonHours: Record<string, number> = {
      "1h": 1, "4h": 4, "1d": 24, "1w": 120,
    };

    const targets = Object.entries(byHorizon).map(([horizon, forecast]) => {
      const hours = horizonHours[horizon] ?? 1;
      const startTime = lastBarTime
        ? Math.floor(new Date(lastBarTime).getTime() / 1000)
        : Math.floor(Date.now() / 1000);
      const endTime = startTime + hours * 3600;

      const price = Number(forecast.predicted_price);
      const mae = Number(forecast.predicted_mae) || 0;

      return {
        id: `forecast-${horizon}`,
        kind: "TP" as const,
        label: `${horizon.toUpperCase()} ${price.toFixed(2)}` +
          (forecast.mc_prob_up != null ? ` | P(up) ${(Number(forecast.mc_prob_up) * 100).toFixed(0)}%` : "") +
          (mae > 0 ? ` | MAE ±${mae.toFixed(2)}` : ""),
        startTime,
        endTime,
        price,
        bandHalfWidth: mae,
        tags: ["OOF", `H-${horizon.toUpperCase()}`],
        color: price > (currentPrice ?? 0) ? "#26a69a" : "#ef5350",
        mcProbTouch: forecast.mc_prob_up != null ? Number(forecast.mc_prob_up) : undefined,
        mcRuns: 10000,
      };
    });

    return NextResponse.json({
      targets,
      current_price: currentPrice,
      forecasts: byHorizon,
    });
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    return NextResponse.json({ error: message }, { status: 500 });
  }
}
