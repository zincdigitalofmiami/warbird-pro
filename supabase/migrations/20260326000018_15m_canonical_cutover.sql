-- Migration 018: make Warbird execution tables 15m-canonical, preserve legacy rows via backup copies,
-- and remove dormant legacy surfaces.

begin;

drop table if exists mes_1s;
drop table if exists options_ohlcv_1d;

do $$
begin
  if to_regclass('public.warbird_setup_events') is not null
     and to_regclass('public.warbird_setup_events_legacy_20260326') is null then
    execute 'create table public.warbird_setup_events_legacy_20260326 as table public.warbird_setup_events';
  end if;

  if to_regclass('public.warbird_setups') is not null
     and to_regclass('public.warbird_setups_legacy_20260326') is null then
    execute 'create table public.warbird_setups_legacy_20260326 as table public.warbird_setups';
  end if;

  if to_regclass('public.warbird_conviction') is not null
     and to_regclass('public.warbird_conviction_legacy_20260326') is null then
    execute 'create table public.warbird_conviction_legacy_20260326 as table public.warbird_conviction';
  end if;

  if to_regclass('public.warbird_risk') is not null
     and to_regclass('public.warbird_risk_legacy_20260326') is null then
    execute 'create table public.warbird_risk_legacy_20260326 as table public.warbird_risk';
  end if;

  if to_regclass('public.warbird_triggers_15m') is not null
     and to_regclass('public.warbird_triggers_15m_legacy_20260326') is null then
    execute 'create table public.warbird_triggers_15m_legacy_20260326 as table public.warbird_triggers_15m';
  end if;

  if to_regclass('public.warbird_forecasts_1h') is not null
     and to_regclass('public.warbird_forecasts_1h_legacy_20260326') is null then
    execute 'create table public.warbird_forecasts_1h_legacy_20260326 as table public.warbird_forecasts_1h';
  end if;
end $$;

drop table if exists warbird_setup_events;
drop table if exists warbird_setups;
drop table if exists warbird_conviction;
drop table if exists warbird_risk;
drop table if exists warbird_triggers_15m;
drop table if exists warbird_forecasts_1h;

create table warbird_triggers_15m (
  id                    bigint generated always as identity primary key,
  bar_close_ts          timestamptz not null,
  timeframe             timeframe not null default 'M15',
  symbol_code           text not null default 'MES' references symbols(code),
  direction             signal_direction not null,
  decision              warbird_trigger_decision not null,
  fib_level             numeric,
  fib_ratio             numeric,
  entry_price           numeric,
  stop_loss             numeric,
  tp1                   numeric,
  tp2                   numeric,
  candle_confirmed      boolean not null default false,
  volume_confirmation   boolean not null default false,
  volume_ratio          numeric,
  stoch_rsi             numeric,
  correlation_score     numeric,
  trigger_quality_ratio numeric,
  no_trade_reason       text,
  created_at            timestamptz not null default now(),
  unique (symbol_code, timeframe, bar_close_ts)
);

create table warbird_conviction (
  id               bigint generated always as identity primary key,
  bar_close_ts     timestamptz not null,
  timeframe        timeframe not null default 'M15',
  trigger_id       bigint not null unique references warbird_triggers_15m(id) on delete cascade,
  symbol_code      text not null default 'MES' references symbols(code),
  level            warbird_conviction_level not null,
  counter_trend    boolean not null default false,
  all_layers_agree boolean not null default false,
  daily_bias       warbird_bias not null,
  bias_4h          warbird_bias not null,
  bias_15m         warbird_bias not null,
  trigger_decision warbird_trigger_decision not null,
  created_at       timestamptz not null default now(),
  unique (symbol_code, timeframe, bar_close_ts)
);

create table warbird_setups (
  id                    bigint generated always as identity primary key,
  setup_key             text not null unique,
  bar_close_ts          timestamptz not null,
  timeframe             timeframe not null default 'M15',
  symbol_code           text not null default 'MES' references symbols(code),
  trigger_id            bigint not null unique references warbird_triggers_15m(id) on delete cascade,
  conviction_id         bigint not null unique references warbird_conviction(id) on delete cascade,
  direction             signal_direction not null,
  status                warbird_setup_status not null default 'ACTIVE',
  conviction_level      warbird_conviction_level not null,
  counter_trend         boolean not null default false,
  fib_level             numeric,
  fib_ratio             numeric,
  entry_price           numeric not null,
  stop_loss             numeric not null,
  tp1                   numeric not null,
  tp2                   numeric not null,
  volume_confirmation   boolean not null default false,
  volume_ratio          numeric,
  trigger_quality_ratio numeric,
  current_event         warbird_setup_event_type not null default 'TRIGGERED',
  trigger_bar_ts        timestamptz not null,
  tp1_hit_at            timestamptz,
  tp2_hit_at            timestamptz,
  stopped_at            timestamptz,
  expires_at            timestamptz,
  notes                 text,
  created_at            timestamptz not null default now(),
  updated_at            timestamptz not null default now(),
  unique (symbol_code, timeframe, bar_close_ts)
);

create trigger trg_warbird_setups_updated_at
  before update on warbird_setups
  for each row execute function update_updated_at();

create table warbird_setup_events (
  id          bigint generated always as identity primary key,
  setup_id    bigint not null references warbird_setups(id) on delete cascade,
  ts          timestamptz not null,
  event_type  warbird_setup_event_type not null,
  price       numeric,
  note        text,
  metadata    jsonb not null default '{}'::jsonb,
  created_at  timestamptz not null default now()
);

create table warbird_risk (
  id                    bigint generated always as identity primary key,
  bar_close_ts          timestamptz not null,
  timeframe             timeframe not null default 'M15',
  symbol_code           text not null default 'MES' references symbols(code),
  tp1_probability       numeric,
  tp2_probability       numeric,
  reversal_risk         numeric,
  confidence_score      numeric,
  garch_sigma           numeric,
  garch_vol_ratio       numeric,
  zone_1_upper          numeric,
  zone_1_lower          numeric,
  zone_2_upper          numeric,
  zone_2_lower          numeric,
  gpr_level             numeric,
  trump_effect_active   boolean,
  vix_level             numeric,
  vix_percentile_20d    numeric,
  vix_percentile_regime numeric,
  vol_state_name        vol_state,
  regime_label          text not null default 'trump_2',
  days_into_regime      integer,
  created_at            timestamptz not null default now(),
  unique (symbol_code, timeframe, bar_close_ts)
);

do $$
begin
  if to_regclass('public.warbird_triggers_15m_legacy_20260326') is not null then
    insert into warbird_triggers_15m (
      id,
      bar_close_ts,
      timeframe,
      symbol_code,
      direction,
      decision,
      fib_level,
      fib_ratio,
      entry_price,
      stop_loss,
      tp1,
      tp2,
      candle_confirmed,
      volume_confirmation,
      volume_ratio,
      stoch_rsi,
      correlation_score,
      trigger_quality_ratio,
      no_trade_reason,
      created_at
    )
    overriding system value
    select
      legacy.id,
      legacy.ts,
      'M15'::timeframe,
      legacy.symbol_code,
      legacy.direction,
      legacy.decision,
      legacy.fib_level,
      legacy.fib_ratio,
      legacy.entry_price,
      legacy.stop_loss,
      legacy.tp1,
      legacy.tp2,
      legacy.candle_confirmed,
      legacy.volume_confirmation,
      legacy.volume_ratio,
      legacy.stoch_rsi,
      legacy.correlation_score,
      legacy.trigger_quality_ratio,
      legacy.no_trade_reason,
      legacy.created_at
    from public.warbird_triggers_15m_legacy_20260326 legacy
    order by legacy.id;
  end if;

  if to_regclass('public.warbird_conviction_legacy_20260326') is not null then
    insert into warbird_conviction (
      id,
      bar_close_ts,
      timeframe,
      trigger_id,
      symbol_code,
      level,
      counter_trend,
      all_layers_agree,
      daily_bias,
      bias_4h,
      bias_15m,
      trigger_decision,
      created_at
    )
    overriding system value
    select
      legacy.id,
      legacy.ts,
      'M15'::timeframe,
      legacy.trigger_id,
      legacy.symbol_code,
      legacy.level,
      legacy.counter_trend,
      legacy.all_layers_agree,
      legacy.daily_bias,
      legacy.bias_4h,
      case
        when trigger_legacy.direction = 'LONG' then 'BULL'::warbird_bias
        when trigger_legacy.direction = 'SHORT' then 'BEAR'::warbird_bias
        else legacy.bias_1h
      end,
      legacy.trigger_decision,
      legacy.created_at
    from public.warbird_conviction_legacy_20260326 legacy
    left join public.warbird_triggers_15m_legacy_20260326 trigger_legacy
      on trigger_legacy.id = legacy.trigger_id
    order by legacy.id;
  end if;

  if to_regclass('public.warbird_setups_legacy_20260326') is not null then
    insert into warbird_setups (
      id,
      setup_key,
      bar_close_ts,
      timeframe,
      symbol_code,
      trigger_id,
      conviction_id,
      direction,
      status,
      conviction_level,
      counter_trend,
      fib_level,
      fib_ratio,
      entry_price,
      stop_loss,
      tp1,
      tp2,
      volume_confirmation,
      volume_ratio,
      trigger_quality_ratio,
      current_event,
      trigger_bar_ts,
      tp1_hit_at,
      tp2_hit_at,
      stopped_at,
      expires_at,
      notes,
      created_at,
      updated_at
    )
    overriding system value
    select
      legacy.id,
      legacy.setup_key,
      legacy.ts,
      'M15'::timeframe,
      legacy.symbol_code,
      legacy.trigger_id,
      legacy.conviction_id,
      legacy.direction,
      legacy.status,
      legacy.conviction_level,
      legacy.counter_trend,
      legacy.fib_level,
      legacy.fib_ratio,
      legacy.entry_price,
      legacy.stop_loss,
      legacy.tp1,
      legacy.tp2,
      legacy.volume_confirmation,
      legacy.volume_ratio,
      legacy.trigger_quality_ratio,
      legacy.current_event,
      legacy.trigger_bar_ts,
      legacy.tp1_hit_at,
      legacy.tp2_hit_at,
      legacy.stopped_at,
      legacy.expires_at,
      legacy.notes,
      legacy.created_at,
      legacy.updated_at
    from public.warbird_setups_legacy_20260326 legacy
    order by legacy.id;
  end if;

  if to_regclass('public.warbird_setup_events_legacy_20260326') is not null then
    insert into warbird_setup_events (
      id,
      setup_id,
      ts,
      event_type,
      price,
      note,
      metadata,
      created_at
    )
    overriding system value
    select
      legacy.id,
      legacy.setup_id,
      legacy.ts,
      legacy.event_type,
      legacy.price,
      legacy.note,
      legacy.metadata,
      legacy.created_at
    from public.warbird_setup_events_legacy_20260326 legacy
    order by legacy.id;
  end if;

  if to_regclass('public.warbird_risk_legacy_20260326') is not null then
    if to_regclass('public.warbird_forecasts_1h_legacy_20260326') is not null then
      insert into warbird_risk (
        id,
        bar_close_ts,
        timeframe,
        symbol_code,
        tp1_probability,
        tp2_probability,
        reversal_risk,
        confidence_score,
        garch_sigma,
        garch_vol_ratio,
        zone_1_upper,
        zone_1_lower,
        zone_2_upper,
        zone_2_lower,
        gpr_level,
        trump_effect_active,
        vix_level,
        vix_percentile_20d,
        vix_percentile_regime,
        vol_state_name,
        regime_label,
        days_into_regime,
        created_at
      )
      overriding system value
      select
        legacy.id,
        legacy.ts,
        'M15'::timeframe,
        legacy.symbol_code,
        null,
        null,
        null,
        forecast_legacy.confidence,
        legacy.garch_sigma,
        legacy.garch_vol_ratio,
        legacy.zone_1_upper,
        legacy.zone_1_lower,
        legacy.zone_2_upper,
        legacy.zone_2_lower,
        legacy.gpr_level,
        legacy.trump_effect_active,
        legacy.vix_level,
        legacy.vix_percentile_20d,
        legacy.vix_percentile_regime,
        legacy.vol_state_name,
        legacy.regime_label,
        legacy.days_into_regime,
        legacy.created_at
      from public.warbird_risk_legacy_20260326 legacy
      left join public.warbird_forecasts_1h_legacy_20260326 forecast_legacy
        on forecast_legacy.id = legacy.forecast_id
      order by legacy.id;
    else
      insert into warbird_risk (
        id,
        bar_close_ts,
        timeframe,
        symbol_code,
        tp1_probability,
        tp2_probability,
        reversal_risk,
        confidence_score,
        garch_sigma,
        garch_vol_ratio,
        zone_1_upper,
        zone_1_lower,
        zone_2_upper,
        zone_2_lower,
        gpr_level,
        trump_effect_active,
        vix_level,
        vix_percentile_20d,
        vix_percentile_regime,
        vol_state_name,
        regime_label,
        days_into_regime,
        created_at
      )
      overriding system value
      select
        legacy.id,
        legacy.ts,
        'M15'::timeframe,
        legacy.symbol_code,
        null,
        null,
        null,
        null,
        legacy.garch_sigma,
        legacy.garch_vol_ratio,
        legacy.zone_1_upper,
        legacy.zone_1_lower,
        legacy.zone_2_upper,
        legacy.zone_2_lower,
        legacy.gpr_level,
        legacy.trump_effect_active,
        legacy.vix_level,
        legacy.vix_percentile_20d,
        legacy.vix_percentile_regime,
        legacy.vol_state_name,
        legacy.regime_label,
        legacy.days_into_regime,
        legacy.created_at
      from public.warbird_risk_legacy_20260326 legacy
      order by legacy.id;
    end if;
  end if;
end $$;

select setval(
  pg_get_serial_sequence('warbird_triggers_15m', 'id'),
  coalesce((select max(id) from warbird_triggers_15m), 0) + 1,
  false
);

select setval(
  pg_get_serial_sequence('warbird_conviction', 'id'),
  coalesce((select max(id) from warbird_conviction), 0) + 1,
  false
);

select setval(
  pg_get_serial_sequence('warbird_setups', 'id'),
  coalesce((select max(id) from warbird_setups), 0) + 1,
  false
);

select setval(
  pg_get_serial_sequence('warbird_setup_events', 'id'),
  coalesce((select max(id) from warbird_setup_events), 0) + 1,
  false
);

select setval(
  pg_get_serial_sequence('warbird_risk', 'id'),
  coalesce((select max(id) from warbird_risk), 0) + 1,
  false
);

create index idx_warbird_triggers_15m_symbol_bar_close
  on warbird_triggers_15m (symbol_code, timeframe, bar_close_ts desc);
create index idx_warbird_triggers_15m_decision_bar_close
  on warbird_triggers_15m (decision, bar_close_ts desc);
create index idx_warbird_conviction_symbol_bar_close
  on warbird_conviction (symbol_code, timeframe, bar_close_ts desc);
create index idx_warbird_conviction_level_bar_close
  on warbird_conviction (level, bar_close_ts desc);
create index idx_warbird_setups_symbol_bar_close
  on warbird_setups (symbol_code, timeframe, bar_close_ts desc);
create index idx_warbird_setups_status_bar_close
  on warbird_setups (status, bar_close_ts desc);
create index idx_warbird_setup_events_setup_ts
  on warbird_setup_events (setup_id, ts desc);
create index idx_warbird_setup_events_type_ts
  on warbird_setup_events (event_type, ts desc);
create index idx_warbird_risk_symbol_bar_close
  on warbird_risk (symbol_code, timeframe, bar_close_ts desc);

alter table warbird_triggers_15m enable row level security;
create policy "Authenticated read warbird_triggers_15m"
  on warbird_triggers_15m for select to authenticated using (true);

alter table warbird_conviction enable row level security;
create policy "Authenticated read warbird_conviction"
  on warbird_conviction for select to authenticated using (true);

alter table warbird_setups enable row level security;
create policy "Authenticated read warbird_setups"
  on warbird_setups for select to authenticated using (true);

alter table warbird_setup_events enable row level security;
create policy "Authenticated read warbird_setup_events"
  on warbird_setup_events for select to authenticated using (true);

alter table warbird_risk enable row level security;
create policy "Authenticated read warbird_risk"
  on warbird_risk for select to authenticated using (true);

do $$
begin
  if not exists (
    select 1
    from pg_publication_tables
    where pubname = 'supabase_realtime'
      and schemaname = 'public'
      and tablename = 'warbird_setups'
  ) then
    execute 'alter publication supabase_realtime add table warbird_setups';
  end if;
end $$;

commit;
