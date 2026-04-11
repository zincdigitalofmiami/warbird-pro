-- Migration 007: Canonical AG lineage tables and training view
-- Authority: docs/contracts/ag_local_training_schema.md
-- Three canonical local AG tables and one canonical training view.
-- Exact SQL contract reproduced below. Do not modify column names or types
-- without updating docs/contracts/ag_local_training_schema.md first.

-- ── ag_fib_snapshots ─────────────────────────────────────────────────────────
-- One row per fib anchor event (ZigZag pivot confirmation at bar close).
-- ts is the MES 15m bar-close timestamp of the anchor event in UTC.
CREATE TABLE IF NOT EXISTS ag_fib_snapshots (
  ts                    TIMESTAMPTZ PRIMARY KEY,
  anchor_high           FLOAT8,
  anchor_low            FLOAT8,
  anchor_high_bar_ts    TIMESTAMPTZ,
  anchor_low_bar_ts     TIMESTAMPTZ,
  fib_range             FLOAT8,
  fib_bull              BOOLEAN,
  zz_deviation          FLOAT8,
  zz_depth              INT,
  anchor_swing_bars     INT,
  anchor_swing_velocity FLOAT8,
  time_since_anchor     INT,
  atr14                 FLOAT8,
  atr_pct               FLOAT8
);

-- ── ag_fib_interactions ──────────────────────────────────────────────────────
-- One row per candidate fib-level interaction (each bar that touches a fib level
-- from an active snapshot). This is the primary ML feature surface.
CREATE TABLE IF NOT EXISTS ag_fib_interactions (
  id                              BIGSERIAL PRIMARY KEY,
  ts                              TIMESTAMPTZ,
  snapshot_ts                     TIMESTAMPTZ REFERENCES ag_fib_snapshots(ts),
  direction                       INT,
  fib_level_touched               INT,
  fib_level_price                 FLOAT8,
  touch_distance_pts              FLOAT8,
  touch_distance_norm             FLOAT8,
  interaction_state               INT,
  archetype                       INT,
  entry_price                     FLOAT8,
  sl_price                        FLOAT8,
  tp1_price                       FLOAT8,
  tp2_price                       FLOAT8,
  tp3_price                       FLOAT8,
  tp4_price                       FLOAT8,
  tp5_price                       FLOAT8,
  sl_dist_pts                     FLOAT8,
  sl_dist_atr                     FLOAT8,
  tp1_dist_pts                    FLOAT8,
  rr_to_tp1                       FLOAT8,
  open                            FLOAT8,
  high                            FLOAT8,
  low                             FLOAT8,
  close                           FLOAT8,
  volume                          FLOAT8,
  body_pct                        FLOAT8,
  upper_wick_pct                  FLOAT8,
  lower_wick_pct                  FLOAT8,
  rvol                            FLOAT8,
  rsi14                           FLOAT8,
  ema9                            FLOAT8,
  ema21                           FLOAT8,
  ema50                           FLOAT8,
  ema200                          FLOAT8,
  ema_stacked_bull                BOOLEAN,
  ema_stacked_bear                BOOLEAN,
  ema9_dist_pct                   FLOAT8,
  macd_hist                       FLOAT8,
  adx                             FLOAT8,
  energy                          FLOAT8,
  confluence_quality              FLOAT8
);
CREATE INDEX IF NOT EXISTS ag_fib_interactions_ts_idx           ON ag_fib_interactions (ts);
CREATE INDEX IF NOT EXISTS ag_fib_interactions_snapshot_ts_idx  ON ag_fib_interactions (snapshot_ts);
CREATE INDEX IF NOT EXISTS ag_fib_interactions_direction_idx    ON ag_fib_interactions (direction);
CREATE INDEX IF NOT EXISTS ag_fib_interactions_fib_level_idx    ON ag_fib_interactions (fib_level_touched);

-- ── ag_fib_outcomes ──────────────────────────────────────────────────────────
-- One row per resolved interaction. Populated after observation window closes.
CREATE TABLE IF NOT EXISTS ag_fib_outcomes (
  interaction_id      BIGINT PRIMARY KEY REFERENCES ag_fib_interactions(id),
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
CREATE INDEX IF NOT EXISTS ag_fib_outcomes_outcome_label_idx ON ag_fib_outcomes (outcome_label);

-- ── ag_training (view) ───────────────────────────────────────────────────────
-- Canonical flat training surface. Joins interactions + snapshots + outcomes.
-- Excludes CENSORED rows (observation window not closed at query time).
-- This is the ONLY surface consumed by AG training scripts.
CREATE OR REPLACE VIEW ag_training AS
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

INSERT INTO local_schema_migrations (filename) VALUES ('007_ag_schema.sql')
  ON CONFLICT (filename) DO NOTHING;
