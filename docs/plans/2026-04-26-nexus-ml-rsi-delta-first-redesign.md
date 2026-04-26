# Nexus ML RSI — Delta-First Redesign Design Doc
**Date:** 2026-04-26  
**Status:** ACTIVE REPAIR — Pine footprint surface restored; TradingView export manifest required before Optuna launch
**Indicator:** `indicators/warbird-nexus-machine-learning-rsi-optuna-fast-test.pine`

---

## QA Takeover Decision

This design is not launch-ready for a new Optuna batch until a TradingView/Pine
export manifest exists. The delta-first concept remains valid, and the active
Nexus profile now requires exported `nexus_fp_*` fields from `request.footprint()`
instead of accepting local OHLCV/parquet delta proxies.

Study A must stay blocked until the project has:

- exact indicator source path, version, and commit
- symbol and timeframe
- Pine input defaults
- exported columns or Strategy Tester fields
- trigger family `NEXUS_FOOTPRINT_DELTA`
- plot/request budget and compile/lint status
- TradingView export or CDP evidence
- manifest with row/trade count, date range, export method, and export hash

If Nexus is intentionally reopened as a pure sandbox, that decision must be
documented explicitly first. Sandbox outputs cannot be called champion settings
and cannot be promoted to Pine defaults.

Implementation note: `warbird_nexus_ml_rsi_profile.py` now refuses to load
without `scripts/optuna/workspaces/warbird_nexus_ml_rsi/pine_export_manifest.json`
or `WARBIRD_NEXUS_EXPORT_MANIFEST`. The manifest must point at a TradingView
CSV export containing the hidden `nexus_fp_*` footprint fields.

---

## Why We're Rebuilding

The prior Optuna study produced a score of 0.402 because the objective function was fundamentally wrong:

- `favorable_atr = 0.50` / `adverse_atr = 0.50` hardcoded — rewarded half-ATR scalp ticks, not real legs
- `ENTRY_RESPONSE_BARS = 5` hardcoded — 25 minutes is too short for swing entry evaluation
- 33 parameters with sub-1000 trial coverage = thin coverage (TPE needs ~330 trials just to warm up)
- Volume: only body/wick-weighted signed volume (VNVF) — no footprint delta, no true order flow
- Mode presets (Scalping/Default/Swing/Position): only Default unlocked fine-grained numeric tuning

Kirk's actual success criterion: **signal at the bottom (or top) that precedes a 10+ point reversal leg**. The prior objective didn't score for this at all.

---

## Approved Architecture: Option A — Delta-First, Oscillator Confirms

### Core Principle
True footprint cumulative delta is the **target primary signal driver**. The oscillator (AMF: ROC + EWI + Stoch) is confirmation only. KNN is trained on exported Pine/TradingView delta features to validate conviction.

The existing indicator visual style is PRESERVED — smooth AMF wave, gradual color fills, positioned diamonds. The redesign layers delta intelligence on top without changing the core oscillator math.

Historical Python runs computed synthetic OHLCV delta, not true footprint delta.
Do not treat those outputs as active tuning evidence.

---

## Signal Tier System

| Tier | Shape | Bull Color | Bear Color | Condition |
|------|-------|-----------|-----------|-----------|
| Confirmed reversal | Diamond | `#26C6DA` (Warbird teal) | `#cc0000` (Warbird red) | Delta flip + cumulative delta diverging + oscillator crossed + KNN voting reversal |
| Gassing out | White diamond | `#FFFFFF` (faded) | `#FFFFFF` (faded) | Price at extreme, delta flat/declining, NOT yet reversing — early warning |
| Weak signal | Yellow dot | `#FFCC00` | `#FFCC00` | Oscillator signal but low volume / KNN neutral |
| No signal | (none) | — | — | All gates inconclusive |

**Critical suppression rule:** Red diamonds do NOT print when price is in the green zone and continuing higher. A red/bear diamond requires actual delta flip confirmation — not just an oscillator dip during a climb.

---

## Brand Color System

All colors sourced from the Warbird Pro codebase (`components/dashboard/`):

```
WARBIRD_BULL    = #26C6DA  // Warbird teal — matches dashboard LONG color
WARBIRD_BEAR    = #cc0000  // Warbird red — from eagle SVG logo
WARBIRD_WARN    = #FFFFFF  // White — gassing out / momentum fade
WARBIRD_WEAK    = #FFCC00  // Yellow — low confluence heads-up
WARBIRD_NEUTRAL = #888888  // Gray — transition / no conviction
```

---

## Bar Color Fade System

Bars on the price chart are colored by delta conviction. As cumulative delta weakens, bars fade toward near-invisible gray. When delta flips, the new color starts at low saturation and builds conviction as the new leg develops.

```
delta_strength = normalized cumulative delta (0.0 to 1.0)
transparency   = 100 - int(delta_strength × 85)
// 15% opacity at full conviction → ~90% opacity fading out

barcolor = delta_dir == 1  → color.new(#26C6DA, transparency)
           delta_dir == -1 → color.new(#cc0000, transparency)
           else             → color.new(#888888, 80)
```

Visual reference approved: the fade behavior matches the reference indicator screenshot shared 2026-04-26 — color burns bright at conviction, fades to near-invisible as volume thins.

---

## Volume Architecture — Target Footprint Cumulative Delta

**Research basis:** Cumulative delta divergence + bar-level order flow imbalance is the highest research-proven method for detecting 5m MES reversal setups (CME microstructure research, VSA/auction theory literature).

**Active implementation requirement via `request.footprint()` or exported Pine fields:**
- Bar delta = `ask_volume − bid_volume` per bar
- Cumulative delta = rolling sum over `delta_lookback` bars
- Normalized cumulative delta = cumulative delta / (avg_bar_volume × lookback)

The prior Python profile's `body_direction × body_ratio × volume` helper was
synthetic OHLCV delta. The active profile must not use that proxy as footprint
evidence.

**Gassing out signature → White diamond:**
- Price making new high (or continuing) across 2–3 bars
- Bar-level delta declining per bar — less buying power behind the move
- Cumulative delta still positive but slope flattening

**True reversal signature → Teal/Red diamond (all three required):**
1. Price at extreme (oscillator in OB/OS zone)
2. Delta flip: first bar where `bid_vol > ask_vol` after a bullish sequence
3. Cumulative delta diverging from price direction

**KNN features (trained on exported delta + price state):**
- `delta_slope` — rate of change of bar delta over N bars
- `norm_cumulative_delta` — cumulative delta normalized by avg bar volume
- `bar_delta_ratio` — `(ask − bid) / total_volume` per bar (range: −1 to +1)
- `price_position` — where in the bar's range price closed
- `oscillator_value` — current AMF oscillator reading

Each feature must be present in, or deterministically derived from, the same
TradingView/Pine export named by the run manifest.

---

## Optuna: Behavioral Discovery

### The Job
After the Pine/TradingView baseline is locked, find what volume, KNN, price action, footprint delta, and imbalance ALL did before large moves. Define the repeating behavior signature. Watch when it replicates. Watch when it breaks down and fails — what caused the failure. Tune to detect success setups and suppress failure-mode lookalikes.

Do not launch this study from raw OHLCV parquet under an active tuning or
promotion frame. Raw OHLCV reconstruction is prohibited as canonical active
model truth by `WARBIRD_MODEL_SPEC.md`.

### Two Labeled Datasets
- **Success set:** Bars in the N bars BEFORE a confirmed 10+ point leg started
- **Failure set:** Bars where the signature appeared but the move did NOT materialize

KNN trains on both sets. Optuna rewards: correctly identifying success setups + correctly suppressing failure-mode impostors.

### Formerly Hardcoded Constants — Now All Tunable Per Mode

| Parameter | Old (hardcoded) | New (tunable) |
|-----------|----------------|--------------|
| `favorable_atr = 0.50` | hardcoded | → `leg_threshold_pts` (actual MES points) |
| `adverse_atr = 0.50` | hardcoded | → tunable |
| `ENTRY_RESPONSE_BARS = 5` | hardcoded | → `response_bars` |
| `FAST_RESPONSE_BARS = 3` | hardcoded | → `early_bars` |
| (new) | — | `delta_lookback` |
| (new) | — | `delta_slope_len` |
| (new) | — | `gasout_stall_bars` |

### Objective Formula

```
score = 0.40 × reversal_precision           # diamonds catch real 10+ pt legs
      + 0.25 × early_entry_quality          # leg starts fast after signal
      + 0.15 × gasout_accuracy              # white diamonds correctly flag pauses
      + 0.10 × false_continuation_avoidance # penalize diamonds in trending zones
      + 0.10 × signal_rate_band_score       # signal frequency in target band
```

---

## Mode Architecture — One Indicator, One Active Hub Study

The only active Nexus route is the existing hub study:
`warbird_nexus_ml_rsi` / `Warbird Nexus ML Fast 5m Signal Quality April 25`.
Do not create duplicate per-timeframe Optuna profiles or study keys. Multi-mode
Pine presets can be reconsidered only after the canonical 5m lane has
manifest-backed Pine/TradingView evidence.

| Route | Chart TF | Current status | Evidence class |
|------|----------|----------------|----------------|
| `warbird_nexus_ml_rsi` | 5m | Existing hub sandbox study | Non-promotable until Pine/TradingView manifest exists |

---

## Additional Pine Deliverables

- **White diamond tier** — gassing out detection, printed when delta is fading but not yet flipped
- **Bear color fix** — change from current orange-red to `#cc0000` (Warbird red from logo SVG)
- **Watermark** — `Show Watermark` input already exists in indicator; enable by default (was unchecked)

---

## What Is NOT Changing

- Core AMF oscillator math (ROC + EWI + Stoch blend) — smoothness and speed preserved
- `v7-warbird-institutional.pine` — LOCKED, not touched
- `v7-warbird-strategy.pine` — LOCKED, not touched

---

## Implementation Phases (for writing-plans)

**Phase 1 — Optuna profile rebuild (existing Nexus lane, 1000-trial batches)**
- Rebuild `warbird_nexus_ml_rsi_profile.py` to load a manifest-backed
  Pine/TradingView export before active Study A
- Reject OHLCV/parquet delta proxies so they cannot be mistaken for footprint
  delta
- Make leg_threshold_pts, response_bars, early_bars, delta_lookback all tunable
- Build pre-move success set + failure set labeling logic
- Rewrite objective function with new formula
- Run the existing `warbird_nexus_ml_rsi` lane at 1000 trials only after the
  baseline/export gate passes

**Phase 2 — Pine indicator update**
- Blocked until explicit current-session Pine approval, Pine budget pricing, and
  a manifest-backed true footprint/export field source exist
- Add true footprint delta computation layer from ask/bid evidence only
- Add white diamond tier (gassing out detection)
- Update bar coloring to delta-fade system (`#26C6DA` / `#cc0000`)
- Fix bear color to `#cc0000`
- Add Mode input (5m / 15m / 1H / 4H)
- Enable watermark by default

**Phase 3 — Retired duplicate mode-study proposal**
- Do not create separate Nexus 15m, 1H, or 4H Optuna profile modules.
- Do not add duplicate registry keys for per-timeframe Nexus studies.
- Keep all current Nexus trials on the existing `warbird_nexus_ml_rsi` hub lane.

---

## Progress Table

| Phase | Task | Status | Notes |
|-------|------|--------|-------|
| Brainstorm | Context exploration | DONE | Profile analyzed, objective gaps identified |
| QA takeover | Strict contract decision | DONE | Nexus is not exempt when outputs drive settings, defaults, Pine changes, or champion claims |
| Phase 0 | Pine/TradingView baseline + manifest | BLOCKED | Required before active Optuna launch |
| Phase 1 | Optuna profile rebuild (5m) | BLOCKED | Promotable loader gate still requires manifest-backed Pine/TradingView rows |
| Phase 2 | Pine indicator update | BLOCKED | Requires explicit Pine edit approval, budget pricing, compile/lint path, and true footprint/export fields |
| Phase 3 | Duplicate mode-study proposal | RETIRED | Use the existing `warbird_nexus_ml_rsi` hub lane only |
