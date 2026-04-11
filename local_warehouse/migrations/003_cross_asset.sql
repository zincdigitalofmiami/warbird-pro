-- Migration 003: Cross-asset 1H OHLCV table
-- Canonical 6-symbol basket: NQ, RTY, CL, HG, 6E, 6J.
-- Composite natural PK (symbol, ts). No FK to symbols table.
--
-- Bootstrap source mapping (rabid_raccoon → warbird):
--   mkt_futures_1h."symbolCode" → cross_asset_1h.symbol
--   mkt_futures_1h."eventTime"  → cross_asset_1h.ts
--   mkt_futures_1h."openInterest" → cross_asset_1h.open_interest
--   Filter: symbolCode IN ('NQ','RTY','CL','HG','6E','6J')
--
-- HG BLOCKER (2026-04-11): HG is not present in rabid_raccoon.mkt_futures_1h.
-- HG data must be sourced from raw Databento files on the Satechi drive before
-- Phase 2 bootstrap is signed off. See MASTER_PLAN.md Phase 2 bootstrap notes.

CREATE TABLE IF NOT EXISTS cross_asset_1h (
  symbol        VARCHAR(16) NOT NULL,
  ts            TIMESTAMPTZ NOT NULL,
  open          FLOAT8      NOT NULL,
  high          FLOAT8      NOT NULL,
  low           FLOAT8      NOT NULL,
  close         FLOAT8      NOT NULL,
  volume        BIGINT,
  open_interest BIGINT,
  PRIMARY KEY (symbol, ts)
);
CREATE INDEX IF NOT EXISTS cross_asset_1h_ts_idx     ON cross_asset_1h (ts);
CREATE INDEX IF NOT EXISTS cross_asset_1h_symbol_idx ON cross_asset_1h (symbol);

INSERT INTO local_schema_migrations (filename) VALUES ('003_cross_asset.sql')
  ON CONFLICT (filename) DO NOTHING;
