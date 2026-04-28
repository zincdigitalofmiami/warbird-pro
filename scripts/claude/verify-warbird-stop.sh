#!/bin/bash

set -euo pipefail

INPUT="$(cat)"

if ! command -v jq >/dev/null 2>&1; then
  printf '{"decision":"block","reason":"Warbird stop verifier requires jq in PATH."}\n'
  exit 0
fi

CWD="$(printf '%s' "$INPUT" | jq -r '.cwd // empty')"
MESSAGE="$(printf '%s' "$INPUT" | jq -r '.last_assistant_message // empty')"

if [[ -z "$CWD" || -z "$MESSAGE" ]]; then
  exit 0
fi

cd "$CWD"

block() {
  local reason="$1"
  jq -Rn --arg reason "$reason" '{decision:"block", reason:$reason}'
  exit 0
}

extract_section() {
  local start="$1"
  local end="$2"

  if [[ -z "$end" ]]; then
    printf '%s\n' "$MESSAGE" | awk -v start="$start" '
      $0 == start {flag=1; next}
      flag {print}
    '
  else
    printf '%s\n' "$MESSAGE" | awk -v start="$start" -v end="$end" '
      $0 == start {flag=1; next}
      $0 == end {flag=0}
      flag {print}
    '
  fi
}

STATUS="$(printf '%s\n' "$MESSAGE" | sed -n 's/^STATUS:[[:space:]]*//p' | head -1 | tr '[:lower:]' '[:upper:]' | xargs)"

if [[ -z "$STATUS" ]]; then
  block "Missing STATUS line. Use the Warbird completion schema from docs/agent-safety-gates.md."
fi

if [[ "$STATUS" != "COMPLETE" && "$STATUS" != "INCOMPLETE" ]]; then
  block "Invalid STATUS value '$STATUS'. Use COMPLETE or INCOMPLETE."
fi

TOUCHED_FILES_SECTION="$(extract_section "TOUCHED FILES:" "VERIFICATION:")"
VERIFICATION_SECTION="$(extract_section "VERIFICATION:" "BLOCKERS:")"
BLOCKERS_SECTION="$(extract_section "BLOCKERS:" "")"

if [[ -z "$(printf '%s' "$TOUCHED_FILES_SECTION" | tr -d '[:space:]')" ]]; then
  block "Missing TOUCHED FILES section."
fi

if [[ -z "$(printf '%s' "$VERIFICATION_SECTION" | tr -d '[:space:]')" ]]; then
  block "Missing VERIFICATION section."
fi

if [[ -z "$(printf '%s' "$BLOCKERS_SECTION" | tr -d '[:space:]')" ]]; then
  block "Missing BLOCKERS section."
fi

if [[ "$STATUS" == "COMPLETE" ]]; then
  if printf '%s\n' "$VERIFICATION_SECTION" | rg -q '^[[:space:]]*-[[:space:]]*(FAIL|NOT RUN):'; then
    block "STATUS is COMPLETE but VERIFICATION contains FAIL or NOT RUN entries."
  fi

  if ! printf '%s\n' "$BLOCKERS_SECTION" | rg -q '^[[:space:]]*-[[:space:]]*none[[:space:]]*$'; then
    block "STATUS is COMPLETE but BLOCKERS is not '- none'."
  fi
else
  if printf '%s\n' "$BLOCKERS_SECTION" | rg -q '^[[:space:]]*-[[:space:]]*none[[:space:]]*$'; then
    block "STATUS is INCOMPLETE. BLOCKERS must list the actual remaining blocker."
  fi
fi

TOUCHED_FILES=()
while IFS= read -r line; do
  [[ -z "$line" ]] && continue
  if printf '%s\n' "$line" | grep -Eiq '^none$'; then
    continue
  fi
  TOUCHED_FILES+=("$line")
done < <(
  printf '%s\n' "$TOUCHED_FILES_SECTION" |
    sed -n 's/^[[:space:]]*-[[:space:]]*//p' |
    sed '/^[[:space:]]*$/d'
)

NEED_BUILD=0
NEED_PINE=0

for file in "${TOUCHED_FILES[@]:-}"; do
  [[ -z "$file" ]] && continue

  if [[ "$file" = /* ]]; then
    file_path="$file"
  else
    file_path="$CWD/$file"
  fi

  if [[ ! -e "$file_path" ]]; then
    block "Touched file '$file' does not exist on disk."
  fi

  case "$file" in
    *.pine)
      NEED_PINE=1
      NEED_BUILD=1
      ;;
    app/*|components/*|lib/*|package.json|package-lock.json|tsconfig.json|vercel.json|next.config.*|middleware.*|supabase/*|scripts/*)
      NEED_BUILD=1
      ;;
  esac
done

if (( NEED_PINE )); then
  for file in "${TOUCHED_FILES[@]:-}"; do
    [[ "$file" != *.pine ]] && continue
    if ! ./scripts/guards/pine-lint.sh "$file" >/tmp/warbird-stop-pine-lint.log 2>&1; then
      tail -40 /tmp/warbird-stop-pine-lint.log >&2 || true
      block "Pine lint failed for $file. Fix the file or report STATUS: INCOMPLETE."
    fi
  done

  if ! ./scripts/guards/check-fib-scanner-guardrails.sh >/tmp/warbird-stop-fib-guard.log 2>&1; then
    tail -40 /tmp/warbird-stop-fib-guard.log >&2 || true
    block "Fib scanner guard failed. The banned pivot-window/barssince fibHtfSnapshot pattern was detected."
  fi

  if ! ./scripts/guards/check-contamination.sh >/tmp/warbird-stop-contamination.log 2>&1; then
    tail -40 /tmp/warbird-stop-contamination.log >&2 || true
    block "Contamination check failed. Fix the issue or report STATUS: INCOMPLETE."
  fi
fi

if (( NEED_BUILD )); then
  if ! npm run build >/tmp/warbird-stop-build.log 2>&1; then
    tail -60 /tmp/warbird-stop-build.log >&2 || true
    block "npm run build failed. Fix the build or report STATUS: INCOMPLETE."
  fi
fi

exit 0
