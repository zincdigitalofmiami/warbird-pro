-- Add FRED-sourced inflation expectations series to series_catalog.
-- These replace the Massive Economy API equivalents (MASSIVE_IE_*) with
-- free FRED series: Cleveland Fed model expectations + 5Y5Y forward rate.
-- T5YIE and T10YIE (market-based breakevens) already exist in the catalog.

INSERT INTO series_catalog (series_id, name, category, frequency, is_active)
VALUES
  ('EXPINF1YR',  'Cleveland Fed 1-Year Expected Inflation',  'inflation', 'monthly', true),
  ('EXPINF5YR',  'Cleveland Fed 5-Year Expected Inflation',  'inflation', 'monthly', true),
  ('EXPINF10YR', 'Cleveland Fed 10-Year Expected Inflation', 'inflation', 'monthly', true),
  ('EXPINF30YR', 'Cleveland Fed 30-Year Expected Inflation', 'inflation', 'monthly', true),
  ('T5YIFR',     '5-Year Forward Inflation Expectation Rate', 'inflation', 'daily',   true)
ON CONFLICT (series_id) DO NOTHING;
