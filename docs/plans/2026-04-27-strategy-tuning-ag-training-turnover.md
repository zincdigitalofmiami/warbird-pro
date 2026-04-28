# Strategy Tuning + AG Training Turnover

**Date:** 2026-04-27  
**Status:** Active handoff snapshot  
**Scope:** Warbird indicator-only plan (`MASTER_PLAN v6`) with focus on strategy tuning and AG training from TradingView/Pine outputs.

## 1) Current Operating Snapshot

- Active architecture: **Warbird Indicator-Only AG Plan v6**.
- Canonical truth: **TradingView/Pine outputs only** (indicator CSV, Strategy Tester exports, CDP `reportData().trades()`, and Pine footprint snapshots where required).
- Baseline checkpoint lock (2026-04-27):
  - 15m reference: `+6.74%`, `PF 1.143`, `434 trades`, `3.47% max DD`
  - 5m tuning lane: `-2.55%`, `PF 0.91`, `295 trades`, `3.44% max DD`
  - 1h deprioritized
- Current directive: run a **full-surface 5m optimization** on the main fib engine + main strategy, with Optuna responsible for selecting best settings across the full tuning surface.
- Hard freeze: **fib architecture and structure are not to be touched** (no code edits to fib core/structure logic; no Optuna mutation of frozen fib-architecture controls).
- 2026-04-27 safety hotfix (non-repaint contract): setup-phase ladder/entry is now frozen at `TRADE_SETUP` seed and released on resolution/expiry. This is a stability fix for repeatable tuning evidence, not a tunable surface expansion.

## 2) Guardrails (Non-Negotiable)

- No mock/demo/synthetic rows.
- No external joins in active modeling: no FRED, macro, news, options, cross-asset, Supabase training mirrors, or Databento feature stacking.
- Every run declares one trigger family only:
  - `LIVE_ANCHOR_FOOTPRINT`
  - `STRATEGY_ACCEPT_SCALP`
  - `BACKTEST_DIRECT_ANCHOR`
  - `NEXUS_FOOTPRINT_DELTA`
- For Nexus lane: use TradingView/Pine `request.footprint()` evidence only.
- MES friction floors: commission `$1.00/side`, slippage `1 tick`; use Bar Magnifier when intrabar stop/target behavior matters.

## 3) Full-Surface 5m Tuning Mandate (Main Engine, Fib/Structure Frozen)

### Frozen — Do Not Touch

Keep fib architecture and structure logic unchanged in tuning and implementation:

- `fibHtfSnapshot`, `fibZzSource`
- anchor ownership/state transitions for fib legs
- canonical fib ladder construction (`fibPrice` + canonical ratios/targets)
- trade-time fib freeze surfaces (`snapP*`, `effectiveP*`, draw-span freeze behavior)
- setup-phase lock behavior for execution direction + entry/SL/TP levels (freeze at `TRADE_SETUP`, print at confirmed trigger)
- structure semantics and state-machine primitives (`breakInDir`, `acceptInDir`, `rejectAtZone`, `breakAgainst`, event edge logic)

### Tunable — 5m Primary Search Surface

Optuna must search the primary non-frozen engine surface for 5m optimization, including:

- Trend/MA controls
  - MA selection used by the strategy gates
  - MA lengths used by entry/trend filters
- Entry and structure gating
  - optimal entry path and anchor hit/reclaim behavior
  - liquidity sweep lookback (`liqSweepLookbackBarsInput`)
  - ADX short gate floor (`shortTrendGateAdx`) and related trend gates
- Footprint exhaustion and quality gates
  - exhaustion lookbacks/cooldowns
  - footprint imbalance/zero-print/absorption controls
  - related footprint strictness knobs used in entry and exhaustion logic

If any required non-frozen knob (for example MA family selector) is not yet exposed in the active search space, add it before running the full trial campaign.

## 4) Strategy Tuning Workflow (Primary)

Primary runbook: `docs/runbooks/strategy_tuning.md`

1. Expand/verify search space to cover all required **non-frozen** main-engine knobs and explicitly exclude frozen fib/structure controls.
2. Generate candidates:
```bash
python scripts/ag/tune_strategy_params.py suggest --count 50
```
3. Execute via CDP (preferred authoritative mode `TV_MCP_STRICT`):
```bash
python scripts/ag/tv_auto_tune.py run --batch-dir artifacts/tuning/suggestions/<timestamp>/
```
4. Review leaderboard:
```bash
python scripts/ag/tune_strategy_params.py leaderboard --top 20
```
5. Repeat batch loops until **1,000 authoritative trials** are completed for the primary 5m campaign.
6. For manual CSV fallback (`CSV_FULL`), enforce 2020-01-01+ date range and record with manifest notes.

### Strategy Tuning Acceptance Gates
- Adequate sample/trade count
- Stability across rolling windows and yearly splits
- Directional balance (long/short not one-sided)
- Drawdown efficiency acceptable vs PF/expectancy
- No champion accepted without IS/OOS or walk-forward style review
- Trial budget gate: no final candidate promotion before the 1,000-trial campaign is complete (unless explicitly overridden).
- Freeze gate: reject any trial batch/config that mutates frozen fib architecture or structure controls.

## 5) AG Training Workflow (Indicator-Only)

Use AG/Optuna as offline analyzers of Pine behavior, not a separate decision engine.

Reference surfaces:
- `scripts/optuna/`
- `scripts/ag/tune_strategy_params.py`
- `scripts/ag/tv_auto_tune.py`
- `scripts/optuna/workspaces/<indicator_key>/`
- `artifacts/tuning/`

Example institutional Optuna lane:
```bash
python3 scripts/optuna/runner.py \
  --indicator-key v7_warbird_institutional \
  --profile-module scripts.optuna.v7_warbird_institutional_profile \
  --study-name v7_warbird_institutional_wr_pf \
  --n-trials 1000 \
  --start 2020-01-01
```

Post-Optuna AG analysis order (required for change decisions):

1. Promote the top settings cohort from the 1,000-trial main-engine run.
2. Run AG training/evaluation using those settings with **multiple folds** and **bagging**.
3. Run **walk-forward** validation on selected finalists.
4. Run **deep SHAP** analysis (high-depth feature attribution) on finalists.
5. Convert SHAP + walk-forward evidence into concrete Pine setting/build change recommendations.

### AG Training Deliverable (Required)
Each batch must produce:
- Trial/config artifact set
- Manifest with source file, commit, symbol, timeframe, date range, method, trigger family, Pine inputs, tester properties, row/trade counts, hash
- Ranked recommendation set: champion, rejects, stability notes, failure modes
- Multi-fold/bagging and walk-forward summary for finalists
- Deep-SHAP evidence pack for the selected finalist set
- Explicit statement that recommendation is for Pine settings/build changes only

## 6) Pine Budget + Verification Status

Current budget baseline:
- `v7-warbird-institutional.pine`: `58/64`
- `v7-warbird-strategy.pine`: `60/64`
- `v7-warbird-institutional-backtest-strategy.pine`: `53/64`

Any `.pine` edit requires:
1. pine-facade compile check
2. `./scripts/guards/pine-lint.sh <file>`
3. `./scripts/guards/check-contamination.sh`
4. `npm run build`
5. `./scripts/guards/check-indicator-strategy-parity.sh` when v7 indicator/strategy coupling is touched

## 7) Next Action Queue (Recommended)

1. Finalize 5m search space for the primary engine while preserving frozen fib architecture and structure.
2. Execute and complete a **1,000-trial** Optuna campaign (authoritative run mode).
3. Publish leaderboard + manifest + trial-count/date-range proof.
4. Select best settings cohort and run AG multi-fold + bagging validation.
5. Run walk-forward and deep-SHAP on finalists; derive concrete Pine changes.
6. After main primary indicator engine decisions are finalized, start Nexus lane tuning.

## 8) Handoff Checklist (End Of Session)

- Save artifacts in `artifacts/tuning/` and workspace DB outputs.
- Capture manifest for every authoritative run.
- Update docs if contract/trigger/scope changed:
  - `docs/MASTER_PLAN.md`
  - `docs/contracts/pine_indicator_ag_contract.md`
  - `docs/runbooks/strategy_tuning.md`
  - `WARBIRD_MODEL_SPEC.md`
  - `CLAUDE.md`
- Record unresolved risks/open questions and exact pending command to resume.

## 9) Known Risks To Watch

- Overfitting to a narrow period while PF looks strong.
- Mixing trigger families in one training set.
- Accepting results without full manifest and friction assumptions.
- Prematurely switching to Nexus before main-engine optimization and AG evidence closure.
- Accidental mutation of frozen fib architecture/structure via search-space drift.

---

**Turnover intent:** execute 5m main-engine optimization with fib architecture/structure frozen, complete 1,000-trial Optuna evidence, validate with AG fold/bagging + walk-forward + deep-SHAP, and only then move to Nexus.
