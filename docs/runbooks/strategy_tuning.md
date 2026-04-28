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

## Active Search Surface — Phased

The 5m main-fib campaign is run as four sequential 1,000-trial Optuna phases,
each with its own search-space JSON. The legacy single-pass file
`scripts/ag/strategy_tuning_space.json` is kept as a baseline reference and
must NOT be used for the phased campaign. Always pass `--space` explicitly.

| Phase | Profile | Space file | Scope |
|---|---|---|---|
| 1 | `mes5m_phase1_trend_vwap_ma_liqsweep` | `scripts/ag/strategy_tuning_space.phase1.json` | trend / VWAP / MA / liquidity sweep |
| 2 | `mes5m_phase2_momentum` | `scripts/ag/strategy_tuning_space.phase2.json` | VF Window / VF Candle Weight / VF Volume Weight / NFE Length / RSI KNN Window |
| 3 | `mes5m_phase3_footprint_exhaustion` | `scripts/ag/strategy_tuning_space.phase3.json` | Ticks / VA / Imbalance% / Extension ATR Tol / Zero-Print / Swing Lookback / Cooldown / Imbalance Rows |
| 4 | `mes5m_phase4_entry_risk` | `scripts/ag/strategy_tuning_space.phase4.json` | Execution Anchor / ATR Stop Multiplier / Max Setup Stop ATR / Acceptance Retest Window |

Runtime context for every phase: `CME_MINI:MES1!` on `5m`, Bar Magnifier ON,
commission `$1.00`/side, slippage `1` tick, capital `$50,000`.

Locked controls in every phase intentionally keep fib architecture / structure
internals unchanged (ZigZag/fib-threshold internals, confluence span,
visual/debug knobs, and other non-trade-list controls).

### Phase 0 — Pine Schema Parity

Before Phase 1 may run, both shared Pine surfaces must expose the Phase 1 / 3
knobs that did not previously exist:

- `Use MA Trend Filter` (bool)
- `MA Family` (string)
- `MA Fast Length` (int)
- `MA Slow Length` (int)
- `Use VWAP Gate` (bool)
- `Liquidity Sweep Lookback` (int)
- `Exhaustion Swing Lookback` (int)
- `Exhaustion Cooldown Bars` (int)

Files: `indicators/v7-warbird-strategy.pine`,
`indicators/v7-warbird-institutional.pine`.

Phase 0 also fixes the `Max Setup Stop ATR` Pine `minval` from `2.5` to `1.0`
so the Phase 4 search range (1.0–3.5) is not silently floor-rejected by the
input parser.

Phase 0 is a Pine edit and requires explicit per-session approval per CLAUDE.md
and `docs/runbooks/claude_rogue_proof_phase_contract.md`.

## Files

- Phase 1 space: [scripts/ag/strategy_tuning_space.phase1.json](../../scripts/ag/strategy_tuning_space.phase1.json)
- Phase 2 space: [scripts/ag/strategy_tuning_space.phase2.json](../../scripts/ag/strategy_tuning_space.phase2.json)
- Phase 3 space: [scripts/ag/strategy_tuning_space.phase3.json](../../scripts/ag/strategy_tuning_space.phase3.json)
- Phase 4 space: [scripts/ag/strategy_tuning_space.phase4.json](../../scripts/ag/strategy_tuning_space.phase4.json)
- Legacy single-pass baseline: [scripts/ag/strategy_tuning_space.json](../../scripts/ag/strategy_tuning_space.json)
- Cohort banding: [scripts/ag/band_phase_winners.py](../../scripts/ag/band_phase_winners.py)
- Suggester / leaderboard CLI: [scripts/ag/tune_strategy_params.py](../../scripts/ag/tune_strategy_params.py)
- CDP automation: [scripts/ag/tv_auto_tune.py](../../scripts/ag/tv_auto_tune.py)
- Local tables: `warbird_strategy_tuning_batches`, `warbird_strategy_tuning_trials`
- Migrations: [local_warehouse/migrations/008_strategy_tuning_trials.sql](../../local_warehouse/migrations/008_strategy_tuning_trials.sql), [009](../../local_warehouse/migrations/009_strategy_tuning_evaluation_mode.sql)
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

Before advancing to the next phase OR promoting a champion:
- Complete **1,000 authoritative trials** for the current phase.
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

## Phased 5m Protocol

Each phase = **20 batches × 50 trials = 1,000 authoritative trials**.
Phases run sequentially; phase N+1 cannot start until phase N has cleared the
acceptance and OOS gates and the carry-forward banding step has produced
phase N+1's banded space.

### Per-phase loop (repeat 20 times)

```bash
PHASE=1   # 1, 2, 3, or 4
SPACE=scripts/ag/strategy_tuning_space.phase${PHASE}.json

# Generate 50 suggestions for the current phase
python scripts/ag/tune_strategy_params.py --space "$SPACE" suggest --count 50

# Execute the batch via CDP (TV_MCP_STRICT). Hand-fall to CSV_FULL only if CDP is down.
python scripts/ag/tv_auto_tune.py --space "$SPACE" run \
    --batch-dir artifacts/tuning/suggestions/<timestamp>/

# Inspect leaderboard for the current phase
python scripts/ag/tune_strategy_params.py --space "$SPACE" leaderboard --top 20
```

Repeat the suggest -> run -> leaderboard loop until 1,000 authoritative
(`TV_MCP_STRICT` or `CSV_FULL`) trials are recorded against the phase's
profile name. Suggestions adapt from the freshly-recorded leaderboard each
loop, which is why the cadence is 20 × 50 rather than one 1,000-suggestion
emission.

### Carry-forward gate (between phases)

After the 1,000-trial phase clears its OOS / walk-forward gate:

```bash
python scripts/ag/band_phase_winners.py \
    --from-space scripts/ag/strategy_tuning_space.phase${PHASE}.json \
    --to-space   scripts/ag/strategy_tuning_space.phase$((PHASE + 1)).json \
    --top 20 \
    --storage postgres
```

Banding rules:
- numeric: median ± clipped IQR (or MAD when IQR collapses), clipped to the
  prior-phase original min/max
- int with discrete values: retain only values within the IQR/MAD window,
  preserving at least one value
- categorical / bool: retain top 1–2 modes, with a minority retained only when
  its support is `>=15%` of the cohort

The banding script writes a sidecar manifest
(`<phase{N+1}>.banding-manifest.json`) recording the contributing trial ids,
per-knob statistics, and the kept domain. The manifest is the audit trail —
do not advance to phase N+1 without reviewing it.

After banding, run a fresh 50-suggestion smoke batch on the phase N+1 space
to confirm the suggester still produces valid configs before opening the full
20×50 loop.

### Phase 0 (Pine schema parity, one-time)

Phase 0 is not an Optuna run; it is the Pine input add required to expose
Phase 1 / 3 knobs on both shared surfaces. See the "Active Search Surface —
Phased" section above for the input list. Phase 0 must clear the full Pine
verification pipeline (pine-facade, pine-lint, contamination, npm build,
parity guard) before Phase 1 may begin.

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
