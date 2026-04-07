# Signal Event Payload Contract

**Status:** Active

## Purpose

Defines the alert payload emitted by Pine and accepted by cloud ingress.

## Required Version Fields

- `schema_version`
- `indicator_version`

## Required Identity Fields

- `symbol`
- `timeframe`
- `bar_close_ts_utc`
- `candidate_idempotency_key`

`bar_close_ts_utc` is the ingress timestamp authority. The canonical warehouse derives the MES 15m `America/Chicago` key from this field during canonical write.

## Required Setup Snapshot Fields

- `direction`
- `setup_archetype`
- `fib_anchor_high_ts_utc`
- `fib_anchor_low_ts_utc`
- `fib_anchor_high_price`
- `fib_anchor_low_price`
- `fib_level_touched`
- `pivot_state`
- `pivot_distance_ticks`
- `target_viable_20pt`
- `regime_class`
- `regime_confidence`

## Required Decision Surface Fields

- `gate_decision`
- `gate_reason_bucket`

Allowed `gate_decision` values:

- `PASS`
- `WAIT`
- `TAKE_TRADE`

## Required Stop Surface Fields

- `stop_family_id`
- `stop_level_price`
- `stop_distance_ticks`

## Optional Audit Fields

- `payload_hash`
- `tv_alert_id`
- `source_chart_id`

## Payload Rules

- UTC only in transport timestamps
- deterministic serialization for idempotency hashing
- confirmed-bar emission only
- no repaint-prone or post-outcome fields
- unknown fields must be rejected or explicitly version-gated
