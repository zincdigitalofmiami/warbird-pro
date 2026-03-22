# Warbird Pro — AF Struct+IM Indicator Plan

**Date:** 2026-03-20
**Status:** Active Plan — Single Source of Truth
**Scope:** One indicator only: `AutoFib Structure + Intermarket Alerts`

**THIS IS THE ONLY PLAN TO UPDATE.**

- All architecture changes, implementation phases, UI decisions, and status updates for this indicator live in this file.
- Do not create new architecture or plan docs for this indicator without explicit approval.
- All other plan docs are archived under `docs/plans/archive/`.

---

## Update Log

- 2026-03-22: Added dependency-security remediation checkpoint order (plan updates first, then implementation). Scope includes Next.js and transitive lockfile remediation plus `xlsx` ingestion-surface removal/replacement.
- 2026-03-20: Converted the active plan into a single-indicator plan.
- 2026-03-20: Archived older plan docs and removed them from the active path.
- 2026-03-20: AG model concept — fib continuation probability engine with TP1/TP2 targets (1.236/1.618 extensions), re-entry signals, full macro/economic training context, and Pine config packet output.
- 2026-03-20: Added "AG Models Pine's Configuration Space" — AG output must be Pine-native (exact input values, thresholds, weights, gates, module decisions).
- 2026-03-20: Added Forensic Review of current script — 8 high-risk problems to fix before AG training.
- 2026-03-20: Restructured plan around Canonical Goal / Canonical Outputs / Canonical Standards / Locked v1 Mechanisms. The product goal and chart-output surface are canonical. The v1 build path is now locked.

---

## Security Remediation Checkpoint (2026-03-22)

This checkpoint is execution-ordered and is part of the active plan:

1. Update plan state and remediation intent in docs first.
2. Patch all open Dependabot vulnerabilities in the repository.
3. Run verification gates (`npm audit`, `npm run build`) before merge/push.

Locked constraints for this checkpoint:

- Keep scope minimal to vulnerability closure and direct runtime-path disambiguation.
- No unrelated refactors.
- Preserve production boundary rules and cron guardrails.
- Keep dependency changes explicit and auditable in lockfile history.

---

## Canonical Goal

Deliver the best possible **fib continuation/reversal entry indicator** on TradingView for MES, with:

- actionable entries on chart
- TP1 (1.236 extension) and TP2 (1.618 extension) path visualization
- probability, win rate, and trade stats visible in a right-side chart table
- AG used aggressively to improve it offline
- Deep Backtesting used to prove it

The goal is canonical. Whatever it takes to get there is what we do.

---

## Canonical Outputs (must appear on chart)

These are the required chart outputs. Each must map to a defined calculation. Each must come from real data.

| Output | Definition |
|--------|-----------|
| **Entry marker** | Exact bar where the indicator signals entry at a fib pullback level |
| **TP1 probability** | Probability the current setup reaches the 1.236 fib extension. Must be defensible and calibrated — when it says 70%, it should be right ~70% of the time. |
| **TP2 probability** | Probability the current setup reaches the 1.618 fib extension. Same calibration standard. |
| **Reversal risk** | Probability that the continuation fails into a reversal |
| **Win rate** | Historical hit rate for the current setup bucket (fib level, regime, session, direction). Based on real backtested data, not a guess. |
| **Stats window** | What history/regime/sample the displayed numbers are based on |
| **Action state** | `LONG READY`, `SHORT READY`, `NO TRADE`, `CONFLICT` |
| **Target eligibility** | 20pt+ pass/fail |
| **Regime** | Intermarket regime, volatility state, macro posture |
| **Stop level** | From a bounded, deterministic stop family — not a per-trade model output |
| **TP1 / TP2 levels** | The 1.236 and 1.618 fib extension prices |
| **Re-entry signal** | When a pullback after TP1 is a continuation opportunity |

---

## Canonical Standards

1. Every stat on the chart must come from real data — never mocked, never fabricated.
2. Every probability/win rate must be defensible and calibrated.
3. Whatever appears in the table must map to a defined calculation.
4. Pine must remain the visible production surface.
5. AG is offline only — never in the live signal path.
6. Deep Backtesting is the proof layer.

---

## Locked v1 Mechanisms

The chart-output surface is canonical. The v1 mechanism for producing those outputs is now locked.

### Primary v1 delivery path

Use a **hybrid Pine + AG packet** architecture:

1. Pine computes all live features, states, and the deterministic `confidence_score` from current bar context.
2. AG trains offline, calibrates the score, and produces a Pine-ready packet of:
   - score-to-probability mappings
   - win-rate tables
   - reversal-risk tables
   - stop-family decisions
   - module keep/remove calls
   - exact Pine input values
3. Pine renders the right-side table by:
   - identifying the current setup bucket
   - identifying the current confidence bin
   - looking up the calibrated TP1 / TP2 / reversal / win-rate stats from the latest promoted packet

This is the primary v1 path.

### Allowed fallback

If the full bucketed calibration surface is too sparse in early testing, the fallback is:

- Pine-embedded probability bands keyed off fewer variables
- coarser confidence bins
- coarser bucket hierarchy

Fallback is allowed only if it preserves defensible calibration and real sample counts.

### Update cadence

The packet update cadence for v1 is:

- offline retrain / recalibration on demand during development
- promoted packet refresh no more than once per week in normal operation

No intraday live model serving.

### Locked table-stat formulas

These definitions are canonical for v1:

- `confidence_score`
  - deterministic Pine score on a `0-100` scale computed from live Pine features and rules
- `tp1_probability_display`
  - empirical TP1 hit rate for the current `setup_bucket x confidence_bin`, calibrated offline by AG
- `tp2_probability_display`
  - empirical TP2 hit rate for the current `setup_bucket x confidence_bin`, calibrated offline by AG
- `reversal_risk_display`
  - empirical `REVERSAL` rate for the current `setup_bucket x confidence_bin`
- `win_rate_display`
  - empirical rate of `TP1_ONLY OR TP2_HIT` for the current `setup_bucket x confidence_bin`
- `stats_window_display`
  - training date range + sample count used for the displayed bucketed stats

### Locked bucket hierarchy

#### Confidence bins

Use 5 bins for v1:

- `BIN_1 = 0-19`
- `BIN_2 = 20-39`
- `BIN_3 = 40-59`
- `BIN_4 = 60-79`
- `BIN_5 = 80-100`

#### Setup bucket key

The primary bucket key is:

- `direction`
- `setup_archetype`
- `fib_level_touched`
- `regime_bucket`
- `session_bucket`

#### Setup archetype values

Use these v1 archetypes:

- `ACCEPT_CONTINUATION`
- `ZONE_REJECTION`
- `PIVOT_CONTINUATION`
- `FAILED_MOVE_REVERSAL`
- `REENTRY_AFTER_TP1`

#### Regime bucket values

Use these v1 regime buckets:

- `RISK_ON`
- `NEUTRAL`
- `RISK_OFF`
- `CONFLICT`

#### Session bucket values

Use these v1 session buckets in `America/Chicago`:

- `RTH_OPEN = 08:30-09:30`
- `RTH_CORE = 09:30-11:30`
- `LUNCH = 11:30-13:00`
- `RTH_PM = 13:00-15:00`
- `ETH = all other bars`

### Locked bucket fallback ladder

If the current `setup_bucket x confidence_bin` does not meet the minimum sample floor, Pine must walk this fallback ladder:

1. `direction x setup_archetype x fib_level_touched x regime_bucket x session_bucket x confidence_bin` with `n >= 40`
2. `direction x fib_level_touched x regime_bucket x session_bucket x confidence_bin` with `n >= 60`
3. `direction x fib_level_touched x regime_bucket x confidence_bin` with `n >= 80`
4. `direction x fib_level_touched x confidence_bin` with `n >= 120`
5. `direction x confidence_bin` with `n >= 200`
6. global confidence-bin baseline

If even the final fallback is under-sampled, Pine must display `LOW SAMPLE` and suppress the stat as actionable.

### Stop logic — bounded Pine-implementable family

AG does NOT invent a per-trade stop. AG chooses among a **bounded family** of deterministic stop methods that Pine can implement:

1. Fib invalidation (break below the fib level touched)
2. Fib invalidation + ATR buffer
3. Structure breach (break of swing low/high)
4. Fixed ATR multiple from entry

AG's job: evaluate which stop family member works best for which fib level / regime, and output that as a Pine config decision. Not a learned float.

---

## Scope Freeze

This plan is only for the indicator below and its paired validation strategy:

- `AutoFib Structure + Intermarket Alerts`

This plan includes:

- the live indicator
- the paired Pine strategy used for Deep Backtesting
- the offline AG optimization loop that tunes the indicator

This plan does not include:

- dashboards
- FastAPI
- Cloudflare Tunnel
- Supabase as a live decision dependency
- live AG inference
- browser extensions that inject TradingView inputs

---

## Core Architecture

### Live Trading

The live chart runs a Pine **indicator**.

That indicator must:

- calculate all live signal logic inside Pine
- pull all permitted live external series through TradingView-supported `request.*()` calls
- draw the fib structure and entry context on the chart
- render a side-panel table like the reference image
- fire alerts from Pine only

### Validation

The same signal logic must also exist in a Pine **strategy**.

That strategy exists only to:

- run Deep Backtesting
- measure entry quality
- validate that entries can hit 20+ points before stop
- compare parameter sets over long history

### Optimization

AutoGluon is not connected live to the chart.

AutoGluon exists only to:

- rank which settings and features improve entry quality
- identify noisy settings to remove
- suggest tighter parameter ranges
- help choose the next Pine parameter set to test

The live chart never waits on AG.

---

## Non-Negotiable Rules

1. If Pine cannot compute it or request it live from TradingView-supported data, it cannot be part of the live signal.
2. Every live entry must be explainable from Pine-visible state on that bar.
3. No hidden server-side decision engine.
4. No dynamic input injection hacks.
5. The strategy and indicator must share the same core entry predicate.
6. The optimization target is not “looks smart.” It is entry quality:
   - reaches TP1 / TP2 with the `20pt+` eligibility gate satisfied
   - acceptable adverse excursion
   - acceptable signal count

---

## What Must Change In The Current Script

### Required Functional Changes

1. Add explicit **0 fib line**.
2. Add explicit **1 fib line**.
3. Promote the script from a structure/regime overlay into a true **entry engine**.
4. Separate the code into:
   - fib engine
   - intermarket engine
   - macro/credit/volatility engine
   - entry predicate
   - visuals/table
5. Add a side table area on the chart edge modeled after the reference image.
6. Add entry markers that show exactly where the trade is actionable.
7. Add a strict 20-point minimum target gate.

### Required Design Changes

1. Stop treating intermarket as just confirmation color.
2. Turn every external series into a scored feature or explicit gate.
3. Reduce duplicated logic and repeated `request.*()` calls.
4. Build one shared rule block for both the indicator and the strategy.

---

## Forensic Review Of The Current Script

This review exists to carve off weak mechanics before AG training and before Deep Backtesting becomes the validation source.

### Forced Review Standard

This section is not a generic cleanup list. It is a forced **high-reason logic review**.

Every major module must be reviewed:

1. **Before** changes
   - identify what the module is actually doing
   - identify what the module claims to be doing
   - identify where those differ
   - identify whether the current mechanic is valid for live Pine, export, Deep Backtesting, and AG training
2. **During** redesign
   - compare at least two viable replacements when the mechanic is weak
   - choose the simpler mechanic unless the stronger one has a clear material advantage
   - document why the chosen replacement is more trustworthy
3. **After** implementation
   - verify the mechanic is internally coherent
   - verify the mechanic is Pine-reproducible
   - verify the mechanic exports usable data if AG needs it
   - verify the mechanic works identically enough for both indicator and strategy use

No module should move into AG training or Deep Backtesting just because it “looks better.” It must survive a high-reason logic review first.

### High-Risk Problems To Resolve Before AG

1. The intermarket MTF mechanics are not trustworthy yet.
   - `request.security()` is pulling `close` from `tfIM`, but EMA and slope are then computed on the chart timeframe from repeated higher-timeframe values.
   - That distorts `maLen`, `slopeBars`, and the regime logic.
   - Direction:
     - compute EMA, slope, and any regime-state transforms inside the requested timeframe context
     - reduce the intermarket engine to a small set of defensible states first: trend, slope, distance-from-mean, agreement
     - prove the higher-timeframe implementation in Deep Backtesting before letting AG optimize its settings

2. The news proxy mechanics are too weak for v1.
   - The current proxy uses lower-timeframe `request.security()` and then measures lookback on chart bars, not proxy-timeframe bars.
   - It also hard-overrides `riskOn` / `riskOff`, which is too aggressive for a synthetic news proxy.
   - Direction:
     - demote this to a secondary modifier, not a hard regime override
     - prefer deterministic macro-event windows and Pine-supported economic context before synthetic lower-timeframe shock logic
     - only restore a richer macro proxy if it survives a separate reasoning and validation pass

3. Fib direction is too unstable.
   - `fibBull = close >= fibMidpoint` lets direction flip based on current price location inside the range, not on a true swing-leg definition.
   - That can invert base, direction, and targets without a real structural change.
   - Direction:
     - replace midpoint direction with an ordered swing-leg or anchored-leg direction model
     - direction should change only when structural conditions justify a new leg, not when price floats around the midpoint
     - make leg direction a first-class exported state for both strategy and AG dataset building

4. The confluence anchor is not yet a validated continuation anchor.
   - The `8/13/21/34/55` window family is a reasonable candidate search space.
   - But the current chooser is range-based, not explicitly continuation-based.
   - Direction:
     - keep the window family, but test it as a candidate leg-definition surface rather than assuming it is already correct
     - compare the current confluence chooser against at least one more explicit continuation-leg method
     - promote only the anchor logic that produces the cleanest continuation/reversal separation in Deep Backtesting

5. The script has no deterministic trade contract yet.
   - There is no explicit entry price rule.
   - There is no stop family.
   - There is no strict `+20` eligibility gate.
   - Without those, Deep Backtesting cannot prove anything and AG labels like `reached_tp1`, `reached_tp2`, and `outcome` are not well-defined.
   - Direction:
     - define one explicit trade contract for v1: entry trigger, stop family, target path, invalidation rule
     - treat stop logic as a bounded family AG may select from, not an unconstrained learned artifact
     - freeze the `+20` rule as an eligibility gate before dataset labels are generated

6. Core fib/entry data is drawn, not exported.
   - The script currently renders important levels with line objects while the `plot()` calls are `na`.
   - For TradingView export and dataset-building, key levels and states must exist as plotted or otherwise extractable Pine series.
   - Do not rely on visual line objects as the feature-export surface.
   - Direction:
     - promote all key fib levels, state flags, and eligibility states into exportable series
     - separate chart rendering from dataset exposure
     - build the strategy/indicator shared core so export-worthy series are explicit, named, and stable

7. The optimization surface currently includes noise.
   - Visual toggles, colors, widths, lookback draw settings, and line-extension settings are not AG targets.
   - `oneShotEvent` is also not part of the true market model and should not be treated as a core optimization variable.
   - Direction:
     - divide settings into three buckets:
       - AG-searchable market logic
       - Pine-required but non-searchable structural settings
       - visual-only settings
     - only the first bucket belongs in the AG optimization surface

8. The symbol set is not frozen yet.
   - `NQ`, `VIX`, `DXY`, and `US10Y` are reasonable first-pass candidates.
   - `BANK`, credit proxies, oil, and any additional cross-asset series must be verified and justified before they are allowed into the production contract.
   - Direction:
     - start with the smallest defensible live series set
     - add `BANK`, credit, oil, or additional symbols only if holdout and Deep Backtesting evidence show material value
     - do not let AG search a drifting symbol universe

### Keep As Candidate Logic

- confluence-anchor concept
- `8/13/21/34/55` anchor family as a candidate search space
- accept / reject / retest structure archetypes
- weighted intermarket regime concept
- `NQ`, `VIX`, `DXY`, `US10Y` as first-pass context candidates

### Cut Or Demote For v1 Until Proven

- lower-timeframe news proxy as currently written
- hard override of `riskOn` / `riskOff` from the news proxy
- visual/style settings from the AG search space
- `oneShotEvent` from the AG search space
- arbitrary symbol expansion before the live-series inventory is frozen

### Must Be Built Before Deep Backtesting And AG

1. Rebuild intermarket EMA/slope so requested-timeframe logic is computed correctly.
2. Replace midpoint-based fib direction with a true ordered swing-leg direction model.
3. Add explicit `0` and `1` fib lines.
4. Add a deterministic stop family:
   - fib invalidation
   - fib invalidation plus ATR buffer
   - structure breach
5. Add the strict `+20` eligibility gate.
6. Expose key fib and state values as exportable Pine series.
7. Build the paired Pine strategy using the same shared predicate as the indicator.

### Preferred Directional Replacements

When a module is marked weak, prefer these replacements unless a better alternative survives review:

- Intermarket MTF:
  compute state in-request rather than deriving it from repeated requested closes on the chart timeframe
- Macro/news:
  deterministic event windows and Pine-supported macro context before synthetic lower-timeframe shock proxies
- Fib direction:
  anchored leg-direction logic rather than midpoint state flips
- Anchor selection:
  continuation-valid leg selection rather than visually convenient range capture
- Stop logic:
  bounded stop families with explicit invalidation rules rather than vague adaptive stops
- Export surface:
  named series for every AG-relevant state rather than line-object-only visuals
- AG search space:
  market-logic settings only, never visual or presentation settings

### Order Of Operations

1. Run the high-reason logic review on each core module.
2. Harden the mechanics with directional replacements, not ad hoc tweaks.
3. Build the strategy and establish baseline Deep Backtesting behavior.
4. Freeze the surviving feature and setting surface.
5. Export valid feature columns.
6. Let AG optimize only the hardened Pine surface.

### Rule

AG is not allowed to optimize broken mechanics.

If a setting or module is not mechanically trustworthy in Pine first, it does not belong in the AG search space yet.

The bar for promotion is:

- logically coherent
- Pine-valid
- export-valid if AG needs it
- Deep Backtesting-valid
- simple enough to defend

---

## Live Data Boundary

### Pine Can Pull Live

The indicator may use TradingView-supported live pulls such as:

- `request.security()` for market symbols and proxies
- `request.economic()` for supported economic series
- built-in chart OHLCV and any requested symbol OHLCV

### Pine Cannot Pull Live

The indicator cannot depend on:

- arbitrary HTTP APIs
- local files
- Supabase rows
- Python outputs
- custom AG predictions

### Implication

All “advanced” logic must be built from:

- MES price and volume
- requested intermarket symbols
- requested economic series
- Pine-computed derived features

---

## Live Inputs To Build

### A. Fib Structure Engine

Keep and improve:

- confluence anchor selection
- active fib period selection
- structural break re-anchoring
- zone logic

Add:

- `0` line
- `1` line
- explicit distance to 0 / 1 / pivot / zone / target
- target-size eligibility gate for the 20-point requirement

### B. Intermarket Engine

Locked v1 live intermarket series:

- `NQ1!`
- `BANK`
- `VIX`
- `DXY`
- `US10Y`
- `HYG`
- `LQD`

Excluded from v1 unless explicitly reopened by a new decision:

- `RTY1!`
- `YM1!`
- crude
- gold

Use Pine to compute:

- trend state
- slope state
- distance from EMA
- agreement score
- hysteresis state
- flip persistence

### C. Volatility / Credit / Macro Engine

The plan uses only TradingView-available live series.

Locked v1 live macro / credit inputs:

- VIX
- US10Y
- credit proxy = `HYG / LQD`
- `request.economic("US", "IRSTCB01")` for Fed funds
- `request.economic("US", "CPALTT01")` for CPI YoY
- `request.economic("US", "LRHUTTTTUSM156S")` for unemployment
- `request.economic("US", "BSCICP02")` for PMI manufacturing
- Pine calendar logic for `is_fomc_week`, `is_cpi_day`, `is_nfp_day`

Important constraint:

- “Credit” is not assumed to exist as a magical direct feed.
- `VVIX`, `JNK`, GDP growth, and any extra economic fields are v2 candidates, not v1 requirements.

### D. Volume Engine

“Volume of all types” will be interpreted as Pine-available volume state, not fictional order-book access.

Planned volume features:

- chart volume
- relative volume vs rolling baseline
- volume acceleration
- bar spread x volume interaction
- cross-asset volume proxies where the requested symbols expose volume

No unsupported order-book assumptions will be baked into v1.

### E. Session / Market State Engine

Planned live session features:

- regular session / overnight state
- session opening shock window
- lunch/noise window
- time-since-break
- bars-since-zone-touch
- bars-since-regime-flip

---

## Entry System Definition

The entry system is not “any accept/reject event.”

It becomes a scored entry predicate that must answer one question:

**Is this bar an entry worth taking if it passes the `20pt+` eligibility gate and has a credible path to TP1 / TP2?**

### Entry Predicate v1

A valid entry must include:

1. valid fib anchor and non-degenerate range
2. valid 20+ point path to target
3. acceptable structure event
4. acceptable intermarket regime
5. acceptable volatility / credit / macro state
6. acceptable volume state
7. no explicit conflict state

### Structure Event Candidates

The strategy will compare at least these structure archetypes:

- break -> retest -> accept
- rejection from decision zone
- pivot reclaim / pivot loss
- continuation after one clean pullback
- reversal after regime-aligned failed move

### Output States

The indicator should output one clear action state:

- `LONG READY`
- `SHORT READY`
- `NO TRADE`
- `CONFLICT`

---

## Shared Pine Architecture

Two Pine artifacts will exist:

### 1. Validation Strategy

Purpose:

- Deep Backtesting
- historical parameter comparison
- trade outcome measurement

Required outputs:

- entry
- stop
- target 1
- target 2
- trade stats in Strategy Tester

### 2. Live Indicator

Purpose:

- chart visualization
- live entry markers
- side-panel table
- alerts

Required outputs:

- 0 / 1 / pivot / zone / target lines
- entry markers
- stop / target guide lines
- right-side table panel
- alertconditions

### Shared Core

These must be identical between strategy and indicator:

- fib anchor selection
- external series pulls
- feature calculations
- entry predicate
- target eligibility logic

---

## Right-Side Table Plan

The indicator will include a table area on the chart edge inspired by the reference image.

### Table Contents v1

Top block:

- symbol
- timeframe
- active fib period
- direction

Signal block:

- action state
- target eligibility (`20pt+` pass/fail)
- entry price
- stop level
- target 1
- target 2

Regime block:

- intermarket regime
- volatility state
- credit state
- macro posture

Component block:

- NQ
- BANK
- VIX
- DXY
- US10Y
- credit proxy
- volume state

Structure block:

- break / accept / reject / conflict state
- bars since event
- active score

### Visual Direction

The table should feel dense and intentional, not like default Pine debug output:

- compact
- right aligned
- readable at trading size
- color-coded state bars
- minimal wasted text

Arc gauges are optional. The table and state bars are the priority.

---

## AutoGluon Optimization Loop

AG is offline only.

### Training Goal

Optimize for entry quality, not prediction vanity.

Primary labels:

- reached TP1
- reached TP2
- categorical outcome (`TP2_HIT`, `TP1_ONLY`, `STOPPED`, `REVERSAL`, `TIMED_OUT`)
- max favorable excursion
- max adverse excursion

### Optimization Targets

AG should search for settings that improve:

- precision of actionable entries
- stop-before-target reduction
- acceptable signal frequency
- favorable MAE / MFE profile

### Parameter Families To Optimize

Fib engine:

- confluence tolerance
- active period set
- zone ratios
- target ratios
- 20-point eligibility threshold details

Structure logic:

- retest window
- rejection definition

Intermarket:

- timeframe
- EMA length
- slope bars
- neutral band
- scoring model
- weights
- confirm bars
- cooldown

News / macro proxy:

- proxy timeframe
- lookback bars
- shock thresholds
- hold bars

Volume:

- baseline lengths
- shock thresholds
- relative volume gates

### AG Deliverable

AG should output:

- best parameter set
- runner-up parameter sets
- feature importance
- settings to remove because they are noisy
- settings to lock because they are robust across walk-forward windows

AG does not output live trades.

---

## AutoGluon Model Specification

Claude must treat the AG work as an **indicator optimization and entry-quality modeling problem**, not a live inference architecture.

### Training Unit

The base training unit is a **15-minute MES bar** where the indicator has enough context to evaluate a potential entry.

Each row should represent:

- one bar
- one direction (`LONG` or `SHORT`)
- one frozen parameter set
- one fully Pine-reproducible feature snapshot

### Feature Boundary

Claude must only train on features that can be reproduced inside Pine from:

- chart OHLCV
- `request.security()` pulls
- `request.economic()` pulls
- Pine-computed transforms

If a feature cannot be recreated in Pine for live use, it must be excluded from the production feature set even if it improves offline metrics.

### Labels

The AG workflow should model at least these targets:

- `reached_tp1`
- `reached_tp2`
- `outcome`
- `max_favorable_excursion`
- `max_adverse_excursion`
- `bars_to_tp1`
- `bars_to_tp2`

Optional secondary labels:

- `fib_level_touched`
- `session_quality_bucket`

### Parameter Search Space

Claude should treat the indicator inputs as a formal search space, not as ad hoc tweaks.

Minimum search scope:

- fib confluence tolerance
- pivot / zone / target / down-magnet ratios
- retest bars
- rejection mode
- intermarket timeframe
- EMA length
- slope bars
- neutral band
- intermarket scoring weights
- confirmation bars
- cooldown bars
- news proxy timeframe
- shock thresholds
- proxy hold bars
- volume baseline lengths
- volume thresholds

### Model Objective

The AG objective is to maximize **entry quality** under realistic signal frequency.

Primary optimization target:

- strong TP1 / TP2 discrimination and calibration on `20pt+` eligible setups

Primary penalties:

- `STOPPED` and `REVERSAL` outcomes
- excessive signal count
- unstable parameter sets across walk-forward windows

### Validation Protocol

Claude must use time-aware validation only:

- expanding window or walk-forward validation
- no random split
- no shuffled folds

Minimum validation outputs:

- TP1 / TP2 hit-rate quality on high-confidence eligible setups
- TP1 / TP2 calibration quality
- stop-before-target rate
- MAE / MFE distribution
- results by session/regime
- parameter stability across windows

### Selection Rule

The selected production configuration is not the single best in-sample score.

Claude must promote the parameter set that is:

- strong out of sample
- stable across windows
- explainable in Pine
- not dependent on unsupported data
- not overtrading

### Production Handoff From AG

Claude’s AG work must produce a Pine-ready handoff:

- best parameter set
- top 3 runner-up parameter sets
- features to keep
- features to remove
- thresholds/weights to encode in Pine
- notes on which settings are robust versus fragile

Claude must not leave the outcome as “the model knows.” The outcome must be a Pine-implementable ruleset and parameter set.

---

## Claude Handoff Constraints

Claude is allowed to:

- deepen the AG model design
- define the dataset builder logic
- define the label generation logic
- define the parameter search and walk-forward protocol
- tighten the indicator’s live feature inventory

Claude is not allowed to:

- reintroduce dashboards
- reintroduce FastAPI / Cloudflare / webhook return loops
- assume Pine can consume custom HTTP responses
- introduce non-Pine live dependencies
- drift this plan into a different product

Claude’s job is to finish the AG model concept **for this indicator only**.

---

## Claude Execution Brief

Claude must review this plan as the single active architecture document and then complete the AG concept around one narrow objective:

- optimize this indicator for the highest-quality MES entry signals that can realistically reach `+20` points before stop

Claude must treat that as an **entry-ranking and parameter-optimization problem**, not as a generic forecasting project and not as a live model-serving project.

### Required Claude Deliverables

Claude must add or tighten the following inside this plan and any directly supporting implementation docs/scripts:

1. a formal dataset-builder design for this indicator
2. exact label definitions and horizon rules for the `+20 before stop` objective
3. a search-space definition for every indicator setting worth tuning
4. the AG training and validation protocol
5. the model-selection rule for promoting one Pine-ready configuration
6. the final Pine handoff format:
   - parameter values
   - feature keep/remove calls
   - thresholds
   - scoring weights
   - notes on fragile vs robust settings

### Required Claude Reasoning Standard

Claude must use deep reasoning and explicitly stress-test:

- long vs short symmetry
- session dependence
- regime dependence
- whether one global parameter set is weaker than regime-specific parameter sets
- whether any candidate feature improves metrics but fails the Pine live-data rule
- whether a higher-scoring configuration is too unstable to promote

### Required Claude Boundary

Claude may design:

- offline training pipelines
- dataset builders
- labeling rules
- AG experiments
- Pine-implementable outputs

Claude may not design:

- live inference servers
- dashboard sync loops
- browser automation for TradingView inputs
- non-Pine live dependencies
- any architecture outside this indicator and its paired validation strategy

---

## AG Work Product

The AG work is complete only when it can hand Pine a production-ready optimization packet.

### Minimum Optimization Packet

The output packet must contain:

- selected production parameter set
- top 3 alternates with why they lost
- selected feature inventory
- rejected feature inventory with reason for rejection
- best-performing long configuration
- best-performing short configuration
- recommendation on unified vs split long/short settings
- walk-forward summary table
- session/regime breakdown
- Pine implementation notes

### Promotion Rule

No configuration gets promoted just because it wins one metric.

The promoted configuration must satisfy all of these:

1. strong out-of-sample TP1 / TP2 quality on `20pt+` eligible setups
2. acceptable stop-before-target rate
3. acceptable weekly signal count
4. stability across walk-forward windows
5. full reproducibility in Pine with live TradingView-accessible data

### Failure Rule

If AG cannot find a stable configuration that materially improves entry quality, the outcome must say so plainly.

Do not fake confidence, do not hide instability, and do not force a Pine handoff from a weak model.

---

## Build Phases

### Phase 1: Series Inventory Freeze

1. Inventory every live series the indicator wants.
2. Verify exact TradingView ticker or economic-series availability.
3. Freeze the initial v1 external series list.
4. Eliminate any data source Pine cannot request reliably.

### Phase 2: Refactor The Current Script

1. Add 0 and 1 fib lines.
2. Isolate fib calculations.
3. Isolate intermarket calculations.
4. Add volatility / credit / macro modules.
5. Add volume-state module.
6. Create one explicit entry predicate.

### Phase 3: Strategy Build

1. Port the shared logic into a Pine strategy.
2. Implement stop / target mechanics.
3. Add 20-point minimum target gate.
4. Run Deep Backtesting over the longest reliable MES history.

### Phase 4: Dataset + AG Loop

1. Export chart data with the final feature columns.
2. Build labels tied to TP1 / TP2 / outcome, with `20pt+` used as an eligibility gate.
3. Train AG on settings and feature robustness.
4. Select the best candidate rule set.

### Phase 5: Indicator UI Build

1. Build the right-side table.
2. Add entry markers and level lines.
3. Add concise alertconditions.
4. Ensure the indicator remains within Pine limits.

### Phase 6: Walk-Forward Validation

1. Re-test the candidate settings out of sample.
2. Compare against prior settings.
3. Promote only if entry-quality metrics improve.

---

## Success Metrics

The indicator is successful only if it improves entry quality on the chart.

Primary metrics:

- percent of eligible signals that reach TP1
- percent of eligible signals that reach TP2
- stop-before-target rate
- average MAE before TP1
- average time to TP1
- signal count per week

Secondary metrics:

- percent of signals filtered out versus baseline
- expectancy improvement versus baseline
- regime-specific performance consistency

---

## Open Research Items

These are non-blocking v2 questions, not blockers for v1:

1. Whether `RTY1!` or `YM1!` add material value beyond the locked v1 basket.
2. Whether `VVIX`, `JNK`, crude, or gold add enough value to justify request-budget expansion.
3. Whether one unified model works best, or whether separate long and short parameter sets are required.
4. Whether a compact gauge improves table usability over bar-state rows after v1 is visually complete.

---

## AG Model Concept — Locked Specification

### Status: LOCKED (2026-03-20, revised)

AG is a **fib continuation probability engine** that models both the market AND the Pine indicator's configuration space. AG trains on thousands of historical fib pullbacks with full market context — macro events (CPI, FOMC, GDP, NFP), intermarket state, indicators, volatility — and outputs the probability of hitting the 1.236 and 1.618 fib extensions. AG also learns when a pullback is actually a reversal.

**Critical framing:** AutoGluon must treat the Pine indicator as the production surface and the Pine input space as the optimization surface. Every AG conclusion must terminate in a Pine-implementable setting, threshold, weight, gate, or rule selection. If AG produces an insight that cannot be expressed through Pine inputs, Pine logic, Pine-requestable data, or Pine-rendered outputs, that insight is not production-ready and cannot be promoted.

AG is offline only. Pine owns the live signal. AG teaches Pine what it learned.

---

### 1. AG Models Pine's Configuration Space

AG is not just modeling the market. AG is modeling the Pine indicator configuration space.

AG must understand:

- Every Pine input in the indicator
- What each setting changes in the live logic
- Which settings interact with each other
- Which outputs Pine can actually render, alert on, and calculate live

The AG output is NOT "here's a smart model" or "here's a probability blob." The AG output must be **Pine-native**:

- Exact input values (e.g., `tfIM = 60`, `retestBars = 4`)
- Exact thresholds (e.g., `neutralBandPct = 0.08`)
- Exact weights for scoring
- Exact on/off feature decisions (e.g., `useIntermarket = true`, `creditFilter = shorts_only`)
- Exact rule/gate selections (e.g., `rejectWick = false`)
- Exact stop/target family selection
- Exact long/short split decision if needed

AG helps answer not just entry/targets but also:

- What the indicator must expose as inputs
- What states it must calculate
- What filters it must support
- What table outputs it must show
- What alerts it must fire
- Which modules are worth keeping versus dead weight

**Pine indicator = production interface. AG = optimizer for that interface.**

Before AG is fully useful, the indicator needs a defined contract:

- Inputs (all tunable parameters)
- Internal computed states
- Output states (LONG READY, SHORT READY, NO TRADE, CONFLICT)
- Alerts
- Visualization / table fields

Then AG can output things like:

- `useIntermarket = true` should stay
- `tfIM = 60` outperforms 15 and 240
- `neutralBandPct` should be 0.08
- VIX and DXY are useful, BANK is weak in holdout
- `retestBars = 4` is robust
- `rejectWick = false` is better than `true`
- news proxy hold = 8 bars
- credit filter improves shorts only
- re-entry mode adds noise, remove from v1
- the table must show: action state, target eligibility, regime, conflict, stop family, TP1/TP2 path

---

### 2. Dataset Builder Design

#### Data Source

Training data comes from **two sources**:

1. **Supabase DB** — 2-year historical data: MES 15m OHLCV, cross-asset prices, FRED economic series (all 10 tables), GPR index, Trump Effect, news signals, economic calendar
2. **TradingView CSV exports** — indicator-specific columns (MACD, RSI, Heikin Ashi, etc.) that map to the exact indicators on Kirk's chart

For indicators present on the TradingView chart but not yet in our dataset, we **create the missing indicator in Pine Script first** (using Pine tools and skills), **test it**, then add its output to the training dataset alongside the rest of the data.

The dataset builder must:

1. Pull base OHLCV + cross-asset + macro data from Supabase (2-year window)
2. Ingest TradingView CSV exports for indicator columns
3. Create and test any missing Pine indicators needed for features
4. Identify every fib pullback event in the history
5. Compute all features at each pullback
6. Generate forward-looking labels (TP1/TP2 hit, reversal, stop, pullback depth)
7. Output a single CSV ready for AG training

#### Locked Dataset Alignment Contract

The dataset builder must obey these alignment rules:

1. **Canonical timezone**
   - all timestamps normalize to `America/Chicago`
2. **Canonical bar key**
   - every training row is keyed by the MES 15m **bar close timestamp**
3. **TradingView CSV join**
   - TradingView exports must be normalized to the same MES 15m bar-close timestamp
   - if a CSV row cannot be matched exactly after timezone normalization, it is rejected and logged
4. **Cross-asset join**
   - cross-asset series are joined **as-of bar close**
   - only the most recent value available at or before the MES bar close may be used
5. **Economic / macro join**
   - no economic value may appear in the dataset before its release-effective timestamp
   - if a release timestamp is unknown, that field cannot be used as a Tier 1 production feature
   - unknown-timestamp macro fields remain Tier 2 research-only
6. **Session tagging**
   - `session_bucket` and RTH/ETH state are assigned from the MES bar timestamp before feature merges
7. **No lookahead**
   - every feature must be available as of the current MES bar close
   - future daily values, same-day unreleased macro values, and revised values from the future are forbidden
8. **Missing-value rule**
   - rows missing critical Tier 1 fields are dropped and counted
   - the dataset builder must log dropped-row counts by reason
9. **Leakage check**
   - the builder must run a final leakage audit confirming that no joined feature timestamp exceeds the MES row timestamp

#### Feature Boundary — Two Tiers

**Tier 1: Pine-Live Features** — computable in Pine from chart OHLCV, `request.security()`, `request.economic()`, or Pine transforms. These drive the live indicator signal.

**Tier 2: Research-Only Context** — macro event data (FRED, GPR, Trump Effect, news signals) that AG uses to discover regime patterns and validate hypotheses. Tier 2 data does NOT produce production features directly. If AG discovers a Tier 2 insight (e.g., "CPI day pullbacks fail more often"), it can only become production-ready if there is an **exact Pine analogue** — either via `request.economic()`, Pine calendar logic, or a Tier 1 proxy that AG can prove correlates (e.g., VIX spike on CPI day). If no Pine analogue exists, the insight stays in the research report but does NOT enter the Pine indicator.

**Rule:** AG trains on everything available. But only Tier 1 features can become production features. Tier 2 insights must pass through a Pine-analogue gate before they influence the live indicator.

#### Pine-Reproducible Feature Set

**A. Fib Structure Features** (from chart OHLCV)

| Feature | Pine Source | Description |
|---------|------------|-------------|
| `fib_anchor_high` | chart OHLCV | Multi-period confluence anchor high |
| `fib_anchor_low` | chart OHLCV | Multi-period confluence anchor low |
| `fib_range` | derived | `anchor_high - anchor_low` |
| `fib_retrace_ratio` | derived | Deepest retrace level reached (0.236–0.786) |
| `dist_to_fib_0` | derived | Points from close to 0-level |
| `dist_to_fib_1` | derived | Points from close to 1-level |
| `dist_to_nearest_zone` | derived | Points from close to nearest zone level |
| `target_distance_pts` | derived | Distance from entry to TP1 in points |
| `target_eligible_20pt` | derived | Boolean: target path ≥ 20 points |
| `fib_range_atr_ratio` | derived | `fib_range / ATR(14)` — quality filter |

**B. Intermarket Features** (from `request.security()`)

| Feature | Pine Source | Description |
|---------|------------|-------------|
| `nq_trend` | `request.security("NQ1!")` | NQ EMA slope state: -1/0/1 |
| `nq_dist_ema` | `request.security("NQ1!")` | NQ distance from EMA(20) as % |
| `vix_level` | `request.security("CBOE:VIX")` | VIX close |
| `vix_sma_ratio` | derived | `VIX / SMA(VIX, 20)` |
| `dxy_trend` | `request.security("DXY")` | DXY EMA slope state: -1/0/1 |
| `us10y_level` | `request.security("TVC:US10Y")` | 10Y yield |
| `us10y_delta` | derived | 10Y yield change over 5 bars |
| `bank_trend` | `request.security("NASDAQ:BANK")` | Bank index slope state |
| `hyg_lqd_ratio` | `request.security("AMEX:HYG")` / `request.security("AMEX:LQD")` | Credit risk proxy |
| `intermarket_agreement` | derived | Count of aligned trend states / total |

**C. Volatility Features** (from chart OHLCV + `request.security()`)

| Feature | Pine Source | Description |
|---------|------------|-------------|
| `atr_14` | chart OHLCV | ATR(14) on 15m |
| `atr_ratio_5_20` | derived | `ATR(5) / ATR(20)` — volatility expansion/contraction |
| `realized_vol_20` | derived | 20-bar realized volatility |
| `vix_regime` | derived | Low/Normal/High/Extreme (quartile buckets) |

**C2. Economic / Macro Features** (from `request.economic()` + Supabase for training)

| Feature | Pine Source | Description |
|---------|------------|-------------|
| `fed_funds_rate` | `request.economic("US", "IRSTCB01")` | Current Fed funds rate |
| `cpi_yoy` | `request.economic("US", "CPALTT01")` | CPI year-over-year |
| `gdp_growth` | `request.economic("US", "NAEXKP01")` | GDP growth rate |
| `unemployment` | `request.economic("US", "LRHUTTTTUSM156S")` | Unemployment rate |
| `pmi_manufacturing` | `request.economic("US", "BSCICP02")` | PMI manufacturing |
| `is_fomc_week` | Pine calendar logic | Boolean: is this FOMC week? |
| `is_cpi_day` | Pine calendar logic | Boolean: is CPI releasing today? |
| `is_nfp_day` | Pine calendar logic | Boolean: is Non-Farm Payroll today? |
| `bars_since_major_release` | derived | Bars since last major economic release |

AG trains on the FULL economic context from all 10 Supabase FRED tables + GPR + Trump Effect + news signals. What Pine gets is the distilled version: `request.economic()` for live levels, plus calendar-based event windows that AG learned are significant. Example: AG discovers "CPI day pullbacks to 0.5 have 25% lower TP1 rate before 10am ET" → Pine encodes `is_cpi_day AND hour < 10 → reduce confidence`.

**Research-Only Macro Context (Tier 2 — AG uses for discovery, NOT direct production features)**

| Feature | Source | Pine Analogue (required for promotion) |
|---------|--------|---------------------------------------|
| Full FRED series (all 10 tables) | Supabase `econ_*_1d` | Must find exact `request.economic()` equivalent OR prove a Tier 1 proxy (e.g., US10Y, VIX) captures the same signal |
| GPR geopolitical risk index | Supabase `geopolitical_risk_1d` | Must prove VIX + intermarket captures the same signal, OR stays research-only |
| Trump Effect / policy uncertainty | Supabase `trump_effect_1d` | Must prove a Pine time/calendar analogue exists, OR stays research-only |
| News signal counts by segment | Supabase `news_signals` | Must prove time-of-day + volatility proxy captures the same effect, OR stays research-only |
| Economic calendar events | Supabase + user-maintained | Pine calendar logic (`is_fomc_week`, `is_cpi_day`) IF AG proves these events materially change outcomes |

**Promotion gate:** A Tier 2 insight only enters Pine if there is an exact Pine analogue that AG can prove correlates. "AG discovered it matters" is not enough — "AG proved Pine feature X captures the same signal" is required.

#### Locked Pine request budget

The v1 indicator must stay under this request budget:

- target operating budget: `<= 12` unique `request.*()` calls
- hard ceiling: `<= 16` unique `request.*()` calls

Planned v1 usage:

- `request.security()`:
  - `NQ1!`
  - `BANK`
  - `VIX`
  - `DXY`
  - `US10Y`
  - `HYG`
  - `LQD`
- `request.economic()`:
  - `IRSTCB01`
  - `CPALTT01`
  - `LRHUTTTTUSM156S`
  - `BSCICP02`

This yields a planned base budget of `11` unique `request.*()` calls, leaving limited room for future additions.

**D. Volume Features** (from chart OHLCV)

| Feature | Pine Source | Description |
|---------|------------|-------------|
| `volume` | chart | Raw bar volume |
| `vol_sma_20` | derived | 20-bar volume SMA |
| `vol_ratio` | derived | `volume / vol_sma_20` |
| `vol_acceleration` | derived | `vol_ratio - vol_ratio[1]` |
| `bar_spread_x_vol` | derived | `(high - low) * volume` — effort vs result |

**E. Session / Market State Features** (from Pine time functions)

| Feature | Pine Source | Description |
|---------|------------|-------------|
| `session_state` | `syminfo.session` | RTH=1, ETH=0 |
| `hour_utc` | `hour(time, "UTC")` | Hour of day (0-23) |
| `minutes_since_rth_open` | derived | Minutes since 09:30 ET |
| `is_opening_30min` | derived | Boolean: within first 30min of RTH |
| `is_lunch_noise` | derived | Boolean: 11:30-13:00 ET |
| `day_of_week` | `dayofweek` | 1-7 |
| `bars_since_structure_break` | derived | Bars since last pivot break |

**F. Oscillator / TA Features** (from Pine built-ins)

| Feature | Pine Source | Description |
|---------|------------|-------------|
| `rsi_8` | `ta.rsi(close, 8)` | RSI with Kirk's length |
| `rsi_14` | `ta.rsi(close, 14)` | Standard RSI |
| `stoch_k` | `ta.stoch(close, high, low, 14)` | Stochastic %K |
| `macd_hist` | derived | MACD(8,17,9) histogram |
| `squeeze_on` | derived | BB inside KC boolean |
| `squeeze_momentum` | derived | Squeeze momentum value |
| `ema_9_slope` | derived | EMA(9) slope over 3 bars |
| `price_vs_ema_20` | derived | `(close - EMA(20)) / ATR(14)` |
| `price_vs_sma_50` | derived | `(close - SMA(50)) / ATR(14)` |

**Total production features: ~40**

#### Feature Delivery to Pine

**Nothing is rejected from AG training.** AG trains on everything. The question is only how Pine consumes each feature:

| Feature Category | AG Trains On | Pine Receives As |
|-----------------|-------------|-----------------|
| FRED economic series (all 10 tables) | Full daily values from Supabase | `request.economic()` for key levels + calendar rules AG learned |
| GPR geopolitical risk | Daily index from Supabase | VIX + intermarket proxy (AG identifies which proxies correlate) |
| Trump Effect / policy uncertainty | Daily index from Supabase | Calendar event windows + VIX regime |
| News sentiment counts by segment | Hourly counts from Supabase | Time-of-day volatility rules AG learned |
| Order book depth | Not available for training either | Not applicable |
| Cross-asset volume | Unreliable on continuous contracts | Excluded from Pine — AG uses for research only |

---

### 3. Training Unit Definition

Each training row represents **one fib pullback event**:

- **One 15-minute bar** where price touched or crossed a fib level during a trend
- **One direction** (LONG or SHORT, from trend context)
- **One fib level touched** (0.236, 0.382, 0.5, 0.618, 0.786)
- **One frozen Pine indicator parameter set** (every indicator input fixed for that training run — AG treats the Pine input space as the optimization surface)
- **One full feature snapshot** (Tier 1 Pine-live features + Tier 2 macro context from Supabase)

#### What Constitutes a Fib Pullback Event

A row is generated when:

1. A valid fib anchor exists (non-degenerate range ≥ 10 points)
2. Price is in a trend (higher highs/lows for LONG, lower highs/lows for SHORT)
3. Price pulls back and touches or crosses a fib level on this bar
4. The 1.236 extension is ≥ 20 points away (minimum viable trade filter)
5. Sufficient lookback data exists for all features (≥ 50 prior bars)

Not every bar is a training row. Only bars where a fib pullback event occurs.

#### Reversal Rows

AG also trains on failed continuations / reversals — price broke through the fib level, structure died, conditions shifted. These rows have `outcome = REVERSAL` and teach AG when NOT to signal. AG learns the difference between "healthy pullback to 0.382 before continuation" and "0.618 break where VIX spiked, yields moved, NQ diverged — trend is dead."

---

### 4. Label Definitions

All labels are computed from future price action. Targets are the 1.236 and 1.618 fib extensions (dynamic). Stop is determined by a **bounded family** of deterministic methods (see Locked v1 Mechanisms) — AG chooses which family member works best, not an unconstrained learned distance.

#### Primary Labels

| Label | Type | Definition |
|-------|------|------------|
| `reached_tp1` | binary | Price reached the 1.236 fib extension in trade direction within horizon |
| `reached_tp2` | binary | Price reached the 1.618 fib extension in trade direction within horizon |
| `outcome` | categorical | `TP2_HIT`, `TP1_ONLY`, `STOPPED`, `REVERSAL`, `TIMED_OUT` |

#### Outcome Logic

For LONG on bar `i` with entry = close[i]:

```
tp1_price = anchor_low + fib_range * 1.236
tp2_price = anchor_low + fib_range * 1.618
fib_level_price = price at the fib level touched

for each future bar j in [i+1, i+1+max_horizon]:
    track max_favorable_excursion
    track max_adverse_excursion
    track pullback_depth (entry - lowest low before TP1)

    if high[j] >= tp2_price: outcome = TP2_HIT, break
    if high[j] >= tp1_price: mark tp1 hit

    # Stop = bounded family member (fib invalidation, fib+ATR, structure breach, or fixed ATR)
    if low[j] < stop_price:  # stop_price from the selected stop family member
        if structure also broken: outcome = REVERSAL
        else: outcome = STOPPED
        break

if timed out:
    if tp1 hit: outcome = TP1_ONLY
    else: outcome = TIMED_OUT
```

Maximum horizon: 40 bars (10 hours of 15m bars).

Stopped trades get **higher penalty weight** during training (weight = 2.0) so AG learns what causes failures. Timed-out trades get weight 0.5 (ambiguous).

#### Secondary Labels

| Label | Type | Definition |
|-------|------|------------|
| `fib_level_touched` | categorical | Which fib level (0.236/0.382/0.5/0.618/0.786) |
| `max_favorable_excursion` | float | Max points in trade direction within horizon |
| `max_adverse_excursion` | float | Max points against trade direction |
| `pullback_depth_from_entry` | float | Deepest pullback before TP1 — used to evaluate which stop family member would have been optimal (not a live model output) |
| `stop_family_best` | categorical | Which bounded stop method (fib_invalidation / fib_atr / structure_breach / fixed_atr) would have avoided the stop while staying tight |
| `bars_to_tp1` | int or NaN | Bars to reach 1.236 extension |
| `bars_to_tp2` | int or NaN | Bars to reach 1.618 extension |
| `session_at_entry` | categorical | RTH / ETH |
| `had_reentry_opportunity` | binary | After TP1, did price pull back ≥ 5 pts before TP2? |
| `macro_event_active` | binary | Was a major economic release within ±2 hours? |

---

### 5. Parameter Search Space

AG treats the Pine indicator's input schema as the optimization surface. Every parameter below must map directly to a Pine `input.*()` declaration in the actual hardened indicator.

**IMPORTANT:** The parameter families below are a **candidate starting point**. After the Forensic Review items are fixed and the indicator is hardened (Phase 2), the search space MUST be rebuilt from the actual indicator's `input.*()` declarations. Parameters like `tfIM`, `requireAnchors`, explicit intermarket weights, `vixMaxRiskOn`, `use10YConfirm`, and the current proxy settings from the existing script must be included if they survive hardening. Parameters that do not exist in the hardened indicator's input schema must be removed.

#### Approach

1. Map every `input.*()` in the hardened Pine indicator → that is the search space
2. Define 20-50 discrete configurations (Latin hypercube sampling over the actual inputs)
3. For each, build the dataset with those Pine inputs frozen
4. Train AG on `reached_tp1` and `reached_tp2` for each
5. Compare out-of-sample calibration and discrimination
6. Promote the best — output is exact Pine input values

#### Parameter Families

**Fib Engine:**

| Parameter | Range | Step | Default |
|-----------|-------|------|---------|
| `confluence_tolerance_pct` | 0.5%–3.0% | 0.5% | 1.5% |
| `anchor_periods` | [21,34,55], [34,55,89], [21,55,89] | discrete | [21,34,55] |
| `zone_width_atr_mult` | 0.3–1.0 | 0.1 | 0.5 |
| `min_range_pts` | 10, 15, 20 | discrete | 10 |

**Structure Logic:**

| Parameter | Range | Step | Default |
|-----------|-------|------|---------|
| `retest_window_bars` | 3–10 | 1 | 5 |
| `rejection_mode` | wick_ratio, close_beyond, both | discrete | both |

**Intermarket Engine:**

| Parameter | Range | Step | Default |
|-----------|-------|------|---------|
| `im_ema_length` | 10, 15, 20, 30 | discrete | 20 |
| `im_slope_bars` | 3, 5, 8 | discrete | 5 |
| `im_neutral_band_pct` | 0.05%, 0.1%, 0.2% | discrete | 0.1% |
| `im_min_agreement` | 2, 3, 4 (out of 6 markets) | discrete | 3 |
| `im_confirm_bars` | 1, 2, 3 | discrete | 2 |
| `im_cooldown_bars` | 0, 2, 4 | discrete | 2 |

**Volume Engine:**

| Parameter | Range | Step | Default |
|-----------|-------|------|---------|
| `vol_baseline_bars` | 10, 20, 30 | discrete | 20 |
| `vol_spike_threshold` | 1.3, 1.5, 2.0 | discrete | 1.5 |
| `vol_gate_enabled` | true, false | discrete | true |

**Session / State:**

| Parameter | Range | Step | Default |
|-----------|-------|------|---------|
| `block_opening_minutes` | 0, 15, 30 | discrete | 15 |
| `block_lunch_window` | true, false | discrete | true |
| `eth_allowed` | true, false | discrete | true |

**Target: ~25 parameter combinations for the initial grid** (Latin hypercube sampling from the full space, not exhaustive Cartesian product).

---

### 6. Unified vs Split Configuration Decision

Default: start unified with `direction` as a feature. AG decides whether direction matters for probability estimates. Split into separate LONG/SHORT Pine configs only if directional probability accuracy diverges > 10pp out-of-sample. AG's output on this is a concrete Pine recommendation: either one parameter set for both, or two sets with a direction switch.

---

### 7. AG Training Protocol

#### Model Type: Multi-Output Probability + Stop Distance

AG trains two probability models and evaluates stop families:

1. **TP1 model**: `reached_tp1` → calibrated probability of hitting 1.236 extension → used to validate Pine's deterministic confidence score
2. **TP2 model**: `reached_tp2` → calibrated probability of hitting 1.618 extension → same validation purpose
3. **Stop family evaluation**: AG compares the bounded stop family members (fib invalidation, fib+ATR, structure breach, fixed ATR) across fib levels and regimes → outputs which family member to use as a Pine config decision

All probability models use `predict_proba()` for calibrated output.

#### AutoGluon Configuration

```python
tp1_predictor = TabularPredictor(
    label="reached_tp1",
    problem_type="binary",
    eval_metric="log_loss",           # calibrated probabilities
    path=output_dir / "tp1",
)

tp1_predictor.fit(
    train_data=train_df,
    tuning_data=val_df,
    time_limit=7200,
    presets="best_quality",
    num_bag_folds=5,
    num_stack_levels=2,
    excluded_model_types=["KNN", "FASTAI"],
    ag_args_fit={"num_cpus": 10, "num_early_stopping_rounds": 50},
)
# Same config for TP2 model
# Stop family evaluation: compare outcomes across the 4 bounded stop methods per fib level/regime
```

#### Why Log Loss

AG uses log_loss so its offline probability estimates are calibrated. This calibration is used to **validate** that Pine's deterministic confidence scores map to real-world hit rates. Pine does NOT call `predict_proba()` live. Pine computes a deterministic score from its features; AG's offline calibration proves what that score means in terms of real probability. The mechanism for getting probability onto the chart is the locked v1 path defined in Locked v1 Mechanisms above.

---

### 8. Walk-Forward Validation Protocol

Expanding window with purge + embargo (Lopez de Prado):

- **Min training**: 3 months (~6,000 bars) | **Validation**: 1 month (~2,000 bars)
- **Purge**: 40 bars | **Embargo**: 80 bars | **Folds**: 5 expanding windows

#### Per-Fold Metrics

- TP1/TP2 offline probability calibration (validates Pine's deterministic confidence score)
- TP1/TP2 AUC-ROC (discrimination power)
- Stop rate by stop family member (which family member performs best per fib level?)
- Signals per week at various confidence thresholds
- Feature importance (top 10 — which Pine features matter most?)
- Performance by fib level touched (does 0.618 behave differently than 0.382?)
- Performance by session (RTH vs ETH) and direction (LONG vs SHORT)
- Performance during macro event windows vs quiet periods (Tier 2 research insight)
- Which Pine modules contributed vs were dead weight

#### Stability: AUC > 0.60 every fold, calibration error < 10%

---

### 9. Feature Selection Protocol

Per-fold on training data: IC ranking → cluster dedup → 15-25 features.
Cross-fold: features in ≥ 4/5 folds = robust (keep in Pine). < 2/5 = fragile (remove from Pine).

AG also reports which Pine indicator modules are worth keeping vs dead weight. This directly maps to Pine: "remove this module" or "keep this module with these settings."

---

### 10. Promotion Rule

| Metric | Threshold |
|--------|-----------|
| Mean OOS TP1 AUC-ROC | ≥ 0.65 |
| Mean OOS TP2 AUC-ROC | ≥ 0.60 |
| TP1 calibration error | ≤ 10% |
| Worst fold TP1 AUC | ≥ 0.55 |
| Stop rate on high-confidence calls | ≤ 30% |
| High-confidence signals per week | 3–25 |
| AUC stability across folds | ≤ 0.15 |

Pine reproducibility gate: every feature computable in Pine v6 with ≤ 40 `request.security()` + `request.economic()` calls total.

**The promoted output is a Pine config packet** — exact input values, exact thresholds, exact weights, exact on/off decisions, exact rule/gate selections. Not a model blob. Not a notebook conclusion.

---

### 11. Failure Rule

If no configuration meets thresholds: report honestly, identify failure mode, deliver failure packet with same format but marked FAILED. Do not force a promotion. Do not hide instability.

---

### 12. Pine-Ready Optimization Packet Format

The AG work product plugs directly into Pine's input schema and rule schema.

```
WARBIRD AG OPTIMIZATION PACKET
================================
Status: PROMOTED | FAILED
Model: Fib continuation probability engine
Training Data:
- date range
- pullback event count
- MES bar count
- sample counts by bucket depth
- packet generated at timestamp

PINE INPUT VALUES (exact — plug directly into indicator)
----------------------------------
confluence_tolerance_pct: X.X%
anchor_periods: [A, B, C]
zone_width_atr_mult: X.X
min_range_pts: XX
retest_window_bars: X
rejection_mode: [mode]
im_ema_length: XX
im_slope_bars: X
im_neutral_band_pct: X.X%
im_min_agreement: X
im_confirm_bars: X
im_cooldown_bars: X
vol_baseline_bars: XX
vol_spike_threshold: X.X
vol_gate_enabled: [bool]
block_opening_minutes: XX
block_lunch_window: [bool]
eth_allowed: [bool]
[every surviving Pine input with its optimized value]

MODULE KEEP/REMOVE DECISIONS
----------------------------------
useIntermarket: [true/false] — [reason]
useNewsProxy: [true/false] — [reason]
useCreditFilter: [true/false/shorts_only] — [reason]
useReentryMode: [true/false] — [reason]
[every surviving module with AG's recommendation]

TP1/TP2 HIT RATES BY FIB LEVEL
----------------------------------
0.236: TP1=XX%, TP2=XX% (N obs)
0.382: TP1=XX%, TP2=XX%
0.5:   TP1=XX%, TP2=XX%
0.618: TP1=XX%, TP2=XX%
0.786: TP1=XX%, TP2=XX%

STOP FAMILY SELECTION (Pine-implementable, bounded)
----------------------------------
- per fib level: selected stop family member (`fib_invalidation` / `fib_atr` / `structure` / `fixed_atr`)
- per regime: any regime-specific stop-family overrides

MACRO EVENT RESEARCH (Tier 2 — only promoted if Pine analogue proven)
----------------------------------
- CPI day: TP1 delta, TP2 delta, reversal delta, Pine analogue status
- FOMC week: TP1 delta, TP2 delta, reversal delta, Pine analogue status
- NFP day: TP1 delta, TP2 delta, reversal delta, Pine analogue status
- every other promoted macro insight with Pine analogue status

CONFIDENCE SCORE CALIBRATION (maps Pine's deterministic score to real probability)
----------------------------------
- `BIN_1` through `BIN_5` calibration table for TP1 / TP2 / reversal
- reversal-warning threshold and suppression rules

RE-ENTRY CONDITIONS
----------------------------------
- explicit re-entry rule by setup archetype / regime

WALK-FORWARD SUMMARY
----------------------------------
| Fold | TP1 AUC | TP2 AUC | Cal | Stop% | Signals/wk |
|------|---------|---------|-----|-------|------------|

BREAKDOWN
----------------------------------
By fib level / session bucket / direction / regime bucket / macro event

PINE IMPLEMENTATION NOTES
----------------------------------
- total `request.security()` + `request.economic()` calls used vs v1 budget
- exact Pine functions/modules required for packet compatibility
- table fields required: action, TP1 probability, TP2 probability, reversal risk, win rate, stats window, regime, conflict, stop family, TP1/TP2 path
- alerts required: entry, re-entry, reversal warning, TP1 hit, TP2 hit
```

---

### 13. Implementation Files

| File | Purpose |
|------|---------|
| `scripts/ag/build-fib-dataset.py` | Find all fib pullback events, compute features (Tier 1 + Tier 2 from Supabase), generate labels |
| `scripts/ag/train-fib-model.py` | TP1/TP2 probability models + stop-family evaluation with walk-forward CV |
| `scripts/ag/evaluate-configs.py` | Parameter grid evaluation — each config maps to a Pine input set |
| `scripts/ag/generate-packet.py` | Generate Pine-ready optimization packet with exact input values |

Existing files (`build-dataset.py`, `train-warbird.py`, `fib-engine.ts`, `trigger-15m.ts`) are reference only — different model architecture.

---

### 14. Training Data Assessment

#### Available Data

- **Supabase DB**: 2-year MES 15m OHLCV, cross-asset 1H, 10 FRED economic tables, GPR, Trump Effect, news signals
- **TradingView CSV exports**: 9 files (~5,593 rows), includes OHLC + indicator columns (MACD, RSI, Heikin Ashi, etc.)
- **Missing indicators**: Any indicator on Kirk's chart not yet in the CSV must be created in Pine first, tested, then exported

#### Data Sufficiency

- Supabase has 2 years of base OHLCV + macro data — sufficient for AG training
- TradingView CSV has limited indicator-specific columns — need longer export for full indicator feature coverage
- For 5-fold walk-forward: need 12+ months of indicator-enriched data
- Missing indicators must be built in Pine (using Pine tools/skills), validated, then added to exports

#### Next Action

Export 12+ months of MES 15m data from TradingView with all current indicators loaded. For any indicators not yet on the chart or not exporting cleanly, create them in Pine Script first, test them, then add to the chart for export.

---

### 15. Immediate Next Steps

1. **Map the current Pine indicator's input schema** — every `input.*()`, every module, every gate, every dependency
2. **Harden the Pine indicator mechanics** per the Forensic Review (fix intermarket MTF, fib direction, add 0/1 lines, add stop family, add +20 gate, expose series for export)
3. **Create any missing Pine indicators** needed for features (using Pine tools/skills), test them
4. **Export 12+ months of MES 15m data from TradingView** with all indicators loaded
5. **Verify the locked v1 live series inventory** resolves exactly in TradingView
6. **Build `scripts/ag/build-fib-dataset.py`** — Supabase 2-year data + TradingView indicator columns
7. **Build `scripts/ag/train-fib-model.py`** — TP1/TP2 probability models + stop-family evaluation
8. **Run AG on default config** → evaluate
9. **Run parameter grid** → find best Pine config
10. **Generate optimization packet** → exact Pine input values, module decisions, macro rules
11. **Build the Pine indicator** from existing AF Struct+IM as base, encoding everything AG learned, using Pine tools/skills only
