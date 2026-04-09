# Label Resolution Contract

**Status:** Active

## Purpose

Defines how canonical outcomes and model labels are resolved from point-in-time candidates.

## Canonical Economic Outcomes

- `TP5_HIT`
- `TP4_HIT`
- `TP3_HIT`
- `TP2_HIT`
- `TP1_ONLY`
- `STOPPED`
- `REVERSAL`
- `OPEN`

`OPEN` is operational-only and excluded from completed training targets.

## Exit Target Levels

Five targets tracked by Pine state machine (highest checked first):

| Label | Fib Extension | Pine `ml_last_exit_outcome` code |
|---|---|---|
| TP1 | 1.236 | 1 |
| TP2 | 1.618 | 2 |
| TP3 | 2.0 | 5 |
| TP4 | 2.236 | 6 |
| TP5 | 2.618 | 7 |
| STOPPED | SL | 3 |
| EXPIRED | timeout | 4 |
| none | none | 0 |

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

- `TP1_ONLY` means TP1 was reached and no higher target was reached before stop or resolution cutoff
- `TP2_HIT` implies TP1 was reached first on the same resolved path; TP3/TP4/TP5 were not reached
- `TP3_HIT` / `TP4_HIT` / `TP5_HIT` imply all lower targets were reached on the same path first
- State machine checks highest target first (TP5 → TP4 → TP3 → TP2 → TP1 → SL) to correctly record first-crossed exit level

## Derived Metrics

- `mae_pts` and `mfe_pts` are measured from the canonical entry reference to the worst and best realized excursion before resolution
