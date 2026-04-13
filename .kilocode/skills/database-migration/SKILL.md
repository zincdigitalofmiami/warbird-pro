---
name: database-migration
description: >
  Workflow for Warbird-Pro schema migrations across local canonical warehouse and
  cloud serving Supabase. Enforces local-vs-cloud routing, migration-ledger
  discipline, and naming contracts. Invoke with /database-migration.
---

# Database Migration Workflow

Use this workflow for every DDL change.

## Step 1: Classify the target surface first

- Decide whether the change belongs to:
  - local canonical warehouse (`warbird` on PG17 `127.0.0.1:5432`)
  - cloud serving subset (Supabase `qhwgrzqjcdtdqppvhhme`)
- Do not proceed until the target surface is explicit.
- Verify authority before writing SQL:
  - `AGENTS.md`
  - `docs/contracts/schema_migration_policy.md`
  - `docs/contracts/ag_local_training_schema.md` for AG table/view contract

## Workflow A: Local warehouse DDL

Location: `local_warehouse/migrations/<NNN>_<description>.sql`

Rules:
- Apply local canonical DDL only through `local_warehouse/migrations/`.
- Track applies in the local `local_schema_migrations` ledger.
- Target database is local `warbird` on PG17 (`127.0.0.1:5432`).
- Use contract naming prefixes: `mes_`, `cross_asset_`, `econ_`, `warbird_`, `ag_`.
- AG canonical objects must use `ag_` names exactly as defined in `docs/contracts/ag_local_training_schema.md`.
- Keep columns snake_case.
- Do not add uncontracted columns (for example `created_at`) unless the governing contract explicitly requires them.
- Do not apply blanket cloud RLS requirements to local warehouse tables.
- NO Prisma. NO Drizzle. Raw SQL only.

## Workflow B: Cloud serving DDL

Location: `supabase/migrations/<timestamp>_<description>.sql`

Rules:
- Apply cloud DDL only through versioned files in `supabase/migrations/`.
- Never run manual production cloud DDL without matching migration file and ledger reconciliation.
- Confirm object approval in `docs/cloud_scope.md` before adding it.
- Use contract naming prefixes and snake_case columns.
- Add RLS/policies according to the active cloud contract requirements for the surface (current authority requires RLS on cloud tables).
- NO Prisma. NO Drizzle. Raw SQL only.

## Step 2: Verify

- Confirm migration file path matches the target surface:
  - local canonical -> `local_warehouse/migrations/`
  - cloud serving -> `supabase/migrations/`
- Confirm naming prefixes and contract names are correct.
- Confirm local/cloud migration ledgers are consistent with files.
- Run `npm run build` when TypeScript surfaces depend on the schema change.

## Step 3: Report

- State whether the migration is local canonical or cloud serving.
- List migration files changed.
- List authority docs and contracts used for validation.
