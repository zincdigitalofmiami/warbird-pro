---
name: training-indicator-optimization
description: Sweep indicator parameters (ZigZag Deviation / Depth, Threshold Floor, Min Fib Range) to find the best configuration before training. Uses scripts/ag/tv_auto_tune.py + tune_strategy_params.py. Different job than Monte Carlo — MC varies market context given FIXED indicator settings; this varies the settings themselves.
---

# Training — Indicator Optimization

Find the best indicator parameters (Deviation, Depth, Threshold Floor, Min Fib Range, etc.) BEFORE training a model on the data they produce. Bad indicator settings produce bad setups; no model training can fix fundamentally bad setups.

## When to use

- Before any fresh training cycle when you suspect the current indicator settings aren't optimal
- After Monte Carlo shows every stop family is negative-EV even after threshold gating (the data itself may be bad)
- When a competing setup geometry is proposed (new fib levels, different ZigZag parameters, alternative confluence scoring)

## When NOT to use

- For market-context / entry-condition analysis given fixed indicator settings — that's `training-monte-carlo`
- For strategy-layer tuning (SL/TP placement, position sizing) — that's TV strategy tester
- When the current indicator config is already under a 15m-fib-owner freeze (per CLAUDE.md: `Deviation=4, Depth=20, Threshold Floor=0.50, Min Fib Range=0.5`) — don't sweep a frozen surface

## Current status in Warbird

**15m fib-owner freeze** (CLAUDE.md) — current production config:
- `zigzag_deviation = 4`
- `zigzag_depth = 20`
- `threshold_floor = 0.50`
- `min_fib_range = 0.5`

These were locked 2026-04-14 after a tuner run. The tuner infrastructure exists but **has not recorded any authoritative `mes15m_agfit_v3` trials yet**. Any optimization sweep you propose should explicitly state whether it's challenging the freeze or accepting it.

## Tools

### `scripts/ag/tv_auto_tune.py`

CDP-driven (Chrome DevTools Protocol) automation that:
1. Opens TradingView Desktop at a specified symbol/timeframe
2. Loads the target Pine script
3. Applies a set of input overrides via the indicator's input panel
4. Triggers a recompile and waits for the strategy tester to recalc
5. Pulls `data_get_strategy_results`, `data_get_trades`, `data_get_equity`
6. Records the trial to a JSONL

### `scripts/ag/tune_strategy_params.py`

Higher-level wrapper that:
1. Loads a search-space JSON (`scripts/ag/strategy_tuning_space.json`)
2. Generates trial candidates (grid or random search)
3. Calls `tv_auto_tune.py` per candidate
4. Scores candidates per the profile's objective (drawdown efficiency + rolling-window stability + footprint-tail stability + yearly consistency per CLAUDE.md)
5. Writes a leaderboard to `artifacts/tuner/<profile>/`

### `scripts/ag/strategy_tuning_space.json`

Defines:
- `profile` name (e.g., `mes15m_agfit_v3`)
- `search_space` per parameter (min, max, step, type)
- `locked_inputs` — params that must NOT vary (e.g., the frozen fib-owner settings)
- `rejection_rules` — coupled-parameter constraints
- `objective_weights` — how trial scores combine

## Profile: `mes15m_agfit_v3` (current, 2026-04-13 hardening)

Per CLAUDE.md:
- Search ranges narrowed (vs earlier profiles)
- Non-causal locked inputs removed from trial signatures
- Coupled-parameter rejection rules added
- Objective upgraded to include:
  - Drawdown efficiency
  - Rolling-window stability
  - Footprint-tail stability
  - Yearly consistency

**No authoritative trials recorded yet** — the tuner is ready, but no sweep has been executed and ledgered. This is an open work item.

## Canonical sweep workflow

```bash
# 1. Launch TV Desktop with CDP enabled
/usr/local/bin/python3 -c "
from scripts.ag.tv_auto_tune import tv_launch
tv_launch(port=9222, kill_existing=True)
"

# 2. Run the tuner
cd "/Volumes/Satechi Hub/warbird-pro"
/usr/local/bin/python3 scripts/ag/tune_strategy_params.py \
  --profile mes15m_agfit_v3 \
  --space scripts/ag/strategy_tuning_space.json \
  --n-trials 40 \
  --output-root artifacts/tuner
```

Background via `run_in_background: true`. Each trial is 1-5 min; 40 trials ~1-3 h.

## Interpreting tuner output

### Per-trial JSONL row

```json
{
  "profile": "mes15m_agfit_v3",
  "trial_id": "...",
  "inputs": {"zigzag_deviation": 3, "zigzag_depth": 15, ...},
  "results": {
    "net_profit": 12340,
    "profit_factor": 1.52,
    "max_drawdown": 2120,
    "total_trades": 312,
    "win_rate": 0.471,
    "trading_days": 245,
    "yearly_consistency_score": 0.78,
    "footprint_tail_stability": 0.61
  },
  "score": 0.645  // objective_weights.dot(normalized_results)
}
```

### Selection criteria

Top trial by `score` is NOT automatically the winner. Sanity-check:
1. `total_trades` > some minimum (e.g., 100 per year) — too few trades = overfit
2. `max_drawdown` < some ceiling ($5k as a rough MES-1-contract threshold)
3. `yearly_consistency_score` close to 1 (consistent across years)
4. Winning inputs aren't on the boundary of the search space (if they are, expand search)
5. Winning inputs pass the project's rejection rules (coupled-param constraints)

### When to commit new freeze settings

ONLY commit a new freeze to CLAUDE.md when:
1. Top-5 trials are in close agreement on parameter values
2. Statistical tie-breaker (bootstrap EV or Sharpe) prefers the winner over the current freeze
3. Backtest on held-out year (out-of-sample to the tuner window) validates

## Known traps

1. **CDP races.** TV Desktop sometimes doesn't repaint the chart after an input change — the tuner includes polling logic, but if trials come back with identical scores, check for stale inputs.
2. **TV re-compile lag.** After `pine_smart_compile`, the strategy tester can take 10-60 s to regenerate trades. If the tuner polls too fast, it records stale results. Existing code has this in the polling loop — don't disable it.
3. **Non-causal inputs in the trial signature.** Some indicator inputs don't affect the trade logic (cosmetic plot colors, label positions). The profile's `locked_inputs` exists to exclude these — expanding the sweep to cosmetic params wastes compute.
4. **"Best" on a short window is overfit.** Tuner windows of < 1 year are unreliable. Use full multi-year history.

## Relationship to Monte Carlo and full-zoo training

- **Indicator optimization = choose the setup-generation parameters**. Varies: Deviation, Depth, Threshold, MinFibRange.
- **Training = given those parameters, learn the best predictor**. Varies: model family, hyperparameters.
- **Monte Carlo = given the trained predictor, find the best trading rules**. Varies: stop_family, probability threshold, entry conditions.

Don't confuse the three. Each answers a different question and requires a different loop.

## Related skills

- `training-tv-backtesting` — validating a specific config interactively before committing
- `training-pre-audit` — run before any optimization cycle to ensure data is ready
- `training-monte-carlo` — the *downstream* job — what to do once indicator settings are fixed
- `trading-indicators:pine:verify` — Pine verification gates before commit
