# Stop Families Contract

**Status:** Active

## Purpose

Defines the bounded stop-family set that Pine and AutoGluon may reference.

## Rules

- stop selection must come from a bounded family set
- stop math must be deterministic
- stop prices must round to the instrument tick size
- expanding the family set requires a contract version bump

## Initial Family Set

- `fib_neg_0236`
  - stop at the negative `0.236` fib extension from the active setup range
- `fib_neg_0382`
  - stop at the negative `0.382` fib extension from the active setup range
- `atr_1_0`
  - stop at `1.0 x ATR` from the entry reference defined by the setup archetype
- `atr_1_5`
  - stop at `1.5 x ATR` from the entry reference defined by the setup archetype

## Storage Rule

The warehouse must store:

- `stop_family_id`
- `stop_level_price`
- `stop_distance_ticks`

Model outputs may rank or recommend stop families, but they may not emit arbitrary floating stop prices outside this family set.
