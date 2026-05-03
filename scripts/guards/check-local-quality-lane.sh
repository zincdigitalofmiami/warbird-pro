#!/usr/bin/env bash
# Scoped deterministic local quality lane for Warbird repo checks.

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"

SCOPE="auto"
BASE_REF=""
INTENSITY="full"

usage() {
  cat <<'USAGE'
Usage: scripts/guards/check-local-quality-lane.sh [--scope staged|worktree|range|auto] [--base-ref REF] [--fast|--full]

--fast checks whitespace, changed-file syntax, deterministic repo guards, and
       Pine compile/lint when Pine files are in scope.
--full runs --fast plus npm lint, npm build, and targeted pytest checks.
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --scope)
      SCOPE="${2:-}"
      shift 2
      ;;
    --base-ref)
      BASE_REF="${2:-}"
      shift 2
      ;;
    --fast)
      INTENSITY="fast"
      shift
      ;;
    --full)
      INTENSITY="full"
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

case "$SCOPE" in
  staged|worktree|range|auto) ;;
  *)
    echo "FAIL: invalid scope '$SCOPE'"
    usage
    exit 2
    ;;
esac

case "$INTENSITY" in
  fast|full) ;;
  *)
    echo "FAIL: invalid intensity '$INTENSITY'"
    usage
    exit 2
    ;;
esac

append_file() {
  local file="$1"
  [[ -n "$file" ]] || return 0
  CHANGED_FILES+=("$file")
}

collect_from_command() {
  local line
  while IFS= read -r line; do
    append_file "$line"
  done < <("$@")
}

collect_changed_files() {
  CHANGED_FILES=()

  case "$SCOPE" in
    staged)
      collect_from_command git diff --cached --name-only --diff-filter=ACMR
      ;;
    worktree)
      collect_from_command git diff --name-only --diff-filter=ACMR
      collect_from_command git ls-files --others --exclude-standard
      ;;
    range)
      [[ -n "$BASE_REF" ]] || {
        echo "FAIL: --scope range requires --base-ref"
        exit 2
      }
      collect_from_command git diff --name-only --diff-filter=ACMR "$BASE_REF"...HEAD
      ;;
    auto)
      collect_from_command git diff --cached --name-only --diff-filter=ACMR
      if [[ "${#CHANGED_FILES[@]}" -eq 0 ]]; then
        collect_from_command git diff --name-only --diff-filter=ACMR
        collect_from_command git ls-files --others --exclude-standard
      fi
      ;;
  esac
}

run_git_whitespace_check() {
  echo "CHECK: git whitespace safety"
  case "$SCOPE" in
    staged)
      git diff --cached --check
      ;;
    worktree)
      git diff --check
      ;;
    range)
      git diff --check "$BASE_REF"...HEAD
      ;;
    auto)
      if ! git diff --cached --quiet --exit-code; then
        git diff --cached --check
      else
        git diff --check
      fi
      ;;
  esac
}

run_syntax_checks() {
  echo "CHECK: changed-file syntax"
  if [[ "${#CHANGED_FILES[@]}" -eq 0 ]]; then
    echo "INFO: no changed files in scope; skipping changed-file syntax checks."
    return 0
  fi

  local file
  for file in "${CHANGED_FILES[@]}"; do
    [[ -f "$file" ]] || continue
    case "$file" in
      *.sh|*.bash|*.zsh|.githooks/*)
        bash -n "$file"
        ;;
      *.py)
        python3 -m py_compile "$file"
        ;;
      *.json)
        python3 -m json.tool "$file" >/dev/null
        ;;
    esac
  done
}

run_deterministic_repo_guards() {
  echo "CHECK: repository contamination guard"
  ./scripts/guards/check-contamination.sh

  echo "CHECK: TradingView force-launch guard"
  ./scripts/guards/check-no-tv-force.sh

  echo "CHECK: canonical zoo guard"
  ./scripts/guards/check-canonical-zoo.sh

  echo "CHECK: fib scanner regression guard"
  ./scripts/guards/check-fib-scanner-guardrails.sh
}

run_pine_guards_if_needed() {
  local pine_files=()
  local file

  if [[ "${#CHANGED_FILES[@]}" -gt 0 ]]; then
    for file in "${CHANGED_FILES[@]}"; do
      if [[ "$file" == *.pine && -f "$file" ]]; then
        pine_files+=("$file")
      fi
    done
  fi

  if [[ "${#pine_files[@]}" -eq 0 ]]; then
    echo "INFO: no changed Pine files in scope; skipping Pine-specific guards."
    return 0
  fi

  echo "CHECK: Pine compile/lint for changed Pine files"
  for file in "${pine_files[@]}"; do
    ./scripts/guards/compile-pine.sh "$file"
    ./scripts/guards/pine-lint.sh "$file"
  done
}

run_full_checks() {
  echo "CHECK: npm lint"
  npm run lint

  echo "CHECK: npm build"
  npm run build

  echo "CHECK: Warbird V9 contract tests"
  python3 -m pytest tests/optuna/test_warbird_pro_v9_contract.py -q

  echo "CHECK: tuner jsonl safety tests"
  python3 -m pytest scripts/ag/test_tuner.py -k "load_trials_jsonl_csv_full_includes_tv_mcp_strict or load_history_jsonl_filters_by_profile" -q
}

collect_changed_files

echo "INFO: running local quality lane in $ROOT_DIR"
echo "INFO: scope=$SCOPE intensity=$INTENSITY"
if [[ -n "$BASE_REF" ]]; then
  echo "INFO: base_ref=$BASE_REF"
fi

if [[ "${#CHANGED_FILES[@]}" -eq 0 ]]; then
  echo "INFO: no changed files detected for this scope; running baseline guards."
else
  echo "INFO: changed files:"
  printf '  - %s\n' "${CHANGED_FILES[@]}"
fi

run_git_whitespace_check
run_syntax_checks
run_deterministic_repo_guards
run_pine_guards_if_needed

if [[ "$INTENSITY" == "full" ]]; then
  run_full_checks
else
  echo "INFO: fast lane selected; skipping npm build/lint and pytest."
fi

echo "PASS: local quality lane complete"
