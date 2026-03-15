-- Migration 007: Trading engine, model registry, operations
-- Covers all 3 prongs: model outputs, app state, Pine Script API

-- Warbird setup state machine (Touch -> Hook -> Go -> TP/SL)
create table warbird_setups (
  id              bigint generated always as identity primary key,
  ts              timestamptz     not null,
  symbol_code     text            not null default 'MES' references symbols(code),
  timeframe       timeframe       not null default 'M15',
  direction       signal_direction not null,
  phase           setup_phase     not null default 'TOUCHED',
  entry_price     numeric,
  stop_loss       numeric,
  tp1             numeric,
  tp2             numeric,
  confidence      numeric,
  pivot_level     numeric,
  pivot_type      text,
  measured_move_target numeric,
  expires_at      timestamptz,
  created_at      timestamptz     not null default now(),
  updated_at      timestamptz     not null default now()
);

create trigger trg_warbird_setups_updated_at
  before update on warbird_setups
  for each row execute function update_updated_at();

-- Model prediction scores (12 models: 3 targets x 4 horizons)
create table trade_scores (
  id                  bigint generated always as identity primary key,
  ts                  timestamptz not null,
  symbol_code         text        not null default 'MES' references symbols(code),
  horizon             text        not null,
  predicted_price     numeric,
  predicted_mae       numeric,
  predicted_mfe       numeric,
  actual_price        numeric,
  actual_mae          numeric,
  actual_mfe          numeric,
  model_version       text,
  confidence          numeric,
  direction_correct   boolean,
  created_at          timestamptz not null default now()
);

-- Measured move detection
create table measured_moves (
  id                bigint generated always as identity primary key,
  ts                timestamptz     not null,
  symbol_code       text            not null default 'MES' references symbols(code),
  direction         signal_direction not null,
  anchor_price      numeric         not null,
  target_price      numeric         not null,
  retracement_price numeric,
  fib_level         numeric,
  status            signal_status   not null default 'ACTIVE',
  created_at        timestamptz     not null default now()
);

-- GARCH volatility state output (5 states, MC distributions)
create table vol_states (
  id              bigint generated always as identity primary key,
  ts              timestamptz not null,
  symbol_code     text        not null default 'MES' references symbols(code),
  state           vol_state   not null,
  conditional_vol numeric     not null,
  garch_alpha     numeric,
  garch_beta      numeric,
  garch_gamma     numeric,
  mc_median       numeric,
  mc_5th          numeric,
  mc_95th         numeric,
  created_at      timestamptz not null default now()
);

-- Forecasts: what the Pine Script indicator and dashboard consume via API
create table forecasts (
  id              bigint generated always as identity primary key,
  ts              timestamptz     not null,
  symbol_code     text            not null default 'MES' references symbols(code),
  horizon         text            not null,
  predicted_price numeric         not null,
  predicted_mae   numeric,
  predicted_mfe   numeric,
  target_zone_low numeric,
  target_zone_high numeric,
  vol_state_name  vol_state,
  confidence      numeric,
  direction       signal_direction,
  model_version   text,
  created_at      timestamptz     not null default now()
);

-- Data source registry
create table sources (
  id          serial      primary key,
  name        text        not null unique,
  description text,
  base_url    text,
  api_key_env text,
  is_active   boolean     not null default true,
  created_at  timestamptz not null default now()
);

-- Coverage audit log
create table coverage_log (
  id          bigint generated always as identity primary key,
  checked_at  timestamptz not null default now(),
  table_name  text        not null,
  symbol_code text,
  latest_ts   timestamptz,
  gap_count   integer     not null default 0,
  status      ingestion_status not null,
  created_at  timestamptz not null default now()
);

-- Cron job execution log
create table job_log (
  id            bigint generated always as identity primary key,
  job_name      text            not null,
  started_at    timestamptz     not null default now(),
  finished_at   timestamptz,
  status        ingestion_status not null default 'SUCCESS',
  rows_affected integer         not null default 0,
  error_message text,
  duration_ms   integer,
  created_at    timestamptz     not null default now()
);

-- Model registry
create table models (
  id                   serial      primary key,
  name                 text        not null,
  symbol_code          text        not null default 'MES' references symbols(code),
  horizon              text        not null,
  target_type          text        not null,
  version              text        not null,
  rmse                 numeric,
  directional_accuracy numeric,
  calibration_method   text,
  feature_list         jsonb,
  fold_info            jsonb,
  is_active            boolean     not null default false,
  trained_at           timestamptz,
  created_at           timestamptz not null default now(),
  updated_at           timestamptz not null default now(),
  unique (name, version)
);

create trigger trg_models_updated_at
  before update on models
  for each row execute function update_updated_at();

-- Indexes
create index idx_warbird_setups_ts on warbird_setups (ts desc);
create index idx_warbird_setups_phase on warbird_setups (phase) where phase in ('TOUCHED', 'HOOKED', 'GO_FIRED');
create index idx_warbird_setups_symbol on warbird_setups (symbol_code, ts desc);
create index idx_trade_scores_ts on trade_scores (ts desc);
create index idx_trade_scores_horizon on trade_scores (symbol_code, horizon, ts desc);
create index idx_measured_moves_ts on measured_moves (ts desc);
create index idx_measured_moves_active on measured_moves (status) where status = 'ACTIVE';
create index idx_vol_states_ts on vol_states (symbol_code, ts desc);
create index idx_forecasts_ts on forecasts (ts desc);
create index idx_forecasts_symbol_horizon on forecasts (symbol_code, horizon, ts desc);
create index idx_job_log_name on job_log (job_name, started_at desc);
create index idx_job_log_status on job_log (status) where status != 'SUCCESS';
create index idx_coverage_log_table on coverage_log (table_name, checked_at desc);
create index idx_models_active on models (is_active) where is_active = true;
