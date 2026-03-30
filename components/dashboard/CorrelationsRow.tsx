"use client";

interface CorrelationTicker {
  label: string;
  symbolCode: string | null;
  close: number | null;
  prevClose: number | null;
  changePercent: number | null;
}

// Requested correlation tickers mapped to available symbol codes.
// Symbols not in the DB show "—" per zero-mock-data rule.
const TICKERS: { label: string; symbolCode: string | null; sublabel: string }[] = [
  { label: "NQ", symbolCode: "NQ", sublabel: "Risk Appetite" },
  { label: "BANK", symbolCode: null, sublabel: "Financials" },
  { label: "VVIX", symbolCode: null, sublabel: "Vol of Vol" },
  { label: "DXY", symbolCode: "DX", sublabel: "USD" },
  { label: "US10Y", symbolCode: "US10Y", sublabel: "Yield" },
  { label: "SOX", symbolCode: "SOX", sublabel: "Semis" },
];

interface CorrelationsRowProps {
  correlations: Record<string, { close: number; prevClose: number }> | null;
}

export default function CorrelationsRow({ correlations }: CorrelationsRowProps) {
  return (
    <div
      className="flex items-center gap-0 w-full overflow-x-auto"
      style={{
        background: "#131722",
        borderBottom: "1px solid rgba(255,255,255,0.06)",
      }}
    >
      {TICKERS.map((ticker) => {
        const data = ticker.symbolCode
          ? correlations?.[ticker.symbolCode] ?? null
          : null;
        const close = data?.close ?? null;
        const prevClose = data?.prevClose ?? null;
        const changePct =
          close != null && prevClose != null && prevClose !== 0
            ? ((close - prevClose) / prevClose) * 100
            : null;
        const isPositive = changePct != null ? changePct >= 0 : null;

        return (
          <div
            key={ticker.label}
            className="flex-1 min-w-[120px] px-4 py-3 flex flex-col gap-0.5"
            style={{
              borderRight: "1px solid rgba(255,255,255,0.04)",
            }}
          >
            <div className="flex items-center gap-2">
              <span className="text-[11px] font-semibold text-white/80 tracking-wide">
                {ticker.label}
              </span>
              <span className="text-[9px] text-white/25 uppercase tracking-wider">
                {ticker.sublabel}
              </span>
            </div>
            <div className="flex items-baseline gap-2">
              <span className="text-sm font-medium text-white/70 tabular-nums">
                {close != null ? formatPrice(close, ticker.symbolCode) : "—"}
              </span>
              {changePct != null ? (
                <span
                  className="text-[10px] font-medium tabular-nums"
                  style={{
                    color: isPositive ? "#26C6DA" : "#FF0000",
                  }}
                >
                  {isPositive ? "+" : ""}
                  {changePct.toFixed(2)}%
                </span>
              ) : (
                <span className="text-[10px] text-white/15">—</span>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}

function formatPrice(price: number, symbolCode: string | null): string {
  if (symbolCode === "US10Y") return price.toFixed(3);
  if (symbolCode === "DX") return price.toFixed(3);
  return price.toFixed(2);
}
