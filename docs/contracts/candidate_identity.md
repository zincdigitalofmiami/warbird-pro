# Candidate Identity Contract

**Status:** Active

## Purpose

Defines what makes a candidate the same candidate and how replays are handled.

## Same-Candidate Rule

Two payloads represent the same candidate only when all of the following match:

- `symbol`
- `timeframe`
- `bar_close_ts_utc`
- `direction`
- `setup_archetype`
- `fib_anchor_high_ts_utc`
- `fib_anchor_low_ts_utc`
- `fib_anchor_high_price`
- `fib_anchor_low_price`
- `indicator_version`

## Idempotency Key Rule

`candidate_idempotency_key` must be a deterministic hash of the same-candidate fields above plus the normalized `stop_family_id`.

## Replay Handling

- exact replay with the same payload is a no-op
- exact replay with missing audit metadata may update audit-only columns
- conflicting replay with the same `candidate_idempotency_key` must not overwrite canonical warehouse truth silently
- conflicting replay must be logged as an ingress conflict for reconciliation

## Revision Rule

Canonical candidate rows are immutable after first acceptance.

If Pine emits a materially different payload for the same candidate key:

- do not overwrite the accepted canonical row
- record the later payload in audit or conflict storage
- require an explicit contract or writer change before allowing mutation semantics

This keeps training truth stable and replay-safe.
