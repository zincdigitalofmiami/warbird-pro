-- Migration 036: Remove GPR production cron infrastructure
-- GPR (Caldara-Iacoviello Geopolitical Risk Index) is backfill-only data.
-- Populated once locally, refreshed manually monthly. No recurring cron needed.
--
-- Removes:
--   - warbird_gpr_pull pg_cron job (was daily Mon-Fri)
--   - run_gpr_pull() helper function (migrations 027, 029, 033)
--   - warbird_vercel_base_url vault secret (only used for GPR Vercel fallback in migration 029)

begin;

-- Unschedule warbird_gpr_pull pg_cron job
do $$
declare
  v_job_id bigint;
begin
  for v_job_id in
    select jobid from cron.job
    where jobname = 'warbird_gpr_pull'
  loop
    perform cron.unschedule(v_job_id);
  end loop;
exception
  when undefined_table then null;
end $$;

-- Drop the pg_net helper function
drop function if exists public.run_gpr_pull();

-- Vault cleanup: warbird_vercel_base_url was only used for GPR Vercel fallback (migration 029)
delete from vault.secrets where name = 'warbird_vercel_base_url';

commit;
