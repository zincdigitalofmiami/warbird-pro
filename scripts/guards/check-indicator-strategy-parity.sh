#!/bin/bash
# Check v7 parity between indicator and strategy Pine surfaces.
# Verifies:
#   1. Hidden ml_* export field names match
#   2. Plot budget is within TradingView's 64 hard cap
#   3. Core contract lines match (stop family, archetype, event codes)
#   4. Coupled input defaults match (strategy is source of truth)
#   5. Strategy execution primitives are present
#   6. Strategy pins hostile TV defaults (bar magnifier, commission, slippage)

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
INDICATOR_FILE="$ROOT_DIR/indicators/v7-warbird-institutional.pine"
STRATEGY_FILE="$ROOT_DIR/indicators/v7-warbird-strategy.pine"

echo "=== Warbird v7 Indicator/Strategy Parity Check ==="

if [[ ! -f "$INDICATOR_FILE" ]]; then
    echo "FAIL: Missing indicator file: $INDICATOR_FILE"
    exit 1
fi

if [[ ! -f "$STRATEGY_FILE" ]]; then
    echo "FAIL: Missing strategy file: $STRATEGY_FILE"
    exit 1
fi

TMP_DIR="$ROOT_DIR/.tmp/parity"
mkdir -p "$TMP_DIR"

FAIL=0

extract_ml_fields() {
    local source_file="$1"
    local out_file="$2"
    rg -o '"ml_[^"]+"' "$source_file" | tr -d '"' | sort -u > "$out_file"
}

count_plot_calls() {
    local source_file="$1"
    rg 'plot(shape|char|arrow|bar|candle)?\(' "$source_file" | rg -v '^\s*//' | wc -l | tr -d ' '
}

# ── 1. Hidden ml_* export field parity ──
extract_ml_fields "$INDICATOR_FILE" "$TMP_DIR/ml_indicator.txt"
extract_ml_fields "$STRATEGY_FILE" "$TMP_DIR/ml_strategy.txt"

if ! diff -u "$TMP_DIR/ml_indicator.txt" "$TMP_DIR/ml_strategy.txt" > "$TMP_DIR/ml_diff.txt"; then
    echo "FAIL: Hidden export field mismatch between indicator and strategy"
    sed -n '1,120p' "$TMP_DIR/ml_diff.txt"
    FAIL=1
else
    ML_FIELD_COUNT=$(wc -l < "$TMP_DIR/ml_indicator.txt" | tr -d '[:space:]')
    echo "INFO: Hidden export fields match (${ML_FIELD_COUNT} fields)"
fi

# ── 2. Plot budget ──
INDICATOR_PLOT_COUNT=$(count_plot_calls "$INDICATOR_FILE")
STRATEGY_PLOT_COUNT=$(count_plot_calls "$STRATEGY_FILE")
echo "INFO: Total plot-style calls -> indicator=${INDICATOR_PLOT_COUNT}, strategy=${STRATEGY_PLOT_COUNT}"

if [[ "$INDICATOR_PLOT_COUNT" -gt 64 ]]; then
    echo "FAIL: Indicator exceeds TradingView's 64 plot-count cap (${INDICATOR_PLOT_COUNT}/64)"
    FAIL=1
fi

if [[ "$STRATEGY_PLOT_COUNT" -gt 64 ]]; then
    echo "FAIL: Strategy exceeds TradingView's 64 plot-count cap (${STRATEGY_PLOT_COUNT}/64)"
    FAIL=1
fi

# ── 3. Core contract line parity (indicator == strategy) ──
compare_contract_line() {
    local pattern="$1"
    local label="$2"
    local indicator_out="$TMP_DIR/indicator_${label}.txt"
    local strategy_out="$TMP_DIR/strategy_${label}.txt"

    rg --no-filename --no-line-number "$pattern" "$INDICATOR_FILE" > "$indicator_out" 2>/dev/null || true
    rg --no-filename --no-line-number "$pattern" "$STRATEGY_FILE" > "$strategy_out" 2>/dev/null || true

    if ! diff -u "$indicator_out" "$strategy_out" > "$TMP_DIR/diff_${label}.txt"; then
        echo "FAIL: Contract drift for $label"
        sed -n '1,80p' "$TMP_DIR/diff_${label}.txt"
        FAIL=1
    fi
}

compare_contract_line '^int stopFamilyCode =' 'stop_family'
compare_contract_line '^int setupArchetypeCode =' 'setup_archetype'
compare_contract_line '^int eventPivotInteractionCode =' 'pivot_interaction'
compare_contract_line '^float mlExhZScore =' 'exh_z_score'
compare_contract_line '^bool mlExhZeroPrint =' 'exh_zero_print'
compare_contract_line '^int mlContConfidenceTier' 'cont_confidence_tier'

# ── 4. Coupled input defaults (strategy is source of truth) ──
check_input_default() {
    local pattern="$1"
    local label="$2"

    local ind_val strat_val
    ind_val=$(rg -o "$pattern" "$INDICATOR_FILE" | head -1 || true)
    strat_val=$(rg -o "$pattern" "$STRATEGY_FILE" | head -1 || true)

    if [[ -z "$ind_val" || -z "$strat_val" ]]; then
        echo "FAIL: Input default not found for $label (ind='$ind_val' strat='$strat_val')"
        FAIL=1
    elif [[ "$ind_val" != "$strat_val" ]]; then
        echo "FAIL: Input default mismatch for $label (ind='$ind_val' strat='$strat_val')"
        FAIL=1
    else
        echo "INFO: Input default OK: $label = $strat_val"
    fi
}

check_input_default 'footprintTicksPerRow = input.int\([0-9]+' 'footprintTicksPerRow'
check_input_default 'footprintVaPercent = input.float\([0-9.]+' 'footprintVaPercent'
check_input_default 'footprintImbalancePercent = input.float\([0-9.]+' 'footprintImbalancePercent'
check_input_default 'exhaustionZLen = input.int\([0-9]+' 'exhaustionZLen'
check_input_default 'exhaustionZThreshold = input.float\([0-9.]+' 'exhaustionZThreshold'
check_input_default 'zeroPrintVolRatio = input.float\([0-9.]+' 'zeroPrintVolRatio'
check_input_default 'stackedImbalanceRows = input.int\([0-9]+' 'stackedImbalanceRows'
check_input_default 'continuationHoldBars = input.int\([0-9]+' 'continuationHoldBars'
check_input_default 'continuationHoldStopAtrMult = input.float\([0-9.]+' 'continuationHoldStopAtrMult'
check_input_default 'shortTrendGateAdx = input.float\([0-9.]+' 'shortTrendGateAdx'
check_input_default 'exhAtrMult = input.float\([0-9.]+' 'exhAtrMult'
check_input_default '"ATR_1_5", "Fallback Stop Family"' 'stopFamilyId_default'

# ── 5. Strategy execution primitives ──
for required in \
    'strategy\.entry\("Long", strategy\.long\)' \
    'strategy\.entry\("Short", strategy\.short\)' \
    'strategy\.exit\("Long Exit"' \
    'strategy\.exit\("Short Exit"' \
    '^bool canTradeBar =' \
    '^bool strategyLongEntry =' \
    '^bool strategyShortEntry ='
do
    if ! rg -q "$required" "$STRATEGY_FILE"; then
        echo "FAIL: Strategy execution primitive missing: $required"
        FAIL=1
    fi
done

# ── 6. Strategy must pin hostile TV defaults ──
for pinned in \
    'use_bar_magnifier=true' \
    'commission_value=1\.00' \
    'slippage=1'
do
    if ! rg -q "$pinned" "$STRATEGY_FILE"; then
        echo "FAIL: Strategy missing pinned TV default: $pinned"
        FAIL=1
    fi
done

if [[ "$FAIL" -eq 0 ]]; then
    echo "PASS: v7 indicator/strategy parity checks passed."
else
    echo "FAIL: One or more parity checks failed."
    exit 1
fi

echo "=== Check Complete ==="
