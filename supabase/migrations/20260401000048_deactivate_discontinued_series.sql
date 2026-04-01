-- BOPBCA (Balance on Current Account) was DISCONTINUED by FRED in 2014.
-- Last observation: 2014-01-01. No data exists in the 2020+ training window.
-- Deactivate so the FRED backfill script skips it.

UPDATE series_catalog
SET is_active = false
WHERE series_id = 'BOPBCA';
