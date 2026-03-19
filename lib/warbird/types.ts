export type WarbirdBias = "BULL" | "BEAR" | "NEUTRAL";
export type WarbirdDirection = "LONG" | "SHORT";
export type WarbirdTriggerDecision = "GO" | "WAIT" | "NO_GO";
export type WarbirdConvictionLevel =
  | "MAXIMUM"
  | "HIGH"
  | "MODERATE"
  | "LOW"
  | "NO_TRADE";
export type WarbirdSetupStatus =
  | "ACTIVE"
  | "TP1_HIT"
  | "TP2_HIT"
  | "STOPPED"
  | "EXPIRED";
export type WarbirdSetupEventType =
  | "TRIGGERED"
  | "TP1_HIT"
  | "TP2_HIT"
  | "STOPPED"
  | "EXPIRED";

export interface WarbirdDailyBiasRow {
  ts: string;
  symbol_code: string;
  bias: WarbirdBias;
  close_price: number;
  ma_200: number | null;
  price_vs_200d_ma: number | null;
  distance_pct: number | null;
  slope_200d_ma: number | null;
  sessions_on_side: number | null;
  daily_return: number | null;
  daily_range_vs_avg: number | null;
}

export interface WarbirdStructure4HRow {
  ts: string;
  symbol_code: string;
  bias_4h: WarbirdBias;
  agrees_with_daily: boolean;
  trend_score: number | null;
  swing_high: number | null;
  swing_low: number | null;
  structural_note: string | null;
}

export interface WarbirdForecastRow {
  id: number;
  ts: string;
  symbol_code: string;
  bias_1h: WarbirdBias;
  target_price_1h: number;
  target_price_4h: number;
  target_mae_1h: number;
  target_mae_4h: number;
  target_mfe_1h: number;
  target_mfe_4h: number;
  prob_hit_sl_first: number | null;
  prob_hit_pt1_first: number | null;
  prob_hit_pt2_after_pt1: number | null;
  expected_max_extension: number | null;
  setup_score: number | null;
  confidence: number | null;
  mfe_mae_ratio_1h: number | null;
  current_price: number | null;
  model_version: string | null;
  feature_snapshot: Record<string, unknown> | null;
  created_at?: string;
}

export interface WarbirdTriggerRow {
  id: number;
  ts: string;
  forecast_id: number;
  symbol_code: string;
  direction: WarbirdDirection;
  decision: WarbirdTriggerDecision;
  fib_level: number | null;
  fib_ratio: number | null;
  entry_price: number | null;
  stop_loss: number | null;
  tp1: number | null;
  tp2: number | null;
  candle_confirmed: boolean;
  volume_confirmation: boolean;
  volume_ratio: number | null;
  stoch_rsi: number | null;
  correlation_score: number | null;
  trigger_quality_ratio: number | null;
  no_trade_reason: string | null;
}

export interface WarbirdConvictionRow {
  id: number;
  ts: string;
  forecast_id: number;
  trigger_id: number | null;
  symbol_code: string;
  level: WarbirdConvictionLevel;
  counter_trend: boolean;
  all_layers_agree: boolean;
  daily_bias: WarbirdBias;
  bias_4h: WarbirdBias;
  bias_1h: WarbirdBias;
  trigger_decision: WarbirdTriggerDecision;
}

export interface WarbirdRiskRow {
  id: number;
  ts: string;
  forecast_id: number;
  symbol_code: string;
  garch_sigma: number | null;
  garch_vol_ratio: number | null;
  zone_1_upper: number | null;
  zone_1_lower: number | null;
  zone_2_upper: number | null;
  zone_2_lower: number | null;
  gpr_level: number | null;
  trump_effect_active: boolean | null;
  vix_level: number | null;
  vix_percentile_20d: number | null;
  vix_percentile_regime: number | null;
  vol_state_name: string | null;
  regime_label: string;
  days_into_regime: number | null;
}

export interface WarbirdSetupRow {
  id: number;
  setup_key: string;
  ts: string;
  symbol_code: string;
  forecast_id: number;
  trigger_id: number;
  conviction_id: number;
  direction: WarbirdDirection;
  status: WarbirdSetupStatus;
  conviction_level: WarbirdConvictionLevel;
  counter_trend: boolean;
  fib_level: number | null;
  fib_ratio: number | null;
  entry_price: number;
  stop_loss: number;
  tp1: number;
  tp2: number;
  volume_confirmation: boolean;
  volume_ratio: number | null;
  trigger_quality_ratio: number | null;
  current_event: WarbirdSetupEventType;
  trigger_bar_ts: string;
  tp1_hit_at: string | null;
  tp2_hit_at: string | null;
  stopped_at: string | null;
  expires_at: string | null;
  notes: string | null;
  created_at: string;
  updated_at: string;
}

export interface WarbirdSetupEventRow {
  id: number;
  setup_id: number;
  ts: string;
  event_type: WarbirdSetupEventType;
  price: number | null;
  note: string | null;
  metadata: Record<string, unknown> | null;
  created_at: string;
}

export interface WarbirdSignal {
  version: string;
  generatedAt: string;
  symbol: string;
  daily: {
    bias: WarbirdBias;
    price_vs_200d_ma: number | null;
    distance_pct: number | null;
    slope_200d_ma: number | null;
  };
  structure: {
    bias_4h: WarbirdBias;
    agrees_with_daily: boolean;
  };
  directional: {
    bias_1h: WarbirdBias;
    price_target_1h: number | null;
    price_target_4h: number | null;
    mae_band_1h: number | null;
    mae_band_4h: number | null;
    mfe_band_1h: number | null;
    mfe_band_4h: number | null;
    prob_hit_sl_first: number | null;
    prob_hit_pt1_first: number | null;
    prob_hit_pt2_after_pt1: number | null;
    expected_max_extension: number | null;
    setup_score: number | null;
    confidence: number | null;
  };
  conviction: {
    level: WarbirdConvictionLevel;
    counter_trend: boolean;
    all_layers_agree: boolean;
  };
  setup?: {
    id: number;
    direction: WarbirdDirection;
    status: WarbirdSetupStatus;
    fibLevel: number | null;
    fibRatio: number | null;
    entry: number | null;
    stopLoss: number | null;
    tp1: number | null;
    tp2: number | null;
    volume_confirmation: boolean;
    trigger_quality_ratio: number | null;
  };
  risk: {
    garch_vol_forecast: number | null;
    garch_vol_ratio: number | null;
    gpr_level: number | null;
    trump_effect_active: boolean | null;
    vix_level: number | null;
    vix_percentile_20d: number | null;
    vix_percentile_regime: number | null;
    regime: string | null;
    days_into_regime: number | null;
  };
  zones?: {
    zone_1_upper: number | null;
    zone_1_lower: number | null;
    zone_2_upper: number | null;
    zone_2_lower: number | null;
  };
  feedback: {
    win_rate_last20: number | null;
    current_streak: number | null;
    avg_r_recent: number | null;
    setup_frequency_7d: number | null;
  };
}

export interface WarbirdSignalResponse {
  signal: WarbirdSignal | null;
  forecast: WarbirdForecastRow | null;
  setup: WarbirdSetupRow | null;
  trigger: WarbirdTriggerRow | null;
  conviction: WarbirdConvictionRow | null;
  risk: WarbirdRiskRow | null;
}
