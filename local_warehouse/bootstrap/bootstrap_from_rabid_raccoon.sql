-- Phase 2: One-Time Bootstrap from rabid_raccoon → warbird
-- Run once only. After completion, rabid_raccoon is legacy reference only.
-- Retention floor: 2020-01-01T00:00:00Z (UTC) = '2020-01-01 00:00:00+00'
--
-- EXECUTE FROM PSQL:
--   psql -h 127.0.0.1 -p 5432 -d warbird -f bootstrap_from_rabid_raccoon.sql
--
-- PREREQUISITES:
--   1. warbird migrations 001-006 applied and verified.
--   2. warbird tables are empty (fresh bootstrap only).
--   3. rabid_raccoon is reachable on same PG instance.
--
-- HG BLOCKER: HG is absent from rabid_raccoon.mkt_futures_1h.
--   cross_asset_1h will be populated for 5 of 6 symbols (NQ, RTY, CL, 6E, 6J).
--   HG must be loaded separately from raw Databento files before Phase 2 is signed off.
--   See: data/ directory on Satechi drive for raw Databento archives.

SET search_path = public;

-- ── 1. MES 15m ──────────────────────────────────────────────────────────────
INSERT INTO warbird.public.mes_15m (ts, open, high, low, close, volume)
SELECT
  "eventTime"         AS ts,
  open::FLOAT8        AS open,
  high::FLOAT8        AS high,
  low::FLOAT8         AS low,
  close::FLOAT8       AS close,
  volume
FROM rabid_raccoon.public.mkt_futures_mes_15m
WHERE "eventTime" >= '2020-01-01 00:00:00+00'
ON CONFLICT (ts) DO NOTHING;

-- ── 2. MES 1H ───────────────────────────────────────────────────────────────
INSERT INTO warbird.public.mes_1h (ts, open, high, low, close, volume)
SELECT
  "eventTime"         AS ts,
  open::FLOAT8        AS open,
  high::FLOAT8        AS high,
  low::FLOAT8         AS low,
  close::FLOAT8       AS close,
  volume
FROM rabid_raccoon.public.mkt_futures_mes_1h
WHERE "eventTime" >= '2020-01-01 00:00:00+00'
ON CONFLICT (ts) DO NOTHING;

-- ── 3. MES 4H — derived from mes_1h (NOT from mkt_futures_mes_4h) ──────────
-- Aggregates 1H bars into 4H sessions aligned to 18:00 CT session open.
-- 4H periods: 18:00, 22:00, 02:00, 06:00, 10:00, 14:00 CT (Chicago/America)
-- Using date_trunc with 4-hour offset aligned to CME session.
INSERT INTO warbird.public.mes_4h (ts, open, high, low, close, volume)
SELECT
  date_trunc('hour', ts - INTERVAL '0 hours') -
    INTERVAL '1 hour' * (EXTRACT(HOUR FROM ts AT TIME ZONE 'America/Chicago')::INT % 4) AS ts_4h,
  (array_agg(open  ORDER BY ts))[1]  AS open,
  MAX(high)                          AS high,
  MIN(low)                           AS low,
  (array_agg(close ORDER BY ts DESC))[1] AS close,
  SUM(volume)                        AS volume
FROM warbird.public.mes_1h
GROUP BY ts_4h
HAVING COUNT(*) > 0
ON CONFLICT (ts) DO NOTHING;

-- ── 4. MES 1D ───────────────────────────────────────────────────────────────
INSERT INTO warbird.public.mes_1d (date, open, high, low, close, volume)
SELECT
  "eventDate"         AS date,
  open::FLOAT8        AS open,
  high::FLOAT8        AS high,
  low::FLOAT8         AS low,
  close::FLOAT8       AS close,
  volume
FROM rabid_raccoon.public.mkt_futures_mes_1d
WHERE "eventDate" >= '2020-01-01'
ON CONFLICT (date) DO NOTHING;

-- ── 5. Cross-asset 1H (5 of 6 symbols — HG missing) ────────────────────────
INSERT INTO warbird.public.cross_asset_1h (symbol, ts, open, high, low, close, volume, open_interest)
SELECT
  "symbolCode"        AS symbol,
  "eventTime"         AS ts,
  open::FLOAT8        AS open,
  high::FLOAT8        AS high,
  low::FLOAT8         AS low,
  close::FLOAT8       AS close,
  volume,
  "openInterest"      AS open_interest
FROM rabid_raccoon.public.mkt_futures_1h
WHERE "symbolCode" IN ('NQ', 'RTY', 'CL', '6E', '6J')
  AND "eventTime" >= '2020-01-01 00:00:00+00'
ON CONFLICT (symbol, ts) DO NOTHING;

-- ── 6. Economic series registry ──────────────────────────────────────────────
INSERT INTO warbird.public.economic_series (series_id, display_name, category, source, source_symbol, frequency, units, is_active)
SELECT
  "seriesId"          AS series_id,
  "displayName"       AS display_name,
  "category"::TEXT    AS category,
  "source"::TEXT      AS source,
  "sourceSymbol"      AS source_symbol,
  "frequency"         AS frequency,
  "units"             AS units,
  "isActive"          AS is_active
FROM rabid_raccoon.public.economic_series
ON CONFLICT (series_id) DO NOTHING;

-- ── 7. FRED families ─────────────────────────────────────────────────────────
INSERT INTO warbird.public.econ_rates_1d (series_id, event_date, value)
SELECT "seriesId", "eventDate", value::FLOAT8
FROM rabid_raccoon.public.econ_rates_1d
WHERE "eventDate" >= '2020-01-01'
ON CONFLICT (series_id, event_date) DO NOTHING;

INSERT INTO warbird.public.econ_yields_1d (series_id, event_date, value)
SELECT "seriesId", "eventDate", value::FLOAT8
FROM rabid_raccoon.public.econ_yields_1d
WHERE "eventDate" >= '2020-01-01'
ON CONFLICT (series_id, event_date) DO NOTHING;

INSERT INTO warbird.public.econ_fx_1d (series_id, event_date, value)
SELECT "seriesId", "eventDate", value::FLOAT8
FROM rabid_raccoon.public.econ_fx_1d
WHERE "eventDate" >= '2020-01-01'
ON CONFLICT (series_id, event_date) DO NOTHING;

INSERT INTO warbird.public.econ_vol_1d (series_id, event_date, value)
SELECT "seriesId", "eventDate", value::FLOAT8
FROM rabid_raccoon.public.econ_vol_indices_1d
WHERE "eventDate" >= '2020-01-01'
ON CONFLICT (series_id, event_date) DO NOTHING;

INSERT INTO warbird.public.econ_inflation_1d (series_id, event_date, value)
SELECT "seriesId", "eventDate", value::FLOAT8
FROM rabid_raccoon.public.econ_inflation_1d
WHERE "eventDate" >= '2020-01-01'
ON CONFLICT (series_id, event_date) DO NOTHING;

INSERT INTO warbird.public.econ_labor_1d (series_id, event_date, value)
SELECT "seriesId", "eventDate", value::FLOAT8
FROM rabid_raccoon.public.econ_labor_1d
WHERE "eventDate" >= '2020-01-01'
ON CONFLICT (series_id, event_date) DO NOTHING;

INSERT INTO warbird.public.econ_activity_1d (series_id, event_date, value)
SELECT "seriesId", "eventDate", value::FLOAT8
FROM rabid_raccoon.public.econ_activity_1d
WHERE "eventDate" >= '2020-01-01'
ON CONFLICT (series_id, event_date) DO NOTHING;

INSERT INTO warbird.public.econ_money_1d (series_id, event_date, value)
SELECT "seriesId", "eventDate", value::FLOAT8
FROM rabid_raccoon.public.econ_money_1d
WHERE "eventDate" >= '2020-01-01'
ON CONFLICT (series_id, event_date) DO NOTHING;

INSERT INTO warbird.public.econ_commodities_1d (series_id, event_date, value)
SELECT "seriesId", "eventDate", value::FLOAT8
FROM rabid_raccoon.public.econ_commodities_1d
WHERE "eventDate" >= '2020-01-01'
ON CONFLICT (series_id, event_date) DO NOTHING;

INSERT INTO warbird.public.econ_indexes_1d (series_id, event_date, value)
SELECT "seriesId", "eventDate", value::FLOAT8
FROM rabid_raccoon.public.econ_indexes_1d
WHERE "eventDate" >= '2020-01-01'
ON CONFLICT (series_id, event_date) DO NOTHING;

-- ── 8. Economic calendar ─────────────────────────────────────────────────────
INSERT INTO warbird.public.econ_calendar (
  event_date, event_time, event_name, event_type,
  fred_release_id, fred_series_id, frequency,
  forecast, previous, actual, surprise, impact_rating
)
SELECT
  "eventDate"         AS event_date,
  "eventTime"         AS event_time,
  "eventName"         AS event_name,
  "eventType"         AS event_type,
  "fredReleaseId"     AS fred_release_id,
  "fredSeriesId"      AS fred_series_id,
  "frequency"         AS frequency,
  forecast::FLOAT8    AS forecast,
  previous::FLOAT8    AS previous,
  actual::FLOAT8      AS actual,
  surprise::FLOAT8    AS surprise,
  "impactRating"      AS impact_rating
FROM rabid_raccoon.public.econ_calendar
ON CONFLICT (event_date, event_name) DO NOTHING;

-- ── Validation queries (run after bootstrap) ──────────────────────────────────
-- Uncomment and run to verify:
/*
SELECT 'mes_15m'       AS tbl, COUNT(*), MIN(ts)::DATE, MAX(ts)::DATE FROM warbird.public.mes_15m
UNION ALL
SELECT 'mes_1h'        AS tbl, COUNT(*), MIN(ts)::DATE, MAX(ts)::DATE FROM warbird.public.mes_1h
UNION ALL
SELECT 'mes_4h'        AS tbl, COUNT(*), MIN(ts)::DATE, MAX(ts)::DATE FROM warbird.public.mes_4h
UNION ALL
SELECT 'mes_1d'        AS tbl, COUNT(*), MIN(date), MAX(date) FROM warbird.public.mes_1d
UNION ALL
SELECT 'cross_asset'   AS tbl, COUNT(*), MIN(ts)::DATE, MAX(ts)::DATE FROM warbird.public.cross_asset_1h
UNION ALL
SELECT 'econ_series'   AS tbl, COUNT(*), NULL, NULL FROM warbird.public.economic_series
UNION ALL
SELECT 'econ_calendar' AS tbl, COUNT(*), MIN(event_date), MAX(event_date) FROM warbird.public.econ_calendar;

SELECT symbol, COUNT(*), MIN(ts)::DATE, MAX(ts)::DATE
FROM warbird.public.cross_asset_1h
GROUP BY symbol ORDER BY symbol;
*/
