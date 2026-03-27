-- Migration 033: Clean stale vault secrets + spread daily crons
-- Combines Phase 5 (vault cleanup) and Phase 6 (cron reschedule).
--
-- Phase 5: Remove 3 stale Vercel-era vault secrets superseded by migration 023.
-- NOTE: warbird_cron_secret is KEPT because GPR now uses it (migration 029).
--
-- Phase 6: Spread non-time-critical daily pulls across 24h.
-- Current overnight window (01:00-04:20 UTC) is kept for market-critical data.
-- Non-critical daily pulls moved to morning/afternoon:
--   GPR:          19:00 -> 06:00 UTC (daily geopolitical index, not intraday-critical)
--   Trump Effect: 19:30 -> 08:00 UTC (Federal Register, publishes during business hours)

begin;

-- ============================================================
-- Phase 5: Delete stale vault secrets
-- ============================================================

delete from vault.secrets where name in (
  'warbird_newsfilter_raw_cron_url',
  'warbird_finnhub_raw_cron_url',
  'warbird_mes_1m_cron_url'
);

-- ============================================================
-- Phase 6: Reschedule non-critical daily pulls
-- ============================================================

-- Unschedule existing GPR and trump-effect jobs
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

-- GPR: moved from 19:00 to 06:00 UTC Mon-Fri
select cron.schedule(
  'warbird_gpr_pull',
  '0 6 * * 1-5',
  $$select public.run_gpr_pull();$$
)
where not exists (
  select 1 from cron.job where jobname = 'warbird_gpr_pull'
);

-- Trump Effect: moved from 19:30 to 08:00 UTC Mon-Fri
select cron.schedule(
  'warbird_trump_effect_pull',
  '0 8 * * 1-5',
  $$select public.run_trump_effect_pull();$$
)
where not exists (
  select 1 from cron.job where jobname = 'warbird_trump_effect_pull'
);

commit;
