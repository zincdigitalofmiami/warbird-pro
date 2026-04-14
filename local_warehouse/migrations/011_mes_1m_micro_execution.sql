-- Migration 011: subordinate mes_1m surface + child execution fields
-- mes_1m is a local-only microstructure input for the parent MES 15m setup.
-- It does not create a new canonical trade object and does not authorize
-- canonical 3m / 5m stored tables.

CREATE TABLE IF NOT EXISTS mes_1m (
  ts     TIMESTAMPTZ PRIMARY KEY,
  open   FLOAT8      NOT NULL,
  high   FLOAT8      NOT NULL,
  low    FLOAT8      NOT NULL,
  close  FLOAT8      NOT NULL,
  volume BIGINT
);
CREATE INDEX IF NOT EXISTS mes_1m_ts_idx ON mes_1m (ts);

ALTER TABLE ag_fib_interactions
  ADD COLUMN IF NOT EXISTS ml_exec_tf_code INT NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS ml_exec_state_code INT NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS ml_exec_pattern_code INT NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS ml_exec_pocket_code INT NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS ml_exec_impulse_break_atr FLOAT8,
  ADD COLUMN IF NOT EXISTS ml_exec_reclaim_dist_atr FLOAT8,
  ADD COLUMN IF NOT EXISTS ml_exec_orderflow_bias INT NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS ml_exec_delta_norm FLOAT8,
  ADD COLUMN IF NOT EXISTS ml_exec_absorption BOOLEAN NOT NULL DEFAULT FALSE,
  ADD COLUMN IF NOT EXISTS ml_exec_zero_print BOOLEAN NOT NULL DEFAULT FALSE,
  ADD COLUMN IF NOT EXISTS ml_exec_same_dir_imbalance_ct INT NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS ml_exec_opp_dir_imbalance_ct INT NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS ml_exec_target_leg_code INT NOT NULL DEFAULT 0;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM pg_constraint
    WHERE conname = 'ag_fib_interactions_ml_exec_tf_code_ck'
  ) THEN
    ALTER TABLE ag_fib_interactions
      ADD CONSTRAINT ag_fib_interactions_ml_exec_tf_code_ck
      CHECK (ml_exec_tf_code IN (0, 1, 3, 5));
  END IF;

  IF NOT EXISTS (
    SELECT 1
    FROM pg_constraint
    WHERE conname = 'ag_fib_interactions_ml_exec_state_code_ck'
  ) THEN
    ALTER TABLE ag_fib_interactions
      ADD CONSTRAINT ag_fib_interactions_ml_exec_state_code_ck
      CHECK (ml_exec_state_code IN (0, 1, 2, 3, 4));
  END IF;

  IF NOT EXISTS (
    SELECT 1
    FROM pg_constraint
    WHERE conname = 'ag_fib_interactions_ml_exec_pattern_code_ck'
  ) THEN
    ALTER TABLE ag_fib_interactions
      ADD CONSTRAINT ag_fib_interactions_ml_exec_pattern_code_ck
      CHECK (ml_exec_pattern_code IN (0, 1, 2, 3, 4));
  END IF;

  IF NOT EXISTS (
    SELECT 1
    FROM pg_constraint
    WHERE conname = 'ag_fib_interactions_ml_exec_pocket_code_ck'
  ) THEN
    ALTER TABLE ag_fib_interactions
      ADD CONSTRAINT ag_fib_interactions_ml_exec_pocket_code_ck
      CHECK (ml_exec_pocket_code IN (0, 236, 382, 500, 618, 786));
  END IF;

  IF NOT EXISTS (
    SELECT 1
    FROM pg_constraint
    WHERE conname = 'ag_fib_interactions_ml_exec_orderflow_bias_ck'
  ) THEN
    ALTER TABLE ag_fib_interactions
      ADD CONSTRAINT ag_fib_interactions_ml_exec_orderflow_bias_ck
      CHECK (ml_exec_orderflow_bias IN (-1, 0, 1));
  END IF;

  IF NOT EXISTS (
    SELECT 1
    FROM pg_constraint
    WHERE conname = 'ag_fib_interactions_ml_exec_target_leg_code_ck'
  ) THEN
    ALTER TABLE ag_fib_interactions
      ADD CONSTRAINT ag_fib_interactions_ml_exec_target_leg_code_ck
      CHECK (ml_exec_target_leg_code IN (0, 1, 2, 3));
  END IF;

  IF NOT EXISTS (
    SELECT 1
    FROM pg_constraint
    WHERE conname = 'ag_fib_interactions_ml_exec_same_dir_imbalance_ct_ck'
  ) THEN
    ALTER TABLE ag_fib_interactions
      ADD CONSTRAINT ag_fib_interactions_ml_exec_same_dir_imbalance_ct_ck
      CHECK (ml_exec_same_dir_imbalance_ct >= 0);
  END IF;

  IF NOT EXISTS (
    SELECT 1
    FROM pg_constraint
    WHERE conname = 'ag_fib_interactions_ml_exec_opp_dir_imbalance_ct_ck'
  ) THEN
    ALTER TABLE ag_fib_interactions
      ADD CONSTRAINT ag_fib_interactions_ml_exec_opp_dir_imbalance_ct_ck
      CHECK (ml_exec_opp_dir_imbalance_ct >= 0);
  END IF;
END $$;

CREATE INDEX IF NOT EXISTS ag_fib_interactions_ml_exec_state_idx
  ON ag_fib_interactions (ml_exec_state_code);
CREATE INDEX IF NOT EXISTS ag_fib_interactions_ml_exec_pattern_idx
  ON ag_fib_interactions (ml_exec_pattern_code);

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

INSERT INTO local_schema_migrations (filename) VALUES ('011_mes_1m_micro_execution.sql')
  ON CONFLICT (filename) DO NOTHING;
