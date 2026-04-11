# Fib Engine Fix + Packet Policy Layer Design

**Date:** 2026-04-10
**Status:** Approved for implementation
**Scope:** v7-warbird-institutional.pine fib engine fixes + morning packet input layer
**Constraint:** READ-ONLY until implementation plan is approved

---

## 1. Problem Statement

The v7 fib engine has four compounding bugs that produce untradeable setups:

1. **Threshold too sensitive** — ATR-multiplied deviation drops to ~0.5% on 15m MES, catching micro-swings. Reference auto-fib (Auto Fib GOLDEN TARGET) uses fixed ~3% and works.
2. **Depth too shallow** — depth=10 on 15m vs reference's 15. Fewer bars = shallower pivots qualify.
3. **No minimum range gate** — `fibRange > 0` is the only check. Micro-swings produce sub-10-point trades with clustered TP lines.
4. **Direction from last ZigZag leg** — retracement leg flips `fibBull`, inverting the entire fib grid. Same anchors as reference, but upside down.

Additionally, the overlay is incoherent: LONG ENTRY / SHORT ENTRY labels display as always-on projections with no live signal behind them.

**Evidence:** Side-by-side comparison on MES1! 15m — reference auto-fib (Deviation=3, Depth=15, static) finds correct structural swing with proper direction and tradeable target separation. WB v7 on the same chart produces inverted direction, clustered targets, and sub-10-point trades.

**Constraint from contracts:**
- Pine owns geometry and candidate emission (WARBIRD_MODEL_SPEC.md line 9, 18, 24)
- AG scores candidates later (WARBIRD_MODEL_SPEC.md line 43)
- HTF is an AG feature, not a Pine gate (MASTER_PLAN.md line 64)
- The 15m fib setup is the canonical trade object (WARBIRD_MODEL_SPEC.md line 16)

**Constraint from Kirk's SL standard:** Entry precision must support 24-tick (6-point) stops with 4:1+ R:R. If the engine cannot produce entries precise enough for this stop budget, the entry model needs rethinking — not the stop width.

---

## 2. Architecture

Three layers, cleanly separated:

```
Pine = geometry + fast invalidation
Morning packet = session policy (bounded rules, not price levels)
AG = overnight selector/tuner of bounded rule families
```

### Layer 1: Standalone Geometry Engine (Pine)
- Owns anchors, direction, entry line, invalidation line, target ladder
- Works without AG — must produce valid candidates standalone
- Rapid invalidation: suppresses signals when structure breaks intraday
- Never flips direction mid-session on a ZigZag retracement leg

### Layer 2: Packet-Policy Gate (Pine inputs, set manually each morning)
- Session policy snapshot, NOT geometry replacement
- Pine computes all price levels locally from live chart
- Packet sets bounded admissibility rules that filter Pine's candidates
- Packet does not send raw price levels or fib anchors

### Layer 3: AG Overnight Selector (future, not built yet)
- Trains on thousands of historical 15m candidates
- Learns which bounded rule families produce tradeable setups
- Publishes one morning packet (occasionally intraday on real regime breaks)
- Does NOT replace Pine geometry or direction

---

## 3. Four Engine Fixes

### Fix 1: Threshold Floor

**Current (line 362):**
```pine
fibSettings.devThreshold := ta.atr(10) / close * 100 * fibDeviation
```

**Fixed:**
```pine
fibSettings.devThreshold := math.max(ta.atr(10) / close * 100 * fibDeviation, 2.0)
```

ATR-adaptive stays (AG needs parameter space). Floor of 2.0% prevents micro-swing detection on compressed-vol bars. On 15m MES at 6868, this prevents thresholds below ~137 points of price movement, which is the minimum structural swing size.

### Fix 2: Depth Floor

**Current (lines 65-67):**
```pine
int fibDepth = autoTuneZZ
  ? (_tfSec >= 14400 ? 20 : _tfSec >= 3600 ? 15 : 10)
  : fibDepthManual
```

**Fixed:**
```pine
int fibDepth = autoTuneZZ
  ? (_tfSec >= 14400 ? 20 : 15)
  : fibDepthManual
```

15m and 1H both get depth=15 (matching reference auto-fib). 4H stays at 20. Manual override preserved for AG testing.

### Fix 3: Minimum Range Gate

**Current (line 437):**
```pine
bool isValid = not na(fibAnchorHigh) and not na(fibAnchorLow) and fibRange > 0
```

**Fixed:**
```pine
float minFibRange = minFibRangeAtr * atr14
bool isValid = not na(fibAnchorHigh) and not na(fibAnchorLow) and fibRange >= minFibRange
```

Where `minFibRangeAtr` is a packet input (default 1.5). A 15-point swing when ATR=12 (1.25x) is rejected. A 25-point swing (2.1x) passes. Scales with volatility.

### Fix 4: Direction from Anchor Structure + Rebase on Invalidation

**4a: Direction from anchor relationship, not last ZigZag leg.**

**Current (lines 443-445):**
```pine
var bool fibBull = true
if zzNewPivot and zzSwingDir != 0
    fibBull := zzSwingDir > 0
```

**Fixed:**
```pine
var bool fibBull = true
if zzNewPivot
    // Which anchor was confirmed most recently?
    // If high came after low → up-swing confirmed → bullish
    // If low came after high → down-swing confirmed → bearish
    if zzHighBar > zzLowBar
        fibBull := true
    else if zzLowBar > zzHighBar
        fibBull := false
```

Key difference: `zzSwingDir` tells which way the last *leg* went. `zzHighBar > zzLowBar` tells which *anchor point* was confirmed most recently. After an up-swing (low→high), the high was confirmed last → bullish. After a down-swing (high→low), the low was confirmed last → bearish.

**4b: `breakAgainst` triggers ladder invalidation.**

**Current:** `breakAgainst` (line 600) only fires an alert and event code.

**Fixed:**
```pine
var bool ladderInvalidated = false

if breakAgainst
    ladderInvalidated := true

if zzNewPivot
    ladderInvalidated := false

// Gate entry triggers on ladder validity
bool entryLongTrigger  = acceptEvent and dir == 1 and not ladderInvalidated
bool entryShortTrigger = acceptEvent and dir == -1 and not ladderInvalidated
```

Pine's rapid-change intelligence: when price breaks against the .50 level, signals are suppressed until a new ZigZag pivot re-anchors. The fib ladder stays visible (operator sees structure), but no entry fires.

---

## 4. Packet-Policy Input Fields

These start as Pine indicator inputs. Operator sets them manually each morning from AG's overnight recommendation. When AG pipeline is real, they migrate to automated transport.

| Input | Type | Default | Purpose |
|---|---|---|---|
| `pkt_bias` | string dropdown | `"BOTH"` | `LONG_ONLY`, `SHORT_ONLY`, `BOTH`, `FLAT` |
| `pkt_max_sl_ticks` | int | `30` | Maximum stop budget in ticks. Setup rejected if SL > this. |
| `pkt_min_fib_range_atr` | float | `1.5` | Minimum fibRange as multiple of ATR(14). |
| `pkt_min_rr` | float | `3.0` | Minimum R:R to TP1. Setup rejected if TP1/SL < this. |
| `pkt_stop_family` | string dropdown | `"FIB_NEG_0236"` | Which stop family to use. |
| `pkt_max_entry_offset_ticks` | int | `8` | Max distance from ideal fib entry line at bar close. If price has already moved too far, no trade. |
| `pkt_session_filter` | string dropdown | `"RTH_ONLY"` | `RTH_ONLY`, `ETH_OK`, `ALL` |

### Admissibility gate logic (applied at entry trigger):

```pine
float slDist = math.abs(entryLevel - slLevel)
float tp1Dist = math.abs(tp1Level - entryLevel)
float entryOffset = math.abs(close - entryLevel)
bool biasAllowed = pkt_bias == "BOTH" or (pkt_bias == "LONG_ONLY" and dir == 1) or (pkt_bias == "SHORT_ONLY" and dir == -1)
bool slAdmissible = slDist <= pkt_max_sl_ticks * syminfo.mintick
bool rrAdmissible = slDist > 0 and (tp1Dist / slDist) >= pkt_min_rr
bool entryClean = entryOffset <= pkt_max_entry_offset_ticks * syminfo.mintick
bool pktFlat = pkt_bias == "FLAT"

bool packetGatePassed = biasAllowed and slAdmissible and rrAdmissible and entryClean and not pktFlat
```

Entry triggers become:
```pine
bool entryLongTrigger  = acceptEvent and dir == 1 and not ladderInvalidated and packetGatePassed
bool entryShortTrigger = acceptEvent and dir == -1 and not ladderInvalidated and packetGatePassed
```

---

## 5. Overlay Coherence

### Signal-gated display (Mode A — current build target):

| Element | When visible |
|---|---|
| Fib ladder (ZERO, .236, .382, .5, .618, .786, 1.0) | Always (when `isValid`) — this is structure |
| Extension lines (1.236, 1.382, 1.5, 1.618, 1.786, 2.0, 2.236, 2.618) | Always (when `isValid`) — structural targets |
| LONG ENTRY / SHORT ENTRY label | ONLY when trade state machine fires AND packet gate passes |
| SL label | ONLY during active trade |
| TP1-TP5 labels | ONLY during active trade |
| Packet status label | Always during session — small text showing active policy |

### Packet status label (new):
```
PKT 2026-04-10 | LONG_ONLY | SL≤24t | RR≥3.0
```
Small label in a fixed corner. Shows operator what policy is active. Uses `label.new()` from the 200-label pool — zero plot budget.

### Future Mode B (packet/probability overlay):
When AG pipeline is real, TP lines carry probability scores from the active scored packet. Not built now.

---

## 6. AG Export Surface

No changes to the 35-plot export budget. All existing ML exports remain:
- Fib engine state, trade state machine, HTF fib confluence
- VWAP code, OR state, IM state stubs, NYSE A/D slope
- Entry/exit trigger events, TP1-TP5 hit events

New exports (from existing headroom — 29 plots available):
- `ml_packet_gate_passed` (1/0) — did the setup pass all packet admissibility checks
- `ml_ladder_invalidated` (1/0) — is the current ladder suppressed by breakAgainst
- `ml_sl_dist_ticks` — measured stop distance in ticks at entry
- `ml_rr_to_tp1` — measured R:R to TP1 at entry

4 new plots → 39/64 total. 25 headroom remaining.

---

## 7. What This Does NOT Change

- Fib level constants (0 through 2.618) — locked to spec
- Extension target math — same formulas, better anchors
- Trade state machine — SETUP → ACTIVE → TP progress → resolution
- HTF confluence check — stays as AG feature export, not Pine gate
- Alert conditions — 3 alertcondition() calls stay
- Color/width/style spec — locked to operator-approved visual contract
- Stop family calculation logic — same families, packet selects which one
- AG label encoding — 0=none through 7=TP5_HIT

---

## 8. Implementation Sequence

1. Fix the four engine bugs (threshold, depth, range gate, direction/rebase)
2. Add packet-policy input fields and admissibility gate
3. Implement signal-gated overlay (suppress always-on entry labels)
4. Add packet status label
5. Add 4 new ML export plots
6. Verify: pine-lint, check-contamination, npm run build, TV compiler
7. Visual validation on live MES 15m chart against reference auto-fib

---

## 9. Success Criteria

- On MES1! 15m, the engine anchors on the same structural swing as the reference auto-fib
- Direction matches the reference (bullish when reference says bullish)
- TP1 is >= 20 points from entry on typical swings (not sub-10-point garbage)
- No LONG ENTRY / SHORT ENTRY label unless a real signal fires
- With `pkt_max_sl_ticks=24`, setups with wider stops are rejected
- With `pkt_min_rr=3.0`, low-R:R setups are rejected
- `breakAgainst` suppresses signals until re-anchor
- Pine-lint, check-contamination, npm run build all pass
- Budget stays at or below 40/64 plots
