#!/bin/bash
# Test suite: TA Core Pack — v6-warbird-complete.pine
# Validates contract from plan: Replace harnesses with TA core pack
# Usage: ./scripts/tests/test-ta-pack.sh

set -euo pipefail

PINE="indicators/v6-warbird-complete.pine"
SPEC="WARBIRD_MODEL_SPEC.md"
CLAUDE="CLAUDE.md"

PASS=0
FAIL=0

pass() { echo "  PASS: $1"; PASS=$((PASS + 1)); }
fail() { echo "  FAIL: $1"; FAIL=$((FAIL + 1)); }

assert_present()  { grep -qF "$2" "$1" && pass "$3" || fail "$3"; }
assert_absent()   { grep -qF "$2" "$1" && fail "$3" || pass "$3"; }
assert_count()    { local n; n=$(grep -c "$2" "$1" 2>/dev/null || echo 0); [ "$n" -eq "$3" ] && pass "$4 (got $n)" || fail "$4 (expected $3, got $n)"; }

# ─────────────────────────────────────────────
echo ""
echo "=== TA Core Pack Test Suite ==="
echo ""

# ── 1. Compilation fixes ─────────────────────
echo "1. Compilation fixes"

# isValid is declared (not just referenced)
grep -qE '^bool isValid\s*=' "$PINE" && pass "isValid declared at top scope" || fail "isValid NOT declared at top scope"

# bare 'atr' identifier replaced with atrRaw
# Exclude: atrRaw, atr14, atr_, ta.atr() calls — only flag standalone 'atr' variable refs
bare=$(grep -nE '\batr\b' "$PINE" | grep -vE '\batrRaw\b|\batr14\b|\batr_|ta\.atr' || true)
[ -z "$bare" ] && pass "bare 'atr' identifier removed" || fail "bare 'atr' still present: $bare"

# ── 2. TA core calculations ───────────────────
echo ""
echo "2. TA core calculations"

assert_present "$PINE" "ta.ema(close, 100)"         "ema100 calculation"
assert_present "$PINE" "ta.macd(close, 12, 26, 9)"  "macdHist calculation"
assert_present "$PINE" "ta.rsi(close, 14)"          "rsi14 calculation"
assert_present "$PINE" "ta.atr(14)"                 "atr14 calculation"
assert_present "$PINE" "ta.sma(volume, 20)"         "volSma20 calculation"
assert_present "$PINE" "volSma20 > 0 ? volume / volSma20" "volRatio calculation (div-by-zero guarded)"
assert_present "$PINE" "volRatio - nz(volRatio[1])" "volAccel calculation"
assert_present "$PINE" "(high - low) * volume"      "barSpreadXVol calculation"
assert_present "$PINE" "ta.cum("                    "obvVal calculation (ta.cum)"
assert_present "$PINE" "ta.mfi(hlc3, 14)"           "mfi14 calculation"

# ── 3. ml_* TA pack exports (all 15) ─────────
echo ""
echo "3. ml_* TA pack exports"

assert_present "$PINE" '"ml_ema_21"'           "ml_ema_21 export"
assert_present "$PINE" '"ml_ema_50"'           "ml_ema_50 export"
assert_present "$PINE" '"ml_ema_100"'          "ml_ema_100 export"
assert_present "$PINE" '"ml_ema_200"'          "ml_ema_200 export"
assert_present "$PINE" '"ml_macd_hist"'        "ml_macd_hist export"
assert_present "$PINE" '"ml_rsi_14"'           "ml_rsi_14 export"
assert_present "$PINE" '"ml_atr_14"'           "ml_atr_14 export"
assert_present "$PINE" '"ml_adx_14"'           "ml_adx_14 export"
assert_present "$PINE" '"ml_volume_raw"'       "ml_volume_raw export"
assert_present "$PINE" '"ml_vol_sma_20"'       "ml_vol_sma_20 export"
assert_present "$PINE" '"ml_vol_ratio"'        "ml_vol_ratio export"
assert_present "$PINE" '"ml_vol_acceleration"' "ml_vol_acceleration export"
assert_present "$PINE" '"ml_bar_spread_x_vol"' "ml_bar_spread_x_vol export"
assert_present "$PINE" '"ml_obv"'              "ml_obv export"
assert_present "$PINE" '"ml_mfi_14"'           "ml_mfi_14 export"

# ── 4. Plot budget ────────────────────────────
echo ""
echo "4. Plot budget"

assert_count "$PINE" "^plot(" 64 "Total plot() calls = 64 (TradingView hard limit)"

# ── 5. Harness removal ────────────────────────
echo ""
echo "5. Harness removal"

[ ! -f "indicators/harnesses/bigbeluga-pivot-levels-harness.pine" ]        && pass "BigBeluga harness deleted"           || fail "BigBeluga harness still exists"
[ ! -f "indicators/harnesses/luxalgo-msb-ob-probability-toolkit-harness.pine" ] && pass "LuxAlgo MSB/OB harness deleted"  || fail "LuxAlgo MSB/OB harness still exists"
[ ! -f "indicators/harnesses/luxalgo-luminance-breakout-engine-harness.pine" ]  && pass "LuxAlgo Luminance harness deleted" || fail "LuxAlgo Luminance harness still exists"
[ ! -d "indicators/harnesses" ]                                             && pass "harnesses/ directory removed"        || fail "harnesses/ directory still exists"

assert_absent "$PINE" '"ml_pivot_'    "No ml_pivot_* exports in indicator"
assert_absent "$PINE" '"ml_msb_'      "No ml_msb_* exports in indicator"
assert_absent "$PINE" '"ml_ob_'       "No ml_ob_* exports in indicator"
assert_absent "$PINE" '"ml_luminance_' "No ml_luminance_* exports in indicator"

# ── 6. Docs updated ──────────────────────────
echo ""
echo "6. Docs updated"

assert_present "$SPEC" "TA Core Pack"                     "WARBIRD_MODEL_SPEC.md has TA Core Pack section"
assert_absent  "$SPEC" "Required Third-Party Harnesses"   "WARBIRD_MODEL_SPEC.md: 'Required Third-Party Harnesses' removed"
assert_absent  "$SPEC" "Pivot Levels [BigBeluga]"         "WARBIRD_MODEL_SPEC.md: BigBeluga reference removed"
assert_absent  "$SPEC" "ml_pivot_distance_nearest"        "WARBIRD_MODEL_SPEC.md: ml_pivot_* removed from export list"
assert_absent  "$SPEC" "ml_luminance_signal"              "WARBIRD_MODEL_SPEC.md: ml_luminance_* removed from export list"
assert_present "$SPEC" "ml_ema_21"                        "WARBIRD_MODEL_SPEC.md has ml_ema_21 in export list"
assert_present "$SPEC" "ml_mfi_14"                        "WARBIRD_MODEL_SPEC.md has ml_mfi_14 in export list"

assert_present "$CLAUDE" "compiles clean"                 "CLAUDE.md: compilation fix documented"
assert_present "$CLAUDE" "15-metric TA core pack"         "CLAUDE.md: TA core pack documented"
assert_present "$CLAUDE" "harnesses retired"              "CLAUDE.md: harness retirement documented"
assert_absent  "$CLAUDE" "Required BigBeluga standalone"  "CLAUDE.md: old harness bullet removed"

# ── Summary ──────────────────────────────────
echo ""
echo "=== Summary ==="
echo "  Passed: $PASS"
echo "  Failed: $FAIL"
echo ""

if [ "$FAIL" -gt 0 ]; then
  echo "FAIL ($FAIL test(s) failed)"
  exit 1
else
  echo "PASS (all $PASS tests)"
  exit 0
fi
