# Warbird v8 — SuperTrend + TQI Execution Supplement

**Status:** ACTIVE execution supplement for Phase 4 (governance authority remains `docs/MASTER_PLAN.md`)  
**Approved:** 2026-04-16  
**Architect:** Kirk Musick  
**Collaborators:** Claude (architecture, Pine, SHAP/MC, review), GPT Codex (Python pipeline, SQL, data engineering)

---

## Why This Exists

The prior ZigZag-fib path produced unstable direction state and parity drift between chart behavior and labels.
This v8 lane locks a deterministic SuperTrend + TQI workflow with strict Pine↔Python parity controls.

---

## Architecture Summary

### Pine Skeleton (Locked Baseline)

**Base framework: locked inherited baseline [WillyAlgoTrader] — verbatim Pine skeleton for Phase 1 live surface.**

No blocks are adopted from Precision Sniper, Fibonacci Structure Engine, or Smart Money Engine in Phase 1.
Those three remain reference-only until post-SHAP contract revision and Kirk approval.

### Python Feature Layer (Indicator-Only)

Python computes training features from `mes_15m` OHLCV + timestamp only.
No external plot import and no TradingView export dependency.

Phase 1 indicator-only features (12):

`er`, `vol_ratio`, `tqi_struct`, `tqi_mom`, `tqi`, `atr14`, `direction`, `in_ote_zone`, `structure_event`, `htf_bias`, `hour_bucket`, `session_type`

### Semantics Resolver

Execution ordering and same-bar conflict handling are governed by:

- `docs/contracts/st_execution_semantics.md`

This resolver is canonical for both Pine (Slice 9) and Python labeling (Slices 3/4).

### Training Grid

| Dimension | Candidates | Count |
|---|---|---|
| ATR Period | 7, 10, 14, 21 | 4 |
| ATR Multiplier | 2.0, 2.5, 3.0, 3.5, 4.0 | 5 |
| ATR Method | `atr`, `sma_tr` | 2 |
| Source | `hl2`, `close`, `ohlc4` | 3 |
| SL ATR Mult | 0.62, 0.80, 1.00, 1.20 | 4 |
| **Flip grid total** | | **480** |
| TP Mode | Fixed, Dynamic | 2 |
| TQI Influence | 0.2, 0.4, 0.6, 0.8 | 4 |
| Vol Influence | 0.2, 0.4, 0.6, 0.8 | 4 |
| Min TP Scale | 0.5, 0.7, 1.0 | 3 |
| Max TP Scale | 1.5, 2.0, 3.0 | 3 |
| TP1 Floor (R) | 0.5, 0.75, 1.0 | 3 |
| TP3 Ceiling (R) | 4.0, 6.0, 8.0 | 3 |
| **TP grid total** | | **2,592** |
| **Combined** | | **1,244,160 policy combos** |

Minimum sample floor: `N >= 30` per `(flip_cfg_id, tp_cfg_id, regime_slice)`.
Below floor => `INSUFFICIENT`, excluded from training.

### Canonical Row Key

`(signal_id, flip_cfg_id, tp_cfg_id)`

---

## WillyAlgoTrader Source Reference

All four indicators are open-source on TradingView.

| Indicator | Role in v8 |
|---|---|
| Locked inherited baseline | Base framework — Pine v8 skeleton (verbatim) |
| Precision Sniper | Reference only — TP/SL state machine pattern |
| Fibonacci Structure Engine | Reference only — fib anchor lifecycle pattern |
| Smart Money Engine | Reference only — OB/FVG/BOS/CHoCH pattern |

Phase 1 uses the locked inherited baseline skeleton only. The other three are not code donors until SHAP proves need.

---

## Hard Constraints

1. 15m is the parent timeframe. SuperTrend flip on confirmed 15m bar close only.
2. Features freeze at signal bar close. No lookahead of any kind.
3. Walk-forward splits only. One-session embargo minimum. No shuffle. No fit on full dataset.
4. Pine v8 indicator framework is the locked inherited baseline skeleton. No other code donors in Phase 1.
5. AG feature set is 12 indicator-derived features from `mes_15m` OHLCV + timestamp in Python.
   `in_ote_zone` and `structure_event` are Python-side features, not Pine plot exports.
6. Cloud never receives `st_signals`, `st_outcomes`, raw features, raw labels, or raw SHAP.
7. Prescreen uses in-sample windows only (`2020-01-01` through `2023-12-31`).
   OOS fold (`2024-01-01` onward) is untouched until config selection is locked.
8. TV entry/exit semantics must match Python exactly.
   Authority: `docs/contracts/st_execution_semantics.md`. Any discrepancy is a bug.
9. No flip config enters Slice 3 without a `pass=true` row in `st_prescreen_ledger`.
10. No FRED fields in Phase 1 training. `st_signals` is indicator-only.
11. `+FRED` is a challenger model only. It runs after Pine v8 is Kirk-approved on live chart and parity audit passes.
12. Slice 9 Pine budget check (`trading-indicators:pine:budget` skill) is a required DoD gate.
13. **CODE FREEZE (2026-04-17): `indicators/v8-warbird-live.pine` and `indicators/v8-warbird-prescreen.pine`
    are locked for code changes. The ONLY permitted modification is adjusting `input.*` default values
    for settings optimization (e.g., ATR length, multiplier presets). No structural edits, no new code
    blocks, no geometry changes, no signal logic changes, no new outputs. These files define the
    training signal surface; code changes invalidate the model contract and corrupt the config grid.**

---

## Collaboration Model

| Role | Responsibilities |
|---|---|
| **Kirk** | Approves each slice before next begins. Rules on architecture and final contract locks. |
| **Claude** | Architecture, schema design, Pine v8 build, AG training script, SHAP/MC analysis, Codex output review. |
| **GPT Codex** | Python pipeline (signal extraction, labeling), SQL migrations, validation scripts, checklist evidence. |

**Protocol:** Claude reviews all Codex output. Kirk approves slice close. Next slice does not start early.

**Codex handoff per slice includes:**
1. Schema contract (exact names/types)
2. Input spec (source data + boundaries)
3. Output spec (required artifacts)
4. Validation criteria (proof of correctness)
5. Leakage rules (explicitly forbidden paths)

## Approval & Drift Gate

### Required Gate Flow (mandatory on every slice)
1. Claude defines slice contract (schema / input / output / validation / leakage rules)
2. Kirk approves contract — no implementation starts without this
3. Codex executes only approved scope
4. Claude reviews outputs, diff, and validation evidence
5. Kirk approves slice close — next slice cannot start without this

### Drift Controls
- No schema edits without migration + ledger verification
- No contract changes without doc updates (`WARBIRD_V8_PLAN.md` + relevant contracts)
- No promotion/live cutover without full validation artifacts

---

## Slices

Slice order is fixed:

`Slice 1 -> Slice 2 -> Slice 2b -> Slice 3 -> Slice 4 -> Slice 5 (DEFERRED) -> Slice 6 -> Slice 7 -> Slice 8 -> Slice 9 -> Slice 10`

### Slice 1 — Schema & Migration

**What:** New local warehouse tables for SuperTrend training lane (`st_` namespace)  
**Deliverable:** `local_warehouse/migrations/018_st_training_schema.sql`

**DDL contract:**

```sql
CREATE TABLE st_run_config (
    run_id      TEXT PRIMARY KEY,
    oos_start   TIMESTAMPTZ NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    notes       TEXT
);

CREATE TABLE st_flip_configs (
    flip_cfg_id  SERIAL PRIMARY KEY,
    atr_period   INTEGER      NOT NULL,
    atr_mult     NUMERIC(4,2) NOT NULL,
    atr_method   TEXT         NOT NULL,
    source_id    TEXT         NOT NULL,
    sl_atr_mult  NUMERIC(4,2) NOT NULL,
    UNIQUE (atr_period, atr_mult, atr_method, source_id, sl_atr_mult)
);

CREATE TABLE st_tp_configs (
    tp_cfg_id     SERIAL PRIMARY KEY,
    tp_mode       TEXT         NOT NULL,
    tqi_influence NUMERIC(3,2) NOT NULL,
    vol_influence NUMERIC(3,2) NOT NULL,
    min_tp_scale  NUMERIC(3,2) NOT NULL,
    max_tp_scale  NUMERIC(3,2) NOT NULL,
    tp1_floor_r   NUMERIC(4,2) NOT NULL,
    tp3_ceil_r    NUMERIC(4,2) NOT NULL,
    UNIQUE (tp_mode, tqi_influence, vol_influence, min_tp_scale,
            max_tp_scale, tp1_floor_r, tp3_ceil_r)
);

CREATE TABLE st_signals (
    signal_id       SERIAL PRIMARY KEY,
    run_id          TEXT         NOT NULL REFERENCES st_run_config(run_id),
    ts              TIMESTAMPTZ  NOT NULL,
    flip_cfg_id     INTEGER      NOT NULL REFERENCES st_flip_configs(flip_cfg_id),
    direction       SMALLINT     NOT NULL,
    tqi             NUMERIC(6,4),
    er              NUMERIC(6,4),
    vol_ratio       NUMERIC(6,4),
    tqi_struct      NUMERIC(6,4),
    tqi_mom         NUMERIC(6,4),
    atr14           NUMERIC(10,4),
    in_ote_zone     BOOLEAN,
    structure_event SMALLINT,
    htf_bias        SMALLINT,
    hour_bucket     SMALLINT,
    session_type    TEXT,
    UNIQUE (ts, flip_cfg_id, run_id)
);

CREATE TABLE st_outcomes (
    outcome_id              SERIAL PRIMARY KEY,
    signal_id               INTEGER      NOT NULL REFERENCES st_signals(signal_id),
    tp_cfg_id               INTEGER      NOT NULL REFERENCES st_tp_configs(tp_cfg_id),
    outcome_label           TEXT         NOT NULL,
    realized_r              NUMERIC(8,4),
    bars_to_outcome         INTEGER,
    mae                     NUMERIC(10,4),
    mfe                     NUMERIC(10,4),
    pts_to_survive_to_tp1   NUMERIC(8,4),
    pts_to_survive_to_tp2   NUMERIC(8,4),
    min_stop_atr_to_tp1     NUMERIC(8,4),
    UNIQUE (signal_id, tp_cfg_id)
);

CREATE TABLE st_prescreen_ledger (
    prescreen_id   SERIAL PRIMARY KEY,
    run_id         TEXT         NOT NULL REFERENCES st_run_config(run_id),
    flip_cfg_id    INTEGER      NOT NULL REFERENCES st_flip_configs(flip_cfg_id),
    window_start   TIMESTAMPTZ  NOT NULL,
    window_end     TIMESTAMPTZ  NOT NULL,
    n_signals      INTEGER      NOT NULL,
    win_rate       NUMERIC(6,4),
    profit_factor  NUMERIC(8,4),
    avg_r          NUMERIC(8,4),
    max_drawdown_r NUMERIC(8,4),
    pass           BOOLEAN      NOT NULL,
    fail_reason    TEXT,
    run_ts         TIMESTAMPTZ  NOT NULL DEFAULT now(),
    UNIQUE (flip_cfg_id, run_id)
);
```

**Owner:** Claude drafts, Codex executes  
**DoD:** Migration applies clean in local `warbird`; schema documented

---

### Slice 2 — Config Grid Population

**What:** Populate `st_flip_configs` (480 rows) and `st_tp_configs` (2,592 rows)  
**Owner:** Codex writes population script, Claude reviews  
**Validation:** row counts exact; full cartesian completeness; no duplicates  
**DoD:** both tables populated; completeness test passes

---

### Slice 2b — TV Prescreen (Coarse Config Filter)

**Owner:** CDP tuner sweep, Codex ledger insert, Claude review, Kirk approve

**Pine prescreen (v8-warbird-prescreen.pine): COMPLETE — 2026-04-18**
- Locked inherited baseline + strategy wrapper (strategy() declaration,
  entry/exit execution block, barstate.islast removed from dashboard+watermark gates).
  TV smart_compile clean, pine-facade clean, delta=19 lines vs live (within 8-20 tolerance).
  Commit bcb4d92 (entry execution fix). **File is now CODE-FROZEN (Hard Constraint 13).**

**Entry execution semantics (Hard Constraint 8):**
- `process_orders_on_close = true` — all fills at bar close, not next-bar open.
- Entry block is OUTSIDE confirmedBuy/confirmedSell. Fires on any post-flip bar.
- Gate: `bar_index > tradeEntryBar` prevents entry on the flip bar itself.
- Trigger: `close <= tradeEntry` (long) / `close >= tradeEntry` (short) — bar close must
  reach or cross through the gray ENTRY line before any fill.
- `strategy.position_size == 0` prevents pyramiding and re-entry while already in trade.
- `strategy.exit` uses `stop = tradeSl, limit = tradeTp3` on the same bar as entry.
- Python labeling in Slice 3 must replicate these semantics exactly.

**What:** Run all 480 flip configs through TV Deep Backtesting on in-sample window only (`2020-01-01` through `2023-12-31`). Persist results to `st_prescreen_ledger`.

Pass criteria (both required):
- `profit_factor >= 1.0`
- `n_signals >= 100`

Drift controls:
1. In-sample only. OOS fold (`2024-01-01+`) untouched during prescreen.
2. TV semantics must match `docs/contracts/st_execution_semantics.md` exactly.
3. No config promoted to Slice 3 without `pass=true` ledger row.
4. Config selection is locked before OOS fold opens; no revisiting after.

**DoD:** `st_prescreen_ledger` has all 480 configs, pass count documented, Kirk approves survivors.

---

### Slice 3 — Signal Extraction Pipeline

**What:** Python runs surviving flip configs across MES 15m history and writes `st_signals`.

Features frozen at signal bar close:
- `er`, `vol_ratio`, `tqi_struct`, `tqi_mom`, `tqi`, `atr14`
- `direction`, `in_ote_zone`, `structure_event`
- `htf_bias`, `hour_bucket`, `session_type`

**Owner:** Codex implements, Claude reviews leakage/parity  
**DoD:** `st_signals` populated by `run_id`; no future-bar leakage

---

### Slice 4 — TP Outcome Labeling

**What:** Label each `(signal, tp_cfg)` over a forward 32-bar window.

Labels:
- `STOPPED`
- `TP1_ONLY`
- `TP2_HIT`
- `TP3_HIT`
- `CENSORED`

Resolver authority: `docs/contracts/st_execution_semantics.md`.

#### SL Ranking Leaderboard

- `pts_to_survive_to_tp1` and `pts_to_survive_to_tp2` are populated for `STOPPED` rows only.
- `min_stop_atr_to_tp1` uses `eff_atr = raw_atr * (0.5 + 0.5 * er)`, not raw ATR.

**Owner:** Codex implements, Claude reviews label correctness  
**DoD:** `st_outcomes` populated; label distribution + parity checks pass

---

### Slice 5 — FRED Macro Enrichment — DEFERRED (Challenger Model Only)

Blocked until:
- Pine v8 (Slice 9) is Kirk-approved on live chart
- Pine↔Python feature parity audit passes

Not in active file map. Not executable in Phase 1.

---

### Slice 6 — AG Training

**What:** Walk-forward training over `(signal_id, flip_cfg_id, tp_cfg_id)` rows.

- Target: `outcome_label` (multiclass)
- Embargo: one full session minimum
- No shuffle, no IID bagging

**Owner:** Claude adapts trainer, Codex validates fold boundaries  
**DoD:** OOS metrics beat baseline with leakage checks passing

---

### Slice 7 — SHAP Analysis

**What:** Feature importance and interaction analysis by regime and config family  
**Owner:** Claude runs SHAP, Codex verifies artifact shape and schema alignment  
**DoD:** SHAP summary committed; follow-on feature decisions documented

---

### Slice 8 — MC Sweep

**What:** Rank `(flip_cfg, tp_cfg)` policy combos per regime slice using EV, win rate, PF, max drawdown, Sharpe.

Required artifact:

`artifacts/sl_leaderboard/regime_{regime_id}.csv`

Columns:

`rank | sl_atr_mult | win_rate | trades | avg_r | median_r | pct_stopped_early_fixable`

AG output per regime must surface ranked SL options (rank 1/2/3).

**Owner:** Claude runs MC, Codex validates outputs and contract columns  
**DoD:** regime policy map + SL leaderboard artifacts produced

---

### Slice 9 — Pine v8 Build

**What:** `indicators/v8-warbird-live.pine` live indicator

Components:
- Locked inherited baseline skeleton
- TQI dashboard state and regime readout
- AG recommendation slot
- MES guardrails (RTH opening suppressor, 0.25 tick awareness)
- Robust styling options surface for dashboard/table appearance

#### Colored Bars

`barcolor()` call (+1 output unit against Pine budget).

Bar coloring is required in the v8 build.
Runtime control is via the indicator's native Style tab; users may disable bar
coloring there without removing the feature from the script.

Color map:
- bull = teal, bear = red
- `tqi >= 0.65`: 0% transparency
- `0.40 <= tqi < 0.65`: 45% transparency
- `tqi < 0.40`: 75% transparency

`barcolor(bar_col)`

When the Style-tab bar color output is disabled, no override is applied and
Kirk's TV candle colors remain unchanged.

#### Styling Options Surface

A robust styling options area is required in the Pine surface.

Minimum appearance controls:
- table area colors
- font/text styling controls
- background colors
- related dashboard appearance settings needed to theme the live readout cleanly

**DoD gate:** `trading-indicators:pine:budget` skill must pass before Slice 9 can close.

---

### Slice 10 — Live Integration

**What:** Regime policy output feeds live table state in Pine surface  
**Owner:** Claude architecture, Codex data plumbing  
**DoD:** live table updates with current regime recommendations

---

## File Map (Active)

```text
local_warehouse/migrations/018_st_training_schema.sql      <- Slice 1
scripts/ag/populate_st_configs.py                          <- Slice 2
indicators/v8-warbird-prescreen.pine                       <- Slice 2b (locked inherited baseline + strategy() declarations)
scripts/ag/run_st_prescreen.py                             <- Slice 2b (CDP sweep + ledger insert)
scripts/ag/extract_st_signals.py                           <- Slice 3
scripts/ag/label_st_outcomes.py                            <- Slice 4
scripts/ag/train_st_baseline.py                            <- Slice 6
scripts/ag/run_st_shap.py                                  <- Slice 7
scripts/ag/run_st_mc.py                                    <- Slice 8
indicators/v8-warbird-live.pine                            <- Slice 9
scripts/ag/publish_st_policy.py                            <- Slice 10
docs/contracts/st_execution_semantics.md                   <- Semantics authority
```

## Deferred / Challenger Only

- Slice 5 (FRED Macro Enrichment): blocked on Phase 1 parity proof

---

## Validation Checklist (v2.2)

- [x] `MASTER_PLAN.md` Phase 4 has v8 cross-reference
- [x] `AGENTS.md` has v8 execution-front note + indicator-only override
- [x] `AGENTS.md` includes `st_` prefix in naming
- [x] `AGENTS.md` stop-floor language updated (`0.618` minimum candidate; live enforces)
- [x] `docs/INDEX.md` cross-reference to v8 supplement added
- [x] `docs/contracts/st_execution_semantics.md` exists
- [x] Hard Constraints contains items 1–12
- [x] Slice order is `1 -> 2 -> 2b -> 3 -> 4 -> 5(DEFERRED) -> 6 -> 7 -> 8 -> 9 -> 10`
- [x] `st_flip_configs` grid supports 480 combos and includes `sl_atr_mult`
- [x] `source_id` excludes `fib_0618` — enforced via DB CHECK (`hl2`, `close`, `ohlc4` only); applied 2026-04-17
- [x] `st_signals` has `run_id` and `UNIQUE (ts, flip_cfg_id, run_id)`
- [x] `st_prescreen_ledger` has `run_id` FK and `UNIQUE (flip_cfg_id, run_id)`
- [x] Slice 5 is DEFERRED and removed from active file map
- [x] Slice 9 colored bars spec ships with Style-tab runtime toggle and budget gate
- [x] Slice 9 styling options surface covers table areas, font/text styling, and backgrounds
- [x] Slice 4 and Slice 8 include SL leaderboard requirements
- [x] Migration `018_st_training_schema.sql` exists and applies cleanly — DB verified 2026-04-17; ledger entry confirmed
- [x] `v8-warbird-prescreen.pine` strategy wrapper: TV smart_compile clean, pine-facade clean, delta=19 lines, commit bcb4d92 (2026-04-18) — entry execution: close-at/through ENTRY line on post-flip bar
- [x] `v8-warbird-live.pine` CW10003/CW10004 hoist + presetInput="Custom": TV compile clean, commit cd5cbd5 (2026-04-17)
- [x] Hard Constraint 13 (v8 code freeze) added — settings optimization only, no code changes
