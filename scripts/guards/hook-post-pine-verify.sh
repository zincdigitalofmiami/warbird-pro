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
  exit 0
fi

# v8 prescreen parity check — blocks hand-rolled drift between live and prescreen
case "$fp" in
  */v8-warbird-live.pine|*/v8-warbird-prescreen.pine)
    parity_output=$(bash scripts/guards/check-v8-prescreen-parity.sh 2>&1)
    parity_status=$?
    if [ $parity_status -ne 0 ]; then
      jq -cn --arg fp "$fp" --arg out "$parity_output" \
        '{hookSpecificOutput:{hookEventName:"PostToolUse",additionalContext:("v8 parity FAILED after editing " + $fp + ". Prescreen must be live verbatim + minimal strategy() wrapper only. Fix before continuing:\n\n" + $out)}, decision:"block", reason:"v8 prescreen parity failed — see additionalContext"}'
      exit 0
    fi
    ;;
esac

# TV Desktop compile reminder for strategy() files — pine-facade misses CE10244
# ADVISORY ONLY — not a block. Only act on this if:
#   (a) the change is FUNCTIONAL (logic, not a display label or comment), AND
#   (b) Kirk has explicitly authorized TV use this session (CDP confirmed up via tv_health_check)
# If CDP is unavailable, DO NOT call tv_launch. Skip TV verification and say so.
if head -25 "$fp" 2>/dev/null | grep -q '^strategy('; then
  jq -cn --arg fp "$fp" \
    '{hookSpecificOutput:{hookEventName:"PostToolUse",additionalContext:("ADVISORY (not a block): " + $fp + " is a strategy() script. pine-facade misses CE10244. IF this was a functional change AND TV CDP is confirmed up: run pine_smart_compile via MCP. If display-only change (shorttitle/comment) or CDP unavailable: pine-facade success is sufficient — skip TV and proceed.")}}'
fi

exit 0
