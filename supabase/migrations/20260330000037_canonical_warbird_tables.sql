-- Migration 037: Canonical Warbird normalized schema
-- Aligned to the 2026-03-28 hierarchy lock.
-- Applies the canonical cloud tables and packet lineage tables
-- for the MES 15m fib candidate contract.
--
-- Applied to production 2026-03-31. All tables empty — no writers active yet.
--
-- Existing types reused from earlier migrations:
--   timeframe          (migration 001)
--   signal_direction   (migration 001)
--   symbols(code)      (migration 002)

begin;

-- ============================================================
-- Enums
-- ============================================================

create type warbird_decision_code as enum (
  'TAKE_TRADE',
  'WAIT',
  'PASS'
);

create type warbird_outcome_code as enum (
  'TP2_HIT',
  'TP1_ONLY',
  'STOPPED',
  'REVERSAL',
  'OPEN'
);

create type warbird_signal_status as enum (
  'ACTIVE',
  'TP1_HIT',
  'TP2_HIT',
  'STOPPED',
  'CANCELLED'
);

create type warbird_signal_event_type as enum (
  'SIGNAL_EMITTED',
  'TP1_HIT',
  'TP2_HIT',
  'STOPPED',
  'CANCELLED',
  'REVERSAL_DETECTED'
);

create type warbird_setup_archetype as enum (
  'ACCEPT_CONTINUATION',
  'ZONE_REJECTION',
  'PIVOT_CONTINUATION',
  'FAILED_MOVE_REVERSAL',
  'REENTRY_AFTER_TP1'
);

create type warbird_stop_family as enum (
  'FIB_INVALIDATION',
  'FIB_ATR',
  'STRUCTURE',
  'FIXED_ATR'
);

create type warbird_fib_level as enum (
  'ZERO',
  'FIB_236',
  'FIB_382',
  'FIB_500',
  'FIB_618',
  'FIB_786',
  'ONE',
  'TP1',
  'TP2'
);

create type warbird_regime_bucket as enum (
  'RISK_ON',
  'NEUTRAL',
  'RISK_OFF',
  'CONFLICT'
);

create type warbird_session_bucket as enum (
  'RTH_OPEN',
  'RTH_CORE',
  'LUNCH',
  'RTH_PM',
  'ETH'
);

create type warbird_packet_status as enum (
  'CANDIDATE',
  'PROMOTED',
  'FAILED',
  'ROLLED_BACK',
  'SUPERSEDED'
);

-- ============================================================
-- warbird_training_runs
-- Published run registry for packet lineage.
-- ============================================================
create table warbird_training_runs (
  run_id              uuid                  primary key default gen_random_uuid(),
  contract_version    text                  not null,
  symbol_code         text                  not null default 'MES' references symbols(code),
  timeframe           timeframe             not null default 'M15',
  dataset_date_range  tstzrange             not null,
  feature_count       integer               not null,
  packet_status       warbird_packet_status not null default 'CANDIDATE',
  tp1_auc             numeric,
  tp2_auc             numeric,
  calibration_error   numeric,
  selector_family     text                  not null,
  created_at          timestamptz           not null default now(),
  constraint ck_warbird_training_runs_symbol
    check (symbol_code = 'MES'),
  constraint ck_warbird_training_runs_timeframe
    check (timeframe = 'M15'),
  constraint ck_warbird_training_runs_range
    check (not isempty(dataset_date_range)),
  constraint ck_warbird_training_runs_feature_count
    check (feature_count >= 1),
  constraint ck_warbird_training_runs_tp1_auc
    check (tp1_auc is null or tp1_auc between 0 and 1),
  constraint ck_warbird_training_runs_tp2_auc
    check (tp2_auc is null or tp2_auc between 0 and 1),
  constraint ck_warbird_training_runs_calibration_error
    check (calibration_error is null or calibration_error >= 0)
);

create index idx_warbird_training_runs_created_at
  on warbird_training_runs (created_at desc);
create index idx_warbird_training_runs_dataset_range
  on warbird_training_runs using gist (dataset_date_range);

alter table warbird_training_runs enable row level security;
create policy "Authenticated read warbird_training_runs"
  on warbird_training_runs for select to authenticated using (true);

-- ============================================================
-- warbird_training_run_metrics
-- Full training and evaluation metrics per run.
-- ============================================================
create table warbird_training_run_metrics (
  training_run_metric_id  uuid        primary key default gen_random_uuid(),
  run_id                  uuid        not null references warbird_training_runs(run_id) on delete cascade,
  target_name             text        not null,
  split_code              text        not null,
  fold_code               text,
  metric_family           text        not null,
  metric_name             text        not null,
  metric_value            numeric     not null,
  metric_unit             text,
  metric_rank             integer,
  is_primary              boolean     not null default false,
  created_at              timestamptz not null default now(),
  constraint ck_warbird_training_run_metrics_rank
    check (metric_rank is null or metric_rank >= 1)
);

create index idx_warbird_training_run_metrics_run
  on warbird_training_run_metrics (run_id, target_name, split_code, created_at desc);
create unique index uq_warbird_training_run_metrics_key
  on warbird_training_run_metrics (run_id, target_name, split_code, coalesce(fold_code, ''), metric_family, metric_name);

alter table warbird_training_run_metrics enable row level security;
create policy "Authenticated read warbird_training_run_metrics"
  on warbird_training_run_metrics for select to authenticated using (true);

-- ============================================================
-- warbird_packets
-- AG scoring/model packet registry.
-- ============================================================
create table warbird_packets (
  packet_id          uuid                  primary key default gen_random_uuid(),
  run_id             uuid                  not null references warbird_training_runs(run_id) on delete restrict,
  packet_version     text                  not null,
  contract_version   text                  not null,
  symbol_code        text                  not null default 'MES' references symbols(code),
  timeframe          timeframe             not null default 'M15',
  status             warbird_packet_status not null default 'CANDIDATE',
  packet_json        jsonb                 not null,
  sample_count       integer               not null,
  description        text,
  promoted_at        timestamptz,
  superseded_at      timestamptz,
  created_at         timestamptz           not null default now(),
  constraint uq_warbird_packets_version unique (packet_version),
  constraint ck_warbird_packets_symbol
    check (symbol_code = 'MES'),
  constraint ck_warbird_packets_timeframe
    check (timeframe = 'M15'),
  constraint ck_warbird_packets_json_object
    check (jsonb_typeof(packet_json) = 'object'),
  constraint ck_warbird_packets_sample_count
    check (sample_count >= 0),
  constraint ck_warbird_packets_promoted_ts
    check (promoted_at is null or status in ('PROMOTED', 'ROLLED_BACK', 'SUPERSEDED')),
  constraint ck_warbird_packets_superseded_ts
    check (superseded_at is null or status = 'SUPERSEDED')
);

create index idx_warbird_packets_run_id
  on warbird_packets (run_id);
create index idx_warbird_packets_status_created
  on warbird_packets (status, created_at desc);

alter table warbird_packets enable row level security;
create policy "Authenticated read warbird_packets"
  on warbird_packets for select to authenticated using (true);

-- ============================================================
-- warbird_packet_activations
-- Immutable activation and rollback log for packet promotion.
-- ============================================================
create table warbird_packet_activations (
  activation_id      uuid        primary key default gen_random_uuid(),
  packet_id          uuid        not null references warbird_packets(packet_id) on delete cascade,
  activated_at       timestamptz not null default now(),
  deactivated_at     timestamptz,
  activation_reason  text        not null,
  rollback_reason    text,
  is_current         boolean     not null default false,
  created_at         timestamptz not null default now(),
  constraint ck_warbird_packet_activations_deactivated_at
    check (deactivated_at is null or deactivated_at >= activated_at),
  constraint ck_warbird_packet_activations_rollback_reason
    check (rollback_reason is null or deactivated_at is not null)
);

create unique index uq_warbird_packet_activations_single_current
  on warbird_packet_activations ((1))
  where is_current;
create index idx_warbird_packet_activations_packet_id
  on warbird_packet_activations (packet_id, activated_at desc);

alter table warbird_packet_activations enable row level security;
create policy "Authenticated read warbird_packet_activations"
  on warbird_packet_activations for select to authenticated using (true);

-- ============================================================
-- warbird_packet_metrics
-- Structured packet-level KPIs for the Admin dashboard.
-- ============================================================
create table warbird_packet_metrics (
  packet_metric_id               uuid        primary key default gen_random_uuid(),
  packet_id                      uuid        not null references warbird_packets(packet_id) on delete cascade,
  target_name                    text        not null,
  split_code                     text        not null,
  auc                            numeric,
  log_loss                       numeric,
  brier_score                    numeric,
  calibration_error              numeric,
  resolved_count                 integer     not null,
  open_count                     integer     not null default 0,
  tp1_before_sl_rate             numeric,
  tp2_before_sl_rate             numeric,
  sl_before_tp1_rate             numeric,
  sl_after_tp1_before_tp2_rate   numeric,
  created_at                     timestamptz not null default now(),
  constraint uq_warbird_packet_metrics_target_split
    unique (packet_id, target_name, split_code),
  constraint ck_warbird_packet_metrics_auc
    check (auc is null or auc between 0 and 1),
  constraint ck_warbird_packet_metrics_log_loss
    check (log_loss is null or log_loss >= 0),
  constraint ck_warbird_packet_metrics_brier
    check (brier_score is null or brier_score >= 0),
  constraint ck_warbird_packet_metrics_calibration
    check (calibration_error is null or calibration_error >= 0),
  constraint ck_warbird_packet_metrics_resolved
    check (resolved_count >= 0),
  constraint ck_warbird_packet_metrics_open
    check (open_count >= 0),
  constraint ck_warbird_packet_metrics_tp1_rate
    check (tp1_before_sl_rate is null or tp1_before_sl_rate between 0 and 1),
  constraint ck_warbird_packet_metrics_tp2_rate
    check (tp2_before_sl_rate is null or tp2_before_sl_rate between 0 and 1),
  constraint ck_warbird_packet_metrics_sl_pre_rate
    check (sl_before_tp1_rate is null or sl_before_tp1_rate between 0 and 1),
  constraint ck_warbird_packet_metrics_sl_post_rate
    check (sl_after_tp1_before_tp2_rate is null or sl_after_tp1_before_tp2_rate between 0 and 1)
);

create index idx_warbird_packet_metrics_packet
  on warbird_packet_metrics (packet_id, created_at desc);

alter table warbird_packet_metrics enable row level security;
create policy "Authenticated read warbird_packet_metrics"
  on warbird_packet_metrics for select to authenticated using (true);

-- ============================================================
-- warbird_packet_feature_importance
-- Packet-level top drivers published for Admin review.
-- ============================================================
create table warbird_packet_feature_importance (
  packet_feature_importance_id uuid        primary key default gen_random_uuid(),
  packet_id                   uuid        not null references warbird_packets(packet_id) on delete cascade,
  target_name                 text        not null,
  feature_family              text        not null,
  feature_name                text        not null,
  importance_source_code      text        not null default 'SHAP',
  importance_rank             integer     not null,
  mean_abs_importance         numeric     not null,
  effect_direction_code       text,
  created_at                  timestamptz not null default now(),
  constraint uq_warbird_packet_feature_importance
    unique (packet_id, target_name, feature_name, importance_source_code),
  constraint ck_warbird_packet_feature_importance_source
    check (importance_source_code in ('SHAP', 'PERMUTATION')),
  constraint ck_warbird_packet_feature_importance_rank
    check (importance_rank >= 1),
  constraint ck_warbird_packet_feature_importance_value
    check (mean_abs_importance >= 0),
  constraint ck_warbird_packet_feature_importance_effect
    check (effect_direction_code is null or effect_direction_code in ('POSITIVE', 'NEGATIVE', 'MIXED', 'CONDITIONAL', 'NEUTRAL'))
);

create index idx_warbird_packet_feature_importance_packet_rank
  on warbird_packet_feature_importance (packet_id, target_name, importance_rank);

alter table warbird_packet_feature_importance enable row level security;
create policy "Authenticated read warbird_packet_feature_importance"
  on warbird_packet_feature_importance for select to authenticated using (true);

-- ============================================================
-- warbird_packet_setting_hypotheses
-- Structured setting suggestions for indicator and entry-definition review.
-- ============================================================
create table warbird_packet_setting_hypotheses (
  hypothesis_id              uuid        primary key default gen_random_uuid(),
  packet_id                  uuid        not null references warbird_packets(packet_id) on delete cascade,
  target_name                text,
  indicator_family           text        not null,
  parameter_name             text        not null,
  action_code                text        not null,
  suggested_numeric_value    numeric,
  suggested_text_value       text,
  stability_score            numeric,
  evidence_feature_family    text,
  support_summary_json       jsonb       not null default '{}'::jsonb,
  created_at                 timestamptz not null default now(),
  constraint ck_warbird_packet_setting_hypotheses_action
    check (action_code in ('TEST_RANGE', 'INCREASE', 'DECREASE', 'KEEP_BASELINE', 'REMOVE_FAMILY')),
  constraint ck_warbird_packet_setting_hypotheses_stability
    check (stability_score is null or stability_score between 0 and 1),
  constraint ck_warbird_packet_setting_hypotheses_support_json
    check (jsonb_typeof(support_summary_json) = 'object')
);

create index idx_warbird_packet_setting_hypotheses_packet
  on warbird_packet_setting_hypotheses (packet_id, created_at desc);
create unique index uq_warbird_packet_setting_hypotheses
  on warbird_packet_setting_hypotheses (packet_id, coalesce(target_name, ''), indicator_family, parameter_name, action_code);

alter table warbird_packet_setting_hypotheses enable row level security;
create policy "Authenticated read warbird_packet_setting_hypotheses"
  on warbird_packet_setting_hypotheses for select to authenticated using (true);

-- ============================================================
-- warbird_packet_recommendations
-- Structured AI-generated guidance for the Admin page.
-- ============================================================
create table warbird_packet_recommendations (
  recommendation_id   uuid        primary key default gen_random_uuid(),
  packet_id           uuid        not null references warbird_packets(packet_id) on delete cascade,
  section_code        text        not null,
  priority            smallint    not null,
  recommendation_code text        not null,
  title               text        not null,
  summary_text        text        not null,
  rationale_json      jsonb       not null default '{}'::jsonb,
  action_json         jsonb       not null default '{}'::jsonb,
  created_at          timestamptz not null default now(),
  constraint uq_warbird_packet_recommendations_code
    unique (packet_id, recommendation_code),
  constraint ck_warbird_packet_recommendations_section
    check (section_code in ('OVERVIEW', 'ENTRY', 'TARGETS', 'RISK', 'FEATURES', 'DATA_QUALITY', 'BACKTEST', 'OPERATIONS')),
  constraint ck_warbird_packet_recommendations_priority
    check (priority between 1 and 5),
  constraint ck_warbird_packet_recommendations_rationale_json
    check (jsonb_typeof(rationale_json) = 'object'),
  constraint ck_warbird_packet_recommendations_action_json
    check (jsonb_typeof(action_json) = 'object')
);

create index idx_warbird_packet_recommendations_packet_priority
  on warbird_packet_recommendations (packet_id, priority, created_at desc);

alter table warbird_packet_recommendations enable row level security;
create policy "Authenticated read warbird_packet_recommendations"
  on warbird_packet_recommendations for select to authenticated using (true);

-- ============================================================
-- warbird_fib_engine_snapshots_15m
-- One row per (symbol_code, timeframe, bar_close_ts, fib_engine_version).
-- ============================================================
create table warbird_fib_engine_snapshots_15m (
  snapshot_id                   uuid             primary key default gen_random_uuid(),
  bar_close_ts                  timestamptz      not null,
  timeframe                     timeframe        not null default 'M15',
  symbol_code                   text             not null default 'MES' references symbols(code),
  fib_engine_version            text             not null,
  direction                     signal_direction not null,
  anchor_hash                   text             not null,
  anchor_high                   numeric          not null,
  anchor_low                    numeric          not null,
  anchor_high_ts                timestamptz      not null,
  anchor_low_ts                 timestamptz      not null,
  anchor_range_pts              numeric          not null,
  resolved_left_bars            smallint         not null,
  resolved_right_bars           smallint         not null,
  resolved_anchor_lookback_bars smallint         not null,
  resolved_anchor_spacing_bars  smallint         not null,
  reversal_mode_code            text             not null,
  anchor_lock_state_code        text             not null,
  fib_zero                      numeric          not null,
  fib_236                       numeric          not null,
  fib_382                       numeric          not null,
  fib_500                       numeric          not null,
  fib_618                       numeric          not null,
  fib_786                       numeric          not null,
  fib_one                       numeric          not null,
  fib_tp1                       numeric          not null,
  fib_tp2                       numeric          not null,
  target_eligible_20pt          boolean          not null,
  exhaustion_precursor_flag     boolean          not null,
  exhaustion_precursor_score    numeric,
  exhaustion_location_code      text,
  created_at                    timestamptz      not null default now(),
  constraint uq_warbird_fib_snapshots_bar
    unique (symbol_code, timeframe, bar_close_ts, fib_engine_version),
  constraint uq_warbird_fib_snapshots_contract_key
    unique (snapshot_id, symbol_code, timeframe, bar_close_ts),
  constraint ck_warbird_fib_snapshots_symbol
    check (symbol_code = 'MES'),
  constraint ck_warbird_fib_snapshots_timeframe
    check (timeframe = 'M15'),
  constraint ck_warbird_fib_snapshots_range
    check (anchor_range_pts > 0),
  constraint ck_warbird_fib_snapshots_left_bars
    check (resolved_left_bars > 0),
  constraint ck_warbird_fib_snapshots_right_bars
    check (resolved_right_bars > 0),
  constraint ck_warbird_fib_snapshots_lookback
    check (resolved_anchor_lookback_bars > 0),
  constraint ck_warbird_fib_snapshots_spacing
    check (resolved_anchor_spacing_bars >= 0),
  constraint ck_warbird_fib_snapshots_tp1_beyond_one
    check (
      (direction = 'LONG' and fib_tp1 > fib_one and fib_tp2 > fib_tp1) or
      (direction = 'SHORT' and fib_tp1 < fib_one and fib_tp2 < fib_tp1)
    )
);

create index idx_warbird_fib_snapshots_symbol_bar
  on warbird_fib_engine_snapshots_15m (symbol_code, timeframe, bar_close_ts desc);
create index idx_warbird_fib_snapshots_anchor_hash
  on warbird_fib_engine_snapshots_15m (anchor_hash);
create index idx_warbird_fib_snapshots_eligible
  on warbird_fib_engine_snapshots_15m (bar_close_ts desc)
  where target_eligible_20pt;

alter table warbird_fib_engine_snapshots_15m enable row level security;
create policy "Authenticated read warbird_fib_engine_snapshots_15m"
  on warbird_fib_engine_snapshots_15m for select to authenticated using (true);

-- ============================================================
-- warbird_fib_candidates_15m
-- One row per tradable candidate derived from a snapshot.
-- ============================================================
create table warbird_fib_candidates_15m (
  candidate_id           uuid                    primary key default gen_random_uuid(),
  snapshot_id            uuid                    not null,
  bar_close_ts           timestamptz             not null,
  timeframe              timeframe               not null default 'M15',
  symbol_code            text                    not null default 'MES' references symbols(code),
  candidate_seq          smallint                not null default 1,
  direction              signal_direction        not null,
  setup_archetype        warbird_setup_archetype not null,
  fib_level_touched      warbird_fib_level       not null,
  fib_ratio_touched      numeric                 not null,
  entry_price            numeric                 not null,
  stop_loss              numeric                 not null,
  tp1_price              numeric                 not null,
  tp2_price              numeric                 not null,
  stop_family            warbird_stop_family     not null,
  target_eligible_20pt   boolean                 not null,
  event_mode_code        text                    not null,
  pivot_interaction_code text                    not null,
  regime_bucket          warbird_regime_bucket   not null,
  session_bucket         warbird_session_bucket  not null,
  confidence_score       numeric                 not null,
  decision_code          warbird_decision_code,
  decision_reason_code   text,
  tp1_probability        numeric,
  tp2_probability        numeric,
  reversal_risk          numeric,
  expected_mae_pts       numeric,
  expected_mfe_pts       numeric,
  packet_id              uuid references warbird_packets(packet_id),
  created_at             timestamptz             not null default now(),
  constraint uq_warbird_fib_candidates_bar_seq
    unique (symbol_code, timeframe, bar_close_ts, candidate_seq),
  constraint uq_warbird_fib_candidates_contract_key
    unique (candidate_id, symbol_code, timeframe, bar_close_ts),
  constraint uq_warbird_fib_candidates_take_trade_fk
    unique (candidate_id, decision_code),
  constraint uq_warbird_fib_candidates_packet_fk
    unique (candidate_id, packet_id),
  constraint fk_warbird_candidates_snapshot_contract
    foreign key (snapshot_id, symbol_code, timeframe, bar_close_ts)
    references warbird_fib_engine_snapshots_15m (snapshot_id, symbol_code, timeframe, bar_close_ts)
    on delete cascade,
  constraint ck_warbird_fib_candidates_symbol
    check (symbol_code = 'MES'),
  constraint ck_warbird_fib_candidates_timeframe
    check (timeframe = 'M15'),
  constraint ck_warbird_fib_candidates_seq
    check (candidate_seq >= 1),
  constraint ck_warbird_fib_candidates_target_eligible
    check (target_eligible_20pt),
  constraint ck_warbird_fib_candidates_confidence
    check (confidence_score between 0 and 100),
  constraint ck_warbird_fib_candidates_tp1_prob
    check (tp1_probability is null or tp1_probability between 0 and 1),
  constraint ck_warbird_fib_candidates_tp2_prob
    check (tp2_probability is null or tp2_probability between 0 and 1),
  constraint ck_warbird_fib_candidates_reversal_risk
    check (reversal_risk is null or reversal_risk between 0 and 1),
  constraint ck_warbird_fib_candidates_tp_prob_order
    check (tp1_probability is null or tp2_probability is null or tp2_probability <= tp1_probability),
  constraint ck_warbird_fib_candidates_price_geometry
    check (
      (direction = 'LONG' and stop_loss < entry_price and tp1_price > entry_price and tp2_price > tp1_price) or
      (direction = 'SHORT' and stop_loss > entry_price and tp1_price < entry_price and tp2_price < tp1_price)
    ),
  constraint ck_warbird_fib_candidates_tp1_distance
    check (abs(tp1_price - entry_price) >= 20),
  constraint ck_warbird_fib_candidates_scored_state
    check (
      (packet_id is null and decision_code is null and tp1_probability is null and tp2_probability is null and reversal_risk is null and expected_mae_pts is null and expected_mfe_pts is null)
      or
      (packet_id is not null and decision_code is not null and tp1_probability is not null and tp2_probability is not null and reversal_risk is not null and expected_mae_pts is not null and expected_mfe_pts is not null)
    )
);

create index idx_warbird_fib_candidates_symbol_bar
  on warbird_fib_candidates_15m (symbol_code, timeframe, bar_close_ts desc);
create index idx_warbird_fib_candidates_snapshot
  on warbird_fib_candidates_15m (snapshot_id);
create index idx_warbird_fib_candidates_decision
  on warbird_fib_candidates_15m (decision_code, bar_close_ts desc);
create index idx_warbird_fib_candidates_bucket
  on warbird_fib_candidates_15m (regime_bucket, session_bucket, direction);
create index idx_warbird_fib_candidates_packet
  on warbird_fib_candidates_15m (packet_id)
  where packet_id is not null;

alter table warbird_fib_candidates_15m enable row level security;
create policy "Authenticated read warbird_fib_candidates_15m"
  on warbird_fib_candidates_15m for select to authenticated using (true);

-- ============================================================
-- warbird_candidate_outcomes_15m
-- One row per candidate regardless of decision_code.
-- ============================================================
create table warbird_candidate_outcomes_15m (
  outcome_id                uuid                 primary key default gen_random_uuid(),
  candidate_id              uuid                 not null unique,
  bar_close_ts              timestamptz          not null,
  symbol_code               text                 not null default 'MES' references symbols(code),
  timeframe                 timeframe            not null default 'M15',
  outcome_code              warbird_outcome_code not null,
  tp1_before_sl             boolean              not null default false,
  tp2_before_sl             boolean              not null default false,
  sl_before_tp1             boolean              not null default false,
  sl_after_tp1_before_tp2   boolean              not null default false,
  reversal_detected         boolean              not null default false,
  tp1_hit_ts                timestamptz,
  tp2_hit_ts                timestamptz,
  stopped_ts                timestamptz,
  reversal_ts               timestamptz,
  mae_pts                   numeric              not null,
  mfe_pts                   numeric              not null,
  scorer_version            text                 not null,
  scored_at                 timestamptz          not null,
  created_at                timestamptz          not null default now(),
  constraint fk_warbird_outcomes_candidate_contract
    foreign key (candidate_id, symbol_code, timeframe, bar_close_ts)
    references warbird_fib_candidates_15m (candidate_id, symbol_code, timeframe, bar_close_ts)
    on delete cascade,
  constraint ck_warbird_outcomes_symbol
    check (symbol_code = 'MES'),
  constraint ck_warbird_outcomes_timeframe
    check (timeframe = 'M15'),
  constraint ck_warbird_outcomes_mae
    check (mae_pts >= 0),
  constraint ck_warbird_outcomes_mfe
    check (mfe_pts >= 0),
  constraint ck_warbird_outcomes_tp2_requires_tp1
    check (not tp2_before_sl or tp1_before_sl),
  constraint ck_warbird_outcomes_stop_conflict
    check (not (sl_before_tp1 and sl_after_tp1_before_tp2)),
  constraint ck_warbird_outcomes_stop_pre_conflict
    check (not (sl_before_tp1 and tp1_before_sl)),
  constraint ck_warbird_outcomes_tp1_ts
    check (not tp1_before_sl or tp1_hit_ts is not null),
  constraint ck_warbird_outcomes_tp2_ts
    check (not tp2_before_sl or tp2_hit_ts is not null),
  constraint ck_warbird_outcomes_tp_ts_order
    check (tp1_hit_ts is null or tp2_hit_ts is null or tp2_hit_ts >= tp1_hit_ts),
  constraint ck_warbird_outcomes_stop_ts
    check (not (sl_before_tp1 or sl_after_tp1_before_tp2) or stopped_ts is not null),
  constraint ck_warbird_outcomes_stop_post_tp1_order
    check (not sl_after_tp1_before_tp2 or tp1_hit_ts is not null and stopped_ts >= tp1_hit_ts),
  constraint ck_warbird_outcomes_reversal_ts
    check (not reversal_detected or reversal_ts is not null),
  constraint ck_warbird_outcomes_code_mapping
    check (
      (outcome_code = 'TP2_HIT' and tp1_before_sl and tp2_before_sl and not sl_before_tp1 and not sl_after_tp1_before_tp2 and not reversal_detected)
      or
      (outcome_code = 'TP1_ONLY' and tp1_before_sl and not tp2_before_sl and not sl_before_tp1 and not sl_after_tp1_before_tp2 and not reversal_detected)
      or
      (outcome_code = 'STOPPED' and not tp2_before_sl and (sl_before_tp1 or sl_after_tp1_before_tp2) and not reversal_detected)
      or
      (outcome_code = 'REVERSAL' and reversal_detected and not tp2_before_sl and not sl_before_tp1 and not sl_after_tp1_before_tp2)
      or
      (outcome_code = 'OPEN' and not tp1_before_sl and not tp2_before_sl and not sl_before_tp1 and not sl_after_tp1_before_tp2 and not reversal_detected)
    )
);

create index idx_warbird_outcomes_outcome_bar
  on warbird_candidate_outcomes_15m (outcome_code, bar_close_ts desc);
create index idx_warbird_outcomes_scored_at
  on warbird_candidate_outcomes_15m (scored_at desc);
create index idx_warbird_outcomes_resolved
  on warbird_candidate_outcomes_15m (bar_close_ts desc)
  where outcome_code <> 'OPEN';

alter table warbird_candidate_outcomes_15m enable row level security;
create policy "Authenticated read warbird_candidate_outcomes_15m"
  on warbird_candidate_outcomes_15m for select to authenticated using (true);

-- ============================================================
-- warbird_signals_15m
-- One row per published signal where decision_code = TAKE_TRADE.
-- ============================================================
create table warbird_signals_15m (
  signal_id       uuid                  primary key default gen_random_uuid(),
  candidate_id    uuid                  not null unique,
  decision_code   warbird_decision_code not null default 'TAKE_TRADE',
  bar_close_ts    timestamptz           not null,
  timeframe       timeframe             not null default 'M15',
  symbol_code     text                  not null default 'MES' references symbols(code),
  direction       signal_direction      not null,
  status          warbird_signal_status not null default 'ACTIVE',
  entry_price     numeric               not null,
  stop_loss       numeric               not null,
  tp1_price       numeric               not null,
  tp2_price       numeric               not null,
  packet_id       uuid                  not null references warbird_packets(packet_id),
  emitted_at      timestamptz           not null default now(),
  tv_alert_ready  boolean               not null default false,
  created_at      timestamptz           not null default now(),
  constraint fk_warbird_signals_candidate_contract
    foreign key (candidate_id, symbol_code, timeframe, bar_close_ts)
    references warbird_fib_candidates_15m (candidate_id, symbol_code, timeframe, bar_close_ts)
    on delete cascade,
  constraint fk_warbird_signals_take_trade
    foreign key (candidate_id, decision_code)
    references warbird_fib_candidates_15m (candidate_id, decision_code),
  constraint fk_warbird_signals_packet_match
    foreign key (candidate_id, packet_id)
    references warbird_fib_candidates_15m (candidate_id, packet_id),
  constraint ck_warbird_signals_symbol
    check (symbol_code = 'MES'),
  constraint ck_warbird_signals_timeframe
    check (timeframe = 'M15'),
  constraint ck_warbird_signals_decision_code
    check (decision_code = 'TAKE_TRADE'),
  constraint ck_warbird_signals_price_geometry
    check (
      (direction = 'LONG' and stop_loss < entry_price and tp1_price > entry_price and tp2_price > tp1_price) or
      (direction = 'SHORT' and stop_loss > entry_price and tp1_price < entry_price and tp2_price < tp1_price)
    )
);

create index idx_warbird_signals_symbol_bar
  on warbird_signals_15m (symbol_code, timeframe, bar_close_ts desc);
create index idx_warbird_signals_status_bar
  on warbird_signals_15m (status, bar_close_ts desc);
create index idx_warbird_signals_packet
  on warbird_signals_15m (packet_id);

alter table warbird_signals_15m enable row level security;
create policy "Authenticated read warbird_signals_15m"
  on warbird_signals_15m for select to authenticated using (true);

-- ============================================================
-- warbird_signal_events
-- Append-only lifecycle log for published signals.
-- ============================================================
create table warbird_signal_events (
  signal_event_id  uuid                      primary key default gen_random_uuid(),
  signal_id        uuid                      not null references warbird_signals_15m(signal_id) on delete cascade,
  ts               timestamptz               not null,
  event_type       warbird_signal_event_type not null,
  price            numeric,
  note             text,
  metadata         jsonb                     not null default '{}'::jsonb,
  created_at       timestamptz               not null default now(),
  constraint ck_warbird_signal_events_metadata_object
    check (jsonb_typeof(metadata) = 'object')
);

create index idx_warbird_signal_events_signal_ts
  on warbird_signal_events (signal_id, ts desc);
create index idx_warbird_signal_events_type_ts
  on warbird_signal_events (event_type, ts desc);

alter table warbird_signal_events enable row level security;
create policy "Authenticated read warbird_signal_events"
  on warbird_signal_events for select to authenticated using (true);

commit;
