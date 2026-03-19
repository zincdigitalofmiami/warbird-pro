Read and follow AGENTS.md at the repository root.

## Quick Reference

- **Plan:** `/Volumes/Satechi Hub/warbird-pro/docs/plans/2026-03-17-warbird-simplification-handoff.md`
- **Canonical spec:** `/Volumes/Satechi Hub/warbird-pro/WARBIRD_CANONICAL.md`
- **Live:** warbird-pro.vercel.app
- **Repo:** github.com/zincdigitalofmiami/warbird-pro
- **DB:** Supabase (check env vars, NOT Prisma)

## Current Status (2026-03-18)

Canonical Warbird v1 cutover is the active architecture. Older phase-plan language is not authoritative where it conflicts.

### Locked Rules
- 15m is the primary model/chart/setup timeframe.
- MES authority map:
  - `mes_1s` is the canonical continuity ingestion layer
  - `mes_1m` is trigger-resolution data (derived from `mes_1s` when available)
  - `mes_15m` is the primary setup/model/chart layer (derived from `mes_1m`)
  - `mes_1h` and `mes_4h` are context layers only (not primary decision authority)
  - `mes_1d` is optional macro context
- Local machines are for training/calculations/research only.
- Production ingestion, crons, reconciliation, and chart-serving must not depend on local machines.

### Repo Reality
- Auth flow (login, signup, forgot-password, protected routes)
- 10 SQL migrations in repo, including the canonical Warbird v1 cutover
- MES 15m chart rendering with gap-free time mapping
- Canonical Warbird routes exist at `/api/warbird/signal` and `/api/warbird/history`
- `mes-catchup` Vercel Cron (every 5 min) is the production MES feed path — no sidecar dependency
- `mes_1s` + `1s -> 1m -> 15m` continuity is canonical direction
- Python backfill scripts exist for historical data research

### Next Up (in order)
1. Keep docs aligned to canonical Warbird v1 and the current MES authority map
2. Restore and verify hosted MES continuity for direct-source and derived bars
3. Fill missing support data needed for trigger/model validation
4. Dry-test deterministic engine logic
5. Train only after data continuity is proven

## Absolute Rules

1. NEVER mock data. Real or nothing.
2. NEVER query inactive Databento symbols.
3. NEVER use Prisma or any ORM.
4. `series.update()` for live ticks, `setData()` only on initial load.
5. `npm run build` must pass before every push.
6. One task at a time. Complete fully.
