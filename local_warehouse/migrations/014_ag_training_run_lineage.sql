-- Migration 014: local AG run metadata and SHAP lineage tables
-- Authority:
--   - docs/MASTER_PLAN.md Phase 5
--   - WARBIRD_MODEL_SPEC.md Section 8
-- Local-only lineage spine for AutoGluon runs and SHAP outputs.

CREATE TABLE IF NOT EXISTS ag_training_runs (
  run_id                     TEXT PRIMARY KEY,
  run_kind                   TEXT        NOT NULL DEFAULT 'AUTOGLOON_TABULAR',
  run_status                 TEXT        NOT NULL,
  dry_run                    BOOLEAN     NOT NULL DEFAULT FALSE,
  problem_type               TEXT        NOT NULL,
  label_name                 TEXT        NOT NULL,
  eval_metric                TEXT        NOT NULL,
  presets                    TEXT        NOT NULL,
  time_limit_sec             INT,
  num_bag_folds              INT,
  num_stack_levels           INT,
  dynamic_stacking_mode      TEXT        NOT NULL,
  excluded_model_types_json  JSONB       NOT NULL DEFAULT '[]'::jsonb,
  training_zoo_scope         TEXT,
  start_date_ct              DATE,
  end_date_ct                DATE,
  actual_start_date_ct       DATE,
  actual_end_date_ct         DATE,
  rows_total                 INT,
  sessions_total             INT,
  feature_count              INT,
  fold_count                 INT,
  coverage_json              JSONB       NOT NULL DEFAULT '{}'::jsonb,
  feature_manifest_json      JSONB       NOT NULL DEFAULT '{}'::jsonb,
  command_json               JSONB       NOT NULL DEFAULT '{}'::jsonb,
  git_commit_sha             TEXT,
  error_message              TEXT,
  started_at                 TIMESTAMPTZ NOT NULL,
  completed_at               TIMESTAMPTZ,
  created_at                 TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT ag_training_runs_run_status_ck
    CHECK (run_status IN ('RUNNING', 'SUCCEEDED', 'FAILED', 'BLOCKED')),
  CONSTRAINT ag_training_runs_run_kind_ck
    CHECK (run_kind IN ('AUTOGLOON_TABULAR')),
  CONSTRAINT ag_training_runs_dynamic_stacking_mode_ck
    CHECK (dynamic_stacking_mode IN ('off', 'auto')),
  CONSTRAINT ag_training_runs_excluded_model_types_json_ck
    CHECK (jsonb_typeof(excluded_model_types_json) = 'array'),
  CONSTRAINT ag_training_runs_coverage_json_ck
    CHECK (jsonb_typeof(coverage_json) = 'object'),
  CONSTRAINT ag_training_runs_feature_manifest_json_ck
    CHECK (jsonb_typeof(feature_manifest_json) = 'object'),
  CONSTRAINT ag_training_runs_command_json_ck
    CHECK (jsonb_typeof(command_json) = 'object'),
  CONSTRAINT ag_training_runs_rows_total_ck
    CHECK (rows_total IS NULL OR rows_total >= 0),
  CONSTRAINT ag_training_runs_sessions_total_ck
    CHECK (sessions_total IS NULL OR sessions_total >= 0),
  CONSTRAINT ag_training_runs_feature_count_ck
    CHECK (feature_count IS NULL OR feature_count >= 0),
  CONSTRAINT ag_training_runs_fold_count_ck
    CHECK (fold_count IS NULL OR fold_count >= 0),
  CONSTRAINT ag_training_runs_time_limit_sec_ck
    CHECK (time_limit_sec IS NULL OR time_limit_sec > 0),
  CONSTRAINT ag_training_runs_num_bag_folds_ck
    CHECK (num_bag_folds IS NULL OR num_bag_folds >= 0),
  CONSTRAINT ag_training_runs_num_stack_levels_ck
    CHECK (num_stack_levels IS NULL OR num_stack_levels >= 0)
);

CREATE INDEX IF NOT EXISTS ag_training_runs_status_started_idx
  ON ag_training_runs (run_status, started_at DESC);

CREATE TABLE IF NOT EXISTS ag_training_run_metrics (
  metric_id          BIGSERIAL PRIMARY KEY,
  run_id             TEXT        NOT NULL REFERENCES ag_training_runs(run_id) ON DELETE CASCADE,
  target_name        TEXT        NOT NULL,
  fold_code          TEXT        NOT NULL,
  split_code         TEXT        NOT NULL,
  metric_scope       TEXT        NOT NULL,
  metric_name        TEXT        NOT NULL,
  metric_value       FLOAT8      NOT NULL,
  row_count          INT,
  class_count        INT,
  model_name         TEXT,
  created_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT ag_training_run_metrics_split_code_ck
    CHECK (split_code IN ('train', 'val', 'test', 'overall')),
  CONSTRAINT ag_training_run_metrics_metric_scope_ck
    CHECK (metric_scope IN ('BASELINE', 'AUTOGLOON')),
  CONSTRAINT ag_training_run_metrics_row_count_ck
    CHECK (row_count IS NULL OR row_count >= 0),
  CONSTRAINT ag_training_run_metrics_class_count_ck
    CHECK (class_count IS NULL OR class_count >= 0)
);

CREATE INDEX IF NOT EXISTS ag_training_run_metrics_run_fold_idx
  ON ag_training_run_metrics (run_id, fold_code, split_code, metric_scope, metric_name);

CREATE TABLE IF NOT EXISTS ag_artifacts (
  artifact_id        BIGSERIAL PRIMARY KEY,
  run_id             TEXT        NOT NULL REFERENCES ag_training_runs(run_id) ON DELETE CASCADE,
  artifact_type      TEXT        NOT NULL,
  target_name        TEXT,
  fold_code          TEXT,
  split_code         TEXT,
  artifact_path      TEXT        NOT NULL,
  media_type         TEXT,
  file_size_bytes    BIGINT,
  sha256             TEXT,
  created_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT ag_artifacts_artifact_type_ck
    CHECK (artifact_type IN (
      'DATASET_SUMMARY',
      'FEATURE_MANIFEST',
      'TRAINING_SUMMARY',
      'FOLD_SUMMARY',
      'LEADERBOARD',
      'PREDICTOR_DIR',
      'RAW_SHAP_VALUES',
      'RAW_SHAP_INTERACTIONS'
    )),
  CONSTRAINT ag_artifacts_file_size_bytes_ck
    CHECK (file_size_bytes IS NULL OR file_size_bytes >= 0),
  CONSTRAINT ag_artifacts_run_path_uq
    UNIQUE (run_id, artifact_path)
);

CREATE INDEX IF NOT EXISTS ag_artifacts_run_type_idx
  ON ag_artifacts (run_id, artifact_type, created_at DESC);

CREATE TABLE IF NOT EXISTS ag_shap_feature_summary (
  shap_feature_summary_id  BIGSERIAL PRIMARY KEY,
  run_id                   TEXT        NOT NULL REFERENCES ag_training_runs(run_id) ON DELETE CASCADE,
  target_name              TEXT        NOT NULL,
  split_code               TEXT        NOT NULL,
  fold_code                TEXT        NOT NULL,
  model_name               TEXT,
  feature_name             TEXT        NOT NULL,
  mean_abs_shap            FLOAT8      NOT NULL,
  importance_rank          INT,
  source_artifact_id       BIGINT      REFERENCES ag_artifacts(artifact_id) ON DELETE SET NULL,
  created_at               TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT ag_shap_feature_summary_split_code_ck
    CHECK (split_code IN ('train', 'val', 'test', 'overall')),
  CONSTRAINT ag_shap_feature_summary_mean_abs_ck
    CHECK (mean_abs_shap >= 0),
  CONSTRAINT ag_shap_feature_summary_rank_ck
    CHECK (importance_rank IS NULL OR importance_rank >= 1)
);

CREATE INDEX IF NOT EXISTS ag_shap_feature_summary_run_target_idx
  ON ag_shap_feature_summary (run_id, target_name, fold_code, split_code, importance_rank);

CREATE TABLE IF NOT EXISTS ag_shap_cohort_summary (
  shap_cohort_summary_id    BIGSERIAL PRIMARY KEY,
  run_id                    TEXT        NOT NULL REFERENCES ag_training_runs(run_id) ON DELETE CASCADE,
  target_name               TEXT        NOT NULL,
  split_code                TEXT        NOT NULL,
  fold_code                 TEXT        NOT NULL,
  model_name                TEXT,
  fib_level_touched         INT,
  direction                 INT,
  outcome_label             TEXT,
  stop_family_code          TEXT,
  session_bucket            TEXT,
  volatility_regime_code    TEXT,
  feature_name              TEXT        NOT NULL,
  mean_abs_shap             FLOAT8      NOT NULL,
  importance_rank           INT,
  cohort_row_count          INT,
  source_artifact_id        BIGINT      REFERENCES ag_artifacts(artifact_id) ON DELETE SET NULL,
  created_at                TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT ag_shap_cohort_summary_split_code_ck
    CHECK (split_code IN ('train', 'val', 'test', 'overall')),
  CONSTRAINT ag_shap_cohort_summary_direction_ck
    CHECK (direction IS NULL OR direction IN (-1, 1)),
  CONSTRAINT ag_shap_cohort_summary_mean_abs_ck
    CHECK (mean_abs_shap >= 0),
  CONSTRAINT ag_shap_cohort_summary_rank_ck
    CHECK (importance_rank IS NULL OR importance_rank >= 1),
  CONSTRAINT ag_shap_cohort_summary_row_count_ck
    CHECK (cohort_row_count IS NULL OR cohort_row_count >= 0)
);

CREATE INDEX IF NOT EXISTS ag_shap_cohort_summary_run_target_idx
  ON ag_shap_cohort_summary (
    run_id,
    target_name,
    fold_code,
    split_code,
    session_bucket,
    volatility_regime_code,
    importance_rank
  );

CREATE TABLE IF NOT EXISTS ag_shap_interaction_summary (
  shap_interaction_summary_id BIGSERIAL PRIMARY KEY,
  run_id                      TEXT        NOT NULL REFERENCES ag_training_runs(run_id) ON DELETE CASCADE,
  target_name                 TEXT        NOT NULL,
  split_code                  TEXT        NOT NULL,
  fold_code                   TEXT        NOT NULL,
  model_name                  TEXT,
  fib_level_touched           INT,
  direction                   INT,
  outcome_label               TEXT,
  stop_family_code            TEXT,
  session_bucket              TEXT,
  volatility_regime_code      TEXT,
  feature_name_left           TEXT        NOT NULL,
  feature_name_right          TEXT        NOT NULL,
  mean_abs_interaction        FLOAT8      NOT NULL,
  interaction_rank            INT,
  cohort_row_count            INT,
  source_artifact_id          BIGINT      REFERENCES ag_artifacts(artifact_id) ON DELETE SET NULL,
  created_at                  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT ag_shap_interaction_summary_split_code_ck
    CHECK (split_code IN ('train', 'val', 'test', 'overall')),
  CONSTRAINT ag_shap_interaction_summary_direction_ck
    CHECK (direction IS NULL OR direction IN (-1, 1)),
  CONSTRAINT ag_shap_interaction_summary_mean_abs_ck
    CHECK (mean_abs_interaction >= 0),
  CONSTRAINT ag_shap_interaction_summary_rank_ck
    CHECK (interaction_rank IS NULL OR interaction_rank >= 1),
  CONSTRAINT ag_shap_interaction_summary_row_count_ck
    CHECK (cohort_row_count IS NULL OR cohort_row_count >= 0),
  CONSTRAINT ag_shap_interaction_summary_feature_pair_ck
    CHECK (feature_name_left <> feature_name_right)
);

CREATE INDEX IF NOT EXISTS ag_shap_interaction_summary_run_target_idx
  ON ag_shap_interaction_summary (run_id, target_name, fold_code, split_code, interaction_rank);

CREATE TABLE IF NOT EXISTS ag_shap_temporal_stability (
  shap_temporal_stability_id  BIGSERIAL PRIMARY KEY,
  run_id                      TEXT        NOT NULL REFERENCES ag_training_runs(run_id) ON DELETE CASCADE,
  target_name                 TEXT        NOT NULL,
  feature_name                TEXT        NOT NULL,
  base_fold_code              TEXT,
  compare_fold_code           TEXT,
  rank_correlation            FLOAT8,
  importance_drift_norm       FLOAT8,
  stability_bucket            TEXT        NOT NULL,
  created_at                  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT ag_shap_temporal_stability_stability_bucket_ck
    CHECK (stability_bucket IN ('HIGH', 'MEDIUM', 'LOW', 'UNSTABLE'))
);

CREATE INDEX IF NOT EXISTS ag_shap_temporal_stability_run_target_idx
  ON ag_shap_temporal_stability (run_id, target_name, feature_name);

CREATE TABLE IF NOT EXISTS ag_shap_feature_decisions (
  shap_feature_decision_id  BIGSERIAL PRIMARY KEY,
  run_id                    TEXT        NOT NULL REFERENCES ag_training_runs(run_id) ON DELETE CASCADE,
  target_name               TEXT        NOT NULL,
  feature_name              TEXT        NOT NULL,
  decision_code             TEXT        NOT NULL,
  supporting_run_count      INT,
  decision_reason           TEXT,
  evidence_json             JSONB       NOT NULL DEFAULT '{}'::jsonb,
  approved_by               TEXT,
  created_at                TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT ag_shap_feature_decisions_decision_code_ck
    CHECK (decision_code IN (
      'KEEP',
      'REVIEW_DROP',
      'DROP_APPROVED',
      'RETAIN_FOR_INTERACTION',
      'PROMOTE'
    )),
  CONSTRAINT ag_shap_feature_decisions_supporting_run_count_ck
    CHECK (supporting_run_count IS NULL OR supporting_run_count >= 0),
  CONSTRAINT ag_shap_feature_decisions_evidence_json_ck
    CHECK (jsonb_typeof(evidence_json) = 'object')
);

CREATE INDEX IF NOT EXISTS ag_shap_feature_decisions_run_target_idx
  ON ag_shap_feature_decisions (run_id, target_name, feature_name, created_at DESC);

CREATE TABLE IF NOT EXISTS ag_shap_run_drift (
  shap_run_drift_id  BIGSERIAL PRIMARY KEY,
  run_id             TEXT        NOT NULL REFERENCES ag_training_runs(run_id) ON DELETE CASCADE,
  prior_run_id       TEXT        REFERENCES ag_training_runs(run_id) ON DELETE SET NULL,
  target_name        TEXT        NOT NULL,
  drift_scope        TEXT        NOT NULL,
  feature_name       TEXT,
  cohort_name        TEXT,
  cohort_value       TEXT,
  metric_name        TEXT        NOT NULL,
  prior_value        FLOAT8,
  current_value      FLOAT8,
  delta_value        FLOAT8,
  rank_delta         INT,
  created_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT ag_shap_run_drift_scope_ck
    CHECK (drift_scope IN ('GLOBAL', 'COHORT', 'INTERACTION', 'METRIC'))
);

CREATE INDEX IF NOT EXISTS ag_shap_run_drift_run_target_idx
  ON ag_shap_run_drift (run_id, target_name, drift_scope, metric_name, created_at DESC);

INSERT INTO local_schema_migrations (filename) VALUES ('014_ag_training_run_lineage.sql')
  ON CONFLICT (filename) DO NOTHING;
