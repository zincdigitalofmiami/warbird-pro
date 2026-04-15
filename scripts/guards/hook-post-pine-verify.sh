#!/bin/bash
# PostToolUse hook: auto-run pine-lint after any indicators/*.pine edit
# Input: JSON on stdin with tool_input.file_path or tool_response.filePath
# Output: On lint failure, JSON with decision:block + additionalContext. On success or non-match, nothing.
# Wired to: .claude/settings.json PostToolUse/Edit|Write matcher

set -uo pipefail

fp=$(jq -r '.tool_input.file_path // .tool_response.filePath // ""' 2>/dev/null || true)

# Only act on indicators/*.pine files
case "$fp" in
  */indicators/*.pine) ;;
  *) exit 0 ;;
esac

cd "${CLAUDE_PROJECT_DIR:-/Volumes/Satechi Hub/warbird-pro}" 2>/dev/null || exit 0

# Run pine-lint. Capture stdout+stderr.
lint_output=$(bash scripts/guards/pine-lint.sh "$fp" 2>&1)
lint_status=$?

if [ $lint_status -ne 0 ]; then
  # Lint failed — block and inject context so Claude sees the errors immediately
  jq -cn --arg fp "$fp" --arg out "$lint_output" \
    '{hookSpecificOutput:{hookEventName:"PostToolUse",additionalContext:("pine-lint FAILED for " + $fp + ". Fix before continuing:\n\n" + $out)}, decision:"block", reason:"pine-lint failed — see additionalContext"}'
fi

exit 0
