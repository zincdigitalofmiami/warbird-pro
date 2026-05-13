from scripts.ag.train_v9_locked import ML_FEATURES, MODEL_FEATURES, TRADE_DISCOVERABLE_FEATURES
from scripts.duckdb_local.workspaces.warbird_pro_core import build_core_dataset as core


REQUIRED_KNOBS = {
    "knob_auto_tune_zz",
    "knob_fib_deviation_manual",
    "knob_fib_depth_manual",
    "knob_fib_threshold_floor_pct",
    "knob_min_fib_range_atr",
    "knob_fib_hysteresis_pct",
    "knob_htf_conf_tol_pct",
    "knob_use_pattern_confirm",
    "knob_use_liq_gate",
    "knob_liq_recency_bars",
    "knob_trade_stop_atr_mult",
    "knob_trade_max_hold_bars",
    "knob_use_ma_gate",
    "knob_length_ema",
    "knob_length_ma",
    "knob_rsi_length",
    "knob_rsi_overbought",
    "knob_rsi_oversold",
    "knob_liq_lookback_bars",
    "knob_eqh_tol_pct",
    "knob_eqh_min_taps",
    "knob_eqh_lookback",
    "knob_vol_z_length",
    "knob_use_session_vwap",
    "knob_use_xa_gate",
    "knob_nq_symbol",
    "knob_zn_symbol",
    "knob_6e_symbol",
    "knob_vix_symbol",
    "knob_corr_length",
    "knob_vix_move_bars",
    "knob_vix_atr_length",
    "knob_vix_pressure_band",
    "knob_xa_min_agreement",
    "knob_zn_gate_direction",
    "knob_use_footprint",
    "knob_fp_ticks_per_row",
    "knob_fp_va_pct",
    "knob_fp_imbalance_pct",
    "knob_fp_absorption_delta_pct",
    "knob_fp_flush_delta_pct",
    "knob_fp_event_vol_spike",
    "knob_fp_compressed_range_atr",
}


REQUIRED_FEATURES = {
    "ml_entry_long_trigger",
    "ml_entry_short_trigger",
    "ml_trade_entry",
    "ml_trade_stop",
    # `ml_trade_tp` retired 2026-05-12 — Pine emits the fib ladder via
    # ml_trade_tp1/2/3 which are label-construction inputs (not ML_FEATURES).
    "ml_fib_touch_level_code",
    "ml_fib_entry_dist_atr",
    "ml_fib_pierce_atr",
    "ml_fib_close_reclaim_atr",
    "ml_fib_reaction_body_ratio",
    "ml_fib_reaction_upper_wick_ratio",
    "ml_fib_reaction_lower_wick_ratio",
    "ml_fib_reaction_code",
    "ml_recent_liq_bull",
    "ml_recent_liq_bear",
    "ml_liq_bars_since_bull",
    "ml_liq_bars_since_bear",
    "ml_xa_long_agreement",
    "ml_xa_short_agreement",
    # Phase 1 continuous cross-asset features (locked 2026-05-11 gate-as-feature pivot).
    # DXY (Yahoo) removed 2026-05-11; 6E (Databento CME) replaces.
    "ml_xa_6e_code",
    "ml_xa_nq_rel_strength_atr",
    "ml_xa_6e_momentum_zscore",
}


LEAN_CUT_KEEPERS = {
    "ml_xa_long_agreement",
    "ml_xa_short_agreement",
}


LEAN_CUT_DROPS_MUST_BE_ABSENT = {
    "ml_lvl_pdh_dist_atr",
    "ml_lvl_pdl_dist_atr",
    "ml_lvl_pwh_dist_atr",
    "ml_lvl_pwl_dist_atr",
    "ml_fib_touch_500_long",
    "ml_fib_touch_618_long",
    "ml_fib_touch_786_long",
    "ml_fib_touch_500_short",
    "ml_fib_touch_618_short",
    "ml_fib_touch_786_short",
    "ml_fp_delta_pct",
    "ml_fp_poc_dist_atr",
    "ml_fp_va_position",
    "ml_delta_imbalance_pct",
    "ml_delta_acceleration",
    "ml_aggressor_pulse",
    "ml_absorption_candidate",
    "ml_flush_candidate",
    "ml_poc_shift",
    "ml_cvd_div_bull",
    "ml_cvd_div_bear",
    "ml_xa_zn_code",
    "ml_xa_zn_rate_pressure",
    "ml_xa_vix_pressure",
    "ml_xa_hg_growth_proxy",
}


def test_all_model_affecting_indicator_inputs_are_knob_columns():
    assert REQUIRED_KNOBS.issubset(set(core.KNOB_COLUMNS))


def test_entry_fib_liquidity_symbol_context_is_in_ag_features():
    assert REQUIRED_FEATURES.issubset(set(ML_FEATURES))


def test_trade_discoverables_are_in_model_feature_surface():
    assert set(TRADE_DISCOVERABLE_FEATURES).issubset(set(MODEL_FEATURES))


def test_v9_feature_surface_counts_are_locked():
    assert len(ML_FEATURES) == 82
    assert len(MODEL_FEATURES) == 88


def test_lean_cut_keeper_agreement_features_are_present():
    assert LEAN_CUT_KEEPERS.issubset(set(ML_FEATURES))


def test_lean_cut_dropped_features_absent_from_ml_features():
    assert not (set(ML_FEATURES) & LEAN_CUT_DROPS_MUST_BE_ABSENT)


def test_ml_features_do_not_intersect_dropped_feature_constant():
    dropped = set(core.DROPPED_FEATURES_2026_05_12)
    assert not (set(ML_FEATURES) & dropped)


def test_manifest_declares_indicator_knobs_and_feature_columns():
    profiles = core.generate_indicator_profiles("base")
    assert len(profiles) == 1
    profile = profiles[0]
    assert REQUIRED_KNOBS.issubset(profile.keys())
    assert profile["knob_nq_symbol"] == "CME_MINI:NQ1!"
    assert profile["knob_zn_symbol"] == "CBOT:ZN1!"
    assert profile["knob_6e_symbol"] == "CME:6E1!"
    assert profile["knob_vix_symbol"] == "CBOE:VIX"
