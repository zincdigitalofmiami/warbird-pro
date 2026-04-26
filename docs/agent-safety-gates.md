# Warbird Agent Safety Gates

Use this document as the Warbird-specific fail-closed operating contract for Claude Code, Codex, and any subagent working in this repository.

This document exists for one reason: agents in this repo must not self-certify. Completion requires repo evidence.

## 1. Authority Order

Resolve instruction conflicts in this exact order:

1. `AGENTS.md`
2. `docs/INDEX.md`
3. `docs/MASTER_PLAN.md`
4. `docs/contracts/README.md`
5. `docs/contracts/pine_indicator_ag_contract.md`
6. `docs/cloud_scope.md`
7. `WARBIRD_MODEL_SPEC.md`
8. `CLAUDE.md`
9. `docs/agent-safety-gates.md`

If a task touches one specific phase or checkpoint, reread that exact active-plan section before editing.

## 2. Model Policy

Default Claude Code model policy for this repo:

1. Use `opusplan` for normal repo work.
2. Use raw `opus` only for planning, architecture, or review.
3. Use `sonnet` for bounded execution-only tasks when plan ambiguity is already closed.

`Opus` is allowed to reason. It is not allowed to self-attest completion without proof.

## 3. Execution Phases

Every substantive task must run in this order:

1. `Preflight`
2. `Write`
3. `Verification`
4. `Closure`

### Preflight

Before editing:

1. Run `git status --short`
2. Discover the touched surface with `rg --files` / `rg -n`
3. Read the governing docs for the touched surface
4. Inventory:
   - impacted code paths
   - impacted tables / routes / scripts / indicators
   - verification gates
   - blockers / unknowns

### Write

During edits:

1. Touch the smallest viable write-set.
2. Do not refactor unrelated areas.
3. Do not revert unrelated user changes.
4. Do not add dependencies unless explicitly approved.
5. Treat any contract ambiguity as a stop trigger.

### Verification

Verification is part of the task, not an optional follow-up.

If a required gate is not run, the task is `INCOMPLETE`.

### Closure

The final response must use the completion schema in Section 7. Any other format is non-compliant for implementation work.

## 4. Pine-Specific Tool Routing

When the task touches Pine indicators, strategies, harnesses, or TradingView mechanics:

1. Prefer the Pine helpers that are confirmed available in the current environment:
   - `pine-patterns` skill
   - `tradingview-indicator-contract-audit` skill when contract/audit work is needed
   - `./scripts/guards/pine-lint.sh`
   - `./scripts/guards/check-contamination.sh`
   - `./scripts/guards/check-indicator-strategy-parity.sh` when both the indicator and strategy are in scope
2. Treat `pinescript-server`, TradingView CLI, or chart-capable MCP flows as optional only after confirming they are actually configured in the active Codex profile.
3. Do not treat tool presence, slash-command names, or plan references as proof that a Pine / TradingView tool is really installed.
4. Repo guard scripts remain the hard completion gates, and Deep Backtesting or live-chart validation remain manual unless a real chart-capable tool is installed and verified.

## 5. Hard Guardrails

These rules are fail-closed:

1. No mock, demo, placeholder, or fake production data.
2. No label leakage or future-data contamination.
3. No Prisma or ORM paths.
4. No inactive Databento symbols.
5. No broad naming churn.
6. No silent schema/API contract changes.
7. No destructive git commands.
8. No "done" claim when any required verification is missing.

## 6. Verification Matrix

Run the required gates for the files you actually touched.

### Pine / Indicator / Strategy Work

If any touched file ends in `.pine`:

1. `./scripts/guards/pine-lint.sh <each touched .pine file>`
2. `./scripts/guards/check-contamination.sh`
3. `npm run build`

If either of these files is touched:

- `indicators/v7-warbird-institutional.pine`
- `indicators/v7-warbird-strategy.pine`

Also run:

4. `./scripts/guards/check-indicator-strategy-parity.sh`

### Next.js / API / Shared TS Work

If any touched file is under `app/`, `components/`, `lib/`, or changes runtime config:

1. `npm run build`

Add route/runtime checks for the touched path when the task changes actual execution flow.

### Supabase / Cron / Ingestion Work

If any touched file is under `supabase/`, `app/api/cron/`, or ingestion libraries:

1. `npm run build`
2. Run the narrowest path-specific runtime or script validation available

Runtime ingestion work must not be described as training work unless the active
Pine indicator-only contract is explicitly updated.

### Docs-Only Work

If only docs changed, no build gate is required unless the docs describe a newly claimed operational truth that should have been validated.

## 7. Required Completion Schema

For implementation work, the final response must contain these exact headings:

```text
STATUS: COMPLETE | INCOMPLETE
TOUCHED FILES:
- path

VERIFICATION:
- PASS: command
- FAIL: command
- NOT RUN: command — reason

BLOCKERS:
- none
```

Rules:

1. `STATUS: COMPLETE` is allowed only if all required gates passed.
2. `STATUS: COMPLETE` cannot include any `FAIL:` or `NOT RUN:` items.
3. `STATUS: INCOMPLETE` is mandatory if any gate failed, was skipped, or was impossible to run.
4. `TOUCHED FILES` must list the actual edited files, or `- none`.
5. `BLOCKERS` must be `- none` only when status is complete.

## 8. High-Risk Stop Triggers

Stop and report blockers if any are true:

1. Required authority docs conflict.
2. A schema/API/model contract mismatch is unresolved.
3. A Pine task lacks required guard passes.
4. Runtime validation is required but unavailable.
5. The assistant cannot prove that the claimed file edits exist.
6. The assistant cannot prove that verification commands actually passed.

When blocked, report:

1. the blocker
2. the evidence
3. the safest next options
4. the recommended next option

## 9. Warbird Verifier Intent

The repo-local Claude hooks should enforce this contract:

1. Block `Stop` when the completion schema is missing or false.
2. Block `TaskCompleted` when a teammate tries to close work without proof.
3. Default the project to `opusplan`.
4. Keep Pine helper commands advisory and repo verification mandatory.

## 10. Local Claude Wiring

The current local Claude Code implementation in this workspace is:

1. `.claude/settings.json` (gitignored local project settings)
   - sets `model` to `opusplan`
   - adds `Stop` and `TaskCompleted` verifiers
2. `.claude/rules/warbird-opus-execution-contract.md` (gitignored local rule)
   - keeps the completion schema and Pine command routing in active context
3. `scripts/claude/verify-warbird-stop.sh`
   - deterministic stop gate for completion schema, file existence, Pine guards, parity, and build checks
