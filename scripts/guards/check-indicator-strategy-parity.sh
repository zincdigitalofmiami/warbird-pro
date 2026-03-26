#!/bin/bash
# Check Phase 3 parity between indicator and strategy Pine surfaces.
# Fails if core contract encodings or hidden export names drift.

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
INDICATOR_FILE="$ROOT_DIR/indicators/v6-warbird-complete.pine"
STRATEGY_FILE="$ROOT_DIR/indicators/v6-warbird-complete-strategy.pine"

echo "=== Warbird Indicator/Strategy Parity Check ==="

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

extract_ml_fields() {
    local source_file="$1"
    local out_file="$2"
    rg -o '"ml_[^"]+"' "$source_file" | tr -d '"' | sort -u > "$out_file"
}

count_plot_calls() {
    local source_file="$1"
    rg 'plot(shape|char|arrow|bar|candle)?\(' "$source_file" | rg -v '^\s*//' | wc -l | tr -d ' '
}

compare_contract_line() {
    local pattern="$1"
    local label="$2"
    local indicator_out="$TMP_DIR/indicator_${label}.txt"
    local strategy_out="$TMP_DIR/strategy_${label}.txt"

    rg --no-filename --no-line-number "$pattern" "$INDICATOR_FILE" > "$indicator_out"
    rg --no-filename --no-line-number "$pattern" "$STRATEGY_FILE" > "$strategy_out"

    if ! diff -u "$indicator_out" "$strategy_out" > "$TMP_DIR/diff_${label}.txt"; then
        echo "FAIL: Contract drift for $label"
        sed -n '1,80p' "$TMP_DIR/diff_${label}.txt"
        exit 1
    fi
}

extract_ml_fields "$INDICATOR_FILE" "$TMP_DIR/ml_indicator.txt"
extract_ml_fields "$STRATEGY_FILE" "$TMP_DIR/ml_strategy.txt"

if ! diff -u "$TMP_DIR/ml_indicator.txt" "$TMP_DIR/ml_strategy.txt" > "$TMP_DIR/ml_diff.txt"; then
    echo "FAIL: Hidden export field mismatch between indicator and strategy"
    sed -n '1,120p' "$TMP_DIR/ml_diff.txt"
    exit 1
fi

ML_FIELD_COUNT=$(wc -l < "$TMP_DIR/ml_indicator.txt" | tr -d '[:space:]')
echo "INFO: Hidden export fields match (${ML_FIELD_COUNT} fields)"

INDICATOR_PLOT_COUNT=$(count_plot_calls "$INDICATOR_FILE")
STRATEGY_PLOT_COUNT=$(count_plot_calls "$STRATEGY_FILE")
echo "INFO: Total plot-style calls -> indicator=${INDICATOR_PLOT_COUNT}, strategy=${STRATEGY_PLOT_COUNT}"

if [[ "$INDICATOR_PLOT_COUNT" -gt 64 ]]; then
    echo "FAIL: Indicator exceeds TradingView's 64 plot-count cap (${INDICATOR_PLOT_COUNT}/64)"
    exit 1
fi

if [[ "$STRATEGY_PLOT_COUNT" -gt 64 ]]; then
    echo "FAIL: Strategy exceeds TradingView's 64 plot-count cap (${STRATEGY_PLOT_COUNT}/64)"
    exit 1
fi

compare_contract_line '^int stopFamilyCode =' 'stop_family'
compare_contract_line '^bool targetEligible20pt =' 'target_gate'
compare_contract_line '^int eventPivotInteractionCode =' 'pivot_interaction'
compare_contract_line '^eventPivotInteractionCode :=' 'pivot_interaction_harness'
compare_contract_line '^int eventModeCode =' 'event_mode'
compare_contract_line '^int regimeBucketCode =' 'regime_bucket'
compare_contract_line '^int sessionBucketCode =' 'session_bucket'
compare_contract_line '^int setupArchetypeCode =' 'setup_archetype'
compare_contract_line '^bool longSignal =' 'long_signal'
compare_contract_line '^bool shortSignal =' 'short_signal'

for required in \
    'strategy\(' \
    'strategy.entry\("Long", strategy.long\)' \
    'strategy.entry\("Short", strategy.short\)' \
    'strategy.exit\("Long-TP1"' \
    'strategy.exit\("Long-TP2"' \
    'strategy.exit\("Short-TP1"' \
    'strategy.exit\("Short-TP2"' \
    '^bool canTradeBar ='
do
    if ! rg -q "$required" "$STRATEGY_FILE"; then
        echo "FAIL: Strategy execution primitive missing: $required"
        exit 1
    fi
done

echo "PASS: Core contract + strategy execution parity checks passed."
echo "=== Check Complete ==="
