-- Restore cross-asset runtime cron schedules for Edge Function pull chain.
-- Keeps cross_asset_1h / cross_asset_1d fresh for intermarket dashboard lanes.

create extension if not exists pg_cron;

-- Remove stale copies first, then recreate canonical schedules.
do $$
declare
  v_job_id bigint;
begin
  for v_job_id in
    select jobid
    from cron.job
    where jobname in (
      'warbird_cross_asset_s0',
      'warbird_cross_asset_s1',
      'warbird_cross_asset_s2',
      'warbird_cross_asset_s3'
    )
  loop
    perform cron.unschedule(v_job_id);
  end loop;
exception
  when undefined_table then null;
end $$;

-- Cross-asset shard pulls every hour, Sunday-Friday.
select cron.schedule(
  'warbird_cross_asset_s0',
  '5 * * * 0-5',
  $$select public.run_cross_asset_pull(0);$$
)
where not exists (
  select 1
  from cron.job
  where jobname = 'warbird_cross_asset_s0'
);

select cron.schedule(
  'warbird_cross_asset_s1',
  '6 * * * 0-5',
  $$select public.run_cross_asset_pull(1);$$
)
where not exists (
  select 1
  from cron.job
  where jobname = 'warbird_cross_asset_s1'
);

select cron.schedule(
  'warbird_cross_asset_s2',
  '7 * * * 0-5',
  $$select public.run_cross_asset_pull(2);$$
)
where not exists (
  select 1
  from cron.job
  where jobname = 'warbird_cross_asset_s2'
);

select cron.schedule(
  'warbird_cross_asset_s3',
  '8 * * * 0-5',
  $$select public.run_cross_asset_pull(3);$$
)
where not exists (
  select 1
  from cron.job
  where jobname = 'warbird_cross_asset_s3'
);
