from __future__ import annotations

import hashlib
import json
import re
import subprocess
from dataclasses import dataclass
from functools import lru_cache
from html import unescape
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "news_raw_contract.json"
EXTRACTOR_SCRIPT_PATH = Path(__file__).resolve().parent / "extract-article.mjs"

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

HTML_TAG_RE = re.compile(r"<[^>]+>")
WHITESPACE_RE = re.compile(r"\s+")
NON_ALNUM_RE = re.compile(r"[^a-z0-9]+")
NUMBER_SIGNAL_RE = re.compile(r"\b\d+(?:[.,]\d+)?\s*(?:%|bp|bps|k|m|b|points?)\b", re.IGNORECASE)


@dataclass(frozen=True)
class TopicSpec:
    code: str
    label: str
    family: str
    econ_category: str | None
    tags: tuple[str, ...]
    google_query: str
    keywords: tuple[str, ...]


@dataclass(frozen=True)
class RawNewsContract:
    scoring_version: str
    watchlist_symbols: tuple[str, ...]
    blocked_domains: frozenset[str]
    trusted_domains: frozenset[str]
    premier_domains: frozenset[str]
    newsfilter_source_allowlist: frozenset[str]
    finnhub_categories: tuple[str, ...]
    benchmark_weights: dict[str, float]
    benchmark_terms: dict[str, tuple[str, ...]]
    topics: tuple[TopicSpec, ...]

    @property
    def topic_codes(self) -> tuple[str, ...]:
        return tuple(topic.code for topic in self.topics)

    @property
    def topic_map(self) -> dict[str, TopicSpec]:
        return {topic.code: topic for topic in self.topics}


@lru_cache(maxsize=1)
def load_raw_news_contract() -> RawNewsContract:
    payload = json.loads(CONFIG_PATH.read_text())
    topics = tuple(
        TopicSpec(
            code=entry["code"],
            label=entry["label"],
            family=entry["family"],
            econ_category=entry.get("econ_category"),
            tags=tuple(entry.get("tags", [])),
            google_query=entry["google_query"],
            keywords=tuple(entry.get("keywords", [])),
        )
        for entry in payload["topics"]
    )
    benchmark_terms = {
        key: tuple(values)
        for key, values in payload["benchmark_terms"].items()
    }
    return RawNewsContract(
        scoring_version=payload["scoring_version"],
        watchlist_symbols=tuple(payload["watchlist_symbols"]),
        blocked_domains=frozenset(payload["blocked_domains"]),
        trusted_domains=frozenset(payload["trusted_domains"]),
        premier_domains=frozenset(payload["premier_domains"]),
        newsfilter_source_allowlist=frozenset(payload["newsfilter_source_allowlist"]),
        finnhub_categories=tuple(payload["finnhub_categories"]),
        benchmark_weights={key: float(value) for key, value in payload["benchmark_weights"].items()},
        benchmark_terms=benchmark_terms,
        topics=topics,
    )


def normalize_text(value: str | None) -> str:
    if not value:
        return ""
    return WHITESPACE_RE.sub(" ", unescape(value)).strip()


def strip_html_tags(value: str | None) -> str:
    return normalize_text(HTML_TAG_RE.sub(" ", value or ""))


def extract_domain(url: str | None) -> str | None:
    if not url:
        return None
    try:
        hostname = urlparse(url).hostname or ""
    except ValueError:
        return None
    hostname = hostname.lower()
    if hostname.startswith("www."):
        hostname = hostname[4:]
    return hostname or None


def normalize_title_for_dedupe(title: str) -> str:
    lowered = normalize_text(title).lower()
    lowered = NON_ALNUM_RE.sub(" ", lowered)
    return WHITESPACE_RE.sub(" ", lowered).strip()


def published_minute_iso(iso_value: str) -> str:
    trimmed = iso_value[:16]
    if trimmed.endswith(":"):
        trimmed = trimmed[:-1]
    return f"{trimmed}:00+00:00"


def build_article_key(*parts: str) -> str:
    base = "|".join(part for part in parts if part)
    return hashlib.sha256(base.encode("utf-8")).hexdigest()


def build_dedupe_key(normalized_title: str, publisher_domain: str | None, published_minute: str) -> str:
    return build_article_key(normalized_title, publisher_domain or "", published_minute)


def is_junk(title: str, summary: str, publisher_domain: str | None, contract: RawNewsContract) -> bool:
    if publisher_domain in contract.blocked_domains:
        return True
    if publisher_domain in contract.trusted_domains:
        return False
    haystack = f"{title} {summary}"
    for pattern in CLICKBAIT_PATTERNS:
        if pattern.search(haystack):
            return True
    return len(normalize_text(title)) < 15


def matched_keywords(title: str, summary: str, keywords: tuple[str, ...]) -> tuple[str, ...]:
    haystack = f"{title} {summary}".lower()
    return tuple(keyword for keyword in keywords if keyword.lower() in haystack)


def extract_watchlist_symbols(
    contract: RawNewsContract,
    text: str,
    explicit_symbols: list[str] | tuple[str, ...] | None = None,
) -> tuple[str, ...]:
    haystack = f" {normalize_text(text).upper()} "
    matched: list[str] = []
    explicit = {symbol.upper() for symbol in (explicit_symbols or [])}
    for symbol in contract.watchlist_symbols:
        if symbol.upper() in explicit:
            matched.append(symbol)
            continue
        if f" {symbol.upper()} " in haystack:
            matched.append(symbol)
    return tuple(dict.fromkeys(matched))


def count_term_matches(text: str, terms: tuple[str, ...]) -> int:
    lowered = normalize_text(text).lower()
    return sum(1 for term in terms if term.lower() in lowered)


def count_number_signals(text: str) -> int:
    return len(NUMBER_SIGNAL_RE.findall(text))


def _bounded_score(raw_value: float, ceiling: float) -> float:
    return max(0.0, min(raw_value / ceiling, 1.0))


def score_article(
    *,
    provider: str,
    publisher_domain: str | None,
    topic: TopicSpec,
    title: str,
    summary: str | None,
    body_text: str | None,
    image_url: str | None,
    explicit_symbols: list[str] | tuple[str, ...] | None = None,
    matched_topic_keywords: tuple[str, ...] = (),
) -> dict[str, Any]:
    contract = load_raw_news_contract()
    text = normalize_text(f"{title} {summary or ''} {body_text or ''}")
    identified_symbols = extract_watchlist_symbols(contract, text, explicit_symbols)
    market_match_count = count_term_matches(text, contract.benchmark_terms["market_context"])
    macro_match_count = count_term_matches(text, contract.benchmark_terms["macro_specificity"])
    technical_match_count = count_term_matches(text, contract.benchmark_terms["technical_specificity"])
    cross_asset_match_count = count_term_matches(text, contract.benchmark_terms["cross_asset_context"])
    number_match_count = count_number_signals(text)

    if publisher_domain in contract.premier_domains:
        source_quality_score = 1.0
    elif publisher_domain in contract.trusted_domains:
        source_quality_score = 0.82
    elif publisher_domain:
        source_quality_score = 0.55
    else:
        source_quality_score = 0.45

    market_relevance_score = min(
        1.0,
        0.45 + _bounded_score(len(matched_topic_keywords), 4.0) * 0.35 + _bounded_score(market_match_count, 4.0) * 0.20,
    )
    macro_specificity_score = min(
        1.0,
        _bounded_score(macro_match_count, 4.0) * 0.65 + _bounded_score(number_match_count, 3.0) * 0.35,
    )
    technical_specificity_score = min(
        1.0,
        _bounded_score(technical_match_count, 4.0) * 0.70 + _bounded_score(number_match_count, 4.0) * 0.30,
    )
    cross_asset_context_score = _bounded_score(cross_asset_match_count, 4.0)
    image_presence_score = 1.0 if image_url else 0.0
    watchlist_relevance_score = _bounded_score(len(identified_symbols), 2.0)

    weights = contract.benchmark_weights
    benchmark_fit_score = (
        source_quality_score * weights["source_quality"]
        + market_relevance_score * weights["market_relevance"]
        + macro_specificity_score * weights["macro_specificity"]
        + technical_specificity_score * weights["technical_specificity"]
        + cross_asset_context_score * weights["cross_asset_context"]
        + image_presence_score * weights["image_presence"]
        + watchlist_relevance_score * weights["watchlist_relevance"]
    )

    reason_flags: list[str] = [f"topic:{topic.code}", f"family:{topic.family}", f"provider:{provider}"]
    if publisher_domain in contract.premier_domains:
        reason_flags.append("premier_source")
    elif publisher_domain in contract.trusted_domains:
        reason_flags.append("trusted_source")
    if matched_topic_keywords:
        reason_flags.append("topic_keyword_match")
    if market_match_count > 0:
        reason_flags.append("market_context")
    if macro_match_count > 0:
        reason_flags.append("macro_context")
    if number_match_count > 0:
        reason_flags.append("exact_numbers")
    if technical_match_count > 0:
        reason_flags.append("technical_levels")
    if cross_asset_match_count > 0:
        reason_flags.append("cross_asset_context")
    if image_url:
        reason_flags.append("image_present")
    if identified_symbols:
        reason_flags.append("watchlist_symbol_match")

    reasoning_confidence = min(
        1.0,
        0.25
        + _bounded_score(len(reason_flags), 8.0) * 0.45
        + benchmark_fit_score * 0.30,
    )

    return {
        "provider": provider,
        "identified_symbols": list(identified_symbols),
        "reason_flags": list(dict.fromkeys(reason_flags)),
        "source_quality_score": round(source_quality_score, 4),
        "market_relevance_score": round(market_relevance_score, 4),
        "macro_specificity_score": round(macro_specificity_score, 4),
        "technical_specificity_score": round(technical_specificity_score, 4),
        "cross_asset_context_score": round(cross_asset_context_score, 4),
        "image_presence_score": round(image_presence_score, 4),
        "watchlist_relevance_score": round(watchlist_relevance_score, 4),
        "reasoning_confidence": round(reasoning_confidence, 4),
        "benchmark_fit_score": round(benchmark_fit_score, 4),
        "evidence": {
            "matched_topic_keywords": list(matched_topic_keywords),
            "market_term_hits": market_match_count,
            "macro_term_hits": macro_match_count,
            "technical_term_hits": technical_match_count,
            "cross_asset_term_hits": cross_asset_match_count,
            "number_signal_hits": number_match_count,
            "image_present": bool(image_url),
        },
    }


def extract_article_with_node(url: str) -> dict[str, Any]:
    result = subprocess.run(
        ["node", str(EXTRACTOR_SCRIPT_PATH), url],
        capture_output=True,
        check=False,
        text=True,
    )
    output = (result.stdout or "").strip()
    if not output:
        raise RuntimeError(result.stderr.strip() or "article extractor returned no output")
    return json.loads(output)
