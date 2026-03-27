-- Migration 023: Edge Function cron cutover
-- Updates pg_cron helper functions to call Supabase Edge Functions instead of Vercel.
-- Auth: x-cron-secret header (validated against EDGE_CRON_SECRET Function secret).
--
-- Required Supabase Vault secrets (create before applying this migration):
--   warbird_edge_cron_secret           -> value of EDGE_CRON_SECRET (set as Function secret too)
--   warbird_edge_base_url              -> https://qhwgrzqjcdtdqppvhhme.supabase.co/functions/v1
--
-- The following old Vault secrets are superseded but can remain:
--   warbird_mes_1m_cron_url            (was Vercel URL — no longer used after this migration)
--   warbird_mes_hourly_cron_url        (was Vercel URL — no longer used after this migration)
--   warbird_cross_asset_cron_url       (was Vercel URL — no longer used after this migration)
--   warbird_fred_cron_base_url         (was Vercel URL — no longer used after this migration)
--   warbird_massive_cron_base_url      (was Vercel URL — no longer used after this migration)
--   warbird_newsfilter_raw_cron_url    (was Vercel URL — no longer used after this migration)
--   warbird_finnhub_raw_cron_url       (was Vercel URL — no longer used after this migration)
--   warbird_cron_secret                (was used by Vercel routes — no longer needed here)
--
-- Edge Function secrets (set via Supabase dashboard → Edge Functions → Secrets):
--   EDGE_CRON_SECRET        -> same value as warbird_edge_cron_secret
--   DATABENTO_API_KEY       -> Databento API key
--   FRED_API_KEY            -> FRED API key
--   MASSIVE_API_KEY         -> Massive Economy API key
--   NEWSFILTER_API_KEY      -> Newsfilter API key
--   FINNHUB_API_KEY         -> Finnhub API key

create extension if not exists pg_cron;
create extension if not exists pg_net;
create extension if not exists supabase_vault;

-- ---------------------------------------------------------------------------
-- MES 1m pull — update to call Edge Function
-- ---------------------------------------------------------------------------

create or replace function public.run_mes_1m_pull()
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
    raise notice 'Skipping run_mes_1m_pull: missing vault secrets warbird_edge_base_url or warbird_edge_cron_secret.';
    return;
  end if;

  perform net.http_post(
    url     := v_base_url || '/mes-1m',
    headers := jsonb_build_object(
      'x-cron-secret', v_secret,
      'content-type', 'application/json'
    ),
    body    := '{}'::jsonb,
    timeout_milliseconds := 55000
  );
end;
$$;

comment on function public.run_mes_1m_pull() is
  'Supabase cron worker: triggers Edge Function mes-1m every minute (Sun-Fri).';

-- ---------------------------------------------------------------------------
-- MES hourly pull — update to call Edge Function
-- ---------------------------------------------------------------------------

create or replace function public.run_mes_hourly_pull()
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
    raise notice 'Skipping run_mes_hourly_pull: missing vault secrets warbird_edge_base_url or warbird_edge_cron_secret.';
    return;
  end if;

  perform net.http_get(
    url     := v_base_url || '/mes-hourly',
    params  := '{}'::jsonb,
    headers := jsonb_build_object('x-cron-secret', v_secret),
    timeout_milliseconds := 55000
  );
end;
$$;

comment on function public.run_mes_hourly_pull() is
  'Supabase cron worker: triggers Edge Function mes-hourly at :05 past every hour (Sun-Fri).';

-- ---------------------------------------------------------------------------
-- Cross-asset pull — update to call Edge Function
-- ---------------------------------------------------------------------------

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
  where name = 'warbird_edge_base_url'
  order by created_at desc limit 1;

  select decrypted_secret into v_secret
  from vault.decrypted_secrets
  where name = 'warbird_edge_cron_secret'
  order by created_at desc limit 1;

  if v_base_url is null or v_secret is null then
    raise notice 'Skipping run_cross_asset_pull(shard=%): missing vault secrets warbird_edge_base_url or warbird_edge_cron_secret.', p_shard;
    return;
  end if;

  perform net.http_get(
    url     := v_base_url || '/cross-asset?shard=' || p_shard::text,
    params  := '{}'::jsonb,
    headers := jsonb_build_object('x-cron-secret', v_secret),
    timeout_milliseconds := 55000
  );
end;
$$;

comment on function public.run_cross_asset_pull(int) is
  'Supabase cron worker: triggers Edge Function cross-asset?shard=N for overnight Databento pulls.';

-- ---------------------------------------------------------------------------
-- FRED pull — update to call Edge Function (category is now a query param)
-- ---------------------------------------------------------------------------

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
  where name = 'warbird_edge_base_url'
  order by created_at desc limit 1;

  select decrypted_secret into v_secret
  from vault.decrypted_secrets
  where name = 'warbird_edge_cron_secret'
  order by created_at desc limit 1;

  if v_base_url is null or v_secret is null then
    raise notice 'Skipping run_fred_pull(category=%): missing vault secrets warbird_edge_base_url or warbird_edge_cron_secret.', p_category;
    return;
  end if;

  perform net.http_get(
    url     := v_base_url || '/fred?category=' || p_category,
    params  := '{}'::jsonb,
    headers := jsonb_build_object('x-cron-secret', v_secret),
    timeout_milliseconds := 55000
  );
end;
$$;

comment on function public.run_fred_pull(text) is
  'Supabase cron worker: triggers Edge Function fred?category=<category> for overnight FRED pulls.';

-- ---------------------------------------------------------------------------
-- Massive pull — two dedicated Edge Functions (no base_url concat)
-- ---------------------------------------------------------------------------

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
  where name = 'warbird_edge_base_url'
  order by created_at desc limit 1;

  select decrypted_secret into v_secret
  from vault.decrypted_secrets
  where name = 'warbird_edge_cron_secret'
  order by created_at desc limit 1;

  if v_base_url is null or v_secret is null then
    raise notice 'Skipping run_massive_pull(endpoint=%): missing vault secrets warbird_edge_base_url or warbird_edge_cron_secret.', p_endpoint;
    return;
  end if;

  -- Edge Functions: massive-inflation and massive-inflation-expectations (named with full endpoint)
  perform net.http_get(
    url     := v_base_url || '/massive-' || p_endpoint,
    params  := '{}'::jsonb,
    headers := jsonb_build_object('x-cron-secret', v_secret),
    timeout_milliseconds := 55000
  );
end;
$$;

comment on function public.run_massive_pull(text) is
  'Supabase cron worker: triggers Edge Function massive-<endpoint> for overnight Massive economy pulls.';

-- ---------------------------------------------------------------------------
-- Newsfilter raw pull — update to call Edge Function (no provider key header)
-- ---------------------------------------------------------------------------

create or replace function public.run_newsfilter_raw_pull()
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
    raise notice 'Skipping run_newsfilter_raw_pull: missing vault secrets warbird_edge_base_url or warbird_edge_cron_secret.';
    return;
  end if;

  -- API key is now a Function secret (NEWSFILTER_API_KEY) — no x-provider-api-key header needed
  perform net.http_post(
    url     := v_base_url || '/newsfilter-news',
    headers := jsonb_build_object(
      'x-cron-secret', v_secret,
      'content-type', 'application/json'
    ),
    body    := '{}'::jsonb,
    timeout_milliseconds := 55000
  );
end;
$$;

comment on function public.run_newsfilter_raw_pull() is
  'Supabase cron worker: triggers Edge Function newsfilter-news using pg_net.';

-- ---------------------------------------------------------------------------
-- Finnhub raw pull — update to call Edge Function (no provider key header)
-- ---------------------------------------------------------------------------

create or replace function public.run_finnhub_raw_pull()
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
    raise notice 'Skipping run_finnhub_raw_pull: missing vault secrets warbird_edge_base_url or warbird_edge_cron_secret.';
    return;
  end if;

  -- API key is now a Function secret (FINNHUB_API_KEY) — no x-provider-api-key header needed
  perform net.http_post(
    url     := v_base_url || '/finnhub-news',
    headers := jsonb_build_object(
      'x-cron-secret', v_secret,
      'content-type', 'application/json'
    ),
    body    := '{}'::jsonb,
    timeout_milliseconds := 55000
  );
end;
$$;

comment on function public.run_finnhub_raw_pull() is
  'Supabase cron worker: triggers Edge Function finnhub-news using pg_net.';
