// Edge Function: finnhub-news
// Ported from app/api/cron/finnhub-news/route.ts
// All logic lives in _shared/news-provider.ts (runFinnhubRawIngest).
// Auth: x-cron-secret header validated against EDGE_CRON_SECRET env var.

import { runFinnhubRawIngest } from "../_shared/news-provider.ts";

Deno.serve((req: Request) => {
  return runFinnhubRawIngest(req);
});
