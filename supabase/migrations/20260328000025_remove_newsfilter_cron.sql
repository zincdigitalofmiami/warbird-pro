-- Migration 025: Remove Newsfilter cron job and helper function
-- Newsfilter removed: no free API tier exists. Provider access was never obtained.

do $$
declare
  v_job_id bigint;
begin
  for v_job_id in
    select jobid
    from cron.job
    where jobname = 'warbird_newsfilter_raw_pull'
  loop
    perform cron.unschedule(v_job_id);
  end loop;
exception
  when undefined_table then
    null;
end $$;

drop function if exists public.run_newsfilter_raw_pull();
