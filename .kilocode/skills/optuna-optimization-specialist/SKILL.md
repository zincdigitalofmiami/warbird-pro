---
name: optuna-optimization-specialist
description: Use when designing, launching, reviewing, repairing, or promoting Warbird Optuna studies for indicator or strategy optimization, including advisory requests like optimizing Nexus Fusion Engine ML / Warbird Nexus Machine Learning RSI for 5m MES trading. Covers the shared scripts/optuna runner, profile adapter contracts, canonical workspace layout, 8090 hub, IS/OOS walk-forward discipline, champion selection, frozen Pine/input boundaries, preset and alert validation, and routing decisions between Optuna, CDP TradingView tuning, AutoGluon HPO, Monte Carlo, and manual TV backtesting.
---

# Optuna Optimization Specialist

Operate Optuna as a controlled experiment harness. Do not use it to search around locked contracts, missing data, weak validation, or unapproved Pine changes.

## Authority

Read these before substantive Optuna work:

1. `AGENTS.md`
2. `docs/INDEX.md`
3. `docs/MASTER_PLAN.md` — especially the Optuna Operator Surface checkpoint and current v8/v7 locks
4. `CLAUDE.md` — current runtime truth, frozen settings, verification gates
5. `scripts/optuna/README.md`
6. `docs/runbooks/wbv7_institutional_optuna.md` when working on the v7 institutional lane

Load related skills only when needed:

- `optuna-setup` for a new profile adapter, registry entry, workspace, or hub wiring.
- `optuna-mes-es-hpo` for MES/ES study design and trial interpretation.
- `training-indicator-optimization` for CDP-driven TradingView input sweeps.
- `training-monte-carlo` for post-model threshold, stop-family, or entry-condition sweeps.
- `training-tv-backtesting` for manual TradingView out-of-sample validation.

## Nexus 5m MES Advisory Mode

Use this mode when the user asks how to optimize Nexus Fusion Engine ML / Warbird Nexus Machine Learning RSI for discretionary 5m MES trading, especially early reversals, highs/lows, volume changes, divergence, KNN, presets, crossovers, regime state, or alerts.

Do not answer with generic indicator advice. Build a trust framework around the user's actual chart workflow.

### Ground Truth First

- Inspect the active local script when available: `indicators/warbird-nexus-machine-learning-rsi.pine`.
- Treat the public TradingView page as an upstream reference, not proof of the local file. The public page describes AMF, VNVF, KNN, divergence, fatigue, confluence, and HTF bias; the local Warbird file may intentionally differ.
- For the current local 5m-only lane, note differences before recommending settings. Example: local defaults include `lengthInput=18`, `sigLenInput=6`, `presetInput=Default`, `obInput=75`, `osInput=25`, `knnKInput=7`, `knnWindowInput=180`, structural filter ON, and max pivot age 60.
- If the user provides only the public URL, browse it and then request or inspect the exact Pine code before claiming exact optimization coverage.

### Current Nexus Optimization Lane

The repo already has a Nexus lane:

- indicator key: `warbird_nexus_ml_rsi`
- Pine file: `indicators/warbird-nexus-machine-learning-rsi.pine`
- profile: `scripts.optuna.warbird_nexus_ml_rsi_profile`
- workspace: `scripts/optuna/workspaces/warbird_nexus_ml_rsi`
- contract: MES 5m, native 5m bar close
- data: `data/mes_5m.parquet`, with `data/mes_1m.parquet` rollup fallback
- objective metric: `nexus_5m_signal_quality`

The current profile can evaluate source, preset, smoothing, signal smoothing, engine period, OB/OS zones, confluence thresholds, fatigue bars, KNN K/window, and confirmation gates for confluence, volume flow, zone exits, and KNN. Volume Flow is a first-class scored subsystem through `volume_flow_quality`, not just a boolean gate.

For MES 5m, assume real exchange volume is available and required. The local parquet must contain a real `volume` column, and the profile must use it directly. Do not fake volume, infer volume from price range, or silently substitute tick counts. If a non-volume symbol is ever used, Pine should display `N/A` and remove Volume Flow from regime/confluence scoring; Optuna should mark that lane as unsupported for volume validation.

Footprint/order-flow data is richer than the current Nexus Volume Flow. Do not claim Nexus is footprint-aware unless the Pine file and profile explicitly consume footprint-derived fields. If the user wants footprint-aware optimization, route that as a separate profile extension with an explicit persisted data source.

The current profile does not fully validate every visual subsystem. Before claiming trust in divergence, max pivot age, structural filter thresholds, alert routing, or any public-script HTF bias behavior, verify whether those knobs exist in the local script and whether the profile actually scores them. If not, mark them as a profile-extension requirement.

### Operator Intake Questions

After inventorying the indicator and current profile, ask sharp questions before prescribing settings. Keep the first round to the highest-leverage unknowns; do not ask questions whose answers are already visible in the Pine file or profile.

Ask these when the user's prompt is broad:

1. Which session do you trade most: RTH only, ETH, opening hour, power hour, or all day?
2. Is the indicator meant to be an early warning tool, an entry trigger, a confirmation layer, or all three?
3. For a 5m MES reversal, what is the minimum move you care about: scalp 2-4 points, rotation 5-10 points, or larger swing?
4. Which failure hurts more: missing a reversal or taking too many false reversals?
5. How many alerts per session is tolerable before you ignore them?
6. Do you want long and short settings treated symmetrically, or should shorts be stricter?
7. Which signals have already felt useful or useless: cross dots, divergence, fatigue diamonds, volume flow, KNN flips, confluence, regime fills?
8. Do you have screenshots, trade timestamps, or a journal of good/bad examples to score against?

If the user cannot answer yet, proceed with clearly labeled assumptions for a 5m MES discretionary reversal trader and mark them as assumptions to validate.

### Required Answer Shape

For a user asking "what should I optimize and how should I use it," produce:

1. **Inventory**: state what script/profile/data were inspected and what cannot be verified yet.
2. **Clarifying questions**: ask the smallest useful set of operator questions if preferences are missing.
3. **What the indicator is doing**: explain AMF, volume flow, KNN, confluence, divergence, fatigue, and regime in trading terms.
4. **What to trust now vs test first**: split settings into validated, partially validated, and unvalidated.
5. **Preset plan**: give a purpose for each preset and propose any additional custom presets as hypotheses, not facts.
6. **5m MES playbooks**: define reversal, continuation/pullback, no-trade chop, and volume-shift workflows.
7. **Alert plan**: specify which alerts to enable, which are context-only, and which should never be standalone entries.
8. **Optimization plan**: state which settings are Optuna-ready now, which need CDP/TradingView validation, and which need profile changes.
9. **Validation gates**: require real MES 5m data, OOS review, TradingView replay or exported alerts, and a written journal of false positives/false negatives.

### Preset Design Rules

Default presets must have distinct jobs:

- `Scalping`: early warning and fast reversal scouting. Expect more noise; require confluence or volume/KNN confirmation before entry.
- `Default`: balanced 5m operating mode. Use for regular MES session monitoring and as the baseline for optimization.
- `Swing`: slower, fewer signals. Use for major high/low attempts, session trend transitions, and avoiding chop.
- `Position`: regime and exhaustion context only on 5m; do not treat every crossover as an entry because it will be late by design.

When proposing new presets, name them by purpose and define exact knobs. Suitable hypotheses for this user's style:

- `Rodeo Reversal`: faster fatigue/divergence detection with stricter confirmation.
- `Volume Flip`: emphasizes VNVF crossing, confluence, and KNN agreement after a high/low.
- `Opening Patience`: suppresses noisy first-15-minute signals and waits for confirmed regime/volume alignment.
- `Chop Filter`: slower smoothing, wider zones, higher confluence thresholds, and stricter KNN.

Do not add new Pine presets unless the user explicitly asks for code changes. If code changes are requested, Pine approval and verification gates apply.

### Alert Policy For 5m MES

Separate alerts into three classes:

- Entry candidate: bull/bear cross on the correct side of the midline, preferably after OB/OS or with confluence/KNN/VF agreement.
- Early warning: regular divergence, OB/OS fatigue, zone exit, and KNN flip.
- Context: volume inflow/outflow and confluence high/low.

Default recommendation for a discretionary 5m MES operator:

- Enable regular divergence alerts and fatigue alerts as "look now" warnings.
- Enable bull/bear cross alerts as candidate entries only when they align with volume flow and KNN.
- Enable volume flow alerts for context, not standalone entries.
- Enable KNN flip alerts only if the flip rate is not too high in live testing.
- Keep confluence alerts off until thresholds are calibrated; otherwise they can become noisy.

JSON webhooks are valuable as a sidecar capture stream beside the main Warbird indicator when every dynamic alert path honors the JSON toggle. Verify bull/bear crosses, zone exits, regular/hidden divergences, volume inflow/outflow, fatigue, KNN flips, and confluence alerts before telling the user the suite is webhook-ready. Treat webhook payloads as telemetry and review evidence first, not as automated trade instructions.

### Trust Standard

Never say the user can "trust everything" because Optuna found a top trial. Trust requires subsystem-specific evidence:

- smoothing/source/preset: Optuna rank stability and OOS survival
- crossovers: forward favorable/adverse excursion after signal
- volume flow: improvement when gate is on vs off
- KNN: precision and flip-rate stability, not just confidence display
- divergence/max pivot age/structural filter: explicit divergence event scoring or TradingView replay/export evidence
- alerts: alert frequency, false-positive rate, missed-move review, and session/time-of-day breakdown

## Scope Split

Use Optuna when parameters can be evaluated inside a profile adapter from stable, real data without re-running Pine per trial.

Use the CDP TradingView tuner when a parameter changes Pine's historical state machine output, footprint-derived values, or any TV-only result that cannot be recomputed from a single export.

Use AutoGluon training skills for model-family selection and predictor hyperparameters. Do not call AutoGluon HPO an Optuna study.

Use Monte Carlo only after a trained predictor or fixed policy exists. Monte Carlo varies decision thresholds and market-context rules; it does not choose indicator geometry.

## Non-Negotiables

- No mock data, synthetic fills, inactive symbols, or stale exports.
- Canonical Optuna state lives under `scripts/optuna/`, not `data/optuna/`.
- Active lanes are real directories under `scripts/optuna/workspaces/`; registry entries without a workspace directory are intent only, not active runtime truth.
- The canonical hub is `http://localhost:8090/`; do not resurrect the retired 8080 compatibility path.
- Never fork `scripts/optuna/runner.py` for a new study. Add or repair a profile adapter.
- Never tune frozen fib-owner settings unless the user explicitly approves challenging the freeze.
- Never tune on OOS. Keep a one-session embargo minimum between train/validation/test windows.
- Respect MES friction floors: `$1.00` per side commission, at least one tick slippage, MES point value `$5.00`.
- Respect stop discipline: structural stop floor is `0.618 x ATR(14)`.
- If any `.pine` file is touched, Pine approval and the full Pine verification gate apply.

## Preflight Checklist

Run this before launching or modifying a study:

```bash
git status --short
rg -n "indicator_key|profile_module|study.db|default_study_name" scripts/optuna docs/runbooks AGENTS.md CLAUDE.md
find scripts/optuna/workspaces -mindepth 1 -maxdepth 1 -type d -print | sort
python scripts/optuna/runtime_health.py
```

Then answer:

- Which lane is active: `indicator_key`, profile module, workspace path, study name, symbol, timeframe?
- Is the profile evaluating real data from the approved source?
- Which parameters are swept, locked, categorical, boolean, and derived?
- Which parameters are TV-only and must be routed to the CDP tuner instead?
- What is IS, validation, OOS, and embargo?
- What trial-count floor prevents under-trading overfit?
- What artifact will prove the champion: `study.db`, `top5.json`, `champion.json`, OOS report?

## Profile Adapter Contract

Every profile must satisfy the shared runner contract:

```python
BOOL_PARAMS: list[str]
NUMERIC_RANGES: dict[str, tuple[float, float]]
INT_PARAMS: set[str]
CATEGORICAL_PARAMS: dict[str, list]
INPUT_DEFAULTS: dict

def load_data() -> pandas.DataFrame: ...
def run_backtest(df: pandas.DataFrame, params: dict, start_date: str) -> dict: ...
```

The result dict must expose enough metrics for ranking and audit: trades, win rate or composite objective, profit factor, gross profit/loss, drawdown, and any profile-specific quality gates.

Raise exceptions for invalid configurations and let `runner.py` prune the trial. Do not silently coerce invalid trial geometry into plausible-looking results.

## Study Design

Keep the first study narrow. Prefer staged optimization:

1. Freeze the structural champion or locked baseline.
2. Tune entry/stop/risk knobs that can be recomputed honestly.
3. Validate the champion OOS.
4. Start a second study for confirmation-layer parameters only if stage 1 survives.

Use champion seeding when prior grid or manual evidence exists. Use `--resume` for existing studies; do not delete or recreate a study to hide failed trials.

Treat boundary winners as suspicious. If the best trial sits on a range boundary, inspect whether the range is too narrow or the objective is rewarding an invalid edge.

## Launch Patterns

```bash
source .venv/bin/activate

python scripts/optuna/runner.py \
  --indicator-key <key> \
  --profile-module scripts.optuna.<profile_module> \
  --n-trials 300 \
  --start 2025-01-01 \
  --top-n 5
```

Resume:

```bash
python scripts/optuna/runner.py \
  --indicator-key <key> \
  --resume \
  --n-trials 500 \
  --top-n 5
```

Seed a champion:

```bash
python scripts/optuna/runner.py \
  --indicator-key <key> \
  --champion-path scripts/optuna/workspaces/<key>/champion.json \
  --n-trials 300 \
  --top-n 5
```

## Champion Standard

Do not promote a champion until all are true:

- Rank 1 in `top5.json` under the declared objective.
- Trade count clears the lane-specific floor.
- Profit factor, raw win rate, drawdown, and yearly consistency are coherent.
- OOS re-check survives without tuning on OOS.
- Top trials agree enough to suggest a stable region, not a single lucky point.
- Parameters do not violate frozen Pine/input boundaries.
- The result can be explained in terms of the strategy contract, not only a high score.

## Common Failure Modes

| Symptom | Likely cause | Response |
|---|---|---|
| Hub shows a lane with no live study | Registry entry exists without workspace directory | Treat as inactive unless creating an approved lane |
| All trials pruned | Search space too tight or data/export missing | Verify data first, then widen legal ranges |
| Great IS, weak OOS | Overfit or regime-specific objective | Narrow search, stage the study, re-check embargo |
| High score with tiny trade count | Under-trading exploit | Raise or enforce the trade-count floor |
| Champion fails live/TV replay | Swept TV-only parameter in Python | Move that parameter to CDP tuning |
| Study DB locked | Multiple workers on one SQLite DB | Use `--n-jobs 1` or separate DBs deliberately |
| Identical scores across many trials | Params not wired into `run_backtest` or stale export | Audit profile wiring before continuing |

## Closure

Before claiming completion, provide:

- touched files or study artifacts
- exact command(s) run
- pass/fail status
- active workspace path
- top result summary
- OOS validation status or a clear reason it was not run

If validation is missing, mark the work incomplete.
