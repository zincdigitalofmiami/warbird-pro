---
name: supabase-database-audit
description: "Audit Supabase schema, migrations, RLS, pg_cron, Edge Functions, writers, and repo-to-live drift in Warbird. Use for schema audits, migration drift reviews, empty-table investigations, cron ownership checks, route-to-table wiring, and push-readiness when Supabase state is involved."
argument-hint: "audit target, scope, or suspected issue"
user-invocable: true
---

# Supabase Database Audit

Use this skill to produce an evidence-backed audit of the Warbird Supabase surface. Default output is a full audit report covering both repo-local and cloud-live evidence when live access is available.

Load [supabase-reference-guide](./references/supabase-reference-guide.md) at the start of every substantive audit.

If the task also involves contract drift, rogue-agent cleanup, or uncertainty about what the repo actually does, load [repo-truth-audit](../repo-truth-audit/SKILL.md).

If the task also affects training datasets, feature freshness, target definitions, or financial-model validity, load [point-in-time-ml-audit](../point-in-time-ml-audit/SKILL.md).

## When to Use

- Audit the Supabase database
- Check schema drift or migration drift
- Explain why tables are empty or stale
- Verify what writes to a table or view
- Review RLS, grants, pg_cron, or Edge Function ownership
- Decide whether a migration or cutover is safe to push

## Governing Context

1. Read these files first:

- `AGENTS.md`
- `CLAUDE.md`
- `docs/plans/2026-03-20-ag-teaches-pine-architecture.md`
- `WARBIRD_MODEL_SPEC.md` when the contract is in question
- `docs/agent-safety-gates.md`

2. Treat these repo truths as defaults unless newer repo evidence disproves them:

- Supabase is the sole recurring schedule producer.
- Recurring ingestion should flow `pg_cron -> pg_net -> Supabase Edge Functions -> Supabase DB`.
- No Prisma or ORM paths are allowed.
- No mock data is allowed.
- The remote migration ledger may drift from the repo; do not assume `supabase db push` is safe without evidence.

3. Treat markdown docs and status files as claims, not ground truth.

- Cross-check docs against migrations, route code, shared libraries, live metadata, live row counts, and job ownership.
- If docs conflict with code or live state, report `doc-drift` and prefer the strongest runtime evidence.
- Assume prior agents may have gone off contract; actively test whether the intended architecture was actually implemented.

4. Apply point-in-time market-data and ML discipline during the audit.

- Prefer outcome-state framing over naive price forecasting unless the current contract explicitly says otherwise.
- Check timestamp alignment, timezone alignment, contract roll handling, label leakage risk, feature freshness, and point-in-time reproducibility.
- Treat MES as the active repo contract while also checking whether the data design remains sound for S&P 500 futures forecasting and classification workflows more broadly.

## Cross-Skill Routing

- Use `repo-truth-audit` first when the user is asking what is actually live, what is canonical, whether docs drifted, or whether prior agents built the wrong thing.
- Use `point-in-time-ml-audit` whenever the Supabase surface feeds datasets, features, targets, labels, packets, materialized views, or live model inputs.
- Run all three skills together when the question spans runtime ownership plus data-contract validity.
- Do not return a neat single-surface answer if the real problem crosses these boundaries.

## Choose Audit Mode

Default to `full-audit` unless the user clearly requests a narrower mode.

1. `full-audit`

- Combine repo audit, live schema audit, drift audit, and pipeline starvation audit.
- This is the default for production questions, schema confusion, or architecture uncertainty.

2. `repo-audit`

- Use when live DB access is unavailable or the task is about planned changes.
- Inspect migrations, Edge Functions, route handlers, shared libs, and docs.

3. `live-schema-audit`

- Use when database access is available.
- Inspect actual tables, columns, policies, indexes, jobs, row counts, and freshness.

4. `drift-audit`

- Compare repo migrations and code expectations against live DB truth.
- Focus on ledger gaps, direct-live changes, and stale docs.

5. `pipeline-starvation-audit`

- Use when tables exist but are empty or stale.
- Verify writers, schedules, secrets, and gate conditions before blaming schema.

6. `push-readiness-audit`

- Use before migrations, cron cutovers, or production rollout.
- Confirm drift status, runtime ownership, and rollback surface.

If the request is ambiguous, run `full-audit` and narrow only when access or evidence is constrained.

## Workflow

1. `Preflight`

- If edits are in scope, run `git status --short`.
- Inventory touched surfaces under `supabase/`, `app/api/cron/`, `lib/supabase/`, and related docs.
- Search the repo for the target table, function, cron name, route, or policy.
- Determine what can be checked locally versus in live Supabase and explicitly record any access limits.
- Record whether the user asked for local-only, cloud-only, or both. If both were requested, both sections are mandatory.

2. `Contract lock`

- Confirm the canonical architecture and naming from `AGENTS.md` and `CLAUDE.md`.
- Decide whether the target is canonical, legacy, zombie, or backup-only.
- Do not stop at the docs. Cross-check the claimed contract against current migrations, actual writers, and live runtime ownership.

3. `Architecture skepticism pass`

- Ask whether the system may be built wrong, not just broken.
- Test whether the current Supabase schema and job topology support the actual product contract, point-in-time truth, and deploy model.
- Flag structural mismatches such as forecast-era tables lingering under an outcome-state contract, dashboard recomputation of canonical state, missing canonical packet tables, or schedules still owned outside Supabase.

4. `Writer map`

- For each target table or view, identify:
- active writer
- active readers
- schedule owner
- secret dependencies
- whether the path is live, retired, missing, or backup-only

5. `Schema audit`

- Verify table existence, primary and unique keys, foreign keys, indexes, RLS, grants, and timestamp contract.
- For live audits, inspect actual metadata and row counts.
- Verify that keys and timestamps support point-in-time reconstruction for futures data.
- Verify that retained historical windows, active symbol filters, and contract-roll assumptions align with the intended MES or S&P futures workflow.
- Load the RLS, scheduling, and migration sections from [supabase-reference-guide](./references/supabase-reference-guide.md) before calling schema or policy work complete.

6. `Runtime audit`

- Verify Edge Function presence, pg_cron ownership, secret dependencies, and invocation path.
- If App Router cron routes are still in scope, verify `CRON_SECRET` handling and `maxDuration = 60`.
- Treat missing schedules or missing secrets as pipeline failures, not missing schema.

7. `Drift audit`

- Compare live schema, repo migrations, and route code.
- Flag direct-live changes, migration-ledger gaps, and stale docs separately.
- Do not recommend `supabase db push` when live drift is unresolved.

8. `ML and market-data audit`

- Check whether the schema and writers preserve point-in-time training truth.
- Flag future-data contamination, post-close joins masquerading as same-bar features, non-canonical target definitions, stale support tables, and any design that would make S&P futures model evaluation misleading.
- Check whether the system is mixing decision-policy state, realized outcomes, and predicted-price surfaces in a way that weakens model validity.

9. `Findings and decision`

- Report findings ordered by severity.
- Separate confirmed facts from assumptions.
- End with the narrowest safe next action.

## Fail-Closed Rules

- Never claim a cloud-live verdict without live evidence.
- If the user asked for both local and cloud but live inspection is unavailable, mark the cloud section `INCOMPLETE` and name the missing proof.
- Never recommend `supabase db push` unless migration-history trust has been explicitly checked.
- Never certify RLS as safe just because policies exist; verify enablement, role scope, view behavior, and bypass surfaces.
- Never stop at schema correctness if the real failure is writer starvation, schedule ownership, or stale secrets.

## Classification Rules

- `schema-missing`: a required table, view, function, policy, or index is absent.
- `pipeline-starved`: schema exists and writer code exists, but schedule, secret, or invocation is missing.
- `zombie`: a table or code path exists with no active writer and no approved contract role.
- `legacy-backup`: retained only as backup or migration residue and not a live dependency.
- `doc-drift`: plan or status docs disagree with code or DB truth.
- `unsafe-push`: repo migrations cannot be trusted to apply cleanly to live because of ledger drift or direct-live changes.
- `architecture-misaligned`: the implemented schema or runtime shape does not actually support the intended contract or operating model.
- `ml-contract-risk`: the data design breaks point-in-time ML discipline, leaks future information, or encodes weak target logic for futures prediction or classification.

## Evidence Checklist

Collect only the evidence needed for the current mode:

- target tables and row counts
- migration files that define or mutate the surface
- active writers and readers
- cron jobs and invocation path
- RLS, policies, and grants
- required secrets or env prerequisites
- proof for any claimed drift
- proof for any claimed architecture mismatch
- proof for any point-in-time ML or market-data risk
- explicit blocker for anything that could not be verified

## Live Query Targets

When live DB access is available, prefer targeted inspection of:

- `information_schema` tables and columns
- `pg_catalog` indexes and constraints
- `pg_policies` and grants
- `cron.job` and related pg_cron metadata
- materialized views and refresh paths
- row counts and freshness windows for the target tables

## Warbird-Specific Guardrails

- Default the canonical contract to the MES 15m fib setup keyed by the `America/Chicago` bar close.
- Treat Pine as the canonical signal surface and the dashboard as the mirrored operator surface.
- Supabase pg_cron is the sole recurring schedule producer.
- If code still depends on Vercel cron routes or local-only runtime for production writes, flag it.
- Empty `warbird_*` tables do not prove missing schema; verify `detect-setups` and `score-trades` ownership and scheduling first.
- If repo docs already state that live drift exists, assume push-readiness is blocked until disproven.
- Do not assume the markdown architecture is correct just because it is recent; verify that migrations, writers, and live DB surfaces actually implement it.
- Favor point-in-time snapshots, bar-close keys, and outcome-state labels over reconstructed or repaint-prone truths.
- For futures workflows, flag any design that ignores session boundaries, contract roll realities, active-symbol filtering, or the distinction between decision time and outcome realization time.

## Completion Standard

A good audit ends with:

1. severity-ranked findings
2. a local-vs-cloud evidence split
3. affected tables, routes, functions, and jobs
4. evidence used
5. open questions
6. exact next actions
7. a clear status: `GO`, `NO-GO`, or `INCOMPLETE`

## Output Shape

- Executive summary
- Scope and access limits
- Local repo audit
- Cloud-live audit
- Drift analysis
- ML and market-data validity check
- Findings
- Open questions
- Recommended next action
- If implementation is requested next, leave audit mode and follow the repo verification contract for code changes

## Resources

- Load [supabase-reference-guide](./references/supabase-reference-guide.md) for official Supabase guidance on RLS, scheduled functions, and migration discipline.
- Load [cross-skill-routing](../repo-truth-audit/references/cross-skill-routing.md) when the audit spans architecture truth, Supabase runtime, and ML validity.
