import type { SupabaseClient } from "@supabase/supabase-js";
import type {
  WarbirdConvictionRow,
  WarbirdDailyBiasRow,
  WarbirdForecastRow,
  WarbirdRiskRow,
  WarbirdSetupEventRow,
  WarbirdSetupRow,
  WarbirdStructure4HRow,
  WarbirdTriggerRow,
} from "@/lib/warbird/types";

export async function fetchLatestWarbirdState(
  supabase: SupabaseClient,
  symbolCode: string = "MES",
) {
  const forecastResult = await supabase
    .from("warbird_forecasts_1h")
    .select("*")
    .eq("symbol_code", symbolCode)
    .order("ts", { ascending: false })
    .limit(1)
    .returns<WarbirdForecastRow>()
    .maybeSingle();
  const forecast = (forecastResult.data as WarbirdForecastRow | null) ?? null;

  const [dailyResult, structureResult] = await Promise.all([
    supabase
      .from("warbird_daily_bias")
      .select("*")
      .eq("symbol_code", symbolCode)
      .order("ts", { ascending: false })
      .limit(1)
      .returns<WarbirdDailyBiasRow>()
      .maybeSingle(),
    supabase
      .from("warbird_structure_4h")
      .select("*")
      .eq("symbol_code", symbolCode)
      .order("ts", { ascending: false })
      .limit(1)
      .returns<WarbirdStructure4HRow>()
      .maybeSingle(),
  ]);

  let trigger: WarbirdTriggerRow | null = null;
  let conviction: WarbirdConvictionRow | null = null;
  let risk: WarbirdRiskRow | null = null;
  let setup: WarbirdSetupRow | null = null;

  if (forecast) {
    const [triggerResult, convictionResult, riskResult, setupResult] = await Promise.all([
      supabase
        .from("warbird_triggers_15m")
        .select("*")
        .eq("forecast_id", forecast.id)
        .order("ts", { ascending: false })
        .limit(1)
        .returns<WarbirdTriggerRow>()
        .maybeSingle(),
      supabase
        .from("warbird_conviction")
        .select("*")
        .eq("forecast_id", forecast.id)
        .limit(1)
        .returns<WarbirdConvictionRow>()
        .maybeSingle(),
      supabase
        .from("warbird_risk")
        .select("*")
        .eq("forecast_id", forecast.id)
        .limit(1)
        .returns<WarbirdRiskRow>()
        .maybeSingle(),
      supabase
        .from("warbird_setups")
        .select("*")
        .eq("forecast_id", forecast.id)
        .order("ts", { ascending: false })
        .limit(1)
        .returns<WarbirdSetupRow>()
        .maybeSingle(),
    ]);

    trigger = (triggerResult.data as WarbirdTriggerRow | null) ?? null;
    conviction = (convictionResult.data as WarbirdConvictionRow | null) ?? null;
    risk = (riskResult.data as WarbirdRiskRow | null) ?? null;
    setup = (setupResult.data as WarbirdSetupRow | null) ?? null;
  }

  return {
    daily: (dailyResult.data as WarbirdDailyBiasRow | null) ?? null,
    structure: (structureResult.data as WarbirdStructure4HRow | null) ?? null,
    forecast: forecast ?? null,
    trigger,
    conviction,
    risk,
    setup,
  };
}

export async function fetchWarbirdHistory(
  supabase: SupabaseClient,
  {
    symbolCode = "MES",
    days = 7,
    limit = 50,
  }: {
    symbolCode?: string;
    days?: number;
    limit?: number;
  } = {},
) {
  const since = new Date(Date.now() - days * 24 * 60 * 60 * 1000).toISOString();

  const setupsResult = await supabase
    .from("warbird_setups")
    .select("*")
    .eq("symbol_code", symbolCode)
    .gte("ts", since)
    .order("ts", { ascending: false })
    .limit(limit)
    .returns<WarbirdSetupRow[]>();
  const setups = (setupsResult.data as WarbirdSetupRow[] | null) ?? [];

  const setupIds = setups.map((setup) => setup.id);
  let events: WarbirdSetupEventRow[] = [];

  if (setupIds.length > 0) {
    const { data } = await supabase
      .from("warbird_setup_events")
      .select("*")
      .in("setup_id", setupIds)
      .order("ts", { ascending: false })
      .returns<WarbirdSetupEventRow[]>();
    events = (data as WarbirdSetupEventRow[] | null) ?? [];
  }

  const forecastsResult = await supabase
    .from("warbird_forecasts_1h")
    .select("*")
    .eq("symbol_code", symbolCode)
    .gte("ts", since)
    .order("ts", { ascending: false })
    .limit(limit)
    .returns<WarbirdForecastRow[]>();
  const forecasts = (forecastsResult.data as WarbirdForecastRow[] | null) ?? [];

  return {
    setups,
    events,
    forecasts,
  };
}
