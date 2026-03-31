# AG Model Concept — Archived from Active Plan

**Date archived:** 2026-03-31
**Canonical version:** See `WARBIRD_MODEL_SPEC.md` at repo root.
**Reason:** Content duplicates WARBIRD_MODEL_SPEC.md. Archived for reference.

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

Operational correction:

1. We do not pre-load the indicator with every plausible rule, asset, and setting family and then hope AG sorts it out later.
2. We build the minimal exportable core first.
3. AG + SHAP + admission testing decide what is actually important.
4. Only then do surviving assets, settings, and feature families earn permanent places in the live indicator and packet contract.

Before AG is fully useful, the indicator needs a defined contract:

- Inputs (all tunable parameters)
- Internal computed states
- Decision states (`TAKE_TRADE`, `WAIT`, `PASS`)
- Realized outcome states kept separate from the decision codes
- Alerts
- Visualization / dashboard fields

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
- the operator surface must show: decision state, target eligibility, regime context, stop family, TP1/TP2 path

---

### 2. Dataset Builder Design

#### Data Source

Training data comes from **two sources**:

1. **Supabase DB / local research extracts** — MES 15m OHLCV, cross-asset prices, FRED economic series, GPR index, Trump Effect, news signals, economic calendar, pulled into local research workflows without introducing a standing cloud-to-local sync subsystem
2. **TradingView local exports and any later-validated chart capture tooling** — fib lines, pivot-state fields, and admitted indicator / harness outputs from the canonical indicator surface. Do not assume CLI/MCP chart capture exists until the exact tool is installed and documented.

For indicators present on the TradingView chart but not yet in our dataset, we **create the missing indicator in Pine Script first** (using Pine tools and skills), **test it**, then add its output to the training dataset alongside the rest of the data.

The dataset builder must:

1. Pull base OHLCV + cross-asset + macro data into the local research workflow without adding a recurring sync subsystem
2. Ingest TradingView exports for indicator columns, plus any later-validated CLI/MCP chart captures only after the exact tool is installed and documented
3. Materialize point-in-time fib snapshots before downstream feature assembly
4. Create and test any missing Pine indicators or standalone feature harnesses needed for features
5. Identify every fib pullback event in the history from the snapshot surface
6. Compute all features at each pullback
7. Generate forward-looking labels (TP1/TP2 hit, reversal, stop, pullback depth)
8. Output a single CSV ready for AG training

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

#### Fib Snapshot Surface For AG

The fib engine is a first-class state surface and must be materialized point-in-time for training.

Rules:

1. AG training must consume explicit fib snapshots, not ad hoc recomputation from a fully known history window.
2. The snapshot builder must emit one row per MES 15m bar close, keyed by the canonical bar timestamp.
3. Each snapshot may use only data available at or before that bar close, including pivot confirmation/right-bar rules.
4. Once a snapshot row is written for a bar, later anchor discoveries may not rewrite that historical row.

#### Locked normalized operational tables

The next migration must normalize the live decision surface around these tables:

1. `warbird_fib_engine_snapshots_15m`
   - one row per `symbol_code + timeframe + bar_close_ts + fib_engine_version`
   - the canonical frozen fib engine snapshot at MES 15m bar close
2. `warbird_fib_candidates_15m`
   - one row per candidate derived from a snapshot
   - canonical candidate key is `symbol_code + timeframe + bar_close_ts + candidate_seq`
   - carries the policy decision code `TAKE_TRADE` / `WAIT` / `PASS`
3. `warbird_candidate_outcomes_15m`
   - one row per candidate, regardless of decision
   - carries realized outcome truth plus MAE / MFE
4. `warbird_signals_15m`
   - one row per published TradingView signal where the candidate decision is `TAKE_TRADE`
5. `warbird_signal_events`
   - lifecycle events for published signals only

Rules:

1. Decision codes and realized outcomes must remain separate.
2. Missed winners and correct skips become visible only if every candidate receives an outcome row, not only published signals.
3. The dashboard must render from these canonical tables or compatibility views over them; it must not recompute fib geometry locally.
4. Compatibility views may exist during cutover, but the normalized tables above are the new source of truth.
5. Accuracy beats feature count. Example context fields such as retrace-depth variants, volume state, EMA distance, daily 200d distance, or other candidate-side signals are admitted only if they are point-in-time clean, exactly defined, and worth the added complexity.

Locked truth semantics for the next schema rewrite:

- `warbird_decision_code`
  - `TAKE_TRADE`
  - `WAIT`
  - `PASS`
- realized economic truth must distinguish:
  - TP2 reached before stop
  - TP1 reached before stop while TP2 is not yet realized
  - stop before TP1
  - stop after TP1 but before TP2
  - reversal when the locked reversal rule is satisfied
- unresolved rows remain `OPEN` until they resolve to an economic outcome
- exact enum names and exact column names for these semantics are part of the next schema rewrite checkpoint, not this lock
5. Snapshot rows must record, at minimum:
   - active anchor high / low
   - anchor timestamps / bar indexes
   - selected lookback family or period set
   - active fib direction
   - 0 / 1 / pivot / TP1 / TP2 prices
   - target-eligibility state
   - pivot-distance and pivot-state fields used by the trigger
6. The canonical implementation surface for offline fib snapshots is Python in `scripts/ag/build-fib-snapshots.py`, because it needs deterministic materialization for AG and leakage audits.
7. A simple zigzag-only anchor path is not sufficient for Warbird. The engine must preserve the lookback/confluence intelligence that makes the fib state useful, while still being point-in-time clean.
8. User-referenced non-open-source fib indicators, including `Auto Fib Golden Target (with custom text)` when source is unavailable, may be behavior references only. They are not approved code sources and may not be cloned internally.

#### Feature Boundary — Two Tiers

**Tier 1: Pine-Live Features** — computable in Pine from chart OHLCV, `request.security()`, `request.economic()`, or Pine transforms. These drive the live indicator signal.

**Tier 2: Research-Only Context** — macro event data (FRED, GPR, Trump Effect, news signals) that AG uses to discover regime patterns and validate hypotheses. Tier 2 data does NOT produce production features directly. If AG discovers a Tier 2 insight (e.g., "CPI day pullbacks fail more often"), it can only become production-ready if there is an **exact Pine analogue** — either via `request.economic()`, Pine calendar logic, or a Tier 1 proxy that AG can prove correlates (e.g., VIX spike on CPI day). If no Pine analogue exists, the insight stays in the research report but does NOT enter the Pine indicator.

**Rule:** AG trains on everything available. But only Tier 1 features can become production features. Tier 2 insights must pass through a Pine-analogue gate before they influence the live indicator.

#### Feature-Family De-Duplication Rule

The TA core pack and pre-ML exports together form the production feature surface. Do not add redundant variants of the same concept.

Rules:

1. Do not keep overlapping MA / trend / volume features from multiple export blocks unless they encode materially different information.
2. If the TA core pack already exports the canonical state for a concept family (e.g., volume via `ml_vol_ratio` + `ml_vol_acceleration`), a separate hand-built copy is research-only until it proves additive value.
3. AG admission should compare feature families, not reward the same idea repeated in different columns.
4. Any future third-party harness re-admission must go through the Third-Party Pine Admission Gate and prove additive value over the TA core pack baseline.

Neural-layer policy (research-only unless promoted):

1. Neural feature extraction from text/event data is allowed for offline discovery only.
2. Candidate neural cues include policy/lobbying-style event text, obscure news context, and cross-source narrative drift.
3. Neural outputs must be timestamp-aligned to MES 15m bar close and leak-audited before any model training use.
4. No neural score may enter live Pine unless a deterministic Pine-analogue or mirrored-live contract is proven additive and non-breaking.

#### Pine-Reproducible Feature Set

**A. Fib Structure Features** (from chart OHLCV)

Fib-structure rules:

1. The live and offline fib engine may use confirmed lookback/confluence logic, but the training surface must come from frozen point-in-time snapshots.
2. Do not reduce the Warbird fib engine to a simple zigzag feature family.
3. Pivot distance and pivot-state features are critical to trigger admission and reversal derivation, but they are not the sole final decision maker.

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

**B. Intermarket Features** (from `request.security()`) — **UPDATED 2026-03-31: CME Globex basket (Databento GLBX.MDP3)**

| Feature | Pine Source | Description |
|---------|------------|-------------|
| `nq_trend` | `request.security("CME_MINI:NQ1!")` | NQ EMA trend state: -1/0/1 (tech leadership) |
| `rty_trend` | `request.security("CME_MINI:RTY1!")` | RTY EMA trend state: -1/0/1 (small-cap risk appetite) |
| `cl_trend` | `request.security("NYMEX:CL1!")` | CL EMA trend state: -1/0/1 (energy/inflation proxy) |
| `hg_trend` | `request.security("COMEX:HG1!")` | HG EMA trend state: -1/0/1 (copper = industrial demand) |
| `eur_trend` | `request.security("CME:6E1!")` | 6E EMA trend state: -1/0/1 (EUR/USD macro-FX flow) |
| `jpy_trend` | `request.security("CME:6J1!")` | 6J EMA trend state: -1/0/1 (JPY/USD risk-off flow) |
| `nq_rel_strength` | derived | NQ relative strength vs ES (percent change ratio) |
| `rty_rel_strength` | derived | RTY relative strength vs ES |
| `skew_level` | `request.security("CBOE:SKEW")` | SKEW level (daily-only context, NOT gate member) |
| `add_value` | `request.security("USI:ADD")` | NYSE A/D breadth (daily-only context, NOT gate member) |
| `intermarket_alignment` | derived | Count of 6 CME symbols in agreement (0-6) |

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

AG trains on the FULL economic context from all 10 Supabase FRED tables + GPR + Trump Effect. What Pine gets is the distilled version: `request.economic()` for live levels, plus calendar-based event windows that AG learned are significant. Example: AG discovers "CPI day pullbacks to 0.5 have 25% lower TP1 rate before 10am ET" → Pine encodes `is_cpi_day AND hour < 10 → reduce confidence`.

**Research-Only Macro Context (Tier 2 — AG uses for discovery, NOT direct production features)**

| Feature | Source | Pine Analogue (required for promotion) |
|---------|--------|---------------------------------------|
| Full FRED series (all 10 tables) | Supabase `econ_*_1d` | Must find exact `request.economic()` equivalent OR prove a Tier 1 proxy (e.g., US10Y, VIX) captures the same signal |
| GPR geopolitical risk index | Supabase `geopolitical_risk_1d` | Must prove VIX + intermarket captures the same signal, OR stays research-only |
| Trump Effect / policy uncertainty | Supabase `trump_effect_1d` | Must prove a Pine time/calendar analogue exists, OR stays research-only |
| Economic calendar events | Supabase + user-maintained | Pine calendar logic (`is_fomc_week`, `is_cpi_day`) IF AG proves these events materially change outcomes |

**Promotion gate:** A Tier 2 insight only enters Pine if there is an exact Pine analogue that AG can prove correlates. "AG discovered it matters" is not enough — "AG proved Pine feature X captures the same signal" is required.

#### Locked Pine request budget

The v1 indicator must stay under this request budget:

- target operating budget: `<= 12` unique `request.*()` calls
- hard ceiling: `<= 16` unique `request.*()` calls

Planned v7b usage (UPDATED 2026-03-31 — CME Globex pivot):

- `request.security()` — CME Globex intermarket (15m or 60min):
  - `CME_MINI:NQ1!` — tech leadership
  - `CME_MINI:RTY1!` — small-cap risk appetite
  - `NYMEX:CL1!` — energy/inflation proxy
  - `COMEX:HG1!` — copper/industrial demand
  - `CME:6E1!` — EUR/USD macro-FX flow
  - `CME:6J1!` — JPY/USD risk-off flow
- `request.security()` — daily context (NOT gate members):
  - `CBOE:SKEW`
  - `USI:ADD`
- `request.economic()`:
  - `IRSTCB01`
  - `CPALTT01`
  - `LRHUTTTTUSM156S`
  - `BSCICP02`

This yields a planned base budget of `12` unique `request.*()` calls, leaving room for future additions within the 16-call hard ceiling.

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
| `outcome` | categorical | `TP2_HIT`, `TP1_ONLY`, `STOPPED`, `REVERSAL`, `OPEN` |

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
    else: outcome = OPEN
```

Maximum horizon: 40 bars (10 hours of 15m bars).

Stopped trades get **higher penalty weight** during training (weight = 2.0) so AG learns what causes failures. `OPEN` rows are operational-only and excluded from training targets.

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
- alerts kept: entry long, entry short, pivot break reversal (.50 warning). All other alerts moved to dashboard.
```

---

### 13. Implementation Files

| File | Purpose |
|------|---------|
| `scripts/ag/build-fib-snapshots.py` | Materialize point-in-time MES 15m fib state snapshots with frozen anchors and trigger-context fields for AG |
| `scripts/ag/build-fib-dataset.py` | Find all fib pullback events, compute features (Tier 1 + Tier 2 from Supabase), generate labels |
| `scripts/ag/train-fib-model.py` | TP1/TP2 probability models + stop-family evaluation with walk-forward CV |
| `scripts/ag/evaluate-configs.py` | Parameter grid evaluation — each config maps to a Pine input set |
| `scripts/ag/generate-packet.py` | Generate Pine-ready optimization packet with exact input values |

Existing files (`build-dataset.py`, `train-warbird.py`, `fib-engine.ts`, `trigger-15m.ts`) are reference only — different model architecture.

---

### 14. Audited Runtime, Scheduling, and Ownership Snapshot (2026-03-23)

This snapshot is based on the linked Supabase project, the repo runtime surfaces, the production environment variable set, and the live Supabase/Postgres database.

#### Verified live environment

1. Supabase project `warbird-pro` is linked and active as a Next.js deployment.
2. Production environment variables include the required Supabase/Postgres connection surface plus `DATABENTO_API_KEY` and `FRED_API_KEY`.
3. Supabase cloud now has the raw-news schema and raw-news Supabase cron wrapper migrations applied live (`20260326000019`, `20260326000020`) in addition to the earlier baseline schema.
4. Local PostgreSQL 17 is installed, running on `:5432`, and `warbird_training` now exists locally.
5. `supabase/functions/` contains 9 Edge Functions (the production ingestion runtime). All Vercel cron routes have been deleted except `detect-setups` and `score-trades` (unscheduled legacy bridge code).

#### Current runtime: Supabase pg_cron → Edge Functions (COMPLETED)

Runtime truth: `pg_cron → pg_net → Supabase Edge Functions → Supabase DB`. Vercel is the frontend deploy surface only. All recurring ingestion is Supabase-owned.

**Symbology:** All Databento calls use `.c.0` continuous front-month contracts with `stype_in=continuous`. No manual contract-roll logic. `contract-roll.ts` in `_shared/` is dead code.

| pg_cron Job | Schedule | Edge Function | Writes |
| --- | --- | --- | --- |
| `warbird_mes_1m_pull` | `* * * * 0-5` (every min Sun-Fri) | `mes-1m` (Databento Live API, ohlcv-1s → 1m/15m) | `mes_1m`, `mes_15m`, `job_log` |
| `warbird_mes_hourly_pull` | `5 * * * 0-5` (:05 hourly Sun-Fri) | `mes-hourly` (ohlcv-1h + ohlcv-1d, rolls 1h→4h) | `mes_1h`, `mes_4h`, `mes_1d`, `job_log` |
| `warbird_cross_asset_s0` | `5 * * * 0-5` (:05 hourly Sun-Fri) | `cross-asset` shard 0 | `cross_asset_1h`, `cross_asset_1d`, `job_log` |
| `warbird_cross_asset_s1` | `6 * * * 0-5` (:06 hourly Sun-Fri) | `cross-asset` shard 1 | `cross_asset_1h`, `cross_asset_1d`, `job_log` |
| `warbird_cross_asset_s2` | `7 * * * 0-5` (:07 hourly Sun-Fri) | `cross-asset` shard 2 | `cross_asset_1h`, `cross_asset_1d`, `job_log` |
| `warbird_cross_asset_s3` | `8 * * * 0-5` (:08 hourly Sun-Fri) | `cross-asset` shard 3 | `cross_asset_1h`, `cross_asset_1d`, `job_log` |
| `warbird_fred_rates` | `45 2 * * 1-5` (02:45 Mon-Fri) | `fred?category=rates` | `econ_rates_1d`, `job_log` |
| `warbird_fred_yields` | `55 2 * * 1-5` (02:55 Mon-Fri) | `fred?category=yields` | `econ_yields_1d`, `job_log` |
| `warbird_fred_vol` | `5 3 * * 1-5` (03:05 Mon-Fri) | `fred?category=vol` | `econ_vol_1d`, `job_log` |
| `warbird_fred_inflation` | `15 3 * * 1-5` (03:15 Mon-Fri) | `fred?category=inflation` | `econ_inflation_1d`, `job_log` |
| `warbird_fred_fx` | `25 3 * * 1-5` (03:25 Mon-Fri) | `fred?category=fx` | `econ_fx_1d`, `job_log` |
| `warbird_fred_labor` | `35 3 * * 1-5` (03:35 Mon-Fri) | `fred?category=labor` | `econ_labor_1d`, `job_log` |
| `warbird_fred_activity` | `45 3 * * 1-5` (03:45 Mon-Fri) | `fred?category=activity` | `econ_activity_1d`, `job_log` |
| `warbird_fred_money` | `55 3 * * 1-5` (03:55 Mon-Fri) | `fred?category=money` | `econ_money_1d`, `job_log` |
| `warbird_fred_commodities` | `5 4 * * 1-5` (04:05 Mon-Fri) | `fred?category=commodities` | `econ_commodities_1d`, `job_log` |
| `warbird_fred_indexes` | `15 4 * * 1-5` (04:15 Mon-Fri) | `fred?category=indexes` | `econ_indexes_1d`, `job_log` |
| `warbird_econ_calendar` | `20 4 * * 1-5` (04:20 Mon-Fri) | `econ-calendar` | `econ_calendar`, `job_log` |
| `warbird_massive_inflation` | `30 4 * * 1-5` (04:30 Mon-Fri) | `massive-inflation` | `econ_inflation_1d`, `job_log` |
| `warbird_massive_ie` | `40 4 * * 1-5` (04:40 Mon-Fri) | `massive-inflation-expectations` | `econ_inflation_1d`, `job_log` |
| `warbird_trump_effect_pull` | `0 8 * * 1-5` (08:00 Mon-Fri) | `trump-effect` | `trump_effect_1d`, `job_log` |
| `warbird_finnhub_raw_pull` | `5,20,35,50 11-23 * * 1-5` (4x/hr) | `finnhub-news` | `econ_news_finnhub_*`, `job_log` |
| `warbird_refresh_news_signals` | `2,17,32,47 11-23 * * 1-5` (4x/hr) | N/A (in-DB matview refresh) | `news_signals` |

**Removed:** `warbird_newsfilter_raw_pull` (no free API), `warbird_gpr_pull` (backfill-only, manual monthly).

**Unscheduled legacy:** `detect-setups` and `score-trades` are Vercel App Router routes with NO pg_cron schedule. They write to empty legacy `warbird_*` tables and must be ported to Edge Functions writing canonical tables.

#### Cross-asset pipeline detail

The `cross-asset` Edge Function (`supabase/functions/cross-asset/index.ts`):
1. Queries `symbols` for all active `DATABENTO` symbols (excludes MES and `.OPT`)
2. Shards by `index % shardCount` — 4 shards cover all ~17 symbols within 4 minutes
3. For each symbol: finds latest `cross_asset_1h` row, pulls incremental `ohlcv-1h` from Databento Historical API
4. Upserts new 1h bars, then re-aggregates touched days into `cross_asset_1d`
5. All symbols use `.c.0` continuous contracts — Databento handles contract rolls automatically

**Dashboard symbol bar** reads `cross_asset_1h` for HG/NQ/6E/CL (latest 2 rows → current vs previous close → green/red MES-aligned tiles).

#### Runtime rules

1. Supabase pg_cron is the sole schedule producer. All schedules are defined in `supabase/migrations/` SQL files.
2. Every recurring job logs to `job_log` on success, failure, and skip.
3. Local machines are for training/research only — no recurring production ingestion.
4. Vercel hosts the Next.js frontend dashboard and read-oriented API/UI route handlers only.

---

### 15. Approved Data Scope And Provider Contract

This is the exact approved source boundary for Phase 1 through Phase 4 work.

#### Provider boundary

1. Databento `GLBX.MDP3 Standard ($179 / month)` is the approved exchange-data boundary.
2. FRED is the approved macro / release / calendar boundary.
3. Massive is approved for one live macro exception only: `GET /fed/v1/inflation-expectations`; treasury yields, realized inflation, and labor market remain FRED-sourced.
4. Massive stocks/indices intraday or delayed market-data products are not part of the Warbird feature contract; Databento remains the sole market intraday source.
5. Google Finance watchlist / AI summary capture is approved as **manual operator / research capture only** and is not a recurring training or live contract.

#### Databento schema scope

| Schema | Status | Use |
| --- | --- | --- |
| `ohlcv-1m` | Required | default live bar bridge and local training bar source for MES |
| `ohlcv-1h` | Required | higher-timeframe context and cross-asset backfill |
| `ohlcv-1d` | Required | daily context and official higher-timeframe history |
| `definition` | Required | symbol metadata, roll mapping, instrument identity |
| `statistics` | Required | official open interest / settlement / exchange-provided statistics |
| `ohlcv-1s` | Later-phase only | evidence-gated research; not default dashboard or training path |
| `trades` | Later-phase only | evidence-gated MES microstructure research only |
| `mbp-1` | Later-phase only | evidence-gated MES order-book research only |
| `mbp-10` | Later-phase only | evidence-gated MES order-book research only |
| `mbo` | Later-phase only | evidence-gated MES order-book research only |

Hard rules:

1. Default live/dashboard bridge is `ohlcv-1m`, not `ohlcv-1s`.
2. Use one Databento live session per live path; do not create duplicate paid sessions for identical subscriptions.
3. Do not plan around data products outside the current subscription.

#### Approved market symbols

| Role | Required baseline | Approved later-context additions |
| --- | --- | --- |
| Canonical traded object | `MES` | none |
| Equity confirmation | `ES`, `NQ` | `YM`, `RTY` |
| Rates / liquidity | `ZN`, `ZF`, `ZB`, `SR3` | `ZT` only if later explicitly added to `symbols` |
| FX / dollar proxy | `6E`, `6J` | none |
| Energy / commodity shock | `CL` | `GC`, `NG` |

#### Options scope

1. Options are limited to `MES.OPT` and `ES.OPT`.
2. `SPX` options are blocked under the current provider boundary.
3. Do not hand-roll Greeks.
4. Do not persist columns that imply provider-backed Greeks unless the provider actually emits them for the approved contract.
5. Initial options work is official-statistics-first. If 15m option-state features are pursued, they must be built from approved provider data with a clean timestamp contract before any schema expansion is treated as canonical.

#### Exact FRED series map

| Table | Exact approved series |
| --- | --- |
| `econ_rates_1d` | `FEDFUNDS`, `DFF`, `SOFR` |
| `econ_yields_1d` | `DGS2`, `DGS5`, `DGS10`, `DGS30`, `T10Y2Y`, `T10Y3M` |
| `econ_fx_1d` | `DTWEXBGS`, `DEXUSEU`, `DEXJPUS` |
| `econ_vol_1d` | `VIXCLS`, `OVXCLS` |
| `econ_inflation_1d` | `CPILFESL`, `CPIAUCSL` (FRED realized inflation) |
| `econ_labor_1d` | `UNRATE`, `PAYEMS`, `ICSA`, `CCSA` |
| `econ_activity_1d` | `INDPRO`, `RSXFS`, `DGORDER` |
| `econ_money_1d` | `M2SL`, `WALCL` |
| `econ_commodities_1d` | `DCOILWTICO`, `GVZCLS` |
| `econ_indexes_1d` | `USEPUINDXD`, `BAMLH0A0HYM2` |

#### Massive inflation-expectations map (approved exception)

| Table | Massive field | Provider-tagged `series_id` |
| --- | --- | --- |
| `econ_inflation_1d` | `forward_years_5_to_10` | `MASSIVE_IE_FORWARD_YEARS_5_TO_10` |
| `econ_inflation_1d` | `market_10_year` | `MASSIVE_IE_MARKET_10_YEAR` |
| `econ_inflation_1d` | `market_5_year` | `MASSIVE_IE_MARKET_5_YEAR` |
| `econ_inflation_1d` | `model_10_year` | `MASSIVE_IE_MODEL_10_YEAR` |
| `econ_inflation_1d` | `model_1_year` | `MASSIVE_IE_MODEL_1_YEAR` |
| `econ_inflation_1d` | `model_30_year` | `MASSIVE_IE_MODEL_30_YEAR` |
| `econ_inflation_1d` | `model_5_year` | `MASSIVE_IE_MODEL_5_YEAR` |

#### Mandatory macro package (provider-agnostic)

These four macro domains are required in every Phase 4+ training snapshot:

1. `yields`
2. `inflation`
3. `inflation_expectations`
4. `labor_market`

Source policy:

1. `yields`, `inflation` (realized), and `labor_market` remain on the existing FRED ingestion path.
2. `inflation_expectations` is sourced from Massive endpoint `GET /fed/v1/inflation-expectations`.
3. Massive inflation-expectations rows are mapped into `econ_inflation_1d` via deterministic provider-tagged `series_id` values and logged via `job_log`; no second macro feature path is allowed.

Dollar-state rule:

1. Local research uses FRED broad-dollar and FX proxies, not a separate paid `DXY` provider feed.
2. The CME Globex basket now includes `6E` (EUR/USD) and `6J` (JPY/USD) as direct FX flow inputs, superseding the need for a separate DXY Pine pull. Dollar-state is derived from 6E/6J trend agreement.
3. The old `ml_event_dxy_state` export is retired; replaced by `ml_event_eur_state` + `ml_event_jpy_state`.

#### Promotion-parity rule

1. If a feature cannot be computed in Pine exactly, or mirrored into the live stack as an approved realtime state, it cannot drive live decisions.
2. The only valid feature classes are:
   - Pine-native
   - mirrored-live
   - research-only
3. Research-only features may inform model discovery and reports, but not live indicator logic.

---

### 16. Local Training Warehouse Requirement

The AG system needs a local PostgreSQL training warehouse. This is the research and training workbench for the MES 15m contract. It is not the live production decision owner.

#### Current local status

1. PostgreSQL 17 is installed and running on `:5432`.
2. Python `3.12` is installed.
3. AutoGluon `1.5.0` is installed globally.
4. `warbird_training` exists locally.
5. A project-local Python venv does not exist yet.
6. `scripts/ag/` remains effectively empty and is still a blocking gap.
7. A local Supabase stack is not running yet, so current local execution truth is PostgreSQL-first, not full local Supabase-first.

#### Local warehouse responsibilities

1. Hold explicit source snapshots aligned to the MES 15m bar-close contract.
2. Hold feature-engineering staging tables and auditable training artifacts.
3. Hold SHAP, calibration, packet candidates, and evaluation outputs.
4. Never become a required always-on dependency for the cloud dashboard or live chart.

#### Exact local source-snapshot surface

The local warehouse may materialize explicit snapshots of:

- `mes_1m`, `mes_15m`, `mes_1h`, `mes_4h`, `mes_1d`
- `cross_asset_1h`, `cross_asset_1d`
- `options_stats_1d`
- `econ_rates_1d`, `econ_yields_1d`, `econ_fx_1d`, `econ_vol_1d`, `econ_inflation_1d`, `econ_labor_1d`, `econ_activity_1d`, `econ_money_1d`, `econ_commodities_1d`, `econ_indexes_1d`
- `econ_calendar`, `macro_reports_1d`, `geopolitical_risk_1d`, `trump_effect_1d`

Every snapshot table or extract must record:

- source table name
- snapshot timestamp
- source max timestamp
- load timestamp

#### Exact local training / ops tables

| Table | Purpose | Minimum key columns |
| --- | --- | --- |
| `warbird_training_runs` | one row per AG run | `run_id`, `created_at`, `contract_version`, `dataset_date_range`, `feature_count`, `packet_status`, `tp1_auc`, `tp2_auc`, `calibration_error` |
| `warbird_training_run_metrics` | local full metric rows per run/target/split | `run_id`, `target_name`, `split_code`, `metric_family`, `metric_name`, `metric_value`, `is_primary` |
| `warbird_shap_results` | local feature-level explainability per run | `run_id`, `feature_name`, `feature_family`, `tier`, `mean_abs_shap`, `rank_in_run` |
| `warbird_shap_indicator_settings` | local SHAP-derived indicator-setting candidates | `run_id`, `indicator_family`, `parameter_name`, `suggested_numeric_value`, `stability_score` |
| `warbird_snapshot_pine_features` | point-in-time Pine hidden exports per snapshot | `snapshot_id`, `feature_contract_version`, `ml_confidence_score`, `ml_direction_code`, `ml_setup_archetype_code` |
| `warbird_candidate_macro_context` | local Tier 2 macro context | `candidate_id`, `bar_date`, `macro_window_active`, `gpr_level` |
| `warbird_candidate_microstructure` | local OHLCV-derived 1m context | `candidate_id`, `window_bars`, `window_start_ts`, `window_end_ts`, `vol_ratio_at_entry`, `atr_14_at_touch` |
| `warbird_candidate_path_diagnostics` | local path-first-touch diagnostics | `candidate_id`, `first_touch_code`, `bars_to_tp1`, `bars_to_tp2`, `bars_to_stop` |
| `warbird_candidate_stopout_attribution` | local stop-out attribution surface | `candidate_id`, `stop_driver_code`, `stop_driver_confidence`, `notes_json` |
| `warbird_feature_ablation_runs` | local feature-family add/remove experiments | `ablation_run_id`, `baseline_run_id`, `candidate_run_id`, `feature_family`, `metric_name`, `delta_metric_value` |
| `warbird_entry_definition_experiments` | local entry-definition experiment results | `experiment_id`, `experiment_code`, `anchor_policy_code`, `retrace_rule_code`, `tp1_before_sl_rate`, `tp2_before_sl_rate` |

#### Required local implementation files

| File | Responsibility |
| --- | --- |
| `scripts/ag/load-source-snapshots.py` | explicit local loads from approved source tables or extracts |
| `scripts/ag/build-fib-dataset.py` | 15m-aligned dataset assembly and label construction |
| `scripts/ag/compute-features.py` | deterministic non-leaky feature computation and bucket assignment |
| `scripts/ag/train-fib-model.py` | staged AutoGluon module admission and packet training |
| `scripts/ag/evaluate-configs.py` | packet candidate comparison, fold review, calibration checks |
| `scripts/ag/generate-packet.py` | Pine-ready packet assembly |
| `scripts/ag/publish-artifacts.py` | idempotent publish-up to cloud ops tables |

#### Local warehouse rules

1. Populate it through explicit cloud snapshots and local TradingView capture flows only.
2. Do not build or extend a standing cloud-to-local sync subsystem or a local-first production ingestion path.
3. The local warehouse may hold scratch tables and intermediate joins.
4. No live production endpoint may depend on the local warehouse being up.
5. Research news collection may target local, but recurring production-owned raw-news retention remains cloud-first; local copies are optional research mirrors only.

---

### 17. Cloud Publish-Up And Dashboard Realtime Requirement

Cloud is the display, realtime, and operator-facing operations surface. It is not the local model-training workbench.

#### Verified current cloud state

1. Legacy cloud tables from the earlier 1H / 4H architecture still exist and do not match the locked MES 15m fib-outcome contract:
   - `warbird_forecasts_1h`
   - `warbird_daily_bias`
   - `warbird_structure_4h`
   - `warbird_conviction`
   - `warbird_risk`
2. `public.models` exists but is empty and is not the right packet / activation lifecycle table.
3. `trade_scores` exists but is empty and reflects the older predicted-price / MAE / MFE path.
4. No cloud tables currently exist for:
   - `warbird_training_runs`
   - `warbird_training_run_metrics`
   - `warbird_packets`
   - `warbird_packet_activations`
   - `warbird_packet_metrics`
   - `warbird_packet_feature_importance`
   - `warbird_packet_setting_hypotheses`
   - `warbird_packet_recommendations`
5. No cloud storage buckets are in active use for model/report artifacts.

#### Required cloud publish-up entities

| Table | Purpose | Minimum key columns |
| --- | --- | --- |
| `warbird_training_runs` | published run registry | `run_id`, `created_at`, `contract_version`, `symbol_code`, `timeframe`, `dataset_date_range`, `feature_count`, `tp1_auc`, `tp2_auc`, `calibration_error`, `packet_status` |
| `warbird_training_run_metrics` | full training/evaluation metrics for Admin and model review | `run_id`, `target_name`, `split_code`, `fold_code`, `metric_family`, `metric_name`, `metric_value`, `is_primary` |
| `warbird_packets` | AG scoring/model packet registry | `packet_id`, `run_id`, `created_at`, `contract_version`, `symbol_code`, `timeframe`, `status`, `packet_json`, `sample_count`, `promoted_at`, `superseded_at` |
| `warbird_packet_activations` | immutable activation log | `activation_id`, `packet_id`, `activated_at`, `deactivated_at`, `activation_reason`, `rollback_reason`, `is_current` |
| `warbird_packet_metrics` | structured Admin KPIs per packet target/split | `packet_id`, `target_name`, `split_code`, `auc`, `log_loss`, `brier_score`, `calibration_error`, `resolved_count`, `open_count` |
| `warbird_packet_feature_importance` | published top drivers for active packet review | `packet_id`, `target_name`, `feature_family`, `feature_name`, `importance_source_code`, `importance_rank`, `mean_abs_importance` |
| `warbird_packet_setting_hypotheses` | structured indicator and entry-definition suggestions | `packet_id`, `target_name`, `indicator_family`, `parameter_name`, `action_code`, `stability_score`, `support_summary_json` |
| `warbird_packet_recommendations` | structured AI-generated Admin guidance | `packet_id`, `section_code`, `priority`, `recommendation_code`, `title`, `summary_text`, `rationale_json`, `action_json` |

#### Required cloud realtime dashboard entities

Current dashboard consumers already expect `mes_1m` and `mes_15m`. Keep those. The Next.js dashboard and any TradingView-facing mirror must consume the same MES 15m fib/state contract. Add these:

| Table | Purpose | Minimum key columns |
| --- | --- | --- |
| `warbird_fib_engine_snapshots_15m` | canonical frozen fib engine state per MES 15m bar close (provenance is `fib_engine_version`, not packet) | `snapshot_id`, `bar_close_ts`, `symbol_code`, `timeframe`, `fib_engine_version`, `anchor_hash`, `direction`, `anchor_high`, `anchor_low`, `resolved_left_bars`, `resolved_right_bars`, `target_eligible_20pt` |
| `warbird_fib_candidates_15m` | canonical candidate + decision state per MES 15m bar close | `candidate_id`, `snapshot_id`, `bar_close_ts`, `symbol_code`, `timeframe`, `candidate_seq`, `setup_archetype_code`, `fib_level_touched`, `entry_price`, `stop_loss`, `tp1_price`, `tp2_price`, `decision_code`, `reason_code`, `packet_id` |
| `warbird_candidate_outcomes_15m` | candidate-level realized truth for both taken and skipped trades | `outcome_id`, `candidate_id`, `bar_close_ts`, `symbol_code`, `timeframe`, `outcome_code`, `mae_pts`, `mfe_pts`, `scorer_version`, `scored_at` |
| `warbird_signals_15m` | published TradingView signals only | `signal_id`, `candidate_id`, `bar_close_ts`, `symbol_code`, `timeframe`, `status`, `emitted_at`, `tv_alert_ready`, `packet_id` |
| `warbird_signal_events` | lifecycle events for published signals only | `signal_event_id`, `signal_id`, `ts`, `event_type`, `price` |

The dashboard compatibility/live views should then be derived from those canonical tables:

| View | Purpose | Minimum source contract |
| --- | --- | --- |
| `warbird_active_signals_v` | mirrored current signal and candidate state for chart/dashboard rendering | latest joined row from `warbird_signals_15m` + `warbird_fib_candidates_15m` + `warbird_candidate_outcomes_15m` |
| `warbird_admin_candidate_rows_v` | Admin candidate row surface — **locked staple columns: Dir, Target, TP1 Hit, TP2 Hit, SL Hit, Status** (plus Time, Entry, SL Price, TP2 Price, Fib Level, Outcome, Decision). Replaces legacy "Measured Moves". View must expose explicit `tp1_hit`, `tp2_hit`, `sl_hit` computed columns — not the ambiguous single `target_hit_state`. | current rows from `warbird_fib_candidates_15m` + `warbird_fib_engine_snapshots_15m` + `warbird_signals_15m` + `warbird_candidate_outcomes_15m` |
| `warbird_active_training_run_metrics_v` | Admin full-metric surface for the active packet run | current row from `warbird_packet_activations` + `warbird_packets` + `warbird_training_run_metrics` |
| `warbird_active_packet_metrics_v` | Admin packet KPI surface | current row from `warbird_packet_activations` + `warbird_packets` + `warbird_packet_metrics` |
| `warbird_active_packet_feature_importance_v` | Admin feature-driver surface | current row from `warbird_packet_activations` + `warbird_packets` + `warbird_packet_feature_importance` |
| `warbird_active_packet_setting_hypotheses_v` | Admin indicator-setting suggestion surface | current row from `warbird_packet_activations` + `warbird_packets` + `warbird_packet_setting_hypotheses` |
| `warbird_active_packet_recommendations_v` | formatted Admin AI-guidance surface | current row from `warbird_packet_activations` + `warbird_packets` + `warbird_packet_recommendations` |

#### Locked Admin candidate table staple columns (2026-03-29)

The Admin candidate table (replacing legacy "Measured Moves") MUST include these columns. The first 8 are non-negotiable staples; the remaining 5 are recommended operator context.

| # | Column | View field | Values | Notes |
|---|--------|-----------|--------|-------|
| 1 | **Time** | `bar_close_ts` | timestamp | Row identity, sort descending |
| 2 | **Dir** | `direction` | LONG / SHORT | Color-coded badge |
| 3 | **Entry** | `entry_price` | numeric | Entry price level |
| 4 | **Target** | `tp1_price` | numeric | TP1 target price (canonical target) |
| 5 | **TP1 Hit** | `tp1_hit` | HIT / MISS / OPEN | Explicit derived state — replaces `target_hit_state` |
| 6 | **TP2 Hit** | `tp2_hit` | HIT / MISS / OPEN | Explicit derived state — new column |
| 7 | **SL Hit** | `sl_hit` | HIT / MISS / OPEN | Explicit derived state — new column |
| 8 | **Status** | `status` | ACTIVE / TP1_HIT / TP2_HIT / STOPPED / CANCELLED | Signal lifecycle state |
| 9 | SL Price | `stop_loss` | numeric | Mechanical stop level |
| 10 | TP2 Price | `tp2_price` | numeric | Full extension target |
| 11 | Fib Level | `fib_level_touched` | enum | Which fib level triggered |
| 12 | Outcome | `outcome_state` | TP2_HIT / TP1_ONLY / STOPPED / REVERSAL / OPEN | Final resolved state |
| 13 | Decision | `decision_code` | TAKE_TRADE / WAIT / PASS | Model policy decision |

**Required view changes to migration 038 before Admin cutover:**

Replace the single ambiguous `target_hit_state` column in `warbird_admin_candidate_rows_v` with three explicit columns:

```sql
case when o.tp1_before_sl then 'HIT'
     when o.sl_before_tp1 or o.sl_after_tp1_before_tp2 then 'MISS'
     else 'OPEN' end                                            as tp1_hit,

case when o.tp2_before_sl then 'HIT'
     when o.outcome_code in ('TP1_ONLY','STOPPED','REVERSAL') then 'MISS'
     else 'OPEN' end                                            as tp2_hit,

case when o.sl_before_tp1 or o.sl_after_tp1_before_tp2 then 'HIT'
     when o.outcome_code in ('TP2_HIT','TP1_ONLY') then 'MISS'
     else 'OPEN' end                                            as sl_hit,
```

#### Locked replacement semantics for the legacy forecast surface

1. `warbird_forecasts_1h` is a legacy misnamed surface from the pre-15m architecture and must not drive new work.
2. Its replacement contract is the MES 15m setup outcome surface:
   - `warbird_fib_candidates_15m.tp1_probability`
   - `warbird_fib_candidates_15m.tp2_probability`
   - `warbird_fib_candidates_15m.reversal_risk`
   - `warbird_fib_candidates_15m.decision_code`
3. No new publish-up contract may use predicted-price tables as the primary model output.

#### Cloud rules

1. Keep the new tables in `public`.
2. Do not overload `public.models` or `trade_scores` for the new packet lifecycle.
3. Keep cloud tables strictly publish-up targets, dashboard state, and run history.
4. Do not make cloud tables part of the direct live Pine decision path.
5. Do not create new predicted-price or `1H forecast` tables; the live model surface is MES 15m setup-outcome state keyed by `bar_close_ts`.
6. Every publish-up write must be idempotent on its natural key.
7. Cloud Realtime is the dashboard transport; Databento is not a dashboard-direct contract.
8. `warbird_triggers_15m`, `warbird_conviction`, `warbird_risk`, `warbird_setups`, `warbird_setup_events`, and `measured_moves` are **legacy/operational only**. They are not the canonical AG training truth, must not drive new architecture, and will be retired once the canonical tables above exist and all readers have migrated. The legacy `detect-setups` and `score-trades` routes that write to these tables are unscheduled bridge code pending the canonical Edge Function writer.

#### Cloud pruning sequence

Do not drop a table until its current readers and writers are removed or replaced.

Current audited prune candidates by class:

1. Dormant / zombie cloud candidates:
   - `trade_scores`
   - `vol_states`
   - `sources`
   - `policy_news_1d`
   - `options_ohlcv_1d`
2. Legacy 1H / 4H tables to retire only after route migration:
   - `warbird_forecasts_1h`
   - `warbird_daily_bias`
   - `warbird_structure_4h`
   - `warbird_conviction`
   - `warbird_risk`

Current repo dependencies that block immediate removal:

1. `app/api/cron/detect-setups/route.ts` still reads or writes `warbird_forecasts_1h`, `warbird_daily_bias`, `warbird_structure_4h`, `warbird_conviction`.
2. `app/api/cron/forecast/route.ts` still reads `warbird_forecasts_1h`.
3. `app/api/admin/status/route.ts` still audits multiple dormant and legacy tables.
4. `scripts/warbird/predict-warbird.py` still writes `warbird_forecasts_1h` and `warbird_risk`.

Cloud-prune order:

1. build local warehouse and local AG scripts
2. add cloud publish-up tables and realtime dashboard tables
3. cut routes and scripts off the dormant / legacy tables
4. migrate dashboard and `admin/status` to the new publish-up and live-state surface
5. only then write drop migrations for retired cloud tables

---

### 18. Model Packet, Activation, And Rollback Lifecycle

The packet lifecycle is a first-class contract surface. It cannot stay implied.

#### Required statuses

Packet status values must include at least:

- `CANDIDATE`
- `PROMOTED`
- `FAILED`
- `ROLLED_BACK`
- `SUPERSEDED`

#### Lifecycle rules

1. Every local AG run must produce a traceable run record.
2. Every packet candidate must reference its source training run.
3. Only one packet may be active for a given `symbol_code + timeframe + contract_version`.
4. Promotion and rollback must be reversible state transitions, not destructive rewrites.
5. Use `warbird_packet_activations` for the activation log rather than mutating packet history in place.

#### Exact rollback trigger

The hard rollback / review trigger is:

- **2 consecutive initiated trades from the active packet that fail to hit PT1**

Interpretation rules:

1. Count only initiated trades from the active packet.
2. `WAIT` and `PASS` are not misses.
3. A single miss does not trigger rollback.
4. The second consecutive PT1 miss opens the rollback/retrain path immediately.

#### Required rollback response

When the 2-consecutive-PT1-miss rule is hit:

1. write the failure event and packet context to `warbird_packet_activations`, `warbird_packet_metrics`, and `warbird_packet_recommendations`
2. mark the current packet under review
3. retrain the affected model path with fresh data
4. review the packet logs and failure samples before a new promotion
5. if a prior promoted packet exists and remains valid, reactivate it explicitly rather than silently mutating the failing packet row

#### Required run contents

Each run must capture, directly or by referenced artifacts:

1. TP1 model outputs
2. TP2 model outputs
3. reversal-risk outputs
4. stop-family evaluation outputs
5. bucket calibration outputs
6. SHAP and feature-admission outputs
7. the exact active packet / prior packet comparison used in any rollback decision

#### Explicit non-goals

The model lifecycle does **not** require:

1. live cloud inference
2. cloud-to-local training sync
3. dashboard writes from Pine
4. generic model-serving endpoints for the chart path

---
