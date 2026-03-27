-- Migration 031: econ-calendar Edge Function pg_cron schedule
-- Follows exact pattern from migration 023 (edge function cron cutover).
-- FRED_API_KEY must be set as an Edge Function secret in the Supabase dashboard.
--
-- Schedule: 04:20 UTC Mon-Fri — 20 min gap after the last Massive job (04:00).
--
-- Required Supabase Vault secrets (already exist from migration 023):
--   warbird_edge_base_url       -> https://qhwgrzqjcdtdqppvhhme.supabase.co/functions/v1
--   warbird_edge_cron_secret    -> value of EDGE_CRON_SECRET

create or replace function public.run_econ_calendar_pull()
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
    raise notice 'Skipping run_econ_calendar_pull: missing vault secrets warbird_edge_base_url or warbird_edge_cron_secret.';
    return;
  end if;

  perform net.http_get(
    url     := v_base_url || '/econ-calendar',
    headers := jsonb_build_object('x-cron-secret', v_secret),
    timeout_milliseconds := 55000
  );
end;
$$;

comment on function public.run_econ_calendar_pull() is
  'Supabase cron worker: triggers Edge Function econ-calendar daily at 04:20 UTC Mon-Fri.';

-- Remove stale version before scheduling
do $$
declare
  v_job_id bigint;
begin
  for v_job_id in
    select jobid from cron.job
    where jobname = 'warbird_econ_calendar'
  loop
    perform cron.unschedule(v_job_id);
  end loop;
exception
  when undefined_table then null;
end $$;

-- Schedule: 04:20 UTC Mon-Fri (20 min after last Massive job)
select cron.schedule(
  'warbird_econ_calendar',
  '20 4 * * 1-5',
  $$select public.run_econ_calendar_pull();$$
)
where not exists (
  select 1 from cron.job where jobname = 'warbird_econ_calendar'
);
