-- Migration 043: Rename trump_effect → executive_orders + drop 14 safe legacy tables
--
-- Part 1: Rename trump_effect_1d → executive_orders_1d (table, constraints, indexes, policy, cron, function)
-- Part 2: Drop 14 legacy tables with zero active consumers

-- ============================================================
-- PART 1: Rename trump_effect_1d → executive_orders_1d
-- ============================================================

-- Rename the table
alter table if exists trump_effect_1d rename to executive_orders_1d;

-- Rename constraints
alter index if exists trump_effect_1d_pkey rename to executive_orders_1d_pkey;
alter index if exists trump_effect_1d_ts_title_key rename to executive_orders_1d_ts_title_key;

-- Rename indexes
alter index if exists idx_trump_effect_ts rename to idx_executive_orders_ts;
alter index if exists idx_trump_effect_type rename to idx_executive_orders_type;

do $$ begin
  alter index uq_trump_effect_1d_ts_title rename to uq_executive_orders_1d_ts_title;
exception when undefined_object then null;
end $$;

-- Drop old RLS policy, create new one
do $$ begin
  if exists (select 1 from pg_policies where tablename = 'executive_orders_1d' and policyname = 'Authenticated read trump_effect_1d') then
    drop policy "Authenticated read trump_effect_1d" on executive_orders_1d;
  end if;
end $$;

create policy "Authenticated read executive_orders_1d"
  on executive_orders_1d for select to authenticated using (true);

-- Unschedule old cron job
do $$
declare v_job_id bigint;
begin
  for v_job_id in select jobid from cron.job where jobname = 'warbird_trump_effect_pull'
  loop perform cron.unschedule(v_job_id); end loop;
exception when undefined_table then null;
end $$;

-- Drop old function
drop function if exists public.run_trump_effect_pull();

-- Create renamed function
create or replace function public.run_exec_orders_pull()
returns void
language plpgsql
security definer
set search_path = public, extensions
as $$
declare
  v_base_url text;
  v_secret   text;
begin
  select decrypted_secret into v_base_url
  from vault.decrypted_secrets
  where name = 'warbird_edge_base_url'
  order by created_at desc limit 1;

  select decrypted_secret into v_secret
  from vault.decrypted_secrets
  where name = 'warbird_edge_cron_secret'
  order by created_at desc limit 1;

  if v_base_url is null or v_secret is null then
    raise notice 'Skipping run_exec_orders_pull: missing vault secrets.';
    return;
  end if;

  perform net.http_get(
    url     := v_base_url || '/exec-orders',
    headers := jsonb_build_object('x-cron-secret', v_secret),
    timeout_milliseconds := 55000
  );
end;
$$;

comment on function public.run_exec_orders_pull() is
  'Supabase cron worker: triggers Edge Function exec-orders daily at 08:00 UTC Mon-Fri.';

-- Schedule renamed cron job
select cron.schedule(
  'warbird_exec_orders_pull',
  '0 8 * * 1-5',
  $$select public.run_exec_orders_pull();$$
)
where not exists (
  select 1 from cron.job where jobname = 'warbird_exec_orders_pull'
);

-- ============================================================
-- PART 2: Drop 14 safe legacy tables (zero active consumers)
-- ============================================================

-- Empty legacy tables with zero consumers in app code
drop table if exists trade_scores cascade;
drop table if exists vol_states cascade;
drop table if exists models cascade;
drop table if exists sources cascade;
drop table if exists coverage_log cascade;
drop table if exists symbol_mappings cascade;

-- Offline-only backfill targets (scripts still exist but tables unused by app)
drop table if exists options_stats_1d cascade;
drop table if exists macro_reports_1d cascade;

-- Migration 018 backup tables (all empty)
drop table if exists warbird_setup_events_legacy_20260326 cascade;
drop table if exists warbird_setups_legacy_20260326 cascade;
drop table if exists warbird_conviction_legacy_20260326 cascade;
drop table if exists warbird_risk_legacy_20260326 cascade;
drop table if exists warbird_triggers_15m_legacy_20260326 cascade;
drop table if exists warbird_forecasts_1h_legacy_20260326 cascade;

-- ============================================================
-- PART 3: Update admin coverage to use new table name
-- ============================================================

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
    'warbird_triggers_15m',
    'warbird_conviction',
    'warbird_setups',
    'warbird_setup_events',
    'warbird_risk',
    'measured_moves',
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
    'executive_orders_1d'
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
