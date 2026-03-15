-- Migration 009: Supabase Realtime replication
-- Enable realtime on tables that push updates to the browser.
-- mes_1m: live 1m bar feed for chart intrabar updates
-- mes_15m: live 15m bar feed for chart primary display
-- warbird_setups: live setup state changes for chart markers
-- forecasts: live forecast updates for Pine Script API consumers

alter publication supabase_realtime add table mes_1m;
alter publication supabase_realtime add table mes_15m;
alter publication supabase_realtime add table warbird_setups;
alter publication supabase_realtime add table forecasts;
