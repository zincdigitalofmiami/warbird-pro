# Schema Migration Policy

**Status:** Active

## Purpose

Defines how cloud/runtime schema changes are proposed, versioned, and applied.
The active modeling plan does not require new training schema.

## Cloud Policy

- all cloud Supabase DDL must ship through versioned SQL migrations in `supabase/migrations/`
- no manual production DDL without a matching migration file and ledger reconciliation
- any cloud schema addition must first be approved in `docs/cloud_scope.md`

## Local Database Policy

- local database DDL must be versioned in repo before it is applied
- local tables used only for Optuna/tuning bookkeeping must not be described as
  canonical training truth
- local training tables for the retired warehouse AG plan must not be expanded
  unless that architecture is explicitly reopened

## Promotion Policy

- contract change first
- migration second
- writer or reader implementation third
- publish and activation after verification

## Review Questions

Before any schema change lands, answer:

1. Is this object runtime support, Optuna bookkeeping, or legacy/reference?
2. Why does it exist?
3. Which contract field or plan phase requires it?
4. What reader or writer owns it?
5. What is the retirement path if it becomes obsolete?
