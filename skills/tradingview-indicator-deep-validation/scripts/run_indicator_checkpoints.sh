#!/bin/bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../" && pwd)"
INDICATOR_FILE="$ROOT_DIR/indicators/v6-warbird-complete.pine"
SKIP_PARITY=0
SKIP_BUILD=0

usage() {
  cat <<USAGE
Usage: $(basename "$0") [options]

Options:
  --indicator <path>   Indicator file to lint (default: indicators/v6-warbird-complete.pine)
  --skip-parity        Skip indicator/strategy parity check
  --skip-build         Skip npm build gate
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
  shift

  echo ""
  echo "=== $name ==="
  if "$@"; then
    echo "PASS: $name"
  else
    echo "FAIL: $name"
    FAILURES+=("$name")
  fi
}

run_step "pine-lint" "$ROOT_DIR/scripts/guards/pine-lint.sh" "$INDICATOR_FILE"
run_step "anti-contamination" "$ROOT_DIR/scripts/guards/check-contamination.sh"

if [[ "$SKIP_PARITY" -eq 0 ]]; then
  run_step "indicator-strategy-parity" "$ROOT_DIR/scripts/guards/check-indicator-strategy-parity.sh"
else
  echo ""
  echo "=== indicator-strategy-parity ==="
  echo "SKIP: indicator-strategy-parity"
fi

if [[ "$SKIP_BUILD" -eq 0 ]]; then
  run_step "npm-build" bash -lc "cd '$ROOT_DIR' && npm run build"
else
  echo ""
  echo "=== npm-build ==="
  echo "SKIP: npm-build"
fi

echo ""
echo "=== Checkpoint Summary ==="
if [[ "${#FAILURES[@]}" -eq 0 ]]; then
  echo "PASS: all executed checkpoints passed."
  exit 0
fi

printf 'FAIL: %s\n' "${FAILURES[@]}"
exit 1
