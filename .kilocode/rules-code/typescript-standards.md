# TypeScript Standards for Warbird-Pro

## Imports

- Use Supabase client from `lib/supabase/admin.ts` (service role) or `lib/supabase/client.ts` (anon).
- No Prisma imports. No Drizzle imports. No ORM.

## API Routes

- All cron routes: `export const maxDuration = 60`
- All cron routes must validate `CRON_SECRET` header.
- All cron routes must log to `job_log` table on success and failure.
- Use `series.update()` for live ticks, `setData()` only on initial load.

## Error Handling

- Log errors with enough context to debug (route name, input params, error message).
- Never swallow errors silently in cron routes.
- Return proper HTTP status codes (200 success, 401 unauthorized, 500 error).

## Naming Conventions

- Database columns: snake_case always.
- TypeScript variables: camelCase.
- API route files: kebab-case matching the URL path.
- Table prefixes: `mes_`, `cross_asset_`, `econ_`, `warbird_`, `ag_`
