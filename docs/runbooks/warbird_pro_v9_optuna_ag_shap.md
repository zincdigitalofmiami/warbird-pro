# Warbird Pro V9 — Optuna + AG + SHAP Runbook

**Date authorized:** 2026-05-04
**Active Pine surface:** `indicators/warbird-pro-v9.pine` (frozen until promotion approval)
**Trigger family:** `LIVE_ANCHOR_FOOTPRINT`
**Symbol:** MES1! only (ES, NQ, MNQ ignored)
**Timeframe:** 5m only
**Data source:** Databento historical MES (no TradingView CSV imports for HPO)

This runbook ties together the V9 indicator's hidden `ml_*` exports, the
two-lane Optuna setup (entry filter + exit policy), AutoGluon training, and
SHAP-driven feature pruning. It is the operator playbook for the
"best entry, best exit, heads-up exhaustion" goal.

## 1. The two-lane Optuna pair

Both lanes operate on the same MES 5m Databento history and the same export
feature schema. They optimize different layers.

| Lane key | Profile | What it tunes | Objective |
|---|---|---|---|
| `warbird_pro` | `scripts.optuna.warbird_pro_profile` | Post-trigger filter (which V9 candidates to TAKE) + exit policy | `v9_entry_filter_score` |
| `warbird_pro_v9` | `scripts.optuna.warbird_pro_v9_profile` | Exit policy (ATR bracket / RR / breakeven / ATR trail) on all triggers | `v9_risk_exit_score` |

Hub URLs:

- `http://127.0.0.1:8090/studies/warbird_pro`
- `http://127.0.0.1:8090/studies/warbird_pro_v9`

## 2. Pine ml_* feature surface

The V9 indicator emits these hidden plot columns for every confirmed bar (50
features + 5 trade-state outputs). All are Optuna/AG/SHAP fodder.

### Structural / regime
`ml_atr14`, `ml_dir`, `ml_fib_range`, `ml_pivot_dist_atr`, `ml_p618_dist_atr`,
`ml_in_zone`, `ml_bars_since_break`, `ml_break_in_dir`, `ml_reject_at_zone`

### Momentum
`ml_rsi_value`, `ml_rsi_stance_code`, `ml_ma_bias`

### Candlestick patterns (top handful, 7 bull + 7 bear)
Bullish: `ml_pat_hammer`, `ml_pat_inv_hammer`, `ml_pat_dragonfly`,
`ml_pat_bull_engulf`, `ml_pat_piercing`, `ml_pat_morning_star`,
`ml_pat_three_white`
Bearish: `ml_pat_shooting_star`, `ml_pat_hanging_man`, `ml_pat_gravestone`,
`ml_pat_bear_engulf`, `ml_pat_dark_cloud`, `ml_pat_evening_star`,
`ml_pat_three_black`

### Liquidity (BSL/SSL, 2-bar reclaim)
`ml_bsl_dist_atr`, `ml_ssl_dist_atr`, `ml_swept_bsl`, `ml_swept_ssl`,
`ml_reclaimed_bsl`, `ml_reclaimed_ssl`

### Volume delta (proportional close-position split)
`ml_bar_delta`, `ml_net_delta_20`

### Cross-asset 15m trend codes ({-2,-1,0,1,2})
`ml_xa_nq_code`, `ml_xa_zn_code`, `ml_xa_dx_code`

### Exhaustion heads-up
`ml_exhaust_long`, `ml_exhaust_short`

### Entry routing + HTF agreement
`ml_entry_route_code`, `ml_htf_conf_total`

### Triggers + trade state
`ml_entry_long_trigger`, `ml_entry_short_trigger`, `ml_trade_entry`,
`ml_trade_stop`, `ml_trade_tp`, `ml_last_exit_outcome` (0=none, 1=target,
-1=stop, 2=time-exit)

## 3. Databento MES 5m export pipeline

### Step 1 — Pull bars

Use the project's Databento client to fetch MES continuous-front 5m bars from
`2020-01-01` to present.

### Step 2 — Replay through Pine V9 to derive ml_* features

Run a Python harness that mirrors the Pine V9 indicator's emitted ml_* columns
bar-by-bar, OR (preferred) cross-check Pine vs replay output before promoting
this lane. Output must include all `REQUIRED_FEATURE_COLS` listed in
`scripts/optuna/warbird_pro_profile.py`.

### Step 3 — Save with manifest

Save each derived export to:

```
scripts/optuna/workspaces/warbird_pro/exports/databento_mes_5m_<from>-<to>.csv
```

Sibling manifest `databento_mes_5m_<from>-<to>.csv.manifest.json`:

```json
{
  "symbol": "MES1!",
  "timeframe": "5",
  "capture_method": "DATABENTO_TRAINING_CSV",
  "trigger_family": "LIVE_ANCHOR_FOOTPRINT",
  "csv_sha256": "<sha256>",
  "row_count": 0,
  "export_window": {"start": "2020-01-01T00:00:00Z", "end": "..."},
  "repo_commit": "<sha>",
  "notes": "Databento MES continuous-front 5m, Warbird Pro V9 ml_* features derived via Python replay parity."
}
```

Use `DATABENTO_OHLCV_CSV` if the file is raw OHLCV without derived features.
Use `DATABENTO_BARS_CSV` for the raw Databento bar dump prior to any
processing.

The hash check is mandatory; missing or mismatched hash will fail the load.
Manifests must NOT declare an `indicator_file` field for Databento data.

## 4. Optuna runs

### IS / OOS window contract (locked)

- IS (HPO sees this): `2020-01-01` → `2024-12-31`
- OOS (locked, no HPO trial may see it): `2025-01-01` → present

Every Optuna invocation in this runbook MUST pass `--start 2020-01-01 --end
2024-12-31`. The `--end` flag clamps the data frame to `ts <= end_ts` before
each trial runs, keeping 2025+ as a held-out forward window for final
champion selection only. Earlier revisions of this runbook started the HPO
window inside the locked OOS, contaminating the structural-break period
(Trump regime). That is Bug 2; do not regress.

### Step A — Exit policy first (frozen entries)

This warms the exit space without touching filtering. It also tells you the
ceiling of the V9 trigger universe under each exit family.

```bash
source .venv/bin/activate
python scripts/optuna/runner.py \
  --indicator-key warbird_pro_v9 \
  --profile-module scripts.optuna.warbird_pro_v9_profile \
  --n-trials 500 \
  --start 2020-01-01 \
  --end 2024-12-31 \
  --top-n 10
```

Champion artefact: `scripts/optuna/workspaces/warbird_pro_v9/champion.json`.

### Step B — Entry filter on top of the exit champion

Seed the filter HPO with the Step A exit champion, then explore the filter
space.

```bash
python scripts/optuna/runner.py \
  --indicator-key warbird_pro \
  --profile-module scripts.optuna.warbird_pro_profile \
  --champion-path scripts/optuna/workspaces/warbird_pro_v9/champion.json \
  --n-trials 1000 \
  --start 2020-01-01 \
  --end 2024-12-31 \
  --top-n 10
```

### Step C — Locked OOS replay (champion gate)

Re-evaluate the top-10 from each lane against the locked OOS window
(`2025-01-01` → present) which was never seen during HPO. Reject any champion
whose OOS WR drops by >25% absolute or whose PF drops below 1.10. Promotion
is gated on this OOS metric, never on IS folds.

## 5. AutoGluon entry-quality model

After the Optuna champions stabilize, train an AG model that learns
`label = ml_last_exit_outcome` (or a derived 0/1 winner label) from the rich
feature surface.

```bash
source .venv/bin/activate
python scripts/ag/train_ag_baseline.py \
  --workspace scripts/optuna/workspaces/warbird_pro \
  --label ml_last_exit_outcome \
  --presets best_quality \
  --hyperparameters '{"GBM":{},"CAT":{},"XGB":{},"RF":{},"XT":{},"NN_TORCH":{},"FASTAI":{}}' \
  --num-bag-folds 0 \
  --time-limit 14400
```

**Mandatory:** `--num-bag-folds 0` — required by training-full-zoo skill for
time-series correctness (no IID bagging).

The trainer reads the same `exports/` dir and applies the same manifest
validation. Output: `models/warbird_pro_v9_<timestamp>/`.

## 6. SHAP feature pruning

After AG training:

```bash
python scripts/ag/run_shap_analysis.py \
  --predictor models/warbird_pro_v9_<timestamp>/ \
  --report-dir reports/shap/warbird_pro_v9_<timestamp>/
```

The report ranks every `ml_*` feature by mean |SHAP| and per-class importance.

**Pruning loop:**

1. Identify the bottom-quartile features (low |SHAP|, low coverage).
2. Decide: drop from Pine emission (next Pine edit) or keep as junior context.
3. For features SHAP shows as actively misleading (negative correlation with
   true outcome), open a Pine review item — the math may be wrong.
4. Re-run Optuna Step B with the pruned feature set. Compare champion score.
5. Keep features that survive the SHAP cut AND the Optuna re-tune.

## 7. Promotion gate

A V9 setting/build is promoted only when ALL are true:

- Top-1 in `top5.json` under the declared lane objective.
- Trade count clears `min_trades_floor` (40 for filter lane, 20 for exit lane).
- IS PF, raw WR, max DD%, and yearly consistency are coherent.
- OOS re-check holds (Step C).
- Top-3 trials agree enough to suggest a stable region.
- No frozen Pine input mutated.
- No negative-fib stop in the championed exit family.
- AG predictor's calibration is sane (no class collapse, no leakage).
- SHAP-pruned feature set still passes the lane re-run.

## 8. Trading discipline

This pipeline informs the operator. It does not auto-trade.

- Mechanical SL is non-negotiable (`feedback_mechanical_stops_nonnegotiable`).
- 5m bar-close only (`feedback_no_midbar_trading`).
- Post-sweep entries are higher-quality than entries at the level
  (`feedback_post_sweep_entry`).
- Never push to TradingView Pine Editor without explicit per-session approval.

## 9. Friction floors (V9 contract)

- Commission: $1.00/side flat (no slippage adjustment for indicator-only V9).
- MES point value: $5.00.
- MINTICK: 0.25.
- Data floor: 2020-01-01.

## 10. Authority docs

- `AGENTS.md`
- `CLAUDE.md`
- `docs/MASTER_PLAN.md`
- `docs/contracts/pine_indicator_ag_contract.md`
- `scripts/optuna/README.md`
