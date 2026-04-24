# /work Mode Redesign — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace the advisory-only /work scaffold with a 32-hook, mechanically-enforced, failproof working agent that checkpoints after every task, self-improves via error pattern detection, and never lets the model self-certify.

**Architecture:** Global harness (`~/.claude/`) — skills + hooks + state. Three layers: SKILL (mindset), HOOK (mechanical enforcement), STATE (persistence). Specialist tool registry per file surface. Checkpoints gate every task transition mechanically via state flag.

**Tech Stack:** bash, jq, shasum, Claude Code hook events (SessionStart / UserPromptSubmit / PreToolUse / PostToolUse / Stop), per-cwd JSON state files.

**Design doc:** `docs/plans/2026-04-24-work-mode-redesign.md` (commit 626c27d)

---

## Pre-implementation: Read These Files First

Before touching anything, read every existing hook to avoid clobbering:

```bash
cat ~/.claude/hooks/workflow-state.sh
cat ~/.claude/hooks/session-start.sh
cat ~/.claude/hooks/prompt-submit.sh
cat ~/.claude/hooks/pre-edit-gate.sh
cat ~/.claude/hooks/post-edit-lint.sh
cat ~/.claude/hooks/post-todowrite.sh
cat ~/.claude/settings.json
cat ~/.claude/skills/work/SKILL.md
cat ~/.claude/skills/done/SKILL.md
cat ~/.claude/hooks/workflow-preamble.txt
```

All paths below are absolute. `~` = `/Users/zincdigital`.

---

## Task 1: Extend State Schema

**Files:**
- Modify: `~/.claude/hooks/workflow-state.sh`

**Step 1: Read the current state_init function (lines 24–44)**

```bash
grep -n "state_init\|pending_checkpoint\|memory_read" ~/.claude/hooks/workflow-state.sh
```

Expected: no matches for the new fields — confirms they don't exist yet.

**Step 2: Add new fields to state_init**

In `state_init()`, extend the `jq -n` object to include the new fields after `required_tools_verified: []`:

```bash
    pending_checkpoint: false,
    last_checkpoint_at: null,
    checkpoint_count: 0,
    last_completed_todo: null,
    memory_read_this_session: false,
    preflight_result: null,
    plan_doc_path: null,
    plan_scope_files: [],
    pattern_counts: {},
    reasoning_log: [],
    specialist_tools_verified: []
```

**Step 3: Verify**

```bash
bash -n ~/.claude/hooks/workflow-state.sh && echo "syntax OK"
```

Expected: `syntax OK`

**Step 4: Test state_init creates correct schema**

```bash
source ~/.claude/hooks/workflow-state.sh
sf=$(state_path /tmp/test-work-state)
rm -f "$sf"
state_init "$sf" /tmp/test-work-state
jq '{pending_checkpoint, memory_read_this_session, checkpoint_count}' "$sf"
```

Expected:
```json
{
  "pending_checkpoint": false,
  "memory_read_this_session": false,
  "checkpoint_count": 0
}
```

**Step 5: Commit**

```bash
git -C ~/.claude add hooks/workflow-state.sh 2>/dev/null || true
# Note: ~/.claude may not be a git repo — if not, skip git steps for hook files.
# warbird-pro plan doc tracks the change.
echo "state schema extended"
```

---

## Task 2: Fix the Stop Auditor (Critical)

**Problem:** Current Stop hook is `type=agent` with `$PWD` and `$ARGUMENTS` as literal strings in JSON — the harness does not substitute shell variables into agent prompts. The auditor computes sha12 from the string `"$PWD"`, finds no state file, returns `{"ok": true}`, and every turn passes unchecked.

**Fix:** Convert to `type=command` + bash script that reads stdin (real payload), does mechanical checks from the state file, and emits block/proceed based on hard rules. Qualitative checks (self-certification) are handled pre-emptively by `pre-checkpoint-gate.sh` instead.

**Files:**
- Create: `~/.claude/hooks/stop-auditor.sh`
- Modify: `~/.claude/settings.json` — Stop hook entry

**Step 1: Write `stop-auditor.sh`**

```bash
#!/usr/bin/env bash
# Stop hook: mechanical audit of work-mode contract.
# Reads hook payload from stdin. Checks state file for violations.
# Returns {"decision":"block","reason":"..."} or exits 0 (proceed).
set -euo pipefail
source "$HOME/.claude/hooks/workflow-state.sh"

input="$(cat || true)"

sf="$(state_path "$PWD")"
[[ -f "$sf" ]] || exit 0

active="$(state_get "$sf" '.work_mode_active')"
[[ "$active" == "true" ]] || exit 0

violations=()

# Rule 1: TodoWrite must have been invoked
todowrite="$(state_get "$sf" '.todowrite_invoked')"
if [[ "$todowrite" != "true" ]]; then
  violations+=("Rule 1: TodoWrite was never invoked this turn. Call TodoWrite with a concrete plan before any Edit/Write.")
fi

# Rule 2: pending_checkpoint must be false (all checkpoints cleared)
pending="$(state_get "$sf" '.pending_checkpoint')"
last_todo="$(state_get "$sf" '.last_completed_todo')"
if [[ "$pending" == "true" ]]; then
  violations+=("Rule 6: Checkpoint pending for task \"$last_todo\" — checkpoint was never completed before turn ended.")
fi

# Rule 3: edits_since_last_lint should be 0 if any lintable file was touched
edits="$(state_get "$sf" '.edits_since_last_lint')"
if [[ "$edits" -gt 3 ]]; then
  violations+=("Rule 2: $edits edits since last lint run. Lint after each logical chunk — not just at the end.")
fi

# Rule 4: memory must have been read this session before any governed edit
memory_read="$(state_get "$sf" '.memory_read_this_session')"
if [[ "$memory_read" != "true" && "$todowrite" == "true" ]]; then
  violations+=("Rule 4: Memory was not confirmed read before work began. MEMORY.md must be read before touching governed surfaces.")
fi

if [[ "${#violations[@]}" -gt 0 ]]; then
  msg="$(printf '%s\n' "${violations[@]}")"
  jq -cn --arg reason "$msg" '{
    decision: "block",
    reason: $reason
  }'
  exit 0
fi

exit 0
```

**Step 2: Make executable**

```bash
chmod +x ~/.claude/hooks/stop-auditor.sh
```

**Step 3: Verify syntax**

```bash
bash -n ~/.claude/hooks/stop-auditor.sh && echo "syntax OK"
```

**Step 4: Update Stop hook in `~/.claude/settings.json`**

Replace the existing Stop hook entry. The new entry:

```json
"Stop": [
  {
    "hooks": [
      {
        "type": "command",
        "command": "bash ~/.claude/hooks/stop-auditor.sh",
        "timeout": 30
      }
    ]
  }
]
```

Remove the old `type=agent` Stop hook entirely. The `asyncRewake` / `rewakeMessage` fields only apply to `type=agent` — with `type=command`, a non-zero exit or `{"decision":"block"}` response triggers the block natively.

**Step 5: Test the auditor in isolation**

```bash
# Simulate a work-mode active state with a pending checkpoint
source ~/.claude/hooks/workflow-state.sh
sf=$(state_path "$PWD")
state_init "$sf" "$PWD"
state_set "$sf" '.work_mode_active = true | .todowrite_invoked = true | .pending_checkpoint = true | .last_completed_todo = "test task"'

# Run auditor with empty stdin
echo '{}' | bash ~/.claude/hooks/stop-auditor.sh
```

Expected: JSON with `decision: "block"` and rule 6 violation.

**Step 6: Commit marker**

```bash
echo "stop-auditor rewritten as type=command" >> /tmp/work-mode-progress.txt
```

---

## Task 3: Fix `post-edit-lint.sh` — Emit PASS Explicitly

**Problem:** Clean lint emits nothing. The auditor cannot distinguish "lint passed" from "lint never ran."

**Files:**
- Modify: `~/.claude/hooks/post-edit-lint.sh` (lines 59–66)

**Step 1: Read current emit block**

```bash
sed -n '59,66p' ~/.claude/hooks/post-edit-lint.sh
```

Expected: the `if [[ -n "$output" ]]` gate with no else branch.

**Step 2: Replace the emit block**

Find:
```bash
if [[ -n "$ran" ]]; then
  # Emit a systemMessage only if output is non-empty
  if [[ -n "$output" ]]; then
    jq -cn --arg r "$ran" --arg o "$output" '{
      systemMessage: ("Post-edit lint (" + $r + "):\n" + $o)
    }'
  fi
fi
```

Replace with:
```bash
if [[ -n "$ran" ]]; then
  if [[ -n "$output" ]]; then
    jq -cn --arg r "$ran" --arg o "$output" '{
      systemMessage: ("Post-edit lint (" + $r + "):\n" + $o)
    }'
  else
    jq -cn --arg r "$ran" '{
      systemMessage: ("Post-edit lint (" + $r + "): PASS — 0 errors, 0 warnings")
    }'
  fi
fi
```

**Step 3: Also scope `edits_since_last_lint` to lintable types only**

Currently the counter increments for ALL file types including `.sh`, `.md`, `.json`. Find the increment block (lines 24–28):

```bash
# Bump edit counter in state (if a state file exists for this cwd)
sf="$(state_path "$PWD")"
if [[ -f "$sf" ]]; then
  state_set "$sf" '.edits_since_last_lint += 1' || true
fi
```

Replace with:
```bash
sf="$(state_path "$PWD")"
# Only count edits to lintable file types
case "$path" in
  *.pine|*.py|*.ts|*.tsx|*.js|*.jsx|*.mjs|*.cjs|*.sql|*.sh)
    if [[ -f "$sf" ]]; then
      state_set "$sf" '.edits_since_last_lint += 1' || true
    fi
    ;;
esac
```

**Step 4: Verify**

```bash
bash -n ~/.claude/hooks/post-edit-lint.sh && echo "syntax OK"
```

**Step 5: Commit marker**

```bash
echo "post-edit-lint PASS confirmation added" >> /tmp/work-mode-progress.txt
```

---

## Task 4: Strengthen `pre-edit-gate.sh`

**Problem:** Gate checks `todowrite_invoked` (boolean) — satisfied by calling `TodoWrite([])`. Should require at least one `in_progress` todo.

**Files:**
- Modify: `~/.claude/hooks/pre-edit-gate.sh` (lines 22–33)

**Step 1: Read current check**

```bash
sed -n '22,33p' ~/.claude/hooks/pre-edit-gate.sh
```

**Step 2: Replace the check**

Find:
```bash
todowrite_done="$(state_get "$sf" '.todowrite_invoked')"

if [[ "$todowrite_done" != "true" ]]; then
```

Replace with:
```bash
todowrite_done="$(state_get "$sf" '.todowrite_invoked')"
todos_in_progress="$(state_get "$sf" '.todos_in_progress')"
todos_total="$(state_get "$sf" '.todo_count')"

if [[ "$todowrite_done" != "true" || ("$todos_total" -eq 0) ]]; then
```

Also update the deny message to include the stronger requirement:

```bash
permissionDecisionReason: "WORK-MODE GATE: No active todos. TodoWrite must be called with at least one concrete task before any Edit/Write. An empty list or a list with only completed todos does not satisfy this gate. If this is a trivial single-step edit, call TodoWrite with a one-item in_progress list acknowledging that. Run /done to exit work mode."
```

**Step 3: Verify**

```bash
bash -n ~/.claude/hooks/pre-edit-gate.sh && echo "syntax OK"
```

---

## Task 5: Build `pre-checkpoint-gate.sh`

The spine of the checkpoint system. Blocks all Edit/Write/Bash while `pending_checkpoint=true`.

**Files:**
- Create: `~/.claude/hooks/pre-checkpoint-gate.sh`

**Step 1: Write the hook**

```bash
#!/usr/bin/env bash
# PreToolUse: block Edit/Write/Bash if a checkpoint is pending.
# Set by post-checkpoint-trigger.sh when a todo → completed.
set -euo pipefail
source "$HOME/.claude/hooks/workflow-state.sh"

input="$(cat)"
tool="$(jq -r '.tool_name // ""' <<<"$input")"
[[ "$tool" == "Edit" || "$tool" == "Write" || "$tool" == "Bash" ]] || exit 0

sf="$(state_path "$PWD")"
[[ -f "$sf" ]] || exit 0

active="$(state_get "$sf" '.work_mode_active')"
[[ "$active" == "true" ]] || exit 0

pending="$(state_get "$sf" '.pending_checkpoint')"
[[ "$pending" == "true" ]] || exit 0

last_todo="$(state_get "$sf" '.last_completed_todo')"
count="$(state_get "$sf" '.checkpoint_count')"

jq -cn --arg todo "$last_todo" --arg n "$count" '{
  hookSpecificOutput: {
    hookEventName: "PreToolUse",
    permissionDecision: "deny",
    permissionDecisionReason: ("CHECKPOINT GATE (checkpoint #" + $n + "): Task \"" + $todo + "\" completed but checkpoint not cleared.\n\nRequired before next action:\n1. Name the specialist tool from your plan doc entry for this task\n2. Run it — full output in transcript\n3. Write findings to memory (Edit to session file)\n4. Scan for error patterns — write new feedback_*.md if new pattern found\n5. Surface suggestions: task-level + workflow-level\n6. Update Progress table in plan doc\n\nOnce specialist tool output is in transcript, call: state_set to clear pending_checkpoint=false")
  }
}' 
exit 0
```

**Step 2: Make executable and verify**

```bash
chmod +x ~/.claude/hooks/pre-checkpoint-gate.sh
bash -n ~/.claude/hooks/pre-checkpoint-gate.sh && echo "syntax OK"
```

**Step 3: Register in `~/.claude/settings.json`**

Add to the `PreToolUse` array, before `pre-edit-gate.sh` (checkpoint gate fires first):

```json
{
  "matcher": "Edit|Write|Bash",
  "hooks": [
    { "type": "command", "command": "bash ~/.claude/hooks/pre-checkpoint-gate.sh", "timeout": 5 }
  ]
}
```

---

## Task 6: Build `post-checkpoint-trigger.sh`

Sets `pending_checkpoint=true` when any todo moves to completed. Emits the checkpoint demand.

**Files:**
- Create: `~/.claude/hooks/post-checkpoint-trigger.sh`
- Modify: `~/.claude/settings.json` — add to PostToolUse

**Step 1: Write the hook**

```bash
#!/usr/bin/env bash
# PostToolUse on TodoWrite: detect todo → completed transition,
# set pending_checkpoint flag, emit checkpoint demand.
set -euo pipefail
source "$HOME/.claude/hooks/workflow-state.sh"

input="$(cat)"
tool="$(jq -r '.tool_name // ""' <<<"$input")"
[[ "$tool" == "TodoWrite" ]] || exit 0

sf="$(state_path "$PWD")"
[[ -f "$sf" ]] || exit 0

active="$(state_get "$sf" '.work_mode_active')"
[[ "$active" == "true" ]] || exit 0

# Count completed todos in THIS call
new_completed="$(jq '[(.tool_input.todos // [])[] | select(.status=="completed")] | length' <<<"$input")"
prev_completed="$(state_get "$sf" '.todos_completed')"

# Detect upward transition only
if [[ "$new_completed" -gt "$prev_completed" ]]; then
  last_todo="$(jq -r '[(.tool_input.todos // [])[] | select(.status=="completed")] | last | .content // "unknown task"' <<<"$input")"
  new_count="$(state_get "$sf" '.checkpoint_count')"
  new_count=$(( new_count + 1 ))

  state_set "$sf" "
    .pending_checkpoint = true
    | .last_completed_todo = \"$(echo "$last_todo" | sed 's/"/\\"/g')\"
    | .checkpoint_count = $new_count
    | .last_checkpoint_at = (now | todate)
  " || true

  jq -cn --arg todo "$last_todo" --arg n "$new_count" '{
    systemMessage: ("=== CHECKPOINT #" + $n + " REQUIRED ===\nTask just completed: \"" + $todo + "\"\n\nYou must now:\n1. Identify the specialist tool(s) from the plan doc entry for this task\n2. Run each tool — capture full output\n3. Write findings to session memory file\n4. Check for error patterns vs feedback memory\n5. Surface suggestions (task + workflow level)\n6. Update Progress table in plan doc\n7. Call TodoWrite or state update to clear pending_checkpoint\n\nNext Edit/Write/Bash is BLOCKED until checkpoint clears.")
  }'
fi

exit 0
```

**Step 2: Make executable and verify**

```bash
chmod +x ~/.claude/hooks/post-checkpoint-trigger.sh
bash -n ~/.claude/hooks/post-checkpoint-trigger.sh && echo "syntax OK"
```

**Step 3: Register in `~/.claude/settings.json`** under PostToolUse:

```json
{
  "matcher": "TodoWrite",
  "hooks": [
    { "type": "command", "command": "bash ~/.claude/hooks/post-checkpoint-trigger.sh", "timeout": 5 }
  ]
}
```

---

## Task 7: Build `pre-memory-read-check.sh`

Blocks the first Edit/Write of a session if MEMORY.md has not been read.

**Files:**
- Create: `~/.claude/hooks/pre-memory-read-check.sh`

**Step 1: Write the hook**

```bash
#!/usr/bin/env bash
# PreToolUse: on first Edit/Write of a work-mode session, verify
# that memory was read (memory_read_this_session=true in state).
set -euo pipefail
source "$HOME/.claude/hooks/workflow-state.sh"

input="$(cat)"
tool="$(jq -r '.tool_name // ""' <<<"$input")"
[[ "$tool" == "Edit" || "$tool" == "Write" ]] || exit 0

sf="$(state_path "$PWD")"
[[ -f "$sf" ]] || exit 0

active="$(state_get "$sf" '.work_mode_active')"
[[ "$active" == "true" ]] || exit 0

memory_read="$(state_get "$sf" '.memory_read_this_session')"
[[ "$memory_read" == "true" ]] && exit 0

# Check if this is the first edit (edits_since_last_lint == 0 and todo is in_progress)
todos_in_prog="$(state_get "$sf" '.todos_in_progress')"
[[ "$todos_in_prog" -gt 0 ]] || exit 0

jq -cn '{
  hookSpecificOutput: {
    hookEventName: "PreToolUse",
    permissionDecision: "deny",
    permissionDecisionReason: "MEMORY GATE: Work mode requires memory to be read before any edit. Read ~/.claude/projects/<sanitized-cwd>/memory/MEMORY.md and relevant feedback files first. Once read, update state: state_set <sf> \".memory_read_this_session = true\". This is Phase 0 of the /work contract."
  }
}'
exit 0
```

**Step 2: Make executable and verify**

```bash
chmod +x ~/.claude/hooks/pre-memory-read-check.sh
bash -n ~/.claude/hooks/pre-memory-read-check.sh && echo "syntax OK"
```

**Step 3: Register in `~/.claude/settings.json`**

Add to PreToolUse `Edit|Write` matcher hooks array.

---

## Task 8: Build `pre-bash-danger.sh`

Hard-blocks destructive commands regardless of work mode.

**Files:**
- Create: `~/.claude/hooks/pre-bash-danger.sh`

**Step 1: Write the hook**

```bash
#!/usr/bin/env bash
# PreToolUse: hard-block destructive bash commands.
# These are blocked globally — not just in work mode.
set -euo pipefail

input="$(cat)"
tool="$(jq -r '.tool_name // ""' <<<"$input")"
[[ "$tool" == "Bash" ]] || exit 0

cmd="$(jq -r '.tool_input.command // ""' <<<"$input")"

# Normalize for pattern matching
cmd_lower="${cmd,,}"

declare -a patterns=(
  "rm -rf"
  "git reset --hard"
  "git push --force"
  "git push -f"
  "drop table"
  "drop database"
  "truncate "
  "deletedb "
  "dropdb "
  "git clean -f"
  "git checkout -- "
  "> /dev/null 2>&1 && rm"
)

for pattern in "${patterns[@]}"; do
  if [[ "$cmd_lower" == *"$pattern"* ]]; then
    jq -cn --arg p "$pattern" --arg c "$cmd" '{
      hookSpecificOutput: {
        hookEventName: "PreToolUse",
        permissionDecision: "deny",
        permissionDecisionReason: ("DANGER GATE: Command matches destructive pattern \"" + $p + "\". This is a hard block — not overridable by work mode. If this is genuinely needed: tell Kirk, get explicit approval, then Kirk runs it manually or gives a specific one-time unlock. Command was: " + $c)
      }
    }'
    exit 0
  fi
done

exit 0
```

**Step 2: Make executable and verify**

```bash
chmod +x ~/.claude/hooks/pre-bash-danger.sh
bash -n ~/.claude/hooks/pre-bash-danger.sh && echo "syntax OK"
```

**Step 3: Test the pattern matching**

```bash
echo '{"tool_name":"Bash","tool_input":{"command":"rm -rf /tmp/test"}}' \
  | bash ~/.claude/hooks/pre-bash-danger.sh | jq .
```

Expected: `permissionDecision: "deny"` with danger gate message.

```bash
echo '{"tool_name":"Bash","tool_input":{"command":"ls /tmp"}}' \
  | bash ~/.claude/hooks/pre-bash-danger.sh
```

Expected: no output (exits 0, clean pass).

**Step 4: Register in `~/.claude/settings.json`** — new PreToolUse entry:

```json
{
  "matcher": "Bash",
  "hooks": [
    { "type": "command", "command": "bash ~/.claude/hooks/pre-bash-danger.sh", "timeout": 5 }
  ]
}
```

---

## Task 9: Build `post-bash-exit.sh`

Surfaces non-zero bash exit codes as systemMessages.

**Files:**
- Create: `~/.claude/hooks/post-bash-exit.sh`

**Step 1: Write the hook**

```bash
#!/usr/bin/env bash
# PostToolUse: surface non-zero Bash exit codes.
set -euo pipefail

input="$(cat)"
tool="$(jq -r '.tool_name // ""' <<<"$input")"
[[ "$tool" == "Bash" ]] || exit 0

# Claude Code may encode exit code under different fields depending on version
exit_code="$(jq -r '
  .tool_response.exit_code //
  .tool_response.exitCode //
  .tool_response.metadata.exit_code //
  "0"
' <<<"$input")"

[[ "$exit_code" == "0" || "$exit_code" == "null" || -z "$exit_code" ]] && exit 0

cmd="$(jq -r '.tool_input.command // ""' <<<"$input" | head -c 100)"
out="$(jq -r '.tool_response.output // .tool_response.stdout // ""' <<<"$input" | tail -20)"

jq -cn --arg code "$exit_code" --arg cmd "$cmd" --arg out "$out" '{
  systemMessage: ("⚠ BASH EXIT CODE " + $code + "\nCommand: " + $cmd + "\nLast output:\n" + $out)
}'
```

**Step 2: Make executable, verify, register**

```bash
chmod +x ~/.claude/hooks/post-bash-exit.sh
bash -n ~/.claude/hooks/post-bash-exit.sh && echo "syntax OK"
```

Register under PostToolUse with matcher `Bash`.

---

## Task 10: Build `post-pine-budget.sh`

After any `.pine` edit, counts output calls and surfaces headroom.

**Files:**
- Create: `~/.claude/hooks/post-pine-budget.sh`

**Step 1: Write the hook**

```bash
#!/usr/bin/env bash
# PostToolUse: after any .pine edit, count output budget usage.
set -euo pipefail

input="$(cat)"
tool="$(jq -r '.tool_name // ""' <<<"$input")"
[[ "$tool" == "Edit" || "$tool" == "Write" ]] || exit 0

path="$(jq -r '.tool_input.file_path // ""' <<<"$input")"
[[ "$path" == *.pine ]] || exit 0

[[ -f "$path" ]] || exit 0

# Count output calls: plot(), plotshape(), plotchar(), plotbar(), plotcandle(),
# alertcondition(), bgcolor(), barcolor(), fill(), hline()
plots=$(grep -cE '^\s*(plot|plotshape|plotchar|plotbar|plotcandle)\s*\(' "$path" 2>/dev/null || echo 0)
alerts=$(grep -cE '^\s*alertcondition\s*\(' "$path" 2>/dev/null || echo 0)
bgcolors=$(grep -cE '^\s*(bgcolor|barcolor)\s*\(' "$path" 2>/dev/null || echo 0)
fills=$(grep -cE '^\s*(fill|hline)\s*\(' "$path" 2>/dev/null || echo 0)

total=$(( plots + alerts + bgcolors + fills ))
headroom=$(( 64 - total ))

status="OK"
[[ "$headroom" -le 5 ]] && status="WARNING — CRITICAL LOW"
[[ "$headroom" -le 0 ]] && status="OVER BUDGET — WILL FAIL TO COMPILE"

fname="$(basename "$path")"
jq -cn \
  --arg f "$fname" \
  --arg t "$total" \
  --arg h "$headroom" \
  --arg s "$status" \
  --arg plots "$plots" \
  --arg alerts "$alerts" \
  --arg bg "$bgcolors" \
  --arg fills "$fills" '{
  systemMessage: ("Pine budget [" + $f + "]: " + $t + "/64 used, " + $h + " headroom — " + $s + "\n  plot/shape/char: " + $plots + "  alertcondition: " + $alerts + "  bgcolor/barcolor: " + $bg + "  fill/hline: " + $fills)
}'
```

**Step 2: Make executable, verify, register**

```bash
chmod +x ~/.claude/hooks/post-pine-budget.sh
bash -n ~/.claude/hooks/post-pine-budget.sh && echo "syntax OK"
```

Register under PostToolUse with matcher `Edit|Write`.

---

## Task 11: Build `stop-memory-audit.sh`

Blocks turn-end if significant decisions happened without a memory save.

**Files:**
- Create: `~/.claude/hooks/stop-memory-audit.sh`

**Step 1: Write the hook**

```bash
#!/usr/bin/env bash
# Stop hook: verify that memory was saved if work completed this turn.
# Blocks if todos were completed but no Write/Edit to a memory path occurred.
set -euo pipefail
source "$HOME/.claude/hooks/workflow-state.sh"

input="$(cat || true)"

sf="$(state_path "$PWD")"
[[ -f "$sf" ]] || exit 0

active="$(state_get "$sf" '.work_mode_active')"
[[ "$active" == "true" ]] || exit 0

completed="$(state_get "$sf" '.todos_completed')"
[[ "$completed" -gt 0 ]] || exit 0

# Check if memory was written this turn by scanning tool_results in payload
# Memory paths: */.remember/* or */.claude/projects/*/memory/*
memory_written="$(jq -r '
  [.tool_results // [] |
    .[] |
    select(.tool_name == "Edit" or .tool_name == "Write") |
    select(
      (.tool_input.file_path // "") |
      test("/.remember/|/.claude/projects/.*/memory/")
    )
  ] | length
' <<<"$input" 2>/dev/null || echo "0")"

if [[ "$memory_written" == "0" ]]; then
  jq -cn '{
    decision: "block",
    reason: "MEMORY AUDIT: Todos were completed this turn but no memory save was detected. Before this turn ends: write a session memory entry with what landed, what was skipped, and follow-ons. Edit (do not Write) to ~/.claude/projects/<sanitized-cwd>/memory/session_<date>.md and append a pointer to MEMORY.md."
  }'
  exit 0
fi

exit 0
```

**Step 2: Make executable, verify, register**

```bash
chmod +x ~/.claude/hooks/stop-memory-audit.sh
bash -n ~/.claude/hooks/stop-memory-audit.sh && echo "syntax OK"
```

Register as second Stop hook entry in `~/.claude/settings.json`.

---

## Task 12: Build `stop-error-pattern-writer.sh`

Writes new feedback memory entries when error patterns are detected this turn.

**Files:**
- Create: `~/.claude/hooks/stop-error-pattern-writer.sh`

**Step 1: Write the hook**

```bash
#!/usr/bin/env bash
# Stop hook: consolidate new error patterns detected this turn.
# Reads pattern_counts from state; if any count >= 1 AND no feedback file
# exists for that pattern, emits a systemMessage to write one.
set -euo pipefail
source "$HOME/.claude/hooks/workflow-state.sh"

input="$(cat || true)"

sf="$(state_path "$PWD")"
[[ -f "$sf" ]] || exit 0

active="$(state_get "$sf" '.work_mode_active')"
[[ "$active" == "true" ]] || exit 0

# Check for patterns that hit count >= 1 this turn
new_patterns="$(jq -r '
  .pattern_counts // {} |
  to_entries |
  map(select(.value >= 1)) |
  map(.key) |
  join("\n")
' "$sf" 2>/dev/null || echo "")"

[[ -n "$new_patterns" ]] || exit 0

# Determine memory dir
sanitized="$(printf '%s' "$PWD" | tr '/ ' '--')"
mem_dir="$HOME/.claude/projects/$sanitized/memory"

# Check which patterns already have a feedback file
missing=""
while IFS= read -r pattern; do
  slug="$(echo "$pattern" | tr ' ' '_' | tr '[:upper:]' '[:lower:]' | head -c 40)"
  if ! ls "$mem_dir"/feedback_*"$slug"*.md 2>/dev/null | grep -q .; then
    missing="${missing}  - $pattern\n"
  fi
done <<<"$new_patterns"

[[ -n "$missing" ]] || exit 0

jq -cn --arg patterns "$missing" '{
  systemMessage: ("ERROR PATTERNS DETECTED THIS TURN — no feedback memory entry exists yet:\n" + $patterns + "\nBefore /done: write a feedback_<topic>.md for each pattern. Use Edit (not Write). Include: rule, Why: (what caused it), How to apply: (how to prevent it). Append pointer to MEMORY.md.")
}'
```

**Step 2: Make executable, verify, register**

```bash
chmod +x ~/.claude/hooks/stop-error-pattern-writer.sh
bash -n ~/.claude/hooks/stop-error-pattern-writer.sh && echo "syntax OK"
```

Register as third Stop hook in settings.json.

---

## Task 13: Build `session-mcp-health.sh` and `session-dumpster-fire.sh`

**Files:**
- Create: `~/.claude/hooks/session-mcp-health.sh`
- Create: `~/.claude/hooks/session-dumpster-fire.sh`

**Step 1: Write `session-mcp-health.sh`**

```bash
#!/usr/bin/env bash
# SessionStart: report MCP health context into the session.
set -euo pipefail
input="$(cat || true)"

# Extract MCP tool namespaces from the session payload if available
mcp_tools="$(jq -r '
  (.available_tools // []) |
  map(select(startswith("mcp__"))) |
  map(split("__")[1]) |
  unique |
  join(", ")
' <<<"$input" 2>/dev/null || echo "unavailable in payload")"

jq -cn --arg tools "$mcp_tools" '{
  hookSpecificOutput: {
    hookEventName: "SessionStart",
    additionalContext: ("MCP HEALTH CHECK: Connected namespaces this session: " + $tools + "\nIf a required MCP is missing, /work Phase 0 will catch it during tool preflight.")
  }
}'
```

**Step 2: Write `session-dumpster-fire.sh`**

```bash
#!/usr/bin/env bash
# SessionStart: quick repo health scan. RED/YELLOW/GREEN.
set -euo pipefail
input="$(cat || true)"

status="GREEN"
findings=()

# Check git status
if command -v git >/dev/null 2>&1 && git -C "$PWD" rev-parse --git-dir >/dev/null 2>&1; then
  uncommitted="$(git -C "$PWD" status --porcelain 2>/dev/null | wc -l | tr -d ' ')"
  if [[ "$uncommitted" -gt 0 ]]; then
    findings+=("YELLOW: $uncommitted uncommitted file(s) in working tree")
    status="YELLOW"
  fi
  
  unpushed="$(git -C "$PWD" log --oneline origin/main..HEAD 2>/dev/null | wc -l | tr -d ' ')"
  if [[ "$unpushed" -gt 5 ]]; then
    findings+=("YELLOW: $unpushed commits ahead of origin/main — consider pushing")
    status="YELLOW"
  fi
fi

# Check for lock files suggesting crashed processes
for lockfile in "$PWD"/.claude/hooks/*.lock "$PWD"/node_modules/.package-lock.json.lock; do
  if [[ -f "$lockfile" ]]; then
    findings+=("YELLOW: Lock file found: $lockfile — may indicate crashed process")
    status="YELLOW"
  fi
done

# Check local DB if pg_isready available
if command -v pg_isready >/dev/null 2>&1; then
  if ! pg_isready -q 2>/dev/null; then
    findings+=("YELLOW: PostgreSQL not ready — local warbird DB may be down")
    [[ "$status" == "GREEN" ]] && status="YELLOW"
  fi
fi

summary="$(printf '%s\n' "${findings[@]}" 2>/dev/null || echo "No issues found")"
[[ "${#findings[@]}" -eq 0 ]] && summary="No issues found"

jq -cn --arg s "$status" --arg f "$summary" '{
  hookSpecificOutput: {
    hookEventName: "SessionStart",
    additionalContext: ("DUMPSTER FIRE CHECK: " + $s + "\n" + $f)
  }
}'
```

**Step 3: Make executable, verify, register both**

```bash
chmod +x ~/.claude/hooks/session-mcp-health.sh
chmod +x ~/.claude/hooks/session-dumpster-fire.sh
bash -n ~/.claude/hooks/session-mcp-health.sh && echo "mcp-health OK"
bash -n ~/.claude/hooks/session-dumpster-fire.sh && echo "dumpster-fire OK"
```

Register both under SessionStart in `~/.claude/settings.json`:

```json
"SessionStart": [
  {
    "hooks": [
      { "type": "command", "command": "bash ~/.claude/hooks/session-start.sh", "timeout": 5 },
      { "type": "command", "command": "bash ~/.claude/hooks/session-mcp-health.sh", "timeout": 5 },
      { "type": "command", "command": "bash ~/.claude/hooks/session-dumpster-fire.sh", "timeout": 10 }
    ]
  }
]
```

---

## Task 14: Build `prompt-preflight-scan.sh` and `prompt-danger-scan.sh`

**Files:**
- Create: `~/.claude/hooks/prompt-preflight-scan.sh`
- Create: `~/.claude/hooks/prompt-danger-scan.sh`

**Step 1: Write `prompt-preflight-scan.sh`**

```bash
#!/usr/bin/env bash
# UserPromptSubmit: scan prompt keywords to prime tool inventory.
set -euo pipefail
input="$(cat || true)"
prompt="$(jq -r '(.prompt // .user_prompt // "") | ascii_downcase' <<<"$input" 2>/dev/null || echo "")"

hints=()
[[ "$prompt" == *"pine"* || "$prompt" == *".pine"* || "$prompt" == *"indicator"* || "$prompt" == *"strategy"* ]] && hints+=("pine-lint.sh, pine-facade, check-contamination.sh, check-indicator-strategy-parity.sh")
[[ "$prompt" == *"python"* || "$prompt" == *".py"* || "$prompt" == *"autogluon"* || "$prompt" == *"training"* ]] && hints+=("ruff, python3 -m py_compile, pg_isready")
[[ "$prompt" == *"migration"* || "$prompt" == *"sql"* || "$prompt" == *"schema"* ]] && hints+=("psql, pg_isready, supabase CLI")
[[ "$prompt" == *"typescript"* || "$prompt" == *".ts"* || "$prompt" == *"next"* ]] && hints+=("npm run lint, npm run build")
[[ "$prompt" == *"supabase"* || "$prompt" == *"edge function"* ]] && hints+=("supabase CLI, edge function health endpoint")

[[ "${#hints[@]}" -eq 0 ]] && exit 0

hint_str="$(printf '%s\n' "${hints[@]}")"
jq -cn --arg h "$hint_str" '{
  hookSpecificOutput: {
    hookEventName: "UserPromptSubmit",
    additionalContext: ("TOOL PREFLIGHT HINT: Based on your prompt, Phase 0 should verify:\n" + $h)
  }
}'
```

**Step 2: Write `prompt-danger-scan.sh`**

```bash
#!/usr/bin/env bash
# UserPromptSubmit: warn if prompt mentions locked files or dangerous ops.
set -euo pipefail
input="$(cat || true)"
prompt="$(jq -r '(.prompt // .user_prompt // "") | ascii_downcase' <<<"$input" 2>/dev/null || echo "")"

warnings=()
[[ "$prompt" == *"v7-warbird-institutional"* ]] && warnings+=("LOCKED FILE: v7-warbird-institutional.pine requires explicit session approval per CLAUDE.md")
[[ "$prompt" == *"v7-warbird-strategy"* ]] && warnings+=("LOCKED FILE: v7-warbird-strategy.pine is the AG training data generator — parity with institutional is mandatory")
[[ "$prompt" == *"v8-warbird"* ]] && warnings+=("CODE FREEZE: v8-warbird-live.pine and v8-warbird-prescreen.pine are code-frozen per CLAUDE.md v8 freeze (2026-04-17)")
[[ "$prompt" == *"drop table"* || "$prompt" == *"truncate"* || "$prompt" == *"delete from"* ]] && warnings+=("DANGEROUS SQL: destructive SQL detected in prompt — verify this is intentional")
[[ "$prompt" == *"supabase/migrations"* || "$prompt" == *"migration"* ]] && warnings+=("MIGRATION: migrations affect production schema — ensure local test first")

[[ "${#warnings[@]}" -eq 0 ]] && exit 0

warn_str="$(printf '%s\n' "${warnings[@]}")"
jq -cn --arg w "$warn_str" '{
  hookSpecificOutput: {
    hookEventName: "UserPromptSubmit",
    additionalContext: ("⚠ DANGER SCAN WARNINGS:\n" + $w + "\n\nPhase 1 discovery must explicitly address each of these before the plan is written.")
  }
}'
```

**Step 3: Make executable, verify, register**

```bash
chmod +x ~/.claude/hooks/prompt-preflight-scan.sh
chmod +x ~/.claude/hooks/prompt-danger-scan.sh
bash -n ~/.claude/hooks/prompt-preflight-scan.sh && echo "preflight-scan OK"
bash -n ~/.claude/hooks/prompt-danger-scan.sh && echo "danger-scan OK"
```

Register both under UserPromptSubmit in `settings.json`, after `prompt-submit.sh`.

---

## Task 15: Build Remaining PreToolUse Hooks

Build `pre-plan-deviation.sh`, `pre-migration-guard.sh`, `pre-todo-integrity.sh`.

**`pre-plan-deviation.sh`** — flags edits to files not declared in the active plan:

```bash
#!/usr/bin/env bash
set -euo pipefail
source "$HOME/.claude/hooks/workflow-state.sh"

input="$(cat)"
tool="$(jq -r '.tool_name // ""' <<<"$input")"
[[ "$tool" == "Edit" || "$tool" == "Write" ]] || exit 0

sf="$(state_path "$PWD")"
[[ -f "$sf" ]] || exit 0
active="$(state_get "$sf" '.work_mode_active')"
[[ "$active" == "true" ]] || exit 0

path="$(jq -r '.tool_input.file_path // ""' <<<"$input")"
scope="$(state_get "$sf" '.plan_scope_files')"
scope_count="$(echo "$scope" | jq 'length')"

# Only enforce if plan scope was populated (Phase 2 complete)
[[ "$scope_count" -gt 0 ]] || exit 0

in_scope="$(echo "$scope" | jq -r --arg p "$path" 'map(select($p | endswith(.))) | length')"
[[ "$in_scope" -gt 0 ]] && exit 0

jq -cn --arg p "$path" '{
  hookSpecificOutput: {
    hookEventName: "PreToolUse",
    permissionDecision: "deny",
    permissionDecisionReason: ("PLAN DEVIATION: " + $p + " is not in the declared plan scope. If this edit is necessary, update the plan doc first (add the file to the task entry) and update plan_scope_files in state. Scope creep without plan updates is a contract violation.")
  }
}'
exit 0
```

**`pre-migration-guard.sh`** — requires plan entry for any migration edit:

```bash
#!/usr/bin/env bash
set -euo pipefail
source "$HOME/.claude/hooks/workflow-state.sh"

input="$(cat)"
tool="$(jq -r '.tool_name // ""' <<<"$input")"
[[ "$tool" == "Edit" || "$tool" == "Write" ]] || exit 0

path="$(jq -r '.tool_input.file_path // ""' <<<"$input")"
case "$path" in
  */supabase/migrations/*|*/local_warehouse/migrations/*)
    sf="$(state_path "$PWD")"
    plan_doc="$(state_get "$sf" '.plan_doc_path' 2>/dev/null || echo "")"
    jq -cn --arg p "$path" --arg plan "$plan_doc" '{
      hookSpecificOutput: {
        hookEventName: "PreToolUse",
        permissionDecision: "ask",
        permissionDecisionReason: ("MIGRATION GUARD: " + $p + " is a migration file. Migrations are irreversible on cloud. Confirm: (1) this migration is explicitly listed in the plan doc (" + $plan + "), (2) local pg test has been run, (3) rollback plan exists. Approve to proceed.")
      }
    }'
    exit 0
    ;;
esac
exit 0
```

**`pre-todo-integrity.sh`** — warns on unplanned mid-session todo additions:

```bash
#!/usr/bin/env bash
set -euo pipefail
source "$HOME/.claude/hooks/workflow-state.sh"

input="$(cat)"
tool="$(jq -r '.tool_name // ""' <<<"$input")"
[[ "$tool" == "TodoWrite" ]] || exit 0

sf="$(state_path "$PWD")"
[[ -f "$sf" ]] || exit 0
active="$(state_get "$sf" '.work_mode_active')"
[[ "$active" == "true" ]] || exit 0

prev_count="$(state_get "$sf" '.todo_count')"
new_count="$(jq '(.tool_input.todos // []) | length' <<<"$input")"

# Adding todos mid-session (after first TodoWrite) requires rationale
todowrite_count="$(state_get "$sf" '.todowrite_invoked')"
if [[ "$todowrite_count" == "true" && "$new_count" -gt "$prev_count" ]]; then
  added=$(( new_count - prev_count ))
  jq -cn --arg n "$added" '{
    systemMessage: ("TODO INTEGRITY: " + $n + " new todo(s) added mid-session. Per work-mode contract, unplanned scope additions must be rationalized. Note why in the plan doc progress section before continuing.")
  }'
fi
exit 0
```

Make all three executable, verify syntax, register in `settings.json` PreToolUse.

---

## Task 16: Build `post-specialist-suggest.sh` and `post-memory-enforcer.sh`

**`post-specialist-suggest.sh`** — after edits, suggests the specialist tool if it wasn't in recent calls:

```bash
#!/usr/bin/env bash
set -euo pipefail

input="$(cat)"
tool="$(jq -r '.tool_name // ""' <<<"$input")"
[[ "$tool" == "Edit" || "$tool" == "Write" ]] || exit 0

path="$(jq -r '.tool_input.file_path // ""' <<<"$input")"

suggestion=""
case "$path" in
  *.pine)
    suggestion="Specialist tools required: pine-lint.sh → pine-facade TV compiler → check-contamination.sh. If this is a strategy file, also: check-indicator-strategy-parity.sh." ;;
  */supabase/functions/*.ts)
    suggestion="Specialist tool: Supabase CLI function check + edge function health endpoint." ;;
  */local_warehouse/migrations/*.sql|*/supabase/migrations/*.sql)
    suggestion="Specialist tools: psql dry-run + migration ledger reconciliation." ;;
  *.py)
    suggestion="Specialist tools: ruff + python3 -m py_compile. If trainer touched: AG dry-run." ;;
  */scripts/guards/*.sh)
    suggestion="Specialist tools: shellcheck + dry-run against known-good input." ;;
esac

[[ -n "$suggestion" ]] || exit 0

jq -cn --arg s "$suggestion" '{
  systemMessage: ("SPECIALIST TOOL REMINDER: " + $s)
}'
```

**`post-memory-enforcer.sh`** — warns when a todo completes without a memory write nearby:

```bash
#!/usr/bin/env bash
set -euo pipefail
source "$HOME/.claude/hooks/workflow-state.sh"

input="$(cat)"
tool="$(jq -r '.tool_name // ""' <<<"$input")"
[[ "$tool" == "TodoWrite" ]] || exit 0

new_completed="$(jq '[(.tool_input.todos // [])[] | select(.status=="completed")] | length' <<<"$input")"
sf="$(state_path "$PWD")"
[[ -f "$sf" ]] || exit 0
prev_completed="$(state_get "$sf" '.todos_completed')"

[[ "$new_completed" -gt "$prev_completed" ]] || exit 0

# Emit a reminder — post-checkpoint-trigger handles the hard block,
# this is the soft memory reminder
jq -cn '{
  systemMessage: ("MEMORY REMINDER: A todo just completed. After your checkpoint validation, write findings to the session memory file before clearing pending_checkpoint.")
}'
```

Make both executable, verify, register under PostToolUse.

---

## Task 17: Wire All New Hooks into `~/.claude/settings.json`

This is the integration task. Read the current `settings.json` and produce the complete final version.

**Step 1: Read current settings**

```bash
cat ~/.claude/settings.json | jq '.hooks | keys'
```

**Step 2: Build the complete hooks object**

The final `hooks` section in `settings.json`:

```json
"hooks": {
  "SessionStart": [
    {
      "hooks": [
        { "type": "command", "command": "bash ~/.claude/hooks/session-start.sh", "timeout": 5 },
        { "type": "command", "command": "bash ~/.claude/hooks/session-mcp-health.sh", "timeout": 5 },
        { "type": "command", "command": "bash ~/.claude/hooks/session-dumpster-fire.sh", "timeout": 10 }
      ]
    }
  ],
  "UserPromptSubmit": [
    {
      "hooks": [
        { "type": "command", "command": "bash ~/.claude/hooks/prompt-submit.sh", "timeout": 5 },
        { "type": "command", "command": "bash ~/.claude/hooks/prompt-preflight-scan.sh", "timeout": 5 },
        { "type": "command", "command": "bash ~/.claude/hooks/prompt-danger-scan.sh", "timeout": 5 }
      ]
    }
  ],
  "PreToolUse": [
    {
      "matcher": "Edit|Write|Bash",
      "hooks": [
        { "type": "command", "command": "bash ~/.claude/hooks/pre-checkpoint-gate.sh", "timeout": 5 }
      ]
    },
    {
      "matcher": "Edit|Write",
      "hooks": [
        { "type": "command", "command": "bash ~/.claude/hooks/pre-edit-gate.sh", "timeout": 5 },
        { "type": "command", "command": "bash ~/.claude/hooks/guard-memory-overwrite.sh", "timeout": 5 },
        { "type": "command", "command": "bash ~/.claude/hooks/pre-memory-read-check.sh", "timeout": 5 },
        { "type": "command", "command": "bash ~/.claude/hooks/pre-plan-deviation.sh", "timeout": 5 },
        { "type": "command", "command": "bash ~/.claude/hooks/pre-migration-guard.sh", "timeout": 5 }
      ]
    },
    {
      "matcher": "Bash",
      "hooks": [
        { "type": "command", "command": "bash ~/.claude/hooks/pre-bash-danger.sh", "timeout": 5 }
      ]
    },
    {
      "matcher": "Skill",
      "hooks": [
        { "type": "command", "command": "bash ~/.claude/hooks/pre-skill-record.sh", "timeout": 3 }
      ]
    },
    {
      "matcher": "TodoWrite",
      "hooks": [
        { "type": "command", "command": "bash ~/.claude/hooks/pre-todo-integrity.sh", "timeout": 5 }
      ]
    }
  ],
  "PostToolUse": [
    {
      "matcher": "TodoWrite",
      "hooks": [
        { "type": "command", "command": "bash ~/.claude/hooks/post-todowrite.sh", "timeout": 3 },
        { "type": "command", "command": "bash ~/.claude/hooks/post-checkpoint-trigger.sh", "timeout": 5 },
        { "type": "command", "command": "bash ~/.claude/hooks/post-memory-enforcer.sh", "timeout": 3 }
      ]
    },
    {
      "matcher": "Edit|Write",
      "hooks": [
        { "type": "command", "command": "bash ~/.claude/hooks/post-edit-lint.sh", "timeout": 60 },
        { "type": "command", "command": "bash ~/.claude/hooks/post-pine-budget.sh", "timeout": 10 },
        { "type": "command", "command": "bash ~/.claude/hooks/post-specialist-suggest.sh", "timeout": 5 }
      ]
    },
    {
      "matcher": "Bash",
      "hooks": [
        { "type": "command", "command": "bash ~/.claude/hooks/post-bash-exit.sh", "timeout": 5 }
      ]
    }
  ],
  "Stop": [
    {
      "hooks": [
        { "type": "command", "command": "bash ~/.claude/hooks/stop-auditor.sh", "timeout": 30 },
        { "type": "command", "command": "bash ~/.claude/hooks/stop-memory-audit.sh", "timeout": 10 },
        { "type": "command", "command": "bash ~/.claude/hooks/stop-error-pattern-writer.sh", "timeout": 10 }
      ]
    }
  ]
}
```

**Step 3: Verify JSON is valid after edit**

```bash
jq . ~/.claude/settings.json > /dev/null && echo "valid JSON"
```

Expected: `valid JSON`

---

## Task 18: Rewrite `~/.claude/skills/work/SKILL.md`

**Files:**
- Modify: `~/.claude/skills/work/SKILL.md` (full rewrite)

The new SKILL.md must cover all 5 phases with the mindset shift front-loaded. Key content requirements:

- **Frontmatter**: update description to reflect the 5-phase system
- **Phase 0** (Pre-flight): exact steps — read memory, MCP health, tool verification, git/lint/db state, RED/YELLOW/GREEN output, hard block on RED
- **Phase 1** (Discovery): Track A (3 questions), Track B (autonomous research list), pushback triggers with evidence requirements
- **Phase 2** (Battle Plan): exact template reference, commit requirement before execution
- **Phase 3** (Execute): checkpoint loop — specialist tool name → run → memory → pattern scan → suggestions → plan doc update → clear flag
- **Checkpoint clearing**: explicit instruction — after all 6 checkpoint steps are done, update state to clear `pending_checkpoint`: `bash -c "source ~/.claude/hooks/workflow-state.sh; state_set $(state_path $PWD) '.pending_checkpoint = false'"`
- **Specialist tool registry**: embedded lookup table
- **Self-improvement**: when to write `feedback_*.md`, when to propose hook escalation

Keep it under 200 lines. Mindset first, mechanics second.

---

## Task 19: Rewrite `~/.claude/skills/done/SKILL.md`

**Files:**
- Modify: `~/.claude/skills/done/SKILL.md` (targeted additions)

The current `/done` skill is mostly correct. Additions needed:

1. **Step 0** (before todo verification): Run `stop-auditor.sh` logic manually — confirm `pending_checkpoint=false` before proceeding
2. **Specialist tool sweep** (replaces "final lint"): run each specialist tool from the plan doc's Progress table that hasn't been run in the final checkpoint
3. **Pattern consolidation**: check `stop-error-pattern-writer.sh` findings, write any outstanding `feedback_*.md` entries
4. **Plan doc close-out**: update status to `COMPLETE` or `PARTIAL`, update Progress table with final results, commit
5. **Updated final report format**: match the 10-field format from design doc

---

## Task 20: Update `workflow-preamble.txt`

**Files:**
- Modify: `~/.claude/hooks/workflow-preamble.txt`

Add two new rules to the existing 7 (now 9 total):

```
8. Checkpoints are mechanical. After every completed todo:
   name + run the specialist tool → memory write → pattern scan → 
   plan doc update → clear pending_checkpoint via state_set.
   The gate will not open until this sequence is in the transcript.

9. Self-improve continuously. When you spot a workflow gap,
   write it to the plan doc §Workflow Improvements. When you 
   find a new error pattern, write feedback_*.md immediately.
   Propose hook escalations to Kirk — never self-apply them.
```

Also update the enforcement section at the bottom to list the new hooks.

---

## Task 21: Smoke Test End-to-End

**Step 1: Test pre-flight on a fresh session**

Open a new Claude Code session in warbird-pro. Type `/work test smoke test`. Verify:
- Session start shows MCP health + dumpster fire status
- Pre-flight reads memory (or denies first Edit if memory wasn't read)
- Prompt-danger-scan fires (no warnings expected for "smoke test")

**Step 2: Test checkpoint gate**

```bash
# Simulate: activate work mode, invoke TodoWrite with a completed todo
source ~/.claude/hooks/workflow-state.sh
sf=$(state_path "$PWD")
state_set "$sf" '.work_mode_active = true | .todowrite_invoked = true | .todos_in_progress = 0 | .todo_count = 1'

# Simulate post-checkpoint-trigger (todo just completed)
echo '{"tool_name":"TodoWrite","tool_input":{"todos":[{"content":"test task","status":"completed"}]}}' \
  | bash ~/.claude/hooks/post-checkpoint-trigger.sh

# Verify pending_checkpoint is now true
state_get "$sf" '.pending_checkpoint'
```

Expected: `true`

**Step 3: Test the gate blocks Edit**

```bash
echo '{"tool_name":"Edit","tool_input":{"file_path":"/tmp/test.ts"}}' \
  | bash ~/.claude/hooks/pre-checkpoint-gate.sh | jq .hookSpecificOutput.permissionDecision
```

Expected: `"deny"`

**Step 4: Clear the checkpoint and verify gate opens**

```bash
state_set "$sf" '.pending_checkpoint = false'
echo '{"tool_name":"Edit","tool_input":{"file_path":"/tmp/test.ts"}}' \
  | bash ~/.claude/hooks/pre-checkpoint-gate.sh
```

Expected: no output (exit 0, gate open).

**Step 5: Test stop auditor**

```bash
# With pending_checkpoint=true, auditor should block
state_set "$sf" '.pending_checkpoint = true | .todos_completed = 1'
echo '{}' | bash ~/.claude/hooks/stop-auditor.sh | jq .decision
```

Expected: `"block"`

**Step 6: Test danger scan**

```bash
echo '{"tool_name":"Bash","tool_input":{"command":"rm -rf /tmp/test"}}' \
  | bash ~/.claude/hooks/pre-bash-danger.sh | jq .hookSpecificOutput.permissionDecision
```

Expected: `"deny"`

**Step 7: Test pine budget hook**

```bash
# Create a test pine file with known output count
echo 'plot(close)
plot(open)
alertcondition(true)' > /tmp/test-budget.pine
echo "{\"tool_name\":\"Edit\",\"tool_input\":{\"file_path\":\"/tmp/test-budget.pine\"}}" \
  | bash ~/.claude/hooks/post-pine-budget.sh | jq .systemMessage
```

Expected: message showing `3/64 used, 61 headroom`.

**Step 8: Commit final state**

```bash
cd "/Volumes/Satechi Hub/warbird-pro"
git add docs/plans/2026-04-24-work-mode-redesign-plan.md
git commit -m "Add /work mode redesign implementation plan

32 hooks, 5-phase workflow, checkpoint gate, specialist tool
registry, self-improvement mechanism. Ready for execution.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Execution Notes

- **All hook files** live in `~/.claude/hooks/` — not in the warbird-pro repo
- **Settings** are in `~/.claude/settings.json` — always validate JSON after edits
- **Work on main** — no branches
- **Each hook is independent** — test in isolation before wiring into settings.json
- **settings.json is load-bearing** — a malformed JSON here breaks all Claude Code sessions. Always run `jq . ~/.claude/settings.json` after every edit
- **Hook payload structure** may vary by Claude Code version — the bash scripts use `// "fallback"` jq patterns throughout for resilience
- **The checkpoint flag must be cleared** by the model after completing checkpoint steps — it is not auto-cleared by any hook. The model runs: `source ~/.claude/hooks/workflow-state.sh && state_set $(state_path $PWD) '.pending_checkpoint = false'`
