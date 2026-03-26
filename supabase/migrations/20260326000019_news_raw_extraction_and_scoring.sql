-- Raw news contract expansion:
-- 1. canonical topic catalog with family tags
-- 2. full article extraction fields on raw article tables
-- 3. Finnhub and Newsfilter raw article capture
-- 4. research-only article assessment/scoring surface

create type news_topic_family as enum (
  'market_structure',
  'macro_policy',
  'macro_prices',
  'rates_credit',
  'macro_growth',
  'geopolitics',
  'corporate_leadership'
);

create type news_extraction_status as enum (
  'FULL',
  'PARTIAL',
  'FAILED'
);

create table econ_news_topics (
  topic_code      text primary key,
  topic_label     text              not null,
  topic_family    news_topic_family not null,
  econ_category   econ_category,
  topic_tags      text[]            not null default '{}'::text[],
  description     text,
  is_active       boolean           not null default true,
  created_at      timestamptz       not null default now()
);

insert into econ_news_topics (topic_code, topic_label, topic_family, econ_category, topic_tags, description)
values
  ('sp500_market', 'S&P 500 market context', 'market_structure', 'indexes', '{sp500,market,equities,wall_street}', 'Broad U.S. equity market context around the S&P 500 and index futures.'),
  ('sp500_fed_policy', 'S&P 500 Fed policy', 'macro_policy', 'rates', '{sp500,fed,rates,policy}', 'Federal Reserve, FOMC, and rate-policy coverage with direct index context.'),
  ('sp500_inflation', 'S&P 500 inflation', 'macro_prices', 'inflation', '{sp500,inflation,cpi,pce,ppi}', 'Inflation, CPI, PCE, and price-level news with direct index context.'),
  ('sp500_yields_rates', 'S&P 500 yields and rates', 'rates_credit', 'yields', '{sp500,yields,treasury,rates,sofr}', 'Treasury yield, breakeven, and rates-state coverage with direct index context.'),
  ('sp500_labor_growth', 'S&P 500 labor and growth', 'macro_growth', 'labor', '{sp500,labor,growth,claims,gdp}', 'Jobs, claims, unemployment, GDP, and activity coverage with direct index context.'),
  ('sp500_geopolitics', 'S&P 500 geopolitics', 'geopolitics', null, '{sp500,geopolitics,war,sanctions,tariffs}', 'Geopolitical, war, sanctions, and trade-escalation coverage with direct index context.'),
  ('sp500_energy_inflation', 'S&P 500 energy and inflation', 'macro_prices', 'commodities', '{sp500,energy,oil,wti,inflation}', 'Oil, gasoline, OPEC, and energy-price shocks with direct index context.'),
  ('sp500_volatility', 'S&P 500 volatility', 'market_structure', 'vol', '{sp500,volatility,vix,selloff,risk_off}', 'Volatility, correction, selloff, and risk-off coverage with direct index context.'),
  ('sp500_earnings_megacap', 'S&P 500 earnings and megacap', 'corporate_leadership', 'indexes', '{sp500,earnings,megacap,nvidia,apple,microsoft}', 'Megacap earnings and leadership-narrative coverage with direct index context.'),
  ('sp500_policy', 'S&P 500 policy', 'macro_policy', null, '{sp500,policy,white_house,congress,treasury}', 'White House, Congress, Treasury, and executive-policy coverage with direct index context.'),
  ('sp500_credit_liquidity', 'S&P 500 credit and liquidity', 'rates_credit', 'indexes', '{sp500,credit,liquidity,high_yield,bank_stress}', 'Credit spreads, liquidity, and stress-state coverage with direct index context.')
on conflict (topic_code) do update
set
  topic_label = excluded.topic_label,
  topic_family = excluded.topic_family,
  econ_category = excluded.econ_category,
  topic_tags = excluded.topic_tags,
  description = excluded.description,
  is_active = true;

alter table econ_news_rss_articles
  add column if not exists canonical_url text,
  add column if not exists image_url text,
  add column if not exists article_excerpt text,
  add column if not exists article_body text,
  add column if not exists body_word_count integer not null default 0,
  add column if not exists extraction_status news_extraction_status not null default 'FAILED',
  add column if not exists extraction_method text,
  add column if not exists extracted_at timestamptz,
  add column if not exists normalized_title text,
  add column if not exists published_minute timestamptz,
  add column if not exists dedupe_key text,
  add column if not exists provider_metadata jsonb not null default '{}'::jsonb;

update econ_news_rss_articles
set
  normalized_title = coalesce(
    normalized_title,
    lower(trim(regexp_replace(regexp_replace(title, '[^[:alnum:][:space:]]+', ' ', 'g'), '\s+', ' ', 'g')))
  ),
  published_minute = coalesce(published_minute, date_trunc('minute', published_at)),
  dedupe_key = coalesce(
    dedupe_key,
    md5(
      concat_ws(
        '|',
        lower(trim(regexp_replace(regexp_replace(title, '[^[:alnum:][:space:]]+', ' ', 'g'), '\s+', ' ', 'g'))),
        coalesce(publisher_domain, ''),
        to_char(date_trunc('minute', published_at) at time zone 'UTC', 'YYYY-MM-DD HH24:MI')
      )
    )
  ),
  extraction_status = case
    when coalesce(body_word_count, 0) >= 120 then 'FULL'::news_extraction_status
    when coalesce(body_word_count, 0) > 0 then 'PARTIAL'::news_extraction_status
    else 'FAILED'::news_extraction_status
  end,
  provider_metadata = coalesce(provider_metadata, '{}'::jsonb);

alter table econ_news_rss_articles
  alter column normalized_title set not null,
  alter column published_minute set not null,
  alter column dedupe_key set not null;

create unique index if not exists uq_econ_news_rss_articles_dedupe_key
  on econ_news_rss_articles (dedupe_key);

alter table econ_news_rss_article_segments
  add column if not exists matched_symbols text[] not null default '{}'::text[];

alter table econ_news_rss_article_segments
  drop constraint if exists econ_news_rss_article_segments_topic_fk;

alter table econ_news_rss_article_segments
  add constraint econ_news_rss_article_segments_topic_fk
  foreign key (segment) references econ_news_topics (topic_code);

create table econ_news_finnhub_articles (
  id                bigint generated always as identity primary key,
  article_key       text                   not null,
  provider          text                   not null default 'finnhub',
  finnhub_id        bigint                 not null,
  source_category   text,
  url               text                   not null,
  canonical_url     text,
  publisher_name    text                   not null,
  publisher_domain  text,
  title             text                   not null,
  summary           text,
  article_excerpt   text,
  article_body      text,
  body_word_count   integer                not null default 0,
  image_url         text,
  related_symbols   text[]                 not null default '{}'::text[],
  published_at      timestamptz            not null,
  published_minute  timestamptz            not null,
  normalized_title  text                   not null,
  dedupe_key        text                   not null,
  extraction_status news_extraction_status not null default 'FAILED',
  extraction_method text,
  provider_metadata jsonb                  not null default '{}'::jsonb,
  fetched_at        timestamptz            not null default now(),
  extracted_at      timestamptz,
  created_at        timestamptz            not null default now(),
  constraint econ_news_finnhub_articles_article_key_unique unique (article_key),
  constraint econ_news_finnhub_articles_finnhub_id_unique unique (finnhub_id),
  constraint econ_news_finnhub_articles_dedupe_key_unique unique (dedupe_key)
);

create table econ_news_finnhub_article_segments (
  id                bigint generated always as identity primary key,
  article_id        bigint      not null references econ_news_finnhub_articles (id) on delete cascade,
  segment           text        not null references econ_news_topics (topic_code),
  query_text        text        not null,
  matched_keywords  text[]      not null default '{}'::text[],
  matched_symbols   text[]      not null default '{}'::text[],
  fetched_at        timestamptz not null default now(),
  created_at        timestamptz not null default now(),
  constraint econ_news_finnhub_article_segments_article_segment_unique unique (article_id, segment)
);

create index idx_econ_news_finnhub_articles_published
  on econ_news_finnhub_articles (published_at desc);

create index idx_econ_news_finnhub_articles_publisher_domain
  on econ_news_finnhub_articles (publisher_domain, published_at desc);

create index idx_econ_news_finnhub_articles_category
  on econ_news_finnhub_articles (source_category, published_at desc);

create index idx_econ_news_finnhub_article_segments_segment
  on econ_news_finnhub_article_segments (segment, fetched_at desc);

create table econ_news_newsfilter_articles (
  id                bigint generated always as identity primary key,
  article_key       text                   not null,
  provider          text                   not null default 'newsfilter',
  newsfilter_id     text                   not null,
  source_id         text                   not null,
  source_name       text                   not null,
  url               text                   not null,
  canonical_url     text,
  publisher_domain  text,
  title             text                   not null,
  summary           text,
  article_excerpt   text,
  article_body      text,
  body_word_count   integer                not null default 0,
  image_url         text,
  related_symbols   text[]                 not null default '{}'::text[],
  published_at      timestamptz            not null,
  published_minute  timestamptz            not null,
  normalized_title  text                   not null,
  dedupe_key        text                   not null,
  extraction_status news_extraction_status not null default 'FAILED',
  extraction_method text,
  provider_metadata jsonb                  not null default '{}'::jsonb,
  fetched_at        timestamptz            not null default now(),
  extracted_at      timestamptz,
  created_at        timestamptz            not null default now(),
  constraint econ_news_newsfilter_articles_article_key_unique unique (article_key),
  constraint econ_news_newsfilter_articles_newsfilter_id_unique unique (newsfilter_id),
  constraint econ_news_newsfilter_articles_dedupe_key_unique unique (dedupe_key)
);

create table econ_news_newsfilter_article_segments (
  id                bigint generated always as identity primary key,
  article_id        bigint      not null references econ_news_newsfilter_articles (id) on delete cascade,
  segment           text        not null references econ_news_topics (topic_code),
  query_text        text        not null,
  matched_keywords  text[]      not null default '{}'::text[],
  matched_symbols   text[]      not null default '{}'::text[],
  fetched_at        timestamptz not null default now(),
  created_at        timestamptz not null default now(),
  constraint econ_news_newsfilter_article_segments_article_segment_unique unique (article_id, segment)
);

create index idx_econ_news_newsfilter_articles_published
  on econ_news_newsfilter_articles (published_at desc);

create index idx_econ_news_newsfilter_articles_source_id
  on econ_news_newsfilter_articles (source_id, published_at desc);

create index idx_econ_news_newsfilter_articles_publisher_domain
  on econ_news_newsfilter_articles (publisher_domain, published_at desc);

create index idx_econ_news_newsfilter_article_segments_segment
  on econ_news_newsfilter_article_segments (segment, fetched_at desc);

create table econ_news_article_assessments (
  id                           bigint generated always as identity primary key,
  provider                     text        not null,
  dedupe_key                   text        not null,
  article_key                  text        not null,
  topic_code                   text        not null references econ_news_topics (topic_code),
  identified_symbols           text[]      not null default '{}'::text[],
  reason_flags                 text[]      not null default '{}'::text[],
  source_quality_score         numeric     not null,
  market_relevance_score       numeric     not null,
  macro_specificity_score      numeric     not null,
  technical_specificity_score  numeric     not null,
  cross_asset_context_score    numeric     not null,
  image_presence_score         numeric     not null,
  watchlist_relevance_score    numeric     not null,
  reasoning_confidence         numeric     not null,
  benchmark_fit_score          numeric     not null,
  evidence                     jsonb       not null default '{}'::jsonb,
  scoring_version              text        not null default 'reuters_benchmark_v1',
  scored_at                    timestamptz not null default now(),
  created_at                   timestamptz not null default now(),
  constraint econ_news_article_assessments_unique
    unique (provider, dedupe_key, topic_code, scoring_version),
  constraint econ_news_article_assessments_score_bounds check (
    source_quality_score between 0 and 1
    and market_relevance_score between 0 and 1
    and macro_specificity_score between 0 and 1
    and technical_specificity_score between 0 and 1
    and cross_asset_context_score between 0 and 1
    and image_presence_score between 0 and 1
    and watchlist_relevance_score between 0 and 1
    and reasoning_confidence between 0 and 1
    and benchmark_fit_score between 0 and 1
  )
);

create index idx_econ_news_article_assessments_topic_score
  on econ_news_article_assessments (topic_code, benchmark_fit_score desc, scored_at desc);

create index idx_econ_news_article_assessments_provider
  on econ_news_article_assessments (provider, scored_at desc);

alter table econ_news_topics enable row level security;
create policy "Authenticated read econ_news_topics"
  on econ_news_topics for select to authenticated using (true);

alter table econ_news_finnhub_articles enable row level security;
create policy "Authenticated read econ_news_finnhub_articles"
  on econ_news_finnhub_articles for select to authenticated using (true);

alter table econ_news_finnhub_article_segments enable row level security;
create policy "Authenticated read econ_news_finnhub_article_segments"
  on econ_news_finnhub_article_segments for select to authenticated using (true);

alter table econ_news_newsfilter_articles enable row level security;
create policy "Authenticated read econ_news_newsfilter_articles"
  on econ_news_newsfilter_articles for select to authenticated using (true);

alter table econ_news_newsfilter_article_segments enable row level security;
create policy "Authenticated read econ_news_newsfilter_article_segments"
  on econ_news_newsfilter_article_segments for select to authenticated using (true);

alter table econ_news_article_assessments enable row level security;
create policy "Authenticated read econ_news_article_assessments"
  on econ_news_article_assessments for select to authenticated using (true);
