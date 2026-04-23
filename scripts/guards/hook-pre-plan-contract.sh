#!/bin/bash
# PreToolUse hook: surface active-plan Hard Constraints before Pine or training edits.
#
# Motivation: verbal requests have contradicted WARBIRD_V8_PLAN.md hard constraints
# before (e.g. "SuperTrend flip on confirmed 15m bar close only"). Hand-rolled logic
# landed and took ~2 hrs to unwind. This hook injects
# the Hard Constraints into additionalContext before any edit on governed surfaces,
# so the constraints are visible in real time — not post-mortem.
#
# Non-blocking: just adds context. Kirk's verbal overrides still rule; this ensures
# the contradiction is SEEN before, not after.

set -uo pipefail

fp=$(jq -r '.tool_input.file_path // ""' 2>/dev/null || true)

# Governed surfaces where Hard Constraints apply
case "$fp" in
  */indicators/*.pine) ;;
  */scripts/ag/*.py) ;;
  */local_warehouse/migrations/*.sql) ;;
  *) exit 0 ;;
esac

PROJECT_DIR="${CLAUDE_PROJECT_DIR:-/Volumes/Satechi Hub/warbird-pro}"
PLAN_FILE="$PROJECT_DIR/docs/WARBIRD_V8_PLAN.md"

if [ ! -f "$PLAN_FILE" ]; then
  exit 0
fi

# Extract the "Hard Constraints" section (between ## Hard Constraints header and next ## header)
constraints=$(awk '/^## Hard Constraints/{flag=1;next} /^## /{flag=0} flag' "$PLAN_FILE" | head -40)

if [ -z "$constraints" ]; then
  exit 0
fi

jq -cn --arg fp "$fp" --arg c "$constraints" \
  '{hookSpecificOutput:{hookEventName:"PreToolUse",additionalContext:("ACTIVE PLAN HARD CONSTRAINTS (WARBIRD_V8_PLAN.md) — edit to " + $fp + " must respect these. If a verbal request conflicts with a constraint below, STOP and confirm before proceeding:\n\n" + $c)}}'

exit 0
