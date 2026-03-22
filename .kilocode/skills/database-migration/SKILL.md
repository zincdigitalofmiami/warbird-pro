---
name: database-migration
description: >
  Workflow for creating Supabase database migrations in Warbird-Pro. Ensures proper
  naming, RLS policies, snake_case columns, and correct table prefixes. Invoke with
  /database-migration.
---

# Database Migration Workflow

Follow these steps when creating or modifying database tables.

## Step 1: Review Existing Schema

- Check `supabase/migrations/` for existing migrations
- Identify the next sequential migration number
- Confirm the table prefix is correct: `mes_`, `cross_asset_`, `econ_`, `warbird_`

## Step 2: Write the Migration

Location: `supabase/migrations/<NNN>_<description>.sql`

Rules:
- ALL columns must be snake_case
- Include `created_at timestamptz default now()` on all tables
- Include appropriate indexes for query patterns
- NO Prisma. NO Drizzle. Raw SQL only.

## Step 3: Add RLS Policy

Every table MUST have RLS enabled:
```sql
ALTER TABLE <table_name> ENABLE ROW LEVEL SECURITY;

-- At minimum, read access for authenticated users
CREATE POLICY "Allow read access"
  ON <table_name>
  FOR SELECT
  TO authenticated
  USING (true);
```

## Step 4: Verify

- Confirm migration file is in `supabase/migrations/`
- Confirm table prefix is correct
- Confirm all columns are snake_case
- Confirm RLS is enabled
- Run `npm run build` to catch any TypeScript references to the new table

## Step 5: Update Types

If the new table is referenced in TypeScript:
- Add types manually in the appropriate types file
- Do NOT rely on auto-generated types (type generation not set up yet)
