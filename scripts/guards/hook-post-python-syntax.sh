#!/bin/bash
# PostToolUse hook: Python syntax check (AST parse) after any Edit|Write on a .py file
# Input: JSON on stdin with tool_input.file_path or tool_response.filePath
# Output: On syntax failure, JSON with decision:block + additionalContext. On success or non-.py, nothing.
# Scope: syntax only — NOT a style or type check. Stdlib-only (no ruff/mypy dependency).
# Wired to: .claude/settings.json PostToolUse/Edit|Write matcher

set -uo pipefail

fp=$(jq -r '.tool_input.file_path // .tool_response.filePath // ""' 2>/dev/null || true)

# Only act on .py files
case "$fp" in
  *.py) ;;
  *) exit 0 ;;
esac

# Skip pyc / __pycache__ / .venv — never edit those anyway but defensive
case "$fp" in
  */__pycache__/*|*/.venv/*|*.pyc) exit 0 ;;
esac

PY="${CLAUDE_PROJECT_DIR:-/Volumes/Satechi Hub/warbird-pro}/.venv/bin/python3"
[ -x "$PY" ] || PY="/usr/bin/env python3"

# ast.parse: compiles without executing, no side effects, stdlib only
err=$("$PY" -c "import ast, sys; ast.parse(open(sys.argv[1]).read(), sys.argv[1])" "$fp" 2>&1)
status=$?

if [ $status -ne 0 ]; then
  jq -cn --arg fp "$fp" --arg out "$err" \
    '{hookSpecificOutput:{hookEventName:"PostToolUse",additionalContext:("Python syntax error in " + $fp + ". Fix before continuing:\n\n" + $out)}, decision:"block", reason:"Python syntax check failed — see additionalContext"}'
fi

exit 0
