import { runNewsfilterRawIngest } from "@/lib/news/provider-ingest";

export const maxDuration = 60;

export async function GET(request: Request) {
  return runNewsfilterRawIngest(request);
}

export async function POST(request: Request) {
  return runNewsfilterRawIngest(request);
}
