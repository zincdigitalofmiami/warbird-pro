---
name: pre-commit-verify
description: >
  Pre-commit verification checklist. Use before every git commit or push to ensure
  the build passes, no mock data exists, and all rules are followed. Invoke with
  /pre-commit-verify.
---

# Pre-Commit Verification

Run this checklist before every commit or push. ALL items must pass.

## Step 1: Build Check

Run `npm run build` and confirm zero errors. Do NOT proceed if the build fails.

## Step 2: Data Integrity Scan

- Grep for mock/fake/demo/placeholder/dummy data in changed files
- Grep for `bhg_`, `BHG`, `mkt_futures_` legacy naming in changed files
- Confirm no inactive Databento symbols are queried

## Step 3: Database Rules

- If SQL migrations were added: confirm they are in `supabase/migrations/`
- Confirm no Prisma/Drizzle imports were introduced
- Confirm table prefixes are correct (`mes_`, `cross_asset_`, `econ_`, `warbird_`)
- Confirm all columns use snake_case

## Step 4: Cron Route Rules

- If cron routes were added/modified:
  - `CRON_SECRET` validation present
  - `job_log` logging present
  - `export const maxDuration = 60` present
  - Schedule added to `vercel.json`

## Step 5: Deploy Safety

- Confirm NO `npx vercel --prod` commands
- Confirm NO `--no-verify` flags
- Confirm NO `/* */` block comments disabling code

## Step 6: Report

List all files being committed and summarize changes.
