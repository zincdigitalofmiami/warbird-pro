#!/usr/bin/env bash
# Canonical full zoo guard.
#
# Refuses to pass if scripts/ag/train_ag_baseline.py's CANONICAL_ZOO does not
# contain all 7 required model families, OR if the module-level assertion has
# been removed. Pairs with .githooks/commit-msg, which can override via
# ZOO_CHANGE_APPROVED: token in the commit message (type it intentionally).
#
# Callable directly: ./scripts/guards/check-canonical-zoo.sh
# Exit codes: 0 OK, 1 drift, 2 trainer missing / cwd wrong.
set -euo pipefail

TRAINER="scripts/ag/train_ag_baseline.py"
REQUIRED_FAMILIES=(GBM CAT XGB RF XT NN_TORCH FASTAI)

if [[ ! -f "$TRAINER" ]]; then
  echo "check-canonical-zoo: $TRAINER not found (wrong cwd?)" >&2
  exit 2
fi

# 1. Assertion must still be present and invoked at module level.
if ! grep -q "^_assert_canonical_zoo()" "$TRAINER"; then
  echo "check-canonical-zoo: _assert_canonical_zoo() call is missing from $TRAINER" >&2
  echo "check-canonical-zoo: the module-level invocation is the import-time drift guard." >&2
  exit 1
fi

# 2. Each family must appear as a quoted key in the file.
missing=()
for fam in "${REQUIRED_FAMILIES[@]}"; do
  if ! grep -qE "\"$fam\"[[:space:]]*:" "$TRAINER"; then
    missing+=("$fam")
  fi
done

if (( ${#missing[@]} > 0 )); then
  echo "check-canonical-zoo: CANONICAL_ZOO is missing families: ${missing[*]}" >&2
  echo "check-canonical-zoo: full zoo (GBM, CAT, XGB, RF, XT, NN_TORCH, FASTAI) is mandatory on this project." >&2
  echo "check-canonical-zoo: override only via ZOO_CHANGE_APPROVED: in commit message." >&2
  exit 1
fi

echo "check-canonical-zoo: CANONICAL_ZOO contains all 7 required families — OK"
exit 0
