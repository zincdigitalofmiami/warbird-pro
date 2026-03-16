import { NextResponse } from "next/server";
import { createAdminClient } from "@/lib/supabase/admin";
import { isMarketOpen } from "@/lib/market-hours";
import type { CandleData } from "@/lib/types";
import { buildDailyBiasLayer } from "@/scripts/warbird/daily-layer";
import { buildStructure4H } from "@/scripts/warbird/structure-4h";
import { buildFibGeometry } from "@/scripts/warbird/fib-engine";
import { evaluateTrigger15m } from "@/scripts/warbird/trigger-15m";
import { evaluateConviction } from "@/scripts/warbird/conviction-matrix";
import { REGIME_LABEL, WARBIRD_DEFAULT_SYMBOL, getDaysIntoRegime } from "@/lib/warbird/constants";
import type { WarbirdForecastRow } from "@/lib/warbird/types";

export const maxDuration = 60;

type OhlcvRow = {
  ts: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
};

function toCandles(rows: OhlcvRow[] | null | undefined): CandleData[] {
  return (rows ?? [])
    .slice()
    .reverse()
    .map((row) => ({
      time: Math.floor(new Date(row.ts).getTime() / 1000),
      open: Number(row.open),
      high: Number(row.high),
      low: Number(row.low),
      close: Number(row.close),
      volume: Number(row.volume),
    }));
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
  const url = new URL(request.url);
  const force = url.searchParams.get("force") === "1";

  if (!force && !isMarketOpen()) {
    return NextResponse.json({ skipped: true, reason: "market_closed" });
  }

  try {
    const [dailyBarsRes, fourHourBarsRes, oneHourBarsRes, fifteenBarsRes, forecastRes] =
      await Promise.all([
        supabase
          .from("mes_1d")
          .select("ts, open, high, low, close, volume")
          .order("ts", { ascending: false })
          .limit(240),
        supabase
          .from("mes_4h")
          .select("ts, open, high, low, close, volume")
          .order("ts", { ascending: false })
          .limit(120),
        supabase
          .from("mes_1h")
          .select("ts, open, high, low, close, volume")
          .order("ts", { ascending: false })
          .limit(160),
        supabase
          .from("mes_15m")
          .select("ts, open, high, low, close, volume")
          .order("ts", { ascending: false })
          .limit(160),
        supabase
          .from("warbird_forecasts_1h")
          .select("*")
          .eq("symbol_code", WARBIRD_DEFAULT_SYMBOL)
          .order("ts", { ascending: false })
          .limit(1)
          .returns<WarbirdForecastRow>()
          .maybeSingle(),
      ]);

    if (dailyBarsRes.error) throw new Error(`mes_1d query failed: ${dailyBarsRes.error.message}`);
    if (fourHourBarsRes.error) throw new Error(`mes_4h query failed: ${fourHourBarsRes.error.message}`);
    if (oneHourBarsRes.error) throw new Error(`mes_1h query failed: ${oneHourBarsRes.error.message}`);
    if (fifteenBarsRes.error) throw new Error(`mes_15m query failed: ${fifteenBarsRes.error.message}`);
    if (forecastRes.error) throw new Error(`warbird_forecasts_1h query failed: ${forecastRes.error.message}`);

    const dailyBars = toCandles(dailyBarsRes.data);
    const fourHourBars = toCandles(fourHourBarsRes.data);
    const oneHourBars = toCandles(oneHourBarsRes.data);
    const fifteenBars = toCandles(fifteenBarsRes.data);

    if (dailyBars.length < 20 || fourHourBars.length < 20 || oneHourBars.length < 55 || fifteenBars.length < 20) {
      return NextResponse.json({ skipped: true, reason: "insufficient_data" });
    }

    const daily = buildDailyBiasLayer(dailyBars, WARBIRD_DEFAULT_SYMBOL);
    const structure = buildStructure4H(fourHourBars, daily?.bias ?? "NEUTRAL", WARBIRD_DEFAULT_SYMBOL);

    if (!daily || !structure) {
      return NextResponse.json({ skipped: true, reason: "layer_build_failed" });
    }

    await supabase.from("warbird_daily_bias").upsert(daily, { onConflict: "ts" });
    await supabase.from("warbird_structure_4h").upsert(structure, { onConflict: "ts" });

    const forecast = (forecastRes.data as WarbirdForecastRow | null) ?? null;
    if (!forecast) {
      await supabase.from("job_log").insert({
        job_name: "detect-setups",
        status: "SKIPPED",
        rows_affected: 2,
        duration_ms: Date.now() - startTime,
        error_message: "No warbird_forecasts_1h row available",
      });
      return NextResponse.json({ skipped: true, reason: "no_forecast" });
    }

    const geometry = buildFibGeometry(oneHourBars, forecast.bias_1h);
    if (!geometry) {
      return NextResponse.json({ skipped: true, reason: "no_fib_geometry" });
    }

    const correlationScore =
      typeof forecast.feature_snapshot?.correlation_score === "number"
        ? Number(forecast.feature_snapshot.correlation_score)
        : null;

    const triggerPayload = evaluateTrigger15m({
      candles: fifteenBars,
      forecast,
      geometry,
      correlationScore,
    });

    const { data: trigger, error: triggerError } = await supabase
      .from("warbird_triggers_15m")
      .upsert(triggerPayload, { onConflict: "symbol_code,ts,forecast_id" })
      .select("*")
      .single();

    if (triggerError) {
      throw new Error(`warbird_triggers_15m upsert failed: ${triggerError.message}`);
    }

    const convictionPayload = {
      ts: trigger.ts,
      forecast_id: forecast.id,
      trigger_id: trigger.id,
      symbol_code: WARBIRD_DEFAULT_SYMBOL,
      ...evaluateConviction({
        dailyBias: daily.bias,
        bias4h: structure.bias_4h,
        bias1h: forecast.bias_1h,
        triggerDecision: trigger.decision,
      }),
      daily_bias: daily.bias,
      bias_4h: structure.bias_4h,
      bias_1h: forecast.bias_1h,
      trigger_decision: trigger.decision,
    };

    const { data: conviction, error: convictionError } = await supabase
      .from("warbird_conviction")
      .upsert(convictionPayload, { onConflict: "forecast_id" })
      .select("*")
      .single();

    if (convictionError) {
      throw new Error(`warbird_conviction upsert failed: ${convictionError.message}`);
    }

    let setupId: number | null = null;
    if (trigger.decision === "GO" && conviction.level !== "NO_TRADE") {
      const setupKey = [
        forecast.id,
        trigger.ts,
        trigger.direction,
        Number(trigger.fib_ratio ?? 0).toFixed(3),
      ].join(":");

      const setupPayload = {
        setup_key: setupKey,
        ts: trigger.ts,
        symbol_code: WARBIRD_DEFAULT_SYMBOL,
        forecast_id: forecast.id,
        trigger_id: trigger.id,
        conviction_id: conviction.id,
        direction: trigger.direction,
        status: "ACTIVE",
        conviction_level: conviction.level,
        counter_trend: conviction.counter_trend,
        runner_eligible: conviction.runner_eligible,
        fib_level: trigger.fib_level,
        fib_ratio: trigger.fib_ratio,
        entry_price: trigger.entry_price,
        stop_loss: trigger.stop_loss,
        tp1: trigger.tp1,
        tp2: trigger.tp2,
        volume_confirmation: trigger.volume_confirmation,
        volume_ratio: trigger.volume_ratio,
        trigger_quality_ratio: trigger.trigger_quality_ratio,
        runner_headroom: trigger.runner_headroom,
        current_event: "TRIGGERED",
        trigger_bar_ts: trigger.ts,
        expires_at: new Date(new Date(trigger.ts).getTime() + 48 * 60 * 60 * 1000).toISOString(),
        notes: geometry.measuredMove
          ? `Measured move quality ${geometry.quality}`
          : "Canonical fib setup",
      };

      const { data: setup, error: setupError } = await supabase
        .from("warbird_setups")
        .upsert(setupPayload, { onConflict: "setup_key" })
        .select("*")
        .single();

      if (setupError) {
        throw new Error(`warbird_setups upsert failed: ${setupError.message}`);
      }

      setupId = setup.id;

      const { data: existingEvent } = await supabase
        .from("warbird_setup_events")
        .select("id")
        .eq("setup_id", setup.id)
        .eq("event_type", "TRIGGERED")
        .limit(1)
        .maybeSingle();

      if (!existingEvent) {
        const { error: eventError } = await supabase
          .from("warbird_setup_events")
          .insert({
            setup_id: setup.id,
            ts: setup.ts,
            event_type: "TRIGGERED",
            price: setup.entry_price,
            note: setup.notes,
            metadata: {
              conviction_level: setup.conviction_level,
              runner_eligible: setup.runner_eligible,
              regime_label: REGIME_LABEL,
              days_into_regime: getDaysIntoRegime(setup.ts),
            },
          });
        if (eventError) {
          throw new Error(`warbird_setup_events insert failed: ${eventError.message}`);
        }
      }

      if (geometry.measuredMove) {
        await supabase.from("measured_moves").upsert(
          {
            ts: new Date(geometry.measuredMove.pointC.time * 1000).toISOString(),
            symbol_code: WARBIRD_DEFAULT_SYMBOL,
            direction: geometry.measuredMove.direction === "BULLISH" ? "LONG" : "SHORT",
            anchor_price: geometry.measuredMove.pointA.price,
            target_price: geometry.measuredMove.target,
            retracement_price: geometry.measuredMove.pointC.price,
            fib_level: geometry.measuredMove.retracementRatio,
            status: "ACTIVE",
          },
          { onConflict: "ts" },
        );
      }
    }

    await supabase.from("job_log").insert({
      job_name: "detect-setups",
      status: "SUCCESS",
      rows_affected: setupId ? 5 : 4,
      duration_ms: Date.now() - startTime,
    });

    return NextResponse.json({
      success: true,
      daily_bias: daily.bias,
      bias_4h: structure.bias_4h,
      bias_1h: forecast.bias_1h,
      trigger: trigger.decision,
      conviction: conviction.level,
      setup_id: setupId,
      duration_ms: Date.now() - startTime,
    });
  } catch (error) {
    const message = error instanceof Error ? error.message : "Internal error";
    try {
      await supabase.from("job_log").insert({
        job_name: "detect-setups",
        status: "FAILED",
        error_message: message,
        duration_ms: Date.now() - startTime,
      });
    } catch {
      // ignore logging failure
    }
    return NextResponse.json({ error: message }, { status: 500 });
  }
}
