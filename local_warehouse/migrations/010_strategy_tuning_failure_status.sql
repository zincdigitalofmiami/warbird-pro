-- Migration 010: Add FAILED status and failure_reason column to strategy tuning trials
-- Purpose: Allow the hardened CDP tuner (Phase A) to persist failure rows with structured
--          reason codes instead of silently discarding them. Also adds TV_MCP_STRICT as
--          an authoritative evaluation_mode for trials recorded via the hardened CDP path.

-- Drop and recreate the status CHECK to add 'FAILED'
ALTER TABLE warbird_strategy_tuning_trials
  DROP CONSTRAINT IF EXISTS warbird_strategy_tuning_trials_status_check;

ALTER TABLE warbird_strategy_tuning_trials
  ADD CONSTRAINT warbird_strategy_tuning_trials_status_check
  CHECK (status IN ('SUGGESTED', 'RECORDED', 'REJECTED', 'FAILED'));

-- Drop and recreate the evaluation_mode CHECK to add 'TV_MCP_STRICT'
ALTER TABLE warbird_strategy_tuning_trials
  DROP CONSTRAINT IF EXISTS warbird_strategy_tuning_trials_evaluation_mode_check;

ALTER TABLE warbird_strategy_tuning_trials
  ADD CONSTRAINT warbird_strategy_tuning_trials_evaluation_mode_check
  CHECK (evaluation_mode IN ('PENDING', 'CSV_FULL', 'TV_DOM_SCREEN', 'TV_MCP_STRICT'));

-- Add failure_reason column (NULL for RECORDED/SUGGESTED rows)
ALTER TABLE warbird_strategy_tuning_trials
  ADD COLUMN IF NOT EXISTS failure_reason TEXT;

-- Enforce allowed values on failure_reason when non-null
ALTER TABLE warbird_strategy_tuning_trials
  DROP CONSTRAINT IF EXISTS warbird_strategy_tuning_trials_failure_reason_check;

ALTER TABLE warbird_strategy_tuning_trials
  ADD CONSTRAINT warbird_strategy_tuning_trials_failure_reason_check
  CHECK (
    failure_reason IS NULL OR
    failure_reason IN ('no_recalc', 'invalid_input', 'schema_drift', 'compile_error', 'tv_disconnected')
  );

-- Index to query/count failures by profile + reason
CREATE INDEX IF NOT EXISTS warbird_strategy_tuning_trials_profile_failed_idx
  ON warbird_strategy_tuning_trials (profile_name, failure_reason)
  WHERE status = 'FAILED';

INSERT INTO local_schema_migrations (filename) VALUES ('010_strategy_tuning_failure_status.sql')
  ON CONFLICT (filename) DO NOTHING;
