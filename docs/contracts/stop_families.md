# Stop Families Contract

**Status:** Active
**Updated:** 2026-04-08 — migrated to formula-specific IDs

## Purpose

Defines the bounded stop-family set that Pine and AutoGluon may reference.

## Rules

- stop selection must come from a bounded family set
- stop math must be deterministic
- stop prices must round to the instrument tick size
- expanding the family set requires a contract version bump
- each family ID must bind to a deterministic formula so AG can compare specific stop placements

## Family Set

| Family ID | Formula (longs) | Formula (shorts) |
|-----------|----------------|-----------------|
| `FIB_NEG_0236` | `SLow - 0.236 × Range - 1 tick` | `SHigh + 0.236 × Range + 1 tick` |
| `FIB_NEG_0382` | `SLow - 0.382 × Range - 1 tick` | `SHigh + 0.382 × Range + 1 tick` |
| `ATR_1_0` | `EntryPrice - 1.0 × ATR` | `EntryPrice + 1.0 × ATR` |
| `ATR_1_5` | `EntryPrice - 1.5 × ATR` | `EntryPrice + 1.5 × ATR` |
| `ATR_STRUCTURE_1_25` | `max(SLow - 1tick, Entry - 1.25×ATR)` | `min(SHigh + 1tick, Entry + 1.25×ATR)` |
| `FIB_0236_ATR_COMPRESS_0_50` | `max(SLow - 0.5×ATR, FibExt) - 1tick` | `min(SHigh + 0.5×ATR, FibExt) + 1tick` |

Where:
- `SLow` / `SHigh` = the fib engine swing low / swing high anchor
- `Range` = `SHigh - SLow`
- `FibExt` = the negative 0.236 fib extension (`SLow - 0.236 × Range` for longs)
- `ATR` = ATR(14) at bar close
- `EntryPrice` = canonical fill price from the execution model

## Storage Rule

The warehouse must store:

- `stop_family_id`
- `stop_level_price`
- `stop_distance_ticks`

Model outputs may rank or recommend stop families, but they may not emit arbitrary floating stop prices outside this family set.

## Training Rule

Both fib-based and ATR-based families are trained in parallel. AG learns which wins per regime, direction, and volatility context. SHAP reports the result. No family is pre-favored.
