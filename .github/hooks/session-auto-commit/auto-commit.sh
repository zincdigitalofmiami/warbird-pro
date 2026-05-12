#!/bin/bash

# Session Git Status Hook
# Reports pending changes when a Copilot session ends.

set -euo pipefail

# Check if SKIP_AUTO_COMMIT is set. The variable name is retained so older
# hook configuration can disable this report-only hook without churn.
if [[ "${SKIP_AUTO_COMMIT:-}" == "true" ]]; then
  echo "Auto-commit skipped (SKIP_AUTO_COMMIT=true)"
  exit 0
fi

# Check if we're in a git repository
if ! git rev-parse --is-inside-work-tree &>/dev/null; then
  echo "Not in a git repository"
  exit 0
fi

# Check for uncommitted changes
if [[ -z "$(git status --porcelain)" ]]; then
  echo "No pending git changes"
  exit 0
fi

echo "Pending git changes after Copilot session:"
git status --short

exit 0
