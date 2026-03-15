-- Migration 006: News, events, calendar, GPR, Trump Effect

create table econ_news_1d (
  id          bigint generated always as identity primary key,
  ts          timestamptz not null,
  headline    text        not null,
  source      text        not null,
  summary     text,
  sentiment   text,
  relevance_score numeric,
  created_at  timestamptz not null default now()
);

create table policy_news_1d (
  id          bigint generated always as identity primary key,
  ts          timestamptz not null,
  title       text        not null,
  source      text        not null,
  category    text,
  summary     text,
  market_impact text,
  created_at  timestamptz not null default now()
);

create table macro_reports_1d (
  id          bigint generated always as identity primary key,
  ts          timestamptz not null,
  report_type report_category not null,
  actual      numeric,
  forecast    numeric,
  previous    numeric,
  surprise    numeric,
  created_at  timestamptz not null default now()
);

create table econ_calendar (
  id          bigint generated always as identity primary key,
  ts          timestamptz not null,
  event_name  text        not null,
  category    report_category,
  forecast    numeric,
  actual      numeric,
  previous    numeric,
  importance  smallint    not null default 1,
  created_at  timestamptz not null default now()
);

create table news_signals (
  id          bigint generated always as identity primary key,
  ts          timestamptz not null,
  signal_type text        not null,
  direction   signal_direction,
  confidence  numeric,
  source_headline text,
  created_at  timestamptz not null default now()
);

create table geopolitical_risk_1d (
  ts          timestamptz not null,
  gpr_daily   numeric     not null,
  gpr_threats numeric,
  gpr_acts    numeric,
  country     text,
  created_at  timestamptz not null default now(),
  primary key (ts)
);

create table trump_effect_1d (
  id          bigint generated always as identity primary key,
  ts          timestamptz not null,
  event_type  text        not null,
  title       text        not null,
  summary     text,
  market_impact text,
  sector      text,
  source      text        not null,
  source_url  text,
  created_at  timestamptz not null default now()
);

-- Indexes
create index idx_econ_news_ts on econ_news_1d (ts desc);
create index idx_policy_news_ts on policy_news_1d (ts desc);
create index idx_macro_reports_ts on macro_reports_1d (ts desc);
create index idx_macro_reports_type on macro_reports_1d (report_type);
create index idx_econ_calendar_ts on econ_calendar (ts desc);
create index idx_econ_calendar_cat on econ_calendar (category);
create index idx_news_signals_ts on news_signals (ts desc);
create index idx_gpr_ts on geopolitical_risk_1d (ts desc);
create index idx_trump_effect_ts on trump_effect_1d (ts desc);
create index idx_trump_effect_type on trump_effect_1d (event_type);
