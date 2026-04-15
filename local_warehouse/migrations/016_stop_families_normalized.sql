-- Migration 016: Normalized stop-family surface
-- Authority: docs/contracts/ag_local_training_schema.md (updated)
--            docs/contracts/stop_families.md
--
-- Contract change: four canonical local AG tables + one canonical training view.
--
-- What this migration does:
--   1. Removes stop-derived columns from ag_fib_interactions (making it stop-agnostic)
--   2. Creates ag_fib_stop_variants — one row per (interaction_id, stop_family_id)
--   3. Drops and recreates ag_fib_outcomes keyed on stop_variant_id
--   4. Rebuilds ag_training view with four-way join
--
-- Result: one training row per (interaction x stop family). 6x training population.
-- stop_family_id is a real categorical AG feature. stop_variant_id goes in LEAKAGE_COLS.
-- best_stop_family must never appear in ag_training.
--
-- Safe to run: build_ag_pipeline.py truncates and rebuilds all AG tables on every run.
-- The pipeline must be updated to match before the next rebuild.

-- ── Step 1: Drop ag_training view (depends on ag_fib_outcomes) ───────────────
DROP VIEW IF EXISTS ag_training;

-- ── Step 2: Drop ag_fib_outcomes (will be recreated with new PK) ─────────────
DROP TABLE IF EXISTS ag_fib_outcomes;

-- ── Step 3: Remove stop-derived columns from ag_fib_interactions ─────────────
-- These columns are stop-family-specific and belong in ag_fib_stop_variants.
-- entry_price and tp*_price stay — they are stop-agnostic.
-- tp1_dist_pts stays — it depends only on entry_price and tp1_price.
ALTER TABLE ag_fib_interactions
  DROP COLUMN IF EXISTS sl_price,
  DROP COLUMN IF EXISTS sl_dist_pts,
  DROP COLUMN IF EXISTS sl_dist_atr,
  DROP COLUMN IF EXISTS rr_to_tp1;

-- ── Step 4: Create ag_fib_stop_variants ──────────────────────────────────────
-- Stop-specific candidate surface. One row per (interaction_id, stop_family_id).
-- stop_level_price and stop_distance_ticks use exact names from stop_families.md.
-- sl_dist_pts, sl_dist_atr, rr_to_tp1 are computed convenience fields admitted as AG features.
-- MES tick size = 0.25 points. stop_distance_ticks = round(sl_dist_pts / 0.25).
CREATE TABLE IF NOT EXISTS ag_fib_stop_variants (
  id                  BIGSERIAL PRIMARY KEY,
  interaction_id      BIGINT NOT NULL REFERENCES ag_fib_interactions(id),
  stop_family_id      TEXT NOT NULL,
  stop_level_price    FLOAT8 NOT NULL,
  stop_distance_ticks INT NOT NULL,
  sl_dist_pts         FLOAT8 NOT NULL,
  sl_dist_atr         FLOAT8 NOT NULL,
  rr_to_tp1           FLOAT8 NOT NULL,
  UNIQUE (interaction_id, stop_family_id),
  CHECK (stop_family_id IN (
    'FIB_NEG_0236',
    'FIB_NEG_0382',
    'ATR_1_0',
    'ATR_1_5',
    'ATR_STRUCTURE_1_25',
    'FIB_0236_ATR_COMPRESS_0_50'
  ))
);
CREATE INDEX IF NOT EXISTS ag_fib_stop_variants_interaction_idx
  ON ag_fib_stop_variants (interaction_id);
CREATE INDEX IF NOT EXISTS ag_fib_stop_variants_family_idx
  ON ag_fib_stop_variants (stop_family_id);

-- ── Step 5: Recreate ag_fib_outcomes keyed on stop_variant_id ────────────────
-- One row per stop variant. stop_variant_id is the PK — outcomes hang off the
-- variant identity, not duplicated across a composite key.
CREATE TABLE ag_fib_outcomes (
  stop_variant_id     BIGINT PRIMARY KEY REFERENCES ag_fib_stop_variants(id),
  highest_tp_hit      INT,
  hit_tp1             BOOLEAN,
  hit_tp2             BOOLEAN,
  hit_tp3             BOOLEAN,
  hit_tp4             BOOLEAN,
  hit_tp5             BOOLEAN,
  hit_sl              BOOLEAN,
  tp1_before_sl       BOOLEAN,
  bars_to_tp1         INT,
  bars_to_sl          INT,
  bars_to_resolution  INT,
  mae_pts             FLOAT8,
  mfe_pts             FLOAT8,
  outcome_label       TEXT,
  observation_window  INT
);
CREATE INDEX IF NOT EXISTS ag_fib_outcomes_outcome_label_idx
  ON ag_fib_outcomes (outcome_label);

-- ── Step 6: Rebuild ag_training view ─────────────────────────────────────────
-- Four-way join: interactions -> snapshots, interactions -> stop_variants -> outcomes.
-- stop_family_id, stop_level_price, stop_distance_ticks, sl_dist_pts, sl_dist_atr,
-- rr_to_tp1 are admitted AG features.
-- stop_variant_id is row identity — add to LEAKAGE_COLS in train_ag_baseline.py.
-- best_stop_family must never appear here.
CREATE VIEW ag_training AS
SELECT
  i.*,
  s.anchor_high, s.anchor_low, s.fib_range, s.fib_bull,
  s.anchor_swing_bars, s.anchor_swing_velocity, s.atr14,
  v.id AS stop_variant_id, v.stop_family_id, v.stop_level_price,
  v.stop_distance_ticks, v.sl_dist_pts, v.sl_dist_atr, v.rr_to_tp1,
  o.highest_tp_hit, o.hit_tp1, o.hit_tp2, o.hit_tp3, o.hit_tp4, o.hit_tp5,
  o.tp1_before_sl, o.mae_pts, o.mfe_pts, o.outcome_label,
  o.bars_to_tp1, o.bars_to_sl
FROM ag_fib_interactions i
JOIN ag_fib_snapshots s ON i.snapshot_ts = s.ts
JOIN ag_fib_stop_variants v ON v.interaction_id = i.id
JOIN ag_fib_outcomes o ON o.stop_variant_id = v.id
WHERE o.outcome_label != 'CENSORED';

-- ── Step 7: Register migration ────────────────────────────────────────────────
INSERT INTO local_schema_migrations (filename)
  VALUES ('016_stop_families_normalized.sql')
  ON CONFLICT (filename) DO NOTHING;
