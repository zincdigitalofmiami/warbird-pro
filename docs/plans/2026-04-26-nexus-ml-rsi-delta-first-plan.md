# Nexus ML RSI — Delta-First Redesign Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Rebuild the Nexus ML RSI Optuna profile and Pine indicator around TradingView `request.footprint()` cumulative delta as the primary signal driver, with four signal tiers, Warbird brand colors, delta-fade bar coloring, and per-mode Optuna studies tuned for real 10+ point MES reversal legs.

**Architecture:** Delta-first (TradingView footprint cumulative delta drives signal firing), oscillator confirmation (AMF: ROC + EWI + Stoch blend preserved unchanged), KNN validation on delta features. Four-tier signals: teal diamond (confirmed bull reversal), red diamond (confirmed bear reversal), white diamond (gassing out — delta fading, not flipped), yellow dot (oscillator signal but low volume/KNN neutral). Four-mode indicator with separate Optuna study per mode.

**Hard Data Rule:** Nexus Optuna must not tune from CSV exports, local OHLCV parquet, Databento-derived bars, or synthetic body/wick delta. The only valid delta source is TradingView/Pine `request.footprint()` evidence captured into a manifest-backed `nexus_fp_*` footprint snapshot.

**Tech Stack:** Pine Script v6, Python 3, Optuna TPE, backtesting.py, ruff, pine-lint.sh, pine-facade TV compiler

**Design Doc:** `docs/plans/2026-04-26-nexus-ml-rsi-delta-first-redesign.md`

---

## Phase 1: Optuna Profile Rebuild (5m Study A)

### Task 1: Add TV footprint delta contract and helpers to profile

**Files:**
- Modify: `scripts/optuna/warbird_nexus_ml_rsi_profile.py` (after line ~217, before `class NexusMLRSIProfile`)

**Step 1: Add the TradingView footprint input contract and delta helpers**

Delete any local `mes_5m.parquet` / `mes_1m.parquet` loader and any synthetic
OHLCV delta helper. The profile must load only a manifest-backed TradingView
footprint snapshot with these Pine-derived columns:

- `nexus_fp_available`
- `nexus_fp_bar_delta`
- `nexus_fp_total_volume`

Keep only true delta helpers that operate on the TradingView/Pine footprint
series:

```python
# ── Delta helpers ─────────────────────────────────────────────────────────────

def _cumulative_delta(bar_delta: np.ndarray, lookback: float) -> np.ndarray:
    lb = max(int(lookback), 1)
    return _series(bar_delta).rolling(lb, min_periods=1).sum().to_numpy(dtype=np.float64)


def _delta_slope(cumulative_delta: np.ndarray, slope_len: float) -> np.ndarray:
    sl = max(int(slope_len), 1)
    shifted = np.roll(cumulative_delta, sl)
    shifted[:sl] = cumulative_delta[0]
    return cumulative_delta - shifted
```

**Step 2: Run ruff + py_compile**

```bash
cd "/Volumes/Satechi Hub/warbird-pro"
ruff check scripts/optuna/warbird_nexus_ml_rsi_profile.py && python3 -m py_compile scripts/optuna/warbird_nexus_ml_rsi_profile.py && echo "PASS"
```

Expected: `PASS` with no errors

**Step 3: Commit**

```bash
git add scripts/optuna/warbird_nexus_ml_rsi_profile.py
git commit -m "optuna: add delta helper functions to nexus profile"
```

---

### Task 2: Add tunable delta + evaluation parameters

**Files:**
- Modify: `scripts/optuna/warbird_nexus_ml_rsi_profile.py` — `suggest_params()` method

**Step 1: Replace the hardcoded evaluation constants and add delta params**

Find and replace the block that defines `ENTRY_RESPONSE_BARS`, `FAST_RESPONSE_BARS`, `CONTEXT_RESPONSE_BARS` as module-level constants. These move into `suggest_params()` as tunable values:

```python
# ── Evaluation horizon (formerly hardcoded) ────────────────────────────────
params["leg_threshold_pts"] = trial.suggest_float("leg_threshold_pts", 6.0, 20.0)
params["response_bars"]     = trial.suggest_int("response_bars", 5, 25)
params["early_bars"]        = trial.suggest_int("early_bars", 2, 10)
params["adverse_bars"]      = trial.suggest_int("adverse_bars", 3, 15)

# ── Delta parameters ────────────────────────────────────────────────────────
params["delta_lookback"]    = trial.suggest_int("delta_lookback", 3, 20)
params["delta_slope_len"]   = trial.suggest_int("delta_slope_len", 2, 10)
params["gasout_stall_bars"] = trial.suggest_int("gasout_stall_bars", 2, 8)
params["delta_flip_thresh"] = trial.suggest_float("delta_flip_thresh", 0.05, 0.40)
params["gasout_thresh"]     = trial.suggest_float("gasout_thresh", -0.20, -0.01)
```

Remove the old module-level constants:
```python
# DELETE these lines:
ENTRY_RESPONSE_BARS = 5
FAST_RESPONSE_BARS  = 3
CONTEXT_RESPONSE_BARS = 3
```

**Step 2: Run ruff + py_compile**

```bash
cd "/Volumes/Satechi Hub/warbird-pro"
ruff check scripts/optuna/warbird_nexus_ml_rsi_profile.py && python3 -m py_compile scripts/optuna/warbird_nexus_ml_rsi_profile.py && echo "PASS"
```

**Step 3: Commit**

```bash
git add scripts/optuna/warbird_nexus_ml_rsi_profile.py
git commit -m "optuna: make evaluation horizon + delta params tunable"
```

---

### Task 3: Wire TradingView footprint delta features into `_compute_features()`

**Files:**
- Modify: `scripts/optuna/warbird_nexus_ml_rsi_profile.py` — `_compute_features()` / `_compute_core()` methods

**Step 1: Add delta computation from `nexus_fp_*` fields at the top of `_compute_features()`**

After the existing feature computation (VNVF etc.), add. Do not reconstruct
delta from OHLCV:

```python
# ── TradingView request.footprint() cumulative delta ────────────────────────
bar_dlt   = df["nexus_fp_bar_delta"].values
total_vol = np.maximum(df["nexus_fp_total_volume"].values, 1.0)
cum_dlt   = _cumulative_delta(bar_dlt, params["delta_lookback"])
avg_vol   = _series(total_vol).rolling(
                max(int(params["delta_lookback"]), 1), min_periods=1
            ).mean().to_numpy(dtype=np.float64)
norm_cum  = cum_dlt / np.maximum(avg_vol * params["delta_lookback"], 1.0)
norm_cum  = np.clip(norm_cum, -1.0, 1.0)
dlt_slope = _delta_slope(cum_dlt, params["delta_slope_len"])

bar_ratio = np.clip(bar_dlt / total_vol, -1.0, 1.0)

price_pos = (df["close"].values - df["low"].values) / np.maximum(
                df["high"].values - df["low"].values, 1e-9
            )

features["delta_slope"]      = dlt_slope
features["norm_cum_delta"]   = norm_cum
features["bar_delta_ratio"]  = bar_ratio
features["price_position"]   = price_pos
```

Also expose these arrays on the dataframe for use in `_label_setups()`:
```python
df = df.copy()
df["_bar_dlt"]   = bar_dlt
df["_norm_cum"]  = norm_cum
df["_dlt_slope"] = dlt_slope
```

**Step 2: Run ruff + py_compile**

```bash
cd "/Volumes/Satechi Hub/warbird-pro"
ruff check scripts/optuna/warbird_nexus_ml_rsi_profile.py && python3 -m py_compile scripts/optuna/warbird_nexus_ml_rsi_profile.py && echo "PASS"
```

**Step 3: Commit**

```bash
git add scripts/optuna/warbird_nexus_ml_rsi_profile.py
git commit -m "optuna: wire delta features into _compute_features"
```

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

### Task 6: Smoke test the rebuilt profile (1 trial)

**Files:**
- Read: `scripts/optuna/runner.py` — verify it imports and calls the profile correctly

**Step 1: Run a single-trial smoke test**

```bash
cd "/Volumes/Satechi Hub/warbird-pro"
python3 scripts/optuna/runner.py \
    --profile warbird_nexus_ml_rsi \
    --study-name "nexus-delta-smoke" \
    --n-trials 1 \
    --symbol MES1! \
    --timeframe 5 \
    2>&1 | tail -20
```

Expected: `Trial 0 finished with value: X.XXX` (any non-zero score) with no stack traces

**Step 2: Fix any import or runtime errors before proceeding**

If the smoke test fails, read the full traceback and fix before Step 3.

**Step 3: Commit smoke-test confirmation note to plan doc**

Edit this plan doc's Progress table to update Task 6 status to DONE once smoke passes.

---

### Task 7: Launch Study A — 5m, 500 trials

**Files:**
- Run: `scripts/optuna/runner.py`

**Step 1: Launch Study A**

```bash
cd "/Volumes/Satechi Hub/warbird-pro"
python3 scripts/optuna/runner.py \
    --profile warbird_nexus_ml_rsi \
    --study-name "nexus-5m-delta-first-v1" \
    --n-trials 500 \
    --symbol MES1! \
    --timeframe 5 \
    2>&1 | tee /tmp/nexus_study_a.log &
echo "Study A launched — PID $!"
```

**Step 2: Monitor until completion**

```bash
tail -f /tmp/nexus_study_a.log
```

Expected: 500 trials, best score > 0.55 (meaningfully above the prior 0.402 baseline)

**Step 3: Extract champion params**

```bash
python3 -c "
import optuna
study = optuna.load_study(study_name='nexus-5m-delta-first-v1', storage='sqlite:///scripts/optuna/optuna.db')
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

### Task 8: Add Mode input and per-mode parameter presets

**Files:**
- Modify: `indicators/warbird-nexus-machine-learning-rsi-optuna-fast-test.pine`

**Step 1: Add Mode input at top of inputs section**

```pine
modeInput = input.string("5m", "Mode", options=["5m", "15m", "1H", "4H"],
    tooltip="Select chart timeframe. Each mode uses champion Optuna settings for that TF.")
```

**Step 2: Add mode-keyed parameter defaults**

```pine
// Champion defaults wired in after Study A/B/C/D complete.
// Temporary: use Study A champion values for all modes until studies run.
i_enginePeriod  = modeInput == "5m"  ? 21  : modeInput == "15m" ? 21 : modeInput == "1H" ? 21 : 21
i_signalPeriod  = modeInput == "5m"  ? 8   : modeInput == "15m" ? 8  : modeInput == "1H" ? 8  : 8
i_knnWindow     = modeInput == "5m"  ? 184 : modeInput == "15m" ? 184 : modeInput == "1H" ? 184 : 184
i_knnK          = modeInput == "5m"  ? 6   : modeInput == "15m" ? 6  : modeInput == "1H" ? 6  : 6
i_knnBull       = modeInput == "5m"  ? 58  : modeInput == "15m" ? 58 : modeInput == "1H" ? 58 : 58
i_knnBear       = modeInput == "5m"  ? 42  : modeInput == "15m" ? 42 : modeInput == "1H" ? 42 : 42
```

(Update these values in Task 16 after all four studies complete.)

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

### Task 11: Add footprint cumulative delta computation layer

**Files:**
- Modify: `indicators/warbird-nexus-machine-learning-rsi-optuna-fast-test.pine`

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

**Step 3: Add delta computation**

```pine
// ── Footprint cumulative delta ──────────────────────────────────────────────
body         = math.abs(close - open)
candleRange  = math.max(high - low, 1e-9)
bodyRatio    = math.min(body / candleRange, 1.0)
bodyDir      = close > open ? 1.0 : close < open ? -1.0 : 0.0
barDelta     = bodyDir * bodyRatio * math.max(volume, 0.0)
cumDelta     = ta.sma(barDelta, i_deltaLookback) * i_deltaLookback   // rolling sum via SMA×N
avgVol       = ta.sma(volume, i_deltaLookback)
normCumDelta = math.max(-1.0, math.min(1.0, cumDelta / math.max(avgVol * i_deltaLookback, 1.0)))
deltaSlope   = normCumDelta - normCumDelta[math.max(i_deltaLookback / 2, 1)]
deltaDir     = normCumDelta > i_deltaFlipThresh ? 1 : normCumDelta < -i_deltaFlipThresh ? -1 : 0
```

**Step 4: Run pine-lint + pine-facade**

```bash
./scripts/guards/pine-lint.sh indicators/warbird-nexus-machine-learning-rsi-optuna-fast-test.pine
```

Then `pine_smart_compile` via MCP.

**Step 5: Commit**

```bash
git add indicators/warbird-nexus-machine-learning-rsi-optuna-fast-test.pine
git commit -m "Pine: add footprint cumulative delta computation layer"
```

---

### Task 12: Add white diamond tier (gassing out) + wire teal/red/white to signal conditions

**Files:**
- Modify: `indicators/warbird-nexus-machine-learning-rsi-optuna-fast-test.pine`

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

## Phase 3: Mode Studies (15m / 1H / 4H)

### Task 14: Create 15m Optuna profile and run Study B

**Files:**
- Create: `scripts/optuna/warbird_nexus_ml_rsi_15m_profile.py` (copy + adjust ranges for 15m)

**Step 1: Copy 5m profile and adjust parameter ranges for 15m**

15m adjustments:
- `leg_threshold_pts`: range `15.0–50.0` (vs 6–20 for 5m)
- `response_bars`: range `4–15` (15m bars are 3× longer)
- `delta_lookback`: range `3–15`
- Target signal rate: `2–6/day` → `bars_per_day = 26` (6.5 hr × 4 bars/hr)

**Step 2: Launch Study B**

```bash
python3 scripts/optuna/runner.py \
    --profile warbird_nexus_ml_rsi_15m \
    --study-name "nexus-15m-delta-first-v1" \
    --n-trials 500 \
    --symbol MES1! \
    --timeframe 15
```

**Step 3: Extract champion params and wire into Pine Mode preset**

Update Task 8's `i_enginePeriod` / `i_knnWindow` etc. for `modeInput == "15m"` with Study B champion values.

---

### Task 15: Create 1H Optuna profile and run Study C

**Files:**
- Create: `scripts/optuna/warbird_nexus_ml_rsi_1h_profile.py`

**Step 1: Copy and adjust for 1H**

1H adjustments:
- `leg_threshold_pts`: range `30.0–100.0`
- `response_bars`: range `3–10`
- Target signal rate: `1–4/day` → `bars_per_day = 7`

**Step 2: Launch Study C**

```bash
python3 scripts/optuna/runner.py \
    --profile warbird_nexus_ml_rsi_1h \
    --study-name "nexus-1h-delta-first-v1" \
    --n-trials 500 \
    --symbol MES1! \
    --timeframe 60
```

**Step 3: Wire champion defaults into Pine for `modeInput == "1H"`**

---

### Task 16: Create 4H Optuna profile and run Study D + finalize Pine mode presets

**Files:**
- Create: `scripts/optuna/warbird_nexus_ml_rsi_4h_profile.py`
- Modify: `indicators/warbird-nexus-machine-learning-rsi-optuna-fast-test.pine` — wire all four champion sets

**Step 1: Copy and adjust for 4H**

4H adjustments:
- `leg_threshold_pts`: range `60.0–200.0`
- `response_bars`: range `2–6`
- Target signal rate: `0.5–2/day` → `bars_per_day = 2`

**Step 2: Launch Study D**

```bash
python3 scripts/optuna/runner.py \
    --profile warbird_nexus_ml_rsi_4h \
    --study-name "nexus-4h-delta-first-v1" \
    --n-trials 500 \
    --symbol MES1! \
    --timeframe 240
```

**Step 3: Wire all four champion sets into Pine Mode presets**

Update Task 8's `i_enginePeriod`, `i_knnWindow`, `i_knnK`, `i_knnBull`, `i_knnBear` for all four modes with their respective Study champion values.

**Step 4: Run full verification pipeline on final Pine file**

```bash
cd "/Volumes/Satechi Hub/warbird-pro"
./scripts/guards/pine-lint.sh indicators/warbird-nexus-machine-learning-rsi-optuna-fast-test.pine
./scripts/guards/check-contamination.sh
npm run build
```

**Step 5: Final commit**

```bash
git add indicators/warbird-nexus-machine-learning-rsi-optuna-fast-test.pine \
        scripts/optuna/warbird_nexus_ml_rsi_4h_profile.py
git commit -m "Pine+optuna: wire all four mode champion defaults — delta-first redesign complete"
```

---

## Progress Table

| Phase | Task | Status | Notes |
|-------|------|--------|-------|
| Phase 1 | Task 1: Delta helpers | PENDING | |
| Phase 1 | Task 2: Tunable params | PENDING | |
| Phase 1 | Task 3: Wire delta features | PENDING | |
| Phase 1 | Task 4: _label_setups() | PENDING | |
| Phase 1 | Task 5: Rewrite run_backtest() | PENDING | |
| Phase 1 | Task 6: Smoke test (1 trial) | PENDING | |
| Phase 1 | Task 7: Study A (500 trials) | PENDING | |
| Phase 2 | Task 8: Mode input + presets | PENDING | |
| Phase 2 | Task 9: Bear color #cc0000 | PENDING | |
| Phase 2 | Task 10: Watermark default=true | PENDING | |
| Phase 2 | Task 11: Footprint delta layer | PENDING | |
| Phase 2 | Task 12: White diamond + delta gates | PENDING | |
| Phase 2 | Task 13: Delta-fade bar coloring | PENDING | |
| Phase 3 | Task 14: 15m Study B | PENDING | After Study A |
| Phase 3 | Task 15: 1H Study C | PENDING | After Study A |
| Phase 3 | Task 16: 4H Study D + finalize | PENDING | After Studies B/C |

---

## Champion Parameters (filled in after each study)

### Study A — 5m

| Parameter | Champion Value | Notes |
|-----------|---------------|-------|
| (pending Study A completion) | | |

---

## Rollback Plan

- All changes are isolated to `warbird-nexus-machine-learning-rsi-optuna-fast-test.pine` (fast-test copy). `v7-warbird-institutional.pine` and `v7-warbird-strategy.pine` are NOT touched.
- To rollback Pine: `git checkout <prior-commit> -- indicators/warbird-nexus-machine-learning-rsi-optuna-fast-test.pine`
- Optuna studies are additive. The old `nexus-fast-5m-optuna` study remains in `optuna.db` and is unaffected.
