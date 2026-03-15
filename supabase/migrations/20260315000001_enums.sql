-- Migration 001: Enum types
-- All enums used across warbird-pro tables

create type data_source as enum (
  'DATABENTO',
  'FRED',
  'MANUAL'
);

create type econ_category as enum (
  'rates',
  'yields',
  'fx',
  'vol',
  'inflation',
  'labor',
  'activity',
  'money',
  'commodities',
  'indexes'
);

create type report_category as enum (
  'fomc',
  'cpi',
  'nfp',
  'claims',
  'ppi',
  'retail_sales',
  'gdp',
  'ism',
  'housing',
  'consumer_confidence'
);

create type timeframe as enum (
  'M1',
  'M5',
  'M15',
  'H1',
  'H4',
  'D1'
);

create type signal_direction as enum (
  'LONG',
  'SHORT'
);

create type signal_status as enum (
  'ACTIVE',
  'EXPIRED',
  'STOPPED',
  'TP1_HIT',
  'TP2_HIT'
);

create type setup_phase as enum (
  'TOUCHED',
  'HOOKED',
  'GO_FIRED',
  'EXPIRED',
  'STOPPED',
  'TP1_HIT',
  'TP2_HIT'
);

create type ingestion_status as enum (
  'SUCCESS',
  'PARTIAL',
  'FAILED',
  'SKIPPED'
);

create type vol_state as enum (
  'EXTREME',
  'CRISIS',
  'ELEVATED',
  'NORMAL',
  'COMPRESSED'
);
