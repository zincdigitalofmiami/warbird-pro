-- Migration 041: Reconcile DDL drift from direct execute_sql operations (2026-03-31)
--
-- During the migration ledger reconciliation, these changes were applied to
-- production via MCP execute_sql without a migration file. This migration
-- captures them so local replay matches remote state.
--
-- 1. Enable RLS on 6 legacy backup tables created by migration 018
-- 2. Enable RLS on warbird_alert_events (pre-existing table missing RLS)
-- 3. Recreate all_news_articles view with security_invoker=true (was security_definer)
--
-- All statements are idempotent (IF NOT EXISTS / CREATE OR REPLACE).

-- ============================================================
-- 1. RLS on legacy backup tables (all empty, created by migration 018)
-- ============================================================

alter table if exists warbird_setup_events_legacy_20260326 enable row level security;
do $$ begin
  if not exists (select 1 from pg_policies where tablename = 'warbird_setup_events_legacy_20260326') then
    create policy "Authenticated read warbird_setup_events_legacy"
      on warbird_setup_events_legacy_20260326 for select to authenticated using (true);
  end if;
end $$;

alter table if exists warbird_setups_legacy_20260326 enable row level security;
do $$ begin
  if not exists (select 1 from pg_policies where tablename = 'warbird_setups_legacy_20260326') then
    create policy "Authenticated read warbird_setups_legacy"
      on warbird_setups_legacy_20260326 for select to authenticated using (true);
  end if;
end $$;

alter table if exists warbird_conviction_legacy_20260326 enable row level security;
do $$ begin
  if not exists (select 1 from pg_policies where tablename = 'warbird_conviction_legacy_20260326') then
    create policy "Authenticated read warbird_conviction_legacy"
      on warbird_conviction_legacy_20260326 for select to authenticated using (true);
  end if;
end $$;

alter table if exists warbird_risk_legacy_20260326 enable row level security;
do $$ begin
  if not exists (select 1 from pg_policies where tablename = 'warbird_risk_legacy_20260326') then
    create policy "Authenticated read warbird_risk_legacy"
      on warbird_risk_legacy_20260326 for select to authenticated using (true);
  end if;
end $$;

alter table if exists warbird_triggers_15m_legacy_20260326 enable row level security;
do $$ begin
  if not exists (select 1 from pg_policies where tablename = 'warbird_triggers_15m_legacy_20260326') then
    create policy "Authenticated read warbird_triggers_15m_legacy"
      on warbird_triggers_15m_legacy_20260326 for select to authenticated using (true);
  end if;
end $$;

alter table if exists warbird_forecasts_1h_legacy_20260326 enable row level security;
do $$ begin
  if not exists (select 1 from pg_policies where tablename = 'warbird_forecasts_1h_legacy_20260326') then
    create policy "Authenticated read warbird_forecasts_1h_legacy"
      on warbird_forecasts_1h_legacy_20260326 for select to authenticated using (true);
  end if;
end $$;

-- ============================================================
-- 2. RLS on warbird_alert_events (exists on production only, not in any migration)
-- ============================================================

do $$ begin
  if to_regclass('public.warbird_alert_events') is not null then
    execute 'alter table warbird_alert_events enable row level security';
    if not exists (select 1 from pg_policies where tablename = 'warbird_alert_events') then
      execute 'create policy "Authenticated read warbird_alert_events"
        on warbird_alert_events for select to authenticated using (true)';
    end if;
  end if;
end $$;

-- ============================================================
-- 3. Recreate all_news_articles view with security_invoker
-- ============================================================

create or replace view public.all_news_articles
  with (security_invoker = true)
as
select dedupe_key, provider, title, summary, article_body, body_word_count,
       extraction_status, published_at, published_minute, publisher_domain,
       url, canonical_url, related_symbols, created_at
from econ_news_finnhub_articles;

comment on view all_news_articles is
  'Unified read view for news articles (Finnhub only). security_invoker=true respects underlying RLS.';
