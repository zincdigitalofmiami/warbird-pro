-- Migration 013: Google News RSS raw research intake
-- This stores raw article/card capture for later aggregation into news_signals.
-- It is intentionally normalized so one article can map to many tracked segments.

create table econ_news_rss_articles (
  id                bigint generated always as identity primary key,
  article_key       text        not null,
  provider          text        not null default 'google_news_rss',
  google_news_guid  text        not null,
  google_news_url   text        not null,
  publisher_name    text,
  publisher_url     text,
  publisher_domain  text,
  title             text        not null,
  summary           text,
  published_at      timestamptz not null,
  fetched_at        timestamptz not null default now(),
  created_at        timestamptz not null default now(),
  constraint econ_news_rss_articles_article_key_unique unique (article_key),
  constraint econ_news_rss_articles_guid_unique unique (google_news_guid)
);

create table econ_news_rss_article_segments (
  id                bigint generated always as identity primary key,
  article_id        bigint      not null references econ_news_rss_articles (id) on delete cascade,
  segment           text        not null,
  query_text        text        not null,
  matched_keywords  text[]      not null default '{}'::text[],
  fetched_at        timestamptz not null default now(),
  created_at        timestamptz not null default now(),
  constraint econ_news_rss_article_segments_article_segment_unique unique (article_id, segment)
);

create index idx_econ_news_rss_articles_published
  on econ_news_rss_articles (published_at desc);

create index idx_econ_news_rss_articles_publisher_domain
  on econ_news_rss_articles (publisher_domain, published_at desc);

create index idx_econ_news_rss_articles_provider
  on econ_news_rss_articles (provider, published_at desc);

create index idx_econ_news_rss_article_segments_segment
  on econ_news_rss_article_segments (segment, fetched_at desc);

create index idx_econ_news_rss_article_segments_article
  on econ_news_rss_article_segments (article_id);

alter table econ_news_rss_articles enable row level security;
create policy "Authenticated read econ_news_rss_articles"
  on econ_news_rss_articles for select to authenticated using (true);

alter table econ_news_rss_article_segments enable row level security;
create policy "Authenticated read econ_news_rss_article_segments"
  on econ_news_rss_article_segments for select to authenticated using (true);
