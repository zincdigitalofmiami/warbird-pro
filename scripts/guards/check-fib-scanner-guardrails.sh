#!/bin/bash
# Guardrail: block known wide-fib regression pattern in fibHtfSnapshot().
# This specifically bans the pivot-window + barssince variant that has
# repeatedly broken Warbird fib geometry.

set -euo pipefail

echo "=== Warbird Fib Scanner Guardrails ==="

pine_files=()
while IFS= read -r line; do
    [ -n "$line" ] && pine_files+=("$line")
done < <(rg -l '^fibHtfSnapshot\(.*=>\s*$' indicators/*.pine 2>/dev/null || true)

if [ ${#pine_files[@]} -eq 0 ]; then
    echo "INFO: No fibHtfSnapshot() definitions found under indicators/*.pine."
    echo "PASS: Fib scanner guardrails satisfied."
    exit 0
fi

for file in "${pine_files[@]}"; do
    block="$(
        awk '
            /^fibHtfSnapshot\(.*=>[[:space:]]*$/ {in_block=1}
            in_block {print}
            in_block && /^[[:space:]]*\[.*\][[:space:]]*$/ {in_block=0}
        ' "$file"
    )"

    [ -z "$block" ] && continue

    if printf '%s\n' "$block" | rg -n 'ta\.barssince\(|pivotHighInWindow|pivotLowInWindow|ta\.valuewhen\(hasPivotHigh|ta\.valuewhen\(hasPivotLow' >/tmp/warbird-fib-guard-hit.log 2>&1; then
        echo "FAIL: Forbidden fib scanner pattern detected in $file"
        echo "The pivot-window/barssince variant is banned because it causes wide-fib regressions."
        cat /tmp/warbird-fib-guard-hit.log
        exit 1
    fi
done

echo "PASS: Fib scanner guardrails satisfied."
echo "=== Check Complete ==="
