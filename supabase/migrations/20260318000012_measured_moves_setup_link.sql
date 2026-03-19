-- Migration 012: Link measured moves to setup lifecycle truth.
-- Adds nullable measured_moves.setup_id so admin/reporting can derive outcomes
-- from warbird_setups + warbird_setup_events instead of inferred status only.

begin;

alter table measured_moves
  add column if not exists setup_id bigint references warbird_setups(id) on delete set null;

create unique index if not exists uq_measured_moves_setup_id
  on measured_moves (setup_id)
  where setup_id is not null;

commit;
