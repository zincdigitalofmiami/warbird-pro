# Candlestick Pattern TF-Priority Data — MES1!

**Date:** 2026-04-29
**Status:** Research — empirical evidence for the next Optuna confirmation-gate phase
**Source:** "Candlestick Patterns on Backtest" by MUQWISHI (MPL 2.0). Reference copy: `.references/candlestick-patterns-on-backtest-MUQWISHI.pine`
**Companion plan:** `docs/plans/2026-04-29-confirmation-gate-optuna-phase.md`
**Constraint:** This doc is fat-cut to the actionable evidence. It does not duplicate methodology coverage that already exists in the saved reference Pine source.

## Sign convention (proven from MUQWISHI source backtest function)

- **Positive %** = pattern's labeled-direction trade was profitable over the backtest window.
- **Negative %** = pattern's labeled-direction trade lost money. The pattern fails as a directional signal.
- All cells are compounded equity returns at 1× leverage, ATR(14) stop × 1.0, R:R selectable per column, SMA(50) trend filter ON by default.

## Per-TF empirical winners — at R:R 1:4 / 1:5 / 1:6 (where pattern edge typically shows)

Sample windows are bar-history-bounded by TradingView, NOT user-chosen. They cap how authoritative each TF's data is.

### 5m (window 2026-01-11, ~3 months — TOO SHORT to be authoritative)

| Pattern | 1:4 | 1:5 | 1:6 |
|---|---|---|---|
| Engulfing (Bear) | +1.77% | +4.08% | +5.62% / +6.43% |
| Tweezer Top (Bear) | small + | small + | small + |

Treat 5m as preliminary only.

### 10m (window 2025-09-28, ~7 months)

| Pattern | 1:4 | 1:5 | 1:6 |
|---|---|---|---|
| Long Upper Shadow (Bear) | +3.78% | +3.66% | +3.69% |
| Tweezer Bottom (Bull) | +1.41% | +3.76% | +6.89% |
| Engulfing (Bear) | +1.59% | +1.82% | +1.72% |

### 15m (window 2025-06-01, ~11 months)

| Pattern | 1:4 | 1:5 | 1:6 |
|---|---|---|---|
| Long Lower Shadow (Bull) | +3.06% | +1.76% | +8.37% |
| Marubozu Black (Bear) | +1.41% | +0.80% | +1.66% |

15m has fewer clean winners than expected — mostly because the dashboard's SMA(50) trend filter on 15m is much shorter-lived than on higher TFs, making single-direction wins rarer.

### 30m (window 2024-01-01, ~28 months)

| Pattern | 1:4 | 1:5 | 1:6 |
|---|---|---|---|
| Engulfing (Bull) | +22.75% | +30.06% | +22.08% |
| Long Lower Shadow (Bull) | +14.98% | +22.50% | +31.86% |
| Hammer (Bull) | +6.38% | +9.83% | +11.62% |
| Tweezer Bottom (Bull) | +9.76% | +10.68% | +14.05% |
| Doji Star (Bull) | +5.99% | +6.18% | +1.86% |

### 1h (window 2022-04-13, ~4 years)

| Pattern | 1:4 | 1:5 | 1:6 |
|---|---|---|---|
| Falling Window (Bear) | +9.16% | +13.60% | +15.39% |
| Marubozu White (Bull) | -3.72% | -5.12% | -11.37% — LOSER |
| Dragonfly Doji (Bull) | +0.73% (1:1.5 +3.66%, 1:2 +5.06%) | small | flat |

1h has fewer clean high-R:R winners but a strong Falling Window signal.

### 4h (window 2019-05-05, ~7 years — most reliable)

| Pattern | 1:4 | 1:5 | 1:6 |
|---|---|---|---|
| Engulfing (Bull) | +10.45% | +17.54% | +14.39% |
| Engulfing (Bear) | +15.03% | +0.10% | +9.06% |
| Tweezer Bottom (Bull) | +19.71% | +25.87% | (clipped) |
| Marubozu White (Bull) | +7.31% | +15.35% | +17.01% |
| Doji Star (Bear) | +5.76% | +4.94% | +1.96% |

## Cross-TF candidate set for Optuna (consensus winners)

Patterns that win on ≥2 timeframes with reliable sample size (≥30m):

1. **Engulfing (Bull)** — wins on 30m (+22% to +30%) and 4h (+10% to +17%).
2. **Engulfing (Bear)** — wins on 4h (+9% to +15%) and 5m (+4% to +6%, low confidence).
3. **Tweezer Bottom (Bull)** — wins on 30m (+10% to +14%) and 4h (+19% to +25%).
4. **Long Lower Shadow (Bull)** — wins on 30m (+15% to +32%) and 15m (+8% at 1:6 only).
5. **Hammer (Bull)** — wins on 30m (+6% to +12%). Single-TF.
6. **Falling Window (Bear)** — wins on 1h (+9% to +15%). Single-TF.
7. **Marubozu White (Bull)** — wins on 4h (+7% to +17%). Single-TF (loses on 1h).

**Top-6 candidate slate for the Optuna confirmation-gate phase:** Engulfing (Bull), Engulfing (Bear), Tweezer Bottom (Bull), Long Lower Shadow (Bull), Hammer (Bull), Falling Window (Bear).

## The paste's hardcoded set is wrong, and why

`indicators/v7-warbird-institutional-backtest-strategy.pine` lines ~738-790 commit to a "PROVEN PATTERNS" comment block claiming:
- Long Upper Shadow (-7.7% / 1:6) — "STRONGEST bearish on MES 15m"
- Shooting Star (-5.6% / 1:6) — "strong"
- Bearish Engulfing (-6.6% / 1:6) — "strong at high R:R"
- Falling Window (-1.5% / 1:6) — "moderate"
- Long Lower Shadow (+3.9% / 1:6) — "STRONGEST bullish"
- Dragonfly Doji (+1.2% / 1:6) — "consistent winner"

The paste interprets **negative-return Bear cells as "strong bearish signals."** That conflates *return sign* (did the trade make money?) with *price direction* (which way did price go?). Per the proven sign convention above, a negative cell on a Bear pattern means the short trade lost — i.e., price went UP after the pattern, contrary to the bearish thesis.

Cross-checked on 4h with 7 years of data:
- Long Upper Shadow (Bear): -33.97% / -39.91% — **catastrophic loser as a short signal**
- Bearish Engulfing: +15% / +0% / +9% — **actually a winner** (paste's negative-as-strong reading is inverted)
- Falling Window (Bear): +2.40% / +3.08% — **small winner** (paste called it "-1.5% moderate")

**Net effect:** the paste's confirmation gate green-lights shorts on Long Upper Shadow and Shooting Star, both of which are losers as bear signals on the most reliable TF available. The hardcoded set must be replaced before any Optuna study of the strategy can produce meaningful results.

## Caveats Optuna must respect

1. **MUQWISHI dashboard uses ATR(14) × 1.0 stop, SMA(50) trend filter, "At Close" entry.** Warbird's strategy uses ATR(14) × 1.5 stop (tunable via `optStopAtrMult`), no SMA-50 trend filter on patterns, and bar-close entry plus footprint gate. Pattern returns under Warbird's actual setup will differ from dashboard returns in absolute %, but the relative ranking of patterns should be reasonably preserved.
2. **Sample windows are uneven across TFs.** Optuna validation must include a walk-forward split that respects the available history per TF.
3. **MUQWISHI pattern definitions live in external library `MUQWISHI/CandlestickPatterns/2`.** If Warbird re-implements its own pattern detectors (it currently does), the body/wick thresholds may differ subtly from MUQWISHI's. A pre-Optuna sanity check should fire each Warbird-detected pattern alongside the MUQWISHI dashboard on the same chart and confirm they trigger on the same bars within a tolerance.

## Source dashboards (saved as evidence)

Six chart screenshots delivered by Architect 2026-04-29 — one per timeframe (5m / 10m / 15m / 30m / 1h / 4h) with the MUQWISHI indicator's table visible. Numbers above are read directly from those tables.
