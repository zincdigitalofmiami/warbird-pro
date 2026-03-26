-- Migration 016: cost guardrails, dedup constraints, and admin coverage RPC

begin;

delete from econ_calendar a
using econ_calendar b
where a.id > b.id
  and a.ts = b.ts
  and a.event_name = b.event_name;

create unique index if not exists uq_econ_calendar_ts_event_name
  on econ_calendar (ts, event_name);

create unique index if not exists uq_news_signals_ts_signal_type
  on news_signals (ts, signal_type);

create unique index if not exists uq_trump_effect_1d_ts_title
  on trump_effect_1d (ts, title);

create or replace function public.get_admin_table_coverage()
returns table(table_name text, latest_ts timestamptz, row_count bigint)
language plpgsql
security definer
set search_path = public, pg_catalog
as $$
declare
  table_names text[] := array[
    'mes_1m',
    'mes_15m',
    'mes_1h',
    'mes_4h',
    'mes_1d',
    'cross_asset_1h',
    'cross_asset_1d',
    'warbird_daily_bias',
    'warbird_structure_4h',
    'warbird_forecasts_1h',
    'warbird_triggers_15m',
    'warbird_conviction',
    'warbird_setups',
    'warbird_setup_events',
    'warbird_risk',
    'measured_moves',
    'vol_states',
    'trade_scores',
    'econ_rates_1d',
    'econ_yields_1d',
    'econ_fx_1d',
    'econ_vol_1d',
    'econ_inflation_1d',
    'econ_labor_1d',
    'econ_activity_1d',
    'econ_money_1d',
    'econ_commodities_1d',
    'econ_indexes_1d',
    'econ_news_1d',
    'policy_news_1d',
    'macro_reports_1d',
    'econ_calendar',
    'news_signals',
    'geopolitical_risk_1d',
    'trump_effect_1d'
  ];
  current_table text;
begin
  foreach current_table in array table_names loop
    execute format('select ts from public.%I order by ts desc limit 1', current_table)
      into latest_ts;

    select greatest(c.reltuples, 0)::bigint
      into row_count
      from pg_class c
      join pg_namespace n on n.oid = c.relnamespace
     where n.nspname = 'public'
       and c.relname = current_table
     limit 1;

    table_name := current_table;
    row_count := coalesce(row_count, 0);
    return next;
  end loop;
end;
$$;

revoke all on function public.get_admin_table_coverage() from public;
grant execute on function public.get_admin_table_coverage() to authenticated;
grant execute on function public.get_admin_table_coverage() to service_role;

comment on function public.get_admin_table_coverage() is
  'Authenticated admin coverage helper using indexed latest-ts lookups and approximate row counts.';

commit;
