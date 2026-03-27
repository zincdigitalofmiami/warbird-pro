-- Migration 027: GPR + Trump Effect Edge Function cron schedules
-- Follows exact pattern from migration 023 (edge function cron cutover).
-- Both APIs are free and require no API keys.
--
-- GPR: Caldara-Iacoviello daily index from public XLS file
-- Trump Effect: Federal Register executive orders + memoranda
--
-- Required Supabase Vault secrets (already exist from migration 023):
--   warbird_edge_base_url       -> https://qhwgrzqjcdtdqppvhhme.supabase.co/functions/v1
--   warbird_edge_cron_secret    -> value of EDGE_CRON_SECRET

-- ---------------------------------------------------------------------------
-- GPR helper function
-- ---------------------------------------------------------------------------

create or replace function public.run_gpr_pull()
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
    raise notice 'Skipping run_gpr_pull: missing vault secrets warbird_edge_base_url or warbird_edge_cron_secret.';
    return;
  end if;

  perform net.http_post(
    url     := v_base_url || '/gpr',
    headers := jsonb_build_object(
      'x-cron-secret', v_secret,
      'content-type', 'application/json'
    ),
    body    := '{}'::jsonb,
    timeout_milliseconds := 55000
  );
end;
$$;

comment on function public.run_gpr_pull() is
  'Supabase cron worker: triggers Edge Function gpr daily at 19:00 UTC Mon-Fri.';

-- ---------------------------------------------------------------------------
-- Trump Effect helper function
-- ---------------------------------------------------------------------------

create or replace function public.run_trump_effect_pull()
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
    raise notice 'Skipping run_trump_effect_pull: missing vault secrets warbird_edge_base_url or warbird_edge_cron_secret.';
    return;
  end if;

  perform net.http_post(
    url     := v_base_url || '/trump-effect',
    headers := jsonb_build_object(
      'x-cron-secret', v_secret,
      'content-type', 'application/json'
    ),
    body    := '{}'::jsonb,
    timeout_milliseconds := 55000
  );
end;
$$;

comment on function public.run_trump_effect_pull() is
  'Supabase cron worker: triggers Edge Function trump-effect daily at 19:30 UTC Mon-Fri.';

-- ---------------------------------------------------------------------------
-- Remove stale versions before (re)scheduling
-- ---------------------------------------------------------------------------

do $$
declare
  v_job_id bigint;
begin
  for v_job_id in
    select jobid from cron.job
    where jobname in ('warbird_gpr_pull', 'warbird_trump_effect_pull')
  loop
    perform cron.unschedule(v_job_id);
  end loop;
exception
  when undefined_table then null;
end $$;

-- ---------------------------------------------------------------------------
-- Schedule both jobs: Mon-Fri evening after market close
-- ---------------------------------------------------------------------------

-- GPR: daily at 19:00 UTC Mon-Fri
select cron.schedule(
  'warbird_gpr_pull',
  '0 19 * * 1-5',
  $$select public.run_gpr_pull();$$
)
where not exists (
  select 1 from cron.job where jobname = 'warbird_gpr_pull'
);

-- Trump Effect: daily at 19:30 UTC Mon-Fri
select cron.schedule(
  'warbird_trump_effect_pull',
  '30 19 * * 1-5',
  $$select public.run_trump_effect_pull();$$
)
where not exists (
  select 1 from cron.job where jobname = 'warbird_trump_effect_pull'
);
