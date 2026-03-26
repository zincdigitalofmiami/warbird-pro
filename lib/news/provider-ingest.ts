import { NextResponse } from "next/server";
import { createAdminClient } from "@/lib/supabase/admin";
import { validateCronRequest } from "@/lib/cron-auth";
import { extractArticleFromUrl } from "@/lib/news/article-extractor.mjs";
import {
  RAW_NEWS_CONTRACT,
  RAW_NEWS_TOPIC_MAP,
  buildArticleKey,
  buildDedupeKey,
  extractDomain,
  isJunk,
  matchedKeywords,
  normalizeText,
  normalizeTitleForDedupe,
  publishedMinuteIso,
  scoreArticle,
  stripHtmlTags,
  type ArticleScore,
  type TopicSpec,
} from "@/lib/news/raw-news-contract";

type JobLogStatus = "SUCCESS" | "PARTIAL" | "FAILED" | "SKIPPED";

type SegmentLinkRow = {
  dedupeKey: string;
  segment: string;
  queryText: string;
  matchedKeywords: string[];
  matchedSymbols: string[];
};

type AssessmentInsertRow = {
  provider: string;
  dedupe_key: string;
  article_key: string;
  topic_code: string;
  identified_symbols: string[];
  reason_flags: string[];
  source_quality_score: number;
  market_relevance_score: number;
  macro_specificity_score: number;
  technical_specificity_score: number;
  cross_asset_context_score: number;
  image_presence_score: number;
  watchlist_relevance_score: number;
  reasoning_confidence: number;
  benchmark_fit_score: number;
  evidence: Record<string, unknown>;
  scoring_version: string;
  scored_at: string;
};

const USER_AGENT =
  "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36";
const DEFAULT_NEWSFILTER_LOOKBACK_DAYS = 3;
const DEFAULT_NEWSFILTER_SIZE = 60;
const DEFAULT_FINNHUB_LIMIT_PER_CATEGORY = 60;

function chunked<T>(values: T[], size: number): T[][] {
  const chunks: T[][] = [];
  for (let index = 0; index < values.length; index += size) {
    chunks.push(values.slice(index, index + size));
  }
  return chunks;
}

async function writeJobLog(
  supabase: ReturnType<typeof createAdminClient>,
  params: {
    job_name: string;
    status: JobLogStatus;
    rows_affected: number;
    duration_ms: number;
    error_message?: string | null;
  },
) {
  const { error } = await supabase.from("job_log").insert({
    ...params,
    error_message: params.error_message ?? null,
  });

  if (error) {
    throw new Error(`job_log insert failed: ${error.message}`);
  }
}

function providerApiKey(request: Request, envVarName: string): string | null {
  const headerKey = normalizeText(request.headers.get("x-provider-api-key"));
  if (headerKey) {
    return headerKey;
  }

  const envKey = normalizeText(process.env[envVarName]);
  return envKey || null;
}

function parsePositiveInt(
  url: URL,
  key: string,
  defaultValue: number,
  maxValue: number,
): number {
  const rawValue = normalizeText(url.searchParams.get(key));
  if (!rawValue) {
    return defaultValue;
  }

  const parsed = Number.parseInt(rawValue, 10);
  if (!Number.isFinite(parsed) || parsed <= 0) {
    return defaultValue;
  }

  return Math.min(parsed, maxValue);
}

function parseTopicCodes(url: URL): {
  topicCodes: string[];
  invalidTopicCodes: string[];
} {
  const rawTopics = normalizeText(url.searchParams.get("topics"));
  if (!rawTopics) {
    return {
      topicCodes: [...RAW_NEWS_TOPIC_MAP.keys()],
      invalidTopicCodes: [],
    };
  }

  const valid: string[] = [];
  const invalid: string[] = [];

  for (const value of rawTopics.split(",").map((item) => normalizeText(item))) {
    if (!value) {
      continue;
    }
    if (RAW_NEWS_TOPIC_MAP.has(value)) {
      valid.push(value);
    } else {
      invalid.push(value);
    }
  }

  return {
    topicCodes: [...new Set(valid)],
    invalidTopicCodes: [...new Set(invalid)],
  };
}

function mapAssessmentRow(params: {
  provider: string;
  dedupeKey: string;
  articleKey: string;
  topicCode: string;
  score: ArticleScore;
}): AssessmentInsertRow {
  const { provider, dedupeKey, articleKey, topicCode, score } = params;
  return {
    provider,
    dedupe_key: dedupeKey,
    article_key: articleKey,
    topic_code: topicCode,
    identified_symbols: score.identifiedSymbols,
    reason_flags: score.reasonFlags,
    source_quality_score: score.sourceQualityScore,
    market_relevance_score: score.marketRelevanceScore,
    macro_specificity_score: score.macroSpecificityScore,
    technical_specificity_score: score.technicalSpecificityScore,
    cross_asset_context_score: score.crossAssetContextScore,
    image_presence_score: score.imagePresenceScore,
    watchlist_relevance_score: score.watchlistRelevanceScore,
    reasoning_confidence: score.reasoningConfidence,
    benchmark_fit_score: score.benchmarkFitScore,
    evidence: score.evidence,
    scoring_version: RAW_NEWS_CONTRACT.scoringVersion,
    scored_at: new Date().toISOString(),
  };
}

async function upsertArticles(
  supabase: ReturnType<typeof createAdminClient>,
  table: string,
  rows: Array<Record<string, unknown>>,
): Promise<Map<string, number>> {
  const articleIdByDedupe = new Map<string, number>();
  if (rows.length === 0) {
    return articleIdByDedupe;
  }

  const { error: upsertError } = await supabase.from(table).upsert(rows, { onConflict: "dedupe_key" });
  if (upsertError) {
    throw new Error(`${table} upsert failed: ${upsertError.message}`);
  }

  for (const dedupeChunk of chunked(rows.map((row) => String(row.dedupe_key)), 200)) {
    const { data, error } = await supabase.from(table).select("id, dedupe_key").in("dedupe_key", dedupeChunk);
    if (error) {
      throw new Error(`${table} id lookup failed: ${error.message}`);
    }

    for (const row of data ?? []) {
      articleIdByDedupe.set(String(row.dedupe_key), Number(row.id));
    }
  }

  return articleIdByDedupe;
}

async function upsertSegmentLinks(
  supabase: ReturnType<typeof createAdminClient>,
  table: string,
  links: SegmentLinkRow[],
  articleIds: Map<string, number>,
): Promise<number> {
  const rows = links
    .map((link) => ({
      article_id: articleIds.get(link.dedupeKey),
      segment: link.segment,
      query_text: link.queryText,
      matched_keywords: link.matchedKeywords,
      matched_symbols: link.matchedSymbols,
      fetched_at: new Date().toISOString(),
    }))
    .filter((row) => row.article_id !== undefined);

  if (rows.length === 0) {
    return 0;
  }

  const { error } = await supabase.from(table).upsert(rows, { onConflict: "article_id,segment" });
  if (error) {
    throw new Error(`${table} upsert failed: ${error.message}`);
  }

  return rows.length;
}

async function upsertAssessments(
  supabase: ReturnType<typeof createAdminClient>,
  rows: AssessmentInsertRow[],
): Promise<number> {
  if (rows.length === 0) {
    return 0;
  }

  const { error } = await supabase
    .from("econ_news_article_assessments")
    .upsert(rows, { onConflict: "provider,dedupe_key,topic_code,scoring_version" });
  if (error) {
    throw new Error(`econ_news_article_assessments upsert failed: ${error.message}`);
  }

  return rows.length;
}

async function fetchJson<T>(url: string, init: RequestInit): Promise<T> {
  const response = await fetch(url, {
    ...init,
    signal: AbortSignal.timeout(30_000),
  });

  if (!response.ok) {
    throw new Error(`http_${response.status}`);
  }

  return (await response.json()) as T;
}

async function fetchText(url: string, init: RequestInit): Promise<string> {
  const response = await fetch(url, {
    ...init,
    signal: AbortSignal.timeout(30_000),
  });

  if (!response.ok) {
    throw new Error(`http_${response.status}`);
  }

  return response.text();
}

function finalizeJobError(error: unknown): string {
  return error instanceof Error ? error.message : "Internal error";
}

function topicFromCode(topicCode: string): TopicSpec {
  const topic = RAW_NEWS_TOPIC_MAP.get(topicCode);
  if (!topic) {
    throw new Error(`unknown_topic:${topicCode}`);
  }
  return topic;
}

export async function runNewsfilterRawIngest(request: Request) {
  const authError = validateCronRequest(request);
  if (authError) {
    return authError;
  }

  const startTime = Date.now();
  const supabase = createAdminClient();
  const url = new URL(request.url);
  const dryRun = url.searchParams.get("dry_run") === "1";
  const lookbackDays = parsePositiveInt(url, "lookback_days", DEFAULT_NEWSFILTER_LOOKBACK_DAYS, 14);
  const size = parsePositiveInt(url, "size", DEFAULT_NEWSFILTER_SIZE, 120);
  const { topicCodes, invalidTopicCodes } = parseTopicCodes(url);
  const apiKey = providerApiKey(request, "NEWSFILTER_API_KEY");

  try {
    if (!apiKey) {
      throw new Error("missing_newsfilter_api_key");
    }
    if (topicCodes.length === 0) {
      throw new Error("no_valid_topics");
    }

    const startDate = new Date(Date.now() - lookbackDays * 24 * 60 * 60 * 1000)
      .toISOString()
      .slice(0, 10);
    const sourceClause = [...RAW_NEWS_CONTRACT.newsfilterSourceAllowlist].sort().join(" OR ");
    const payload = {
      queryString: `publishedAt:[${startDate} TO *] AND source.id:(${sourceClause})`,
      from: 0,
      size,
    };

    const searchResult = await fetchJson<{ articles?: Array<Record<string, unknown>> }>(
      "https://api.newsfilter.io/search",
      {
        method: "POST",
        headers: {
          Authorization: apiKey,
          "Content-Type": "application/json",
          "User-Agent": USER_AGENT,
        },
        body: JSON.stringify(payload),
      },
    );

    const fetchedRows = Array.isArray(searchResult.articles) ? searchResult.articles : [];
    const articleRows = new Map<string, Record<string, unknown>>();
    const segmentLinks = new Map<string, SegmentLinkRow>();
    const assessments = new Map<string, AssessmentInsertRow>();
    let duplicatesDropped = 0;
    let extractionFailures = 0;

    for (const item of fetchedRows) {
      const source = (item.source ?? {}) as Record<string, unknown>;
      const sourceId = normalizeText(String(source.id ?? ""));
      if (!RAW_NEWS_CONTRACT.newsfilterSourceAllowlist.has(sourceId)) {
        continue;
      }

      const title = normalizeText(String(item.title ?? ""));
      const summary = normalizeText(String(item.description ?? "")) || null;
      const sourceUrl = normalizeText(String(item.sourceUrl ?? ""));
      if (!title || !sourceUrl) {
        continue;
      }

      const symbols = Array.isArray(item.symbols)
        ? item.symbols.map((value) => normalizeText(String(value)).toUpperCase()).filter(Boolean)
        : [];
      const matchedSymbols = symbols.filter((symbol) => RAW_NEWS_CONTRACT.watchlistSymbols.includes(symbol));
      if (matchedSymbols.length === 0) {
        continue;
      }

      const publisherDomain = extractDomain(sourceUrl);
      if (publisherDomain && !RAW_NEWS_CONTRACT.trustedDomains.has(publisherDomain)) {
        continue;
      }

      const publishedAt = normalizeText(String(item.publishedAt ?? ""));
      if (!publishedAt) {
        continue;
      }

      const normalizedTitle = normalizeTitleForDedupe(title);
      const publishedMinute = publishedMinuteIso(publishedAt);
      const dedupeKey = buildDedupeKey(normalizedTitle, publisherDomain, publishedMinute);
      if (articleRows.has(dedupeKey)) {
        duplicatesDropped += 1;
        continue;
      }

      const articleId = normalizeText(String(item.id ?? ""));
      if (!articleId) {
        continue;
      }

      const articleHtml = await fetchText(
        `https://api.newsfilter.io/articles/${articleId}.html?token=${encodeURIComponent(apiKey)}`,
        {
          headers: {
            "User-Agent": USER_AGENT,
          },
        },
      );
      const articleBody = stripHtmlTags(articleHtml);
      const bodyWordCount = articleBody.split(/\s+/).filter(Boolean).length;
      const extractionStatus =
        bodyWordCount >= 120 ? "FULL" : bodyWordCount > 0 ? "PARTIAL" : "FAILED";
      if (extractionStatus === "FAILED") {
        extractionFailures += 1;
      }

      const articleKey = buildArticleKey(articleId, sourceUrl, title, publishedAt);
      const imageUrl = normalizeText(String(item.imageUrl ?? item.image ?? "")) || null;

      articleRows.set(dedupeKey, {
        article_key: articleKey,
        provider: "newsfilter",
        newsfilter_id: articleId,
        source_id: sourceId,
        source_name: normalizeText(String(source.name ?? "")) || sourceId,
        url: sourceUrl,
        canonical_url: sourceUrl,
        publisher_domain: publisherDomain,
        title,
        summary,
        article_excerpt: summary,
        article_body: articleBody || null,
        body_word_count: bodyWordCount,
        image_url: imageUrl,
        related_symbols: matchedSymbols,
        published_at: publishedAt,
        published_minute: publishedMinute,
        normalized_title: normalizedTitle,
        dedupe_key: dedupeKey,
        extraction_status: extractionStatus,
        extraction_method: "newsfilter_article_content_api",
        provider_metadata: {
          source_id: sourceId,
          source_name: normalizeText(String(source.name ?? "")) || null,
        },
        extracted_at: new Date().toISOString(),
      });

      let matchedAnyTopic = false;
      for (const topicCode of topicCodes) {
        const topic = topicFromCode(topicCode);
        const matchedTopicKeywords = matchedKeywords(title, `${summary ?? ""} ${articleBody}`, topic.keywords);
        if (matchedTopicKeywords.length === 0) {
          continue;
        }

        matchedAnyTopic = true;
        const score = scoreArticle({
          provider: "newsfilter",
          publisherDomain,
          topic,
          title,
          summary,
          bodyText: articleBody,
          imageUrl,
          explicitSymbols: matchedSymbols,
          matchedTopicKeywords,
        });

        segmentLinks.set(`${dedupeKey}::${topicCode}`, {
          dedupeKey,
          segment: topicCode,
          queryText: "newsfilter:search",
          matchedKeywords: matchedTopicKeywords,
          matchedSymbols: score.identifiedSymbols,
        });

        assessments.set(
          `${dedupeKey}::${topicCode}::${RAW_NEWS_CONTRACT.scoringVersion}`,
          mapAssessmentRow({
            provider: "newsfilter",
            dedupeKey,
            articleKey,
            topicCode,
            score,
          }),
        );
      }

      if (!matchedAnyTopic) {
        articleRows.delete(dedupeKey);
      }
    }

    const errors: string[] = [];
    if (invalidTopicCodes.length > 0) {
      errors.push(`invalid_topics=${invalidTopicCodes.join(",")}`);
    }

    if (dryRun) {
      return NextResponse.json({
        success: true,
        dry_run: true,
        fetched_articles: fetchedRows.length,
        unique_articles: articleRows.size,
        segment_links: segmentLinks.size,
        assessments: assessments.size,
        duplicates_dropped: duplicatesDropped,
        extraction_failures: extractionFailures,
        errors: errors.length > 0 ? errors : undefined,
        duration_ms: Date.now() - startTime,
      });
    }

    if (articleRows.size === 0) {
      await writeJobLog(supabase, {
        job_name: "newsfilter-raw",
        status: "SKIPPED",
        rows_affected: 0,
        duration_ms: Date.now() - startTime,
        error_message: errors.length > 0 ? errors.join(" | ") : "no_articles",
      });
      return NextResponse.json({
        success: true,
        skipped: true,
        reason: "no_articles",
        errors: errors.length > 0 ? errors : undefined,
        duration_ms: Date.now() - startTime,
      });
    }

    const articleIdByDedupe = await upsertArticles(
      supabase,
      "econ_news_newsfilter_articles",
      [...articleRows.values()],
    );
    const linked = await upsertSegmentLinks(
      supabase,
      "econ_news_newsfilter_article_segments",
      [...segmentLinks.values()],
      articleIdByDedupe,
    );
    const assessed = await upsertAssessments(supabase, [...assessments.values()]);

    const finalStatus: JobLogStatus =
      errors.length > 0 || extractionFailures > 0 ? "PARTIAL" : "SUCCESS";
    const rowsAffected = articleIdByDedupe.size + linked + assessed;
    await writeJobLog(supabase, {
      job_name: "newsfilter-raw",
      status: finalStatus,
      rows_affected: rowsAffected,
      duration_ms: Date.now() - startTime,
      error_message:
        errors.length > 0 || extractionFailures > 0
          ? [...errors, `duplicates_dropped=${duplicatesDropped}`, `extraction_failures=${extractionFailures}`].join(" | ")
          : null,
    });

    return NextResponse.json({
      success: true,
      fetched_articles: fetchedRows.length,
      unique_articles: articleIdByDedupe.size,
      segment_links: linked,
      assessments: assessed,
      duplicates_dropped: duplicatesDropped,
      extraction_failures: extractionFailures,
      errors: errors.length > 0 ? errors : undefined,
      duration_ms: Date.now() - startTime,
    });
  } catch (error) {
    const message = finalizeJobError(error);
    try {
      await writeJobLog(supabase, {
        job_name: "newsfilter-raw",
        status: "FAILED",
        rows_affected: 0,
        duration_ms: Date.now() - startTime,
        error_message: message,
      });
    } catch {
      // ignore log failure in error path
    }
    return NextResponse.json({ error: message }, { status: 500 });
  }
}

export async function runFinnhubRawIngest(request: Request) {
  const authError = validateCronRequest(request);
  if (authError) {
    return authError;
  }

  const startTime = Date.now();
  const supabase = createAdminClient();
  const url = new URL(request.url);
  const dryRun = url.searchParams.get("dry_run") === "1";
  const limitPerCategory = parsePositiveInt(url, "limit_per_category", DEFAULT_FINNHUB_LIMIT_PER_CATEGORY, 120);
  const { topicCodes, invalidTopicCodes } = parseTopicCodes(url);
  const apiKey = providerApiKey(request, "FINNHUB_API_KEY");

  try {
    if (!apiKey) {
      throw new Error("missing_finnhub_api_key");
    }
    if (topicCodes.length === 0) {
      throw new Error("no_valid_topics");
    }

    const articleRows = new Map<string, Record<string, unknown>>();
    const segmentLinks = new Map<string, SegmentLinkRow>();
    const assessments = new Map<string, AssessmentInsertRow>();
    let duplicatesDropped = 0;
    let extractionFailures = 0;
    let fetchedRows = 0;

    for (const category of RAW_NEWS_CONTRACT.finnhubCategories) {
      const rows = await fetchJson<Array<Record<string, unknown>>>(
        `https://finnhub.io/api/v1/news?category=${encodeURIComponent(category)}&token=${encodeURIComponent(apiKey)}`,
        {
          headers: {
            "User-Agent": USER_AGENT,
          },
        },
      );
      fetchedRows += rows.length;

      for (const item of rows.slice(0, limitPerCategory)) {
        const title = normalizeText(String(item.headline ?? ""));
        const summary = normalizeText(String(item.summary ?? "")) || null;
        const sourceUrl = normalizeText(String(item.url ?? ""));
        const publisherName = normalizeText(String(item.source ?? "")) || "Finnhub";
        const publisherDomain = extractDomain(sourceUrl);
        const publishedAt = new Date(Number(item.datetime ?? 0) * 1000).toISOString();
        const relatedSymbols = String(item.related ?? "")
          .split(",")
          .map((value) => normalizeText(value).toUpperCase())
          .filter(Boolean);
        const matchedSymbols = relatedSymbols.filter((symbol) =>
          RAW_NEWS_CONTRACT.watchlistSymbols.includes(symbol),
        );

        if (!title || !sourceUrl || matchedSymbols.length === 0) {
          continue;
        }
        if (!publisherDomain || !RAW_NEWS_CONTRACT.trustedDomains.has(publisherDomain)) {
          continue;
        }
        if (isJunk(title, summary ?? "", publisherDomain)) {
          continue;
        }

        const normalizedTitle = normalizeTitleForDedupe(title);
        const publishedMinute = publishedMinuteIso(publishedAt);
        const dedupeKey = buildDedupeKey(normalizedTitle, publisherDomain, publishedMinute);
        if (articleRows.has(dedupeKey)) {
          duplicatesDropped += 1;
          continue;
        }

        const extraction = await extractArticleFromUrl(sourceUrl);
        if (extraction.extractionStatus === "FAILED") {
          extractionFailures += 1;
        }

        const finnhubId = Number(item.id ?? 0);
        if (!Number.isFinite(finnhubId) || finnhubId <= 0) {
          continue;
        }

        const articleKey = buildArticleKey(String(finnhubId), sourceUrl, title, publishedAt);
        articleRows.set(dedupeKey, {
          article_key: articleKey,
          provider: "finnhub",
          finnhub_id: finnhubId,
          source_category: category,
          url: sourceUrl,
          canonical_url: extraction.canonicalUrl,
          publisher_name: publisherName,
          publisher_domain: publisherDomain,
          title,
          summary,
          article_excerpt: extraction.excerpt,
          article_body: extraction.contentText,
          body_word_count: Number(extraction.wordCount ?? 0),
          image_url: normalizeText(String(item.image ?? "")) || extraction.imageUrl,
          related_symbols: matchedSymbols,
          published_at: publishedAt,
          published_minute: publishedMinute,
          normalized_title: normalizedTitle,
          dedupe_key: dedupeKey,
          extraction_status: extraction.extractionStatus ?? "FAILED",
          extraction_method: extraction.extractionMethod,
          provider_metadata: {
            request_url: extraction.requestUrl,
            final_url: extraction.finalUrl,
            site_name: extraction.siteName,
            byline: extraction.byline,
            category,
          },
          extracted_at: new Date().toISOString(),
        });

        let matchedAnyTopic = false;
        for (const topicCode of topicCodes) {
          const topic = topicFromCode(topicCode);
          const matchedTopicKeywords = matchedKeywords(
            title,
            `${summary ?? ""} ${extraction.contentText ?? ""}`,
            topic.keywords,
          );
          if (matchedTopicKeywords.length === 0) {
            continue;
          }

          matchedAnyTopic = true;
          const score = scoreArticle({
            provider: "finnhub",
            publisherDomain,
            topic,
            title,
            summary,
            bodyText: extraction.contentText,
            imageUrl: normalizeText(String(item.image ?? "")) || extraction.imageUrl,
            explicitSymbols: matchedSymbols,
            matchedTopicKeywords,
          });

          segmentLinks.set(`${dedupeKey}::${topicCode}`, {
            dedupeKey,
            segment: topicCode,
            queryText: `finnhub:${category}`,
            matchedKeywords: matchedTopicKeywords,
            matchedSymbols: score.identifiedSymbols,
          });

          assessments.set(
            `${dedupeKey}::${topicCode}::${RAW_NEWS_CONTRACT.scoringVersion}`,
            mapAssessmentRow({
              provider: "finnhub",
              dedupeKey,
              articleKey,
              topicCode,
              score,
            }),
          );
        }

        if (!matchedAnyTopic) {
          articleRows.delete(dedupeKey);
        }
      }
    }

    const errors: string[] = [];
    if (invalidTopicCodes.length > 0) {
      errors.push(`invalid_topics=${invalidTopicCodes.join(",")}`);
    }

    if (dryRun) {
      return NextResponse.json({
        success: true,
        dry_run: true,
        fetched_articles: fetchedRows,
        unique_articles: articleRows.size,
        segment_links: segmentLinks.size,
        assessments: assessments.size,
        duplicates_dropped: duplicatesDropped,
        extraction_failures: extractionFailures,
        errors: errors.length > 0 ? errors : undefined,
        duration_ms: Date.now() - startTime,
      });
    }

    if (articleRows.size === 0) {
      await writeJobLog(supabase, {
        job_name: "finnhub-raw",
        status: "SKIPPED",
        rows_affected: 0,
        duration_ms: Date.now() - startTime,
        error_message: errors.length > 0 ? errors.join(" | ") : "no_articles",
      });
      return NextResponse.json({
        success: true,
        skipped: true,
        reason: "no_articles",
        errors: errors.length > 0 ? errors : undefined,
        duration_ms: Date.now() - startTime,
      });
    }

    const articleIdByDedupe = await upsertArticles(
      supabase,
      "econ_news_finnhub_articles",
      [...articleRows.values()],
    );
    const linked = await upsertSegmentLinks(
      supabase,
      "econ_news_finnhub_article_segments",
      [...segmentLinks.values()],
      articleIdByDedupe,
    );
    const assessed = await upsertAssessments(supabase, [...assessments.values()]);

    const finalStatus: JobLogStatus =
      errors.length > 0 || extractionFailures > 0 ? "PARTIAL" : "SUCCESS";
    const rowsAffected = articleIdByDedupe.size + linked + assessed;
    await writeJobLog(supabase, {
      job_name: "finnhub-raw",
      status: finalStatus,
      rows_affected: rowsAffected,
      duration_ms: Date.now() - startTime,
      error_message:
        errors.length > 0 || extractionFailures > 0
          ? [...errors, `duplicates_dropped=${duplicatesDropped}`, `extraction_failures=${extractionFailures}`].join(" | ")
          : null,
    });

    return NextResponse.json({
      success: true,
      fetched_articles: fetchedRows,
      unique_articles: articleIdByDedupe.size,
      segment_links: linked,
      assessments: assessed,
      duplicates_dropped: duplicatesDropped,
      extraction_failures: extractionFailures,
      errors: errors.length > 0 ? errors : undefined,
      duration_ms: Date.now() - startTime,
    });
  } catch (error) {
    const message = finalizeJobError(error);
    try {
      await writeJobLog(supabase, {
        job_name: "finnhub-raw",
        status: "FAILED",
        rows_affected: 0,
        duration_ms: Date.now() - startTime,
        error_message: message,
      });
    } catch {
      // ignore log failure in error path
    }
    return NextResponse.json({ error: message }, { status: 500 });
  }
}
