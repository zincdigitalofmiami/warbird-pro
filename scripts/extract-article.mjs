#!/usr/bin/env node

import { extractArticleFromUrl } from "../lib/news/article-extractor.mjs";

const url = process.argv[2];

if (!url) {
  console.error("Usage: node scripts/extract-article.mjs <url>");
  process.exit(1);
}

try {
  const result = await extractArticleFromUrl(url);
  process.stdout.write(`${JSON.stringify(result)}\n`);
} catch (error) {
  const message = error instanceof Error ? error.message : String(error);
  process.stdout.write(
    `${JSON.stringify({
      requestUrl: url,
      finalUrl: url,
      canonicalUrl: url,
      title: null,
      byline: null,
      siteName: null,
      excerpt: null,
      imageUrl: null,
      contentHtml: null,
      contentText: null,
      wordCount: 0,
      extractionStatus: "FAILED",
      extractionMethod: "mozilla_readability",
      error: message,
    })}\n`,
  );
  process.exit(1);
}
