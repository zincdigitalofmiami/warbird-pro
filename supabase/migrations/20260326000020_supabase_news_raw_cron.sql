-- Migration 020: Supabase-owned raw news schedules for Newsfilter and Finnhub
--
-- Required Supabase secrets (Vault):
--   warbird_newsfilter_raw_cron_url -> full URL to /api/cron/newsfilter-news
--   warbird_finnhub_raw_cron_url    -> full URL to /api/cron/finnhub-news
--   warbird_newsfilter_api_key      -> Newsfilter API key
--   warbird_finnhub_api_key         -> Finnhub API key
--   warbird_cron_secret             -> CRON_SECRET value used by API route auth

create extension if not exists pg_cron;
create extension if not exists pg_net;

create or replace function public.run_newsfilter_raw_pull()
returns void
language plpgsql
security definer
set search_path = public, extensions
as $$
declare
  v_url text;
  v_secret text;
  v_provider_key text;
begin
  select decrypted_secret
    into v_url
  from vault.decrypted_secrets
  where name = 'warbird_newsfilter_raw_cron_url'
  order by created_at desc
  limit 1;

  select decrypted_secret
    into v_secret
  from vault.decrypted_secrets
  where name = 'warbird_cron_secret'
  order by created_at desc
  limit 1;

  select decrypted_secret
    into v_provider_key
  from vault.decrypted_secrets
  where name = 'warbird_newsfilter_api_key'
  order by created_at desc
  limit 1;

  if v_url is null or v_secret is null or v_provider_key is null then
    raise notice 'Skipping run_newsfilter_raw_pull: missing vault secrets warbird_newsfilter_raw_cron_url, warbird_newsfilter_api_key, or warbird_cron_secret.';
    return;
  end if;

  perform net.http_post(
    url := v_url,
    headers := jsonb_build_object(
      'authorization', 'Bearer ' || v_secret,
      'content-type', 'application/json',
      'x-provider-api-key', v_provider_key
    ),
    body := '{}'::jsonb
  );
end;
$$;

comment on function public.run_newsfilter_raw_pull() is
  'Supabase cron worker: triggers /api/cron/newsfilter-news using pg_net + vault secrets.';

create or replace function public.run_finnhub_raw_pull()
returns void
language plpgsql
security definer
set search_path = public, extensions
as $$
declare
  v_url text;
  v_secret text;
  v_provider_key text;
begin
  select decrypted_secret
    into v_url
  from vault.decrypted_secrets
  where name = 'warbird_finnhub_raw_cron_url'
  order by created_at desc
  limit 1;

  select decrypted_secret
    into v_secret
  from vault.decrypted_secrets
  where name = 'warbird_cron_secret'
  order by created_at desc
  limit 1;

  select decrypted_secret
    into v_provider_key
  from vault.decrypted_secrets
  where name = 'warbird_finnhub_api_key'
  order by created_at desc
  limit 1;

  if v_url is null or v_secret is null or v_provider_key is null then
    raise notice 'Skipping run_finnhub_raw_pull: missing vault secrets warbird_finnhub_raw_cron_url, warbird_finnhub_api_key, or warbird_cron_secret.';
    return;
  end if;

  perform net.http_post(
    url := v_url,
    headers := jsonb_build_object(
      'authorization', 'Bearer ' || v_secret,
      'content-type', 'application/json',
      'x-provider-api-key', v_provider_key
    ),
    body := '{}'::jsonb
  );
end;
$$;

comment on function public.run_finnhub_raw_pull() is
  'Supabase cron worker: triggers /api/cron/finnhub-news using pg_net + vault secrets.';

do $$
declare
  v_job_id bigint;
begin
  for v_job_id in
    select jobid
    from cron.job
    where jobname in ('warbird_newsfilter_raw_pull', 'warbird_finnhub_raw_pull')
  loop
    perform cron.unschedule(v_job_id);
  end loop;
exception
  when undefined_table then
    null;
end $$;

select cron.schedule(
  'warbird_newsfilter_raw_pull',
  '*/15 11-23 * * 1-5',
  $$select public.run_newsfilter_raw_pull();$$
)
where not exists (
  select 1
  from cron.job
  where jobname = 'warbird_newsfilter_raw_pull'
);

select cron.schedule(
  'warbird_finnhub_raw_pull',
  '5,20,35,50 11-23 * * 1-5',
  $$select public.run_finnhub_raw_pull();$$
)
where not exists (
  select 1
  from cron.job
  where jobname = 'warbird_finnhub_raw_pull'
);
