#!/usr/bin/env bash
# Fail fast on GitHub repository rules that can block protected pushes or PR merges.

set -euo pipefail

REPO=""
PR_NUMBER=""
BRANCH=""
SKIP_PR=0
SKIP_LOCAL_SYNC=0

usage() {
  cat <<'USAGE'
Usage: scripts/guards/check-github-merge-readiness.sh [options]

Options:
  --repo OWNER/REPO       GitHub repository. Defaults to gh's current repo.
  --pr NUMBER            Pull request number. Defaults to current branch PR.
  --branch NAME          Local branch name for sync reporting. Defaults to HEAD.
  --skip-pr              Only audit repository/ruleset setup.
  --skip-local-sync      Do not inspect local upstream/ahead/behind state.
  -h, --help             Show this help.

Checks:
  - GitHub CLI auth and repository resolution.
  - active branch rulesets, including CodeQL code-scanning requirements.
  - GitHub CodeQL default setup and local workflow only when a ruleset requires CodeQL.
  - current PR mergeability and status-check rollup when a PR is available.
  - local branch drift that can make PR checks stale.
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --repo)
      REPO="${2:-}"
      shift 2
      ;;
    --pr)
      PR_NUMBER="${2:-}"
      shift 2
      ;;
    --branch)
      BRANCH="${2:-}"
      shift 2
      ;;
    --skip-pr)
      SKIP_PR=1
      shift
      ;;
    --skip-local-sync)
      SKIP_LOCAL_SYNC=1
      shift
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

for cmd in git gh jq; do
  if ! command -v "$cmd" >/dev/null 2>&1; then
    echo "FAIL: $cmd is required for GitHub merge-readiness audit."
    exit 1
  fi
done

if ! gh auth status >/dev/null 2>&1; then
  echo "FAIL: gh is not authenticated. Run gh auth status for details."
  exit 1
fi

FAILURES=0
WARNINGS=0

fail() {
  echo "FAIL: $*"
  FAILURES=$((FAILURES + 1))
}

warn() {
  echo "WARN: $*"
  WARNINGS=$((WARNINGS + 1))
}

pass() {
  echo "PASS: $*"
}

info() {
  echo "INFO: $*"
}

if [[ -z "$REPO" ]]; then
  if ! REPO="$(gh repo view --json nameWithOwner --jq '.nameWithOwner' 2>/dev/null)"; then
    fail "could not resolve GitHub repository from current checkout."
  fi
fi

if [[ -z "$BRANCH" ]]; then
  BRANCH="$(git rev-parse --abbrev-ref HEAD 2>/dev/null || true)"
fi

if [[ -n "$REPO" ]]; then
  pass "resolved repository $REPO"
fi

if [[ "$SKIP_LOCAL_SYNC" -eq 0 ]]; then
  if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    if [[ -n "$(git status --porcelain)" ]]; then
      warn "working tree has local changes; remote PR checks may not represent disk."
    else
      pass "working tree has no unstaged or staged changes"
    fi

    if upstream="$(git rev-parse --abbrev-ref --symbolic-full-name '@{u}' 2>/dev/null)"; then
      ahead="$(git rev-list --count '@{u}..HEAD')"
      behind="$(git rev-list --count 'HEAD..@{u}')"
      if [[ "$ahead" -gt 0 ]]; then
        warn "branch $BRANCH is ahead of $upstream by $ahead commit(s); PR checks do not include those commits until pushed."
      else
        pass "branch $BRANCH has no unpushed commits relative to $upstream"
      fi

      if [[ "$behind" -gt 0 ]]; then
        warn "branch $BRANCH is behind $upstream by $behind commit(s)."
      else
        pass "branch $BRANCH is not behind $upstream"
      fi
    else
      warn "branch $BRANCH has no upstream; push/merge readiness cannot compare remote state."
    fi
  else
    warn "not inside a git worktree; skipping local sync checks."
  fi
fi

tmp_dir="$(mktemp -d)"
trap 'rm -rf "$tmp_dir"' EXIT

DEFAULT_SETUP_STATE="unknown"
if [[ -n "$REPO" ]]; then
  default_setup_file="$tmp_dir/default-setup.json"
  if gh api "repos/$REPO/code-scanning/default-setup" >"$default_setup_file" 2>"$tmp_dir/default-setup.err"; then
    DEFAULT_SETUP_STATE="$(jq -r '.state // "unknown"' "$default_setup_file")"
    default_languages="$(jq -r '(.languages // []) | join(", ")' "$default_setup_file")"
    if [[ "$DEFAULT_SETUP_STATE" == "configured" ]]; then
      pass "GitHub CodeQL default setup is configured (${default_languages:-no languages reported})."
    else
      info "GitHub CodeQL default setup state is '$DEFAULT_SETUP_STATE' (only required when a ruleset requires CodeQL)."
    fi
  else
    fail "could not inspect GitHub CodeQL default setup: $(cat "$tmp_dir/default-setup.err")"
  fi
fi

if [[ -f ".github/workflows/codeql.yml" ]]; then
  if grep -q 'github/codeql-action/init' .github/workflows/codeql.yml &&
     grep -q 'github/codeql-action/analyze' .github/workflows/codeql.yml; then
    pass "local CodeQL workflow is present at .github/workflows/codeql.yml"
  else
    fail "local .github/workflows/codeql.yml does not contain both CodeQL init and analyze steps."
  fi
else
  if [[ "$DEFAULT_SETUP_STATE" == "configured" ]]; then
    pass "local CodeQL workflow file is absent; GitHub default setup is the active CodeQL provider."
  else
    info "local CodeQL workflow file is absent (only required when a ruleset requires CodeQL and default setup is unavailable)."
  fi
fi

CODEQL_REQUIRED=0
if [[ -n "$REPO" ]]; then
  rulesets_file="$tmp_dir/rulesets.json"
  if gh api "repos/$REPO/rulesets" >"$rulesets_file" 2>"$tmp_dir/rulesets.err"; then
    active_branch_rule_ids="$(jq -r '.[] | select(.target == "branch" and .enforcement == "active") | .id' "$rulesets_file")"
    if [[ -z "$active_branch_rule_ids" ]]; then
      pass "no active branch rulesets found."
    else
      while IFS= read -r ruleset_id; do
        [[ -z "$ruleset_id" ]] && continue
        detail_file="$tmp_dir/ruleset-$ruleset_id.json"
        if ! gh api "repos/$REPO/rulesets/$ruleset_id" >"$detail_file" 2>"$tmp_dir/ruleset-$ruleset_id.err"; then
          fail "could not inspect ruleset $ruleset_id: $(cat "$tmp_dir/ruleset-$ruleset_id.err")"
          continue
        fi

        ruleset_name="$(jq -r '.name' "$detail_file")"
        bypass="$(jq -r '.current_user_can_bypass // "unknown"' "$detail_file")"
        info "active branch ruleset: $ruleset_name (id $ruleset_id, bypass: $bypass)"

        if jq -e '.rules[]? | select(.type == "code_scanning") | .parameters.code_scanning_tools[]? | select(.tool == "CodeQL")' "$detail_file" >/dev/null; then
          CODEQL_REQUIRED=1
          pass "ruleset '$ruleset_name' requires CodeQL code scanning."
        fi

        if jq -e '.rules[]? | select(.type == "code_quality")' "$detail_file" >/dev/null; then
          info "ruleset '$ruleset_name' also enforces code quality."
        fi

        if jq -e '.rules[]? | select(.type == "copilot_code_review")' "$detail_file" >/dev/null; then
          info "ruleset '$ruleset_name' also requests Copilot code review."
        fi
      done <<<"$active_branch_rule_ids"
    fi
  else
    fail "could not inspect repository rulesets: $(cat "$tmp_dir/rulesets.err")"
  fi
fi

if [[ "$CODEQL_REQUIRED" -eq 1 && "$DEFAULT_SETUP_STATE" != "configured" ]]; then
  fail "an active ruleset requires CodeQL, but GitHub CodeQL default setup is not configured."
fi

if [[ "$CODEQL_REQUIRED" -eq 1 && -n "$REPO" ]]; then
  alerts_file="$tmp_dir/codeql-alerts.json"
  if gh api "repos/$REPO/code-scanning/alerts?state=open&tool_name=CodeQL" >"$alerts_file" 2>"$tmp_dir/codeql-alerts.err"; then
    alert_count="$(jq 'length' "$alerts_file")"
    if [[ "$alert_count" -gt 0 ]]; then
      fail "$alert_count open CodeQL alert(s) exist and can block protected pushes or merges:"
      jq -r '
        .[0:10][]
        | "  - #\(.number) \(.rule.id): \(.rule.description) at \(.most_recent_instance.location.path):\(.most_recent_instance.location.start_line) on \(.most_recent_instance.ref)"
      ' "$alerts_file"
    else
      pass "no open CodeQL alerts reported."
    fi
  else
    fail "could not inspect CodeQL alerts: $(cat "$tmp_dir/codeql-alerts.err")"
  fi
fi

if [[ "$SKIP_PR" -eq 0 ]]; then
  if [[ -z "$PR_NUMBER" ]]; then
    PR_NUMBER="$(gh pr view --json number --jq '.number' 2>/dev/null || true)"
  fi

  if [[ -z "$PR_NUMBER" ]]; then
    warn "no current PR found; skipping PR merge-state checks."
  else
    pr_file="$tmp_dir/pr.json"
    if ! gh pr view "$PR_NUMBER" --repo "$REPO" \
      --json number,state,isDraft,mergeable,mergeStateStatus,statusCheckRollup,url,headRefName,baseRefName \
      >"$pr_file" 2>"$tmp_dir/pr.err"; then
      fail "could not inspect PR #$PR_NUMBER: $(cat "$tmp_dir/pr.err")"
    else
      pr_url="$(jq -r '.url' "$pr_file")"
      pr_state="$(jq -r '.state' "$pr_file")"
      pr_draft="$(jq -r '.isDraft' "$pr_file")"
      pr_mergeable="$(jq -r '.mergeable // "UNKNOWN"' "$pr_file")"
      pr_merge_state="$(jq -r '.mergeStateStatus // "UNKNOWN"' "$pr_file")"
      info "PR #$PR_NUMBER: $pr_url"

      if [[ "$pr_state" != "OPEN" ]]; then
        fail "PR #$PR_NUMBER is $pr_state, not OPEN."
      fi

      if [[ "$pr_draft" == "true" ]]; then
        fail "PR #$PR_NUMBER is draft."
      fi

      if [[ "$pr_mergeable" == "CONFLICTING" ]]; then
        fail "PR #$PR_NUMBER has merge conflicts."
      elif [[ "$pr_mergeable" == "UNKNOWN" || "$pr_mergeable" == "null" ]]; then
        warn "PR #$PR_NUMBER mergeability is $pr_mergeable."
      else
        pass "PR #$PR_NUMBER mergeability is $pr_mergeable."
      fi

      case "$pr_merge_state" in
        CLEAN)
          pass "PR #$PR_NUMBER merge state is CLEAN."
          ;;
        *)
          fail "PR #$PR_NUMBER merge state is $pr_merge_state."
          ;;
      esac

      check_count="$(jq '.statusCheckRollup | length' "$pr_file")"
      if [[ "$check_count" -eq 0 ]]; then
        warn "PR #$PR_NUMBER has no reported status checks."
      else
        while IFS=$'\t' read -r check_name check_status check_result; do
          [[ -z "$check_name" ]] && continue
          case "$check_status:$check_result" in
            COMPLETED:SUCCESS|COMPLETED:NEUTRAL|COMPLETED:SKIPPED|SUCCESS:SUCCESS)
              pass "PR check '$check_name' is $check_result."
              ;;
            *)
              fail "PR check '$check_name' is status=$check_status result=$check_result."
              ;;
          esac
        done < <(
          jq -r '
            .statusCheckRollup[]
            | if .__typename == "CheckRun" then
                [.name, .status, (.conclusion // "")]
              elif .__typename == "StatusContext" then
                [.context, "COMPLETED", .state]
              else
                [(.name // .context // .__typename), (.status // "UNKNOWN"), (.conclusion // .state // "UNKNOWN")]
              end
            | @tsv
          ' "$pr_file"
        )
      fi
    fi
  fi
fi

if [[ "$FAILURES" -gt 0 ]]; then
  echo "GitHub merge readiness: FAIL ($FAILURES failure(s), $WARNINGS warning(s))."
  exit 1
fi

echo "GitHub merge readiness: PASS ($WARNINGS warning(s))."
