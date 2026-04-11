-- Migration 005: FRED macro family tables
-- Ten canonical daily FRED families. All share (series_id, event_date) composite PK.
-- FLOAT8 for value. FK to economic_series.
--
-- Bootstrap source mapping (rabid_raccoon → warbird):
--   econ_*_1d."seriesId"   → econ_*_1d.series_id
--   econ_*_1d."eventDate"  → econ_*_1d.event_date
--   econ_*_1d."value"      → econ_*_1d.value (NUMERIC→FLOAT8)
--   Drop: source, ingestedAt, knowledgeTime, rowHash, metadata
--   Note: rabid_raccoon uses "econ_vol_indices_1d"; canonical name is "econ_vol_1d"

CREATE TABLE IF NOT EXISTS econ_rates_1d (
  series_id  VARCHAR(50) NOT NULL REFERENCES economic_series(series_id),
  event_date DATE        NOT NULL,
  value      FLOAT8,
  PRIMARY KEY (series_id, event_date)
);
CREATE INDEX IF NOT EXISTS econ_rates_1d_date_idx ON econ_rates_1d (event_date);

CREATE TABLE IF NOT EXISTS econ_yields_1d (
  series_id  VARCHAR(50) NOT NULL REFERENCES economic_series(series_id),
  event_date DATE        NOT NULL,
  value      FLOAT8,
  PRIMARY KEY (series_id, event_date)
);
CREATE INDEX IF NOT EXISTS econ_yields_1d_date_idx ON econ_yields_1d (event_date);

CREATE TABLE IF NOT EXISTS econ_fx_1d (
  series_id  VARCHAR(50) NOT NULL REFERENCES economic_series(series_id),
  event_date DATE        NOT NULL,
  value      FLOAT8,
  PRIMARY KEY (series_id, event_date)
);
CREATE INDEX IF NOT EXISTS econ_fx_1d_date_idx ON econ_fx_1d (event_date);

CREATE TABLE IF NOT EXISTS econ_vol_1d (
  series_id  VARCHAR(50) NOT NULL REFERENCES economic_series(series_id),
  event_date DATE        NOT NULL,
  value      FLOAT8,
  PRIMARY KEY (series_id, event_date)
);
CREATE INDEX IF NOT EXISTS econ_vol_1d_date_idx ON econ_vol_1d (event_date);

CREATE TABLE IF NOT EXISTS econ_inflation_1d (
  series_id  VARCHAR(50) NOT NULL REFERENCES economic_series(series_id),
  event_date DATE        NOT NULL,
  value      FLOAT8,
  PRIMARY KEY (series_id, event_date)
);
CREATE INDEX IF NOT EXISTS econ_inflation_1d_date_idx ON econ_inflation_1d (event_date);

CREATE TABLE IF NOT EXISTS econ_labor_1d (
  series_id  VARCHAR(50) NOT NULL REFERENCES economic_series(series_id),
  event_date DATE        NOT NULL,
  value      FLOAT8,
  PRIMARY KEY (series_id, event_date)
);
CREATE INDEX IF NOT EXISTS econ_labor_1d_date_idx ON econ_labor_1d (event_date);

CREATE TABLE IF NOT EXISTS econ_activity_1d (
  series_id  VARCHAR(50) NOT NULL REFERENCES economic_series(series_id),
  event_date DATE        NOT NULL,
  value      FLOAT8,
  PRIMARY KEY (series_id, event_date)
);
CREATE INDEX IF NOT EXISTS econ_activity_1d_date_idx ON econ_activity_1d (event_date);

CREATE TABLE IF NOT EXISTS econ_money_1d (
  series_id  VARCHAR(50) NOT NULL REFERENCES economic_series(series_id),
  event_date DATE        NOT NULL,
  value      FLOAT8,
  PRIMARY KEY (series_id, event_date)
);
CREATE INDEX IF NOT EXISTS econ_money_1d_date_idx ON econ_money_1d (event_date);

CREATE TABLE IF NOT EXISTS econ_commodities_1d (
  series_id  VARCHAR(50) NOT NULL REFERENCES economic_series(series_id),
  event_date DATE        NOT NULL,
  value      FLOAT8,
  PRIMARY KEY (series_id, event_date)
);
CREATE INDEX IF NOT EXISTS econ_commodities_1d_date_idx ON econ_commodities_1d (event_date);

CREATE TABLE IF NOT EXISTS econ_indexes_1d (
  series_id  VARCHAR(50) NOT NULL REFERENCES economic_series(series_id),
  event_date DATE        NOT NULL,
  value      FLOAT8,
  PRIMARY KEY (series_id, event_date)
);
CREATE INDEX IF NOT EXISTS econ_indexes_1d_date_idx ON econ_indexes_1d (event_date);

INSERT INTO local_schema_migrations (filename) VALUES ('005_fred_families.sql')
  ON CONFLICT (filename) DO NOTHING;
