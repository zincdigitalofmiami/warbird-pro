-- Migration 040: Add HG (Copper) symbol + switch cross-asset crons to hourly
--
-- 1. Insert HG into symbols (active Databento, GLBX.MDP3, continuous contract)
-- 2. Unschedule the 4 nightly cross-asset shard jobs (02:00-02:30 UTC)
-- 3. Schedule 4 hourly shard jobs (:05-:08 past every hour, Sun-Fri)
--    All ~15 symbols updated within the first 8 minutes of every hour.

begin;

-- ============================================================
-- 1. Add HG (Copper Futures)
-- ============================================================

insert into symbols (
  code, display_name, short_name, description,
  tick_size, data_source, dataset, databento_symbol, fred_symbol, is_active
) values (
  'HG', 'HG', 'Copper', 'COMEX Copper Futures',
  0.0005, 'DATABENTO', 'GLBX.MDP3', 'HG.c.0', null, true
)
on conflict (code) do update set
  is_active        = true,
  databento_symbol = 'HG.c.0',
  dataset          = 'GLBX.MDP3';

-- ============================================================
-- 2. Unschedule existing nightly shard jobs
-- ============================================================

do $$
declare
  v_job_id bigint;
begin
  for v_job_id in
    select jobid from cron.job
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

-- ============================================================
-- 3. Schedule hourly shard jobs — :05/:06/:07/:08 past every hour, Sun-Fri
--    All 4 shards fire within 4 minutes; all symbols updated every hour.
-- ============================================================

select cron.schedule(
  'warbird_cross_asset_s0',
  '5 * * * 0-5',
  $$select public.run_cross_asset_pull(0);$$
)
where not exists (
  select 1 from cron.job where jobname = 'warbird_cross_asset_s0'
);

select cron.schedule(
  'warbird_cross_asset_s1',
  '6 * * * 0-5',
  $$select public.run_cross_asset_pull(1);$$
)
where not exists (
  select 1 from cron.job where jobname = 'warbird_cross_asset_s1'
);

select cron.schedule(
  'warbird_cross_asset_s2',
  '7 * * * 0-5',
  $$select public.run_cross_asset_pull(2);$$
)
where not exists (
  select 1 from cron.job where jobname = 'warbird_cross_asset_s2'
);

select cron.schedule(
  'warbird_cross_asset_s3',
  '8 * * * 0-5',
  $$select public.run_cross_asset_pull(3);$$
)
where not exists (
  select 1 from cron.job where jobname = 'warbird_cross_asset_s3'
);

commit;
