-- BAMLHYH0A0HYM2EY does not exist on FRED (returns 400 "series does not exist").
-- BAMLH0A0HYM2 (OAS spread, already loaded) is the correct live series.
-- Mark the bad EY series as inactive so the FRED backfill script skips it.

UPDATE series_catalog
SET is_active = false
WHERE series_id = 'BAMLHYH0A0HYM2EY';
