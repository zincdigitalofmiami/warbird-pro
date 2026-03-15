-- Migration 003: MES OHLCV data tables
-- Primary instrument. 5 timeframes: 1m, 15m, 1h, 4h, 1d
-- ts is the bar open time, always timestamptz

create table mes_1m (
  ts       timestamptz not null,
  open     numeric     not null,
  high     numeric     not null,
  low      numeric     not null,
  close    numeric     not null,
  volume   bigint      not null default 0,
  created_at timestamptz not null default now(),
  primary key (ts)
);

create table mes_15m (
  ts       timestamptz not null,
  open     numeric     not null,
  high     numeric     not null,
  low      numeric     not null,
  close    numeric     not null,
  volume   bigint      not null default 0,
  created_at timestamptz not null default now(),
  primary key (ts)
);

create table mes_1h (
  ts       timestamptz not null,
  open     numeric     not null,
  high     numeric     not null,
  low      numeric     not null,
  close    numeric     not null,
  volume   bigint      not null default 0,
  created_at timestamptz not null default now(),
  primary key (ts)
);

create table mes_4h (
  ts       timestamptz not null,
  open     numeric     not null,
  high     numeric     not null,
  low      numeric     not null,
  close    numeric     not null,
  volume   bigint      not null default 0,
  created_at timestamptz not null default now(),
  primary key (ts)
);

create table mes_1d (
  ts       timestamptz not null,
  open     numeric     not null,
  high     numeric     not null,
  low      numeric     not null,
  close    numeric     not null,
  volume   bigint      not null default 0,
  created_at timestamptz not null default now(),
  primary key (ts)
);

-- Indexes for range queries (common: WHERE ts >= X AND ts < Y)
create index idx_mes_1m_ts on mes_1m (ts desc);
create index idx_mes_15m_ts on mes_15m (ts desc);
create index idx_mes_1h_ts on mes_1h (ts desc);
create index idx_mes_4h_ts on mes_4h (ts desc);
create index idx_mes_1d_ts on mes_1d (ts desc);
