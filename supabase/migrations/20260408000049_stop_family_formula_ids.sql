-- Migration: stop_family_formula_ids
-- Purpose: Replace the coarse warbird_stop_family enum (category buckets) with
--          formula-specific IDs that AG can meaningfully compare.
--
-- Safety precondition: warbird_fib_candidates_15m must be empty (0 rows).
--   The old enum values (FIB_INVALIDATION, FIB_ATR, STRUCTURE, FIXED_ATR)
--   have no mapping to the new values, so a populated table would fail.
--   The DO block below asserts emptiness before proceeding.
--
-- Dependent objects:
--   warbird_active_signals_v (migration 038) selects c.stop_family.
--   It must be dropped before the column type change and recreated after.
--
-- Authority: docs/contracts/stop_families.md (2026-04-08)

begin;

-- Assert the table is empty. Abort if any rows exist.
do $$
begin
  if (select count(*) from warbird_fib_candidates_15m) > 0 then
    raise exception 'warbird_fib_candidates_15m is not empty — cannot swap enum safely';
  end if;
end
$$;

-- Drop the dependent view that references c.stop_family.
drop view if exists warbird_active_signals_v;

-- Create the new enum with formula-specific IDs.
create type warbird_stop_family_v2 as enum (
  'FIB_NEG_0236',
  'FIB_NEG_0382',
  'ATR_1_0',
  'ATR_1_5',
  'ATR_STRUCTURE_1_25',
  'FIB_0236_ATR_COMPRESS_0_50'
);

-- Swap the column type. Table is empty so no value remapping needed.
alter table warbird_fib_candidates_15m
  alter column stop_family type warbird_stop_family_v2
  using null::warbird_stop_family_v2;

-- Drop the old enum and rename the new one to the canonical name.
drop type warbird_stop_family;
alter type warbird_stop_family_v2 rename to warbird_stop_family;

-- Recreate the dependent view (verbatim from migration 038).
create or replace view warbird_active_signals_v
  with (security_invoker = true)
as
select
  s.signal_id,
  s.bar_close_ts,
  s.symbol_code,
  s.direction,
  s.status,
  s.entry_price,
  s.stop_loss,
  s.tp1_price,
  s.tp2_price,
  s.packet_id,
  s.emitted_at,
  s.tv_alert_ready,
  c.setup_archetype,
  c.fib_level_touched,
  c.fib_ratio_touched,
  c.confidence_score,
  c.decision_code,
  c.tp1_probability,
  c.tp2_probability,
  c.reversal_risk,
  c.regime_bucket,
  c.session_bucket,
  c.stop_family,
  o.outcome_code,
  o.tp1_before_sl,
  o.tp2_before_sl,
  o.sl_before_tp1,
  o.sl_after_tp1_before_tp2,
  o.reversal_detected,
  o.mae_pts,
  o.mfe_pts
from warbird_signals_15m                  s
join warbird_fib_candidates_15m           c on c.candidate_id = s.candidate_id
left join warbird_candidate_outcomes_15m  o on o.candidate_id = s.candidate_id
where s.status = 'ACTIVE';

comment on view warbird_active_signals_v is
  'Active signals joined to candidate geometry and current realized path facts. '
  'Forward-facing view for dashboard cutover from legacy warbird_setups. '
  'Outcome join is LEFT so rows remain visible before the scorer resolves the path.';

commit;
