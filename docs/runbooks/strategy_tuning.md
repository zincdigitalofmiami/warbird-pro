# Strategy Tuning Runbook

**Date:** 2026-04-13
**Status:** Active — pre-AG settings sweep for MES1! 15m v7 strategy

## Purpose

Exhaustively sweep all tunable Pine v7 indicator/strategy knobs across 2020+ 15m MES1! history
and produce a defensible minimum-viable settings lock before AutoGluon starts optimizing via packets.

This is **not** AutoGluon training. AG does the real optimization via live packets after Phase 4.
This harness locks the settings floor AG trains from. AG must not train from a garbage baseline.

Three commands: `suggest`, `record`, `leaderboard`. The authoritative evaluation mode is `CSV_FULL` —
every other mode is deprecated.

**Preferred path: CDP automation** (`tv_auto_tune.py`) — applies inputs, waits for recalc, and reads
`reportData().trades()` directly. No CSV export needed. See [Automated Workflow](#automated-workflow-preferred) below.

## Files

- Search space: [scripts/ag/strategy_tuning_space.json](scripts/ag/strategy_tuning_space.json)
- CLI: [scripts/ag/tune_strategy_params.py](scripts/ag/tune_strategy_params.py)
- CDP automation: [scripts/ag/tv_auto_tune.py](scripts/ag/tv_auto_tune.py)
- Local tables: `warbird_strategy_tuning_batches`, `warbird_strategy_tuning_trials`
- Migrations: [local_warehouse/migrations/008_strategy_tuning_trials.sql](local_warehouse/migrations/008_strategy_tuning_trials.sql), [009](local_warehouse/migrations/009_strategy_tuning_evaluation_mode.sql)
- Suggested configs: `artifacts/tuning/suggestions/<timestamp>/trial_*.json`
- JSONL fallback: `artifacts/tuning/strategy_trials.jsonl` (use `--storage jsonl` to activate)

## Automated Workflow (preferred)

`tv_auto_tune.py` connects to TradingView Desktop via Chrome DevTools Protocol (CDP),
applies all inputs via `setInputValues()`, polls `isLoading()` until recalc completes,
reads `reportData().trades()` directly, and records the trial — no CSV export needed.

### Prerequisites

1. TradingView Desktop must be launched with CDP enabled:
   ```
   open -a "TradingView" --args --remote-debugging-port=9222
   ```
2. Active chart: `CME_MINI:MES1!` 15m with Warbird v7 Strategy loaded.
3. Strategy Tester → Properties → **From** set to `2020-01-01`, Bar Magnifier ON.
4. `pip install requests websockets` (one-time, if not already installed).

> **Entity ID note:** `STRATEGY_ENTITY_ID = "kGnTgb"` is set at the top of `tv_auto_tune.py`.
> If the chart is reloaded and the strategy gets a new entity ID, update this constant.
> Run `chart_get_state` via the MCP or check `chart.getAllStudies()` in the TV console.

### Automated run

```bash
# Generate new trial batch (same as before)
python scripts/ag/tune_strategy_params.py suggest --count 20

# Run the batch automatically via CDP -- no manual knob-turning or CSV export
python scripts/ag/tv_auto_tune.py run --batch-dir artifacts/tuning/suggestions/<timestamp>/

# Run a single trial
python scripts/ag/tv_auto_tune.py run --trial-file artifacts/tuning/suggestions/<timestamp>/trial_001.json

# Review leaderboard (same as before)
python scripts/ag/tune_strategy_params.py leaderboard --top 20
```

Trials are stored in the same `warbird_strategy_tuning_trials` table with `evaluation_mode = 'CSV_FULL'`
and `source_csv = 'tv_auto_tune:cdp'`. The leaderboard and scoring are identical to manual CSV runs.

### Adverse excursion sign convention

TV `reportData().trades()` returns `dd.v` as a positive magnitude (e.g., `117.25`).
The tuner's 30-tick survival boundary uses a signed convention (`survival_stop_usd = -37.50`).
`tv_auto_tune.py` negates `dd.v` before the survival check — this matches the CSV convention exactly.

---

## Manual Deep Backtesting Checklist

**Do this before every CSV export.** The tuner validates the CSV start date post-hoc and
refuses records that start after `2020-01-01`. TV's Deep Backtesting date range is UI-only —
there is no way to set it programmatically.

1. Open TradingView → Warbird v7 Strategy → Strategy Tester → Properties
2. Set **From** date to `2020-01-01` (or January 1, 2020 in the date picker)
3. Set **To** to today (or leave blank for live end)
4. Enable **Use Bar Magnifier** (matches `use_bar_magnifier=true` pinned in `strategy()`)
5. Verify **Commission** = $1.00 per contract (pinned in `strategy()`)
6. Verify **Slippage** = 1 tick (pinned in `strategy()`)
7. Click **OK** and wait for the full backtest to finish (progress bar at top)
8. Go to **List of Trades** tab → click the download icon → Export CSV
9. Save the file; note the path for the `--trades-csv` argument

> **Why 2020-01-01?** The v5 training data floor is `2020-01-01`. Most bars in
> 2020–2023 will have `ml_exh_footprint_available = false` (TV tick archive is bounded —
> this is a platform limit, not a subscription tier issue). The tuner stratifies metrics
> by this footprint boundary so a knob that looks good only on the recent footprint-rich
> tail does not dominate the leaderboard.

## Workflow

### 1. Generate candidate configs

```bash
python scripts/ag/tune_strategy_params.py suggest --count 20
```

This emits trial JSON files in `artifacts/tuning/suggestions/<timestamp>/`.
Each config covers all search knobs in `strategy_tuning_space.json`.
New suggestions are deduplicated against previously-recorded CSV_FULL trials.

### 2. Apply one config to TradingView manually

Open the trial JSON to see the parameter values:

```bash
cat artifacts/tuning/suggestions/<batch>/trial_001.json | python3 -m json.tool
```

In TradingView, open the Warbird v7 Strategy indicator settings and set each input
under `search_parameters` to the suggested value. Leave `locked_parameters` inputs
at the values shown in the JSON (they should match your current indicator settings).

Run the backtest and export the CSV per the checklist above.

### 3. Record the trial

```bash
python scripts/ag/tune_strategy_params.py record \
  --params-file artifacts/tuning/suggestions/<batch>/trial_001.json \
  --trades-csv /path/to/List_of_Trades.csv \
  --notes "full 2020+ history, bar magnifier on, commission $1.00, slippage 1 tick"
```

The `record` command:
- Reads first/last trade timestamps from the CSV to validate the window
- Rejects the record if the CSV starts after `2020-01-01` (override with `--required-csv-start`)
- Computes metrics for all bars AND a footprint cohort (trades from `2024-01-01` onward by default)
- Stores the trial in the local `warbird` warehouse under `evaluation_mode = 'CSV_FULL'`

To override the footprint cohort boundary (e.g., if TV has extended archive coverage):

```bash
python scripts/ag/tune_strategy_params.py record \
  --params-file ... \
  --trades-csv ... \
  --footprint-available-from 2023-06-01
```

**Re-recording is idempotent**: re-running with the same trial JSON and CSV produces
the same signature and upserts in place.

### 4. Review the leaderboard

```bash
python scripts/ag/tune_strategy_params.py leaderboard --top 20
```

Output columns:
- `score` — primary ranking metric (weighted blend of net_pnl, PF, DD, survival, long/short PF)
- `fp_pf` — footprint-cohort profit factor (diagnostic; bars from `DEFAULT_FOOTPRINT_AVAILABLE_FROM` onward)
- `params` — search parameter values for this trial

The `fp_pf` column is diagnostic only. A config that scores well on `score` (all bars)
but has a weak `fp_pf` is still a valid candidate — it was solid on the pre-footprint history
which is the majority of the training window.

### 5. Iterate

Generate the next batch. The harness mutates the top-ranked configs and adds exploratory
candidates so the search does not get stuck in a local optimum:

```bash
python scripts/ag/tune_strategy_params.py suggest --count 20
```

Lock the winning config in `strategy_tuning_space.json` under `locked_parameters` once
you have a stable leaderboard top. AG starts from this lock.

## What The Harness Scores

The CSV_FULL mode captures from the full TradingView trade-list export:

- net P&L, gross profit/loss
- profit factor
- max drawdown and max drawdown % (computed from cumulative P&L curve)
- win rate, average trade / win / loss
- long-side and short-side breakdowns (trades, net_pnl, PF, WR)
- yearly P&L
- 30-tick survival rate (MES `$37.50` adverse-excursion boundary)
- **footprint cohort** metrics (same fields, filtered to `footprint_available_from` date onward)

The objective score is a weighted blend. Weights live in the JSON search space:

```json
"weights": {
  "net_pnl": 1.0,
  "profit_factor": 1.25,
  "drawdown": 0.8,
  "survival": 0.35,
  "long_pf": 0.35,
  "short_pf": 0.85,
  "trade_penalty": 0.75
}
```

## Storage Model

Default storage: Postgres in the local `warbird` warehouse.

- `warbird_strategy_tuning_batches` — one row per suggestion batch
- `warbird_strategy_tuning_trials` — one row per trial
  - `evaluation_mode = 'CSV_FULL'` — authoritative, fully scored from trade CSV
  - `evaluation_mode = 'PENDING'` — generated suggestion, not yet run
  - `TV_DOM_SCREEN` rows from prior sessions are preserved but filtered out of all reads

To use JSONL fallback instead:

```bash
python scripts/ag/tune_strategy_params.py --storage jsonl suggest --count 10
python scripts/ag/tune_strategy_params.py --storage jsonl record --params-file ... --trades-csv ...
python scripts/ag/tune_strategy_params.py --storage jsonl leaderboard
```

## Boundaries

- This harness does not modify Pine code.
- This harness does not call AutoGluon.
- This harness cannot set TradingView's Deep Backtesting date range (TV UI-only).
- If Pine semantics are wrong, this tool ranks wrong semantics more efficiently.

**Fix the signal truth first. Then run this harness.**

Pine semantic fixes are tracked in the repair plan at
[docs/plans/2026-04-12-v7-interface-reconciliation.md](docs/plans/2026-04-12-v7-interface-reconciliation.md).
