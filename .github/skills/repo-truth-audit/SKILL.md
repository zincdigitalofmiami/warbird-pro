---
name: repo-truth-audit
description: "Audit whether the repo, docs, runtime paths, and live systems match each other. Use for repo truth checks, architecture skepticism, rogue-agent cleanup, doc-vs-code drift, runtime ownership checks, and deciding what the project actually does right now."
argument-hint: "surface, contract, or suspected drift"
user-invocable: true
---

# Repo Truth Audit

Use this skill when the main risk is not a single bug but that the repo may have drifted away from its stated architecture. Treat docs, comments, plans, and status files as claims that must be verified.

Load [cross-skill-routing](./references/cross-skill-routing.md) at the start of every non-trivial audit.

Use [supabase-database-audit](../supabase-database-audit/SKILL.md) when tables, migrations, RLS, pg_cron, Edge Functions, secrets, or writers are part of the truth question.

Use [point-in-time-ml-audit](../point-in-time-ml-audit/SKILL.md) when datasets, labels, targets, leakage risk, or financial-model validity are part of the truth question.

## When to Use

- The repo feels off track
- Multiple agents have touched the same surface
- Docs say one thing and runtime behavior suggests another
- You need to know the real source of truth before editing
- You need an evidence-backed answer to what is canonical, legacy, zombie, or broken

## Defaults

- Prefer runtime and code evidence over markdown claims
- Assume recent docs can still be wrong
- Assume partial migrations, abandoned cutovers, and stale status updates are possible
- Separate intended architecture from implemented architecture
- Require at least two independent evidence sources for any strong architectural claim when possible

## Workflow

1. Read the governing repo files first:

- `AGENTS.md`
- `CLAUDE.md`
- the active plan named in `AGENTS.md`
- `WARBIRD_MODEL_SPEC.md` when the contract is involved
- `docs/agent-safety-gates.md`

2. Define the audit question in one sentence:

- what surface is being audited
- what claim is being tested
- what evidence would falsify the claim

3. Build a truth table for the target surface:

- docs claim
- migration or schema truth
- route or function truth
- shared library truth
- live runtime truth if available
- current owner or writer

4. Route into specialist skills where needed:

- Supabase/runtime ownership questions: load `supabase-database-audit`
- dataset/ML validity questions: load `point-in-time-ml-audit`
- merged operational-data-contract questions: run all relevant skills and reconcile findings

5. Run an architecture skepticism pass:

- ask whether the current design is merely broken or fundamentally misbuilt
- look for duplicated engines, dead cutovers, backup tables being treated as live, or legacy vocabulary surviving under a new contract

6. Classify each artifact:

- canonical
- active but non-canonical
- legacy
- zombie
- backup-only
- doc-drift

7. Produce findings ordered by severity, then state the narrowest safe next action.

## Guardrails

- Do not assume the newest markdown file is correct
- Do not treat a successful build as proof that the runtime architecture is sound
- Do not recommend broad refactors just because drift exists
- When evidence conflicts, say so directly and rank the stronger source
- Do not produce a half-baked architecture verdict from docs alone when runtime or schema evidence is still missing
- If a requested evidence layer is unavailable, mark it as a blocker instead of smoothing it over

## Output Shape

- Executive summary
- Truth table
- Architecture mismatches
- Severity-ranked findings
- Open questions
- Recommended next action

## Resources

- Load [cross-skill-routing](./references/cross-skill-routing.md) for evidence hierarchy and skill orchestration.
