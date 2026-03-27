-- Migration 032: Fix 3 broken FRED series IDs in series_catalog
-- These were inserted in migration 026 but FRED API returns 400 for them.
--
-- 1. A191RL1A225SBEA (Annual GDP Growth Rate):
--    Does not exist on FRED. Quarterly version A191RL1Q225SBEA already in catalog.
--    Fix: deactivate.
--
-- 2. CUSR0000SAH (CPI Housing):
--    Missing trailing '1'. Correct ID is CUSR0000SAH1 (CPI Shelter, Monthly, SA).
--    Fix: update series_id.
--
-- 3. NYGDPPCAPPPCD (GDP Per Capita PPP, World Bank):
--    Does not exist on FRED. Correct World Bank series on FRED is NYGDPPCAPKDUSA
--    (Constant GDP per capita for the United States, Annual).
--    Fix: update series_id and name.

begin;

-- 1. Deactivate the annual GDP growth series (does not exist on FRED)
update series_catalog
set is_active = false
where series_id = 'A191RL1A225SBEA';

-- 2. Fix CPI Housing series ID (missing trailing '1')
update series_catalog
set series_id = 'CUSR0000SAH1',
    name = 'CPI Shelter'
where series_id = 'CUSR0000SAH';

-- 3. Fix GDP per capita PPP series ID
update series_catalog
set series_id = 'NYGDPPCAPKDUSA',
    name = 'Constant GDP Per Capita (World Bank)'
where series_id = 'NYGDPPCAPPPCD';

commit;
