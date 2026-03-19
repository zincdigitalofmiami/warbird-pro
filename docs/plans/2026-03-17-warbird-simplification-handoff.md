# Warbird Simplification Handoff
**Date:** 2026-03-17
**Status:** Canonical plan of record (15m-primary, sidecar out)

---

## 1. Purpose

This note captures the architecture decisions made on 2026-03-17 so they are not lost in chat history.

The goal is not a broad rewrite. The goal is to:

- get fast, continuous data into the system
- keep the model reliable
- reduce complexity
- preserve as much of the existing schema, naming, and admin shell as possible

---

## 2. Core Direction

Warbird should behave like a **stateful geometry scoring engine**, not a layered 1H macro-conviction machine.

The geometry engine already owns:

- `entry_price`
- `stop_loss`
- `pt1_price`
- `pt2_price`
- fib levels
- trigger zone

The model should score that geometry and write:

- `prob_hit_sl_first`
- `prob_hit_pt1_first`
- `prob_hit_pt2_after_pt1`
- `expected_max_extension`
- `setup_score`

The system should present the current stated fib as:

- `PT1 probability = xx.xx%`
- `PT2 probability = xx.xx%`
- `SL first probability = xx.xx%`
- `expected max extension = 1.236 / 1.618 / 2.0`
- `geometry_status = current`

---

## 3. Geometry Rules

### 3.1 Frozen geometry

Fib geometry is market-derived and must be treated as a snapshot.

- when a valid geometry package is created, it becomes the current frozen package
- that package is typically frozen for at least `10` bars
- during that freeze window, the system does not move:
  - anchors
  - fib levels
  - trigger zone
  - `entry_price`
  - `stop_loss`
  - `pt1_price`
  - `pt2_price`

### 3.2 Redraw behavior

We cannot force the fib to stay fixed forever. If price action invalidates it or creates a better reversal geometry, the system must version it instead of mutating history.

When a material redraw occurs:

- old geometry becomes `superseded`
- old forecast becomes `superseded`
- new geometry becomes `current`
- new forecast is computed against the new frozen package

This applies only to geometry state. It does **not** rewrite open trades.

### 3.3 Active trade behavior

If a trade is opened off a geometry version:

- that trade remains frozen to the exact geometry version used at entry
- redraws after entry do not rewrite that trade's `SL/PT1/PT2`
- the trade closes against the frozen map it entered on

---

## 4. Timeframe Roles

The clean separation is:

- `1s` = fast ingestion / continuity layer
- `1m` = trigger-resolution and trigger-training data
- `15m` = setup-definition and model evaluation timeframe
- `4h` = optional higher-timeframe context only

Important distinction:

- `1m` is valid and needed for trigger-engine training
- `1m` should **not** become the main prediction timeframe
- `15m` remains the primary geometry and scoring timeframe

---

## 5. Model Contract

The model does not invent fibs. The fibs are deterministic from geometry.

The model's job every `15m` while flat is:

- read the current frozen geometry
- read recent market behavior around that geometry
- score the probability of path outcomes

Live model outputs should be limited to:

- `prob_hit_sl_first`
- `prob_hit_pt1_first`
- `prob_hit_pt2_after_pt1`
- `expected_max_extension`
- `setup_score`

The model should not be centered on:

- 1H forecast tables as the primary logic
- runner logic
- broad MAE/MFE target-price forecasting
- daily / 4H conviction stacks as hard dependencies

---

## 6. Training Data Rules

### 6.1 Record everything

The system must log geometry evaluations whether a trade is taken or not.

Reason:

- logging only taken trades creates selection bias
- complete geometry history is needed to learn what works and what does not
- complete history is needed to evaluate time of day, pullback quality, volume conditions, and news-driven behavior

### 6.2 Features to train on

The model must learn from the geometry and the interaction with that geometry.

Required feature families:

- pullback depth
- exact fib line reached
- trigger-zone interaction quality
- time of day
- session context
- bid/ask and aggressive flow proxies if available
- blocks / desk activity proxies if available
- 1m or 1s momentum away from the zone
- optional 4H context if it proves useful

Time of day is considered extremely important.

### 6.3 Labels

At minimum, the system should label:

- `hit_sl_first`
- `hit_pt1_first`
- `hit_pt2_after_pt1`
- `max_extension_reached`

The system should also preserve post-hoc analysis fields so reporting can explain:

- why the trade worked
- why it failed
- what market conditions were present
- which fib depths perform best
- which sessions and windows have the highest quality

---

## 7. Data Feed Reality

The current chart/feed path is not trustworthy enough for fine trigger work.

Observed issue:

- bad chart compression / continuity artifacts indicate data-feed and/or aggregation problems

Conclusion:

- this is a data continuity problem first
- do not trust fine trigger logic or model training until continuity is proven

Immediate feed direction:

- add `mes_1s` as a fast ingestion layer
- keep `mes_1m`, `mes_15m`, and `mes_4h`
- use `1s -> 1m -> 15m` continuity to reduce malformed live structure

TradingView webhooks may be used where useful for:

- trigger alerts
- indicator events
- news-related event annotations

But TradingView webhooks are not the primary market-data transport.

---

## 8. Minimal-Change Table Strategy

Do **not** detonate the schema.

The preferred path is to preserve the current naming surface and admin shell as much as possible.

### 8.1 Keep

Keep these existing tables if possible:

- `mes_1m`
- `mes_15m`
- `mes_4h`
- `warbird_triggers_15m`
- `warbird_setups`
- `warbird_setup_events`
- `job_log`

### 8.2 Add

Add:

- `mes_1s`

### 8.3 Reuse instead of rename

For speed, it is acceptable to temporarily reuse an imperfect existing table name rather than trigger broad app churn.

Most likely candidate:

- keep `warbird_forecasts_1h` as the model-score table for now, even if the name is wrong

The faster path is:

- add the correct scoring columns
- ignore obsolete columns in app logic
- defer renames until the system is stable

### 8.4 Use existing tables differently

- `warbird_triggers_15m` should become the primary geometry snapshot / trigger-observation record
- `warbird_setups` should remain the execution record tied to a frozen geometry version
- `warbird_setup_events` should remain the lifecycle trail

---

## 9. Admin Page Direction

The current admin shell is worth preserving.

Existing surfaces already provide value:

- data coverage
- job health
- active setups
- recent setups
- forecasts
- measured moves

The right move is not to rebuild the admin page. The right move is to feed it cleaner state from the simplified geometry model and the repaired feed path.

---

## 10. Explicit Non-Goals

Do not do these next:

- broad schema renaming
- large migration churn
- runner rework
- more layered conviction logic
- more 1H-only architecture expansion
- chart cosmetics before data continuity is fixed

---

## 11. Next Session: First Sequence

Tomorrow's implementation should start here:

1. Define the smallest migration set needed to support the simplified model.
2. Add `mes_1s` and wire the fast-ingestion path.
3. Preserve `mes_1m`, `mes_15m`, `mes_4h` as canonical training/serving layers.
4. Add geometry version/status fields to the trigger layer with minimal churn.
5. Add probability/score fields to the forecast layer with minimal churn.
6. Ensure all evaluations are stored whether traded or not.
7. Keep the admin/status shell and point it at the cleaner state.
8. Use TradingView webhooks only where they improve trigger/news event capture.

---

## 12. Final Principle

The target system is:

- fast data in
- frozen geometry versions
- deterministic fib map
- simple probability scoring
- minimal schema churn
- complete historical logging
- reliable admin visibility

That is the architecture to build from next.

---

## 13. Live Session Capture (2026-03-18)

This section captures observed behavior from live trading context and translates it into non-negotiable execution rules.

### 13.1 Observed pain points

- Current feed/chart state is unusable for precision trigger work when bars are malformed or continuity is broken.
- `15m` and `1h` can tell conflicting stories during fast conditions; the conflict is material.
- `1000t` view showed clearer sweep/reclaim/acceptance structure than coarse timeframe views.
- VWAP context can disagree across constructions; event-time VWAP gave a different directional read than coarse-time view.
- "Everything lined up" setups still failed when there was no true acceptance after a sweep.

### 13.2 Canonical trap sequence

Treat this as the core failure mode:

- liquidity probe or sweep
- acceptance failure or reclaim
- imbalance/depth transition
- displacement

Execution must not occur at step 1 by default.

### 13.3 Required trigger state machine

- `SweepDetected`
- `AcceptanceConfirmed` or `AcceptanceFailed`
- `ImbalanceShiftConfirmed`
- `DisplacementConfirmed`

Allowed execution state:

- execute only at `ImbalanceShiftConfirmed` or `DisplacementConfirmed`

Blocked execution states:

- block at `SweepDetected`
- block at `AcceptanceFailed` until confirmation rules pass

### 13.4 Timeframe authority split

- `15m`: context and geometry authority
- `1000t`: trigger and acceptance authority

When they disagree:

- default state is `WATCH` or `NO_TRADE`, not `EXECUTE`

### 13.5 Event-day guardrails

For scheduled macro windows:

- PPI window around 08:30 ET
- FOMC statement window around 14:00 ET

During guardrail windows:

- require stricter acceptance/displacement confirmation
- reduce confidence and block marginal setups

### 13.6 Translation to build work

Implement in this order:

1. Feed integrity first.
2. Add and test state-machine events in storage.
3. Enforce state-gated execution.
4. Calibrate probabilities only after stable event logging is proven.
