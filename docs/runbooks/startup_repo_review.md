# Startup Repo Review

**Date:** 2026-04-29
**Status:** Required Startup / Start-of-Day Initialization

Use this runbook at the start of every fresh chat, start of day, context reset,
or resumed session where current repo state is unknown.

This pass is read-only. Its purpose is to establish current repo truth before
planning, implementation, Pine work, tuning, training, or deployment.

## Scope

- Use `/Volumes/Satechi Hub/warbird-pro/` as the source of truth.
- Do not modify, create, delete, format, stage, commit, push, install, build,
  test, train, or run artifact-producing scripts during this review.
- Do not touch TradingView or Pine Editor during this review.
- Do not trust stale summaries, old chat context, or remote GitHub state over
  the local clone.
- If the user asks for implementation after the review, transition to the
  normal task preflight and preserve any unrelated WIP.

## Required Reads

Read the authority stack first:

1. `AGENTS.md`
2. `docs/INDEX.md`
3. `docs/MASTER_PLAN.md`
4. `docs/contracts/README.md`
5. `docs/contracts/pine_indicator_ag_contract.md`
6. `docs/runbooks/README.md`
7. `docs/runbooks/startup_repo_review.md`
8. `docs/cloud_scope.md`
9. `WARBIRD_MODEL_SPEC.md`
10. `CLAUDE.md`
11. `docs/agent-safety-gates.md`
12. `MEMORY.md` and any referenced durable memory relevant to the active task

## Required Git Inventory

Run read-only inspection commands:

```bash
git status --short --branch
git stash list
git branch -vv --all
git worktree list
git remote -v
```

Capture:

- current branch and upstream
- divergence from the upstream/default branch
- staged, unstaged, and untracked files
- stashes and their apparent purpose
- active worktrees and branches that may contain relevant WIP

## Recent History Review

Inspect at least the last 20 to 30 commits, and go farther if the recent theme
is incomplete or spans more history.

```bash
git log -30 --date=iso-strict --pretty=format:'%h%x09%ad%x09%an%x09%s'
git log -30 --name-status --oneline
```

For high-signal commits, inspect the actual diffs:

```bash
git show --stat --find-renames <commit>
git show --name-status --find-renames <commit>
git show --find-renames <commit> -- <path>
```

Capture:

- commit messages, authors, and dates
- changed surfaces by commit
- repeated themes and apparent current direction
- commits that changed Pine, contracts, tuning scripts, guardrails, memory, or
  active runbooks

## Working Tree Diff Review

Inspect current WIP without changing it:

```bash
git diff --stat
git diff --cached --stat
git diff --name-status
git diff --cached --name-status
```

For untracked files, read enough content to understand purpose and risk.

Capture:

- whether changes appear user-authored, generated, or agent WIP
- whether changes conflict with the current active plan
- whether any dirty files affect the requested task

## Project Structure Review

Use `rg --files` and targeted reads to map current structure:

```bash
rg --files
rg -n "TODO|FIXME|INCOMPLETE|superseded|legacy|deprecated|locked|guardrail" AGENTS.md CLAUDE.md README.md docs WARBIRD_MODEL_SPEC.md indicators scripts
```

At minimum, understand:

- Pine surfaces under `indicators/`
- active tuning and automation scripts under `scripts/optuna/` and `scripts/ag/`
- contract and runbook authority under `docs/`
- runtime/dashboard support under `app/`, `components/`, `lib/`, and `supabase/`
- memory pointers in `MEMORY.md`

## Required Report

Return a concise startup report with these sections:

```text
STARTUP REVIEW: READ-ONLY

PROJECT / ARCHITECTURE:
- what the project is
- current active plan
- primary code and data/modeling surfaces

RECENT DIRECTION:
- recent commit themes
- apparent active work
- notable shifts in architecture or guardrails

WORKING TREE:
- branch/upstream/divergence
- staged/unstaged/untracked files
- stashes and worktrees

NOTABLE ISSUES / INCONSISTENCIES:
- stale docs, contract drift, TODOs, in-flight mismatches, or blockers

STABLE VS. IN-FLUX:
- stable surfaces
- actively changing surfaces

REVIEW LIMITS:
- commands intentionally not run
- files or systems not inspected
```

The report must explicitly state that the review was read-only and that no
builds, tests, training, installs, staging, commits, or file edits were run.

## Transition After Review

If the user asks for implementation after the startup review:

1. Run normal preflight for the requested touched surface.
2. Preserve unrelated WIP.
3. Read the surface-specific docs before edits.
4. Apply the relevant verification gates from `docs/agent-safety-gates.md`.
5. Update active Markdown and memory when the task changes operational truth.
