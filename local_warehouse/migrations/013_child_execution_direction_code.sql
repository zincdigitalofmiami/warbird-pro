-- Migration 013: admit explicit child execution trigger direction
-- Distinguishes parent 15m map direction from child lower-timeframe execution direction.
--   -1 = short trigger
--    0 = no child trigger direction
--    1 = long trigger

ALTER TABLE ag_fib_interactions
  ADD COLUMN IF NOT EXISTS ml_exec_direction_code INT NOT NULL DEFAULT 0;

ALTER TABLE ag_fib_interactions
  DROP CONSTRAINT IF EXISTS ag_fib_interactions_ml_exec_direction_code_ck;

ALTER TABLE ag_fib_interactions
  ADD CONSTRAINT ag_fib_interactions_ml_exec_direction_code_ck
  CHECK (ml_exec_direction_code IN (-1, 0, 1));

CREATE INDEX IF NOT EXISTS ag_fib_interactions_ml_exec_direction_code_idx
  ON ag_fib_interactions (ml_exec_direction_code);

DROP VIEW IF EXISTS ag_training;

CREATE VIEW ag_training AS
SELECT
  i.*,
  s.anchor_high, s.anchor_low, s.fib_range, s.fib_bull,
  s.anchor_swing_bars, s.anchor_swing_velocity, s.atr14,
  o.highest_tp_hit, o.hit_tp1, o.hit_tp2, o.hit_tp3, o.hit_tp4, o.hit_tp5,
  o.tp1_before_sl, o.mae_pts, o.mfe_pts, o.outcome_label,
  o.bars_to_tp1, o.bars_to_sl
FROM ag_fib_interactions i
JOIN ag_fib_snapshots s ON i.snapshot_ts = s.ts
JOIN ag_fib_outcomes o ON o.interaction_id = i.id
WHERE o.outcome_label != 'CENSORED';

INSERT INTO local_schema_migrations (filename) VALUES ('013_child_execution_direction_code.sql')
  ON CONFLICT (filename) DO NOTHING;
