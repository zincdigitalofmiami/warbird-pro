---
name: warbird-phase-execution
description: >
  Execute Warbird work against the current authority stack. Use when Kilo must absorb
  plan changes, execute one active phase at a time, or align Pine, data, runtime,
  and contract work to the current MES 15m setup-first architecture.
---

# Warbird Phase Execution

Use this skill when work must align to the active Warbird plan instead of stale project memory.

## Required Reads

1. `AGENTS.md`
2. `docs/INDEX.md`
3. `CLAUDE.md`
4. `docs/MASTER_PLAN.md`
5. `docs/contracts/README.md`
6. `docs/cloud_scope.md`
7. `WARBIRD_MODEL_SPEC.md`
8. The live files for the touched subsystem

## Lock These Truths First

- The canonical object is the MES 15m fib setup at confirmed bar close.
- The canonical key is the MES 15m bar-close timestamp in `America/Chicago`.
- The setup snapshot includes entry-state truth, including entry spot semantics.
- `indicators/v7-warbird-institutional.pine` is the live structural candidate-generator surface.
- `indicators/v7-warbird-strategy.pine` mirrors that trigger path for backtesting.
- Tier 1 is Pine candidate transport only.
- Tier 2 is server-side AG scoring and operator-visible signal logic.
- The external-drive local PostgreSQL warehouse is canonical truth; cloud Supabase is the serving subset only.

## Work Modes

### 1. Plan Delta

Use when the user says the plan changed or corrects execution order.

- Extract the exact delta
- Recompute what phase is actually active
- Update execution order before touching ordinary implementation

### 2. Phase Kickoff

Use when starting or resuming a phase.

- Inventory the touched files, tables, routes, scripts, and indicators
- Separate canonical-local truth from cloud-serving truth
- Identify blockers before editing

### 3. Phase Execution

Use once scope is clear.

- Make a bounded change set
- Run the real gates for that surface
- Update active docs only if contract or operational truth changed
- End with the next blocking item

## Execution Workflow

1. Run `git status --short`
2. Scope the surface with `rg --files` and `rg -n`
3. Read the governing docs for the touched phase
4. Inventory the write-set and required verification gates
5. Execute only the active phase scope
6. Verify with repo gates
7. Report what changed, what was validated, and what blocks next

## Guardrails

- Do not reduce Warbird to TP1 or TP2 label language only. Entry-state fidelity is mandatory.
- Do not blur Tier 1 Pine transport with Tier 2 AG decisions.
- Do not collapse local canonical truth and cloud runtime subsets into one database story.
- Do not reintroduce stale v6 assumptions into v7 Pine work.
- Do not create new architecture docs unless explicitly asked. Update the active docs instead.
