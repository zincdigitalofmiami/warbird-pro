# Policy MC Sweep — Design (2026-04-15)

## 🔴 READ THIS FIRST — ASSUME NOTHING

**In this project, do NOT assume anything claimed in docs, skills, plans, audits, prior agent summaries, or prior commits is correct. Verify against ground truth before acting or writing.**

This rule exists because in this single session alone, the following assumptions were made and proved wrong:

| Assumption | Source | Ground truth |
|---|---|---|
| "Task E was degraded on agtrain_20260415T165437712806Z" | earlier audit report + prior skill updates | `task_E_entry_rules.json` shows `degraded=False, overlap_keys=[], top_k_take=30, top_k_avoid=30, eligible_combo_count=294` |
| SHAP artifacts live at `artifacts/ag_runs/<RUN_ID>/shap/` | `.claude/skills/training-shap/SKILL.md:23` + `training-hard-gate/SKILL.md:67,98` | Actual path is `artifacts/shap/<run_id>/` |
| SHAP code emits `integrity.json` | skill prescribed it | zero references in `run_diagnostic_shap.py`, `monte_carlo_run.py`, `train_hard_gate.py`; file does not exist at the referenced path |
| "SHAP patch at run_diagnostic_shap.py:267 is currently uncommitted" | `.claude/skills/training-pre-audit/SKILL.md:186, :200` (and mirrored copies) | stale — needs re-verification, skill prose lies about commit state |
| "ag_training_runs has 0 RUNNING rows" | top-level retrospective | DB had 1 RUNNING orphan at check time (`agtrain_20260415T202042354476Z`) |
| "FIB_NEG_0236 / FIB_NEG_0382 have no edge" (implied by PF 0.58 / 0.49) | Task A per-family rollup | those PFs are ONE training run's pricing of those families. Families may be undertrained, not unmeritorious. Do not label families NO_EDGE from Task A alone. |
| Drive unmount is a real risk | my own caveat | external drive is welded onto the Mac; unmount is not a concern |
| "Anchors" in the user's chart question meant drawing circles | pattern-matched on the word | user meant pivot-selection behavior, not visual markers |

**Every one of those was a statement read from a prior artifact that was itself wrong.** The pattern: each agent in the chain (human or AI) took the prior agent's claim at face value and propagated it forward.

### Ground truth sources (in priority order)

1. **Artifact files on disk** — JSON / parquet / CSV in `artifacts/`. Read the bytes.
2. **Local PG17 `warbird` database** — `psql -d warbird -h 127.0.0.1 -p 5432` queries. Truth for schema + row counts + run state.
3. **Source code** — `scripts/ag/*.py`, `indicators/*.pine`. What the code does, not what its docstring says.
4. **Git history** — `git log`, `git blame`. Note: prior commits can also be wrong; history tells you WHEN a claim entered the repo, not whether it was true then.
5. **`.remember/today-*.md`** — chronological session checkpoints. Subjective but timestamped.

### Sources to treat with SUSPICION until verified

- **Skill files** (`.claude/skills/`, `.kilocode/skills/`, `.github/skills/`) — can contain prescriptive contracts that the code does not implement.
- **`docs/plans/*.md`** — including THIS file. A plan can be stale as of the second it's committed.
- **`CLAUDE.md` / `AGENTS.md`** — high-level claims are usually true; specific numbers and path claims drift.
- **Prior retrospectives or audit reports** — summarize; may simplify or misread.
- **Anything that says "currently uncommitted" / "pending" / "about to land"** — may have landed, may have been reverted, may still be pending.

### Verification discipline before making any claim in this project

| Claim type | Minimum verification |
|---|---|
| "stop-family X has no edge" | Phase 3 full-pipeline Bayesian sweep under varied training conditions. Single-run PFs do not qualify. |
| "run is clean / contaminated" | read `run_config.json` for `num_bag_folds`, `num_stack_levels`, `dynamic_stacking`; `fold_*/fold_summary.json` for `zoo_families_present` |
| "artifact X exists at path Y" | `ls Y` in same message before asserting |
| "skill contract is enforced" | grep source code for the referenced behavior; verify at least one code path emits what the skill says |
| "script does X" | read the function. The docstring and the name may not agree with the body. |
| "pipeline regen will / won't affect Z" | trace the code path end-to-end |

**If you catch yourself writing a claim without having just verified it this turn — stop, verify, then write.**

---

## Context

The Warbird indicator and strategy (`indicators/v7-warbird-institutional.pine`, `indicators/v7-warbird-strategy.pine`) expose ~30 tunable inputs ("knobs") spread across five TradingView sections: FIBONACCI ENGINE, STRUCTURE LOGIC, STOP LOGIC, EXECUTION CONTRACT, FOOTPRINT EXHAUSTION, plus VISUALS and HTF CONFLUENCE. Manually tuning this space is estimated at roughly a year of work. This design specifies a Monte-Carlo-driven policy sweep that replaces a portion of that manual work on existing training artifacts — specifically the knobs that can be swept POST-HOC without retraining AG.

The remaining knobs (those that change what AG sees as features, or which interactions qualify as training inputs) require a separate full-pipeline outer-loop project designated **Phase 3**, which is NOT part of this design. Phase 3 is acknowledged but will have its own design doc once Phase 1+2 is validated in practice.

## Knob taxonomy

| Category | Examples | Swept in this design? |
|---|---|---|
| **A. Upstream feature/gate knobs** | Footprint Ticks Per Row, VA%, Imbalance%, Z Length, Z Threshold, HTF Wall Buffer, Use 1H/4H Filter, ZigZag Dev/Depth/Threshold, Min Fib Range, Confluence Tolerance, Anchor TF Override, Extension ATR Tolerance, Zero-Print Volume Ratio, Extreme Rows, Tier 1 Hold Bars | **No — Phase 3 only.** Changing them changes the feature set or interaction set, requiring pipeline regen + full AG retrain per combo. |
| **B. Stop-family sub-parameters** | Tier 1 Hold Stop ATR, structural stop ATR mult, emergency stop ATR mult | **No — Phase 3 only.** New values require new `ag_fib_stop_variants` rows and outcome regen. |
| **C. Post-prediction exit management** | Cooldown Bars, Scalp Target Points, Scalp BE Trigger, Scalp Max Hold, Let Fast Runners Run, Fast Runner Window, Fast Runner Target, Break-Even After TP1 | **Yes — Phase 2** (requires per-trade forward trajectory). |
| **D. Structural entry filters** | Gate Shorts In Bull Trend, Short Gate ADX Floor, Rejection=wick, Use Footprint Scalp Entries | **Yes — Phase 1** (pure filter on existing labeled outcomes; no trajectory needed). |

## Objective function (locked)

For each policy combo within a stop family:

```
primary:      tp1_reach_rate = P(outcome_label ∈ {TP1_ONLY, TP2_HIT, TP3_HIT, TP4_HIT, TP5_HIT})
tiebreaker:   expected_net_$_per_trade  (after $1.25 flat fee per trade)
hard filter:  n_trades >= min_combo_n (default 50)
```

**No hard SL width constraint.** All 6 stop families remain eligible regardless of their mean `sl_dist_pts`. The output surfaces `tp1_reach_rate` so the user can judge whether a wide-SL policy is worth taking given its survival odds.

**No cross-family ranking.** This sweep ranks POLICIES within each stop family. It does NOT declare a winner stop family. Family-vs-family comparison requires Phase 3 under varied training conditions. See Anti-Pattern A below.

## Scope

- One new script: `scripts/ag/policy_mc_sweep.py`
- Outputs under `artifacts/ag_runs/<RUN_ID>/policy_sweep/` (new directory)
- Read-only against existing artifacts and the local `warbird` DB (`mes_1m` only)
- Pure Python + pandas + numpy + psycopg2 + pyarrow (already installed)
- Runs on the locked clean-chain fixture `agtrain_20260415T165437712806Z` first; parameterized by `--run-id` for any future run that has SHAP + MC Task A artifacts

## Non-scope

- Does NOT modify `scripts/ag/train_ag_baseline.py`
- Does NOT modify `scripts/ag/run_diagnostic_shap.py`
- Does NOT modify `scripts/ag/monte_carlo_run.py`
- Does NOT modify `scripts/ag/build_ag_pipeline.py`
- Does NOT modify any `.pine` file
- Does NOT modify any `local_warehouse/migrations/*.sql`
- Does NOT trigger AG training
- Does NOT decide which stop family to deploy
- Does NOT drive TradingView via CDP (`tv_auto_tune.py` is unrelated; the recommended_settings.json artifact CAN be consumed by a future extension of that tuner, but that integration is out of scope)

## Anti-patterns to avoid (carved into the design)

### Anti-Pattern A — "The model said this family has no edge"

**Never** infer that a stop family is fundamentally weak from a single training run's per-family PF. The model may have undertrained on that family's trades due to class imbalance, feature sparsity, time-limit starvation, or a specific training configuration. The only valid test for "this family has edge" is **Phase 3 — a Bayesian outer-loop that retrains AG under varied training conditions and observes whether the family remains weak across configurations.**

Concrete enforcement in this script:
- No `NO_EDGE` family label
- No `--min-tp1-reach-floor` CLI flag
- All 6 families get their best-available policy emitted in `recommended_settings.json`
- `recommended_settings.json.cross_family_ranking_valid = false`
- `policy_summary.md` opens with a "not a family ranking" disclaimer

### Anti-Pattern B — "Hardcoded narrative caveats"

Every caveat sentence in `policy_summary.md` MUST be runtime-conditional on actual source-run metadata. Hardcoded strings like `"IID bag leakage"` or `"GBM-only"` that fire regardless of actual config are a contract violation. Enforcement pattern mandated in Section 4 below.

### Anti-Pattern C — "Prior claim, no verification"

Before asserting any fact about the source run (bag config, zoo coverage, fold baselines, calibration, leakage candidates), the script re-derives it from the raw artifacts in THIS invocation. It does not trust prior summaries, prior skill prose, or prior agent outputs.

## Architecture

**New file (only new file created by this design):** `scripts/ag/policy_mc_sweep.py`

**Output directory layout:**
```
artifacts/ag_runs/<RUN_ID>/policy_sweep/
    trajectory_cache/
        fold_01.parquet     ← per-trade forward high/low/close deltas
        fold_02.parquet
        fold_03.parquet
        fold_04.parquet
        fold_05.parquet
    filter_sweep_results.json    ← Phase 1: filter combo ranking per stop family
    exit_sweep_results.json      ← Phase 2: exit combo ranking per top-K filter per family
    recommended_settings.json    ← Pine input translation per stop family
    policy_summary.md            ← human-readable report
    integrity.json               ← gate verdicts, drift checks, fixture hashes
```

**CLI:**
```bash
python3 scripts/ag/policy_mc_sweep.py \
  --run-id agtrain_20260415T165437712806Z \
  --phase both                    # 'filter' | 'exit' | 'both' (default: both)
  --min-combo-n 50                # min trades per combo to rank
  --top-k 10                      # top/bottom K per family
  --max-trajectory-bars 120       # Phase 2: 15m bars forward from entry
  --rebuild-trajectory-cache      # force rebuild Phase 2 cache
  --dry-run                       # validate gates + print combo counts, no outputs
```

**Exit codes:**
- `0` — script completed, all gates passed, outputs written
- `1` — gate failure (drift, alignment, integrity mismatch) — outputs partial or absent
- `2` — invalid CLI args or missing source artifacts

## Components & data flow

```
┌─────────────────┐   ┌──────────────┐   ┌──────────────────────────┐
│ mes_1m          │   │ ag_training  │   │ monte_carlo/cache/       │
│ (local PG17)    │   │ (local PG17) │   │   fold_0N/probs.parquet  │
└────────┬────────┘   └──────┬───────┘   └──────────────┬───────────┘
         │                   │                          │
         │ Phase 2 only      │ both phases              │ both phases
         ▼                   │                          │
┌────────────────────┐       │                          │
│ TrajectoryBuilder  │       │                          │
│ (per-fold loader,  │       │                          │
│  bar slicer,       │       │                          │
│  parquet cacher)   │       │                          │
└────────┬───────────┘       │                          │
         │                   │                          │
         └──────────┐   ┌────┘                          │
                    ▼   ▼                               │
           ┌────────────────────────────────────┐       │
           │ OutcomeJoiner                      │◀──────┘
           │ joins on stop_variant_id:          │
           │  - entry_ts, entry_price           │
           │  - stop_family_id, direction       │
           │  - adx, archetype                  │
           │  - is_bull_trend (derived)         │
           │  - outcome_label, highest_tp_hit   │
           │  - bars_to_tp1, mae_pts, mfe_pts   │
           │  - sl_dist_pts                     │
           │  - predict_proba (6 classes)       │
           │  - trajectory_arr (Phase 2 only)   │
           └────┬───────────────────────────────┘
                │
        ┌───────┴─────────────────┐
        ▼                         ▼
┌─────────────────┐   ┌──────────────────────────────────┐
│ FilterSweeper   │   │ ExitSweeper                      │
│ (Phase 1)       │   │ (Phase 2)                        │
│                 │   │ takes top-K filter combos from   │
│ 56 filter       │   │ Phase 1                          │
│ combos:         │   │                                  │
│  - apply gate   │   │ for each (top_filter ×           │
│  - count TP1    │   │           exit_combo):           │
│  - count stop   │   │  walk trajectory bar-by-bar,     │
│  - compute $    │   │  apply exit rules,               │
│  - MC p5 EV     │   │  compute realized $ per trade    │
└────────┬────────┘   │                                  │
         │            │  exit rules:                     │
         │            │   - Scalp Target (long/short)    │
         │            │   - BE Trigger (move stop)       │
         │            │   - Max Hold Bars (force close)  │
         │            │   - Fast Runner (extend TP2→TP3) │
         │            │   - Break-Even After TP1         │
         │            │   - Cooldown Bars (rejection)    │
         │            └────────┬─────────────────────────┘
         │                     │
         ▼                     ▼
┌──────────────────────────────────────────────────┐
│ Ranker                                           │
│ primary sort: tp1_reach_rate DESC                │
│ tiebreak:     expected_net_$_per_trade DESC      │
│ filters:      n_trades >= min_combo_n            │
│ grouping:     per stop_family_id                 │
│ outputs:      top_k TAKE + bottom_k AVOID        │
└────────┬─────────────────────────────────────────┘
         │
         ▼
┌──────────────────────────────────────────────────┐
│ PineSettingsEmitter                              │
│ - maps swept var → Pine input label              │
│ - groups by target indicator (strat / institut.) │
│ - lists unmapped knobs with CURRENT values       │
│ - flags statistical validity per policy          │
│ - EMITS ALL 6 FAMILIES (no NO_EDGE exclusion)    │
└────────┬─────────────────────────────────────────┘
         │
         ▼
┌──────────────────────────────────────────────────┐
│ SummaryWriter                                    │
│ → filter_sweep_results.json                      │
│ → exit_sweep_results.json                        │
│ → recommended_settings.json                      │
│ → policy_summary.md                              │
│ → integrity.json                                 │
└──────────────────────────────────────────────────┘
```

### Phase 1 sweep space (entry filters)

4 knobs, cartesian product:
- `Gate Shorts In Bull Trend`: {off, on}
- `Short Gate ADX Floor`: {15, 18, 20, 23, 25, 28, 30} (7 levels)
- `Rejection = wick into zone`: {off, on}
- `Use Footprint Scalp Entries`: {off, on}

Total combos: 2 × 7 × 2 × 2 = **56**

### Phase 2 sweep space (exit management)

6 knobs per top-K filter combo from Phase 1:
- `Scalp Target (Points)`: {12, 16, 20, 24, 28, 32, 36, 40} (8 levels)
- `Scalp Break-Even Trigger`: {5, 8, 10, 12, 15, 20} (6 levels)
- `Scalp Max Hold Bars`: {6, 10, 12, 16, 20, 25, 30} (7 levels)
- `Fast Runner Target`: {TP1, TP2, TP3} (3 levels)
- `Break-Even After TP1`: {off, on}
- `Let Fast Runners Run`: {off, on}

Per top-5-filter-combo exit space: 8 × 6 × 7 × 3 × 2 × 2 = **4,032 combos per filter**
Total Phase 2 combos per family: 5 × 4,032 = 20,160
Across 6 families: ~121,000 exit evaluations (all against cached trajectories)

## Error handling & drift detection (Gates A–H)

Every gate either aborts with a clear error or marks output as degraded — no silent failures.

### Gate A — Trajectory drift detection

On a random sample of 200 trades from fold_01:
- Trajectory-derived stop-hit / TP1-hit / outcome vs warehouse `outcome_label`
- Trajectory-derived `bars_to_tp1` vs warehouse `bars_to_tp1`

If ≥ 5% of the sample disagrees → **abort** (exit 1). Phase 1 can still run standalone (does not depend on trajectory).

Rationale: drift means re-simulation scores against a different exit contract than training was labeled under — silently invalid.

### Gate B — Cache invalidation

Trajectory cache key = `md5(fold_start || fold_end || mes_1m_max_ts || ag_training_row_count || script_version || max_trajectory_bars)`.

Cache hit → load. Cache miss → rebuild. Filename embeds the key so stale caches cannot leak across runs.

### Gate C — Min-n gate per combo

Combos with `n_trades < min_combo_n` excluded from ranking, logged in `integrity.json.combos_below_min_n` with reason. Never silently dropped.

### Gate D — predict_proba alignment

On loading `monte_carlo/cache/fold_0N/probs.parquet`:
- Assert `len(probs) == len(joined_dataset_fold)`
- Assert `probs["stop_variant_id"]` set equals joined dataset's set

On mismatch → **abort** with diff report (exit 1).

### Gate E — Stop-family coverage

If a stop family has zero combos passing `min_combo_n`:
- Family marked `"no_policy_found"` in `recommended_settings.json` with reason (`"n=X, below min 50"`)
- Explicit in summary: `"<family>: no policy found at min_n=50 (max observed n=X)"`
- NOT an exclusion from the sweep — a reporting of what the data supports

### Gate F — Source run integrity propagation

Script re-derives source-run integrity at invocation (never trusts prior artifacts):
- Read `run_config.json` → `num_bag_folds`, `num_stack_levels`, `dynamic_stacking`
- Read each `fold_*/fold_summary.json` → `zoo_families_present`, `test_macro_f1 vs majority_baseline.test.macro_f1`, `val_class_count vs test_class_count`
- Read SHAP `drop_candidates.csv` if present → count `reason_code == LEAKAGE_SUSPECT`

Flag conditions:
- Any `LEAKAGE_SUSPECT` → `source_run_has_leakage_suspects: true`
- Any fold `test_macro_f1 < majority_baseline.test.macro_f1` → `source_run_has_below_baseline_fold: true`
- Any fold `val_class_count < test_class_count` → `source_run_has_class_coverage_gap: true`
- Any of the above → `promotion_allowed: false` in `recommended_settings.json`

`policy_summary.md` prepends a banner listing the specific flags. Script still runs for diagnostic value.

### Gate G — Empty-trajectory trades

If `mes_1m` has a data gap for a trade's window (no bars between `entry_ts` and `entry_ts + max_window`):
- Trade excluded from **Phase 2 only**
- Logged in `integrity.json.phase2_excluded_trades` with stop_variant_id + reason
- Phase 1 still includes the trade (uses only `outcome_label`)

### Gate H — Fixture row count assertion

At script start, `SELECT count(*) FROM ag_training`. Assert equals the count in `task_A.json.indicator_settings_frozen` row manifest (if present) or the source-run expected floor.

On drift → **abort** (exit 1): "Source fixture changed since Task A was generated. Re-run MC tasks A–I first."

Prevents the "someone reran the pipeline mid-sweep" failure.

## Outputs

### `filter_sweep_results.json`

Top-level keys:
- `run_id`, `generated_at_utc`, `script_version`, `source_run_integrity`
- `sweep_space`: {knob_name: [values]}
- `total_combos`, `combos_below_min_n`, `combos_ranked`
- `per_stop_family`: dict keyed by stop_family_id; each entry has `top_k_take` + `top_k_avoid` lists of combos with full per-combo metrics
- `global_combos`: dict of all 56 × 6 = 336 combos keyed by `<stop_family>|<filter_combo_key>`, full metrics

Per-combo metrics stored:
- `filter_knobs`: {knob_name: value}
- `n_trades`, `per_fold_n_trades`
- `tp1_reach_rate`, `tp2_plus_rate`, `tp5_rate`, `stop_rate`
- `mean_sl_dist_pts`
- `expected_net_$_per_trade`
- `mc_p5_ev_per_trade` (where computed)
- `per_fold_tp1_reach_rate` (stability check)

### `exit_sweep_results.json`

Top-level keys: same frame as filter_sweep + `top_k_filter_combos_used: [list of filter keys passed from Phase 1]`.

Per-combo:
- `exit_knobs` + `filter_knobs` (both sets, since exit is conditioned on filter)
- Re-simulated `tp1_reach_rate`, `stop_rate`, `expected_net_$_per_trade`
- `re_sim_correctness_check`: sanity result of re-simulating with CURRENT live knob values vs warehouse outcomes (should match at default knob values)

### `recommended_settings.json`

Structure per Section 2:
```json
{
  "generated_at_utc": "...",
  "source_run_id": "...",
  "fixture_hashes": { "ag_training_row_count": 327942, ... },
  "caveat": "Per-family policies optimized on predict_proba from ONE training run. Cross-family ranking is NOT valid from this artifact. See Anti-Pattern A in docs/plans/2026-04-15-policy-mc-sweep-design.md.",
  "cross_family_ranking_valid": false,
  "promotion_allowed": <true|false based on Gate F>,
  "promotion_blocked_reason": "<populated if false>",
  "winning_policy_per_stop_family": {
    "ATR_1_0":   { "strat_settings": {...}, "institutional_settings": {...}, "metrics": {...}, "statistical_validity": {...} },
    "ATR_1_5":   { same shape },
    "ATR_STRUCTURE_1_25": { same shape },
    "FIB_0236_ATR_COMPRESS_0_50": { same shape },
    "FIB_NEG_0236": { same shape },
    "FIB_NEG_0382": { same shape }
  },
  "unmapped_knobs": {
    "comment": "Live TV inputs NOT optimized by this sweep. Current values retained. Phase 3 targets these.",
    "strat": { knob_name: current_value, ... },
    "institutional": { knob_name: current_value, ... }
  }
}
```

### `policy_summary.md`

```markdown
# Policy Sweep — <run_id>
Generated: <utc>
Source run integrity: <verdict string derived from Gate F>
Promotion allowed: <bool from integrity.json>

## ⚠ Not a family ranking
This sweep ranks POLICIES within each stop family. It does NOT judge
which stop family is better than another. Cross-family comparison
requires Phase 3 pipeline sweep under varied training conditions.

## 1. Best policy per stop family (6 blocks, no verdict rank)
### ATR_1_0 — best policy
### ATR_1_5 — best policy
### ATR_STRUCTURE_1_25 — best policy
### FIB_0236_ATR_COMPRESS_0_50 — best policy
### FIB_NEG_0236 — best policy
### FIB_NEG_0382 — best policy
(each block: filter stack, exit stack, tp1_reach_rate, mean_sl_dist_pts,
 n_trades, expected net $, per-fold stability, statistical_validity verdict)

## 2. Full top-10 TAKE policies per family (detailed)

## 3. Full bottom-10 AVOID policies per family

## 4. Filter-knob sensitivity (how each Cat D knob shifts mean tp1_reach)

## 5. Exit-knob sensitivity (how each Cat C knob shifts expected net $)

## 6. Cross-fold stability per winning policy

## 7. Diagnostics (Gates A–H results)
- Gate A trajectory drift: <pass/fail + sample stats>
- Gate B cache state: <hit/miss>
- Gate C combos below min_n: <count>
- Gate D proba alignment: <pass>
- Gate E stop-family coverage: <all/partial + list>
- Gate F source integrity: <verdict>
- Gate G empty-trajectory trades: <count>
- Gate H fixture assertion: <pass>

## 8. Source run integrity inheritance
(only if Gate F flagged anything — lists the specific flags verbatim)
```

### `integrity.json`

```json
{
  "run_id": "...",
  "script_version": "1.0.0",
  "generated_at_utc": "...",
  "fixture_hashes": { "ag_training_row_count": 327942, "task_A_md5": "..." },
  "gates": {
    "A_trajectory_drift": { "status": "PASS", "sample_size": 200, "disagreements": 3, "disagreement_rate": 0.015 },
    "B_cache_key": "<md5>",
    "C_combos_below_min_n": { "count": 12, "samples": [...] },
    "D_proba_alignment": { "status": "PASS" },
    "E_stop_family_coverage": { "per_family": { ... } },
    "F_source_run_integrity": {
      "source_run_has_leakage_suspects": <bool>,
      "source_run_has_below_baseline_fold": <bool>,
      "source_run_has_class_coverage_gap": <bool>,
      "derived_from": ["run_config.json", "fold_*/fold_summary.json", "shap/drop_candidates.csv"]
    },
    "G_empty_trajectory_trades": { "count": 0, "samples": [] },
    "H_fixture_assertion": { "status": "PASS", "expected_count": 327942, "observed_count": 327942 }
  },
  "narrative_caveat_audit": {
    "hardcoded_strings_found": [],
    "conditional_caveats_emitted": [
      { "caveat": "...", "condition_key": "...", "value": "..." }
    ]
  },
  "cross_family_ranking_valid": false,
  "promotion_allowed": <bool>,
  "promotion_blocked_reason": "<populated if false>"
}
```

## Stale-caveat avoidance (the critical non-regression rule)

Every narrative line in `policy_summary.md` and every caveat string must be derived from actual source-run metadata at write-time. Code pattern mandated in the implementation:

```python
# BANNED
summary.append("Source run flagged for IID bag leakage and GBM-only model zoo.")

# REQUIRED
source_cfg = json.load(open(f"{RD}/run_config.json"))["args"]
if source_cfg["num_bag_folds"] > 0:
    summary.append(
        f"Source run used num_bag_folds={source_cfg['num_bag_folds']}; "
        f"SHAP/MC absolute numbers may reflect IID bag leakage."
    )

families = set()
for f in glob(f"{RD}/fold_*/fold_summary.json"):
    families |= set(json.load(open(f))["autogluon"]["zoo_families_present"])
if len(families) < 7:
    missing = {"GBM","CAT","XGB","RF","XT","NN_TORCH","FASTAI"} - families
    summary.append(f"Source run zoo coverage incomplete: missing {sorted(missing)}.")
```

Each emitted caveat is logged to `integrity.json.narrative_caveat_audit.conditional_caveats_emitted` with the condition key and value that caused it to fire. A future hard-gate integrity check can grep `policy_summary.md` for forbidden literal strings (`"IID bag leakage"`, `"GBM-only"`, `"bag-fold"`) when the source run config proves they should not have emitted.

## Validation before declaring the script complete

Before the script is claimed ready:

1. **Phase 1 parity check:** run with default knob values (matching current live settings) and confirm that the full-data combo's metrics match what direct aggregation of `ag_training + monte_carlo/cache` produces. If they differ, the filter logic has a bug.

2. **Phase 2 drift check:** at default knob values (Scalp Target=20, BE Trigger=10, Max Hold=12, Fast Runner Target=TP2, BE After TP1=on, Let Fast Runners Run=on), Phase 2's re-simulated `tp1_reach_rate` per family should match Phase 1's within tolerance. If trajectory re-simulation gives a different answer than label-counting at matched knob settings, trajectory is drifting — Gate A should catch this, but this is a belt-and-suspenders check.

3. **Gate H fixture assertion** runs clean.

4. **Dry-run mode** prints combo counts + gate pre-checks and writes no outputs. Exit 0.

5. **Re-run with cache** completes in < 30 sec.

6. **`integrity.json.narrative_caveat_audit.hardcoded_strings_found` is empty** on a clean source run.

7. **grep `policy_summary.md`** for forbidden literals (`"IID bag leakage"`, `"GBM-only"`, `"bag-fold"`) — 0 matches when source run is clean.

## Future work (out of scope for this design)

- **Phase 3** — Bayesian outer-loop that sweeps Category A + B knobs by driving the full pipeline (build_ag_pipeline → train_ag_baseline → run_diagnostic_shap → monte_carlo_run → policy_mc_sweep) per probe, records the objective per trial, and iteratively refines. Separate design doc at `docs/plans/YYYY-MM-DD-phase3-bayesian-pipeline-sweep-design.md` (to be created AFTER Phase 1+2 is in use).
- **Extended PineSettingsEmitter** — once Phase 3 exists, the emitter learns to populate the Category A knobs too (currently listed only in `unmapped_knobs`).
- **Automated TV input injection** — extend `scripts/ag/tv_auto_tune.py` to consume `recommended_settings.json` and inject via CDP into the TradingView Desktop app. Separate project.
- **Hard-gate integrity check on policy sweep output** — analogous to the SHAP/MC contract grep, verify policy sweep narrative contains no stale caveats and no implicit family ranking. Contract is described in this doc; implementation in `scripts/ag/train_hard_gate.py` is a separate change.

## Open questions

- None blocking for implementation. All design forks have been decided with user approval.
- Execution dependency: `scripts/ag/policy_mc_sweep.py` does not exist yet. Creation is the next step.

## Design approval trail

- Section 1 Architecture: approved 2026-04-15
- Section 2 Components + PineSettingsEmitter (Phase 3 deferred): approved 2026-04-15
- Section 3 Error handling (Gates A–H): approved 2026-04-15
- Section 4 Outputs + ranking (with Anti-Pattern A correction dropping NO_EDGE labeling): approved 2026-04-15
- "Assume nothing" meta-rule added to top of document by user request: 2026-04-15

---
