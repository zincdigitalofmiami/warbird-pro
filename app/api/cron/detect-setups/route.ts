import { NextResponse } from "next/server";
import { createAdminClient } from "@/lib/supabase/admin";
import { validateCronRequest } from "@/lib/cron-auth";
import { isMarketOpen, isWeekendBar } from "@/lib/market-hours";
import type { CandleData } from "@/lib/types";
import { buildDailyBiasLayer } from "@/scripts/warbird/daily-layer";
import { buildStructure4H } from "@/scripts/warbird/structure-4h";
import { buildFibGeometry } from "@/scripts/warbird/fib-engine";
import { evaluateTrigger } from "@/scripts/warbird/trigger-15m";
import { evaluateConviction } from "@/scripts/warbird/conviction-matrix";
import { REGIME_LABEL, WARBIRD_DEFAULT_SYMBOL, getDaysIntoRegime } from "@/lib/warbird/constants";
import type { WarbirdBias } from "@/lib/warbird/types";

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

function hasNonWeekendContinuity(candles: CandleData[], intervalSec: number): boolean {
  if (candles.length < 2) return true;

  for (let i = 1; i < candles.length; i += 1) {
    const prev = candles[i - 1].time;
    const current = candles[i].time;
    const delta = current - prev;

    if (delta === intervalSec) continue;
    if (delta < intervalSec) return false;

    for (let missing = prev + intervalSec; missing < current; missing += intervalSec) {
      if (!isWeekendBar(missing)) {
        return false;
      }
    }
  }

  return true;
}

function directionToBias(direction: "LONG" | "SHORT"): WarbirdBias {
  return direction === "LONG" ? "BULL" : "BEAR";
}

export async function GET(request: Request) {
  const authError = validateCronRequest(request);
  if (authError) {
    return authError;
  }

  const startTime = Date.now();
  const supabase = createAdminClient();
  const url = new URL(request.url);
  const force = url.searchParams.get("force") === "1";

  if (!force && !isMarketOpen()) {
    try {
      await writeJobLog(supabase, {
        job_name: "detect-setups",
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
    // Fetch all timeframes in parallel:
    // - 1D/4H for macro context layers
    // - 15m for strict setup geometry authority
    // - 1m for microstructure + indicator computation
    const [
      dailyBarsRes,
      fourHourBarsRes,
      fifteenMinBarsRes,
      oneMinBarsRes,
      gprRes,
      vixRes,
      trumpEffectRes,
    ] =
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
        // 15-minute bars are strict geometry authority
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
          .from("geopolitical_risk_1d")
          .select("ts, gpr_daily")
          .order("ts", { ascending: false })
          .limit(1)
          .maybeSingle(),
        supabase
          .from("econ_vol_1d")
          .select("ts, value")
          .eq("series_id", "VIXCLS")
          .order("ts", { ascending: false })
          .limit(1)
          .maybeSingle(),
        supabase
          .from("trump_effect_1d")
          .select("ts")
          .order("ts", { ascending: false })
          .limit(1)
          .maybeSingle(),
      ]);

    if (dailyBarsRes.error) throw new Error(`mes_1d query failed: ${dailyBarsRes.error.message}`);
    if (fourHourBarsRes.error) throw new Error(`mes_4h query failed: ${fourHourBarsRes.error.message}`);
    if (fifteenMinBarsRes.error) throw new Error(`mes_15m query failed: ${fifteenMinBarsRes.error.message}`);
    if (oneMinBarsRes.error) throw new Error(`mes_1m query failed: ${oneMinBarsRes.error.message}`);
    if (gprRes.error) throw new Error(`geopolitical_risk_1d query failed: ${gprRes.error.message}`);
    if (vixRes.error) throw new Error(`econ_vol_1d query failed: ${vixRes.error.message}`);
    if (trumpEffectRes.error) throw new Error(`trump_effect_1d query failed: ${trumpEffectRes.error.message}`);

    const dailyBars = toCandles(dailyBarsRes.data);
    const fourHourBars = toCandles(fourHourBarsRes.data);
    const fifteenMinBars = toCandles(fifteenMinBarsRes.data);
    const oneMinBars = toCandles(oneMinBarsRes.data);

    if (dailyBars.length < 20 || fourHourBars.length < 20 || fifteenMinBars.length < 55) {
      await writeJobLog(supabase, {
        job_name: "detect-setups",
        status: "SKIPPED",
        rows_affected: 0,
        duration_ms: Date.now() - startTime,
        error_message: "insufficient_data",
      });
      return NextResponse.json({ skipped: true, reason: "insufficient_data" });
    }

    const has15mContinuity = hasNonWeekendContinuity(fifteenMinBars, 15 * 60);
    const has1mContinuity = hasNonWeekendContinuity(oneMinBars, 60);
    if (!has15mContinuity || !has1mContinuity) {
      await writeJobLog(supabase, {
        job_name: "detect-setups",
        status: "SKIPPED",
        rows_affected: 0,
        duration_ms: Date.now() - startTime,
        error_message: `continuity_gap (mes_15m=${has15mContinuity}, mes_1m=${has1mContinuity})`,
      });
      return NextResponse.json({
        skipped: true,
        reason: "continuity_gap",
        continuity: {
          mes_15m: has15mContinuity,
          mes_1m: has1mContinuity,
        },
      });
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
    let rowsWritten = 2;

    const barCloseTs = new Date(fifteenMinBars[fifteenMinBars.length - 1].time * 1000).toISOString();
    const triggerBarTs = new Date(oneMinBars[oneMinBars.length - 1].time * 1000).toISOString();
    const geometryBias = structure.bias_4h !== "NEUTRAL" ? structure.bias_4h : daily.bias;

    // ── Layer 3: 15m fib geometry (strict setup authority) ──────────────
    const triggerGeometry = buildFibGeometry(fifteenMinBars, geometryBias);
    if (!triggerGeometry) {
      await writeJobLog(supabase, {
        job_name: "detect-setups",
        status: "SKIPPED",
        rows_affected: rowsWritten,
        duration_ms: Date.now() - startTime,
        error_message: "no_fib_geometry",
      });
      return NextResponse.json({ skipped: true, reason: "no_fib_geometry" });
    }

    const bias15m = directionToBias(triggerGeometry.direction);

    // ── Layer 4: Conviction (bias alignment) ───────────────────────────
    const convictionResult = evaluateConviction({
      dailyBias: daily.bias,
      bias4h: structure.bias_4h,
      bias15m,
    });

    // ── Layer 5: Trigger (1m indicators + microstructure at 15m fib zone)
    // Trigger uses the 15m fib levels for zone proximity — that's where
    // the intraday reversal happens.
    const { trigger: triggerResult, features: triggerFeatures } = evaluateTrigger({
      candles1m: oneMinBars,
      geometry: triggerGeometry,
      barCloseTs,
      symbolCode: WARBIRD_DEFAULT_SYMBOL,
    });

    // ── Persist trigger ────────────────────────────────────────────────
    const { data: triggerRow, error: triggerError } = await supabase
      .from("warbird_triggers_15m")
      .upsert(triggerResult, { onConflict: "symbol_code,timeframe,bar_close_ts" })
      .select("*")
      .single();

    if (triggerError) {
      throw new Error(`warbird_triggers_15m upsert failed: ${triggerError.message}`);
    }
    const triggerId = triggerRow.id;
    rowsWritten += 1;

    // ── Persist conviction ─────────────────────────────────────────────
    const convictionPayload = {
      bar_close_ts: barCloseTs,
      timeframe: "M15",
      trigger_id: triggerId,
      symbol_code: WARBIRD_DEFAULT_SYMBOL,
      ...convictionResult,
      daily_bias: daily.bias,
      bias_4h: structure.bias_4h,
      bias_15m: bias15m,
      trigger_decision: triggerResult.decision,
    };

    const { data: conviction, error: convictionError } = await supabase
      .from("warbird_conviction")
      .upsert(convictionPayload, { onConflict: "symbol_code,timeframe,bar_close_ts" })
      .select("*")
      .single();

    if (convictionError) {
      throw new Error(`warbird_conviction upsert failed: ${convictionError.message}`);
    }
    rowsWritten += 1;

    const latestGprTs = gprRes.data?.ts ? new Date(gprRes.data.ts).getTime() : null;
    const latestTrumpTs = trumpEffectRes.data?.ts ? new Date(trumpEffectRes.data.ts).getTime() : null;
    const riskPayload = {
      bar_close_ts: barCloseTs,
      timeframe: "M15",
      symbol_code: WARBIRD_DEFAULT_SYMBOL,
      tp1_probability: null,
      tp2_probability: null,
      reversal_risk: null,
      confidence_score: triggerFeatures.triggerScore,
      garch_sigma: null,
      garch_vol_ratio: null,
      zone_1_upper: null,
      zone_1_lower: null,
      zone_2_upper: null,
      zone_2_lower: null,
      gpr_level:
        latestGprTs != null && Date.now() - latestGprTs <= 14 * 24 * 60 * 60 * 1000
          ? Number(gprRes.data?.gpr_daily ?? null)
          : null,
      trump_effect_active:
        latestTrumpTs != null
          ? Date.now() - latestTrumpTs <= 7 * 24 * 60 * 60 * 1000
          : null,
      vix_level: vixRes.data?.value != null ? Number(vixRes.data.value) : null,
      vix_percentile_20d: null,
      vix_percentile_regime: null,
      vol_state_name: null,
      regime_label: REGIME_LABEL,
      days_into_regime: getDaysIntoRegime(barCloseTs),
    };

    const { error: riskError } = await supabase
      .from("warbird_risk")
      .upsert(riskPayload, { onConflict: "symbol_code,timeframe,bar_close_ts" });

    if (riskError) {
      throw new Error(`warbird_risk upsert failed: ${riskError.message}`);
    }
    rowsWritten += 1;

    // ── Create setup only if trigger says GO and conviction allows. ─────
    let setupId: number | null = null;
    const triggerEligible = triggerResult.decision === "GO" && conviction.level !== "NO_TRADE";

    if (triggerEligible) {
      const setupKey = `${WARBIRD_DEFAULT_SYMBOL}:M15:${barCloseTs}`;

      const setupPayload = {
        setup_key: setupKey,
        bar_close_ts: barCloseTs,
        timeframe: "M15",
        symbol_code: WARBIRD_DEFAULT_SYMBOL,
        trigger_id: triggerId,
        conviction_id: conviction.id,
        direction: triggerGeometry.direction,
        status: "ACTIVE",
        conviction_level: conviction.level,
        counter_trend: convictionResult.counterTrend,
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
        current_event: "TRIGGERED",
        trigger_bar_ts: triggerBarTs,
        notes: buildSetupNotes(triggerGeometry, triggerFeatures),
      };

      const { data: setup, error: setupError } = await supabase
        .from("warbird_setups")
        .upsert(setupPayload, { onConflict: "symbol_code,timeframe,bar_close_ts" })
        .select("*")
        .single();

      if (setupError) {
        throw new Error(`warbird_setups upsert failed: ${setupError.message}`);
      }

      setupId = setup.id;
      rowsWritten += 1;

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
            ts: setup.trigger_bar_ts,
            event_type: "TRIGGERED",
            price: setup.entry_price,
            note: setup.notes,
            metadata: {
              conviction_level: setup.conviction_level,
              regime_label: REGIME_LABEL,
              days_into_regime: getDaysIntoRegime(setup.bar_close_ts),
              actual_retrace_ratio: triggerGeometry.actualRetraceRatio,
              fib_source: "15m",
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
        rowsWritten += 1;
      }

      if (triggerGeometry.measuredMove && setupId != null) {
        await supabase.from("measured_moves").upsert(
          {
            setup_id: setupId,
            ts: new Date(triggerGeometry.measuredMove.pointC.time * 1000).toISOString(),
            symbol_code: WARBIRD_DEFAULT_SYMBOL,
            direction: triggerGeometry.measuredMove.direction === "BULLISH" ? "LONG" : "SHORT",
            anchor_price: triggerGeometry.measuredMove.pointA.price,
            target_price: triggerGeometry.measuredMove.target,
            retracement_price: triggerGeometry.measuredMove.pointC.price,
            fib_level: triggerGeometry.measuredMove.retracementRatio,
            status: "ACTIVE",
          },
          { onConflict: "setup_id" },
        );
        rowsWritten += 1;
      }
    }

    await writeJobLog(supabase, {
      job_name: "detect-setups",
      status: "SUCCESS",
      rows_affected: rowsWritten,
      duration_ms: Date.now() - startTime,
    });

    return NextResponse.json({
      success: true,
      daily_bias: daily.bias,
      bias_4h: structure.bias_4h,
      bias_15m: bias15m,
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
      fib_source: "15m",
      precise_entry: triggerFeatures.preciseEntry,
      precise_stop: triggerFeatures.preciseStop,
      trigger_fib: {
        entry: triggerGeometry.entry,
        stop: triggerGeometry.stopLoss,
        tp1: triggerGeometry.tp1,
        tp2: triggerGeometry.tp2,
      },
      setup_id: setupId,
      duration_ms: Date.now() - startTime,
    });
  } catch (error) {
    const message = error instanceof Error ? error.message : "Internal error";
    try {
      await writeJobLog(supabase, {
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
