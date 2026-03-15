import { NextResponse } from "next/server";
import { createAdminClient } from "@/lib/supabase/admin";
import { isMarketOpen } from "@/lib/market-hours";

export const maxDuration = 60;

// Runs every 15 min on weekdays: :10, :25, :40, :55
// Checks active GO_FIRED setups against current price to determine
// if TP1, TP2, or SL has been hit.

export async function GET(request: Request) {
  const cronSecret = process.env.CRON_SECRET;
  if (cronSecret) {
    const auth = request.headers.get("authorization");
    if (auth !== `Bearer ${cronSecret}`) {
      return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
    }
  }

  const startTime = Date.now();
  const supabase = createAdminClient();

  const url = new URL(request.url);
  const force = url.searchParams.get("force") === "1";
  if (!force && !isMarketOpen()) {
    return NextResponse.json({ skipped: true, reason: "market_closed" });
  }

  try {
    // Fetch all active setups (GO_FIRED phase)
    const { data: activeSetups, error: setupError } = await supabase
      .from("warbird_setups")
      .select("*")
      .in("phase", ["GO_FIRED", "TP1_HIT"]);

    if (setupError) throw new Error(`warbird_setups query failed: ${setupError.message}`);
    if (!activeSetups || activeSetups.length === 0) {
      return NextResponse.json({ skipped: true, reason: "no_active_setups" });
    }

    // Get latest price from mes_1m
    const { data: latestBar, error: priceError } = await supabase
      .from("mes_1m")
      .select("ts, high, low, close")
      .order("ts", { ascending: false })
      .limit(1)
      .single();

    if (priceError || !latestBar) {
      return NextResponse.json({ skipped: true, reason: "no_price_data" });
    }

    const currentHigh = Number(latestBar.high);
    const currentLow = Number(latestBar.low);
    let updated = 0;

    for (const setup of activeSetups) {
      const direction = setup.direction as string;
      const entry = Number(setup.entry_price);
      const sl = Number(setup.stop_loss);
      const tp1 = Number(setup.tp1);
      const tp2 = Number(setup.tp2);
      let newPhase: string | null = null;

      if (setup.phase === "GO_FIRED") {
        // Check SL first (worst case)
        if (direction === "LONG" && currentLow <= sl) {
          newPhase = "STOPPED";
        } else if (direction === "SHORT" && currentHigh >= sl) {
          newPhase = "STOPPED";
        }
        // Check TP1
        else if (direction === "LONG" && currentHigh >= tp1) {
          newPhase = "TP1_HIT";
        } else if (direction === "SHORT" && currentLow <= tp1) {
          newPhase = "TP1_HIT";
        }

        // Check expiry (48 hours from creation)
        if (!newPhase) {
          const createdAt = new Date(setup.created_at).getTime();
          if (Date.now() - createdAt > 48 * 60 * 60 * 1000) {
            newPhase = "EXPIRED";
          }
        }
      } else if (setup.phase === "TP1_HIT") {
        // After TP1, check if runner reaches TP2 or retraces to entry (stop moves to breakeven)
        if (direction === "LONG" && currentHigh >= tp2) {
          newPhase = "TP2_HIT";
        } else if (direction === "SHORT" && currentLow <= tp2) {
          newPhase = "TP2_HIT";
        }
        // Breakeven stop after TP1 hit
        else if (direction === "LONG" && currentLow <= entry) {
          newPhase = "TP1_HIT"; // stays TP1_HIT, trade closed at breakeven
        } else if (direction === "SHORT" && currentHigh >= entry) {
          newPhase = "TP1_HIT"; // same
        }
      }

      if (newPhase && newPhase !== setup.phase) {
        const { error: updateError } = await supabase
          .from("warbird_setups")
          .update({ phase: newPhase, updated_at: new Date().toISOString() })
          .eq("id", setup.id);

        if (!updateError) updated++;
      }
    }

    await supabase.from("job_log").insert({
      job_name: "score-trades",
      status: "OK",
      rows_written: updated,
      duration_ms: Date.now() - startTime,
    });

    return NextResponse.json({
      success: true,
      active_setups: activeSetups.length,
      updated,
      latest_price: Number(latestBar.close),
      duration_ms: Date.now() - startTime,
    });
  } catch (e) {
    const message = e instanceof Error ? e.message : "Internal error";
    try {
      await supabase.from("job_log").insert({
        job_name: "score-trades",
        status: "ERROR",
        error_message: message,
        duration_ms: Date.now() - startTime,
      });
    } catch {
      // ignore
    }
    return NextResponse.json({ error: message }, { status: 500 });
  }
}
