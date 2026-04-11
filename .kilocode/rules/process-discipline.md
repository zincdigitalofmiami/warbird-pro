# Process Discipline

## Task Execution

- ONE task at a time. Complete fully before starting the next.
- NEVER refactor, rename, or "improve" code outside the current task.
- NEVER add or remove dependencies without asking the user first.
- NEVER delete or overwrite files without confirming first.
- NEVER guess — check the codebase, then ask the user.
- Less complexity, fewer moving parts, better naming.

## Verification Before Claims

- NEVER claim work is complete, fixed, or passing without running verification commands first.
- NEVER agree with user's premise without verifying data first.
- NEVER fabricate explanations. Check the DB / codebase.
- Run `npm run build` and confirm it passes before claiming success.
- After every task: list every file changed and what you did.

## Planning & Context

- Read AGENTS.md at repo root before any project work.
- Check the active architecture plan before making architectural decisions.
- `docs/MASTER_PLAN.md` (Warbird Full Reset Plan v5) is the only planning authority.
- Ground decisions in actual repo code/migrations/routes, not docs. Audit first, decide second.
- Save decisions, plans, and progress to plan files continuously. Never let context loss destroy work.

## Code Quality

- Do not over-engineer. Only make changes that are directly requested or clearly necessary.
- Do not add features, refactor code, or make "improvements" beyond what was asked.
- Do not add error handling for scenarios that can't happen.
- Do not create helpers or abstractions for one-time operations.
- Avoid backwards-compatibility hacks.

## Communication

- NEVER start editing/fixing code without explicit user approval.
- Frustration or sarcasm is NOT permission to act.
- Always confirm before touching anything when the scope is unclear.
