-- Migration 001: Local schema migrations ledger
-- This table tracks which migrations have been applied to the local warbird warehouse.
-- It is the first object created and must not be modified after initial creation.

CREATE TABLE IF NOT EXISTS local_schema_migrations (
  id          SERIAL PRIMARY KEY,
  filename    TEXT    NOT NULL UNIQUE,
  applied_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  checksum    TEXT
);

-- Self-register this migration
INSERT INTO local_schema_migrations (filename) VALUES ('001_local_schema_migrations.sql')
  ON CONFLICT (filename) DO NOTHING;
