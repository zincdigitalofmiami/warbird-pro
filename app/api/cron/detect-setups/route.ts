import { NextResponse } from "next/server";
import { createAdminClient } from "@/lib/supabase/admin";
import { isMarketOpen } from "@/lib/market-hours";
import type { CandleData } from "@/lib/types";
import { buildDailyBiasLayer } from "@/scripts/warbird/daily-layer";
import { buildStructure4H } from "@/scripts/warbird/structure-4h";
import { buildFibGeometry } from "@/scripts/warbird/fib-engine";
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
    const [dailyBarsRes, fourHourBarsRes, oneHourBarsRes, forecastRes] =
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
    if (forecastRes.error) throw new Error(`warbird_forecasts_1h query failed: ${forecastRes.error.message}`);

    const dailyBars = toCandles(dailyBarsRes.data);
    const fourHourBars = toCandles(fourHourBarsRes.data);
    const oneHourBars = toCandles(oneHourBarsRes.data);

    if (dailyBars.length < 20 || fourHourBars.length < 20 || oneHourBars.length < 55) {
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

    const convictionTs = new Date().toISOString();
    const triggerDecision = geometry ? "GO" : "NO_GO" as const;

    const convictionResult = evaluateConviction({
      dailyBias: daily.bias,
      bias4h: structure.bias_4h,
      bias1h: forecast.bias_1h,
      triggerDecision,
    });

    const convictionPayload = {
      ts: convictionTs,
      forecast_id: forecast.id,
      trigger_id: null,
      symbol_code: WARBIRD_DEFAULT_SYMBOL,
      ...convictionResult,
      daily_bias: daily.bias,
      bias_4h: structure.bias_4h,
      bias_1h: forecast.bias_1h,
      trigger_decision: triggerDecision,
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
    if (triggerDecision === "GO" && conviction.level !== "NO_TRADE") {
      const setupKey = [
        forecast.id,
        convictionTs.slice(0, 13),
        geometry.direction,
        Number(geometry.fibRatio ?? 0).toFixed(3),
      ].join(":");

      const setupPayload = {
        setup_key: setupKey,
        ts: convictionTs,
        symbol_code: WARBIRD_DEFAULT_SYMBOL,
        forecast_id: forecast.id,
        trigger_id: null,
        conviction_id: conviction.id,
        direction: geometry.direction,
        status: "ACTIVE",
        conviction_level: conviction.level,
        counter_trend: convictionResult.counterTrend,
        runner_eligible: false,
        fib_level: geometry.fibLevel,
        fib_ratio: geometry.fibRatio,
        entry_price: geometry.entry,
        stop_loss: geometry.stopLoss,
        tp1: geometry.tp1,
        tp2: geometry.tp2,
        volume_confirmation: null,
        volume_ratio: null,
        trigger_quality_ratio: null,
        runner_headroom: null,
        current_event: "TRIGGERED",
        trigger_bar_ts: convictionTs,
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
      rows_affected: setupId ? 4 : 3,
      duration_ms: Date.now() - startTime,
    });

    return NextResponse.json({
      success: true,
      daily_bias: daily.bias,
      bias_4h: structure.bias_4h,
      bias_1h: forecast.bias_1h,
      trigger: triggerDecision,
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
