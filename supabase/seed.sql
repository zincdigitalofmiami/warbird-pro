-- Seed data for warbird-pro
-- 60 real symbols from rabid-raccoon production DB (34 active, 26 inactive)
-- CRITICAL: Only active DATABENTO symbols may be queried. Kirk got massive bill from inactive ones.

-- ============================================================
-- SYMBOLS (60 total: 31 active DATABENTO, 3 active FRED, 26 inactive)
-- ============================================================

insert into symbols (code, display_name, short_name, description, tick_size, data_source, dataset, databento_symbol, fred_symbol, is_active) values
  -- Active DATABENTO futures (16)
  ('MES', 'MES', 'Micro S&P', 'Micro E-mini S&P 500 Futures', 0.25, 'DATABENTO', 'GLBX.MDP3', 'MES.v.0', null, true),
  ('ES', 'ES', 'E-mini S&P', 'E-mini S&P 500 Futures', 0.25, 'DATABENTO', 'GLBX.MDP3', 'ES.c.0', null, true),
  ('NQ', 'NQ', 'E-mini Nasdaq', 'E-mini Nasdaq-100 Futures', 0.25, 'DATABENTO', 'GLBX.MDP3', 'NQ.c.0', null, true),
  ('YM', 'YM', 'E-mini Dow', 'E-mini Dow Jones Futures', 1, 'DATABENTO', 'GLBX.MDP3', 'YM.c.0', null, true),
  ('RTY', 'RTY', 'E-mini Russell', 'E-mini Russell 2000 Futures', 0.1, 'DATABENTO', 'GLBX.MDP3', 'RTY.c.0', null, true),
  ('CL', 'CL', 'Crude Oil', 'WTI Crude Oil Futures', 0.01, 'DATABENTO', 'GLBX.MDP3', 'CL.c.0', null, true),
  ('GC', 'GC', 'Gold', 'Gold Futures', 0.1, 'DATABENTO', 'GLBX.MDP3', 'GC.c.0', null, true),
  ('SI', 'SI', 'Silver', 'Silver Futures', 0.005, 'DATABENTO', 'GLBX.MDP3', 'SI.c.0', null, true),
  ('NG', 'NG', 'Nat Gas', 'Natural Gas Futures', 0.001, 'DATABENTO', 'GLBX.MDP3', 'NG.c.0', null, true),
  ('ZN', 'ZN', '10Y Note', '10-Year Treasury Note Futures', 0.015625, 'DATABENTO', 'GLBX.MDP3', 'ZN.c.0', null, true),
  ('ZB', 'ZB', '30Y Bond', '30-Year Treasury Bond Futures', 0.03125, 'DATABENTO', 'GLBX.MDP3', 'ZB.c.0', null, true),
  ('ZF', 'ZF', '5Y Note', '5-Year Treasury Note Futures', 0.007813, 'DATABENTO', 'GLBX.MDP3', 'ZF.c.0', null, true),
  ('SOX', 'SOX', 'Semiconductor', 'PHLX Semiconductor Index Futures', 0.1, 'DATABENTO', 'GLBX.MDP3', 'SOX.c.0', null, true),
  ('SR3', 'SR3', 'SOFR 3M', '3-Month SOFR Futures', 0.0025, 'DATABENTO', 'GLBX.MDP3', 'SR3.c.0', null, true),
  ('6E', '6E', 'EUR/USD', 'Euro FX Futures (EUR/USD)', 0.00005, 'DATABENTO', 'GLBX.MDP3', '6E.c.0', null, true),
  ('6J', '6J', 'JPY/USD', 'Japanese Yen Futures (JPY/USD)', 0, 'DATABENTO', 'GLBX.MDP3', '6J.c.0', null, true),

  -- Active DATABENTO options (15)
  ('ES.OPT', 'ES Options', 'ES Opts', 'E-mini S&P 500 Options (CME parent)', 0, 'DATABENTO', 'GLBX.MDP3', 'ES.OPT', null, true),
  ('NQ.OPT', 'NQ Options', 'NQ Opts', 'E-mini Nasdaq-100 Options (CME parent)', 0, 'DATABENTO', 'GLBX.MDP3', 'NQ.OPT', null, true),
  ('EUU.OPT', 'EUU Options', 'EUU Opts', 'Euro FX (E-micro) Options (CME parent)', 0, 'DATABENTO', 'GLBX.MDP3', 'EUU.OPT', null, true),
  ('HXE.OPT', 'HXE Options', 'HXE Opts', 'Euro FX Options (CME parent)', 0, 'DATABENTO', 'GLBX.MDP3', 'HXE.OPT', null, true),
  ('JPU.OPT', 'JPU Options', 'JPU Opts', 'Japanese Yen Options (CME parent)', 0, 'DATABENTO', 'GLBX.MDP3', 'JPU.OPT', null, true),
  ('LO.OPT', 'LO Options', 'LO Opts', 'Crude Oil Options (CME parent)', 0, 'DATABENTO', 'GLBX.MDP3', 'LO.OPT', null, true),
  ('OB.OPT', 'OB Options', 'OB Opts', 'RBOB Gasoline Options (CME parent)', 0, 'DATABENTO', 'GLBX.MDP3', 'OB.OPT', null, true),
  ('OG.OPT', 'OG Options', 'OG Opts', 'Gold Options (CME parent)', 0, 'DATABENTO', 'GLBX.MDP3', 'OG.OPT', null, true),
  ('OH.OPT', 'OH Options', 'OH Opts', 'Heating Oil Options (CME parent)', 0, 'DATABENTO', 'GLBX.MDP3', 'OH.OPT', null, true),
  ('OKE.OPT', 'OKE Options', 'OKE Opts', 'Eurodollar Options (CME parent)', 0, 'DATABENTO', 'GLBX.MDP3', 'OKE.OPT', null, true),
  ('ON.OPT', 'ON Options', 'ON Opts', 'Natural Gas Options (CME parent)', 0, 'DATABENTO', 'GLBX.MDP3', 'ON.OPT', null, true),
  ('OZB.OPT', 'OZB Options', 'OZB Opts', 'Treasury Bond Options (CME parent)', 0, 'DATABENTO', 'GLBX.MDP3', 'OZB.OPT', null, true),
  ('OZF.OPT', 'OZF Options', 'OZF Opts', '5-Year Treasury Note Options (CME parent)', 0, 'DATABENTO', 'GLBX.MDP3', 'OZF.OPT', null, true),
  ('OZN.OPT', 'OZN Options', 'OZN Opts', '10-Year Treasury Note Options (CME parent)', 0, 'DATABENTO', 'GLBX.MDP3', 'OZN.OPT', null, true),
  ('SO.OPT', 'SO Options', 'SO Opts', 'Soybean Options (CME parent)', 0, 'DATABENTO', 'GLBX.MDP3', 'SO.OPT', null, true),

  -- Active FRED (3) — free API, no Databento cost
  ('DX', 'US Dollar Index', 'DXY', 'ICE US Dollar Index futures', 0.005, 'FRED', null, null, null, true),
  ('US10Y', '10-Year Treasury', 'US10Y', 'US 10-Year Treasury Yield', 0.001, 'FRED', null, null, null, true),
  ('VX', 'VIX Futures', 'VIX', 'CBOE Volatility Index futures', 0.05, 'FRED', null, null, null, true),

  -- Inactive DATABENTO — DO NOT QUERY (billing risk)
  ('BIO', 'BIO', 'BIO', 'BIO Futures', 0.01, 'DATABENTO', 'GLBX.MDP3', 'BIO.c.0', null, false),
  ('EMD', 'EMD', 'S&P Midcap', 'S&P MidCap 400 Futures', 0.1, 'DATABENTO', 'GLBX.MDP3', 'EMD.c.0', null, false),
  ('M2K', 'M2K', 'Micro Russell', 'Micro E-mini Russell 2000 Futures', 0.1, 'DATABENTO', 'GLBX.MDP3', 'M2K.c.0', null, false),
  ('MNQ', 'MNQ', 'Micro Nasdaq', 'Micro E-mini Nasdaq-100 Futures', 0.25, 'DATABENTO', 'GLBX.MDP3', 'MNQ.c.0', null, false),
  ('MYM', 'MYM', 'Micro Dow', 'Micro E-mini Dow Jones Futures', 1, 'DATABENTO', 'GLBX.MDP3', 'MYM.c.0', null, false),
  ('NIY', 'NIY', 'Nikkei USD', 'Nikkei 225 USD Futures', 5, 'DATABENTO', 'GLBX.MDP3', 'NIY.c.0', null, false),
  ('NKD', 'NKD', 'Nikkei JPY', 'Nikkei 225 JPY Futures', 5, 'DATABENTO', 'GLBX.MDP3', 'NKD.c.0', null, false),
  ('RS1', 'RS1', 'RS1', 'RS1 Futures', 0.01, 'DATABENTO', 'GLBX.MDP3', 'RS1.c.0', null, false),
  ('RSG', 'RSG', 'RSG', 'RSG Futures', 0.01, 'DATABENTO', 'GLBX.MDP3', 'RSG.c.0', null, false),
  ('RSV', 'RSV', 'RSV', 'RSV Futures', 0.01, 'DATABENTO', 'GLBX.MDP3', 'RSV.c.0', null, false),
  ('SXB', 'SXB', 'SX B', 'SX B Futures', 0.01, 'DATABENTO', 'GLBX.MDP3', 'SXB.c.0', null, false),
  ('SXI', 'SXI', 'SX I', 'SX I Futures', 0.01, 'DATABENTO', 'GLBX.MDP3', 'SXI.c.0', null, false),
  ('SXO', 'SXO', 'SX O', 'SX O Futures', 0.01, 'DATABENTO', 'GLBX.MDP3', 'SXO.c.0', null, false),
  ('SXR', 'SXR', 'SX R', 'SX R Futures', 0.01, 'DATABENTO', 'GLBX.MDP3', 'SXR.c.0', null, false),
  ('SXT', 'SXT', 'SX T', 'SX T Futures', 0.01, 'DATABENTO', 'GLBX.MDP3', 'SXT.c.0', null, false),
  ('XAB', 'XAB', 'XA B', 'XA B Futures', 0.01, 'DATABENTO', 'GLBX.MDP3', 'XAB.c.0', null, false),
  ('XAE', 'XAE', 'XA E', 'XA E Futures', 0.01, 'DATABENTO', 'GLBX.MDP3', 'XAE.c.0', null, false),
  ('XAF', 'XAF', 'XA F', 'XA F Futures', 0.01, 'DATABENTO', 'GLBX.MDP3', 'XAF.c.0', null, false),
  ('XAI', 'XAI', 'XA I', 'XA I Futures', 0.01, 'DATABENTO', 'GLBX.MDP3', 'XAI.c.0', null, false),
  ('XAK', 'XAK', 'XA K', 'XA K Futures', 0.01, 'DATABENTO', 'GLBX.MDP3', 'XAK.c.0', null, false),
  ('XAP', 'XAP', 'XA P', 'XA P Futures', 0.01, 'DATABENTO', 'GLBX.MDP3', 'XAP.c.0', null, false),
  ('XAR', 'XAR', 'XA R', 'XA R Futures', 0.01, 'DATABENTO', 'GLBX.MDP3', 'XAR.c.0', null, false),
  ('XAU', 'XAU', 'XA U', 'XA U Futures', 0.01, 'DATABENTO', 'GLBX.MDP3', 'XAU.c.0', null, false),
  ('XAV', 'XAV', 'XA V', 'XA V Futures', 0.01, 'DATABENTO', 'GLBX.MDP3', 'XAV.c.0', null, false),
  ('XAY', 'XAY', 'XA Y', 'XA Y Futures', 0.01, 'DATABENTO', 'GLBX.MDP3', 'XAY.c.0', null, false),
  ('XAZ', 'XAZ', 'XA Z', 'XA Z Futures', 0.01, 'DATABENTO', 'GLBX.MDP3', 'XAZ.c.0', null, false)
on conflict (code) do nothing;

-- ============================================================
-- SYMBOL ROLES
-- ============================================================

insert into symbol_roles (name, description) values
  ('PRIMARY', 'Primary trading instrument (MES)'),
  ('EQUITY_INDEX', 'Equity index futures'),
  ('TREASURY', 'Treasury/rate futures'),
  ('COMMODITY', 'Commodity futures'),
  ('FX', 'Foreign exchange futures'),
  ('VOLATILITY', 'Volatility instruments'),
  ('OPTIONS', 'Options on futures')
on conflict (name) do nothing;

insert into symbol_role_members (role_id, symbol_code)
select r.id, s.code from symbol_roles r, (values
  ('PRIMARY', 'MES')
) as s(role, code) where r.name = s.role
on conflict do nothing;

insert into symbol_role_members (role_id, symbol_code)
select r.id, s.code from symbol_roles r, (values
  ('EQUITY_INDEX', 'ES'), ('EQUITY_INDEX', 'NQ'), ('EQUITY_INDEX', 'YM'),
  ('EQUITY_INDEX', 'RTY'), ('EQUITY_INDEX', 'SOX')
) as s(role, code) where r.name = s.role
on conflict do nothing;

insert into symbol_role_members (role_id, symbol_code)
select r.id, s.code from symbol_roles r, (values
  ('TREASURY', 'ZN'), ('TREASURY', 'ZB'), ('TREASURY', 'ZF'),
  ('TREASURY', 'SR3'), ('TREASURY', 'US10Y')
) as s(role, code) where r.name = s.role
on conflict do nothing;

insert into symbol_role_members (role_id, symbol_code)
select r.id, s.code from symbol_roles r, (values
  ('COMMODITY', 'CL'), ('COMMODITY', 'GC'), ('COMMODITY', 'SI'), ('COMMODITY', 'NG')
) as s(role, code) where r.name = s.role
on conflict do nothing;

insert into symbol_role_members (role_id, symbol_code)
select r.id, s.code from symbol_roles r, (values
  ('FX', '6E'), ('FX', '6J'), ('FX', 'DX')
) as s(role, code) where r.name = s.role
on conflict do nothing;

insert into symbol_role_members (role_id, symbol_code)
select r.id, s.code from symbol_roles r, (values
  ('VOLATILITY', 'VX')
) as s(role, code) where r.name = s.role
on conflict do nothing;

insert into symbol_role_members (role_id, symbol_code)
select r.id, s.code from symbol_roles r, (values
  ('OPTIONS', 'ES.OPT'), ('OPTIONS', 'NQ.OPT'), ('OPTIONS', 'EUU.OPT'),
  ('OPTIONS', 'HXE.OPT'), ('OPTIONS', 'JPU.OPT'), ('OPTIONS', 'LO.OPT'),
  ('OPTIONS', 'OB.OPT'), ('OPTIONS', 'OG.OPT'), ('OPTIONS', 'OH.OPT'),
  ('OPTIONS', 'OKE.OPT'), ('OPTIONS', 'ON.OPT'), ('OPTIONS', 'OZB.OPT'),
  ('OPTIONS', 'OZF.OPT'), ('OPTIONS', 'OZN.OPT'), ('OPTIONS', 'SO.OPT')
) as s(role, code) where r.name = s.role
on conflict do nothing;

-- ============================================================
-- DATA SOURCES
-- ============================================================

insert into sources (name, description, base_url, api_key_env, is_active) values
  ('databento', 'Databento market data (Standard plan)', 'https://hist.databento.com/v0', 'DATABENTO_API_KEY', true),
  ('fred', 'Federal Reserve Economic Data', 'https://api.stlouisfed.org/fred', 'FRED_API_KEY', true),
  ('massive', 'Massive economy endpoints (inflation expectations)', 'https://api.massive.com/fed/v1', 'MASSIVE_API_KEY', true),
  ('federal_register', 'Federal Register API (free, no key)', 'https://www.federalregister.gov/api/v1', null, true),
  ('gpr', 'Caldara-Iacoviello Geopolitical Risk Index', 'https://www.matteoiacoviello.com/gpr_files', null, true)
on conflict (name) do nothing;

-- ============================================================
-- SERIES CATALOG (FRED series used for economic data)
-- ============================================================

insert into series_catalog (series_id, name, category, frequency, is_active) values
  -- Rates
  ('FEDFUNDS', 'Federal Funds Effective Rate', 'rates', 'daily', true),
  ('DFF', 'Federal Funds Rate (daily)', 'rates', 'daily', true),
  ('SOFR', 'Secured Overnight Financing Rate', 'rates', 'daily', true),

  -- Yields
  ('DGS2', '2-Year Treasury Yield', 'yields', 'daily', true),
  ('DGS5', '5-Year Treasury Yield', 'yields', 'daily', true),
  ('DGS10', '10-Year Treasury Yield', 'yields', 'daily', true),
  ('DGS30', '30-Year Treasury Yield', 'yields', 'daily', true),
  ('T10Y2Y', '10Y-2Y Treasury Spread', 'yields', 'daily', true),
  ('T10Y3M', '10Y-3M Treasury Spread', 'yields', 'daily', true),

  -- FX
  ('DTWEXBGS', 'Trade Weighted Dollar Index', 'fx', 'daily', true),
  ('DEXUSEU', 'USD/EUR Exchange Rate', 'fx', 'daily', true),
  ('DEXJPUS', 'JPY/USD Exchange Rate', 'fx', 'daily', true),

  -- Volatility
  ('VIXCLS', 'VIX Close', 'vol', 'daily', true),
  ('OVXCLS', 'Crude Oil ETF Volatility Index', 'vol', 'daily', true),

  -- Inflation
  ('CPIAUCSL', 'CPI All Urban Consumers', 'inflation', 'monthly', true),
  ('CPILFESL', 'Core CPI (ex Food & Energy)', 'inflation', 'monthly', true),
  ('T5YIE', '5-Year Breakeven Inflation (legacy FRED source)', 'inflation', 'daily', false),
  ('T10YIE', '10-Year Breakeven Inflation (legacy FRED source)', 'inflation', 'daily', false),

  -- Labor
  ('UNRATE', 'Unemployment Rate', 'labor', 'monthly', true),
  ('PAYEMS', 'Total Nonfarm Payrolls', 'labor', 'monthly', true),
  ('ICSA', 'Initial Jobless Claims', 'labor', 'weekly', true),
  ('CCSA', 'Continued Claims', 'labor', 'weekly', true),

  -- Activity
  ('INDPRO', 'Industrial Production Index', 'activity', 'monthly', true),
  ('RSXFS', 'Retail Sales ex Food Service', 'activity', 'monthly', true),
  ('DGORDER', 'Durable Goods Orders', 'activity', 'monthly', true),

  -- Money
  ('M2SL', 'M2 Money Supply', 'money', 'monthly', true),
  ('WALCL', 'Fed Balance Sheet Total Assets', 'money', 'weekly', true),

  -- Commodities
  ('DCOILWTICO', 'WTI Crude Oil Price', 'commodities', 'daily', true),
  ('GVZCLS', 'Gold ETF Volatility Index', 'commodities', 'daily', true),

  -- Indexes
  ('USEPUINDXD', 'Economic Policy Uncertainty (daily)', 'indexes', 'daily', true),
  ('BAMLH0A0HYM2', 'High Yield OAS Spread', 'indexes', 'daily', true),

  -- Volatility (additional)
  ('VXNCLS', 'Nasdaq-100 Volatility Index (VXN)', 'vol', 'daily', true),
  ('RVXCLS', 'Russell 2000 Volatility Index (RVX)', 'vol', 'daily', true),

  -- Credit spreads
  ('BAMLC0A0CM', 'ICE BofA IG Corporate OAS', 'indexes', 'daily', true),
  ('BAMLHYH0A0HYM2EY', 'ICE BofA HY Option-Adjusted Spread', 'indexes', 'daily', true),
  ('BAA10Y', 'Baa Corporate Bond Spread', 'yields', 'daily', true),

  -- Financial conditions
  ('NFCI', 'Chicago Fed National Financial Conditions Index', 'indexes', 'weekly', true),
  ('STLFSI4', 'St. Louis Fed Financial Stress Index', 'indexes', 'weekly', true),
  ('ANFCI', 'Adjusted NFCI', 'indexes', 'weekly', true),

  -- Consumer sentiment
  ('UMCSENT', 'University of Michigan Consumer Sentiment', 'indexes', 'monthly', true),

  -- Recession indicators
  ('RECPROUSM156N', 'Smoothed US Recession Probabilities', 'indexes', 'monthly', true),
  ('SAHMCURRENT', 'Sahm Rule Recession Indicator', 'indexes', 'monthly', true),

  -- Macro business cycle
  ('EMVMACROBUS', 'Equity Market Macro Business Cycle Uncertainty', 'indexes', 'daily', true)
on conflict (series_id) do nothing;
