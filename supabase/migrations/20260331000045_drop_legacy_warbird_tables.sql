-- Migration 045: Drop 9 remaining legacy warbird tables
--
-- These tables have no active writers, no active cron schedules, and contain
-- only stale or empty data. The canonical replacement is warbird_fib_candidates_15m +
-- warbird_candidate_outcomes_15m + warbird_admin_candidate_rows_v (migration 037+038).
--
-- Dropped:
--   warbird_setup_events (0 rows, FK depends on warbird_setups)
--   warbird_setups (0 rows, has realtime publication)
--   warbird_conviction (0 rows)
--   warbird_risk (0 rows)
--   warbird_triggers_15m (0 rows)
--   warbird_daily_bias (4 rows, no active writer)
--   warbird_structure_4h (12 rows, no active writer)
--   warbird_alert_events (1 row, not in any migration — orphaned)
--   measured_moves (76 rows, all stale from March 9-12, NULL setup_ids)

-- Remove warbird_setups from realtime publication before dropping
do $$
begin
  if exists (
    select 1 from pg_publication_tables
    where pubname = 'supabase_realtime' and tablename = 'warbird_setups'
  ) then
    execute 'alter publication supabase_realtime drop table warbird_setups';
  end if;
end $$;

-- Drop in FK-dependency order
drop table if exists warbird_setup_events cascade;
drop table if exists warbird_setups cascade;
drop table if exists warbird_conviction cascade;
drop table if exists warbird_risk cascade;
drop table if exists warbird_triggers_15m cascade;
drop table if exists warbird_daily_bias cascade;
drop table if exists warbird_structure_4h cascade;
drop table if exists warbird_alert_events cascade;
drop table if exists measured_moves cascade;

-- Update admin coverage to remove dropped tables
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
    'cross_asset_15m',
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
    'econ_calendar',
    'geopolitical_risk_1d',
    'executive_orders_1d',
    'warbird_fib_candidates_15m',
    'warbird_candidate_outcomes_15m',
    'warbird_signals_15m'
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
          from information_schema.columns cols
          where cols.table_schema = 'public'
            and cols.table_name = current_table
            and cols.column_name = 'bar_close_ts'
        ) then 'bar_close_ts'
        when exists (
          select 1
          from information_schema.columns cols
          where cols.table_schema = 'public'
            and cols.table_name = current_table
            and cols.column_name = 'ts'
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
