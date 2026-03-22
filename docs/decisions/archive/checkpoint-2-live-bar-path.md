# Checkpoint 2: Live Bar Formation Path

**Date:** 2026-03-18
**Status:** Decision Made (Revised)
**Checkpoint:** Supabase Architecture Rethink — Checkpoint 2
**Depends on:** Checkpoint 1 (Plain local PostgreSQL chosen)

---

## Decision

**`mes_1s` is the canonical ingestion layer that powers the forming 15m bar.** The data flows:

```
mes_1s (ingestion) → mes_1m (derived) → mes_15m (derived)
```

- `mes_1s` is written to cloud Supabase as **ephemeral live data** (not retained for training).
- `mes_1m` is derived from `mes_1s` by aggregating 60 × 1s bars into 1 × 1m bar.
- `mes_15m` is derived from `mes_1m` by aggregating 15 × 1m bars into 1 × 15m bar.
- The chart subscribes to `mes_1s` Realtime and builds the forming 15m candle client-side from incoming 1s bars.
- `mes_1s` is cleaned up periodically (retain only recent 24-48h). It is NOT synced to local PG for training.

The local PostgreSQL warehouse (Checkpoint 1) receives only `mes_1m` and higher for training.

---

## Options Evaluated

### Option A: `mes_1s` via cron-batched Historical API (chosen)

Extend the existing mes-catchup Vercel Cron to also fetch `ohlcv-1s` from Databento Historical API every 5 minutes. Write 1s bars to cloud Supabase `mes_1s`. Chart subscribes via Realtime.

**Data flow per cron cycle:**

```
Cron fires (every 5 min)
  → Databento Historical: fetch ohlcv-1s for gap window
  → INSERT ~300 rows into mes_1s (cloud Supabase)
  → Supabase Realtime pushes 1s bars to browser
  → Browser aggregates 1s bars into forming 15m candle
  → Separately: derive completed mes_1m bars from mes_1s
  → Separately: derive completed mes_15m bars from mes_1m
```

**Forming bar timeline (e.g., 10:00–10:15 bar):**

```
10:00  cron fires → inserts 1s bars through ~09:58
       → chart has no 10:00+ data yet
10:05  cron fires → inserts ~300 new 1s bars (10:00:00 through ~10:03:00)
       → Realtime pushes each 1s bar → chart builds forming candle from 180+ data points
       → derives completed 1m bars: 10:00, 10:01, 10:02
10:10  cron fires → inserts ~300 more 1s bars (10:03:00 through ~10:08:00)
       → chart updates forming candle with ~480 total data points
       → derives completed 1m bars: 10:03, 10:04, 10:05, 10:06, 10:07
10:15  cron fires → inserts remaining 1s bars
       → derives completed 1m bars: 10:08 through 10:14
       → aggregation creates completed mes_15m bar for 10:00
       → Realtime pushes completed 15m bar → chart finalizes candle
```

**Strengths:**
- Honors the canonical `mes_1s → mes_1m → mes_15m` derivation chain.
- `ohlcv-1s` is FREE on Standard plan ($0, included with $179/mo subscription).
- Cloud-only: no local machine dependency for chart serving.
- Forming bar gets ~300 granular data points per cron cycle instead of ~5 (1m resolution).
- Reuses existing cron infrastructure (no new services).
- Ephemeral `mes_1s` with TTL cleanup — not retained for training.
- 5-minute batch latency is within AGENTS.md acceptable bounds.

**Weaknesses:**
- 5-minute batch latency. Chart updates in 5-min steps, not true real-time. Each step is highly granular (1s resolution), but there's still a 5-min gap between batches.
- `mes_1s` volume: ~300 rows per 5-min cron × ~276 crons/day ≈ ~83K rows/day. Needs TTL cleanup.
- Databento Historical API has ~2 min delay for most recent data.

### Option B: Databento Live WebSocket → cloud relay → `mes_1s`

Use Databento Live (streaming) API with a persistent cloud process (Supabase Edge Function, Cloudflare Worker, or similar) to relay 1s bars in true real-time.

**Strengths:**
- True sub-second chart updates. The forming bar moves with the market.
- Lowest possible latency.

**Weaknesses:**
- Requires a persistent WebSocket connection in the cloud (adds operational complexity).
- Databento Live API cost and licensing may differ from Historical.
- Edge Functions have execution time limits (may not sustain persistent connections).
- Significantly more complex than extending the existing cron.
- Over-engineering for v1 scope.

### Option C: No `mes_1s` — use `mes_1m` only (rejected by user)

Previously proposed in the initial Checkpoint 2 draft. Rejected: user requires `mes_1s` to power the forming bar.

---

## Reasoning

### `mes_1s` is canonical — the plan drops it from training, not from ingestion

The WARBIRD_CANONICAL.md bar authority map is explicit:

> - `mes_1s` — canonical continuity ingestion layer
> - `mes_1m` — trigger-resolution layer (derived from `mes_1s` when available)
> - `mes_15m` — primary setup/model/chart layer (derived from stored `mes_1m`)

The architecture rethink plan drops `mes_1s` from **retained training** architecture. It does not drop it from the live ingestion path. The plan explicitly allows: "If live bar formation is needed, use a separate ephemeral live-feed path only for the currently forming chart bar."

`mes_1s` IS that ephemeral live-feed path.

### Ephemeral vs retained boundary

| Data | Location | Retained? | Purpose |
|------|----------|-----------|---------|
| `mes_1s` (cloud Supabase) | Cloud | **No** — TTL cleanup, keep 24-48h | Live forming bar, continuity ingestion |
| `mes_1m` (cloud Supabase) | Cloud | Yes (chart history) | Completed bars, Realtime source, derived from 1s |
| `mes_15m` (cloud Supabase) | Cloud | Yes (chart history) | Completed 15m candles |
| `mes_1m` (local PG) | Local | Yes (training) | Training warehouse |
| `mes_15m_mv` (local PG) | Local | Yes (materialized view) | Training features |
| Forming 15m bar | Browser only | No (ephemeral) | Live candle display, built from 1s Realtime |

The forming bar lives in the browser's JavaScript state, built from `mes_1s` Realtime events. It is replaced by the completed `mes_15m` bar when the 15m window closes.

`mes_1s` rows in cloud Supabase are ephemeral — cleaned up after 24-48h by a scheduled job. They serve only the live chart path.

### Cost safety

`ohlcv-1s` is a free schema on the Databento Standard CME plan. No additional cost.

Data volume per day: ~82,800 rows (23h × 3600s/h). At ~100 bytes/row, that's ~8MB/day. With 48h retention: ~16MB max in `mes_1s`. Trivial for Supabase cloud.

### `mes_1m` derivation moves to DB

With `mes_1s` as the ingestion layer, `mes_1m` should be derived from `mes_1s` rather than fetched separately from Databento. This eliminates the current dual-fetch (`ohlcv-1m` + `ohlcv-1h`) and replaces it with a single `ohlcv-1s` fetch plus DB-side aggregation:

```sql
-- Derive mes_1m from mes_1s (run after each 1s batch insert)
INSERT INTO mes_1m (ts, open, high, low, close, volume)
SELECT
  date_trunc('minute', ts) AS ts,
  (array_agg(open ORDER BY ts))[1] AS open,
  max(high) AS high,
  min(low) AS low,
  (array_agg(close ORDER BY ts DESC))[1] AS close,
  sum(volume) AS volume
FROM mes_1s
WHERE ts >= [last_derived_1m_ts]
GROUP BY date_trunc('minute', ts)
HAVING count(*) >= 50  -- only complete-ish minutes (allow small gaps)
ON CONFLICT (ts) DO UPDATE SET
  open = EXCLUDED.open, high = EXCLUDED.high,
  low = EXCLUDED.low, close = EXCLUDED.close,
  volume = EXCLUDED.volume;
```

This aligns with the plan's goal: "Move aggregation to Postgres functions — not TypeScript."

### Option A is simpler and sufficient

Option B (Databento Live WebSocket) provides true real-time but adds a persistent cloud process, new API integration, and operational complexity. For a single-user intelligence platform running a 15m-primary model, 5-minute batched 1s data is more than sufficient. The forming bar updates with ~300 granular data points per cycle — visually smooth.

True real-time via Live API is a clear v2 upgrade path if sub-second responsiveness becomes necessary.

---

## Verification Checklist

| Rule | Passes? | Note |
|------|---------|------|
| Plan: live-bar logic must be ephemeral and chart-only | Yes | `mes_1s` ephemeral (24-48h TTL), forming bar is browser-only |
| Plan: clear separation between retained and ephemeral | Yes | `mes_1s` ephemeral cloud, `mes_1m` retained both cloud + local |
| Plan: no retained `mes_1s` for training | Yes | `mes_1s` not synced to local PG, TTL cleanup in cloud |
| AGENTS.md: `mes_1s` is canonical continuity ingestion layer | Yes | Preserved as ingestion layer |
| AGENTS.md: `mes_1m` derived from `mes_1s` when available | Yes | DB aggregation: 1s → 1m |
| AGENTS.md: no continuous local runtime for chart serving | Yes | Cloud-only via Vercel Cron + Supabase |
| AGENTS.md: 5-minute maximum acceptable latency | Yes | Cron runs every 5 min |
| WARBIRD_CANONICAL.md: `series.update()` for live ticks | Yes | Realtime `mes_1s` → `series.update()` in chart |
| Cost boundary | Yes | `ohlcv-1s` is free on Standard plan |
| Production boundary | Yes | Dashboard depends only on cloud Supabase |

---

## Implementation Implications

1. **Extend mes-catchup cron:** Replace `ohlcv-1m` + `ohlcv-1h` dual-fetch with single `ohlcv-1s` fetch. Write to `mes_1s` table.
2. **DB-side derivation:** Postgres function to aggregate `mes_1s → mes_1m`. Called after each 1s batch insert (trigger or explicit call in cron).
3. **Keep existing `mes_1m → mes_15m/1h/4h/1d` aggregation** — can stay in TypeScript initially, migrate to DB functions per plan.
4. **`mes_1s` table in cloud Supabase:** New migration. Ephemeral. Realtime enabled.
5. **TTL cleanup job:** `pg_cron` or Vercel Cron to `DELETE FROM mes_1s WHERE ts < now() - interval '48 hours'`.
6. **Chart update:** `LiveMesChart.tsx` subscribes to `mes_1s` Realtime (instead of or in addition to `mes_1m`) for forming-bar updates.
7. **Local PG:** No `mes_1s` table. Receives `mes_1m` only via backfill/sync.
8. **Future upgrade path (v2):** Databento Live WebSocket → cloud relay for true sub-second updates.

## Sources

- [Databento OHLCV schemas](https://databento.com/docs/schemas-and-data-formats/ohlcv)
- [Databento Historical API](https://databento.com/docs/api-reference-historical)
- Databento Standard plan memory: `ohlcv-1s` confirmed free ($0, included)
