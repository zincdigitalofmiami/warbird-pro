-- 017_ag_run_kind_metric_scope_typo_fix.sql
--
-- Fix the AUTOGLOON → AUTOGLUON typos introduced in migration 014.
--
-- The trainer (scripts/ag/train_ag_baseline.py) writes 'AUTOGLUON' (correct
-- spelling) for both run_kind and metric_scope. The check constraints from
-- migration 014 enforced the misspelled 'AUTOGLOON'. This caused
-- replace_run_metrics to throw CheckViolation inside the trainer's finally
-- block, which rolled back the entire transaction (including the SUCCEEDED
-- upsert) and left runs stuck at RUNNING with zero metric/artifact rows.
--
-- This migration:
--   1. Migrates any existing 'AUTOGLOON_TABULAR' run_kind values and the
--      default value to 'AUTOGLUON_TABULAR'.
--   2. Drops the old typo-guarded check constraints.
--   3. Recreates the constraints using the correct 'AUTOGLUON' spelling.
--
-- Safe to apply even though ag_training_run_metrics is empty for the
-- broken run — the UPDATE block is a no-op when no typo rows exist.

BEGIN;

-- 1. Drop the old check constraints FIRST (they enforce the typo spellings
--    and would block the UPDATE statements below).
ALTER TABLE ag_training_runs
  DROP CONSTRAINT IF EXISTS ag_training_runs_run_kind_ck;

ALTER TABLE ag_training_run_metrics
  DROP CONSTRAINT IF EXISTS ag_training_run_metrics_metric_scope_ck;

-- 2a. Rewrite existing rows that used the typo spelling.
UPDATE ag_training_runs
   SET run_kind = 'AUTOGLUON_TABULAR'
 WHERE run_kind = 'AUTOGLOON_TABULAR';

UPDATE ag_training_run_metrics
   SET metric_scope = 'AUTOGLUON'
 WHERE metric_scope = 'AUTOGLOON';

-- 2b. Change the column default on run_kind to the correct spelling.
ALTER TABLE ag_training_runs
  ALTER COLUMN run_kind SET DEFAULT 'AUTOGLUON_TABULAR';

-- 3. Recreate the constraints with correct spelling.
ALTER TABLE ag_training_runs
  ADD CONSTRAINT ag_training_runs_run_kind_ck
  CHECK (run_kind IN ('AUTOGLUON_TABULAR'));

ALTER TABLE ag_training_run_metrics
  ADD CONSTRAINT ag_training_run_metrics_metric_scope_ck
  CHECK (metric_scope IN ('BASELINE', 'AUTOGLUON'));

-- 4. Stamp the ledger.
INSERT INTO local_schema_migrations (filename, applied_at)
VALUES ('017_ag_run_kind_metric_scope_typo_fix.sql', NOW());

COMMIT;
