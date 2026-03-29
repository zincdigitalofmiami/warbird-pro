---
name: point-in-time-ml-audit
description: "Audit ML and data pipelines for point-in-time correctness, leakage, target design, timestamp alignment, and futures-market validity. Use for forecasting or classification audits, feature freshness checks, label leakage reviews, and financial time-series model contract validation."
argument-hint: "dataset, feature pipeline, target, or model contract"
user-invocable: true
---

# Point-In-Time ML Audit

Use this skill to test whether a financial ML pipeline is valid at decision time, not just convenient in hindsight. Treat point-in-time reproducibility as a hard requirement.

Load [quant-pit-reference-guide](./references/quant-pit-reference-guide.md) at the start of every substantive audit.

If the data path depends on Supabase tables, materialized views, cron refreshes, Edge Functions, or secret-gated ingestion, load [supabase-database-audit](../supabase-database-audit/SKILL.md).

If the repo docs and implementation disagree about the model contract, load [repo-truth-audit](../repo-truth-audit/SKILL.md).

## When to Use

- Review forecasting or classification pipelines for financial assets
- Check whether a dataset leaks future information
- Validate target definitions and outcome windows
- Review timestamp joins, news joins, or macro joins
- Test whether a futures pipeline is credible for live deployment

## Core Principles

- Decision time and outcome time must be distinct
- Every feature must be available at or before the decision timestamp
- Every label must be defined only from data after the decision timestamp
- Reproducibility must hold for the exact bar-close contract and timezone in use
- If the pipeline mixes policy decisions, realized outcomes, and predicted-price surfaces, flag it
- Any feature or weight derived from wall-clock runtime rather than the historical decision timestamp is suspect until proven intentional

## Audit Workflow

1. Lock the contract:

- instrument or symbol universe
- timeframe
- timezone
- decision timestamp key
- label definition
- live deployment surface

2. Inventory the pipeline:

- raw data sources
- ingestion jobs
- feature builders
- joins and aggregation windows
- training dataset builders
- live inference inputs

3. Run point-in-time checks:

- timestamp alignment
- timezone normalization
- publish lag or vendor lag
- feature freshness at decision time
- forward-fill behavior
- contract roll or symbol-activity filtering
- wall-clock dependencies such as `Date.now()`, `now()`, run-date weighting, or unversioned external state

4. Run leakage checks:

- post-close feature joins
- future-bar highs or lows inside current-bar labels
- materialized views or derived tables refreshed after the decision time but treated as contemporaneous
- hindsight filters that would not exist live
- scalers, imputers, encoders, or normalizers fit on full-history data instead of training-only or as-of subsets

5. Run futures-market checks:

- active contract handling
- session boundaries and overnight behavior
- continuous-contract assumptions
- roll logic consistency
- realistic target framing for S&P 500 futures or MES workflows

6. Run evaluation-discipline checks:

- temporal split before fitting transformations
- walk-forward or rolling-origin validation when appropriate
- reproducible randomness policy
- train/live feature parity

7. Rate the contract:

- sound
- risky but usable with caveats
- invalid for live ML

## What to Flag

- label leakage
- feature leakage
- stale support tables
- ambiguous target definitions
- non-reproducible joins
- mismatched training versus live inputs
- predicted-price outputs where outcome-state policy would be more valid
- wall-clock-dependent sample weights or features
- cross-validation or randomness settings that make results non-comparable or non-reproducible

## Fail-Closed Rules

- If publication lag, timestamp semantics, or live feature availability cannot be proven, do not certify point-in-time validity.
- If a user asks for a live-ready verdict and the audit only proves offline convenience, rate the contract `INCOMPLETE` or `invalid for live ML`.
- If the data path includes Supabase-managed sources and writer freshness is unknown, defer to `supabase-database-audit` before closing the report.

## Output Shape

- Executive summary
- Contract snapshot
- Point-in-time checks
- Leakage findings
- Futures-market validity findings
- Severity-ranked issues
- Recommended next action

## Resources

- Load [quant-pit-reference-guide](./references/quant-pit-reference-guide.md) for scikit-learn leakage guidance, reproducibility guidance, and public point-in-time time-series feature-engineering patterns.
- Load [cross-skill-routing](../repo-truth-audit/references/cross-skill-routing.md) when the ML audit depends on architecture or Supabase runtime truth.
