-- Migration 021: repair admin coverage RPC for mixed ts/bar_close_ts tables after 15m cutover.

begin;

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
  table_oid regclass;
  latest_column text;
begin
  foreach current_table in array table_names loop
    table_oid := to_regclass(format('public.%I', current_table));
    latest_ts := null;
    row_count := 0;
    latest_column := null;

    if table_oid is not null then
      select case
        when exists (
          select 1
          from information_schema.columns
          where table_schema = 'public'
            and table_name = current_table
            and column_name = 'bar_close_ts'
        ) then 'bar_close_ts'
        when exists (
          select 1
          from information_schema.columns
          where table_schema = 'public'
            and table_name = current_table
            and column_name = 'ts'
        ) then 'ts'
        else null
      end
        into latest_column;

      if latest_column is not null then
        execute format(
          'select %I from public.%I order by %I desc limit 1',
          latest_column,
          current_table,
          latest_column
        )
          into latest_ts;
      end if;

      select greatest(c.reltuples, 0)::bigint
        into row_count
        from pg_class c
       where c.oid = table_oid
       limit 1;
    end if;

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
  'Authenticated admin coverage helper that tolerates mixed ts/bar_close_ts schemas and missing retired tables.';

commit;
