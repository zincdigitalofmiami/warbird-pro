-- Migration 008: Row Level Security
-- Rule: Authenticated users = SELECT only. Service role = all operations.
-- RLS enabled on ALL tables.

-- Helper: policy for authenticated SELECT
-- Service role bypasses RLS automatically in Supabase.

-- Symbols
alter table symbols enable row level security;
create policy "Authenticated read symbols" on symbols for select to authenticated using (true);

alter table symbol_roles enable row level security;
create policy "Authenticated read symbol_roles" on symbol_roles for select to authenticated using (true);

alter table symbol_role_members enable row level security;
create policy "Authenticated read symbol_role_members" on symbol_role_members for select to authenticated using (true);

alter table symbol_mappings enable row level security;
create policy "Authenticated read symbol_mappings" on symbol_mappings for select to authenticated using (true);

-- MES data
alter table mes_1m enable row level security;
create policy "Authenticated read mes_1m" on mes_1m for select to authenticated using (true);

alter table mes_15m enable row level security;
create policy "Authenticated read mes_15m" on mes_15m for select to authenticated using (true);

alter table mes_1h enable row level security;
create policy "Authenticated read mes_1h" on mes_1h for select to authenticated using (true);

alter table mes_4h enable row level security;
create policy "Authenticated read mes_4h" on mes_4h for select to authenticated using (true);

alter table mes_1d enable row level security;
create policy "Authenticated read mes_1d" on mes_1d for select to authenticated using (true);

-- Cross-asset
alter table cross_asset_1h enable row level security;
create policy "Authenticated read cross_asset_1h" on cross_asset_1h for select to authenticated using (true);

alter table cross_asset_1d enable row level security;
create policy "Authenticated read cross_asset_1d" on cross_asset_1d for select to authenticated using (true);

alter table options_stats_1d enable row level security;
create policy "Authenticated read options_stats_1d" on options_stats_1d for select to authenticated using (true);

alter table options_ohlcv_1d enable row level security;
create policy "Authenticated read options_ohlcv_1d" on options_ohlcv_1d for select to authenticated using (true);

-- Economic
alter table series_catalog enable row level security;
create policy "Authenticated read series_catalog" on series_catalog for select to authenticated using (true);

alter table econ_rates_1d enable row level security;
create policy "Authenticated read econ_rates_1d" on econ_rates_1d for select to authenticated using (true);

alter table econ_yields_1d enable row level security;
create policy "Authenticated read econ_yields_1d" on econ_yields_1d for select to authenticated using (true);

alter table econ_fx_1d enable row level security;
create policy "Authenticated read econ_fx_1d" on econ_fx_1d for select to authenticated using (true);

alter table econ_vol_1d enable row level security;
create policy "Authenticated read econ_vol_1d" on econ_vol_1d for select to authenticated using (true);

alter table econ_inflation_1d enable row level security;
create policy "Authenticated read econ_inflation_1d" on econ_inflation_1d for select to authenticated using (true);

alter table econ_labor_1d enable row level security;
create policy "Authenticated read econ_labor_1d" on econ_labor_1d for select to authenticated using (true);

alter table econ_activity_1d enable row level security;
create policy "Authenticated read econ_activity_1d" on econ_activity_1d for select to authenticated using (true);

alter table econ_money_1d enable row level security;
create policy "Authenticated read econ_money_1d" on econ_money_1d for select to authenticated using (true);

alter table econ_commodities_1d enable row level security;
create policy "Authenticated read econ_commodities_1d" on econ_commodities_1d for select to authenticated using (true);

alter table econ_indexes_1d enable row level security;
create policy "Authenticated read econ_indexes_1d" on econ_indexes_1d for select to authenticated using (true);

-- News & events
alter table econ_news_1d enable row level security;
create policy "Authenticated read econ_news_1d" on econ_news_1d for select to authenticated using (true);

alter table policy_news_1d enable row level security;
create policy "Authenticated read policy_news_1d" on policy_news_1d for select to authenticated using (true);

alter table macro_reports_1d enable row level security;
create policy "Authenticated read macro_reports_1d" on macro_reports_1d for select to authenticated using (true);

alter table econ_calendar enable row level security;
create policy "Authenticated read econ_calendar" on econ_calendar for select to authenticated using (true);

alter table news_signals enable row level security;
create policy "Authenticated read news_signals" on news_signals for select to authenticated using (true);

alter table geopolitical_risk_1d enable row level security;
create policy "Authenticated read geopolitical_risk_1d" on geopolitical_risk_1d for select to authenticated using (true);

alter table trump_effect_1d enable row level security;
create policy "Authenticated read trump_effect_1d" on trump_effect_1d for select to authenticated using (true);

-- Trading engine
alter table warbird_setups enable row level security;
create policy "Authenticated read warbird_setups" on warbird_setups for select to authenticated using (true);

alter table trade_scores enable row level security;
create policy "Authenticated read trade_scores" on trade_scores for select to authenticated using (true);

alter table measured_moves enable row level security;
create policy "Authenticated read measured_moves" on measured_moves for select to authenticated using (true);

alter table vol_states enable row level security;
create policy "Authenticated read vol_states" on vol_states for select to authenticated using (true);

alter table forecasts enable row level security;
create policy "Authenticated read forecasts" on forecasts for select to authenticated using (true);

alter table sources enable row level security;
create policy "Authenticated read sources" on sources for select to authenticated using (true);

alter table coverage_log enable row level security;
create policy "Authenticated read coverage_log" on coverage_log for select to authenticated using (true);

alter table job_log enable row level security;
create policy "Authenticated read job_log" on job_log for select to authenticated using (true);

alter table models enable row level security;
create policy "Authenticated read models" on models for select to authenticated using (true);
