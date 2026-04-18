# SATS Optuna Tuning Runbook

## Overview

Optuna TPE replaces the 6-stage grid sweep (`sats_sweep.py`) for ongoing
SATS v1.9.0 parameter optimization. The backtest engine is `backtesting.py`
wrapping the same indicator math as the original `simulate_sats()`.

**Seeded from:** grid-sweep champion (PF=1.1748, 1307 trades, atrLen=15,
erLen=16, adaptStrength=1.0, useTqi=OFF, multSmooth=OFF, slAtrMult=2.5).

---

## Quick Start

```bash
cd "/Volumes/Satechi Hub/warbird-pro"
source .venv/bin/activate

# Parity check (run once before first Optuna study)
python scripts/sats/sats_backtest.py

# Smoke test (3 trials)
python scripts/sats/sats_optuna.py --n-trials 3 --study-name smoke

# Full run (resume-safe)
python scripts/sats/sats_optuna.py --n-trials 300 --study-name sats_v1 --resume
```

---

## Parity Re-Validation Protocol

Before trusting any Optuna winner, confirm the backtesting.py port matches
the validated sim within tolerance:

```bash
python scripts/sats/sats_backtest.py --config data/sats_ps_sweep/champion.json
```

Expected output:
- **Trade count**: must match exactly (currently 1307 on 2025-01-01 start)
- **PF diff vs simulate_sats**: ≤ 5% (currently ~3.3% — known gap from
  reversal/timeout exits at next-bar-open in bt vs current-bar-close in sim)

If the trade count diverges, the signal logic is broken — stop and fix before
running Optuna.

---

## IS / OOS Discipline

| Window | Date Range | Purpose |
|--------|-----------|---------|
| IS (optimization) | 2020-01-01 → 2023-12-31 | Optuna objective |
| OOS (validation) | 2024-01-01 → present | TV Deep Backtest only, after config lock |

**Never run Optuna on OOS data.** The `--start` default is `2020-01-01`
(full IS window). Use `--start 2025-01-01` only for quick spot-checks that
match the grid-sweep window.

---

## Dashboard Access

### Machine Service (persistent)

Install launchd agent (one-time):
```bash
cp "/Volumes/Satechi Hub/warbird-pro/scripts/sats/optuna-dashboard.plist" \
   ~/Library/LaunchAgents/com.warbird.optuna-dashboard.plist
launchctl load ~/Library/LaunchAgents/com.warbird.optuna-dashboard.plist
```

Dashboard runs at **http://localhost:8080** and restarts automatically on reboot.

Logs: `/tmp/optuna-dashboard.log`, `/tmp/optuna-dashboard.err`

Stop/start:
```bash
launchctl unload ~/Library/LaunchAgents/com.warbird.optuna-dashboard.plist
launchctl load   ~/Library/LaunchAgents/com.warbird.optuna-dashboard.plist
```

### VS Code Extension

1. Open the Optuna Dashboard panel in the VS Code sidebar.
2. Point it at `data/sats_ps_optuna/study.db` (absolute path).
3. Both the VS Code extension and the machine service read the same SQLite
   file — no conflict.

---

## Study Lifecycle

```
create study → seed champion → run trials → inspect → export top-5 → TV validate → lock
```

### 1. Create and run
```bash
python scripts/sats/sats_optuna.py \
  --n-trials 300 \
  --study-name sats_v1 \
  --start 2020-01-01
```

### 2. Resume (add more trials)
```bash
python scripts/sats/sats_optuna.py \
  --n-trials 200 \
  --study-name sats_v1 \
  --resume
```

### 3. Inspect in Python
```python
import optuna
study = optuna.load_study(
    study_name='sats_v1',
    storage='sqlite:///data/sats_ps_optuna/study.db'
)
df = study.trials_dataframe()
print(df.nlargest(10, 'value')[['number','value','params_atrLenInput','params_baseMultInput']])
```

### 4. Export top-5 for TV validation
Top-5 configs are written automatically to `data/sats_ps_optuna/top5.json`
at the end of each run. To re-export manually:
```python
from scripts.sats.sats_optuna import export_top_n
export_top_n(study, n=5)
```

---

## TV Validation Protocol

For each top-N config:
1. Open `v8-warbird-prescreen.pine` → Strategy Tester → Properties.
2. Set `presetInput = Custom`.
3. Apply config values from `top5.json` (`params` dict → TV input names).
4. Enable **Deep Backtesting**, date range 2024-01-01 → present (OOS window).
5. Record TV PF. Expect TV PF ≈ Optuna sim PF × 0.92–0.97 (bar magnifier gap).
6. Lock the config with the highest TV PF.

---

## Calibration Notes

- **Sim vs TV gap**: the sim (and backtesting.py) runs 3–8% higher PF than TV
  due to bar magnifier (sim uses 15m OHLC for SL, TV resolves to 1m intrabar).
- **backtesting.py vs sim gap**: ~3.3% on champion — reversal/timeout exits
  price at next-bar-open in bt vs current-bar-close in sim. Trade counts match exactly.
- **Commission**: $1.00/side = $2.00 round-trip, computed post-hoc from raw trade P&L × $5/pt.
- **SL floor**: `slAtrMultInput ≥ 0.618` enforced in `suggest_params()`.

---

## Files

| Path | Purpose |
|------|---------|
| `scripts/sats/sats_backtest.py` | SATSStrategy + run_sats_bt() + parity CLI |
| `scripts/sats/sats_optuna.py` | Optuna study wrapper + CLI |
| `scripts/sats/optuna-dashboard.plist` | launchd agent template |
| `data/sats_ps_optuna/study.db` | SQLite study DB (not tracked in git) |
| `data/sats_ps_optuna/top5.json` | Top-N export (not tracked in git) |
| `data/sats_ps_sweep/champion.json` | Grid-sweep champion seed |
