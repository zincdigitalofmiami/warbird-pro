# Legacy Lineage Audit

**Date:** 2026-03-22
**Status:** Documented — No Action Required Yet

## Rabid Raccoon Lineage (Safe — Comments Only)

These files contain COMMENTS referencing Rabid Raccoon but have NO runtime imports or data dependencies:

| File | Line | Content | Risk |
|------|------|---------|------|
| `lib/setup-engine.ts` | 7 | "Ported from rabid-raccoon bhg-engine.ts" comment | None — comment only |
| `lib/fibonacci.ts` | 23 | "Matches rabid-raccoon.pine exactly" comment | None — comment only |
| `supabase/migrations/20260315000002_symbols.sql` | 2 | "60 symbols from rabid-raccoon snapshot" provenance comment | None — migration already applied |
| `supabase/seed.sql` | 2 | "60 real symbols from rabid-raccoon production DB" provenance comment | None — seed data |

## Duplicate Pipeline Paths (Deprecated)

| Legacy Path | Canonical Path | Status |
|-------------|---------------|--------|
| `scripts/build-dataset.py` | `scripts/ag/build-fib-dataset.py` (Phase 4) | Deprecated with hard exit |
| `scripts/train-warbird.py` | `scripts/ag/train-fib-model.py` (Phase 4) | Deprecated with hard exit |
| `scripts/predict-warbird.py` | `scripts/ag/` (Phase 4) | Deprecated with hard exit |

## scripts/warbird/* Status

These are the "current-ish" path from the prior architecture. They will be superseded by `scripts/ag/*` in Phase 4 but are NOT deprecated yet because they contain reference logic:

- `scripts/warbird/build-warbird-dataset.ts` — reference for dataset builder design
- `scripts/warbird/train-warbird.py` — reference for training config
- `scripts/warbird/predict-warbird.py` — reference for inference pattern
- `scripts/warbird/fib-engine.ts` — reference for fib calculation logic
- `scripts/warbird/trigger-15m.ts` — reference for 15m bar trigger logic
- `scripts/warbird/garch-engine.py` — reference for GARCH volatility model
- `scripts/warbird/conviction-matrix.ts` — reference for conviction scoring
- `scripts/warbird/daily-layer.ts` — reference for daily aggregation layer
- `scripts/warbird/structure-4h.ts` — reference for 4h structure detection

These stay as-is until Phase 4 builds their replacements.
