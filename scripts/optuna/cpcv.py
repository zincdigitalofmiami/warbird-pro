#!/usr/bin/env python3
"""Combinatorial Purged Cross-Validation with label-horizon-aware embargo.

Vendored, dependency-free implementation of López de Prado's CPCV pattern
(Advances in Financial Machine Learning, Ch. 7). Mirrors the contract of
skfolio.model_selection.CombinatorialPurgedCV without adding skfolio as a
dependency.

Used by:
- scripts/ag/train_v9_locked.py (V9 Core diagnostic splits)
- scripts/optuna/cards/core_training/ (Core AG card, under construction)

(Originally also used by the Hybrid+ 4-card chain. That chain was deprecated
2026-05-09; its profile modules raise SystemExit on import.)

Hard contract: embargo_bars MUST be >= label_horizon_bars + 1. The
_enforce_embargo_floor() check raises ValueError if violated, so a regression
to a smaller embargo is impossible without explicit code change. This is the
single source of truth that makes Bug 1 (1-bar embargo with 72-bar label
horizon) impossible to recur.

References:
- López de Prado, M. (2018). Advances in Financial Machine Learning, Ch. 7.
- skfolio CombinatorialPurgedCV docs:
  https://skfolio.org/generated/skfolio.model_selection.CombinatorialPurgedCV.html
"""
from __future__ import annotations

from collections.abc import Iterator
from itertools import combinations
from math import comb

import numpy as np


def _enforce_embargo_floor(embargo_bars: int, label_horizon_bars: int) -> None:
    floor = label_horizon_bars + 1
    if embargo_bars < floor:
        raise ValueError(
            f"embargo_bars={embargo_bars} is below label_horizon_bars+1 floor "
            f"({floor}); label leakage would be possible. Increase embargo or "
            f"reduce label horizon."
        )


def n_combinatorial_splits(n_splits: int, n_test_groups: int) -> int:
    """Return how many combinatorial folds CPCV will yield.

    Raises ValueError if n_test_groups is not in [1, n_splits - 1].
    """
    if not (1 <= n_test_groups < n_splits):
        raise ValueError(
            f"n_test_groups must be in [1, n_splits-1]; got "
            f"{n_test_groups}/{n_splits}"
        )
    return comb(n_splits, n_test_groups)


def combinatorial_purged_splits(
    n_samples: int,
    n_splits: int,
    n_test_groups: int,
    embargo_bars: int,
    label_horizon_bars: int,
) -> Iterator[tuple[np.ndarray, np.ndarray]]:
    """Yield (train_idx, test_idx) pairs for CPCV with embargo around test.

    Samples are assumed to be ordered chronologically (e.g., trade-entry bars
    sorted by ts). The function partitions [0, n_samples) into n_splits
    contiguous equal-sized groups, then for every C(n_splits, n_test_groups)
    combination treats the chosen groups as the test set and the rest as
    train, applying an embargo of embargo_bars around each test group's
    boundaries to purge any train sample whose label horizon could leak into
    the test region.

    Args:
        n_samples: total chronological samples.
        n_splits: number of equal contiguous groups to partition into.
        n_test_groups: how many groups form the test set per fold.
        embargo_bars: bars to embargo around test groups; MUST be
            >= label_horizon_bars + 1.
        label_horizon_bars: maximum forward-looking bars used to construct
            labels (used to enforce the embargo floor).

    Yields:
        (train_idx, test_idx) numpy int arrays of indices into [0, n_samples).

    Raises:
        ValueError: invalid parameters or embargo below the label-horizon floor.
        RuntimeError: any fold collapses to an empty train or test set
            (e.g., n_samples too small for the chosen splits + embargo).
    """
    _enforce_embargo_floor(embargo_bars, label_horizon_bars)
    if n_splits < 2:
        raise ValueError(f"n_splits must be >= 2, got {n_splits}")
    if not (1 <= n_test_groups < n_splits):
        raise ValueError(
            f"n_test_groups must be in [1, n_splits-1]; got "
            f"{n_test_groups}/{n_splits}"
        )
    if n_samples < n_splits:
        raise ValueError(
            f"n_samples ({n_samples}) < n_splits ({n_splits}); cannot partition"
        )

    bounds = np.linspace(0, n_samples, n_splits + 1, dtype=int)
    groups = [(int(bounds[i]), int(bounds[i + 1])) for i in range(n_splits)]

    for combo in combinations(range(n_splits), n_test_groups):
        test_pieces = [np.arange(groups[g][0], groups[g][1]) for g in combo]
        test_idx = np.concatenate(test_pieces) if test_pieces else np.array([], dtype=int)

        train_mask = np.ones(n_samples, dtype=bool)
        train_mask[test_idx] = False
        for g in combo:
            lo, hi = groups[g]
            train_mask[max(0, lo - embargo_bars):lo] = False
            train_mask[hi:min(n_samples, hi + embargo_bars)] = False

        train_idx = np.where(train_mask)[0]
        if train_idx.size == 0 or test_idx.size == 0:
            raise RuntimeError(
                f"CPCV fold collapsed: combo={combo} "
                f"train={train_idx.size} test={test_idx.size}"
            )
        yield train_idx, test_idx


def embargoed_chronological_split(
    n_samples: int,
    train_end_idx: int,
    val_end_idx: int,
    embargo_bars: int,
    label_horizon_bars: int,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Return (train_idx, val_idx, test_idx) for a fixed chronological split
    with proper embargo gaps between segments.

    Used by the standalone AG trainers to fix Bug 1 (1-bar embargo on a
    72-bar label horizon) without forcing full CPCV in scripts that are
    about to be subsumed by Hybrid+ Card 3. Card 3 itself uses
    combinatorial_purged_splits().

    Layout (with embargo region E = embargo_bars):
        [ 0 .. train_end_idx )  TRAIN
        [ train_end_idx .. train_end_idx + E )    EMBARGO (dropped)
        [ train_end_idx + E .. val_end_idx )      VAL
        [ val_end_idx .. val_end_idx + E )        EMBARGO (dropped)
        [ val_end_idx + E .. n_samples )          TEST

    Raises ValueError if any segment is empty after applying the embargo,
    or if embargo_bars < label_horizon_bars + 1.
    """
    _enforce_embargo_floor(embargo_bars, label_horizon_bars)
    if not (0 < train_end_idx < val_end_idx < n_samples):
        raise ValueError(
            f"Bad split bounds: train_end={train_end_idx} "
            f"val_end={val_end_idx} n={n_samples}"
        )

    train_idx = np.arange(0, train_end_idx)
    val_start = train_end_idx + embargo_bars
    val_idx = np.arange(val_start, val_end_idx)
    test_start = val_end_idx + embargo_bars
    test_idx = np.arange(test_start, n_samples)

    if val_idx.size == 0:
        raise ValueError(
            f"VAL collapsed after embargo (embargo={embargo_bars}, "
            f"train_end={train_end_idx}, val_end={val_end_idx})"
        )
    if test_idx.size == 0:
        raise ValueError(
            f"TEST collapsed after embargo (embargo={embargo_bars}, "
            f"val_end={val_end_idx}, n={n_samples})"
        )
    return train_idx, val_idx, test_idx
