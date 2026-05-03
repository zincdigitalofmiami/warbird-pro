#!/usr/bin/env bash
# Agent-owned Warbird precheck gate for commits and pushes.

set -euo pipefail

MODE="manual"

usage() {
  cat <<'USAGE'
Usage: scripts/guards/warbird-agent-precheck.sh [--mode pre-commit|pre-push|manual]

This is the Codex/Claude-owned local gate. It writes an audit log for every
attempt, refuses ambiguous working-tree state, and then runs the Warbird local
quality lane. Pre-push mode also checks remote GitHub merge readiness.
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --mode)
      MODE="${2:-}"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "FAIL: unknown argument '$1'"
      usage
      exit 2
      ;;
  esac
done

case "$MODE" in
  pre-commit|pre-push|manual) ;;
  *)
    echo "FAIL: invalid mode '$MODE'"
    usage
    exit 2
    ;;
esac

ROOT_DIR="$(git rev-parse --show-toplevel)"
cd "$ROOT_DIR"

LOG_DIR="$ROOT_DIR/.git/warbird-prechecks"
mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/$(date -u +%Y%m%dT%H%M%SZ)-$MODE.log"
ln -sf "$(basename "$LOG_FILE")" "$LOG_DIR/latest.log"

exec > >(tee "$LOG_FILE") 2>&1

fail() {
  echo
  echo "FAIL: $*"
  echo "AGENT AUDIT LOG: $LOG_FILE"
  exit 1
}

if [[ "${WARBIRD_AGENT_REVIEW_ACTIVE:-}" == "1" ]]; then
  fail "refusing to start a Warbird precheck from inside the nested text-only agent review process."
fi

detect_owner() {
  if [[ -n "${WARBIRD_AGENT_OWNER:-}" ]]; then
    echo "$WARBIRD_AGENT_OWNER"
  elif [[ -n "${CLAUDECODE:-}" || -n "${CLAUDE_CODE:-}" ]]; then
    echo "Claude Code"
  elif command -v claude >/dev/null 2>&1; then
    echo "Claude Code"
  elif [[ -n "${CODEX_THREAD_ID:-}" || -n "${CODEX_SHELL:-}" ]]; then
    echo "Codex"
  elif command -v codex >/dev/null 2>&1; then
    echo "Codex"
  else
    echo "Codex/Claude Code unavailable"
  fi
}

resolve_upstream_ref() {
  git rev-parse --abbrev-ref --symbolic-full-name '@{upstream}' 2>/dev/null || true
}

write_agent_review_prompt() {
  local prompt_file="$1"
  local upstream_ref="$2"

  {
    cat <<'PROMPT'
You are the required Warbird Codex/Claude Code commit gate.

Review the included change packet as a blocking precheck, not as a style pass.
Prioritize only defects that should block commit or push:
- hook bypasses, recursion, false pass/fail behavior, or missing dirty-state coverage
- Warbird repo-rule violations, especially Pine/TradingView safety rules
- broken shell logic, missing executable paths, missing guard coverage, or merge-readiness blind spots
- docs that claim operational truth not enforced by the hook or guard

Return exactly this format:
RESULT: PASS or FAIL
FINDINGS:
- none

Use RESULT: FAIL if there is any blocker. Do not include general suggestions.
PROMPT
    echo
    echo "MODE: $MODE"
    echo "REPO: $ROOT_DIR"
    echo "HEAD: $(git rev-parse --short HEAD)"
    echo "BRANCH: $(git rev-parse --abbrev-ref HEAD)"
    echo
    echo "STATUS:"
    git status --short --branch
    echo
    echo "TRACKED GUARD EVIDENCE:"
    for guard_file in \
      scripts/guards/compile-pine.sh \
      scripts/guards/check-canonical-zoo.sh \
      scripts/guards/check-github-merge-readiness.sh; do
      if git ls-files --error-unmatch "$guard_file" >/dev/null 2>&1; then
        ls -l "$guard_file"
      else
        echo "MISSING: $guard_file"
      fi
    done
    echo
    echo "MERGE READINESS FLAG EVIDENCE:"
    "$ROOT_DIR/scripts/guards/check-github-merge-readiness.sh" --help | sed -n '1,14p'
    echo
    echo "RECURSION GUARD EVIDENCE:"
    echo "Nested agent review runs with WARBIRD_AGENT_REVIEW_ACTIVE=1 and no tools."
    echo "This script fails immediately if WARBIRD_AGENT_REVIEW_ACTIVE=1."
    echo
    echo "CLAUDE NO-TOOLS FLAG EVIDENCE:"
    if command -v claude >/dev/null 2>&1; then
      claude --help | grep -F 'Use "" to disable all tools' || true
    else
      echo "Claude CLI unavailable; Codex fallback would be used."
    fi
    echo
    echo "CHANGED FILES:"
    if [[ "$MODE" == "pre-push" && -n "$upstream_ref" ]]; then
      git diff --name-status "$upstream_ref"...HEAD || true
    elif ! git diff --cached --quiet --exit-code; then
      git diff --cached --name-status
    else
      git diff --name-status
      git ls-files --others --exclude-standard | sed 's/^/??\t/'
    fi
    echo
    echo "DIFF:"
    if [[ "$MODE" == "pre-push" && -n "$upstream_ref" ]]; then
      git diff --no-ext-diff "$upstream_ref"...HEAD || true
    elif ! git diff --cached --quiet --exit-code; then
      git diff --cached --no-ext-diff
    else
      git diff --no-ext-diff
    fi
  } >"$prompt_file"
}

run_agent_review() {
  local upstream_ref=""
  local prompt_file="$LOG_DIR/$(date -u +%Y%m%dT%H%M%SZ)-$MODE-agent-review-prompt.txt"
  local result_file="$LOG_DIR/$(date -u +%Y%m%dT%H%M%SZ)-$MODE-agent-review-result.txt"

  if [[ "$MODE" == "pre-push" ]]; then
    upstream_ref="$(resolve_upstream_ref)"
    if [[ -n "$upstream_ref" ]] && git diff --quiet "$upstream_ref"...HEAD; then
      echo "INFO: no branch diff against $upstream_ref; skipping agent diff review."
      return 0
    fi
  elif git diff --cached --quiet --exit-code && git diff --quiet --exit-code; then
    echo "INFO: no local diff to agent-review."
    return 0
  fi

  write_agent_review_prompt "$prompt_file" "$upstream_ref"

  echo "CHECK: Codex/Claude agent review"
  echo "INFO: agent review prompt $prompt_file"
  echo "INFO: agent review result $result_file"

  if command -v claude >/dev/null 2>&1; then
    local budget="${WARBIRD_AGENT_REVIEW_BUDGET_USD:-2.00}"
    if ! WARBIRD_AGENT_REVIEW_ACTIVE=1 claude -p --model sonnet --effort low --tools "" --permission-mode dontAsk --max-budget-usd "$budget" <"$prompt_file" | tee "$result_file"; then
      fail "Claude Code agent review failed to complete."
    fi
  elif command -v codex >/dev/null 2>&1; then
    local codex_model="${WARBIRD_CODEX_REVIEW_MODEL:-gpt-5.3-codex}"
    if ! WARBIRD_AGENT_REVIEW_ACTIVE=1 codex exec review -m "$codex_model" --uncommitted | tee "$result_file"; then
      fail "Codex agent review failed to complete."
    fi
  else
    fail "no Codex or Claude Code executable is available for the required agent review."
  fi

  if grep -Eq '^RESULT:[[:space:]]*FAIL\b' "$result_file"; then
    fail "agent review returned RESULT: FAIL."
  fi
  if ! grep -Eq '^RESULT:[[:space:]]*PASS\b' "$result_file"; then
    fail "agent review did not return RESULT: PASS."
  fi
}

OWNER="$(detect_owner)"

cat <<EOF
============================================================
WARBIRD AGENT PRECHECK
Owner: $OWNER
Mode: $MODE
Repo: $ROOT_DIR
Audit log: $LOG_FILE
============================================================
EOF

if [[ "$OWNER" == "Codex/Claude Code unavailable" ]]; then
  fail "neither codex nor claude is available in PATH; this repo requires an agent-owned precheck."
fi

if command -v osascript >/dev/null 2>&1; then
  osascript -e 'display notification "Warbird agent precheck started" with title "Codex/Claude Commit Gate"' >/dev/null 2>&1 || true
fi

hooks_path="$(git config --get core.hooksPath || true)"
if [[ "$hooks_path" != ".githooks" ]]; then
  fail "core.hooksPath is '$hooks_path', expected '.githooks'. Run: git config core.hooksPath .githooks"
fi

echo "INFO: branch $(git rev-parse --abbrev-ref HEAD)"
echo "INFO: head $(git rev-parse --short HEAD)"

echo "INFO: working tree status"
git status --short --branch

tracked_dirty="$(git diff --name-only)"
untracked_dirty="$(git ls-files --others --exclude-standard)"

if [[ "$MODE" == "pre-commit" ]]; then
  staged_count="$(git diff --cached --name-only | sed '/^$/d' | wc -l | tr -d ' ')"
  if [[ "$staged_count" -eq 0 ]]; then
    fail "pre-commit gate saw no staged files."
  fi

  if [[ -n "$tracked_dirty" ]]; then
    echo "UNSTAGED TRACKED FILES:"
    printf '%s\n' "$tracked_dirty"
    fail "commit blocked because unstaged tracked files make the checked state ambiguous."
  fi

  if [[ -n "$untracked_dirty" ]]; then
    echo "UNTRACKED FILES:"
    printf '%s\n' "$untracked_dirty"
    fail "commit blocked because untracked files make the checked state ambiguous."
  fi
elif [[ "$MODE" == "pre-push" ]]; then
  if [[ -n "$(git status --porcelain)" ]]; then
    fail "push blocked because the working tree is not clean."
  fi
fi

echo "CHECK: Warbird local quality lane"
"$ROOT_DIR/scripts/guards/check-local-quality-lane.sh"

run_agent_review

if [[ "$MODE" == "pre-push" ]]; then
  repo="$(gh repo view --json nameWithOwner --jq '.nameWithOwner' 2>/dev/null || true)"
  if [[ -z "$repo" ]]; then
    fail "pre-push remote audit could not resolve GitHub repo."
  fi
  echo "CHECK: GitHub merge-readiness audit for $repo"
  "$ROOT_DIR/scripts/guards/check-github-merge-readiness.sh" --repo "$repo"
fi

echo "PASS: Warbird agent precheck complete"
echo "AGENT AUDIT LOG: $LOG_FILE"
