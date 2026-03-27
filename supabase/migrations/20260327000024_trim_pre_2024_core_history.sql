-- Trim core historical series to the January 1, 2024 retention floor.
-- This is an operational data-retention migration, not a schema change.
-- Keep only rows at or after 2024-01-01T00:00:00+00:00.

begin;

delete from econ_rates_1d
where ts < '2024-01-01T00:00:00+00:00'::timestamptz;

delete from econ_yields_1d
where ts < '2024-01-01T00:00:00+00:00'::timestamptz;

delete from econ_fx_1d
where ts < '2024-01-01T00:00:00+00:00'::timestamptz;

delete from econ_vol_1d
where ts < '2024-01-01T00:00:00+00:00'::timestamptz;

delete from econ_inflation_1d
where ts < '2024-01-01T00:00:00+00:00'::timestamptz;

delete from econ_labor_1d
where ts < '2024-01-01T00:00:00+00:00'::timestamptz;

delete from econ_activity_1d
where ts < '2024-01-01T00:00:00+00:00'::timestamptz;

delete from econ_money_1d
where ts < '2024-01-01T00:00:00+00:00'::timestamptz;

delete from econ_commodities_1d
where ts < '2024-01-01T00:00:00+00:00'::timestamptz;

delete from econ_indexes_1d
where ts < '2024-01-01T00:00:00+00:00'::timestamptz;

delete from geopolitical_risk_1d
where ts < '2024-01-01T00:00:00+00:00'::timestamptz;

delete from econ_news_1d
where ts < '2024-01-01T00:00:00+00:00'::timestamptz;

commit;
