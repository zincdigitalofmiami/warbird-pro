-- Migration 004: Cross-asset data tables
-- Non-MES futures (ES, NQ, YM, RTY, CL, GC, SI, NG, ZN, ZB, ZF, SOX, SR3, 6E, 6J)
-- Plus FRED symbols (DX, US10Y, VX)
-- Options aggregate + OHLCV for 15 .OPT symbols

create table cross_asset_1h (
  ts          timestamptz not null,
  symbol_code text        not null references symbols(code),
  open        numeric     not null,
  high        numeric     not null,
  low         numeric     not null,
  close       numeric     not null,
  volume      bigint      not null default 0,
  created_at  timestamptz not null default now(),
  primary key (ts, symbol_code)
);

create table cross_asset_1d (
  ts          timestamptz not null,
  symbol_code text        not null references symbols(code),
  open        numeric     not null,
  high        numeric     not null,
  low         numeric     not null,
  close       numeric     not null,
  volume      bigint      not null default 0,
  created_at  timestamptz not null default now(),
  primary key (ts, symbol_code)
);

create table options_stats_1d (
  ts             timestamptz not null,
  symbol_code    text        not null references symbols(code),
  open_interest  bigint,
  implied_vol    numeric,
  volume         bigint,
  put_call_ratio numeric,
  delta          numeric,
  gamma          numeric,
  created_at     timestamptz not null default now(),
  primary key (ts, symbol_code)
);

create table options_ohlcv_1d (
  ts          timestamptz not null,
  symbol_code text        not null references symbols(code),
  open        numeric     not null,
  high        numeric     not null,
  low         numeric     not null,
  close       numeric     not null,
  volume      bigint      not null default 0,
  created_at  timestamptz not null default now(),
  primary key (ts, symbol_code)
);

-- Indexes for symbol + time range queries
create index idx_cross_asset_1h_sym_ts on cross_asset_1h (symbol_code, ts desc);
create index idx_cross_asset_1d_sym_ts on cross_asset_1d (symbol_code, ts desc);
create index idx_options_stats_1d_sym_ts on options_stats_1d (symbol_code, ts desc);
create index idx_options_ohlcv_1d_sym_ts on options_ohlcv_1d (symbol_code, ts desc);
