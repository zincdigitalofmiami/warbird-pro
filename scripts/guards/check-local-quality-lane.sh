#!/usr/bin/env bash
# Single deterministic local quality lane for Codex/Claude-owned checks.

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"

echo "INFO: running local quality lane in $ROOT_DIR"

# Detect changed files (prefer staged set; fallback to working tree diff).
CHANGED_FILES=()
while IFS= read -r line; do
  [[ -n "$line" ]] && CHANGED_FILES+=("$line")
done < <(git diff --cached --name-only --diff-filter=ACMR)

if [[ "${#CHANGED_FILES[@]}" -eq 0 ]]; then
  while IFS= read -r line; do
    [[ -n "$line" ]] && CHANGED_FILES+=("$line")
  done < <(git diff --name-only --diff-filter=ACMR)
  while IFS= read -r line; do
    [[ -n "$line" ]] && CHANGED_FILES+=("$line")
  done < <(git ls-files --others --exclude-standard)
fi

if [[ "${#CHANGED_FILES[@]}" -eq 0 ]]; then
  echo "INFO: no changed files detected; running baseline checks anyway."
else
  echo "INFO: changed files:"
  printf '  - %s\n' "${CHANGED_FILES[@]}"
fi

echo "CHECK: git whitespace safety"
if ! git diff --cached --quiet --exit-code; then
  git diff --cached --check
fi
git diff --check

echo "CHECK: changed-file syntax"
if [[ "${#CHANGED_FILES[@]}" -gt 0 ]]; then
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
fi

echo "CHECK: npm lint"
npm run lint

echo "CHECK: npm build"
npm run build

echo "CHECK: Warbird V9 contract tests"
python3 -m pytest tests/optuna/test_warbird_pro_v9_contract.py -q

echo "CHECK: tuner jsonl safety tests"
python3 -m pytest scripts/ag/test_tuner.py -k "load_trials_jsonl_csv_full_includes_tv_mcp_strict or load_history_jsonl_filters_by_profile" -q

echo "CHECK: repository contamination guard"
./scripts/guards/check-contamination.sh

echo "CHECK: TradingView force-launch guard"
./scripts/guards/check-no-tv-force.sh

echo "CHECK: canonical zoo guard"
./scripts/guards/check-canonical-zoo.sh

echo "CHECK: fib scanner regression guard"
./scripts/guards/check-fib-scanner-guardrails.sh

# Pine guard routing only when Pine sources changed.
PINE_CHANGED=0
if [[ "${#CHANGED_FILES[@]}" -gt 0 ]]; then
  for file in "${CHANGED_FILES[@]}"; do
    if [[ "$file" == *.pine ]]; then
      PINE_CHANGED=1
      break
    fi
  done
fi

if [[ "$PINE_CHANGED" -eq 1 ]]; then
  echo "CHECK: Pine guards (changed Pine files detected)"
  for file in "${CHANGED_FILES[@]}"; do
    if [[ "$file" == *.pine ]]; then
      ./scripts/guards/compile-pine.sh "$file"
      ./scripts/guards/pine-lint.sh "$file"
    fi
  done
else
  echo "INFO: no changed Pine files; skipping Pine-specific guards."
fi

echo "PASS: local quality lane complete"
