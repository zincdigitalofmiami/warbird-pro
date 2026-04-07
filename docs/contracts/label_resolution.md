# Label Resolution Contract

**Status:** Active

## Purpose

Defines how canonical outcomes and model labels are resolved from point-in-time candidates.

## Canonical Economic Outcomes

- `TP2_HIT`
- `TP1_ONLY`
- `STOPPED`
- `REVERSAL`
- `OPEN`

`OPEN` is operational-only and excluded from completed training targets.

## Required Model Labels

- `tp1_before_sl`
- `tp2_before_sl`
- `sl_before_tp1`
- `path_outcome`
- `mae_pts`
- `mfe_pts`

## Resolution Rules

- labels must resolve from point-in-time candidate truth only
- no post-outcome features may participate in label generation
- TP and SL checks must use deterministic price-path rules
- if both TP and SL appear hit in the same bar and no finer path exists, resolve ties conservatively in favor of stop

## Horizon Rule

The active training horizon must be versioned alongside the dataset manifest. Horizon changes require a dataset and packet version bump.

## Partial Progress Rule

- `TP1_ONLY` means TP1 was reached and TP2 was not reached before stop or resolution cutoff
- `TP2_HIT` implies TP1 was reached first or on the same resolved path

## Derived Metrics

- `mae_pts` and `mfe_pts` are measured from the canonical entry reference to the worst and best realized excursion before resolution
