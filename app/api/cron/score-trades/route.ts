import { NextResponse } from "next/server";
import { createAdminClient } from "@/lib/supabase/admin";
import { isMarketOpen } from "@/lib/market-hours";
import type { WarbirdSetupEventType, WarbirdSetupRow } from "@/lib/warbird/types";

export const maxDuration = 60;

type JobLogPayload = {
  job_name: string;
  status: "SUCCESS" | "PARTIAL" | "FAILED" | "SKIPPED";
  rows_affected?: number;
  duration_ms: number;
  error_message?: string;
};

async function writeJobLog(
  supabase: ReturnType<typeof createAdminClient>,
  payload: JobLogPayload,
) {
  const { error } = await supabase.from("job_log").insert(payload);
  if (error) {
    throw new Error(`job_log insert failed: ${error.message}`);
  }
}

async function recordEvent(
  supabase: ReturnType<typeof createAdminClient>,
  setupId: number,
  eventType: WarbirdSetupEventType,
  ts: string,
  price: number,
  note: string,
) {
  const { data: existing } = await supabase
    .from("warbird_setup_events")
    .select("id")
    .eq("setup_id", setupId)
    .eq("event_type", eventType)
    .limit(1)
    .maybeSingle();

  if (existing) return;

  await supabase.from("warbird_setup_events").insert({
    setup_id: setupId,
    ts,
    event_type: eventType,
    price,
    note,
  });
}

async function syncMeasuredMoveStatus(
  supabase: ReturnType<typeof createAdminClient>,
  setupId: number,
  status: "TP1_HIT" | "TP2_HIT" | "STOPPED" | "EXPIRED",
) {
  const { error } = await supabase
    .from("measured_moves")
    .update({ status })
    .eq("setup_id", setupId);
  if (error) {
    throw new Error(`measured_moves update failed: ${error.message}`);
  }
}

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
  const force = new URL(request.url).searchParams.get("force") === "1";

  if (!force && !isMarketOpen()) {
    try {
      await writeJobLog(supabase, {
        job_name: "score-trades",
        status: "SKIPPED",
        rows_affected: 0,
        duration_ms: Date.now() - startTime,
        error_message: "market_closed",
      });
    } catch {
      // Ignore logging failure to preserve skip response.
    }
    return NextResponse.json({ skipped: true, reason: "market_closed" });
  }

  try {
    const { data: monitoredSetups, error: setupError } = await supabase
      .from("warbird_setups")
      .select("*")
      .in("status", ["ACTIVE", "TP1_HIT"])
      .returns<WarbirdSetupRow[]>();

    if (setupError) throw new Error(`warbird_setups query failed: ${setupError.message}`);
    if (!monitoredSetups || monitoredSetups.length === 0) {
      await writeJobLog(supabase, {
        job_name: "score-trades",
        status: "SKIPPED",
        rows_affected: 0,
        duration_ms: Date.now() - startTime,
        error_message: "no_monitored_setups",
      });
      return NextResponse.json({ skipped: true, reason: "no_active_setups" });
    }

    const { data: latestBar, error: priceError } = await supabase
      .from("mes_1m")
      .select("ts, high, low, close")
      .order("ts", { ascending: false })
      .limit(1)
      .single();

    if (priceError || !latestBar) {
      await writeJobLog(supabase, {
        job_name: "score-trades",
        status: "SKIPPED",
        rows_affected: 0,
        duration_ms: Date.now() - startTime,
        error_message: "no_price_data",
      });
      return NextResponse.json({ skipped: true, reason: "no_price_data" });
    }

    const currentHigh = Number(latestBar.high);
    const currentLow = Number(latestBar.low);
    const nowIso = new Date().toISOString();

    let updated = 0;
    for (const setup of monitoredSetups) {
      const direction = setup.direction;
      const entry = Number(setup.entry_price);
      const stopLoss = Number(setup.stop_loss);
      const tp1 = Number(setup.tp1);
      const tp2 = Number(setup.tp2);
      const alreadyHitTp1 = setup.status === "TP1_HIT" || setup.tp1_hit_at != null;

      const stopped =
        (direction === "LONG" && currentLow <= stopLoss) ||
        (direction === "SHORT" && currentHigh >= stopLoss);
      const hitTp2 =
        (direction === "LONG" && currentHigh >= tp2) ||
        (direction === "SHORT" && currentLow <= tp2);
      const hitTp1 =
        (direction === "LONG" && currentHigh >= tp1) ||
        (direction === "SHORT" && currentLow <= tp1);
      const expired =
        setup.expires_at != null && new Date(setup.expires_at).getTime() <= Date.now();

      // Conservative conflict rule: if stop and target touch in the same bar, stop wins.
      if (stopped) {
        await supabase
          .from("warbird_setups")
          .update({
            status: "STOPPED",
            current_event: "STOPPED",
            stopped_at: nowIso,
          })
          .eq("id", setup.id);
        await syncMeasuredMoveStatus(supabase, setup.id, "STOPPED");
        await recordEvent(supabase, setup.id, "STOPPED", nowIso, stopLoss, "Stop loss hit");
        updated += 1;
        continue;
      }

      if (hitTp2) {
        await supabase
          .from("warbird_setups")
          .update({
            status: "TP2_HIT",
            current_event: "TP2_HIT",
            tp1_hit_at: setup.tp1_hit_at,
            tp2_hit_at: nowIso,
          })
          .eq("id", setup.id);
        await syncMeasuredMoveStatus(supabase, setup.id, "TP2_HIT");
        if (alreadyHitTp1 && setup.tp1_hit_at != null) {
          await recordEvent(supabase, setup.id, "TP1_HIT", setup.tp1_hit_at, tp1, "TP1 reached");
        }
        await recordEvent(supabase, setup.id, "TP2_HIT", nowIso, tp2, "TP2 reached");
        updated += 1;
        continue;
      }

      if (!alreadyHitTp1 && hitTp1) {
        await supabase
          .from("warbird_setups")
          .update({
            status: "TP1_HIT",
            current_event: "TP1_HIT",
            tp1_hit_at: nowIso,
          })
          .eq("id", setup.id);
        await syncMeasuredMoveStatus(supabase, setup.id, "TP1_HIT");
        await recordEvent(supabase, setup.id, "TP1_HIT", nowIso, tp1, "TP1 reached");
        updated += 1;
        continue;
      }

      if (expired) {
        await supabase
          .from("warbird_setups")
          .update({
            status: "EXPIRED",
            current_event: "EXPIRED",
          })
          .eq("id", setup.id);
        await syncMeasuredMoveStatus(supabase, setup.id, "EXPIRED");
        await recordEvent(supabase, setup.id, "EXPIRED", nowIso, entry, "Setup expired");
        updated += 1;
      }
    }

    await writeJobLog(supabase, {
      job_name: "score-trades",
      status: "SUCCESS",
      rows_affected: updated,
      duration_ms: Date.now() - startTime,
    });

    return NextResponse.json({
      success: true,
      monitored_setups: monitoredSetups.length,
      updated,
      latest_price: Number(latestBar.close),
      duration_ms: Date.now() - startTime,
    });
  } catch (error) {
    const message = error instanceof Error ? error.message : "Internal error";
    try {
      await writeJobLog(supabase, {
        job_name: "score-trades",
        status: "FAILED",
        error_message: message,
        duration_ms: Date.now() - startTime,
      });
    } catch {
      // ignore
    }
    return NextResponse.json({ error: message }, { status: 500 });
  }
}
