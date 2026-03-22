# Checkpoint 4: API Scaffolding Audit

**Date:** 2026-03-19
**Status:** Decision Made
**Checkpoint:** Supabase Architecture Rethink — Checkpoint 4
**Depends on:** Checkpoint 2 (mes_1s cloud ingestion), Checkpoint 3 (DB URL topology)

---

## Decision

**All 17 routes keep.** No routes removed, shrunk, or moved. The existing API scaffolding already maps to the dual-database architecture: cloud routes serve external ingestion, published signals, and chart data. Local infrastructure (training, inference) is additive — it does not displace any existing cloud routes.

---

## Route-by-Route Matrix

### Cron Routes (13 routes, 21 schedules in vercel.json)

| Route | Schedule | What It Does | Decision | Reason |
|-------|----------|-------------|----------|--------|
| `cron/mes-catchup` | `*/5 * * * 0-5` | Databento ohlcv-1m + ohlcv-1h → all mes_* tables | **Keep + Overhaul** | Primary production data path. Needs full overhaul: add ohlcv-1s (Checkpoint 2), optimize pull spacing, rock-solid error handling. See "mes-catchup Overhaul" section below. |
| `cron/cross-asset` | `*/15 * * * *` | Databento ohlcv-1h → cross_asset_1h/1d (sharded) | **Keep** | External API fetch → cloud write. Clean. |
| `cron/fred/[category]` | 9 daily schedules | FRED API → econ_*_1d tables | **Keep** | External API fetch → cloud write. 9 categories, all working. |
| `cron/econ-calendar` | `0 15 * * *` | TradingEconomics + FRED → econ_calendar | **Keep** | External API fetch → cloud write. |
| `cron/news` | `0 16 * * *` | Macro surprise → news_signals | **Keep** | External processing → cloud write. |
| `cron/google-news` | `0 13 * * 1-5` | Google News RSS → econ_news_1d + news_signals | **Keep** | External fetch + NLP → cloud write. |
| `cron/gpr` | `0 19 * * *` | GPR XLS download → geopolitical_risk_1d | **Keep** | External fetch + parse → cloud write. |
| `cron/trump-effect` | `30 19 * * *` | Federal Register → trump_effect_1d | **Keep** | External API fetch → cloud write. |
| `cron/detect-setups` | `*/5 12-21 * * 1-5` | 6-layer Warbird engine → 7 warbird_* tables | **Keep** | Core trading engine. Reads cloud, computes, writes cloud. |
| `cron/score-trades` | `10,25,40,55 * * * 1-5` | Monitor ACTIVE/TP1_HIT setups → update status/events | **Keep** | Cloud-only scoring loop. |
| `cron/measured-moves` | `0 18 * * 1-5` | AB=CD pattern detection → measured_moves | **Keep** | Cloud read + pattern math → cloud write. |
| `cron/forecast` | `30 * * * 1-5` | Health check + invoke external forecast writer | **Keep** | Cloud-to-local relay bridge. Explicitly dual-target by design. |

### Public API Routes (5)

| Route | Purpose | Decision | Reason |
|-------|---------|----------|--------|
| `live/mes15m` | Chart initial snapshot (last N 15m bars) | **Keep** | Cloud SELECT → serve. Powers chart `setData()`. |
| `warbird/signal` | Current WarbirdSignal v1.0 | **Keep** | Cloud read composition → published signal. |
| `warbird/history` | Setup history for backtesting | **Keep** | Cloud SELECT → serve published history. |
| `pivots/mes` | Traditional pivot levels | **Keep** | Cloud read + math → chart overlay. |
| `admin/status` | System health (all tables, job logs, setups) | **Keep** | Cloud health dashboard. Future: add local health endpoint separately. |

---

## Reasoning

### All routes fit the cloud publication boundary

The dual-database architecture adds a local training warehouse. It does not replace the cloud publication layer. Every existing route falls into one of these patterns:

1. **External API → Cloud write** (mes-catchup, cross-asset, fred, econ-calendar, news, google-news, gpr, trump-effect)
2. **Cloud read → Cloud write** (detect-setups, score-trades, measured-moves)
3. **Cloud read → Serve** (live/mes15m, warbird/signal, warbird/history, pivots/mes, admin/status)
4. **Cloud → Local relay** (forecast — invokes external writer URL)

None of these patterns conflict with adding local PostgreSQL for training.

### No routes are dead or superseded

Every route in `vercel.json` has an active purpose. No route has been made obsolete by checkpoint decisions 1-3.

### The forecast route is the explicit bridge

`cron/forecast` already implements the cloud-to-local bridge pattern: it runs on Vercel Cron, invokes `WARBIRD_FORECAST_WRITER_URL` (which points to a local or external inference endpoint), then checks if fresh forecasts appeared in cloud Supabase. This is the publication pattern the architecture rethink envisions — local inference writes results to cloud, cloud cron verifies freshness.

### detect-setups stays cloud

At ~600 lines, detect-setups is the heaviest compute route. It runs the full 6-layer Warbird engine (daily bias → 4H structure → 1H forecast → 15m fib geometry → conviction → trigger). All inputs come from cloud tables. All outputs go to cloud tables. Moving this local would violate the production boundary rule ("production crons must not depend on local machines"). It stays.

### admin/status will evolve

Currently checks only cloud tables. In the dual-DB future, local pipeline health (local PG connectivity, training freshness, sync status) would be a separate concern — either a local script or a new route that the forecast relay pattern could surface. Not a current change.

---

## mes-catchup Overhaul

The current mes-catchup route is functional but not production-hardened. It needs a full overhaul, not just an ohlcv-1s addition.

### Current Problems

1. **Dual-fetch in one call** — Fetches ohlcv-1m AND ohlcv-1h in the same cron invocation. If one fails, both fail.
2. **No pull spacing** — All schemas fetched back-to-back in the same 60s window.
3. **Aggregation in-memory** — 15m/4h/1d derived in TypeScript during the same invocation. More work = more timeout risk.
4. **Single monolithic function** — ~260 lines doing fetch + upsert + aggregate + log. Hard to debug, hard to isolate failures.

### Overhaul Principles

| Principle | Why |
|-----------|-----|
| **Space pulls evenly** | Never stack all symbol/schema pulls at the same time. Spread across available windows. Less API limit risk. |
| **One concern per invocation** | Separate ohlcv-1s, ohlcv-1m, ohlcv-1h into distinct cron schedules or sharded invocations. |
| **Fail independently** | If 1s fetch fails, 1m and 1h should still work. Isolation per schema. |
| **Stagger daily pulls overnight** | Any heavy backfill or daily aggregation should run during off-hours, not stacked at market open. |
| **Rock-solid error handling** | Retry logic, partial success logging, clear error messages per schema. |

### Databento Free Schema Inventory

GLBX.MDP3 offers 11 schemas. **6 are FREE** on the Standard $179/mo plan:

| Schema | Free? | What It Gives Us | Current Usage | Target Usage |
|--------|-------|-----------------|---------------|-------------|
| `ohlcv-1s` | **FREE** | 1-second OHLCV bars | Not fetched | MES only (ephemeral, Checkpoint 2) |
| `ohlcv-1m` | **FREE** | 1-minute OHLCV bars | MES only | MES + key cross-assets |
| `ohlcv-1h` | **FREE** | 1-hour OHLCV bars | MES + cross-asset | All symbols |
| `ohlcv-1d` | **FREE** | Daily OHLCV bars | Not fetched | **All symbols** (tiny, one pull/day) |
| `definition` | **FREE** | Contract specs, expiry, strike (options), tick size, multiplier | Not fetched | **All symbols** (instrument enrichment) |
| `statistics` | **FREE** | Settlement, OI, volume, session H/L, opening price | Not fetched | **All symbols** (daily stats enrichment) |
| `trades` | PAID ~$3.15/wk | Individual trades | Skip | Skip |
| `mbp-1` | PAID ~$4.56/wk | Best bid/offer + last trade | Skip | Skip (needed for greeks — future decision) |
| `tbbo` | PAID ~$5.25/wk | Top of book BBO | Skip | Skip |
| `mbo` | PAID ~$5.68/wk | Full order book | Skip | Skip |
| `mbp-10` | PAID ~$8.06/wk | 10-level depth | Skip | Skip |

### What Statistics Gives Us (FREE, CME stat_types)

Available for BOTH futures AND options:
- `SETTLEMENT_PRICE` (3) — daily settlement price
- `OPEN_INTEREST` (9) — open interest
- `CLEARED_VOLUME` (6) — cleared volume
- `OPENING_PRICE` (1) — opening price
- `SESSION_HIGH` (5) / `SESSION_LOW` (4) — session range
- `HIGHEST_BID` (8) / `LOWEST_OFFER` (7) — best bid/offer at close
- `FIXING_PRICE` (10) — fixing price
- `INDICATIVE_OPENING_PRICE` (2) — pre-open indicative

### What Definition Gives Us (FREE)

For futures: symbol, expiry date, tick size, min price increment, contract multiplier, trading hours.
For options: all of the above PLUS strike price, put/call, underlying symbol. This maps every option contract to its underlying.

### Options Greeks — NOT Free

Computing greeks (Delta, Gamma, Theta, Vega, IV) requires `mbp-1` (paid ~$4.50/wk) + `definition` (free) + Black-76 model. Deferred to a future cost decision if needed.

### Target MES Route Architecture

```
cron/mes-1s         — */5 * * * 0-5     (ephemeral 1s bars for forming candle)
cron/mes-1m         — */5 * * * 0-5     (1m bars, offset from 1s)
cron/mes-1h         — 5 * * * 0-5       (1h bars, hourly)
cron/mes-1d         — 0 22 * * 0-5      (daily bar, once after session close)
cron/mes-stats      — 30 22 * * 0-5     (statistics: settlement, OI, volume)
cron/mes-definition — 0 3 * * 0-5       (contract definitions, daily refresh)
cron/mes-aggregate  — 2,7,12 * * * 0-5  (derive 15m/4h from stored bars)
```

### Target Cross-Asset Route Architecture

```
cron/cross-asset-1h    — */15 * * * *      (existing sharded 1h, keep)
cron/cross-asset-1d    — 0 23 * * *        (daily bars, all symbols, once/night)
cron/cross-asset-stats — 30 23 * * *       (statistics: settlement, OI, volume)
cron/cross-asset-def   — 0 4 * * *         (contract definitions, daily refresh)
```

### Target Options Route Architecture (NEW)

```
cron/options-1d        — 0 0 * * 1-5       (daily OHLCV for active option contracts)
cron/options-stats     — 30 0 * * 1-5      (settlement, OI, volume per option)
cron/options-def       — 0 1 * * 1-5       (option definitions: strikes, expiry, underlying)
```

### Spacing Strategy

All daily/nightly pulls spread across **22:00–04:00 UTC** (off-hours):

| Time (UTC) | Route | Notes |
|------------|-------|-------|
| 22:00 | mes-1d | After session close |
| 22:30 | mes-stats | Settlement + OI |
| 23:00 | cross-asset-1d | Daily bars all symbols |
| 23:30 | cross-asset-stats | Settlement + OI all symbols |
| 00:00 | options-1d | Daily option bars |
| 00:30 | options-stats | Option settlement + OI |
| 01:00 | options-def | Option contract definitions |
| 03:00 | mes-definition | MES contract definitions |
| 04:00 | cross-asset-def | Cross-asset contract definitions |

Intraday pulls (MES only) stay in market hours:

| Schedule | Route | Notes |
|----------|-------|-------|
| `*/5 * * * 0-5` | mes-1s | Ephemeral forming bar |
| `*/5 * * * 0-5` | mes-1m | 1m bars (offset) |
| `5 * * * 0-5` | mes-1h | Hourly |
| `2,7,12 * * * 0-5` | mes-aggregate | Derive 15m/4h |

**Principle: each pull is isolated, spaced, and can fail independently. No stacking.**

### Broader Principle (All Routes)

- FRED 9 categories already staggered hourly (good)
- cross-asset 1h already sharded (good)
- News/GPR/Trump-effect already spread across afternoon/evening (good)
- **MES needs overhaul** — split monolith into per-schema routes
- **Cross-asset needs enrichment** — add 1d, statistics, definition
- **Options are entirely new** — 1d, statistics, definition pulls

### Data Enrichment Impact on AutoGluon Training

| New Data Source | Training Value |
|----------------|---------------|
| `ohlcv-1d` (all symbols) | Clean daily bars without aggregation artifacts |
| `statistics/settlement` | Authoritative daily close (not last trade) |
| `statistics/open_interest` | Positioning signal, regime detection |
| `statistics/cleared_volume` | True volume (not just electronic) |
| `statistics/session_high_low` | True range (exchange-official, not derived) |
| `definition` (futures) | Contract metadata for roll-aware features |
| `definition` (options) | Strike/expiry mapping for vol surface features |
| `options ohlcv-1d` | Option price action for sentiment/hedging signals |
| `options statistics` | Option OI + volume for put/call ratio features |

## What Changes Summary

| Route | Change |
|-------|--------|
| `mes-catchup` | **Full overhaul**: split into mes-1s, mes-1m, mes-1h, mes-1d, mes-stats, mes-definition, mes-aggregate |
| `cross-asset` | **Enrich**: add cross-asset-1d, cross-asset-stats, cross-asset-def routes |
| Options | **New**: options-1d, options-stats, options-def routes |
| All other cron routes | No changes |
| All public API routes | No changes |

---

## Verification Checklist

| Rule | Passes? | Note |
|------|---------|------|
| Plan: do not preserve routes just because they exist | Yes | All 17 routes independently justified |
| Plan: preserve only routes that serve final architecture | Yes | Each route maps to a clear architectural role |
| AGENTS.md: production boundary (no local dependency) | Yes | All cron routes depend only on cloud + external APIs |
| AGENTS.md: 13 cron routes match | Yes | 13 route files, 21 schedules in vercel.json |
| Cost boundary | Yes | No new routes, no new API calls |
| AGENTS.md: no dead schedules in vercel.json | Yes | All 21 schedules have active routes |

---

## Implementation Implications

1. **No routes to remove.** All 17 stay.
2. **No routes to add.** Local health monitoring is a future concern.
3. **mes-catchup evolves** per Checkpoint 2 (add ohlcv-1s fetch) — separate implementation task.
4. **vercel.json stays as-is.** 21 schedules are all active and correct.
5. **Future: local sync/publish script** — Not a Vercel route. Runs locally, pushes to cloud. Designed in Checkpoint 5 (schema ownership).
