# Supabase Audit Reference Guide

Use this reference to keep Supabase audit work tied to official platform guidance instead of repo folklore.

## Official Sources

- RLS: https://supabase.com/docs/guides/database/postgres/row-level-security
- Scheduled Edge Functions: https://supabase.com/docs/guides/functions/schedule-functions
- Database migrations: https://supabase.com/docs/guides/deployment/database-migrations

## RLS Audit Rules From Supabase Docs

- Tables in exposed schemas should have RLS enabled. Tables created outside the dashboard may need explicit `alter table ... enable row level security`.
- Policies are effectively implicit `WHERE` clauses. Presence of a policy is not enough; role scope and predicates matter.
- `auth.uid()` returns `null` when unauthenticated. Policies that rely on it should usually make the null case explicit.
- UPDATE behavior depends on both `using` and `with check`, and UPDATE operations also need a compatible SELECT policy.
- Views can bypass RLS by default. On Postgres 15+, `security_invoker = true` is the documented way to make views obey underlying-table RLS for `anon` and `authenticated` callers.
- Service keys bypass RLS and must never be treated as browser-safe.

## RLS Performance And Safety Guidance

- Index columns referenced by policies.
- Prefer wrapping stable helper calls like `auth.uid()` in `select` when used inside policies.
- Prefer `to authenticated` or explicit role scoping so policies do not run unnecessarily for `anon` callers.
- Security-definer functions can help, but they should not live in exposed schemas.

## Scheduled Function Guidance

- Official Supabase scheduling uses `pg_cron` plus `pg_net` to invoke Edge Functions.
- Secrets such as project URL or auth tokens should live in Supabase Vault, not hard-coded SQL or client code.
- The documented pattern is a `cron.schedule(...)` wrapper around `net.http_post(...)` targeting `/functions/v1/<name>`.
- In audits, treat cron ownership, Vault secrets, function deployment, and direct invocation proof as separate evidence layers.

## Migration Discipline Guidance

- The official flow assumes schema changes are captured in migration files, tested locally, and then pushed after the project is linked.
- `supabase db diff` and `supabase db reset` are part of the recommended workflow for generating and testing migrations.
- `supabase db push` is safe only when the repo migration history is trustworthy relative to the remote database.
- If the repo already knows live drift exists, drift reconciliation is required before treating `db push` as a safe next step.

## Warbird Audit Implications

- A green build is not proof that Edge Functions deploy or that pg_cron owns recurring jobs.
- A table can be structurally correct and still be operationally dead because the writer, schedule, or secret path is missing.
- An RLS audit must include tables, views, grants, bypass paths, and the client type using them.
