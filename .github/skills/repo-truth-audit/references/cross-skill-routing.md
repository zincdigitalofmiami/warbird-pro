# Cross-Skill Routing

Use this map to decide which audit skills must be loaded together.

## Mandatory Routing

- Docs, plan, or status files may be wrong:
  Load `repo-truth-audit`
- Tables, migrations, RLS, pg_cron, Edge Functions, views, grants, secrets, or writer ownership are part of the question:
  Load `supabase-database-audit`
- Datasets, features, labels, targets, leakage risk, or model validity are part of the question:
  Load `point-in-time-ml-audit`

## Combined Cases

- Production data pipeline feeding live models or offline training:
  Load all three skills
- Empty or stale model-support tables:
  Load `supabase-database-audit` and `point-in-time-ml-audit`, then reconcile with `repo-truth-audit`
- Rogue-agent cleanup or architecture reset on a data surface:
  Start with `repo-truth-audit`, then branch into the specialist skills

## Evidence Hierarchy

1. live runtime or database metadata
2. current code and migration files
3. current generated artifacts or logs
4. markdown docs and status files

If a weaker source conflicts with a stronger source, call that out explicitly.

## Fail-Closed Rules

- If the user asked for local and cloud evidence, both must be addressed or the missing side must be marked `INCOMPLETE`.
- If model validity depends on source freshness or publish lag and that cannot be proven, do not certify point-in-time correctness.
- If architecture claims rely only on markdown, the report is incomplete.
