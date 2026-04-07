# Feature Catalog Contract

**Status:** Active

## Purpose

Defines which features are packet-eligible and which are local-only research features.

## Tier 1: Packet-Eligible Features

Tier 1 features must be:

- computable from Pine or canonical runtime state
- point-in-time valid at bar close
- stable enough to publish in a packet

Allowed Tier 1 families:

- fib geometry and anchor state
- pivot state and pivot distance
- target-viability state
- exhaustion and event-response state
- TA core pack states
- intermarket state from the admitted basket
- ES execution-quality states
- regime score
- agreement velocity
- impulse quality
- session or schedule context that is available at decision time

## Tier 2: Local-Only Research Features

Tier 2 features may exist only in local PostgreSQL and local artifacts.

Allowed Tier 2 families:

- wide macro joins
- experimental feature expansions
- research-only derived statistics
- raw SHAP matrices
- fold diagnostics
- training-only regime experiments
- post-trade explanatory features

## Point-In-Time Rule

Every feature must declare:

- source surface
- event timestamp
- bar-close alignment rule
- whether it is Tier 1 or Tier 2

If a feature cannot be proven point-in-time valid, it is not admitted.
