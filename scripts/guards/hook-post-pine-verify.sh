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
# Per memory/feedback_pine_strategy_tv_compile_required.md
if head -25 "$fp" 2>/dev/null | grep -q '^strategy('; then
  jq -cn --arg fp "$fp" \
    '{hookSpecificOutput:{hookEventName:"PostToolUse",additionalContext:("REQUIRED NEXT STEP: " + $fp + " is a strategy() script. pine-facade passed but misses CE10244. Before claiming complete, run via TradingView MCP:\n  1. mcp__tradingview__pine_set_source (with full file contents)\n  2. mcp__tradingview__pine_smart_compile\n  3. mcp__tradingview__pine_get_errors\nCE10244 will only be caught here, not by pine-facade or pine-lint.")}}'
fi

exit 0
