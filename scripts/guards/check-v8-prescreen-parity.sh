#!/bin/bash
# Check v8 parity between SATS live indicator and SATS-PS prescreen strategy.
#
# Contract (per Kirk, 2026-04-17): prescreen must be live verbatim PLUS
# minimal strategy() wrapper ONLY. No hand-rolled signal logic, no invented
# fib gates, no reinvented state machines.
#
# Allowed differences:
#   1. Line 1-N: `strategy(...)` declaration block vs live's `indicator(...)`
#   2. `strategy.entry(...)` + `strategy.exit(...)` calls inside the existing
#      confirmedBuy / confirmedSell blocks (4 lines total, 2 per direction)
#
# Everything else MUST match live byte-for-byte.

set -uo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
LIVE_FILE="$ROOT_DIR/indicators/v8-warbird-live.pine"
PRESCREEN_FILE="$ROOT_DIR/indicators/v8-warbird-prescreen.pine"

echo "=== Warbird v8 Live/Prescreen Parity Check ==="

if [[ ! -f "$LIVE_FILE" ]]; then
    echo "FAIL: Missing live file: $LIVE_FILE"
    exit 1
fi
if [[ ! -f "$PRESCREEN_FILE" ]]; then
    echo "FAIL: Missing prescreen file: $PRESCREEN_FILE"
    exit 1
fi

FAIL=0

# ── 1. Declaration check: prescreen must declare strategy(), live indicator() ──
if ! head -25 "$PRESCREEN_FILE" | grep -q '^strategy('; then
    echo "FAIL: prescreen missing strategy() declaration"
    FAIL=1
fi
if ! head -25 "$LIVE_FILE" | grep -q '^indicator('; then
    echo "FAIL: live missing indicator() declaration"
    FAIL=1
fi

# ── 2. Prescreen must contain exactly 2 strategy.entry + 2 strategy.exit calls ──
ENTRY_COUNT=$(grep -c '^\s*strategy\.entry(' "$PRESCREEN_FILE" || true)
EXIT_COUNT=$(grep -c '^\s*strategy\.exit('  "$PRESCREEN_FILE" || true)

if [[ "$ENTRY_COUNT" -ne 2 ]]; then
    echo "FAIL: prescreen has $ENTRY_COUNT strategy.entry() calls, expected exactly 2"
    FAIL=1
fi
if [[ "$EXIT_COUNT" -ne 2 ]]; then
    echo "FAIL: prescreen has $EXIT_COUNT strategy.exit() calls, expected exactly 2"
    FAIL=1
fi

# ── 3. Line delta check: prescreen ≈ live + declaration delta + 4 strategy lines ──
LIVE_LINES=$(wc -l < "$LIVE_FILE" | tr -d ' ')
PRESCREEN_LINES=$(wc -l < "$PRESCREEN_FILE" | tr -d ' ')
DELTA=$((PRESCREEN_LINES - LIVE_LINES))

# Allowed delta range: 10-20 lines (declaration bloat + 4 strategy calls + comment tolerance)
if [[ "$DELTA" -lt 8 || "$DELTA" -gt 20 ]]; then
    echo "FAIL: prescreen is $PRESCREEN_LINES lines, live is $LIVE_LINES lines (delta $DELTA). Expected 8-20 line delta."
    echo "  Large deltas indicate hand-rolled logic added beyond the strategy wrapper contract."
    FAIL=1
else
    echo "INFO: line delta OK (live=$LIVE_LINES, prescreen=$PRESCREEN_LINES, delta=$DELTA)"
fi

# ── 4. Hand-rolled signal logic detector ──
# These patterns were in Codex's hand-rolled fib-hit state machine. Never again.
FORBIDDEN_PATTERNS=(
    "awaitLongFibHit"
    "awaitShortFibHit"
    "rawBuyTrigger"
    "rawSellTrigger"
    "fibLongTouch"
    "fibShortTouch"
    "fibLong382"
    "fibShort382"
)

for pattern in "${FORBIDDEN_PATTERNS[@]}"; do
    if grep -q "$pattern" "$PRESCREEN_FILE"; then
        echo "FAIL: prescreen contains forbidden hand-rolled pattern: $pattern"
        echo "  (This was Codex's fib-hit state machine. Prescreen = live verbatim only.)"
        FAIL=1
    fi
done

# ── 5. Signal logic byte-parity: the confirmedBuy/confirmedSell line MUST match ──
LIVE_SIGNAL=$(grep -n '^bool confirmedBuy\s*=' "$LIVE_FILE" | head -1 | cut -d: -f2-)
PRESCREEN_SIGNAL=$(grep -n '^bool confirmedBuy\s*=' "$PRESCREEN_FILE" | head -1 | cut -d: -f2-)

if [[ "$LIVE_SIGNAL" != "$PRESCREEN_SIGNAL" ]]; then
    echo "FAIL: confirmedBuy signal definition drift"
    echo "  live:      $LIVE_SIGNAL"
    echo "  prescreen: $PRESCREEN_SIGNAL"
    FAIL=1
else
    echo "INFO: confirmedBuy signal matches live verbatim"
fi

# ── 6. strategy() pins hostile TV defaults ──
REQUIRED_STRATEGY_PINS=(
    "use_bar_magnifier"
    "slippage"
    "commission_type"
    "commission_value"
    "pyramiding"
)

for pin in "${REQUIRED_STRATEGY_PINS[@]}"; do
    if ! grep -q "$pin" "$PRESCREEN_FILE"; then
        echo "FAIL: prescreen missing required strategy() pin: $pin"
        FAIL=1
    fi
done

echo ""
if [[ $FAIL -eq 0 ]]; then
    echo "=== PASS: v8 prescreen parity verified ==="
    exit 0
else
    echo "=== FAIL: v8 prescreen parity violations detected ==="
    exit 1
fi
