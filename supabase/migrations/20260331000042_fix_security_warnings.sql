-- Migration 042: Fix security warnings + remove all news article infrastructure
--
-- Security fixes:
--   1. Set search_path on update_updated_at() trigger function
--
-- News removal (keeping FRED, GPR, Trump Effect, econ_calendar):
--   2. Unschedule finnhub + news_signals refresh crons
--   3. Drop functions: run_finnhub_raw_pull, refresh_news_signals
--   4. Drop materialized view: news_signals
--   5. Drop view: all_news_articles
--   6. Drop tables: econ_news_article_assessments, econ_news_finnhub_article_segments,
--      econ_news_finnhub_articles, econ_news_topics
--   7. Drop types: news_topic_family, news_extraction_status
--   8. Update get_admin_table_coverage() to remove news_signals reference

-- ============================================================
-- 1. Fix update_updated_at() search_path (security warning)
-- ============================================================

create or replace function update_updated_at()
returns trigger
language plpgsql
security invoker
set search_path = public
as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

-- ============================================================
-- 2. Unschedule news cron jobs
-- ============================================================

do $$
declare
  v_job_id bigint;
begin
  for v_job_id in
    select jobid from cron.job
    where jobname in ('warbird_finnhub_raw_pull', 'warbird_refresh_news_signals')
  loop
    perform cron.unschedule(v_job_id);
  end loop;
exception
  when undefined_table then null;
end $$;

-- ============================================================
-- 3. Drop news helper functions
-- ============================================================

drop function if exists public.run_finnhub_raw_pull();
drop function if exists public.refresh_news_signals();

-- ============================================================
-- 4. Drop news_signals materialized view
-- ============================================================

drop materialized view if exists news_signals;

-- ============================================================
-- 5. Drop all_news_articles view
-- ============================================================

drop view if exists all_news_articles;

-- ============================================================
-- 6. Drop news article tables (reverse FK order)
-- ============================================================

drop table if exists econ_news_article_assessments;
drop table if exists econ_news_finnhub_article_segments;
drop table if exists econ_news_finnhub_articles;
drop table if exists econ_news_topics;

-- ============================================================
-- 7. Drop news-only types
-- ============================================================

drop type if exists news_topic_family;
drop type if exists news_extraction_status;

-- ============================================================
-- 8. Update admin coverage function — remove news_signals, add cross_asset_15m
--    MUST match existing return type: table(table_name text, latest_ts timestamptz, row_count bigint)
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

comment on function public.get_admin_table_coverage() is
  'Admin coverage: row counts + latest timestamps. News tables removed 2026-03-31. cross_asset_15m added.';
