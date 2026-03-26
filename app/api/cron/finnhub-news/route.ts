import { runFinnhubRawIngest } from "@/lib/news/provider-ingest";

export const maxDuration = 60;

export async function GET(request: Request) {
  return runFinnhubRawIngest(request);
}

export async function POST(request: Request) {
  return runFinnhubRawIngest(request);
}
