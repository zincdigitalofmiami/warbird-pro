-- Migration 026: Expand FRED series catalog with 22 new macro indicators
-- Adds GDP, trade, government fiscal, prices, investment, expectations series.
-- Reactivates breakeven inflation series (T5YIE, T10YIE).
-- The existing nightly pg_cron FRED jobs query series_catalog WHERE category = X AND is_active = true,
-- so new series are automatically picked up -- no cron changes needed.

insert into series_catalog (series_id, name, category, frequency, is_active) values
  -- GDP (7 series)
  ('GDP',                 'Nominal GDP',                              'activity', 'quarterly', true),
  ('GDPC1',              'Real GDP (Constant Prices)',                'activity', 'quarterly', true),
  ('A191RL1Q225SBEA',    'Real GDP Growth Rate (Quarterly)',          'activity', 'quarterly', true),
  ('A191RL1A225SBEA',    'Real GDP Growth Rate (Annual)',             'activity', 'annual',    true),
  ('GDPDEF',             'GDP Implicit Price Deflator',              'inflation', 'quarterly', true),
  ('A939RX0Q048SBEA',    'Real GDP Per Capita',                      'activity', 'quarterly', true),
  ('GNP',                'Gross National Product',                    'activity', 'quarterly', true),

  -- Trade (2 series)
  ('BOPGSTB',            'Balance of Trade (Goods & Services)',       'activity', 'monthly',   true),
  ('BOPBCA',             'Current Account Balance',                   'activity', 'quarterly', true),

  -- Government fiscal (7 series)
  ('GFDEBTN',            'Federal Debt Total Public',                 'activity', 'quarterly', true),
  ('GFDEGDQ188S',        'Federal Debt as Percent of GDP',           'activity', 'quarterly', true),
  ('FGEXPND',            'Federal Government Expenditures',          'activity', 'quarterly', true),
  ('FGRECPT',            'Federal Government Receipts',              'activity', 'quarterly', true),
  ('FYFSD',              'Federal Surplus or Deficit as Pct of GDP', 'activity', 'annual',    true),
  ('FYOIGDA188S',        'Federal Outlays as Percent of GDP',        'activity', 'annual',    true),
  ('MTSDS133FMS',        'Monthly Treasury Statement Deficit',       'activity', 'monthly',   true),

  -- Prices (3 series)
  ('PPIFIS',             'PPI Final Demand',                         'inflation', 'monthly',   true),
  ('CUSR0000SAH',        'CPI Housing',                              'inflation', 'monthly',   true),
  ('CPIFABSL',           'CPI Food and Beverages',                   'inflation', 'monthly',   true),

  -- Investment proxy (1 series)
  ('GPDI',               'Gross Private Domestic Investment',         'activity', 'quarterly', true),

  -- Expectations (1 series)
  ('MICH',               'U Michigan Inflation Expectations 1Y',     'inflation', 'monthly',   true),

  -- GDP per capita PPP (1 series)
  ('NYGDPPCAPPPCD',      'GDP Per Capita PPP (World Bank)',          'activity', 'annual',    true)
on conflict (series_id) do nothing;

-- Reactivate breakeven inflation series (were set inactive)
update series_catalog set is_active = true where series_id in ('T5YIE', 'T10YIE');
