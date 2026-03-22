#!/bin/bash
# Anti-contamination check: ensure no Rabid Raccoon data/code paths leak into training
# Run before any AG training or dataset build

set -e

echo "=== Warbird Anti-Contamination Check ==="

# Check for rabid-raccoon RUNTIME references (imports, data paths) in active code
# Exclude comment-only matches (lines starting with // or # or * after whitespace)
HITS=$(grep -rn "rabid.raccoon\|rabid_raccoon\|/rabid-raccoon/" scripts/ lib/ app/ --include="*.py" --include="*.ts" --include="*.tsx" 2>/dev/null | grep -v node_modules | grep -v archive | grep -v '^\s*[/#*]' | grep -v '^\([^:]*:[0-9]*:\s*//\)' | grep -v '^\([^:]*:[0-9]*:\s*#\)' | grep -v '^\([^:]*:[0-9]*:\s*\*\)' || true)

if [ -n "$HITS" ]; then
    echo "FAIL: Rabid Raccoon runtime references found in active code:"
    echo "$HITS"
    exit 1
fi

# Known safe comment-only references (documented in legacy-lineage-audit.md):
#   lib/setup-engine.ts:7    — "Ported from rabid-raccoon" comment
#   lib/fibonacci.ts:23      — "Matches rabid-raccoon.pine" comment

# Check for cross-project data paths in scripts (non-comment)
DATA_HITS=$(grep -rn "/rabid-raccoon/\|rabid.raccoon" scripts/ --include="*.py" --include="*.ts" 2>/dev/null | grep -v '^\([^:]*:[0-9]*:\s*[/#*]\)' || true)

if [ -n "$DATA_HITS" ]; then
    echo "FAIL: Cross-project data paths found:"
    echo "$DATA_HITS"
    exit 1
fi

echo "PASS: No cross-project contamination detected."
echo "=== Check Complete ==="
