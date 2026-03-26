#!/usr/bin/env python3
"""
Poll Finnhub free news endpoints into normalized raw research tables as Warbird's secondary news source.
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from collections.abc import Iterable
from datetime import datetime, timezone
from typing import Any

import requests
from supabase import Client, create_client

from project_env import load_project_env
from raw_news_contract import (
    build_article_key,
    build_dedupe_key,
    extract_article_with_node,
    extract_domain,
    is_junk,
    load_raw_news_contract,
    matched_keywords,
    normalize_text,
    normalize_title_for_dedupe,
    published_minute_iso,
    score_article,
)

DEFAULT_LIMIT_PER_CATEGORY = 60
DEFAULT_INTERVAL_SECONDS = 300


def parse_args() -> argparse.Namespace:
    contract = load_raw_news_contract()
    parser = argparse.ArgumentParser(description="Poll Finnhub news into raw research tables.")
    parser.add_argument("--target", required=True, choices=("local", "cloud"))
    parser.add_argument("--once", action="store_true", help="Run one pass and exit.")
    parser.add_argument("--interval-seconds", type=int, default=DEFAULT_INTERVAL_SECONDS)
    parser.add_argument("--limit-per-category", type=int, default=DEFAULT_LIMIT_PER_CATEGORY)
    parser.add_argument(
        "--topics",
        nargs="*",
        choices=sorted(contract.topic_codes),
        help="Optional subset of tracked topics.",
    )
    parser.add_argument("--supabase-url", help="Override Supabase URL.")
    parser.add_argument("--supabase-key", help="Override Supabase service-role key.")
    parser.add_argument("--dry-run", action="store_true", help="Fetch and classify without writing.")
    parser.add_argument("--sample-limit", type=int, default=0)
    return parser.parse_args()


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
            raise RuntimeError("local target requires local Supabase credentials.")
        return url, key

    url = args.supabase_url or os.environ.get("SUPABASE_URL") or os.environ.get("NEXT_PUBLIC_SUPABASE_URL")
    key = args.supabase_key or os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        raise RuntimeError("cloud target requires cloud Supabase credentials.")
    return url, key


def require_finnhub_key() -> str:
    load_project_env()
    api_key = os.environ.get("FINNHUB_API_KEY")
    if not api_key:
        raise RuntimeError("FINNHUB_API_KEY is required for Finnhub polling.")
    return api_key


def chunked(values: list[str], size: int) -> Iterable[list[str]]:
    for start in range(0, len(values), size):
        yield values[start:start + size]


def fetch_category_news(api_key: str, category: str, limit_per_category: int) -> list[dict[str, Any]]:
    response = requests.get(
        "https://finnhub.io/api/v1/news",
        params={"category": category, "token": api_key},
        timeout=30,
    )
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, list):
        raise RuntimeError(f"Unexpected Finnhub payload for category={category}")
    return payload[:limit_per_category]


def upsert_articles(supabase: Client, rows: list[dict[str, Any]]) -> dict[str, int]:
    if not rows:
        return {}
    supabase.table("econ_news_finnhub_articles").upsert(rows, on_conflict="dedupe_key").execute()
    id_by_dedupe: dict[str, int] = {}
    for keys_chunk in chunked([row["dedupe_key"] for row in rows], 200):
        response = (
            supabase.table("econ_news_finnhub_articles")
            .select("id, dedupe_key")
            .in_("dedupe_key", keys_chunk)
            .execute()
        )
        for row in response.data or []:
            id_by_dedupe[str(row["dedupe_key"])] = int(row["id"])
    return id_by_dedupe


def upsert_segment_links(
    supabase: Client,
    rows: list[dict[str, Any]],
    article_ids: dict[str, int],
) -> int:
    payload = []
    fetched_at = datetime.now(timezone.utc).isoformat()
    for row in rows:
        article_id = article_ids.get(row["dedupe_key"])
        if article_id is None:
            continue
        payload.append(
            {
                "article_id": article_id,
                "segment": row["segment"],
                "query_text": row["query_text"],
                "matched_keywords": row["matched_keywords"],
                "matched_symbols": row["matched_symbols"],
                "fetched_at": fetched_at,
            }
        )
    if not payload:
        return 0
    supabase.table("econ_news_finnhub_article_segments").upsert(
        payload,
        on_conflict="article_id,segment",
    ).execute()
    return len(payload)


def upsert_assessments(supabase: Client, rows: list[dict[str, Any]]) -> int:
    if not rows:
        return 0
    supabase.table("econ_news_article_assessments").upsert(
        rows,
        on_conflict="provider,dedupe_key,topic_code,scoring_version",
    ).execute()
    return len(rows)


def print_samples(samples: list[dict[str, Any]], sample_limit: int) -> None:
    if sample_limit <= 0:
        return
    print()
    print("Sample Finnhub articles:")
    for sample in samples[:sample_limit]:
        preview = (sample["article_body"] or sample["summary"] or "")[:500]
        print(f"- topic={sample['topic_code']} source={sample['publisher_domain'] or 'unknown'}")
        print(f"  published_at={sample['published_at']} extraction_status={sample['extraction_status']} words={sample['body_word_count']}")
        print(f"  benchmark_fit={sample['benchmark_fit_score']:.4f} reasoning_confidence={sample['reasoning_confidence']:.4f}")
        print(f"  title={sample['title']}")
        if preview:
            print(f"  preview={preview}")
    print()


def run_pass(args: argparse.Namespace, supabase: Client | None) -> tuple[int, int, int]:
    contract = load_raw_news_contract()
    api_key = require_finnhub_key()
    topic_codes = args.topics or list(contract.topic_codes)
    topic_map = contract.topic_map

    article_rows: dict[str, dict[str, Any]] = {}
    segment_links: dict[str, dict[str, Any]] = {}
    assessment_rows: dict[str, dict[str, Any]] = {}
    samples: list[dict[str, Any]] = []
    duplicates_dropped = 0
    extraction_failures = 0

    for category in contract.finnhub_categories:
        rows = fetch_category_news(api_key, category, args.limit_per_category)
        print(f"[{category}] fetched {len(rows)} rows")
        for item in rows:
            title = normalize_text(item.get("headline"))
            summary = normalize_text(item.get("summary")) or None
            url = normalize_text(item.get("url"))
            publisher_name = normalize_text(item.get("source")) or "Finnhub"
            publisher_domain = extract_domain(url)
            published_at = datetime.fromtimestamp(int(item.get("datetime", 0)), tz=timezone.utc).isoformat()
            related = [symbol.strip().upper() for symbol in str(item.get("related") or "").split(",") if symbol.strip()]
            matched_symbols = [symbol for symbol in related if symbol in contract.watchlist_symbols]

            if not title or not url or not matched_symbols:
                continue
            if publisher_domain not in contract.trusted_domains:
                continue
            if is_junk(title, summary or "", publisher_domain, contract):
                continue

            normalized_title = normalize_title_for_dedupe(title)
            published_minute = published_minute_iso(published_at)
            dedupe_key = build_dedupe_key(normalized_title, publisher_domain, published_minute)
            if dedupe_key in article_rows:
                duplicates_dropped += 1
                continue

            extraction = extract_article_with_node(url)
            if extraction["extractionStatus"] == "FAILED":
                extraction_failures += 1

            article_key = build_article_key(str(item.get("id") or ""), url, title, published_at)
            article_rows[dedupe_key] = {
                "article_key": article_key,
                "provider": "finnhub",
                "finnhub_id": int(item["id"]),
                "source_category": category,
                "url": url,
                "canonical_url": extraction.get("canonicalUrl"),
                "publisher_name": publisher_name,
                "publisher_domain": publisher_domain,
                "title": title,
                "summary": summary,
                "article_excerpt": extraction.get("excerpt"),
                "article_body": extraction.get("contentText"),
                "body_word_count": int(extraction.get("wordCount") or 0),
                "image_url": normalize_text(item.get("image")) or extraction.get("imageUrl"),
                "related_symbols": matched_symbols,
                "published_at": published_at,
                "published_minute": published_minute,
                "normalized_title": normalized_title,
                "dedupe_key": dedupe_key,
                "extraction_status": extraction.get("extractionStatus") or "FAILED",
                "extraction_method": extraction.get("extractionMethod"),
                "provider_metadata": {
                    "request_url": extraction.get("requestUrl"),
                    "final_url": extraction.get("finalUrl"),
                    "site_name": extraction.get("siteName"),
                    "byline": extraction.get("byline"),
                    "category": category,
                },
                "extracted_at": datetime.now(timezone.utc).isoformat(),
            }

            matched_any_topic = False
            for topic_code in topic_codes:
                topic = topic_map[topic_code]
                matched_topic_keywords = matched_keywords(
                    title,
                    f"{summary or ''} {extraction.get('contentText') or ''}",
                    topic.keywords,
                )
                if not matched_topic_keywords:
                    continue

                matched_any_topic = True
                score = score_article(
                    provider="finnhub",
                    publisher_domain=publisher_domain,
                    topic=topic,
                    title=title,
                    summary=summary,
                    body_text=extraction.get("contentText"),
                    image_url=normalize_text(item.get("image")) or extraction.get("imageUrl"),
                    explicit_symbols=matched_symbols,
                    matched_topic_keywords=matched_topic_keywords,
                )

                segment_links[f"{dedupe_key}::{topic_code}"] = {
                    "dedupe_key": dedupe_key,
                    "segment": topic_code,
                    "query_text": f"finnhub:{category}",
                    "matched_keywords": list(matched_topic_keywords),
                    "matched_symbols": score["identified_symbols"],
                }

                assessment_rows[f"{dedupe_key}::{topic_code}"] = {
                    "provider": "finnhub",
                    "dedupe_key": dedupe_key,
                    "article_key": article_key,
                    "topic_code": topic_code,
                    "identified_symbols": score["identified_symbols"],
                    "reason_flags": score["reason_flags"],
                    "source_quality_score": score["source_quality_score"],
                    "market_relevance_score": score["market_relevance_score"],
                    "macro_specificity_score": score["macro_specificity_score"],
                    "technical_specificity_score": score["technical_specificity_score"],
                    "cross_asset_context_score": score["cross_asset_context_score"],
                    "image_presence_score": score["image_presence_score"],
                    "watchlist_relevance_score": score["watchlist_relevance_score"],
                    "reasoning_confidence": score["reasoning_confidence"],
                    "benchmark_fit_score": score["benchmark_fit_score"],
                    "evidence": score["evidence"],
                    "scoring_version": contract.scoring_version,
                    "scored_at": datetime.now(timezone.utc).isoformat(),
                }

                samples.append(
                    {
                        "topic_code": topic_code,
                        "publisher_domain": publisher_domain,
                        "published_at": published_at,
                        "extraction_status": article_rows[dedupe_key]["extraction_status"],
                        "body_word_count": article_rows[dedupe_key]["body_word_count"],
                        "benchmark_fit_score": score["benchmark_fit_score"],
                        "reasoning_confidence": score["reasoning_confidence"],
                        "title": title,
                        "summary": summary,
                        "article_body": article_rows[dedupe_key]["article_body"],
                    }
                )

            if not matched_any_topic:
                article_rows.pop(dedupe_key, None)

    print(f"Unique articles={len(article_rows)} segment_links={len(segment_links)} assessments={len(assessment_rows)}")
    print(f"Duplicates dropped={duplicates_dropped} extraction_failures={extraction_failures}")
    print_samples(samples, args.sample_limit)

    if args.dry_run:
        return len(article_rows), len(segment_links), len(assessment_rows)

    if supabase is None:
        raise RuntimeError("Supabase client required for non-dry-run execution.")

    article_ids = upsert_articles(supabase, list(article_rows.values()))
    linked = upsert_segment_links(supabase, list(segment_links.values()), article_ids)
    assessed = upsert_assessments(supabase, list(assessment_rows.values()))
    return len(article_ids), linked, assessed


def main() -> None:
    args = parse_args()
    try:
        supabase: Client | None = None
        if not args.dry_run:
            supabase_url, supabase_key = resolve_supabase_credentials(args)
            supabase = create_client(supabase_url, supabase_key)

        mode = "single pass" if args.once else f"continuous ({args.interval_seconds}s interval)"
        print(f"Finnhub raw intake | target={args.target} | mode={mode} | dry_run={args.dry_run}")

        if args.once:
            articles, segment_links, assessments = run_pass(args, supabase)
            print(f"Done. {articles} articles, {segment_links} topic links, {assessments} assessments.")
            return

        while True:
            tick = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
            print(f"[{tick}] polling...")
            articles, segment_links, assessments = run_pass(args, supabase)
            print(f"[{tick}] complete: {articles} articles, {segment_links} topic links, {assessments} assessments.\n")
            time.sleep(args.interval_seconds)
    except KeyboardInterrupt:
        print("\nStopped.")
    except Exception as exc:
        print(f"ERROR: {exc}")
        sys.exit(1)


if __name__ == "__main__":
    main()
