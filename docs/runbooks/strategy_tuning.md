# Strategy Tuning Runbook

**Date:** 2026-04-13
**Status:** Active — pre-AG settings sweep for MES1! 15m v7 strategy

## Purpose

Exhaustively sweep all tunable Pine v7 indicator/strategy knobs across 2020+ 15m MES1! history
and produce a defensible minimum-viable settings lock before AutoGluon starts optimizing via packets.

This is **not** AutoGluon training. AG does the real optimization via live packets after Phase 4.
This harness locks the settings floor AG trains from. AG must not train from a garbage baseline.
This harness also does **not** choose the lower-timeframe micro trigger (`5m`)
versus parent-bar `15m` execution. It tunes the parent 15m strategy surface
only. A separate micro-execution profile is required
for the 2026-04-14 parent/micro execution delta.

Three commands: `suggest`, `record`, `leaderboard`.
Authoritative scored evaluation modes are:
- `CSV_FULL` (manual CSV record path)
- `TV_MCP_STRICT` (CDP automation path)
Deprecated/legacy modes are non-authoritative.

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

> **Entity ID note:** `tv_auto_tune.py` discovers the strategy entity ID at runtime
> from `chartModel().dataSources()`. No hardcoded `STRATEGY_ENTITY_ID` is required.

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

Trials are stored in the same `warbird_strategy_tuning_trials` table with
`evaluation_mode = 'TV_MCP_STRICT'` and `source_csv = 'tv_auto_tune:cdp'`.
The leaderboard includes both authoritative scored modes (`CSV_FULL`, `TV_MCP_STRICT`).

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
New suggestions are deduplicated against previously-recorded scored trials
(`CSV_FULL` + `TV_MCP_STRICT`).

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
- `score` — primary ranking metric (profit-first objective with AG richness constraints)
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
- **rolling time windows** (4 chronological windows with PF / expectancy / drawdown-efficiency)

The objective score is a weighted blend. Weights and gates live in
`scripts/ag/strategy_tuning_space.json`.

Current scoring model:
- Hard sample gate (reject): `total_trades < min` OR one-sided samples (no long/no short)
- Profit-first ranking components:
  - `profit_factor` (primary)
  - `expectancy_per_trade` (secondary)
- Stability and sample-quality components:
  - `trade_density` (target range, not monotonic "more trades is always better")
  - `directional_balance`
  - `regime_coverage`
  - `outcome_diversity`
  - `drawdown_efficiency`
  - `rolling_stability`
  - `footprint_stability`
  - `yearly_consistency`
- Realism and instability gates:
  - penalties apply if PF/expectancy/side-PF floors are violated
  - penalties apply if the result is concentrated in one time slice or degrades sharply in the footprint-rich tail

Example objective block:

```json
"trade_count_bounds": { "min": 220, "target": 375, "max": 900 },
"profit_factor_range": { "floor": 0.9, "target": 1.6, "realism_cap": 2.4 },
"expectancy_per_trade": { "floor": 0.0, "target": 18.0, "negative_penalty": 0.35 },
"return_over_drawdown": { "floor": 0.25, "target": 1.5 },
"footprint_cohort": { "min_trades": 60, "min_score": 0.45 },
"rolling_window_stability": {
  "window_count": 4,
  "min_trades_per_window": 40,
  "target_positive_windows": 0.75,
  "max_score_stddev": 0.18,
  "min_score": 0.45
},
"yearly_consistency": {
  "target_positive_ratio": 0.67,
  "max_dominance": 0.55,
  "min_score": 0.45
},
"side_profit_factor_floor": { "long": 0.95, "short": 0.95 },
"weights": {
  "profit_factor": 0.23,
  "expectancy": 0.12,
  "trade_density": 0.12,
  "directional_balance": 0.08,
  "regime_coverage": 0.06,
  "outcome_diversity": 0.04,
  "drawdown_efficiency": 0.14,
  "rolling_stability": 0.12,
  "footprint_stability": 0.05,
  "yearly_consistency": 0.04,
  "realism_gate_penalty": 0.40,
  "instability_penalty": 0.55
}
```

## 2026-04-13 Optimization Update

This runbook now reflects the production tuning surface in `mes15m_agfit_v3`.
The update is deliberately narrower than the earlier broad random sweep because the
15m backtest evidence and PowerDrill synthesis both showed that the old tuner was
spending too much search budget on unstable or low-information regions.

### Audit findings that changed the tuner

- Search-space width was too large for a CDP-backed full-history tuner. The previous space exceeded `208B` discrete combinations and encouraged random combinations with no coupling awareness.
- The old score rewarded trade count monotonically up to the cap. That pushed the tuner toward overtrading even though the 15m baseline pathology is already "too many mediocre trades."
- The old score ignored drawdown efficiency, rolling-window stability, and footprint-tail degradation even though those are exactly where this strategy class can overfit.
- Locked visual/debug inputs polluted the trial signature. They can change chart rendering while leaving the trade list unchanged.

### Final recommended search ranges

These are the default production ranges in `scripts/ag/strategy_tuning_space.json`:

| Component | Parameter | Range / Values | Why |
| --- | --- | --- | --- |
| Footprint core | `Footprint Ticks Per Row` | `4`, `6` | Avoid the noisiest 2-tick historical footprint surface |
| Footprint core | `Footprint VA %` | `65-75` step `5` | Keeps POC stable without over-diluting extreme-row tests |
| Footprint core | `Footprint Imbalance %` | `250-350` step `25` | Preserves meaningful imbalance without starving continuation/reversal evidence |
| Footprint core | `Extreme Rows To Inspect` | `2`, `3`, `4` | Keeps the row scan local to the extreme instead of drifting into redundant rows |
| Exhaustion stats | `Exhaustion Z Length` | `14`, `20`, `30` | Covers fast / medium / regime-normalized windows without wasting search on ultra-long tails |
| Exhaustion stats | `Exhaustion Z Threshold` | `2.2-2.8` step `0.1` | Centers around the repo's `2.5` reference zone |
| Exhaustion geometry | `Extension ATR Tolerance` | `0.08-0.12` step `0.01` | Keeps extension checks structural instead of fuzzy |
| Exhaustion auction | `Zero-Print Volume Ratio` | `0.08-0.15` step `0.01` | Matches the finished-auction intent without making the test toothless |
| Short asymmetry | `Gate Shorts In Bull Trend` | `true/false` | Still searchable, but scored under stricter side-PF and stability penalties |
| Short asymmetry | `Short Gate ADX Floor` | `18-24` step `1` | Focuses on the zone where trend-context gating matters |
| Hold logic | `Tier 1 Hold Bars` | `2`, `3`, `4`, `5` | Avoids extended stop-widening that lets losers sit too long |
| Hold logic | `Tier 1 Hold Stop ATR` | `1.5-2.25` step `0.25` | Preserves hold protection without recreating the baseline stop problem |
| Stop family | `Fallback Stop Family` | `ATR_1_0`, `ATR_1_5`, `ATR_STRUCTURE_1_25`, `FIB_NEG_0236`, `FIB_0236_ATR_COMPRESS_0_50` | Keeps one fib control plus the ATR-aware families most relevant to the 15m pathology |

### Coupling rules now enforced by the suggester

- Reject over-wide hold combinations (`Tier 1 Hold Bars >= 5` with `Tier 1 Hold Stop ATR > 2.0`).
- Reject exhaustion gates that are too permissive (`Z Length <= 14`, `Z Threshold <= 2.2`, `ATR Tolerance >= 0.12`).
- Reject exhaustion gates that are too sparse (`Z Length >= 30`, `Z Threshold >= 2.8`, `ATR Tolerance <= 0.08`).
- Reject coarse-row + loose-auction combinations (`Ticks Per Row >= 6` with `Zero-Print Volume Ratio > 0.14`).
- Reject shallow row scans paired with very high imbalance thresholds (`Imbalance >= 325` and `Rows To Inspect < 3`).

### Trial identity rules

Trial signatures now exclude these locked inputs because they do not change the trade list:

- `Anchor Span = Active Fib Window`
- `Confluence Tolerance (%)`
- `Extend Levels Right`
- `Show Footprint Audit Table`
- `Target Line Lookback Bars`

This prevents the tuner from treating chart-rendering tweaks as distinct strategy results.

## Repeatable Optimization Protocol

1. Run `suggest` from the current `mes15m_agfit_v3` space.
2. Execute a coarse batch with CDP or CSV on the full `2020+` window.
3. Filter by score, then inspect the top rows for side PF, drawdown efficiency, rolling-window stability, and footprint-cohort retention.
4. Freeze the best footprint / exhaustion cluster.
5. Run a second sweep focused on stop family plus hold settings.
6. Only lock a winner after it survives the same friction settings, the same date window, and at least one walk-forward style review.

## Known Limitations

- This harness still ranks one parameter set at a time against a single full-history TV backtest; it is not a full Bayesian optimizer.
- TradingView Deep Backtesting date selection is still manual.
- Footprint history quality is not stationary across the full sample. Recent bars are richer than the early `2020-2023` segment.
- Walk-forward stability is approximated from rolling chronological trade windows. It is a penalty surface, not a replacement for a true purged re-optimization loop.
- This runbook does not solve `FORMING -> READY -> TRADE_ON -> INVALIDATED`
  micro execution policy or select which `5m` / `15m` trigger family should fire under an active 15m parent setup.

## Re-optimization Triggers

Re-run the tuner when any of these happen:

- rolling 60-trade PF drops below `0.95`
- rolling max drawdown exceeds the locked config's backtest drawdown by `25%+`
- footprint-cohort PF diverges materially from all-bars PF for two consecutive monthly reviews
- a structural strategy change lands in `v7-warbird-strategy.pine`
- quarterly calendar roll / macro regime shifts materially alter the MES 15m trade distribution

## Storage Model

Default storage: Postgres in the local `warbird` warehouse.

- `warbird_strategy_tuning_batches` — one row per suggestion batch
- `warbird_strategy_tuning_trials` — one row per trial
  - `evaluation_mode = 'CSV_FULL'` — authoritative manual CSV scoring
  - `evaluation_mode = 'TV_MCP_STRICT'` — authoritative CDP scoring
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
