-- Migration 005: Economic data tables
-- series_catalog: FRED series registry
-- 10 domain tables: one per econ_category

create table series_catalog (
  id           serial        primary key,
  series_id    text          not null unique,
  name         text          not null,
  description  text,
  category     econ_category not null,
  frequency    text          not null default 'daily',
  source_url   text,
  is_active    boolean       not null default true,
  created_at   timestamptz   not null default now()
);

create index idx_series_catalog_category on series_catalog (category);

-- All 10 econ domain tables share the same schema:
-- ts + series_id composite PK, value column, created_at

create table econ_rates_1d (
  ts          timestamptz not null,
  series_id   text        not null,
  value       numeric     not null,
  created_at  timestamptz not null default now(),
  primary key (ts, series_id)
);

create table econ_yields_1d (
  ts          timestamptz not null,
  series_id   text        not null,
  value       numeric     not null,
  created_at  timestamptz not null default now(),
  primary key (ts, series_id)
);

create table econ_fx_1d (
  ts          timestamptz not null,
  series_id   text        not null,
  value       numeric     not null,
  created_at  timestamptz not null default now(),
  primary key (ts, series_id)
);

create table econ_vol_1d (
  ts          timestamptz not null,
  series_id   text        not null,
  value       numeric     not null,
  created_at  timestamptz not null default now(),
  primary key (ts, series_id)
);

create table econ_inflation_1d (
  ts          timestamptz not null,
  series_id   text        not null,
  value       numeric     not null,
  created_at  timestamptz not null default now(),
  primary key (ts, series_id)
);

create table econ_labor_1d (
  ts          timestamptz not null,
  series_id   text        not null,
  value       numeric     not null,
  created_at  timestamptz not null default now(),
  primary key (ts, series_id)
);

create table econ_activity_1d (
  ts          timestamptz not null,
  series_id   text        not null,
  value       numeric     not null,
  created_at  timestamptz not null default now(),
  primary key (ts, series_id)
);

create table econ_money_1d (
  ts          timestamptz not null,
  series_id   text        not null,
  value       numeric     not null,
  created_at  timestamptz not null default now(),
  primary key (ts, series_id)
);

create table econ_commodities_1d (
  ts          timestamptz not null,
  series_id   text        not null,
  value       numeric     not null,
  created_at  timestamptz not null default now(),
  primary key (ts, series_id)
);

create table econ_indexes_1d (
  ts          timestamptz not null,
  series_id   text        not null,
  value       numeric     not null,
  created_at  timestamptz not null default now(),
  primary key (ts, series_id)
);

-- Time range indexes on all econ tables
create index idx_econ_rates_ts on econ_rates_1d (ts desc);
create index idx_econ_yields_ts on econ_yields_1d (ts desc);
create index idx_econ_fx_ts on econ_fx_1d (ts desc);
create index idx_econ_vol_ts on econ_vol_1d (ts desc);
create index idx_econ_inflation_ts on econ_inflation_1d (ts desc);
create index idx_econ_labor_ts on econ_labor_1d (ts desc);
create index idx_econ_activity_ts on econ_activity_1d (ts desc);
create index idx_econ_money_ts on econ_money_1d (ts desc);
create index idx_econ_commodities_ts on econ_commodities_1d (ts desc);
create index idx_econ_indexes_ts on econ_indexes_1d (ts desc);
