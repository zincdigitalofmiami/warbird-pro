# 2026-05-09 — Warbird Pro Autogluon Core Training — Chat Handoff

**Status: PRE-LAUNCH. Not training. Awaiting Kirk's final decisions on open items below.**

---

## TL;DR

Building the next AG training run with the FULL feature surface from the new V9 indicator. Previous run (May 8) trained on 23 available features while key surfaces (footprint, VIX, eqh/eql, levels, ADX, MA distances, vol z-score) were missing from the dataset.

The data IS local, including 4.4GB of MES tick-level Trades from Databento (1 year window, May 2025 → May 2026). Footprint can be fully reconstructed offline. Pre-audit shows the environment is clean. Indicator is rebuilt and pushed to TV with zero compile errors.

**Next chat MUST:**
1. Read `MEMORY.md` and ALL feedback memories before doing anything
2. Run pre-audit checklist (see § Pre-audit) before any training command
3. Resolve open decisions with Kirk before writing one line of training code
4. NEVER train on partial features (this is the #1 lesson from May 8)
5. NEVER assume / guess what Kirk wants — ask explicitly when unclear

---

## Hard rules (durable, from feedback memories — read these first)

| Rule | Memory file |
|---|---|
| Always train AG with the FULL feature set the indicator emits — never split | `memory/feedback_train_full_feature_set.md` |
| When Kirk says "add X," include it; do not silently downgrade or skip | `memory/feedback_listen_when_kirk_says_add.md` |
| AG model runs must be visible in the Optuna hub UI (port 8090) | `memory/feedback_ag_visible_in_optuna.md` |
| Cross-asset symbol naming: **DXY**, not DX | `memory/project_dxy_not_dx.md` |
| Always invoke `superpowers:verification-before-completion` before claiming done | (CLAUDE.md) |
| Use `superpowers:systematic-debugging` before proposing any bug fix | (CLAUDE.md) |
| **No feature branches.** All commits land on `main`. | (CLAUDE.md) |
| Names must spell out what they are. Banned: "AG Meta", "V*" version codes, anything not self-describing | This handoff |

---

## Project context

- **Project:** Warbird Pro — MES (E-mini S&P 500 Micro) futures, 5m chart, TradingView Pine indicator + offline AG training
- **Architecture:** Indicator-only. Pine indicator emits 49 `ml_*` hidden exports; offline ETL adds Python-only features, builds dataset, trains AG.
- **Live indicator:** `Warbird Pro V9` — `indicators/warbird-pro-v9.pine`, 1026 lines in the local worktree
- **TradingView chart:** `CME_MINI:MES1!` 5m, indicator pushed and verified
- **Repo:** github.com/zincdigitalofmiami/warbird-pro
- **Working dir:** `/Volumes/Satechi Hub/warbird-pro`
- **Kirk's email:** kirk@zincmiami.com

---

## Current state (as of commit `32fce60`)

### What landed in `training-prep` commit
- New V9 indicator with curated patterns, liquidity package, cross-asset advanced, S/R levels, footprint, FOMC, per-line styles
- `scripts/ag/train_v9_locked.py` — ML_FEATURES aligned to 45 features (43 Pine features + 2 ETL CVD divergence features), tz-bug fixed, persist() API fixed
- `scripts/optuna/warbird_pro_profile.py` — MA ranges now track live V9 defaults +/-10: `lengthMA` 90-110 and `lengthEMA` 40-60; MA type categoricals removed
- `scripts/optuna/cpcv_helpers.py` — eval_metric=log_loss, calibrate=True, persist() fix
- `scripts/ag/monte_carlo_v9.py` (new) — MC robustness analysis
- `scripts/ag/shap_v9.py` (new) — SHAP explainability
- `scripts/optuna/walk_forward.py` (new) — expanding-window validator
- `.gitignore` — excludes `models/` (large pkl artifacts)

### What is unstaged/untouched (NOT to commit with training-prep)
- `app/`, `components/`, `lib/`, `supabase/` UI/infra edits — unrelated, leave for separate commits
- `scripts/maintenance/update-claude-plugins.sh` — utility, leave alone
- 2 supabase migrations (hourly-only edge schedule) — unrelated

### Indicator pushed to TV
- Compile clean (0 errors)
- Footprint API verified working (`fp.buy_volume()`, `fp.sell_volume()`, `fp.delta()`, `fp.poc()`, `fp.vah()`, `fp.val()` with `volume_row.up_price()` / `down_price()`)
- 53/64 output budget used after pattern cleanup (51 `plot()` + 2 `alertcondition()` by `pine-lint`)

### Optuna hub
- Running, PID 568, port 8090 LISTEN
- Ready to spawn child cards on ports 8100+

---

## Pattern set — LOCKED to 4 from real backtest data

Kirk's screenshot of the candlestick patterns backtest table showed which patterns earn their slot. Drop the marginal ones; keep only:

| Pattern | Direction | Backtest return range | Status |
|---|---|---|---|
| `patBearEngulf` (Engulfing Bear) | Short | 0.52% → 6.30% | KEEP |
| `patRisingWindow` (Rising Window Bull) | Long | 0.71% → 5.21% | KEEP |
| `patMarubozuBlack` (Marubozu Black Bear) | Short | 0.78% → 3.28% | KEEP |
| `patTweezerTop` (Tweezer Top Bear) | Short | 1.17% → 2.21% | KEEP |
| ~~patBullEngulf~~ | — | mixed/weak | **DROP** |
| ~~patPiercing~~ | — | small/inconsistent | **DROP** |
| ~~patHaramiBull~~ | — | small/inconsistent | **DROP** |
| ~~patHaramiBear~~ | — | small/inconsistent | **DROP** |

Note: 3 of 4 are bearish — bearish patterns dominate the MES backtest data.

Pattern cleanup completed in the local worktree:
- `indicators/warbird-pro-v9.pine` — removed the 4 unused pattern bool definitions + their `plot()` exports + removed from `provenBullishPattern` / `provenBearishPattern`
- `scripts/ag/train_v9_locked.py` — removed the 4 from `ML_FEATURES`
- Output count dropped from 57/64 to 53/64, leaving 11 output slots before the hard cap.

**Side effect on `provenBullishPattern`:** with patBullEngulf, patPiercing, patHaramiBull all dropped, `provenBullishPattern = patRisingWindow` (single-pattern). `patternConfirm` toggle becomes effectively "must be Rising Window" for longs. Either accept that or rethink the gate logic. Likely OK — the toggle is off by default anyway.

---

## Audit of items Kirk flagged (full transparency)

These were items I previously deferred or skipped. Status after Kirk's review:

| # | Item | Status | Action |
|---|---|---|---|
| 1 | SHAP in Core | **LOCKED IN** | Run after AG.fit completes, on the trained predictor. Existing `scripts/ag/shap_v9.py` is the basis. |
| 2 | DXY rename (`ml_xa_dx_code` → `ml_xa_dxy_code`, `dxClose5` → `dxyClose5`, table label "DX" → "DXY") | **LOCKED IN** | Rename pass before push. TV symbol string `ICEUS:DX1!` STAYS (contract code). |
| 3 | Microstructure features from 1m data | **DECISION OWED** | 7 features proposed: `ml_intrabar_max_delta_pct`, `_min_delta_pct`, `_delta_skew`, `_price_path_atr`, `_max_excursion_atr`, `_volume_burst_pct`, `_close_late_pct`. Compute from raw trades or 1m bars per 5m bin. |
| 4 | Volume profile / HVN-LVN | **DECISION OWED** | Was in original scope, dropped to fit budget. Now have headroom from pattern cleanup. |
| 5 | Initial Balance / Opening Range S/R | **DECISION OWED** | First 30/60min RTH H/L. Was in original D/W S/R proposal. Dropped to fit budget. |
| 6 | Side cards (candlesticks-only, liquidity-only, cross-asset-only, footprint-only) | **DECISION OWED** | Build now in scaffold form, or after Core lands? |
| 7 | MA range wiring through to entry-filter Optuna profile | **LOCKED IN** | Base profile uses live V9 defaults +/-10: `lengthMA` 90-110 and `lengthEMA` 40-60. |
| 8 | Optuna entry-filter profile uses obsolete features | **LOCKED IN** | Current V9 restored `useMaGate` as the Pine gate switch and keeps fixed SMA/EMA semantics; banned OHLCV-delta features remain excluded. |
| 9 | Footprint window strategy (A/B/C) | **DECISION OWED** | A: train 2010-now, footprint=NaN pre-2025; B: train only 2025-05→2026-05; C: train 2010-now, validate/test on footprint window only. |
| 10 | ETL pre-flight gate (Kirk: "make sure that shit is loaded") | **LOCKED IN** | Hard assertion before AG.fit — see § Pre-training gates below. |
| 11 | Sub-bar features from raw trades schema | **DECISION OWED** | Trade-size distribution, large-print frequency, time-weighted imbalance per bar. Beyond the 7 microstructure features. |
| 12 | Anti-leakage assertion baked into ETL | **LOCKED IN** | Codify check 8 from pre-audit skill (no IID bag leakage). |
| 13 | Earnings / CPI / NFP / PPI heads-up labels | **DECISION OWED** | FOMC is in. Kirk said "drop events" earlier but later listed earnings/CPI/NFP as MISSED. Need explicit yes/no per category. |
| 14 | Optuna directory `scripts/optuna/cards/{baseline,core_training,side_models}/` | **LOCKED IN** | Build before Core card writes. |
| 15 | Card filename naming convention | **LOCKED IN** | Filename: underscores (`2026_05_09_warbird_pro_autogluon_core.py`); display title: spelled out (`2026-05-09 - Warbird Pro Autogluon Core`). |

---

## Open decisions Kirk owes for Core scope

Tagging the items above marked DECISION OWED:

```
□ #3  Microstructure features (7 proposed) — yes / no / partial?
□ #4  Volume profile HVN/LVN — yes / no?
□ #5  Initial Balance + Opening Range — yes / no?
□ #6  Side cards — scaffold now or post-Core?
□ #7  Entry-filter Optuna profile MA wiring — refactor now or post-Core?
□ #8  Entry-filter Optuna profile schema rewrite — refactor now or skip?
□ #9  Footprint window strategy — A, B, or C?
□ #11 Sub-bar trades features — yes / no / partial?
□ #13 Events: earnings / CPI / NFP / PPI — yes / no per category (FOMC already in)?

Plus from earlier discussions (still open):
□ Time budget Finding 1 remediation — A (num_bag_folds=4), B (num_trials=10), C (bump to 6h), or accept current?
```

Until those answers exist, the Core card script does NOT get written.

---

## Data inventory (all local, no fresh downloads needed)

| Feature group | Source | Local path | Schema | Date range |
|---|---|---|---|---|
| MES OHLCV | Databento | `data/MES 1m 2010 GLBX-20260503-N6U6W7EDKU.zip` | ohlcv-1m | 2010-06-06 → 2026-05-31 |
| MES OHLCV (alt) | Databento | `data/MES 1m 2019 2026 GLBX-20260503-J9H7XNXFBT.zip` | ohlcv-1m | 2019-01-01 → 2026-05-31 |
| MES + NQ OHLCV | Databento | `data/MES NQ 2010GLBX-20260503-7NPBEX7NFV.zip` | ohlcv-1m | 2010-06-06 → 2026-05-31 |
| ES OHLCV (parity) | Databento | `data/ES 2010 2026 GLBX-20260503-MMNA8VPWFH.zip` | ohlcv-1m | 2010-06-06 → 2026-05-31 |
| CL OHLCV | Databento | `data/GLBX-20260503-QGNEGSBQDN.zip` | ohlcv-1m | 2010-06-06 → 2026-05-31 |
| ZT OHLCV | Databento | `data/GLBX-20260503-FDRMEM3EMX.zip` | ohlcv-1m | 2010-06-06 → 2026-05-31 |
| TN OHLCV | Databento | `data/GLBX-20260503-SYE7R843QV.zip` | ohlcv-1m | 2010-06-06 → 2026-05-31 |
| Cross-asset 1h (NQ/ZN/6E/6J/CL/HG/RTY) | Databento | `Historical Data/Databento/raw/databento_futures_ohlcv_1h.parquet` | ohlcv-1h | 2010-06 → 2025-12 |
| MES Trades (TICK) | Databento | `data/MES ES Trades GLBX-20260508-SAGMRP8P3H.zip` | trades | **2025-05-08 → 2026-05-08** (1yr) |
| VIX movement pressure fallback | FRED VIXCLS | `/Volumes/Satechi Hub/ZINC-FUSION-V15/data/downloads/VIXCLS.csv` | daily close-only pressure proxy | 1990-01-02 → 2026-01-29 |
| DXY | Yahoo `DX-Y.NYB` | NOT LOCAL — fetch via `yfinance` | daily | 1985 → present |

**Disk:** 515 GiB free on `/Volumes/Satechi Hub` — adequate (footprint expansion ~50GB).

---

## Pattern definitions (final 4 only) — for indicator + ETL

```pine
// Bull (1)
bool patRisingWindow  = bullishCandle and low > high[1]

// Bear (3)
bool patBearEngulf    = bearishCandle and bullishCandle[1] and close < open[1] and open > close[1]
bool patMarubozuBlack = bearishCandle and bodyRatio >= 0.85 and upperWickRatio <= 0.10 and lowerWickRatio <= 0.10
bool patTweezerTop    = bearishCandle and math.abs(high - high[1]) <= atr14 * 0.05 and bullishCandle[1]
```

ML features (4):
```python
ml_pat_rising_window
ml_pat_bear_engulf
ml_pat_marubozu_black
ml_pat_tweezer_top
```

Replaces the current 8.

---

## Pre-training hard gates (Kirk's directive: "make sure that shit is loaded")

Before AG.fit is called in the Core card, the script MUST assert ALL of the following. Any failure aborts the run before compute burns:

```python
# 1. Every column in ML_FEATURES exists in the assembled DataFrame
missing = [c for c in ML_FEATURES if c not in df.columns]
assert not missing, f"FATAL: missing features in dataset: {missing}"

# 2. Footprint columns have non-trivial data in the footprint-available window
fp_window = df[(df['ts'] >= pd.Timestamp('2025-05-08', tz='UTC')) &
               (df['ts'] < pd.Timestamp('2026-05-08', tz='UTC'))]
for col in ['ml_fp_delta_pct', 'ml_fp_poc_dist_atr', 'ml_fp_va_position']:
    nan_rate = fp_window[col].isna().mean()
    assert nan_rate < 0.01, f"FATAL: {col} {nan_rate:.1%} NaN in footprint window — reconstruction failed"
    assert fp_window[col].nunique() > 100, f"FATAL: {col} has < 100 unique values — reconstruction broken"

# 3. Cross-asset features non-zero (constant 0 = broken pull)
for col in ['ml_xa_nq_code', 'ml_xa_zn_code', 'ml_xa_dxy_code']:
    n_nonzero = (df[col] != 0).sum()
    assert n_nonzero > len(df) * 0.1, f"FATAL: {col} is {(df[col]==0).mean():.1%} zeros — pull broken"

# 4. VIX movement pressure has variance
assert df['ml_xa_vix_pressure'].std() > 0.1, "FATAL: ml_xa_vix_pressure is constant — VIX pressure pull broken"

# 5. Patterns fire on real bars (not all zeros)
for col in [c for c in ML_FEATURES if c.startswith('ml_pat_')]:
    fire_rate = (df[col] == 1).mean()
    assert fire_rate > 0.001, f"FATAL: {col} fires < 0.1% — pattern logic broken"
    assert fire_rate < 0.30, f"FATAL: {col} fires > 30% — pattern threshold too loose"

# 6. Trade dataset is non-degenerate
assert trades['winner_10pt_24bar'].sum() > 100, "FATAL: < 100 winning trades — labels broken"
assert trades['winner_10pt_24bar'].nunique() == 2, "FATAL: only one outcome class in dataset"
assert 0.10 < trades['winner_10pt_24bar'].mean() < 0.50, f"FATAL: WR {trades['winner_10pt_24bar'].mean():.2f} out of expected range"

# 7. Train/val/test all have both classes
for name, slice_df in [('train', train_df), ('val', val_df), ('test', test_df)]:
    assert slice_df['winner_10pt_24bar'].nunique() == 2, f"FATAL: {name} split missing a class"
    assert len(slice_df) >= 100, f"FATAL: {name} split has < 100 trades"

# 8. No timestamp leakage between splits (embargo violated check)
assert train_df['ts'].max() < val_df['ts'].min(), "FATAL: train/val timestamps overlap — leakage"
assert val_df['ts'].max() < test_df['ts'].min(), "FATAL: val/test timestamps overlap — leakage"
embargo_train_val = (val_df['ts'].min() - train_df['ts'].max()).total_seconds() / 60 / 5
assert embargo_train_val >= 73, f"FATAL: train→val embargo {embargo_train_val:.0f} bars < 73 required"
```

If ANY assertion fails, log the exact reason and exit nonzero. Don't run training.

---

## Core card scope (revised, post-pattern-cleanup)

| Aspect | Plan |
|---|---|
| **Filename** | `scripts/optuna/cards/core_training/2026_05_09_warbird_pro_autogluon_core.py` |
| **Display title** | `2026-05-09 - Warbird Pro Autogluon Core` (literal in Optuna hub UI) |
| **AG objective** | Binary classification: `winner_10pt_24bar` (1=+10pts before -5pts within 24 bars; neither-hit rows dropped) |
| **Eval metric** | `log_loss` (proper probability scoring + isotonic calibration) |
| **Data** | NEW dataset rebuilt from new V9 indicator + Databento trades + Yahoo DXY + VIX movement pressure fallback (see § Data inventory) |
| **Train/val/test** | Chronological with 73-bar embargo (max_hold_bars + 1). Window split per Kirk's decision on item #9. |
| **Feature set** | 45 features: 43 Pine-emitted features plus Python-only `ml_cvd_div_bull` / `ml_cvd_div_bear`. STRICT ASSERTION: no missing columns. |
| **Model zoo** | Full canonical 7-family: GBM, CAT, XGB, RF, XT, **NN_TORCH, FASTAI** (FastAI explicitly required per Kirk) |
| **Bagging / Stacking** | `num_bag_folds=0`, `num_stack_levels=0`, `use_bag_holdout=False`, `dynamic_stacking=False` |
| **Calibration** | `calibrate=True` (isotonic) |
| **Time budget** | 18000s (5h) — Kirk's directive |
| **HPO** | random searcher, num_trials=20 per family (subject to Finding 1 remediation) |
| **Optuna wrapper** | Hub at localhost:8090 spawns child dashboard on next free port (8100+). Single trial fits the AG run; not HPO over AG. |
| **SHAP** | After AG.fit, run `scripts/ag/shap_v9.py` on the saved predictor against the OOS test slice. |

---

## Optuna directory structure to create

```
scripts/optuna/cards/
├── baseline/
│   └── (May 8 ruined run — archive existing run dir as reference, no script)
│
├── core_training/
│   └── 2026_05_09_warbird_pro_autogluon_core.py
│
└── side_models/
    └── (per Kirk's decision on item #6)
```

Each card module exposes:
- `CARD_TITLE` constant (shown in Optuna hub UI)
- `register_with_hub()` function (registers to `localhost:8090`, spawns child port)
- `main()` that runs ETL → assertions → AG.fit → SHAP → write artifacts

---

## Outputs (locked structure)

```
models/warbird_pro_autogluon_core/
└── 2026_05_09_<HHMMSS>/
    ├── leaderboard.csv
    ├── feature_importance.csv
    ├── shap_values.parquet
    ├── shap_summary.png
    ├── summary.json                (includes git SHA, dataset hash, timing)
    ├── training.log
    ├── etl_assertions.log          (PRE-FIT gate output — proves data was clean)
    └── (AG predictor: predictor.pkl, learner.pkl, models/, metadata.json)
```

---

## Pre-audit results (just executed)

| Check | Result |
|---|---|
| Trades zip integrity | ✓ unzip -t clean, manifest matches |
| Orphan training processes | ✓ none (only Optuna hub idle) |
| Python + AG environment | ✓ python3 3.12.8, AG 1.5.0, all ETL libs present |
| Schema parity (indicator vs ML_FEATURES) | ✓ 49 Pine `ml_*` outputs = 43 Pine features + 6 telemetry; trainer adds 2 ETL CVD features for 45 total |
| Optuna hub state | ✓ port 8090 LISTEN, ready |
| OMP guards | ✓ in place before AG/lightgbm imports |
| Disk space | ✓ 515 GiB free |
| Git state | clean after `training-prep` commit |
| Time budget math | No inner bagging/stacking; keep `best_quality` but `num_bag_folds=0`, `num_stack_levels=0`. |
| Inner-bag IID leakage | Avoided by disabling bagging/stacking for this time-series run. |

---

## What NOT to do (lessons from May 8)

1. **DO NOT train on a partial feature set.** If the dataset is missing any feature in `ML_FEATURES`, ABORT. Don't use `[c for c in ML_FEATURES if c in df.columns]` as a workaround.
2. **DO NOT skip features Kirk says to add** based on prior runs' importance scores. (Patterns ranked low on May 8 partial-feature run; that doesn't mean they don't matter when paired with the missing features.)
3. **DO NOT defer items to "later" without explicit confirmation.** Default is "include now."
4. **DO NOT name things ambiguously.** Banned: V*, AG Meta, anything that needs a decoder ring. Use spelled-out card titles.
5. **DO NOT save memories then make the same mistake an hour later.** The memories ARE the contract. Read them, follow them.
6. **DO NOT push Pine without verification.** Pine compile + lint + guards + manual chart check.
7. **DO NOT start the 5h training run without all gate assertions passing.** The PR gate logs go to `etl_assertions.log`.

---

## Memory file paths (read at start of next chat)

```
/Users/zincdigital/.claude/projects/-Volumes-Satechi-Hub-warbird-pro/memory/
├── MEMORY.md                                    (index)
├── feedback_train_full_feature_set.md           (don't split features)
├── feedback_listen_when_kirk_says_add.md        (do what Kirk says)
├── feedback_ag_visible_in_optuna.md             (Optuna hub wiring required)
├── project_dxy_not_dx.md                        (DXY naming)
└── feedback_always_verify_before_completion.md  (verify before done)
```

Memory dir alt path (if symlinked):
`/Volumes/Satechi Hub/warbird-pro-state/claude-project-memory/`

---

## What's committed at the time of this handoff

```
HEAD = 32fce60   training-prep: V9 indicator rebuild + AG/Optuna profile updates
HEAD~ = e692319  chore: gitignore .claude-state/ after consolidating project folders
```

Untracked (NOT in this handoff's scope):
- `app/`, `components/`, `lib/`, `supabase/` UI/infra edits — separate concern
- 2 supabase migrations — separate concern
- `scripts/maintenance/update-claude-plugins.sh` — utility

---

## Resumption checklist for next chat

1. ✓ Read `MEMORY.md` and the 5 referenced memory files
2. ✓ Read this handoff doc end-to-end
3. ✓ Run pre-audit (see § Pre-audit) — fresh, don't trust this snapshot
4. ✓ Ask Kirk to resolve open decisions (§ Open decisions Kirk owes)
5. ✓ Apply pattern cleanup to indicator (drop 4 unused) + push + verify on TV
6. ✓ Apply DXY rename pass (indicator + downstream code) + push + verify
7. ✓ Apply Kirk's confirmed answers from open decisions
8. ✓ Build the ETL script (footprint reconstruction + cross-asset alignment + indicator math replication)
9. ✓ Run ETL → verify dataset against pre-training hard gates
10. ✓ Build the Core card script (`scripts/optuna/cards/core_training/2026_05_09_warbird_pro_autogluon_core.py`)
11. ✓ Wire Core card into Optuna hub at localhost:8090
12. ✓ Show Kirk the final scope + dataset gate output
13. ✓ Get green light
14. ✓ Launch — visible in Optuna hub UI, watchable live
15. ✓ Post-train: SHAP + Monte Carlo + summary written
