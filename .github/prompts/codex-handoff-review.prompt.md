---
name: "Codex Handoff Review"
description: "Review current repo state and produce a strict Codex handoff prompt with exact findings, blockers, proofs, and next actions. Use when preparing implementation handoffs after review or audit work."
argument-hint: "task, surface, or review target"
agent: "agent"
---

Produce a self-contained Codex handoff prompt for the current repo state.

Requirements:

- Load [repo-truth-audit](../skills/repo-truth-audit/SKILL.md) before drafting the handoff.
- If the surface touches Supabase, migrations, RLS, cron, Edge Functions, tables, views, or secrets, also load [supabase-database-audit](../skills/supabase-database-audit/SKILL.md).
- If the surface touches datasets, features, training, labels, targets, leakage risk, or financial model validity, also load [point-in-time-ml-audit](../skills/point-in-time-ml-audit/SKILL.md).
- Use [cross-skill-routing](../skills/repo-truth-audit/references/cross-skill-routing.md) to decide which evidence layers are mandatory.
- Read the relevant repo truth first instead of trusting docs blindly.
- Identify what Codex last did, what the review found, and the exact next actions.
- Name exact files, commands, branches, refs, blockers, and proofs required.
- Prefer runtime truth over status markdown when they disagree.
- If the repo may be architecturally off track, say so directly and frame the handoff around correcting the real contract.
- If ML or market-data validity is in scope, require point-in-time checks, leakage checks, and futures-data contract validation.
- If any requested evidence is missing, state it explicitly and make evidence collection part of the Codex task instead of pretending the review is complete.
- Do not write vague instructions such as fix this, clean this up, or take a look.

Return one copyable Markdown block with these sections in order:

1. Execution location
2. Read-first files
3. Hard rules
4. What Codex last did
5. What the review found
6. Exact requested actions
7. Verification requirements
8. Strict return format

The prompt must be concrete enough that Codex can execute without guessing.
