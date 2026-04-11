-- Migration 006: Economic calendar
-- Event-level macro calendar with FRED cross-references.
-- Composite PK (event_date, event_name) matches rabid_raccoon unique constraint.
--
-- Bootstrap source mapping (rabid_raccoon → warbird):
--   econ_calendar."eventDate"     → econ_calendar.event_date
--   econ_calendar."eventTime"     → econ_calendar.event_time
--   econ_calendar."eventName"     → econ_calendar.event_name
--   econ_calendar."eventType"     → econ_calendar.event_type
--   econ_calendar."fredReleaseId" → econ_calendar.fred_release_id
--   econ_calendar."fredSeriesId"  → econ_calendar.fred_series_id
--   econ_calendar."frequency"     → econ_calendar.frequency
--   econ_calendar."impactRating"  → econ_calendar.impact_rating
--   Drop: id, ingestedAt, knowledgeTime, metadata, source (ingestion tracking)

CREATE TABLE IF NOT EXISTS econ_calendar (
  event_date      DATE         NOT NULL,
  event_time      VARCHAR(16),
  event_name      VARCHAR(120) NOT NULL,
  event_type      VARCHAR(64)  NOT NULL,
  fred_release_id INTEGER,
  fred_series_id  VARCHAR(50),
  frequency       VARCHAR(32),
  forecast        FLOAT8,
  previous        FLOAT8,
  actual          FLOAT8,
  surprise        FLOAT8,
  impact_rating   VARCHAR(16),
  PRIMARY KEY (event_date, event_name)
);
CREATE INDEX IF NOT EXISTS econ_calendar_date_idx       ON econ_calendar (event_date);
CREATE INDEX IF NOT EXISTS econ_calendar_series_idx     ON econ_calendar (fred_series_id);
CREATE INDEX IF NOT EXISTS econ_calendar_type_idx       ON econ_calendar (event_type);
CREATE INDEX IF NOT EXISTS econ_calendar_impact_idx     ON econ_calendar (impact_rating);

INSERT INTO local_schema_migrations (filename) VALUES ('006_econ_calendar.sql')
  ON CONFLICT (filename) DO NOTHING;
