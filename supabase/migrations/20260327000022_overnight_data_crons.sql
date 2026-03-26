-- Migration 022: Overnight data cron schedules + series_catalog registrations
-- Schedules 17 new pg_cron jobs using net.http_get() (all new routes are GET-only).
--
-- Required Supabase Vault secrets (create before applying this migration):
--   warbird_mes_hourly_cron_url   -> https://warbird-pro.vercel.app/api/cron/mes-hourly
--   warbird_cross_asset_cron_url  -> https://warbird-pro.vercel.app/api/cron/cross-asset
--   warbird_fred_cron_base_url    -> https://warbird-pro.vercel.app/api/cron/fred
--   warbird_massive_cron_base_url -> https://warbird-pro.vercel.app/api/cron/massive
--   warbird_cron_secret           -> (already exists)

create extension if not exists pg_cron;
create extension if not exists pg_net;
create extension if not exists vault;

-- ---------------------------------------------------------------------------
-- series_catalog: register 13 new FRED series + 6 Massive inflation series
-- ---------------------------------------------------------------------------

insert into series_catalog (series_id, name, category, frequency, is_active) values
  -- FRED yields (7 new maturities not yet in catalog)
  ('DGS1MO', '1-Month Treasury Yield',          'yields',    'daily',   true),
  ('DGS3MO', '3-Month Treasury Yield',           'yields',    'daily',   true),
  ('DGS6MO', '6-Month Treasury Yield',           'yields',    'daily',   true),
  ('DGS1',   '1-Year Treasury Yield',            'yields',    'daily',   true),
  ('DGS3',   '3-Year Treasury Yield',            'yields',    'daily',   true),
  ('DGS7',   '7-Year Treasury Yield',            'yields',    'daily',   true),
  ('DGS20',  '20-Year Treasury Yield',           'yields',    'daily',   true),
  -- FRED inflation (3 new PCE series)
  ('PCEPI',          'PCE Price Index',                             'inflation', 'monthly', true),
  ('PCEPILFE',       'Core PCE Price Index',                        'inflation', 'monthly', true),
  ('PCE',            'Personal Consumption Expenditures ($B)',      'inflation', 'monthly', true),
  -- FRED labor (3 new series; UNRATE already in catalog)
  ('CIVPART',        'Labor Force Participation Rate',              'labor',     'monthly', true),
  ('CES0500000003',  'Avg Hourly Earnings All Private',             'labor',     'monthly', true),
  ('JTSJOL',         'Job Openings JOLTS',                          'labor',     'monthly', true),
  -- Massive inflation series (6 fields from /fed/v1/inflation)
  ('MASSIVE_CPI',          'CPI All Urban Consumers (Massive)',      'inflation', 'monthly', true),
  ('MASSIVE_CPI_CORE',     'Core CPI ex food/energy (Massive)',      'inflation', 'monthly', true),
  ('MASSIVE_CPI_YOY',      'CPI Year-over-Year % (Massive)',         'inflation', 'monthly', true),
  ('MASSIVE_PCE',          'PCE Price Index (Massive)',               'inflation', 'monthly', true),
  ('MASSIVE_PCE_CORE',     'Core PCE Price Index (Massive)',          'inflation', 'monthly', true),
  ('MASSIVE_PCE_SPENDING', 'Nominal PCE Spending $B (Massive)',       'inflation', 'monthly', true)
on conflict (series_id) do nothing;

-- ---------------------------------------------------------------------------
-- SQL helper functions (parameterized to avoid 1-function-per-job duplication)
-- ---------------------------------------------------------------------------

-- MES hourly aggregation (keeps mes_1h, mes_4h, mes_1d current)
create or replace function public.run_mes_hourly_pull()
returns void
language plpgsql
security definer
set search_path = public, extensions
as $$
declare
  v_url    text;
  v_secret text;
begin
  select decrypted_secret into v_url
  from vault.decrypted_secrets
  where name = 'warbird_mes_hourly_cron_url'
  order by created_at desc limit 1;

  select decrypted_secret into v_secret
  from vault.decrypted_secrets
  where name = 'warbird_cron_secret'
  order by created_at desc limit 1;

  if v_url is null or v_secret is null then
    raise notice 'Skipping run_mes_hourly_pull: missing vault secrets warbird_mes_hourly_cron_url or warbird_cron_secret.';
    return;
  end if;

  perform net.http_get(
    url     := v_url,
    params  := '{}'::jsonb,
    headers := jsonb_build_object('authorization', 'Bearer ' || v_secret),
    timeout_milliseconds := 55000
  );
end;
$$;

comment on function public.run_mes_hourly_pull() is
  'Supabase cron worker: triggers /api/cron/mes-hourly at :05 past every hour (Sun-Fri).';

-- Cross-asset Databento (sharded: shard=0..3)
create or replace function public.run_cross_asset_pull(p_shard int)
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
  where name = 'warbird_cross_asset_cron_url'
  order by created_at desc limit 1;

  select decrypted_secret into v_secret
  from vault.decrypted_secrets
  where name = 'warbird_cron_secret'
  order by created_at desc limit 1;

  if v_base_url is null or v_secret is null then
    raise notice 'Skipping run_cross_asset_pull(shard=%): missing vault secrets warbird_cross_asset_cron_url or warbird_cron_secret.', p_shard;
    return;
  end if;

  perform net.http_get(
    url     := v_base_url || '?shard=' || p_shard::text,
    params  := '{}'::jsonb,
    headers := jsonb_build_object('authorization', 'Bearer ' || v_secret),
    timeout_milliseconds := 55000
  );
end;
$$;

comment on function public.run_cross_asset_pull(int) is
  'Supabase cron worker: triggers /api/cron/cross-asset?shard=N for overnight Databento pulls.';

-- FRED category pull (parameterized: category text matches /api/cron/fred/[category])
create or replace function public.run_fred_pull(p_category text)
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
  where name = 'warbird_fred_cron_base_url'
  order by created_at desc limit 1;

  select decrypted_secret into v_secret
  from vault.decrypted_secrets
  where name = 'warbird_cron_secret'
  order by created_at desc limit 1;

  if v_base_url is null or v_secret is null then
    raise notice 'Skipping run_fred_pull(category=%): missing vault secrets warbird_fred_cron_base_url or warbird_cron_secret.', p_category;
    return;
  end if;

  perform net.http_get(
    url     := v_base_url || '/' || p_category,
    params  := '{}'::jsonb,
    headers := jsonb_build_object('authorization', 'Bearer ' || v_secret),
    timeout_milliseconds := 55000
  );
end;
$$;

comment on function public.run_fred_pull(text) is
  'Supabase cron worker: triggers /api/cron/fred/<category> for overnight FRED pulls.';

-- Massive economy pull (parameterized: endpoint text, e.g. "inflation")
create or replace function public.run_massive_pull(p_endpoint text)
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
  where name = 'warbird_massive_cron_base_url'
  order by created_at desc limit 1;

  select decrypted_secret into v_secret
  from vault.decrypted_secrets
  where name = 'warbird_cron_secret'
  order by created_at desc limit 1;

  if v_base_url is null or v_secret is null then
    raise notice 'Skipping run_massive_pull(endpoint=%): missing vault secrets warbird_massive_cron_base_url or warbird_cron_secret.', p_endpoint;
    return;
  end if;

  perform net.http_get(
    url     := v_base_url || '/' || p_endpoint,
    params  := '{}'::jsonb,
    headers := jsonb_build_object('authorization', 'Bearer ' || v_secret),
    timeout_milliseconds := 55000
  );
end;
$$;

comment on function public.run_massive_pull(text) is
  'Supabase cron worker: triggers /api/cron/massive/<endpoint> for overnight Massive economy pulls.';

-- ---------------------------------------------------------------------------
-- Remove any stale versions of these jobs before (re)scheduling
-- ---------------------------------------------------------------------------

do $$
declare
  v_job_id bigint;
begin
  for v_job_id in
    select jobid from cron.job
    where jobname in (
      'warbird_mes_hourly_pull',
      'warbird_cross_asset_s0',
      'warbird_cross_asset_s1',
      'warbird_cross_asset_s2',
      'warbird_cross_asset_s3',
      'warbird_fred_rates',
      'warbird_fred_yields',
      'warbird_fred_vol',
      'warbird_fred_inflation',
      'warbird_fred_fx',
      'warbird_fred_labor',
      'warbird_fred_activity',
      'warbird_fred_money',
      'warbird_fred_commodities',
      'warbird_fred_indexes',
      'warbird_massive_inflation',
      'warbird_massive_ie'
    )
  loop
    perform cron.unschedule(v_job_id);
  end loop;
exception
  when undefined_table then null;
end $$;

-- ---------------------------------------------------------------------------
-- Schedule 17 jobs
-- ---------------------------------------------------------------------------

-- MES hourly aggregation: :05 past every hour, Sun-Fri
select cron.schedule(
  'warbird_mes_hourly_pull',
  '5 * * * 0-5',
  $$select public.run_mes_hourly_pull();$$
)
where not exists (
  select 1 from cron.job where jobname = 'warbird_mes_hourly_pull'
);

-- Cross-asset shards: 02:00-02:30 UTC, Mon-Fri, 10 min apart
select cron.schedule(
  'warbird_cross_asset_s0',
  '0 2 * * 1-5',
  $$select public.run_cross_asset_pull(0);$$
)
where not exists (
  select 1 from cron.job where jobname = 'warbird_cross_asset_s0'
);

select cron.schedule(
  'warbird_cross_asset_s1',
  '10 2 * * 1-5',
  $$select public.run_cross_asset_pull(1);$$
)
where not exists (
  select 1 from cron.job where jobname = 'warbird_cross_asset_s1'
);

select cron.schedule(
  'warbird_cross_asset_s2',
  '20 2 * * 1-5',
  $$select public.run_cross_asset_pull(2);$$
)
where not exists (
  select 1 from cron.job where jobname = 'warbird_cross_asset_s2'
);

select cron.schedule(
  'warbird_cross_asset_s3',
  '30 2 * * 1-5',
  $$select public.run_cross_asset_pull(3);$$
)
where not exists (
  select 1 from cron.job where jobname = 'warbird_cross_asset_s3'
);

-- FRED categories: 02:45-04:15 UTC, Mon-Fri, 10 min apart
select cron.schedule(
  'warbird_fred_rates',
  '45 2 * * 1-5',
  $$select public.run_fred_pull('rates');$$
)
where not exists (
  select 1 from cron.job where jobname = 'warbird_fred_rates'
);

select cron.schedule(
  'warbird_fred_yields',
  '55 2 * * 1-5',
  $$select public.run_fred_pull('yields');$$
)
where not exists (
  select 1 from cron.job where jobname = 'warbird_fred_yields'
);

select cron.schedule(
  'warbird_fred_vol',
  '5 3 * * 1-5',
  $$select public.run_fred_pull('vol');$$
)
where not exists (
  select 1 from cron.job where jobname = 'warbird_fred_vol'
);

select cron.schedule(
  'warbird_fred_inflation',
  '15 3 * * 1-5',
  $$select public.run_fred_pull('inflation');$$
)
where not exists (
  select 1 from cron.job where jobname = 'warbird_fred_inflation'
);

select cron.schedule(
  'warbird_fred_fx',
  '25 3 * * 1-5',
  $$select public.run_fred_pull('fx');$$
)
where not exists (
  select 1 from cron.job where jobname = 'warbird_fred_fx'
);

select cron.schedule(
  'warbird_fred_labor',
  '35 3 * * 1-5',
  $$select public.run_fred_pull('labor');$$
)
where not exists (
  select 1 from cron.job where jobname = 'warbird_fred_labor'
);

select cron.schedule(
  'warbird_fred_activity',
  '45 3 * * 1-5',
  $$select public.run_fred_pull('activity');$$
)
where not exists (
  select 1 from cron.job where jobname = 'warbird_fred_activity'
);

select cron.schedule(
  'warbird_fred_money',
  '55 3 * * 1-5',
  $$select public.run_fred_pull('money');$$
)
where not exists (
  select 1 from cron.job where jobname = 'warbird_fred_money'
);

select cron.schedule(
  'warbird_fred_commodities',
  '5 4 * * 1-5',
  $$select public.run_fred_pull('commodities');$$
)
where not exists (
  select 1 from cron.job where jobname = 'warbird_fred_commodities'
);

select cron.schedule(
  'warbird_fred_indexes',
  '15 4 * * 1-5',
  $$select public.run_fred_pull('indexes');$$
)
where not exists (
  select 1 from cron.job where jobname = 'warbird_fred_indexes'
);

-- Massive economy: 04:30-04:40 UTC, Mon-Fri, 10 min apart
select cron.schedule(
  'warbird_massive_inflation',
  '30 4 * * 1-5',
  $$select public.run_massive_pull('inflation');$$
)
where not exists (
  select 1 from cron.job where jobname = 'warbird_massive_inflation'
);

select cron.schedule(
  'warbird_massive_ie',
  '40 4 * * 1-5',
  $$select public.run_massive_pull('inflation-expectations');$$
)
where not exists (
  select 1 from cron.job where jobname = 'warbird_massive_ie'
);
