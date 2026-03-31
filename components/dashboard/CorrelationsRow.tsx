"use client";

// Symbol bar: HG, NQ, 6E, CL — all Databento hourly, green/red = MES-aligned move
// mesPolarity: "positive" = symbol up → MES up (green bg)
//              "inverse"  = symbol up → MES down (red bg)
const TICKERS: {
  label: string;
  symbolCode: string;
  sublabel: string;
  mesPolarity: "positive" | "inverse";
}[] = [
  { label: "HG",  symbolCode: "HG",  sublabel: "Copper",  mesPolarity: "positive" },
  { label: "NQ",  symbolCode: "NQ",  sublabel: "Nasdaq",  mesPolarity: "positive" },
  { label: "EUR", symbolCode: "6E",  sublabel: "EUR/USD", mesPolarity: "positive" },
  { label: "CL",  symbolCode: "CL",  sublabel: "Crude",   mesPolarity: "positive" },
];

interface CorrelationsRowProps {
  correlations: Record<string, { close: number; prevClose: number }> | null;
}

export default function CorrelationsRow({ correlations }: CorrelationsRowProps) {
  return (
    <div
      className="flex items-center gap-0 w-full overflow-x-auto flex-shrink-0"
      style={{
        borderBottom: "1px solid rgba(255,255,255,0.06)",
      }}
    >
      {TICKERS.map((ticker) => {
        const data = correlations?.[ticker.symbolCode] ?? null;
        const close = data?.close ?? null;
        const prevClose = data?.prevClose ?? null;
        const changePct =
          close != null && prevClose != null && prevClose !== 0
            ? ((close - prevClose) / prevClose) * 100
            : null;

        // Green bg = this hour's move is aligned with MES going up
        // Red bg   = this hour's move is aligned with MES going down
        // Null     = no data → transparent (zero-mock rule)
        const isBullishForMES =
          changePct == null
            ? null
            : ticker.mesPolarity === "positive"
              ? changePct > 0
              : changePct < 0;

        const bgColor =
          isBullishForMES === true
            ? "rgba(38, 166, 91, 0.15)"
            : isBullishForMES === false
              ? "rgba(242, 54, 69, 0.15)"
              : "transparent";

        const changeColor =
          changePct == null
            ? "rgba(255,255,255,0.15)"
            : changePct >= 0
              ? "#26C6DA"
              : "#F23645";

        return (
          <div
            key={ticker.label}
            className="flex-1 min-w-[110px] px-3 py-1.5 flex flex-col gap-0"
            style={{
              background: bgColor,
              borderRight: "1px solid rgba(255,255,255,0.04)",
              transition: "background 0.3s ease",
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
                  style={{ color: changeColor }}
                >
                  {changePct >= 0 ? "+" : ""}
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

function formatPrice(price: number, symbolCode: string): string {
  if (symbolCode === "6E") return price.toFixed(5);
  if (symbolCode === "HG") return price.toFixed(4);
  return price.toFixed(2);
}
