import { NextResponse } from "next/server";
import { createAdminClient } from "@/lib/supabase/admin";
import { isMarketOpen } from "@/lib/market-hours";
import type { CandleData } from "@/lib/types";
import { buildDailyBiasLayer } from "@/scripts/warbird/daily-layer";
import { buildStructure4H } from "@/scripts/warbird/structure-4h";
import { buildFibGeometry } from "@/scripts/warbird/fib-engine";
import { evaluateTrigger } from "@/scripts/warbird/trigger-15m";
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
    // Fetch all timeframes in parallel:
    // - 1D/4H/1H for macro layers (bias, structure, zone)
    // - 15m for trigger-level fib geometry (intraday precision)
    // - 1m for microstructure + indicator computation
    const [dailyBarsRes, fourHourBarsRes, oneHourBarsRes, fifteenMinBarsRes, oneMinBarsRes, forecastRes] =
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
        // 15-minute bars for trigger-level fib (last 120 = 30 hours of intraday structure)
        supabase
          .from("mes_15m")
          .select("ts, open, high, low, close, volume")
          .order("ts", { ascending: false })
          .limit(120),
        // 1-minute bars for trigger microstructure + indicators (last 60 = 1 hour)
        supabase
          .from("mes_1m")
          .select("ts, open, high, low, close, volume")
          .order("ts", { ascending: false })
          .limit(60),
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
    if (fifteenMinBarsRes.error) throw new Error(`mes_15m query failed: ${fifteenMinBarsRes.error.message}`);
    if (oneMinBarsRes.error) throw new Error(`mes_1m query failed: ${oneMinBarsRes.error.message}`);
    if (forecastRes.error) throw new Error(`warbird_forecasts_1h query failed: ${forecastRes.error.message}`);

    const dailyBars = toCandles(dailyBarsRes.data);
    const fourHourBars = toCandles(fourHourBarsRes.data);
    const oneHourBars = toCandles(oneHourBarsRes.data);
    const fifteenMinBars = toCandles(fifteenMinBarsRes.data);
    const oneMinBars = toCandles(oneMinBarsRes.data);

    if (dailyBars.length < 20 || fourHourBars.length < 20 || oneHourBars.length < 55) {
      return NextResponse.json({ skipped: true, reason: "insufficient_data" });
    }

    // ── Layer 1: Daily bias (200d MA) ──────────────────────────────────
    const daily = buildDailyBiasLayer(dailyBars, WARBIRD_DEFAULT_SYMBOL);
    // ── Layer 2: 4H structure ──────────────────────────────────────────
    const structure = buildStructure4H(fourHourBars, daily?.bias ?? "NEUTRAL", WARBIRD_DEFAULT_SYMBOL);

    if (!daily || !structure) {
      return NextResponse.json({ skipped: true, reason: "layer_build_failed" });
    }

    await supabase.from("warbird_daily_bias").upsert(daily, { onConflict: "ts" });
    await supabase.from("warbird_structure_4h").upsert(structure, { onConflict: "ts" });

    // ── Layer 3: 1H forecast (model output) ────────────────────────────
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

    // ── Layer 4: 1H fib geometry (macro zone identification) ────────────
    const geometry1h = buildFibGeometry(oneHourBars, forecast.bias_1h);
    if (!geometry1h) {
      return NextResponse.json({ skipped: true, reason: "no_fib_geometry" });
    }

    // ── Layer 4b: 15m fib geometry (trigger-level precision) ──────────
    // This is the intraday fib — tighter anchor, tighter levels, catches
    // the 20-60pt moves that the 1H misses. Same function, different data.
    const geometry15m = fifteenMinBars.length >= 55
      ? buildFibGeometry(fifteenMinBars, forecast.bias_1h)
      : null;

    // Use 15m fib for trigger precision when available, 1H as fallback
    const triggerGeometry = geometry15m ?? geometry1h;

    // ── Layer 5: Conviction (bias alignment) ───────────────────────────
    const convictionResult = evaluateConviction({
      dailyBias: daily.bias,
      bias4h: structure.bias_4h,
      bias1h: forecast.bias_1h,
    });

    // ── Layer 6: Trigger (1m indicators + microstructure at 15m fib zone)
    // Trigger uses the 15m fib levels for zone proximity — that's where
    // the intraday reversal happens, not at the wide 1H levels.
    const { trigger: triggerResult, features: triggerFeatures } = evaluateTrigger({
      candles1m: oneMinBars,
      forecast,
      geometry: triggerGeometry,
    });

    // ── Persist trigger ────────────────────────────────────────────────
    const { data: triggerRow, error: triggerError } = await supabase
      .from("warbird_triggers")
      .upsert(triggerResult, { onConflict: "forecast_id" })
      .select("*")
      .single();

    // If triggers table doesn't exist yet, continue without it
    const triggerId = triggerRow?.id ?? null;
    if (triggerError && !triggerError.message.includes("does not exist")) {
      console.error(`warbird_triggers upsert: ${triggerError.message}`);
    }

    // ── Persist conviction ─────────────────────────────────────────────
    const convictionTs = new Date().toISOString();
    const convictionPayload = {
      ts: convictionTs,
      forecast_id: forecast.id,
      trigger_id: triggerId,
      symbol_code: WARBIRD_DEFAULT_SYMBOL,
      ...convictionResult,
      daily_bias: daily.bias,
      bias_4h: structure.bias_4h,
      bias_1h: forecast.bias_1h,
      trigger_decision: triggerResult.decision,
    };

    const { data: conviction, error: convictionError } = await supabase
      .from("warbird_conviction")
      .upsert(convictionPayload, { onConflict: "forecast_id" })
      .select("*")
      .single();

    if (convictionError) {
      throw new Error(`warbird_conviction upsert failed: ${convictionError.message}`);
    }

    // ── Create setup only if trigger says GO and conviction allows ─────
    let setupId: number | null = null;
    if (triggerResult.decision === "GO" && conviction.level !== "NO_TRADE") {
      const setupKey = [
        forecast.id,
        convictionTs.slice(0, 13),
        triggerGeometry.direction,
        Number(triggerGeometry.fibRatio ?? 0).toFixed(3),
        triggerFeatures.triggerScore.toFixed(2),
      ].join(":");

      const setupPayload = {
        setup_key: setupKey,
        ts: convictionTs,
        symbol_code: WARBIRD_DEFAULT_SYMBOL,
        forecast_id: forecast.id,
        trigger_id: triggerId,
        conviction_id: conviction.id,
        direction: triggerGeometry.direction,
        status: "ACTIVE",
        conviction_level: conviction.level,
        counter_trend: convictionResult.counterTrend,
        runner_eligible: false,
        fib_level: triggerGeometry.fibLevel,
        fib_ratio: triggerGeometry.fibRatio,
        // Use PRECISE levels from 1m trigger, not coarse 1H levels
        entry_price: triggerFeatures.preciseEntry,
        stop_loss: triggerFeatures.preciseStop,
        // TP from trigger fib (15m precision), not 1H
        tp1: triggerGeometry.tp1,
        tp2: triggerGeometry.tp2,
        volume_confirmation: triggerFeatures.volumeConfirmed,
        volume_ratio: triggerFeatures.volumeRatio,
        trigger_quality_ratio: triggerFeatures.triggerScore,
        runner_headroom: triggerResult.runner_headroom,
        current_event: "TRIGGERED",
        trigger_bar_ts: triggerResult.ts,
        notes: buildSetupNotes(triggerGeometry, triggerFeatures),
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
              actual_retrace_ratio: triggerGeometry.actualRetraceRatio,
              fib_source: geometry15m ? "15m" : "1h",
              macro_fib_entry: geometry1h.entry,
              macro_fib_tp1: geometry1h.tp1,
              macro_fib_tp2: geometry1h.tp2,
              trigger_score: triggerFeatures.triggerScore,
              rejection_detected: triggerFeatures.rejectionDetected,
              rejection_wick_ratio: triggerFeatures.rejectionWickRatio,
              volume_spike: triggerFeatures.volumeSpike,
              engulfing: triggerFeatures.engulfingDetected,
              momentum_shift: triggerFeatures.momentumShift,
              reversal_speed: triggerFeatures.reversalSpeed,
              bars_in_zone: triggerFeatures.barsInZone,
              hour_utc: triggerFeatures.hourUtc,
              zone_proximity: triggerFeatures.zoneProximity,
              wick_through: triggerFeatures.wickThrough,
            },
          });
        if (eventError) {
          throw new Error(`warbird_setup_events insert failed: ${eventError.message}`);
        }
      }

      if (triggerGeometry.measuredMove) {
        await supabase.from("measured_moves").upsert(
          {
            ts: new Date(triggerGeometry.measuredMove.pointC.time * 1000).toISOString(),
            symbol_code: WARBIRD_DEFAULT_SYMBOL,
            direction: triggerGeometry.measuredMove.direction === "BULLISH" ? "LONG" : "SHORT",
            anchor_price: triggerGeometry.measuredMove.pointA.price,
            target_price: triggerGeometry.measuredMove.target,
            retracement_price: triggerGeometry.measuredMove.pointC.price,
            fib_level: triggerGeometry.measuredMove.retracementRatio,
            status: "ACTIVE",
          },
          { onConflict: "ts" },
        );
      }
    }

    await supabase.from("job_log").insert({
      job_name: "detect-setups",
      status: "SUCCESS",
      rows_affected: setupId ? 5 : 3,
      duration_ms: Date.now() - startTime,
    });

    return NextResponse.json({
      success: true,
      daily_bias: daily.bias,
      bias_4h: structure.bias_4h,
      bias_1h: forecast.bias_1h,
      trigger_decision: triggerResult.decision,
      trigger_score: triggerFeatures.triggerScore,
      trigger_features: {
        rejection: triggerFeatures.rejectionDetected,
        volume_spike: triggerFeatures.volumeSpike,
        engulfing: triggerFeatures.engulfingDetected,
        momentum_shift: triggerFeatures.momentumShift,
        reversal_speed: triggerFeatures.reversalSpeed,
        bars_in_zone: triggerFeatures.barsInZone,
        hour_utc: triggerFeatures.hourUtc,
      },
      conviction: conviction.level,
      fib_source: geometry15m ? "15m" : "1h",
      precise_entry: triggerFeatures.preciseEntry,
      precise_stop: triggerFeatures.preciseStop,
      trigger_fib: {
        entry: triggerGeometry.entry,
        stop: triggerGeometry.stopLoss,
        tp1: triggerGeometry.tp1,
        tp2: triggerGeometry.tp2,
      },
      macro_fib: {
        entry: geometry1h.entry,
        stop: geometry1h.stopLoss,
        tp1: geometry1h.tp1,
        tp2: geometry1h.tp2,
      },
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

function buildSetupNotes(
  geometry: ReturnType<typeof buildFibGeometry> & object,
  features: { triggerScore: number; rejectionDetected: boolean; volumeSpike: boolean; engulfingDetected: boolean; momentumShift: boolean; reversalSpeed: number; actualRetraceRatio?: number },
): string {
  const parts: string[] = [];

  if ('measuredMove' in geometry && geometry.measuredMove) {
    parts.push(`Measured move quality ${('quality' in geometry ? geometry.quality : 'N/A')}`);
  } else {
    parts.push("Canonical fib setup");
  }

  if ('actualRetraceRatio' in geometry) {
    parts.push(`retrace ${geometry.actualRetraceRatio}`);
  }

  parts.push(`trigger=${features.triggerScore.toFixed(2)}`);

  const signals: string[] = [];
  if (features.rejectionDetected) signals.push("rejection");
  if (features.volumeSpike) signals.push("vol_spike");
  if (features.engulfingDetected) signals.push("engulfing");
  if (features.momentumShift) signals.push("mom_shift");
  if (signals.length > 0) parts.push(`[${signals.join("+")}]`);

  if (features.reversalSpeed > 0) {
    parts.push(`rev_speed=${features.reversalSpeed.toFixed(1)}pts`);
  }

  return parts.join(", ");
}
