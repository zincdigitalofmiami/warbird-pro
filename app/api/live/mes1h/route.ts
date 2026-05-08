import { NextResponse } from "next/server";
import { createAdminClient } from "@/lib/supabase/admin";

interface MesPriceBar {
  symbol: string;
  tradeDate: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

interface Mes1hRow {
  ts: string;
  open: number | string;
  high: number | string;
  low: number | string;
  close: number | string;
  volume: number | string | null;
}

const DEFAULT_LOOKBACK = 5000;
const MAX_LOOKBACK = 20000;
const CACHE_TTL_MS = 55 * 60 * 1000;
const PAGE_SIZE = 1000;

const mes1hCache = new Map<number, { expiresAt: number; data: MesPriceBar[]; asOf: string }>();

function parseLookback(url: URL): number {
  const raw = Number(url.searchParams.get("lookback") ?? DEFAULT_LOOKBACK);
  if (!Number.isFinite(raw)) return DEFAULT_LOOKBACK;
  return Math.max(500, Math.min(MAX_LOOKBACK, Math.floor(raw)));
}

function isValidMesBar(bar: MesPriceBar): boolean {
  if (
    !Number.isFinite(bar.open) ||
    !Number.isFinite(bar.high) ||
    !Number.isFinite(bar.low) ||
    !Number.isFinite(bar.close) ||
    !Number.isFinite(bar.volume)
  ) {
    return false;
  }

  if (bar.high < bar.low) return false;
  if (bar.high < Math.max(bar.open, bar.close)) return false;
  if (bar.low > Math.min(bar.open, bar.close)) return false;
  if (Number.isNaN(new Date(bar.tradeDate).getTime())) return false;

  return true;
}

async function fetchMes1hFromSupabase(lookback: number): Promise<MesPriceBar[]> {
  const supabase = createAdminClient();
  const rows: Mes1hRow[] = [];
  let from = 0;

  while (rows.length < lookback) {
    const batchSize = Math.min(PAGE_SIZE, lookback - rows.length);
    const to = from + batchSize - 1;

    const { data, error } = await supabase
      .from("mes_1h")
      .select("ts, open, high, low, close, volume")
      .order("ts", { ascending: false })
      .range(from, to);

    if (error) {
      throw new Error(`mes_1h query failed: ${error.message}`);
    }

    if (!data || data.length === 0) {
      break;
    }

    rows.push(...(data as Mes1hRow[]));
    from += data.length;

    if (data.length < batchSize) {
      break;
    }
  }

  return rows
    .map((row) => ({
      symbol: "MES",
      tradeDate: String(row.ts),
      open: Number(row.open),
      high: Number(row.high),
      low: Number(row.low),
      close: Number(row.close),
      volume: Number(row.volume ?? 0),
    }))
    .filter(isValidMesBar)
    .sort((a, b) => new Date(a.tradeDate).getTime() - new Date(b.tradeDate).getTime());
}

export async function GET(request: Request) {
  try {
    const url = new URL(request.url);
    const lookback = parseLookback(url);
    const cached = mes1hCache.get(lookback) ?? null;
    if (cached && cached.expiresAt > Date.now()) {
      return NextResponse.json({
        ok: true,
        data: cached.data,
        asOf: cached.asOf,
        source: "supabase mes_1h",
        timeframe: "1h",
        requestedLookback: lookback,
        returnedRows: cached.data.length,
        cache: "hit",
      });
    }

    const bars = await fetchMes1hFromSupabase(lookback);
    if (bars.length === 0 && cached) {
      return NextResponse.json({
        ok: true,
        data: cached.data,
        asOf: cached.asOf,
        source: "supabase mes_1h",
        timeframe: "1h",
        requestedLookback: lookback,
        returnedRows: cached.data.length,
        cache: "stale",
      });
    }

    const asOf = new Date().toISOString();
    mes1hCache.set(lookback, {
      expiresAt: Date.now() + CACHE_TTL_MS,
      data: bars,
      asOf,
    });

    return NextResponse.json({
      ok: true,
      data: bars,
      asOf,
      source: "supabase mes_1h",
      timeframe: "1h",
      requestedLookback: lookback,
      returnedRows: bars.length,
      cache: "miss",
    });
  } catch (err) {
    const url = new URL(request.url);
    const lookback = parseLookback(url);
    const cached = mes1hCache.get(lookback) ?? null;
    if (cached) {
      return NextResponse.json({
        ok: true,
        data: cached.data,
        asOf: cached.asOf,
        source: "supabase mes_1h",
        timeframe: "1h",
        requestedLookback: lookback,
        returnedRows: cached.data.length,
        cache: "stale",
      });
    }
    return NextResponse.json(
      {
        ok: false,
        data: [],
        asOf: new Date().toISOString(),
        error: String(err),
      },
      { status: 500 },
    );
  }
}
