"use client";

// Intermarket Full Agreement Panel
// 6 boxes: NQ, RTY, CL, HG, 6E, 6J — all Databento 1h from cross_asset_1h
//
// Polarity:
//   NQ, RTY, CL, HG, 6E: positive (up = bullish for MES)
//   6J: INVERSE (JPY weakness = bullish for MES, so price DOWN = +1)
//
// Atomic state per symbol: +1 (Bull), 0 (Neutral), -1 (Bear)
//   Derived from hourly % change: > +0.01% = +1, < -0.01% = -1, else 0
//   6J polarity is flipped after computing raw change
//
// Background rule (STRICT CONSENSUS):
//   All six +1 → all boxes green
//   All six -1 → all boxes red
//   Otherwise  → all boxes transparent
//
// Weighted IM Score (Warbird weights):
//   NQ: 25%, RTY: 13.33%, CL: 13.33%, HG: 13.33%, 6E: 7.5%, 6J: 7.5%
//   Range: -0.80 to +0.80

interface TickerConfig {
  label: string;
  symbolCode: string;
  sublabel: string;
  polarity: "positive" | "inverse";
  weight: number;
}

const TICKERS: TickerConfig[] = [
  { label: "NQ",  symbolCode: "NQ",  sublabel: "Nasdaq",   polarity: "positive", weight: 0.25 },
  { label: "RTY", symbolCode: "RTY", sublabel: "Russell",  polarity: "positive", weight: 0.1333 },
  { label: "CL",  symbolCode: "CL",  sublabel: "Crude",    polarity: "positive", weight: 0.1333 },
  { label: "HG",  symbolCode: "HG",  sublabel: "Copper",   polarity: "positive", weight: 0.1333 },
  { label: "EUR", symbolCode: "6E",  sublabel: "EUR/USD",  polarity: "positive", weight: 0.075 },
  { label: "JPY", symbolCode: "6J",  sublabel: "JPY/USD",  polarity: "inverse",  weight: 0.075 },
];

// Minimum absolute change to register as directional (avoids noise at flat)
const NEUTRAL_THRESHOLD_PCT = 0.01;

interface CorrelationsRowProps {
  correlations: Record<string, { close: number; prevClose: number }> | null;
}

function computeAtomicState(changePct: number | null, polarity: "positive" | "inverse"): -1 | 0 | 1 {
  if (changePct == null) return 0;
  const rawDirection = changePct > NEUTRAL_THRESHOLD_PCT ? 1 : changePct < -NEUTRAL_THRESHOLD_PCT ? -1 : 0;
  return (polarity === "inverse" ? -rawDirection : rawDirection) as -1 | 0 | 1;
}

function stateLabel(state: -1 | 0 | 1): string {
  if (state === 1) return "▲";
  if (state === -1) return "▼";
  return "—";
}

function stateColor(state: -1 | 0 | 1): string {
  if (state === 1) return "#26a65b";
  if (state === -1) return "#F23645";
  return "rgba(255,255,255,0.20)";
}

export default function CorrelationsRow({ correlations }: CorrelationsRowProps) {
  // Compute per-symbol data
  const tickerData = TICKERS.map((ticker) => {
    const data = correlations?.[ticker.symbolCode] ?? null;
    const close = data?.close ?? null;
    const prevClose = data?.prevClose ?? null;
    const changePct =
      close != null && prevClose != null && prevClose !== 0
        ? ((close - prevClose) / prevClose) * 100
        : null;
    const atomicState = computeAtomicState(changePct, ticker.polarity);
    return { ticker, close, prevClose, changePct, atomicState };
  });

  const states = tickerData.map((d) => d.atomicState);

  // Strict consensus: all must agree for colored background
  const allLongAligned = states.every((v) => v === 1);
  const allShortAligned = states.every((v) => v === -1);
  const globalBg = allLongAligned
    ? "rgba(38, 166, 91, 0.15)"
    : allShortAligned
      ? "rgba(242, 54, 69, 0.15)"
      : "transparent";

  // Weighted IM score: NQ 25%, RTY/CL/HG 13.33%, 6E/6J 7.5%
  const imScore = tickerData.reduce(
    (sum, d) => sum + d.ticker.weight * d.atomicState,
    0,
  );

  return (
    <div
      className="flex flex-col w-full flex-shrink-0"
      style={{ borderBottom: "1px solid rgba(255,255,255,0.06)" }}
    >
      {/* Symbol boxes */}
      <div className="flex items-center gap-0 w-full overflow-x-auto">
        {tickerData.map(({ ticker, close, changePct, atomicState }) => {
          const changeColor =
            changePct == null
              ? "rgba(255,255,255,0.15)"
              : changePct >= 0
                ? "#26C6DA"
                : "#F23645";

          return (
            <div
              key={ticker.label}
              className="flex-1 min-w-[90px] px-3 py-1.5 flex flex-col gap-0"
              style={{
                background: globalBg,
                borderRight: "1px solid rgba(255,255,255,0.04)",
                transition: "background 0.3s ease",
              }}
            >
              <div className="flex items-center gap-1.5">
                <span
                  className="text-[11px] font-bold"
                  style={{ color: stateColor(atomicState) }}
                >
                  {stateLabel(atomicState)}
                </span>
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

        {/* IM Score badge */}
        <div
          className="flex-none min-w-[80px] px-3 py-1.5 flex flex-col items-center justify-center gap-0"
          style={{
            background: globalBg,
            borderLeft: "1px solid rgba(255,255,255,0.08)",
          }}
        >
          <span className="text-[9px] text-white/30 uppercase tracking-wider font-medium">
            IM Score
          </span>
          <span
            className="text-sm font-bold tabular-nums"
            style={{
              color: imScore > 0.3
                ? "#26a65b"
                : imScore < -0.3
                  ? "#F23645"
                  : "rgba(255,255,255,0.40)",
            }}
          >
            {imScore >= 0 ? "+" : ""}
            {imScore.toFixed(2)}
          </span>
        </div>
      </div>
    </div>
  );
}

function formatPrice(price: number, symbolCode: string): string {
  if (symbolCode === "6E") return price.toFixed(5);
  if (symbolCode === "6J") return price.toFixed(6);
  if (symbolCode === "HG") return price.toFixed(4);
  return price.toFixed(2);
}
