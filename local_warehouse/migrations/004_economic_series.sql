-- Migration 004: Economic series reference table
-- Canonical registry of FRED and other macro series admitted to the local warehouse.
-- Required before FRED family tables (005) due to FK dependency.
--
-- Bootstrap source mapping (rabid_raccoon → warbird):
--   economic_series."seriesId"     → economic_series.series_id
--   economic_series."displayName"  → economic_series.display_name
--   economic_series."category"     → economic_series.category (TEXT, drop enum)
--   economic_series."source"       → economic_series.source (TEXT, drop enum)
--   economic_series."sourceSymbol" → economic_series.source_symbol
--   economic_series."isActive"     → economic_series.is_active
--   Drop: metadata, createdAt, updatedAt (ingestion tracking, not needed)

CREATE TABLE IF NOT EXISTS economic_series (
  series_id     VARCHAR(50)  PRIMARY KEY,
  display_name  VARCHAR(200),
  category      VARCHAR(64)  NOT NULL DEFAULT 'OTHER',
  source        VARCHAR(64)  NOT NULL,
  source_symbol VARCHAR(50),
  frequency     VARCHAR(20),
  units         VARCHAR(32),
  is_active     BOOLEAN      NOT NULL DEFAULT TRUE
);
CREATE INDEX IF NOT EXISTS economic_series_category_idx ON economic_series (category, is_active);

INSERT INTO local_schema_migrations (filename) VALUES ('004_economic_series.sql')
  ON CONFLICT (filename) DO NOTHING;
