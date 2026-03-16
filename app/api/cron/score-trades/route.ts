import { NextResponse } from "next/server";
import { createAdminClient } from "@/lib/supabase/admin";
import { isMarketOpen } from "@/lib/market-hours";
import { WARBIRD_RUNNER_VOLUME_RATIO } from "@/lib/warbird/constants";
import type { WarbirdSetupEventType, WarbirdSetupRow } from "@/lib/warbird/types";

export const maxDuration = 60;

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
    return NextResponse.json({ skipped: true, reason: "market_closed" });
  }

  try {
    const { data: activeSetups, error: setupError } = await supabase
      .from("warbird_setups")
      .select("*")
      .in("status", ["ACTIVE", "RUNNER_ACTIVE"])
      .returns<WarbirdSetupRow[]>();

    if (setupError) throw new Error(`warbird_setups query failed: ${setupError.message}`);
    if (!activeSetups || activeSetups.length === 0) {
      return NextResponse.json({ skipped: true, reason: "no_active_setups" });
    }

    const [{ data: latestBar, error: priceError }, { data: recent15m, error: volError }] =
      await Promise.all([
        supabase
          .from("mes_1m")
          .select("ts, high, low, close")
          .order("ts", { ascending: false })
          .limit(1)
          .single(),
        supabase
          .from("mes_15m")
          .select("ts, volume")
          .order("ts", { ascending: false })
          .limit(21),
      ]);

    if (priceError || !latestBar) {
      return NextResponse.json({ skipped: true, reason: "no_price_data" });
    }
    if (volError) {
      throw new Error(`mes_15m volume query failed: ${volError.message}`);
    }

    const currentHigh = Number(latestBar.high);
    const currentLow = Number(latestBar.low);
    const nowIso = new Date().toISOString();

    const volumes = (recent15m ?? []).map((row) => Number(row.volume));
    const latestVolume = volumes[0] ?? 0;
    const averageVolume =
      volumes.length > 1
        ? volumes.slice(1).reduce((sum, value) => sum + value, 0) / (volumes.length - 1)
        : 0;
    const volumeRatio = averageVolume > 0 ? latestVolume / averageVolume : 0;

    let updated = 0;
    for (const setup of activeSetups) {
      const direction = setup.direction;
      const entry = Number(setup.entry_price);
      const stopLoss = Number(setup.stop_loss);
      const tp1 = Number(setup.tp1);
      const tp2 = Number(setup.tp2);

      if (setup.status === "ACTIVE") {
        const stopped =
          (direction === "LONG" && currentLow <= stopLoss) ||
          (direction === "SHORT" && currentHigh >= stopLoss);
        const hitTp1 =
          (direction === "LONG" && currentHigh >= tp1) ||
          (direction === "SHORT" && currentLow <= tp1);
        const expired =
          setup.expires_at != null && new Date(setup.expires_at).getTime() <= Date.now();

        if (stopped) {
          await supabase
            .from("warbird_setups")
            .update({
              status: "STOPPED",
              current_event: "STOPPED",
              stopped_at: nowIso,
            })
            .eq("id", setup.id);
          await recordEvent(supabase, setup.id, "STOPPED", nowIso, stopLoss, "Stop loss hit");
          updated += 1;
          continue;
        }

        if (hitTp1) {
          const runnerActive =
            Boolean(setup.runner_eligible) &&
            Number(setup.runner_headroom ?? 0) > 0 &&
            volumeRatio >= WARBIRD_RUNNER_VOLUME_RATIO;

          await supabase
            .from("warbird_setups")
            .update({
              status: runnerActive ? "RUNNER_ACTIVE" : "TP1_HIT",
              current_event: runnerActive ? "RUNNER_STARTED" : "TP1_HIT",
              tp1_hit_at: nowIso,
              runner_started_at: runnerActive ? nowIso : setup.runner_started_at,
              volume_ratio: volumeRatio,
            })
            .eq("id", setup.id);

          await recordEvent(supabase, setup.id, "TP1_HIT", nowIso, tp1, "TP1 reached");
          if (runnerActive) {
            await recordEvent(
              supabase,
              setup.id,
              "RUNNER_STARTED",
              nowIso,
              tp1,
              "Runner started on continued volume expansion",
            );
          }
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
          await recordEvent(supabase, setup.id, "EXPIRED", nowIso, entry, "Setup expired");
          updated += 1;
        }
      } else if (setup.status === "RUNNER_ACTIVE") {
        const hitTp2 =
          (direction === "LONG" && currentHigh >= tp2) ||
          (direction === "SHORT" && currentLow <= tp2);
        const pullbackToTp1 =
          (direction === "LONG" && currentLow <= tp1) ||
          (direction === "SHORT" && currentHigh >= tp1);
        const reversalToEntry =
          (direction === "LONG" && currentLow <= entry) ||
          (direction === "SHORT" && currentHigh >= entry);

        if (hitTp2) {
          await supabase
            .from("warbird_setups")
            .update({
              status: "TP2_HIT",
              current_event: "TP2_HIT",
              tp2_hit_at: nowIso,
            })
            .eq("id", setup.id);
          await recordEvent(supabase, setup.id, "TP2_HIT", nowIso, tp2, "TP2 reached");
          updated += 1;
          continue;
        }

        if (reversalToEntry) {
          await supabase
            .from("warbird_setups")
            .update({
              status: "PULLBACK_REVERSAL",
              current_event: "PULLBACK_REVERSAL",
              runner_exited_at: nowIso,
            })
            .eq("id", setup.id);
          await recordEvent(
            supabase,
            setup.id,
            "PULLBACK_REVERSAL",
            nowIso,
            entry,
            "Runner reversed back to entry",
          );
          updated += 1;
          continue;
        }

        if (pullbackToTp1) {
          await supabase
            .from("warbird_setups")
            .update({
              status: "RUNNER_EXITED",
              current_event: "RUNNER_EXITED",
              runner_exited_at: nowIso,
            })
            .eq("id", setup.id);
          await recordEvent(
            supabase,
            setup.id,
            "RUNNER_EXITED",
            nowIso,
            tp1,
            "Runner exited on pullback to TP1",
          );
          updated += 1;
        }
      }
    }

    await supabase.from("job_log").insert({
      job_name: "score-trades",
      status: "SUCCESS",
      rows_affected: updated,
      duration_ms: Date.now() - startTime,
    });

    return NextResponse.json({
      success: true,
      active_setups: activeSetups.length,
      updated,
      latest_price: Number(latestBar.close),
      duration_ms: Date.now() - startTime,
    });
  } catch (error) {
    const message = error instanceof Error ? error.message : "Internal error";
    try {
      await supabase.from("job_log").insert({
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
