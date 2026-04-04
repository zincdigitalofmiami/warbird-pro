# Local Warehouse Completion Execution Plan

Status: execution plan subordinate to the active architecture plan. This document does not replace `docs/plans/2026-03-20-ag-teaches-pine-architecture.md`.

## Summary

Complete the local Supabase warehouse in a fixed order:

1. freeze the clean baseline and reconcile local migration drift
2. split the overloaded economic taxonomy into semantically correct tables
3. fill the missing MES warehouse surfaces: `mes_1m` and `mes_4h`
4. export options only, keep intermarket and retained futures data intact
5. restore local writer/bootstrap capability
6. reactivate live pulls only in the final test checkpoint

The local warehouse remains research and training only. Cloud Supabase remains the production system of record. The external drive project is a data bucket only and must not be treated as application architecture, runtime wiring, or schema truth.

## Required Skills

- `warbird-phase-execution`
  - keeps work aligned to the single active architecture plan, the MES 15m contract, and the cloud/local boundary
- `supabase-ml-data-audit`
  - required for schema drift checks, extraction contract review, leakage prevention, integrity diagnostics, and reproducibility
- `quantitative-financial-analyst`
  - required for market-data naming, timeframe semantics, aggregation parity, and financial-series classification
- `fred-economic-data`
  - required to confirm official series naming, category meaning, and release frequency before any taxonomy move
- `build-web-apps:supabase-postgres-best-practices`
  - required for migration hygiene, FK/RLS/index correctness, and safe cutovers

## Precautions

- No dirty tree at any checkpoint boundary.
- Local and cloud must be audited and described separately.
- No DDL outside migration files.
- No external-drive runtime, docs, or wiring may be imported into this project.
- Intermarket stays in local and cloud. Do not prune retained futures or `cross_asset_*`.
- Options are the only removal/export path in scope.
- `MES.c.0` is the canonical MES source symbol for warehouse work.
- `mes_4h` remains derived from canonical `mes_1h`.
- Live pulls stay paused throughout execution and are only reactivated in the final testing checkpoint.

## Implementation Changes

### Checkpoint 0: Baseline Freeze And Drift Reconciliation

- Verify repo tree is clean before any warehouse mutation.
- Reconcile local migration ledger before adding new migrations.
  - local migration files currently run through `20260401000048`
  - local DB ledger must be brought into exact alignment first
- Snapshot before-state counts and date ranges for:
  - `mes_1m`, `mes_15m`, `mes_1h`, `mes_4h`, `mes_1d`
  - `cross_asset_1h`, `cross_asset_1d`, `cross_asset_15m`
  - `series_catalog`
  - `econ_commodities_1d`, `econ_vol_1d`, `econ_indexes_1d`
- Confirm options export artifacts exist and that `.OPT` rows are absent from active local symbol membership.

### Checkpoint 1: Taxonomy Split

- Replace ambiguous labels with financial-meaning labels.
- Rebuild `econ_category` from:
  - `rates`, `yields`, `fx`, `vol`, `inflation`, `labor`, `activity`, `money`, `commodities`, `indexes`
- To:
  - `rates`, `yields`, `fx`, `volatility`, `inflation`, `labor`, `activity`, `money`, `commodities`, `market_indexes`, `financial_conditions`, `credit`, `sentiment`, `uncertainty`, `recession`
- Create and wire new tables:
  - `econ_volatility_1d`
  - `econ_market_indexes_1d`
  - `econ_financial_conditions_1d`
  - `econ_credit_1d`
  - `econ_sentiment_1d`
  - `econ_uncertainty_1d`
  - `econ_recession_1d`
- Migrate row ownership:
  - `econ_vol_1d` -> `econ_volatility_1d`
  - `GVZCLS` from `econ_commodities_1d` -> `econ_volatility_1d`
  - `ANFCI`, `NFCI`, `STLFSI4` -> `econ_financial_conditions_1d`
  - `BAA10Y`, `BAMLC0A0CM`, `BAMLH0A0HYM2`, `BAMLHYH0A0HYM2EY` -> `econ_credit_1d`
  - `UMCSENT` -> `econ_sentiment_1d`
  - `USEPUINDXD`, `EMVMACROBUS` -> `econ_uncertainty_1d`
  - `SAHMCURRENT`, `RECPROUSM156N` -> `econ_recession_1d`
- Seed true market index series and backfill them:
  - `SP500`, `DJIA`, `NASDAQCOM`
- Correct metadata:
  - `FEDFUNDS.frequency` -> `monthly`
  - `EMVMACROBUS.frequency` -> `monthly`
- Update ingestion and scheduling surfaces to the new taxonomy names.
  - FRED category maps
  - FRED Edge Function validation
  - category-driven cron helper names and schedule entries
- Remove old live labels when cutover is complete:
  - `econ_vol_1d`
  - `econ_indexes_1d`
  - old enum labels `vol` and `indexes`

### Checkpoint 2: MES Warehouse Completion

- Canonical source is Databento historical data on `MES.c.0`.
- Do not use feature-enriched CSVs as the primary warehouse source.
- Patch the backfill path so all MES historical writes use the locked symbol contract.
- Fill in this order:
  1. refresh `mes_1h` and `mes_1d` through the latest closed bar
  2. backfill `mes_1m` from `2020-01-01T00:00:00Z`
  3. regenerate `mes_15m` from canonical `mes_1m`
  4. regenerate `mes_4h` from canonical `mes_1h`
- Preserve current 4-hour bar definition used by the repo codebase.
- Keep all writes idempotent by natural primary key `ts`.

### Checkpoint 3: Local Writer Bootstrap

- Verify local `cron.job` schedules and helper functions exist.
- Restore the missing local runtime prerequisites:
  - local edge function runtime
  - local vault secrets for edge base URL and cron secret
  - local invocation path for `run_mes_1m_pull`, `run_mes_hourly_pull`, `run_cross_asset_pull`, and FRED category pulls
- Smoke local writers manually after historical seeding.
- Confirm `job_log` starts recording real runs.

### Checkpoint 4: Final Testing And Live Pull Reactivation

- Reactivate dashboard/chart live pulls only after Checkpoints 0-3 pass.
- Validate live dashboard and chart paths against the repaired local warehouse.
- If reactivation testing fails, re-pause immediately and fix before advancing.
- Do not leave live pulls active unless final validation passes.

## Reviews

### Review 1: Schema Review

- Confirm migration ledger matches repo files before and after the taxonomy cutover.
- Confirm new tables have PKs, FK enforcement to `series_catalog`, indexes, and RLS.
- Confirm no live code path still references `econ_vol_1d`, `econ_indexes_1d`, `vol`, or `indexes`.

### Review 2: Financial Semantics Review

- Confirm each moved series matches official source semantics.
- Confirm market indexes only contain actual market index level series.
- Confirm volatility is not conflated with traded volume anywhere in table naming.

### Review 3: Data Contract Review

- Confirm intermarket tables remain intact.
- Confirm options stay exported and out of active local symbol membership.
- Confirm local and cloud differences are documented after every checkpoint.

### Review 4: Runtime Review

- Confirm local cron helpers can actually dispatch.
- Confirm `job_log` proves local runtime activity.
- Confirm live pulls remain paused until the final checkpoint.

## Test Plan

- Git/tree hygiene:
  - `git status --short` clean before and after every checkpoint
- Migration replay:
  - `supabase db reset`
  - local migration ledger equals repo file set
- App gates:
  - `npm run lint`
  - `npm run build`
- Taxonomy validation SQL:
  - no `series_catalog.category` values of `vol` or `indexes`
  - no rows left in dropped legacy econ tables
  - row counts preserved per moved series
  - `GVZCLS` only in `econ_volatility_1d`
  - `BAA10Y` only in `econ_credit_1d`
  - `ANFCI`, `NFCI`, `STLFSI4` only in `econ_financial_conditions_1d`
- MES integrity:
  - `mes_1m` non-zero with range starting at `2020-01-01`
  - `mes_4h` non-zero and derived parity against `mes_1h`
  - duplicate-key checks
  - OHLC consistency checks
- Bootstrap validation:
  - local cron helper invocations succeed
  - `job_log` records rows
  - post-seed runs advance data rather than staying idle
- Final live-pull test:
  - dashboard fetch path works
  - chart subscription path works
  - pause can be reasserted if testing fails

## Assumptions And Defaults

- The options export/removal is already complete and is not reopened.
- This document is an execution plan, not a replacement for the single active architecture plan.
- Intermarket stays in both local and cloud.
- The external drive remains data-only fallback and validation material.
- No compatibility alias layer is kept for old econ category names once the taxonomy cutover lands.
- Live pulls are reactivated only in the final testing checkpoint, never earlier.
