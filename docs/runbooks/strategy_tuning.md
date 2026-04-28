# Strategy Tuning Runbook

**Date:** 2026-04-27
**Status:** Active — 5m primary tuning lane for Warbird v7 strategy surfaces

## Purpose

Tune the 5m Warbird strategy surface using TradingView/Pine-only evidence and
produce a defensible Pine settings recommendation.

This runbook is part of the active indicator-only modeling loop. AutoGluon,
Optuna, and SHAP are offline analyzers over Pine/TradingView outputs only. No
FRED, macro, cross-asset, Databento-ingestion, Supabase, or local
`ag_training` joins are admitted.

The current promotion floor for the primary 5m campaign is **1,000
authoritative trials** before final champion promotion, unless explicitly
overridden.

Three commands: `suggest`, `record`, `leaderboard`.
Authoritative scored evaluation modes are:
- `CSV_FULL` (manual CSV record path)
- `TV_MCP_STRICT` (CDP automation path)
Deprecated/legacy modes are non-authoritative.

## Active Search Surface

Canonical space file:
- `scripts/ag/strategy_tuning_space.json`
- active profile: `mes5m_agfit_v1`
- runtime context: `CME_MINI:MES1!` on `5m`

Tunable non-frozen knobs in this profile:
- `Execution Anchor`
- `Acceptance Retest Window (bars)`
- `ATR Stop Multiplier`
- `Max Setup Stop ATR`
- `Gate Shorts In Bull Trend`
- `Short Gate ADX Floor`
- `Footprint Ticks Per Row`
- `Footprint VA %`
- `Footprint Imbalance %`
- `Imbalance Rows`
- `Exhaustion Z Length`
- `Exhaustion Z Threshold`
- `Extension ATR Tolerance`
- `Zero-Print Volume Ratio`

Locked controls in this profile intentionally keep fib architecture/structure
internals unchanged during tuning (for example ZigZag/fib-threshold internals,
confluence span, visual/debug knobs, and other non-trade-list controls).

### Scope Note: Missing Knobs

The 5m turnover brief references MA-family selectors, MA-length controls,
liquidity-sweep lookback, and exhaustion cooldown/lookback knobs. Those are not
currently present on the **shared CDP dual-surface intersection** required by
`tv_auto_tune.py` preflight (strategy + institutional indicator schemas).

Do not hand-wave these as tuned. If these knobs are required for the active
campaign, add them to the shared Pine surfaces first, then expand this search
space.

## Files

- Search space: [scripts/ag/strategy_tuning_space.json](scripts/ag/strategy_tuning_space.json)
- CLI: [scripts/ag/tune_strategy_params.py](scripts/ag/tune_strategy_params.py)
- CDP automation: [scripts/ag/tv_auto_tune.py](scripts/ag/tv_auto_tune.py)
- Local tables: `warbird_strategy_tuning_batches`, `warbird_strategy_tuning_trials`
- Migrations: [local_warehouse/migrations/008_strategy_tuning_trials.sql](local_warehouse/migrations/008_strategy_tuning_trials.sql), [009](local_warehouse/migrations/009_strategy_tuning_evaluation_mode.sql)
- Suggested configs: `artifacts/tuning/suggestions/<timestamp>/trial_*.json`
- JSONL fallback: `artifacts/tuning/strategy_trials.jsonl` (use `--storage jsonl`)

## Automated Workflow (Preferred)

`tv_auto_tune.py` connects to TradingView Desktop via CDP, applies trial inputs
via `setInputValues()`, waits for recalc, reads `reportData().trades()`, and
records trials as `TV_MCP_STRICT`.

### Prerequisites

1. Launch TradingView Desktop with CDP:
   ```bash
   open -a "TradingView" --args --remote-debugging-port=9222
   ```
2. Active chart is `CME_MINI:MES1!` on `5m` with Warbird v7 Strategy loaded.
3. Record trigger family before each batch. Default v7 strategy lane is
   `STRATEGY_ACCEPT_SCALP`.
4. Strategy Tester Properties:
   - From: `2020-01-01`
   - Bar Magnifier: ON
   - Commission: `$1.00` per contract
   - Slippage: `1` tick
5. `pip install requests websockets` (if needed).

### Commands

```bash
# 1) Generate a batch
python scripts/ag/tune_strategy_params.py suggest --count 50

# 2) Execute batch via CDP
python scripts/ag/tv_auto_tune.py run --batch-dir artifacts/tuning/suggestions/<timestamp>/

# 3) Inspect leaderboard
python scripts/ag/tune_strategy_params.py leaderboard --top 20
```

For a single trial file:

```bash
python scripts/ag/tv_auto_tune.py run --trial-file artifacts/tuning/suggestions/<timestamp>/trial_001.json
```

## Manual CSV Fallback

Use only when CDP automation is unavailable.

1. Apply one `trial_*.json` config in TradingView strategy inputs.
2. Export Strategy Tester trade list CSV (`2020-01-01` start enforced).
3. Record trial:

```bash
python scripts/ag/tune_strategy_params.py record \
  --params-file artifacts/tuning/suggestions/<batch>/trial_001.json \
  --trades-csv /path/to/List_of_Trades.csv \
  --notes "5m manual CSV fallback, bar magnifier on, commission $1.00, slippage 1 tick"
```

## Acceptance And Promotion Gates

Before champion promotion:
- Complete **1,000 authoritative trials** for the active 5m campaign.
- Preserve frozen fib/structure scope (no frozen-control mutation).
- Validate sample adequacy and directional balance.
- Validate rolling-window/yearly stability.
- Validate drawdown efficiency vs PF/expectancy.
- Require IS/OOS or walk-forward style review.
- Preserve friction assumptions: commission `$1.00`/side, slippage `1 tick`.

## Coupling Guards In Suggester

The tuner rejects unstable combinations to keep search efficient:
- overly permissive exhaustion cluster (`Z Length <= 14`, `Z Threshold <= 2.2`, `ATR Tolerance >= 0.12`)
- overly sparse exhaustion cluster (`Z Length >= 30`, `Z Threshold >= 2.8`, `ATR Tolerance <= 0.08`)
- coarse-row + loose-auction (`Ticks Per Row >= 6` with `Zero-Print Volume Ratio > 0.14`)
- shallow row depth with extreme imbalance (`Footprint Imbalance % >= 325` and `Imbalance Rows < 2`)
- inverted stop caps (`Max Setup Stop ATR` below `ATR Stop Multiplier`)

## Repeatable 5m Protocol

1. Generate `--count 50` suggestions from `mes5m_agfit_v1`.
2. Execute batch via `TV_MCP_STRICT` (preferred) or `CSV_FULL` fallback.
3. Inspect leaderboard and reject unstable/one-sided candidates.
4. Repeat until 1,000 authoritative trials are complete.
5. Promote finalist cohort into AG multi-fold/bagging, then walk-forward and SHAP.
6. Recommend Pine settings/build changes only after evidence is complete.

## Storage Model

Default storage is local Postgres `warbird` for trial bookkeeping only.
This is not permission to use warehouse joins as active modeling features.

- `warbird_strategy_tuning_batches` — batch metadata
- `warbird_strategy_tuning_trials` — trial rows
  - `CSV_FULL` — authoritative manual CSV scoring
  - `TV_MCP_STRICT` — authoritative CDP scoring
  - `PENDING` — suggested, not yet run

JSONL fallback:

```bash
python scripts/ag/tune_strategy_params.py --storage jsonl suggest --count 10
python scripts/ag/tune_strategy_params.py --storage jsonl record --params-file ... --trades-csv ...
python scripts/ag/tune_strategy_params.py --storage jsonl leaderboard
```

## Boundaries

- This harness does not modify Pine code.
- This harness does not call AutoGluon directly.
- TradingView Deep Backtesting date range is still UI-only.
- If Pine semantics are wrong, the tuner only ranks wrong semantics faster.

Pine semantic repair work remains tracked in
[docs/plans/2026-04-12-v7-interface-reconciliation.md](docs/plans/2026-04-12-v7-interface-reconciliation.md).
