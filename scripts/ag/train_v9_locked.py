#!/usr/bin/env python3
"""Warbird Pro V9 — LOCKED AG full-zoo training run.

Per-skill discipline (training-ag-best-practices, training-full-zoo,
training-ag-feature-finder):
  - 7-family canonical zoo with single-thread pins
  - presets="best_quality" — full zoo (no bagging/stacking)
  - calibrate=True — built-in isotonic calibration so predict_proba
    outputs true probabilities for the downstream EV decision rule
  - eval_metric=log_loss — proper probability scoring (roc_auc only
    ranks; log_loss penalizes miscalibrated confidence)
  - hyperparameter_tune_kwargs — per-family HPO within time budge
  - num_bag_folds=0, num_stack_levels=0 — time-series safe
    (no internal IID bagging/stacking)
  - dynamic_stacking=False (explicit, reproducible)
  - time_limit=7200s (2 hours so NN_TORCH/FASTAI fully converge)
  - chronological train/val/test split with 24-bar embargo
    (FORWARD_SCAN_BARS = 24, EMBARGO_BARS = 25; enforced by
    scripts/duckdb_local/cpcv.py)
  - predictor.persist() after fit for fast repeated prediction
  - leaderboard(extra_info=True) for hyperparameter visibility
  - Apple Silicon OpenMP guards set BEFORE any AG/lightgbm impor
  - Drop AG-flagged useless features (ml_in_zone constant=1, stale dx_code,
    ml_entry_route_code constant)

Note: this IS the production V9 trainer. It fits the entry classifier (and
optionally the auxiliary TP/SL/MFE/MAE side models under --model-suite) on the
locked DuckDB-backed Core export at
scripts/duckdb_local/workspaces/warbird_pro_core/exports/es_15m_core.csv.
The smoke-validation card at
scripts/duckdb_local/cards/core_training/2026_05_09_warbird_pro_autogluon_core.py
only records local validation evidence — it does not invoke
AutoGluon. scripts/ag/train_hard_gate.py is the legacy Postgres-backed gate
(ag_training_runs table, baseline.DEFAULT_DSN) and is not on the V9 path.
The earlier Hybrid+ 4-card tuning chain (warbird_pro_v9_exit_cpcv,
warbird_pro_v9_entry_filter_cpcv, warbird_pro_v9_ag_meta_cpcv,
warbird_pro_v9_joint_challenger) was deprecated 2026-05-09 and superseded by
this single trainer.
"""
from __future__ import annotations

import os

# Apple Silicon OpenMP guards — MUST be set BEFORE any AG/lightgbm impor
os.environ["OMP_NUM_THREADS"] = "1"
os.environ["LIGHTGBM_NUM_THREADS"] = "1"
os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"
os.environ["MKL_NUM_THREADS"] = "1"
os.environ["OPENBLAS_NUM_THREADS"] = "1"

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.duckdb_local.cpcv import embargoed_chronological_split
from scripts.ag.v9_run_provenance import build_csv_provenance

CSV_PATH = REPO_ROOT / "scripts/duckdb_local/workspaces/warbird_pro_core/exports/es_15m_core.csv"
OUTPUT_ROOT = REPO_ROOT / "models/warbird_pro_v9"

# Features matching the locked Warbird Pro V9 Core surface.
# Missing columns are fatal. The Core trainer must not silently fall back to an
# older replay/export schema because that masks stale feature contracts.
ML_FEATURES = [
    # indicator profile / Pine input knobs
    "knob_auto_tune_zz", "knob_fib_deviation_manual",
    "knob_fib_depth_manual", "knob_fib_threshold_floor_pct",
    "knob_min_fib_range_atr", "knob_fib_hysteresis_pct",
    "knob_htf_conf_tol_pct",
    "knob_use_pattern_confirm", "knob_use_liq_gate",
    "knob_liq_recency_bars", "knob_trade_stop_atr_mult",
    "knob_use_ma_gate", "knob_length_ema", "knob_length_ma",
    "knob_rsi_length", "knob_rsi_overbought", "knob_rsi_oversold",
    "knob_liq_lookback_bars", "knob_eqh_tol_pct",
    "knob_eqh_min_taps", "knob_eqh_lookback", "knob_vol_z_length",
    "knob_use_session_vwap",
    "knob_use_xa_gate", "knob_nq_symbol", "knob_zn_symbol",
    "knob_6e_symbol", "knob_vix_symbol", "knob_corr_length",
    "knob_vix_move_bars", "knob_vix_atr_length",
    "knob_vix_pressure_band", "knob_xa_min_agreement",
    "knob_use_footprint", "knob_fp_ticks_per_row", "knob_fp_va_pct",
    "knob_fp_imbalance_pct", "knob_fp_absorption_delta_pct",
    "knob_fp_flush_delta_pct", "knob_fp_event_vol_spike",
    "knob_fp_compressed_range_atr",
    # single-source trade trigger and entry context. `ml_trade_tp` (single
    # live TP) was retired 2026-05-12 — Pine now emits the full fib ladder
    # via `ml_trade_tp1` / `ml_trade_tp2` / `ml_trade_tp3`, which are
    # required label-construction inputs (see REQUIRED_INPUT_COLUMNS) but
    # NOT model features (AG already sees fib geometry via ml_fib_* +
    # ml_atr14; adding the prices would be redundant).
    "ml_entry_long_trigger", "ml_entry_short_trigger",
    "ml_trade_entry", "ml_trade_stop",
    "ml_fib_touch_level_code",
    "ml_fib_touch_500_long", "ml_fib_touch_618_long",
    "ml_fib_touch_786_long",
    "ml_fib_touch_500_short", "ml_fib_touch_618_short",
    "ml_fib_touch_786_short",
    "ml_fib_entry_dist_atr", "ml_fib_pierce_atr",
    "ml_fib_close_reclaim_atr", "ml_fib_reaction_body_ratio",
    "ml_fib_reaction_upper_wick_ratio",
    "ml_fib_reaction_lower_wick_ratio", "ml_fib_reaction_code",
    # structural / regime
    "ml_atr14", "ml_dir", "ml_fib_range",
    "ml_pivot_dist_atr", "ml_p618_dist_atr",
    "ml_bars_since_break", "ml_break_in_dir",
    # momentum
    "ml_rsi_value", "ml_rsi_stance_code", "ml_ma_bias",
    "ml_ma_slow_dist_atr", "ml_ma_fast_dist_atr",
    # ADX
    "ml_adx_value", "ml_adx_plus_di", "ml_adx_minus_di",
    # candlestick patterns (curated 4 from real backtest performance)
    "ml_pat_rising_window",
    "ml_pat_bear_engulf", "ml_pat_marubozu_black", "ml_pat_tweezer_top",
    # liquidity primitives (BSL/SSL sweep+reclaim)
    "ml_bsl_dist_atr", "ml_ssl_dist_atr",
    "ml_swept_bsl", "ml_swept_ssl",
    "ml_reclaimed_bsl", "ml_reclaimed_ssl",
    "ml_recent_liq_bull", "ml_recent_liq_bear",
    "ml_liq_bars_since_bull", "ml_liq_bars_since_bear",
    # liquidity expansions (equal H/L pools, VWAP, volume z-score)
    "ml_liq_eqh_dist_atr", "ml_liq_eql_dist_atr",
    "ml_liq_vwap_dist_atr", "ml_liq_vol_zscore",
    # ETL CVD divergence features (Python-only, no Pine budget impact)
    "ml_cvd_div_bull", "ml_cvd_div_bear",
    # cross-asset trend codes (NQ/ZN/6E — DXY removed 2026-05-11)
    "ml_xa_nq_code", "ml_xa_zn_code", "ml_xa_6e_code",
    # cross-asset advanced (VIX movement pressure, ES↔NQ correlation)
    "ml_xa_vix_pressure", "ml_xa_corr_nq",
    "ml_xa_long_agreement", "ml_xa_short_agreement",
    # cross-asset continuous (locked 2026-05-11 gate-as-feature pivot — XA agreement
    # is no longer a hard gate; these normalized continuous signals let AG learn
    # regime-relative interactions instead of absolute-level cliffs. 6E momentum
    # z-score replaces the original DXY momentum z-score).
    "ml_xa_nq_rel_strength_atr",
    "ml_xa_zn_rate_pressure",
    "ml_xa_hg_growth_proxy",
    "ml_xa_6e_momentum_zscore",
    # HTF confluence
    "ml_htf_conf_total",
    # daily/weekly S/R distances
    "ml_lvl_pdh_dist_atr", "ml_lvl_pdl_dist_atr",
    "ml_lvl_pwh_dist_atr", "ml_lvl_pwl_dist_atr",
    # footprint / order flow (real intrabar bid/ask delta, POC, VA position)
    "ml_fp_delta_pct", "ml_fp_poc_dist_atr", "ml_fp_va_position",
    "ml_delta_imbalance_pct", "ml_delta_acceleration",
    "ml_aggressor_pulse", "ml_absorption_candidate",
    "ml_flush_candidate", "ml_volume_spike_ratio", "ml_poc_shift",
]

# Trade-surface discoverables (derived at label-build time).
# TP families use fib ladder ratios relative to entry anchor.
DISCOVERABLE_SL_ATR_MULTS: tuple[float, ...] = (0.75, 1.0, 1.5, 2.0)
DISCOVERABLE_TP_RATIOS: tuple[float, ...] = (1.0, 1.236, 1.618)

# Per-combo TP price source columns (emitted by Pine 2026-05-12). One-to-one
# with DISCOVERABLE_TP_RATIOS by index: tp_family_code 1 -> ml_trade_tp1
# (fib 1.000), 2 -> ml_trade_tp2 (fib 1.236), 3 -> ml_trade_tp3 (fib 1.618).
# These are label-construction inputs only (see REQUIRED_INPUT_COLUMNS).
LABEL_INPUT_TP_COLUMNS: tuple[str, ...] = (
    "ml_trade_tp1",
    "ml_trade_tp2",
    "ml_trade_tp3",
)

# 24-bar forward-scan contract (ES 15m entry-precision priority, 2026-05-12).
# Every triple-barrier label is computed over the same 24-bar window:
#   - TP touched before SL within 24 bars     -> winner_tp_before_sl = 1
#   - SL touched before TP within 24 bars     -> winner_tp_before_sl = 0
#   - Same-bar TP+SL collision                -> winner_tp_before_sl = 0
#   - Neither barrier touched within 24 bars  -> winner_tp_before_sl = 0
#   - Fewer than 24 future bars available     -> entry is DROPPED
# Pine's `tradeMaxHoldBars` must mirror this constant so the live chart and
# the trainer answer the same trade-duration question.
FORWARD_SCAN_BARS: int = 24
MIN_FUTURE_BARS: int = 24
EMBARGO_BARS: int = 25

TRADE_DISCOVERABLE_FEATURES = [
    "sl_atr_mult",
    "tp_ratio",
    "tp_family_code",
    "target_distance_points",
    "stop_distance_points",
    "rr_ratio",
]

MODEL_FEATURES = [*ML_FEATURES, *TRADE_DISCOVERABLE_FEATURES]
LABEL_COL = "winner_tp_before_sl"
TP_LABEL_COL = "tp_hit"
STOP_LABEL_COL = "stop_hit"
MFE_LABEL_COL = "mfe_points"
MAE_LABEL_COL = "mae_points"
MODEL_SPECS = {
    "entry": {"label": LABEL_COL, "problem_type": "binary", "eval_metric": "log_loss"},
    "tp": {"label": TP_LABEL_COL, "problem_type": "binary", "eval_metric": "log_loss"},
    "stop": {"label": STOP_LABEL_COL, "problem_type": "binary", "eval_metric": "log_loss"},
    "mfe": {"label": MFE_LABEL_COL, "problem_type": "regression", "eval_metric": "root_mean_squared_error"},
    "mae": {"label": MAE_LABEL_COL, "problem_type": "regression", "eval_metric": "root_mean_squared_error"},
}

REQUIRED_INPUT_COLUMNS = [
    "ts",
    "high",
    "low",
    "close",
    "ml_entry_long_trigger",
    "ml_entry_short_trigger",
    # Label-construction inputs (not model features) — Pine ladder TPs.
    *LABEL_INPUT_TP_COLUMNS,
    *ML_FEATURES,
]


def validate_input_schema(df: pd.DataFrame) -> None:
    missing = [col for col in REQUIRED_INPUT_COLUMNS if col not in df.columns]
    if missing:
        raise RuntimeError(
            "Core training CSV is missing required columns: "
            + ", ".join(missing)
        )
    stale = [col for col in ("ml_xa_dx_code", "ml_bar_delta", "ml_net_delta_20") if col in df.columns]
    if stale:
        raise RuntimeError(
            "Core training CSV still contains stale/banned columns: "
            + ", ".join(stale)
        )


def validate_trade_features(trades: pd.DataFrame) -> None:
    missing = [col for col in MODEL_FEATURES if col not in trades.columns]
    if missing:
        raise RuntimeError(f"Trade feature set missing required columns: {missing}")
    bad_inf = [
        col for col in MODEL_FEATURES
        if np.isinf(pd.to_numeric(trades[col], errors="coerce")).any()
    ]
    if bad_inf:
        raise RuntimeError(f"Trade feature set contains +/-inf values: {bad_inf}")
    all_null = [col for col in MODEL_FEATURES if trades[col].isna().all()]
    if all_null:
        raise RuntimeError(f"Trade feature columns are entirely null: {all_null}")



def build_trade_dataset(df: pd.DataFrame) -> pd.DataFrame:
    """Build TP×SL discoverable triple-barrier labels at entry bars.

    Each entry candidate expands into a 4×3 grid:
      - SL ATR multiples: {0.75, 1.0, 1.5, 2.0}   ATR-based stop, multiples of
                                                  the entry-bar `ml_atr14`.
      - TP ratios:        {1.000, 1.236, 1.618}   fib-ladder extensions read
                                                  directly from Pine's per-row
                                                  `ml_trade_tp1` /
                                                  `ml_trade_tp2` /
                                                  `ml_trade_tp3` (one column
                                                  per ratio, same index order
                                                  as DISCOVERABLE_TP_RATIOS).

    Forward-scan window is fixed at `FORWARD_SCAN_BARS = 24` bars (the ES 15m
    entry-precision contract). Every label is computed over that same 24-bar
    window: entry classifier, tp_hit, stop_hit, MFE, MAE. Entries closer
    than `MIN_FUTURE_BARS = 24` bars to end-of-data are DROPPED because they
    cannot be fairly assessed. Embargo for the train/val/test split is
    `EMBARGO_BARS = 25` (label horizon + 1).

    Three label columns are emitted per combo row:

      winner_tp_before_sl (LABEL_COL):
        Pessimistic resolution outcome FOR THE SPECIFIC (sl_mult, tp_ratio)
        combo encoded in this row.
          1 iff this combo's TP price touched strictly before its SL price
            within the 24-bar window.
          0 if SL touched first, both touched same bar (intrabar sequencing
            unobservable -> pessimistic loss), OR neither touched within 24
            bars (sideways / avoid).
        This is the entry classifier's supervision target —
        production-faithful: the model trains on the same fib-ladder TP ×
        ATR-based SL exit family the Pine indicator live-trades, with the
        same 24-bar quality window.

      tp_hit (TP_LABEL_COL), stop_hit (STOP_LABEL_COL):
        TOUCH EVENTS at the resolution bar — NOT resolution outcomes. tp_hit=1
        means the TP price was crossed on the bar where the trade resolved.
        On same-bar collisions both flags are 1 (TP was touched, SL was touched)
        even though winner_tp_before_sl=0. These are the supervision targets
        for the auxiliary --model-suite predictors, which estimate "P(TP
        touched at resolution)" and "P(SL touched at resolution)" — physically
        valid probabilities the downstream EV/policy layer combines with the
        entry probability. Do not interpret tp_hit=1 as 'trade won'.

    Same-bar conflict handling: pessimistic loss for winner_tp_before_sl; raw
    touch flags preserved for tp_hit/stop_hit. This is the canonical contract
    consumed by scripts.ag.monte_carlo_v9 and scripts.ag.shap_v9 via shared
    import — do not reimplement.
    """
    df = df.sort_values("ts").reset_index(drop=True)
    long_mask = df["ml_entry_long_trigger"].astype(float) > 0
    short_mask = df["ml_entry_short_trigger"].astype(float) > 0
    entry_mask = long_mask | short_mask
    entry_idx = np.where(entry_mask)[0]
    print(f"  entry candidates: {len(entry_idx):,}", flush=True)

    highs = df["high"].to_numpy(dtype=float)
    lows = df["low"].to_numpy(dtype=float)
    entries = (
        df["ml_trade_entry"].to_numpy(dtype=float)
        if "ml_trade_entry" in df.columns
        else np.full(len(df), np.nan)
    )
    # Per-combo TP price columns, indexed by tp_family_code (1/2/3).
    # Required-input contract — Pine emits these from current fib geometry
    # on every bar; missing-column at this stage is a fatal validation error.
    tp_arrays_by_code: dict[int, np.ndarray] = {
        idx + 1: df[col].to_numpy(dtype=float)
        for idx, col in enumerate(LABEL_INPUT_TP_COLUMNS)
    }
    stops = (
        df["ml_trade_stop"].to_numpy(dtype=float)
        if "ml_trade_stop" in df.columns
        else np.full(len(df), np.nan)
    )
    closes = df["close"].to_numpy(dtype=float)
    atr_vals = (
        pd.to_numeric(df["ml_atr14"], errors="coerce").to_numpy(dtype=float)
        if "ml_atr14" in df.columns
        else np.full(len(df), np.nan)
    )

    rows: list[dict[str, Any]] = []
    dropped_insufficient = 0
    neither_hit_zeros = 0

    for i in entry_idx:
        # Drop entries that cannot be fairly assessed: need at least
        # FORWARD_SCAN_BARS future bars after i.
        if (len(df) - i - 1) < FORWARD_SCAN_BARS:
            dropped_insufficient += 1
            continue
        entry_price = entries[i] if pd.notna(entries[i]) and entries[i] > 0 else closes[i]
        is_long = bool(long_mask.iloc[i])

        atr_i = atr_vals[i]
        if not pd.notna(atr_i) or float(atr_i) <= 1e-9:
            existing_stop = (
                stops[i]
                if pd.notna(stops[i]) and stops[i] > 0
                else (entry_price - 5.0 if is_long else entry_price + 5.0)
            )
            atr_i = abs(float(existing_stop) - float(entry_price)) / 1.5
            if atr_i <= 1e-9:
                atr_i = 1.0

        mfe_points = 0.0
        mae_points = 0.0
        end_idx = i + FORWARD_SCAN_BARS + 1
        if end_idx > i + 1:
            future_high = highs[i + 1:end_idx]
            future_low = lows[i + 1:end_idx]
            if is_long:
                mfe_points = float(np.nanmax(future_high - entry_price))
                mae_points = float(np.nanmax(entry_price - future_low))
            else:
                mfe_points = float(np.nanmax(entry_price - future_low))
                mae_points = float(np.nanmax(future_high - entry_price))
            mfe_points = max(mfe_points, 0.0)
            mae_points = max(mae_points, 0.0)

        for sl_mult in DISCOVERABLE_SL_ATR_MULTS:
            stop_dist = max(float(atr_i) * float(sl_mult), 0.25)
            sl_price = float(entry_price - stop_dist if is_long else entry_price + stop_dist)

            for tp_family_code, tp_ratio in enumerate(DISCOVERABLE_TP_RATIOS, start=1):
                # Pine-emitted TP for this fib-ratio family (no Python-side
                # reconstruction — the price comes straight from the ladder
                # plot in indicators/warbird-pro-v9.pine).
                tp_raw = tp_arrays_by_code[tp_family_code][i]
                if not pd.notna(tp_raw) or float(tp_raw) <= 0:
                    # Pine couldn't emit a ladder price for this bar (fib
                    # range invalid). Skip the combo — it's not a fair label.
                    continue
                tp_price = float(tp_raw)
                target_dist = abs(tp_price - entry_price)

                target_hit_idx = -1
                stop_hit_idx = -1
                resolution_bar = -1
                outcome = 0

                for j in range(i + 1, end_idx):
                    h = highs[j]
                    l = lows[j]

                    if is_long and l <= sl_price:
                        stop_hit_idx = j
                    elif (not is_long) and h >= sl_price:
                        stop_hit_idx = j

                    if is_long and h >= tp_price:
                        target_hit_idx = j
                    elif (not is_long) and l <= tp_price:
                        target_hit_idx = j

                    if target_hit_idx != -1 and stop_hit_idx != -1:
                        outcome = 0
                        resolution_bar = j
                        break
                    if target_hit_idx != -1:
                        outcome = 1
                        resolution_bar = j
                        break
                    if stop_hit_idx != -1:
                        outcome = 0
                        resolution_bar = j
                        break
                else:
                    # Neither barrier touched within the 24-bar window.
                    # Label = 0 (sideways / avoid). Resolution sentinel =
                    # FORWARD_SCAN_BARS + 1 so embargo math and resolution
                    # diagnostics treat this row as a full-window miss.
                    neither_hit_zeros += 1
                    outcome = 0
                    resolution_bar = i + FORWARD_SCAN_BARS + 1

                rec = {col: df[col].iloc[i] for col in ML_FEATURES}
                rec["sl_atr_mult"] = float(sl_mult)
                rec["tp_ratio"] = float(tp_ratio)
                rec["tp_family_code"] = int(tp_family_code)
                rec["tp_is_t2"] = 1.0 if abs(float(tp_ratio) - 1.618) < 1e-12 else 0.0
                rec["target_distance_points"] = float(target_dist)
                rec["stop_distance_points"] = float(stop_dist)
                rec["rr_ratio"] = float(target_dist / stop_dist) if stop_dist > 1e-9 else 0.0
                rec["ts"] = df["ts"].iloc[i]
                rec["direction"] = 1 if is_long else -1
                rec["entry_price"] = float(entry_price)
                rec["target_price"] = float(tp_price)
                rec["stop_price"] = float(sl_price)
                rec[LABEL_COL] = outcome
                rec[TP_LABEL_COL] = 1 if target_hit_idx != -1 else 0
                rec[STOP_LABEL_COL] = 1 if stop_hit_idx != -1 else 0
                rec["time_to_tp_bars"] = target_hit_idx - i if target_hit_idx != -1 else (FORWARD_SCAN_BARS + 1)
                rec["time_to_stop_bars"] = stop_hit_idx - i if stop_hit_idx != -1 else (FORWARD_SCAN_BARS + 1)
                rec[MFE_LABEL_COL] = mfe_points
                rec[MAE_LABEL_COL] = mae_points
                rec["stop_required_atr"] = float(mae_points / atr_i) if pd.notna(atr_i) and abs(float(atr_i)) > 1e-12 else 0.0
                rec["_outcome_code"] = 1 if outcome == 1 else -1
                rec["_bars_to_resolution"] = resolution_bar - i
                rec["_combo_id"] = f"tp{tp_family_code}_sl{sl_mult:.1f}"
                rows.append(rec)

    if not rows:
        out_cols = [
            *MODEL_FEATURES,
            "ts",
            "direction",
            "entry_price",
            "target_price",
            "stop_price",
            LABEL_COL,
            TP_LABEL_COL,
            STOP_LABEL_COL,
            "time_to_tp_bars",
            "time_to_stop_bars",
            MFE_LABEL_COL,
            MAE_LABEL_COL,
            "stop_required_atr",
            "_outcome_code",
            "_bars_to_resolution",
            "_combo_id",
        ]
        print("  resolved trades: 0")
        print(f"  dropped (insufficient future bars): {dropped_insufficient:,}")
        print(f"  neither-hit labeled 0: {neither_hit_zeros:,}")
        return pd.DataFrame(columns=out_cols)

    out = pd.DataFrame(rows).sort_values("ts").reset_index(drop=True)
    print(f"  resolved trades: {len(out):,}")
    print(f"  dropped (insufficient future bars): {dropped_insufficient:,}")
    print(f"  neither-hit labeled 0: {neither_hit_zeros:,}")
    if len(out) > 0:
        print(
            f"  {LABEL_COL} rate: {out[LABEL_COL].mean():.4f}"
            f"  ({int(out[LABEL_COL].sum()):,} positives / {len(out):,} total)"
        )
    validate_trade_features(out)
    return out


def split_trade_positions(
    trades: pd.DataFrame,
    train_frac: float,
    val_frac: float,
    embargo_bars: int,
    label_horizon_bars: int,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    if "profile_id" not in trades.columns:
        train_end_idx = int(len(trades) * train_frac)
        val_end_idx = int(len(trades) * (train_frac + val_frac))
        return embargoed_chronological_split(
            n_samples=len(trades),
            train_end_idx=train_end_idx,
            val_end_idx=val_end_idx,
            embargo_bars=embargo_bars,
            label_horizon_bars=label_horizon_bars,
        )

    unique_ts = pd.Series(pd.to_datetime(trades["ts"], utc=True).drop_duplicates().to_numpy())
    train_end_idx = int(len(unique_ts) * train_frac)
    val_end_idx = int(len(unique_ts) * (train_frac + val_frac))
    train_ts_pos, val_ts_pos, test_ts_pos = embargoed_chronological_split(
        n_samples=len(unique_ts),
        train_end_idx=train_end_idx,
        val_end_idx=val_end_idx,
        embargo_bars=embargo_bars,
        label_horizon_bars=label_horizon_bars,
    )
    train_ts = set(unique_ts.iloc[train_ts_pos])
    val_ts = set(unique_ts.iloc[val_ts_pos])
    test_ts = set(unique_ts.iloc[test_ts_pos])
    ts_values = pd.to_datetime(trades["ts"], utc=True)
    train_pos = np.flatnonzero(ts_values.isin(train_ts).to_numpy())
    val_pos = np.flatnonzero(ts_values.isin(val_ts).to_numpy())
    test_pos = np.flatnonzero(ts_values.isin(test_ts).to_numpy())
    return train_pos, val_pos, test_pos


def _fit_locked_predictor(
    *,
    train: pd.DataFrame,
    val: pd.DataFrame,
    test: pd.DataFrame,
    label: str,
    spec: dict[str, str],
    out_dir: Path,
    time_limit: int,
    feature_cols: list[str],
) -> dict[str, Any]:
    from autogluon.tabular import TabularPredictor

    out_dir.mkdir(parents=True, exist_ok=False)
    problem_type = spec["problem_type"]
    pred = TabularPredictor(
        label=label,
        path=str(out_dir),
        eval_metric=spec["eval_metric"],
        problem_type=problem_type,
    ).fit(
        train_data=train[feature_cols + [label]],
        tuning_data=val[feature_cols + [label]],
        use_bag_holdout=False,
        time_limit=time_limit,
        presets="best_quality",
        calibrate=problem_type == "binary",
        num_bag_folds=0,
        num_stack_levels=0,
        dynamic_stacking=False,
        ag_args_ensemble={"fold_fitting_strategy": "sequential_local"},
        hyperparameter_tune_kwargs={
            "searcher": "random",
            "scheduler": "local",
            "num_trials": 20,
        },
        hyperparameters={
            "GBM": [{"num_threads": 1}, {"num_threads": 1, "extra_trees": True}],
            "CAT": {"thread_count": 1},
            "XGB": {"n_jobs": 1},
            "RF":  [{"criterion": "gini"}, {"criterion": "entropy"}],
            "XT":  [{"criterion": "gini"}, {"criterion": "entropy"}],
            "NN_TORCH": {},
            "FASTAI":   {},
        },
        verbosity=2,
        num_gpus=0,
    )
    pred.persist()
    test_data = test[feature_cols + [label]]
    lb = pred.leaderboard(test_data, extra_info=True, silent=True)
    lb.to_csv(out_dir / "leaderboard.csv", index=False)
    fi = pred.feature_importance(test_data, num_shuffle_sets=5)
    fi.to_csv(out_dir / "feature_importance.csv")
    return {
        "label": label,
        "problem_type": problem_type,
        "eval_metric": spec["eval_metric"],
        "rows": {
            "train": int(len(train)),
            "val": int(len(val)),
            "test": int(len(test)),
        },
        "leaderboard_top_model": str(lb.iloc[0]["model"]) if len(lb) else None,
        "leaderboard_top_score_test": float(lb.iloc[0]["score_test"]) if len(lb) else None,
        "leaderboard_top_score_val": float(lb.iloc[0]["score_val"]) if len(lb) else None,
        "feature_importance_top10": fi.head(10).to_dict(orient="index"),
    }


def _git_commit_hash() -> str:
    try:
        result = subprocess.run(
            ["git", "-C", str(REPO_ROOT), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        )
    except Exception:
        return "unknown"
    value = result.stdout.strip()
    return value if value else "unknown"


def _split_bounds_payload(df: pd.DataFrame) -> dict[str, str | None]:
    if df.empty:
        return {"ts_start": None, "ts_end": None}
    ts = pd.to_datetime(df["ts"], utc=True)
    return {
        "ts_start": ts.min().isoformat(),
        "ts_end": ts.max().isoformat(),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", type=Path, default=CSV_PATH)
    ap.add_argument("--output-root", type=Path, default=OUTPUT_ROOT)
    ap.add_argument("--time-limit", type=int, default=7200)
    ap.add_argument("--train-frac", type=float, default=0.70)
    ap.add_argument("--val-frac", type=float, default=0.15)
    ap.add_argument("--validate-only", action="store_true",
                    help="Build labels/splits and run hard schema gates without fitting AutoGluon.")
    ap.add_argument("--smoke-ok", action="store_true",
                    help="With --validate-only, accept a small smoke CSV below full-training trade/split floors.")
    ap.add_argument("--model-suite", action="store_true",
                    help="Fit entry, TP, stop, MFE, and MAE predictors instead of only the entry classifier.")
    args = ap.parse_args()
    if args.smoke_ok and not args.validate_only:
        raise SystemExit("--smoke-ok is only valid with --validate-only")
    if not (0.0 < args.train_frac < 1.0):
        raise SystemExit("--train-frac must be in (0, 1)")
    if not (0.0 < args.val_frac < 1.0):
        raise SystemExit("--val-frac must be in (0, 1)")
    if args.train_frac + args.val_frac >= 1.0:
        raise SystemExit("--train-frac + --val-frac must leave a non-empty test segment")

    print(f"loading {args.csv}", flush=True)
    df = pd.read_csv(args.csv, parse_dates=["ts"])
    print(f"  rows={len(df):,}  range={df['ts'].iloc[0]} -> {df['ts'].iloc[-1]}", flush=True)
    validate_input_schema(df)

    trades = build_trade_dataset(df)
    feature_cols = list(MODEL_FEATURES)
    if args.validate_only and args.smoke_ok:
        if len(trades) == 0:
            raise RuntimeError("Smoke validation requires at least one resolved trade")
        if trades[LABEL_COL].nunique() != 2:
            raise RuntimeError(f"Smoke validation requires both {LABEL_COL} classes")
        print("\nsmoke validate-only PASS")
        print(f"  resolved trades: {len(trades):,}")
        print(f"  positives: {int(trades[LABEL_COL].sum()):,}")
        print(f"  negatives: {int((1 - trades[LABEL_COL]).sum()):,}")
        print(f"  features: {len(feature_cols)}")
        print(f"  label: {LABEL_COL}")
        return 0

    if len(trades) < 200:
        raise RuntimeError(f"Too few resolved trades: {len(trades):,}")
    if trades[LABEL_COL].nunique() != 2:
        raise RuntimeError(f"{LABEL_COL} must contain both classes")

    # Label-horizon-aware embargo. Fixed 24-bar forward-scan contract:
    # every label is computed over the same 24-bar window, so the embargo is
    # the constant EMBARGO_BARS (= FORWARD_SCAN_BARS + 1 = 25).
    label_horizon_bars = FORWARD_SCAN_BARS
    embargo_bars = EMBARGO_BARS

    train_pos, val_pos, test_pos = split_trade_positions(
        trades,
        train_frac=args.train_frac,
        val_frac=args.val_frac,
        embargo_bars=embargo_bars,
        label_horizon_bars=label_horizon_bars,
    )
    train_df = trades.iloc[train_pos].copy()
    val_df = trades.iloc[val_pos].copy()
    test_df = trades.iloc[test_pos].copy()

    print(f"\nsplit (embargo={embargo_bars} bars between segments):")
    print(f"  IS  (train):  {len(train_df):,}  WR={train_df[LABEL_COL].mean():.4f}  ({train_df['ts'].min()} → {train_df['ts'].max()})", flush=True)
    print(f"  VAL (tuning): {len(val_df):,}  WR={val_df[LABEL_COL].mean():.4f}  ({val_df['ts'].min()} → {val_df['ts'].max()})", flush=True)
    print(f"  OOS (test):   {len(test_df):,}  WR={test_df[LABEL_COL].mean():.4f}  ({test_df['ts'].min()} → {test_df['ts'].max()})", flush=True)
    if len(train_df) < 200 or len(val_df) < 50 or len(test_df) < 50:
        raise RuntimeError(f"Splits too thin: train={len(train_df)} val={len(val_df)} test={len(test_df)}")
    for name, slice_df in (("train", train_df), ("val", val_df), ("test", test_df)):
        if slice_df[LABEL_COL].nunique() != 2:
            raise RuntimeError(f"{name} split missing one label class")

    if args.validate_only:
        selected_specs_for_log = MODEL_SPECS if args.model_suite else {"entry": MODEL_SPECS["entry"]}
        print("\nvalidate-only PASS")
        print(f"  features: {len(feature_cols)}")
        print(f"  labels: {', '.join(spec['label'] for spec in selected_specs_for_log.values())}")
        print(f"  label_horizon_bars: {label_horizon_bars} (data-derived)")
        print(f"  embargo_bars: {embargo_bars}")
        return 0

    ts_tag = pd.Timestamp.now().strftime("%Y%m%d_%H%M%S")
    out_dir = args.output_root / f"locked_{ts_tag}"
    out_dir.mkdir(parents=True, exist_ok=False)

    print(f"\nLOCKED AG full-zoo run", flush=True)
    print(f"  output dir:    {out_dir}", flush=True)
    print(f"  features:      {len(feature_cols)} ({', '.join(feature_cols[:6])}, ...)", flush=True)
    print(f"  time-limit:    {args.time_limit}s", flush=True)
    print(f"  preset:        best_quality (full zoo, no bagging/stacking)", flush=True)
    print(f"  calibrate:     True (isotonic calibration for EV rule)", flush=True)
    print(f"  num_bag_folds: 0 (time-series safe)", flush=True)
    print(f"  stack_levels:  0", flush=True)
    print(f"  dyn_stacking:  False (explicit, reproducible)", flush=True)
    print(f"  HPO:           random searcher, 20 trials per family", flush=True)
    print(f"  zoo:           7-family canonical (single-thread pins)", flush=True)
    print(f"  eval_metric:   log_loss (probability scoring for EV rule)", flush=True)
    print(f"  OMP_NUM_THREADS={os.environ.get('OMP_NUM_THREADS')} KMP_DUPLICATE_LIB_OK={os.environ.get('KMP_DUPLICATE_LIB_OK')}", flush=True)

    selected_specs = MODEL_SPECS if args.model_suite else {"entry": MODEL_SPECS["entry"]}
    model_summaries: dict[str, Any] = {}
    for model_key, spec in selected_specs.items():
        label = spec["label"]
        if label not in train_df.columns:
            raise RuntimeError(f"Requested model {model_key!r} but label column is missing: {label}")
        model_dir = out_dir / model_key if args.model_suite else out_dir / "entry"
        print(f"\n=== fitting {model_key} model ({label}) ===", flush=True)
        summary = _fit_locked_predictor(
            train=train_df,
            val=val_df,
            test=test_df,
            label=label,
            spec=spec,
            out_dir=model_dir,
            time_limit=args.time_limit,
            feature_cols=feature_cols,
        )
        model_summaries[model_key] = summary
        print(f"  top model: {summary['leaderboard_top_model']} score_test={summary['leaderboard_top_score_test']}", flush=True)

    csv_provenance = build_csv_provenance(args.csv)
    summary = {
        "trained_at": ts_tag,
        "csv_sha256_assumed_via_manifest": csv_provenance.get("manifest_declared_csv_sha256"),
        "csv_sha256": csv_provenance["csv_sha256"],
        "csv_path": str(args.csv),
        "is_rows": int(len(train_df)),
        "val_rows": int(len(val_df)),
        "oos_rows": int(len(test_df)),
        "is_winrate": float(train_df[LABEL_COL].mean()),
        "val_winrate": float(val_df[LABEL_COL].mean()),
        "oos_winrate": float(test_df[LABEL_COL].mean()),
        "feature_count": len(feature_cols),
        "time_limit_sec": args.time_limit,
        "model_suite": bool(args.model_suite),
        "run_provenance": {
            **csv_provenance,
            "repo_commit": _git_commit_hash(),
        },
        "split_contract": {
            "train_frac": float(args.train_frac),
            "val_frac": float(args.val_frac),
            "label_horizon_bars": int(label_horizon_bars),
            "embargo_bars": int(embargo_bars),
        },
        "split_ranges_utc": {
            "train": _split_bounds_payload(train_df),
            "val": _split_bounds_payload(val_df),
            "oos": _split_bounds_payload(test_df),
        },
        "models": model_summaries,
    }
    summary_path = out_dir / "v9_winner_clf_summary.json"
    summary_path.write_text(json.dumps(summary, default=str, indent=2))
    print(f"\nwrote {summary_path}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
