-- Migration 008: Strategy tuning trial storage for programmatic TradingView optimization
-- Purpose: Persist suggested parameter sets and recorded TradingView backtest results
-- in the canonical local warbird warehouse instead of screenshot-only/manual memory.

CREATE TABLE IF NOT EXISTS warbird_strategy_tuning_batches (
  batch_id            TEXT PRIMARY KEY,
  created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  profile_name        TEXT NOT NULL,
  generation_seed     INT,
  requested_count     INT NOT NULL,
  search_space_path   TEXT NOT NULL,
  search_space_hash   TEXT NOT NULL,
  objective           JSONB NOT NULL,
  locked_parameters   JSONB NOT NULL,
  runtime_context     JSONB NOT NULL,
  notes               TEXT
);

CREATE TABLE IF NOT EXISTS warbird_strategy_tuning_trials (
  trial_id                TEXT PRIMARY KEY,
  batch_id                TEXT REFERENCES warbird_strategy_tuning_batches(batch_id) ON DELETE SET NULL,
  parent_trial_id         TEXT REFERENCES warbird_strategy_tuning_trials(trial_id) ON DELETE SET NULL,
  profile_name            TEXT NOT NULL,
  origin                  TEXT NOT NULL,
  status                  TEXT NOT NULL CHECK (status IN ('SUGGESTED', 'RECORDED', 'REJECTED')),
  params_signature        TEXT NOT NULL,
  search_parameters       JSONB NOT NULL,
  locked_parameters       JSONB NOT NULL,
  runtime_context         JSONB NOT NULL,
  metrics                 JSONB,
  objective               JSONB,
  source_csv              TEXT,
  notes                   TEXT,
  objective_score         FLOAT8,
  net_pnl                 FLOAT8,
  profit_factor           FLOAT8,
  max_drawdown            FLOAT8,
  max_drawdown_pct        FLOAT8,
  survival_30_tick_pct    FLOAT8,
  total_trades            INT,
  percent_profitable      FLOAT8,
  long_net_pnl            FLOAT8,
  long_profit_factor      FLOAT8,
  short_net_pnl           FLOAT8,
  short_profit_factor     FLOAT8,
  recorded_at             TIMESTAMPTZ,
  created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (profile_name, params_signature)
);

CREATE INDEX IF NOT EXISTS warbird_strategy_tuning_trials_profile_status_idx
  ON warbird_strategy_tuning_trials (profile_name, status);

CREATE INDEX IF NOT EXISTS warbird_strategy_tuning_trials_profile_score_idx
  ON warbird_strategy_tuning_trials (profile_name, objective_score DESC);

CREATE INDEX IF NOT EXISTS warbird_strategy_tuning_trials_recorded_at_idx
  ON warbird_strategy_tuning_trials (recorded_at DESC);

INSERT INTO local_schema_migrations (filename) VALUES ('008_strategy_tuning_trials.sql')
  ON CONFLICT (filename) DO NOTHING;
