# WARBIRD MODEL SPEC — v2

**Date:** 2026-03-16 · **Author:** Kirk Musick / Claude · **Status:** DRAFT

This document defines exactly what the Warbird ML model does, how it does it, what data it uses, and why. It supersedes any prior version or training pipeline code that contradicts it.

---

## 1. WHAT THE MODEL IS

The model evaluates **fib setups on 1H candles**. It does not predict price.

When price interacts with a 1H fib level and conditions align, a setup forms. The model scores that setup: is this a good one? Will it reach TP1? TP2? How much adverse excursion should the trader expect?

The model learns these things from historical outcomes. We don't tell it anything about fib theory. We give it the data and let it figure it out.

---

## 2. ONE FIB LAYER — 1H

The 1H fib engine identifies the structure and the trigger. One computation. One timeframe.

It computes levels: .236, .382, .5, .618, .786, 1.0, 1.236 (TP1), 1.618 (TP2).

It uses Fibonacci-sequence lookback periods (8, 13, 21, 34, 55 bars) with multi-period confluence scoring. **Not zigzag.** The best anchor is selected by confluence count × range.

A setup triggers when a 1H bar closes at or through a fib level with the right context. That is the GO signal.

---

## 3. WHAT THE MODEL TRAINS ON

### The Training Row

Each row represents a **setup that occurred at a 1H fib level**. Not a random hourly candle.

A setup is identified historically by scanning 1H candles for fib structures and finding moments where price interacted with a fib level and trigger conditions were met.

### Target Labels (Fib-Relative Outcomes)

All targets are measured relative to the setup entry, not raw price:

| Target | Type | Description |
|--------|------|-------------|
| `reached_tp1` | Binary (0/1) | Did price reach the 1.236 extension? |
| `reached_tp2` | Binary (0/1) | Did price reach the 1.618 extension? |
| `max_adverse_excursion` | Continuous (points) | Furthest price moved against the setup from entry |
| `max_favorable_excursion` | Continuous (points) | Furthest price moved in setup direction from entry |
| `setup_stopped` | Binary (0/1) | Did price hit the stop loss before reaching TP1? |

**Stop definition:** Price closes back through the 0.0 level (full retracement of the anchor swing).

**Setup ends when:** Price hits TP2, hits the stop, or a new conflicting anchor forms that invalidates the structure.

### Feature Groups

| Group | Features |
|-------|----------|
| **Fib context** | Fib ratio at entry (.382/.5/.618/.786), retracement depth (how deep pulled back from anchor high/low to trigger bar close, as fib ratio), confluence score, anchor age (bars since anchor formed) |
| **Volume** | Volume on trigger bar vs 20-bar avg, volume trend (expanding/contracting last 5 bars), relative to session avg |
| **Daily bias** | Above or below 200d EMA (binary) |
| **4H structure** | HH/HL or LH/LL, agrees with daily bias (binary), trend score |
| **Cross-asset** | NQ correlation, DXY direction, VIX level, yield direction — at trigger moment |
| **FRED/macro** | Forward-filled FRED series values at setup time (~47 series, raw + regime-anchored) |
| **Calendar** | Hours to next high-impact event, high-impact today (binary) |
| **News** | Net sentiment last 24h, layer count |
| **Risk/vol** | GARCH sigma, vol ratio, GPR level, trump events last 7d |
| **Regime** | Days into regime, regime label |
| **Time** | Hour (Central), day of week, session (US/EU/Asia), month |
| **Sample weight** | Exponential decay: newest=1.0, oldest=0.3 |

---

## 4. WHAT THE MODEL DOES NOT DO

- Does not predict raw price
- Does not have a runner target or runner logic
- Does not detect micro-pullbacks (requires tick data)
- Does not use zigzag for fib computation
- Does not have time-based expiry on setups (price action only)

---

## 5. THE 5-MINUTE CRON LOOP

Runs every 5 minutes, 6:00 AM to 4:00 PM Central.

Every run:
1. **Read latest closed 1H bar** and current price
2. **Refresh 1H fib structure** (only changes on new 1H bar close)
3. **Check for new setups** — is price at a 1H fib level with trigger conditions met?
4. **Score new setups** through the model → GO / NO-GO
5. **Monitor active setups** — TP1 hit? TP2 hit? Stopped?
6. **Push signal state** to Supabase → API → dashboard

Most 5M checks see the same 1H bar. Those runs just monitor active setup state against current price. When a new 1H bar closes, that's when new triggers can fire.

---

## 6. CONVICTION MATRIX

Rule-based. No ML.

| Condition | Level |
|-----------|-------|
| Daily + 4H + 1H all agree | MAXIMUM |
| Daily + 4H agree, 1H trigger GO | HIGH |
| Daily + 4H agree, 1H trigger weak | MODERATE |
| Daily neutral, 4H + 1H agree | MODERATE |
| Counter-trend (daily opposes) | LOW — TP1 only, reduced size |
| Disagreement | NO_TRADE |

---

## 7. TRADE TARGETS

- **TP1** = 1.236 fib extension. Exit.
- **TP2** = 1.618 fib extension. Exit.
- **No runners.** Full exit at TP2.
- **Counter-trend:** TP1 only. Always.

---

## 8. AUTOGLUON CONFIGURATION

```python
predictor = TabularPredictor(
    label=target_col,
    eval_metric='root_mean_squared_error',  # or 'log_loss' for binary targets
    path=output_dir,
)
predictor.fit(
    train_data=train,
    presets='best_quality',
    num_bag_folds=5,
    num_stack_levels=1,
    dynamic_stacking='auto',
    excluded_model_types=['KNN', 'FASTAI'],
    ag_args_ensemble={'fold_fitting_strategy': 'sequential_local'},
)
```

5 predictors trained separately — one per target label. Binary targets (`reached_tp1`, `reached_tp2`, `setup_stopped`) use `log_loss`. Continuous targets (`max_adverse_excursion`, `max_favorable_excursion`) use `RMSE`.

---

## 9. HARD RULES

- Model evaluates 1H fib setups. Not price.
- One fib layer. 1H candles only.
- No runner logic. TP1 and TP2 only.
- No tick data. No micro-pullback detection.
- No time-based expiry. Price action only.
- 200d EMA: above or below. Binary. Keep simple.
- Custom fib engine with Fibonacci-sequence lookbacks. Not zigzag.
- 5M cron is infrastructure. 1H candles are the fib structure and the trigger.
- No mocked data. Real or nothing.

---

*Designed and architected by Kirk Musick, MS, MBA*
