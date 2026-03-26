#!/bin/bash

set -euo pipefail

MODE="REPAIR"

detect_root() {
  if [[ -n "${WARBIRD_ROOT:-}" ]] && [[ -f "${WARBIRD_ROOT}/AGENTS.md" ]]; then
    echo "${WARBIRD_ROOT}"
    return 0
  fi

  if git_root="$(git rev-parse --show-toplevel 2>/dev/null)"; then
    if [[ -f "${git_root}/AGENTS.md" ]]; then
      echo "${git_root}"
      return 0
    fi
  fi

  if [[ -f "$(pwd)/AGENTS.md" ]]; then
    echo "$(pwd)"
    return 0
  fi

  echo "$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../.." && pwd)"
}

ROOT_DIR="$(detect_root)"
INDICATOR_FILE="$ROOT_DIR/indicators/v6-warbird-complete.pine"
SKIP_PARITY=0
SKIP_BUILD=0
DRY_RUN=0

if [[ ! -x "$ROOT_DIR/scripts/guards/pine-lint.sh" ]]; then
  echo "ERROR: Could not resolve Warbird repo root. Set WARBIRD_ROOT or run from repo root."
  exit 2
fi

usage() {
  cat <<USAGE
Usage: $(basename "$0") [options]

Options:
  --indicator <path>   Indicator file to lint (default: indicators/v6-warbird-complete.pine)
  --skip-parity        Skip indicator/strategy parity check
  --skip-build         Skip npm build gate
  --dry-run            Print planned commands and exit
  --help               Show this help
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --indicator)
      INDICATOR_FILE="$2"
      shift 2
      ;;
    --skip-parity)
      SKIP_PARITY=1
      shift
      ;;
    --skip-build)
      SKIP_BUILD=1
      shift
      ;;
    --dry-run)
      DRY_RUN=1
      shift
      ;;
    --help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1"
      usage
      exit 2
      ;;
  esac
done

declare -a FAILURES=()

run_step() {
  local name="$1"
  local cmd="$2"

  echo ""
  echo "=== $name ==="
  if [[ "$DRY_RUN" -eq 1 ]]; then
    echo "DRY-RUN: $cmd"
    return 0
  fi

  if bash -lc "$cmd"; then
    echo "PASS: $name"
  else
    echo "FAIL: $name"
    FAILURES+=("$name")
  fi
}

run_step "pine-lint" "'$ROOT_DIR/scripts/guards/pine-lint.sh' '$INDICATOR_FILE'"
run_step "anti-contamination" "'$ROOT_DIR/scripts/guards/check-contamination.sh'"

if [[ "$SKIP_PARITY" -eq 0 ]]; then
  run_step "indicator-strategy-parity" "'$ROOT_DIR/scripts/guards/check-indicator-strategy-parity.sh'"
else
  echo ""
  echo "=== indicator-strategy-parity ==="
  echo "SKIP: indicator-strategy-parity"
fi

if [[ "$SKIP_BUILD" -eq 0 ]]; then
  run_step "npm-build" "cd '$ROOT_DIR' && npm run build"
else
  echo ""
  echo "=== npm-build ==="
  echo "SKIP: npm-build"
fi

echo ""
echo "=== $MODE Checkpoint Summary ==="
if [[ "$DRY_RUN" -eq 1 ]]; then
  echo "DRY-RUN complete: no commands executed."
  exit 0
fi

if [[ "${#FAILURES[@]}" -eq 0 ]]; then
  echo "PASS: all executed checkpoints passed."
  exit 0
fi

printf 'FAIL: %s\n' "${FAILURES[@]}"
exit 1
