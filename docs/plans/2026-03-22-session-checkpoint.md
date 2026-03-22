# Session Checkpoint — 2026-03-22

> **For Claude:** This is a progress snapshot. Read before any new session on warbird-pro.

---

## Completed Today

### P0 + Phase 1 — Ground Zero + Series Inventory (7 commits)

| Commit | What |
|--------|------|
| 945b79a | Design doc + execution plan committed |
| af4dcb9 | WARBIRD_CANONICAL.md archived |
| b680c3b | Legacy scripts deprecated with hard exit |
| fd729c0 | Admin UI reference updated to Phase 4 path |
| b4c69ec | Anti-contamination guard + scripts/ag/ directory |
| 764860d | Legacy lineage audit documented |
| 5d1ee76 | Series inventory freeze doc created |

### Phase 2 — Pine Script v2 Indicator (7 commits)

| Commit | What |
|--------|------|
| 0988187 | v2 scaffold from v1 |
| 8fe696a | Canonical 10-level constants |
| 122e61f | Range-weighted confluence scoring |
| ca6f4ec | All 10 lines + zone fill |
| eb318b7 | No-repaint audit |
| 135797e | TARGET 3 alert |
| 176965e | Plan + reference indicators tracked |

### Phase 2 Bug Fixes (3 commits)

| Commit | Fix | What |
|--------|-----|------|
| b8969f9 | F1 | `ta.barssince` → `var int lastBreakBar` with reset on anchor change |
| 39f79aa | W2/W10 | All signal conditions gated on `barstate.isconfirmed` |
| 13a1ea7 | W3/W7 | Midpoint hysteresis band (±2% of range) prevents direction flicker |

### Phase 2 Logic Overhaul (6 commits)

| Commit | Checkpoint | What |
|--------|------------|------|
| 656b12c | 1 | Regime detection: ADX(14), DI spread, ADX slope, ER(10/20), VIX percentile, ATR% |
| 1efda03 | 2 | HTF fib confluence: 1H/4H/Daily with tuple syntax (3 calls), alignment scoring |
| 3fba2ee | 3 | Volume delta: CLV-weighted signed volume, fib touch detection |
| 9731185 | 4 | Chart cleanup: removed all 8 plotshape markers |
| 37ca572 | 5 | Sidebar stats bar: 8-row table, GitHub Dark palette, configurable styling |
| 2de9b8c | 6 | Feature export: 23 hidden plots tagged with AG feature matrix column names |

**Indicator stats:** 780 lines, 14 active request.security() calls (16 budgeted of 40), 23 hidden AG feature plots.

### Phase 2.5 — Validation (read-only)

**Pine v6 Syntax:** VALID — no fixes needed.

**Logic Testing:** 2 FAILs, 10 WARNs.

| # | Issue | Severity |
|---|-------|----------|
| F1 | `ta.barssince(breakInDir)` persists across anchor changes — accept can fire on previous fib structure | Medium (false positive risk) |
| F2 | `fibConfluenceScore()` counts self-matches (+3 inflation) | Low (ranking preserved) |
| W2 | `breakInDir`/`breakAgainst` lack `barstate.isconfirmed` — flicker on live bar | Repaint risk |
| W3 | `fibBull` direction flips intra-bar at midpoint | Inverts signal logic momentarily |
| W7 | No hysteresis on midpoint direction detection | Rapid direction flips in chop |
| W10 | One-shot filter doesn't prevent intra-bar alert firing | Premature alerts |
| W1 | EMA on step-function hourly data — laggier than expected | Monitor |
| W4 | News proxy very conservative (VIX 4% + 3/4 score) | May only fire on major macro |
| W8 | Overnight gaps treated as breaks | May or may not be desired |
| W9 | 10 `request.security()` calls = 25% of 40-call budget | Monitor |

### GPT 4.6 Deep Research — Complete

**Regime Detection v1 (ranked):**
1. ADX(14) + signed DI spread + ADX slope — High confidence
2. Efficiency Ratio (10, 20) — Medium-High
3. VIX percentile + MES realized-vol percentile — overlay only
4. SKIP v1: Hurst, FDI (unstable/noisy on short windows)
5. CI(21) as benchmark only — 38.2/61.8 thresholds are folklore

**Feature Matrix v1 — 54 columns:**
- Regime (8): adx_14, di_spread_14, adx_slope_14, er_10, er_20, ci_21, atr_pct_20, vix_pct_252d
- RSI/Momentum (7): rsi_8/14/21_15m, rsi_14_1h/4h, roc_5, roc_10
- Trend/MA (11): EMA 9,20,50,200 + SMA 20,50,200 + HTF EMAs (spaced, NOT dense grid)
- MACD/Stoch/Squeeze (8): macd_hist 3 configs, stoch_k 2 configs, squeeze on/hist, ppo
- Volume/VWAP (7): mfi_14, cmf_20, obv_slope_21, rvol_20, vwap_dist/slope, donchian_pos_20
- Volatility/Target (7): atr_14/21, bb_width_20, kc_width_20, tp1/tp2_atr_mult, retracement_depth_norm
- Microstructure (6): signed_vol_proxy, clv, range*vol, abs_ret*vol, upper/lower_wick_ratio

**Multicollinearity rules:** No adjacent MA lengths. Cluster |rho|>0.85 before SHAP. Prefer price-minus-MA.

**Supabase Migration:**
- pg_cron schedules everything
- Edge Functions own external I/O (FRED, Databento, news, RSS)
- DB functions own data-local compute (detect-setups, score-trades, measured-moves)
- 23 jobs ≈ 200K invocations/month, Pro plan includes 2M
- Edge Function limits: 256MB memory, 400s wall-clock, 2s CPU

### TV Script Research — Priority Ranked

| Priority | Script | Borrow What | For |
|----------|--------|-------------|-----|
| HIGH | Breakout Volume Delta | LTF volume delta at fib touches | AG feature |
| HIGH | Fed Decision Forecast | FRED symbols, regime classification | AG feature |
| MED-HIGH | Bear Market Prob Model | Composite stress score, McClellan, breadth | AG + sidebar |
| MED | Bloomberg FCI Proxy | Financial conditions composite (or NFCI from FRED) | AG feature |
| MED | Trend Filter v2 | Asymmetric percentile deviation as skew | AG feature |
| LOW | DeepTest | Walk-forward methodology + metric checklist | Python pipeline |
| LOW | COT Library | Institutional positioning via Pine import | AG feature |

---

## Locked Decisions

1. **Approach C:** Pine authority + dashboard advisory with sync alerts
2. **Chart cleanliness:** ONLY fibs + entry/exit markers on chart. Everything else in sidebar table.
3. **Sidebar style:** LuxAlgo Market Sentiment Technicals — modern, polished, not flat/archaic.
4. **Cadence:** Weekly retrain, daily SHAP refresh, 15m prediction refresh to dashboard.
5. **Feature matrix:** 54 columns v1, spaced lengths, no dense grids.
6. **Regime v1:** ADX/ER/VIX-vol. Skip Hurst/FDI.
7. **Supabase owns compute:** All crons + functions migrate from Vercel. Vercel = dashboard/API only.
8. **No custom skill replacement:** Use superpowers + memory for domain context.

---

## What's Next

| Phase | What | Who | Status |
|-------|------|-----|--------|
| v2 TV verification | Load overhauled indicator into TradingView | Kirk | Ready |
| Phase 3 | Strategy build + deep backtesting | VSCode | Needs execution plan |
| Phase 4 | Dataset + AG loop + local DB setup | VSCode | Needs execution plan |
| Supabase migration | Vercel crons → pg_cron + Edge Functions | VSCode | Needs execution plan |
| Indicator decision | COT, Volume Delta, Bear Prob, FCI evaluation | All agents | After TV verification |
| GPT research pending | LuxAlgo styling spec + Pine data export methods | GPT 4.6 | In progress |

## Total Commits Today: 23

P0+Phase 1: 7 | Phase 2 initial: 7 | Bug fixes: 3 | Logic overhaul: 6
