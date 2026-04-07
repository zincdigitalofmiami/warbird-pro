# Schema Migration Policy

**Status:** Active

## Purpose

Defines how local canonical and cloud runtime schema changes are proposed, versioned, and applied.

## Cloud Policy

- all cloud Supabase DDL must ship through versioned SQL migrations in `supabase/migrations/`
- no manual production DDL without a matching migration file and ledger reconciliation
- any cloud schema addition must first be approved in `docs/cloud_scope.md`

## Local Canonical Policy

- local PostgreSQL canonical DDL must be versioned in repo before it is applied
- local warehouse changes must preserve canonical lineage and auditability
- local training tables must not be introduced ad hoc from notebooks or one-off scripts without versioned DDL

## Promotion Policy

- contract change first
- migration second
- writer or reader implementation third
- publish and activation after verification

## Review Questions

Before any schema change lands, answer:

1. Is this object local canonical or cloud runtime subset?
2. Why does it exist?
3. Which contract field or plan phase requires it?
4. What reader or writer owns it?
5. What is the retirement path if it becomes obsolete?
