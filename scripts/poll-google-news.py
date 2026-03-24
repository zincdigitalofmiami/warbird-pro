#!/usr/bin/env python3
"""
Poll Google News RSS into normalized raw research tables.

This script captures raw article cards only. It does not create `news_signals`
or synthetic sentiment, because that admission belongs to a later phase after
the raw intake contract is validated against the active plan.

Google News RSS links are Google-owned redirect/article URLs, so domain
filtering and source attribution rely on the RSS <source url="..."> metadata,
not on the item link itself.

Usage:
    python3 scripts/poll-google-news.py --target local --once
    python3 scripts/poll-google-news.py --target local --interval-seconds 60
    python3 scripts/poll-google-news.py --target cloud --once --dry-run

Environment:
    cloud target:
      SUPABASE_URL or NEXT_PUBLIC_SUPABASE_URL
      SUPABASE_SERVICE_ROLE_KEY

    local target:
      WARBIRD_LOCAL_SUPABASE_URL or SUPABASE_LOCAL_URL
      WARBIRD_LOCAL_SUPABASE_SERVICE_ROLE_KEY or SUPABASE_LOCAL_SERVICE_ROLE_KEY

Notes:
    - Research/raw intake only. Do not wire into production until phase-ready.
    - Verify Google News RSS usage rights before any production/commercial use.
"""
from __future__ import annotations

import argparse
import hashlib
import html
import os
import re
import sys
import time
import xml.etree.ElementTree as ET
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote_plus, urlparse
from urllib.request import Request, urlopen

from supabase import Client, create_client

from project_env import load_project_env

GOOGLE_NEWS_RSS = "https://news.google.com/rss/search?q={query}&hl=en-US&gl=US&ceid=US:en"
DEFAULT_TIMEOUT_SECONDS = 20
DEFAULT_INTERVAL_SECONDS = 60
DEFAULT_LIMIT_PER_SEGMENT = 20


@dataclass(frozen=True)
class SegmentSpec:
    query_text: str
    keywords: tuple[str, ...]


SEGMENTS: dict[str, SegmentSpec] = {
    "sp500_market": SegmentSpec(
        query_text='"S&P 500" OR "stock market today" OR "Wall Street" OR "U.S. stocks"',
        keywords=(
            "S&P 500",
            "stock market today",
            "Wall Street",
            "U.S. stocks",
        ),
    ),
    "sp500_fed_policy": SegmentSpec(
        query_text='"S&P 500" AND ("Federal Reserve" OR FOMC OR Powell OR "interest rate" OR "rate cut" OR "rate hike")',
        keywords=(
            "Federal Reserve",
            "FOMC",
            "Powell",
            "interest rate",
            "rate cut",
            "rate hike",
        ),
    ),
    "sp500_inflation": SegmentSpec(
        query_text='"S&P 500" AND (inflation OR CPI OR PCE OR PPI OR "core inflation")',
        keywords=(
            "inflation",
            "CPI",
            "PCE",
            "PPI",
            "core inflation",
        ),
    ),
    "sp500_yields_rates": SegmentSpec(
        query_text='"S&P 500" AND ("10-year yield" OR Treasury OR yields OR SOFR OR breakeven)',
        keywords=(
            "10-year yield",
            "Treasury",
            "yields",
            "SOFR",
            "breakeven",
        ),
    ),
    "sp500_labor_growth": SegmentSpec(
        query_text='"S&P 500" AND ("jobs report" OR payrolls OR unemployment OR claims OR GDP OR retail sales)',
        keywords=(
            "jobs report",
            "payrolls",
            "unemployment",
            "claims",
            "GDP",
            "retail sales",
        ),
    ),
    "sp500_geopolitics": SegmentSpec(
        query_text='"S&P 500" AND (Iran OR Israel OR war OR sanctions OR tariffs OR "trade war" OR "Middle East")',
        keywords=(
            "Iran",
            "Israel",
            "war",
            "sanctions",
            "tariffs",
            "trade war",
            "Middle East",
        ),
    ),
    "sp500_energy_inflation": SegmentSpec(
        query_text='"S&P 500" AND (oil OR WTI OR crude OR OPEC OR gasoline OR energy prices)',
        keywords=(
            "oil",
            "WTI",
            "crude",
            "OPEC",
            "gasoline",
            "energy prices",
        ),
    ),
    "sp500_volatility": SegmentSpec(
        query_text='"S&P 500" AND (VIX OR volatility OR selloff OR correction OR "risk off" OR "flight to safety")',
        keywords=(
            "VIX",
            "volatility",
            "selloff",
            "correction",
            "risk off",
            "flight to safety",
        ),
    ),
    "sp500_earnings_megacap": SegmentSpec(
        query_text='"S&P 500" AND (earnings OR Nvidia OR Apple OR Microsoft OR Amazon OR Meta OR Tesla)',
        keywords=(
            "earnings",
            "Nvidia",
            "Apple",
            "Microsoft",
            "Amazon",
            "Meta",
            "Tesla",
        ),
    ),
    "sp500_policy": SegmentSpec(
        query_text='"S&P 500" AND (Trump OR "White House" OR Congress OR regulation OR "executive order" OR Treasury)',
        keywords=(
            "Trump",
            "White House",
            "Congress",
            "regulation",
            "executive order",
            "Treasury",
        ),
    ),
    "sp500_credit_liquidity": SegmentSpec(
        query_text='"S&P 500" AND ("credit spreads" OR liquidity OR "high yield" OR "bank stress" OR "Fed balance sheet" OR "money supply")',
        keywords=(
            "credit spreads",
            "liquidity",
            "high yield",
            "bank stress",
            "Fed balance sheet",
            "money supply",
        ),
    ),
}


BLOCKED_DOMAINS: set[str] = {
    "247wallst.com",
    "ambcrypto.com",
    "beincrypto.com",
    "bitcoinist.com",
    "coindesk.com",
    "coingape.com",
    "cointelegraph.com",
    "cryptonews.com",
    "cryptopotato.com",
    "cryptoslate.com",
    "dailymail.co.uk",
    "decrypt.co",
    "eonline.com",
    "espn.com",
    "express.co.uk",
    "gurufocus.com",
    "insidermonkey.com",
    "motleyfool.com",
    "nypost.com",
    "otcmarkets.com",
    "pennystocks.com",
    "people.com",
    "smallcapvoice.com",
    "stockanalysis.com",
    "stockstowatch.com",
    "thesun.co.uk",
    "tipranks.com",
    "tmz.com",
    "u.today",
    "wallstreetpr.com",
}

TRUSTED_DOMAINS: set[str] = {
    "apnews.com",
    "axios.com",
    "barrons.com",
    "bea.gov",
    "bls.gov",
    "bloomberg.com",
    "cmegroup.com",
    "cnbc.com",
    "federalreserve.gov",
    "finance.yahoo.com",
    "ft.com",
    "investopedia.com",
    "marketwatch.com",
    "nytimes.com",
    "politico.com",
    "reuters.com",
    "seekingalpha.com",
    "thehill.com",
    "tradingview.com",
    "washingtonpost.com",
    "wsj.com",
}

CLICKBAIT_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"you won't believe", re.IGNORECASE),
    re.compile(r"\d+\s+stocks?\s+to\s+buy", re.IGNORECASE),
    re.compile(r"next\s+(big|huge)\s+thing", re.IGNORECASE),
    re.compile(r"get rich", re.IGNORECASE),
    re.compile(r"millionaire", re.IGNORECASE),
    re.compile(r"(bitcoin|ethereum|crypto|altcoin|memecoin|dogecoin)", re.IGNORECASE),
    re.compile(r"(nft|web3|metaverse)", re.IGNORECASE),
    re.compile(r"penny stock", re.IGNORECASE),
    re.compile(r"passive income", re.IGNORECASE),
    re.compile(r"(horoscope|zodiac|astrology)", re.IGNORECASE),
    re.compile(r"celebrity", re.IGNORECASE),
)


@dataclass(frozen=True)
class ArticleCard:
    article_key: str
    google_news_guid: str
    google_news_url: str
    publisher_name: str | None
    publisher_url: str | None
    publisher_domain: str | None
    title: str
    summary: str | None
    published_at: str


@dataclass(frozen=True)
class SegmentMatch:
    article_key: str
    segment: str
    query_text: str
    matched_keywords: tuple[str, ...]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Poll Google News RSS into raw research tables.")
    parser.add_argument("--target", required=True, choices=("local", "cloud"))
    parser.add_argument("--once", action="store_true", help="Run one pass and exit.")
    parser.add_argument(
        "--interval-seconds",
        type=int,
        default=DEFAULT_INTERVAL_SECONDS,
        help=f"Polling interval for continuous mode. Default: {DEFAULT_INTERVAL_SECONDS}",
    )
    parser.add_argument(
        "--limit-per-segment",
        type=int,
        default=DEFAULT_LIMIT_PER_SEGMENT,
        help=f"Max RSS items to keep per segment. Default: {DEFAULT_LIMIT_PER_SEGMENT}",
    )
    parser.add_argument(
        "--segments",
        nargs="*",
        choices=sorted(SEGMENTS.keys()),
        help="Optional subset of tracked segments.",
    )
    parser.add_argument("--supabase-url", help="Override Supabase URL.")
    parser.add_argument("--supabase-key", help="Override Supabase service-role key.")
    parser.add_argument("--dry-run", action="store_true", help="Fetch and classify without writing.")
    return parser.parse_args()


def extract_domain(url: str | None) -> str | None:
    if not url:
        return None
    try:
        hostname = urlparse(url).hostname or ""
    except ValueError:
        return None
    if hostname.startswith("www."):
        hostname = hostname[4:]
    return hostname or None


def normalize_text(value: str | None) -> str:
    if not value:
        return ""
    return re.sub(r"\s+", " ", html.unescape(value)).strip()


def strip_html_tags(value: str | None) -> str:
    return normalize_text(re.sub(r"<[^>]+>", " ", value or ""))


def parse_published_at(raw_value: str | None) -> str | None:
    if not raw_value:
        return None
    for fmt in ("%a, %d %b %Y %H:%M:%S %Z", "%a, %d %b %Y %H:%M:%S GMT"):
        try:
            dt = datetime.strptime(raw_value, fmt)
            return dt.replace(tzinfo=timezone.utc).isoformat()
        except ValueError:
            continue
    try:
        dt = datetime.fromisoformat(raw_value.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).isoformat()
    except ValueError:
        return None


def build_article_key(google_news_guid: str, google_news_url: str, title: str, published_at: str) -> str:
    base = google_news_guid or google_news_url or f"{title}|{published_at}"
    return hashlib.sha256(base.encode("utf-8")).hexdigest()


def is_junk(title: str, summary: str, publisher_domain: str | None) -> bool:
    if publisher_domain in BLOCKED_DOMAINS:
        return True
    if publisher_domain in TRUSTED_DOMAINS:
        return False
    haystack = f"{title} {summary}"
    for pattern in CLICKBAIT_PATTERNS:
        if pattern.search(haystack):
            return True
    return len(title.strip()) < 15


def matched_keywords(title: str, summary: str, keywords: Iterable[str]) -> tuple[str, ...]:
    haystack = f"{title} {summary}".lower()
    return tuple(keyword for keyword in keywords if keyword.lower() in haystack)


def fetch_xml(url: str, timeout_seconds: int) -> bytes:
    request = Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urlopen(request, timeout=timeout_seconds) as response:
        return response.read()


def parse_feed_items(xml_bytes: bytes) -> list[ET.Element]:
    root = ET.fromstring(xml_bytes)
    return list(root.findall("./channel/item"))


def article_from_item(item: ET.Element) -> tuple[ArticleCard | None, dict[str, Any]]:
    title = normalize_text(item.findtext("title"))
    google_news_url = normalize_text(item.findtext("link"))
    google_news_guid = normalize_text(item.findtext("guid"))
    published_at = parse_published_at(item.findtext("pubDate"))
    description = strip_html_tags(item.findtext("description"))
    source = item.find("source")
    publisher_name = normalize_text(source.text if source is not None else "")
    publisher_url = source.get("url") if source is not None else None
    publisher_url = normalize_text(publisher_url) or None
    publisher_domain = extract_domain(publisher_url)

    if not title or not google_news_url or not google_news_guid or not published_at:
        return None, {
            "title": title,
            "google_news_url": google_news_url,
            "google_news_guid": google_news_guid,
            "published_at": published_at,
        }

    article = ArticleCard(
        article_key=build_article_key(google_news_guid, google_news_url, title, published_at),
        google_news_guid=google_news_guid,
        google_news_url=google_news_url,
        publisher_name=publisher_name or None,
        publisher_url=publisher_url,
        publisher_domain=publisher_domain,
        title=title,
        summary=description[:2000] or None,
        published_at=published_at,
    )
    return article, {}


def fetch_segment(
    segment: str,
    spec: SegmentSpec,
    timeout_seconds: int,
    limit_per_segment: int,
) -> tuple[dict[str, ArticleCard], list[SegmentMatch]]:
    url = GOOGLE_NEWS_RSS.format(query=quote_plus(spec.query_text))
    xml_bytes = fetch_xml(url, timeout_seconds)
    items = parse_feed_items(xml_bytes)

    articles: dict[str, ArticleCard] = {}
    segment_links: list[SegmentMatch] = []

    for item in items[:limit_per_segment]:
        article, _ = article_from_item(item)
        if article is None:
            continue
        if is_junk(article.title, article.summary or "", article.publisher_domain):
            continue

        articles[article.article_key] = article
        segment_links.append(
            SegmentMatch(
                article_key=article.article_key,
                segment=segment,
                query_text=spec.query_text,
                matched_keywords=matched_keywords(article.title, article.summary or "", spec.keywords),
            )
        )

    return articles, segment_links


def resolve_supabase_credentials(args: argparse.Namespace) -> tuple[str, str]:
    load_project_env()

    if args.supabase_url and args.supabase_key:
        return args.supabase_url, args.supabase_key

    if args.target == "local":
        url = args.supabase_url or os.environ.get("WARBIRD_LOCAL_SUPABASE_URL") or os.environ.get("SUPABASE_LOCAL_URL")
        key = (
            args.supabase_key
            or os.environ.get("WARBIRD_LOCAL_SUPABASE_SERVICE_ROLE_KEY")
            or os.environ.get("SUPABASE_LOCAL_SERVICE_ROLE_KEY")
        )
        if not url or not key:
            raise RuntimeError(
                "local target requires --supabase-url/--supabase-key or "
                "WARBIRD_LOCAL_SUPABASE_URL + WARBIRD_LOCAL_SUPABASE_SERVICE_ROLE_KEY."
            )
        return url, key

    url = args.supabase_url or os.environ.get("SUPABASE_URL") or os.environ.get("NEXT_PUBLIC_SUPABASE_URL")
    key = args.supabase_key or os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        raise RuntimeError(
            "cloud target requires --supabase-url/--supabase-key or "
            "SUPABASE_URL + SUPABASE_SERVICE_ROLE_KEY."
        )
    return url, key


def chunked(values: list[str], size: int) -> Iterable[list[str]]:
    for start in range(0, len(values), size):
        yield values[start:start + size]


def upsert_articles(supabase: Client, articles: dict[str, ArticleCard]) -> dict[str, int]:
    if not articles:
        return {}

    rows = [
        {
            "article_key": article.article_key,
            "provider": "google_news_rss",
            "google_news_guid": article.google_news_guid,
            "google_news_url": article.google_news_url,
            "publisher_name": article.publisher_name,
            "publisher_url": article.publisher_url,
            "publisher_domain": article.publisher_domain,
            "title": article.title,
            "summary": article.summary,
            "published_at": article.published_at,
            "fetched_at": datetime.now(timezone.utc).isoformat(),
        }
        for article in articles.values()
    ]

    supabase.table("econ_news_rss_articles").upsert(rows, on_conflict="article_key").execute()

    id_by_key: dict[str, int] = {}
    keys = list(articles.keys())
    for keys_chunk in chunked(keys, 200):
        response = (
            supabase.table("econ_news_rss_articles")
            .select("id, article_key")
            .in_("article_key", keys_chunk)
            .execute()
        )
        for row in response.data or []:
            id_by_key[str(row["article_key"])] = int(row["id"])
    return id_by_key


def upsert_segment_links(
    supabase: Client,
    segment_links: list[SegmentMatch],
    article_ids: dict[str, int],
) -> int:
    rows = []
    fetched_at = datetime.now(timezone.utc).isoformat()
    for link in segment_links:
        article_id = article_ids.get(link.article_key)
        if article_id is None:
            continue
        rows.append(
            {
                "article_id": article_id,
                "segment": link.segment,
                "query_text": link.query_text,
                "matched_keywords": list(link.matched_keywords),
                "fetched_at": fetched_at,
            }
        )

    if not rows:
        return 0

    supabase.table("econ_news_rss_article_segments").upsert(
        rows,
        on_conflict="article_id,segment",
    ).execute()
    return len(rows)


def run_pass(args: argparse.Namespace, supabase: Client | None) -> tuple[int, int]:
    tracked_segments = args.segments or list(SEGMENTS.keys())
    all_articles: dict[str, ArticleCard] = {}
    all_segment_links: list[SegmentMatch] = []

    for segment in tracked_segments:
        spec = SEGMENTS[segment]
        try:
            articles, segment_links = fetch_segment(
                segment=segment,
                spec=spec,
                timeout_seconds=DEFAULT_TIMEOUT_SECONDS,
                limit_per_segment=args.limit_per_segment,
            )
            all_articles.update(articles)
            all_segment_links.extend(segment_links)
            print(f"[{segment}] {len(articles)} articles, {len(segment_links)} segment links")
        except Exception as exc:
            print(f"[{segment}] ERROR: {exc}")
        time.sleep(1)

    if args.dry_run:
        return len(all_articles), len(all_segment_links)

    if supabase is None:
        raise RuntimeError("Supabase client required for non-dry-run execution.")

    article_ids = upsert_articles(supabase, all_articles)
    linked = upsert_segment_links(supabase, all_segment_links, article_ids)
    return len(article_ids), linked


def main() -> None:
    args = parse_args()

    try:
        supabase: Client | None = None
        if not args.dry_run:
            supabase_url, supabase_key = resolve_supabase_credentials(args)
            supabase = create_client(supabase_url, supabase_key)

        tracked_segments = args.segments or list(SEGMENTS.keys())
        mode = "single pass" if args.once else f"continuous ({args.interval_seconds}s interval)"
        print(f"Google News RSS raw intake | target={args.target} | mode={mode}")
        print(f"Segments: {', '.join(tracked_segments)}")
        print(
            f"Blocked domains={len(BLOCKED_DOMAINS)} | "
            f"Trusted domains={len(TRUSTED_DOMAINS)} | dry_run={args.dry_run}"
        )
        print()

        if args.once:
            articles, segment_links = run_pass(args, supabase)
            print(f"Done. {articles} unique articles, {segment_links} segment links.")
            return

        while True:
            tick = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
            print(f"[{tick}] polling...")
            articles, segment_links = run_pass(args, supabase)
            print(f"[{tick}] complete: {articles} unique articles, {segment_links} segment links.\n")
            time.sleep(args.interval_seconds)
    except KeyboardInterrupt:
        print("\nStopped.")
    except Exception as exc:
        print(f"ERROR: {exc}")
        sys.exit(1)


if __name__ == "__main__":
    main()
