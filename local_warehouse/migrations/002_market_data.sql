-- Migration 002: MES OHLCV warehouse tables
-- Canonical snake_case schema. FLOAT8 for all price/volume values (ML-optimized).
-- Natural primary keys (ts or date). No ingestion-tracking metadata columns.
-- Retention floor enforced at bootstrap time (2020-01-01T00:00:00Z).
--
-- Bootstrap source mapping (rabid_raccoon → warbird):
--   mkt_futures_mes_15m."eventTime" → mes_15m.ts
--   mkt_futures_mes_1h."eventTime"  → mes_1h.ts
--   mkt_futures_mes_4h."eventTime"  → mes_4h.ts  (18 rows in source; rebuild from 1h in Phase 2)
--   mkt_futures_mes_1d."eventDate"  → mes_1d.date
--   open/high/low/close cast NUMERIC→FLOAT8, volume cast BIGINT→BIGINT

CREATE TABLE IF NOT EXISTS mes_15m (
  ts     TIMESTAMPTZ PRIMARY KEY,
  open   FLOAT8      NOT NULL,
  high   FLOAT8      NOT NULL,
  low    FLOAT8      NOT NULL,
  close  FLOAT8      NOT NULL,
  volume BIGINT
);
CREATE INDEX IF NOT EXISTS mes_15m_ts_idx ON mes_15m (ts);

CREATE TABLE IF NOT EXISTS mes_1h (
  ts     TIMESTAMPTZ PRIMARY KEY,
  open   FLOAT8      NOT NULL,
  high   FLOAT8      NOT NULL,
  low    FLOAT8      NOT NULL,
  close  FLOAT8      NOT NULL,
  volume BIGINT
);
CREATE INDEX IF NOT EXISTS mes_1h_ts_idx ON mes_1h (ts);

-- mes_4h is derived from mes_1h via OHLCV aggregation during Phase 2 bootstrap.
-- It is NOT bootstrapped from mkt_futures_mes_4h (only 18 rows, incomplete).
CREATE TABLE IF NOT EXISTS mes_4h (
  ts     TIMESTAMPTZ PRIMARY KEY,
  open   FLOAT8      NOT NULL,
  high   FLOAT8      NOT NULL,
  low    FLOAT8      NOT NULL,
  close  FLOAT8      NOT NULL,
  volume BIGINT
);
CREATE INDEX IF NOT EXISTS mes_4h_ts_idx ON mes_4h (ts);

-- Daily uses DATE as natural key (not TIMESTAMPTZ) — MES daily sessions align to date.
CREATE TABLE IF NOT EXISTS mes_1d (
  date   DATE        PRIMARY KEY,
  open   FLOAT8      NOT NULL,
  high   FLOAT8      NOT NULL,
  low    FLOAT8      NOT NULL,
  close  FLOAT8      NOT NULL,
  volume BIGINT
);

INSERT INTO local_schema_migrations (filename) VALUES ('002_market_data.sql')
  ON CONFLICT (filename) DO NOTHING;
