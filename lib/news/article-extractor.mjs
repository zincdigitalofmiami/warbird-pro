import { Readability } from "@mozilla/readability";
import { JSDOM } from "jsdom";

const USER_AGENT =
  "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36";

function normalizeText(value) {
  if (!value) {
    return "";
  }
  return value.replace(/\s+/g, " ").trim();
}

function extractMetaContent(document, selectors) {
  for (const selector of selectors) {
    const element = document.querySelector(selector);
    const content = normalizeText(element?.getAttribute("content") || element?.getAttribute("href") || "");
    if (content) {
      return content;
    }
  }
  return null;
}

function extractParagraphText(contentHtml) {
  const contentDom = new JSDOM(contentHtml || "<body></body>");
  const paragraphs = Array.from(contentDom.window.document.querySelectorAll("p"));
  const parts = paragraphs
    .map((paragraph) => normalizeText(paragraph.textContent || ""))
    .filter(Boolean);
  if (parts.length > 0) {
    return parts.join("\n\n");
  }
  return normalizeText(contentDom.window.document.body?.textContent || "");
}

function resolveCanonicalUrl(document, finalUrl) {
  return (
    extractMetaContent(document, [
      'link[rel="canonical"]',
      'meta[property="og:url"]',
      'meta[name="twitter:url"]',
    ]) || finalUrl
  );
}

function buildFailedResult(requestUrl, finalUrl, message) {
  return {
    requestUrl,
    finalUrl,
    canonicalUrl: finalUrl,
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
  };
}

export async function extractArticleFromUrl(requestUrl, options = {}) {
  const timeoutMs = options.timeoutMs ?? 20000;
  const response = await fetch(requestUrl, {
    headers: {
      "User-Agent": USER_AGENT,
      "Accept-Language": "en-US,en;q=0.9",
    },
    redirect: "follow",
    signal: AbortSignal.timeout(timeoutMs),
  });

  if (!response.ok) {
    return buildFailedResult(requestUrl, response.url || requestUrl, `http_${response.status}`);
  }

  const html = await response.text();
  const finalUrl = response.url || requestUrl;
  return extractArticleFromHtml(html, {
    requestUrl,
    finalUrl,
  });
}

export function extractArticleFromHtml(html, context) {
  const requestUrl = context?.requestUrl || context?.finalUrl || "";
  const finalUrl = context?.finalUrl || requestUrl;
  const dom = new JSDOM(html, { url: finalUrl });
  const document = dom.window.document;

  const article = new Readability(document).parse();
  if (!article) {
    return buildFailedResult(requestUrl, finalUrl, "readability_parse_failed");
  }

  const contentText = extractParagraphText(article.content);
  const wordCount = contentText ? contentText.split(/\s+/).filter(Boolean).length : 0;
  const extractionStatus = wordCount >= 120 ? "FULL" : wordCount > 0 ? "PARTIAL" : "FAILED";

  return {
    requestUrl,
    finalUrl,
    canonicalUrl: resolveCanonicalUrl(document, finalUrl),
    title: normalizeText(article.title || ""),
    byline: normalizeText(article.byline || "") || null,
    siteName:
      normalizeText(article.siteName || "") ||
      extractMetaContent(document, ['meta[property="og:site_name"]']) ||
      null,
    excerpt: normalizeText(article.excerpt || "") || null,
    imageUrl: extractMetaContent(document, [
      'meta[property="og:image"]',
      'meta[name="twitter:image"]',
      'meta[property="twitter:image"]',
    ]),
    contentHtml: article.content || null,
    contentText: contentText || null,
    wordCount,
    extractionStatus,
    extractionMethod: "mozilla_readability",
    error: extractionStatus === "FAILED" ? "empty_content" : null,
  };
}
