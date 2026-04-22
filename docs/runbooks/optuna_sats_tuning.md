# SATS Optuna Tuning Runbook

## Overview

Optuna TPE replaces the 6-stage grid sweep (`sats_sweep.py`) for ongoing
SATS v1.9.0 parameter optimization. The backtest engine is `backtesting.py`
wrapping the same indicator math as the original `simulate_sats()`.

**Ranking policy:** runner-configurable.  
`scripts/optuna/runner.py` defaults to `dsr_composite` and still exports
leaderboards `win_rate` first, `PF` second.

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
python scripts/optuna/runner.py --n-trials 3 --study-name smoke

# Full run (resume-safe)
python scripts/optuna/runner.py --n-trials 300 --study-name sats_2025_wr_pf --resume
```

---

## Parity Re-Validation Protocol

Before trusting any Optuna winner, confirm the backtesting.py port matches
the validated sim within tolerance:

```bash
python scripts/sats/sats_backtest.py --config scripts/optuna/workspaces/sats_ps/champion.json
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
| IS (optimization) | 2025-01-01 → lock date | Optuna objective |
| OOS (validation) | lock date onward | TV Deep Backtest only, after config lock |

**Never run Optuna on OOS data.** The `--start` default is `2025-01-01`.

---

## Dashboard Access

### Warbird Card Hub (multi-indicator)

```bash
cd "/Volumes/Satechi Hub/warbird-pro"
source .venv/bin/activate
python scripts/optuna/warbird_optuna_hub.py --print-layout
```

Hub UI:
- `http://127.0.0.1:8090`
- JSON snapshot API: `http://127.0.0.1:8090/api/snapshot`

The hub renders one card per indicator key from:
- `scripts/optuna/indicator_registry.json`

Each card points to:
- the indicator workspace (`scripts/optuna/workspaces/<indicator_key>/`)
- that workspace's `experiments/` folder for extra named studies
- the current `study.db` status
- a per-indicator `optuna-dashboard` child UI (when `study.db` exists)

Folder scaffolding only (no web server):
```bash
python scripts/optuna/warbird_optuna_hub.py --init-folders-only
```

Optional launchd service:
```bash
cp "/Volumes/Satechi Hub/warbird-pro/scripts/optuna/warbird-optuna-hub.plist" \
   ~/Library/LaunchAgents/com.warbird.optuna-hub.plist
launchctl load ~/Library/LaunchAgents/com.warbird.optuna-hub.plist
```

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

The Optuna VS Code extension is **file-driven**. It does not expose a workspace
setting for a default study path.

Workspace wiring now lives in `.vscode/`:

- `.vscode/OPTUNA_WORKSPACE.md` gives one-click VS Code Simple Browser links for:
  - `http://127.0.0.1:8090/`
  - `http://127.0.0.1:8080/dashboard/`
- `.vscode/extensions.json` recommends the required Optuna/Python extensions
- `.vscode/settings.json` pins the repo interpreter to `.venv/bin/python`
- `.vscode/tasks.json` adds:
  - `Optuna: Doctor`
  - `Optuna: Print Study Layout`
- `.vscode/launch.json` adds **optional sidecar** launch configs on isolated
  ports (`8180`, `8181`, `8182`, `8190`, `8200+`) for ad-hoc debugging without
  touching the already-running live services on `8080`, `8090`, and `8100+`

Primary live services:

- Hub: `http://127.0.0.1:8090/`
- Shared dashboard: `http://127.0.0.1:8080/dashboard/`

Open inside VS Code:

1. Open `.vscode/OPTUNA_WORKSPACE.md` and use the Simple Browser links for the
   live hub/shared dashboard when you want the web UI embedded in VS Code.
2. In Explorer, right-click any `study.db` file.
3. Select **Open in Optuna Dashboard**.
4. Common study DBs:
   - `scripts/optuna/workspaces/sats_ps/study.db`
   - `scripts/optuna/workspaces/warbird_pro_sniper/study.db`
   - `scripts/optuna/workspaces/v7_warbird_institutional/study.db`
5. For additional studies, open any other `scripts/optuna/workspaces/**/study.db` file the same way.

Workspace helpers:

- Run `Terminal -> Run Task -> Optuna: Doctor` to verify extension/binaries/DBs/services
- Run the optional sidecar launch configs only when you want an isolated
  `optuna-dashboard` process without touching the persistent machine services

---

## Study Lifecycle

```
create study → seed champion → run trials → inspect → export top-5 → TV validate → lock
```

### 1. Create and run
```bash
python scripts/optuna/runner.py \
  --n-trials 300 \
  --study-name sats_2025_wr_pf \
  --start 2025-01-01
```

### 2. Resume (add more trials)
```bash
python scripts/optuna/runner.py \
  --n-trials 200 \
  --study-name sats_2025_wr_pf \
  --resume
```

### 3. Non-SATS strategy profile (same dashboard contract)
```bash
python scripts/optuna/runner.py \
  --indicator-key wb7 \
  --profile-module scripts.optuna.my_wb7_profile \
  --study-name wb7_wr_pf \
  --n-trials 300
```

Reference adapter template:
- `scripts/optuna/profile_template.py`

### 4. Inspect in Python
```python
import optuna
study = optuna.load_study(
    study_name='sats_2025_wr_pf',
    storage='sqlite:///scripts/optuna/workspaces/sats_ps/study.db'
)
df = study.trials_dataframe()
print(df.nlargest(10, 'value')[['number','value','user_attrs_win_rate','user_attrs_pf']])
```

### 5. Export top-5 for TV validation
Top-5 configs are written automatically to `scripts/optuna/workspaces/sats_ps/top5.json`
at the end of each run. To re-export manually:
```python
from scripts.optuna.runner import export_top_n
from pathlib import Path
export_top_n(study, optuna_dir=Path("scripts/optuna/workspaces/sats_ps"), n=5)
```

---

## TV Validation Protocol

For each top-N config:
1. Open `v8-warbird-prescreen.pine` → Strategy Tester → Properties.
2. Set `presetInput = Custom`.
3. Apply config values from `top5.json` (`params` dict → TV input names).
4. Enable **Deep Backtesting**, date range 2024-01-01 → present (OOS window).
5. Rank candidates by **TV win rate first**, then **TV PF**.
6. Lock the config that wins by this order.

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
| `scripts/optuna/runner.py` | Shared Optuna study wrapper + CLI |
| `scripts/optuna/README.md` | Canonical Optuna workspace contract |
| `scripts/optuna/profile_template.py` | Adapter contract for non-SATS strategies |
| `scripts/sats/optuna-dashboard.plist` | launchd agent template |
| `scripts/optuna/workspaces/sats_ps/study.db` | Canonical SATS SQLite study DB |
| `scripts/optuna/workspaces/sats_ps/top5.json` | SATS top-N export |
| `scripts/optuna/workspaces/<indicator_key>/study.db` | Canonical per-indicator study DB layout |
| `scripts/optuna/workspaces/sats_ps/champion.json` | SATS champion seed |
