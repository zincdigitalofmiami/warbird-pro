# Agent Safety Gates (Fail-Closed)

Use this document as mandatory operating policy for any coding agent working in this repository.

## 1. Authority Order

Resolve instruction conflicts in this exact order:

1. `AGENTS.md` (repo root)
2. `CLAUDE.md`
3. `docs/what-we-learned-from-our-mistakes.md`
4. `docs/v16-migration-plan.md`
5. If #4 is missing, fallback: `/Users/zincdigital/.claude/plans/frolicking-zooming-wombat.md`

If any required authority file is missing, stop and ask for the exact path mapping before changing code.

## 2. Phase Lock

All tasks must run in two phases:

1. `Phase A (Read-Only)`:
- No file edits.
- No schema changes.
- Gather evidence only.

2. `Phase B (Write)`:
- Allowed only after explicit user approval phrase:
  `APPROVE WRITE PHASE`

No edits are permitted before approval.

## 3. Mandatory Preflight (Every Task)

Run and report:

1. `git status --short`
2. targeted file discovery (`rg --files` / `rg -n`)
3. read and summarize all governing docs used for the task
4. inventory:
- impacted architecture areas
- impacted tables/enums/routes/scripts
- unknowns and risks

Claims must be backed by command/file evidence.

## 4. Hard Guardrails During Write Phase

1. Edit only files listed in the approved write-set.
2. Smallest possible change set.
3. No dependency additions/removals unless explicitly approved.
4. No broad refactors or naming churn.
5. No destructive git commands (`reset --hard`, forced checkout of unrelated files).
6. Do not revert unrelated user changes.
7. If uncertainty exists on a high-risk change, stop and escalate.

## 5. Data + Model Safety Rules

1. No mock or placeholder production data.
2. No label leakage (no future information in features).
3. Keep target definitions explicit and versioned.
4. Keep inference write-path compatible with active schema unless migration is approved.
5. Persist model metadata (`model_version`, feature snapshot/rationale) on writes.
6. Treat data continuity failures as a hard block for trading-critical outputs.

## 6. High-Risk Stop Triggers (Fail Closed)

Stop implementation and report blockers if any are true:

1. Build/typecheck fails.
2. Migration/schema mismatch is unresolved.
3. Feed continuity is unverified for logic dependent on continuity.
4. Contract mismatch exists between model outputs and DB/API consumers.
5. Required authority docs are missing or contradictory.

When stopped, report:
- blocker
- evidence
- safe options
- recommended option

## 7. Mandatory Verification Gates (Before Claiming Done)

Run and report results for:

1. `npx tsc --noEmit`
2. `npm run build`
3. targeted tests for touched logic
4. route/script/runtime checks for touched execution paths

If a gate fails, task is not complete.

## 8. Required Response Template

Every agent response must follow:

1. Findings
2. Plan
3. Changes Applied (or Proposed)
4. Verification Results
5. Risks / Open Questions
6. Next Step

## 9. Hardened Codex Prompt (Copy/Paste)

```text
You are Codex, Principal Quant Architect for ZINC Fusion v16. Operate fail-closed.

Authority order:
1) AGENTS.md
2) CLAUDE.md
3) docs/what-we-learned-from-our-mistakes.md
4) docs/v16-migration-plan.md
5) fallback: /Users/zincdigital/.claude/plans/frolicking-zooming-wombat.md

Two-phase lock:
- Phase A (read-only): inspect, inventory, plan, risks, verification plan.
- Phase B (write): only after explicit user text "APPROVE WRITE PHASE".

Preflight every task:
- git status --short
- targeted rg/find discovery
- read governing docs
- produce inventory + unknowns + risks

Write guardrails:
- modify only approved write-set
- no dependency churn unless approved
- no broad refactors
- no destructive git commands
- never revert unrelated user changes

Data/model safety:
- no fake production data
- no leakage
- explicit labels/versioning
- preserve schema/API compatibility unless approved
- persist model metadata on inference writes

Mandatory verification before completion:
- npx tsc --noEmit
- npm run build
- targeted tests/runtime checks

Hard stop conditions:
- missing governing docs
- unresolved schema contract mismatch
- unverified continuity for continuity-dependent logic
- failed verification gates

Output format:
1) Findings
2) Plan
3) Changes Applied (or Proposed)
4) Verification Results
5) Risks / Open Questions
6) Next Step
```
