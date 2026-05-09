"""Guards for scripts/optuna/cpcv.py — Bug 1 cannot recur.

Bug 1 was a 1-bar embargo applied around a 72-bar label horizon in
scripts/ag/train_v9_locked.py (and the now-deprecated train_v9_winner_classifier.py).
These tests prove the cpcv utility refuses any embargo below label_horizon + 1,
and that combinatorial folds + the chronological fixed-split helper both honor
the floor.
"""
from __future__ import annotations

import numpy as np
import pytest

from scripts.optuna.cpcv import (
    combinatorial_purged_splits,
    embargoed_chronological_split,
    n_combinatorial_splits,
)


LABEL_HORIZON = 72  # max_hold_bars used in the AG trainers
FLOOR = LABEL_HORIZON + 1  # cpcv contract


def test_floor_rejects_one_bar_embargo() -> None:
    """The exact regression that produced Bug 1 must raise."""
    with pytest.raises(ValueError, match="below label_horizon_bars\\+1 floor"):
        list(
            combinatorial_purged_splits(
                n_samples=10_000,
                n_splits=6,
                n_test_groups=2,
                embargo_bars=1,
                label_horizon_bars=LABEL_HORIZON,
            )
        )


def test_floor_rejects_under_floor_for_chronological_split() -> None:
    with pytest.raises(ValueError, match="below label_horizon_bars\\+1 floor"):
        embargoed_chronological_split(
            n_samples=10_000,
            train_end_idx=6_000,
            val_end_idx=8_000,
            embargo_bars=10,
            label_horizon_bars=LABEL_HORIZON,
        )


def test_floor_value_is_label_horizon_plus_one() -> None:
    # at floor exactly: must succeed
    list(
        combinatorial_purged_splits(
            n_samples=10_000,
            n_splits=6,
            n_test_groups=2,
            embargo_bars=FLOOR,
            label_horizon_bars=LABEL_HORIZON,
        )
    )
    # one below floor: must raise
    with pytest.raises(ValueError):
        list(
            combinatorial_purged_splits(
                n_samples=10_000,
                n_splits=6,
                n_test_groups=2,
                embargo_bars=FLOOR - 1,
                label_horizon_bars=LABEL_HORIZON,
            )
        )


def test_n_combinatorial_splits_matches_yield_count() -> None:
    n_splits, n_test = 6, 2
    expected = n_combinatorial_splits(n_splits, n_test)  # C(6,2) == 15
    assert expected == 15
    folds = list(
        combinatorial_purged_splits(
            n_samples=20_000,
            n_splits=n_splits,
            n_test_groups=n_test,
            embargo_bars=FLOOR,
            label_horizon_bars=LABEL_HORIZON,
        )
    )
    assert len(folds) == expected


def test_train_and_test_indices_disjoint_with_embargo_gap() -> None:
    embargo = FLOOR
    folds = list(
        combinatorial_purged_splits(
            n_samples=20_000,
            n_splits=6,
            n_test_groups=2,
            embargo_bars=embargo,
            label_horizon_bars=LABEL_HORIZON,
        )
    )
    for train_idx, test_idx in folds:
        assert np.intersect1d(train_idx, test_idx).size == 0
        # Every train sample must be at least `embargo` away from every
        # test sample's contiguous group boundary.
        if train_idx.size and test_idx.size:
            test_min = int(test_idx.min())
            test_max = int(test_idx.max())
            train_min = int(train_idx.min())
            train_max = int(train_idx.max())
            # No train sample can sit inside the embargo window of any test
            # boundary. Sanity: if train spans below test_min, the highest
            # train index below test_min must be <= test_min - embargo.
            below = train_idx[train_idx < test_min]
            if below.size:
                assert int(below.max()) <= test_min - embargo
            above = train_idx[train_idx > test_max]
            if above.size:
                assert int(above.min()) >= test_max + embargo
            # Suppress unused-var lint while preserving the smoke assertion.
            assert train_min <= train_max


def test_chronological_split_applies_embargo_gaps() -> None:
    n = 20_000
    train_end = 12_000
    val_end = 16_000
    embargo = FLOOR
    train_idx, val_idx, test_idx = embargoed_chronological_split(
        n_samples=n,
        train_end_idx=train_end,
        val_end_idx=val_end,
        embargo_bars=embargo,
        label_horizon_bars=LABEL_HORIZON,
    )
    assert train_idx.max() == train_end - 1
    assert val_idx.min() == train_end + embargo
    assert val_idx.max() == val_end - 1
    assert test_idx.min() == val_end + embargo
    assert test_idx.max() == n - 1
    # No overlap.
    assert np.intersect1d(train_idx, val_idx).size == 0
    assert np.intersect1d(val_idx, test_idx).size == 0
    assert np.intersect1d(train_idx, test_idx).size == 0


def test_chronological_split_raises_when_segment_collapses() -> None:
    # Embargo so large the val window vanishes.
    with pytest.raises(ValueError, match="VAL collapsed"):
        embargoed_chronological_split(
            n_samples=1_000,
            train_end_idx=400,
            val_end_idx=410,
            embargo_bars=FLOOR,
            label_horizon_bars=LABEL_HORIZON,
        )


def test_combo_collapses_raise_runtime_error() -> None:
    # n_samples too small relative to n_splits + embargo → some folds collapse
    with pytest.raises((RuntimeError, ValueError)):
        list(
            combinatorial_purged_splits(
                n_samples=200,
                n_splits=6,
                n_test_groups=2,
                embargo_bars=FLOOR,
                label_horizon_bars=LABEL_HORIZON,
            )
        )
