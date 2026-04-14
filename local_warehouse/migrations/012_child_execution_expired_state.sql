-- Migration 012: admit EXPIRED child execution state
-- Extends ml_exec_state_code taxonomy:
--   0=none, 1=WATCH, 2=ARMED, 3=GREEN_LIGHT, 4=INVALIDATED, 5=EXPIRED

ALTER TABLE ag_fib_interactions
  DROP CONSTRAINT IF EXISTS ag_fib_interactions_ml_exec_state_code_ck;

ALTER TABLE ag_fib_interactions
  ADD CONSTRAINT ag_fib_interactions_ml_exec_state_code_ck
  CHECK (ml_exec_state_code IN (0, 1, 2, 3, 4, 5));

INSERT INTO local_schema_migrations (filename) VALUES ('012_child_execution_expired_state.sql')
  ON CONFLICT (filename) DO NOTHING;
