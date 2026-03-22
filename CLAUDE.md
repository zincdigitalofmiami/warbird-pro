Read and follow AGENTS.md at the repository root.

## Quick Reference

- **Active architecture plan:** `/Volumes/Satechi Hub/warbird-pro/docs/plans/2026-03-20-ag-teaches-pine-architecture.md`
- **Live:** warbird-pro.vercel.app
- **Repo:** github.com/zincdigitalofmiami/warbird-pro
- **DB:** Supabase cloud (check env vars, NOT Prisma)

## Current Status

### What Works
- MES chart pipeline end-to-end (Databento → cron → Supabase → Realtime → chart)
- 13 Vercel Cron routes (23 schedules) for MES, cross-asset, FRED, news, setups, scoring
- Warbird v1 8-table normalized schema (migration 010 + 011 + 012)
- Auth flow, API surface (/warbird/signal, /warbird/history, /live/mes15m, /pivots/mes)
- 12 SQL migrations applied, 60 symbols seeded

### What Doesn't Work Yet
- mes_1s ingestion (table exists, nothing writes to it)
- ML model training (scripts exist, no trained model)
- Local PostgreSQL training warehouse (decided in Checkpoint 1, not set up)
- DB-side aggregation (all TypeScript, zero Postgres functions)
- Type generation (manual types, no supabase gen types)

### Architecture Direction
Follow the active architecture plan only.

### Locked Rules
- 15m is the primary model/chart/setup timeframe.
- Local machines are for training/calculations/research only.
- Production ingestion, crons, and chart-serving must not depend on local machines.

## Pine Script Verification Pipeline

Before committing ANY change to `indicators/*.pine`, run ALL of these in order:

```bash
./scripts/guards/pine-lint.sh          # Static analysis (errors block commit)
./scripts/guards/check-contamination.sh # Cross-project leak detection
npm run build                           # TypeScript build gate
```

For major refactors, also run `trading-indicators:pine:validate` agent.

**Available MCP:** `pinescript-server` — Pine v6 reference (475 functions, 466 variables). Available after session restart.

## Absolute Rules

1. NEVER mock data. Real or nothing.
2. NEVER query inactive Databento symbols.
3. NEVER use Prisma or any ORM.
4. `series.update()` for live ticks, `setData()` only on initial load.
5. `npm run build` must pass before every push.
6. `pine-lint.sh` must pass (0 errors) before every Pine commit.
7. One task at a time. Complete fully.
