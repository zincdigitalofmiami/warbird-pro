import type { SupabaseClient } from "@supabase/supabase-js";
import type {
  WarbirdConvictionRow,
  WarbirdDailyBiasRow,
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
  const [dailyResult, structureResult, triggerResult] = await Promise.all([
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
    supabase
      .from("warbird_triggers_15m")
      .select("*")
      .eq("symbol_code", symbolCode)
      .order("bar_close_ts", { ascending: false })
      .limit(1)
      .returns<WarbirdTriggerRow>()
      .maybeSingle(),
  ]);

  const trigger = (triggerResult.data as WarbirdTriggerRow | null) ?? null;

  let conviction: WarbirdConvictionRow | null = null;
  let risk: WarbirdRiskRow | null = null;
  let setup: WarbirdSetupRow | null = null;

  if (trigger) {
    const [convictionResult, riskResult, setupResult] = await Promise.all([
      supabase
        .from("warbird_conviction")
        .select("*")
        .eq("trigger_id", trigger.id)
        .limit(1)
        .returns<WarbirdConvictionRow>()
        .maybeSingle(),
      supabase
        .from("warbird_risk")
        .select("*")
        .eq("symbol_code", symbolCode)
        .eq("bar_close_ts", trigger.bar_close_ts)
        .eq("timeframe", "M15")
        .limit(1)
        .returns<WarbirdRiskRow>()
        .maybeSingle(),
      supabase
        .from("warbird_setups")
        .select("*")
        .eq("trigger_id", trigger.id)
        .limit(1)
        .returns<WarbirdSetupRow>()
        .maybeSingle(),
    ]);

    conviction = (convictionResult.data as WarbirdConvictionRow | null) ?? null;
    risk = (riskResult.data as WarbirdRiskRow | null) ?? null;
    setup = (setupResult.data as WarbirdSetupRow | null) ?? null;
  }

  return {
    daily: (dailyResult.data as WarbirdDailyBiasRow | null) ?? null,
    structure: (structureResult.data as WarbirdStructure4HRow | null) ?? null,
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
  return fetchWarbirdSetupHistory(supabase, {
    symbolCode,
    days,
    limit,
  });
}

export async function fetchWarbirdSetupHistory(
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
    .gte("bar_close_ts", since)
    .order("bar_close_ts", { ascending: false })
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

  return {
    setups,
    events,
  };
}
