import { NextResponse } from "next/server";
import { createAdminClient } from "@/lib/supabase/admin";

export const maxDuration = 60;

const SEGMENTS = {
  fed_policy: [
    `"Federal Reserve" interest rate decision`,
    `Jerome Powell speech testimony`,
    `FOMC minutes statement`,
  ],
  inflation_economy: [
    `CPI inflation report surprise`,
    `nonfarm payrolls jobs report`,
    `GDP recession contraction`,
  ],
  geopolitical_war: [
    `Ukraine Russia war escalation`,
    `Middle East oil supply military`,
    `trade war tariffs sanctions`,
  ],
  policy_trump: [
    `Trump tariff executive order markets`,
    `Treasury deficit debt ceiling`,
    `DOGE federal spending cuts`,
  ],
  market_structure: [
    `S&P 500 crash selloff correction`,
    `VIX volatility spike fear`,
    `bank failure contagion systemic`,
  ],
  earnings_tech: [
    `NVIDIA Apple Microsoft Meta earnings`,
    `semiconductor AI chip demand`,
  ],
} as const;

type Segment = keyof typeof SEGMENTS;

function googleNewsUrl(query: string): string {
  return `https://news.google.com/rss/search?q=${encodeURIComponent(query)}&hl=en-US&gl=US&ceid=US:en`;
}

async function fetchSegmentArticles(segment: Segment): Promise<Array<{
  ts: string;
  headline: string;
  source: string;
  sentiment: string;
  segment: string;
}>> {
  const keywords = SEGMENTS[segment];
  const articles: Array<{ts: string; headline: string; source: string; sentiment: string; segment: string}> = [];

  for (const keyword of keywords) {
    const rssUrl = googleNewsUrl(keyword);
    try {
      const resp = await fetch(rssUrl, {
        headers: { "User-Agent": "Mozilla/5.0" },
        signal: AbortSignal.timeout(10000),
      });
      if (!resp.ok) continue;
      const xml = await resp.text();

      const items = xml.match(/<item>[\s\S]*?<\/item>/g) ?? [];
      for (const item of items.slice(0, 5)) {
        const title = item.match(/<title><!\[CDATA\[(.*?)\]\]><\/title>/)?.[1]
          ?? item.match(/<title>(.*?)<\/title>/)?.[1] ?? "";
        const pubDate = item.match(/<pubDate>(.*?)<\/pubDate>/)?.[1] ?? "";
        const source = item.match(/<source[^>]*>(.*?)<\/source>/)?.[1] ?? "";

        if (!title || !pubDate) continue;

        const ts = new Date(pubDate).toISOString();
        const lower = title.toLowerCase();
        const bullish = ["surge", "gain", "rally", "rise", "recovery", "beat", "strong"].filter(w => lower.includes(w)).length;
        const bearish = ["crash", "fall", "plunge", "fear", "recession", "weak", "miss", "collapse"].filter(w => lower.includes(w)).length;
        const sentiment = bullish > bearish ? "bullish" : bearish > bullish ? "bearish" : "neutral";

        articles.push({
          ts,
          headline: title.slice(0, 500),
          source: source.slice(0, 200) || "Google News",
          sentiment,
          segment,
        });
      }
    } catch {
      // Skip failed keyword fetch
    }
  }

  return articles;
}

export async function GET(request: Request) {
  const cronSecret = process.env.CRON_SECRET;
  if (cronSecret) {
    const auth = request.headers.get("authorization");
    if (auth !== `Bearer ${cronSecret}`) {
      return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
    }
  }

  const startTime = Date.now();
  const supabase = createAdminClient();

  try {
    const segments = Object.keys(SEGMENTS) as Segment[];
    const allArticles = (
      await Promise.all(segments.map(fetchSegmentArticles))
    ).flat();

    let rowsWritten = 0;
    for (const article of allArticles) {
      // Insert into econ_news_1d (matches schema: ts, headline, source, sentiment)
      const { error } = await supabase.from("econ_news_1d").insert({
        ts: article.ts,
        headline: article.headline,
        source: article.source,
        sentiment: article.sentiment,
      });
      if (!error) rowsWritten++;
    }

    // Aggregate sentiment by segment into news_signals
    const sentimentBySegment = new Map<string, { bullish: number; bearish: number; total: number }>();
    for (const article of allArticles) {
      const stats = sentimentBySegment.get(article.segment) ?? { bullish: 0, bearish: 0, total: 0 };
      stats.total++;
      if (article.sentiment === "bullish") stats.bullish++;
      if (article.sentiment === "bearish") stats.bearish++;
      sentimentBySegment.set(article.segment, stats);
    }

    for (const [segment, stats] of sentimentBySegment.entries()) {
      const direction = stats.bullish > stats.bearish ? "LONG" : stats.bearish > stats.bullish ? "SHORT" : null;
      const confidence = stats.total > 0 ? Math.abs(stats.bullish - stats.bearish) / stats.total : null;
      await supabase.from("news_signals").insert({
        ts: new Date().toISOString(),
        signal_type: segment,
        direction,
        confidence,
        source_headline: `${stats.total} articles scraped`,
      });
    }

    await supabase.from("job_log").insert({
      job_name: "google-news",
      status: "SUCCESS",
      rows_affected: rowsWritten,
      duration_ms: Date.now() - startTime,
    });

    return NextResponse.json({ success: true, articles: allArticles.length, rows_written: rowsWritten, duration_ms: Date.now() - startTime });
  } catch (error) {
    const message = error instanceof Error ? error.message : "Internal error";
    try {
      await supabase.from("job_log").insert({
        job_name: "google-news",
        status: "FAILED",
        error_message: message,
        duration_ms: Date.now() - startTime,
      });
    } catch {
      // ignore
    }
    return NextResponse.json({ error: message }, { status: 500 });
  }
}
