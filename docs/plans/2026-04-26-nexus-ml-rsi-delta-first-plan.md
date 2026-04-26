# Nexus ML RSI — Delta-First Redesign Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Rebuild the Nexus ML RSI Optuna profile and Pine indicator around footprint cumulative delta as the primary signal driver, with four signal tiers, Warbird brand colors, delta-fade bar coloring, and 5m/15m/1H/4H modes tuned from the existing Nexus hub lane.

**Architecture:** Delta-first (footprint cumulative delta drives signal firing), oscillator confirmation (AMF: ROC + EWI + Stoch blend preserved unchanged), KNN validation on delta features. Four-tier signals: teal diamond (confirmed bull reversal), red diamond (confirmed bear reversal), white diamond (gassing out — delta fading, not flipped), yellow dot (oscillator signal but low volume/KNN neutral). One Nexus study lane covers the four-mode indicator; do not create duplicate per-timeframe lanes.

**Tech Stack:** Pine Script v6, Python 3, Optuna TPE, backtesting.py, ruff, pine-lint.sh, pine-facade TV compiler

**Design Doc:** `docs/plans/2026-04-26-nexus-ml-rsi-delta-first-redesign.md`

---

## Takeover Gate - 2026-04-26

**Current status:** BLOCKED for active Optuna launch.

This plan is now governed by the active Warbird indicator-only contract. Nexus
fast-test is not exempt when results are used for settings recommendations,
Pine defaults, Pine edits, champion claims, or promotion decisions.

The current profile work is quarantined until it is made evidence-clean:

- active source rows must be a manifest-backed Pine/TradingView export
- active delta features must be ask/bid footprint fields exported from Pine
- Nexus trigger family is `NEXUS_FOOTPRINT_DELTA`
- no Study A process, DB entry, or log exists for `nexus-5m-delta-first-v1`
- no Pine changes are approved or complete in this session

**Do not launch promotable Study A** until Phase 0 below is complete. The
existing `warbird_nexus_ml_rsi` hub study must not be resumed until the manifest
gate passes; historical raw-parquet trials remain non-promotable.

Required before active Study A:

1. Lock the exact indicator baseline: source path, version, commit, symbol,
   timeframe, inputs, plot/request budget, compile/lint status.
2. Use trigger family `NEXUS_FOOTPRINT_DELTA`.
3. Capture a TradingView/Pine export or CDP evidence package.
4. Save a manifest with date range, row/trade count, export method, export hash,
   exact inputs, and platform-limited fields.
5. Use the profile loader that consumes the manifest-backed export, not
   `data/mes_5m.parquet`.
6. Reserve "footprint delta" for ask/bid footprint evidence.
7. Resume `warbird_nexus_ml_rsi` only after the manifest gate passes.

---

## Phase 0: Strict Baseline Recovery

### Task 0.1: Contract classification

Choose one path before any new study:

- **Active tuning path:** update the active contract/spec/runbook set to define
  the Nexus trigger family and export fields.
- **Sandbox path:** document Nexus as non-promotable research. Sandbox results
  may inform hypotheses but cannot become champion settings or Pine defaults.

### Task 0.2: Pine/TradingView baseline lock

Record these facts in a manifest before modeling:

- indicator file and commit
- indicator version
- TradingView symbol and timeframe
- Pine input settings
- trigger family
- exported columns or Strategy Tester fields
- plot/request budget
- compile/lint status
- export date range
- row/trade count
- export hash

### Task 0.3: Profile source rewrite

Promotable Nexus tuning requires `warbird_nexus_ml_rsi_profile.py` to load a
manifest-backed Pine/TradingView export. The active hub profile now rejects
local OHLCV/parquet proxies. The planned manifest path is:

```text
scripts/optuna/workspaces/warbird_nexus_ml_rsi/pine_export_manifest.json
```

The manifest may also be selected with `WARBIRD_NEXUS_EXPORT_MANIFEST`.

---

## Phase 1: Optuna Profile Rebuild (5m Study A)

**Gate:** Tasks 1-3 are superseded. Do not add synthetic OHLCV delta helpers or
synthetic delta feature columns to the active Nexus profile.

### Task 1: Enforce manifest-backed source loading

**Status:** DONE for source gating; blocked only by missing export manifest.

`scripts/optuna/warbird_nexus_ml_rsi_profile.py` now requires the manifest path
above or `WARBIRD_NEXUS_EXPORT_MANIFEST`.

### Task 2: Require true footprint delta fields

**Status:** DONE in the active profile.

The active profile requires one of these manifest/export surfaces:

- `nexus_fp_available`
- `nexus_fp_bar_delta`
- `nexus_fp_total_volume`
- optional precomputed `nexus_norm_cum_delta`, `nexus_delta_slope`, and
  `nexus_bar_delta_ratio` exported from Pine/TradingView footprint logic

Synthetic candle-body delta is not an active feature source.

### Task 3: Keep tunable evaluation parameters

**Status:** DONE in the active profile.

The profile keeps the evaluation horizon and delta threshold parameters, but all
delta calculations start from exported footprint fields.

---

### Task 4: Add `_label_setups()` — success/failure pre-move labeling

**Files:**
- Modify: `scripts/optuna/warbird_nexus_ml_rsi_profile.py` — add new method to profile class

**Step 1: Add the labeling method**

```python
def _label_setups(
    self,
    df: pd.DataFrame,
    signal_mask: np.ndarray,
    params: dict,
    direction: int,          # +1 = bull, -1 = bear
) -> tuple[np.ndarray, np.ndarray]:
    """
    Returns (success_mask, failure_mask) aligned to signal_mask.

    SUCCESS: signal bar → price moves leg_threshold_pts in direction
             within response_bars bars before adverse_bars-bar adverse.
    FAILURE: signal fired but adverse move happened first OR neither
             threshold reached within response_bars.
    """
    close    = df["close"].values
    n        = len(close)
    leg_pts  = params["leg_threshold_pts"]
    r_bars   = int(params["response_bars"])
    adv_bars = int(params["adverse_bars"])

    success = np.zeros(n, dtype=bool)
    failure = np.zeros(n, dtype=bool)

    for i in np.where(signal_mask)[0]:
        if i + r_bars >= n:
            failure[i] = True
            continue
        entry = close[i]
        hit_success = False
        hit_failure = False
        for j in range(1, r_bars + 1):
            if i + j >= n:
                break
            move = (close[i + j] - entry) * direction
            if move >= leg_pts:
                hit_success = True
                break
            if j <= adv_bars and move <= -leg_pts * 0.5:
                hit_failure = True
                break
        if hit_success:
            success[i] = True
        else:
            failure[i] = True

    return success, failure
```

**Step 2: Run ruff + py_compile**

```bash
cd "/Volumes/Satechi Hub/warbird-pro"
ruff check scripts/optuna/warbird_nexus_ml_rsi_profile.py && python3 -m py_compile scripts/optuna/warbird_nexus_ml_rsi_profile.py && echo "PASS"
```

**Step 3: Commit**

```bash
git add scripts/optuna/warbird_nexus_ml_rsi_profile.py
git commit -m "optuna: add _label_setups success/failure pre-move labeler"
```

---

### Task 5: Rewrite `run_backtest()` with delta-first objective

**Files:**
- Modify: `scripts/optuna/warbird_nexus_ml_rsi_profile.py` — `run_backtest()` method

**Step 1: Replace objective scoring with delta-first formula**

The new `run_backtest()` computes five sub-scores and combines them:

```python
def run_backtest(self, df: pd.DataFrame, params: dict) -> float:
    features = self._compute_features(df, params)
    signals  = self._generate_signals(features, params)

    bull_mask = signals["bull_signal"].values.astype(bool)
    bear_mask = signals["bear_signal"].values.astype(bool)
    gasout_bull = signals.get("gasout_bull", pd.Series(False, index=df.index)).values.astype(bool)
    gasout_bear = signals.get("gasout_bear", pd.Series(False, index=df.index)).values.astype(bool)

    # ── Reversal precision ────────────────────────────────────────────────
    bull_succ, bull_fail = self._label_setups(df, bull_mask, params, +1)
    bear_succ, bear_fail = self._label_setups(df, bear_mask, params, -1)

    total_signals = bull_mask.sum() + bear_mask.sum()
    if total_signals < 5:
        return 0.0

    total_succ = bull_succ.sum() + bear_succ.sum()
    reversal_precision = total_succ / max(total_signals, 1)

    # ── Early entry quality ───────────────────────────────────────────────
    early = int(params["early_bars"])
    close = df["close"].values
    early_hits = 0
    early_total = int(bull_succ.sum() + bear_succ.sum())
    for direction, succ_mask in [(+1, bull_succ), (-1, bear_succ)]:
        for i in np.where(succ_mask)[0]:
            entry = close[i]
            for j in range(1, early + 1):
                if i + j < len(close):
                    move = (close[i + j] - entry) * direction
                    if move >= params["leg_threshold_pts"] * 0.5:
                        early_hits += 1
                        break
    early_entry_quality = early_hits / max(early_total, 1)

    # ── Gassing out accuracy ──────────────────────────────────────────────
    gasout_mask = gasout_bull | gasout_bear
    if gasout_mask.sum() > 0:
        gasout_correct = 0
        for i in np.where(gasout_mask)[0]:
            direction = +1 if gasout_bull[i] else -1
            entry = close[i]
            stall = int(params["gasout_stall_bars"])
            stalled = True
            for j in range(1, stall + 1):
                if i + j < len(close):
                    move = (close[i + j] - entry) * direction
                    if move >= params["leg_threshold_pts"]:
                        stalled = False
                        break
            if stalled:
                gasout_correct += 1
        gasout_accuracy = gasout_correct / gasout_mask.sum()
    else:
        gasout_accuracy = 0.5  # neutral if no gasout signals

    # ── False continuation avoidance ─────────────────────────────────────
    false_avoidance = 1.0 - (bull_fail.sum() + bear_fail.sum()) / max(total_signals, 1)

    # ── Signal rate in target band (4–10/day on 5m = ~48–120 bars) ───────
    bars_per_day = 78  # regular session MES (9:30–16:00 ET)
    total_bars   = len(df)
    trading_days = max(total_bars / bars_per_day, 1.0)
    signals_per_day = total_signals / trading_days
    target_lo, target_hi = 4.0, 10.0
    if target_lo <= signals_per_day <= target_hi:
        signal_rate_score = 1.0
    elif signals_per_day < target_lo:
        signal_rate_score = max(0.0, signals_per_day / target_lo)
    else:
        signal_rate_score = max(0.0, 1.0 - (signals_per_day - target_hi) / target_hi)

    # ── Composite score ───────────────────────────────────────────────────
    score = (
        0.40 * reversal_precision
        + 0.25 * early_entry_quality
        + 0.15 * gasout_accuracy
        + 0.10 * false_avoidance
        + 0.10 * signal_rate_score
    )
    return float(np.clip(score, 0.0, 1.0))
```

**Step 2: Run ruff + py_compile**

```bash
cd "/Volumes/Satechi Hub/warbird-pro"
ruff check scripts/optuna/warbird_nexus_ml_rsi_profile.py && python3 -m py_compile scripts/optuna/warbird_nexus_ml_rsi_profile.py && echo "PASS"
```

**Step 3: Commit**

```bash
git add scripts/optuna/warbird_nexus_ml_rsi_profile.py
git commit -m "optuna: rewrite run_backtest with delta-first 5-component objective"
```

---

### Task 6: Smoke test the rebuilt profile (1 trial, after Phase 0)

**Files:**
- Read: `scripts/optuna/runner.py` — verify it imports and calls the profile correctly

**Step 1: Run a single-trial smoke test only after the profile consumes the
manifest-backed Pine/TradingView export**

```bash
cd "/Volumes/Satechi Hub/warbird-pro"
python3 scripts/optuna/runner.py \
    --indicator-key warbird_nexus_ml_rsi \
    --profile-module scripts.optuna.warbird_nexus_ml_rsi_profile \
    --study-name "nexus-delta-smoke" \
    --n-trials 1 \
    --start <manifest-start-date> \
    2>&1 | tail -20
```

Expected: `Trial 0 finished with value: X.XXX` with no stack traces and the
trial user attributes matching the manifest-backed source. A raw-parquet smoke
test does not open the active Study A gate.

**Step 2: Fix any import or runtime errors before proceeding**

If the smoke test fails, read the full traceback and fix before Step 3.

**Step 3: Commit smoke-test confirmation note to plan doc**

Edit this plan doc's Progress table to update Task 6 status to DONE once smoke passes.

---

### Task 7: Launch Study A — existing Nexus lane, 1000 trials (blocked until Phase 0)

**Files:**
- Run: `scripts/optuna/runner.py`

**Step 1: Launch Study A only after Phase 0 and Task 6 pass**

Before running this command, set `launch_enabled` back to `true` in
`scripts/optuna/indicator_registry.json` and record the approved manifest path.

```bash
cd "/Volumes/Satechi Hub/warbird-pro"
python3 scripts/optuna/runner.py \
    --indicator-key warbird_nexus_ml_rsi \
    --profile-module scripts.optuna.warbird_nexus_ml_rsi_profile \
    --study-name "Warbird Nexus ML Fast 5m Signal Quality April 25" \
    --n-trials 1000 \
    --start <manifest-start-date> \
    --top-n 10 \
    2>&1 | tee scripts/optuna/workspaces/warbird_nexus_ml_rsi/study_a.log &
echo "Study A launched — PID $!"
```

**Step 2: Monitor until completion**

```bash
tail -f scripts/optuna/workspaces/warbird_nexus_ml_rsi/study_a.log
```

Expected: 1000 completed trials with the same manifest identity. Do not use a
score threshold alone as evidence; compare against manifest, signal count,
feature availability, and later IS/OOS or walk-forward review.

**Step 3: Extract champion params**

```bash
python3 -c "
import optuna
study = optuna.load_study(
    study_name='nexus-5m-delta-first-v1',
    storage='sqlite:///scripts/optuna/workspaces/warbird_nexus_ml_rsi/study.db',
)
t = study.best_trial
print(f'Best trial: #{t.number}  score={t.value:.6f}')
for k, v in sorted(t.params.items()):
    print(f'  {k}: {v}')
"
```

**Step 4: Record champion params**

Save the output to this plan doc's §Champion Parameters section (add below Progress table).

**Step 5: Commit log + plan update**

```bash
git add docs/plans/2026-04-26-nexus-ml-rsi-delta-first-plan.md
git commit -m "optuna: Study A complete — record champion params"
```

---

## Phase 2: Pine Indicator Update

**Gate:** Phase 2 is blocked. Do not edit the Nexus fast-test Pine file from
this plan until there is explicit current-session Pine approval, a locked
Pine/TradingView baseline manifest, priced plot/request budget, a verified
compile/lint path, and true ask/bid footprint evidence available through
`request.footprint()` or exported Pine fields.

### Task 8: Add Mode input and per-mode parameter presets

**Files:**
- Modify: `indicators/warbird-nexus-machine-learning-rsi-optuna-fast-test.pine`

**Gate:** do not wire mode presets until manifest-backed Study A/B/C/D champion
values exist. Do not reuse placeholder values as defaults.

**Step 1: Add Mode input at top of inputs section**

```pine
modeInput = input.string("5m", "Mode", options=["5m", "15m", "1H", "4H"],
    tooltip="Select chart timeframe. Each mode uses champion Optuna settings for that TF.")
```

**Step 2: Add mode-keyed parameter defaults only after champion evidence exists**

Preserve the current defaults until each mode has its own manifest-backed
champion parameters. When evidence exists, wire each value from that mode's
study manifest:

```pine
i_enginePeriod = modeInput == "5m"  ? <study_a_engine_period> :
                 modeInput == "15m" ? <study_b_engine_period> :
                 modeInput == "1H"  ? <study_c_engine_period> :
                                       <study_d_engine_period>
```

Repeat for `i_signalPeriod`, `i_knnWindow`, `i_knnK`, `i_knnBull`, and
`i_knnBear` after all four studies complete.

**Step 3: Run pine-lint and pine-facade**

```bash
cd "/Volumes/Satechi Hub/warbird-pro"
./scripts/guards/pine-lint.sh indicators/warbird-nexus-machine-learning-rsi-optuna-fast-test.pine
```

Then via MCP: `pine_smart_compile` on the indicator file.

**Step 4: Commit**

```bash
git add indicators/warbird-nexus-machine-learning-rsi-optuna-fast-test.pine
git commit -m "Pine: add Mode input (5m/15m/1H/4H) to nexus fast-test"
```

---

### Task 9: Fix bear color to Warbird red `#cc0000`

**Files:**
- Modify: `indicators/warbird-nexus-machine-learning-rsi-optuna-fast-test.pine`

**Step 1: Find all bear/short color references**

```bash
grep -n "color\." indicators/warbird-nexus-machine-learning-rsi-optuna-fast-test.pine | grep -iE "red|bear|short|orange|f23|e53|ff0000"
```

**Step 2: Replace with `#cc0000`**

Replace all bear-direction color definitions with `color.new(#cc0000, <transparency>)`. Do NOT change bull colors (keep `#26C6DA`).

**Step 3: Run pine-lint**

```bash
./scripts/guards/pine-lint.sh indicators/warbird-nexus-machine-learning-rsi-optuna-fast-test.pine
```

**Step 4: Commit**

```bash
git add indicators/warbird-nexus-machine-learning-rsi-optuna-fast-test.pine
git commit -m "Pine: fix bear color to Warbird red #cc0000"
```

---

### Task 10: Enable watermark by default

**Files:**
- Modify: `indicators/warbird-nexus-machine-learning-rsi-optuna-fast-test.pine`

**Step 1: Find the watermark input**

```bash
grep -n -i "watermark\|Show Watermark" indicators/warbird-nexus-machine-learning-rsi-optuna-fast-test.pine
```

**Step 2: Change default from `false` to `true`**

```pine
// Before:
showWatermark = input.bool(false, "Show Watermark")
// After:
showWatermark = input.bool(true, "Show Watermark")
```

**Step 3: Run pine-lint**

```bash
./scripts/guards/pine-lint.sh indicators/warbird-nexus-machine-learning-rsi-optuna-fast-test.pine
```

**Step 4: Commit**

```bash
git add indicators/warbird-nexus-machine-learning-rsi-optuna-fast-test.pine
git commit -m "Pine: enable watermark by default"
```

---

### Task 11: Add true footprint cumulative delta computation layer

**Files:**
- Modify: `indicators/warbird-nexus-machine-learning-rsi-optuna-fast-test.pine`

**Gate:** Do not execute this task without explicit current-session Pine edit
approval, Pine budget pricing, a verified compile/lint path, and ask/bid
footprint evidence from TradingView/Pine. An OHLCV reconstruction is not
acceptable for this task.

**Step 1: Verify footprint budget**

```bash
grep -c "request\.footprint\|request\.security\|plot\|plotshape\|plotarrow\|plotchar\|plotbar\|plotcandle\|hline\|bgcolor\|barcolor\|fill\|label\|line\|box\|table" indicators/warbird-nexus-machine-learning-rsi-optuna-fast-test.pine
```

Confirm output calls ≤ 64. (CLAUDE.md budget: 58/64 on institutional — fast-test may differ.)

**Step 2: Add delta inputs**

```pine
i_deltaLookback = input.int(10, "Delta Lookback", minval=3, maxval=20, group="Delta")
i_deltaFlipThresh = input.float(0.10, "Delta Flip Threshold", minval=0.05, maxval=0.40, step=0.01, group="Delta")
i_gasoutThresh = input.float(-0.08, "Gas-Out Threshold", minval=-0.20, maxval=-0.01, step=0.01, group="Delta")
```

**Step 3: Add true footprint delta computation**

Do not use `body_direction * body_ratio * volume` here. This layer must consume
ask/bid footprint volume from `request.footprint()` or exported Pine fields
already named in the run manifest. Minimum calculations:

- `barDelta = askVolume - bidVolume`
- `cumDelta = rolling sum(barDelta, i_deltaLookback)`
- `normCumDelta = cumDelta / max(avgVolume * i_deltaLookback, 1.0)`
- `deltaSlope = normCumDelta - normCumDelta[lookback_half]`
- `deltaDir = 1/-1/0` from `i_deltaFlipThresh`

**Step 4: Run pine-lint + pine-facade**

```bash
./scripts/guards/pine-lint.sh indicators/warbird-nexus-machine-learning-rsi-optuna-fast-test.pine
```

Then `pine_smart_compile` via MCP.

**Step 5: Commit**

```bash
git add indicators/warbird-nexus-machine-learning-rsi-optuna-fast-test.pine
git commit -m "Pine: add true footprint cumulative delta computation layer"
```

---

### Task 12: Add white diamond tier (gassing out) + wire teal/red/white to signal conditions

**Files:**
- Modify: `indicators/warbird-nexus-machine-learning-rsi-optuna-fast-test.pine`

**Gate:** complete in the active Pine surface; white diamonds and red/teal gates
are wired to `request.footprint()` variables only.

**Step 1: Add gassing-out detection**

```pine
// ── Gassing out: price continuing but delta fading ─────────────────────────
gasOutBull = normCumDelta > 0.0 and deltaSlope < i_gasoutThresh     // bull continuing, delta dropping
gasOutBear = normCumDelta < 0.0 and deltaSlope > -i_gasoutThresh    // bear continuing, delta rising
```

**Step 2: Add delta gates to existing bull/bear diamond conditions**

Find the existing bull/bear signal condition. Add delta flip confirmation:

```pine
// Existing condition (example — find actual variable names):
// bullSignal = oscCrossUp and knnBull
// bearSignal = oscCrossDown and knnBear

// Delta-gated version:
bullSignal = oscCrossUp  and knnBull and deltaDir == 1
bearSignal = oscCrossDown and knnBear and deltaDir == -1
```

**Step 3: Update plotshape calls**

```pine
// Bull diamond — Warbird teal
plotshape(bullSignal, style=shape.diamond, location=location.belowbar,
    color=color.new(#26C6DA, 0), size=size.normal, title="Bull Reversal")

// Bear diamond — Warbird red
plotshape(bearSignal, style=shape.diamond, location=location.abovebar,
    color=color.new(#cc0000, 0), size=size.normal, title="Bear Reversal")

// White diamond — gassing out
plotshape(gasOutBull, style=shape.diamond, location=location.belowbar,
    color=color.new(#FFFFFF, 30), size=size.small, title="Gassing Out Bull")
plotshape(gasOutBear, style=shape.diamond, location=location.abovebar,
    color=color.new(#FFFFFF, 30), size=size.small, title="Gassing Out Bear")
```

**Step 4: Run full verification pipeline**

```bash
cd "/Volumes/Satechi Hub/warbird-pro"
./scripts/guards/pine-lint.sh indicators/warbird-nexus-machine-learning-rsi-optuna-fast-test.pine
./scripts/guards/check-contamination.sh
npm run build
```

Then `pine_smart_compile` via MCP.

**Step 5: Commit**

```bash
git add indicators/warbird-nexus-machine-learning-rsi-optuna-fast-test.pine
git commit -m "Pine: add white diamond gassing-out tier + delta gates on teal/red diamonds"
```

---

### Task 13: Add delta-fade bar coloring

**Files:**
- Modify: `indicators/warbird-nexus-machine-learning-rsi-optuna-fast-test.pine`

**Gate:** blocked until Task 11 has true footprint variables. Bar color must
reflect ask/bid delta conviction, not synthetic candle-body direction.

**Step 1: Add barcolor with conviction-faded transparency**

```pine
// ── Delta-conviction bar coloring ─────────────────────────────────────────
deltaConviction = math.abs(normCumDelta)
barTransp       = int(math.max(15.0, math.min(88.0, 88.0 - deltaConviction * 73.0)))
barcolor(deltaDir == 1  ? color.new(#26C6DA, barTransp) :
         deltaDir == -1 ? color.new(#cc0000, barTransp) :
                          color.new(#888888, 80),
         title="Delta Bar Color")
```

**Step 2: Suppress bar coloring suppression rule — no bear diamonds in green zone**

The delta gate in Task 12 already handles this: `bearSignal` requires `deltaDir == -1`, which means cumulative delta has actually flipped negative. Bars still in green delta (`deltaDir == 1`) cannot fire a bear diamond. Verify this logic is correct by tracing the condition chain.

**Step 3: Run full verification pipeline**

```bash
cd "/Volumes/Satechi Hub/warbird-pro"
./scripts/guards/pine-lint.sh indicators/warbird-nexus-machine-learning-rsi-optuna-fast-test.pine
./scripts/guards/check-contamination.sh
npm run build
```

**Step 4: Commit**

```bash
git add indicators/warbird-nexus-machine-learning-rsi-optuna-fast-test.pine
git commit -m "Pine: add delta-fade bar coloring (teal/red/gray by conviction)"
```

---

## Phase 3: Mode Studies Retained On Existing Hub Lane

Keep 5m, 15m, 1H, and 4H as first-class Nexus modes. Do not create duplicate
profile modules, registry keys, alternate hubs, or replacement workspaces for
those modes. Run each mode through the existing `warbird_nexus_ml_rsi` hub lane
using a manifest-backed TradingView export from the selected Pine `Mode`.

Every mode export must include both the real footprint fields and
`nexus_mode_minutes`; rows missing the mode export are invalid. Per-mode Pine
defaults stay blocked until that mode has a manifest-backed champion.

---

## Progress Table

| Phase | Task | Status | Notes |
|-------|------|--------|-------|
| Pre  | Design doc | DONE | `docs/plans/2026-04-26-nexus-ml-rsi-delta-first-redesign.md` commit bb0c918 |
| Pre  | Implementation plan | DONE | This doc, commit 874b9e8 |
| QA takeover | Strict contract gate | DONE | Active tuning requires Pine/TradingView export + manifest before Study A |
| Phase 0 | Contract classification | DONE | Nexus trigger family is `NEXUS_FOOTPRINT_DELTA` |
| Phase 0 | Baseline + manifest | BLOCKED | No manifest-backed Pine/TradingView export exists yet |
| Phase 0 | Profile manifest gate | DONE | Active profile refuses OHLCV/parquet rows and requires a manifest-backed TradingView export |
| Phase 1 | Task 1: Manifest source gate | DONE | Loader requires `pine_export_manifest.json` or `WARBIRD_NEXUS_EXPORT_MANIFEST` |
| Phase 1 | Task 2: True footprint field gate | DONE | Required `nexus_fp_*` fields come from Pine `request.footprint()` exports |
| Phase 1 | Task 3: Synthetic delta quarantine | DONE | OHLCV/parquet delta proxy removed from active profile |
| Phase 1 | Task 4: _label_setups() | DONE | vectorized inner loop (commit 254a58b) |
| Phase 1 | Task 5: Rewrite run_backtest() | DONE | 5-component objective + runner aliases |
| Phase 1 | Task 6: Smoke test (1 trial) | QUARANTINED | raw-parquet smoke does not open active Study A gate |
| Phase 1 | Task 7: Study A (1000 trials) | BLOCKED | no run, no log, no DB entry; wait for TradingView export manifest |
| Phase 2 | Task 8: Mode input + presets | PARTIAL | 5m/15m/1H/4H Mode input restored; evidence-backed per-mode defaults still pending |
| Phase 2 | Task 9: Bear color #cc0000 | DONE | Nexus fast-test uses Warbird red |
| Phase 2 | Task 10: Watermark default=true | DONE | Existing default retained and Warbird Pro watermark restored |
| Phase 2 | Task 11: True footprint delta layer | DONE | Pine caches one `request.footprint()` path and exports `nexus_fp_*` fields |
| Phase 2 | Task 12: White diamond + delta gates | DONE | Gas-out diamonds and delta-confirmed reversal triggers restored |
| Phase 2 | Task 13: Delta-fade bar coloring | DONE | Bar colors now fade by real footprint delta conviction |
| Phase 3 | Mode studies B/C/D | RETAINED | 15m/1H/4H remain active modes on the existing Nexus hub lane; no duplicate profile keys |

---

## Champion Parameters (filled in after each study)

### Study A — 5m

| Parameter | Champion Value | Notes |
|-----------|---------------|-------|
| (none) | | Study A is blocked until a manifest-backed Pine/TradingView export exists |

### Study B — 15m

| Parameter | Champion Value | Notes |
|-----------|---------------|-------|
| (none) | | Blocked until a manifest-backed 15m Pine/TradingView export with `nexus_mode_minutes = 15` exists |

### Study C — 1H

| Parameter | Champion Value | Notes |
|-----------|---------------|-------|
| (none) | | Blocked until a manifest-backed 1H Pine/TradingView export with `nexus_mode_minutes = 60` exists |

### Study D — 4H

| Parameter | Champion Value | Notes |
|-----------|---------------|-------|
| (none) | | Blocked until a manifest-backed 4H Pine/TradingView export with `nexus_mode_minutes = 240` exists |

No current Nexus Optuna result is promotable as a champion setting or Pine
default for any mode. Existing raw-parquet trials may be reviewed only as
sandbox hypothesis material.

---

## Rollback Plan

- All changes are isolated to `warbird-nexus-machine-learning-rsi-optuna-fast-test.pine` (fast-test copy). `v7-warbird-institutional.pine` and `v7-warbird-strategy.pine` are NOT touched.
- To rollback Pine: `git checkout <prior-commit> -- indicators/warbird-nexus-machine-learning-rsi-optuna-fast-test.pine`
- Optuna studies are additive. The old `nexus-fast-5m-optuna` study remains in `optuna.db` and is unaffected.
