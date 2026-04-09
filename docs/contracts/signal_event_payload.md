# Signal Event Payload Contract

**Status:** Active
**Updated:** 2026-04-08 — separated Pine candidate transport from AG decision fields

## Purpose

Defines the alert payload emitted by Pine (Tier 1 candidate transport) and the decision fields assigned by AG scoring (Tier 2 operator signal).

## Tier 1 — Pine Candidate Payload

This is the structured candidate event emitted by Pine at bar close. It feeds the ingress pipeline only.

### Required Version Fields

- `schema_version`
- `indicator_version`

### Required Identity Fields

- `symbol`
- `timeframe`
- `bar_close_ts_utc`
- `candidate_idempotency_key`

`bar_close_ts_utc` is the ingress timestamp authority. The canonical warehouse derives the MES 15m `America/Chicago` key from this field during canonical write.

### Required Setup Snapshot Fields

- `direction`
- `setup_archetype`
- `fib_anchor_high_ts_utc`
- `fib_anchor_low_ts_utc`
- `fib_anchor_high_price`
- `fib_anchor_low_price`
- `fib_level_touched`
- `target_viable_20pt`

### Required Stop Surface Fields

- `stop_family_id`
- `stop_level_price`
- `stop_distance_ticks`

### Optional Audit Fields

- `payload_hash`
- `tv_alert_id`
- `source_chart_id`

## Tier 2 — AG Decision Fields (Server-Side Only)

These fields are assigned after AG scores the candidate against the active packet. They are NOT emitted by Pine.

- `gate_decision` — one of `TAKE_TRADE`, `WAIT`, `PASS`
- `gate_reason_bucket` — one of `REGIME_BLOCK`, `CONFLUENCE_TOO_LOW`, `VOLATILITY_BLOCK`, `SESSION_TIME_BLOCK`, `STRUCTURE_INVALID`
- `tp1_probability` — calibrated from active packet
- `tp2_probability` — calibrated from active packet
- `reversal_probability` — calibrated from active packet
- `packet_id` — FK to the scoring packet
- `scored_at` — timestamp of AG scoring

## Payload Rules

- UTC only in transport timestamps
- deterministic serialization for idempotency hashing
- confirmed-bar emission only
- no repaint-prone or post-outcome fields
- unknown fields must be rejected or explicitly version-gated
- Pine must NOT emit `gate_decision`, `gate_reason_bucket`, or calibrated probabilities — those come from AG
