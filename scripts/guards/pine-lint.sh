#!/bin/bash
# Pine Script v6 static analysis guard
# Run before pasting into TradingView to catch common issues
# Usage: ./scripts/guards/pine-lint.sh [indicators/v7-warbird-institutional.pine]

set -e

FILE="${1:-indicators/v7-warbird-institutional.pine}"

if [ ! -f "$FILE" ]; then
    echo "FAIL: File not found: $FILE"
    exit 1
fi

echo "=== Pine Script Lint: $FILE ==="
echo "Lines: $(wc -l < "$FILE")"
ERRORS=0
WARNINGS=0

# --- ERRORS (will not compile) ---

# E1: ta.highestbars/ta.lowestbars inside ternary operators
# These must be pre-computed at global scope
TERNARY_TA=$(grep -n '? ta\.highestbars\|? ta\.lowestbars\|? ta\.highest(\|? ta\.lowest(' "$FILE" 2>/dev/null || true)
if [ -n "$TERNARY_TA" ]; then
    echo "ERROR [E1]: ta.* series function inside ternary operator:"
    echo "$TERNARY_TA"
    ERRORS=$((ERRORS + 1))
fi

# E2: Function definition with typed params inside if block
# Pine doesn't allow this — must be at global scope
FUNC_IN_IF=$(grep -n '^\s\+[a-zA-Z_]*(.* int \| float \| bool \| string \| color ).*) =>' "$FILE" 2>/dev/null | grep -v '^[^ ]' || true)
if [ -n "$FUNC_IN_IF" ]; then
    echo "ERROR [E2]: Function with typed params possibly inside if block:"
    echo "$FUNC_IN_IF"
    ERRORS=$((ERRORS + 1))
fi

# E3: Undeclared forward references in functions
# Check if htfConfluenceCheck references fibRange directly (not as param)
FORWARD_REF=$(grep -A 20 'htfConfluenceCheck(' "$FILE" | head -25 | grep -w 'fibRange' | grep -v 'currentFibRange\|// ' || true)
if [ -n "$FORWARD_REF" ]; then
    echo "ERROR [E3]: htfConfluenceCheck references fibRange directly (should be parameter):"
    echo "$FORWARD_REF"
    ERRORS=$((ERRORS + 1))
fi

# --- WARNINGS (may cause issues) ---

# W1: request.security() budget
SEC_COUNT=$(grep -c 'request\.security(' "$FILE" 2>/dev/null || echo 0)
# Subtract comment-only lines
SEC_COMMENT=$(grep 'request\.security(' "$FILE" | grep '^\s*//' | wc -l | tr -d ' ')
SEC_ACTUAL=$((SEC_COUNT - SEC_COMMENT))
echo "INFO: request.security() calls: $SEC_ACTUAL (budget: 40)"
if [ "$SEC_ACTUAL" -gt 30 ]; then
    echo "WARNING [W1]: request.security() budget > 75% ($SEC_ACTUAL/40)"
    WARNINGS=$((WARNINGS + 1))
fi

# W2: barstate.isconfirmed missing on structure conditions
# Check breakInDir, acceptInDir, rejectAtZone, breakAgainst
# Look at the assignment line AND the next 3 lines for isconfirmed
for VAR in breakInDir acceptInDir rejectAtZone breakAgainst; do
    LINE_NUM=$(grep -n "^$VAR \|^ $VAR " "$FILE" 2>/dev/null | head -1 | cut -d: -f1 || true)
    if [ -n "$LINE_NUM" ]; then
        CONTEXT=$(sed -n "${LINE_NUM},$((LINE_NUM + 3))p" "$FILE")
        if ! echo "$CONTEXT" | grep -q 'barstate.isconfirmed'; then
            echo "WARNING [W2]: $VAR may lack barstate.isconfirmed gate (line $LINE_NUM)"
            WARNINGS=$((WARNINGS + 1))
        fi
    fi
done

# W3: var declarations inside if blocks (potential scope issue)
VAR_IN_IF=$(grep -n '^\s\+var ' "$FILE" 2>/dev/null | grep -v '^\s*//\|^[^ ]' || true)
if [ -n "$VAR_IN_IF" ]; then
    echo "WARNING [W3]: var declarations inside indented blocks (may be intentional):"
    echo "$VAR_IN_IF" | head -5
    WARNINGS=$((WARNINGS + 1))
fi

# W4: plot() without display parameter (visible on chart)
VISIBLE_PLOTS=$(grep -n 'plot(' "$FILE" | grep -Ev 'display[[:space:]]*=' | grep -v '//' | grep -v 'plotshape' || true)
if [ -n "$VISIBLE_PLOTS" ]; then
    echo "WARNING [W4]: plot() calls without display= (visible on chart):"
    echo "$VISIBLE_PLOTS" | head -5
    WARNINGS=$((WARNINGS + 1))
fi

# W9/E9: TradingView output-count budget
# Official TradingView hard cap is 64 outputs per script. Outputs include:
# plot(), plotshape(), plotchar(), plotarrow(), plotbar(), plotcandle(),
# bgcolor(), fill(), hline(), AND alertcondition().
# Hidden display.none plots still count. All alertcondition() calls count.
# Note: bgcolor/fill/hline regexes exclude method calls like .set_bgcolor()
PLOT_RAW=$(grep -E -c 'plot(shape|char|arrow|bar|candle)?\(' "$FILE" 2>/dev/null) || PLOT_RAW=0
PLOT_COMMENT=$(grep -E 'plot(shape|char|arrow|bar|candle)?\(' "$FILE" 2>/dev/null | grep -c '^\s*//' 2>/dev/null) || PLOT_COMMENT=0
PLOT_ACTUAL=$((PLOT_RAW - PLOT_COMMENT))
BG_RAW=$(grep -E -c '(^|[[:space:]])bgcolor\(' "$FILE" 2>/dev/null) || BG_RAW=0
BG_COMMENT=$(grep -E '(^|[[:space:]])bgcolor\(' "$FILE" 2>/dev/null | grep -c '^\s*//' 2>/dev/null) || BG_COMMENT=0
BG_ACTUAL=$((BG_RAW - BG_COMMENT))
FILL_RAW=$(grep -E -c '(^|[[:space:]])fill\(' "$FILE" 2>/dev/null) || FILL_RAW=0
FILL_COMMENT=$(grep -E '(^|[[:space:]])fill\(' "$FILE" 2>/dev/null | grep -c '^\s*//' 2>/dev/null) || FILL_COMMENT=0
FILL_ACTUAL=$((FILL_RAW - FILL_COMMENT))
HLINE_RAW=$(grep -E -c '(^|[[:space:]])hline\(' "$FILE" 2>/dev/null) || HLINE_RAW=0
HLINE_COMMENT=$(grep -E '(^|[[:space:]])hline\(' "$FILE" 2>/dev/null | grep -c '^\s*//' 2>/dev/null) || HLINE_COMMENT=0
HLINE_ACTUAL=$((HLINE_RAW - HLINE_COMMENT))
ALERT_RAW=$(grep -E -c 'alertcondition\(' "$FILE" 2>/dev/null) || ALERT_RAW=0
ALERT_COMMENT=$(grep -E 'alertcondition\(' "$FILE" 2>/dev/null | grep -c '^\s*//' 2>/dev/null) || ALERT_COMMENT=0
ALERT_ACTUAL=$((ALERT_RAW - ALERT_COMMENT))
OUTPUT_TOTAL=$((PLOT_ACTUAL + BG_ACTUAL + FILL_ACTUAL + HLINE_ACTUAL + ALERT_ACTUAL))
echo "INFO: output calls: $OUTPUT_TOTAL (plot=$PLOT_ACTUAL bg=$BG_ACTUAL fill=$FILL_ACTUAL hline=$HLINE_ACTUAL alert=$ALERT_ACTUAL) (TradingView hard cap: 64)"
if [ "$OUTPUT_TOTAL" -gt 64 ]; then
    echo "ERROR [E9]: output count exceeds TradingView hard cap ($OUTPUT_TOTAL/64)"
    ERRORS=$((ERRORS + 1))
elif [ "$OUTPUT_TOTAL" -gt 48 ]; then
    echo "WARNING [W9]: output count above 75% of TradingView hard cap ($OUTPUT_TOTAL/64)"
    WARNINGS=$((WARNINGS + 1))
fi

# W5: alertcondition() inside if block (must be at global scope)
ALERT_INDENTED=$(grep -n '^\s\+alertcondition(' "$FILE" 2>/dev/null || true)
if [ -n "$ALERT_INDENTED" ]; then
    echo "ERROR [E5]: alertcondition() inside indented block (must be global scope):"
    echo "$ALERT_INDENTED"
    ERRORS=$((ERRORS + 1))
fi

# W6: riskOn/riskOff contradiction check
RISK_ON_BASE=$(grep 'riskOnBase.*=.*not useIntermarket' "$FILE" || true)
RISK_OFF_BASE=$(grep 'riskOffBase.*=.*not useIntermarket' "$FILE" || true)
if [ -n "$RISK_ON_BASE" ] && [ -n "$RISK_OFF_BASE" ]; then
    echo "WARNING [W6]: riskOnBase/riskOffBase both true when useIntermarket=false (known contradiction)"
    WARNINGS=$((WARNINGS + 1))
fi

# W7: max_boxes_count check
MAX_BOXES=$(grep 'max_boxes_count' "$FILE" | grep -oE '[0-9]+' | tail -1 || echo "0")
BOX_NEWS=$(grep -c 'box\.new(' "$FILE" 2>/dev/null || echo 0)
echo "INFO: max_boxes_count=$MAX_BOXES, box.new() calls=$BOX_NEWS"

# W8: import statement present for ZigZag
if grep -q 'zigzag\.' "$FILE" && ! grep -q 'import TradingView/ZigZag' "$FILE"; then
    echo "ERROR [E8]: Uses zigzag.* but missing import TradingView/ZigZag"
    ERRORS=$((ERRORS + 1))
fi

# --- SUMMARY ---
echo ""
echo "=== Lint Summary ==="
echo "Errors:   $ERRORS"
echo "Warnings: $WARNINGS"

if [ "$ERRORS" -gt 0 ]; then
    echo "FAIL: Fix errors before pasting into TradingView"
    exit 1
fi

if [ "$WARNINGS" -gt 0 ]; then
    echo "PASS with warnings"
    exit 0
fi

echo "PASS: Clean"
exit 0
