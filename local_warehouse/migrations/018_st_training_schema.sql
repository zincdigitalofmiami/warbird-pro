-- 018_st_training_schema.sql
--
-- v8 SuperTrend + TQI training schema (st_ namespace)
-- Local warehouse only (warbird PG17)

BEGIN;

CREATE TABLE st_run_config (
    run_id      TEXT PRIMARY KEY,
    oos_start   TIMESTAMPTZ NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    notes       TEXT
);

CREATE TABLE st_flip_configs (
    flip_cfg_id  SERIAL PRIMARY KEY,
    atr_period   INTEGER      NOT NULL,
    atr_mult     NUMERIC(4,2) NOT NULL,
    atr_method   TEXT         NOT NULL,
    source_id    TEXT         NOT NULL CHECK (source_id IN ('hl2', 'close', 'ohlc4')),
    sl_atr_mult  NUMERIC(4,2) NOT NULL,
    UNIQUE (atr_period, atr_mult, atr_method, source_id, sl_atr_mult)
);

CREATE TABLE st_tp_configs (
    tp_cfg_id     SERIAL PRIMARY KEY,
    tp_mode       TEXT         NOT NULL,
    tqi_influence NUMERIC(3,2) NOT NULL,
    vol_influence NUMERIC(3,2) NOT NULL,
    min_tp_scale  NUMERIC(3,2) NOT NULL,
    max_tp_scale  NUMERIC(3,2) NOT NULL,
    tp1_floor_r   NUMERIC(4,2) NOT NULL,
    tp3_ceil_r    NUMERIC(4,2) NOT NULL,
    UNIQUE (tp_mode, tqi_influence, vol_influence, min_tp_scale,
            max_tp_scale, tp1_floor_r, tp3_ceil_r)
);

CREATE TABLE st_signals (
    signal_id       SERIAL PRIMARY KEY,
    run_id          TEXT         NOT NULL REFERENCES st_run_config(run_id),
    ts              TIMESTAMPTZ  NOT NULL,
    flip_cfg_id     INTEGER      NOT NULL REFERENCES st_flip_configs(flip_cfg_id),
    direction       SMALLINT     NOT NULL,
    tqi             NUMERIC(6,4),
    er              NUMERIC(6,4),
    vol_ratio       NUMERIC(6,4),
    tqi_struct      NUMERIC(6,4),
    tqi_mom         NUMERIC(6,4),
    atr14           NUMERIC(10,4),
    in_ote_zone     BOOLEAN,
    structure_event SMALLINT,
    htf_bias        SMALLINT,
    hour_bucket     SMALLINT,
    session_type    TEXT,
    UNIQUE (ts, flip_cfg_id, run_id)
);

CREATE TABLE st_outcomes (
    outcome_id              SERIAL PRIMARY KEY,
    signal_id               INTEGER      NOT NULL REFERENCES st_signals(signal_id),
    tp_cfg_id               INTEGER      NOT NULL REFERENCES st_tp_configs(tp_cfg_id),
    outcome_label           TEXT         NOT NULL,
    realized_r              NUMERIC(8,4),
    bars_to_outcome         INTEGER,
    mae                     NUMERIC(10,4),
    mfe                     NUMERIC(10,4),
    pts_to_survive_to_tp1   NUMERIC(8,4),
    pts_to_survive_to_tp2   NUMERIC(8,4),
    min_stop_atr_to_tp1     NUMERIC(8,4),
    UNIQUE (signal_id, tp_cfg_id)
);

CREATE TABLE st_prescreen_ledger (
    prescreen_id   SERIAL PRIMARY KEY,
    run_id         TEXT         NOT NULL REFERENCES st_run_config(run_id),
    flip_cfg_id    INTEGER      NOT NULL REFERENCES st_flip_configs(flip_cfg_id),
    window_start   TIMESTAMPTZ  NOT NULL,
    window_end     TIMESTAMPTZ  NOT NULL,
    n_signals      INTEGER      NOT NULL,
    win_rate       NUMERIC(6,4),
    profit_factor  NUMERIC(8,4),
    avg_r          NUMERIC(8,4),
    max_drawdown_r NUMERIC(8,4),
    pass           BOOLEAN      NOT NULL,
    fail_reason    TEXT,
    run_ts         TIMESTAMPTZ  NOT NULL DEFAULT now(),
    UNIQUE (flip_cfg_id, run_id)
);

INSERT INTO local_schema_migrations (filename)
VALUES ('018_st_training_schema.sql')
ON CONFLICT (filename) DO NOTHING;

COMMIT;
