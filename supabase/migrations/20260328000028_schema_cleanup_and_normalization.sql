-- Migration 028: Schema cleanup, normalization, and news_signals materialized view
-- Depends on: Phase 2 (dead code deleted), Phase 3 (new series in catalog)
--
-- Pre-apply safety checks (run these manually before applying):
--   1. Verify dead tables are empty or junk:
--      SELECT 'econ_news_1d', COUNT(*) FROM econ_news_1d UNION ALL
--      SELECT 'policy_news_1d', COUNT(*) FROM policy_news_1d UNION ALL
--      SELECT 'econ_news_newsfilter_articles', COUNT(*) FROM econ_news_newsfilter_articles UNION ALL
--      SELECT 'econ_news_newsfilter_article_segments', COUNT(*) FROM econ_news_newsfilter_article_segments UNION ALL
--      SELECT 'econ_news_rss_articles', COUNT(*) FROM econ_news_rss_articles UNION ALL
--      SELECT 'econ_news_rss_article_segments', COUNT(*) FROM econ_news_rss_article_segments;
--      Expected: econ_news_1d = 751 (junk headlines), all others = 0
--
--   2. Verify no duplicate rows block unique constraints:
--      SELECT ts, signal_type, COUNT(*) FROM news_signals GROUP BY ts, signal_type HAVING COUNT(*) > 1;
--      SELECT ts, event_name, COUNT(*) FROM econ_calendar GROUP BY ts, event_name HAVING COUNT(*) > 1;
--      SELECT ts, title, COUNT(*) FROM trump_effect_1d GROUP BY ts, title HAVING COUNT(*) > 1;
--
--   3. Verify no orphaned series_ids in econ tables:
--      (query in Task 6.3 of the plan)


-- ============================================================
-- Drop dead / orphaned tables
-- ============================================================

-- econ_news_1d: flat junk table, no dedupe, no topic linkage, freeform sentiment text.
-- 751 rows of Google News headlines with no body content. Replaced by structured
-- econ_news_finnhub_articles pipeline. No active writer.
drop table if exists econ_news_1d cascade;

-- policy_news_1d: zero rows, zero writers, never had a feed.
-- Policy/administration events are covered by trump_effect_1d (Federal Register API).
drop table if exists policy_news_1d cascade;

-- econ_news_newsfilter_articles + segments: dead provider, no free API tier exists.
-- Provider access was never obtained. Zero rows.
drop table if exists econ_news_newsfilter_article_segments cascade;
drop table if exists econ_news_newsfilter_articles cascade;

-- econ_news_rss_articles + segments: well-designed but never written to.
-- Google News route bypassed these entirely. Google News killed as modeling input
-- (headlines-only, no body extraction due to redirect URLs).
drop table if exists econ_news_rss_article_segments cascade;
drop table if exists econ_news_rss_articles cascade;


-- ============================================================
-- Add missing unique constraints (required for upsert deduplication)
-- ============================================================

-- econ_calendar: upsert target is (ts, event_name) but no constraint enforces it
do $$ begin
  if not exists (
    select 1 from pg_constraint where conname = 'econ_calendar_ts_event_name_key'
  ) then
    -- Deduplicate first if needed (keep highest id)
    delete from econ_calendar a
    using econ_calendar b
    where a.ts = b.ts
      and a.event_name = b.event_name
      and a.id < b.id;

    alter table econ_calendar add constraint econ_calendar_ts_event_name_key unique (ts, event_name);
  end if;
end $$;

-- trump_effect_1d: route upserts on (ts, title) — migration 016 added a unique index
-- but it may not be a proper constraint. Ensure constraint exists.
do $$ begin
  if not exists (
    select 1 from pg_constraint where conname = 'trump_effect_1d_ts_title_key'
  ) then
    -- Deduplicate first if needed (keep highest id)
    delete from trump_effect_1d a
    using trump_effect_1d b
    where a.ts = b.ts
      and a.title = b.title
      and a.id < b.id;

    alter table trump_effect_1d add constraint trump_effect_1d_ts_title_key unique (ts, title);
  end if;
end $$;


-- ============================================================
-- Normalize series_id: FK from econ_*_1d tables -> series_catalog
-- ============================================================
-- series_catalog.series_id already has a UNIQUE constraint (from migration 005).
-- These FKs enforce that no econ data row can reference a non-existent series.
-- If any orphaned series_id values exist, the FK will fail. The pre-apply safety
-- check above identifies them; add missing catalog entries before applying.

do $$ begin
  if not exists (select 1 from pg_constraint where conname = 'fk_rates_series') then
    alter table econ_rates_1d add constraint fk_rates_series foreign key (series_id) references series_catalog(series_id);
  end if;
end $$;

do $$ begin
  if not exists (select 1 from pg_constraint where conname = 'fk_yields_series') then
    alter table econ_yields_1d add constraint fk_yields_series foreign key (series_id) references series_catalog(series_id);
  end if;
end $$;

do $$ begin
  if not exists (select 1 from pg_constraint where conname = 'fk_inflation_series') then
    alter table econ_inflation_1d add constraint fk_inflation_series foreign key (series_id) references series_catalog(series_id);
  end if;
end $$;

do $$ begin
  if not exists (select 1 from pg_constraint where conname = 'fk_labor_series') then
    alter table econ_labor_1d add constraint fk_labor_series foreign key (series_id) references series_catalog(series_id);
  end if;
end $$;

do $$ begin
  if not exists (select 1 from pg_constraint where conname = 'fk_activity_series') then
    alter table econ_activity_1d add constraint fk_activity_series foreign key (series_id) references series_catalog(series_id);
  end if;
end $$;

do $$ begin
  if not exists (select 1 from pg_constraint where conname = 'fk_money_series') then
    alter table econ_money_1d add constraint fk_money_series foreign key (series_id) references series_catalog(series_id);
  end if;
end $$;

do $$ begin
  if not exists (select 1 from pg_constraint where conname = 'fk_commodities_series') then
    alter table econ_commodities_1d add constraint fk_commodities_series foreign key (series_id) references series_catalog(series_id);
  end if;
end $$;

do $$ begin
  if not exists (select 1 from pg_constraint where conname = 'fk_indexes_series') then
    alter table econ_indexes_1d add constraint fk_indexes_series foreign key (series_id) references series_catalog(series_id);
  end if;
end $$;

do $$ begin
  if not exists (select 1 from pg_constraint where conname = 'fk_fx_series') then
    alter table econ_fx_1d add constraint fk_fx_series foreign key (series_id) references series_catalog(series_id);
  end if;
end $$;

do $$ begin
  if not exists (select 1 from pg_constraint where conname = 'fk_vol_series') then
    alter table econ_vol_1d add constraint fk_vol_series foreign key (series_id) references series_catalog(series_id);
  end if;
end $$;


-- ============================================================
-- Convert news_signals from direct-write table to materialized view
-- ============================================================

-- Step 1: Drop the old table (49 rows of low-quality macro aggregations)
drop table if exists news_signals cascade;

-- Step 2: Create materialized view that aggregates ALL signal sources
create materialized view news_signals as

-- Source 1: Finnhub article assessments -> per-topic sentiment per 15m bucket
-- Uses benchmark_fit_score as confidence, topic_code as signal_type
select
  date_trunc('hour', a.scored_at) +
    (extract(minute from a.scored_at)::int / 15) * interval '15 min' as ts,
  a.topic_code as signal_type,
  'article_assessment' as source_table,
  a.provider as source_provider,
  a.dedupe_key as source_key,
  case
    when a.market_relevance_score > 0.6 then 'BULLISH'::market_impact_direction
    when a.market_relevance_score < 0.4 then 'BEARISH'::market_impact_direction
    else null
  end as direction,
  a.benchmark_fit_score as confidence,
  null::text as source_headline,
  a.scored_at as source_ts
from econ_news_article_assessments a

union all

-- Source 2: GPR daily index -> geopolitical regime signal
-- GPR > historical mean = BEARISH (elevated risk), below = BULLISH (calm)
select
  g.ts,
  'geopolitical_risk' as signal_type,
  'geopolitical_risk_1d' as source_table,
  'caldara_iacoviello' as source_provider,
  'gpr_' || g.ts::date as source_key,
  case
    when g.gpr_daily > 100 then 'BEARISH'::market_impact_direction
    when g.gpr_daily < 80 then 'BULLISH'::market_impact_direction
    else null
  end as direction,
  least(1.0, g.gpr_daily / 200.0) as confidence,
  null::text as source_headline,
  g.ts as source_ts
from geopolitical_risk_1d g

union all

-- Source 3: Trump Effect -> policy event presence signal
select
  t.ts,
  'policy_event' as signal_type,
  'trump_effect_1d' as source_table,
  'federal_register' as source_provider,
  'te_' || t.id as source_key,
  null::market_impact_direction as direction,
  0.5 as confidence,
  t.title as source_headline,
  t.ts as source_ts
from trump_effect_1d t

with no data;

-- Step 3: Create indexes on the materialized view
create index idx_news_signals_ts on news_signals (ts desc);
create index idx_news_signals_type_ts on news_signals (signal_type, ts desc);
create index idx_news_signals_source on news_signals (source_table, source_ts desc);

-- Step 4: Initial refresh
refresh materialized view news_signals;

-- Step 5: Add comment explaining the architecture
comment on materialized view news_signals is
  'Derived signal surface aggregating all news/event sources with full provenance. '
  'Refresh via: REFRESH MATERIALIZED VIEW news_signals; '
  'Sources: econ_news_article_assessments, geopolitical_risk_1d, trump_effect_1d. '
  'macro_reports_1d will be added when actual/forecast/surprise data is available. '
  'BULLISH/BEARISH thresholds are starter heuristics pending AG training refinement.';


-- ============================================================
-- Unified news article view (currently Finnhub only)
-- ============================================================

create or replace view all_news_articles as
select
  dedupe_key,
  provider,
  title,
  summary,
  article_body,
  body_word_count,
  extraction_status,
  published_at,
  published_minute,
  publisher_domain,
  url,
  canonical_url,
  related_symbols,
  created_at
from econ_news_finnhub_articles;

comment on view all_news_articles is
  'Unified read view across all news article providers. Currently Finnhub only. '
  'Deduplication across providers uses dedupe_key (md5 of normalized_title + domain + published_minute).';


-- ============================================================
-- Refresh cron for news_signals materialized view
-- ============================================================

create or replace function public.refresh_news_signals()
returns void
language plpgsql
security definer
set search_path = public
as $$
begin
  refresh materialized view news_signals;
end;
$$;

comment on function public.refresh_news_signals() is
  'Refreshes the news_signals materialized view. Called by pg_cron every 15 min during market hours.';

-- Remove stale version before scheduling
do $$
declare
  v_job_id bigint;
begin
  for v_job_id in
    select jobid from cron.job
    where jobname = 'warbird_refresh_news_signals'
  loop
    perform cron.unschedule(v_job_id);
  end loop;
exception
  when undefined_table then null;
end $$;

-- Refresh every 15 min during market hours, aligned with MES 15m bar close
select cron.schedule(
  'warbird_refresh_news_signals',
  '2,17,32,47 11-23 * * 1-5',
  $$select public.refresh_news_signals();$$
)
where not exists (
  select 1 from cron.job where jobname = 'warbird_refresh_news_signals'
);
