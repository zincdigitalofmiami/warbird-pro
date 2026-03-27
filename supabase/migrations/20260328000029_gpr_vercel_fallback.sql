-- Migration 029: GPR Vercel route fallback
-- The GPR Edge Function crashes with WORKER_LIMIT because npm:xlsx exceeds
-- Deno Edge runtime memory budget (~150MB). The source only provides binary
-- XLS format (no CSV alternative exists). The Vercel route at
-- /api/cron/gpr works because Node.js has ~1GB memory budget.
--
-- This is the ONE approved Vercel cron exception per the data-gaps plan.
-- GPR is a single daily call to a public XLS file — minimal cost impact.
--
-- Required vault secrets:
--   warbird_vercel_base_url  -> e.g. https://warbird-pro.vercel.app
--   warbird_cron_secret      -> CRON_SECRET value for Vercel route auth
--
-- Kirk: you must manually insert warbird_vercel_base_url into vault.secrets:
--   SELECT vault.create_secret('https://your-vercel-url.vercel.app', 'warbird_vercel_base_url');

create or replace function public.run_gpr_pull()
returns void
language plpgsql
security definer
set search_path = public, extensions
as $$
declare
  v_vercel_url text;
  v_secret     text;
begin
  -- GPR uses Vercel route because XLS parsing exceeds Edge Function memory.
  select decrypted_secret into v_vercel_url
  from vault.decrypted_secrets
  where name = 'warbird_vercel_base_url'
  order by created_at desc limit 1;

  select decrypted_secret into v_secret
  from vault.decrypted_secrets
  where name = 'warbird_cron_secret'
  order by created_at desc limit 1;

  if v_vercel_url is null or v_secret is null then
    raise notice 'Skipping run_gpr_pull: missing vault secrets warbird_vercel_base_url or warbird_cron_secret.';
    return;
  end if;

  perform net.http_get(
    url     := v_vercel_url || '/api/cron/gpr',
    headers := jsonb_build_object('authorization', 'Bearer ' || v_secret),
    timeout_milliseconds := 55000
  );
end;
$$;

comment on function public.run_gpr_pull() is
  'Supabase cron worker: triggers Vercel GPR route (XLS parsing exceeds Edge memory). Daily at 06:00 UTC Mon-Fri.';
