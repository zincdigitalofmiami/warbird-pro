# AG Local Training Schema Contract

**Date:** 2026-04-10
**Status:** Active schema authority for local AG lineage and training base

Canonical statement: **three canonical local AG tables and one canonical training view.**

## Exact SQL Contract

```sql
CREATE TABLE ag_fib_snapshots (
  ts TIMESTAMPTZ PRIMARY KEY,
  anchor_high FLOAT8,
  anchor_low FLOAT8,
  anchor_high_bar_ts TIMESTAMPTZ,
  anchor_low_bar_ts TIMESTAMPTZ,
  fib_range FLOAT8,
  fib_bull BOOLEAN,
  zz_deviation FLOAT8,
  zz_depth INT,
  anchor_swing_bars INT,
  anchor_swing_velocity FLOAT8,
  time_since_anchor INT,
  atr14 FLOAT8,
  atr_pct FLOAT8
);

CREATE TABLE ag_fib_interactions (
  id BIGSERIAL PRIMARY KEY,
  ts TIMESTAMPTZ,
  snapshot_ts TIMESTAMPTZ REFERENCES ag_fib_snapshots(ts),
  direction INT,
  fib_level_touched INT,
  fib_level_price FLOAT8,
  touch_distance_pts FLOAT8,
  touch_distance_norm FLOAT8,
  interaction_state INT,
  archetype INT,
  entry_price FLOAT8,
  sl_price FLOAT8,
  tp1_price FLOAT8,
  tp2_price FLOAT8,
  tp3_price FLOAT8,
  tp4_price FLOAT8,
  tp5_price FLOAT8,
  sl_dist_pts FLOAT8,
  sl_dist_atr FLOAT8,
  tp1_dist_pts FLOAT8,
  rr_to_tp1 FLOAT8,
  open FLOAT8,
  high FLOAT8,
  low FLOAT8,
  close FLOAT8,
  volume FLOAT8,
  body_pct FLOAT8,
  upper_wick_pct FLOAT8,
  lower_wick_pct FLOAT8,
  rvol FLOAT8,
  rsi14 FLOAT8,
  ema9 FLOAT8,
  ema21 FLOAT8,
  ema50 FLOAT8,
  ema200 FLOAT8,
  ema_stacked_bull BOOLEAN,
  ema_stacked_bear BOOLEAN,
  ema9_dist_pct FLOAT8,
  macd_hist FLOAT8,
  adx FLOAT8,
  energy FLOAT8,
  confluence_quality FLOAT8,
  ml_exec_tf_code INT,
  ml_exec_direction_code INT,
  ml_exec_state_code INT,
  ml_exec_pattern_code INT,
  ml_exec_pocket_code INT,
  ml_exec_impulse_break_atr FLOAT8,
  ml_exec_reclaim_dist_atr FLOAT8,
  ml_exec_orderflow_bias INT,
  ml_exec_delta_norm FLOAT8,
  ml_exec_absorption BOOLEAN,
  ml_exec_zero_print BOOLEAN,
  ml_exec_same_dir_imbalance_ct INT,
  ml_exec_opp_dir_imbalance_ct INT,
  ml_exec_target_leg_code INT
);

CREATE TABLE ag_fib_outcomes (
  interaction_id BIGINT PRIMARY KEY REFERENCES ag_fib_interactions(id),
  highest_tp_hit INT,
  hit_tp1 BOOLEAN,
  hit_tp2 BOOLEAN,
  hit_tp3 BOOLEAN,
  hit_tp4 BOOLEAN,
  hit_tp5 BOOLEAN,
  hit_sl BOOLEAN,
  tp1_before_sl BOOLEAN,
  bars_to_tp1 INT,
  bars_to_sl INT,
  bars_to_resolution INT,
  mae_pts FLOAT8,
  mfe_pts FLOAT8,
  outcome_label TEXT,
  observation_window INT
);

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
```

## S/R Feature Architecture

Canonical shape: one feature family per S/R level type.
PROHIBITED: consolidated string columns, JSON/list-in-cell columns,
raw absolute price levels, single nearest-level column without type.
Reason: AG requires fixed, type-specific, comparable numeric features.
SHAP attribution must be actionable per exact level type.

Per-type feature families (one set per level type listed below):
  dist_to_{type}_pct    FLOAT8   (level - close) / close * 100, signed
  at_{type}             BOOLEAN  abs(dist) < calibrated per-type threshold
  above_{type}          BOOLEAN  close > level
  flip_{type}           BOOLEAN  prior bar closed opposite side, current confirms
  reject_{type}         BOOLEAN  wick touched level, close rejected
  vol_at_{type}         FLOAT8   bar volume when at_{type} = true, else 0
  {type}_is_missing     BOOLEAN  explicit missingness flag, required for all types

Level types in scope for Phase 4 first run:
  prior_day_high / prior_day_low
  overnight_high / overnight_low
  weekly_high / weekly_low
  4h_swing_high / 4h_swing_low     (ZigZag derived)
  rth_open
  prior_session_close
  rolling_poc                       (if available; missingness flag mandatory)

Expected S/R feature budget: 25-35 columns.
All values normalized by ATR or percent. Raw price levels never enter the model.


## Exhaustion Feature Contract

Exhaustion is exported as ml_* hidden features. NOT a hard entry gate.
Do not suppress candidate rows based on exhaustion confluence.
Feature enrichment only. AG discovers the weights.

Required hidden export columns (add to ag_fib_interactions or as join surface):
  ml_exh_geom_confluence      BOOLEAN  price at active leg 1.272 or 1.618 extension
  ml_exh_z_score              FLOAT8   Z-score at trigger bar (signed)
  ml_exh_z_extreme            BOOLEAN  abs(z) >= threshold (configurable, start 2.0)
  ml_exh_delta_div            BOOLEAN  delta divergence confirmed at extension bar
  ml_exh_absorption           BOOLEAN  POC near wick extreme with rejection close
  ml_exh_zero_print           BOOLEAN  extreme-row participation near zero (regime-normalized)
  ml_exh_confidence_tier      INT      reversal tier: 1=geometry+stats+footprint, 0=not triggered
  ml_exh_footprint_available  BOOLEAN  footprint data present for this bar
  ml_exh_session_valid        BOOLEAN  bar outside CME maintenance (17:00-18:00 ET)
  ml_exh_bars_since_trigger   INT      bars since confluence met, null if not triggered
  ml_cont_confidence_tier     INT      continuation tier: 1=full footprint, 2=reduced fallback, 0=not triggered

Confidence tiers:
  Reversal exhaustion (`ml_exh_confidence_tier`):
    Tier 1 only (geometry + Z-score + footprint). No geometry-only Tier 2 fallback.
  Continuation evidence (`ml_cont_confidence_tier`):
    Tier 1 (full): same-direction footprint confirmation.
    Tier 2 (reduced): fallback when footprint is unavailable.


## Behavioral Feature Contract

Derived from live performance loss-driver analysis.
Encode behavioral context at entry. AG uses these to learn which behavioral
contexts produce better outcomes. Do not hardcode direction asymmetry — AG
discovers it from these features.

Required columns (add to ag_fib_interactions):
  ml_session_tier             INT      1=RTH full, 2=pre-market, 3=overnight
  ml_rth_open_bar             BOOLEAN  entry within bars 1-2 of RTH (9:30-9:44 ET)
  ml_consec_losses_prior      INT      consecutive losses before this entry in session
  ml_prior_session_pnl        FLOAT8   session P&L at moment of entry (signed)
  ml_momentum_3bar            FLOAT8   price move in trade direction over 3 bars post-entry
  ml_trade_working_3bar       BOOLEAN  price moved >= 2 pts in direction within 3 bars
  ml_size_in_drawdown         BOOLEAN  position > 1 contract during negative session P&L
  ml_direction_bias           INT      1=aligned with session bias, -1=counter, 0=neutral
  ml_bars_held                INT      total bars from entry to exit
  ml_adverse_excursion_pts    FLOAT8   max adverse move in pts before exit (MAE proxy)
  ml_favorable_excursion_pts  FLOAT8   max favorable move in pts before exit (MFE proxy)

ml_adverse_excursion_pts is a label-quality signal, not just a feature.
Trades with excessive adverse excursion have distinct outcome distributions
from trades that stay within structural stop range.


## Micro Execution Feature Contract

The canonical trade object remains the MES 15m fib setup. Micro execution is a
child layer attached to that parent row. Do not create a fourth canonical AG
table for `1m` / `3m` / `5m` triggers.

Data-source rules:

- local `mes_1m` is the canonical backfill tape for child execution context
- `3m` and `5m` are derived on read from `mes_1m`; they are not separate stored tables
- TradingView footprint/order-flow capture may enrich the child layer where available
- do not claim full-history footprint truth until a real lower-timeframe capture
  path exists

Required child execution states:

- `WATCH` — parent 15m setup is actionable soon; operator should monitor the lower timeframe
- `ARMED` — price has reached the execution pocket and is waiting for lower-timeframe confirmation
- `GREEN_LIGHT` — lower-timeframe trigger confirmed; operator can engage
- `INVALIDATED` — the child trigger is no longer valid against the parent map
- `EXPIRED` — the child setup drifted too far from pocket without fresh impulse and is no longer actionable

First admitted child execution patterns:

- `PULLBACK_HOLD`
- `FAILED_RECLAIM`
- `CLIMAX_REVERSAL`
- `FAILED_EXPANSION`

Required columns (add to `ag_fib_interactions` or a 1:1 local join surface keyed by `id`):
  ml_exec_tf_code               INT      1=1m, 3=3m, 5=5m, 0=none
  ml_exec_direction_code        INT      -1=short child trigger, 0=none, 1=long child trigger
  ml_exec_state_code            INT      0=none, 1=WATCH, 2=ARMED, 3=GREEN_LIGHT, 4=INVALIDATED, 5=EXPIRED
  ml_exec_pattern_code          INT      0=none, 1=PULLBACK_HOLD, 2=FAILED_RECLAIM, 3=CLIMAX_REVERSAL, 4=FAILED_EXPANSION
  ml_exec_pocket_code           INT      dominant child trigger pocket (236/382/500/618/786)
  ml_exec_impulse_break_atr     FLOAT8   normalized size of the impulse break that created the child setup
  ml_exec_reclaim_dist_atr      FLOAT8   normalized distance from child trigger close to the reclaim / half-back line
  ml_exec_orderflow_bias        INT      -1=counter-to-parent, 0=neutral, 1=parent-aligned at trigger
  ml_exec_delta_norm            FLOAT8   normalized signed delta at the trigger
  ml_exec_absorption            BOOLEAN  absorption confirmed near the child trigger level
  ml_exec_zero_print            BOOLEAN  zero-print / finished-auction condition confirmed
  ml_exec_same_dir_imbalance_ct INT      imbalance rows aligned with parent 15m direction
  ml_exec_opp_dir_imbalance_ct  INT      imbalance rows opposing parent 15m direction
  ml_exec_target_leg_code       INT      1=to_1_0, 2=to_t1, 3=to_1_0_then_t1

These fields describe how the parent MES 15m setup becomes actionable. They do
not alter candidate identity, do not create a second trade object, and do not
permit cloud mirroring of raw lower-timeframe execution history.

`ml_exec_direction_code` is the admitted child execution direction. It may
match the parent `direction`, or oppose it when the lower-timeframe tape emits a
legal failure / reversal trigger while the parent 15m map remains unchanged.

These child execution fields are AG-facing primitives. They are not a hand-built
execution policy. AutoGluon and SHAP determine which child timeframe, state,
direction, and pressure combinations survive.

Current warehouse heuristic for `EXPIRED`:

- only admitted from provisional `WATCH` or `ARMED`
- `ml_exec_reclaim_dist_atr >= 1.5`
- `ml_exec_impulse_break_atr <= 0.15`

This is a deterministic stale-state guard for warehouse research, not a claim
that lower-timeframe footprint truth has been historically reconstructed.


## TV v6 Capabilities, Backtesting, and Automation Architecture

Pine v6 capabilities adopted in this contract:
  Enums for type-safe mode selection and state modeling
  Strict two-state booleans for deterministic confluence logic
  Dynamic request strings and dynamic loop boundaries
  request.footprint() for order-flow features (delta, POC, imbalance, rows)
  polyline.new() for low-overhead fib and projection rendering

Backtesting protocol updates (required for indicator/AG alignment):
  Deep Backtesting for multi-regime coverage
  Bar Magnifier for intrabar sequencing on stop/target conflicts
  Walk-forward IS/OOS only with one-session embargo minimum
  Commission/slippage floors must be applied in strategy evaluation
  Threshold sweeps must track frequency and precision jointly

Automated capture architecture (replaces recurring manual TV CSV exports):
  Pine indicator fires alert() at barstate.isconfirmed with JSON payload
  TV sends POST to Supabase Edge Function (indicator-capture)
  Edge Function upserts to indicator_snapshots_15m cloud table
  Nightly Python job syncs cloud indicator_snapshots_15m to local warbird
  AG training reads from local warbird weekly (manual trigger retained)
  TV alerts are server-side: capture runs without TV open or user action

Historical seed remains one-time only:
  Existing CSV is ingested once into local indicator_snapshots_15m
  before Phase 4 pipeline runs. No recurring manual exports after seed.
