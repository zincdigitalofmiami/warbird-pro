-- Migration 009: Split authoritative CSV records from fast TradingView DOM screens
-- Purpose: Keep programmatic TV optimization runs from overwriting CSV-backed results
-- that share the same parameter signature.

ALTER TABLE warbird_strategy_tuning_trials
  ADD COLUMN IF NOT EXISTS evaluation_mode TEXT;

UPDATE warbird_strategy_tuning_trials
SET evaluation_mode = CASE
  WHEN status = 'SUGGESTED' THEN 'PENDING'
  ELSE 'CSV_FULL'
END
WHERE evaluation_mode IS NULL;

ALTER TABLE warbird_strategy_tuning_trials
  DROP CONSTRAINT IF EXISTS warbird_strategy_tuning_trials_profile_name_params_signature_key;

ALTER TABLE warbird_strategy_tuning_trials
  DROP CONSTRAINT IF EXISTS warbird_strategy_tuning_trial_profile_name_params_signature_key;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM pg_constraint
    WHERE conname = 'warbird_strategy_tuning_trials_evaluation_mode_check'
  ) THEN
    ALTER TABLE warbird_strategy_tuning_trials
      ADD CONSTRAINT warbird_strategy_tuning_trials_evaluation_mode_check
      CHECK (evaluation_mode IN ('PENDING', 'CSV_FULL', 'TV_DOM_SCREEN'));
  END IF;
END $$;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM pg_constraint
    WHERE conname = 'warbird_strategy_tuning_trials_profile_sig_mode_key'
  ) THEN
    ALTER TABLE warbird_strategy_tuning_trials
      ADD CONSTRAINT warbird_strategy_tuning_trials_profile_sig_mode_key
      UNIQUE (profile_name, params_signature, evaluation_mode);
  END IF;
END $$;

CREATE INDEX IF NOT EXISTS warbird_strategy_tuning_trials_profile_mode_score_idx
  ON warbird_strategy_tuning_trials (profile_name, evaluation_mode, objective_score DESC);

INSERT INTO local_schema_migrations (filename) VALUES ('009_strategy_tuning_evaluation_mode.sql')
  ON CONFLICT (filename) DO NOTHING;
