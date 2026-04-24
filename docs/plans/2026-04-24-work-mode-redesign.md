# Battle Plan: /work Mode Redesign
**Date:** 2026-04-24
**Status:** IN PROGRESS
**Branch:** main
**Author:** Kirk Musick + Claude Sonnet 4.6

---

## Context & Motivation

The existing `/work` scaffold has the right architecture but broken enforcement. The Stop
auditor silently no-ops because `$ARGUMENTS` is not substituted in `type=agent` hook prompts.
Lint emits nothing on a clean pass so the auditor cannot distinguish "passed" from "never ran."
Memory saves never happen automatically. The 32 rules are advisory text — a distracted model
ignores them. Kirk spends 2–5× time fixing mistakes that mechanical enforcement would have
prevented.

The redesign goal: when `/work` is active, failproof work is the only mode available.
Token cost is a feature. Heavy reasoning, slow and methodical execution, high-frequency
checkpoints, and self-improvement are the design targets.

---

## Design Decisions Locked

1. **Plan docs live in `docs/plans/` in the repo** — not temp files, committed to main
2. **Work off main, not branches**
3. **"Hell no" = strong advisory pushback** with evidence, not a mechanical block. Claude
   acts as a senior engineer who will tell you to your face when you're about to make a
   mistake, then defers to Kirk's final call.
4. **Checkpoints are post-task, Claude-driven, high-frequency** — after every completed
   todo, not at phase or milestone boundaries
5. **Specialist tools only** — no generic lint substitution. The correct tool for the
   work surface is named in the plan before execution and enforced at checkpoint
6. **Suggestions are dual-purpose** — task-level improvements AND workflow gaps spotted
   during the session
7. **Self-improvement is proposed, never auto-applied** — Claude writes draft hooks/rules,
   Kirk approves, Claude applies the specific change described

---

## Architecture: Three Layers

```
SKILL LAYER   → tells Claude what to do and in what mindset
HOOK LAYER    → mechanically enforces it regardless of Claude's state
STATE LAYER   → tracks everything across turns, survives restarts
```

---

## The Five Phases

### Phase 0: Pre-flight
Nothing starts until this clears. Runs the moment `/work` is typed.

```
1. Read ALL memory (MEMORY.md + every linked file)
2. MCP health check — every connected server pinged
3. Tool verification — every shell tool the task might need: command -v
4. Git state — uncommitted changes, ahead/behind, migration drift
5. Lint baseline — run now, record pass/fail in state
6. DB connectivity — pg_isready, warbird PG17 reachable
7. Dumpster fire scan — failing guards, known broken state, stale locks

Output: RED / YELLOW / GREEN
RED  = hard block. Named items must be fixed before /work proceeds.
YELLOW = proceed with named risks surfaced and acknowledged.
GREEN = proceed.
```

### Phase 1: Discovery
Claude runs two tracks simultaneously before asking for plan approval.

**Track A — Ask the user (one at a time until scope is clear):**
- What specific outcome must exist when this is done?
- What are the hard constraints? (locked files, performance, deadline)
- What would make this a failure?
- Push back if the approach is wrong — state the conflict, name the evidence, offer
  the better path with tradeoffs. Wait for resolution before proceeding.

**Track B — Autonomous repo research:**
- `git log --oneline -30` — recent work context
- `git log --all --grep="<topic>"` — prior work on this exact area
- Grep for related symbols, functions, tables in scope
- Read CLAUDE.md locked rules relevant to the area being touched
- Scan `docs/plans/` for prior plans on this topic
- Read all relevant feedback memory files
- Dumpster fire assessment: what broken state exists that could interfere?

**Pushback triggers:**
- Task touches a CLAUDE.md locked rule → name the rule, name the conflict, stop
- Task duplicates recent work → point to the commit or prior plan
- Approach will break something verifiably working → show the evidence
- Better path exists → propose it with tradeoffs, not just "consider X"

### Phase 2: Battle Plan
Written to `docs/plans/YYYY-MM-DD-<task-slug>.md` and committed to main
**before a single line of execution code is touched.**

See Battle Plan Template section below.

### Phase 3: Execute
One task at a time. Heavy reasoning written to state file before touching anything.
After each task: checkpoint fires automatically via `post-checkpoint-trigger.sh`.

**Checkpoint sequence (runs after every completed todo):**
1. Name the specialist tool for this task (from plan doc entry)
2. Run it — full output captured
3. Write findings to memory
4. Scan for error patterns — new pattern → new `feedback_*.md` immediately
5. Surface suggestions: task-level AND workflow-level
6. Update Progress table in plan doc
7. Clear `pending_checkpoint` flag → next task unlocks

### Phase 4: /done
```
1. Verify every todo: completed or explicitly rationalized
2. Run full specialist tool suite for all touched surfaces
3. Compare to Phase 0 baseline
4. Update plan doc status → COMPLETE or PARTIAL with reason
5. Write session memory summary
6. Consolidate all error patterns detected this session
7. Write workflow improvement suggestions to plan doc
8. Commit updated plan doc
9. Deactivate work mode
10. Print final report (see /done section)
```

---

## Specialist Tool Registry

Every checkpoint must run the correct tool for the work surface.
Generic fallbacks are treated as checkpoint failures.

| Work Surface | Specialist Tools (in order) |
|-------------|----------------------------|
| `*.pine` (live indicator) | `pine-lint.sh` → `pine-facade` TV compiler → `check-contamination.sh` |
| `*.pine` (strategy/backtest) | `pine-lint.sh` → `pine-facade` TV compiler → `check-indicator-strategy-parity.sh` → TV strategy compile |
| `supabase/functions/*.ts` | Supabase CLI function check → edge function health endpoint |
| `local_warehouse/migrations/*.sql` | `psql` dry-run → migration ledger reconciliation |
| `supabase/migrations/*.sql` | `supabase db push --dry-run` → remote migration status |
| `scripts/ag/*.py` | `ruff` → `python3 -m py_compile` → AG dry-run if trainer touched |
| `*.ts / *.tsx` | `npm run lint` → `npm run build` |
| `*.sh` | `shellcheck` |
| `scripts/guards/*.sh` | `shellcheck` → dry-run against known-good input |
| Local warehouse + Python pipeline | `pg_isready` → row count sanity query → affected table schema check |

**Rules:**
1. The battle plan names the specialist tool per task before execution starts
2. If the correct specialist tool is unavailable at pre-flight, that task is blocked
3. TV backtesting compile is never substituted with `pine-facade` — they test different things
4. Lint confirmation emits "PASS" explicitly on success — silent output = not run

---

## Battle Plan Template

```markdown
# Battle Plan: <task name>
**Date:** YYYY-MM-DD
**Status:** IN PROGRESS
**Branch:** main

## Discovery Findings
What repo research surfaced. Prior work. Dumpster fire items found.

## Pushback & Resolution
What was challenged, why, and how it was resolved.
If no pushback: "None — approach validated."

## Out-of-Box Suggestions
Alternatives considered. Adjacent improvements surfaced.
Not assigned as tasks — offered for Kirk's awareness.

## Known Pitfalls
Patterns from feedback memory relevant to this work.
Error patterns that have burned us before on this surface.

## Rollback Plan
How to undo this if it goes wrong. Specific commands or steps.

## Milestones

### Milestone 1: <name>

#### Task 1.1: <name>
- Expected outcome: (concrete and verifiable)
- Files touched: (list every file)
- Checkpoint tools (in order):
    1. <tool> — <what it catches>
    2. <tool> — <what it catches>
- NOT sufficient: (list tools that would be wrong here)
- Risk: LOW / MEDIUM / HIGH
- Known pitfall: (specific risk for this task)

#### Task 1.2: ...

## Progress (updated at every checkpoint)
| Task | Status | Checkpoint Result | Suggestions | Notes |
|------|--------|------------------|-------------|-------|
| 1.1  | ✅     | pine-lint: 0 err  | none        |       |
| 1.2  | 🔄     | pending           |             |       |
```

---

## The 32-Hook Inventory

### SessionStart (3 hooks)

| Hook | Status | What It Does |
|------|--------|-------------|
| `session-start.sh` | EXISTS — extend | Work mode state injection + dumpster fire report |
| `session-mcp-health.sh` | NEW | Ping every MCP, report dead ones before model uses them |
| `session-dumpster-fire.sh` | NEW | `git status`, lint state, migration drift, RED/YELLOW/GREEN |

### UserPromptSubmit (3 hooks)

| Hook | Status | What It Does |
|------|--------|-------------|
| `prompt-submit.sh` | EXISTS — extend | Activation/deactivation, preamble injection |
| `prompt-preflight-scan.sh` | NEW | Reads prompt keywords, primes tool inventory for Phase 0 |
| `prompt-danger-scan.sh` | NEW | Detects locked files, cloud DDL, dangerous ops in prompt — injects warning |

### PreToolUse (14 hooks)

| Hook | Matcher | Status | What It Does |
|------|---------|--------|-------------|
| `pre-edit-gate.sh` | `Edit\|Write` | EXISTS — extend | TodoWrite gate + checkpoint flag check |
| `guard-memory-overwrite.sh` | `Write` | EXISTS | Block overwrite of existing memory files |
| `pre-checkpoint-gate.sh` | `Edit\|Write\|Bash` | NEW | Deny if `pending_checkpoint=true` — "run validation first" |
| `pre-plan-deviation.sh` | `Edit\|Write` | NEW | File not in plan scope → deny + require rationale |
| `pre-locked-file.sh` | `Edit\|Write` | NEW | Cross-reference CLAUDE.md locked rules against target file |
| `pre-bash-danger.sh` | `Bash` | NEW | Block `rm -rf`, `git reset --hard`, `git push --force`, `DROP TABLE`, `truncate` |
| `pre-migration-guard.sh` | `Edit\|Write` | NEW | Any migration path requires explicit plan entry |
| `pre-todo-integrity.sh` | `TodoWrite` | NEW | Mid-session unplanned todo additions require one-line rationale |
| `pre-memory-read-check.sh` | `Edit\|Write` | NEW | First Edit/Write: verify MEMORY.md was read this session |
| `pre-reasoning-gate.sh` | `Agent` | NEW | Agent spawns must declare type and purpose in plan |
| `pre-pine-approval.sh` | `Edit\|Write` | EXISTS (project) | Any `*.pine` file requires session approval |
| `pre-tv-slot-guard.sh` | `mcp__tradingview__pine_*` | EXISTS (project) | TV slot overwrite guard |
| `pre-bash-allowlist.sh` | `Bash` | NEW | Commands not on allowlist get soft warn |
| `pre-agent-reasoning.sh` | `Agent` | NEW | Spawning rationale must be in transcript |

### PostToolUse (10 hooks)

| Hook | Matcher | Status | What It Does |
|------|---------|--------|-------------|
| `post-edit-lint.sh` | `Edit\|Write` | EXISTS — fix | Specialist lint + explicit PASS on success |
| `post-todowrite.sh` | `TodoWrite` | EXISTS — extend | State tracking + set `pending_checkpoint=true` on completion |
| `post-checkpoint-trigger.sh` | `TodoWrite` | NEW | When todo → completed: write checkpoint entry, emit validation demand |
| `post-bash-error-scan.sh` | `Bash` | NEW | Scan stdout/stderr for known error signatures |
| `post-pine-budget.sh` | `Edit\|Write` | NEW | After any `.pine` edit: run budget counter, surface headroom |
| `post-error-pattern.sh` | `Edit\|Write` | NEW | Compare changes against known error patterns in feedback memory |
| `post-memory-enforcer.sh` | `TodoWrite` | NEW | On completion: check last 3 tool calls for memory write — warn if missing |
| `post-contamination.sh` | `Edit\|Write` | NEW (global) | `check-contamination.sh` after any `.pine` edit |
| `post-bash-exit.sh` | `Bash` | NEW | Non-zero exit → systemMessage with exit code + last 20 lines |
| `post-specialist-suggest.sh` | `Edit\|Write` | NEW | "You edited `.py` — have you run ruff? You edited `supabase/functions/` — edge function health?" |

### Stop (3 hooks)

| Hook | Status | What It Does |
|------|--------|-------------|
| `stop-auditor.sh` | REWRITE | Fixed transcript access — verifies all 7 rules with real evidence |
| `stop-memory-audit.sh` | NEW | Scans turn for decisions not saved to memory — blocks with list |
| `stop-error-pattern-writer.sh` | NEW | New patterns detected → writes `feedback_*.md` → appends MEMORY.md |

---

## Self-Improvement Mechanism

### Three Error Pattern Types

**Type 1 — Known pattern recurring:**
`post-error-pattern.sh` detects a pattern already in feedback memory.
Action: systemMessage warning + increment `pattern_count` in state.
If `pattern_count >= 2`: propose escalation to Kirk.

**Type 2 — New pattern detected:**
`stop-error-pattern-writer.sh` fires at turn end.
Writes new `feedback_<topic>_<date>.md` + appends MEMORY.md pointer.
Starts at advisory level.

**Type 3 — Workflow gap spotted:**
Claude needed a tool/rule/hook that doesn't exist.
Written to plan doc `## Workflow Improvements` section.
Kirk decides whether to implement.

### Escalation Ladder

```
Session 1: New pattern → feedback memory entry (advisory)
Session 2: Pattern recurs → PreToolUse soft warn via systemMessage
Session 3: Pattern recurs again → draft hook written, proposed to Kirk
Kirk approves → Claude applies the specific change described. Nothing else.
```

### Hard Lines (Never Without Approval)

- `~/.claude/settings.json` (hook config)
- `~/.claude/skills/**` (skill files)
- `CLAUDE.md` or `AGENTS.md`
- Any escalated pattern applied to live hooks

---

## State File Extensions

The per-cwd state file gains new fields:

```json
{
  "pending_checkpoint": false,
  "last_checkpoint_at": null,
  "checkpoint_count": 0,
  "last_completed_todo": null,
  "memory_read_this_session": false,
  "preflight_result": null,
  "plan_doc_path": null,
  "plan_scope_files": [],
  "pattern_counts": {},
  "reasoning_log": [],
  "specialist_tools_verified": []
}
```

---

## /done Final Report Format

```
Work mode DEACTIVATED for <cwd>.
  Tasks:              7/7 completed
  Checkpoints:        7 passed, 0 failed
  Specialist tools:   pine-lint ✅  pine-facade ✅  parity-check ✅
  Lint vs baseline:   PASS (baseline: PASS)
  New error patterns: 2 written to memory
  Workflow gaps:      1 suggestion (see plan doc §Workflow Improvements)
  Memory:             session_20260424_163022.md written
  Plan:               docs/plans/2026-04-24-<task>.md → COMPLETE, committed
Deactivate with /done.
```

---

## Known Holes Being Fixed

| Hole | Fix |
|------|-----|
| Stop auditor $ARGUMENTS not substituted | Rewrite as `type=command` script that reads stdin and calls agent with real payload |
| Lint silent on success | Emit explicit "PASS" systemMessage when exit code 0 |
| Memory saves never happen automatically | `post-memory-enforcer.sh` + `stop-memory-audit.sh` |
| `pre-edit-gate.sh` only checks `todowrite_invoked` | Extend to check `todos_in_progress > 0` |
| No checkpoint enforcement | `post-checkpoint-trigger.sh` + `pre-checkpoint-gate.sh` |
| No plan deviation detection | `pre-plan-deviation.sh` |
| `edits_since_last_lint` inflates for unlinted types | Scope counter to lintable file types only |

---

## Implementation Sequence

1. Fix state schema (`workflow-state.sh`) — add new fields
2. Fix Stop auditor — rewrite as command+script architecture
3. Fix `post-edit-lint.sh` — emit PASS explicitly
4. Fix `pre-edit-gate.sh` — strengthen to `todos_in_progress > 0`
5. Build 3 new SessionStart hooks
6. Build 2 new UserPromptSubmit hooks
7. Build 10 new PreToolUse hooks
8. Build 8 new PostToolUse hooks
9. Build 2 new Stop hooks
10. Rewrite `work/SKILL.md` — full 5-phase flow
11. Rewrite `done/SKILL.md` — align with new checkpoint system
12. Update `workflow-preamble.txt` — reflect new rules
13. Smoke test the full flow end-to-end

## Progress
| Task | Status | Checkpoint Result | Notes |
|------|--------|------------------|-------|
| Design doc written | ✅ | — | This file |
| Implementation plan | 🔄 | pending | writing-plans next |
