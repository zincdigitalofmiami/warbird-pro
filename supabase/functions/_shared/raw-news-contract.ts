// Raw news contract, scoring, and utilities.
// Ported from lib/news/raw-news-contract.ts:
//   - import { createHash } from "crypto" → import { createHash } from "node:crypto"
//   - import contractJson from "@/config/..." → relative JSON with assert { type: "json" }

import { createHash } from "node:crypto";
import contractJson from "./news-raw-contract.json" assert { type: "json" };

export type TopicSpec = {
  code: string;
  label: string;
  family: string;
  econ_category: string | null;
  tags: string[];
  google_query: string;
  keywords: string[];
};

type BenchmarkWeights = {
  source_quality: number;
  market_relevance: number;
  macro_specificity: number;
  technical_specificity: number;
  cross_asset_context: number;
  image_presence: number;
  watchlist_relevance: number;
};

export type ArticleScore = {
  identifiedSymbols: string[];
  reasonFlags: string[];
  sourceQualityScore: number;
  marketRelevanceScore: number;
  macroSpecificityScore: number;
  technicalSpecificityScore: number;
  crossAssetContextScore: number;
  imagePresenceScore: number;
  watchlistRelevanceScore: number;
  reasoningConfidence: number;
  benchmarkFitScore: number;
  evidence: {
    matchedTopicKeywords: string[];
    marketTermHits: number;
    macroTermHits: number;
    technicalTermHits: number;
    crossAssetTermHits: number;
    numberSignalHits: number;
    imagePresent: boolean;
  };
};

export const RAW_NEWS_CONTRACT = {
  scoringVersion: contractJson.scoring_version,
  watchlistSymbols: contractJson.watchlist_symbols,
  blockedDomains: new Set(contractJson.blocked_domains),
  trustedDomains: new Set(contractJson.trusted_domains),
  premierDomains: new Set(contractJson.premier_domains),
  newsfilterSourceAllowlist: new Set(contractJson.newsfilter_source_allowlist),
  finnhubCategories: contractJson.finnhub_categories,
  finnhubCompanyNewsSymbols: contractJson.finnhub_company_news_symbols,
  minBenchmarkFitScore: contractJson.min_benchmark_fit_score,
  benchmarkWeights: contractJson.benchmark_weights as BenchmarkWeights,
  benchmarkTerms: contractJson.benchmark_terms,
  topics: contractJson.topics as TopicSpec[],
} as const;

export const RAW_NEWS_TOPIC_MAP = new Map(
  RAW_NEWS_CONTRACT.topics.map((topic) => [topic.code, topic]),
);

const CLICKBAIT_PATTERNS = [
  /you won't believe/i,
  /\d+\s+stocks?\s+to\s+buy/i,
  /next\s+(big|huge)\s+thing/i,
  /get rich/i,
  /millionaire/i,
  /(bitcoin|ethereum|crypto|altcoin|memecoin|dogecoin)/i,
  /(nft|web3|metaverse)/i,
  /penny stock/i,
  /passive income/i,
  /(horoscope|zodiac|astrology)/i,
  /celebrity/i,
];

const NUMBER_SIGNAL_RE = /\b\d+(?:[.,]\d+)?\s*(?:%|bp|bps|k|m|b|points?)\b/gi;

export function normalizeText(value: string | null | undefined): string {
  return (value ?? "").replace(/\s+/g, " ").trim();
}

export function stripHtmlTags(value: string | null | undefined): string {
  return normalizeText((value ?? "").replace(/<[^>]+>/g, " "));
}

export function extractDomain(url: string | null | undefined): string | null {
  if (!url) {
    return null;
  }
  try {
    const hostname = new URL(url).hostname.toLowerCase().replace(/^www\./, "");
    return hostname || null;
  } catch {
    return null;
  }
}

export function normalizeTitleForDedupe(title: string): string {
  return normalizeText(title).toLowerCase().replace(/[^a-z0-9]+/g, " ");
}

export function buildArticleKey(...parts: Array<string | null | undefined>): string {
  const base = parts.filter(Boolean).join("|");
  return createHash("sha256").update(base).digest("hex");
}

export function publishedMinuteIso(value: string): string {
  const minute = new Date(value);
  minute.setUTCSeconds(0, 0);
  return minute.toISOString();
}

export function buildDedupeKey(
  normalizedTitle: string,
  publisherDomain: string | null,
  publishedMinute: string,
): string {
  return buildArticleKey(normalizedTitle, publisherDomain ?? "", publishedMinute);
}

export function matchedKeywords(title: string, bodyText: string, keywords: string[]): string[] {
  const haystack = `${title} ${bodyText}`.toLowerCase();
  return keywords.filter((keyword) => haystack.includes(keyword.toLowerCase()));
}

export function extractWatchlistSymbols(text: string, explicitSymbols: string[] = []): string[] {
  const haystack = ` ${normalizeText(text).toUpperCase()} `;
  const explicit = new Set(explicitSymbols.map((symbol) => symbol.toUpperCase()));
  const matches: string[] = [];
  for (const symbol of RAW_NEWS_CONTRACT.watchlistSymbols) {
    if (explicit.has(symbol.toUpperCase()) || haystack.includes(` ${symbol.toUpperCase()} `)) {
      matches.push(symbol);
    }
  }
  return [...new Set(matches)];
}

export function isJunk(
  title: string,
  summary: string,
  publisherDomain: string | null,
): boolean {
  if (publisherDomain && RAW_NEWS_CONTRACT.blockedDomains.has(publisherDomain)) {
    return true;
  }
  if (publisherDomain && RAW_NEWS_CONTRACT.trustedDomains.has(publisherDomain)) {
    return false;
  }
  const haystack = `${title} ${summary}`;
  return CLICKBAIT_PATTERNS.some((pattern) => pattern.test(haystack)) || normalizeText(title).length < 15;
}

function countTermMatches(text: string, terms: string[]): number {
  const lowered = normalizeText(text).toLowerCase();
  return terms.reduce((count, term) => count + (lowered.includes(term.toLowerCase()) ? 1 : 0), 0);
}

function countNumberSignals(text: string): number {
  return (text.match(NUMBER_SIGNAL_RE) ?? []).length;
}

function boundedScore(rawValue: number, ceiling: number): number {
  return Math.max(0, Math.min(rawValue / ceiling, 1));
}

export function scoreArticle(params: {
  provider: string;
  publisherDomain: string | null;
  topic: TopicSpec;
  title: string;
  summary: string | null;
  bodyText: string | null;
  imageUrl: string | null;
  explicitSymbols?: string[];
  matchedTopicKeywords?: string[];
}): ArticleScore {
  const {
    provider,
    publisherDomain,
    topic,
    title,
    summary,
    bodyText,
    imageUrl,
    explicitSymbols = [],
    matchedTopicKeywords = [],
  } = params;

  const fullText = normalizeText(`${title} ${summary ?? ""} ${bodyText ?? ""}`);
  const identifiedSymbols = extractWatchlistSymbols(fullText, explicitSymbols);
  const marketTermHits = countTermMatches(fullText, [...RAW_NEWS_CONTRACT.benchmarkTerms.market_context]);
  const macroTermHits = countTermMatches(fullText, [...RAW_NEWS_CONTRACT.benchmarkTerms.macro_specificity]);
  const technicalTermHits = countTermMatches(fullText, [...RAW_NEWS_CONTRACT.benchmarkTerms.technical_specificity]);
  const crossAssetTermHits = countTermMatches(fullText, [...RAW_NEWS_CONTRACT.benchmarkTerms.cross_asset_context]);
  const numberSignalHits = countNumberSignals(fullText);

  let sourceQualityScore = 0.45;
  if (publisherDomain && RAW_NEWS_CONTRACT.premierDomains.has(publisherDomain)) {
    sourceQualityScore = 1;
  } else if (publisherDomain && RAW_NEWS_CONTRACT.trustedDomains.has(publisherDomain)) {
    sourceQualityScore = 0.82;
  } else if (publisherDomain) {
    sourceQualityScore = 0.55;
  }

  const marketRelevanceScore = Math.min(
    1,
    0.45 + boundedScore(matchedTopicKeywords.length, 4) * 0.35 + boundedScore(marketTermHits, 4) * 0.2,
  );
  const macroSpecificityScore = Math.min(
    1,
    boundedScore(macroTermHits, 4) * 0.65 + boundedScore(numberSignalHits, 3) * 0.35,
  );
  const technicalSpecificityScore = Math.min(
    1,
    boundedScore(technicalTermHits, 4) * 0.7 + boundedScore(numberSignalHits, 4) * 0.3,
  );
  const crossAssetContextScore = boundedScore(crossAssetTermHits, 4);
  const imagePresenceScore = imageUrl ? 1 : 0;
  const watchlistRelevanceScore = boundedScore(identifiedSymbols.length, 2);

  const weights = RAW_NEWS_CONTRACT.benchmarkWeights;
  const benchmarkFitScore =
    sourceQualityScore * weights.source_quality +
    marketRelevanceScore * weights.market_relevance +
    macroSpecificityScore * weights.macro_specificity +
    technicalSpecificityScore * weights.technical_specificity +
    crossAssetContextScore * weights.cross_asset_context +
    imagePresenceScore * weights.image_presence +
    watchlistRelevanceScore * weights.watchlist_relevance;

  const reasonFlags = [`topic:${topic.code}`, `family:${topic.family}`, `provider:${provider}`];
  if (publisherDomain && RAW_NEWS_CONTRACT.premierDomains.has(publisherDomain)) {
    reasonFlags.push("premier_source");
  } else if (publisherDomain && RAW_NEWS_CONTRACT.trustedDomains.has(publisherDomain)) {
    reasonFlags.push("trusted_source");
  }
  if (matchedTopicKeywords.length > 0) {
    reasonFlags.push("topic_keyword_match");
  }
  if (marketTermHits > 0) {
    reasonFlags.push("market_context");
  }
  if (macroTermHits > 0) {
    reasonFlags.push("macro_context");
  }
  if (numberSignalHits > 0) {
    reasonFlags.push("exact_numbers");
  }
  if (technicalTermHits > 0) {
    reasonFlags.push("technical_levels");
  }
  if (crossAssetTermHits > 0) {
    reasonFlags.push("cross_asset_context");
  }
  if (imageUrl) {
    reasonFlags.push("image_present");
  }
  if (identifiedSymbols.length > 0) {
    reasonFlags.push("watchlist_symbol_match");
  }

  const reasoningConfidence = Math.min(
    1,
    0.25 + boundedScore(reasonFlags.length, 8) * 0.45 + benchmarkFitScore * 0.3,
  );

  return {
    identifiedSymbols,
    reasonFlags: [...new Set(reasonFlags)],
    sourceQualityScore: Number(sourceQualityScore.toFixed(4)),
    marketRelevanceScore: Number(marketRelevanceScore.toFixed(4)),
    macroSpecificityScore: Number(macroSpecificityScore.toFixed(4)),
    technicalSpecificityScore: Number(technicalSpecificityScore.toFixed(4)),
    crossAssetContextScore: Number(crossAssetContextScore.toFixed(4)),
    imagePresenceScore: Number(imagePresenceScore.toFixed(4)),
    watchlistRelevanceScore: Number(watchlistRelevanceScore.toFixed(4)),
    reasoningConfidence: Number(reasoningConfidence.toFixed(4)),
    benchmarkFitScore: Number(benchmarkFitScore.toFixed(4)),
    evidence: {
      matchedTopicKeywords,
      marketTermHits,
      macroTermHits,
      technicalTermHits,
      crossAssetTermHits,
      numberSignalHits,
      imagePresent: Boolean(imageUrl),
    },
  };
}
