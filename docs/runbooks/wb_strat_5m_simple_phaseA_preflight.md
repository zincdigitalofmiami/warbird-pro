# Warbird Strategy 5m — Simple Mode Phase A Pre-flight Audit

> **For Kirk:** STAGE 0 deliverable. Read end-to-end before approving STAGE 1. Architecture rewritten 2026-04-28 after discovering the actual hub pattern: Optuna-native Python re-simulation, identical to how the Nexus tune was done.

**Goal:** Stand up a slow-and-precise Optuna tuning workflow for `v7-warbird-institutional-backtest-strategy.pine` running in Simple Mode only on MES1! 5m, against 2025-04-28 → 2026-04-01 IS data, with results visible at `http://localhost:8101/dashboard?studies_order_by=desc` (the Optuna Dashboard child of the hub at 8090).

**Architecture:** Strip the strategy to a single entry/exit contract (Simple Mode + ATR Bracket + T2-locked target). Build a Python profile that reproduces Pine entry/exit semantics on a TradingView-exported OHLCV + footprint + Nexus parquet. Run 1000-trial-per-phase tuning via `scripts/optuna/runner.py` writing to `study.db` SQLite. The existing hub at port 8090 already auto-launches an `optuna-dashboard` child at port 8101 for this workspace — same dashboard look as the Nexus study at port 8102.

**Tech Stack:**
- Pine v6 strategy: `indicators/v7-warbird-institutional-backtest-strategy.pine`
- Nexus indicator: `indicators/warbird-nexus-machine-learning-rsi-optuna-fast-test.pine` (`nexus_signal_tier` plot, line 757)
- Optuna runner: `scripts/optuna/runner.py` (existing, profile-module driven)
- Reference profile: `scripts/optuna/warbird_nexus_ml_rsi_profile.py` (the pattern to mirror)
- New profile (to build): `scripts/optuna/v7_warbird_strategy_5m_profile.py`
- New footprint parquet (to capture): `scripts/optuna/workspaces/v7_warbird_strategy_5m/tv_footprint_5m.parquet` + manifest
- Existing workspace: `scripts/optuna/workspaces/v7_warbird_strategy_5m/study.db`
- Hub launcher: `scripts/optuna/warbird_optuna_hub.py` running at `localhost:8090`, child dashboard already up at `localhost:8101`

---

## §1 Current state — what exists right now (verified)

| Asset | Path | State |
|---|---|---|
| Strategy file | `indicators/v7-warbird-institutional-backtest-strategy.pine` | 1852 lines, **110 inputs**, 51/64 plot budget |
| Nexus indicator | `indicators/warbird-nexus-machine-learning-rsi-optuna-fast-test.pine` | 921 lines, exports `nexus_signal_tier` (1.0 / -1.0 / 0.5 / 0) |
| 5m OHLCV data | `data/mes_5m.parquet` | EXISTS |
| Optuna runner | `scripts/optuna/runner.py` | EXISTS, accepts `--profile-module scripts.optuna.<key>_profile` |
| Nexus profile | `scripts/optuna/warbird_nexus_ml_rsi_profile.py` | EXISTS, full pattern reference |
| Strategy 5m profile | `scripts/optuna/v7_warbird_strategy_5m_profile.py` | **DOES NOT EXIST — Stage 4 deliverable** |
| Hub launcher | `scripts/optuna/warbird_optuna_hub.py` running at `localhost:8090` | RUNNING, PID 46540, child dashboards at 8100/8101/8102 |
| Strategy 5m optuna-dashboard | `localhost:8101/dashboard` | RUNNING NOW, PID 42453, points at `scripts/optuna/workspaces/v7_warbird_strategy_5m/study.db` |
| Workspace dir | `scripts/optuna/workspaces/v7_warbird_strategy_5m/` | Contains `study.db` only (1 dead trial) |
| Nexus footprint parquet | `scripts/optuna/workspaces/warbird_nexus_ml_rsi/tv_footprint_5m.parquet` | EXISTS, manifest covers 2026-01-11 → 2026-04-27 (20765 rows). **Insufficient for our IS window 2025-04-28 → 2026-04-01.** Must re-capture. |
| MES 5m OHLCV parquet | `data/mes_5m.parquet` | 441,852 rows, **2020-01-01 → 2026-04-03 verified**. Sufficient for full window. Bottleneck is footprint, not OHLCV. |

### §1.1 Hub architecture clarification

`warbird_optuna_hub.py` is a **launcher and index**, not a database. For each workspace under `scripts/optuna/workspaces/<key>/`, it auto-spawns one `optuna-dashboard` child process bound to that workspace's `study.db`, on incremental ports starting at 8100. Verified live:

```
PID 46540 → warbird_optuna_hub.py (port 8090, launcher)
PID 24985 → optuna-dashboard sqlite:////.../v7_warbird_institutional/study.db --port 8100
PID 42453 → optuna-dashboard sqlite:////.../v7_warbird_strategy_5m/study.db --port 8101  ← OUR TARGET
PID  6702 → optuna-dashboard sqlite:////.../warbird_nexus_ml_rsi/study.db --port 8102
```

The 8101 dashboard is already running — it's just empty because no profile has produced trials yet. **No new hub view needs to be built.** Adding trials to `study.db` makes them visible immediately at `localhost:8101/dashboard`.

---

## §2 What gets stripped (STAGE 1 deletes)

The strategy file currently supports three entry modes (Simple, Loose, Configured) with mutually-inert knobs across modes. Kirk's directive: Simple Mode only.

### §2.1 Inputs to delete (from current 110)

| Input | Lines (approx) | Reason |
|---|---|---|
| `enableCustomFibRatios` + 14 ratio inputs | 64–79 | Fib geometry locked per CLAUDE.md |
| `optEntryLevelInput` ("Execution Anchor" 0.500/0.618/0.786) | 183 | Configured-mode only |
| `optStopAtrMult` | 185 | Replaced by `atrExecutionSlMultInput` |
| `optMaxRiskAtr` | 187 | `atrRiskAcceptable` was hard-set true; dead knob |
| `entryModeInput` ("Simple"/"Loose"/"Configured") | 191 | Becomes redundant once Loose/Configured deleted |
| `executionModeInput` ("Fib Targets (Legacy)"/"ATR Bracket") | 197 | Locked to ATR Bracket |
| `valueReclaimBreakoutLookbackBarsInput` | 207 | Loose-mode only |
| `useMicroValueReclaimInput` | 209 | Loose-mode only |
| `backtestEntryFibModeInput` ("Any Side Fib"/"Configured Anchor") | 213 | Loose-mode only |
| `enableFiveMinBounceSetupInput` | 217 | Configured-mode only |
| `useNexusSourceGateInput` (toggle) | 219 | Made unconditional in Simple Mode |
| `backtestExitTargetInput` ("TP1"…"TP5") | 220 | TP locked to T2 (1.618) |
| `gateShortsInBullTrend` | 177 | Computed but never gated entries |
| `shortTrendGateAdx` | 179 | Tied to dead `bullishTrendBlocksShorts` |
| `requireFootprintForBacktestInput` | 234 | Loose-mode fallback |
| `liqSweepLookbackBarsInput` | 174 | Used only in Loose/Configured liquidity-sweep gate |
| `retestBars` | 171 | Used only in Configured-mode `acceptInDir` gate |
| `rejectWick` | 172 | Used only in Configured-mode `rejectAtZone` gate |

**Total removed: ~30 inputs.** Surface drops from 110 → ~80.

### §2.2 Code blocks to delete

| Block | Lines (approx) | Reason |
|---|---|---|
| Custom fib ratio resolution | 110–145 | Tied to deleted toggle |
| `selectAnySideFibEntry()` helper | 655–670 | Loose-mode-only |
| `entryAnchorHitTriggered()` | 648–653 | Configured-anchor only — Simple Mode replaces with `simpleLadderReclaim` |
| Trend bias / micro-trend / footprint value reclaim | 1124–1138 | Loose/Configured-only gates |
| Duplicate momentum oscillator gate block (`gateVf*`/`gateNfe`/`gateRsiKnn`/`gateConfluence`) | 1139–1155 | DRY — identical to `mlVf*` further down |
| `directionAwareLong/Short` (fib-bias direction lock) | 1174–1175 | Was eating 50% of valid signals |
| Loose/Configured trigger pipeline (`bullAwareLong/bearAwareShort`, `footprintAwareLong/Short`, `momentumGateLong/Short`, `volumeFlowLongAligned/Short`, `fiveMinSetupLong/Short`, `fibAnchorSetupLong/Short`, `setupContextLong/Short`, `longTriggerCore/Event`, `shortTriggerCore/Event`, `directBacktestLongEvent/Trigger`, `directBacktestShortEvent/Trigger`, `ladderInvalidated`, `setupLadderAllowed`) | 1176–1234 | Entire alternate-mode pipeline |
| `acceptEvent`, `rejectEvent`, `breakAgainstEvent`, `tagT1Event`–`tagT5Event` | structure-logic block | Configured-mode setup archetypes |
| Stop ratchet logic (multi-target tightening) | ~1247–1269 | Single-bracket exit — no ratcheting |
| `bullishTrendBlocksShorts` declaration + debug-log reference | 862, 1259 | Dead — never gates an entry |
| Fib Targets exec mode TP1–TP5 fib resolution | TP1Fib..TP5Fib block | Locked to T2 only |
| `backtestExitTargetIndex` switch | 1105 | TP locked to T2 |

### §2.3 ml_* exports — keep all 40 names; replace orphaned expressions with constants

Strategy is parity-coupled to indicator (`indicators/v7-warbird-institutional.pine`). `scripts/guards/check-indicator-strategy-parity.sh` enforces all 40 indicator `ml_*` plots exist in strategy. **Do not delete `ml_*` plots.** Plot names stay; expressions tied to deleted code get replaced.

**Specific ml_* plots that reference variables in the §2.2 deletion list — must be re-pointed to safe constants:**

| ml_* plot | Current expression depends on | Replacement after strip |
|---|---|---|
| `ml_setup_archetype_code` | `acceptConfirmed`, `rejectConfirmed`, `breakAgainstConfirmed`, `tagT1`, `setupAcceptContinuation`, etc. | Compute `simpleLongTrigger ? 1 : simpleShortTrigger ? -1 : 0` (Simple-Mode-aware archetype) |
| `ml_setup_context_active` | `setupContextLong/Short` (deleted) | `(simpleLongTrigger or simpleShortTrigger) ? 1.0 : 0.0` |
| `ml_footprint_entry_long` | `footprintEntryLong` (deleted) | `simpleLongTrigger ? 1.0 : 0.0` |
| `ml_footprint_entry_short` | `footprintEntryShort` (deleted) | `simpleShortTrigger ? 1.0 : 0.0` |
| `ml_event_pivot_interaction_code` | `acceptEvent`, `rejectEvent`, `breakAgainstEvent`, `pivotNearZone` (mostly deleted) | `simpleLongTrigger ? 1 : simpleShortTrigger ? -1 : 0` |
| `ml_entry_long_trigger` | `entryLongTrigger` (kept; rewires to Simple) | No change — variable still exists, just resolves to `simpleLongTrigger` |
| `ml_entry_short_trigger` | `entryShortTrigger` (kept; rewires to Simple) | No change |
| `ml_strategy_long_arm` | `strategyLongArm` (kept) | No change |
| `ml_strategy_short_arm` | `strategyShortArm` (kept) | No change |

**Rule:** every plot that references a variable in §2.2 deletion list MUST get a replacement expression listed here. Stage 1 task list explicitly walks each one. Parity guard catches any name we miss.

---

## §3 What gets kept

| Block | Reason |
|---|---|
| `strategy(...)` declaration with `use_bar_magnifier=true`, `slippage=1`, commission $1/side | CLAUDE.md hard rules |
| Fib engine (ZigZag, anchor selection, `fibPrice()`, fib level constants) | Setup uses fib levels for entry AND for T2 target |
| Footprint block (`request.footprint()`, `fpDelta`, `pocPrice`) | AG export contract; reused by Nexus |
| `barstate.isconfirmed` gate on every entry | No-repaint contract |
| `request.security` HTF fib snapshots (1H/4H/1D) | AG export contract |
| EMA / VWAP / ATR core | Simple Mode entries depend on EMA stack; T2 calc uses fib geometry, stops use ATR |
| Trade state machine (`TRADE_NONE` → `TRADE_SETUP` → `TRADE_ACTIVE` → resolved) | Minimal state machine for setup-bar/fill-bar separation |
| Bracket-of-last-resort, broker-desync recovery, `maxBarsInTradeInput` circuit breaker | Trade #27 leak prevention |
| All 40 `ml_*` exports | Parity contract |
| Web watermark, fib ladder lines, fib labels | Visual contract |

---

## §4 What gets added (STAGE 1 inserts)

### §4.1 New inputs (10 net additions after deletions)

| Input | Default | Range | Notes |
|---|---|---|---|
| `simpleStackStrictnessInput` | `"Direction"` | `"Aligned"` (9>21>50) / `"Direction"` (9>21 + close>50) / `"Loose"` (9>21 only) | Sweep dim |
| `emaFastLenInput` | 9 | 5–21 | Sweep dim |
| `emaMidLenInput` | 21 | 13–55 | Sweep dim |
| `emaSlowLenInput` | 50 | 30–150 | Sweep dim |
| `simpleFibTolAtrInput` | 0.20 | 0.05–0.60 (step 0.01) | Already exists — keep |
| `simpleFibLookbackBarsInput` | 3 | 1–8 | Already exists — keep |
| `simpleFibLevelsLongMaskInput` | 15 (all on) | 1–15 mask of `{.500, .618, .786, 1.000}` | Sweep dim — upper ladder for longs |
| `simpleFibLevelsShortMaskInput` | 15 (all on) | 1–15 mask of `{.500, .382, .236, 0.000}` | Sweep dim — lower ladder for shorts |
| `nexusVoteRequiredInput` | `"Tier1Only"` | `"Tier1Only"` (require ±1.0) / `"Tier1OrLowConv"` (accept ±0.5+) | Sweep dim |
| `momentumVoteThresholdInput` | 2 | 1–4 of {VF velocity, NFE velocity, RSI-KNN velocity, Confluence velocity} | Sweep dim |
| `atrExecutionSlMultInput` | 1.5 | **1.0–2.5** (per Kirk's directive, was 0.5–5.0) | Sweep dim — narrowed |
| `atrExecutionTpMultInput` | DELETE | — | TP locked to T2, not ATR-based |
| `nexusSignalSourceInput` | `close` (manual repoint) | `input.source(close, ...)` | Required in Simple Mode; user manually points to `nexus_signal_tier` plot once per chart |

### §4.2 New helper function

```pine
// Direction-aware fib reclaim: long uses upper ladder (.500/.618/.786/1.000),
// short uses lower ladder (.500/.382/.236/0.000). Mask format: bit per slot.
//   Long  (high-to-low slot order): bit3=1.000 bit2=.786 bit1=.618 bit0=.500
//   Short (low-to-high slot order): bit3=0.000 bit2=.236 bit1=.382 bit0=.500
simpleLadderReclaim(bool wantLong, float tolPts, int lookbackBars, int mask) =>
    bool hit = false
    int hitIdx = na
    float hitLevel = na
    float bestDist = 10e10
    array<int> ladder = wantLong
      ? array.from(FIB_IDX_500, FIB_IDX_618, FIB_IDX_786, FIB_IDX_1000)
      : array.from(FIB_IDX_500, FIB_IDX_382, FIB_IDX_236, FIB_IDX_ZERO)
    for slot = 0 to 3
        bool slotEnabled = bool(math.floor(mask / math.pow(2, slot)) % 2)
        if slotEnabled
            int idx = array.get(ladder, slot)
            float level = fibLevelByIndex(idx)
            if not na(level)
                bool touched = false
                for k = 0 to lookbackBars - 1
                    float lo = low[k]
                    float hi = high[k]
                    if wantLong
                        if not na(lo) and lo <= level + tolPts
                            touched := true
                            break
                    else
                        if not na(hi) and hi >= level - tolPts
                            touched := true
                            break
                bool reclaimed = wantLong ? close > level : close < level
                if touched and reclaimed
                    float dist = math.abs(close - level)
                    if not hit or dist < bestDist
                        hit := true
                        hitIdx := idx
                        hitLevel := level
                        bestDist := dist
    [hit, hitIdx, hitLevel]
```

### §4.3 Simple Mode entry rules (final, after strip)

```
LONG ENTRY (mirror for SHORT):
  isConfirmed                                                          // bar close
  AND isValid                                                          // fib geometry exists
  AND <stack rule per simpleStackStrictnessInput>:
        Aligned   → ema(emaFastLen) > ema(emaMidLen) > ema(emaSlowLen)
        Direction → ema(emaFastLen) > ema(emaMidLen) and close > ema(emaSlowLen)
        Loose     → ema(emaFastLen) > ema(emaMidLen)
  AND simpleLadderReclaim(true, atr14*simpleFibTolAtr, simpleFibLookbackBars, simpleFibLevelsLongMask)
  AND <Nexus rule per nexusVoteRequiredInput>:
        Tier1Only      → nexusSignalSource >= 1.0
        Tier1OrLowConv → nexusSignalSource >= 0.5
  AND momentumLongVelocityVotes >= momentumVoteThresholdInput          // 1..4 votes
  AND oneShotEvent gate                                                 // de-noise
  AND not cooldownActive
  AND tradeState == TRADE_NONE
```

### §4.4 Simple Mode exit rules

```
SL = entry - atr14 * atrExecutionSlMult        (long; flipped for short)
TP = fibLevelByIndex(FIB_IDX_T2)                // locked to T2 (1.618)

Bracket-of-last-resort, broker-desync recovery, time stop maxBarsInTradeInput
all stay in place (already in current code).
```

---

## §5 Nexus signal handling — Optuna pattern

### §5.1 Nexus champion params are FROZEN

Per the Nexus pine file header, defaults are set to Optuna champion trial #936 from `Warbird Nexus ML Fast 5m Signal Quality 2026-04-27 ACTIVE`. **Strategy tuning does not sweep Nexus parameters.** They stay at champion values.

The champion params are baked into the Nexus pine `input.float(...)` defaults. For Python re-simulation, we extract them once at Stage 4 and freeze in the strategy profile.

### §5.2 Pre-export nexus_signal_tier from TV — do NOT reproduce in Python

**Updated decision:** the parquet capture in §5.3 includes the `nexus_signal_tier` column from the Pine plot directly. The strategy profile reads this column as a lookup, no Python re-computation needed.

**Why this beats the Python re-sim approach:**
- Zero risk of Pine↔Python drift on Nexus signal computation (KNN, VF smoothing, fatigue logic — easy to get off-by-one)
- Champion params are baked into the parquet via the Pine indicator's defaults at capture time
- Manifest records the Nexus pine sha256, so any future Nexus indicator update invalidates old captures cleanly
- Strategy profile becomes ~200 lines smaller — only handles strategy-side semantics

**Implication:** if Kirk re-tunes the Nexus indicator later, the strategy profile's parquet must be re-captured to pick up the new Nexus signal. Documented in the manifest.

```python
# scripts/optuna/v7_warbird_strategy_5m_profile.py — Nexus is just a column read

def _nexus_tier_at_bar(df_row):
    return df_row["nexus_signal_tier"]

def _nexus_long_ok(df_row, vote_required: str) -> bool:
    tier = df_row["nexus_signal_tier"]
    return (tier >= 1.0) if vote_required == "Tier1Only" else (tier >= 0.5)

def _nexus_short_ok(df_row, vote_required: str) -> bool:
    tier = df_row["nexus_signal_tier"]
    return (tier <= -1.0) if vote_required == "Tier1Only" else (tier <= -0.5)
```

### §5.2.1 Champion params recorded in manifest, not code

The Nexus champion param values (e.g. `knnBullThresholdInput=63.19994`) live ONCE in the Nexus pine `input.float()` defaults. They appear:
- In the Nexus indicator at chart-load → drive the `nexus_signal_tier` plot
- In the parquet manifest's `nexus_pine_sha256` field, indirectly (sha pins the version)

Strategy profile does NOT carry a `NEXUS_CHAMPION_PARAMS` dict. Single source of truth: the Nexus pine file.

### §5.3 Footprint parquet requirement

The Nexus profile reads OHLCV + `nexus_fp_*` columns from a TV-exported parquet at `tv_footprint_5m.parquet`. The strategy 5m profile needs the same parquet but **covering 2025-04-28 → 2026-04-01** (the IS window) plus embargo + OOS buffer.

The existing Nexus parquet covers only 2026-01-11 → 2026-04-27 — **insufficient.** Stage 4 must capture a fresh export covering 2025-04-28 → 2026-04-28 (full 1-year IS+OOS).

Capture method per Nexus manifest: load Nexus indicator on TV chart MES1! 5m, set date range, click "Export chart data" (CSV), convert to parquet.

**Required parquet columns (verified against Nexus profile imports):**

| Column | Source | Why needed |
|---|---|---|
| `ts` | TV time | Bar timestamp (UTC) |
| `open`, `high`, `low`, `close` | TV OHLC | Strategy entry/exit simulation |
| `volume` | TV | VF normalization, ATR fallback |
| `nexus_fp_available` | Nexus pine line 747 | 0/1 flag — bars where footprint resolved |
| `nexus_fp_bar_delta` | Nexus pine | Per-bar net delta (footprint.delta()) |
| `nexus_fp_total_volume` | Nexus pine | Per-bar total volume from footprint rows |
| `nexus_norm_cum_delta` | Nexus pine line 750 | Smoothed delta, used by Nexus engine + delta direction |
| `nexus_delta_slope` | Nexus pine line 751 | Used in gas-out detection |
| `nexus_bar_delta_ratio` | Nexus pine | Per-bar delta as ratio of total volume |
| `nexus_delta_dir` | Nexus pine line 753 | Discretized delta direction (-1/0/+1) |
| `nexus_gasout_bull` | Nexus pine | Bullish gas-out signal |
| `nexus_gasout_bear` | Nexus pine | Bearish gas-out signal |
| `nexus_mode_minutes` | Nexus pine | Mode marker (5/15/60/240) |
| `nexus_signal_tier` | Nexus pine line 757 | The actual signal source (1.0 / -1.0 / 0.5 / 0). **Pre-exporting this means Python doesn't need to reproduce the engine** — strategy profile reads this column directly. |

**Decision in §5.4 below:** export `nexus_signal_tier` directly (option B), don't reproduce in Python (option A retired). This eliminates Python↔Pine drift risk for Nexus.

Manifest schema (matches Nexus pattern):
- `capture_method`: "TV_FOOTPRINT_PARQUET"
- `trigger_family`: "NEXUS_FOOTPRINT_DELTA"
- `indicator_file`, `symbol`, `timeframe`, `source_csv`, `date_start`, `date_end`, `row_count`, `usable_footprint_rows`, `sha256`
- New: `nexus_pine_sha256` — sha256 of the Nexus pine file at capture time, ensures Nexus version is recorded

---

## §6 Profile module structure

### §6.1 Required interface (per `runner.py`)

```python
# scripts/optuna/v7_warbird_strategy_5m_profile.py

BOOL_PARAMS:        list[str]                         # bool inputs
NUMERIC_RANGES:     dict[str, tuple[float, float]]    # float/int inputs
INT_PARAMS:         set[str]                          # which NUMERIC are ints
CATEGORICAL_PARAMS: dict[str, list[Any]]              # categorical inputs
INPUT_DEFAULTS:     dict[str, Any]                    # baseline values

def load_data() -> pd.DataFrame: ...
def run_backtest(df, params, start_date) -> dict: ...   # returns metrics dict
```

### §6.2 Search space (19 dims)

```python
BOOL_PARAMS = ["oneShotEvent"]

NUMERIC_RANGES = {
    "emaFastLenInput":           (5.0,   21.0),
    "emaMidLenInput":             (13.0,  55.0),
    "emaSlowLenInput":            (30.0,  150.0),
    "simpleFibTolAtrInput":       (0.05,  0.60),
    "simpleFibLookbackBarsInput": (1.0,   8.0),
    "simpleFibLevelsLongMaskInput":  (1.0, 15.0),
    "simpleFibLevelsShortMaskInput": (1.0, 15.0),
    "momentumVoteThresholdInput": (1.0,   4.0),
    "vfLenInput":                 (10.0,  50.0),
    "vfFlowWeight":               (10.0,  50.0),
    "vfVolWeight":                (2.0,   20.0),
    "nfeLenInput":                (7.0,   30.0),
    "rsiKnnWindow":               (10.0,  40.0),
    "atrExecutionSlMultInput":    (1.0,   2.5),
    "maxBarsInTradeInput":        (24.0,  288.0),
    "cooldownBarsInput":          (0.0,   20.0),
    "setupExpiryMinutesInput":    (30.0,  360.0),
}

INT_PARAMS = {
    "emaFastLenInput", "emaMidLenInput", "emaSlowLenInput",
    "simpleFibLookbackBarsInput",
    "simpleFibLevelsLongMaskInput", "simpleFibLevelsShortMaskInput",
    "momentumVoteThresholdInput",
    "vfLenInput", "nfeLenInput", "rsiKnnWindow",
    "maxBarsInTradeInput", "cooldownBarsInput", "setupExpiryMinutesInput",
}

CATEGORICAL_PARAMS = {
    "simpleStackStrictnessInput": ["Aligned", "Direction", "Loose"],
    "nexusVoteRequiredInput":     ["Tier1Only", "Tier1OrLowConv"],
}

INPUT_DEFAULTS = {
    # Pine display titles → defaults that must mirror strategy defaults exactly
    "Simple: Stack Strictness":            "Direction",
    "Simple: EMA Fast Length":              9,
    "Simple: EMA Mid Length":               21,
    "Simple: EMA Slow Length":              50,
    "Simple: Fib Touch Tolerance (ATR)":    0.20,
    "Simple: Fib Reclaim Lookback (bars)":  3,
    "Simple: Long Fib Levels Mask":         15,
    "Simple: Short Fib Levels Mask":        15,
    "Simple: Nexus Vote Required":          "Tier1Only",
    "Simple: Momentum Vote Threshold":      2,
    "ATR SL Mult (ATR Bracket)":            1.5,
    "Max Bars In Trade (0=off)":            96,
    "Post-Exit Cooldown Bars":              0,
    "Setup Expiry Minutes":                 180,
    "One-shot event markers/alerts":        True,
    "VF Window":                            20,
    "VF Candle Weight":                     25.0,
    "VF Volume Weight":                     10.0,
    "NFE Length":                           14,
    "RSI KNN Window":                       20,
}
```

### §6.3 `run_backtest()` semantics

1. Use `df` (already-loaded OHLCV + nexus_fp_* + computed `nexus_signal_tier`).
2. Filter to `start_date` and IS embargo cutoff.
3. Compute EMAs for trial's `emaFastLen/emaMidLen/emaSlowLen`.
4. Compute fib levels per bar from anchor pivots (port `fibHtfSnapshot` semantics).
5. Compute trial momentum oscillators (VF, NFE, RSI-KNN — already in Nexus profile, lift directly).
6. Iterate bars:
   - Check Simple Mode entry per §4.3 with trial params.
   - On entry, simulate exit: stop = `entry ∓ atrSlMult × ATR(14)`, target = T2 fib level frozen at entry bar, time stop = `maxBarsInTrade`, LOR + broker-desync semantics for parity.
   - Apply commission $1/side, slippage 1 tick, contract value $5/point.
7. Score: WR/PF/avg-trade-PnL/max-DD per `tune_strategy_params.summarize_closed_trades()` semantics.
8. Composite score: **`0.55 × normalized_PF + 0.45 × WR`** — PF and WR only, no yearly_consistency (single-year IS window cannot evidence year-over-year stability). Normalization: `normalized_PF = min(PF, 3.0) / 3.0` (caps suspicious-perfection above 3× to limit overfitting reward); `WR` is `wins / total_trades` in [0,1].
9. Apply guards: `optuna.TrialPruned` if `trades < 50`, on negative-TP crash, on OOS leak (any trade timestamp ≥ embargo_start), on PF == ∞ with trades < 50 (suspicious-perfection guard).
10. Embargo cutoff is a profile-module constant `EMBARGO_START = "2026-04-01"`. `run_backtest()` filters `df[df.ts < EMBARGO_START]` before iterating — runner passes `start_date` only; profile owns the embargo end.

### §6.4 Reuse from existing profiles

**From Nexus profile (`warbird_nexus_ml_rsi_profile.py`):**
- footprint parquet schema validation pattern (REQUIRED_TV_FOOTPRINT_COLUMNS list, sha256 verification)
- manifest validation (`TV_FOOTPRINT_CAPTURE_METHODS`, `TV_FOOTPRINT_ENV` env-var loader)
- **NOT** `_compute_core`/`_compute_knn`/`_compute_features` — Nexus signal is a parquet column now (per §5.2)

**From institutional profile (`v7_warbird_institutional_profile.py`):**
- `_atr`, `_ema` numpy implementations
- `_simulate_outcome` adapted for single-bracket exit (drop multi-target ratchet)
- TrialPruned wrapper for negative-TP edge cases
- IS window filtering pattern
- TV footprint manifest schema constants
- score_trial composite formula (replace yearly_consistency weight with normalized_PF/WR per §6.3 step 8)

**Volume Flow / NFE / RSI-KNN computation in strategy profile:**
The strategy sweeps `vfLenInput`, `vfFlowWeight`, `vfVolWeight`, `nfeLenInput`, `rsiKnnWindow`. These are STRATEGY oscillators, separate from the frozen Nexus signal. The strategy profile reproduces these in Python from OHLCV (matches Pine `mlVfBull/mlNfe/mlRsiKnn/mlConfluence` blocks) — these are simple to port and have no footprint dependency. Lift institutional profile's `_add_momentum()` if applicable.

---

## §7 IS / OOS data partition

### §7.1 The hard data constraint: footprint, not OHLCV

| Data type | Available range | Source |
|---|---|---|
| MES 5m **OHLCV** | 2020-01-01 → 2026-04-03 | `data/mes_5m.parquet` (Databento extracted, 441,852 rows verified) |
| MES 5m **real footprint** | ~6 months back from today (2025-10-28 onward, approximately) | TradingView `request.footprint()` storage limit |

**The bottleneck is footprint.** Simple Mode requires Nexus, Nexus is footprint-driven, and TV footprint history is ~6 months. The full IS+OOS window is bounded by the footprint capture, NOT by OHLCV availability. Per Kirk's correction: "we only have a year of data unless you use the MES download from databento" — Databento gives multi-year OHLCV, but it cannot give us footprint history.

### §7.2 Phase A window (footprint-bounded)

| Window | Range | Purpose |
|---|---|---|
| IS (in-sample) | 2025-04-28 → 2026-04-01 | ~11 months of contiguous bars where footprint is verifiable. All Phase A/B/etc tuning here. |
| Embargo | 2026-04-01 → 2026-04-08 | One-week gap |
| OOS (out-of-sample) | 2026-04-08 → 2026-04-28 | Champion validation only |

Bar Magnifier ON, slippage 1 tick, commission $1/side, point value $5, mintick 0.25.

**Hard rule:** `run_backtest()` filters `start_date <= df.ts < EMBARGO_START`. The profile defines `EMBARGO_START = "2026-04-01"` as a module constant. No trial sees OOS data.

### §7.3 Out-of-scope alternatives surfaced to Kirk

For completeness, two alternatives were considered and explicitly NOT recommended for Phase A:

| Alternative | What it gives | Why not for Phase A |
|---|---|---|
| OHLCV-only multi-year (2020-01-01+, no footprint) | yearly_consistency, full Trump-regime + pre-Trump | Strategy requires Nexus; no Nexus without footprint. Removing Nexus is an architecture change Kirk explicitly rejected ("Nexus required") |
| Synthetic footprint proxy (`(close-open)/range × volume` etc.) | yearly_consistency, full window | Kirk explicitly rejected: "no proxies" |

These remain available as **future Phase X** options if Phase A delivers a viable champion and Kirk decides to expand the validation window. Documented here so the choice is recorded, not lost.

---

## §8 Stage-by-stage execution plan with stop-points

> **Each stage requires Kirk's explicit "GO STAGE N" before advancing.**

### STAGE 0 — Pre-flight audit ← THIS DOCUMENT

**Output:** `docs/runbooks/wb_strat_5m_simple_phaseA_preflight.md`.
**Stop-point:** Kirk reviews §10 architecture decisions, replies `GO STAGE 1`.

### STAGE 1 — Pine strategy strip + restructure

**Files modified:** `indicators/v7-warbird-institutional-backtest-strategy.pine` only.
**Files created:** none.

Tasks:
1. Delete inputs in §2.1 (~30 inputs).
2. Delete code blocks in §2.2.
3. Add new inputs in §4.1 + helper `simpleLadderReclaim()` in §4.2.
4. Rewrite entry trigger to single Simple Mode path per §4.3.
5. Lock exit logic per §4.4 (TP at T2).
6. Replace any orphaned `ml_*` plot expressions with `na` (per §2.3) to preserve parity.
7. Run all 6 Pine guards:
   - `./scripts/guards/compile-pine.sh indicators/v7-warbird-institutional-backtest-strategy.pine`
   - `./scripts/guards/pine-lint.sh indicators/v7-warbird-institutional-backtest-strategy.pine`
   - `./scripts/guards/check-fib-scanner-guardrails.sh`
   - `./scripts/guards/check-contamination.sh`
   - `npm run build`
   - `./scripts/guards/check-indicator-strategy-parity.sh`
8. Show full diff to Kirk.

**Stop-point:** Kirk reviews diff, replies `GO STAGE 2`.

### STAGE 2 — Pine commit + push

1. Commit message describing exact deletions/additions.
2. `git commit` (no `--no-verify`).
3. `git push origin main`.
4. Kirk loads strategy on TV chart, manually points `Nexus Signal Source` at `Nexus ML Fast Test: nexus_signal_tier` plot, verifies defaults render the right setup.

**Stop-point:** Kirk replies `GO STAGE 3`.

### STAGE 3 — Manual baseline backtest

Kirk runs Strategy Tester Apr 28 2025 → Apr 1 2026 (IS only) with default Simple Mode. Reports:
- Trade count
- WR / PF / max DD
- No "Open" trade at end-of-data

**Acceptance criteria for Phase A safety:**
- 50 ≤ trades ≤ 2000
- No Open trade at end
- Max DD < 10%
- PF > 0.5

If criteria fail: defaults are wrong, iterate Stage 1. Otherwise: replies `GO STAGE 4`.

### STAGE 4 — Footprint parquet capture + profile build + parity unit test

Tasks:

1. **Capture full-window TV footprint export with all required columns.**
   - On TV chart with Nexus indicator loaded, MES1! 5m, date range **2025-04-28 → 2026-04-28** (covers IS + embargo + OOS).
   - **All Nexus `display=display.none` plots must be temporarily set to `display.all` in the Nexus pine file before exporting CSV** — TV's "Export chart data" only includes visible plots. After export, revert. (Nexus manifest notes this trick: "Converted from TradingView chart export containing nexus_fp_* columns after temporary display enablement for footprint export.")
   - Required columns per §5.3 — verify CSV header includes all 14 columns before conversion.
   - Convert CSV → parquet at `scripts/optuna/workspaces/v7_warbird_strategy_5m/tv_footprint_5m.parquet`.
   - Author manifest at `scripts/optuna/workspaces/v7_warbird_strategy_5m/tv_footprint_5m.manifest.json`.
   - Verify SHA-256 of parquet and manifest's `nexus_pine_sha256` matches `sha256sum indicators/warbird-nexus-machine-learning-rsi-optuna-fast-test.pine`.
   - Verify row count: ~75k 5m bars expected (1 year × 252 trading days × ~290 bars/day).

2. **Author profile module.**
   - File: `scripts/optuna/v7_warbird_strategy_5m_profile.py`.
   - Module-level constants:
     ```python
     EMBARGO_START = "2026-04-01"
     IS_START_DEFAULT = "2025-04-28"
     TV_FOOTPRINT_PATH = WORKSPACE_DIR / "tv_footprint_5m.parquet"
     TV_FOOTPRINT_ENV = "WARBIRD_STRAT_5M_TV_FOOTPRINT_PARQUET"
     TV_FOOTPRINT_MANIFEST_ENV = "WARBIRD_STRAT_5M_TV_FOOTPRINT_MANIFEST"
     ```
   - Reuse policy per §6.4 (do NOT import Nexus engine helpers).
   - `BOOL_PARAMS`, `NUMERIC_RANGES`, `INT_PARAMS`, `CATEGORICAL_PARAMS`, `INPUT_DEFAULTS` per §6.2.
   - `load_data()` joins parquet + `data/mes_5m.parquet` on `ts`; validates schema (all 14 columns from §5.3 present); validates manifest sha256 matches Nexus pine; returns DataFrame.
   - `run_backtest()` per §6.3 with explicit embargo filter `df = df[df.ts < EMBARGO_START]` after start_date filter.

3. **Smoke test (loads parquet, runs default config, prints metrics):**
   ```bash
   cd "/Volumes/Satechi Hub/warbird-pro"
   python3 -c "
   from scripts.optuna.v7_warbird_strategy_5m_profile import (
       BOOL_PARAMS, NUMERIC_RANGES, INT_PARAMS, CATEGORICAL_PARAMS,
       INPUT_DEFAULTS, load_data, run_backtest, EMBARGO_START,
   )
   print('Search dims:', len(NUMERIC_RANGES) + len(BOOL_PARAMS) + len(CATEGORICAL_PARAMS))
   df = load_data()
   print('Rows:', len(df), 'cols:', list(df.columns))
   print('Range:', df['ts'].min(), '→', df['ts'].max())
   print('Embargo cutoff:', EMBARGO_START)
   result = run_backtest(df, INPUT_DEFAULTS, start_date='2025-04-28')
   print('Default backtest:', result)
   "
   ```
   Acceptance: ~75k rows, columns include `nexus_signal_tier`, default backtest produces 50–2000 trades, PF > 0.5.

4. **Pine ↔ Python parity unit test (CRITICAL — catches profile drift before tuning starts).**
   - On TV chart with Strategy in default Simple Mode, run Strategy Tester 2025-04-28 → 2026-04-01.
   - Export trades CSV to `scripts/optuna/workspaces/v7_warbird_strategy_5m/tv_baseline_trades.csv`.
   - Run profile's default `run_backtest(INPUT_DEFAULTS, start_date='2025-04-28')`.
   - Compare first 20 trades:
     - **Entry bar timestamp:** ≤ 1-bar tolerance (Pine fills next bar; Python should match)
     - **Entry price:** ≤ 1 tick (`±0.25`) tolerance
     - **Exit price:** ≤ 1 tick tolerance
     - **Direction:** must match exactly
   - Trade-count delta: ≤ 5% acceptable on 200+ trades.
   - **If any trade differs by > 1 tick on entry/exit, profile is drifting from Pine — abort Stage 4, surface to Kirk.** This is the canonical "did we reproduce Pine semantics" gate. No tuning until this passes.
   - Output: `docs/runbooks/wb_strat_5m_phaseA_parity_check.md` with side-by-side trade table.

**Stop-point:** Kirk reviews profile, smoke test output, AND parity check report, replies `GO STAGE 5`.

### STAGE 5 — Optuna dry-run (10 trials)

```bash
cd "/Volumes/Satechi Hub/warbird-pro"

python3 scripts/optuna/runner.py \
  --indicator-key v7_warbird_strategy_5m \
  --profile-module scripts.optuna.v7_warbird_strategy_5m_profile \
  --study-name "Warbird Strategy 5m Simple Mode Dry Run" \
  --n-trials 10 \
  --start 2025-04-28
```

Verify:
- 10 trials complete in < 5 minutes
- Each trial writes to `study.db` at `scripts/optuna/workspaces/v7_warbird_strategy_5m/`
- Hub at `localhost:8090` shows the study card
- Optuna Dashboard at `localhost:8101/dashboard` shows the 10 trials with all swept params and scores

**Stop-point:** Kirk inspects dashboard, replies `GO STAGE 6`.

### STAGE 6 — Phase A launch (1000 trials)

```bash
cd "/Volumes/Satechi Hub/warbird-pro"

python3 scripts/optuna/runner.py \
  --indicator-key v7_warbird_strategy_5m \
  --profile-module scripts.optuna.v7_warbird_strategy_5m_profile \
  --study-name "Warbird Strategy 5m Full Surface Discovery" \
  --n-trials 1000 \
  --n-jobs 2 \
  --start 2025-04-28 \
  --top-n 10
```

**Wall-clock estimate:** ~30–60 minutes at `--n-jobs 2` (Python re-sim is fast, not 17 hours).

Kirk monitors at `localhost:8101/dashboard`. When all 1000 complete, replies `GO STAGE 7`.

### STAGE 7 — Phase A audit

**Output:** `docs/runbooks/wb_strat_5m_phaseA_audit.md`.

Tasks:
1. Pull top-10 by composite score from `study.db`.
2. Compute Optuna `get_param_importances()`.
3. Identify dims with <1% importance → lock candidates.
4. Identify dims at edge of ranges → widen candidates.
5. Identify TPE clusters and pruned-trial patterns.
6. Propose Phase B search space.

**Stop-point:** Kirk reviews, approves Phase B scope, replies `GO STAGE 8`.

### STAGE 8 — Phase B launch (1000 trials, refined surface)

Same as Stage 6 with new study name `Warbird Strategy 5m Active Dimension Refinement` and revised search space (locked dead dims, widened edge dims).

### STAGE 9+ — Iterate until top-10 stops moving

Continue phases until top-10 PF and trade count stabilize within ±5% across two consecutive phases.

### STAGE FINAL — OOS confirmation

Champion frozen in TV. Run single Strategy Tester pass 2026-04-08 → 2026-04-28. Pass: WR within 5pts of IS, PF > 1.0, no Open trade at end, max DD ≤ $4k.

Output: `docs/runbooks/wb_strat_5m_oos_validation.md` with go/no-go.

---

## §9 Architecture decisions requiring Kirk's GO

### A1 — Optuna-native Python re-simulation (replaces previous CDP proposal)

**Path:** Same as Nexus tune. Build `scripts/optuna/v7_warbird_strategy_5m_profile.py`. `runner.py` writes trials to `study.db`. Hub at 8090 already routes to `optuna-dashboard` at 8101 — same dashboard look as Nexus at 8102.

**Why this beats CDP-per-trial:**
- 1000 trials in 30–60 minutes vs 17h CDP
- Identical hub experience to Nexus tune
- No new CDP automation code; reuse hardened `runner.py`
- Phase B/C/D all run in same pattern

**Decision required:** ✅ approve / ❌ reject.

### A2 — Nexus signal reproduction in Python

**Proposal:** Strategy profile imports `_compute_core`, `_compute_knn`, `_compute_features` from `warbird_nexus_ml_rsi_profile.py` and feeds them frozen Nexus champion params (extracted in §5.2). Reproduces `nexus_signal_tier` per bar.

**Why frozen:** Nexus is at trial #936 champion of its own study. Strategy tuning should not co-tune Nexus parameters or it becomes a different, larger problem.

**Decision required:** ✅ approve / ❌ reject (rejection means Nexus state must be exported per-bar from TV instead).

### A3 — Footprint parquet capture covers 2025-04-28 → 2026-04-28

**Proposal:** Kirk performs the export at start of Stage 4. Existing Nexus parquet (Jan–Apr 2026) is insufficient.

**Decision required:** ✅ Kirk will capture / ❌ specify alternative.

### A4 — Direction-aware fib ladder masks

Two separate inputs `simpleFibLevelsLongMaskInput` (covers `.500/.618/.786/1.000`) and `simpleFibLevelsShortMaskInput` (covers `.500/.382/.236/0.000`), each 4-bit categorical (1–15).

**Decision required:** ✅ approve / ❌ specify alternative.

### A5 — Trial budget per phase

1000 trials per phase. Hold position. Estimated 3–5 phases until stabilization.

**Decision required:** ✅ confirm 1000/phase / ❌ adjust.

### A6 — Ranking policy (CORRECTED per Kirk 2026-04-28)

Phase A composite score: **`0.55 × normalized_PF + 0.45 × WR`**.

- `normalized_PF = min(PF, 3.0) / 3.0` (cap suspicious-perfection)
- `WR = wins / total_trades` in [0, 1]
- yearly_consistency dropped — IS window is ~11 months, no multi-year evidence available
- Top-10 export by composite score, with secondary sort by trade count (favor more-data champions on ties)

**Decision required:** ✅ approve `0.55 PF + 0.45 WR` / ❌ specify alternative weights.

### A7 — IS window 2025-04-28

Matches Kirk's manual Strategy Tester window. One-year IS, one-week embargo, 3-week OOS.

**Decision required:** ✅ approve / ❌ extend to 2025-01-01.

---

## §10 Risk register

| ID | Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|---|
| R1 | Parity guard fails after strip (orphaned `ml_*` plot expressions) | Medium | High — Stage 1 reverts | §2.3 explicit per-plot replacement table; abort + surface if guard fails |
| R2 | Footprint parquet capture has gaps (TV export quirks) | Medium | High — Phase A invalid | Stage 4 verifies row count + manifest sha + Nexus pine sha; abort if gaps |
| R3 | Pre-exported `nexus_signal_tier` mismatches what TV plots live (Nexus indicator updated between capture and tuning) | Low | High — tuning against stale Nexus | §5.2.1 manifest stores `nexus_pine_sha256`; Stage 4 verifies it matches current Nexus pine sha; runner refuses to load if mismatch |
| R4 | Pine entry/exit semantics not perfectly reproduced in Python (R4 is now THE primary risk since Nexus moved to parquet) | High | Critical — Optuna champion doesn't replay in TV | Stage 4 task 4: parity unit test on 20 trades, ≤1-tick tolerance, abort if any single trade differs > 1 tick. Must pass before any tuning launches. |
| R5 | OOS embargo violation | Low | Critical | `run_backtest()` filters `df[df.ts < EMBARGO_START]`; assert in profile module's `__main__` smoke test |
| R6 | Nexus pine indicator updated mid-tune (Kirk re-tunes Nexus while strategy phase runs) | Low | High — silent stale signal | Manifest sha verification at every `runner.py` invocation; refuse to load if drift detected |
| R7 | study.db has stray 1-trial study from prior session | Confirmed | Low — visual clutter | Delete before Stage 5 with: `optuna delete-study --study-name "Warbird Strategy 5m Main Engine Optimization" --storage sqlite:////path/to/study.db` |
| R8 | Hub fails to display new study | Low | Medium — manual workaround | Hub auto-detects on start; restart hub if not (`pkill -HUP -f warbird_optuna_hub`) |
| R9 | Profile pulls institutional `_simulate_outcome` but single-bracket adaptation breaks edge cases (no multi-target ratchet, simpler exit) | Medium | Medium — bad PF | Stage 4 task 4 parity test catches this; cross-check 5 trades manually (entry bar, exit bar, exit price) |
| R10 | TPE samples flood pruned trials | Medium | Medium — wasted compute | `--min-trades 50` floor + TrialPruned wrapper in objective; runner already enforces |
| R11 | Strategy ml_* plot dependencies on deleted vars cause Pine compile fail (caught early but easy to miss) | Medium | Medium — Stage 1 redo | §2.3 walks every plot; Stage 1 task 6 runs all 6 guards including parity check |
| R12 | Stage 4 export csv missing `nexus_signal_tier` because pine line 757 was display=none (TV doesn't export hidden plots) | High first time | High — parquet incomplete | Stage 4 task 1 explicit: "temporarily flip Nexus pine line 757 + all nexus_* hidden plots to `display=display.all` before export, revert after capture" |
| R13 | Footprint window doesn't actually start at 2025-04-28 (TV footprint storage shorter than expected) | Medium | High — IS window narrower than planned | Stage 4 task 1 verifies first-bar timestamp in manifest; abort if footprint coverage starts later than 2025-04-28; fall back to footprint-actual-start as IS_START with Kirk's approval |

---

## §11 Acceptance criteria

This audit is approvable when:
- §9 architecture decisions A1–A7 each have an explicit ✅ from Kirk.
- §2 strip list has Kirk's review (any "keep this" overrides recorded here).
- §4 add list has Kirk's review (any "rename / restructure" recorded here).
- §6.2 search space has Kirk's review.
- §7 IS/OOS partition has Kirk's review.
- §8 stop-points are accepted, OR specific stop-points removed/added with reason recorded.

When all approved, Kirk replies `GO STAGE 1` and Stage 1 begins.

---

## §12 Files this audit touched

- READ ONLY:
  - `indicators/v7-warbird-institutional-backtest-strategy.pine`
  - `indicators/warbird-nexus-machine-learning-rsi-optuna-fast-test.pine`
  - `scripts/optuna/runner.py`
  - `scripts/optuna/warbird_optuna_hub.py`
  - `scripts/optuna/warbird_nexus_ml_rsi_profile.py`
  - `scripts/optuna/v7_warbird_institutional_profile.py`
  - `scripts/optuna/workspaces/warbird_nexus_ml_rsi/tv_footprint_5m.manifest.json`
  - `scripts/optuna/workspaces/v7_warbird_strategy_5m/study.db` (sqlite read)
  - `docs/runbooks/wbv7_institutional_optuna.md`
  - `scripts/ag/tv_auto_tune.py` (verified NOT used in this path)
  - `scripts/ag/tune_strategy_params.py` (verified NOT used in this path)

- CREATED:
  - `docs/runbooks/wb_strat_5m_simple_phaseA_preflight.md` ← this file

- MODIFIED:
  - none

No git commits. No Pine edits. No Optuna runs.

---

## §13 Sign-off

Audit author: Claude Code (this session, 2026-04-28).
Awaiting Kirk's GO/NO-GO on §9.A1–A7.

Reply pattern:
```
GO STAGE 1
A1: APPROVE
A2: APPROVE
A3: I'll capture the parquet
A4: APPROVE
A5: 1000/phase confirmed
A6: APPROVE
A7: APPROVE 2025-04-28
[any §2/§4/§6/§7 overrides]
```
