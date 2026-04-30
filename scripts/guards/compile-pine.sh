#!/bin/bash
# Pine Script Real Compiler Guard
#
# Calls TradingView's pine-facade /translate_light endpoint and parses the FULL
# response. The endpoint's top-level "success" boolean reports whether the API
# call succeeded — it is TRUE even when the Pine code has compile errors.
# Errors and warnings are nested at result.errors / result.warnings.
#
# This guard fails on any compile error. Warnings are reported but do not fail
# (they're often pre-existing fib-core notices). Pass --strict to fail on
# warnings too.
#
# Usage:
#   scripts/guards/compile-pine.sh <path-to-pine-file> [--strict]
#
# Exit codes:
#   0  No compile errors (warnings allowed unless --strict).
#   1  Compile errors detected, OR --strict and warnings present.
#   2  API call failed or response unparseable.

set -euo pipefail

STRICT=0
PINE_FILE=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --strict) STRICT=1; shift ;;
    --help|-h)
      sed -n '2,20p' "$0"
      exit 0
      ;;
    *)
      if [[ -z "$PINE_FILE" ]]; then
        PINE_FILE="$1"
      else
        echo "Error: unexpected arg $1" >&2
        exit 2
      fi
      shift
      ;;
  esac
done

if [[ -z "$PINE_FILE" ]]; then
  echo "Error: provide a path to a .pine file." >&2
  echo "Usage: scripts/guards/compile-pine.sh <pine-file> [--strict]" >&2
  exit 2
fi

if [[ ! -f "$PINE_FILE" ]]; then
  echo "Error: file not found: $PINE_FILE" >&2
  exit 2
fi

echo "Compiling $PINE_FILE via TradingView pine-facade API..."

pine_code=$(cat "$PINE_FILE")
RESPONSE_TMP=$(mktemp)
trap 'rm -f "$RESPONSE_TMP"' EXIT

curl -s -X POST "https://pine-facade.tradingview.com/pine-facade/translate_light?user_name=admin&v=3" \
  -H 'Referer: https://www.tradingview.com/' \
  --form-string "source=$pine_code" > "$RESPONSE_TMP"

# Hand the response file path + flags to python via env (heredoc cannot share
# stdin with a pipe).
RESPONSE_FILE="$RESPONSE_TMP" STRICT="$STRICT" PINE_FILE="$PINE_FILE" python3 <<'PYEOF'
import json, os, sys

response_file = os.environ["RESPONSE_FILE"]
strict = os.environ.get("STRICT", "0") == "1"
pine_file = os.environ.get("PINE_FILE", "<unknown>")

with open(response_file) as f:
    raw = f.read()

if not raw.strip():
    print("FAIL: pine-facade returned empty response.", file=sys.stderr)
    sys.exit(2)

try:
    data = json.loads(raw)
except Exception as exc:
    print(f"FAIL: could not parse pine-facade response: {exc}", file=sys.stderr)
    print(f"Response head: {raw[:300]}", file=sys.stderr)
    sys.exit(2)

api_success = data.get("success", False)
result = data.get("result", {}) or {}
errors = result.get("errors", []) or []
warnings = result.get("warnings", []) or []
reason = data.get("reason", "") or ""

if not api_success and not result:
    print(f"FAIL: API request failed. reason={reason[:300]}", file=sys.stderr)
    sys.exit(2)

def fmt_diagnostic(d):
    if isinstance(d, dict):
        msg = d.get("message", str(d))
        line = d.get("start", {}).get("line", "?")
        col = d.get("start", {}).get("column", "?")
        code = d.get("code", "")
        prefix = f"[{code}] " if code else ""
        return f"L{line}:{col}: {prefix}{msg}"
    return str(d)

print(f"  errors: {len(errors)} | warnings: {len(warnings)}")

for e in errors:
    print(f"  ERROR {fmt_diagnostic(e)}")

for w in warnings:
    print(f"  WARN  {fmt_diagnostic(w)}")

if errors:
    print(f"\nFAIL: {len(errors)} compile error(s) in {pine_file}.")
    sys.exit(1)

if strict and warnings:
    print(f"\nFAIL: --strict and {len(warnings)} warning(s) present in {pine_file}.")
    sys.exit(1)

if warnings:
    print(f"\nPASS: 0 errors. ({len(warnings)} warning(s) — pass without --strict.)")
else:
    print("\nPASS: 0 errors, 0 warnings.")
sys.exit(0)
PYEOF
