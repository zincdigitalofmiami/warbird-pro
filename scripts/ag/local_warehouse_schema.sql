-- Local warehouse schema — research child tables
-- NOT deployed to cloud Supabase. Apply to local PostgreSQL only.
--
-- Prerequisites: the canonical cloud tables must exist in the local DB first.
-- Either restore them from a cloud snapshot or run the cloud migration against
-- the local instance before applying this file.
--
-- These tables stay local because they answer research questions such as:
--   a) why a candidate stopped out or reached TP1 / TP2,
--   b) which feature families should be added or removed,
--   c) how entry definition should change,
--   d) which diagnostics may later earn promotion into live logic.
--
-- All foreign keys reference the canonical cloud tables assumed to be present.

begin;

-- ============================================================
-- warbird_shap_results
-- Local explainability summaries per training run. Never published to cloud.
-- ============================================================
create table warbird_shap_results (
  shap_result_id        uuid        primary key default gen_random_uuid(),
  run_id                uuid        not null references warbird_training_runs(run_id) on delete cascade,
  feature_name          text        not null,
  feature_family        text        not null,
  tier                  text        not null,
  model_name            text,
  mean_abs_shap         numeric     not null,
  rank_in_run           integer     not null,
  golden_zone_min       numeric,
  golden_zone_max       numeric,
  created_at            timestamptz not null default now(),
  constraint uq_warbird_shap_results_run_feature_model
    unique (run_id, feature_name, model_name),
  constraint ck_warbird_shap_results_mean_abs
    check (mean_abs_shap >= 0),
  constraint ck_warbird_shap_results_rank
    check (rank_in_run >= 1)
);

create index idx_warbird_shap_results_run_rank
  on warbird_shap_results (run_id, rank_in_run);

comment on table warbird_shap_results is
  'Local SHAP summaries per training run. '
  'LOCAL ONLY — used to explain model behavior and rank feature families for promotion review.';

-- ============================================================
-- warbird_shap_indicator_settings
-- SHAP-derived indicator-setting candidates for later review.
-- ============================================================
create table warbird_shap_indicator_settings (
  setting_id               uuid        primary key default gen_random_uuid(),
  run_id                   uuid        not null references warbird_training_runs(run_id) on delete cascade,
  indicator_family         text        not null,
  parameter_name           text        not null,
  suggested_numeric_value  numeric,
  suggested_text_value     text,
  stability_score          numeric,
  support_json             jsonb       not null default '{}'::jsonb,
  created_at               timestamptz not null default now(),
  constraint ck_warbird_shap_indicator_settings_stability
    check (stability_score is null or stability_score between 0 and 1),
  constraint ck_warbird_shap_indicator_settings_support_json
    check (jsonb_typeof(support_json) = 'object')
);

create index idx_warbird_shap_indicator_settings_run_family
  on warbird_shap_indicator_settings (run_id, indicator_family, created_at desc);

comment on table warbird_shap_indicator_settings is
  'Local-only SHAP-derived indicator-setting hypotheses. '
  'Used to test whether model evidence supports changing entry-definition or indicator parameters.';

-- ============================================================
-- warbird_snapshot_pine_features
-- All ml_* fields captured from the Pine hidden export at each snapshot bar close.
-- Keyed 1:1 with warbird_fib_engine_snapshots_15m.
-- Core identity fields are required. Family-specific fields remain nullable so
-- phased feature admission does not force schema churn.
-- ============================================================
create table warbird_snapshot_pine_features (
  snapshot_id                            uuid        not null primary key
    references warbird_fib_engine_snapshots_15m(snapshot_id) on delete cascade,
  captured_at                            timestamptz not null default now(),
  feature_contract_version               text        not null default 'v1',

  -- confidence and setup identity
  ml_confidence_score                    numeric     not null,
  ml_direction_code                      smallint    not null,
  ml_setup_archetype_code                smallint    not null,
  ml_fib_level_touched                   numeric     not null,
  ml_stop_family_code                    smallint    not null,

  -- event-response block
  ml_event_mode_code                     smallint,
  ml_event_shock_score                   numeric,
  ml_event_reversal_score                numeric,
  ml_event_nq_state                      smallint,
  ml_event_dxy_state                     smallint,
  ml_event_zn_state                      smallint,
  ml_event_vix_state                     smallint,
  ml_event_pivot_interaction_code        smallint,

  -- ema context
  ml_ema21_dir                           smallint,
  ml_ema50_dir                           smallint,
  ml_ema200_dir                          smallint,
  ml_ema21_dist_pct                      numeric,
  ml_ema50_dist_pct                      numeric,
  ml_ema200_dist_pct                     numeric,

  -- trigger events (binary 0/1 coded as smallint matching Pine plot output)
  ml_entry_long_trigger                  smallint,
  ml_entry_short_trigger                 smallint,
  ml_tp1_hit_event                       smallint,
  ml_tp2_hit_event                       smallint,

  -- BigBeluga pivot harness
  ml_pivot_distance_nearest              numeric,
  ml_pivot_cluster_count                 smallint,
  ml_pivot_active_zone_code              smallint,
  ml_pivot_layer_length                  smallint,
  ml_pivot_volume_nearest                numeric,
  ml_pivot_volume_distribution_pct       numeric,

  -- LuxAlgo MSB/OB harness
  ml_msb_direction_code                  smallint,
  ml_msb_momentum_zscore                 numeric,
  ml_ob_active_count                     smallint,
  ml_ob_hpz_active_count                 smallint,
  ml_ob_nearest_distance                 numeric,
  ml_ob_nearest_quality_score            numeric,
  ml_ob_nearest_poc                      numeric,
  ml_ob_nearest_direction_code           smallint,
  ml_ob_nearest_mitigated_code           smallint,
  ml_ob_reliability_pct                  numeric,

  -- LuxAlgo Luminance harness
  ml_luminance_signal                    smallint,
  ml_luminance_upper_threshold           numeric,
  ml_luminance_lower_threshold           numeric,
  ml_luminance_intensity                 numeric,
  ml_luminance_direction_code            smallint,
  ml_luminance_breakout_code             smallint,
  ml_luminance_bull_ob_active_count      smallint,
  ml_luminance_bear_ob_active_count      smallint,
  ml_luminance_bull_ob_mitigated_count   smallint,
  ml_luminance_bear_ob_mitigated_count   smallint,
  ml_luminance_bull_ob_nearest_distance  numeric,
  ml_luminance_bear_ob_nearest_distance  numeric,
  ml_luminance_bull_ob_nearest_intensity numeric,
  ml_luminance_bear_ob_nearest_intensity numeric
);

comment on table warbird_snapshot_pine_features is
  'All ml_* Pine hidden export fields per snapshot bar close. '
  'LOCAL ONLY — never deployed to cloud Supabase. '
  'Core identity fields are required; family-specific fields stay nullable so phased admission does not force schema churn.';

-- ============================================================
-- warbird_candidate_macro_context
-- Tier 2 macro/news/GPR context at candidate bar close.
-- ============================================================
create table warbird_candidate_macro_context (
  candidate_id           uuid        not null primary key
    references warbird_fib_candidates_15m(candidate_id) on delete cascade,
  bar_date               date        not null,
  nq_return_d1           numeric,
  dxy_return_d1          numeric,
  zn_return_d1           numeric,
  vix_level_d1           numeric,
  vol_state_at_bar       text,
  macro_window_active    boolean     not null default false,
  next_release_hours     numeric,
  prev_release_hours     numeric,
  news_signal_direction  text,
  news_relevance_score   numeric,
  gpr_level              numeric,
  trump_effect_active    boolean     not null default false,
  fred_dgs10             numeric,
  fred_dgs2              numeric,
  fred_effr              numeric,
  fred_vixcls            numeric,
  captured_at            timestamptz not null default now(),
  constraint ck_macro_ctx_next_release
    check (next_release_hours is null or next_release_hours >= 0),
  constraint ck_macro_ctx_prev_release
    check (prev_release_hours is null or prev_release_hours >= 0)
);

create index idx_wmcc_bar_date on warbird_candidate_macro_context (bar_date);

comment on table warbird_candidate_macro_context is
  'Tier 2 macro/news/GPR context at candidate bar close. '
  'LOCAL ONLY — never deployed to cloud Supabase. '
  'Tier 2 cannot enter live Pine without explicit promotion.';

-- ============================================================
-- warbird_candidate_microstructure
-- 1m-derived volume and order-flow context around the candidate setup window.
-- Only OHLCV-derived features are allowed here under the current data contract.
-- ============================================================
create table warbird_candidate_microstructure (
  candidate_id              uuid        not null primary key
    references warbird_fib_candidates_15m(candidate_id) on delete cascade,
  window_bars               smallint    not null,
  window_start_ts           timestamptz not null,
  window_end_ts             timestamptz not null,
  vol_avg_window            numeric     not null,
  vol_ratio_at_entry        numeric     not null,
  vol_shock_flag            boolean     not null,
  price_range_pct           numeric     not null,
  up_bar_pct                numeric     not null,
  down_bar_pct              numeric     not null,
  atr_14_at_touch           numeric     not null,
  vwap_distance_pts         numeric,
  captured_at               timestamptz not null default now(),
  constraint ck_microstructure_window_bars
    check (window_bars >= 1),
  constraint ck_microstructure_window_order
    check (window_end_ts >= window_start_ts),
  constraint ck_microstructure_vol_avg
    check (vol_avg_window >= 0),
  constraint ck_microstructure_price_range
    check (price_range_pct >= 0),
  constraint ck_microstructure_up_down_pct
    check (up_bar_pct between 0 and 1 and down_bar_pct between 0 and 1)
);

create index idx_wmicro_window_end on warbird_candidate_microstructure (window_end_ts desc);

comment on table warbird_candidate_microstructure is
  '1m OHLCV-derived microstructure context around the candidate setup window. '
  'LOCAL ONLY — never deployed to cloud Supabase. '
  'Do not store true order-book, spread, or trade-delta fields here unless a real source is admitted.';

-- ============================================================
-- warbird_candidate_path_diagnostics
-- Deterministic path facts derived after outcome scoring to explain what happened.
-- ============================================================
create table warbird_candidate_path_diagnostics (
  candidate_id                 uuid        not null primary key
    references warbird_candidate_outcomes_15m(candidate_id) on delete cascade,
  first_touch_code             text        not null,
  first_touch_ts               timestamptz,
  bars_to_tp1                  integer,
  bars_to_tp2                  integer,
  bars_to_stop                 integer,
  same_bar_conflict_stop_tp1   boolean     not null default false,
  same_bar_conflict_stop_tp2   boolean     not null default false,
  entry_to_stop_distance_pts   numeric     not null,
  entry_to_tp1_distance_pts    numeric     not null,
  entry_to_tp2_distance_pts    numeric     not null,
  mae_before_tp1_pts           numeric,
  mfe_before_stop_pts          numeric,
  captured_at                  timestamptz not null default now(),
  constraint ck_path_diag_first_touch
    check (first_touch_code in ('TP1', 'TP2', 'STOP', 'NONE')),
  constraint ck_path_diag_bars_to_tp1
    check (bars_to_tp1 is null or bars_to_tp1 >= 1),
  constraint ck_path_diag_bars_to_tp2
    check (bars_to_tp2 is null or bars_to_tp2 >= 1),
  constraint ck_path_diag_bars_to_stop
    check (bars_to_stop is null or bars_to_stop >= 1),
  constraint ck_path_diag_stop_distance
    check (entry_to_stop_distance_pts >= 0),
  constraint ck_path_diag_tp1_distance
    check (entry_to_tp1_distance_pts >= 0),
  constraint ck_path_diag_tp2_distance
    check (entry_to_tp2_distance_pts >= 0)
);

comment on table warbird_candidate_path_diagnostics is
  'Path-level diagnostics that explain which barrier was touched first, how quickly, and under what same-bar conflicts. '
  'LOCAL ONLY — diagnostic support for why trades won or lost.';

-- ============================================================
-- warbird_candidate_stopout_attribution
-- Human-readable and model-usable attribution for losing candidates.
-- ============================================================
create table warbird_candidate_stopout_attribution (
  candidate_id                   uuid        not null primary key
    references warbird_candidate_outcomes_15m(candidate_id) on delete cascade,
  stop_driver_code               text        not null,
  stop_driver_confidence         numeric,
  vol_state_at_stop              text,
  adverse_excursion_zscore       numeric,
  entry_efficiency_pct           numeric,
  volatility_expansion_flag      boolean     not null default false,
  event_conflict_flag            boolean     not null default false,
  cross_asset_divergence_flag    boolean     not null default false,
  structure_failure_flag         boolean     not null default false,
  late_entry_flag                boolean     not null default false,
  thin_liquidity_flag            boolean     not null default false,
  notes_json                     jsonb       not null default '{}'::jsonb,
  captured_at                    timestamptz not null default now(),
  constraint ck_stop_attr_driver
    check (stop_driver_code in (
      'VOL_EXPANSION',
      'EVENT_CONFLICT',
      'CROSS_ASSET_DIVERGENCE',
      'STRUCTURE_FAILURE',
      'LATE_ENTRY',
      'THIN_LIQUIDITY',
      'OTHER'
    )),
  constraint ck_stop_attr_confidence
    check (stop_driver_confidence is null or stop_driver_confidence between 0 and 1),
  constraint ck_stop_attr_efficiency
    check (entry_efficiency_pct is null or entry_efficiency_pct between 0 and 1),
  constraint ck_stop_attr_notes_json
    check (jsonb_typeof(notes_json) = 'object')
);

create index idx_stop_attr_driver on warbird_candidate_stopout_attribution (stop_driver_code);

comment on table warbird_candidate_stopout_attribution is
  'Attribution layer for why candidates stopped out or failed to progress. '
  'LOCAL ONLY — used for diagnostics, SHAP review, and entry-improvement work.';

-- ============================================================
-- warbird_feature_ablation_runs
-- Experiment log for feature-family add/remove tests.
-- ============================================================
create table warbird_feature_ablation_runs (
  ablation_run_id            uuid        primary key default gen_random_uuid(),
  baseline_run_id            uuid        not null references warbird_training_runs(run_id) on delete cascade,
  candidate_run_id           uuid        not null references warbird_training_runs(run_id) on delete cascade,
  feature_family             text        not null,
  experiment_kind            text        not null,
  split_code                 text        not null,
  metric_name                text        not null,
  baseline_metric_value      numeric     not null,
  candidate_metric_value     numeric     not null,
  delta_metric_value         numeric     not null,
  selected_for_promotion     boolean     not null default false,
  summary_json               jsonb       not null default '{}'::jsonb,
  created_at                 timestamptz not null default now(),
  constraint ck_ablation_experiment_kind
    check (experiment_kind in ('DROP_FAMILY', 'ONLY_FAMILY', 'REWEIGHT_FAMILY', 'PARAMETER_FREEZE')),
  constraint ck_ablation_summary_json
    check (jsonb_typeof(summary_json) = 'object')
);

create index idx_ablation_baseline_family
  on warbird_feature_ablation_runs (baseline_run_id, feature_family, created_at desc);
create index idx_ablation_candidate_run
  on warbird_feature_ablation_runs (candidate_run_id);

comment on table warbird_feature_ablation_runs is
  'Feature-family ablation evidence used to decide what data to add, remove, or keep. '
  'LOCAL ONLY — supports SHAP review and promotion decisions.';

-- ============================================================
-- warbird_entry_definition_experiments
-- Experiment log for alternate candidate-entry definitions.
-- ============================================================
create table warbird_entry_definition_experiments (
  experiment_id              uuid        primary key default gen_random_uuid(),
  run_id                     uuid references warbird_training_runs(run_id) on delete set null,
  experiment_code            text        not null unique,
  anchor_policy_code         text        not null,
  retrace_rule_code          text        not null,
  confirmation_rule_code     text        not null,
  trigger_timing_code        text        not null,
  stop_policy_code           text        not null,
  candidate_count            integer     not null,
  resolved_count             integer     not null,
  tp1_before_sl_rate         numeric,
  tp2_before_sl_rate         numeric,
  sl_before_tp1_rate         numeric,
  calibration_error          numeric,
  selected_for_next_round    boolean     not null default false,
  notes_json                 jsonb       not null default '{}'::jsonb,
  created_at                 timestamptz not null default now(),
  constraint ck_entry_experiment_candidate_count
    check (candidate_count >= 0),
  constraint ck_entry_experiment_resolved_count
    check (resolved_count >= 0 and resolved_count <= candidate_count),
  constraint ck_entry_experiment_tp1_rate
    check (tp1_before_sl_rate is null or tp1_before_sl_rate between 0 and 1),
  constraint ck_entry_experiment_tp2_rate
    check (tp2_before_sl_rate is null or tp2_before_sl_rate between 0 and 1),
  constraint ck_entry_experiment_sl_rate
    check (sl_before_tp1_rate is null or sl_before_tp1_rate between 0 and 1),
  constraint ck_entry_experiment_calibration_error
    check (calibration_error is null or calibration_error >= 0),
  constraint ck_entry_experiment_notes_json
    check (jsonb_typeof(notes_json) = 'object')
);

create index idx_entry_experiments_run_id
  on warbird_entry_definition_experiments (run_id, created_at desc);
create index idx_entry_experiments_selected
  on warbird_entry_definition_experiments (selected_for_next_round, created_at desc);

comment on table warbird_entry_definition_experiments is
  'Experiment results for alternate anchor, retrace, confirmation, trigger-timing, and stop-policy definitions. '
  'LOCAL ONLY — primary surface for improving entry quality.';

commit;
