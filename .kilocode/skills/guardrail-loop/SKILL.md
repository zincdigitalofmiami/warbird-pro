---
name: guardrail-loop
description: >
  Continuous quality loop similar to Ralph Loop. Use when working on any multi-step task
  to maintain discipline, verify work at each step, and prevent drift. Invoke with
  /guardrail-loop before starting any significant implementation work.
---

# Guardrail Loop

A disciplined execution loop that ensures every step of work is verified before moving on.
Similar to Ralph Loop — high guardrails, high accuracy.

## Before Starting ANY Work

1. Read `AGENTS.md` at the repo root
2. Identify the active architecture plan
3. Confirm the task scope with the user — do NOT assume
4. List what files you expect to touch

## The Loop (repeat for each step)

### Step 1: Plan
- State what you are about to do in ONE sentence
- Confirm it aligns with the active plan and hard rules
- If unsure, STOP and ask the user

### Step 2: Execute
- Make the minimal change needed
- Do NOT touch code outside the current task
- Do NOT add dependencies without asking

### Step 3: Verify
- Run `npm run build` — it MUST pass
- Check that no mock/fake data was introduced
- Verify database queries use correct table prefixes
- Verify cron routes have `CRON_SECRET` validation and `job_log` logging
- If touching database: confirm migration file exists in `supabase/migrations/`

### Step 4: Report
- List every file changed
- State what was done and what was NOT done
- Flag any concerns or decisions that need user input

### Step 5: Checkpoint
- Ask the user: "Ready for the next step?"
- Do NOT proceed without confirmation

## Red Flags — STOP Immediately If:

- You are about to create mock data
- You are about to refactor code outside the task
- You are about to add a dependency
- You are about to delete a file
- You are about to run `npx vercel --prod`
- You are about to use Prisma or any ORM
- The build is failing and you want to skip verification
- You are guessing instead of checking the codebase

## Exit Condition

The loop ends when:
- All planned steps are complete
- `npm run build` passes
- The user confirms the work is done
- Every file change has been reported
