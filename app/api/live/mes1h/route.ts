import { NextResponse } from "next/server";
import { fetchOhlcv } from "@/lib/ingestion/databento";

interface MesPriceBar {
  symbol: string;
  tradeDate: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

const DEFAULT_LOOKBACK = 5000;
const MAX_LOOKBACK = 20000;
const MIN_VALID_MES_PRICE = 500;
const CACHE_TTL_MS = 55 * 60 * 1000;

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

  if (
    bar.open < MIN_VALID_MES_PRICE ||
    bar.high < MIN_VALID_MES_PRICE ||
    bar.low < MIN_VALID_MES_PRICE ||
    bar.close < MIN_VALID_MES_PRICE
  ) {
    return false;
  }

  if (bar.high < bar.low) return false;
  if (bar.high < Math.max(bar.open, bar.close)) return false;
  if (bar.low > Math.min(bar.open, bar.close)) return false;

  return true;
}

export async function GET(request: Request) {
  try {
    const url = new URL(request.url);
    const lookback = parseLookback(url);
    const cached = mes1hCache.get(lookback);
    if (cached && cached.expiresAt > Date.now()) {
      return NextResponse.json({
        ok: true,
        data: cached.data,
        asOf: cached.asOf,
        source: "Databento GLBX.MDP3 ohlcv-1h (MES.n.0)",
        timeframe: "1h",
        requestedLookback: lookback,
        returnedRows: cached.data.length,
        cache: "hit",
      });
    }

    const end = new Date();
    const start = new Date(end.getTime() - lookback * 60 * 60 * 1000);

    const rawBars = await fetchOhlcv({
      dataset: "GLBX.MDP3",
      symbol: "MES.n.0",
      stypeIn: "continuous",
      schema: "ohlcv-1h",
      start: start.toISOString(),
      end: end.toISOString(),
    });

    const bars = rawBars
      .map((bar) => ({
        symbol: "MES",
        tradeDate: new Date(bar.time * 1000).toISOString(),
        open: Number(bar.open),
        high: Number(bar.high),
        low: Number(bar.low),
        close: Number(bar.close),
        volume: Number(bar.volume),
      }))
      .filter(isValidMesBar);

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
      source: "Databento GLBX.MDP3 ohlcv-1h (MES.n.0)",
      timeframe: "1h",
      requestedLookback: lookback,
      returnedRows: bars.length,
      cache: "miss",
    });
  } catch (err) {
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
