-- Migration 038: Canonical Warbird compatibility views
-- Draft rewrite aligned to the 2026-03-28 hierarchy lock.
-- These are forward-facing read helpers over the canonical tables and do not
-- recreate legacy GO/NO_GO or measured-move semantics.
--
-- This file remains draft-only until the schema rewrite checkpoint is approved.
-- Apply via psql only. Do NOT use supabase db push.

begin;

-- ============================================================
-- warbird_active_signals_v
-- Projects the current ACTIVE signal set with candidate geometry and the latest
-- realized path facts available at read time.
-- ============================================================
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
  o.is_censored,
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

-- ============================================================
-- warbird_admin_candidate_rows_v
-- Admin row surface for the screenshot-style setup/trade table.
-- ============================================================
create or replace view warbird_admin_candidate_rows_v
  with (security_invoker = true)
as
select
  c.candidate_id,
  s.signal_id,
  c.bar_close_ts,
  c.symbol_code,
  c.timeframe,
  c.direction,
  case
    when c.direction = 'LONG' then snap.anchor_low
    else snap.anchor_high
  end                                                   as anchor_price,
  c.tp1_price                                           as target_price,
  c.entry_price                                         as retrace_price,
  c.stop_loss,
  c.tp1_price,
  c.tp2_price,
  c.fib_level_touched,
  c.fib_ratio_touched                                   as fib_ratio,
  c.setup_archetype,
  c.confidence_score,
  c.decision_code,
  c.tp1_probability,
  c.tp2_probability,
  c.reversal_risk,
  case
    when o.tp1_before_sl then 'HIT'
    when o.sl_before_tp1 or o.sl_after_tp1_before_tp2 then 'MISS'
    when o.is_censored then 'CENSORED'
    else 'OPEN'
  end                                                   as target_hit_state,
  case
    when o.outcome_code is not null then o.outcome_code::text
    else 'OPEN'
  end                                                   as outcome_state,
  coalesce(s.status::text, case when c.decision_code = 'TAKE_TRADE' then 'PENDING_SIGNAL' else c.decision_code::text end)
                                                        as status,
  s.emitted_at,
  s.packet_id,
  o.tp1_hit_ts,
  o.tp2_hit_ts,
  o.stopped_ts,
  o.censored_at_ts
from warbird_fib_candidates_15m         c
join warbird_fib_engine_snapshots_15m   snap on snap.snapshot_id = c.snapshot_id
left join warbird_signals_15m           s    on s.candidate_id = c.candidate_id
left join warbird_candidate_outcomes_15m o   on o.candidate_id = c.candidate_id;

comment on view warbird_admin_candidate_rows_v is
  'Admin row surface for screenshot-style setup monitoring. '
  'Exposes time, direction, anchor, target, retrace, fib ratio, target-hit state, outcome state, status, and model probabilities.';

-- ============================================================
-- warbird_candidate_stats_by_bucket_v
-- Aggregated empirical rates by the locked bucket key.
-- Resolved-only rates exclude censored rows from both numerator and denominator.
-- ============================================================
create or replace view warbird_candidate_stats_by_bucket_v
  with (security_invoker = true)
as
select
  c.direction,
  c.setup_archetype,
  c.fib_level_touched,
  c.regime_bucket,
  c.session_bucket,
  count(*) filter (where not o.is_censored)                                    as resolved_count,
  count(*) filter (where o.is_censored)                                        as censored_count,
  count(*) filter (where o.tp1_before_sl and not o.is_censored)                as tp1_before_sl_count,
  count(*) filter (where o.tp2_before_sl and not o.is_censored)                as tp2_before_sl_count,
  count(*) filter (where o.sl_before_tp1 and not o.is_censored)                as stopped_pre_tp1_count,
  count(*) filter (where o.sl_after_tp1_before_tp2 and not o.is_censored)      as stopped_post_tp1_count,
  count(*) filter (where o.reversal_detected and not o.is_censored)            as reversal_detected_count,
  round(
    (avg(case when o.tp1_before_sl then 1.0 else 0.0 end)
      filter (where not o.is_censored))::numeric,
    4
  )                                                                            as tp1_before_sl_rate,
  round(
    (avg(case when o.tp2_before_sl then 1.0 else 0.0 end)
      filter (where not o.is_censored))::numeric,
    4
  )                                                                            as tp2_before_sl_rate,
  round(
    (avg(case when o.sl_before_tp1 then 1.0 else 0.0 end)
      filter (where not o.is_censored))::numeric,
    4
  )                                                                            as sl_before_tp1_rate,
  round(
    (avg(o.mae_pts) filter (where not o.is_censored))::numeric,
    2
  )                                                                            as avg_mae_pts,
  round(
    (avg(o.mfe_pts) filter (where not o.is_censored))::numeric,
    2
  )                                                                            as avg_mfe_pts,
  round(
    (stddev(o.mae_pts) filter (where not o.is_censored))::numeric,
    2
  )                                                                            as stddev_mae_pts,
  round(
    (stddev(o.mfe_pts) filter (where not o.is_censored))::numeric,
    2
  )                                                                            as stddev_mfe_pts,
  min(c.bar_close_ts)                                                          as earliest_bar,
  max(c.bar_close_ts)                                                          as latest_bar
from warbird_fib_candidates_15m         c
join warbird_candidate_outcomes_15m     o on o.candidate_id = c.candidate_id
group by
  c.direction,
  c.setup_archetype,
  c.fib_level_touched,
  c.regime_bucket,
  c.session_bucket
having count(*) filter (where not o.is_censored) > 0;

comment on view warbird_candidate_stats_by_bucket_v is
  'Empirical resolved-only extension and stop rates by setup bucket. '
  'Censored rows are tracked separately and excluded from the rate denominator. '
  'Provides the calibrated stat surface for dashboard display post-cutover.';

-- ============================================================
-- warbird_active_packet_metrics_v
-- Current active packet metrics for the Admin page.
-- ============================================================
create or replace view warbird_active_packet_metrics_v
  with (security_invoker = true)
as
select
  p.packet_id,
  p.packet_version,
  p.contract_version,
  pa.activated_at,
  m.target_name,
  m.split_code,
  m.auc,
  m.log_loss,
  m.brier_score,
  m.calibration_error,
  m.resolved_count,
  m.censored_count,
  m.tp1_before_sl_rate,
  m.tp2_before_sl_rate,
  m.sl_before_tp1_rate,
  m.sl_after_tp1_before_tp2_rate,
  m.created_at as metrics_created_at
from warbird_packet_activations      pa
join warbird_packets                 p on p.packet_id = pa.packet_id
join warbird_packet_metrics          m on m.packet_id = p.packet_id
where pa.is_current;

comment on view warbird_active_packet_metrics_v is
  'Structured metrics for the currently active packet. '
  'Admin-page surface for selector quality, calibration, and resolved versus censored coverage.';

-- ============================================================
-- warbird_active_training_run_metrics_v
-- Full training/evaluation metrics for the currently active packet run.
-- ============================================================
create or replace view warbird_active_training_run_metrics_v
  with (security_invoker = true)
as
select
  p.packet_id,
  p.packet_version,
  p.run_id,
  m.target_name,
  m.split_code,
  m.fold_code,
  m.metric_family,
  m.metric_name,
  m.metric_value,
  m.metric_unit,
  m.metric_rank,
  m.is_primary,
  m.created_at
from warbird_packet_activations   pa
join warbird_packets              p on p.packet_id = pa.packet_id
join warbird_training_run_metrics m on m.run_id = p.run_id
where pa.is_current;

comment on view warbird_active_training_run_metrics_v is
  'Full training and evaluation metrics for the currently active packet run. '
  'Designed for Admin rendering of all model/training metrics without Markdown reports.';

-- ============================================================
-- warbird_active_packet_feature_importance_v
-- Top published drivers for the current active packet.
-- ============================================================
create or replace view warbird_active_packet_feature_importance_v
  with (security_invoker = true)
as
select
  p.packet_id,
  p.packet_version,
  fi.target_name,
  fi.feature_family,
  fi.feature_name,
  fi.importance_source_code,
  fi.importance_rank,
  fi.mean_abs_importance,
  fi.effect_direction_code,
  fi.created_at
from warbird_packet_activations         pa
join warbird_packets                    p  on p.packet_id = pa.packet_id
join warbird_packet_feature_importance  fi on fi.packet_id = p.packet_id
where pa.is_current;

comment on view warbird_active_packet_feature_importance_v is
  'Top published feature drivers for the currently active packet. '
  'Use this instead of exposing raw per-fold SHAP matrices in the dashboard.';

-- ============================================================
-- warbird_active_packet_recommendations_v
-- Structured AI-generated Admin guidance for the current active packet.
-- ============================================================
create or replace view warbird_active_packet_recommendations_v
  with (security_invoker = true)
as
select
  p.packet_id,
  p.packet_version,
  r.section_code,
  r.priority,
  r.recommendation_code,
  r.title,
  r.summary_text,
  r.rationale_json,
  r.action_json,
  r.created_at
from warbird_packet_activations       pa
join warbird_packets                  p on p.packet_id = pa.packet_id
join warbird_packet_recommendations   r on r.packet_id = p.packet_id
where pa.is_current;

comment on view warbird_active_packet_recommendations_v is
  'Structured AI-generated Admin-page guidance for the currently active packet. '
  'Designed for formatted UI rendering, not Markdown report blobs.';

-- ============================================================
-- warbird_active_packet_setting_hypotheses_v
-- Published setting suggestions for the current active packet.
-- ============================================================
create or replace view warbird_active_packet_setting_hypotheses_v
  with (security_invoker = true)
as
select
  p.packet_id,
  p.packet_version,
  h.target_name,
  h.indicator_family,
  h.parameter_name,
  h.action_code,
  h.suggested_numeric_value,
  h.suggested_text_value,
  h.stability_score,
  h.evidence_feature_family,
  h.support_summary_json,
  h.created_at
from warbird_packet_activations       pa
join warbird_packets                  p on p.packet_id = pa.packet_id
join warbird_packet_setting_hypotheses h on h.packet_id = p.packet_id
where pa.is_current;

comment on view warbird_active_packet_setting_hypotheses_v is
  'Published indicator and entry-definition setting suggestions for the currently active packet.';

commit;
