import pandas as pd

from scripts.ag.train_v9_locked import (
    DISCOVERABLE_SL_ATR_MULTS,
    DISCOVERABLE_TP_RATIOS,
    LABEL_COL,
    ML_FEATURES,
    TRADE_DISCOVERABLE_FEATURES,
    build_trade_dataset,
)


def _feature_defaults() -> dict[str, object]:
    out: dict[str, object] = {}
    for col in ML_FEATURES:
        # symbol-knob columns are strings; everything else defaults to 0.0
        if col in {"knob_nq_symbol", "knob_zn_symbol", "knob_6e_symbol", "knob_vix_symbol"}:
            out[col] = "TEST"
        elif col == "knob_zn_gate_direction":
            out[col] = "Same Direction"
        else:
            out[col] = 0.0
    return out


def test_trade_dataset_uses_emitted_entry_tp_stop_and_adds_tp_sl_sidecar_labels():
    """One bullish entry expands into the TP/SL combo grid.

    Trade-surface contract (locked 2026-05-11):
      - Each entry candidate fans out to (#TP × #SL) combos.
      - Combos that resolve (TP hit or SL hit within max_hold_bars) become rows.
      - Combos that neither hit are dropped.
      - Each combo row carries the 6 TRADE_DISCOVERABLE_FEATURES so AG can learn
        per-combo trade geometry as a model input.
    """
    rows = []
    for i, (high, low, close) in enumerate(
        [
            (101.0, 99.0, 100.0),
            (108.5, 99.5, 108.0),
            (109.0, 100.0, 108.5),
        ]
    ):
        rec = _feature_defaults()
        rec.update(
            {
                "ts": pd.Timestamp("2026-01-01T00:00:00Z") + pd.Timedelta(minutes=15 * i),
                "high": high,
                "low": low,
                "close": close,
                "ml_entry_long_trigger": 1.0 if i == 0 else 0.0,
                "ml_entry_short_trigger": 0.0,
                "ml_trade_entry": 100.0 if i == 0 else 0.0,
                "ml_trade_tp": 108.0 if i == 0 else 0.0,
                "ml_trade_stop": 97.0 if i == 0 else 0.0,
            }
        )
        rows.append(rec)
    df = pd.DataFrame(rows)

    trades = build_trade_dataset(df, max_hold_bars=2)

    # Combo expansion: 1 entry × N TP × N SL combos, minus neither-hit drops.
    # Bullish fixture (high reaches 108.5 within 2 bars from entry=100) means
    # the nearest TP families hit; the farthest (tp_ratio=1.618) drops in the
    # 2-bar window. Resolved rows must be > 1 and contain the discoverables.
    assert len(trades) > 1, "combo expansion should produce multiple rows per entry"
    n_tp = len(DISCOVERABLE_TP_RATIOS)
    n_sl = len(DISCOVERABLE_SL_ATR_MULTS)
    assert len(trades) <= n_tp * n_sl, (
        f"trades ({len(trades)}) exceeds full TP×SL grid ({n_tp * n_sl})"
    )

    # All discoverable features present as columns
    for col in TRADE_DISCOVERABLE_FEATURES:
        assert col in trades.columns, f"discoverable feature missing: {col}"

    # Values of tp_ratio and sl_atr_mult are subsets of the declared families
    assert set(trades["tp_ratio"].astype(float)).issubset(set(DISCOVERABLE_TP_RATIOS))
    assert set(trades["sl_atr_mult"].astype(float)).issubset(set(DISCOVERABLE_SL_ATR_MULTS))

    # Every resolved combo for this bullish fixture is a win (high hits TP1/TP2)
    assert (trades[LABEL_COL] == 1).all(), "all resolved combos should be wins for this bullish fixture"
    assert (trades["tp_hit"] == 1).all()
    assert (trades["stop_hit"] == 0).all()

    # rr_ratio must be > 0 for any resolved combo
    assert (trades["rr_ratio"].astype(float) > 0).all()
