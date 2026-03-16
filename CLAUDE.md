Read and follow AGENTS.md at the repository root.

## Quick Reference

- **Plan:** `/Users/zincdigital/.claude/plans/gentle-giggling-mccarthy.md`
- **Live:** warbird-pro.vercel.app
- **Repo:** github.com/zincdigitalofmiami/warbird-pro
- **DB:** Supabase (check env vars, NOT Prisma)

## Current Status (2026-03-15)

**Phases 1-3 complete. Phase 4 partial. Phases 5-8 not started.**

### Done
- Auth flow (login, signup, forgot-password, protected routes)
- 9 SQL migrations applied, seed data loaded (60 symbols, 31 FRED series)
- MES 15m chart rendering with gap-free time mapping
- 10 fib levels (ZERO through TARGET 3), multi-period confluence scoring
- Fib lines: clean (no text labels, no axis labels), correct colors and widths
- Python sidecar streaming Databento Live -> mes_1m + mes_15m
- Vercel Cron catch-up every 5 min (gap recovery)
- 20 cron routes defined in vercel.json

### Next Up (in order)
1. Wire Supabase Realtime into LiveMesChart (replace polling with WebSocket push)
2. Sidecar reliability (process management, health check)
3. Phase 5: FRED + cross-asset + news data pipelines (15 cron routes)
4. Phase 6: Signal engine (detect-setups, measured-moves, score-trades)
5. Phase 7: Dashboard cards (MarketSummary, ActiveSetups, SessionStats)
6. Phase 8: ML model integration (deferred until training completes)

## Absolute Rules

1. NEVER mock data. Real or nothing.
2. NEVER query inactive Databento symbols.
3. NEVER use Prisma or any ORM.
4. `series.update()` for live ticks, `setData()` only on initial load.
5. `npm run build` must pass before every push.
6. One task at a time. Complete fully.
