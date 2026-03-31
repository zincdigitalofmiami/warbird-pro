-- Migration 015: Supabase-owned minute MES pull schedule
-- Replaces Vercel-owned mes-catchup cadence with a lightweight 1m pull route.
--
-- Required Supabase secrets (Vault):
--   warbird_mes_1m_cron_url  -> full URL to /api/cron/mes-1m
--   warbird_cron_secret      -> CRON_SECRET value used by API route auth

create extension if not exists pg_cron;
create extension if not exists pg_net;
create extension if not exists supabase_vault;

create or replace function public.run_mes_1m_pull()
returns void
language plpgsql
security definer
set search_path = public, extensions
as $$
declare
  v_url text;
  v_secret text;
begin
  select decrypted_secret
    into v_url
  from vault.decrypted_secrets
  where name = 'warbird_mes_1m_cron_url'
  order by created_at desc
  limit 1;

  select decrypted_secret
    into v_secret
  from vault.decrypted_secrets
  where name = 'warbird_cron_secret'
  order by created_at desc
  limit 1;

  if v_url is null or v_secret is null then
    raise notice 'Skipping run_mes_1m_pull: missing vault secrets warbird_mes_1m_cron_url or warbird_cron_secret.';
    return;
  end if;

  perform net.http_post(
    url := v_url,
    headers := jsonb_build_object(
      'authorization', 'Bearer ' || v_secret,
      'content-type', 'application/json'
    ),
    body := '{}'::jsonb
  );
end;
$$;

comment on function public.run_mes_1m_pull() is
  'Supabase cron worker: triggers /api/cron/mes-1m every minute using pg_net + vault secrets.';

do $$
declare
  v_job_id bigint;
begin
  for v_job_id in
    select jobid
    from cron.job
    where jobname in ('warbird_mes_catchup', 'warbird_mes_1m_pull')
  loop
    perform cron.unschedule(v_job_id);
  end loop;
exception
  when undefined_table then
    null;
end $$;

select cron.schedule(
  'warbird_mes_1m_pull',
  '* * * * 0-5',
  $$select public.run_mes_1m_pull();$$
)
where not exists (
  select 1
  from cron.job
  where jobname = 'warbird_mes_1m_pull'
);
