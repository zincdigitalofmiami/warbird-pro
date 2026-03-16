-- Migration 010: Warbird v1 canonical cutover
-- Drops the legacy Touch/Hook/Go persistence and replaces it with the
-- normalized 8-table Warbird v1 model defined in WARBIRD_CANONICAL.md.

-- Remove legacy realtime entries if they still exist.
do $$
begin
  if exists (
    select 1
    from pg_publication_tables
    where pubname = 'supabase_realtime' and schemaname = 'public' and tablename = 'forecasts'
  ) then
    execute 'alter publication supabase_realtime drop table forecasts';
  end if;

  if exists (
    select 1
    from pg_publication_tables
    where pubname = 'supabase_realtime' and schemaname = 'public' and tablename = 'warbird_setups'
  ) then
    execute 'alter publication supabase_realtime drop table warbird_setups';
  end if;
end $$;

drop table if exists forecasts cascade;
drop table if exists warbird_setups cascade;

create type warbird_bias as enum (
  'BULL',
  'BEAR',
  'NEUTRAL'
);

create type warbird_trigger_decision as enum (
  'GO',
  'WAIT',
  'NO_GO'
);

create type warbird_conviction_level as enum (
  'MAXIMUM',
  'HIGH',
  'MODERATE',
  'LOW',
  'NO_TRADE'
);

create type warbird_setup_status as enum (
  'ACTIVE',
  'TP1_HIT',
  'TP2_HIT',
  'RUNNER_ACTIVE',
  'RUNNER_EXITED',
  'STOPPED',
  'EXPIRED',
  'PULLBACK_REVERSAL'
);

create type warbird_setup_event_type as enum (
  'TRIGGERED',
  'TP1_HIT',
  'TP2_HIT',
  'RUNNER_STARTED',
  'RUNNER_EXITED',
  'STOPPED',
  'EXPIRED',
  'PULLBACK_REVERSAL'
);

create table warbird_daily_bias (
  ts                     timestamptz primary key,
  symbol_code            text not null default 'MES' references symbols(code),
  bias                   warbird_bias not null,
  close_price            numeric not null,
  ma_200                 numeric,
  price_vs_200d_ma       numeric,
  distance_pct           numeric,
  slope_200d_ma          numeric,
  sessions_on_side       integer,
  daily_return           numeric,
  daily_range_vs_avg     numeric,
  created_at             timestamptz not null default now()
);

create table warbird_structure_4h (
  ts                     timestamptz primary key,
  symbol_code            text not null default 'MES' references symbols(code),
  bias_4h                warbird_bias not null,
  agrees_with_daily      boolean not null default false,
  trend_score            numeric,
  swing_high             numeric,
  swing_low              numeric,
  structural_note        text,
  created_at             timestamptz not null default now()
);

create table warbird_forecasts_1h (
  id                     bigint generated always as identity primary key,
  ts                     timestamptz not null,
  symbol_code            text not null default 'MES' references symbols(code),
  bias_1h                warbird_bias not null,
  target_price_1h        numeric not null,
  target_price_4h        numeric not null,
  target_mae_1h          numeric not null,
  target_mae_4h          numeric not null,
  target_mfe_1h          numeric not null,
  target_mfe_4h          numeric not null,
  confidence             numeric,
  mfe_mae_ratio_1h       numeric,
  runner_headroom_4h     numeric,
  current_price          numeric,
  model_version          text,
  feature_snapshot       jsonb not null default '{}'::jsonb,
  created_at             timestamptz not null default now(),
  unique (symbol_code, ts)
);

create table warbird_triggers_15m (
  id                     bigint generated always as identity primary key,
  ts                     timestamptz not null,
  forecast_id            bigint not null references warbird_forecasts_1h(id) on delete cascade,
  symbol_code            text not null default 'MES' references symbols(code),
  direction              signal_direction not null,
  decision               warbird_trigger_decision not null,
  fib_level              numeric,
  fib_ratio              numeric,
  entry_price            numeric,
  stop_loss              numeric,
  tp1                    numeric,
  tp2                    numeric,
  candle_confirmed       boolean not null default false,
  volume_confirmation    boolean not null default false,
  volume_ratio           numeric,
  stoch_rsi              numeric,
  correlation_score      numeric,
  trigger_quality_ratio  numeric,
  runner_headroom        numeric,
  no_trade_reason        text,
  created_at             timestamptz not null default now(),
  unique (symbol_code, ts, forecast_id)
);

create table warbird_conviction (
  id                     bigint generated always as identity primary key,
  ts                     timestamptz not null,
  forecast_id            bigint not null unique references warbird_forecasts_1h(id) on delete cascade,
  trigger_id             bigint unique references warbird_triggers_15m(id) on delete cascade,
  symbol_code            text not null default 'MES' references symbols(code),
  level                  warbird_conviction_level not null,
  counter_trend          boolean not null default false,
  all_layers_agree       boolean not null default false,
  runner_eligible        boolean not null default false,
  daily_bias             warbird_bias not null,
  bias_4h                warbird_bias not null,
  bias_1h                warbird_bias not null,
  trigger_decision       warbird_trigger_decision not null,
  created_at             timestamptz not null default now()
);

create table warbird_setups (
  id                     bigint generated always as identity primary key,
  setup_key              text not null unique,
  ts                     timestamptz not null,
  symbol_code            text not null default 'MES' references symbols(code),
  forecast_id            bigint not null references warbird_forecasts_1h(id) on delete cascade,
  trigger_id             bigint not null unique references warbird_triggers_15m(id) on delete cascade,
  conviction_id          bigint not null unique references warbird_conviction(id) on delete cascade,
  direction              signal_direction not null,
  status                 warbird_setup_status not null default 'ACTIVE',
  conviction_level       warbird_conviction_level not null,
  counter_trend          boolean not null default false,
  runner_eligible        boolean not null default false,
  fib_level              numeric,
  fib_ratio              numeric,
  entry_price            numeric not null,
  stop_loss              numeric not null,
  tp1                    numeric not null,
  tp2                    numeric not null,
  volume_confirmation    boolean not null default false,
  volume_ratio           numeric,
  trigger_quality_ratio  numeric,
  runner_headroom        numeric,
  current_event          warbird_setup_event_type not null default 'TRIGGERED',
  trigger_bar_ts         timestamptz not null,
  tp1_hit_at             timestamptz,
  tp2_hit_at             timestamptz,
  runner_started_at      timestamptz,
  runner_exited_at       timestamptz,
  stopped_at             timestamptz,
  expires_at             timestamptz,
  notes                  text,
  created_at             timestamptz not null default now(),
  updated_at             timestamptz not null default now()
);

create trigger trg_warbird_setups_updated_at
  before update on warbird_setups
  for each row execute function update_updated_at();

create table warbird_setup_events (
  id                     bigint generated always as identity primary key,
  setup_id               bigint not null references warbird_setups(id) on delete cascade,
  ts                     timestamptz not null,
  event_type             warbird_setup_event_type not null,
  price                  numeric,
  note                   text,
  metadata               jsonb not null default '{}'::jsonb,
  created_at             timestamptz not null default now()
);

create table warbird_risk (
  id                     bigint generated always as identity primary key,
  ts                     timestamptz not null,
  forecast_id            bigint not null unique references warbird_forecasts_1h(id) on delete cascade,
  symbol_code            text not null default 'MES' references symbols(code),
  garch_sigma            numeric,
  garch_vol_ratio        numeric,
  zone_1_upper           numeric,
  zone_1_lower           numeric,
  zone_2_upper           numeric,
  zone_2_lower           numeric,
  gpr_level              numeric,
  trump_effect_active    boolean,
  vix_level              numeric,
  vix_percentile_20d     numeric,
  vix_percentile_regime  numeric,
  vol_state_name         vol_state,
  regime_label           text not null default 'trump_2',
  days_into_regime       integer,
  created_at             timestamptz not null default now()
);

create index idx_warbird_daily_bias_symbol_ts on warbird_daily_bias (symbol_code, ts desc);
create index idx_warbird_structure_4h_symbol_ts on warbird_structure_4h (symbol_code, ts desc);
create index idx_warbird_forecasts_1h_symbol_ts on warbird_forecasts_1h (symbol_code, ts desc);
create index idx_warbird_forecasts_1h_bias on warbird_forecasts_1h (bias_1h, ts desc);
create index idx_warbird_triggers_15m_symbol_ts on warbird_triggers_15m (symbol_code, ts desc);
create index idx_warbird_triggers_15m_decision on warbird_triggers_15m (decision, ts desc);
create index idx_warbird_conviction_symbol_ts on warbird_conviction (symbol_code, ts desc);
create index idx_warbird_conviction_level on warbird_conviction (level, ts desc);
create index idx_warbird_setups_symbol_ts on warbird_setups (symbol_code, ts desc);
create index idx_warbird_setups_status on warbird_setups (status, ts desc);
create index idx_warbird_setup_events_setup_ts on warbird_setup_events (setup_id, ts desc);
create index idx_warbird_setup_events_type on warbird_setup_events (event_type, ts desc);
create index idx_warbird_risk_symbol_ts on warbird_risk (symbol_code, ts desc);

alter table warbird_daily_bias enable row level security;
create policy "Authenticated read warbird_daily_bias" on warbird_daily_bias for select to authenticated using (true);

alter table warbird_structure_4h enable row level security;
create policy "Authenticated read warbird_structure_4h" on warbird_structure_4h for select to authenticated using (true);

alter table warbird_forecasts_1h enable row level security;
create policy "Authenticated read warbird_forecasts_1h" on warbird_forecasts_1h for select to authenticated using (true);

alter table warbird_triggers_15m enable row level security;
create policy "Authenticated read warbird_triggers_15m" on warbird_triggers_15m for select to authenticated using (true);

alter table warbird_conviction enable row level security;
create policy "Authenticated read warbird_conviction" on warbird_conviction for select to authenticated using (true);

alter table warbird_setups enable row level security;
create policy "Authenticated read warbird_setups" on warbird_setups for select to authenticated using (true);

alter table warbird_setup_events enable row level security;
create policy "Authenticated read warbird_setup_events" on warbird_setup_events for select to authenticated using (true);

alter table warbird_risk enable row level security;
create policy "Authenticated read warbird_risk" on warbird_risk for select to authenticated using (true);

alter publication supabase_realtime add table warbird_forecasts_1h;
alter publication supabase_realtime add table warbird_conviction;
alter publication supabase_realtime add table warbird_setups;
alter publication supabase_realtime add table warbird_setup_events;
