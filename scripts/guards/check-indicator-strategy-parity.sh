#!/bin/bash
# Historical guard: v7 indicator/strategy parity.
#
# The active Pine surface was narrowed on 2026-04-30 to:
#   - indicators/warbird-pro-indicator.pine
#   - indicators/warbird-nexus-machine-learning-rsi.pine
#   - indicators/warbird-nexus-machine-learning-rsi-optuna-fast-test.pine
#
# There is no active strategy harness, so indicator/strategy parity is inactive.
# If Kirk explicitly reopens a strategy/backtest surface, replace this guard
# with a Warbird Pro parity check in the same change.

set -euo pipefail

echo "=== Warbird Indicator/Strategy Parity Check ==="
echo "INFO: No active strategy harness exists for Warbird Pro."
echo "PASS: Parity guard inactive until a strategy harness is explicitly reopened."
echo "=== Check Complete ==="
