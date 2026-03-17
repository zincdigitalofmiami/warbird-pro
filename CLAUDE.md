Read and follow AGENTS.md at the repository root.

## Quick Reference

- **Plan:** `/Users/zincdigital/.claude/plans/gentle-giggling-mccarthy.md`
- **Canonical spec:** `/Volumes/Satechi Hub/warbird-pro/WARBIRD_CANONICAL.md`
- **Live:** warbird-pro.vercel.app
- **Repo:** github.com/zincdigitalofmiami/warbird-pro
- **DB:** Supabase (check env vars, NOT Prisma)

## Current Status (2026-03-16)

Canonical Warbird v1 cutover is the active architecture. Older phase-plan language is not authoritative where it conflicts.

### Locked Rules
- 1H is the only fib-anchor timeframe.
- MES authority map:
  - `mes_1m` direct from source
  - `mes_1h` direct from source
  - `mes_1d` direct from source for macro bias only
  - `mes_15m` derived from stored `mes_1m`
  - `mes_4h` derived from stored `mes_1h`
- Local machines are for training/calculations/research only.
- Production ingestion, crons, reconciliation, and chart-serving must not depend on local machines.

### Repo Reality
- Auth flow (login, signup, forgot-password, protected routes)
- 10 SQL migrations in repo, including the canonical Warbird v1 cutover
- MES 15m chart rendering with gap-free time mapping
- Canonical Warbird routes exist at `/api/warbird/signal` and `/api/warbird/history`
- Python sidecar and backfill writers exist, but production data continuity still needs verification
- `mes-catchup` is a reconciliation route, not a second primary writer

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
