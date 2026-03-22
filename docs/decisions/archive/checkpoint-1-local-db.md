# Checkpoint 1: Local Database Choice

**Date:** 2026-03-18
**Status:** Decision Made
**Checkpoint:** Supabase Architecture Rethink — Checkpoint 1

---

## Decision

**Plain local PostgreSQL** (via Homebrew) is the local training warehouse database.

TimescaleDB is not adopted.

---

## Options Evaluated

### Option A: TimescaleDB (Postgres extension)

**Strengths:**
- Continuous aggregates for 1m -> 15m -> 1h -> 4h -> 1d bar rollups (incremental refresh, not full rebuild)
- Automatic hypertable partitioning (no manual partition DDL)
- `time_bucket()` function purpose-built for OHLCV aggregation
- 10-20x compression on older chunks
- ~3-4x faster analytical queries at scale

**Weaknesses:**
- Documented Apple Silicon installation friction (GitHub issue #2690, workarounds needed)
- Extension coupling to specific PostgreSQL major versions
- Additional RAM overhead for background workers (continuous aggregate refresh, compression)
- Another dependency requiring explicit justification per AGENTS.md
- Potential conflicts with non-Homebrew Postgres installations

### Option B: Plain PostgreSQL (Homebrew native)

**Strengths:**
- Zero extension risk — Homebrew-native on Apple Silicon, no workarounds
- Lower RAM footprint (no background workers for aggregation/compression)
- Simpler operational model (one binary, no extension loading)
- Sufficient for the actual data volume (~700K 1m bars over 2 years)
- Declarative partitioning covers the modest partition count (~24 monthly partitions)
- Materialized views + pg_cron refresh handle bar rollups at this scale
- Fewer moving parts (aligns with AGENTS.md reasoning guardrail)

**Weaknesses:**
- Manual partition creation (monthly DDL, trivially scriptable)
- Materialized views require full rebuild on refresh (not incremental)
- No `time_bucket()` — use `date_trunc()` instead (functionally equivalent at this scale)
- No built-in compression (not needed at ~700K rows)

---

## Reasoning

### Data volume does not justify TimescaleDB

MES futures trade ~23 hours/day, ~5.5 days/week. Over 2 years of training data:

```
~1,380 bars/day x 260 trading days/year x 2 years = ~718,000 rows in mes_1m
```

This is a modest dataset. PostgreSQL handles millions of rows with basic indexing and partitioning without breaking a sweat. TimescaleDB's advantages (20x insert rates, chunked scanning, compression) are material at billions of rows, not hundreds of thousands.

### RAM preservation is a hard constraint

The plan explicitly states: "Docker available but NOT running continuously. RAM reserved for ML training." TimescaleDB runs background workers for continuous aggregate refresh and compression jobs. On an M4 Pro running AutoGluon with `best_quality` presets, 5-fold bagging, and 6 model types, every GB of RAM matters. Plain PostgreSQL has no background worker overhead beyond the core server.

### Apple Silicon friction is documented and real

TimescaleDB GitHub issue #2690 documents installation failures on Apple Silicon. While workarounds exist, they introduce fragility. Plain PostgreSQL via Homebrew is a first-class citizen on ARM64 macOS — zero friction.

### Continuous aggregates are nice but not load-bearing

The 1m -> 15m -> 1h -> 4h -> 1d aggregation pipeline is the strongest argument for TimescaleDB. But at ~700K source rows, a materialized view refresh takes seconds, not minutes. The incremental refresh advantage of continuous aggregates is meaningful at scale; here it saves negligible time.

Plain PostgreSQL approach for bar aggregation:

```sql
-- Materialized view for 15m bars from 1m
CREATE MATERIALIZED VIEW mes_15m_mv AS
SELECT
  date_trunc('hour', ts) +
    (EXTRACT(minute FROM ts)::int / 15) * interval '15 minutes' AS ts,
  (array_agg(open ORDER BY ts))[1] AS open,
  max(high) AS high,
  min(low) AS low,
  (array_agg(close ORDER BY ts DESC))[1] AS close,
  sum(volume) AS volume
FROM mes_1m
GROUP BY 1;

-- Refresh via pg_cron every 5 minutes
SELECT cron.schedule('refresh-15m', '*/5 * * * *',
  'REFRESH MATERIALIZED VIEW CONCURRENTLY mes_15m_mv');
```

This is simple, readable, and sufficient.

### AGENTS.md alignment

> "Prefer less complexity, fewer moving parts, and better naming."
> "Do not add any dependency, extension, or paid-plan assumption without an explicit reason."

TimescaleDB is an extension without a clear material advantage at this data scale. The simpler option wins.

---

## Verification Checklist

| Rule | Passes? | Note |
|------|---------|------|
| AGENTS.md: fewer moving parts | Yes | No extension, no background workers |
| AGENTS.md: no dependency without reason | Yes | TimescaleDB not justified at this scale |
| WARBIRD_CANONICAL.md: no new paid plans | Yes | Plain PG is free |
| Cost boundary | Yes | Zero additional cost |
| Naming rules | Yes | All `mes_` prefixed tables unchanged |
| Production boundary | Yes | Local DB is for training only; dashboard stays cloud Supabase |
| RAM constraint | Yes | Lower memory footprint than TimescaleDB |

---

## Implementation Implications

1. **Install:** `brew install postgresql@16` (or latest stable)
2. **Partitioning:** Monthly declarative partitions on `mes_1m` by `ts`
3. **Aggregation:** Materialized views for `mes_15m`, `mes_1h`, `mes_4h`, `mes_1d` with `REFRESH MATERIALIZED VIEW CONCURRENTLY`
4. **Scheduling:** `pg_cron` extension (lightweight, no TimescaleDB dependency) for periodic refresh
5. **Feature engineering:** PL/pgSQL functions for fib levels, pivot levels, swing detection, training features
6. **Indexes:** BRIN index on `ts` for time-range queries (optimal for append-only time-series)
7. **No compression needed:** ~700K rows x ~10 columns ≈ low single-digit GB. Not a storage concern.

---

## Sources

- [TimescaleDB vs PostgreSQL comparison (pgbench.com)](https://pgbench.com/comparisons/postgres-vs-timescaledb/)
- [TimescaleDB Apple Silicon issue #2690](https://github.com/timescale/timescaledb/issues/2690)
- [TimescaleDB Homebrew tap](https://github.com/timescale/homebrew-tap)
- [TimescaleDB continuous aggregates docs](https://www.tigerdata.com/docs/use-timescale/latest/continuous-aggregates/about-continuous-aggregates)
- [Best Database for Financial Data 2026 (Ispirer)](https://www.ispirer.com/blog/best-database-for-financial-data)
- [Managing Time-Series Data: TimescaleDB vs PostgreSQL (MadDevs)](https://maddevs.io/writeups/time-series-data-management-with-timescaledb/)
