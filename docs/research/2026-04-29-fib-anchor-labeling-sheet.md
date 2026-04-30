# Fib Anchor Labeling Sheet — Operator Ground Truth

**Date:** 2026-04-29 (trimmed for fat-cut 2026-04-29)
**Status:** Template — DEFERRED. The anchor work is paused while the confirmation-gate Optuna phase runs first. This sheet stays in repo for when anchor labeling opens.
**Companion to:** `docs/research/2026-04-29-fib-anchor-tf-failure-modes.md`
**Companion plan (currently active):** `docs/plans/2026-04-29-confirmation-gate-optuna-phase.md` — confirmation gate runs before any anchor work.
**Purpose:** Collect operator-judged correct anchors across MES1! timeframes, then score each engine candidate against the labels.

---

## How To Use

1. Pick a chart timestamp on MES1! at the listed timeframe. Span across regimes — trending up, trending down, chop, post-news, gap opens. Pre-2018 data excluded per `docs/contracts/pine_indicator_ag_contract.md`.
2. For each row:
   - **Bar timestamp**: bar's open time, format `YYYY-MM-DD HH:MM ET`
   - **Regime tag**: one of `trend_up`, `trend_down`, `chop`, `post_news`, `gap_open`, `event_day` (NFP/FOMC/CPI), `holiday_thin`
   - **Operator-correct anchor**: visual judgment, the leg you would actually trade off of. High and Low values to one tick precision.
   - **Pure-ZZ engine output**: load institutional indicator, read the printed anchor.
   - **Structural-lock engine output**: load `codex/wb-opt-bt-first-structural-fibs` strategy, read the printed anchor.
   - **Verdict per engine**: `match` | `off_by_one` (one pivot earlier/later than label, same direction) | `wrong_leg` (different leg entirely) | `wrong_direction`
   - **Failure mode tag**: from the failure-mode taxonomy in the companion research doc — `stale_leg_lock`, `stale_pivot_anchor`, `wrong_direction`, `correct`, or `other` (specify)

3. Aim for at least 3 examples per timeframe, ideally 5. More is better. Spread across regimes so a single regime doesn't dominate.

4. After a full pass, summarize at the bottom: which failure mode dominates per TF, and whether existing 2026-04-10 fixes are sufficient or a leg-freshness fix is justified.

---

## 5m

| Bar timestamp (ET) | Regime | Correct H | Correct L | ZZ H | ZZ L | StructLock H | StructLock L | ZZ verdict | StructLock verdict | Failure mode | Notes |
|---|---|---|---|---|---|---|---|---|---|---|---|
| | | | | | | | | | | | |
| | | | | | | | | | | | |
| | | | | | | | | | | | |

## 15m

| Bar timestamp (ET) | Regime | Correct H | Correct L | ZZ H | ZZ L | StructLock H | StructLock L | ZZ verdict | StructLock verdict | Failure mode | Notes |
|---|---|---|---|---|---|---|---|---|---|---|---|
| | | | | | | | | | | | |
| | | | | | | | | | | | |
| | | | | | | | | | | | |

## 30m

| Bar timestamp (ET) | Regime | Correct H | Correct L | ZZ H | ZZ L | StructLock H | StructLock L | ZZ verdict | StructLock verdict | Failure mode | Notes |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 2026-04-29 12:00 | trend_down | 7188.00 | 7146.25 | 7188.00 | 7146.25 | (≈match per visual) | (≈match per visual) | match | match | correct | Seed example; 30m steady state |
| | | | | | | | | | | | |
| | | | | | | | | | | | |

## 1h

| Bar timestamp (ET) | Regime | Correct H | Correct L | ZZ H | ZZ L | StructLock H | StructLock L | ZZ verdict | StructLock verdict | Failure mode | Notes |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 2026-04-29 ~16:50 | (TBD) | 7223.00 | 7146.25 | 7223.00 | 7146.25 | 7223.00 | 7146.25 | match | match | correct | Seed; both engines agree |
| | | | | | | | | | | | |
| | | | | | | | | | | | |

## 4h

| Bar timestamp (ET) | Regime | Correct H | Correct L | ZZ H | ZZ L | StructLock H | StructLock L | ZZ verdict | StructLock verdict | Failure mode | Notes |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 2026-04-29 ~16:50 | trend_up | ~7200 | ~6352 | ~7237 (T4) | (multi-month base) | 6654.75 | 6352.00 | wrong_leg | wrong_leg | StructLock=stale_leg_lock; ZZ=stale_pivot_anchor | Seed; both fail in opposite directions |
| | | | | | | | | | | | |
| | | | | | | | | | | | |

---

## Summary (fill in after full pass)

| TF | Total examples | ZZ matches | StructLock matches | Dominant failure mode | Conclusion |
|---|---|---|---|---|---|
| 5m  | | | | | |
| 15m | | | | | |
| 30m | | | | | |
| 1h  | | | | | |
| 4h  | | | | | |

### Decision criteria

- If ZZ or StructLock matches dominate (≥80%) per TF: that engine is acceptable on that TF; no anchor change needed there.
- If failures are dominantly stale-leg / stale-pivot: leg-freshness fix is justified. Open new plan that builds on `docs/plans/2026-04-10-fib-engine-fix-design.md`.
- If results vary per TF: per-TF threshold scaling is the smaller fix.

---

## What This Sheet Does NOT Do

- Propose Pine changes (data collection only)
- Run Optuna or backtests (anchor correctness comes first, after the confirmation-gate phase wraps)
- Override any locked rule (fib core stays untouched until labeled evidence justifies and Architect approves)
- Pre-judge engine outcomes — operator visual judgment is the dataset.
