-- Disable mes_1m edge cadence and enforce MES hourly-only pull schedule.
-- User directive: ONLY 1H updates (no 1m cadence).

create extension if not exists pg_cron;

do $$
declare
  v_job_id bigint;
begin
  -- Remove any 1m MES pull schedules.
  for v_job_id in
    select jobid
    from cron.job
    where jobname = 'warbird_mes_1m_pull'
       or command ilike '%run_mes_1m_pull%'
  loop
    perform cron.unschedule(v_job_id);
  end loop;

  -- Re-anchor hourly MES pull schedule at :05 (Sun-Fri).
  for v_job_id in
    select jobid
    from cron.job
    where jobname = 'warbird_mes_hourly_pull'
  loop
    perform cron.unschedule(v_job_id);
  end loop;
exception
  when undefined_table then null;
end $$;

select cron.schedule(
  'warbird_mes_hourly_pull',
  '5 * * * 0-5',
  $$select public.run_mes_hourly_pull();$$
)
where not exists (
  select 1
  from cron.job
  where jobname = 'warbird_mes_hourly_pull'
);
