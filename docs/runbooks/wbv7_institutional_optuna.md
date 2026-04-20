# WB v7 Institutional — Optuna Runbook

**Indicator:** `indicators/v7-warbird-institutional.pine`
**Profile:** `scripts/optuna/v7_warbird_institutional_profile.py`
**Study DB:** `data/optuna/v7_warbird_institutional/study.db`
**Symbol/TF:** MES1! 15m
**Data floor:** 2020-01-01

---

## 1. One-time: Export TV CSV

The profile requires a TV Pine Script CSV export from the live chart.
This export is the ground truth for fib geometry, trade state machine, and
footprint exhaustion signals.  You only need to re-export when you bump the
indicator version.

1. Open TradingView Desktop with `indicators/v7-warbird-institutional.pine`
   loaded on MES1! 15m, date range 2020-01-01 to present.
2. In the Pine Editor, click **Export → Export CSV** (or use
   Strategy Tester → Export if you have a strategy version).
3. Save the file to:
   ```
   data/optuna/v7_warbird_institutional/export.csv
   ```
4. Verify the file has columns including `time`, `open`, `high`, `low`,
   `close`, `volume`, `trade_state`, `ml_last_exit_outcome`, `fib_range`,
   `ml_fib_neg_0236`, and the momentum columns (`ml_vf_bull`, etc.).

---

## 2. Verify the profile loads

```bash
cd "/Volumes/Satechi Hub/warbird-pro"

python3 -c "
from scripts.optuna.v7_warbird_institutional_profile import (
    BOOL_PARAMS, NUMERIC_RANGES, INT_PARAMS, CATEGORICAL_PARAMS,
    INPUT_DEFAULTS, load_data, run_backtest,
)
print('BOOL:',        BOOL_PARAMS)
print('NUMERIC:',     len(NUMERIC_RANGES), 'params')
print('INT subset:',  INT_PARAMS)
print('CATEGORICAL:', list(CATEGORICAL_PARAMS.keys()))
print('DEFAULTS:',    list(INPUT_DEFAULTS.keys()))
print('OK')
"
```

---

## 3. Run the study

### First run (200 trials)

```bash
cd "/Volumes/Satechi Hub/warbird-pro"

python3 scripts/optuna/runner.py \
  --indicator-key v7_warbird_institutional \
  --profile-module scripts.optuna.v7_warbird_institutional_profile \
  --study-name v7_warbird_institutional_wr_pf \
  --n-trials 200 \
  --start 2020-01-01
```

Typical runtime: 2–8 min per trial (stop re-simulation is O(n_trades × max_bars)).
200 trials ≈ 7–27 hours.  Run overnight or via `nohup`.

### Resume an existing study

```bash
python3 scripts/optuna/runner.py \
  --indicator-key v7_warbird_institutional \
  --profile-module scripts.optuna.v7_warbird_institutional_profile \
  --study-name v7_warbird_institutional_wr_pf \
  --n-trials 100 \
  --start 2020-01-01 \
  --resume
```

### View top-5 results

After the run, `data/optuna/v7_warbird_institutional/top5.json` is written
automatically.  To view:

```bash
python3 -c "
import json
from pathlib import Path
top5 = json.loads(Path('data/optuna/v7_warbird_institutional/top5.json').read_text())
for t in top5:
    print(f'#{t[\"rank\"]}  score={t[\"objective_score\"]:.4f}  '
          f'WR={t[\"win_rate\"]:.2%}  PF={t[\"pf\"]:.4f}  trades={t[\"trades\"]}')
    print(f'     {t[\"params\"]}')
"
```

### Dashboard

```bash
optuna-dashboard \
  sqlite:////Volumes/Satechi\ Hub/warbird-pro/data/optuna/v7_warbird_institutional/study.db \
  --port 8081
```

Open: http://127.0.0.1:8081

---

## 4. Objective — what is being maximized

The objective is a composite score returned as `result["win_rate"]`:

```
composite = 0.40 × PF_score + 0.35 × WR_score + 0.25 × consistency_score

PF_score          = min(profit_factor / 2.5,  1.0)
WR_score          = min(tp1_win_rate  / 0.65, 1.0)
consistency_score = (years 2020–2025 with PF ≥ 1.0) / 6
```

**Rejection rules** (returns score = -999, trial pruned):
- Fewer than 80 tradeable (non-EXPIRED) trades
- More than 70% EXPIRED outcomes — fib geometry is wrong
- Any year with 1–4 tradeable trades — config breaks a year
- ATR stop family + `continuationHoldStopAtrMult > 2.5` — undefined stop geometry

**Note:** `result["win_rate"]` in the Optuna dashboard is the *composite score*
(0–1 range), not the raw TP1+ win rate.  Raw win rate is in `result["raw_win_rate"]`.

---

## 5. What is swept vs what is not

### Actively swept in Python (no Pine re-run needed)

| Parameter | What it controls |
|---|---|
| `stopFamilyId` | Stop placement family — full outcome re-simulation |
| `continuationHoldStopAtrMult` | Stop width during continuation hold window |
| `continuationHoldBars` | Duration of hold window |
| `vfLenInput`, `vfFlowWeight`, `vfVolWeight` | Volume Flow oscillator — recomputed |
| `nfeLenInput` | NFE RSI lookback — recomputed |
| `rsiKnnWindow` | RSI KNN smoother window — recomputed |
| `gateShortsInBullTrend` | Short entry gate toggle |
| `shortTrendGateAdx` | ADX floor for short gate activation |
| `momentumMinFilter` | `ml_confluence` threshold at entry — filters by momentum quality |

### TV-only params (require Pine re-run per trial via CDP)

These parameters change Pine's state machine output and cannot be correctly
swept from a single CSV export.  They require the full CDP automation path
(`scripts/ag/tv_auto_tune.py`).

| Parameter | Why TV-only |
|---|---|
| `retestBars` | Changes which bars qualify as accepted entries |
| `fibConfluenceTolPct` | Changes the `confluence_quality` continuous score |
| `footprintTicksPerRow` | Changes footprint row resolution — affects POC/imbalance |
| `footprintVaPercent` | Changes VA boundary — affects POC position |
| `footprintImbalancePercent` | Changes imbalance detection threshold |
| `zeroPrintVolRatio` | Changes zero-print detection floor |
| `stackedImbalanceRows` | Changes how many extreme rows are scanned |
| `exhaustionZLen` | Changes the Z-score lookback for exhaustion probe |
| `exhaustionZThreshold` | Changes `mlExhZExtreme` — affects diamond gate |
| `exhaustionLevelAtrTol` | Changes ATR tolerance for fib extension tagging |

### Frozen params (CLAUDE.md 15m fib-owner freeze 2026-04-14)

These must NOT be swept.  They are the locked 15m fib geometry.

| Parameter | Locked value |
|---|---|
| `autoTuneZZ` | `false` |
| `fibDeviationManual` | `4.0` |
| `fibDepthManual` | `20` |
| `fibThresholdFloorPct` | `0.50` |
| `minFibRangeAtr` | `0.5` |

### Pending Pine additions (require Kirk's explicit approval per session)

These inputs do not yet exist in the indicator but would unlock additional
sweep dimensions when added:

- **Entry labels on chart** — Green/red `label.new()` at `entryLongTrigger` /
  `entryShortTrigger` bars showing direction and entry price level.  Zero plot
  budget cost (uses `max_labels_count=200`).

- **Fib extension target labels** — Price labels on each target line (T1–T5),
  SL, and ENTRY refreshed on every bar using `var label` pattern.  Zero plot
  budget cost.

- **Continuous ATR stop multiplier** (`atrStopMult` float input, default 1.0,
  range 0.5–2.5, step 0.25) — Collapses `ATR_1_0`, `ATR_1_5`, and
  `ATR_STRUCTURE_1_25` into one geometry with a tuneable distance.  Once
  added, include in `NUMERIC_RANGES` and add a rejection rule:
  `stopFamilyId in ATR_families and atrStopMult > continuationHoldStopAtrMult`.

---

## 6. Reading the results

### Good trial signs

- `consistency_score` near 1.0 — profitable across all 6 years
- `trades` ≥ 100 — enough history to be meaningful
- `raw_win_rate` > 0.50 — TP1 hit more often than stopped
- `pf` > 1.5 — material edge
- `stopFamilyId` same across top-3 trials — not just lucky family selection

### Warning signs

- `trades` < 100 despite data from 2020 — `momentumMinFilter` may be too high
- `years_above_breakeven` < 4 — seasonal or regime dependency
- `stopFamilyId` = `FIB_NEG_0236` only in top trials — check if `fib_range` is
  being set correctly in the CSV export (small fib range → tight FIB stop)
- Best trial's params at boundary of search space → expand the range

---

## 7. Committing winning params back to Pine

**Never edit the indicator without Kirk's explicit per-session approval.**

When top-5 trials converge on parameter values and pass out-of-sample
sanity checks (run `--start 2025-01-01` as OOS verification):

1. Note the winning `stopFamilyId` and momentum window params.
2. Open session with Kirk, show the top-5 table and yearly PF heatmap.
3. If Kirk approves, update `INPUT_DEFAULTS` in `v7_warbird_institutional_profile.py`
   to match the winner.
4. Apply the same params as new defaults in `indicators/v7-warbird-institutional.pine`
   (requires pine verification pipeline: `pine-lint` + `check-contamination` + `npm run build`).
5. Document the freeze in CLAUDE.md and memory.

---

## 8. Related files

| Path | Purpose |
|---|---|
| `scripts/optuna/v7_warbird_institutional_profile.py` | Optuna profile (this study) |
| `scripts/optuna/runner.py` | Shared Optuna runner |
| `scripts/optuna/indicator_registry.json` | Registry entry for v7_warbird_institutional |
| `data/optuna/v7_warbird_institutional/study.db` | SQLite study DB |
| `data/optuna/v7_warbird_institutional/export.csv` | TV CSV export (manual, one-time) |
| `data/optuna/v7_warbird_institutional/top5.json` | Auto-written after each run |
| `indicators/v7-warbird-institutional.pine` | Source indicator (DO NOT EDIT without approval) |
| `docs/contracts/ag_local_training_schema.md` | AG feature contract |
