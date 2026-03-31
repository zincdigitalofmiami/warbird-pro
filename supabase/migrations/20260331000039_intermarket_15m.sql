-- Migration 039: Intermarket 15m training data surface
-- Adds HG (Copper) to symbols table and creates cross_asset_15m for AG training.
-- AG training basket: NQ, RTY, CL, HG, 6E, 6J — all CME Globex (GLBX.MDP3).

-- 1. Add HG (Copper) to symbols — missing from original seed
insert into symbols (code, display_name, short_name, description, tick_size, data_source, dataset, databento_symbol, fred_symbol, is_active)
values ('HG', 'HG', 'Copper', 'Copper Futures (COMEX)', 0.0005, 'DATABENTO', 'GLBX.MDP3', 'HG.c.0', null, true)
on conflict (code) do nothing;

-- Add HG to COMMODITY role (if role exists)
insert into symbol_role_members (role_id, symbol_code)
select id, 'HG' from symbol_roles where name = 'COMMODITY'
on conflict do nothing;

-- 2. Create cross_asset_15m table for AG training data
create table if not exists cross_asset_15m (
  ts          timestamptz not null,
  symbol_code text        not null references symbols(code),
  open        numeric     not null,
  high        numeric     not null,
  low         numeric     not null,
  close       numeric     not null,
  volume      bigint      not null default 0,
  created_at  timestamptz not null default now(),
  primary key (ts, symbol_code)
);

create index if not exists idx_cross_asset_15m_sym_ts on cross_asset_15m (symbol_code, ts desc);

-- RLS: authenticated read, service role bypasses automatically
alter table cross_asset_15m enable row level security;
create policy "Authenticated read cross_asset_15m"
  on cross_asset_15m for select to authenticated using (true);
