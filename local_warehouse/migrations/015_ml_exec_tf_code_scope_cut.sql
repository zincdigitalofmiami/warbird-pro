-- Migration 015: align ml_exec_tf_code with the current 5m / 15m scope cut
-- Old contract admitted 1m / 3m / 5m child trigger codes: (0, 1, 3, 5)
-- Current contract admits only: 0=none, 5=5m, 15=15m

ALTER TABLE ag_fib_interactions
  DROP CONSTRAINT IF EXISTS ag_fib_interactions_ml_exec_tf_code_ck;

ALTER TABLE ag_fib_interactions
  ADD CONSTRAINT ag_fib_interactions_ml_exec_tf_code_ck
  CHECK (ml_exec_tf_code IN (0, 5, 15));

INSERT INTO local_schema_migrations (filename) VALUES ('015_ml_exec_tf_code_scope_cut.sql')
  ON CONFLICT (filename) DO NOTHING;
