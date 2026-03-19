-- Migration 011: mes_1s continuity + strict 15m cleanup + promoted model outputs
-- Goals:
-- 1) Add mes_1s canonical continuity table.
-- 2) Promote probability outputs to first-class warbird_forecasts_1h columns.
-- 3) Remove runner logic footprint (columns + enum values) safely.

begin;

-- ---------------------------------------------------------------------------
-- 1) mes_1s continuity table
-- ---------------------------------------------------------------------------

create table if not exists mes_1s (
  ts         timestamptz not null,
  open       numeric     not null,
  high       numeric     not null,
  low        numeric     not null,
  close      numeric     not null,
  volume     bigint      not null default 0,
  created_at timestamptz not null default now(),
  primary key (ts)
);

create index if not exists idx_mes_1s_ts on mes_1s (ts desc);

alter table mes_1s enable row level security;

do $$
begin
  if not exists (
    select 1
    from pg_policies
    where schemaname = 'public'
      and tablename = 'mes_1s'
      and policyname = 'Authenticated read mes_1s'
  ) then
    execute 'create policy "Authenticated read mes_1s" on mes_1s for select to authenticated using (true)';
  end if;
end $$;

do $$
begin
  if not exists (
    select 1
    from pg_publication_tables
    where pubname = 'supabase_realtime'
      and schemaname = 'public'
      and tablename = 'mes_1s'
  ) then
    execute 'alter publication supabase_realtime add table mes_1s';
  end if;
end $$;

-- ---------------------------------------------------------------------------
-- 2) Promote forecast probability/score outputs
-- ---------------------------------------------------------------------------

alter table warbird_forecasts_1h
  add column if not exists prob_hit_sl_first numeric,
  add column if not exists prob_hit_pt1_first numeric,
  add column if not exists prob_hit_pt2_after_pt1 numeric,
  add column if not exists expected_max_extension numeric,
  add column if not exists setup_score numeric;

do $$
begin
  if not exists (
    select 1 from pg_constraint
    where conname = 'chk_warbird_forecasts_prob_hit_sl_first'
  ) then
    alter table warbird_forecasts_1h
      add constraint chk_warbird_forecasts_prob_hit_sl_first
      check (prob_hit_sl_first is null or (prob_hit_sl_first >= 0 and prob_hit_sl_first <= 1));
  end if;

  if not exists (
    select 1 from pg_constraint
    where conname = 'chk_warbird_forecasts_prob_hit_pt1_first'
  ) then
    alter table warbird_forecasts_1h
      add constraint chk_warbird_forecasts_prob_hit_pt1_first
      check (prob_hit_pt1_first is null or (prob_hit_pt1_first >= 0 and prob_hit_pt1_first <= 1));
  end if;

  if not exists (
    select 1 from pg_constraint
    where conname = 'chk_warbird_forecasts_prob_hit_pt2_after_pt1'
  ) then
    alter table warbird_forecasts_1h
      add constraint chk_warbird_forecasts_prob_hit_pt2_after_pt1
      check (
        prob_hit_pt2_after_pt1 is null
        or (prob_hit_pt2_after_pt1 >= 0 and prob_hit_pt2_after_pt1 <= 1)
      );
  end if;

  if not exists (
    select 1 from pg_constraint
    where conname = 'chk_warbird_forecasts_setup_score'
  ) then
    alter table warbird_forecasts_1h
      add constraint chk_warbird_forecasts_setup_score
      check (setup_score is null or (setup_score >= 0 and setup_score <= 100));
  end if;
end $$;

-- ---------------------------------------------------------------------------
-- 3) Remove runner logic safely
-- ---------------------------------------------------------------------------

-- Normalize existing statuses/events before enum contraction.
update warbird_setups
set status = 'TP1_HIT'
where status in ('RUNNER_ACTIVE', 'RUNNER_EXITED', 'PULLBACK_REVERSAL');

update warbird_setups
set current_event = 'TP1_HIT'
where current_event in ('RUNNER_STARTED', 'RUNNER_EXITED', 'PULLBACK_REVERSAL');

update warbird_setup_events
set event_type = 'TP1_HIT'
where event_type in ('RUNNER_STARTED', 'RUNNER_EXITED', 'PULLBACK_REVERSAL');

alter table warbird_setups
  alter column status drop default,
  alter column current_event drop default;

create type warbird_setup_status_v2 as enum (
  'ACTIVE',
  'TP1_HIT',
  'TP2_HIT',
  'STOPPED',
  'EXPIRED'
);

create type warbird_setup_event_type_v2 as enum (
  'TRIGGERED',
  'TP1_HIT',
  'TP2_HIT',
  'STOPPED',
  'EXPIRED'
);

alter table warbird_setups
  alter column status type warbird_setup_status_v2
  using status::text::warbird_setup_status_v2;

alter table warbird_setups
  alter column current_event type warbird_setup_event_type_v2
  using current_event::text::warbird_setup_event_type_v2;

alter table warbird_setup_events
  alter column event_type type warbird_setup_event_type_v2
  using event_type::text::warbird_setup_event_type_v2;

drop type warbird_setup_status;
alter type warbird_setup_status_v2 rename to warbird_setup_status;

drop type warbird_setup_event_type;
alter type warbird_setup_event_type_v2 rename to warbird_setup_event_type;

alter table warbird_setups
  alter column status set default 'ACTIVE',
  alter column current_event set default 'TRIGGERED';

-- Drop runner columns from tables.
alter table warbird_forecasts_1h
  drop column if exists runner_headroom_4h;

alter table warbird_triggers_15m
  drop column if exists runner_headroom;

alter table warbird_conviction
  drop column if exists runner_eligible;

alter table warbird_setups
  drop column if exists runner_eligible,
  drop column if exists runner_headroom,
  drop column if exists runner_started_at,
  drop column if exists runner_exited_at;

commit;
