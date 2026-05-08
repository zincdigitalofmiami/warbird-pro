import { NextResponse } from "next/server";
import { createClient } from "@/lib/supabase/server";

interface MesPriceBar {
  symbol: string;
  tradeDate: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

type PriceRow = {
  ts: string;
  open: number | string;
  high: number | string;
  low: number | string;
  close: number | string;
  volume: number | string | null;
};

function dayKey(tsIso: string): string {
  return tsIso.slice(0, 10);
}

function buildLatestDailyFromHourly(rows: PriceRow[]): MesPriceBar | null {
  if (rows.length === 0) return null;

  const latestDay = dayKey(rows[0].ts);
  const sameDayRows = rows.filter((row) => dayKey(row.ts) === latestDay);
  if (sameDayRows.length === 0) return null;

  sameDayRows.sort((a, b) => new Date(a.ts).getTime() - new Date(b.ts).getTime());

  const parsedRows = sameDayRows
    .map((row) => ({
      open: Number(row.open),
      high: Number(row.high),
      low: Number(row.low),
      close: Number(row.close),
      volume: Number(row.volume ?? 0),
    }))
    .filter(
      (row) =>
        Number.isFinite(row.open) &&
        Number.isFinite(row.high) &&
        Number.isFinite(row.low) &&
        Number.isFinite(row.close),
    );

  if (parsedRows.length === 0) return null;

  const open = parsedRows[0].open;
  const close = parsedRows[parsedRows.length - 1].close;
  let high = parsedRows[0].high;
  let low = parsedRows[0].low;
  let volume = 0;

  for (const row of parsedRows) {
    if (row.high > high) high = row.high;
    if (row.low < low) low = row.low;
    if (Number.isFinite(row.volume)) volume += row.volume;
  }

  return {
    symbol: "MES",
    tradeDate: `${latestDay}T00:00:00+00:00`,
    open,
    high,
    low,
    close,
    volume,
  };
}

export async function GET() {
  try {
    const supabase = await createClient();

    const { data: rows, error } = await supabase
      .from("mes_1d")
      .select("ts, open, high, low, close, volume")
      .order("ts", { ascending: true });

    if (error) {
      return NextResponse.json(
        { ok: false, data: [], asOf: new Date().toISOString(), error: error.message },
        { status: 500 },
      );
    }

    const bars: MesPriceBar[] = (rows ?? []).map((row) => ({
      symbol: "MES",
      tradeDate: String(row.ts),
      open: Number(row.open),
      high: Number(row.high),
      low: Number(row.low),
      close: Number(row.close),
      volume: Number(row.volume),
    }));

    const { data: hourlyRows } = await supabase
      .from("mes_1h")
      .select("ts, open, high, low, close, volume")
      .order("ts", { ascending: false })
      .limit(96);

    const latestDailyFromHourly = buildLatestDailyFromHourly((hourlyRows ?? []) as PriceRow[]);

    if (latestDailyFromHourly) {
      const lastBar = bars[bars.length - 1] ?? null;
      const lastDay = lastBar ? dayKey(lastBar.tradeDate) : null;
      const computedDay = dayKey(latestDailyFromHourly.tradeDate);

      if (!lastDay || computedDay > lastDay) {
        bars.push(latestDailyFromHourly);
      } else if (computedDay === lastDay) {
        bars[bars.length - 1] = latestDailyFromHourly;
      }
    }

    return NextResponse.json({
      ok: true,
      data: bars,
      asOf: new Date().toISOString(),
      source: latestDailyFromHourly
        ? "mes_1d + mes_1h (latest daily rollup)"
        : "mes_1d",
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
