-- Enforce hourly-only MES edge pulls to control runtime costs.
-- - warbird_mes_1m_pull moved from every minute to hourly cadence
-- - warbird_mes_hourly_pull remains hourly at :05
-- All jobs run Sunday-Friday.

create extension if not exists pg_cron;

do $$
declare
  v_job_id bigint;
begin
  for v_job_id in
    select jobid
    from cron.job
    where jobname in ('warbird_mes_1m_pull', 'warbird_mes_hourly_pull')
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

-- Keep the 1m/15m maintenance path but cap it to hourly-only runtime.
select cron.schedule(
  'warbird_mes_1m_pull',
  '7 * * * 0-5',
  $$select public.run_mes_1m_pull();$$
)
where not exists (
  select 1
  from cron.job
  where jobname = 'warbird_mes_1m_pull'
);
