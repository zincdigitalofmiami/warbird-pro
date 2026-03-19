import { NextResponse } from "next/server";
import { createAdminClient } from "@/lib/supabase/admin";
import { isMarketOpen, isWeekendBar } from "@/lib/market-hours";
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

type JobLogPayload = {
  job_name: string;
  status: "SUCCESS" | "PARTIAL" | "FAILED" | "SKIPPED";
  rows_affected?: number;
  duration_ms: number;
  error_message?: string;
};

type ForecastGateMetrics = {
  probHitSlFirst: number | null;
  probHitPt1First: number | null;
  probHitPt2AfterPt1: number | null;
  setupScore: number | null;
};

type ForecastGateThresholds = {
  maxProbHitSlFirst: number;
  minProbHitPt1First: number;
  minProbHitPt2AfterPt1: number;
  minSetupScore: number;
};

type ForecastGateDecision = {
  allow: boolean;
  reasons: string[];
  metrics: ForecastGateMetrics;
  thresholds: ForecastGateThresholds;
};

const DEFAULT_FORECAST_GATE_THRESHOLDS: ForecastGateThresholds = {
  maxProbHitSlFirst: 0.45,
  minProbHitPt1First: 0.5,
  minProbHitPt2AfterPt1: 0.35,
  minSetupScore: 55,
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

function readEnvNumber(name: string): number | null {
  const raw = process.env[name];
  if (!raw) return null;
  const parsed = Number(raw);
  if (!Number.isFinite(parsed)) return null;
  return parsed;
}

function parseSnapshotMetric(snapshot: Record<string, unknown> | null | undefined, key: string): number | null {
  const value = snapshot?.[key];
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function resolveForecastMetrics(forecast: WarbirdForecastRow): ForecastGateMetrics {
  const snapshot =
    forecast.feature_snapshot && typeof forecast.feature_snapshot === "object"
      ? (forecast.feature_snapshot as Record<string, unknown>)
      : null;

  return {
    probHitSlFirst: forecast.prob_hit_sl_first ?? parseSnapshotMetric(snapshot, "prob_hit_sl_first"),
    probHitPt1First: forecast.prob_hit_pt1_first ?? parseSnapshotMetric(snapshot, "prob_hit_pt1_first"),
    probHitPt2AfterPt1:
      forecast.prob_hit_pt2_after_pt1 ?? parseSnapshotMetric(snapshot, "prob_hit_pt2_after_pt1"),
    setupScore: forecast.setup_score ?? parseSnapshotMetric(snapshot, "setup_score"),
  };
}

function resolveForecastGateThresholds(): ForecastGateThresholds {
  return {
    maxProbHitSlFirst:
      readEnvNumber("WARBIRD_MAX_PROB_HIT_SL_FIRST") ??
      DEFAULT_FORECAST_GATE_THRESHOLDS.maxProbHitSlFirst,
    minProbHitPt1First:
      readEnvNumber("WARBIRD_MIN_PROB_HIT_PT1_FIRST") ??
      DEFAULT_FORECAST_GATE_THRESHOLDS.minProbHitPt1First,
    minProbHitPt2AfterPt1:
      readEnvNumber("WARBIRD_MIN_PROB_HIT_PT2_AFTER_PT1") ??
      DEFAULT_FORECAST_GATE_THRESHOLDS.minProbHitPt2AfterPt1,
    minSetupScore:
      readEnvNumber("WARBIRD_MIN_SETUP_SCORE") ??
      DEFAULT_FORECAST_GATE_THRESHOLDS.minSetupScore,
  };
}

function evaluateForecastGate(forecast: WarbirdForecastRow): ForecastGateDecision {
  const metrics = resolveForecastMetrics(forecast);
  const thresholds = resolveForecastGateThresholds();
  const reasons: string[] = [];

  if (metrics.probHitSlFirst == null) {
    reasons.push("missing_prob_hit_sl_first");
  } else if (metrics.probHitSlFirst > thresholds.maxProbHitSlFirst) {
    reasons.push(
      `prob_hit_sl_first>${thresholds.maxProbHitSlFirst.toFixed(2)} (${metrics.probHitSlFirst.toFixed(3)})`,
    );
  }

  if (metrics.probHitPt1First == null) {
    reasons.push("missing_prob_hit_pt1_first");
  } else if (metrics.probHitPt1First < thresholds.minProbHitPt1First) {
    reasons.push(
      `prob_hit_pt1_first<${thresholds.minProbHitPt1First.toFixed(2)} (${metrics.probHitPt1First.toFixed(3)})`,
    );
  }

  if (metrics.probHitPt2AfterPt1 == null) {
    reasons.push("missing_prob_hit_pt2_after_pt1");
  } else if (metrics.probHitPt2AfterPt1 < thresholds.minProbHitPt2AfterPt1) {
    reasons.push(
      `prob_hit_pt2_after_pt1<${thresholds.minProbHitPt2AfterPt1.toFixed(2)} (${metrics.probHitPt2AfterPt1.toFixed(3)})`,
    );
  }

  if (metrics.setupScore == null) {
    reasons.push("missing_setup_score");
  } else if (metrics.setupScore < thresholds.minSetupScore) {
    reasons.push(`setup_score<${thresholds.minSetupScore} (${metrics.setupScore.toFixed(2)})`);
  }

  return {
    allow: reasons.length === 0,
    reasons,
    metrics,
    thresholds,
  };
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
    const [dailyBarsRes, fourHourBarsRes, fifteenMinBarsRes, oneMinBarsRes, forecastRes] =
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
    if (fifteenMinBarsRes.error) throw new Error(`mes_15m query failed: ${fifteenMinBarsRes.error.message}`);
    if (oneMinBarsRes.error) throw new Error(`mes_1m query failed: ${oneMinBarsRes.error.message}`);
    if (forecastRes.error) throw new Error(`warbird_forecasts_1h query failed: ${forecastRes.error.message}`);

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

    // ── Layer 3: 1H forecast (model output) ────────────────────────────
    const forecast = (forecastRes.data as WarbirdForecastRow | null) ?? null;
    if (!forecast) {
      await writeJobLog(supabase, {
        job_name: "detect-setups",
        status: "SKIPPED",
        rows_affected: 2,
        duration_ms: Date.now() - startTime,
        error_message: "No warbird_forecasts_1h row available",
      });
      return NextResponse.json({ skipped: true, reason: "no_forecast" });
    }

    const forecastAgeMs = Date.now() - new Date(forecast.ts).getTime();
    const maxForecastAgeMs = 90 * 60 * 1000;
    if (forecastAgeMs > maxForecastAgeMs) {
      await writeJobLog(supabase, {
        job_name: "detect-setups",
        status: "SKIPPED",
        rows_affected: 2,
        duration_ms: Date.now() - startTime,
        error_message: `stale_forecast age_ms=${forecastAgeMs}`,
      });
      return NextResponse.json({
        skipped: true,
        reason: "stale_forecast",
        forecast_ts: forecast.ts,
        forecast_age_ms: forecastAgeMs,
      });
    }

    const forecastGate = evaluateForecastGate(forecast);

    // ── Layer 4: 15m fib geometry (strict setup authority) ──────────────
    const triggerGeometry = buildFibGeometry(fifteenMinBars, forecast.bias_1h);
    if (!triggerGeometry) {
      await writeJobLog(supabase, {
        job_name: "detect-setups",
        status: "SKIPPED",
        rows_affected: 3,
        duration_ms: Date.now() - startTime,
        error_message: "no_fib_geometry",
      });
      return NextResponse.json({ skipped: true, reason: "no_fib_geometry" });
    }

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
      .from("warbird_triggers_15m")
      .upsert(triggerResult, { onConflict: "symbol_code,ts,forecast_id" })
      .select("*")
      .single();

    if (triggerError) {
      throw new Error(`warbird_triggers_15m upsert failed: ${triggerError.message}`);
    }
    const triggerId = triggerRow.id;

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

    // ── Create setup only if trigger says GO, conviction allows, and
    // promoted forecast probabilities pass execution gates.
    let setupId: number | null = null;
    const triggerEligible = triggerResult.decision === "GO" && conviction.level !== "NO_TRADE";

    if (triggerEligible && !forecastGate.allow) {
      const gateReason = `forecast_gate_failed: ${forecastGate.reasons.join("; ")}`;
      const { error: triggerUpdateError } = await supabase
        .from("warbird_triggers_15m")
        .update({ no_trade_reason: gateReason })
        .eq("id", triggerId);
      if (triggerUpdateError) {
        throw new Error(`warbird_triggers_15m gate update failed: ${triggerUpdateError.message}`);
      }
    }

    if (triggerEligible && forecastGate.allow) {
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
      }
    }

    const outcomeRows = setupId ? 5 : 3;
    const partialReason = triggerEligible && !forecastGate.allow
      ? `forecast_gate_failed: ${forecastGate.reasons.join("; ")}`
      : undefined;

    await writeJobLog(supabase, {
      job_name: "detect-setups",
      status: partialReason ? "PARTIAL" : "SUCCESS",
      rows_affected: outcomeRows,
      duration_ms: Date.now() - startTime,
      error_message: partialReason,
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
      forecast_gate: {
        allow: forecastGate.allow,
        reasons: forecastGate.reasons,
        metrics: forecastGate.metrics,
        thresholds: forecastGate.thresholds,
      },
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
