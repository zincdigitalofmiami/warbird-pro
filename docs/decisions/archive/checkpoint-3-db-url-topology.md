# Checkpoint 3: DB URL and Credential Topology

**Date:** 2026-03-19
**Status:** Decision Made
**Checkpoint:** Supabase Architecture Rethink — Checkpoint 3
**Depends on:** Checkpoint 1 (Plain local PostgreSQL), Checkpoint 2 (mes_1s ephemeral cloud)

---

## Decision

**Explicit env var separation by runtime.** Each runtime has one obvious primary database target. Local PG uses `LOCAL_DATABASE_URL`. Cloud Supabase uses existing `NEXT_PUBLIC_SUPABASE_URL` + `SUPABASE_SERVICE_ROLE_KEY`. Only the publish/sync job touches both. Dead `POSTGRES_*` vars are removed.

---

## Current State (Audit)

### Env vars actually used by code

| Var | Used by | Purpose |
|-----|---------|---------|
| `NEXT_PUBLIC_SUPABASE_URL` | lib/supabase/*.ts, all cron routes, TS scripts | Cloud Supabase URL |
| `NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY` | lib/supabase/client.ts, server.ts, proxy.ts | Anon key (frontend reads) |
| `SUPABASE_SERVICE_ROLE_KEY` | lib/supabase/admin.ts, Python scripts | Admin writes (backend) |
| `CRON_SECRET` | All 13 cron routes | Vercel Cron auth header |
| `DATABENTO_API_KEY` | lib/ingestion/databento.ts | Market data API |
| `FRED_API_KEY` | lib/ingestion/fred.ts, econ-calendar route | Economic data API |
| `TRADINGECONOMICS_API_KEY` | cron/econ-calendar route | Calendar data API |
| `WARBIRD_FORECAST_WRITER_URL` | cron/forecast route | External writer invocation |
| `WARBIRD_FORECAST_WRITER_TOKEN` | cron/forecast route | Writer auth |
| `CROSS_ASSET_SHARD_COUNT` | cron/cross-asset route | Shard config |
| `SUPABASE_URL` | Python scripts (fallback) | Alias for cloud URL |

### Dead vars in .env.local (not used by any code)

| Var | Origin | Status |
|-----|--------|--------|
| `POSTGRES_DATABASE` | Supabase Vercel integration | **Dead** — nothing reads it |
| `POSTGRES_HOST` | Supabase Vercel integration | **Dead** |
| `POSTGRES_PASSWORD` | Supabase Vercel integration | **Dead** |
| `POSTGRES_PRISMA_URL` | Supabase Vercel integration | **Dead** — no Prisma in project |
| `POSTGRES_URL` | Supabase Vercel integration | **Dead** |
| `POSTGRES_URL_NON_POOLING` | Supabase Vercel integration | **Dead** |
| `POSTGRES_USER` | Supabase Vercel integration | **Dead** |

### Missing env vars

| Var | Needed for |
|-----|-----------|
| `LOCAL_DATABASE_URL` | Local PG training warehouse (Checkpoint 1) |

### .env.example

Only documents 2 of 11+ actual vars. Wildly incomplete.

---

## Options Evaluated

### Option A: Separate env files per runtime context (chosen)

- `.env.local` — Next.js local dev (cloud Supabase + API keys). Loaded by Next.js automatically.
- `.env.training` — Local scripts (local PG + optional cloud read for migration). Loaded explicitly by scripts via `dotenv` or shell `source`.
- Vercel env vars — Production (set in Vercel dashboard, not in files).

**Strengths:**
- Each file has one obvious purpose. No mixed-use.
- `.env.local` stays in Next.js convention (auto-loaded).
- Training scripts can't accidentally write to cloud if they only source `.env.training`.
- Clear which file to edit for which context.

**Weaknesses:**
- Two env files to maintain locally.
- Publish job needs vars from both contexts (solvable: `.env.training` includes the cloud vars it needs).

### Option B: Single .env.local with comment sections

All vars in one file with `# === Cloud ===` and `# === Local ===` section markers.

**Strengths:**
- One file to maintain.
- Simpler for solo developer.

**Weaknesses:**
- Every runtime sees every var. A bug in a training script could accidentally connect to cloud and write.
- Comment-based separation is advisory, not enforced.
- Violates the plan's "no ambiguous mixed-use URL setup" rule.

---

## Reasoning

### One runtime = one primary database

The plan is explicit: "any runtime should have one obvious primary database target." Separate env files enforce this structurally. A training script sourcing `.env.training` cannot accidentally use `NEXT_PUBLIC_SUPABASE_URL` unless `.env.training` explicitly includes it (which it would only for the publish job).

### Dead vars must go

The `POSTGRES_*` vars are artifacts of the Supabase Vercel integration wizard. No code reads them. They contain cloud credentials in raw connection string format — a liability with no value. Remove them.

### .env.example must be complete

The current .env.example documents 2 of 11+ vars. Anyone cloning this repo would be lost. It should document every var with grouping and placeholder values.

---

## Runtime-to-Database Matrix

| Runtime | Primary DB | Env source | Vars needed |
|---------|-----------|------------|-------------|
| **Vercel Cron routes** | Cloud Supabase | Vercel dashboard | `NEXT_PUBLIC_SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `CRON_SECRET`, API keys |
| **Next.js local dev** | Cloud Supabase | `.env.local` | Same as Vercel |
| **Browser (frontend)** | Cloud Supabase | `NEXT_PUBLIC_*` only | `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY` |
| **Python training** | Local PG | `.env.training` | `LOCAL_DATABASE_URL` |
| **Python inference** | Local PG | `.env.training` | `LOCAL_DATABASE_URL` |
| **TS dataset builder** | Local PG (target) | `.env.training` | `LOCAL_DATABASE_URL` (currently reads cloud — migration later) |
| **Python publish/sync** | Both | `.env.training` | `LOCAL_DATABASE_URL` + `SUPABASE_URL` + `SUPABASE_SERVICE_ROLE_KEY` |

### URL format

| Var | Format | Example |
|-----|--------|---------|
| `NEXT_PUBLIC_SUPABASE_URL` | Supabase project URL | `https://xxxxx.supabase.co` |
| `SUPABASE_URL` | Same (alias for scripts) | `https://xxxxx.supabase.co` |
| `LOCAL_DATABASE_URL` | PostgreSQL connection string | `postgresql://zincdigital@localhost:5432/warbird_training` |

---

## Target .env.example

```bash
# ═══════════════════════════════════════════════════════════
# Warbird Pro — Environment Variables
# ═══════════════════════════════════════════════════════════

# ── Cloud Supabase (Next.js app + Vercel Cron) ───────────
NEXT_PUBLIC_SUPABASE_URL=https://your-project.supabase.co
NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY=your-anon-key
SUPABASE_SERVICE_ROLE_KEY=your-service-role-key

# ── Vercel Cron ───────────────────────────────────────────
CRON_SECRET=your-cron-secret

# ── Market Data ───────────────────────────────────────────
DATABENTO_API_KEY=your-databento-key

# ── Economic Data ─────────────────────────────────────────
FRED_API_KEY=your-fred-key
TRADINGECONOMICS_API_KEY=your-te-key

# ── Warbird Forecast ──────────────────────────────────────
WARBIRD_FORECAST_WRITER_URL=https://your-writer-url
WARBIRD_FORECAST_WRITER_TOKEN=your-writer-token

# ── Cross-Asset Config ────────────────────────────────────
CROSS_ASSET_SHARD_COUNT=3
```

### Target .env.training

```bash
# ═══════════════════════════════════════════════════════════
# Warbird Pro — Local Training Environment
# ═══════════════════════════════════════════════════════════

# ── Local PostgreSQL (training warehouse) ─────────────────
LOCAL_DATABASE_URL=postgresql://zincdigital@localhost:5432/warbird_training

# ── Cloud Supabase (for publish/sync job ONLY) ────────────
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_SERVICE_ROLE_KEY=your-service-role-key
```

---

## Verification Checklist

| Rule | Passes? | Note |
|------|---------|------|
| Plan: one obvious primary DB per runtime | Yes | Matrix shows one primary per row |
| Plan: dual-target only in explicit publish/migration | Yes | Only publish job has both |
| Plan: no ambiguous mixed-use URL setup | Yes | Different var names, different files |
| AGENTS.md: no dependency without reason | Yes | No new dependencies |
| Cost boundary | Yes | Zero cost impact |
| Production boundary | Yes | Dashboard stays cloud-only |
| AGENTS.md: naming rules | Yes | `LOCAL_DATABASE_URL` is descriptive |

---

## Implementation Implications

1. **Remove dead `POSTGRES_*` vars** from `.env.local`.
2. **Rewrite `.env.example`** with all 11+ vars, grouped by context.
3. **Create `.env.training.example`** template for local training env.
4. **Add `.env.training` to `.gitignore`** (contains credentials).
5. **Update Python scripts** to read `LOCAL_DATABASE_URL` instead of `SUPABASE_URL` when targeting local PG (implementation phase, after local PG is set up).
6. **Update `build-warbird-dataset.ts`** to optionally read from local PG via `LOCAL_DATABASE_URL`.
7. **No changes to Vercel env vars or Next.js app code** — cloud path is unchanged.
